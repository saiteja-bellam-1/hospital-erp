"""Canteen API — catalog CRUD and IP-linked food orders.

Module availability follows inpatient (admin toggle + license feature).
Permissions live under module_name=\"canteen\".
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from config.database import get_db
from app.models.user import User
from app.models.hospital import Hospital
from app.models.inpatient import Admission, RoomManagement
from app.models.patient import Patient
from app.models.canteen import (
    CanteenCategory, CanteenItem, CanteenOrder, CanteenOrderItem,
    CanteenSale, CanteenSaleItem,
)
from app.utils.dependencies import require_canteen_permission
from app.services.audit_service import log_action
from app.utils.pdf_service import pdf_service
from app.utils.pdf_settings import pdf_gen_kwargs
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError

router = APIRouter()

ORDER_STATUSES = ("pending", "preparing", "ready", "delivered", "cancelled")
ACTIVE_STATUSES = ("pending", "preparing", "ready", "delivered")
CANCEL_BLOCKED_STATUSES = ("delivered", "cancelled")


def _get_hospital(db: Session) -> Hospital:
    hospital = db.query(Hospital).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not configured")
    return hospital


# ── Schemas ──────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    category_id: Optional[int] = None
    price: float = Field(..., ge=0)
    is_veg: bool = True
    is_active: bool = True
    sort_order: int = 0


class ItemUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    category_id: Optional[int] = None
    price: Optional[float] = Field(None, ge=0)
    is_veg: Optional[bool] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class OrderLineIn(BaseModel):
    item_id: int
    quantity: int = Field(..., ge=1, le=99)


class OrderCreate(BaseModel):
    admission_id: int
    notes: Optional[str] = None
    serve_date: Optional[date] = None
    items: List[OrderLineIn] = Field(..., min_length=1)


class OrderStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(pending|preparing|ready|delivered)$")


class OrderCancel(BaseModel):
    reason: Optional[str] = Field(None, max_length=200)


# ── Serializers ──────────────────────────────────────────────────────────────

def _category_to_dict(c: CanteenCategory) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "sort_order": c.sort_order or 0,
        "is_active": bool(c.is_active),
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _item_to_dict(it: CanteenItem) -> dict:
    return {
        "id": it.id,
        "name": it.name,
        "description": it.description,
        "category_id": it.category_id,
        "category_name": it.category.name if it.category else None,
        "price": float(it.price or 0),
        "is_veg": bool(it.is_veg),
        "is_active": bool(it.is_active),
        "sort_order": it.sort_order or 0,
        "created_at": it.created_at.isoformat() if it.created_at else None,
        "updated_at": it.updated_at.isoformat() if it.updated_at else None,
    }


def _order_to_dict(o: CanteenOrder, include_patient: bool = False) -> dict:
    lines = [
        {
            "id": li.id,
            "item_id": li.item_id,
            "item_name": li.item_name,
            "unit_price": float(li.unit_price or 0),
            "quantity": int(li.quantity or 0),
            "line_total": float(li.line_total or 0),
        }
        for li in (o.items or [])
    ]
    total = sum(l["line_total"] for l in lines)
    out = {
        "id": o.id,
        "admission_id": o.admission_id,
        "patient_id": o.patient_id,
        "status": o.status,
        "notes": o.notes,
        "serve_date": o.serve_date.isoformat() if o.serve_date else None,
        "ordered_at": o.ordered_at.isoformat() if o.ordered_at else None,
        "ordered_by_id": o.ordered_by_id,
        "status_updated_at": o.status_updated_at.isoformat() if o.status_updated_at else None,
        "cancelled_at": o.cancelled_at.isoformat() if o.cancelled_at else None,
        "cancelled_reason": o.cancelled_reason,
        "billed": bool(o.billed),
        "bill_id": o.bill_id,
        "items": lines,
        "total": round(total, 2),
    }
    if include_patient:
        patient = getattr(o, "_patient", None)
        admission = getattr(o, "admission", None)
        room = admission.room if admission else None
        out["patient_name"] = (
            f"{patient.first_name} {patient.last_name}" if patient else None
        )
        out["admission_number"] = getattr(admission, "admission_number", None) if admission else None
        out["room_number"] = room.room_number if room else None
        out["ward"] = getattr(room, "ward", None) if room else None
    return out


# ── Categories ───────────────────────────────────────────────────────────────

@router.get("/categories")
async def list_categories(
    active_only: bool = Query(False),
    current_user: User = Depends(require_canteen_permission("view_catalog")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    q = db.query(CanteenCategory).filter(CanteenCategory.hospital_id == hospital.id)
    if active_only:
        q = q.filter(CanteenCategory.is_active == True)  # noqa: E712
    rows = q.order_by(CanteenCategory.sort_order.asc(), CanteenCategory.name.asc()).all()
    return [_category_to_dict(c) for c in rows]


@router.post("/categories", status_code=201)
async def create_category(
    data: CategoryCreate,
    current_user: User = Depends(require_canteen_permission("manage_catalog")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    name = data.name.strip()
    existing = db.query(CanteenCategory).filter(
        CanteenCategory.hospital_id == hospital.id,
        CanteenCategory.name == name,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category name already exists")
    row = CanteenCategory(
        hospital_id=hospital.id,
        name=name,
        sort_order=data.sort_order,
        is_active=data.is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "create_canteen_category", "canteen", "CanteenCategory", row.id, name)
    return _category_to_dict(row)


@router.put("/categories/{category_id}")
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    current_user: User = Depends(require_canteen_permission("manage_catalog")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    row = db.query(CanteenCategory).filter(
        CanteenCategory.id == category_id,
        CanteenCategory.hospital_id == hospital.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Category not found")
    if data.name is not None:
        name = data.name.strip()
        clash = db.query(CanteenCategory).filter(
            CanteenCategory.hospital_id == hospital.id,
            CanteenCategory.name == name,
            CanteenCategory.id != category_id,
        ).first()
        if clash:
            raise HTTPException(status_code=400, detail="Category name already exists")
        row.name = name
    if data.sort_order is not None:
        row.sort_order = data.sort_order
    if data.is_active is not None:
        row.is_active = data.is_active
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "update_canteen_category", "canteen", "CanteenCategory", row.id, row.name)
    return _category_to_dict(row)


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    current_user: User = Depends(require_canteen_permission("manage_catalog")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    row = db.query(CanteenCategory).filter(
        CanteenCategory.id == category_id,
        CanteenCategory.hospital_id == hospital.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Category not found")
    linked = db.query(CanteenItem).filter(CanteenItem.category_id == category_id).count()
    if linked:
        # Soft-disable rather than orphaning items
        row.is_active = False
        db.commit()
        return {"message": "Category deactivated (has catalog items)", "id": row.id, "is_active": False}
    db.delete(row)
    db.commit()
    log_action(db, current_user, "delete_canteen_category", "canteen", "CanteenCategory", category_id, None)
    return {"message": "Category deleted", "id": category_id}


# ── Catalog items ────────────────────────────────────────────────────────────

@router.get("/items")
async def list_items(
    active_only: bool = Query(False),
    category_id: Optional[int] = Query(None),
    current_user: User = Depends(require_canteen_permission("view_catalog")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    q = db.query(CanteenItem).options(joinedload(CanteenItem.category)).filter(
        CanteenItem.hospital_id == hospital.id,
    )
    if active_only:
        q = q.filter(CanteenItem.is_active == True)  # noqa: E712
    if category_id is not None:
        q = q.filter(CanteenItem.category_id == category_id)
    rows = q.order_by(CanteenItem.sort_order.asc(), CanteenItem.name.asc()).all()
    return [_item_to_dict(it) for it in rows]


@router.post("/items", status_code=201)
async def create_item(
    data: ItemCreate,
    current_user: User = Depends(require_canteen_permission("manage_catalog")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    name = data.name.strip()
    existing = db.query(CanteenItem).filter(
        CanteenItem.hospital_id == hospital.id,
        CanteenItem.name == name,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Item name already exists")
    if data.category_id is not None:
        cat = db.query(CanteenCategory).filter(
            CanteenCategory.id == data.category_id,
            CanteenCategory.hospital_id == hospital.id,
        ).first()
        if not cat:
            raise HTTPException(status_code=400, detail="Category not found")
    row = CanteenItem(
        hospital_id=hospital.id,
        category_id=data.category_id,
        name=name,
        description=data.description,
        price=Decimal(str(round(data.price, 2))),
        is_veg=data.is_veg,
        is_active=data.is_active,
        sort_order=data.sort_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    row = db.query(CanteenItem).options(joinedload(CanteenItem.category)).filter(
        CanteenItem.id == row.id
    ).first()
    log_action(db, current_user, "create_canteen_item", "canteen", "CanteenItem", row.id, name)
    return _item_to_dict(row)


@router.put("/items/{item_id}")
async def update_item(
    item_id: int,
    data: ItemUpdate,
    current_user: User = Depends(require_canteen_permission("manage_catalog")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    row = db.query(CanteenItem).filter(
        CanteenItem.id == item_id,
        CanteenItem.hospital_id == hospital.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    if data.name is not None:
        name = data.name.strip()
        clash = db.query(CanteenItem).filter(
            CanteenItem.hospital_id == hospital.id,
            CanteenItem.name == name,
            CanteenItem.id != item_id,
        ).first()
        if clash:
            raise HTTPException(status_code=400, detail="Item name already exists")
        row.name = name
    if data.description is not None:
        row.description = data.description
    if data.category_id is not None:
        if data.category_id == 0:
            row.category_id = None
        else:
            cat = db.query(CanteenCategory).filter(
                CanteenCategory.id == data.category_id,
                CanteenCategory.hospital_id == hospital.id,
            ).first()
            if not cat:
                raise HTTPException(status_code=400, detail="Category not found")
            row.category_id = data.category_id
    if data.price is not None:
        row.price = Decimal(str(round(data.price, 2)))
    if data.is_veg is not None:
        row.is_veg = data.is_veg
    if data.is_active is not None:
        row.is_active = data.is_active
    if data.sort_order is not None:
        row.sort_order = data.sort_order
    db.commit()
    row = db.query(CanteenItem).options(joinedload(CanteenItem.category)).filter(
        CanteenItem.id == item_id
    ).first()
    log_action(db, current_user, "update_canteen_item", "canteen", "CanteenItem", item_id, row.name)
    return _item_to_dict(row)


@router.delete("/items/{item_id}")
async def delete_item(
    item_id: int,
    current_user: User = Depends(require_canteen_permission("manage_catalog")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    row = db.query(CanteenItem).filter(
        CanteenItem.id == item_id,
        CanteenItem.hospital_id == hospital.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Item not found")
    # Soft-deactivate — preserve name on historical order lines
    row.is_active = False
    db.commit()
    log_action(db, current_user, "deactivate_canteen_item", "canteen", "CanteenItem", item_id, row.name)
    return {"message": "Item deactivated", "id": item_id, "is_active": False}


# ── Orders ───────────────────────────────────────────────────────────────────

@router.get("/active-admissions")
async def list_active_admissions_for_ordering(
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_canteen_permission("place_order")),
    db: Session = Depends(get_db),
):
    """Minimal admission list for the canteen order UI (no inpatient view_occupancy required)."""
    hospital = _get_hospital(db)
    query = (
        db.query(Admission)
        .options(
            joinedload(Admission.patient),
            joinedload(Admission.room),
        )
        .join(Admission.room)
        .filter(
            RoomManagement.hospital_id == hospital.id,
            Admission.status == "admitted",
        )
        .order_by(Admission.admission_date.desc())
    )
    rows = query.limit(200).all()
    needle = (q or "").strip().lower()
    out = []
    for a in rows:
        patient = a.patient
        room = a.room
        name = f"{patient.first_name} {patient.last_name}" if patient else ""
        room_number = room.room_number if room else ""
        if needle:
            hay = f"{name} {a.admission_number or ''} {room_number}".lower()
            if needle not in hay:
                continue
        out.append({
            "id": a.id,
            "admission_number": a.admission_number,
            "patient_id": a.patient_id,
            "patient_name": name or None,
            "room_number": room_number or None,
            "ward": getattr(room, "ward", None) if room else None,
        })
        if len(out) >= limit:
            break
    return out


@router.get("/orders")
async def list_orders(
    status_filter: Optional[str] = Query(None, alias="status"),
    admission_id: Optional[int] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    include_cancelled: bool = Query(False),
    current_user: User = Depends(require_canteen_permission("view_orders")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    q = (
        db.query(CanteenOrder)
        .options(
            joinedload(CanteenOrder.items),
            joinedload(CanteenOrder.admission).joinedload(Admission.room),
        )
        .filter(CanteenOrder.hospital_id == hospital.id)
    )
    if admission_id is not None:
        q = q.filter(CanteenOrder.admission_id == admission_id)
    if status_filter:
        q = q.filter(CanteenOrder.status == status_filter)
    elif not include_cancelled:
        q = q.filter(CanteenOrder.status != "cancelled")
    if from_date:
        q = q.filter(CanteenOrder.serve_date >= from_date)
    if to_date:
        q = q.filter(CanteenOrder.serve_date <= to_date)
    rows = q.order_by(CanteenOrder.ordered_at.desc()).limit(500).all()

    # Attach patient names in one query
    patient_ids = {o.patient_id for o in rows}
    patients = {
        p.id: p
        for p in db.query(Patient).filter(Patient.id.in_(patient_ids)).all()
    } if patient_ids else {}
    result = []
    for o in rows:
        o._patient = patients.get(o.patient_id)
        result.append(_order_to_dict(o, include_patient=True))
    return result


@router.get("/admissions/{admission_id}/orders")
async def list_admission_orders(
    admission_id: int,
    include_cancelled: bool = Query(False),
    current_user: User = Depends(require_canteen_permission("view_orders")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    admission = db.query(Admission).options(joinedload(Admission.room)).filter(
        Admission.id == admission_id,
    ).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if not admission.room or admission.room.hospital_id != hospital.id:
        raise HTTPException(status_code=404, detail="Admission not found")
    q = (
        db.query(CanteenOrder)
        .options(joinedload(CanteenOrder.items))
        .filter(CanteenOrder.admission_id == admission_id)
    )
    if not include_cancelled:
        q = q.filter(CanteenOrder.status != "cancelled")
    rows = q.order_by(CanteenOrder.ordered_at.desc()).all()
    return [_order_to_dict(o) for o in rows]


@router.post("/orders", status_code=201)
async def create_order(
    data: OrderCreate,
    current_user: User = Depends(require_canteen_permission("place_order")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    admission = db.query(Admission).options(joinedload(Admission.room)).filter(
        Admission.id == data.admission_id,
    ).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if not admission.room or admission.room.hospital_id != hospital.id:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status in ("discharged", "cancelled"):
        raise HTTPException(status_code=400, detail="Cannot order food for a closed admission")

    item_ids = [li.item_id for li in data.items]
    catalog = {
        it.id: it
        for it in db.query(CanteenItem).filter(
            CanteenItem.hospital_id == hospital.id,
            CanteenItem.id.in_(item_ids),
            CanteenItem.is_active == True,  # noqa: E712
        ).all()
    }
    missing = [iid for iid in item_ids if iid not in catalog]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Inactive or missing catalog items: {missing}",
        )

    order = CanteenOrder(
        hospital_id=hospital.id,
        admission_id=admission.id,
        patient_id=admission.patient_id,
        status="pending",
        notes=data.notes,
        serve_date=data.serve_date or date.today(),
        ordered_by_id=current_user.id,
    )
    db.add(order)
    db.flush()

    for li in data.items:
        cat = catalog[li.item_id]
        unit = Decimal(str(round(float(cat.price or 0), 2)))
        qty = int(li.quantity)
        db.add(CanteenOrderItem(
            order_id=order.id,
            item_id=cat.id,
            item_name=cat.name,
            unit_price=unit,
            quantity=qty,
            line_total=Decimal(str(round(float(unit) * qty, 2))),
        ))

    db.commit()
    order = (
        db.query(CanteenOrder)
        .options(joinedload(CanteenOrder.items))
        .filter(CanteenOrder.id == order.id)
        .first()
    )
    log_action(
        db, current_user, "create_canteen_order", "canteen", "CanteenOrder", order.id,
        f"Admission {admission.id}: {len(data.items)} line(s)",
        details={"admission_id": admission.id, "item_count": len(data.items)},
    )
    return _order_to_dict(order)


@router.patch("/orders/{order_id}/status")
async def update_order_status(
    order_id: int,
    data: OrderStatusUpdate,
    current_user: User = Depends(require_canteen_permission("manage_order_status")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    order = (
        db.query(CanteenOrder)
        .options(joinedload(CanteenOrder.items))
        .filter(CanteenOrder.id == order_id, CanteenOrder.hospital_id == hospital.id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status == "cancelled":
        raise HTTPException(status_code=400, detail="Cancelled order cannot change status")
    if order.status == "delivered" and data.status != "delivered":
        raise HTTPException(status_code=400, detail="Delivered order is locked")
    order.status = data.status
    order.status_updated_at = datetime.utcnow()
    order.status_updated_by_id = current_user.id
    db.commit()
    db.refresh(order)
    order = (
        db.query(CanteenOrder)
        .options(joinedload(CanteenOrder.items))
        .filter(CanteenOrder.id == order_id)
        .first()
    )
    log_action(
        db, current_user, "update_canteen_order_status", "canteen", "CanteenOrder", order.id,
        f"Status → {data.status}",
    )
    return _order_to_dict(order)


@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: int,
    data: OrderCancel,
    current_user: User = Depends(require_canteen_permission("place_order")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    order = (
        db.query(CanteenOrder)
        .options(joinedload(CanteenOrder.items))
        .filter(CanteenOrder.id == order_id, CanteenOrder.hospital_id == hospital.id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.billed:
        raise HTTPException(
            status_code=409,
            detail="Order already billed — cancel via bill cancel/refund",
            headers={"X-Error-Code": "canteen_order_billed"},
        )
    if order.status in CANCEL_BLOCKED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel an order in status '{order.status}'",
        )
    order.status = "cancelled"
    order.cancelled_at = datetime.utcnow()
    order.cancelled_by_id = current_user.id
    order.cancelled_reason = data.reason
    order.status_updated_at = order.cancelled_at
    order.status_updated_by_id = current_user.id
    db.commit()
    order = (
        db.query(CanteenOrder)
        .options(joinedload(CanteenOrder.items))
        .filter(CanteenOrder.id == order_id)
        .first()
    )
    log_action(
        db, current_user, "cancel_canteen_order", "canteen", "CanteenOrder", order.id,
        data.reason or "Cancelled",
    )
    return _order_to_dict(order)


# ── POS Sales ────────────────────────────────────────────────────────────────

PAYMENT_TYPES = ("cash", "upi", "card")


class SaleLineIn(BaseModel):
    item_id: int
    quantity: int = Field(..., ge=1, le=99)


class SaleCreate(BaseModel):
    payment_type: str = Field("cash", pattern="^(cash|upi|card)$")
    customer_name: Optional[str] = Field(None, max_length=150)
    customer_phone: Optional[str] = Field(None, max_length=30)
    discount_amount: float = Field(0, ge=0)
    notes: Optional[str] = None
    items: List[SaleLineIn] = Field(..., min_length=1)


class SaleVoid(BaseModel):
    reason: Optional[str] = Field(None, max_length=200)


def _next_canteen_sale_number(db: Session, hospital_id: int) -> str:
    today = date.today()
    prefix = f"CNT-{today.strftime('%y%m%d')}-"
    last = (
        db.query(CanteenSale)
        .filter(
            CanteenSale.hospital_id == hospital_id,
            CanteenSale.sale_number.like(prefix + "%"),
        )
        .order_by(CanteenSale.sale_number.desc())
        .first()
    )
    seq = 1
    if last:
        try:
            seq = int(last.sale_number.rsplit("-", 1)[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}{seq:04d}"


def _sale_to_dict(s: CanteenSale) -> dict:
    lines = [
        {
            "id": li.id,
            "item_id": li.item_id,
            "item_name": li.item_name,
            "unit_price": float(li.unit_price or 0),
            "quantity": int(li.quantity or 0),
            "line_total": float(li.line_total or 0),
        }
        for li in (s.items or [])
    ]
    return {
        "id": s.id,
        "sale_number": s.sale_number,
        "sale_date": s.sale_date.isoformat() if s.sale_date else None,
        "status": s.status,
        "payment_type": s.payment_type,
        "customer_name": s.customer_name,
        "customer_phone": s.customer_phone,
        "subtotal": float(s.subtotal or 0),
        "discount_amount": float(s.discount_amount or 0),
        "grand_total": float(s.grand_total or 0),
        "notes": s.notes,
        "void_reason": s.void_reason,
        "voided_at": s.voided_at.isoformat() if s.voided_at else None,
        "created_by_id": s.created_by_id,
        "items": lines,
    }


def _pdf_response(buf, filename: str) -> Response:
    data = buf.getvalue() if hasattr(buf, "getvalue") else buf
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


def _hospital_info_for_pdf(hospital: Hospital) -> dict:
    return {
        "name": hospital.name or "Hospital",
        "address": hospital.address or "",
        "phone": hospital.phone or "",
        "email": getattr(hospital, "email", None) or "",
    }


@router.get("/sales")
async def list_sales(
    status_filter: Optional[str] = Query(None, alias="status"),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(require_canteen_permission("view_sales")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    q = (
        db.query(CanteenSale)
        .options(joinedload(CanteenSale.items))
        .filter(CanteenSale.hospital_id == hospital.id)
    )
    if status_filter:
        q = q.filter(CanteenSale.status == status_filter)
    if from_date:
        q = q.filter(CanteenSale.sale_date >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        q = q.filter(CanteenSale.sale_date <= datetime.combine(to_date, datetime.max.time()))
    rows = q.order_by(CanteenSale.sale_date.desc()).limit(limit).all()
    return [_sale_to_dict(s) for s in rows]


@router.get("/sales/{sale_id}")
async def get_sale(
    sale_id: int,
    current_user: User = Depends(require_canteen_permission("view_sales")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    sale = (
        db.query(CanteenSale)
        .options(joinedload(CanteenSale.items))
        .filter(CanteenSale.id == sale_id, CanteenSale.hospital_id == hospital.id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    return _sale_to_dict(sale)


@router.post("/sales", status_code=201)
async def create_sale(
    data: SaleCreate,
    current_user: User = Depends(require_canteen_permission("create_sale")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    item_ids = [li.item_id for li in data.items]
    catalog = {
        it.id: it
        for it in db.query(CanteenItem).filter(
            CanteenItem.hospital_id == hospital.id,
            CanteenItem.id.in_(item_ids),
            CanteenItem.is_active == True,  # noqa: E712
        ).all()
    }
    missing = [iid for iid in item_ids if iid not in catalog]
    if missing:
        raise HTTPException(status_code=400, detail=f"Inactive or missing catalog items: {missing}")

    lines = []
    subtotal = Decimal("0.00")
    for li in data.items:
        cat = catalog[li.item_id]
        unit = Decimal(str(round(float(cat.price or 0), 2)))
        qty = int(li.quantity)
        line_total = Decimal(str(round(float(unit) * qty, 2)))
        subtotal += line_total
        lines.append((cat, unit, qty, line_total))

    discount = Decimal(str(round(float(data.discount_amount or 0), 2)))
    if discount > subtotal:
        raise HTTPException(status_code=400, detail="Discount cannot exceed subtotal")
    grand = subtotal - discount

    sale = CanteenSale(
        hospital_id=hospital.id,
        sale_number=_next_canteen_sale_number(db, hospital.id),
        status="completed",
        payment_type=data.payment_type,
        customer_name=(data.customer_name or "").strip() or None,
        customer_phone=(data.customer_phone or "").strip() or None,
        subtotal=subtotal,
        discount_amount=discount,
        grand_total=grand,
        notes=data.notes,
        created_by_id=current_user.id,
    )
    db.add(sale)
    db.flush()

    for cat, unit, qty, line_total in lines:
        db.add(CanteenSaleItem(
            sale_id=sale.id,
            item_id=cat.id,
            item_name=cat.name,
            unit_price=unit,
            quantity=qty,
            line_total=line_total,
        ))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Sale number conflict — please retry")
    sale = (
        db.query(CanteenSale)
        .options(joinedload(CanteenSale.items))
        .filter(CanteenSale.id == sale.id)
        .first()
    )
    log_action(
        db, current_user, "create_canteen_sale", "canteen", "CanteenSale", sale.id,
        sale.sale_number,
        details={"grand_total": float(grand), "payment_type": data.payment_type},
    )
    return _sale_to_dict(sale)


@router.post("/sales/{sale_id}/void")
async def void_sale(
    sale_id: int,
    data: SaleVoid,
    current_user: User = Depends(require_canteen_permission("void_sale")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    sale = (
        db.query(CanteenSale)
        .options(joinedload(CanteenSale.items))
        .filter(CanteenSale.id == sale_id, CanteenSale.hospital_id == hospital.id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    if sale.status == "voided":
        raise HTTPException(status_code=400, detail="Sale already voided")
    sale.status = "voided"
    sale.voided_at = datetime.utcnow()
    sale.voided_by_id = current_user.id
    sale.void_reason = data.reason
    db.commit()
    sale = (
        db.query(CanteenSale)
        .options(joinedload(CanteenSale.items))
        .filter(CanteenSale.id == sale_id)
        .first()
    )
    log_action(
        db, current_user, "void_canteen_sale", "canteen", "CanteenSale", sale.id,
        data.reason or "Voided",
    )
    return _sale_to_dict(sale)


@router.get("/sales/{sale_id}/receipt/pdf")
async def sale_receipt_pdf(
    sale_id: int,
    current_user: User = Depends(require_canteen_permission("view_sales")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db)
    sale = (
        db.query(CanteenSale)
        .options(joinedload(CanteenSale.items))
        .filter(CanteenSale.id == sale_id, CanteenSale.hospital_id == hospital.id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    shaped = _sale_to_dict(sale)
    hi = _hospital_info_for_pdf(hospital)
    buf = pdf_service.generate_canteen_sale_receipt_pdf(
        shaped, hi, **pdf_gen_kwargs(db, hospital.id, "canteen_sale_receipt"),
    )
    return _pdf_response(buf, f"{sale.sale_number}.pdf")
