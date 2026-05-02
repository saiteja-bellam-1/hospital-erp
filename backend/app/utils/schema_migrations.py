"""
Schema-migration tracker.

Until now, migrations were idempotent ALTER-TABLE scripts that print()-ed on
failure and let the app boot anyway. That made silent partial migrations
possible. This module:

  1. Owns a `schema_migrations` table that records every migration run with
     its outcome (success / failed) plus error message and timestamp.
  2. Provides a runner that records the result and raises on failure, so
     startup can decide to refuse to boot rather than serve a half-migrated
     DB.
  3. Exposes the run history for the admin Diagnostics endpoint.
"""
from __future__ import annotations

import datetime
from typing import Callable

from sqlalchemy import text


SCHEMA_MIGRATIONS_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    error_message TEXT,
    started_at DATETIME,
    completed_at DATETIME,
    duration_ms INTEGER
)
"""


def ensure_table(engine) -> None:
    with engine.connect() as conn:
        conn.execute(text(SCHEMA_MIGRATIONS_DDL))
        conn.commit()


def _record(engine, name: str, status: str, error: str | None,
            started_at: datetime.datetime, completed_at: datetime.datetime) -> None:
    duration_ms = int((completed_at - started_at).total_seconds() * 1000)
    with engine.connect() as conn:
        conn.execute(
            text(
                "INSERT INTO schema_migrations (name, status, error_message, started_at, completed_at, duration_ms) "
                "VALUES (:name, :status, :err, :started, :completed, :dur)"
            ),
            {
                "name": name,
                "status": status,
                "err": error,
                "started": started_at.isoformat(),
                "completed": completed_at.isoformat(),
                "dur": duration_ms,
            },
        )
        conn.commit()


def run_migration(engine, name: str, fn: Callable[[], None]) -> None:
    """Run a migration function, record the outcome, raise on failure.

    The caller decides whether to abort startup on the raised exception.
    """
    ensure_table(engine)
    started_at = datetime.datetime.utcnow()
    try:
        fn()
    except Exception as e:
        completed_at = datetime.datetime.utcnow()
        try:
            _record(engine, name, "failed", str(e)[:1000], started_at, completed_at)
        except Exception:
            pass  # Recording the failure mustn't mask the original error
        raise
    completed_at = datetime.datetime.utcnow()
    _record(engine, name, "success", None, started_at, completed_at)


def get_history(engine, limit: int = 50) -> list[dict]:
    """Return the most recent migration runs (newest first)."""
    ensure_table(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT name, status, error_message, started_at, completed_at, duration_ms "
                "FROM schema_migrations ORDER BY id DESC LIMIT :n"
            ),
            {"n": limit},
        ).fetchall()
    return [
        {
            "name": r[0],
            "status": r[1],
            "error": r[2],
            "started_at": r[3],
            "completed_at": r[4],
            "duration_ms": r[5],
        }
        for r in rows
    ]


def get_last_failure(engine) -> dict | None:
    """Latest failed migration, if any. Used by the health check."""
    ensure_table(engine)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT name, error_message, completed_at FROM schema_migrations "
                "WHERE status = 'failed' ORDER BY id DESC LIMIT 1"
            )
        ).fetchone()
    if not row:
        return None
    return {"name": row[0], "error": row[1], "completed_at": row[2]}
