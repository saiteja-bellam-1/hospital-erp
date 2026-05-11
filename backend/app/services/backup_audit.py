"""
Backup audit event helper.

Mirror/snapshot/gdrive threads emit at most one audit event per significant
transition (location starts failing, recovers, etc.) to keep the audit log
useful without drowning it in 60-second mirror ticks.

The rate-limit is in-memory only — process restart resets the counters,
which is fine: the first run after a restart is, by definition, a
transition that should be logged.
"""
from __future__ import annotations
import time
from typing import Optional


_LAST_EVENT: dict[str, float] = {}
_MIN_INTERVAL_SECONDS = 60 * 60  # 1 event per category per hour at most


def record_location_transition(
    category: str,
    location: str,
    transition: str,
    message: str = "",
) -> None:
    """Record a backup audit event, throttled.

    category: "mirror" | "snapshot" | "gdrive"
    transition: "failed" | "recovered" | "configured" | "removed"
    """
    key = f"{category}:{location}:{transition}"
    now = time.time()
    last = _LAST_EVENT.get(key)
    if last is not None and (now - last) < _MIN_INTERVAL_SECONDS:
        return
    _LAST_EVENT[key] = now

    try:
        from config.database import SessionLocal
        from app.services.audit_service import log_action

        db = SessionLocal()
        try:
            log_action(
                db,
                None,  # System-generated event
                f"backup_{category}_{transition}",
                "admin",
                "Backup",
                None,
                f"{category} @ {location}: {transition}" + (f" — {message}" if message else ""),
                details={"category": category, "location": location, "transition": transition, "message": message},
            )
        finally:
            db.close()
    except Exception:
        # Audit failures must never break the backup pipeline.
        pass


def record_event(action: str, description: str, details: Optional[dict] = None) -> None:
    """Generic backup-audit emitter for one-off events (config change,
    retention prune, test-restore result)."""
    try:
        from config.database import SessionLocal
        from app.services.audit_service import log_action
        db = SessionLocal()
        try:
            log_action(db, None, action, "admin", "Backup", None, description, details=details or {})
        finally:
            db.close()
    except Exception:
        pass
