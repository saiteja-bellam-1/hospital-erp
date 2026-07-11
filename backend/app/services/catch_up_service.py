"""Shared helpers for the admin catch-up (omitted / backdated bills) tool."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.billing import Bill, BillItem, Payment
from app.models.hospital import Hospital
from app.models.patient import Patient
from app.services.audit_service import log_action

CATCH_UP_LOOKBACK_DAYS = 365


def assert_catch_up_dates(
    service_date: date,
    payment_date: date,
    *,
    lookback_days: int = CATCH_UP_LOOKBACK_DAYS,
) -> None:
    today = date.today()
    if service_date > today:
        raise HTTPException(status_code=400, detail="Service date cannot be in the future")
    if payment_date > today:
        raise HTTPException(status_code=400, detail="Payment date cannot be in the future")
    earliest = today - timedelta(days=lookback_days)
    if service_date < earliest:
        raise HTTPException(
            status_code=400,
            detail=f"Service date cannot be more than {lookback_days} days in the past",
        )
    if payment_date < earliest:
        raise HTTPException(
            status_code=400,
            detail=f"Payment date cannot be more than {lookback_days} days in the past",
        )


def date_to_datetime(d: date, at: time = time.min) -> datetime:
    return datetime.combine(d, at)


def get_hospital(db: Session, current_user) -> Hospital:
    hospital = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
    return hospital


def get_patient(db: Session, patient_id: int, hospital_id: int) -> Patient:
    patient = db.query(Patient).filter(
        Patient.id == patient_id,
        Patient.hospital_id == hospital_id,
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


def next_bill_number(db: Session, prefix: str) -> str:
    last = (
        db.query(Bill)
        .filter(Bill.bill_number.like(f"{prefix}%"))
        .order_by(Bill.id.desc())
        .first()
    )
    seq = 1
    if last and last.bill_number:
        try:
            seq = int(last.bill_number.rsplit("-", 1)[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}{seq:04d}"


def next_payment_number(db: Session, prefix: str) -> str:
    last = (
        db.query(Payment)
        .filter(Payment.payment_number.like(f"{prefix}%"))
        .order_by(Payment.id.desc())
        .first()
    )
    seq = 1
    if last and last.payment_number:
        try:
            seq = int(last.payment_number.rsplit("-", 1)[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}{seq:04d}"


def create_bill_with_payment(
    db: Session,
    *,
    patient_id: int,
    hospital_id: int,
    created_by_id: int,
    bill_type: str,
    items: list[dict],
    service_date: date,
    payment_date: date,
    payment_method: str = "cash",
    reference_id: Optional[int] = None,
    notes: Optional[str] = None,
    referred_by: Optional[str] = None,
) -> tuple[Bill, Payment]:
    """Create a paid Bill + Payment with operator-supplied dates."""
    subtotal = round(sum(float(i.get("total_price") or 0) for i in items), 2)
    if subtotal < 0:
        raise HTTPException(status_code=400, detail="Bill total cannot be negative")

    day = service_date.strftime("%Y%m%d")
    bill_number = next_bill_number(db, f"CU-{bill_type[:4].upper()}-{day}-")
    bill = Bill(
        bill_number=bill_number,
        patient_id=patient_id,
        bill_type=bill_type,
        bill_subtype="final",
        reference_id=reference_id,
        subtotal=subtotal,
        tax_amount=0.0,
        discount_amount=0.0,
        total_amount=subtotal,
        status="paid",
        bill_date=date_to_datetime(service_date),
        created_by_id=created_by_id,
        hospital_id=hospital_id,
        notes=notes,
        referred_by=referred_by,
    )
    db.add(bill)
    db.flush()

    for it in items:
        db.add(BillItem(
            bill_id=bill.id,
            item_type=it.get("item_type") or bill_type,
            item_name=it["item_name"],
            item_code=it.get("item_code"),
            quantity=int(it.get("quantity") or 1),
            unit_price=float(it.get("unit_price") or 0),
            total_price=float(it.get("total_price") or 0),
        ))

    pay_day = payment_date.strftime("%Y%m%d")
    payment = Payment(
        payment_number=next_payment_number(db, f"PAY-{pay_day}-"),
        bill_id=bill.id,
        amount_paid=subtotal,
        payment_method_name=payment_method or "cash",
        payment_date=date_to_datetime(payment_date),
        received_by_id=created_by_id,
        notes=notes,
    )
    db.add(payment)
    db.flush()
    return bill, payment


def log_catch_up(
    db: Session,
    user,
    action: str,
    resource_type: str,
    resource_id,
    description: str,
    *,
    service_date: date,
    payment_date: date,
    reason: Optional[str] = None,
    extra: Optional[dict] = None,
):
    details = {
        "service_date": service_date.isoformat(),
        "payment_date": payment_date.isoformat(),
        "catch_up": True,
    }
    if reason and str(reason).strip():
        details["reason"] = str(reason).strip()
    if extra:
        details.update(extra)
    log_action(
        db, user, action, "billing", resource_type, resource_id,
        description, details=details,
    )
