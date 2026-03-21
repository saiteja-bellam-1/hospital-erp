"""Audit log viewing and management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func, desc
from typing import Optional
from datetime import datetime, date
from io import StringIO
import csv

from config.database import get_db
from app.models.user import User
from app.models.audit import AuditLog
from app.models.permissions import HospitalSettings
from app.utils.dependencies import get_current_user
from app.services.audit_service import cleanup_old_logs, get_retention_days

router = APIRouter()

ADMIN_ROLES = ['super_admin', 'hospital_admin']


def _require_admin(user):
    if not any(r in user.role_names for r in ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/logs")
async def get_audit_logs(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    user_id: Optional[int] = None,
    category: Optional[str] = None,
    action: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)

    query = db.query(AuditLog)

    if date_from:
        query = query.filter(sql_func.date(AuditLog.timestamp) >= date_from)
    if date_to:
        query = query.filter(sql_func.date(AuditLog.timestamp) <= date_to)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if category and category != 'all':
        query = query.filter(AuditLog.category == category)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action}%"))
    if search:
        q = f"%{search}%"
        query = query.filter(
            AuditLog.description.ilike(q) |
            AuditLog.user_name.ilike(q) |
            AuditLog.resource_type.ilike(q)
        )

    total = query.count()
    logs = query.order_by(desc(AuditLog.timestamp)).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "logs": [
            {
                "id": log.id,
                "timestamp": log.timestamp.isoformat() if log.timestamp else "",
                "user_id": log.user_id,
                "user_name": log.user_name,
                "user_role": log.user_role,
                "action": log.action,
                "category": log.category,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "description": log.description,
                "ip_address": log.ip_address,
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("/logs/export")
async def export_audit_logs(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    category: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)

    query = db.query(AuditLog)
    if date_from:
        query = query.filter(sql_func.date(AuditLog.timestamp) >= date_from)
    if date_to:
        query = query.filter(sql_func.date(AuditLog.timestamp) <= date_to)
    if category and category != 'all':
        query = query.filter(AuditLog.category == category)

    logs = query.order_by(desc(AuditLog.timestamp)).all()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Timestamp', 'User', 'Role', 'Action', 'Category', 'Resource', 'Resource ID', 'Description', 'IP'])
    for log in logs:
        writer.writerow([
            log.timestamp.isoformat() if log.timestamp else "",
            log.user_name, log.user_role, log.action, log.category,
            log.resource_type, log.resource_id, log.description, log.ip_address,
        ])

    output.seek(0)
    filename = f"audit_logs_{date_from or 'all'}_{date_to or 'all'}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/stats")
async def get_audit_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)

    today = date.today().isoformat()
    total = db.query(sql_func.count(AuditLog.id)).scalar()
    today_count = db.query(sql_func.count(AuditLog.id)).filter(
        sql_func.date(AuditLog.timestamp) == today
    ).scalar()

    # Category breakdown
    categories = db.query(
        AuditLog.category, sql_func.count(AuditLog.id)
    ).group_by(AuditLog.category).all()

    # Active users today
    active_users = db.query(sql_func.count(sql_func.distinct(AuditLog.user_id))).filter(
        sql_func.date(AuditLog.timestamp) == today
    ).scalar()

    retention = get_retention_days(db)

    return {
        "total_logs": total,
        "today_logs": today_count,
        "active_users_today": active_users,
        "retention_days": retention,
        "categories": {cat: count for cat, count in categories if cat},
    }


@router.get("/retention")
async def get_retention_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    return {"retention_days": get_retention_days(db)}


@router.put("/retention")
async def set_retention_config(
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    days = data.get("retention_days", 90)
    if days < 7:
        raise HTTPException(status_code=400, detail="Minimum retention is 7 days")

    setting = db.query(HospitalSettings).filter(
        HospitalSettings.setting_key == "audit_retention_days"
    ).first()

    if setting:
        setting.setting_value = str(days)
    else:
        setting = HospitalSettings(
            setting_key="audit_retention_days",
            setting_value=str(days),
            setting_category="audit",
        )
        db.add(setting)

    db.commit()
    return {"message": f"Retention set to {days} days", "retention_days": days}


@router.post("/cleanup")
async def run_cleanup(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    retention = get_retention_days(db)
    deleted = cleanup_old_logs(db, retention)
    return {"message": f"Deleted {deleted} old log entries", "deleted": deleted}
