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
import threading


_OUT_PATH: "str | None" = None
# Exit code emitted when --timeout fires. Distinct enough that the Inno Setup
# wizard can recognise it (124 is the POSIX convention for timed-out commands).
_TIMEOUT_EXIT_CODE = 124


def _install_watchdog(seconds: float) -> None:
    """Hard-kill the process if it's still running after ``seconds``.

    The Inno Setup wizard's Pascal layer has no usable subprocess timeout, so
    dbcheck owns its own deadline. A daemon thread fires after the deadline,
    writes a timeout JSON to the --out file (so the wizard's existing
    error-display path picks it up), and ``os._exit``s with code
    ``_TIMEOUT_EXIT_CODE``. We use ``os._exit`` (not ``sys.exit``) because
    the main thread may be blocked inside a slow syscall (UNC share, AV scan)
    that wouldn't see a normal exception.
    """
    if seconds <= 0:
        return

    def _fire():
        try:
            payload = {"ok": False, "error": f"dbcheck timed out after {seconds}s"}
            data = json.dumps(payload) + "\n"
            if _OUT_PATH:
                try:
                    with open(_OUT_PATH, "w", encoding="utf-8") as f:
                        f.write(data)
                except Exception:
                    pass
            else:
                try:
                    sys.stdout.write(data)
                    sys.stdout.flush()
                except Exception:
                    pass
        finally:
            os._exit(_TIMEOUT_EXIT_CODE)

    t = threading.Timer(seconds, _fire)
    t.daemon = True
    t.start()


def _emit(payload: dict, ok: bool) -> int:
    data = json.dumps(payload)
    # When --out is supplied, write JSON to that file instead of stdout.
    # The Inno Setup wizard uses this so it doesn't have to wrap dbcheck
    # in `cmd /C ... > file 2>&1`, which is fragile under Windows
    # command-line quoting (a trailing backslash on a folder path escapes
    # the closing quote and silently breaks the redirection).
    if _OUT_PATH:
        try:
            with open(_OUT_PATH, "w", encoding="utf-8") as f:
                f.write(data)
                f.write("\n")
        except Exception:
            # Fall back to stdout if the out file is unwritable so the
            # caller still sees something.
            sys.stdout.write(data)
            sys.stdout.write("\n")
            sys.stdout.flush()
    else:
        sys.stdout.write(data)
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

    The hard failures are: no DB file, empty file, not-a-SQLite file, or
    missing core schema. WAL/SHM sidecars and an empty users table are
    surfaced as warnings (not failures) because both are legitimate states
    for a DB the operator wants to keep — a stale -wal lingers after an
    unclean shutdown, and a freshly-created DB whose setup wizard was
    interrupted has zero users but is still the right file to reuse.
    """
    # Trim accidental trailing separators before normalising. Belt-and-braces
    # — the wizard now strips them before calling us, but a hand-rolled
    # invocation (e.g. an admin debugging on the install dir) shouldn't
    # quietly target the wrong folder.
    folder_raw = (args.folder or "").rstrip("\\/").strip()
    folder = os.path.abspath(folder_raw) if folder_raw else os.path.abspath(".")

    # Prefer the current filename; fall back to the legacy one for installs
    # that pre-date the rename.
    candidates = [
        ("kthealth_erp.db", False),
        ("hospital_erp.db", True),  # legacy
    ]
    db_path = ""
    legacy = False
    for name, is_legacy in candidates:
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            db_path = path
            legacy = is_legacy
            break

    details = {
        "folder": folder,
        "db_path": db_path,
        "db_filename": os.path.basename(db_path) if db_path else "",
        "legacy_filename": legacy,
        "exists": bool(db_path),
        "size_bytes": 0,
        "has_users_table": False,
        "user_count": 0,
        "has_locks": False,
        "warnings": [],
    }

    if not db_path:
        return _emit({
            "ok": False,
            "error": "No KT HEALTH ERP database found (looked for kthealth_erp.db and legacy hospital_erp.db)",
            "details": details,
        }, False)

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

    # Hard failure: schema is wrong — definitely not a KT HEALTH ERP DB.
    if not details["has_users_table"]:
        return _emit({
            "ok": False,
            "error": "Database is missing the 'users' table — not a KT HEALTH ERP database",
            "details": details,
        }, False)

    # Soft warnings — proceed, but tell the operator.
    if legacy:
        details["warnings"].append(
            "Legacy database filename detected (hospital_erp.db). The app will continue to use it."
        )
    if details["user_count"] == 0:
        details["warnings"].append(
            "Database has the right schema but no users yet — setup may not have finished previously. The wizard will let you reuse this DB."
        )
    if details["has_locks"]:
        details["warnings"].append(
            "A -journal/-wal/-shm sidecar is present. If the app is running, close it before reinstalling; otherwise the sidecar is harmless."
        )

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
        # Use the SQLAlchemy-free helper module so dbcheck.exe (which excludes
        # sqlalchemy in its PyInstaller spec) doesn't crash on import.
        from app.services.license_inspect import inspect_license_file
        report = inspect_license_file(content)
    except Exception as e:
        return _emit({"ok": False, "error": f"License inspection failed: {e}"}, False)

    if not report.get("valid_signature"):
        return _emit({
            "ok": False,
            "error": report.get("error") or "Invalid license signature.",
            "report": report,
        }, False)

    if not report.get("machine_match"):
        lic_mid = report.get("license_machine_id") or "(none)"
        cur_mid = report.get("current_machine_id") or "(unknown)"
        return _emit({
            "ok": False,
            "error": (
                f"License is bound to machine '{lic_mid}' but this machine is "
                f"'{cur_mid}'. Ask your vendor to re-issue the license for this machine."
            ),
            "report": report,
        }, False)

    # Surface expiry at the top level so the Pascal wizard can highlight it
    # without parsing the nested report object. We still return ok=True for
    # expired/expiring licenses — the operator may have a renewal in hand and
    # we shouldn't block install; the wizard shows the status in colour.
    status = report.get("status") or ""
    days_remaining = report.get("days_remaining")
    return _emit({
        "ok": True,
        "status": status,
        "days_remaining": days_remaining,
        "expires_at": report.get("expires_at"),
        "report": report,
    }, True)


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


def cmd_validate_users_csv(args) -> int:
    """Validate the optional install-time users CSV.

    The runtime bootstrap (`bootstrap_from_seed`) re-validates with the live
    DB before applying, so this command is the operator-facing "is my file
    well-formed" check. No DB is available yet at install time, so we only
    catch structural problems: bad header, missing fields, disallowed roles,
    short passwords, within-file dupes, length caps.
    """
    path = os.path.abspath(args.path)
    if not os.path.isfile(path):
        return _emit({"ok": False, "error": "CSV file not found", "path": path}, False)

    try:
        # parse_and_validate is the sqlalchemy-free half of user_csv_import —
        # safe to import here even though dbcheck.spec excludes sqlalchemy.
        from app.services.user_csv_import import (
            INSTALLER_ALLOWED_ROLES,
            parse_and_validate_file,
        )
    except Exception as e:
        return _emit({"ok": False, "error": f"Validator unavailable: {e}"}, False)

    reserved_users = [u for u in (args.reserved_username or []) if u]
    reserved_emails = [e for e in (args.reserved_email or []) if e]
    rows, errors = parse_and_validate_file(
        path,
        allowed_roles=INSTALLER_ALLOWED_ROLES,
        existing_usernames=reserved_users or None,
        existing_emails=reserved_emails or None,
    )

    payload = {
        "path": path,
        "row_count": len(rows),
        "errors": [e.as_dict() for e in errors],
    }
    if errors:
        first = errors[0]
        line_hint = f" (line {first.line_no})" if first.line_no else ""
        payload["error"] = f"{first.message}{line_hint}"
        payload["ok"] = False
        return _emit(payload, False)

    payload["ok"] = True
    return _emit(payload, True)


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
    parser.add_argument(
        "--out",
        default=None,
        help="Write JSON result to this file instead of stdout. Used by the Inno Setup wizard to avoid cmd-shell quoting hazards.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0,
        help="Hard-kill dbcheck if it hasn't finished within N seconds. "
             "Emits a timeout JSON to --out and exits 124. Used by the wizard "
             "so a hung UNC share or AV scan can't freeze the install.",
    )
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

    p_u = sub.add_parser("validate-users-csv", help="Validate an install-time users CSV")
    p_u.add_argument("path")
    p_u.add_argument(
        "--reserved-username",
        action="append",
        default=[],
        help="Reject the CSV if a row uses this username (e.g. the admin chosen "
             "on the previous wizard page). Repeatable.",
    )
    p_u.add_argument(
        "--reserved-email",
        action="append",
        default=[],
        help="Reject the CSV if a row uses this email. Repeatable.",
    )

    args = parser.parse_args(argv)

    global _OUT_PATH
    if getattr(args, "out", None):
        _OUT_PATH = args.out

    # Arm the watchdog AFTER _OUT_PATH is set so a timeout payload still lands
    # in the file the wizard reads.
    _install_watchdog(getattr(args, "timeout", 0) or 0)

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
    if args.cmd == "validate-users-csv":
        return cmd_validate_users_csv(args)
    return _emit({"ok": False, "error": f"unknown command {args.cmd!r}"}, False)


if __name__ == "__main__":
    sys.exit(main())
