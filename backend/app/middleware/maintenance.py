"""
Maintenance-mode middleware.

When enabled, non-GET requests outside the exempt allowlist return 503 so
restore operations can run without racing user writes. GETs and admin /
auth / backup / system endpoints stay reachable so the operator can still
monitor progress and abort.

The frontend axios interceptor watches for 503s with `maintenance: true` in
the body and shows a blocking modal until the API is healthy again.
"""
from __future__ import annotations
import threading
from typing import Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


_state_lock = threading.Lock()
_active = False
_reason: Optional[str] = None
_started_at: Optional[str] = None


# Endpoints that stay reachable in maintenance mode.
EXEMPT_PATH_PREFIXES = (
    "/api/auth/",
    "/api/license/",
    "/api/backup/",
    "/api/system/",
    "/uploads/",
    "/static/",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)


def enable_maintenance_mode(reason: str = "Restore in progress") -> None:
    """Block all non-exempt writes. Idempotent."""
    import datetime
    global _active, _reason, _started_at
    with _state_lock:
        _active = True
        _reason = reason
        _started_at = datetime.datetime.now().isoformat()


def disable_maintenance_mode() -> None:
    global _active, _reason, _started_at
    with _state_lock:
        _active = False
        _reason = None
        _started_at = None


def get_maintenance_state() -> dict:
    with _state_lock:
        return {"active": _active, "reason": _reason, "started_at": _started_at}


def _is_exempt(path: str) -> bool:
    return any(path == p.rstrip("/") or path.startswith(p) for p in EXEMPT_PATH_PREFIXES)


class MaintenanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        with _state_lock:
            active = _active
            reason = _reason
            started_at = _started_at

        if not active:
            return await call_next(request)

        # Always allow GETs and CORS preflights — they're read-only.
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)

        # Exempt write-paths the operator needs during maintenance.
        if _is_exempt(request.url.path):
            return await call_next(request)

        return JSONResponse(
            status_code=503,
            content={
                "maintenance": True,
                "detail": reason or "System is in maintenance mode",
                "started_at": started_at,
            },
            headers={"Retry-After": "5"},
        )
