"""Pharmacy sales returns, purchase returns, challans, debit notes, supplier payments.

Mounted under /api/pharmacy via pharmacy.router.include_router.
"""
from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config.database import get_db
from app.models.hospital import Hospital
from app.models.pharmacy import (
    Medicine,
    PharmacyDebitNote,
    PharmacyDebitNoteAllocation,
    PharmacyInventory,
    PharmacyPurchase,
    PharmacyPurchaseItem,
    PharmacyPurchaseReturn,
    PharmacyPurchaseReturnItem,
    PharmacyReturnChallan,
    PharmacySale,
    PharmacySaleItem,
    PharmacySaleReturn,
    PharmacySaleReturnItem,
    PharmacySupplier,
    PharmacySupplierCreditNote,
    PharmacySupplierPayment,
    PharmacySupplierPaymentAllocation,
)
from app.models.user import User
from app.services.audit_service import log_action
from app.services.pharmacy_returns import (
    apply_return_challan_stock,
    apply_sale_return_stock,
    remaining_challan_qty,
)
from app.services.pharmacy_store_service import resolve_store_id
from app.utils.auth import Modules
from app.utils.dependencies import require_feature_permission
from app.utils.pdf_service import pdf_service
from app.utils.pharmacy_pricing import compute_line_tax, round_money

router = APIRouter()


# ---------------------------------------------------------------------------
# Numbering helpers
# ---------------------------------------------------------------------------

def _next_doc_number(db: Session, model, attr: str, hospital_id: int, prefix: str) -> str:
    last = (
        db.query(model)
        .filter(
            getattr(model, "hospital_id") == hospital_id,
            getattr(model, attr).like(prefix + "%"),
        )
        .order_by(getattr(model, attr).desc())
        .first()
    )
    seq = 1
    if last:
        try:
            seq = int(getattr(last, attr).rsplit("-", 1)[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}{seq:04d}"


def _flush_with_number_retry(db: Session, target, *, regen, set_attr: str, retries: int = 3):
    last_err = None
    for _ in range(retries):
        try:
            db.flush()
            return
        except IntegrityError as e:
            last_err = e
            db.rollback()
            setattr(target, set_attr, regen())
            db.add(target)
    raise last_err


def _hospital_info(db: Session, hospital_id: int) -> dict:
    h = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    return {
        "name": h.name if h else "PHARMACY",
        "address": getattr(h, "address", "") if h else "",
        "phone": getattr(h, "phone", "") if h else "",
        "email": getattr(h, "email", "") if h else "",
        "logo_url": getattr(h, "logo_url", "") if h else "",
    }


def _pdf_response(buf: BytesIO, filename: str) -> StreamingResponse:
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


def _now() -> datetime:
    return datetime.now()


# ---------------------------------------------------------------------------
# Shared allocation / aging helpers
# ---------------------------------------------------------------------------

def _purchase_allocated_total(db: Session, purchase_id: int) -> float:
    pay = (
        db.query(sa_func.coalesce(sa_func.sum(PharmacySupplierPaymentAllocation.amount), 0))
        .join(
            PharmacySupplierPayment,
            PharmacySupplierPayment.id == PharmacySupplierPaymentAllocation.payment_id,
        )
        .filter(
            PharmacySupplierPaymentAllocation.purchase_id == purchase_id,
            PharmacySupplierPayment.status == "recorded",
        )
        .scalar()
        or 0
    )
    dn = (
        db.query(sa_func.coalesce(sa_func.sum(PharmacyDebitNoteAllocation.amount), 0))
        .join(
            PharmacyDebitNote,
            PharmacyDebitNote.id == PharmacyDebitNoteAllocation.debit_note_id,
        )
        .filter(
            PharmacyDebitNoteAllocation.purchase_id == purchase_id,
            PharmacyDebitNote.status == "issued",
        )
        .scalar()
        or 0
    )
    return float(pay) + float(dn)


def _purchase_outstanding(db: Session, purchase: PharmacyPurchase) -> float:
    if purchase.status != "confirmed" or (purchase.payment_type or "") != "credit":
        return 0.0
    return max(0.0, round_money(float(purchase.grand_total or 0) - _purchase_allocated_total(db, purchase.id)))


def _validate_allocations(
    db: Session,
    *,
    supplier_id: int,
    hospital_id: int,
    allocs: list,
    total_cap: float,
    exclude_payment_id: Optional[int] = None,
    exclude_debit_note_id: Optional[int] = None,
) -> list[tuple[PharmacyPurchase, float]]:
    if not allocs:
        return []
    sum_amt = round_money(sum(float(a.amount) for a in allocs))
    if sum_amt - total_cap > 0.009:
        raise HTTPException(
            status_code=400,
            detail=f"Allocation total ₹{sum_amt} exceeds document amount ₹{total_cap}",
        )
    resolved = []
    for a in allocs:
        amt = round_money(float(a.amount))
        if amt <= 0:
            raise HTTPException(status_code=400, detail="Allocation amount must be positive")
        p = db.query(PharmacyPurchase).filter(
            PharmacyPurchase.id == a.purchase_id,
            PharmacyPurchase.hospital_id == hospital_id,
            PharmacyPurchase.supplier_id == supplier_id,
        ).first()
        if not p:
            raise HTTPException(status_code=400, detail=f"Purchase {a.purchase_id} not found for supplier")
        if p.status != "confirmed" or (p.payment_type or "") != "credit":
            raise HTTPException(status_code=400, detail=f"Purchase {p.purchase_number} is not an open credit bill")
        # Outstanding excluding this document's existing allocations
        allocated = _purchase_allocated_total(db, p.id)
        if exclude_payment_id:
            already = (
                db.query(sa_func.coalesce(sa_func.sum(PharmacySupplierPaymentAllocation.amount), 0))
                .filter(
                    PharmacySupplierPaymentAllocation.payment_id == exclude_payment_id,
                    PharmacySupplierPaymentAllocation.purchase_id == p.id,
                )
                .scalar()
                or 0
            )
            allocated -= float(already)
        if exclude_debit_note_id:
            already = (
                db.query(sa_func.coalesce(sa_func.sum(PharmacyDebitNoteAllocation.amount), 0))
                .filter(
                    PharmacyDebitNoteAllocation.debit_note_id == exclude_debit_note_id,
                    PharmacyDebitNoteAllocation.purchase_id == p.id,
                )
                .scalar()
                or 0
            )
            allocated -= float(already)
        outstanding = max(0.0, round_money(float(p.grand_total or 0) - allocated))
        if amt - outstanding > 0.009:
            raise HTTPException(
                status_code=400,
                detail=f"Allocation ₹{amt} exceeds outstanding ₹{outstanding} on {p.purchase_number}",
            )
        resolved.append((p, amt))
    return resolved


# ===========================================================================
# Sales returns
# ===========================================================================

class SaleReturnItemIn(BaseModel):
    sale_item_id: Optional[int] = None
    medicine_id: int
    batch_id: int
    quantity: float = Field(..., gt=0)
    rate: float = 0.0
    discount_pct: float = 0.0
    sgst_pct: float = 0.0
    cgst_pct: float = 0.0
    igst_pct: float = 0.0
    restock: bool = True


class SaleReturnIn(BaseModel):
    return_date: Optional[date] = None
    sale_id: Optional[int] = None
    patient_phone: Optional[str] = None
    patient_ip_id: Optional[str] = None
    patient_name: Optional[str] = None
    patient_address: Optional[str] = None
    doctor_name: Optional[str] = None
    store_id: Optional[int] = None
    reason: Optional[str] = None
    tax_mode: str = "inclusive"
    items: List[SaleReturnItemIn]


class SaleReturnConfirmIn(BaseModel):
    settlement_method: str = "cash"  # cash | upi | card | adjust | none
    settlement_amount: Optional[float] = None
    settlement_reference: Optional[str] = None


class SaleReturnCancelIn(BaseModel):
    reason: Optional[str] = None


class SaleReturnItemOut(BaseModel):
    id: int
    sale_item_id: Optional[int]
    medicine_id: int
    medicine_name: Optional[str] = None
    batch_id: int
    batch_number: Optional[str] = None
    quantity: float
    rate: float
    discount_pct: float
    tax_pct: float
    sgst_pct: float
    cgst_pct: float
    igst_pct: float
    line_total: float
    restock: bool


class SaleReturnOut(BaseModel):
    id: int
    return_number: str
    return_date: date
    sale_id: Optional[int]
    sale_number: Optional[str] = None
    patient_name: Optional[str]
    patient_phone: Optional[str]
    patient_ip_id: Optional[str]
    patient_address: Optional[str]
    doctor_name: Optional[str]
    store_id: Optional[int]
    status: str
    reason: Optional[str]
    subtotal: float
    discount_total: float
    tax_total: float
    grand_total: float
    tax_mode: str
    settlement_method: Optional[str]
    settlement_amount: float
    settlement_reference: Optional[str]
    settled_at: Optional[datetime]
    confirmed_at: Optional[datetime]
    items: List[SaleReturnItemOut] = []


def _compute_sale_return_line(it: SaleReturnItemIn, tax_mode: str):
    tax_pct = float(it.sgst_pct or 0) + float(it.cgst_pct or 0) + float(it.igst_pct or 0)
    base = float(it.quantity) * float(it.rate or 0)
    gross = base * (1 - float(it.discount_pct or 0) / 100.0)
    _taxable, tax_amt, line_total = compute_line_tax(gross, tax_pct, tax_mode=tax_mode)
    return tax_pct, round_money(tax_amt), round_money(line_total)


def _sale_return_out(db: Session, r: PharmacySaleReturn) -> SaleReturnOut:
    items_out = []
    for it in r.items:
        med = db.query(Medicine).filter(Medicine.id == it.medicine_id).first()
        batch = db.query(PharmacyInventory).filter(PharmacyInventory.id == it.batch_id).first()
        items_out.append(SaleReturnItemOut(
            id=it.id,
            sale_item_id=it.sale_item_id,
            medicine_id=it.medicine_id,
            medicine_name=med.name if med else None,
            batch_id=it.batch_id,
            batch_number=batch.batch_number if batch else None,
            quantity=it.quantity,
            rate=it.rate or 0,
            discount_pct=it.discount_pct or 0,
            tax_pct=it.tax_pct or 0,
            sgst_pct=it.sgst_pct or 0,
            cgst_pct=it.cgst_pct or 0,
            igst_pct=it.igst_pct or 0,
            line_total=it.line_total or 0,
            restock=bool(it.restock),
        ))
    sale_number = None
    if r.sale_id:
        sale = db.query(PharmacySale).filter(PharmacySale.id == r.sale_id).first()
        sale_number = sale.sale_number if sale else None
    return SaleReturnOut(
        id=r.id,
        return_number=r.return_number,
        return_date=r.return_date,
        sale_id=r.sale_id,
        sale_number=sale_number,
        patient_name=r.patient_name,
        patient_phone=r.patient_phone,
        patient_ip_id=r.patient_ip_id,
        patient_address=r.patient_address,
        doctor_name=r.doctor_name,
        store_id=r.store_id,
        status=r.status,
        reason=r.reason,
        subtotal=r.subtotal or 0,
        discount_total=r.discount_total or 0,
        tax_total=r.tax_total or 0,
        grand_total=r.grand_total or 0,
        tax_mode=r.tax_mode or "inclusive",
        settlement_method=r.settlement_method,
        settlement_amount=r.settlement_amount or 0,
        settlement_reference=r.settlement_reference,
        settled_at=r.settled_at,
        confirmed_at=r.confirmed_at,
        items=items_out,
    )


def _validate_sale_return_items(db: Session, data: SaleReturnIn, hospital_id: int):
    if not data.items:
        raise HTTPException(status_code=400, detail="At least one item required")
    sale = None
    if data.sale_id:
        sale = db.query(PharmacySale).filter(
            PharmacySale.id == data.sale_id,
            PharmacySale.hospital_id == hospital_id,
        ).first()
        if not sale:
            raise HTTPException(status_code=400, detail="Sale not found")
        if sale.status != "completed":
            raise HTTPException(status_code=400, detail="Can only return against a completed sale")
    for it in data.items:
        batch = db.query(PharmacyInventory).filter(
            PharmacyInventory.id == it.batch_id,
            PharmacyInventory.hospital_id == hospital_id,
        ).first()
        if not batch:
            raise HTTPException(status_code=400, detail=f"Batch {it.batch_id} not found")
        if batch.medicine_id != it.medicine_id:
            raise HTTPException(status_code=400, detail="Batch does not match medicine")
        if it.sale_item_id and sale:
            si = db.query(PharmacySaleItem).filter(
                PharmacySaleItem.id == it.sale_item_id,
                PharmacySaleItem.sale_id == sale.id,
            ).first()
            if not si:
                raise HTTPException(status_code=400, detail=f"Sale item {it.sale_item_id} not on sale")
            if float(it.quantity) - float(si.quantity or 0) > 0.009:
                raise HTTPException(
                    status_code=400,
                    detail=f"Return qty {it.quantity} exceeds sold qty {si.quantity}",
                )
    return sale


def _apply_sale_return_header_totals(ret: PharmacySaleReturn, items: list[PharmacySaleReturnItem], tax_mode: str):
    subtotal = 0.0
    discount = 0.0
    tax = 0.0
    for it in items:
        base = float(it.quantity or 0) * float(it.rate or 0)
        disc = base * float(it.discount_pct or 0) / 100.0
        subtotal += base
        discount += disc
        tax_pct = float(it.tax_pct or 0)
        gross = base - disc
        _taxable, tax_amt, _lt = compute_line_tax(gross, tax_pct, tax_mode=tax_mode)
        tax += tax_amt
    ret.subtotal = round_money(subtotal)
    ret.discount_total = round_money(discount)
    ret.tax_total = round_money(tax)
    ret.grand_total = round_money(sum(float(i.line_total or 0) for i in items))


@router.post("/sale-returns", response_model=SaleReturnOut, status_code=201)
def create_sale_return(
    data: SaleReturnIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_sale_return")),
):
    sale = _validate_sale_return_items(db, data, current_user.hospital_id)
    store_id = resolve_store_id(db, current_user, data.store_id)
    if sale and not data.store_id:
        store_id = sale.store_id or store_id

    patient_name = data.patient_name
    patient_phone = data.patient_phone
    patient_ip_id = data.patient_ip_id
    patient_address = data.patient_address
    doctor_name = data.doctor_name
    if sale:
        patient_name = patient_name or sale.patient_name
        patient_phone = patient_phone or sale.patient_phone
        patient_ip_id = patient_ip_id or sale.patient_ip_id
        patient_address = patient_address or sale.patient_address
        doctor_name = doctor_name or sale.doctor_name

    prefix = f"SR-{date.today().strftime('%y%m')}-"
    ret = PharmacySaleReturn(
        return_number=_next_doc_number(db, PharmacySaleReturn, "return_number", current_user.hospital_id, prefix),
        return_date=data.return_date or date.today(),
        sale_id=data.sale_id,
        patient_phone=patient_phone,
        patient_ip_id=patient_ip_id,
        patient_name=patient_name,
        patient_address=patient_address,
        doctor_name=doctor_name,
        store_id=store_id,
        reason=data.reason,
        tax_mode=data.tax_mode or "inclusive",
        status="draft",
        created_by=current_user.id,
        hospital_id=current_user.hospital_id,
    )
    db.add(ret)
    _flush_with_number_retry(
        db, ret,
        regen=lambda: _next_doc_number(db, PharmacySaleReturn, "return_number", current_user.hospital_id, prefix),
        set_attr="return_number",
    )

    built = []
    for it in data.items:
        tax_pct, _, line_total = _compute_sale_return_line(it, ret.tax_mode)
        row = PharmacySaleReturnItem(
            sale_return_id=ret.id,
            sale_item_id=it.sale_item_id,
            medicine_id=it.medicine_id,
            batch_id=it.batch_id,
            quantity=float(it.quantity),
            rate=round_money(it.rate),
            discount_pct=float(it.discount_pct or 0),
            tax_pct=tax_pct,
            sgst_pct=float(it.sgst_pct or 0),
            cgst_pct=float(it.cgst_pct or 0),
            igst_pct=float(it.igst_pct or 0),
            line_total=line_total,
            restock=bool(it.restock),
        )
        db.add(row)
        built.append(row)
    db.flush()
    _apply_sale_return_header_totals(ret, built, ret.tax_mode)
    db.commit()
    db.refresh(ret)
    log_action(
        db=db, user=current_user,
        action="create_sale_return", category="pharmacy",
        resource_type="pharmacy",
        description=f"Drafted sales return {ret.return_number}",
    )
    return _sale_return_out(db, ret)


@router.get("/sale-returns", response_model=List[SaleReturnOut])
def list_sale_returns(
    status: Optional[str] = None,
    search: Optional[str] = None,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_sale_returns")),
):
    q = db.query(PharmacySaleReturn).filter(PharmacySaleReturn.hospital_id == current_user.hospital_id)
    if status:
        q = q.filter(PharmacySaleReturn.status == status)
    if store_id is not None:
        q = q.filter(PharmacySaleReturn.store_id == store_id)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (PharmacySaleReturn.return_number.ilike(like))
            | (PharmacySaleReturn.patient_name.ilike(like))
        )
    rows = q.order_by(PharmacySaleReturn.id.desc()).limit(500).all()
    return [_sale_return_out(db, r) for r in rows]


@router.get("/sale-returns/{rid}", response_model=SaleReturnOut)
def get_sale_return(
    rid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_sale_returns")),
):
    r = db.query(PharmacySaleReturn).filter(
        PharmacySaleReturn.id == rid,
        PharmacySaleReturn.hospital_id == current_user.hospital_id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Sales return not found")
    return _sale_return_out(db, r)


@router.put("/sale-returns/{rid}", response_model=SaleReturnOut)
def update_sale_return(
    rid: int,
    data: SaleReturnIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_sale_return")),
):
    r = db.query(PharmacySaleReturn).filter(
        PharmacySaleReturn.id == rid,
        PharmacySaleReturn.hospital_id == current_user.hospital_id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Sales return not found")
    if r.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft returns can be edited")
    sale = _validate_sale_return_items(db, data, current_user.hospital_id)
    r.return_date = data.return_date or r.return_date
    r.sale_id = data.sale_id
    r.reason = data.reason
    r.tax_mode = data.tax_mode or r.tax_mode
    if data.store_id is not None:
        r.store_id = resolve_store_id(db, current_user, data.store_id)
    if sale:
        r.patient_name = data.patient_name or sale.patient_name
        r.patient_phone = data.patient_phone or sale.patient_phone
        r.patient_ip_id = data.patient_ip_id or sale.patient_ip_id
        r.patient_address = data.patient_address or sale.patient_address
        r.doctor_name = data.doctor_name or sale.doctor_name
    else:
        r.patient_name = data.patient_name
        r.patient_phone = data.patient_phone
        r.patient_ip_id = data.patient_ip_id
        r.patient_address = data.patient_address
        r.doctor_name = data.doctor_name

    for old in list(r.items):
        db.delete(old)
    db.flush()
    built = []
    for it in data.items:
        tax_pct, _, line_total = _compute_sale_return_line(it, r.tax_mode)
        row = PharmacySaleReturnItem(
            sale_return_id=r.id,
            sale_item_id=it.sale_item_id,
            medicine_id=it.medicine_id,
            batch_id=it.batch_id,
            quantity=float(it.quantity),
            rate=round_money(it.rate),
            discount_pct=float(it.discount_pct or 0),
            tax_pct=tax_pct,
            sgst_pct=float(it.sgst_pct or 0),
            cgst_pct=float(it.cgst_pct or 0),
            igst_pct=float(it.igst_pct or 0),
            line_total=line_total,
            restock=bool(it.restock),
        )
        db.add(row)
        built.append(row)
    db.flush()
    _apply_sale_return_header_totals(r, built, r.tax_mode)
    db.commit()
    db.refresh(r)
    return _sale_return_out(db, r)


@router.post("/sale-returns/{rid}/confirm", response_model=SaleReturnOut)
def confirm_sale_return(
    rid: int,
    data: SaleReturnConfirmIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "confirm_sale_return")),
):
    r = db.query(PharmacySaleReturn).filter(
        PharmacySaleReturn.id == rid,
        PharmacySaleReturn.hospital_id == current_user.hospital_id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Sales return not found")
    if r.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft returns can be confirmed")
    if not r.items:
        raise HTTPException(status_code=400, detail="Return has no items")

    method = (data.settlement_method or "none").lower()
    if method not in ("cash", "upi", "card", "adjust", "none"):
        raise HTTPException(status_code=400, detail="Invalid settlement_method")
    settle_amt = data.settlement_amount
    if settle_amt is None:
        settle_amt = float(r.grand_total or 0) if method != "none" else 0.0

    apply_sale_return_stock(db, r, r.items, user_id=current_user.id)
    r.status = "confirmed"
    r.confirmed_by = current_user.id
    r.confirmed_at = _now()
    r.settlement_method = method
    r.settlement_amount = round_money(settle_amt)
    r.settlement_reference = data.settlement_reference
    r.settled_at = _now() if method != "none" else None
    db.commit()
    db.refresh(r)
    log_action(
        db=db, user=current_user,
        action="confirm_sale_return", category="pharmacy",
        resource_type="pharmacy",
        description=f"Confirmed sales return {r.return_number} (Rs {r.grand_total})",
    )
    return _sale_return_out(db, r)


@router.post("/sale-returns/{rid}/cancel", response_model=SaleReturnOut)
def cancel_sale_return(
    rid: int,
    data: SaleReturnCancelIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "cancel_sale_return")),
):
    r = db.query(PharmacySaleReturn).filter(
        PharmacySaleReturn.id == rid,
        PharmacySaleReturn.hospital_id == current_user.hospital_id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Sales return not found")
    if r.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft returns can be cancelled")
    r.status = "cancelled"
    r.cancelled_by = current_user.id
    r.cancelled_at = _now()
    r.cancel_reason = data.reason
    db.commit()
    db.refresh(r)
    return _sale_return_out(db, r)


@router.get("/sale-returns/{rid}/credit-note/pdf")
def sale_return_credit_note_pdf(
    rid: int,
    include_header: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_sale_returns")),
):
    r = db.query(PharmacySaleReturn).filter(
        PharmacySaleReturn.id == rid,
        PharmacySaleReturn.hospital_id == current_user.hospital_id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Sales return not found")
    out = _sale_return_out(db, r)
    payload = out.model_dump()
    payload["document_title"] = "CREDIT NOTE / SALES RETURN"
    payload["doc_number"] = r.return_number
    hi = _hospital_info(db, current_user.hospital_id)
    buf = pdf_service.generate_pharmacy_document_pdf(payload, hi, include_header=include_header)
    return _pdf_response(buf, f"{r.return_number}.pdf")


# ===========================================================================
# Purchase returns
# ===========================================================================

class PurchaseReturnItemIn(BaseModel):
    purchase_item_id: Optional[int] = None
    medicine_id: int
    batch_id: int
    quantity: float = Field(..., gt=0)
    purchase_rate: float = 0.0
    discount_pct: float = 0.0
    sgst_pct: float = 0.0
    cgst_pct: float = 0.0
    igst_pct: float = 0.0


class PurchaseReturnIn(BaseModel):
    return_date: Optional[date] = None
    supplier_id: int
    purchase_id: Optional[int] = None
    store_id: Optional[int] = None
    reason: Optional[str] = None
    tax_mode: str = "exclusive"
    items: List[PurchaseReturnItemIn]


class PurchaseReturnCancelIn(BaseModel):
    reason: Optional[str] = None


class SupplierCreditNoteIn(BaseModel):
    supplier_credit_note_number: str
    supplier_credit_note_date: Optional[date] = None
    supplier_credit_note_amount: Optional[float] = None
    notes: Optional[str] = None


class ChallanLineIn(BaseModel):
    purchase_return_item_id: int
    quantity: float = Field(..., gt=0)


class ChallanIn(BaseModel):
    challan_date: Optional[date] = None
    transporter: Optional[str] = None
    vehicle: Optional[str] = None
    notes: Optional[str] = None
    # If omitted, ships all remaining qty on every return line.
    items: Optional[List[ChallanLineIn]] = None


class DebitNoteIssueIn(BaseModel):
    debit_note_date: Optional[date] = None
    amount: Optional[float] = None
    notes: Optional[str] = None


class AllocationIn(BaseModel):
    purchase_id: int
    amount: float = Field(..., gt=0)


class AllocateIn(BaseModel):
    allocations: List[AllocationIn]


class PurchaseReturnItemOut(BaseModel):
    id: int
    purchase_item_id: Optional[int]
    medicine_id: int
    medicine_name: Optional[str] = None
    batch_id: int
    batch_number: Optional[str] = None
    quantity: float
    quantity_challaned: float = 0.0
    quantity_remaining: float = 0.0
    purchase_rate: float
    discount_pct: float
    sgst_pct: float
    cgst_pct: float
    igst_pct: float
    tax_amount: float
    line_total: float


class SupplierCreditNoteOut(BaseModel):
    id: int
    credit_note_number: str
    credit_note_date: Optional[date] = None
    amount: float
    notes: Optional[str] = None
    recorded_at: Optional[datetime] = None


class ChallanOut(BaseModel):
    id: int
    challan_number: str
    challan_date: date
    purchase_return_id: int
    store_id: Optional[int]
    status: str
    transporter: Optional[str]
    vehicle: Optional[str]
    notes: Optional[str]


class DebitNoteAllocationOut(BaseModel):
    id: int
    purchase_id: int
    purchase_number: Optional[str] = None
    amount: float


class DebitNoteOut(BaseModel):
    id: int
    debit_note_number: str
    debit_note_date: date
    supplier_id: int
    purchase_return_id: int
    amount: float
    status: str
    notes: Optional[str]
    allocations: List[DebitNoteAllocationOut] = []


class PurchaseReturnOut(BaseModel):
    id: int
    return_number: str
    return_date: date
    supplier_id: int
    supplier_name: Optional[str] = None
    purchase_id: Optional[int]
    purchase_number: Optional[str] = None
    store_id: Optional[int]
    status: str
    reason: Optional[str]
    subtotal: float
    total_discount: float
    total_tax: float
    grand_total: float
    tax_mode: str
    # Legacy single-CN fields (latest CN; kept for older UI)
    supplier_credit_note_number: Optional[str]
    supplier_credit_note_date: Optional[date]
    supplier_credit_note_amount: Optional[float]
    cn_total: float = 0.0
    dn_total: float = 0.0
    pending_cn_amount: float = 0.0
    has_challan: bool = False
    goods_fully_challaned: bool = False
    challan: Optional[ChallanOut] = None
    challans: List[ChallanOut] = []
    credit_notes: List[SupplierCreditNoteOut] = []
    debit_note: Optional[DebitNoteOut] = None
    debit_notes: List[DebitNoteOut] = []
    items: List[PurchaseReturnItemOut] = []


def _compute_pr_line(it: PurchaseReturnItemIn, tax_mode: str):
    tax_pct = float(it.sgst_pct or 0) + float(it.cgst_pct or 0) + float(it.igst_pct or 0)
    base = float(it.quantity) * float(it.purchase_rate or 0)
    gross = base * (1 - float(it.discount_pct or 0) / 100.0)
    _taxable, tax_amt, line_total = compute_line_tax(gross, tax_pct, tax_mode=tax_mode)
    return round_money(tax_amt), round_money(line_total)


def _challan_out(c: PharmacyReturnChallan) -> ChallanOut:
    return ChallanOut(
        id=c.id, challan_number=c.challan_number, challan_date=c.challan_date,
        purchase_return_id=c.purchase_return_id, store_id=c.store_id,
        status=c.status, transporter=c.transporter, vehicle=c.vehicle, notes=c.notes,
    )


def _ensure_legacy_credit_notes(db: Session, r: PharmacyPurchaseReturn) -> None:
    """Backfill first credit-note row from legacy columns on the return header."""
    existing = (
        db.query(PharmacySupplierCreditNote.id)
        .filter(PharmacySupplierCreditNote.purchase_return_id == r.id)
        .first()
    )
    if existing:
        return
    if not r.supplier_credit_note_number:
        return
    db.add(PharmacySupplierCreditNote(
        purchase_return_id=r.id,
        credit_note_number=r.supplier_credit_note_number,
        credit_note_date=r.supplier_credit_note_date,
        amount=float(r.supplier_credit_note_amount if r.supplier_credit_note_amount is not None else r.grand_total or 0),
        recorded_at=r.supplier_credit_note_recorded_at,
        created_by=r.created_by,
        hospital_id=r.hospital_id,
    ))
    db.flush()


def _cn_total(db: Session, r: PharmacyPurchaseReturn) -> float:
    _ensure_legacy_credit_notes(db, r)
    total = (
        db.query(sa_func.coalesce(sa_func.sum(PharmacySupplierCreditNote.amount), 0.0))
        .filter(PharmacySupplierCreditNote.purchase_return_id == r.id)
        .scalar()
    )
    return round_money(float(total or 0))


def _dn_total(db: Session, r: PharmacyPurchaseReturn) -> float:
    total = (
        db.query(sa_func.coalesce(sa_func.sum(PharmacyDebitNote.amount), 0.0))
        .filter(
            PharmacyDebitNote.purchase_return_id == r.id,
            PharmacyDebitNote.status == "issued",
        )
        .scalar()
    )
    return round_money(float(total or 0))


def _sync_purchase_return_status(db: Session, r: PharmacyPurchaseReturn) -> bool:
    """Stages: draft → confirmed → challan_created → cn_recorded → partial → completed.

    Completed only when Σ CN amounts covers the return grand_total AND at least one DN exists.
    Partial when DN exists but CN coverage is still short.
    """
    if r.status in ("draft", "cancelled"):
        return False
    challan = (
        db.query(PharmacyReturnChallan.id)
        .filter(PharmacyReturnChallan.purchase_return_id == r.id)
        .first()
    )
    cn_total = _cn_total(db, r)
    dn = (
        db.query(PharmacyDebitNote.id)
        .filter(
            PharmacyDebitNote.purchase_return_id == r.id,
            PharmacyDebitNote.status == "issued",
        )
        .first()
    )
    covered = cn_total + 1e-6 >= float(r.grand_total or 0)
    if dn and covered:
        desired = "completed"
    elif dn:
        desired = "partial"
    elif cn_total > 0:
        desired = "cn_recorded"
    elif challan:
        desired = "challan_created"
    else:
        desired = "confirmed"
    if r.status != desired:
        r.status = desired
        return True
    return False


def _debit_note_out(db: Session, dn: PharmacyDebitNote) -> DebitNoteOut:
    allocs = []
    for a in dn.allocations:
        p = db.query(PharmacyPurchase).filter(PharmacyPurchase.id == a.purchase_id).first()
        allocs.append(DebitNoteAllocationOut(
            id=a.id, purchase_id=a.purchase_id,
            purchase_number=p.purchase_number if p else None,
            amount=a.amount,
        ))
    return DebitNoteOut(
        id=dn.id, debit_note_number=dn.debit_note_number, debit_note_date=dn.debit_note_date,
        supplier_id=dn.supplier_id, purchase_return_id=dn.purchase_return_id,
        amount=dn.amount, status=dn.status, notes=dn.notes, allocations=allocs,
    )


def _credit_note_out(cn: PharmacySupplierCreditNote) -> SupplierCreditNoteOut:
    return SupplierCreditNoteOut(
        id=cn.id,
        credit_note_number=cn.credit_note_number,
        credit_note_date=cn.credit_note_date,
        amount=float(cn.amount or 0),
        notes=cn.notes,
        recorded_at=cn.recorded_at,
    )


def _purchase_return_out(db: Session, r: PharmacyPurchaseReturn) -> PurchaseReturnOut:
    items_out = []
    goods_remaining = 0.0
    for it in r.items:
        med = db.query(Medicine).filter(Medicine.id == it.medicine_id).first()
        batch = db.query(PharmacyInventory).filter(PharmacyInventory.id == it.batch_id).first()
        rem = remaining_challan_qty(db, it)
        challaned = max(0.0, float(it.quantity or 0) - rem)
        goods_remaining += rem
        items_out.append(PurchaseReturnItemOut(
            id=it.id, purchase_item_id=it.purchase_item_id,
            medicine_id=it.medicine_id, medicine_name=med.name if med else None,
            batch_id=it.batch_id, batch_number=batch.batch_number if batch else None,
            quantity=it.quantity, quantity_challaned=challaned, quantity_remaining=rem,
            purchase_rate=it.purchase_rate or 0,
            discount_pct=it.discount_pct or 0,
            sgst_pct=it.sgst_pct or 0, cgst_pct=it.cgst_pct or 0, igst_pct=it.igst_pct or 0,
            tax_amount=it.tax_amount or 0, line_total=it.line_total or 0,
        ))
    challans = (
        db.query(PharmacyReturnChallan)
        .filter(PharmacyReturnChallan.purchase_return_id == r.id)
        .order_by(PharmacyReturnChallan.id.desc())
        .all()
    )
    _ensure_legacy_credit_notes(db, r)
    credit_notes = (
        db.query(PharmacySupplierCreditNote)
        .filter(PharmacySupplierCreditNote.purchase_return_id == r.id)
        .order_by(PharmacySupplierCreditNote.id.desc())
        .all()
    )
    dns = (
        db.query(PharmacyDebitNote)
        .filter(PharmacyDebitNote.purchase_return_id == r.id, PharmacyDebitNote.status == "issued")
        .order_by(PharmacyDebitNote.id.desc())
        .all()
    )
    cn_total = round_money(sum(float(c.amount or 0) for c in credit_notes))
    dn_total = round_money(sum(float(d.amount or 0) for d in dns))
    pending = max(0.0, round_money(float(r.grand_total or 0) - cn_total))
    latest_cn = credit_notes[0] if credit_notes else None
    purchase_number = None
    if r.purchase_id:
        p = db.query(PharmacyPurchase).filter(PharmacyPurchase.id == r.purchase_id).first()
        purchase_number = p.purchase_number if p else None
    return PurchaseReturnOut(
        id=r.id, return_number=r.return_number, return_date=r.return_date,
        supplier_id=r.supplier_id,
        supplier_name=r.supplier.name if r.supplier else None,
        purchase_id=r.purchase_id, purchase_number=purchase_number,
        store_id=r.store_id, status=r.status, reason=r.reason,
        subtotal=r.subtotal or 0, total_discount=r.total_discount or 0,
        total_tax=r.total_tax or 0, grand_total=r.grand_total or 0,
        tax_mode=r.tax_mode or "exclusive",
        supplier_credit_note_number=(latest_cn.credit_note_number if latest_cn else r.supplier_credit_note_number),
        supplier_credit_note_date=(latest_cn.credit_note_date if latest_cn else r.supplier_credit_note_date),
        supplier_credit_note_amount=(float(latest_cn.amount) if latest_cn else r.supplier_credit_note_amount),
        cn_total=cn_total,
        dn_total=dn_total,
        pending_cn_amount=pending,
        has_challan=bool(challans),
        goods_fully_challaned=goods_remaining <= 1e-9 and bool(r.items),
        challan=_challan_out(challans[0]) if challans else None,
        challans=[_challan_out(c) for c in challans],
        credit_notes=[_credit_note_out(c) for c in credit_notes],
        debit_note=_debit_note_out(db, dns[0]) if dns else None,
        debit_notes=[_debit_note_out(db, d) for d in dns],
        items=items_out,
    )


def _validate_pr_items(db: Session, data: PurchaseReturnIn, hospital_id: int):
    if not data.items:
        raise HTTPException(status_code=400, detail="At least one item required")
    sup = db.query(PharmacySupplier).filter(
        PharmacySupplier.id == data.supplier_id,
        PharmacySupplier.hospital_id == hospital_id,
    ).first()
    if not sup:
        raise HTTPException(status_code=400, detail="Invalid supplier")
    purchase = None
    if data.purchase_id:
        purchase = db.query(PharmacyPurchase).filter(
            PharmacyPurchase.id == data.purchase_id,
            PharmacyPurchase.hospital_id == hospital_id,
        ).first()
        if not purchase:
            raise HTTPException(status_code=400, detail="Purchase not found")
        if purchase.supplier_id != data.supplier_id:
            raise HTTPException(status_code=400, detail="Purchase does not belong to supplier")
    for it in data.items:
        batch = db.query(PharmacyInventory).filter(
            PharmacyInventory.id == it.batch_id,
            PharmacyInventory.hospital_id == hospital_id,
        ).first()
        if not batch:
            raise HTTPException(status_code=400, detail=f"Batch {it.batch_id} not found")
        if batch.medicine_id != it.medicine_id:
            raise HTTPException(status_code=400, detail="Batch does not match medicine")
        if it.purchase_item_id and purchase:
            pi = db.query(PharmacyPurchaseItem).filter(
                PharmacyPurchaseItem.id == it.purchase_item_id,
                PharmacyPurchaseItem.purchase_id == purchase.id,
            ).first()
            if not pi:
                raise HTTPException(status_code=400, detail=f"Purchase item {it.purchase_item_id} not on purchase")
    return sup, purchase


def _apply_pr_totals(ret: PharmacyPurchaseReturn, items: list[PharmacyPurchaseReturnItem]):
    ret.subtotal = round_money(sum(
        float(i.quantity or 0) * float(i.purchase_rate or 0) for i in items
    ))
    ret.total_discount = round_money(sum(
        float(i.quantity or 0) * float(i.purchase_rate or 0) * float(i.discount_pct or 0) / 100.0
        for i in items
    ))
    ret.total_tax = round_money(sum(float(i.tax_amount or 0) for i in items))
    ret.grand_total = round_money(sum(float(i.line_total or 0) for i in items))


@router.post("/purchase-returns", response_model=PurchaseReturnOut, status_code=201)
def create_purchase_return(
    data: PurchaseReturnIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_purchase_return")),
):
    _sup, purchase = _validate_pr_items(db, data, current_user.hospital_id)
    store_id = resolve_store_id(db, current_user, data.store_id, require_purchase_store=True)
    if purchase and not data.store_id:
        store_id = purchase.store_id or store_id

    prefix = f"PR-{date.today().strftime('%y%m')}-"
    ret = PharmacyPurchaseReturn(
        return_number=_next_doc_number(db, PharmacyPurchaseReturn, "return_number", current_user.hospital_id, prefix),
        return_date=data.return_date or date.today(),
        supplier_id=data.supplier_id,
        purchase_id=data.purchase_id,
        store_id=store_id,
        reason=data.reason,
        tax_mode=data.tax_mode or "exclusive",
        status="draft",
        created_by=current_user.id,
        hospital_id=current_user.hospital_id,
    )
    db.add(ret)
    _flush_with_number_retry(
        db, ret,
        regen=lambda: _next_doc_number(db, PharmacyPurchaseReturn, "return_number", current_user.hospital_id, prefix),
        set_attr="return_number",
    )
    built = []
    for it in data.items:
        tax_amt, line_total = _compute_pr_line(it, ret.tax_mode)
        row = PharmacyPurchaseReturnItem(
            purchase_return_id=ret.id,
            purchase_item_id=it.purchase_item_id,
            medicine_id=it.medicine_id,
            batch_id=it.batch_id,
            quantity=float(it.quantity),
            purchase_rate=round_money(it.purchase_rate),
            discount_pct=float(it.discount_pct or 0),
            sgst_pct=float(it.sgst_pct or 0),
            cgst_pct=float(it.cgst_pct or 0),
            igst_pct=float(it.igst_pct or 0),
            tax_amount=tax_amt,
            line_total=line_total,
        )
        db.add(row)
        built.append(row)
    db.flush()
    _apply_pr_totals(ret, built)
    db.commit()
    db.refresh(ret)
    log_action(
        db=db, user=current_user,
        action="create_purchase_return", category="pharmacy",
        resource_type="pharmacy",
        description=f"Drafted purchase return {ret.return_number}",
    )
    return _purchase_return_out(db, ret)


@router.get("/purchase-returns", response_model=List[PurchaseReturnOut])
def list_purchase_returns(
    status: Optional[str] = None,
    supplier_id: Optional[int] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_purchase_returns")),
):
    q = db.query(PharmacyPurchaseReturn).filter(
        PharmacyPurchaseReturn.hospital_id == current_user.hospital_id
    )
    if status:
        q = q.filter(PharmacyPurchaseReturn.status == status)
    if supplier_id:
        q = q.filter(PharmacyPurchaseReturn.supplier_id == supplier_id)
    if search:
        like = f"%{search}%"
        q = q.filter(PharmacyPurchaseReturn.return_number.ilike(like))
    rows = q.order_by(PharmacyPurchaseReturn.id.desc()).limit(500).all()
    out = []
    changed = False
    for r in rows:
        if _sync_purchase_return_status(db, r):
            changed = True
        out.append(_purchase_return_out(db, r))
    if changed:
        db.commit()
    return out


@router.get("/purchase-returns/{rid}", response_model=PurchaseReturnOut)
def get_purchase_return(
    rid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_purchase_returns")),
):
    r = db.query(PharmacyPurchaseReturn).filter(
        PharmacyPurchaseReturn.id == rid,
        PharmacyPurchaseReturn.hospital_id == current_user.hospital_id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Purchase return not found")
    if _sync_purchase_return_status(db, r):
        db.commit()
        db.refresh(r)
    return _purchase_return_out(db, r)


@router.put("/purchase-returns/{rid}", response_model=PurchaseReturnOut)
def update_purchase_return(
    rid: int,
    data: PurchaseReturnIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_purchase_return")),
):
    r = db.query(PharmacyPurchaseReturn).filter(
        PharmacyPurchaseReturn.id == rid,
        PharmacyPurchaseReturn.hospital_id == current_user.hospital_id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Purchase return not found")
    if r.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft returns can be edited")
    _validate_pr_items(db, data, current_user.hospital_id)
    r.return_date = data.return_date or r.return_date
    r.supplier_id = data.supplier_id
    r.purchase_id = data.purchase_id
    r.reason = data.reason
    r.tax_mode = data.tax_mode or r.tax_mode
    if data.store_id is not None:
        r.store_id = resolve_store_id(db, current_user, data.store_id, require_purchase_store=True)
    for old in list(r.items):
        db.delete(old)
    db.flush()
    built = []
    for it in data.items:
        tax_amt, line_total = _compute_pr_line(it, r.tax_mode)
        row = PharmacyPurchaseReturnItem(
            purchase_return_id=r.id,
            purchase_item_id=it.purchase_item_id,
            medicine_id=it.medicine_id,
            batch_id=it.batch_id,
            quantity=float(it.quantity),
            purchase_rate=round_money(it.purchase_rate),
            discount_pct=float(it.discount_pct or 0),
            sgst_pct=float(it.sgst_pct or 0),
            cgst_pct=float(it.cgst_pct or 0),
            igst_pct=float(it.igst_pct or 0),
            tax_amount=tax_amt,
            line_total=line_total,
        )
        db.add(row)
        built.append(row)
    db.flush()
    _apply_pr_totals(r, built)
    db.commit()
    db.refresh(r)
    return _purchase_return_out(db, r)


@router.post("/purchase-returns/{rid}/confirm", response_model=PurchaseReturnOut)
def confirm_purchase_return(
    rid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "confirm_purchase_return")),
):
    r = db.query(PharmacyPurchaseReturn).filter(
        PharmacyPurchaseReturn.id == rid,
        PharmacyPurchaseReturn.hospital_id == current_user.hospital_id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Purchase return not found")
    if r.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft returns can be confirmed")
    if not r.items:
        raise HTTPException(status_code=400, detail="Return has no items")
    r.status = "confirmed"
    r.confirmed_by = current_user.id
    r.confirmed_at = _now()
    db.commit()
    db.refresh(r)
    log_action(
        db=db, user=current_user,
        action="confirm_purchase_return", category="pharmacy",
        resource_type="pharmacy",
        description=f"Confirmed purchase return {r.return_number}",
    )
    return _purchase_return_out(db, r)


@router.post("/purchase-returns/{rid}/cancel", response_model=PurchaseReturnOut)
def cancel_purchase_return(
    rid: int,
    data: PurchaseReturnCancelIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "confirm_purchase_return")),
):
    r = db.query(PharmacyPurchaseReturn).filter(
        PharmacyPurchaseReturn.id == rid,
        PharmacyPurchaseReturn.hospital_id == current_user.hospital_id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Purchase return not found")
    if r.status == "cancelled":
        raise HTTPException(status_code=400, detail="Already cancelled")
    existing_challan = db.query(PharmacyReturnChallan).filter(
        PharmacyReturnChallan.purchase_return_id == r.id
    ).first()
    if existing_challan or r.status in ("challan_created", "cn_recorded", "partial", "debit_note_issued", "completed"):
        raise HTTPException(status_code=400, detail="Cannot cancel after challan is created")
    r.status = "cancelled"
    r.cancelled_by = current_user.id
    r.cancelled_at = _now()
    r.cancel_reason = data.reason
    db.commit()
    db.refresh(r)
    return _purchase_return_out(db, r)


@router.post("/purchase-returns/{rid}/challan", response_model=PurchaseReturnOut)
def create_return_challan(
    rid: int,
    data: ChallanIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_return_challan")),
):
    r = db.query(PharmacyPurchaseReturn).filter(
        PharmacyPurchaseReturn.id == rid,
        PharmacyPurchaseReturn.hospital_id == current_user.hospital_id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Purchase return not found")
    if r.status in ("draft", "cancelled"):
        raise HTTPException(status_code=400, detail="Confirm the purchase return before creating a challan")
    if r.status == "completed":
        raise HTTPException(status_code=400, detail="Return is already completed")

    # Build ship lines: explicit items or all remaining qty
    item_by_id = {it.id: it for it in r.items}
    lines: list[tuple[PharmacyPurchaseReturnItem, float]] = []
    if data.items:
        for line in data.items:
            it = item_by_id.get(line.purchase_return_item_id)
            if not it:
                raise HTTPException(status_code=400, detail=f"Return item {line.purchase_return_item_id} not found")
            lines.append((it, float(line.quantity)))
    else:
        for it in r.items:
            rem = remaining_challan_qty(db, it)
            if rem > 1e-9:
                lines.append((it, rem))
    if not lines:
        raise HTTPException(status_code=400, detail="Nothing remaining to challan on this return")

    prefix = f"CH-{date.today().strftime('%y%m')}-"
    challan = PharmacyReturnChallan(
        challan_number=_next_doc_number(db, PharmacyReturnChallan, "challan_number", current_user.hospital_id, prefix),
        challan_date=data.challan_date or date.today(),
        purchase_return_id=r.id,
        store_id=r.store_id,
        status="confirmed",
        transporter=data.transporter,
        vehicle=data.vehicle,
        notes=data.notes,
        created_by=current_user.id,
        hospital_id=current_user.hospital_id,
    )
    db.add(challan)
    _flush_with_number_retry(
        db, challan,
        regen=lambda: _next_doc_number(db, PharmacyReturnChallan, "challan_number", current_user.hospital_id, prefix),
        set_attr="challan_number",
    )
    apply_return_challan_stock(db, r, challan, lines, user_id=current_user.id)
    if r.status == "confirmed":
        r.status = "challan_created"
    db.commit()
    db.refresh(r)
    _sync_purchase_return_status(db, r)
    db.commit()
    db.refresh(r)
    log_action(
        db=db, user=current_user,
        action="create_return_challan", category="pharmacy",
        resource_type="pharmacy",
        description=f"Challan {challan.challan_number} for {r.return_number}",
    )
    return _purchase_return_out(db, r)


@router.post("/purchase-returns/{rid}/supplier-credit-note", response_model=PurchaseReturnOut)
def record_supplier_credit_note(
    rid: int,
    data: SupplierCreditNoteIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "record_supplier_credit_note")),
):
    r = db.query(PharmacyPurchaseReturn).filter(
        PharmacyPurchaseReturn.id == rid,
        PharmacyPurchaseReturn.hospital_id == current_user.hospital_id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Purchase return not found")
    if r.status in ("draft", "cancelled"):
        raise HTTPException(status_code=400, detail="Purchase return must be confirmed first")
    challan = db.query(PharmacyReturnChallan).filter(
        PharmacyReturnChallan.purchase_return_id == r.id
    ).first()
    if not challan:
        raise HTTPException(status_code=400, detail="Create challan before recording supplier credit note")
    num = (data.supplier_credit_note_number or "").strip()
    if not num:
        raise HTTPException(status_code=400, detail="supplier_credit_note_number required")

    pending = max(0.0, round_money(float(r.grand_total or 0) - _cn_total(db, r)))
    amount = (
        round_money(data.supplier_credit_note_amount)
        if data.supplier_credit_note_amount is not None
        else pending
    )
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Credit note amount must be positive")
    if amount > pending + 1e-6:
        raise HTTPException(
            status_code=400,
            detail=f"Credit note amount ₹{amount} exceeds pending ₹{pending}",
        )

    cn = PharmacySupplierCreditNote(
        purchase_return_id=r.id,
        credit_note_number=num,
        credit_note_date=data.supplier_credit_note_date or date.today(),
        amount=amount,
        notes=data.notes,
        recorded_at=_now(),
        created_by=current_user.id,
        hospital_id=current_user.hospital_id,
    )
    db.add(cn)
    # Keep legacy header fields in sync with latest CN
    r.supplier_credit_note_number = num
    r.supplier_credit_note_date = cn.credit_note_date
    r.supplier_credit_note_amount = amount
    r.supplier_credit_note_recorded_at = cn.recorded_at
    db.flush()
    _sync_purchase_return_status(db, r)
    db.commit()
    db.refresh(r)
    return _purchase_return_out(db, r)


@router.post("/purchase-returns/{rid}/debit-note", response_model=PurchaseReturnOut)
def issue_debit_note(
    rid: int,
    data: DebitNoteIssueIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "issue_debit_note")),
):
    r = db.query(PharmacyPurchaseReturn).filter(
        PharmacyPurchaseReturn.id == rid,
        PharmacyPurchaseReturn.hospital_id == current_user.hospital_id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Purchase return not found")
    cn_total = _cn_total(db, r)
    if cn_total <= 0:
        raise HTTPException(status_code=400, detail="Record supplier credit note before issuing debit note")
    dn_total = _dn_total(db, r)
    uncovered = max(0.0, round_money(cn_total - dn_total))
    if uncovered <= 1e-9:
        raise HTTPException(status_code=400, detail="All recorded credit notes already have debit notes")

    amount = data.amount
    if amount is None:
        amount = uncovered
    amount = round_money(amount)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Debit note amount must be positive")
    if amount > uncovered + 1e-6:
        raise HTTPException(
            status_code=400,
            detail=f"Debit note amount ₹{amount} exceeds uncovered CN balance ₹{uncovered}",
        )

    prefix = f"DN-{date.today().strftime('%y%m')}-"
    dn = PharmacyDebitNote(
        debit_note_number=_next_doc_number(db, PharmacyDebitNote, "debit_note_number", current_user.hospital_id, prefix),
        debit_note_date=data.debit_note_date or date.today(),
        supplier_id=r.supplier_id,
        purchase_return_id=r.id,
        amount=amount,
        status="issued",
        notes=data.notes,
        created_by=current_user.id,
        hospital_id=current_user.hospital_id,
    )
    db.add(dn)
    _flush_with_number_retry(
        db, dn,
        regen=lambda: _next_doc_number(db, PharmacyDebitNote, "debit_note_number", current_user.hospital_id, prefix),
        set_attr="debit_note_number",
    )
    _sync_purchase_return_status(db, r)
    db.commit()
    db.refresh(r)
    log_action(
        db=db, user=current_user,
        action="issue_debit_note", category="pharmacy",
        resource_type="pharmacy",
        description=f"Debit note {dn.debit_note_number} for {r.return_number} ({r.status})",
    )
    return _purchase_return_out(db, r)


@router.get("/debit-notes/{dnid}", response_model=DebitNoteOut)
def get_debit_note(
    dnid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_purchase_returns")),
):
    dn = db.query(PharmacyDebitNote).filter(
        PharmacyDebitNote.id == dnid,
        PharmacyDebitNote.hospital_id == current_user.hospital_id,
    ).first()
    if not dn:
        raise HTTPException(status_code=404, detail="Debit note not found")
    return _debit_note_out(db, dn)


@router.post("/debit-notes/{dnid}/allocate", response_model=DebitNoteOut)
def allocate_debit_note(
    dnid: int,
    data: AllocateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "allocate_debit_note")),
):
    dn = db.query(PharmacyDebitNote).filter(
        PharmacyDebitNote.id == dnid,
        PharmacyDebitNote.hospital_id == current_user.hospital_id,
    ).first()
    if not dn:
        raise HTTPException(status_code=404, detail="Debit note not found")
    if dn.status != "issued":
        raise HTTPException(status_code=400, detail="Debit note is not issued")
    resolved = _validate_allocations(
        db,
        supplier_id=dn.supplier_id,
        hospital_id=current_user.hospital_id,
        allocs=data.allocations,
        total_cap=float(dn.amount or 0),
        exclude_debit_note_id=dn.id,
    )
    for old in list(dn.allocations):
        db.delete(old)
    db.flush()
    for p, amt in resolved:
        db.add(PharmacyDebitNoteAllocation(debit_note_id=dn.id, purchase_id=p.id, amount=amt))
    db.commit()
    db.refresh(dn)
    return _debit_note_out(db, dn)


@router.get("/purchase-returns/{rid}/pdf")
def purchase_return_pdf(
    rid: int,
    include_header: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_purchase_returns")),
):
    r = db.query(PharmacyPurchaseReturn).filter(
        PharmacyPurchaseReturn.id == rid,
        PharmacyPurchaseReturn.hospital_id == current_user.hospital_id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Purchase return not found")
    payload = _purchase_return_out(db, r).model_dump()
    payload["document_title"] = "PURCHASE RETURN"
    payload["doc_number"] = r.return_number
    hi = _hospital_info(db, current_user.hospital_id)
    buf = pdf_service.generate_pharmacy_document_pdf(payload, hi, include_header=include_header)
    return _pdf_response(buf, f"{r.return_number}.pdf")


@router.get("/purchase-returns/{rid}/challan/pdf")
def return_challan_pdf(
    rid: int,
    include_header: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_purchase_returns")),
):
    r = db.query(PharmacyPurchaseReturn).filter(
        PharmacyPurchaseReturn.id == rid,
        PharmacyPurchaseReturn.hospital_id == current_user.hospital_id,
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Purchase return not found")
    challan = db.query(PharmacyReturnChallan).filter(
        PharmacyReturnChallan.purchase_return_id == r.id
    ).first()
    if not challan:
        raise HTTPException(status_code=404, detail="Challan not found")
    payload = _purchase_return_out(db, r).model_dump()
    payload["document_title"] = "RETURN CHALLAN"
    payload["doc_number"] = challan.challan_number
    payload["challan_date"] = challan.challan_date.isoformat() if challan.challan_date else ""
    hi = _hospital_info(db, current_user.hospital_id)
    buf = pdf_service.generate_pharmacy_document_pdf(payload, hi, include_header=include_header)
    return _pdf_response(buf, f"{challan.challan_number}.pdf")


@router.get("/debit-notes/{dnid}/pdf")
def debit_note_pdf(
    dnid: int,
    include_header: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_purchase_returns")),
):
    dn = db.query(PharmacyDebitNote).filter(
        PharmacyDebitNote.id == dnid,
        PharmacyDebitNote.hospital_id == current_user.hospital_id,
    ).first()
    if not dn:
        raise HTTPException(status_code=404, detail="Debit note not found")
    pr = db.query(PharmacyPurchaseReturn).filter(PharmacyPurchaseReturn.id == dn.purchase_return_id).first()
    payload = _debit_note_out(db, dn).model_dump()
    if pr:
        payload["return_number"] = pr.return_number
        payload["supplier_name"] = pr.supplier.name if pr.supplier else None
        payload["supplier_credit_note_number"] = pr.supplier_credit_note_number
        payload["items"] = _purchase_return_out(db, pr).items
    payload["document_title"] = "DEBIT NOTE"
    payload["doc_number"] = dn.debit_note_number
    payload["grand_total"] = dn.amount
    hi = _hospital_info(db, current_user.hospital_id)
    buf = pdf_service.generate_pharmacy_document_pdf(payload, hi, include_header=include_header)
    return _pdf_response(buf, f"{dn.debit_note_number}.pdf")


# ===========================================================================
# Supplier payments
# ===========================================================================

class SupplierPaymentIn(BaseModel):
    supplier_id: int
    paid_on: Optional[date] = None
    amount: float = Field(..., gt=0)
    mode: str = "neft"
    reference: Optional[str] = None
    notes: Optional[str] = None
    allocations: List[AllocationIn] = []


class SupplierPaymentAllocationOut(BaseModel):
    id: int
    purchase_id: int
    purchase_number: Optional[str] = None
    amount: float


class SupplierPaymentOut(BaseModel):
    id: int
    payment_number: str
    supplier_id: int
    supplier_name: Optional[str] = None
    paid_on: date
    amount: float
    mode: str
    reference: Optional[str]
    notes: Optional[str]
    status: str
    allocations: List[SupplierPaymentAllocationOut] = []


class SupplierPayablePurchaseOut(BaseModel):
    purchase_id: int
    purchase_number: str
    entry_date: Optional[date]
    invoice_number: Optional[str]
    grand_total: float
    allocated: float
    outstanding: float


class SupplierPayableOut(BaseModel):
    supplier_id: int
    supplier_name: str
    opening_balance: float
    purchase_total: float
    payment_total: float
    debit_note_total: float
    outstanding: float
    purchases: List[SupplierPayablePurchaseOut] = []


def _payment_out(db: Session, p: PharmacySupplierPayment) -> SupplierPaymentOut:
    allocs = []
    for a in p.allocations:
        pur = db.query(PharmacyPurchase).filter(PharmacyPurchase.id == a.purchase_id).first()
        allocs.append(SupplierPaymentAllocationOut(
            id=a.id, purchase_id=a.purchase_id,
            purchase_number=pur.purchase_number if pur else None,
            amount=a.amount,
        ))
    return SupplierPaymentOut(
        id=p.id, payment_number=p.payment_number, supplier_id=p.supplier_id,
        supplier_name=p.supplier.name if p.supplier else None,
        paid_on=p.paid_on, amount=p.amount, mode=p.mode,
        reference=p.reference, notes=p.notes, status=p.status, allocations=allocs,
    )


@router.post("/supplier-payments", response_model=SupplierPaymentOut, status_code=201)
def create_supplier_payment(
    data: SupplierPaymentIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_supplier_payment")),
):
    sup = db.query(PharmacySupplier).filter(
        PharmacySupplier.id == data.supplier_id,
        PharmacySupplier.hospital_id == current_user.hospital_id,
    ).first()
    if not sup:
        raise HTTPException(status_code=400, detail="Invalid supplier")
    mode = (data.mode or "neft").lower()
    if mode not in ("cash", "upi", "neft", "cheque", "other"):
        raise HTTPException(status_code=400, detail="Invalid payment mode")
    amount = round_money(data.amount)
    resolved = _validate_allocations(
        db,
        supplier_id=data.supplier_id,
        hospital_id=current_user.hospital_id,
        allocs=data.allocations,
        total_cap=amount,
    )
    prefix = f"SP-{date.today().strftime('%y%m')}-"
    pay = PharmacySupplierPayment(
        payment_number=_next_doc_number(db, PharmacySupplierPayment, "payment_number", current_user.hospital_id, prefix),
        supplier_id=data.supplier_id,
        paid_on=data.paid_on or date.today(),
        amount=amount,
        mode=mode,
        reference=data.reference,
        notes=data.notes,
        status="recorded",
        created_by=current_user.id,
        hospital_id=current_user.hospital_id,
    )
    db.add(pay)
    _flush_with_number_retry(
        db, pay,
        regen=lambda: _next_doc_number(db, PharmacySupplierPayment, "payment_number", current_user.hospital_id, prefix),
        set_attr="payment_number",
    )
    for pur, amt in resolved:
        db.add(PharmacySupplierPaymentAllocation(payment_id=pay.id, purchase_id=pur.id, amount=amt))
    db.commit()
    db.refresh(pay)
    log_action(
        db=db, user=current_user,
        action="create_supplier_payment", category="pharmacy",
        resource_type="pharmacy",
        description=f"Payment {pay.payment_number} ₹{pay.amount} to {sup.name}",
    )
    return _payment_out(db, pay)


@router.get("/supplier-payments", response_model=List[SupplierPaymentOut])
def list_supplier_payments(
    supplier_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_supplier_payments")),
):
    q = db.query(PharmacySupplierPayment).filter(
        PharmacySupplierPayment.hospital_id == current_user.hospital_id,
        PharmacySupplierPayment.status == "recorded",
    )
    if supplier_id:
        q = q.filter(PharmacySupplierPayment.supplier_id == supplier_id)
    rows = q.order_by(PharmacySupplierPayment.id.desc()).limit(500).all()
    return [_payment_out(db, p) for p in rows]


@router.get("/supplier-payments/{pid}", response_model=SupplierPaymentOut)
def get_supplier_payment(
    pid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_supplier_payments")),
):
    p = db.query(PharmacySupplierPayment).filter(
        PharmacySupplierPayment.id == pid,
        PharmacySupplierPayment.hospital_id == current_user.hospital_id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    return _payment_out(db, p)


@router.delete("/supplier-payments/{pid}", response_model=SupplierPaymentOut)
def delete_supplier_payment(
    pid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "delete_supplier_payment")),
):
    p = db.query(PharmacySupplierPayment).filter(
        PharmacySupplierPayment.id == pid,
        PharmacySupplierPayment.hospital_id == current_user.hospital_id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    if p.status != "recorded":
        raise HTTPException(status_code=400, detail="Payment already voided")
    p.status = "voided"
    db.commit()
    db.refresh(p)
    log_action(
        db=db, user=current_user,
        action="delete_supplier_payment", category="pharmacy",
        resource_type="pharmacy",
        description=f"Voided payment {p.payment_number}",
    )
    return _payment_out(db, p)


@router.get("/suppliers/{sid}/payables", response_model=SupplierPayableOut)
def supplier_payables(
    sid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_supplier_payments")),
):
    sup = db.query(PharmacySupplier).filter(
        PharmacySupplier.id == sid,
        PharmacySupplier.hospital_id == current_user.hospital_id,
    ).first()
    if not sup:
        raise HTTPException(status_code=404, detail="Supplier not found")

    opening = float(sup.opening_balance or 0)
    if (sup.opening_balance_dr_cr or "Dr").upper() == "Cr":
        opening = -opening

    purchases = db.query(PharmacyPurchase).filter(
        PharmacyPurchase.hospital_id == current_user.hospital_id,
        PharmacyPurchase.supplier_id == sid,
        PharmacyPurchase.status == "confirmed",
        PharmacyPurchase.payment_type == "credit",
    ).order_by(PharmacyPurchase.entry_date.asc(), PharmacyPurchase.id.asc()).all()

    purch_rows = []
    purchase_total = 0.0
    for p in purchases:
        allocated = _purchase_allocated_total(db, p.id)
        outstanding = max(0.0, round_money(float(p.grand_total or 0) - allocated))
        purchase_total += float(p.grand_total or 0)
        purch_rows.append(SupplierPayablePurchaseOut(
            purchase_id=p.id,
            purchase_number=p.purchase_number,
            entry_date=p.entry_date,
            invoice_number=p.invoice_number,
            grand_total=float(p.grand_total or 0),
            allocated=round_money(allocated),
            outstanding=outstanding,
        ))

    payment_total = float(
        db.query(sa_func.coalesce(sa_func.sum(PharmacySupplierPayment.amount), 0))
        .filter(
            PharmacySupplierPayment.supplier_id == sid,
            PharmacySupplierPayment.hospital_id == current_user.hospital_id,
            PharmacySupplierPayment.status == "recorded",
        )
        .scalar()
        or 0
    )
    debit_note_total = float(
        db.query(sa_func.coalesce(sa_func.sum(PharmacyDebitNote.amount), 0))
        .filter(
            PharmacyDebitNote.supplier_id == sid,
            PharmacyDebitNote.hospital_id == current_user.hospital_id,
            PharmacyDebitNote.status == "issued",
        )
        .scalar()
        or 0
    )
    # Outstanding for payables board = opening(Dr+) + purchases - payments - DN
    outstanding = round_money(opening + purchase_total - payment_total - debit_note_total)
    return SupplierPayableOut(
        supplier_id=sup.id,
        supplier_name=sup.name,
        opening_balance=round_money(opening),
        purchase_total=round_money(purchase_total),
        payment_total=round_money(payment_total),
        debit_note_total=round_money(debit_note_total),
        outstanding=outstanding,
        purchases=purch_rows,
    )
