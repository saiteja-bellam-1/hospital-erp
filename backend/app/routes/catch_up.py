"""Admin catch-up APIs — enter omitted / backdated bills and reconstruct IP stays."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from config.database import get_db
from app.models.audit import AuditLog
from app.models.billing import Bill, Payment
from app.models.canteen import CanteenItem, CanteenOrder, CanteenOrderItem, CanteenSale, CanteenSaleItem
from app.models.inpatient import (
    Admission,
    AdmissionAncillaryCharge,
    AdmissionDeposit,
    AdmissionPackage,
    AncillaryServiceCatalog,
    DischargeRecord,
    FoodOrder,
    OTSchedule,
    PatientVisit,
    RoomManagement,
    SurgeryPackage,
)
from app.models.lab import LabTest, PatientLabOrder
from app.models.outpatient import Appointment
from app.models.pharmacy import PharmacyInventory, PharmacySale, PharmacySaleItem, Prescription
from app.models.user import User
from app.services.catch_up_service import (
    assert_catch_up_dates,
    create_bill_with_payment,
    date_to_datetime,
    get_hospital,
    get_patient,
    log_catch_up,
)
from app.utils.auth import Modules
from app.utils.dependencies import get_current_user, require_feature_permission

router = APIRouter()


# ---------------------------------------------------------------------------
# Shared schemas
# ---------------------------------------------------------------------------

class CatchUpDates(BaseModel):
    service_date: date
    payment_date: date
    reason: Optional[str] = None
    payment_method: str = "cash"


class LineItemIn(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=200)
    quantity: int = Field(1, gt=0)
    unit_price: float = Field(..., ge=0)
    item_code: Optional[str] = None
    item_type: Optional[str] = None


# ---------------------------------------------------------------------------
# Consultation
# ---------------------------------------------------------------------------

class ConsultationCatchUp(CatchUpDates):
    patient_id: int
    doctor_id: int
    consultation_fee: float = Field(..., ge=0)
    registration_fee: float = Field(0, ge=0)
    appointment_type: str = "consultation"
    notes: Optional[str] = None
    referred_by: Optional[str] = None


@router.post("/consultation")
async def catch_up_consultation(
    data: ConsultationCatchUp,
    current_user: User = Depends(require_feature_permission(Modules.BILLING, "catch_up_bills")),
    db: Session = Depends(get_db),
):
    assert_catch_up_dates(data.service_date, data.payment_date)
    hospital = get_hospital(db, current_user)
    patient = get_patient(db, data.patient_id, hospital.id)
    doctor = db.query(User).filter(User.id == data.doctor_id, User.hospital_id == hospital.id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    total = round(float(data.consultation_fee) + float(data.registration_fee or 0), 2)
    service_dt = date_to_datetime(data.service_date)
    payment_dt = date_to_datetime(data.payment_date)

    apt = Appointment(
        appointment_number=f"APT-{str(uuid.uuid4())[:8].upper()}",
        patient_id=patient.id,
        doctor_id=doctor.id,
        appointment_date=service_dt,
        appointment_type=data.appointment_type or "consultation",
        status="completed",
        notes=data.notes,
        booked_by_id=current_user.id,
        consultation_fee=float(data.consultation_fee),
        registration_fee=float(data.registration_fee or 0),
        payment_status="paid",
        payment_method=data.payment_method,
        payment_date=payment_dt,
        final_amount=total,
        referred_by=data.referred_by,
        checked_out_at=service_dt,
    )
    db.add(apt)
    db.flush()

    items = []
    if data.consultation_fee:
        items.append({
            "item_type": "consultation",
            "item_name": f"Consultation — Dr. {doctor.first_name} {doctor.last_name}",
            "quantity": 1,
            "unit_price": float(data.consultation_fee),
            "total_price": float(data.consultation_fee),
        })
    if data.registration_fee:
        items.append({
            "item_type": "registration",
            "item_name": "Registration fee",
            "quantity": 1,
            "unit_price": float(data.registration_fee),
            "total_price": float(data.registration_fee),
        })
    if not items:
        raise HTTPException(status_code=400, detail="At least one fee must be greater than zero")

    bill, payment = create_bill_with_payment(
        db,
        patient_id=patient.id,
        hospital_id=hospital.id,
        created_by_id=current_user.id,
        bill_type="consultation",
        items=items,
        service_date=data.service_date,
        payment_date=data.payment_date,
        payment_method=data.payment_method,
        reference_id=apt.id,
        notes=data.reason,
        referred_by=data.referred_by,
    )
    db.commit()
    log_catch_up(
        db, current_user, "catch_up_consultation", "Appointment", apt.id,
        f"Catch-up consultation {apt.appointment_number}",
        service_date=data.service_date, payment_date=data.payment_date,
        reason=data.reason,
        extra={"bill_id": bill.id, "payment_id": payment.id, "amount": total},
    )
    return {
        "appointment_id": apt.id,
        "appointment_number": apt.appointment_number,
        "bill_id": bill.id,
        "bill_number": bill.bill_number,
        "payment_id": payment.id,
        "total": total,
    }


# ---------------------------------------------------------------------------
# Lab
# ---------------------------------------------------------------------------

class LabCatchUp(CatchUpDates):
    patient_id: int
    test_ids: List[int] = Field(..., min_length=1)
    doctor_id: Optional[int] = None
    referred_by: Optional[str] = None
    notes: Optional[str] = None


@router.post("/lab")
async def catch_up_lab(
    data: LabCatchUp,
    current_user: User = Depends(require_feature_permission(Modules.BILLING, "catch_up_bills")),
    db: Session = Depends(get_db),
):
    assert_catch_up_dates(data.service_date, data.payment_date)
    hospital = get_hospital(db, current_user)
    patient = get_patient(db, data.patient_id, hospital.id)

    tests = db.query(LabTest).filter(LabTest.id.in_(data.test_ids)).all()
    by_id = {t.id: t for t in tests}
    missing = [tid for tid in data.test_ids if tid not in by_id]
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown lab test ids: {missing}")

    service_dt = date_to_datetime(data.service_date)
    payment_dt = date_to_datetime(data.payment_date)
    group_id = str(uuid.uuid4())
    bill_number_label = f"LB-CU-{service_date_str(data.service_date)}"
    order_ids = []
    items = []
    total = 0.0

    for tid in data.test_ids:
        test = by_id[tid]
        amount = float(test.cost or 0)
        total += amount
        order = PatientLabOrder(
            order_number=f"LAB-{str(uuid.uuid4())[:8].upper()}",
            patient_id=patient.id,
            test_id=test.id,
            doctor_id=data.doctor_id,
            status="completed",
            order_date=service_dt,
            collection_date=service_dt,
            completion_date=service_dt,
            amount=amount,
            payment_status="paid",
            payment_method=data.payment_method,
            payment_date=payment_dt,
            referred_by=data.referred_by,
            notes=data.notes,
            lab_bill_group_id=group_id,
            lab_bill_number=bill_number_label,
        )
        db.add(order)
        db.flush()
        order_ids.append(order.id)
        items.append({
            "item_type": "lab_test",
            "item_name": test.name,
            "item_code": test.test_code,
            "quantity": 1,
            "unit_price": amount,
            "total_price": amount,
        })

    bill, payment = create_bill_with_payment(
        db,
        patient_id=patient.id,
        hospital_id=hospital.id,
        created_by_id=current_user.id,
        bill_type="lab",
        items=items,
        service_date=data.service_date,
        payment_date=data.payment_date,
        payment_method=data.payment_method,
        reference_id=order_ids[0] if order_ids else None,
        notes=data.reason,
        referred_by=data.referred_by,
    )
    db.commit()
    log_catch_up(
        db, current_user, "catch_up_lab", "PatientLabOrder", order_ids[0],
        f"Catch-up lab bill {bill.bill_number}",
        service_date=data.service_date, payment_date=data.payment_date,
        reason=data.reason,
        extra={"bill_id": bill.id, "order_ids": order_ids, "amount": total},
    )
    return {
        "order_ids": order_ids,
        "bill_id": bill.id,
        "bill_number": bill.bill_number,
        "payment_id": payment.id,
        "total": round(total, 2),
    }


def service_date_str(d: date) -> str:
    return d.strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# Pharmacy POS (financial ledger; optional stock deduction)
# ---------------------------------------------------------------------------

class PharmacyLineIn(BaseModel):
    item_name: str = Field(..., min_length=1, max_length=200)
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    medicine_id: Optional[int] = None
    batch_id: Optional[int] = None


class PharmacyCatchUp(CatchUpDates):
    patient_id: Optional[int] = None
    patient_name: Optional[str] = None
    patient_phone: Optional[str] = None
    items: List[PharmacyLineIn] = Field(..., min_length=1)
    affect_stock: bool = False
    notes: Optional[str] = None


@router.post("/pharmacy-sale")
async def catch_up_pharmacy_sale(
    data: PharmacyCatchUp,
    current_user: User = Depends(require_feature_permission(Modules.BILLING, "catch_up_bills")),
    db: Session = Depends(get_db),
):
    assert_catch_up_dates(data.service_date, data.payment_date)
    hospital = get_hospital(db, current_user)
    patient = None
    if data.patient_id:
        patient = get_patient(db, data.patient_id, hospital.id)

    sale_dt = date_to_datetime(data.service_date)
    bill_items = []
    subtotal = 0.0
    for li in data.items:
        line_total = round(float(li.quantity) * float(li.unit_price), 2)
        subtotal += line_total
        bill_items.append({
            "item_type": "medicine",
            "item_name": li.item_name,
            "quantity": int(li.quantity) if float(li.quantity).is_integer() else 1,
            "unit_price": float(li.unit_price),
            "total_price": line_total,
        })

    sale = None
    if data.affect_stock:
        from app.routes.pharmacy import _next_sale_number
        for li in data.items:
            if not li.medicine_id or not li.batch_id:
                raise HTTPException(
                    status_code=400,
                    detail="affect_stock requires medicine_id and batch_id on every line",
                )
            batch = db.query(PharmacyInventory).filter(
                PharmacyInventory.id == li.batch_id,
                PharmacyInventory.medicine_id == li.medicine_id,
            ).first()
            if not batch:
                raise HTTPException(status_code=400, detail=f"Batch {li.batch_id} not found")
            qty = float(li.quantity)
            available = float(batch.quantity_in_stock or 0)
            if available < qty:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient stock on batch {li.batch_id}: need {qty}, have {available}",
                )
            batch.quantity_in_stock = int(available - qty)

        sale = PharmacySale(
            sale_number=_next_sale_number(db, hospital.id),
            sale_date=sale_dt,
            payment_type=data.payment_method or "cash",
            patient_phone=data.patient_phone or (patient.primary_phone if patient else None),
            patient_name=data.patient_name or (
                f"{patient.first_name} {patient.last_name}" if patient else None
            ),
            subtotal=subtotal,
            discount_total=0.0,
            tax_total=0.0,
            grand_total=subtotal,
            status="completed",
            billing_mode="cash_at_pharmacy",
            created_by=current_user.id,
            hospital_id=hospital.id,
        )
        db.add(sale)
        db.flush()
        for li in data.items:
            line_total = round(float(li.quantity) * float(li.unit_price), 2)
            db.add(PharmacySaleItem(
                sale_id=sale.id,
                medicine_id=li.medicine_id,
                batch_id=li.batch_id,
                quantity=float(li.quantity),
                rate=float(li.unit_price),
                line_total=line_total,
            ))

    if not patient:
        # Central Bill requires a patient_id — create a lightweight placeholder bill
        # only when patient is known; otherwise record pharmacy sale alone.
        if sale is None:
            raise HTTPException(
                status_code=400,
                detail="patient_id is required when affect_stock is false (central bill ledger)",
            )
        db.commit()
        log_catch_up(
            db, current_user, "catch_up_pharmacy_sale", "PharmacySale", sale.id,
            f"Catch-up pharmacy sale {sale.sale_number}",
            service_date=data.service_date, payment_date=data.payment_date,
            reason=data.reason,
            extra={"amount": subtotal, "affect_stock": True},
        )
        return {
            "sale_id": sale.id,
            "sale_number": sale.sale_number,
            "bill_id": None,
            "total": round(subtotal, 2),
        }

    bill, payment = create_bill_with_payment(
        db,
        patient_id=patient.id,
        hospital_id=hospital.id,
        created_by_id=current_user.id,
        bill_type="pharmacy",
        items=bill_items,
        service_date=data.service_date,
        payment_date=data.payment_date,
        payment_method=data.payment_method,
        reference_id=sale.id if sale else None,
        notes=data.reason or data.notes,
    )
    db.commit()
    log_catch_up(
        db, current_user, "catch_up_pharmacy_sale", "Bill", bill.id,
        f"Catch-up pharmacy bill {bill.bill_number}",
        service_date=data.service_date, payment_date=data.payment_date,
        reason=data.reason,
        extra={
            "bill_id": bill.id,
            "sale_id": sale.id if sale else None,
            "amount": subtotal,
            "affect_stock": data.affect_stock,
        },
    )
    return {
        "sale_id": sale.id if sale else None,
        "sale_number": sale.sale_number if sale else None,
        "bill_id": bill.id,
        "bill_number": bill.bill_number,
        "payment_id": payment.id,
        "total": round(subtotal, 2),
    }


# ---------------------------------------------------------------------------
# Canteen POS
# ---------------------------------------------------------------------------

class CanteenLineIn(BaseModel):
    item_id: Optional[int] = None
    item_name: str = Field(..., min_length=1, max_length=200)
    quantity: int = Field(1, gt=0)
    unit_price: float = Field(..., ge=0)


class CanteenCatchUp(CatchUpDates):
    patient_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    items: List[CanteenLineIn] = Field(..., min_length=1)
    notes: Optional[str] = None


@router.post("/canteen-sale")
async def catch_up_canteen_sale(
    data: CanteenCatchUp,
    current_user: User = Depends(require_feature_permission(Modules.BILLING, "catch_up_bills")),
    db: Session = Depends(get_db),
):
    assert_catch_up_dates(data.service_date, data.payment_date)
    hospital = get_hospital(db, current_user)
    patient = get_patient(db, data.patient_id, hospital.id) if data.patient_id else None

    from app.routes.canteen import _next_canteen_sale_number

    sale_dt = date_to_datetime(data.service_date)
    lines = []
    subtotal = Decimal("0.00")
    for li in data.items:
        unit = Decimal(str(round(float(li.unit_price), 2)))
        qty = int(li.quantity)
        line_total = Decimal(str(round(float(unit) * qty, 2)))
        subtotal += line_total
        name = li.item_name
        if li.item_id:
            cat = db.query(CanteenItem).filter(
                CanteenItem.id == li.item_id,
                CanteenItem.hospital_id == hospital.id,
            ).first()
            if cat:
                name = cat.name
        lines.append((li.item_id, name, unit, qty, line_total))

    sale = CanteenSale(
        hospital_id=hospital.id,
        sale_number=_next_canteen_sale_number(db, hospital.id),
        sale_date=sale_dt,
        status="completed",
        payment_type=data.payment_method or "cash",
        customer_name=data.customer_name or (
            f"{patient.first_name} {patient.last_name}" if patient else None
        ),
        customer_phone=data.customer_phone or (patient.primary_phone if patient else None),
        subtotal=subtotal,
        discount_amount=Decimal("0.00"),
        grand_total=subtotal,
        notes=data.notes,
        created_by_id=current_user.id,
    )
    db.add(sale)
    db.flush()
    for item_id, name, unit, qty, line_total in lines:
        db.add(CanteenSaleItem(
            sale_id=sale.id,
            item_id=item_id,
            item_name=name,
            unit_price=unit,
            quantity=qty,
            line_total=line_total,
        ))

    bill = payment = None
    if patient:
        bill_items = [
            {
                "item_type": "canteen",
                "item_name": name,
                "quantity": qty,
                "unit_price": float(unit),
                "total_price": float(line_total),
            }
            for _, name, unit, qty, line_total in lines
        ]
        bill, payment = create_bill_with_payment(
            db,
            patient_id=patient.id,
            hospital_id=hospital.id,
            created_by_id=current_user.id,
            bill_type="canteen",
            items=bill_items,
            service_date=data.service_date,
            payment_date=data.payment_date,
            payment_method=data.payment_method,
            reference_id=sale.id,
            notes=data.reason or data.notes,
        )

    db.commit()
    log_catch_up(
        db, current_user, "catch_up_canteen_sale", "CanteenSale", sale.id,
        f"Catch-up canteen sale {sale.sale_number}",
        service_date=data.service_date, payment_date=data.payment_date,
        reason=data.reason,
        extra={
            "sale_id": sale.id,
            "bill_id": bill.id if bill else None,
            "amount": float(subtotal),
        },
    )
    return {
        "sale_id": sale.id,
        "sale_number": sale.sale_number,
        "bill_id": bill.id if bill else None,
        "bill_number": bill.bill_number if bill else None,
        "payment_id": payment.id if payment else None,
        "total": float(subtotal),
    }


# ---------------------------------------------------------------------------
# Misc bill
# ---------------------------------------------------------------------------

class MiscCatchUp(CatchUpDates):
    patient_id: int
    items: List[LineItemIn] = Field(..., min_length=1)
    notes: Optional[str] = None
    referred_by: Optional[str] = None


@router.post("/misc-bill")
async def catch_up_misc_bill(
    data: MiscCatchUp,
    current_user: User = Depends(require_feature_permission(Modules.BILLING, "catch_up_bills")),
    db: Session = Depends(get_db),
):
    assert_catch_up_dates(data.service_date, data.payment_date)
    hospital = get_hospital(db, current_user)
    patient = get_patient(db, data.patient_id, hospital.id)

    items = []
    for li in data.items:
        total = round(float(li.quantity) * float(li.unit_price), 2)
        items.append({
            "item_type": li.item_type or "misc",
            "item_name": li.item_name,
            "item_code": li.item_code,
            "quantity": li.quantity,
            "unit_price": float(li.unit_price),
            "total_price": total,
        })

    bill, payment = create_bill_with_payment(
        db,
        patient_id=patient.id,
        hospital_id=hospital.id,
        created_by_id=current_user.id,
        bill_type="catch_up",
        items=items,
        service_date=data.service_date,
        payment_date=data.payment_date,
        payment_method=data.payment_method,
        notes=data.reason or data.notes,
        referred_by=data.referred_by,
    )
    db.commit()
    log_catch_up(
        db, current_user, "catch_up_misc_bill", "Bill", bill.id,
        f"Catch-up misc bill {bill.bill_number}",
        service_date=data.service_date, payment_date=data.payment_date,
        reason=data.reason,
        extra={"bill_id": bill.id, "amount": float(bill.total_amount or 0)},
    )
    return {
        "bill_id": bill.id,
        "bill_number": bill.bill_number,
        "payment_id": payment.id,
        "total": float(bill.total_amount or 0),
    }


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@router.get("/history")
async def catch_up_history(
    limit: int = 50,
    current_user: User = Depends(require_feature_permission(Modules.BILLING, "catch_up_bills")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action.like("catch_up_%"))
        .order_by(AuditLog.timestamp.desc())
        .limit(min(limit, 200))
        .all()
    )
    out = []
    for r in rows:
        out.append({
            "id": r.id,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "user_name": r.user_name,
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "description": r.description,
            "details": r.details,
        })
    return out


# ---------------------------------------------------------------------------
# Inpatient stay reconstruction
# ---------------------------------------------------------------------------

class VisitIn(BaseModel):
    visit_type: str = "doctor_visit"
    visitor_id: int
    visit_datetime: datetime
    charge_amount: float = 0
    notes: Optional[str] = None


class AncillaryIn(BaseModel):
    service_id: int
    quantity: float = 1
    unit_price: Optional[float] = None
    charged_at: Optional[datetime] = None
    notes: Optional[str] = None


class CanteenOrderLineIn(BaseModel):
    item_id: Optional[int] = None
    item_name: str
    quantity: int = 1
    unit_price: float


class CanteenOrderIn(BaseModel):
    serve_date: Optional[date] = None
    items: List[CanteenOrderLineIn] = Field(..., min_length=1)
    notes: Optional[str] = None


class DepositIn(BaseModel):
    amount: float = Field(..., gt=0)
    payment_method: str = "cash"
    deposit_type: str = "initial"
    received_at: Optional[datetime] = None
    notes: Optional[str] = None


class PharmacyIpLineIn(BaseModel):
    """Financial-only medicine line rolled into the admission bill (no stock)."""
    item_name: str = Field(..., min_length=1, max_length=200)
    quantity: float = Field(1, gt=0)
    unit_price: float = Field(..., ge=0)


class InpatientStayCatchUp(CatchUpDates):
    patient_id: int
    admitting_doctor_id: int
    room_id: int
    admission_date: datetime
    discharge_date: datetime
    admission_type: str = "elective"
    admission_reason: Optional[str] = None
    is_observation: bool = False
    visits: List[VisitIn] = []
    ancillary: List[AncillaryIn] = []
    canteen_orders: List[CanteenOrderIn] = []
    pharmacy_lines: List[PharmacyIpLineIn] = []
    surgery_package_id: Optional[int] = None
    surgery_package_price: Optional[float] = None
    deposits: List[DepositIn] = []
    discharge_type: str = "normal"
    condition_on_discharge: Optional[str] = "stable"
    discharge_summary: Optional[str] = None
    diagnosis_on_discharge: Optional[str] = None


@router.post("/inpatient-stay")
async def catch_up_inpatient_stay(
    data: InpatientStayCatchUp,
    current_user: User = Depends(require_feature_permission(Modules.BILLING, "catch_up_bills")),
    db: Session = Depends(get_db),
):
    assert_catch_up_dates(data.service_date, data.payment_date)
    if data.discharge_date < data.admission_date:
        raise HTTPException(status_code=400, detail="discharge_date must be on or after admission_date")

    hospital = get_hospital(db, current_user)
    patient = get_patient(db, data.patient_id, hospital.id)
    doctor = db.query(User).filter(
        User.id == data.admitting_doctor_id, User.hospital_id == hospital.id
    ).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Admitting doctor not found")
    room = db.query(RoomManagement).filter(RoomManagement.id == data.room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Block only if patient currently has a live admitted stay (not catch-up)
    live = db.query(Admission).filter(
        Admission.patient_id == patient.id,
        Admission.status == "admitted",
        Admission.is_catch_up == False,  # noqa: E712
    ).first()
    if live:
        raise HTTPException(
            status_code=409,
            detail=f"Patient already has an active admission ({live.admission_number})",
        )

    today = datetime.now().strftime("%Y%m%d")
    prefix = f"ADM-CU-{today}-"
    last = db.query(Admission).filter(Admission.admission_number.like(f"{prefix}%")).order_by(Admission.id.desc()).first()
    seq = (int(last.admission_number.rsplit("-", 1)[-1]) + 1) if last else 1
    adm_number = f"{prefix}{seq:04d}"

    admission = Admission(
        admission_number=adm_number,
        patient_id=patient.id,
        admitting_doctor_id=doctor.id,
        room_id=room.id,
        admission_date=data.admission_date,
        admission_type=data.admission_type or "elective",
        admission_reason=data.admission_reason,
        status="admitted",
        is_observation=bool(data.is_observation),
        is_catch_up=True,
        initial_room_charge_per_day=float(room.room_charge_per_day or 0),
        acceptance_status="accepted",
        accepted_at=data.admission_date,
        accepted_by_doctor_id=doctor.id,
        bed_number=None,
        bed_id=None,
    )
    db.add(admission)
    db.flush()

    for v in data.visits:
        db.add(PatientVisit(
            admission_id=admission.id,
            patient_id=patient.id,
            visitor_id=v.visitor_id,
            visit_type=v.visit_type or "doctor_visit",
            visit_datetime=v.visit_datetime,
            notes=v.notes,
            charge_amount=float(v.charge_amount or 0),
            billed=False,
            auto_posted=False,
            created_by_id=current_user.id,
            hospital_id=hospital.id,
        ))

    for a in data.ancillary:
        svc = db.query(AncillaryServiceCatalog).filter(
            AncillaryServiceCatalog.id == a.service_id,
            AncillaryServiceCatalog.hospital_id == hospital.id,
        ).first()
        if not svc:
            raise HTTPException(status_code=400, detail=f"Ancillary service {a.service_id} not found")
        unit = float(a.unit_price if a.unit_price is not None else (svc.default_charge or 0))
        qty = float(a.quantity or 1)
        db.add(AdmissionAncillaryCharge(
            admission_id=admission.id,
            service_id=svc.id,
            quantity=qty,
            unit_price=unit,
            total_amount=round(unit * qty, 2),
            charged_at=a.charged_at or data.admission_date,
            notes=a.notes,
            hospital_id=hospital.id,
            created_by_id=current_user.id,
        ))

    for co in data.canteen_orders:
        order = CanteenOrder(
            hospital_id=hospital.id,
            admission_id=admission.id,
            patient_id=patient.id,
            status="delivered",
            notes=co.notes,
            serve_date=co.serve_date or data.admission_date.date(),
            ordered_at=date_to_datetime(co.serve_date or data.admission_date.date()),
            ordered_by_id=current_user.id,
            billed=False,
        )
        db.add(order)
        db.flush()
        for li in co.items:
            unit = Decimal(str(round(float(li.unit_price), 2)))
            qty = int(li.quantity)
            db.add(CanteenOrderItem(
                order_id=order.id,
                item_id=li.item_id,
                item_name=li.item_name,
                unit_price=unit,
                quantity=qty,
                line_total=Decimal(str(round(float(unit) * qty, 2))),
            ))

    # Financial-only pharmacy sale deferred to admission bill (no stock deduction)
    if data.pharmacy_lines:
        from app.routes.pharmacy import _next_sale_number
        pharm_total = round(
            sum(float(li.quantity) * float(li.unit_price) for li in data.pharmacy_lines),
            2,
        )
        if pharm_total > 0:
            names = ", ".join(li.item_name for li in data.pharmacy_lines[:5])
            if len(data.pharmacy_lines) > 5:
                names += f" (+{len(data.pharmacy_lines) - 5} more)"
            sale = PharmacySale(
                sale_number=_next_sale_number(db, hospital.id),
                sale_date=data.admission_date,
                payment_type="credit",
                patient_name=f"{patient.first_name} {patient.last_name}",
                patient_phone=patient.primary_phone,
                patient_address=f"Catch-up: {names}",
                subtotal=pharm_total,
                discount_total=0.0,
                tax_total=0.0,
                grand_total=pharm_total,
                status="completed",
                admission_id=admission.id,
                billing_mode="inpatient_bill",
                created_by=current_user.id,
                hospital_id=hospital.id,
            )
            db.add(sale)
            db.flush()

    if data.surgery_package_id:
        pkg = db.query(SurgeryPackage).filter(
            SurgeryPackage.id == data.surgery_package_id,
            SurgeryPackage.hospital_id == hospital.id,
        ).first()
        if not pkg:
            raise HTTPException(status_code=400, detail="Surgery package not found")
        agreed = (
            float(data.surgery_package_price)
            if data.surgery_package_price is not None
            else float(pkg.base_price or 0)
        )
        db.add(AdmissionPackage(
            admission_id=admission.id,
            package_id=pkg.id,
            agreed_price=agreed,
            applied_by_id=current_user.id,
            notes="Catch-up reconstruction",
        ))
        db.flush()

    payment_dt = date_to_datetime(data.payment_date)
    for d in data.deposits:
        dep_day = (d.received_at or payment_dt).strftime("%Y%m%d")
        dep_prefix = f"DEP-CU-{dep_day}-"
        last_dep = (
            db.query(AdmissionDeposit)
            .filter(AdmissionDeposit.deposit_number.like(f"{dep_prefix}%"))
            .order_by(AdmissionDeposit.id.desc())
            .first()
        )
        dep_seq = (int(last_dep.deposit_number.rsplit("-", 1)[-1]) + 1) if last_dep else 1
        dep = AdmissionDeposit(
            admission_id=admission.id,
            deposit_number=f"{dep_prefix}{dep_seq:04d}",
            amount=float(d.amount),
            deposit_type=d.deposit_type or "initial",
            payment_method=d.payment_method or data.payment_method,
            received_by_id=current_user.id,
            received_at=d.received_at or payment_dt,
            notes=d.notes,
            hospital_id=hospital.id,
        )
        db.add(dep)

    # If no deposits provided, create one covering the bill after we know the total
    db.flush()

    discharge = DischargeRecord(
        admission_id=admission.id,
        discharge_date=data.discharge_date,
        discharge_type=data.discharge_type or "normal",
        condition_on_discharge=data.condition_on_discharge,
        discharge_summary=data.discharge_summary or "Catch-up reconstruction",
        diagnosis_on_discharge=data.diagnosis_on_discharge,
        discharge_approved_by_id=current_user.id,
        total_stay_days=max((data.discharge_date - data.admission_date).days, 1),
    )
    db.add(discharge)
    admission.status = "discharged"
    db.flush()
    db.refresh(admission)

    from app.routes.inpatient import (
        _compute_admission_charges,
        _create_admission_bill_record_inner,
        reconcile_admission_bill_statuses,
    )

    breakdown = _compute_admission_charges(db, admission, unbilled_only=True)
    grand = float(breakdown.get("grand_total") or breakdown.get("subtotal") or 0)

    # Ensure deposits cover the bill so finalize/reconcile marks paid
    existing_deps = sum(
        float(d.amount or 0)
        for d in db.query(AdmissionDeposit).filter(AdmissionDeposit.admission_id == admission.id).all()
    )
    if not data.deposits and grand > 0.01:
        dep_day = data.payment_date.strftime("%Y%m%d")
        dep_prefix = f"DEP-CU-{dep_day}-"
        last_dep = (
            db.query(AdmissionDeposit)
            .filter(AdmissionDeposit.deposit_number.like(f"{dep_prefix}%"))
            .order_by(AdmissionDeposit.id.desc())
            .first()
        )
        dep_seq = (int(last_dep.deposit_number.rsplit("-", 1)[-1]) + 1) if last_dep else 1
        db.add(AdmissionDeposit(
            admission_id=admission.id,
            deposit_number=f"{dep_prefix}{dep_seq:04d}",
            amount=grand,
            deposit_type="initial",
            payment_method=data.payment_method or "cash",
            received_by_id=current_user.id,
            received_at=payment_dt,
            notes="Auto deposit for catch-up stay",
            hospital_id=hospital.id,
        ))
        db.flush()
        existing_deps = grand
    elif data.deposits and existing_deps + 0.01 < grand:
        # Top up remaining balance
        shortfall = round(grand - existing_deps, 2)
        dep_day = data.payment_date.strftime("%Y%m%d")
        dep_prefix = f"DEP-CU-{dep_day}-"
        last_dep = (
            db.query(AdmissionDeposit)
            .filter(AdmissionDeposit.deposit_number.like(f"{dep_prefix}%"))
            .order_by(AdmissionDeposit.id.desc())
            .first()
        )
        dep_seq = (int(last_dep.deposit_number.rsplit("-", 1)[-1]) + 1) if last_dep else 1
        db.add(AdmissionDeposit(
            admission_id=admission.id,
            deposit_number=f"{dep_prefix}{dep_seq:04d}",
            amount=shortfall,
            deposit_type="topup",
            payment_method=data.payment_method or "cash",
            received_by_id=current_user.id,
            received_at=payment_dt,
            notes="Auto top-up for catch-up stay settlement",
            hospital_id=hospital.id,
        ))
        db.flush()

    # Recompute after any auto deposit
    db.expire(admission)
    admission = db.query(Admission).options(
        joinedload(Admission.discharge),
        joinedload(Admission.deposits),
    ).filter(Admission.id == admission.id).first()
    breakdown = _compute_admission_charges(db, admission, unbilled_only=True)

    bill = _create_admission_bill_record_inner(
        db, admission, hospital, current_user, breakdown,
        discount_value=0, discount_type="flat", tax_percentage=0,
        bill_subtype="final",
    )
    # Inner helper commits — re-attach and stamp dates
    bill = db.query(Bill).filter(Bill.id == bill.id).first()
    bill.bill_date = date_to_datetime(data.service_date)
    if data.reason:
        bill.notes = ((bill.notes or "") + f"\nCatch-up: {data.reason}").strip()

    # Also record a Payment row for daily-collection reports
    pay_day = data.payment_date.strftime("%Y%m%d")
    from app.services.catch_up_service import next_payment_number
    payment = Payment(
        payment_number=next_payment_number(db, f"PAY-{pay_day}-"),
        bill_id=bill.id,
        amount_paid=float(bill.total_amount or 0),
        payment_method_name=data.payment_method or "cash",
        payment_date=payment_dt,
        received_by_id=current_user.id,
        notes="Catch-up inpatient settlement",
    )
    db.add(payment)
    bill.status = "paid"

    reconcile_admission_bill_statuses(db, admission.id)
    bill.status = "paid"
    db.commit()

    log_catch_up(
        db, current_user, "catch_up_inpatient_stay", "Admission", admission.id,
        f"Catch-up inpatient stay {admission.admission_number}",
        service_date=data.service_date, payment_date=data.payment_date,
        reason=data.reason,
        extra={
            "admission_id": admission.id,
            "bill_id": bill.id,
            "payment_id": payment.id,
            "amount": float(bill.total_amount or 0),
            "admission_date": data.admission_date.isoformat(),
            "discharge_date": data.discharge_date.isoformat(),
        },
    )
    return {
        "admission_id": admission.id,
        "admission_number": admission.admission_number,
        "bill_id": bill.id,
        "bill_number": bill.bill_number,
        "payment_id": payment.id,
        "total": float(bill.total_amount or 0),
        "status": admission.status,
        "is_catch_up": True,
    }


@router.post("/inpatient-stay/preview")
async def catch_up_inpatient_preview(
    data: InpatientStayCatchUp,
    current_user: User = Depends(require_feature_permission(Modules.BILLING, "catch_up_bills")),
    db: Session = Depends(get_db),
):
    """Dry-run charge estimate without persisting. Uses temporary in-memory math
    similar to a real stay (room days + visit/ancillary/canteen sums)."""
    assert_catch_up_dates(data.service_date, data.payment_date)
    if data.discharge_date < data.admission_date:
        raise HTTPException(status_code=400, detail="discharge_date must be on or after admission_date")
    hospital = get_hospital(db, current_user)
    room = db.query(RoomManagement).filter(RoomManagement.id == data.room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    stay_days = max((data.discharge_date - data.admission_date).days, 1)
    room_rate = 0.0 if data.is_observation else float(room.room_charge_per_day or 0)
    room_total = round(room_rate * stay_days, 2)
    visit_total = round(sum(float(v.charge_amount or 0) for v in data.visits), 2)

    ancillary_total = 0.0
    for a in data.ancillary:
        svc = db.query(AncillaryServiceCatalog).filter(
            AncillaryServiceCatalog.id == a.service_id
        ).first()
        unit = float(a.unit_price if a.unit_price is not None else (svc.default_charge if svc else 0) or 0)
        ancillary_total += unit * float(a.quantity or 1)
    ancillary_total = round(ancillary_total, 2)

    food_total = 0.0
    for co in data.canteen_orders:
        for li in co.items:
            food_total += float(li.unit_price) * int(li.quantity)
    food_total = round(food_total, 2)

    pharmacy_total = round(
        sum(float(li.quantity) * float(li.unit_price) for li in data.pharmacy_lines),
        2,
    )

    package_total = 0.0
    if data.surgery_package_id:
        if data.surgery_package_price is not None:
            package_total = float(data.surgery_package_price)
        else:
            pkg = db.query(SurgeryPackage).filter(SurgeryPackage.id == data.surgery_package_id).first()
            package_total = float(pkg.base_price or 0) if pkg else 0.0

    subtotal = round(
        room_total + visit_total + ancillary_total + food_total + pharmacy_total + package_total,
        2,
    )
    return {
        "stay_days": stay_days,
        "room_total": room_total,
        "visit_total": visit_total,
        "ancillary_total": ancillary_total,
        "food_total": food_total,
        "pharmacy_total": pharmacy_total,
        "package_total": package_total,
        "subtotal": subtotal,
        "grand_total": subtotal,
    }


# ---------------------------------------------------------------------------
# Append charges to an existing catch-up stay (re-finalize)
# ---------------------------------------------------------------------------

class AppendChargesCatchUp(CatchUpDates):
    visits: List[VisitIn] = []
    ancillary: List[AncillaryIn] = []
    canteen_orders: List[CanteenOrderIn] = []
    pharmacy_lines: List[PharmacyIpLineIn] = []


def _release_admission_bill_sources(db: Session, bill: Bill) -> dict:
    """Clear source→bill links so charges can be re-billed. Does not commit."""
    visits_q = db.query(PatientVisit).filter(PatientVisit.bill_id == bill.id)
    visits_released = visits_q.count()
    visits_q.update({PatientVisit.billed: False, PatientVisit.bill_id: None}, synchronize_session=False)

    ot_q = db.query(OTSchedule).filter(OTSchedule.bill_id == bill.id)
    ot_released = ot_q.count()
    ot_q.update({OTSchedule.billed: False, OTSchedule.bill_id: None}, synchronize_session=False)

    anc_q = db.query(AdmissionAncillaryCharge).filter(AdmissionAncillaryCharge.bill_id == bill.id)
    anc_released = anc_q.count()
    anc_q.update({AdmissionAncillaryCharge.billed: False, AdmissionAncillaryCharge.bill_id: None}, synchronize_session=False)

    rx_q = db.query(Prescription).filter(Prescription.inpatient_bill_id == bill.id)
    rx_released = rx_q.count()
    rx_q.update({Prescription.inpatient_bill_id: None}, synchronize_session=False)

    pos_q = db.query(PharmacySale).filter(PharmacySale.inpatient_bill_id == bill.id)
    pos_released = pos_q.count()
    pos_q.update({PharmacySale.inpatient_bill_id: None}, synchronize_session=False)

    lab_q = db.query(PatientLabOrder).filter(PatientLabOrder.inpatient_bill_id == bill.id)
    lab_released = lab_q.count()
    lab_q.update({PatientLabOrder.inpatient_bill_id: None}, synchronize_session=False)

    food_q = db.query(FoodOrder).filter(FoodOrder.bill_id == bill.id)
    food_released = food_q.count()
    food_q.update({FoodOrder.billed: False, FoodOrder.bill_id: None}, synchronize_session=False)

    canteen_q = db.query(CanteenOrder).filter(CanteenOrder.bill_id == bill.id)
    canteen_released = canteen_q.count()
    canteen_q.update({CanteenOrder.billed: False, CanteenOrder.bill_id: None}, synchronize_session=False)

    return {
        "visits": visits_released,
        "ot": ot_released,
        "ancillary": anc_released,
        "prescriptions": rx_released,
        "pharmacy_pos_sales": pos_released,
        "lab_orders": lab_released,
        "food_orders": food_released,
        "canteen_orders": canteen_released,
    }


def _add_catch_up_charge_rows(
    db: Session,
    *,
    admission: Admission,
    patient,
    hospital,
    current_user: User,
    visits: List[VisitIn],
    ancillary: List[AncillaryIn],
    canteen_orders: List[CanteenOrderIn],
    pharmacy_lines: List[PharmacyIpLineIn],
    default_dt: datetime,
):
    """Persist optional visit / ancillary / food / pharmacy rows on a catch-up admission."""
    for v in visits:
        db.add(PatientVisit(
            admission_id=admission.id,
            patient_id=patient.id,
            visitor_id=v.visitor_id,
            visit_type=v.visit_type or "doctor_visit",
            visit_datetime=v.visit_datetime,
            notes=v.notes,
            charge_amount=float(v.charge_amount or 0),
            billed=False,
            auto_posted=False,
            created_by_id=current_user.id,
            hospital_id=hospital.id,
        ))

    for a in ancillary:
        svc = db.query(AncillaryServiceCatalog).filter(
            AncillaryServiceCatalog.id == a.service_id,
            AncillaryServiceCatalog.hospital_id == hospital.id,
        ).first()
        if not svc:
            raise HTTPException(status_code=400, detail=f"Ancillary service {a.service_id} not found")
        unit = float(a.unit_price if a.unit_price is not None else (svc.default_charge or 0))
        qty = float(a.quantity or 1)
        db.add(AdmissionAncillaryCharge(
            admission_id=admission.id,
            service_id=svc.id,
            quantity=qty,
            unit_price=unit,
            total_amount=round(unit * qty, 2),
            charged_at=a.charged_at or default_dt,
            notes=a.notes,
            hospital_id=hospital.id,
            created_by_id=current_user.id,
        ))

    for co in canteen_orders:
        order = CanteenOrder(
            hospital_id=hospital.id,
            admission_id=admission.id,
            patient_id=patient.id,
            status="delivered",
            notes=co.notes,
            serve_date=co.serve_date or default_dt.date(),
            ordered_at=date_to_datetime(co.serve_date or default_dt.date()),
            ordered_by_id=current_user.id,
            billed=False,
        )
        db.add(order)
        db.flush()
        for li in co.items:
            unit = Decimal(str(round(float(li.unit_price), 2)))
            qty = int(li.quantity)
            db.add(CanteenOrderItem(
                order_id=order.id,
                item_id=li.item_id,
                item_name=li.item_name,
                unit_price=unit,
                quantity=qty,
                line_total=Decimal(str(round(float(unit) * qty, 2))),
            ))

    if pharmacy_lines:
        from app.routes.pharmacy import _next_sale_number
        pharm_total = round(
            sum(float(li.quantity) * float(li.unit_price) for li in pharmacy_lines),
            2,
        )
        if pharm_total > 0:
            names = ", ".join(li.item_name for li in pharmacy_lines[:5])
            if len(pharmacy_lines) > 5:
                names += f" (+{len(pharmacy_lines) - 5} more)"
            sale = PharmacySale(
                sale_number=_next_sale_number(db, hospital.id),
                sale_date=default_dt,
                payment_type="credit",
                patient_name=f"{patient.first_name} {patient.last_name}",
                patient_phone=patient.primary_phone,
                patient_address=f"Catch-up append: {names}",
                subtotal=pharm_total,
                discount_total=0.0,
                tax_total=0.0,
                grand_total=pharm_total,
                status="completed",
                admission_id=admission.id,
                billing_mode="inpatient_bill",
                created_by=current_user.id,
                hospital_id=hospital.id,
            )
            db.add(sale)


@router.post("/inpatient/{admission_id}/append-charges")
async def catch_up_append_charges(
    admission_id: int,
    data: AppendChargesCatchUp,
    current_user: User = Depends(require_feature_permission(Modules.BILLING, "catch_up_bills")),
    db: Session = Depends(get_db),
):
    """Reopen a catch-up discharged stay: cancel paid final bill, add omitted
    charges, and re-finalize with new Service/Payment dates."""
    assert_catch_up_dates(data.service_date, data.payment_date)
    if not (data.visits or data.ancillary or data.canteen_orders or data.pharmacy_lines):
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: visits, ancillary, canteen_orders, pharmacy_lines",
        )

    hospital = get_hospital(db, current_user)
    admission = (
        db.query(Admission)
        .options(joinedload(Admission.discharge), joinedload(Admission.deposits))
        .filter(Admission.id == admission_id)
        .first()
    )
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if not admission.is_catch_up:
        raise HTTPException(status_code=400, detail="Append-charges is only for catch-up admissions")
    if admission.status != "discharged":
        raise HTTPException(status_code=400, detail="Catch-up admission must be discharged")

    patient = get_patient(db, admission.patient_id, hospital.id)

    old_bill = (
        db.query(Bill)
        .filter(
            Bill.bill_type == "admission",
            Bill.reference_id == admission.id,
            Bill.status != "cancelled",
        )
        .order_by(Bill.id.desc())
        .first()
    )
    if not old_bill:
        raise HTTPException(status_code=404, detail="No active admission bill to reopen")

    # Privileged catch-up path: drop Payment rows so cancel/release can proceed.
    for pay in db.query(Payment).filter(Payment.bill_id == old_bill.id).all():
        db.delete(pay)
    db.flush()

    released = _release_admission_bill_sources(db, old_bill)
    old_bill.status = "cancelled"
    cancel_note = (
        f"[CATCH-UP APPEND cancel by user {current_user.id} on {datetime.now().isoformat()}]"
        + (f": {data.reason}" if data.reason else "")
    )
    old_bill.notes = (old_bill.notes + "\n" if old_bill.notes else "") + cancel_note
    db.flush()

    charge_dt = admission.admission_date or date_to_datetime(data.service_date)
    _add_catch_up_charge_rows(
        db,
        admission=admission,
        patient=patient,
        hospital=hospital,
        current_user=current_user,
        visits=data.visits,
        ancillary=data.ancillary,
        canteen_orders=data.canteen_orders,
        pharmacy_lines=data.pharmacy_lines,
        default_dt=charge_dt,
    )
    db.flush()

    from app.routes.inpatient import (
        _compute_admission_charges,
        _create_admission_bill_record_inner,
        reconcile_admission_bill_statuses,
    )
    from app.services.catch_up_service import next_payment_number

    db.expire(admission)
    admission = (
        db.query(Admission)
        .options(joinedload(Admission.discharge), joinedload(Admission.deposits))
        .filter(Admission.id == admission.id)
        .first()
    )
    breakdown = _compute_admission_charges(db, admission, unbilled_only=True)
    grand = float(breakdown.get("grand_total") or breakdown.get("subtotal") or 0)

    payment_dt = date_to_datetime(data.payment_date)
    existing_deps = sum(float(d.amount or 0) for d in (admission.deposits or []))
    if grand > 0.01 and existing_deps + 0.01 < grand:
        shortfall = round(grand - existing_deps, 2)
        dep_day = data.payment_date.strftime("%Y%m%d")
        dep_prefix = f"DEP-CU-{dep_day}-"
        last_dep = (
            db.query(AdmissionDeposit)
            .filter(AdmissionDeposit.deposit_number.like(f"{dep_prefix}%"))
            .order_by(AdmissionDeposit.id.desc())
            .first()
        )
        dep_seq = (int(last_dep.deposit_number.rsplit("-", 1)[-1]) + 1) if last_dep else 1
        db.add(AdmissionDeposit(
            admission_id=admission.id,
            deposit_number=f"{dep_prefix}{dep_seq:04d}",
            amount=shortfall,
            deposit_type="topup",
            payment_method=data.payment_method or "cash",
            received_by_id=current_user.id,
            received_at=payment_dt,
            notes="Auto top-up for catch-up append-charges",
            hospital_id=hospital.id,
        ))
        db.flush()
        db.expire(admission)
        admission = (
            db.query(Admission)
            .options(joinedload(Admission.discharge), joinedload(Admission.deposits))
            .filter(Admission.id == admission.id)
            .first()
        )
        breakdown = _compute_admission_charges(db, admission, unbilled_only=True)

    bill = _create_admission_bill_record_inner(
        db, admission, hospital, current_user, breakdown,
        discount_value=0, discount_type="flat", tax_percentage=0,
        bill_subtype="final",
    )
    bill = db.query(Bill).filter(Bill.id == bill.id).first()
    bill.bill_date = date_to_datetime(data.service_date)
    if data.reason:
        bill.notes = ((bill.notes or "") + f"\nCatch-up append: {data.reason}").strip()

    payment = Payment(
        payment_number=next_payment_number(db, f"PAY-{data.payment_date.strftime('%Y%m%d')}-"),
        bill_id=bill.id,
        amount_paid=float(bill.total_amount or 0),
        payment_method_name=data.payment_method or "cash",
        payment_date=payment_dt,
        received_by_id=current_user.id,
        notes="Catch-up append-charges settlement",
    )
    db.add(payment)
    bill.status = "paid"
    reconcile_admission_bill_statuses(db, admission.id)
    bill.status = "paid"
    db.commit()

    log_catch_up(
        db, current_user, "catch_up_append_charges", "Admission", admission.id,
        f"Catch-up append charges on {admission.admission_number}",
        service_date=data.service_date, payment_date=data.payment_date,
        reason=data.reason,
        extra={
            "admission_id": admission.id,
            "cancelled_bill_id": old_bill.id,
            "bill_id": bill.id,
            "payment_id": payment.id,
            "amount": float(bill.total_amount or 0),
            "released": released,
        },
    )
    return {
        "admission_id": admission.id,
        "admission_number": admission.admission_number,
        "cancelled_bill_id": old_bill.id,
        "bill_id": bill.id,
        "bill_number": bill.bill_number,
        "payment_id": payment.id,
        "total": float(bill.total_amount or 0),
        "released": released,
        "is_catch_up": True,
    }
