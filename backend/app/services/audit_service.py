"""
Audit logging service.
Provides log_action() for explicit logging in routes,
and cleanup for retention management.
"""
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.audit import AuditLog


def log_action(
    db: Session,
    user=None,
    action: str = "",
    category: str = "",
    resource_type: str = "",
    resource_id=None,
    description: str = "",
    ip_address: str = "",
    details: dict = None,
):
    """Log an audit event. Safe to call — never raises."""
    try:
        entry = AuditLog(
            user_id=user.id if user else None,
            user_name=f"{user.first_name} {user.last_name}" if user else "System",
            user_role=user.role.name if user and user.role else "",
            action=action,
            category=category,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            description=description,
            ip_address=ip_address or "",
            details=json.dumps(details, default=str) if details else None,
        )
        db.add(entry)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def cleanup_old_logs(db: Session, retention_days: int = 90):
    """Delete audit logs older than retention_days."""
    try:
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        deleted = db.query(AuditLog).filter(AuditLog.timestamp < cutoff).delete()
        db.commit()
        return deleted
    except Exception:
        db.rollback()
        return 0


def get_retention_days(db: Session) -> int:
    """Get configured retention days from hospital settings."""
    try:
        from app.models.permissions import HospitalSettings
        setting = db.query(HospitalSettings).filter(
            HospitalSettings.setting_key == "audit_retention_days"
        ).first()
        if setting:
            return int(setting.setting_value)
    except Exception:
        pass
    return 90  # Default 90 days
