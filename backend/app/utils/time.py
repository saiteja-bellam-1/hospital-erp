"""Host-local wall-clock helpers for ORM defaults, print formatting, and stamps.

SQLite's CURRENT_TIMESTAMP / SQLAlchemy func.now() store UTC. This app runs on
hospital LAN machines and treats all business times as naive local datetime.now().
Always prefer these helpers over server_default=func.now().

When formatting for PDFs/UI:
- timezone-aware values (or ISO strings with Z / offset) are converted to local
- naive values are treated as already-local wall clock (app storage convention)
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional


def system_now() -> datetime:
    """Naive system-local 'now' for column defaults and stamps."""
    return datetime.now()


def to_system_local(val: Any) -> Optional[datetime]:
    """Parse/normalize a date/datetime/ISO string to naive system-local wall clock."""
    if val is None or val == "":
        return None

    if isinstance(val, datetime):
        dt = val
    elif isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
    elif isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        # Already display-formatted: dd/mm/yyyy[ time]
        if len(s) >= 10 and s[2:3] == "/" and s[5:6] == "/":
            for fmt in (
                "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M",
                "%d/%m/%Y %I:%M %p",
                "%d/%m/%Y",
            ):
                try:
                    return datetime.strptime(s, fmt)
                except ValueError:
                    continue
            try:
                return datetime.strptime(s[:10], "%d/%m/%Y")
            except ValueError:
                return None
        # dd-Mon-YYYY[ HH:MM] (discharge summary style)
        for fmt in ("%d-%b-%Y %H:%M", "%d-%b-%Y"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if getattr(dt, "tzinfo", None) is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


def format_system_dt(
    val: Any,
    fmt: str = "%d/%m/%Y %I:%M %p",
    empty: str = "-",
) -> str:
    """Format a date/datetime for display in system local time."""
    if val is None or val == "":
        return empty
    try:
        dt = to_system_local(val)
        if dt is None:
            return str(val) if val else empty
        return dt.strftime(fmt)
    except Exception:
        return str(val) if val else empty


def format_bill_date(val: Any, empty: str = "") -> str:
    """Date-only (dd/mm/yyyy) for bills, invoices, and receipts — never include time."""
    if val is None or val == "":
        return empty
    s = str(val).strip()
    # Already display-formatted: "26/07/2026" or "26/07/2026 19:48:22"
    if len(s) >= 10 and s[2:3] == "/" and s[5:6] == "/":
        return s[:10]
    try:
        dt = to_system_local(val)
        if dt is not None:
            return dt.strftime("%d/%m/%Y")
    except Exception:
        pass
    # Fallback for ISO date prefixes if full parse failed
    if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-":
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            pass
    return s.split()[0] if s else empty
