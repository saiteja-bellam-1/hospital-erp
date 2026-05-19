"""Outpatient procedures — billing-only catalog + bill builder.

Designed for day-care centres / OPD desks. The hospital admin maintains a
list of procedures with default prices (Dental cleaning, IV drip, dressing, …)
and receptionists / doctors generate bills by picking from the catalog OR
typing one-off lines. The bill itself lives in the existing `bills` table
with `bill_type='procedure'`, so it inherits the central Billing dashboard,
payments, refunds, credit notes and PDF rendering for free."""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.utils.dependencies import get_current_user
from app.models.user import User
from app.models.patient import Patient
from app.models.outpatient import OutpatientProcedure
from app.models.billing import Bill, BillItem, Payment
from app.services.audit_service import log_action
from config.database import get_db

router = APIRouter()


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------

def _admin_only(user: User):
    if not any(r in user.role_names for r in ('super_admin', 'hospital_admin')):
        raise HTTPException(status_code=403, detail="Admin role required")


def _can_bill(user: User):
    if not any(r in user.role_names for r in
               ('super_admin', 'hospital_admin', 'receptionist', 'doctor')):
        raise HTTPException(status_code=403, detail="Not authorized to create procedure bills")


# ---------------------------------------------------------------------------
# Catalog CRUD
# ---------------------------------------------------------------------------

class ProcedureIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    code: Optional[str] = Field(None, max_length=50)
    category: Optional[str] = Field(None, max_length=80)
    default_price: float = Field(..., ge=0)
    description: Optional[str] = None
    is_active: bool = True


class ProcedureOut(BaseModel):
    id: int
    name: str
    code: Optional[str]
    category: Optional[str]
    default_price: float
    description: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/procedures", response_model=List[ProcedureOut])
async def list_procedures(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(OutpatientProcedure).filter(
        OutpatientProcedure.hospital_id == current_user.hospital_id
    )
    if not include_inactive:
        q = q.filter(OutpatientProcedure.is_active == True)
    return q.order_by(OutpatientProcedure.name).all()


@router.post("/procedures", response_model=ProcedureOut, status_code=201)
async def create_procedure(
    data: ProcedureIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _admin_only(current_user)
    proc = OutpatientProcedure(
        name=data.name.strip(),
        code=data.code,
        category=data.category,
        default_price=data.default_price,
        description=data.description,
        is_active=data.is_active,
        hospital_id=current_user.hospital_id,
        created_by_id=current_user.id,
    )
    db.add(proc)
    db.commit()
    db.refresh(proc)
    log_action(db, current_user, "create_procedure", "outpatient",
               "OutpatientProcedure", proc.id, f"Created procedure '{proc.name}'")
    return proc


@router.patch("/procedures/{procedure_id}", response_model=ProcedureOut)
async def update_procedure(
    procedure_id: int,
    data: ProcedureIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _admin_only(current_user)
    proc = db.query(OutpatientProcedure).filter(
        OutpatientProcedure.id == procedure_id,
        OutpatientProcedure.hospital_id == current_user.hospital_id,
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procedure not found")
    proc.name = data.name.strip()
    proc.code = data.code
    proc.category = data.category
    proc.default_price = data.default_price
    proc.description = data.description
    proc.is_active = data.is_active
    db.commit()
    db.refresh(proc)
    log_action(db, current_user, "update_procedure", "outpatient",
               "OutpatientProcedure", proc.id, f"Updated procedure '{proc.name}'")
    return proc


@router.delete("/procedures/{procedure_id}", status_code=204)
async def deactivate_procedure(
    procedure_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft delete — flips is_active=false. Existing bills remain unaffected."""
    _admin_only(current_user)
    proc = db.query(OutpatientProcedure).filter(
        OutpatientProcedure.id == procedure_id,
        OutpatientProcedure.hospital_id == current_user.hospital_id,
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procedure not found")
    proc.is_active = False
    db.commit()
    log_action(db, current_user, "deactivate_procedure", "outpatient",
               "OutpatientProcedure", proc.id, f"Deactivated procedure '{proc.name}'")
    return None


# ---------------------------------------------------------------------------
# Procedure bill creation
# ---------------------------------------------------------------------------

class ProcedureBillItemIn(BaseModel):
    procedure_id: Optional[int] = None
    item_name: Optional[str] = Field(None, max_length=200)
    quantity: int = Field(1, gt=0)
    unit_price: Optional[float] = Field(None, ge=0)


class ProcedureBillIn(BaseModel):
    patient_id: int
    items: List[ProcedureBillItemIn] = Field(..., min_length=1)
    discount_amount: float = Field(0.0, ge=0)
    tax_percentage: float = Field(0.0, ge=0, le=100)
    notes: Optional[str] = None
    payment_method: str = "cash"
    referred_by: Optional[str] = Field(None, max_length=100)


@router.post("/procedure-bills")
async def create_procedure_bill(
    data: ProcedureBillIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a day-care bill. Each item resolves to a catalog procedure
    (using its current price unless overridden) OR a free-form line. The
    resulting Bill row uses `bill_type='day_care'` so it shows up in the
    main Billing dashboard alongside consultation / lab / admission bills."""
    _can_bill(current_user)

    patient = db.query(Patient).filter(
        Patient.id == data.patient_id,
        Patient.hospital_id == current_user.hospital_id,
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Resolve each line and compute subtotal
    resolved = []
    subtotal = 0.0
    for it in data.items:
        if it.procedure_id:
            proc = db.query(OutpatientProcedure).filter(
                OutpatientProcedure.id == it.procedure_id,
                OutpatientProcedure.hospital_id == current_user.hospital_id,
            ).first()
            if not proc:
                raise HTTPException(status_code=404, detail=f"Procedure #{it.procedure_id} not found")
            name = it.item_name or proc.name
            code = proc.code or f"PROC-{proc.id}"
            unit_price = it.unit_price if it.unit_price is not None else float(proc.default_price or 0)
        else:
            if not (it.item_name and it.item_name.strip()):
                raise HTTPException(status_code=400, detail="Free-form line needs an item_name")
            if it.unit_price is None or it.unit_price < 0:
                raise HTTPException(status_code=400, detail="Free-form line needs a unit_price")
            name = it.item_name.strip()
            code = "ADHOC"
            unit_price = float(it.unit_price)
        line_total = round(unit_price * it.quantity, 2)
        resolved.append({
            "item_name": name, "item_code": code,
            "quantity": it.quantity, "unit_price": unit_price, "total": line_total,
        })
        subtotal += line_total
    subtotal = round(subtotal, 2)

    if subtotal <= 0:
        raise HTTPException(status_code=400, detail="Bill total is zero — add at least one priced line")

    discount = round(min(float(data.discount_amount or 0), subtotal), 2)
    tax = round((subtotal - discount) * (data.tax_percentage / 100), 2)
    total = round(subtotal + tax - discount, 2)

    # Bill number — PROC-YYYYMMDD-NNNN
    today_str = datetime.now().strftime("%Y%m%d")
    prefix = f"PROC-{today_str}-"
    last = db.query(Bill).filter(Bill.bill_number.like(f"{prefix}%")).order_by(Bill.id.desc()).first()
    seq = (int(last.bill_number.split("-")[-1]) + 1) if last else 1
    bill_number = f"{prefix}{seq:04d}"

    # Day-care services are collected at point of sale, so the bill is marked
    # paid on creation and a matching Payment row is written so the central
    # billing ledger / dashboard / reports stay consistent.
    bill = Bill(
        bill_number=bill_number,
        patient_id=patient.id,
        bill_type="day_care",
        bill_subtype="final",
        reference_id=0,
        subtotal=subtotal,
        tax_amount=tax,
        discount_amount=discount,
        total_amount=total,
        status="paid",
        bill_date=datetime.now(),
        created_by_id=current_user.id,
        hospital_id=current_user.hospital_id,
        notes=data.notes or None,
        referred_by=(data.referred_by or '').strip() or None,
    )
    db.add(bill)
    db.flush()

    for row in resolved:
        db.add(BillItem(
            bill_id=bill.id,
            item_type="day_care",
            item_name=row["item_name"],
            item_code=row["item_code"],
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            total_price=row["total"],
        ))

    # Auto-payment matching the bill total (sequence: PAY-YYYYMMDD-NNNN)
    pay_prefix = f"PAY-{today_str}-"
    last_pay = db.query(Payment).filter(Payment.payment_number.like(f"{pay_prefix}%")).order_by(Payment.id.desc()).first()
    pay_seq = (int(last_pay.payment_number.split("-")[-1]) + 1) if last_pay else 1
    db.add(Payment(
        payment_number=f"{pay_prefix}{pay_seq:04d}",
        bill_id=bill.id,
        amount_paid=total,
        payment_method_name=(data.payment_method or "cash"),
        payment_date=datetime.now(),
        received_by_id=current_user.id,
        notes=f"Auto-collected at bill creation ({bill_number})",
    ))

    db.commit()
    db.refresh(bill)

    log_action(db, current_user, "create_procedure_bill", "outpatient",
               "Bill", bill.id,
               f"Created procedure bill {bill_number} for {patient.first_name} {patient.last_name} (Rs.{total:.2f})",
               details={"patient_id": patient.id, "subtotal": subtotal,
                        "discount": discount, "tax": tax, "total": total,
                        "items": len(resolved)})

    return {
        "bill_id": bill.id,
        "bill_number": bill_number,
        "subtotal": subtotal,
        "discount_amount": discount,
        "tax_amount": tax,
        "total_amount": total,
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "items_count": len(resolved),
    }


@router.get("/procedure-bills")
async def list_procedure_bills(
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Recent procedure bills (most recent first). Joined with patient name."""
    _can_bill(current_user)
    rows = db.query(Bill).join(Patient, Bill.patient_id == Patient.id).filter(
        Bill.bill_type == "day_care",
        Patient.hospital_id == current_user.hospital_id,
    ).order_by(Bill.bill_date.desc()).limit(limit).all()
    out = []
    for b in rows:
        p = db.query(Patient).filter(Patient.id == b.patient_id).first()
        paid = sum(float(pay.amount_paid or 0) for pay in (b.payments or []))
        out.append({
            "bill_id": b.id,
            "bill_number": b.bill_number,
            "bill_date": b.bill_date.isoformat() if b.bill_date else None,
            "patient_id": p.patient_id if p else "",
            "patient_name": f"{p.first_name} {p.last_name}" if p else "Unknown",
            "patient_phone": p.primary_phone if p else "",
            "total_amount": float(b.total_amount or 0),
            "amount_paid": paid,
            "balance_due": float(b.total_amount or 0) - paid,
            "status": b.status,
        })
    return out
