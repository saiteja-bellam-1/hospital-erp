"""Referral (affiliate) management endpoints."""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from config.database import get_db
from app.models.user import User
from app.models.referral import Referral, ReferralCommission
from app.models.outpatient import Appointment
from app.models.lab import PatientLabOrder, LabTest
from app.models.patient import Patient
from app.utils.dependencies import get_current_user

router = APIRouter()


class ReferralCreate(BaseModel):
    name: str = Field(..., max_length=100)
    phone: Optional[str] = Field(None, max_length=15)
    village: Optional[str] = Field(None, max_length=100)
    mandal: Optional[str] = Field(None, max_length=100)
    district: Optional[str] = Field(None, max_length=100)


class ReferralUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=15)
    village: Optional[str] = Field(None, max_length=100)
    mandal: Optional[str] = Field(None, max_length=100)
    district: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None


class ReferralResponse(BaseModel):
    id: int
    name: str
    phone: Optional[str]
    village: Optional[str]
    mandal: Optional[str]
    district: Optional[str]
    is_active: bool

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


@router.get("/{referral_id}/details")
async def get_referral_details(
    referral_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get full referral details: info, all bills, commission payments."""
    if not any(r in current_user.role_names for r in ALLOWED_ROLES):
        raise HTTPException(status_code=403, detail="Not authorized")

    referral = db.query(Referral).filter(
        Referral.id == referral_id,
        Referral.hospital_id == current_user.hospital_id
    ).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found")

    ref_name = referral.name

    # Appointments with this referral
    appointments = db.query(Appointment).join(Patient).filter(
        Appointment.referred_by == ref_name,
        Patient.hospital_id == current_user.hospital_id
    ).order_by(Appointment.created_at.desc()).all()

    apt_bills = []
    for apt in appointments:
        patient = apt.patient
        doctor = db.query(User).filter(User.id == apt.doctor_id).first() if apt.doctor_id else None
        apt_bills.append({
            "type": "consultation",
            "id": apt.id,
            "date": apt.created_at.isoformat() if apt.created_at else "",
            "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "Unknown",
            "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "",
            "amount": apt.final_amount or 0,
            "status": apt.payment_status or "pending",
            "reference": apt.appointment_number,
        })

    # Lab orders with this referral
    lab_orders = db.query(PatientLabOrder).join(Patient).filter(
        PatientLabOrder.referred_by == ref_name,
        Patient.hospital_id == current_user.hospital_id
    ).order_by(PatientLabOrder.order_date.desc()).all()

    lab_bills = []
    for lo in lab_orders:
        patient = db.query(Patient).filter(Patient.id == lo.patient_id).first()
        test = db.query(LabTest).filter(LabTest.id == lo.test_id).first()
        lab_bills.append({
            "type": "lab",
            "id": lo.id,
            "date": lo.order_date.isoformat() if lo.order_date else "",
            "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "Unknown",
            "doctor_name": "",
            "amount": lo.amount or 0,
            "status": lo.payment_status or "pending",
            "reference": lo.order_number,
            "test_name": lo.test.name if lo.test else "",
        })

    # Commission payments
    commissions = db.query(ReferralCommission).filter(
        ReferralCommission.referral_id == referral_id
    ).order_by(ReferralCommission.payment_date.desc()).all()

    commission_list = []
    for c in commissions:
        paid_by = db.query(User).filter(User.id == c.paid_by_id).first()
        commission_list.append({
            "id": c.id,
            "amount": c.amount,
            "payment_method": c.payment_method,
            "payment_date": c.payment_date.isoformat() if c.payment_date else "",
            "notes": c.notes or "",
            "paid_by": f"{paid_by.first_name} {paid_by.last_name}" if paid_by else "",
        })

    total_revenue = sum(b["amount"] for b in apt_bills + lab_bills)
    total_commission_paid = sum(c["amount"] for c in commission_list)

    return {
        "referral": ReferralResponse.from_orm(referral).dict(),
        "consultations": apt_bills,
        "lab_orders": lab_bills,
        "commissions": commission_list,
        "summary": {
            "total_consultations": len(apt_bills),
            "total_lab_orders": len(lab_bills),
            "total_revenue": total_revenue,
            "total_commission_paid": total_commission_paid,
            "commission_balance": total_revenue - total_commission_paid,
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
