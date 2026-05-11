"""
Backup verification helpers.

Every backup path (manual, mirror, snapshot, gdrive) calls
`verify_backup_artifact()` after writing the destination DB. It opens the
file fresh, runs an integrity check, hashes the bytes, and writes a sidecar
JSON file so the restore UI and the health checker can both rely on
machine-verified data instead of trusting that "the write succeeded".

Mirror uses `quick_check` (header + structure, fast). Snapshot, manual,
gdrive use `integrity_check` (full table scan). The cost difference matters
because mirror runs every 60s.
"""
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import datetime
from typing import Optional


SIDECAR_SUFFIX = ".verified.json"


def _sha256_of_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def verify_backup_artifact(
    db_path: str,
    *,
    full_check: bool = True,
    source_db_path: Optional[str] = None,
) -> dict:
    """Verify a freshly-written backup file.

    Returns a dict with the verification result. Always writes a sidecar
    `<db_path>.verified.json` capturing the result so future calls (health
    checker, restore UI) can read it without re-opening the DB.
    """
    sidecar_path = db_path + SIDECAR_SUFFIX
    written_at = datetime.datetime.utcnow().isoformat() + "Z"

    result: dict = {
        "ok": False,
        "integrity": None,
        "sha256": None,
        "size": 0,
        "written_at": written_at,
        "check_type": "integrity_check" if full_check else "quick_check",
        "error": None,
        "source_sha256": None,
    }

    try:
        if not os.path.isfile(db_path):
            result["error"] = "Backup file not found after write"
            _write_sidecar(sidecar_path, result)
            return result

        size = os.path.getsize(db_path)
        result["size"] = size
        if size == 0:
            result["error"] = "Backup file is empty"
            _write_sidecar(sidecar_path, result)
            return result

        # Magic-byte gate before opening as SQLite
        with open(db_path, "rb") as f:
            header = f.read(16)
        if not header.startswith(b"SQLite format 3"):
            result["error"] = "File is not a SQLite database (header mismatch)"
            _write_sidecar(sidecar_path, result)
            return result

        check_pragma = "integrity_check" if full_check else "quick_check"
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                row = conn.execute(f"PRAGMA {check_pragma}").fetchone()
                result["integrity"] = row[0] if row else None
            finally:
                conn.close()
        except sqlite3.Error as e:
            result["error"] = f"SQLite open/check error: {e}"
            _write_sidecar(sidecar_path, result)
            return result

        result["sha256"] = _sha256_of_file(db_path)
        if source_db_path and os.path.isfile(source_db_path):
            try:
                result["source_sha256"] = _sha256_of_file(source_db_path)
            except Exception:
                pass

        result["ok"] = (result["integrity"] == "ok")
        if not result["ok"] and result["error"] is None:
            result["error"] = f"Integrity check returned: {result['integrity']}"

    except Exception as e:
        result["error"] = f"Verification crashed: {e}"

    _write_sidecar(sidecar_path, result)
    return result


def _write_sidecar(sidecar_path: str, result: dict) -> None:
    try:
        with open(sidecar_path, "w") as f:
            json.dump(result, f, indent=2)
    except Exception:
        # Sidecar failure must not break the backup itself.
        pass


def read_sidecar(db_path: str) -> Optional[dict]:
    """Return the parsed verification sidecar for a backup file, or None."""
    sidecar_path = db_path + SIDECAR_SUFFIX
    if not os.path.isfile(sidecar_path):
        return None
    try:
        with open(sidecar_path, "r") as f:
            return json.load(f)
    except Exception:
        return None
