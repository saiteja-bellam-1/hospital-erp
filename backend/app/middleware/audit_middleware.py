"""
Lightweight audit middleware — fallback logger for routes that don't have explicit log_action() calls.
Only logs POST/PUT/DELETE that succeed and aren't already logged by routes.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from datetime import datetime

# Routes that have explicit log_action() in their handlers — skip here to avoid duplicates
EXPLICIT_LOGGED = {
    "/api/auth/login", "/api/patients", "/api/appointments",
    "/api/lab/orders", "/api/admin/users", "/api/license/upload",
    "/api/backup/run", "/api/referrals",
}

SKIP_PATHS = {"/profile", "/api/license/status",
              "/api/license/machine-id", "/api/system/enabled-modules",
              "/api/audit/"}

# Simple action labels by method
METHOD_LABELS = {"POST": "created", "PUT": "updated", "DELETE": "deleted"}


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        if request.method not in ("POST", "PUT", "DELETE"):
            return response
        if response.status_code >= 400:
            return response

        path = request.url.path

        # Skip paths that are already explicitly logged or should be ignored
        for skip in SKIP_PATHS:
            if path.startswith(skip):
                return response
        for explicit in EXPLICIT_LOGGED:
            if path.startswith(explicit):
                return response

        # Fallback: log the API call with basic info
        try:
            from app.utils.auth import verify_token
            auth_header = request.headers.get("authorization", "")
            user_name = "Unknown"
            user_id = None
            user_role = ""
            if auth_header.startswith("Bearer "):
                payload = verify_token(auth_header[7:])
                if payload:
                    from config.database import get_db
                    from app.models.user import User
                    db = next(get_db())
                    user = db.query(User).filter(User.username == payload.get("sub")).first()
                    if user:
                        user_name = f"{user.first_name} {user.last_name}"
                        user_id = user.id
                        user_role = user.role.name if user.role else ""
                    db.close()

            # Build description from path
            parts = path.rstrip("/").split("/")
            resource = parts[2] if len(parts) > 2 else "resource"
            action_label = METHOD_LABELS.get(request.method, "modified")

            from config.database import get_db
            from app.models.audit import AuditLog
            db = next(get_db())
            db.add(AuditLog(
                timestamp=datetime.now(),
                user_id=user_id,
                user_name=user_name,
                user_role=user_role,
                action=f"{request.method.lower()}_{resource}",
                category=resource,
                resource_type=resource.capitalize(),
                description=f"{user_name} {action_label} {resource}",
                ip_address=request.client.host if request.client else "",
            ))
            db.commit()
            db.close()
        except Exception:
            pass

        return response
