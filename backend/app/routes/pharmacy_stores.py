"""Pharmacy multi-store and inter-store transfer routes."""
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.hospital import Hospital
from app.models.pharmacy import (
    Medicine,
    PharmacyInventory,
    PharmacyStockLedger,
    PharmacyStore,
    PharmacyTransfer,
    PharmacyTransferItem,
    PharmacyUserStore,
)
from app.models.user import User, UserRole
from app.services.audit_service import log_action
from app.services.pharmacy_store_service import (
    get_default_store,
    list_accessible_stores,
    requires_store_assignment,
    resolve_store_id,
    user_can_access_store,
)
from app.utils.auth import Modules
from app.utils.dependencies import get_current_user, require_feature_permission
from app.utils.pdf_service import pdf_service
from app.utils.pdf_settings import pdf_gen_kwargs
from config.database import get_db

router = APIRouter()


def _audit(db, user, action, resource_type, resource_id, description, details=None):
    log_action(
        db=db, user=user, action=action,
        category="pharmacy",
        resource_type=resource_type, resource_id=resource_id,
        description=description, details=details,
    )


class StoreOut(BaseModel):
    id: int
    code: str
    name: str
    store_type: str
    parent_store_id: Optional[int] = None
    parent_store_name: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    can_receive_supplier_purchase: bool
    is_active: bool
    is_default: bool

    class Config:
        from_attributes = True


class StoreIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=30)
    name: str = Field(..., min_length=1, max_length=150)
    store_type: str = Field("satellite", pattern="^(master|satellite)$")
    parent_store_id: Optional[int] = None
    location: Optional[str] = None
    description: Optional[str] = None
    can_receive_supplier_purchase: bool = False
    is_active: bool = True


class StoreSettingsOut(BaseModel):
    multi_store_enabled: bool
    require_store_assignment: bool = False
    store_locked: bool = False
    stores: List[StoreOut]


class UserStoreAssignIn(BaseModel):
    store_ids: List[int] = Field(default_factory=list)


@router.get("/stores/settings", response_model=StoreSettingsOut)
def get_store_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    hosp = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
    stores = list_accessible_stores(db, current_user, active_only=False)
    out = []
    for s in stores:
        parent_name = None
        if s.parent_store_id:
            parent = db.query(PharmacyStore).filter(PharmacyStore.id == s.parent_store_id).first()
            parent_name = parent.name if parent else None
        out.append(StoreOut(
            id=s.id, code=s.code, name=s.name, store_type=s.store_type,
            parent_store_id=s.parent_store_id, parent_store_name=parent_name,
            location=s.location, description=s.description,
            can_receive_supplier_purchase=bool(s.can_receive_supplier_purchase),
            is_active=bool(s.is_active), is_default=bool(s.is_default),
        ))
    return StoreSettingsOut(
        multi_store_enabled=bool(hosp and hosp.pharmacy_multi_store_enabled),
        require_store_assignment=requires_store_assignment(db, current_user.hospital_id),
        store_locked=len(out) == 1,
        stores=out,
    )


@router.get("/stores/my", response_model=List[StoreOut])
def list_my_stores(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stores = list_accessible_stores(db, current_user)
    out = []
    for s in stores:
        parent_name = None
        if s.parent_store_id:
            parent = db.query(PharmacyStore).filter(PharmacyStore.id == s.parent_store_id).first()
            parent_name = parent.name if parent else None
        out.append(StoreOut(
            id=s.id, code=s.code, name=s.name, store_type=s.store_type,
            parent_store_id=s.parent_store_id, parent_store_name=parent_name,
            location=s.location, description=s.description,
            can_receive_supplier_purchase=bool(s.can_receive_supplier_purchase),
            is_active=bool(s.is_active), is_default=bool(s.is_default),
        ))
    return out


@router.get("/stores", response_model=List[StoreOut])
def list_stores(
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_stores")),
):
    q = db.query(PharmacyStore).filter(PharmacyStore.hospital_id == current_user.hospital_id)
    if active_only:
        q = q.filter(PharmacyStore.is_active == True)  # noqa: E712
    stores = q.order_by(PharmacyStore.store_type.asc(), PharmacyStore.name.asc()).all()
    out = []
    for s in stores:
        parent_name = None
        if s.parent_store_id:
            parent = db.query(PharmacyStore).filter(PharmacyStore.id == s.parent_store_id).first()
            parent_name = parent.name if parent else None
        out.append(StoreOut(
            id=s.id, code=s.code, name=s.name, store_type=s.store_type,
            parent_store_id=s.parent_store_id, parent_store_name=parent_name,
            location=s.location, description=s.description,
            can_receive_supplier_purchase=bool(s.can_receive_supplier_purchase),
            is_active=bool(s.is_active), is_default=bool(s.is_default),
        ))
    return out


@router.post("/stores", response_model=StoreOut, status_code=201)
def create_store(
    data: StoreIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_stores")),
):
    dup = db.query(PharmacyStore).filter(
        PharmacyStore.hospital_id == current_user.hospital_id,
        PharmacyStore.code == data.code.strip().upper(),
    ).first()
    if dup:
        raise HTTPException(status_code=400, detail=f"Store code {data.code} already exists")

    master = get_default_store(db, current_user.hospital_id)
    parent_id = data.parent_store_id
    if data.store_type == "satellite":
        if not parent_id:
            parent_id = master.id
        parent = db.query(PharmacyStore).filter(
            PharmacyStore.id == parent_id,
            PharmacyStore.hospital_id == current_user.hospital_id,
            PharmacyStore.store_type == "master",
        ).first()
        if not parent:
            raise HTTPException(status_code=400, detail="Satellite stores must link to a master store")
    elif data.store_type == "master":
        existing_master = db.query(PharmacyStore).filter(
            PharmacyStore.hospital_id == current_user.hospital_id,
            PharmacyStore.store_type == "master",
            PharmacyStore.is_active == True,  # noqa: E712
        ).first()
        if existing_master and not existing_master.is_default:
            pass
        elif existing_master and data.can_receive_supplier_purchase:
            raise HTTPException(status_code=400, detail="Only one master store can receive supplier purchases")

    can_purchase = data.can_receive_supplier_purchase
    if data.store_type == "satellite":
        can_purchase = False

    store = PharmacyStore(
        code=data.code.strip().upper(),
        name=data.name.strip(),
        store_type=data.store_type,
        parent_store_id=parent_id if data.store_type == "satellite" else None,
        location=data.location,
        description=data.description,
        can_receive_supplier_purchase=can_purchase,
        is_active=data.is_active,
        is_default=False,
        hospital_id=current_user.hospital_id,
    )
    db.add(store)
    hosp = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
    if hosp and not hosp.pharmacy_multi_store_enabled:
        hosp.pharmacy_multi_store_enabled = True
    if hosp and data.store_type == "satellite":
        hosp.pharmacy_require_store_assignment = True
    db.commit()
    db.refresh(store)
    _audit(db, current_user, "create_store", "pharmacy_store", store.id, f"Created store {store.code}")
    return StoreOut(
        id=store.id, code=store.code, name=store.name, store_type=store.store_type,
        parent_store_id=store.parent_store_id, parent_store_name=master.name if store.parent_store_id else None,
        location=store.location, description=store.description,
        can_receive_supplier_purchase=bool(store.can_receive_supplier_purchase),
        is_active=bool(store.is_active), is_default=bool(store.is_default),
    )


@router.put("/stores/{store_id}", response_model=StoreOut)
def update_store(
    store_id: int,
    data: StoreIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_stores")),
):
    store = db.query(PharmacyStore).filter(
        PharmacyStore.id == store_id,
        PharmacyStore.hospital_id == current_user.hospital_id,
    ).first()
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    if store.is_default and data.store_type != "master":
        raise HTTPException(status_code=400, detail="Cannot change the default master store type")

    dup = db.query(PharmacyStore).filter(
        PharmacyStore.hospital_id == current_user.hospital_id,
        PharmacyStore.code == data.code.strip().upper(),
        PharmacyStore.id != store_id,
    ).first()
    if dup:
        raise HTTPException(status_code=400, detail=f"Store code {data.code} already exists")

    store.code = data.code.strip().upper()
    store.name = data.name.strip()
    store.location = data.location
    store.description = data.description
    store.is_active = data.is_active
    if data.store_type == "satellite":
        store.store_type = "satellite"
        store.can_receive_supplier_purchase = False
        parent_id = data.parent_store_id or get_default_store(db, current_user.hospital_id).id
        store.parent_store_id = parent_id
    db.commit()
    db.refresh(store)
    parent_name = None
    if store.parent_store_id:
        parent = db.query(PharmacyStore).filter(PharmacyStore.id == store.parent_store_id).first()
        parent_name = parent.name if parent else None
    return StoreOut(
        id=store.id, code=store.code, name=store.name, store_type=store.store_type,
        parent_store_id=store.parent_store_id, parent_store_name=parent_name,
        location=store.location, description=store.description,
        can_receive_supplier_purchase=bool(store.can_receive_supplier_purchase),
        is_active=bool(store.is_active), is_default=bool(store.is_default),
    )


@router.put("/users/{user_id}/stores")
def assign_user_stores(
    user_id: int,
    data: UserStoreAssignIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_stores")),
):
    target = db.query(User).filter(
        User.id == user_id,
        User.hospital_id == current_user.hospital_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    for sid in data.store_ids:
        if not db.query(PharmacyStore).filter(
            PharmacyStore.id == sid,
            PharmacyStore.hospital_id == current_user.hospital_id,
        ).first():
            raise HTTPException(status_code=400, detail=f"Invalid store_id {sid}")

    db.query(PharmacyUserStore).filter(
        PharmacyUserStore.user_id == user_id,
        PharmacyUserStore.hospital_id == current_user.hospital_id,
    ).delete()
    for sid in data.store_ids:
        db.add(PharmacyUserStore(
            user_id=user_id, store_id=sid, hospital_id=current_user.hospital_id,
        ))
    db.commit()
    _audit(db, current_user, "assign_user_stores", "user", user_id,
           f"Assigned {len(data.store_ids)} pharmacy stores to user {target.username}")
    return {"user_id": user_id, "store_ids": data.store_ids}


class PharmacyStaffOut(BaseModel):
    id: int
    username: str
    display_name: str
    role_name: Optional[str] = None
    store_ids: List[int] = Field(default_factory=list)


@router.get("/stores/staff", response_model=List[PharmacyStaffOut])
def list_pharmacy_staff(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_stores")),
):
    staff_roles = db.query(UserRole).filter(
        UserRole.name.in_([
            "pharmacist", "pharmacy_admin", "pharmacy_pos_operator",
            "satellite_pharmacy_admin", "pharmacy_transfer_clerk",
        ]),
    ).all()
    role_ids = [r.id for r in staff_roles]
    if not role_ids:
        return []
    users = db.query(User).filter(
        User.hospital_id == current_user.hospital_id,
        User.is_active == True,  # noqa: E712
        User.role_id.in_(role_ids),
    ).order_by(User.username.asc()).all()
    role_map = {r.id: r.name for r in staff_roles}
    out = []
    for u in users:
        assigned = db.query(PharmacyUserStore.store_id).filter(
            PharmacyUserStore.user_id == u.id,
            PharmacyUserStore.hospital_id == current_user.hospital_id,
        ).all()
        display = f"{u.first_name or ''} {u.last_name or ''}".strip() or u.username
        out.append(PharmacyStaffOut(
            id=u.id, username=u.username, display_name=display,
            role_name=role_map.get(u.role_id),
            store_ids=[row[0] for row in assigned],
        ))
    return out


@router.get("/users/{user_id}/stores")
def get_user_stores(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_stores")),
):
    target = db.query(User).filter(
        User.id == user_id,
        User.hospital_id == current_user.hospital_id,
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    rows = db.query(PharmacyUserStore.store_id).filter(
        PharmacyUserStore.user_id == user_id,
        PharmacyUserStore.hospital_id == current_user.hospital_id,
    ).all()
    return {"user_id": user_id, "store_ids": [r[0] for r in rows]}


# ---------------------------------------------------------------------------
# Inter-store transfers
# ---------------------------------------------------------------------------

class TransferItemIn(BaseModel):
    source_batch_id: int
    quantity: float = Field(..., gt=0)


class TransferIn(BaseModel):
    entry_date: date
    from_store_id: int
    to_store_id: int
    notes: Optional[str] = None
    items: List[TransferItemIn] = Field(default_factory=list)


class TransferItemOut(BaseModel):
    id: int
    medicine_id: int
    medicine_name: Optional[str] = None
    source_batch_id: int
    batch_number: str
    expiry_date: date
    quantity: float
    target_inventory_id: Optional[int] = None


class TransferOut(BaseModel):
    id: int
    transfer_number: str
    entry_date: date
    from_store_id: int
    from_store_name: Optional[str] = None
    to_store_id: int
    to_store_name: Optional[str] = None
    status: str
    notes: Optional[str] = None
    item_count: int
    total_qty: float
    items: List[TransferItemOut] = Field(default_factory=list)
    created_at: datetime
    confirmed_at: Optional[datetime] = None


def _next_transfer_number(db: Session, hospital_id: int) -> str:
    today = date.today()
    prefix = f"XFER-{today.strftime('%y%m%d')}-"
    last = db.query(PharmacyTransfer).filter(
        PharmacyTransfer.transfer_number.like(prefix + "%"),
        PharmacyTransfer.hospital_id == hospital_id,
    ).order_by(PharmacyTransfer.transfer_number.desc()).first()
    seq = 1
    if last:
        try:
            seq = int(last.transfer_number.rsplit("-", 1)[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}{seq:04d}"


def _shape_transfer(tr: PharmacyTransfer, db: Session) -> TransferOut:
    from_store = db.query(PharmacyStore).filter(PharmacyStore.id == tr.from_store_id).first()
    to_store = db.query(PharmacyStore).filter(PharmacyStore.id == tr.to_store_id).first()
    items_out = []
    for it in tr.items:
        med = db.query(Medicine).filter(Medicine.id == it.medicine_id).first()
        items_out.append(TransferItemOut(
            id=it.id, medicine_id=it.medicine_id,
            medicine_name=med.name if med else None,
            source_batch_id=it.source_batch_id,
            batch_number=it.batch_number, expiry_date=it.expiry_date,
            quantity=it.quantity, target_inventory_id=it.target_inventory_id,
        ))
    return TransferOut(
        id=tr.id, transfer_number=tr.transfer_number, entry_date=tr.entry_date,
        from_store_id=tr.from_store_id, from_store_name=from_store.name if from_store else None,
        to_store_id=tr.to_store_id, to_store_name=to_store.name if to_store else None,
        status=tr.status, notes=tr.notes,
        item_count=tr.item_count or 0, total_qty=tr.total_qty or 0.0,
        items=items_out, created_at=tr.created_at, confirmed_at=tr.confirmed_at,
    )


def _validate_transfer_stores(db, user, from_store_id: int, to_store_id: int):
    if from_store_id == to_store_id:
        raise HTTPException(status_code=400, detail="Source and destination store must differ")
    for sid in (from_store_id, to_store_id):
        if not user_can_access_store(db, user, sid):
            raise HTTPException(status_code=403, detail=f"No access to store {sid}")
    from_store = db.query(PharmacyStore).filter(
        PharmacyStore.id == from_store_id,
        PharmacyStore.hospital_id == user.hospital_id,
    ).first()
    to_store = db.query(PharmacyStore).filter(
        PharmacyStore.id == to_store_id,
        PharmacyStore.hospital_id == user.hospital_id,
    ).first()
    if not from_store or not to_store:
        raise HTTPException(status_code=400, detail="Invalid store")
    if from_store.store_type != "master":
        raise HTTPException(status_code=400, detail="Transfers must originate from the master store")
    if to_store.store_type != "satellite":
        raise HTTPException(status_code=400, detail="Transfers must go to a satellite store")


@router.get("/transfers", response_model=List[TransferOut])
def list_transfers(
    store_id: Optional[int] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_transfers")),
):
    q = db.query(PharmacyTransfer).filter(
        PharmacyTransfer.hospital_id == current_user.hospital_id,
    )
    if store_id:
        q = q.filter(
            (PharmacyTransfer.from_store_id == store_id) | (PharmacyTransfer.to_store_id == store_id)
        )
    if status:
        q = q.filter(PharmacyTransfer.status == status)
    rows = q.order_by(PharmacyTransfer.id.desc()).limit(200).all()
    return [_shape_transfer(r, db) for r in rows]


@router.post("/transfers", response_model=TransferOut, status_code=201)
def create_transfer(
    data: TransferIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_transfer")),
):
    _validate_transfer_stores(db, current_user, data.from_store_id, data.to_store_id)
    tr = PharmacyTransfer(
        transfer_number=_next_transfer_number(db, current_user.hospital_id),
        entry_date=data.entry_date,
        from_store_id=data.from_store_id,
        to_store_id=data.to_store_id,
        status="draft",
        notes=data.notes,
        created_by=current_user.id,
        hospital_id=current_user.hospital_id,
    )
    db.add(tr)
    db.flush()
    total_qty = 0.0
    for line in data.items:
        batch = db.query(PharmacyInventory).filter(
            PharmacyInventory.id == line.source_batch_id,
            PharmacyInventory.hospital_id == current_user.hospital_id,
            PharmacyInventory.store_id == data.from_store_id,
            PharmacyInventory.is_active == True,  # noqa: E712
        ).first()
        if not batch:
            raise HTTPException(status_code=400, detail=f"Invalid batch {line.source_batch_id} for source store")
        if (batch.quantity_in_stock or 0) < line.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock in batch {batch.batch_number}")
        db.add(PharmacyTransferItem(
            transfer_id=tr.id,
            medicine_id=batch.medicine_id,
            source_batch_id=batch.id,
            batch_number=batch.batch_number,
            expiry_date=batch.expiry_date,
            quantity=line.quantity,
        ))
        total_qty += line.quantity
    tr.item_count = len(data.items)
    tr.total_qty = total_qty
    db.commit()
    db.refresh(tr)
    _audit(db, current_user, "create_transfer", "pharmacy_transfer", tr.id, f"Draft transfer {tr.transfer_number}")
    return _shape_transfer(tr, db)


@router.put("/transfers/{tid}", response_model=TransferOut)
def edit_transfer(
    tid: int,
    data: TransferIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "edit_transfer")),
):
    tr = db.query(PharmacyTransfer).filter(
        PharmacyTransfer.id == tid,
        PharmacyTransfer.hospital_id == current_user.hospital_id,
    ).first()
    if not tr:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if tr.status != "draft":
        raise HTTPException(status_code=400, detail=f"Cannot edit a {tr.status} transfer")

    _validate_transfer_stores(db, current_user, data.from_store_id, data.to_store_id)
    tr.entry_date = data.entry_date
    tr.from_store_id = data.from_store_id
    tr.to_store_id = data.to_store_id
    tr.notes = data.notes
    for old in list(tr.items):
        db.delete(old)
    db.flush()
    total_qty = 0.0
    for line in data.items:
        batch = db.query(PharmacyInventory).filter(
            PharmacyInventory.id == line.source_batch_id,
            PharmacyInventory.hospital_id == current_user.hospital_id,
            PharmacyInventory.store_id == data.from_store_id,
            PharmacyInventory.is_active == True,  # noqa: E712
        ).first()
        if not batch:
            raise HTTPException(status_code=400, detail=f"Invalid batch {line.source_batch_id}")
        if (batch.quantity_in_stock or 0) < line.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock in batch {batch.batch_number}")
        db.add(PharmacyTransferItem(
            transfer_id=tr.id,
            medicine_id=batch.medicine_id,
            source_batch_id=batch.id,
            batch_number=batch.batch_number,
            expiry_date=batch.expiry_date,
            quantity=line.quantity,
        ))
        total_qty += line.quantity
    tr.item_count = len(data.items)
    tr.total_qty = total_qty
    db.commit()
    db.refresh(tr)
    return _shape_transfer(tr, db)


@router.post("/transfers/{tid}/confirm", response_model=TransferOut)
def confirm_transfer(
    tid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "confirm_transfer")),
):
    tr = db.query(PharmacyTransfer).filter(
        PharmacyTransfer.id == tid,
        PharmacyTransfer.hospital_id == current_user.hospital_id,
    ).first()
    if not tr:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if tr.status != "draft":
        raise HTTPException(status_code=400, detail=f"Transfer already {tr.status}")
    if not tr.items:
        raise HTTPException(status_code=400, detail="Cannot confirm an empty transfer")

    for item in tr.items:
        src = db.query(PharmacyInventory).filter(
            PharmacyInventory.id == item.source_batch_id,
            PharmacyInventory.store_id == tr.from_store_id,
        ).with_for_update().first()
        if not src:
            raise HTTPException(status_code=400, detail=f"Source batch {item.source_batch_id} not found")
        if (src.quantity_in_stock or 0) < item.quantity:
            raise HTTPException(status_code=400, detail=f"Insufficient stock in batch {src.batch_number}")

        src.quantity_in_stock = (src.quantity_in_stock or 0) - item.quantity
        db.add(PharmacyStockLedger(
            medicine_id=item.medicine_id, batch_id=src.id,
            txn_type="transfer_out", qty_delta=-item.quantity,
            reference_type="transfer", reference_id=tr.id,
            performed_by=current_user.id, store_id=tr.from_store_id,
            hospital_id=current_user.hospital_id,
            notes=f"Transfer {tr.transfer_number} to store {tr.to_store_id}",
        ))

        dest = db.query(PharmacyInventory).filter(
            PharmacyInventory.medicine_id == item.medicine_id,
            PharmacyInventory.batch_number == item.batch_number,
            PharmacyInventory.expiry_date == item.expiry_date,
            PharmacyInventory.store_id == tr.to_store_id,
            PharmacyInventory.hospital_id == current_user.hospital_id,
            PharmacyInventory.is_active == True,  # noqa: E712
        ).first()
        if dest:
            dest.quantity_in_stock = (dest.quantity_in_stock or 0) + item.quantity
            dest.mrp = src.mrp or dest.mrp
            dest.purchase_rate = src.purchase_rate or dest.purchase_rate
            dest.cost_price = src.cost_price or dest.cost_price
            dest.hsn_id = src.hsn_id or dest.hsn_id
            dest.supplier_id = src.supplier_id or dest.supplier_id
        else:
            dest = PharmacyInventory(
                medicine_id=item.medicine_id,
                batch_number=item.batch_number,
                expiry_date=item.expiry_date,
                quantity_in_stock=item.quantity,
                cost_price=src.cost_price,
                selling_price=src.selling_price,
                mrp=src.mrp,
                purchase_rate=src.purchase_rate,
                free_quantity=0,
                discount_pct=src.discount_pct,
                hsn_id=src.hsn_id,
                supplier_id=src.supplier_id,
                purchase_id=src.purchase_id,
                purchase_date=src.purchase_date,
                store_id=tr.to_store_id,
                is_active=True,
                hospital_id=current_user.hospital_id,
            )
            db.add(dest)
            db.flush()
        item.target_inventory_id = dest.id
        db.add(PharmacyStockLedger(
            medicine_id=item.medicine_id, batch_id=dest.id,
            txn_type="transfer_in", qty_delta=item.quantity,
            reference_type="transfer", reference_id=tr.id,
            performed_by=current_user.id, store_id=tr.to_store_id,
            hospital_id=current_user.hospital_id,
            notes=f"Transfer {tr.transfer_number} from store {tr.from_store_id}",
        ))

    tr.status = "confirmed"
    tr.confirmed_by = current_user.id
    tr.confirmed_at = datetime.now()
    db.commit()
    db.refresh(tr)
    _audit(db, current_user, "confirm_transfer", "pharmacy_transfer", tr.id,
           f"Confirmed transfer {tr.transfer_number}")
    return _shape_transfer(tr, db)


class RevokeTransferIn(BaseModel):
    reason: str = Field(..., min_length=2, max_length=500)


class RevokeTransferItemResult(BaseModel):
    medicine_id: int
    medicine_name: Optional[str] = None
    batch_number: str
    transferred_qty: float
    sold_qty: float
    reversed_qty: float


class RevokeTransferResult(BaseModel):
    id: int
    transfer_number: str
    status: str
    fully_reversed: bool
    items: List[RevokeTransferItemResult]


@router.post("/transfers/{tid}/revoke", response_model=RevokeTransferResult)
def revoke_transfer(
    tid: int,
    data: RevokeTransferIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "revoke_transfer")),
):
    tr = db.query(PharmacyTransfer).filter(
        PharmacyTransfer.id == tid,
        PharmacyTransfer.hospital_id == current_user.hospital_id,
    ).first()
    if not tr:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if tr.status != "confirmed":
        raise HTTPException(status_code=400, detail=f"Cannot revoke a {tr.status} transfer")
    if not tr.items:
        raise HTTPException(status_code=400, detail="Transfer has no items")

    results: List[RevokeTransferItemResult] = []
    any_sold = False
    any_reversed = False

    for item in tr.items:
        transferred = float(item.quantity or 0)
        dest_batch_id = item.target_inventory_id
        sold = 0.0
        if dest_batch_id:
            sold_total = db.query(sa_func.coalesce(sa_func.sum(PharmacyStockLedger.qty_delta), 0)).filter(
                PharmacyStockLedger.batch_id == dest_batch_id,
                PharmacyStockLedger.txn_type.in_(("sale", "rx_dispense")),
            ).scalar() or 0
            sold = abs(float(sold_total))
        reversible = max(0.0, transferred - sold)
        med = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
        if sold > 0:
            any_sold = True

        if reversible > 0 and dest_batch_id:
            dest = db.query(PharmacyInventory).filter(
                PharmacyInventory.id == dest_batch_id,
            ).with_for_update().first()
            if dest:
                take = min(reversible, float(dest.quantity_in_stock or 0))
                dest.quantity_in_stock = float(dest.quantity_in_stock or 0) - take
                if (dest.quantity_in_stock or 0) <= 0:
                    dest.quantity_in_stock = 0
                    dest.is_active = False
                db.add(PharmacyStockLedger(
                    medicine_id=item.medicine_id, batch_id=dest.id,
                    txn_type="transfer_revoke_out", qty_delta=-take,
                    reference_type="transfer", reference_id=tr.id,
                    performed_by=current_user.id, store_id=tr.to_store_id,
                    hospital_id=current_user.hospital_id,
                    notes=f"Revoke transfer {tr.transfer_number}: {data.reason}",
                ))

                src = db.query(PharmacyInventory).filter(
                    PharmacyInventory.id == item.source_batch_id,
                ).with_for_update().first()
                if src:
                    src.quantity_in_stock = (src.quantity_in_stock or 0) + take
                    src.is_active = True
                    db.add(PharmacyStockLedger(
                        medicine_id=item.medicine_id, batch_id=src.id,
                        txn_type="transfer_revoke_in", qty_delta=take,
                        reference_type="transfer", reference_id=tr.id,
                        performed_by=current_user.id, store_id=tr.from_store_id,
                        hospital_id=current_user.hospital_id,
                        notes=f"Revoke transfer {tr.transfer_number}: {data.reason}",
                    ))
                if take > 0:
                    any_reversed = True
                reversible = take

        results.append(RevokeTransferItemResult(
            medicine_id=item.medicine_id,
            medicine_name=med.name if med else None,
            batch_number=item.batch_number,
            transferred_qty=transferred,
            sold_qty=sold,
            reversed_qty=reversible,
        ))

    if not any_reversed:
        raise HTTPException(
            status_code=400,
            detail="Nothing to revoke — all transferred stock has already been sold or dispensed.",
        )

    tr.status = "revoked" if not any_sold else "revoked_partial"
    tr.revoked_by = current_user.id
    tr.revoked_at = datetime.now()
    tr.revoke_reason = data.reason
    db.commit()
    db.refresh(tr)
    _audit(db, current_user, "revoke_transfer", "pharmacy_transfer", tr.id,
           f"Revoked transfer {tr.transfer_number}")
    return RevokeTransferResult(
        id=tr.id, transfer_number=tr.transfer_number, status=tr.status,
        fully_reversed=not any_sold, items=results,
    )


def _hospital_info_for_pdf(db: Session, hospital_id: int) -> dict:
    h = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not h:
        return {"name": "Hospital", "address": "", "phone": "", "logo_url": None}
    return {
        "name": h.name, "address": h.address or "", "phone": h.phone or "",
        "logo_url": h.logo_url,
    }


@router.get("/transfers/{tid}/pdf")
def transfer_pdf(
    tid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_transfers")),
):
    tr = db.query(PharmacyTransfer).filter(
        PharmacyTransfer.id == tid,
        PharmacyTransfer.hospital_id == current_user.hospital_id,
    ).first()
    if not tr:
        raise HTTPException(status_code=404, detail="Transfer not found")
    shaped = _shape_transfer(tr, db).model_dump()
    shaped["notes"] = tr.notes
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    buf = pdf_service.generate_pharmacy_transfer_pdf(
        shaped, hi, **pdf_gen_kwargs(db, current_user.hospital_id, 'pharmacy_report'),
    )
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{tr.transfer_number}.pdf"'},
    )
