"""Physiotherapy clinic API — catalog, scheduling, packages, sessions, reports.

Standalone module (`physiotherapy` license feature). Reuses Patient + Bill/Payment/PDF.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from config.database import get_db
from app.models.user import User
from app.models.patient import Patient
from app.models.hospital import Hospital
from app.models.billing import Bill, BillItem, Payment
from app.models.physiotherapy import (
    PhysioService,
    PhysioPackageTemplate,
    PhysioPatientPackage,
    PhysioPackageLedger,
    PhysioTherapistAvailability,
    PhysioTherapistSpecialSchedule,
    PhysioAppointment,
)
from app.utils.auth import Modules
from app.utils.dependencies import require_feature_permission, require_feature_permission_any
from app.services.audit_service import log_action
from app.utils.pdf_service import pdf_service
from app.utils.pdf_settings import pdf_gen_kwargs
from app.utils.time import system_now

router = APIRouter()

SESSION_TYPES = ("assessment", "treatment", "review")
DEFAULT_WEEKLY = {
    "monday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
    "tuesday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
    "wednesday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
    "thursday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
    "friday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
    "saturday": {"start_time": "09:00", "end_time": "13:00", "enabled": True},
    "sunday": {"start_time": "09:00", "end_time": "13:00", "enabled": False},
}


def _hospital_id(user: User) -> int:
    if not user.hospital_id:
        raise HTTPException(status_code=400, detail="User is not assigned to a hospital")
    return user.hospital_id


def _get_patient(db: Session, patient_id: int, hospital_id: int) -> Patient:
    p = db.query(Patient).filter(
        Patient.id == patient_id, Patient.hospital_id == hospital_id
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return p


def _therapist_users(db: Session, hospital_id: int) -> List[User]:
    users = db.query(User).filter(
        User.hospital_id == hospital_id, User.is_active == True  # noqa: E712
    ).all()
    return [u for u in users if "physiotherapist" in set(u.role_names or [])]


def _next_bill_number(db: Session, prefix_kind: str = "PHY") -> str:
    today_str = datetime.now().strftime("%Y%m%d")
    prefix = f"{prefix_kind}-{today_str}-"
    last = (
        db.query(Bill).filter(Bill.bill_number.like(f"{prefix}%"))
        .order_by(Bill.id.desc()).first()
    )
    seq = (int(last.bill_number.split("-")[-1]) + 1) if last else 1
    return f"{prefix}{seq:04d}"


def _next_payment_number(db: Session) -> str:
    today_str = datetime.now().strftime("%Y%m%d")
    prefix = f"PAY-{today_str}-"
    last = (
        db.query(Payment).filter(Payment.payment_number.like(f"{prefix}%"))
        .order_by(Payment.id.desc()).first()
    )
    seq = (int(last.payment_number.split("-")[-1]) + 1) if last else 1
    return f"{prefix}{seq:04d}"


def _next_appt_number(db: Session) -> str:
    today_str = datetime.now().strftime("%Y%m%d")
    prefix = f"PT-{today_str}-"
    last = (
        db.query(PhysioAppointment)
        .filter(PhysioAppointment.appointment_number.like(f"{prefix}%"))
        .order_by(PhysioAppointment.id.desc()).first()
    )
    seq = (int(last.appointment_number.split("-")[-1]) + 1) if last else 1
    return f"{prefix}{seq:04d}"


def _expire_packages(db: Session, hospital_id: int) -> None:
    now = system_now()
    rows = db.query(PhysioPatientPackage).filter(
        PhysioPatientPackage.hospital_id == hospital_id,
        PhysioPatientPackage.status == "active",
        PhysioPatientPackage.expires_at.isnot(None),
        PhysioPatientPackage.expires_at < now,
    ).all()
    for pkg in rows:
        pkg.status = "expired"


def _serialize_service(s: PhysioService) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "code": s.code,
        "default_price": float(s.default_price or 0),
        "duration_minutes": s.duration_minutes or 30,
        "description": s.description,
        "is_active": bool(s.is_active),
    }


def _serialize_appt(a: PhysioAppointment) -> dict:
    patient, therapist, service = a.patient, a.therapist, a.service
    return {
        "id": a.id,
        "appointment_number": a.appointment_number,
        "patient_id": a.patient_id,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
        "patient_phone": patient.primary_phone if patient else None,
        "patient_uuid": patient.patient_id if patient else None,
        "therapist_id": a.therapist_id,
        "therapist_name": f"{therapist.first_name} {therapist.last_name}" if therapist else None,
        "service_id": a.service_id,
        "service_name": service.name if service else None,
        "package_id": a.package_id,
        "bill_id": a.bill_id,
        "appointment_date": a.appointment_date.isoformat() if a.appointment_date else None,
        "appointment_time": a.appointment_time.strftime("%H:%M") if a.appointment_time else None,
        "duration_minutes": a.duration_minutes,
        "session_type": a.session_type,
        "status": a.status,
        "is_walk_in": bool(a.is_walk_in),
        "referral_source": a.referral_source,
        "chief_complaint": a.chief_complaint,
        "notes": a.notes,
        "session_note": a.session_note,
        "next_appointment_suggested": (
            a.next_appointment_suggested.isoformat() if a.next_appointment_suggested else None
        ),
        "checked_in_at": a.checked_in_at.isoformat() if a.checked_in_at else None,
        "started_at": a.started_at.isoformat() if a.started_at else None,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _serialize_package(pkg: PhysioPatientPackage) -> dict:
    return {
        "id": pkg.id,
        "patient_id": pkg.patient_id,
        "patient_name": (
            f"{pkg.patient.first_name} {pkg.patient.last_name}" if pkg.patient else None
        ),
        "template_id": pkg.template_id,
        "service_id": pkg.service_id,
        "service_name": pkg.service.name if pkg.service else None,
        "name": pkg.name,
        "sessions_total": pkg.sessions_total,
        "sessions_remaining": pkg.sessions_remaining,
        "price_paid": float(pkg.price_paid or 0),
        "purchased_at": pkg.purchased_at.isoformat() if pkg.purchased_at else None,
        "expires_at": pkg.expires_at.isoformat() if pkg.expires_at else None,
        "status": pkg.status,
        "bill_id": pkg.bill_id,
        "notes": pkg.notes,
    }


def _create_physio_bill(
    db: Session,
    *,
    patient: Patient,
    hospital_id: int,
    user: User,
    item_name: str,
    item_code: str,
    unit_price: float,
    quantity: int = 1,
    notes: Optional[str] = None,
    referred_by: Optional[str] = None,
    payment_method: Optional[str] = None,
    mark_paid: bool = False,
) -> Bill:
    line_total = round(float(unit_price) * quantity, 2)
    bill_number = _next_bill_number(db)
    status = "paid" if mark_paid else ("pending" if line_total > 0 else "paid")
    bill = Bill(
        bill_number=bill_number,
        patient_id=patient.id,
        bill_type="physiotherapy",
        bill_subtype="final",
        reference_id=0,
        subtotal=line_total,
        tax_amount=0.0,
        discount_amount=0.0,
        total_amount=line_total,
        status=status,
        bill_date=datetime.now(),
        created_by_id=user.id,
        hospital_id=hospital_id,
        notes=notes,
        referred_by=(referred_by or "").strip() or None,
    )
    db.add(bill)
    db.flush()
    db.add(BillItem(
        bill_id=bill.id,
        item_type="physiotherapy",
        item_name=item_name,
        item_code=item_code,
        quantity=quantity,
        unit_price=float(unit_price),
        total_price=line_total,
    ))
    if mark_paid and line_total > 0:
        db.add(Payment(
            payment_number=_next_payment_number(db),
            bill_id=bill.id,
            amount_paid=line_total,
            payment_method_name=(payment_method or "cash"),
            payment_date=datetime.now(),
            received_by_id=user.id,
            notes=f"Physio auto-collected ({bill_number})",
        ))
    return bill


def _parse_time(value: Optional[str]) -> Optional[time]:
    if not value:
        return None
    parts = value.strip().split(":")
    return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


def _has_conflict(
    db: Session,
    therapist_id: int,
    appt_date: date,
    appt_time: Optional[time],
    duration: int,
    exclude_id: Optional[int] = None,
) -> bool:
    if not appt_time:
        return False
    q = db.query(PhysioAppointment).filter(
        PhysioAppointment.therapist_id == therapist_id,
        PhysioAppointment.appointment_date == appt_date,
        PhysioAppointment.status.notin_(("cancelled", "no_show")),
    )
    if exclude_id:
        q = q.filter(PhysioAppointment.id != exclude_id)
    start_dt = datetime.combine(appt_date, appt_time)
    end_dt = start_dt + timedelta(minutes=duration or 30)
    for other in q.all():
        if not other.appointment_time:
            continue
        o_start = datetime.combine(appt_date, other.appointment_time)
        o_end = o_start + timedelta(minutes=other.duration_minutes or 30)
        if start_dt < o_end and end_dt > o_start:
            return True
    return False


# ── Catalog ──────────────────────────────────────────────────────────────────

class ServiceIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    code: Optional[str] = Field(None, max_length=50)
    default_price: float = Field(0.0, ge=0)
    duration_minutes: int = Field(30, ge=5, le=240)
    description: Optional[str] = None
    is_active: bool = True


@router.get("/services")
async def list_services(
    include_inactive: bool = False,
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "view_physio")),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    q = db.query(PhysioService).filter(PhysioService.hospital_id == hid)
    if not include_inactive:
        q = q.filter(PhysioService.is_active == True)  # noqa: E712
    return [_serialize_service(s) for s in q.order_by(PhysioService.name).all()]


@router.post("/services", status_code=201)
async def create_service(
    data: ServiceIn,
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "manage_catalog")),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    svc = PhysioService(
        hospital_id=hid,
        name=data.name.strip(),
        code=data.code,
        default_price=data.default_price,
        duration_minutes=data.duration_minutes,
        description=data.description,
        is_active=data.is_active,
        created_by_id=current_user.id,
    )
    db.add(svc)
    db.commit()
    db.refresh(svc)
    log_action(db, current_user, "create_physio_service", "physiotherapy",
               "PhysioService", svc.id, f"Created service '{svc.name}'")
    return _serialize_service(svc)


@router.patch("/services/{service_id}")
async def update_service(
    service_id: int,
    data: ServiceIn,
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "manage_catalog")),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    svc = db.query(PhysioService).filter(
        PhysioService.id == service_id, PhysioService.hospital_id == hid
    ).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    svc.name = data.name.strip()
    svc.code = data.code
    svc.default_price = data.default_price
    svc.duration_minutes = data.duration_minutes
    svc.description = data.description
    svc.is_active = data.is_active
    db.commit()
    db.refresh(svc)
    return _serialize_service(svc)


@router.delete("/services/{service_id}", status_code=204)
async def deactivate_service(
    service_id: int,
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "manage_catalog")),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    svc = db.query(PhysioService).filter(
        PhysioService.id == service_id, PhysioService.hospital_id == hid
    ).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    svc.is_active = False
    db.commit()
    return None


# ── Package templates ─────────────────────────────────────────────────────────

class PackageTemplateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    service_id: Optional[int] = None
    session_count: int = Field(10, ge=1, le=500)
    price: float = Field(..., ge=0)
    validity_days: int = Field(90, ge=1, le=3650)
    description: Optional[str] = None
    is_active: bool = True


@router.get("/package-templates")
async def list_package_templates(
    include_inactive: bool = False,
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "view_physio")),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    q = db.query(PhysioPackageTemplate).options(
        joinedload(PhysioPackageTemplate.service)
    ).filter(PhysioPackageTemplate.hospital_id == hid)
    if not include_inactive:
        q = q.filter(PhysioPackageTemplate.is_active == True)  # noqa: E712
    rows = q.order_by(PhysioPackageTemplate.name).all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "service_id": t.service_id,
            "service_name": t.service.name if t.service else None,
            "session_count": t.session_count,
            "price": float(t.price or 0),
            "validity_days": t.validity_days,
            "description": t.description,
            "is_active": bool(t.is_active),
        }
        for t in rows
    ]


@router.post("/package-templates", status_code=201)
async def create_package_template(
    data: PackageTemplateIn,
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "manage_packages")),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    if data.service_id:
        svc = db.query(PhysioService).filter(
            PhysioService.id == data.service_id, PhysioService.hospital_id == hid
        ).first()
        if not svc:
            raise HTTPException(status_code=404, detail="Service not found")
    tmpl = PhysioPackageTemplate(
        hospital_id=hid,
        name=data.name.strip(),
        service_id=data.service_id,
        session_count=data.session_count,
        price=data.price,
        validity_days=data.validity_days,
        description=data.description,
        is_active=data.is_active,
        created_by_id=current_user.id,
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return {"id": tmpl.id, "name": tmpl.name}


@router.patch("/package-templates/{template_id}")
async def update_package_template(
    template_id: int,
    data: PackageTemplateIn,
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "manage_packages")),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    tmpl = db.query(PhysioPackageTemplate).filter(
        PhysioPackageTemplate.id == template_id,
        PhysioPackageTemplate.hospital_id == hid,
    ).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Package template not found")
    tmpl.name = data.name.strip()
    tmpl.service_id = data.service_id
    tmpl.session_count = data.session_count
    tmpl.price = data.price
    tmpl.validity_days = data.validity_days
    tmpl.description = data.description
    tmpl.is_active = data.is_active
    db.commit()
    return {"id": tmpl.id, "name": tmpl.name}


# ── Sell / list patient packages ──────────────────────────────────────────────

class SellPackageIn(BaseModel):
    patient_id: int
    template_id: int
    payment_method: str = "cash"
    notes: Optional[str] = None
    referred_by: Optional[str] = None


@router.post("/packages/sell", status_code=201)
async def sell_package(
    data: SellPackageIn,
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "manage_packages")),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    patient = _get_patient(db, data.patient_id, hid)
    tmpl = db.query(PhysioPackageTemplate).options(
        joinedload(PhysioPackageTemplate.service)
    ).filter(
        PhysioPackageTemplate.id == data.template_id,
        PhysioPackageTemplate.hospital_id == hid,
        PhysioPackageTemplate.is_active == True,  # noqa: E712
    ).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Package template not found or inactive")

    bill = _create_physio_bill(
        db,
        patient=patient,
        hospital_id=hid,
        user=current_user,
        item_name=f"Package: {tmpl.name}",
        item_code=f"PKG-{tmpl.id}",
        unit_price=float(tmpl.price or 0),
        notes=data.notes,
        referred_by=data.referred_by,
        payment_method=data.payment_method,
        mark_paid=True,
    )
    expires_at = system_now() + timedelta(days=tmpl.validity_days or 90)
    pkg = PhysioPatientPackage(
        hospital_id=hid,
        patient_id=patient.id,
        template_id=tmpl.id,
        service_id=tmpl.service_id,
        name=tmpl.name,
        sessions_total=tmpl.session_count,
        sessions_remaining=tmpl.session_count,
        price_paid=float(tmpl.price or 0),
        expires_at=expires_at,
        status="active",
        bill_id=bill.id,
        sold_by_id=current_user.id,
        notes=data.notes,
    )
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    log_action(db, current_user, "sell_physio_package", "physiotherapy",
               "PhysioPatientPackage", pkg.id, f"Sold package '{pkg.name}'")
    return {**_serialize_package(pkg), "bill_id": bill.id, "bill_number": bill.bill_number}


@router.get("/packages")
async def list_patient_packages(
    patient_id: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "view_physio")),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    _expire_packages(db, hid)
    db.commit()
    q = db.query(PhysioPatientPackage).options(
        joinedload(PhysioPatientPackage.patient),
        joinedload(PhysioPatientPackage.service),
    ).filter(PhysioPatientPackage.hospital_id == hid)
    if patient_id:
        q = q.filter(PhysioPatientPackage.patient_id == patient_id)
    if status_filter:
        q = q.filter(PhysioPatientPackage.status == status_filter)
    return [_serialize_package(p) for p in q.order_by(PhysioPatientPackage.id.desc()).limit(200).all()]


@router.get("/packages/patient/{patient_id}/active")
async def active_packages_for_patient(
    patient_id: int,
    service_id: Optional[int] = None,
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "view_physio")),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    _expire_packages(db, hid)
    db.commit()
    _get_patient(db, patient_id, hid)
    q = db.query(PhysioPatientPackage).options(
        joinedload(PhysioPatientPackage.service),
        joinedload(PhysioPatientPackage.patient),
    ).filter(
        PhysioPatientPackage.hospital_id == hid,
        PhysioPatientPackage.patient_id == patient_id,
        PhysioPatientPackage.status == "active",
        PhysioPatientPackage.sessions_remaining > 0,
    )
    pkgs = q.order_by(PhysioPatientPackage.expires_at.asc().nullslast()).all()
    if service_id:
        pkgs = [p for p in pkgs if p.service_id is None or p.service_id == service_id]
    return [_serialize_package(p) for p in pkgs]


# ── Therapists + availability ─────────────────────────────────────────────────

@router.get("/therapists")
async def list_therapists(
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "view_physio")),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    return [
        {
            "id": u.id,
            "full_name": f"{u.first_name} {u.last_name}",
            "username": u.username,
            "specialization": getattr(u, "specialization", None),
        }
        for u in _therapist_users(db, hid)
    ]


class AvailabilityIn(BaseModel):
    weekly_schedule: Optional[dict] = None
    default_session_duration: int = Field(30, ge=5, le=240)
    buffer_minutes: int = Field(0, ge=0, le=60)
    max_advance_booking_days: int = Field(30, ge=1, le=365)


@router.get("/therapists/{therapist_id}/availability")
async def get_therapist_availability(
    therapist_id: int,
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "view_physio")),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    row = db.query(PhysioTherapistAvailability).filter(
        PhysioTherapistAvailability.therapist_id == therapist_id,
        PhysioTherapistAvailability.hospital_id == hid,
    ).first()
    if not row:
        return {
            "therapist_id": therapist_id,
            "weekly_schedule": DEFAULT_WEEKLY,
            "default_session_duration": 30,
            "buffer_minutes": 0,
            "max_advance_booking_days": 30,
            "special_schedules": [],
        }
    specials = [
        {
            "id": s.id,
            "date": s.date.isoformat(),
            "schedule_type": s.schedule_type,
            "start_time": s.start_time.strftime("%H:%M") if s.start_time else None,
            "end_time": s.end_time.strftime("%H:%M") if s.end_time else None,
            "title": s.title,
            "description": s.description,
        }
        for s in (row.special_schedules or [])
    ]
    return {
        "therapist_id": therapist_id,
        "weekly_schedule": row.weekly_schedule or DEFAULT_WEEKLY,
        "default_session_duration": row.default_session_duration,
        "buffer_minutes": row.buffer_minutes,
        "max_advance_booking_days": row.max_advance_booking_days,
        "special_schedules": specials,
    }


@router.put("/therapists/{therapist_id}/availability")
async def upsert_therapist_availability(
    therapist_id: int,
    data: AvailabilityIn,
    current_user: User = Depends(
        require_feature_permission(Modules.PHYSIOTHERAPY, "manage_therapist_schedules")
    ),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    therapist = db.query(User).filter(User.id == therapist_id, User.hospital_id == hid).first()
    if not therapist:
        raise HTTPException(status_code=404, detail="Therapist not found")
    row = db.query(PhysioTherapistAvailability).filter(
        PhysioTherapistAvailability.therapist_id == therapist_id,
        PhysioTherapistAvailability.hospital_id == hid,
    ).first()
    if not row:
        row = PhysioTherapistAvailability(
            hospital_id=hid,
            therapist_id=therapist_id,
            weekly_schedule=data.weekly_schedule or DEFAULT_WEEKLY,
        )
        db.add(row)
    if data.weekly_schedule is not None:
        row.weekly_schedule = data.weekly_schedule
    row.default_session_duration = data.default_session_duration
    row.buffer_minutes = data.buffer_minutes
    row.max_advance_booking_days = data.max_advance_booking_days
    db.commit()
    return {"ok": True}


class SpecialScheduleIn(BaseModel):
    date: date
    schedule_type: str
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None


@router.post("/therapists/{therapist_id}/special-schedules", status_code=201)
async def add_special_schedule(
    therapist_id: int,
    data: SpecialScheduleIn,
    current_user: User = Depends(
        require_feature_permission(Modules.PHYSIOTHERAPY, "manage_therapist_schedules")
    ),
    db: Session = Depends(get_db),
):
    if data.schedule_type not in ("holiday", "leave", "modified_hours"):
        raise HTTPException(status_code=400, detail="Invalid schedule_type")
    hid = _hospital_id(current_user)
    avail = db.query(PhysioTherapistAvailability).filter(
        PhysioTherapistAvailability.therapist_id == therapist_id,
        PhysioTherapistAvailability.hospital_id == hid,
    ).first()
    if not avail:
        avail = PhysioTherapistAvailability(
            hospital_id=hid, therapist_id=therapist_id, weekly_schedule=DEFAULT_WEEKLY
        )
        db.add(avail)
        db.flush()
    row = PhysioTherapistSpecialSchedule(
        availability_id=avail.id,
        therapist_id=therapist_id,
        date=data.date,
        schedule_type=data.schedule_type,
        title=data.title,
        description=data.description,
        start_time=_parse_time(data.start_time),
        end_time=_parse_time(data.end_time),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id}


# ── Appointments ──────────────────────────────────────────────────────────────

class AppointmentIn(BaseModel):
    patient_id: int
    therapist_id: int
    service_id: Optional[int] = None
    appointment_date: date
    appointment_time: Optional[str] = None
    duration_minutes: Optional[int] = Field(None, ge=5, le=240)
    session_type: str = "treatment"
    referral_source: Optional[str] = None
    chief_complaint: Optional[str] = None
    notes: Optional[str] = None
    is_walk_in: bool = False
    package_id: Optional[int] = None
    # none | package | a_la_carte — charge/reserve before the session
    billing_mode: str = "none"
    unit_price: Optional[float] = Field(None, ge=0)
    payment_method: Optional[str] = "cash"
    mark_paid: bool = True


class CompleteSessionIn(BaseModel):
    session_note: Optional[str] = None
    next_appointment_suggested: Optional[date] = None
    package_id: Optional[int] = None
    use_package: bool = True
    override_reason: Optional[str] = None
    unit_price: Optional[float] = Field(None, ge=0)
    payment_method: Optional[str] = None
    mark_paid: bool = False


def _ledger_reserved_for_appt(db: Session, appointment_id: int) -> bool:
    row = db.query(PhysioPackageLedger).filter(
        PhysioPackageLedger.appointment_id == appointment_id,
        PhysioPackageLedger.delta < 0,
        PhysioPackageLedger.reason.in_(("session_booked", "session_complete")),
    ).first()
    return row is not None


def _reserve_package(
    db: Session,
    *,
    pkg: PhysioPatientPackage,
    appointment: PhysioAppointment,
    user: User,
    service_id: Optional[int],
    override_reason: Optional[str] = None,
    reason: str = "session_booked",
) -> None:
    if pkg.status != "active" and not override_reason:
        raise HTTPException(status_code=400, detail=f"Package is {pkg.status}")
    if pkg.service_id and service_id and pkg.service_id != service_id:
        if not override_reason:
            raise HTTPException(
                status_code=400,
                detail="Package is for a different service — provide override_reason",
            )
    if pkg.sessions_remaining <= 0:
        if not override_reason:
            raise HTTPException(status_code=400, detail="No sessions remaining on this package")
    else:
        pkg.sessions_remaining -= 1
        if pkg.sessions_remaining <= 0:
            pkg.status = "exhausted"
            pkg.sessions_remaining = 0
    db.add(PhysioPackageLedger(
        package_id=pkg.id,
        appointment_id=appointment.id,
        delta=-1,
        reason=reason,
        override_reason=override_reason,
        created_by_id=user.id,
    ))
    appointment.package_id = pkg.id


def _restore_package_if_reserved(
    db: Session,
    *,
    appt: PhysioAppointment,
    user: User,
    reason: str,
) -> None:
    if not appt.package_id:
        return
    reserved = db.query(PhysioPackageLedger).filter(
        PhysioPackageLedger.appointment_id == appt.id,
        PhysioPackageLedger.package_id == appt.package_id,
        PhysioPackageLedger.delta < 0,
        PhysioPackageLedger.reason == "session_booked",
    ).first()
    if not reserved:
        return
    # Already restored?
    restored = db.query(PhysioPackageLedger).filter(
        PhysioPackageLedger.appointment_id == appt.id,
        PhysioPackageLedger.delta > 0,
        PhysioPackageLedger.reason.in_(("booking_cancelled", "booking_no_show")),
    ).first()
    if restored:
        return
    pkg = db.query(PhysioPatientPackage).filter(
        PhysioPatientPackage.id == appt.package_id
    ).first()
    if not pkg:
        return
    pkg.sessions_remaining = (pkg.sessions_remaining or 0) + 1
    if pkg.status == "exhausted":
        pkg.status = "active"
    db.add(PhysioPackageLedger(
        package_id=pkg.id,
        appointment_id=appt.id,
        delta=1,
        reason=reason,
        created_by_id=user.id,
    ))


def _appointments_query(
    db: Session,
    current_user: User,
    *,
    on_date: Optional[date] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    therapist_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    patient_id: Optional[int] = None,
):
    hid = _hospital_id(current_user)
    q = db.query(PhysioAppointment).options(
        joinedload(PhysioAppointment.patient),
        joinedload(PhysioAppointment.therapist),
        joinedload(PhysioAppointment.service),
    ).filter(PhysioAppointment.hospital_id == hid)
    if on_date:
        q = q.filter(PhysioAppointment.appointment_date == on_date)
    else:
        if date_from:
            q = q.filter(PhysioAppointment.appointment_date >= date_from)
        if date_to:
            q = q.filter(PhysioAppointment.appointment_date <= date_to)
    if therapist_id:
        q = q.filter(PhysioAppointment.therapist_id == therapist_id)
    if status_filter:
        q = q.filter(PhysioAppointment.status == status_filter)
    if patient_id:
        q = q.filter(PhysioAppointment.patient_id == patient_id)
    roles = set(current_user.role_names or [])
    if "physiotherapist" in roles and not roles.intersection(
        {"super_admin", "hospital_admin", "receptionist", "frontdesk", "billing_admin"}
    ):
        q = q.filter(PhysioAppointment.therapist_id == current_user.id)
    return q.order_by(
        PhysioAppointment.appointment_date.asc(),
        PhysioAppointment.appointment_time.asc().nullslast(),
    )


@router.get("/appointments")
async def list_appointments(
    on_date: Optional[date] = Query(None, alias="date"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    therapist_id: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    patient_id: Optional[int] = None,
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "view_physio")),
    db: Session = Depends(get_db),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be on or before date_to")
    q = _appointments_query(
        db,
        current_user,
        on_date=on_date,
        date_from=date_from,
        date_to=date_to,
        therapist_id=therapist_id,
        status_filter=status_filter,
        patient_id=patient_id,
    )
    rows = q.limit(2000).all()
    return [_serialize_appt(a) for a in rows]


@router.get("/appointments/export.pdf")
async def export_appointments_pdf(
    on_date: Optional[date] = Query(None, alias="date"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    therapist_id: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    patient_id: Optional[int] = None,
    include_header: Optional[bool] = Query(None),
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "view_physio")),
    db: Session = Depends(get_db),
):
    """PDF download of physiotherapy appointments for the selected date range."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must be on or before date_to")
    if not on_date and not date_from and not date_to:
        on_date = date.today()
    q = _appointments_query(
        db,
        current_user,
        on_date=on_date,
        date_from=date_from,
        date_to=date_to,
        therapist_id=therapist_id,
        status_filter=status_filter,
        patient_id=patient_id,
    )
    appointments = q.limit(5000).all()
    rows = []
    for a in appointments:
        s = _serialize_appt(a)
        rows.append({
            "date": s.get("appointment_date") or "",
            "time": s.get("appointment_time") or "",
            "patient_name": s.get("patient_name") or "",
            "phone": s.get("patient_phone") or "",
            "therapist_name": s.get("therapist_name") or "",
            "service": s.get("service_name") or s.get("session_type") or "",
            "status": s.get("status") or "",
            "billing": (
                "Package" if s.get("package_id")
                else ("Billed" if s.get("bill_id") else "")
            ),
            "appt_number": s.get("appointment_number") or "",
        })

    hid = _hospital_id(current_user)
    h = db.query(Hospital).filter(Hospital.id == hid).first()
    hospital_info = {
        "name": h.name if h else "Hospital",
        "address": getattr(h, "address", "") if h else "",
        "phone": getattr(h, "phone", "") if h else "",
        "email": getattr(h, "email", "") if h else "",
        "logo_url": getattr(h, "logo_url", "") if h else "",
        "hospital_subname": getattr(h, "hospital_subname", "") if h else "",
    }
    if on_date:
        period = {"from": on_date.isoformat(), "to": on_date.isoformat()}
        filename = f"physio_appointments_{on_date.isoformat()}.pdf"
    else:
        period = {
            "from": date_from.isoformat() if date_from else "—",
            "to": date_to.isoformat() if date_to else "—",
        }
        filename = f"physio_appointments_{date_from or 'all'}_to_{date_to or 'all'}.pdf"

    cols = [
        {"key": "date", "label": "Date", "width": 1.4},
        {"key": "time", "label": "Time", "width": 1},
        {"key": "patient_name", "label": "Patient", "width": 2.4},
        {"key": "phone", "label": "Phone", "width": 1.5},
        {"key": "therapist_name", "label": "Therapist", "width": 2},
        {"key": "service", "label": "Service", "width": 2},
        {"key": "status", "label": "Status", "width": 1.3},
        {"key": "billing", "label": "Billing", "width": 1.1},
        {"key": "appt_number", "label": "Appt #", "width": 1.6},
    ]
    buf = pdf_service.generate_pharmacy_report_pdf(
        title="PHYSIOTHERAPY APPOINTMENTS",
        period=period,
        columns=cols,
        rows=rows,
        hospital_info=hospital_info,
        meta={"Generated": system_now().strftime("%Y-%m-%d %H:%M")},
        **pdf_gen_kwargs(
            db,
            hid,
            "physio_appointments",
            query_include_header=include_header,
        ),
    )
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/board/today")
async def todays_board(
    therapist_id: Optional[int] = None,
    current_user: User = Depends(require_feature_permission(Modules.PHYSIOTHERAPY, "view_physio")),
    db: Session = Depends(get_db),
):
    return await list_appointments(
        on_date=date.today(),
        date_from=None,
        date_to=None,
        therapist_id=therapist_id,
        status_filter=None,
        patient_id=None,
        current_user=current_user,
        db=db,
    )


@router.post("/appointments", status_code=201)
async def create_appointment(
    data: AppointmentIn,
    current_user: User = Depends(
        require_feature_permission(Modules.PHYSIOTHERAPY, "schedule_sessions")
    ),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    if data.session_type not in SESSION_TYPES:
        raise HTTPException(status_code=400, detail=f"session_type must be one of {SESSION_TYPES}")
    billing_mode = (data.billing_mode or "none").strip().lower()
    if billing_mode not in ("none", "package", "a_la_carte"):
        raise HTTPException(status_code=400, detail="billing_mode must be none, package, or a_la_carte")
    # Infer mode from package_id when caller omits billing_mode
    if billing_mode == "none" and data.package_id:
        billing_mode = "package"

    patient = _get_patient(db, data.patient_id, hid)
    therapist = db.query(User).filter(
        User.id == data.therapist_id, User.hospital_id == hid
    ).first()
    if not therapist:
        raise HTTPException(status_code=404, detail="Therapist not found")

    svc = None
    duration = data.duration_minutes
    if data.service_id:
        svc = db.query(PhysioService).filter(
            PhysioService.id == data.service_id, PhysioService.hospital_id == hid
        ).first()
        if not svc:
            raise HTTPException(status_code=404, detail="Service not found")
        if duration is None:
            duration = svc.duration_minutes or 30
    duration = duration or 30
    appt_time = _parse_time(data.appointment_time)

    if _has_conflict(db, data.therapist_id, data.appointment_date, appt_time, duration):
        raise HTTPException(status_code=409, detail="Therapist already has a session in this slot")

    if billing_mode == "a_la_carte" and not data.service_id:
        raise HTTPException(status_code=400, detail="À la carte booking requires a service")
    if billing_mode == "package" and not data.package_id:
        raise HTTPException(status_code=400, detail="Package booking requires package_id")

    pkg = None
    if data.package_id or billing_mode == "package":
        pkg = db.query(PhysioPatientPackage).filter(
            PhysioPatientPackage.id == data.package_id,
            PhysioPatientPackage.hospital_id == hid,
            PhysioPatientPackage.patient_id == patient.id,
        ).first()
        if not pkg or pkg.status != "active" or pkg.sessions_remaining <= 0:
            raise HTTPException(status_code=400, detail="Package is not usable")

    bill = None
    if billing_mode == "a_la_carte":
        price = data.unit_price
        if price is None:
            price = float(svc.default_price) if svc else 0.0
        if price <= 0:
            raise HTTPException(status_code=400, detail="À la carte price must be greater than zero")
        bill = _create_physio_bill(
            db,
            patient=patient,
            hospital_id=hid,
            user=current_user,
            item_name=svc.name if svc else "Physio session",
            item_code=(svc.code or f"SVC-{svc.id}") if svc else "SESSION",
            unit_price=price,
            notes=data.notes,
            referred_by=data.referral_source,
            payment_method=data.payment_method,
            mark_paid=bool(data.mark_paid),
        )

    appt = PhysioAppointment(
        hospital_id=hid,
        appointment_number=_next_appt_number(db),
        patient_id=patient.id,
        therapist_id=data.therapist_id,
        service_id=data.service_id,
        package_id=pkg.id if pkg else None,
        bill_id=bill.id if bill else None,
        appointment_date=data.appointment_date,
        appointment_time=appt_time,
        duration_minutes=duration,
        session_type=data.session_type,
        status="checked_in" if data.is_walk_in else "scheduled",
        is_walk_in=data.is_walk_in,
        referral_source=data.referral_source,
        chief_complaint=data.chief_complaint,
        notes=data.notes,
        booked_by_id=current_user.id,
        checked_in_at=system_now() if data.is_walk_in else None,
    )
    db.add(appt)
    db.flush()

    if billing_mode == "package" and pkg:
        _reserve_package(
            db,
            pkg=pkg,
            appointment=appt,
            user=current_user,
            service_id=data.service_id,
        )

    db.commit()
    db.refresh(appt)
    appt = db.query(PhysioAppointment).options(
        joinedload(PhysioAppointment.patient),
        joinedload(PhysioAppointment.therapist),
        joinedload(PhysioAppointment.service),
    ).filter(PhysioAppointment.id == appt.id).first()
    log_action(db, current_user, "create_physio_appointment", "physiotherapy",
               "PhysioAppointment", appt.id,
               f"Booked {appt.appointment_number} ({billing_mode})")
    out = _serialize_appt(appt)
    if bill:
        out["bill_number"] = bill.bill_number
        out["bill_id"] = bill.id
    if pkg:
        out["package_sessions_remaining"] = pkg.sessions_remaining
    return out


@router.post("/appointments/{appointment_id}/check-in")
async def check_in(
    appointment_id: int,
    current_user: User = Depends(
        require_feature_permission(Modules.PHYSIOTHERAPY, "schedule_sessions")
    ),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    appt = db.query(PhysioAppointment).filter(
        PhysioAppointment.id == appointment_id, PhysioAppointment.hospital_id == hid
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.status != "scheduled":
        raise HTTPException(status_code=400, detail=f"Cannot check in from status '{appt.status}'")
    appt.status = "checked_in"
    appt.checked_in_at = system_now()
    db.commit()
    return {"ok": True, "status": appt.status}


@router.post("/appointments/{appointment_id}/start")
async def start_session(
    appointment_id: int,
    current_user: User = Depends(
        require_feature_permission(Modules.PHYSIOTHERAPY, "record_attendance")
    ),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    appt = db.query(PhysioAppointment).filter(
        PhysioAppointment.id == appointment_id, PhysioAppointment.hospital_id == hid
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.status not in ("scheduled", "checked_in"):
        raise HTTPException(status_code=400, detail=f"Cannot start from status '{appt.status}'")
    roles = set(current_user.role_names or [])
    if "physiotherapist" in roles and not roles.intersection(
        {"super_admin", "hospital_admin", "receptionist", "frontdesk"}
    ):
        if appt.therapist_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not your session")
    appt.status = "in_progress"
    appt.started_at = system_now()
    if not appt.checked_in_at:
        appt.checked_in_at = system_now()
    db.commit()
    return {"ok": True, "status": appt.status}


@router.post("/appointments/{appointment_id}/no-show")
async def mark_no_show(
    appointment_id: int,
    current_user: User = Depends(
        require_feature_permission(Modules.PHYSIOTHERAPY, "schedule_sessions")
    ),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    appt = db.query(PhysioAppointment).filter(
        PhysioAppointment.id == appointment_id, PhysioAppointment.hospital_id == hid
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.status in ("completed", "cancelled", "no_show"):
        raise HTTPException(status_code=400, detail=f"Cannot mark no-show from '{appt.status}'")
    _restore_package_if_reserved(
        db, appt=appt, user=current_user, reason="booking_no_show"
    )
    appt.status = "no_show"
    db.commit()
    return {"ok": True, "status": appt.status}


class CancelIn(BaseModel):
    reason: Optional[str] = None


@router.post("/appointments/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: int,
    data: Optional[CancelIn] = None,
    current_user: User = Depends(
        require_feature_permission(Modules.PHYSIOTHERAPY, "schedule_sessions")
    ),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    appt = db.query(PhysioAppointment).filter(
        PhysioAppointment.id == appointment_id, PhysioAppointment.hospital_id == hid
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.status in ("completed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel from '{appt.status}'")
    _restore_package_if_reserved(
        db, appt=appt, user=current_user, reason="booking_cancelled"
    )
    appt.status = "cancelled"
    appt.cancellation_reason = data.reason if data else None
    db.commit()
    return {"ok": True, "status": appt.status}


@router.post("/appointments/{appointment_id}/complete")
async def complete_session(
    appointment_id: int,
    data: CompleteSessionIn,
    current_user: User = Depends(
        require_feature_permission(Modules.PHYSIOTHERAPY, "record_attendance")
    ),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    _expire_packages(db, hid)
    appt = db.query(PhysioAppointment).options(
        joinedload(PhysioAppointment.patient),
        joinedload(PhysioAppointment.service),
    ).filter(
        PhysioAppointment.id == appointment_id, PhysioAppointment.hospital_id == hid
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.status in ("completed", "cancelled", "no_show"):
        raise HTTPException(status_code=400, detail=f"Cannot complete from '{appt.status}'")

    roles = set(current_user.role_names or [])
    if "physiotherapist" in roles and not roles.intersection(
        {"super_admin", "hospital_admin", "receptionist", "frontdesk"}
    ):
        if appt.therapist_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not your session")

    package_used = appt.package_id
    bill = None
    already_reserved = _ledger_reserved_for_appt(db, appt.id)
    already_billed = bool(appt.bill_id)
    pkg_id = data.package_id or appt.package_id

    # Package already reserved at booking — do not double-decrement
    if already_reserved and appt.package_id:
        package_used = appt.package_id
    elif data.use_package and pkg_id:
        pkg = db.query(PhysioPatientPackage).filter(
            PhysioPatientPackage.id == pkg_id,
            PhysioPatientPackage.hospital_id == hid,
            PhysioPatientPackage.patient_id == appt.patient_id,
        ).first()
        if not pkg:
            raise HTTPException(status_code=404, detail="Package not found")
        _reserve_package(
            db,
            pkg=pkg,
            appointment=appt,
            user=current_user,
            service_id=appt.service_id,
            override_reason=data.override_reason,
            reason="session_complete",
        )
        package_used = pkg.id
    elif not already_billed:
        patient = appt.patient
        svc = appt.service
        price = data.unit_price
        if price is None:
            price = float(svc.default_price) if svc else 0.0
        if price > 0:
            bill = _create_physio_bill(
                db,
                patient=patient,
                hospital_id=hid,
                user=current_user,
                item_name=(svc.name if svc else f"{appt.session_type.title()} session"),
                item_code=(svc.code or f"SVC-{svc.id}") if svc else "SESSION",
                unit_price=price,
                notes=data.session_note,
                payment_method=data.payment_method,
                mark_paid=bool(data.mark_paid and data.payment_method),
            )
            appt.bill_id = bill.id

    appt.status = "completed"
    appt.completed_at = system_now()
    appt.session_note = data.session_note
    appt.next_appointment_suggested = data.next_appointment_suggested
    if not appt.started_at:
        appt.started_at = system_now()
    db.commit()
    log_action(db, current_user, "complete_physio_session", "physiotherapy",
               "PhysioAppointment", appt.id, f"Completed {appt.appointment_number}")
    return {
        "ok": True,
        "status": "completed",
        "package_id": package_used,
        "bill_id": bill.id if bill else appt.bill_id,
        "bill_number": bill.bill_number if bill else None,
        "already_billed_at_booking": already_billed,
        "package_reserved_at_booking": already_reserved,
    }


class WalkInIn(BaseModel):
    patient_id: int
    therapist_id: int
    service_id: Optional[int] = None
    session_type: str = "treatment"
    package_id: Optional[int] = None
    use_package: bool = True
    unit_price: Optional[float] = Field(None, ge=0)
    payment_method: Optional[str] = "cash"
    mark_paid: bool = True
    session_note: Optional[str] = None
    referral_source: Optional[str] = None
    chief_complaint: Optional[str] = None


@router.post("/walk-in", status_code=201)
async def walk_in_complete(
    data: WalkInIn,
    current_user: User = Depends(
        require_feature_permission_any(
            Modules.PHYSIOTHERAPY, "schedule_sessions", "record_attendance", "bill_sessions"
        )
    ),
    db: Session = Depends(get_db),
):
    appt_payload = AppointmentIn(
        patient_id=data.patient_id,
        therapist_id=data.therapist_id,
        service_id=data.service_id,
        appointment_date=date.today(),
        appointment_time=datetime.now().strftime("%H:%M"),
        session_type=data.session_type,
        is_walk_in=True,
        package_id=data.package_id,
        referral_source=data.referral_source,
        chief_complaint=data.chief_complaint,
        billing_mode=("package" if data.use_package and data.package_id else "a_la_carte"),
        unit_price=data.unit_price,
        payment_method=data.payment_method,
        mark_paid=data.mark_paid,
    )
    created = await create_appointment(appt_payload, current_user, db)
    complete_payload = CompleteSessionIn(
        session_note=data.session_note,
        package_id=data.package_id,
        use_package=bool(data.use_package and data.package_id),
        unit_price=data.unit_price,
        payment_method=data.payment_method,
        mark_paid=False,  # already billed/reserved at booking
    )
    result = await complete_session(created["id"], complete_payload, current_user, db)
    return {**created, **result, "status": "completed"}


# ── Reports ───────────────────────────────────────────────────────────────────

@router.get("/reports/summary")
async def reports_summary(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: User = Depends(
        require_feature_permission(Modules.PHYSIOTHERAPY, "view_physio_reports")
    ),
    db: Session = Depends(get_db),
):
    hid = _hospital_id(current_user)
    d_from = date_from or date.today()
    d_to = date_to or date.today()
    _expire_packages(db, hid)
    db.commit()

    appts = db.query(PhysioAppointment).filter(
        PhysioAppointment.hospital_id == hid,
        PhysioAppointment.appointment_date >= d_from,
        PhysioAppointment.appointment_date <= d_to,
    ).all()

    by_status = {}
    by_therapist = {}
    for a in appts:
        by_status[a.status] = by_status.get(a.status, 0) + 1
        tid = a.therapist_id
        if tid not in by_therapist:
            t = db.query(User).filter(User.id == tid).first()
            by_therapist[tid] = {
                "therapist_id": tid,
                "therapist_name": f"{t.first_name} {t.last_name}" if t else str(tid),
                "completed": 0,
                "no_show": 0,
                "cancelled": 0,
                "scheduled": 0,
            }
        key = a.status if a.status in ("completed", "no_show", "cancelled") else "scheduled"
        by_therapist[tid][key] = by_therapist[tid].get(key, 0) + 1

    bills = db.query(Bill).filter(
        Bill.hospital_id == hid,
        Bill.bill_type == "physiotherapy",
        Bill.status != "cancelled",
        func.date(Bill.bill_date) >= d_from,
        func.date(Bill.bill_date) <= d_to,
    ).all()

    collections = {"cash": 0.0, "upi": 0.0, "card": 0.0, "other": 0.0, "total": 0.0}
    outstanding = 0.0
    for b in bills:
        paid = sum(float(p.amount_paid or 0) for p in (b.payments or []))
        outstanding += max(float(b.total_amount or 0) - paid, 0)
        for p in (b.payments or []):
            method = (p.payment_method_name or "other").lower()
            amt = float(p.amount_paid or 0)
            collections["total"] += amt
            if "upi" in method or "gpay" in method or "phonepe" in method:
                collections["upi"] += amt
            elif "card" in method:
                collections["card"] += amt
            elif "cash" in method:
                collections["cash"] += amt
            else:
                collections["other"] += amt

    active_pkgs = db.query(PhysioPatientPackage).filter(
        PhysioPatientPackage.hospital_id == hid,
        PhysioPatientPackage.status == "active",
    ).all()

    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "sessions_by_status": by_status,
        "therapist_utilization": list(by_therapist.values()),
        "collections": collections,
        "outstanding_dues": round(outstanding, 2),
        "package_liability": {
            "active_packages": len(active_pkgs),
            "sessions_owed": sum(p.sessions_remaining for p in active_pkgs),
            "sold_in_range": db.query(func.count(PhysioPatientPackage.id)).filter(
                PhysioPatientPackage.hospital_id == hid,
                func.date(PhysioPatientPackage.purchased_at) >= d_from,
                func.date(PhysioPatientPackage.purchased_at) <= d_to,
            ).scalar() or 0,
        },
        "total_sessions": len(appts),
    }
