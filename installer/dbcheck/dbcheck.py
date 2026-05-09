"""Tiny CLI used by the Inno Setup wizard to perform pre-install checks.

Compiled to ``installer/bin/dbcheck.exe`` via PyInstaller and shipped inside the
installer payload. The wizard's Pascal pages shell out to this tool and parse
its JSON-on-stdout responses.

All commands print **one** line of JSON to stdout and exit 0 on success or
non-zero on failure. A failure still emits JSON describing the error, so the
Pascal side never has to inspect exit codes alone.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile


def _emit(payload: dict, ok: bool) -> int:
    sys.stdout.write(json.dumps(payload))
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0 if ok else 1


def cmd_machine_id(_args) -> int:
    try:
        # Reuse the backend's machine-id implementation when available so the
        # ID shown by the installer matches the ID the running app reports.
        from app.utils.machine_id import get_machine_id
        return _emit({"ok": True, "machine_id": get_machine_id()}, True)
    except Exception as e:
        return _emit({"ok": False, "error": f"machine_id unavailable: {e}"}, False)


def cmd_check_db(args) -> int:
    """Probe an existing DB folder. The wizard's "use existing data folder"
    page calls this to confirm the chosen folder actually holds a working
    install.
    """
    folder = os.path.abspath(args.folder)
    db_path = os.path.join(folder, "kthealth_erp.db")
    details = {
        "folder": folder,
        "db_path": db_path,
        "exists": os.path.isfile(db_path),
        "size_bytes": 0,
        "has_users_table": False,
        "user_count": 0,
        "has_locks": False,
    }

    if not details["exists"]:
        return _emit({"ok": False, "error": "kthealth_erp.db not found in folder", "details": details}, False)

    details["size_bytes"] = os.path.getsize(db_path)

    for suffix in ("-journal", "-wal", "-shm"):
        if os.path.isfile(db_path + suffix):
            details["has_locks"] = True
            break

    if details["size_bytes"] == 0:
        return _emit({"ok": False, "error": "Database file is empty", "details": details}, False)

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            row = cur.fetchone()
            details["has_users_table"] = row is not None
            if row is not None:
                cur = conn.execute("SELECT COUNT(*) FROM users")
                details["user_count"] = cur.fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        return _emit({"ok": False, "error": f"Not a valid SQLite database: {e}", "details": details}, False)

    if not details["has_users_table"]:
        return _emit({"ok": False, "error": "Database is missing the 'users' table — not a KT HEALTH ERP database", "details": details}, False)
    if details["user_count"] == 0:
        return _emit({"ok": False, "error": "Database has no users — setup never finished on this folder", "details": details}, False)
    if details["has_locks"]:
        return _emit({"ok": False, "error": "Database has lock sidecar files (-journal/-wal/-shm). Close the running app before installing.", "details": details}, False)

    return _emit({"ok": True, "details": details}, True)


def cmd_validate_license(args) -> int:
    """Dry-run a .lic file: signature + machine-ID + expiry."""
    path = os.path.abspath(args.path)
    if not os.path.isfile(path):
        return _emit({"ok": False, "error": "License file not found"}, False)
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return _emit({"ok": False, "error": f"Cannot read license file: {e}"}, False)

    try:
        from app.services.license_service import inspect_license_file
        report = inspect_license_file(content)
    except Exception as e:
        return _emit({"ok": False, "error": f"License inspection failed: {e}"}, False)

    ok = bool(report.get("valid_signature")) and bool(report.get("machine_match"))
    return _emit({"ok": ok, "report": report}, ok)


def cmd_validate_backup_db(args) -> int:
    """Validate a single .db file the operator wants to restore from.

    The installer's "Restore from a backup database file" path calls this.
    Same shape of checks as cmd_check_db, minus the lock-file probe — the
    backup file is expected to be a static copy from another machine.
    """
    path = os.path.abspath(args.path)
    details = {
        "path": path,
        "exists": os.path.isfile(path),
        "size_bytes": 0,
        "has_users_table": False,
        "user_count": 0,
        "integrity": "unknown",
    }

    if not details["exists"]:
        return _emit({"ok": False, "error": "Backup file not found", "details": details}, False)

    details["size_bytes"] = os.path.getsize(path)
    if details["size_bytes"] == 0:
        return _emit({"ok": False, "error": "Backup file is empty", "details": details}, False)

    try:
        with open(path, "rb") as f:
            header = f.read(16)
    except Exception as e:
        return _emit({"ok": False, "error": f"Cannot read file: {e}", "details": details}, False)
    if not header.startswith(b"SQLite format 3"):
        return _emit({"ok": False, "error": "File is not a valid SQLite database", "details": details}, False)

    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            details["integrity"] = row[0] if row else "unknown"
            if details["integrity"] != "ok":
                return _emit({"ok": False,
                              "error": f"Database integrity check failed: {details['integrity']}",
                              "details": details}, False)

            row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
            details["has_users_table"] = row is not None
            if row is not None:
                details["user_count"] = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        return _emit({"ok": False, "error": f"Not a valid SQLite database: {e}", "details": details}, False)

    if not details["has_users_table"]:
        return _emit({"ok": False, "error": "Backup is missing the 'users' table — not a KT HEALTH ERP database", "details": details}, False)
    if details["user_count"] == 0:
        return _emit({"ok": False, "error": "Backup database has no users", "details": details}, False)

    return _emit({"ok": True, "details": details}, True)


def cmd_check_writable(args) -> int:
    folder = os.path.abspath(args.folder)
    try:
        os.makedirs(folder, exist_ok=True)
    except Exception as e:
        return _emit({"ok": False, "error": f"Cannot create folder: {e}"}, False)

    try:
        with tempfile.NamedTemporaryFile(prefix=".kthealth_write_", dir=folder, delete=True):
            pass
    except Exception as e:
        return _emit({"ok": False, "error": f"Folder is not writable: {e}"}, False)

    return _emit({"ok": True, "folder": folder}, True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="dbcheck")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("machine-id", help="Print the current machine ID")

    p_db = sub.add_parser("check-db", help="Validate an existing data folder")
    p_db.add_argument("folder")

    p_lic = sub.add_parser("validate-license", help="Dry-run validate a .lic file")
    p_lic.add_argument("path")

    p_w = sub.add_parser("check-writable", help="Confirm a folder is creatable + writable")
    p_w.add_argument("folder")

    p_b = sub.add_parser("validate-backup-db", help="Validate a single .db backup file")
    p_b.add_argument("path")

    args = parser.parse_args(argv)

    if args.cmd == "machine-id":
        return cmd_machine_id(args)
    if args.cmd == "check-db":
        return cmd_check_db(args)
    if args.cmd == "validate-license":
        return cmd_validate_license(args)
    if args.cmd == "check-writable":
        return cmd_check_writable(args)
    if args.cmd == "validate-backup-db":
        return cmd_validate_backup_db(args)
    return _emit({"ok": False, "error": f"unknown command {args.cmd!r}"}, False)


if __name__ == "__main__":
    sys.exit(main())
