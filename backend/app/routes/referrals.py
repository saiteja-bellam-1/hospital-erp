"""Referral (affiliate) management endpoints."""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func, or_
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from config.database import get_db
from app.models.user import User
from app.models.referral import Referral, ReferralCommission
from app.models.outpatient import Appointment
from app.models.lab import PatientLabOrder
from app.models.patient import Patient
from app.models.billing import Bill
from app.models.pharmacy import PharmacySale, PharmacySaleReturn
from app.utils.dependencies import get_current_user

router = APIRouter()


class ReferralCreate(BaseModel):
    name: str = Field(..., max_length=100)
    phone: Optional[str] = Field(None, max_length=15)
    village: Optional[str] = Field(None, max_length=100)
    mandal: Optional[str] = Field(None, max_length=100)
    district: Optional[str] = Field(None, max_length=100)
    op_commission_pct: float = Field(0, ge=0, le=100)
    lab_commission_pct: float = Field(0, ge=0, le=100)
    ip_commission_pct: float = Field(0, ge=0, le=100)
    pharmacy_commission_pct: float = Field(0, ge=0, le=100)


class ReferralUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=15)
    village: Optional[str] = Field(None, max_length=100)
    mandal: Optional[str] = Field(None, max_length=100)
    district: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    op_commission_pct: Optional[float] = Field(None, ge=0, le=100)
    lab_commission_pct: Optional[float] = Field(None, ge=0, le=100)
    ip_commission_pct: Optional[float] = Field(None, ge=0, le=100)
    pharmacy_commission_pct: Optional[float] = Field(None, ge=0, le=100)


class ReferralResponse(BaseModel):
    id: int
    name: str
    phone: Optional[str]
    village: Optional[str]
    mandal: Optional[str]
    district: Optional[str]
    is_active: bool
    op_commission_pct: float = 0
    lab_commission_pct: float = 0
    ip_commission_pct: float = 0
    pharmacy_commission_pct: float = 0

    @field_validator(
        "op_commission_pct",
        "lab_commission_pct",
        "ip_commission_pct",
        "pharmacy_commission_pct",
        mode="before",
    )
    @classmethod
    def _null_rate_is_zero(cls, value):
        return 0 if value is None else value

    class Config:
        from_attributes = True


class CommissionCreate(BaseModel):
    amount: float = Field(..., gt=0)
    payment_method: str = Field(default="cash")
    notes: Optional[str] = None


ALLOWED_ROLES = ['receptionist', 'hospital_admin', 'super_admin']


@router.get("", response_model=List[ReferralResponse])
async def list_referrals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all active referrals for the hospital."""
    referrals = db.query(Referral).filter(
        Referral.hospital_id == current_user.hospital_id,
        Referral.is_active == True
    ).order_by(Referral.name).all()
    return referrals


@router.get("/all", response_model=List[ReferralResponse])
async def list_all_referrals(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all referrals including inactive (admin view)."""
    if not any(r in current_user.role_names for r in ALLOWED_ROLES):
        raise HTTPException(status_code=403, detail="Not authorized")
    referrals = db.query(Referral).filter(
        Referral.hospital_id == current_user.hospital_id
    ).order_by(Referral.name).all()
    return referrals


@router.post("", response_model=ReferralResponse)
async def create_referral(
    data: ReferralCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not any(r in current_user.role_names for r in ALLOWED_ROLES):
        raise HTTPException(status_code=403, detail="Not authorized")

    referral = Referral(
        name=data.name,
        phone=data.phone,
        village=data.village,
        mandal=data.mandal,
        district=data.district,
        op_commission_pct=data.op_commission_pct,
        lab_commission_pct=data.lab_commission_pct,
        ip_commission_pct=data.ip_commission_pct,
        pharmacy_commission_pct=data.pharmacy_commission_pct,
        hospital_id=current_user.hospital_id,
    )
    db.add(referral)
    db.commit()
    db.refresh(referral)
    return referral


@router.put("/{referral_id}", response_model=ReferralResponse)
async def update_referral(
    referral_id: int,
    data: ReferralUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not any(r in current_user.role_names for r in ALLOWED_ROLES):
        raise HTTPException(status_code=403, detail="Not authorized")

    referral = db.query(Referral).filter(
        Referral.id == referral_id,
        Referral.hospital_id == current_user.hospital_id
    ).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")

    for key, val in data.dict(exclude_unset=True).items():
        setattr(referral, key, val)

    db.commit()
    db.refresh(referral)
    return referral


@router.delete("/{referral_id}")
async def delete_referral(
    referral_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not any(r in current_user.role_names for r in ALLOWED_ROLES):
        raise HTTPException(status_code=403, detail="Not authorized")

    referral = db.query(Referral).filter(
        Referral.id == referral_id,
        Referral.hospital_id == current_user.hospital_id
    ).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")

    referral.is_active = False
    db.commit()
    return {"message": "Referral deactivated"}


def _pct(value) -> float:
    try:
        rate = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return min(max(rate, 0.0), 100.0)


def _money(value) -> float:
    return round(float(value or 0), 2)


def _commission_amount(revenue: float, pct: float) -> float:
    return round(_money(revenue) * _pct(pct) / 100.0, 2)


def _patient_label(patient) -> str:
    if not patient:
        return "Unknown"
    return f"{patient.first_name or ''} {patient.last_name or ''}".strip() or "Unknown"


def _not_cancelled(column):
    return or_(column.is_(None), column != "cancelled")


@router.get("/{referral_id}/details")
async def get_referral_details(
    referral_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Bills and payout math for one referrer.

    A patient has one referral, saved on `patients.referred_by`. Outpatient
    visits, walk-in lab orders, admission bills, and counter pharmacy sales
    for those patients are listed separately. Lab and pharmacy already
    consumed by an admission bill stay inside that IP total.
    """
    if not any(r in current_user.role_names for r in ALLOWED_ROLES):
        raise HTTPException(status_code=403, detail="Not authorized")

    referral = db.query(Referral).filter(
        Referral.id == referral_id,
        Referral.hospital_id == current_user.hospital_id
    ).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")

    ref_name = (referral.name or "").strip()
    hospital_id = current_user.hospital_id

    patients = []
    if ref_name:
        patients = db.query(Patient).filter(
            Patient.hospital_id == hospital_id,
            sql_func.trim(Patient.referred_by) == ref_name,
        ).all()

    patient_by_id = {p.id: p for p in patients}
    patient_ids = list(patient_by_id)
    patient_uuids = [p.patient_id for p in patients if p.patient_id]

    apt_bills = []
    lab_bills = []
    ip_bills = []
    pharmacy_bills = []

    if patient_ids:
        appointments = db.query(Appointment).filter(
            Appointment.patient_id.in_(patient_ids),
            _not_cancelled(Appointment.status),
            _not_cancelled(Appointment.payment_status),
            Appointment.bill_cancelled_at.is_(None),
        ).order_by(Appointment.created_at.desc()).all()

        doctor_ids = {a.doctor_id for a in appointments if a.doctor_id}
        doctors = {}
        if doctor_ids:
            for doctor in db.query(User).filter(User.id.in_(doctor_ids)).all():
                doctors[doctor.id] = doctor

        for apt in appointments:
            patient = patient_by_id.get(apt.patient_id) or apt.patient
            doctor = doctors.get(apt.doctor_id)
            doctor_name = f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else ""
            apt_bills.append({
                "type": "consultation",
                "id": apt.id,
                "date": apt.created_at.isoformat() if apt.created_at else "",
                "patient_name": _patient_label(patient),
                "doctor_name": doctor_name,
                "detail": doctor_name,
                "amount": _money(apt.final_amount),
                "status": apt.payment_status or "pending",
                "reference": apt.appointment_number,
            })

        lab_orders = db.query(PatientLabOrder).filter(
            PatientLabOrder.patient_id.in_(patient_ids),
            PatientLabOrder.admission_id.is_(None),
            PatientLabOrder.inpatient_bill_id.is_(None),
            PatientLabOrder.cancelled_at.is_(None),
            PatientLabOrder.bill_cancelled_at.is_(None),
            _not_cancelled(PatientLabOrder.status),
        ).order_by(PatientLabOrder.order_date.desc()).all()

        for lo in lab_orders:
            test_name = lo.test.name if lo.test else ""
            lab_bills.append({
                "type": "lab",
                "id": lo.id,
                "date": lo.order_date.isoformat() if lo.order_date else "",
                "patient_name": _patient_label(patient_by_id.get(lo.patient_id)),
                "doctor_name": "",
                "detail": test_name,
                "test_name": test_name,
                "amount": _money(lo.amount),
                "status": lo.payment_status or "pending",
                "reference": lo.order_number,
            })

        admission_bills = db.query(Bill).filter(
            Bill.patient_id.in_(patient_ids),
            Bill.hospital_id == hospital_id,
            Bill.bill_type == "admission",
            _not_cancelled(Bill.status),
            or_(Bill.bill_subtype.is_(None), Bill.bill_subtype != "advance_receipt"),
        ).order_by(Bill.bill_date.desc()).all()

        for bill in admission_bills:
            subtype = (bill.bill_subtype or "final").replace("_", " ").title()
            ip_bills.append({
                "type": "inpatient",
                "id": bill.id,
                "date": bill.bill_date.isoformat() if bill.bill_date else "",
                "patient_name": _patient_label(patient_by_id.get(bill.patient_id)),
                "detail": subtype,
                "amount": _money(bill.total_amount),
                "status": bill.status or "pending",
                "reference": bill.bill_number,
            })

    if patient_uuids:
        sales = db.query(PharmacySale).filter(
            PharmacySale.hospital_id == hospital_id,
            PharmacySale.patient_ip_id.in_(patient_uuids),
            PharmacySale.status == "completed",
            PharmacySale.inpatient_bill_id.is_(None),
            or_(
                PharmacySale.billing_mode.is_(None),
                PharmacySale.billing_mode != "inpatient_bill",
            ),
        ).order_by(PharmacySale.sale_date.desc()).all()

        returned = {}
        sale_ids = [sale.id for sale in sales]
        if sale_ids:
            for ret in db.query(PharmacySaleReturn).filter(
                PharmacySaleReturn.sale_id.in_(sale_ids),
                PharmacySaleReturn.status == "confirmed",
            ).all():
                returned[ret.sale_id] = returned.get(ret.sale_id, 0.0) + _money(ret.grand_total)

        patient_by_uuid = {p.patient_id: p for p in patients}
        for sale in sales:
            gross = _money(sale.grand_total)
            returned_amt = _money(returned.get(sale.id, 0))
            net = round(max(gross - returned_amt, 0.0), 2)
            patient = patient_by_uuid.get(sale.patient_ip_id)
            detail = (sale.payment_type or "cash").replace("_", " ")
            if returned_amt:
                detail = f"{detail} · return ₹{returned_amt:g}"
            pharmacy_bills.append({
                "type": "pharmacy",
                "id": sale.id,
                "date": sale.sale_date.isoformat() if sale.sale_date else "",
                "patient_name": _patient_label(patient) if patient else (sale.patient_name or "Unknown"),
                "detail": detail,
                "amount": net,
                "status": sale.status or "completed",
                "reference": sale.sale_number,
            })

    commissions = db.query(ReferralCommission).filter(
        ReferralCommission.referral_id == referral_id
    ).order_by(ReferralCommission.payment_date.desc()).all()

    payer_ids = {c.paid_by_id for c in commissions if c.paid_by_id}
    payers = {}
    if payer_ids:
        for user in db.query(User).filter(User.id.in_(payer_ids)).all():
            payers[user.id] = user

    commission_list = []
    for c in commissions:
        paid_by = payers.get(c.paid_by_id)
        commission_list.append({
            "id": c.id,
            "amount": _money(c.amount),
            "payment_method": c.payment_method,
            "payment_date": c.payment_date.isoformat() if c.payment_date else "",
            "notes": c.notes or "",
            "paid_by": f"{paid_by.first_name} {paid_by.last_name}" if paid_by else "",
        })

    op_pct = _pct(referral.op_commission_pct)
    lab_pct = _pct(referral.lab_commission_pct)
    ip_pct = _pct(referral.ip_commission_pct)
    pharmacy_pct = _pct(referral.pharmacy_commission_pct)

    op_revenue = round(sum(b["amount"] for b in apt_bills), 2)
    lab_revenue = round(sum(b["amount"] for b in lab_bills), 2)
    ip_revenue = round(sum(b["amount"] for b in ip_bills), 2)
    pharmacy_revenue = round(sum(b["amount"] for b in pharmacy_bills), 2)
    op_commission = _commission_amount(op_revenue, op_pct)
    lab_commission = _commission_amount(lab_revenue, lab_pct)
    ip_commission = _commission_amount(ip_revenue, ip_pct)
    pharmacy_commission = _commission_amount(pharmacy_revenue, pharmacy_pct)
    total_revenue = round(op_revenue + lab_revenue + ip_revenue + pharmacy_revenue, 2)
    total_earned = round(op_commission + lab_commission + ip_commission + pharmacy_commission, 2)
    total_paid = round(sum(c["amount"] for c in commission_list), 2)

    return {
        "referral": ReferralResponse.model_validate(referral).model_dump(),
        "consultations": apt_bills,
        "lab_orders": lab_bills,
        "inpatient_bills": ip_bills,
        "pharmacy_sales": pharmacy_bills,
        "commissions": commission_list,
        "summary": {
            "total_consultations": len(apt_bills),
            "total_lab_orders": len(lab_bills),
            "total_ip_bills": len(ip_bills),
            "total_pharmacy_sales": len(pharmacy_bills),
            "op_commission_pct": op_pct,
            "lab_commission_pct": lab_pct,
            "ip_commission_pct": ip_pct,
            "pharmacy_commission_pct": pharmacy_pct,
            "op_revenue": op_revenue,
            "lab_revenue": lab_revenue,
            "ip_revenue": ip_revenue,
            "pharmacy_revenue": pharmacy_revenue,
            "op_commission": op_commission,
            "lab_commission": lab_commission,
            "ip_commission": ip_commission,
            "pharmacy_commission": pharmacy_commission,
            "total_revenue": total_revenue,
            "total_commission_earned": total_earned,
            "total_commission_paid": total_paid,
            "commission_balance": round(total_earned - total_paid, 2),
        }
    }


# Legacy endpoint — keep for backward compat
@router.get("/{referral_id}/bills")
async def get_referral_bills(
    referral_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return await get_referral_details(referral_id, current_user, db)


@router.post("/{referral_id}/commissions")
async def add_commission_payment(
    referral_id: int,
    data: CommissionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Record a commission payment to a referral."""
    if not any(r in current_user.role_names for r in ALLOWED_ROLES):
        raise HTTPException(status_code=403, detail="Not authorized")

    referral = db.query(Referral).filter(
        Referral.id == referral_id,
        Referral.hospital_id == current_user.hospital_id
    ).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")

    commission = ReferralCommission(
        referral_id=referral_id,
        amount=data.amount,
        payment_method=data.payment_method,
        notes=data.notes,
        paid_by_id=current_user.id,
        hospital_id=current_user.hospital_id,
    )
    db.add(commission)
    db.commit()
    db.refresh(commission)

    return {"message": "Commission payment recorded", "id": commission.id}


@router.delete("/{referral_id}/commissions/{commission_id}")
async def delete_commission_payment(
    referral_id: int,
    commission_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a commission payment record."""
    if not any(r in current_user.role_names for r in ALLOWED_ROLES):
        raise HTTPException(status_code=403, detail="Not authorized")

    commission = db.query(ReferralCommission).filter(
        ReferralCommission.id == commission_id,
        ReferralCommission.referral_id == referral_id,
    ).first()
    if not commission:
        raise HTTPException(status_code=404, detail="Commission record not found")

    db.delete(commission)
    db.commit()
    return {"message": "Commission payment deleted"}
