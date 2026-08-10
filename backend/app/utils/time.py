"""Host-local wall-clock helpers for ORM defaults and business timestamps.

SQLite's CURRENT_TIMESTAMP / SQLAlchemy func.now() store UTC. This app runs on
hospital LAN machines and treats all business times as naive local datetime.now().
Always prefer these helpers over server_default=func.now().
"""
from datetime import datetime


def system_now() -> datetime:
    """Naive system-local 'now' for column defaults and stamps."""
    return datetime.now()
