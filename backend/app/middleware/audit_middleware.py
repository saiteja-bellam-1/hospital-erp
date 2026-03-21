"""
Automatic audit logging middleware.
Logs all POST/PUT/DELETE requests with user context.
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import json

# URL patterns to action/category mapping
ROUTE_MAP = {
    ("POST", "/api/auth/login"): ("login", "auth", "User"),
    ("POST", "/api/auth/logout"): ("logout", "auth", "User"),
    ("POST", "/api/patients"): ("create_patient", "patient", "Patient"),
    ("PUT", "/api/patients/"): ("update_patient", "patient", "Patient"),
    ("POST", "/api/appointments"): ("book_appointment", "appointment", "Appointment"),
    ("PUT", "/api/appointments/"): ("update_appointment", "appointment", "Appointment"),
    ("DELETE", "/api/appointments/"): ("cancel_appointment", "appointment", "Appointment"),
    ("POST", "/api/lab/orders"): ("order_lab_tests", "lab", "LabOrder"),
    ("PUT", "/api/lab/orders/"): ("update_lab_order", "lab", "LabOrder"),
    ("POST", "/api/lab/orders/"): ("submit_lab_results", "lab", "LabReport"),
    ("POST", "/api/prescriptions"): ("create_prescription", "prescription", "Prescription"),
    ("PUT", "/api/prescriptions/"): ("update_prescription", "prescription", "Prescription"),
    ("POST", "/api/consultations"): ("create_consultation", "consultation", "Consultation"),
    ("POST", "/api/admin/users"): ("create_user", "admin", "User"),
    ("PUT", "/api/admin/users/"): ("update_user", "admin", "User"),
    ("DELETE", "/api/admin/users/"): ("deactivate_user", "admin", "User"),
    ("POST", "/api/license/upload"): ("upload_license", "admin", "License"),
    ("POST", "/api/backup/run"): ("run_backup", "admin", "Backup"),
    ("PUT", "/api/hospital/info"): ("update_hospital_info", "admin", "Hospital"),
    ("POST", "/api/referrals"): ("create_referral", "referral", "Referral"),
    ("PUT", "/api/referrals/"): ("update_referral", "referral", "Referral"),
    ("POST", "/api/lab/packages/"): ("book_package", "lab", "Package"),
}

# Skip logging these paths entirely
SKIP_PATHS = {"/api/auth/login", "/profile", "/api/setup/status", "/api/license/status",
              "/api/license/machine-id", "/api/system/enabled-modules"}


def _match_route(method, path):
    """Find matching route pattern."""
    # Exact match first
    key = (method, path)
    if key in ROUTE_MAP:
        return ROUTE_MAP[key]
    # Prefix match for parameterized routes
    for (m, pattern), mapping in ROUTE_MAP.items():
        if m == method and path.startswith(pattern):
            return mapping
    return None


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # Only log mutating requests that succeeded
        if request.method not in ("POST", "PUT", "DELETE"):
            return response
        if response.status_code >= 400:
            return response

        path = request.url.path
        if path in SKIP_PATHS:
            return response

        match = _match_route(request.method, path)
        if not match:
            return response

        action, category, resource_type = match

        # Extract user from JWT (best effort)
        user_name = "Unknown"
        user_id = None
        try:
            from app.utils.auth import verify_token
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                payload = verify_token(token)
                if payload:
                    username = payload.get("sub", "")
                    from config.database import get_db
                    from app.models.user import User
                    db = next(get_db())
                    user = db.query(User).filter(User.username == username).first()
                    if user:
                        user_name = f"{user.first_name} {user.last_name}"
                        user_id = user.id
                    db.close()
        except Exception:
            pass

        # Extract resource ID from path
        resource_id = None
        parts = path.rstrip("/").split("/")
        if len(parts) > 3:
            try:
                resource_id = parts[-1] if not parts[-1].isalpha() else parts[-2]
            except Exception:
                pass

        ip = request.client.host if request.client else ""

        # Log asynchronously (don't block response)
        try:
            from config.database import get_db
            from app.models.audit import AuditLog
            db = next(get_db())
            entry = AuditLog(
                user_id=user_id,
                user_name=user_name,
                action=action,
                category=category,
                resource_type=resource_type,
                resource_id=str(resource_id) if resource_id else None,
                description=f"{user_name} performed {action.replace('_', ' ')}",
                ip_address=ip,
            )
            db.add(entry)
            db.commit()
            db.close()
        except Exception:
            pass

        return response
