"""
Schema version stamping for KT HEALTH ERP.

Stored as a single row in `system_settings` (key="schema_version", type="integer").
On fresh install we stamp the current SCHEMA_VERSION. On restore we read the
imported value and compare — refuse imports from a newer build (forward
compat is not implied), warn on older imports (they get healed by additive
migrations on startup).

Bump SCHEMA_VERSION whenever a non-additive change ships (column rename,
table rename, semantic change in existing data). Additive ALTER TABLE ADD
COLUMN does not require a bump because the on-startup migrate scripts heal
older DBs idempotently.
"""
from __future__ import annotations
import sqlite3
from typing import Optional


SCHEMA_VERSION = 1
SETTING_KEY = "schema_version"


def get_db_schema_version(db_path: str) -> Optional[int]:
    """Read schema_version from a SQLite file at `db_path`. Returns None if
    the row is missing, the table is missing, or the file isn't readable."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = conn.execute(
                "SELECT setting_value FROM system_settings WHERE setting_key = ?",
                (SETTING_KEY,),
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                return None
            try:
                return int(row[0])
            except (TypeError, ValueError):
                return None
        finally:
            conn.close()
    except Exception:
        return None


def stamp_schema_version(db_session, version: int = SCHEMA_VERSION) -> None:
    """Upsert the schema_version row using a SQLAlchemy session."""
    from app.models.system import SystemSettings

    row = (
        db_session.query(SystemSettings)
        .filter(SystemSettings.setting_key == SETTING_KEY)
        .first()
    )
    if row:
        row.setting_value = str(version)
        row.setting_type = "integer"
    else:
        db_session.add(
            SystemSettings(
                setting_key=SETTING_KEY,
                setting_value=str(version),
                setting_type="integer",
                description="Internal schema version of the application that owns this DB.",
            )
        )


def compatibility(imported_version: Optional[int]) -> dict:
    """Decide whether we can accept an imported DB at `imported_version`.

    - None      → legacy DB (pre-stamping). Allow with a warning; startup
                  migrations will heal it.
    - <current  → allow with a warning; startup migrations will heal it.
    - ==current → fine.
    - >current  → refuse. The imported DB was written by a newer build of
                  the app, possibly with columns/tables we don't know about.
    """
    if imported_version is None:
        return {
            "ok": True,
            "level": "warning",
            "message": (
                "Imported database has no schema version stamp (legacy backup). "
                "Additive migrations will run on first launch."
            ),
        }
    if imported_version > SCHEMA_VERSION:
        return {
            "ok": False,
            "level": "error",
            "message": (
                f"Imported database is from a newer application version "
                f"(schema {imported_version}, this build supports up to "
                f"{SCHEMA_VERSION}). Upgrade the application before importing."
            ),
        }
    if imported_version < SCHEMA_VERSION:
        return {
            "ok": True,
            "level": "warning",
            "message": (
                f"Imported database is from an older application version "
                f"(schema {imported_version} < {SCHEMA_VERSION}). Additive "
                f"migrations will run on first launch."
            ),
        }
    return {"ok": True, "level": "info", "message": "Schema version matches."}
