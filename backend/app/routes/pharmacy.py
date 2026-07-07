"""Pharmacy module routes.

Prefix: /api/pharmacy

This router is the home for the full pharmacy workflow:
catalog (companies/suppliers/salts/racks/uoms/categories/medicines/HSN),
inventory (batches + ledger + alerts), procurement, POS sales,
Rx-linked dispensing, and reports.

Section A bootstraps the router and health check.
Section B adds catalog + master data CRUD.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.hospital import Hospital
from app.utils.pdf_service import pdf_service

from config.database import get_db
from app.utils.pdf_settings import pdf_gen_kwargs
from app.models.user import User
from datetime import date, datetime, timedelta

from app.models.pharmacy import (
    MedicineCategory,
    Medicine,
    PharmacyCompany,
    PharmacySupplier,
    PharmacySalt,
    PharmacyRack,
    PharmacyUoM,
    PharmacyHSN,
    PharmacyInventory,
    PharmacyStockLedger,
    PharmacyStockAdjustment,
    PharmacyPurchase,
    PharmacyPurchaseItem,
    PharmacySale,
    PharmacySaleItem,
    PharmacyStore,
    Prescription,
    PrescriptionItem,
)
from sqlalchemy import func as sa_func
from app.utils.auth import Modules
from app.utils.dependencies import get_current_user, require_feature_permission, require_feature_permission_any
from app.utils.pharmacy_pricing import (
    medicine_sale_rate,
    is_free_text_medicine,
    resolve_pos_sale_line,
    combined_base_qty,
    format_sale_qty_display,
    tab_sale_rate,
    strip_sale_rate,
    apply_cost_pcs_from_mrp,
    apply_medicine_price_rounding,
    round_money,
    compute_line_tax,
)
from app.services.audit_service import log_action
from app.services.pharmacy_store_service import (
    resolve_store_id,
    resolve_report_store_filter,
    get_master_store_id,
    sum_store_stock,
)


router = APIRouter()

from app.routes.pharmacy_stores import router as _stores_router  # noqa: E402
router.include_router(_stores_router)


# ============================================================================
# Health
# ============================================================================

@router.get("/health")
async def pharmacy_health(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Liveness probe — confirms the pharmacy router is mounted and authed."""
    return {
        "status": "ok",
        "module": Modules.PHARMACY,
        "user": current_user.username,
    }


# ============================================================================
# Helpers
# ============================================================================

def _user_has_permission(db, user, module: str, permission_name: str) -> bool:
    """Inline check used for in-route conditional gates (e.g. the `void_sale_legacy`
    bypass on the void window). Mirrors require_feature_permission's matching
    rule against RoleModulePermission for any of the user's roles. Returns
    False for any error so callers can fall through to the "deny by default"
    branch.
    """
    try:
        from app.models.permissions import RoleModulePermission
        role_ids = [r.id for r in (getattr(user, "roles", None) or [])]
        if user.role_id and user.role_id not in role_ids:
            role_ids.append(user.role_id)
        for rid in role_ids:
            rp = db.query(RoleModulePermission).filter(
                RoleModulePermission.role_id == rid,
                RoleModulePermission.module_name == module,
            ).first()
            if rp and rp.permissions and permission_name in rp.permissions:
                return True
    except Exception:
        return False
    return False


def _audit(db, user, action, resource_type, resource_id, description, details=None):
    log_action(
        db=db, user=user, action=action,
        category="pharmacy",
        resource_type=resource_type, resource_id=resource_id,
        description=description, details=details,
    )


def _store_label(db: Session, store_id: Optional[int]) -> Optional[str]:
    if not store_id:
        return None
    s = db.query(PharmacyStore).filter(PharmacyStore.id == store_id).first()
    return f"{s.code} — {s.name}" if s else None


def _ensure_active_or_404(obj, what: str):
    if not obj:
        raise HTTPException(status_code=404, detail=f"{what} not found")


# ============================================================================
# Categories
# ============================================================================

class CategoryIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: bool = True


class CategoryOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/categories", response_model=List[CategoryOut])
def list_categories(
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_catalog")),
):
    q = db.query(MedicineCategory).filter(MedicineCategory.hospital_id == current_user.hospital_id)
    if active_only:
        q = q.filter(MedicineCategory.is_active == True)  # noqa: E712
    return q.order_by(MedicineCategory.name).all()


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    data: CategoryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_categories")),
):
    row = MedicineCategory(
        name=data.name, description=data.description, is_active=data.is_active,
        hospital_id=current_user.hospital_id,
    )
    db.add(row); db.commit(); db.refresh(row)
    _audit(db, current_user, "create_pharmacy_category", "medicine_category", row.id,
           f"Created pharmacy category '{row.name}'")
    return row


@router.put("/categories/{cid}", response_model=CategoryOut)
def update_category(
    cid: int, data: CategoryIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_categories")),
):
    row = db.query(MedicineCategory).filter(
        MedicineCategory.id == cid,
        MedicineCategory.hospital_id == current_user.hospital_id,
    ).first()
    _ensure_active_or_404(row, "Category")
    row.name = data.name
    row.description = data.description
    row.is_active = data.is_active
    db.commit(); db.refresh(row)
    _audit(db, current_user, "update_pharmacy_category", "medicine_category", row.id,
           f"Updated pharmacy category #{row.id}")
    return row


@router.delete("/categories/{cid}", status_code=204)
def delete_category(
    cid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_categories")),
):
    row = db.query(MedicineCategory).filter(
        MedicineCategory.id == cid,
        MedicineCategory.hospital_id == current_user.hospital_id,
    ).first()
    _ensure_active_or_404(row, "Category")
    row.is_active = False
    db.commit()
    _audit(db, current_user, "delete_pharmacy_category", "medicine_category", row.id,
           f"Soft-deleted pharmacy category #{row.id}")
    return None


# ============================================================================
# Generic "simple master" CRUD pattern
# ----------------------------------------------------------------------------
# Companies / Suppliers / Salts / Racks / UoMs each have near-identical CRUD.
# We define a small builder per master to avoid hand-repeating ~25 lines × 5.
# ============================================================================

class CompanyIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    contact: Optional[str] = None
    is_active: bool = True

class CompanyOut(CompanyIn):
    id: int
    class Config: from_attributes = True


class SupplierIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)

    # Accounting
    station: Optional[str] = None
    account_group: str = "Sundry Creditors"
    balancing_method: str = "bill_by_bill"
    opening_balance: float = 0.0
    opening_balance_dr_cr: str = Field("Dr", pattern="^(Dr|Cr)$")
    hold_payment: bool = False
    hold_payment_pct: float = 0.0
    ledger_date: Optional[date] = None
    freeze_upto: Optional[date] = None

    # Contact
    contact_person: Optional[str] = None
    designation: Optional[str] = None
    phone_office: Optional[str] = None
    phone_residence: Optional[str] = None
    mobile: Optional[str] = None
    phone: Optional[str] = None  # legacy
    fax: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None

    # Address
    mail_to: Optional[str] = None
    address: Optional[str] = None
    pin_code: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None
    country: str = "India"

    # GST
    gst_heading: str = "local"
    gstin: Optional[str] = None  # legacy
    gstin_no: Optional[str] = None
    gstin_date: Optional[date] = None

    # Licenses
    dl_number: Optional[str] = None
    dl_expiry: Optional[date] = None
    vat_number: Optional[str] = None
    vat_expiry: Optional[date] = None
    st_number: Optional[str] = None
    st_expiry: Optional[date] = None
    food_license_no: Optional[str] = None
    food_license_expiry: Optional[date] = None
    extra_license_no: Optional[str] = None
    extra_license_expiry: Optional[date] = None
    pan_number: Optional[str] = None

    # Misc
    narco_sch_h_billing: str = "allow_all"
    bill_import: str = "mobile"
    ledger_category: str = "OTHERS"
    ledger_type: str = "unregistered"
    color_tag: str = "normal"
    is_hidden: bool = False
    is_active: bool = True


class SupplierOut(SupplierIn):
    id: int
    class Config: from_attributes = True


class SaltIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = None
    is_active: bool = True

class SaltOut(SaltIn):
    id: int
    class Config: from_attributes = True


class RackIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=30)
    location: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True

class RackOut(RackIn):
    id: int
    class Config: from_attributes = True


class UoMIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    abbreviation: Optional[str] = None
    decimal_supported: bool = False
    is_active: bool = True

class UoMOut(UoMIn):
    id: int
    class Config: from_attributes = True


def _register_master_crud(
    *, path: str, model, schema_in, schema_out, perm_key: str, label: str,
    order_col,
):
    """Attach list/create/update/delete endpoints for a simple master table."""

    @router.get(path, response_model=List[schema_out], name=f"list_{label}")
    def _list(
        active_only: bool = True,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_catalog")),
    ):
        q = db.query(model).filter(model.hospital_id == current_user.hospital_id)
        if active_only:
            q = q.filter(model.is_active == True)  # noqa: E712
        return q.order_by(order_col).all()

    @router.post(path, response_model=schema_out, status_code=201, name=f"create_{label}")
    def _create(
        data: schema_in,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_feature_permission(Modules.PHARMACY, perm_key)),
    ):
        payload = data.model_dump()
        row = model(hospital_id=current_user.hospital_id, **payload)
        db.add(row); db.commit(); db.refresh(row)
        _audit(db, current_user, f"create_{label}", label, row.id,
               f"Created {label} #{row.id}")
        return row

    @router.put(path + "/{rid}", response_model=schema_out, name=f"update_{label}")
    def _update(
        rid: int, data: schema_in,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_feature_permission(Modules.PHARMACY, perm_key)),
    ):
        row = db.query(model).filter(
            model.id == rid, model.hospital_id == current_user.hospital_id,
        ).first()
        _ensure_active_or_404(row, label)
        for k, v in data.model_dump().items():
            setattr(row, k, v)
        db.commit(); db.refresh(row)
        _audit(db, current_user, f"update_{label}", label, row.id,
               f"Updated {label} #{row.id}")
        return row

    @router.delete(path + "/{rid}", status_code=204, name=f"delete_{label}")
    def _delete(
        rid: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_feature_permission(Modules.PHARMACY, perm_key)),
    ):
        row = db.query(model).filter(
            model.id == rid, model.hospital_id == current_user.hospital_id,
        ).first()
        _ensure_active_or_404(row, label)
        row.is_active = False
        db.commit()
        _audit(db, current_user, f"delete_{label}", label, row.id,
               f"Soft-deleted {label} #{row.id}")
        return None


_register_master_crud(
    path="/companies", model=PharmacyCompany,
    schema_in=CompanyIn, schema_out=CompanyOut,
    perm_key="manage_companies", label="pharmacy_company",
    order_col=PharmacyCompany.name,
)
_register_master_crud(
    path="/suppliers", model=PharmacySupplier,
    schema_in=SupplierIn, schema_out=SupplierOut,
    perm_key="manage_suppliers", label="pharmacy_supplier",
    order_col=PharmacySupplier.name,
)
_register_master_crud(
    path="/salts", model=PharmacySalt,
    schema_in=SaltIn, schema_out=SaltOut,
    perm_key="manage_salts", label="pharmacy_salt",
    order_col=PharmacySalt.name,
)
_register_master_crud(
    path="/racks", model=PharmacyRack,
    schema_in=RackIn, schema_out=RackOut,
    perm_key="manage_racks", label="pharmacy_rack",
    order_col=PharmacyRack.code,
)
_register_master_crud(
    path="/uoms", model=PharmacyUoM,
    schema_in=UoMIn, schema_out=UoMOut,
    perm_key="manage_uoms", label="pharmacy_uom",
    order_col=PharmacyUoM.name,
)


# ============================================================================
# Medicines
# ============================================================================

class MedicineIn(BaseModel):
    medicine_code: str = Field(..., min_length=1, max_length=20)
    name: str = Field(..., min_length=1, max_length=200)
    generic_name: Optional[str] = None
    manufacturer: Optional[str] = None  # legacy free-text
    category_id: int
    dosage_form: Optional[str] = None
    strength: Optional[str] = None
    unit_price: float = 0.0  # legacy alias of rate_a

    # Pricing block (Section C)
    mrp: float = 0.0
    purchase_rate: float = 0.0
    rate_a: float = 0.0
    rate_b: float = 0.0
    cost_pcs: float = 0.0
    default_discount_pct: float = 0.0
    hsn_id: Optional[int] = None

    description: Optional[str] = None
    side_effects: Optional[str] = None
    contraindications: Optional[str] = None
    storage_conditions: Optional[str] = None

    is_active: bool = True
    is_hidden: bool = False
    requires_prescription: bool = True

    # Regulatory flags
    is_narcotic: bool = False
    is_high_alert: bool = False
    is_schedule_h: bool = False
    is_schedule_h1: bool = False
    is_tramadol: bool = False
    is_controlled: bool = False
    item_discount_pct: float = 0.0

    # Catalog metadata
    barcode: Optional[str] = None
    packaging: Optional[str] = None
    decimal_supported: bool = False
    strip_conversion_factor: int = Field(1, ge=1)
    rate_unit: str = Field("tablet", pattern="^(tablet|strip)$")

    # Master FKs
    company_id: Optional[int] = None
    rack_id: Optional[int] = None
    salt_id: Optional[int] = None
    uom_id: Optional[int] = None

    # Stock thresholds (Section D)
    min_qty: int = 0
    max_qty: int = 0
    reorder_qty: int = 0

    @field_validator(
        "unit_price", "mrp", "purchase_rate", "rate_a", "rate_b", "cost_pcs",
        "default_discount_pct", "item_discount_pct", mode="before",
    )
    @classmethod
    def _round_money_fields(cls, v):
        if v is None or v == "":
            return 0.0
        return round_money(v)


class MedicineOut(MedicineIn):
    id: int
    company_name: Optional[str] = None

    class Config:
        from_attributes = True


class MedicineLookupOut(MedicineOut):
    store_stock_qty: float = 0.0
    master_stock_qty: float = 0.0


def _medicine_out(med: Medicine) -> MedicineOut:
    """Serialize medicine and resolve manufacturer/company display name."""
    out = MedicineOut.model_validate(med)
    company_name = None
    try:
        if getattr(med, "company", None) is not None:
            company_name = med.company.name
    except Exception:
        company_name = None
    out.company_name = company_name or med.manufacturer
    return out


@router.get("/medicines", response_model=List[MedicineOut])
def list_medicines(
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    company_id: Optional[int] = None,
    schedule: Optional[str] = Query(
        None,
        description="One of: h, h1, narcotic, tramadol, controlled",
    ),
    active_only: bool = True,
    include_hidden: bool = False,
    limit: int = 500,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_catalog")),
):
    q = db.query(Medicine).filter(Medicine.hospital_id == current_user.hospital_id)
    if active_only:
        q = q.filter(Medicine.is_active == True)  # noqa: E712
    if not include_hidden:
        q = q.filter(Medicine.is_hidden == False)  # noqa: E712
    if search:
        like = f"%{search.lower()}%"
        q = q.filter(or_(
            Medicine.name.ilike(like),
            Medicine.generic_name.ilike(like),
            Medicine.medicine_code.ilike(like),
            Medicine.barcode.ilike(like),
        ))
    if category_id:
        q = q.filter(Medicine.category_id == category_id)
    if company_id:
        q = q.filter(Medicine.company_id == company_id)
    if schedule:
        flag_map = {
            "h": Medicine.is_schedule_h,
            "h1": Medicine.is_schedule_h1,
            "narcotic": Medicine.is_narcotic,
            "tramadol": Medicine.is_tramadol,
            "controlled": Medicine.is_controlled,
        }
        col = flag_map.get(schedule.lower())
        if col is None:
            raise HTTPException(status_code=400, detail="Invalid schedule filter")
        q = q.filter(col == True)  # noqa: E712
    return q.order_by(Medicine.name).limit(limit).all()


@router.get("/medicines/lookup", response_model=List[MedicineLookupOut])
def lookup_medicine(
    q: Optional[str] = None,
    barcode: Optional[str] = None,
    store_id: Optional[int] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_catalog")),
):
    """Lightweight search used by sales counter (name / code / barcode).

    When store_id is supplied, each row includes stock at that store and at master
    (for transfer guidance — master qty is informational only).
    """
    query = db.query(Medicine).filter(
        Medicine.hospital_id == current_user.hospital_id,
        Medicine.is_active == True,  # noqa: E712
        Medicine.is_hidden == False,  # noqa: E712
    )
    if barcode:
        query = query.filter(Medicine.barcode == barcode)
    elif q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(
            Medicine.name.ilike(like),
            Medicine.generic_name.ilike(like),
            Medicine.medicine_code.ilike(like),
        ))
    else:
        return []
    meds = query.order_by(Medicine.name).limit(limit).all()

    lookup_store_id = None
    if store_id is not None:
        lookup_store_id = resolve_store_id(db, current_user, store_id)
    master_id = get_master_store_id(db, current_user.hospital_id)

    out = []
    for med in meds:
        base = _medicine_out(med)
        row = MedicineLookupOut(**base.model_dump())
        if lookup_store_id is not None:
            row.store_stock_qty = sum_store_stock(
                db, medicine_id=med.id, hospital_id=current_user.hospital_id,
                store_id=lookup_store_id,
            )
        if master_id is not None and master_id != lookup_store_id:
            row.master_stock_qty = sum_store_stock(
                db, medicine_id=med.id, hospital_id=current_user.hospital_id,
                store_id=master_id,
            )
        elif master_id is not None and lookup_store_id is None:
            row.master_stock_qty = sum_store_stock(
                db, medicine_id=med.id, hospital_id=current_user.hospital_id,
                store_id=master_id,
            )
        out.append(row)
    return out


class UnmappedMedicineOut(BaseModel):
    id: int
    medicine_code: str
    name: str
    created_at: Optional[datetime] = None
    unit_price: float = 0.0
    rate_a: float = 0.0

    class Config:
        from_attributes = True


class MapUnmappedMedicineIn(BaseModel):
    rate_a: float = Field(..., gt=0)
    category_id: int
    generic_name: Optional[str] = None
    strength: Optional[str] = None
    dosage_form: Optional[str] = None
    merge_into_medicine_id: Optional[int] = None

    @field_validator("rate_a", mode="before")
    @classmethod
    def _round_rate_a(cls, v):
        return round_money(v)


@router.get("/medicines/unmapped", response_model=List[UnmappedMedicineOut])
def list_unmapped_medicines(
    search: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission_any(Modules.PHARMACY, "manage_medicines", "dispense_rx")),
):
    """Free-text medicines auto-created from inpatient orders — hidden from catalog until mapped."""
    q = db.query(Medicine).filter(
        Medicine.hospital_id == current_user.hospital_id,
        Medicine.is_active == True,  # noqa: E712
        Medicine.is_hidden == True,  # noqa: E712
        Medicine.medicine_code.like("TXT-%"),
    )
    if search:
        like = f"%{search.lower()}%"
        q = q.filter(or_(
            Medicine.name.ilike(like),
            Medicine.medicine_code.ilike(like),
        ))
    rows = q.order_by(Medicine.created_at.desc()).limit(limit).all()
    return rows


@router.post("/medicines/{mid}/map", response_model=MedicineOut)
def map_unmapped_medicine(
    mid: int,
    data: MapUnmappedMedicineIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission_any(Modules.PHARMACY, "manage_medicines", "dispense_rx")),
):
    """Promote a free-text stub to the catalog, or merge it into an existing medicine."""
    stub = db.query(Medicine).filter(
        Medicine.id == mid,
        Medicine.hospital_id == current_user.hospital_id,
        Medicine.is_hidden == True,  # noqa: E712
    ).first()
    if not stub or not is_free_text_medicine(stub):
        raise HTTPException(status_code=404, detail="Unmapped medicine not found")

    cat = db.query(MedicineCategory).filter(
        MedicineCategory.id == data.category_id,
        MedicineCategory.hospital_id == current_user.hospital_id,
    ).first()
    if not cat:
        raise HTTPException(status_code=400, detail="Invalid category")

    if data.merge_into_medicine_id:
        target = db.query(Medicine).filter(
            Medicine.id == data.merge_into_medicine_id,
            Medicine.hospital_id == current_user.hospital_id,
            Medicine.is_active == True,  # noqa: E712
            Medicine.is_hidden == False,  # noqa: E712
        ).first()
        if not target:
            raise HTTPException(status_code=400, detail="Target medicine not found")
        db.query(PrescriptionItem).filter(PrescriptionItem.medicine_id == stub.id).update(
            {PrescriptionItem.medicine_id: target.id},
            synchronize_session=False,
        )
        stub.is_active = False
        db.commit()
        db.refresh(target)
        _audit(db, current_user, "map_medicine", "medicine", target.id,
               f"Merged free-text stub #{stub.id} into {target.name}")
        return target

    stub.category_id = data.category_id
    stub.rate_a = data.rate_a
    stub.unit_price = data.rate_a
    stub.generic_name = data.generic_name
    stub.strength = data.strength
    stub.dosage_form = data.dosage_form
    stub.is_hidden = False
    db.commit()
    db.refresh(stub)
    _audit(db, current_user, "map_medicine", "medicine", stub.id,
           f"Promoted free-text medicine {stub.name} to catalog at ₹{data.rate_a}")
    return stub


@router.get("/medicines/{mid}", response_model=MedicineOut)
def get_medicine(
    mid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_catalog")),
):
    row = db.query(Medicine).filter(
        Medicine.id == mid, Medicine.hospital_id == current_user.hospital_id,
    ).first()
    _ensure_active_or_404(row, "Medicine")
    return _medicine_out(row)


@router.post("/medicines", response_model=MedicineOut, status_code=201)
def create_medicine(
    data: MedicineIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_medicines")),
):
    # Uniqueness on medicine_code per hospital
    dup = db.query(Medicine).filter(
        Medicine.medicine_code == data.medicine_code,
        Medicine.hospital_id == current_user.hospital_id,
        Medicine.is_active == True,  # noqa: E712
    ).first()
    if dup:
        raise HTTPException(status_code=400, detail="Medicine code already exists")

    row = Medicine(
        hospital_id=current_user.hospital_id,
        **data.model_dump(),
    )
    apply_medicine_price_rounding(row)
    apply_cost_pcs_from_mrp(row)
    db.add(row); db.commit(); db.refresh(row)
    _audit(db, current_user, "create_medicine", "medicine", row.id,
           f"Created medicine '{row.name}' ({row.medicine_code})")
    return row


@router.put("/medicines/{mid}", response_model=MedicineOut)
def update_medicine(
    mid: int, data: MedicineIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_medicines")),
):
    row = db.query(Medicine).filter(
        Medicine.id == mid, Medicine.hospital_id == current_user.hospital_id,
    ).first()
    _ensure_active_or_404(row, "Medicine")
    for k, v in data.model_dump().items():
        setattr(row, k, v)
    apply_medicine_price_rounding(row)
    apply_cost_pcs_from_mrp(row)
    db.commit(); db.refresh(row)
    _audit(db, current_user, "update_medicine", "medicine", row.id,
           f"Updated medicine #{row.id}")
    return row


@router.delete("/medicines/{mid}", status_code=204)
def delete_medicine(
    mid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_medicines")),
):
    row = db.query(Medicine).filter(
        Medicine.id == mid, Medicine.hospital_id == current_user.hospital_id,
    ).first()
    _ensure_active_or_404(row, "Medicine")
    row.is_active = False
    db.commit()
    _audit(db, current_user, "delete_medicine", "medicine", row.id,
           f"Soft-deleted medicine #{row.id}")
    return None


# ============================================================================
# HSN / Tax codes (Section C)
# ============================================================================

class HSNIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=20)
    description: Optional[str] = None
    sgst_pct: float = 0.0
    cgst_pct: float = 0.0
    igst_pct: float = 0.0  # defaults to sgst_pct + cgst_pct; client may override
    is_active: bool = True


def _normalize_hsn_tax(sgst_pct: float, cgst_pct: float) -> tuple:
    """IGST is always the combined rate (CGST + SGST) for inter-state use."""
    sgst = float(sgst_pct or 0)
    cgst = float(cgst_pct or 0)
    return sgst, cgst, round(sgst + cgst, 4)


def _hsn_total_tax_pct(hsn_row: Optional[PharmacyHSN]) -> float:
    """Total GST rate on a line — CGST + SGST (IGST mirrors that sum, never added twice)."""
    if not hsn_row:
        return 0.0
    return (hsn_row.sgst_pct or 0) + (hsn_row.cgst_pct or 0)


def _prepare_hsn_payload(data: HSNIn) -> dict:
    d = data.model_dump()
    sgst, cgst, default_igst = _normalize_hsn_tax(d["sgst_pct"], d["cgst_pct"])
    d["sgst_pct"] = sgst
    d["cgst_pct"] = cgst
    d["igst_pct"] = round(float(d["igst_pct"]) if d["igst_pct"] is not None else default_igst, 4)
    return d


class HSNOut(HSNIn):
    id: int
    class Config: from_attributes = True


@router.get("/hsn", response_model=List[HSNOut])
def list_hsn(
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_catalog")),
):
    q = db.query(PharmacyHSN).filter(PharmacyHSN.hospital_id == current_user.hospital_id)
    if active_only:
        q = q.filter(PharmacyHSN.is_active == True)  # noqa: E712
    return q.order_by(PharmacyHSN.code).all()


def _check_duplicate_hsn_entry(
    db: Session, *, hospital_id: int, code: str,
    sgst_pct: float, cgst_pct: float, exclude_hid: Optional[int] = None,
) -> None:
    """Reject duplicate HSN code + tax-rate combos (same code, different tax is allowed)."""
    normalized = (code or "").strip()
    if not normalized:
        return
    sgst, cgst, _ = _normalize_hsn_tax(sgst_pct, cgst_pct)
    q = db.query(PharmacyHSN).filter(
        PharmacyHSN.hospital_id == hospital_id,
        sa_func.lower(PharmacyHSN.code) == normalized.lower(),
        PharmacyHSN.sgst_pct == sgst,
        PharmacyHSN.cgst_pct == cgst,
    )
    if exclude_hid is not None:
        q = q.filter(PharmacyHSN.id != exclude_hid)
    if q.first():
        raise HTTPException(
            status_code=400,
            detail="HSN code with the same SGST/CGST rates already exists",
        )


@router.post("/hsn", response_model=HSNOut, status_code=201)
def create_hsn(
    data: HSNIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_hsn_tax")),
):
    payload = _prepare_hsn_payload(data)
    _check_duplicate_hsn_entry(
        db, hospital_id=current_user.hospital_id, code=payload["code"],
        sgst_pct=payload["sgst_pct"], cgst_pct=payload["cgst_pct"],
    )
    row = PharmacyHSN(hospital_id=current_user.hospital_id, **payload)
    db.add(row); db.commit(); db.refresh(row)
    _audit(db, current_user, "create_hsn", "pharmacy_hsn", row.id,
           f"Created HSN code {row.code} (SGST {row.sgst_pct}% + CGST {row.cgst_pct}%)")
    return row


@router.put("/hsn/{hid}", response_model=HSNOut)
def update_hsn(
    hid: int, data: HSNIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_hsn_tax")),
):
    row = db.query(PharmacyHSN).filter(
        PharmacyHSN.id == hid, PharmacyHSN.hospital_id == current_user.hospital_id,
    ).first()
    _ensure_active_or_404(row, "HSN")
    payload = _prepare_hsn_payload(data)
    _check_duplicate_hsn_entry(
        db, hospital_id=current_user.hospital_id, code=payload["code"],
        sgst_pct=payload["sgst_pct"], cgst_pct=payload["cgst_pct"], exclude_hid=row.id,
    )
    for k, v in payload.items():
        setattr(row, k, v)
    db.commit(); db.refresh(row)
    _audit(db, current_user, "update_hsn", "pharmacy_hsn", row.id, f"Updated HSN #{row.id}")
    return row


@router.delete("/hsn/{hid}", status_code=204)
def delete_hsn(
    hid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_hsn_tax")),
):
    row = db.query(PharmacyHSN).filter(
        PharmacyHSN.id == hid, PharmacyHSN.hospital_id == current_user.hospital_id,
    ).first()
    _ensure_active_or_404(row, "HSN")
    row.is_active = False
    db.commit()
    _audit(db, current_user, "delete_hsn", "pharmacy_hsn", row.id, f"Soft-deleted HSN #{row.id}")
    return None


# ============================================================================
# Medicine pricing (focused endpoint — Section C)
# ============================================================================

class MedicinePricingIn(BaseModel):
    """Pricing-only update. Use `PUT /medicines/{id}` for full edits — this
    endpoint exists so users with `set_rates` but not `manage_medicines` can
    update rates without needing full medicine-edit rights."""
    mrp: Optional[float] = None
    purchase_rate: Optional[float] = None
    rate_a: Optional[float] = None
    rate_b: Optional[float] = None
    cost_pcs: Optional[float] = None
    default_discount_pct: Optional[float] = None
    hsn_id: Optional[int] = None

    @field_validator(
        "mrp", "purchase_rate", "rate_a", "rate_b", "cost_pcs", "default_discount_pct",
        mode="before",
    )
    @classmethod
    def _round_optional_money(cls, v):
        if v is None or v == "":
            return None
        return round_money(v)


@router.put("/medicines/{mid}/pricing", response_model=MedicineOut)
def update_medicine_pricing(
    mid: int, data: MedicinePricingIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "set_rates")),
):
    row = db.query(Medicine).filter(
        Medicine.id == mid, Medicine.hospital_id == current_user.hospital_id,
    ).first()
    _ensure_active_or_404(row, "Medicine")
    diff = {}
    for k, v in data.model_dump(exclude_none=True).items():
        old = getattr(row, k, None)
        if old != v:
            diff[k] = {"from": old, "to": v}
            setattr(row, k, v)
    if not diff:
        return row
    # Keep legacy unit_price tracking rate_a when rate_a changes
    if "rate_a" in diff and (data.rate_a is not None):
        row.unit_price = round_money(data.rate_a)
    if "mrp" in diff or "strip_conversion_factor" in diff:
        apply_cost_pcs_from_mrp(row)
    apply_medicine_price_rounding(row)
    db.commit(); db.refresh(row)
    _audit(db, current_user, "update_medicine_pricing", "medicine", row.id,
           f"Pricing changed for medicine #{row.id}", details=diff)
    return row


# ============================================================================
# Inventory & batches (Section D)
# ============================================================================

class InventoryRowOut(BaseModel):
    """Per-medicine aggregated stock with low-stock flag."""
    medicine_id: int
    medicine_code: str
    name: str
    rack_code: Optional[str] = None
    uom: Optional[str] = None
    total_stock: float
    min_qty: int
    is_low_stock: bool
    batch_count: int


class BatchOut(BaseModel):
    id: int
    medicine_id: int
    medicine_name: str
    batch_number: str
    expiry_date: Optional[date] = None
    quantity_in_stock: float
    mrp: float
    purchase_rate: float
    rate_a: float = 0.0
    rate_b: float = 0.0
    strip_conversion_factor: int = 1
    selling_price: float
    free_quantity: int
    supplier_id: Optional[int] = None
    supplier_name: Optional[str] = None
    purchase_id: Optional[int] = None
    hsn_id: Optional[int] = None
    is_active: bool

    class Config: from_attributes = True


@router.get("/inventory", response_model=List[InventoryRowOut])
def list_inventory(
    search: Optional[str] = None,
    low_only: bool = False,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_inventory")),
):
    """Per-medicine stock summary across batches with low-stock flag."""
    sid = resolve_store_id(db, current_user, store_id)
    # Aggregate stock + nearest expiry per medicine
    agg = db.query(
        PharmacyInventory.medicine_id,
        sa_func.sum(PharmacyInventory.quantity_in_stock).label("total"),
        sa_func.count(PharmacyInventory.id).label("batches"),
    ).filter(
        PharmacyInventory.hospital_id == current_user.hospital_id,
        PharmacyInventory.store_id == sid,
        PharmacyInventory.is_active == True,  # noqa: E712
    ).group_by(PharmacyInventory.medicine_id).subquery()

    rows = db.query(Medicine, agg.c.total, agg.c.batches, PharmacyRack.code, PharmacyUoM.abbreviation).outerjoin(
        agg, agg.c.medicine_id == Medicine.id,
    ).outerjoin(PharmacyRack, Medicine.rack_id == PharmacyRack.id) \
     .outerjoin(PharmacyUoM, Medicine.uom_id == PharmacyUoM.id) \
     .filter(
        Medicine.hospital_id == current_user.hospital_id,
        Medicine.is_active == True,  # noqa: E712
        Medicine.is_hidden == False,  # noqa: E712
     )
    if search:
        like = f"%{search.lower()}%"
        rows = rows.filter(or_(Medicine.name.ilike(like), Medicine.medicine_code.ilike(like), Medicine.barcode.ilike(like)))

    out = []
    for med, total, batches, rack_code, uom_abbr in rows.order_by(Medicine.name).all():
        total = float(total or 0)
        low = (med.min_qty or 0) > 0 and total <= (med.min_qty or 0)
        if low_only and not low:
            continue
        out.append(InventoryRowOut(
            medicine_id=med.id, medicine_code=med.medicine_code, name=med.name,
            rack_code=rack_code, uom=uom_abbr,
            total_stock=total, min_qty=med.min_qty or 0, is_low_stock=low,
            batch_count=int(batches or 0),
        ))
    return out


@router.get("/inventory/batches", response_model=List[BatchOut])
def list_batches(
    medicine_id: Optional[int] = None,
    supplier_id: Optional[int] = None,
    store_id: Optional[int] = None,
    active_only: bool = True,
    include_batch_id: Optional[int] = None,
    limit: int = 500,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_inventory")),
):
    sid = resolve_store_id(db, current_user, store_id)
    q = db.query(PharmacyInventory, Medicine, PharmacySupplier).join(
        Medicine, Medicine.id == PharmacyInventory.medicine_id,
    ).outerjoin(PharmacySupplier, PharmacySupplier.id == PharmacyInventory.supplier_id).filter(
        PharmacyInventory.hospital_id == current_user.hospital_id,
        PharmacyInventory.store_id == sid,
    )
    if active_only:
        q = q.filter(PharmacyInventory.is_active == True)  # noqa: E712
    if medicine_id:
        q = q.filter(PharmacyInventory.medicine_id == medicine_id)
    if supplier_id:
        q = q.filter(PharmacyInventory.supplier_id == supplier_id)
    rows = q.order_by(
        PharmacyInventory.expiry_date.asc(),
        PharmacyInventory.id.asc(),
    ).limit(limit).all()
    if include_batch_id and not any(inv.id == include_batch_id for inv, _, _ in rows):
        extra = db.query(PharmacyInventory, Medicine, PharmacySupplier).join(
            Medicine, Medicine.id == PharmacyInventory.medicine_id,
        ).outerjoin(
            PharmacySupplier, PharmacySupplier.id == PharmacyInventory.supplier_id,
        ).filter(
            PharmacyInventory.id == include_batch_id,
            PharmacyInventory.hospital_id == current_user.hospital_id,
            PharmacyInventory.store_id == sid,
        ).first()
        if extra:
            rows = [extra] + list(rows)
    return [
        BatchOut(
            id=inv.id, medicine_id=inv.medicine_id, medicine_name=med.name,
            batch_number=inv.batch_number,
            expiry_date=(
                inv.expiry_date if inv.expiry_date and inv.expiry_date != _EXPIRY_SENTINEL
                else None
            ),
            quantity_in_stock=inv.quantity_in_stock, mrp=inv.mrp or 0.0,
            purchase_rate=inv.purchase_rate or 0.0,
            rate_a=inv.rate_a or 0.0,
            rate_b=getattr(inv, "rate_b", 0) or 0.0,
            strip_conversion_factor=max(1, int(inv.strip_conversion_factor or 0) or int(med.strip_conversion_factor or 1) or 1),
            selling_price=inv.selling_price or 0.0,
            free_quantity=inv.free_quantity or 0,
            supplier_id=inv.supplier_id, supplier_name=sup.name if sup else None,
            purchase_id=inv.purchase_id, hsn_id=inv.hsn_id, is_active=inv.is_active,
        ) for inv, med, sup in rows
    ]


@router.get("/inventory/low-stock", response_model=List[InventoryRowOut])
def list_low_stock(
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_low_stock")),
):
    """All medicines whose total stock ≤ min_qty (and min_qty > 0)."""
    return list_inventory(search=None, low_only=True, store_id=store_id, db=db, current_user=current_user)


class StockAdjustIn(BaseModel):
    batch_id: int
    qty_change: float  # signed
    reason: str = Field(..., min_length=2, max_length=200)


@router.post("/inventory/adjust", status_code=201)
def adjust_stock(
    data: StockAdjustIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "adjust_stock")),
):
    """Manual stock adjustment. Writes the adjustment row + a ledger entry."""
    batch = db.query(PharmacyInventory).filter(
        PharmacyInventory.id == data.batch_id,
        PharmacyInventory.hospital_id == current_user.hospital_id,
    ).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    new_qty = (batch.quantity_in_stock or 0) + data.qty_change
    if new_qty < 0:
        raise HTTPException(status_code=400, detail=f"Adjustment would result in negative stock ({new_qty}). Current: {batch.quantity_in_stock}, change: {data.qty_change:+}")

    batch.quantity_in_stock = new_qty
    adj = PharmacyStockAdjustment(
        medicine_id=batch.medicine_id, batch_id=batch.id,
        qty_change=data.qty_change, reason=data.reason,
        performed_by=current_user.id, store_id=batch.store_id,
        hospital_id=current_user.hospital_id,
    )
    db.add(adj)
    db.flush()  # need adj.id for the ledger reference
    led = PharmacyStockLedger(
        medicine_id=batch.medicine_id, batch_id=batch.id,
        txn_type="adjustment", qty_delta=data.qty_change,
        reference_type="adjustment", reference_id=adj.id,
        performed_by=current_user.id, store_id=batch.store_id, notes=data.reason,
        hospital_id=current_user.hospital_id,
    )
    db.add(led)
    db.commit(); db.refresh(adj); db.refresh(batch)
    _audit(db, current_user, "adjust_stock", "pharmacy_inventory", batch.id,
           f"Stock adjusted by {data.qty_change:+g} on batch {batch.batch_number}",
           details={"reason": data.reason, "new_qty": new_qty})
    return {
        "adjustment_id": adj.id,
        "batch_id": batch.id,
        "new_quantity": batch.quantity_in_stock,
    }


class ExpiringBatchOut(BaseModel):
    batch_id: int
    medicine_id: int
    medicine_code: Optional[str] = None
    medicine_name: str
    batch_number: str
    expiry_date: date
    days_to_expiry: int
    quantity_in_stock: float
    stock_value_cost: float


@router.get("/inventory/expiring", response_model=List[ExpiringBatchOut])
def list_expiring_batches(
    days: int = 90,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_expiring")),
):
    """Active batches with `expiry_date <= today + days` and stock > 0.

    Sentinel-expiry batches (no-expiry stock) are excluded. Negative `days`
    is accepted and returns already-expired stock (useful for the write-off
    workflow).
    """
    if days < -3650 or days > 3650:
        raise HTTPException(status_code=400, detail="days must be within ±3650")
    today = date.today()
    threshold = today + timedelta(days=days)
    sid = resolve_store_id(db, current_user, store_id)
    rows = (
        db.query(PharmacyInventory, Medicine)
        .join(Medicine, Medicine.id == PharmacyInventory.medicine_id)
        .filter(
            PharmacyInventory.hospital_id == current_user.hospital_id,
            PharmacyInventory.store_id == sid,
            PharmacyInventory.is_active == True,  # noqa: E712
            PharmacyInventory.quantity_in_stock > 0,
            PharmacyInventory.expiry_date <= threshold,
            PharmacyInventory.expiry_date < _EXPIRY_SENTINEL,
        )
        .order_by(PharmacyInventory.expiry_date.asc(), PharmacyInventory.id.asc())
        .all()
    )
    out: List[ExpiringBatchOut] = []
    for inv, med in rows:
        qty = float(inv.quantity_in_stock or 0)
        cost = float(inv.cost_price or 0)
        out.append(ExpiringBatchOut(
            batch_id=inv.id,
            medicine_id=med.id,
            medicine_code=med.medicine_code,
            medicine_name=med.name,
            batch_number=inv.batch_number,
            expiry_date=inv.expiry_date,
            days_to_expiry=(inv.expiry_date - today).days,
            quantity_in_stock=qty,
            stock_value_cost=round(qty * cost, 2),
        ))
    return out


class ExpiryWriteoffIn(BaseModel):
    batch_ids: List[int] = Field(..., min_items=1)
    reason: str = Field(..., min_length=2, max_length=200)


class ExpiryWriteoffOut(BaseModel):
    batches_written_off: int
    total_qty_written_off: float
    total_cost_value: float
    ledger_rows: int


@router.post("/inventory/expire-writeoff", response_model=ExpiryWriteoffOut, status_code=201)
def writeoff_expired_batches(
    data: ExpiryWriteoffIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "adjust_stock")),
):
    """Zero out the stock on one or more expired batches and write a ledger
    row per batch (txn_type='expiry_writeoff'). Operates only on batches the
    caller's hospital owns and ignores anything already at zero.
    """
    batches = (
        db.query(PharmacyInventory)
        .filter(
            PharmacyInventory.id.in_(data.batch_ids),
            PharmacyInventory.hospital_id == current_user.hospital_id,
            PharmacyInventory.is_active == True,  # noqa: E712
        )
        .with_for_update()
        .all()
    )
    if not batches:
        raise HTTPException(status_code=404, detail="No matching batches found")

    total_qty = 0.0
    total_value = 0.0
    rows_written = 0
    for b in batches:
        qty = float(b.quantity_in_stock or 0)
        if qty <= 0:
            continue
        cost = float(b.cost_price or 0)
        total_qty += qty
        total_value += qty * cost
        b.quantity_in_stock = 0
        db.add(PharmacyStockLedger(
            medicine_id=b.medicine_id, batch_id=b.id,
            txn_type="expiry_writeoff", qty_delta=-qty,
            reference_type="expiry", reference_id=b.id,
            performed_by=current_user.id, hospital_id=current_user.hospital_id,
            notes=f"Expiry write-off ({b.expiry_date}): {data.reason}",
        ))
        rows_written += 1

    db.commit()
    _audit(db, current_user, "expiry_writeoff", "pharmacy_inventory", 0,
           f"Wrote off {rows_written} batch(es), total qty {total_qty:g}, value ₹{round(total_value, 2)}",
           details={"reason": data.reason, "batch_ids": data.batch_ids})
    return ExpiryWriteoffOut(
        batches_written_off=rows_written,
        total_qty_written_off=total_qty,
        total_cost_value=round(total_value, 2),
        ledger_rows=rows_written,
    )


class LedgerOut(BaseModel):
    id: int
    medicine_id: int
    medicine_name: str
    batch_id: Optional[int] = None
    batch_number: Optional[str] = None
    txn_type: str
    qty_delta: float
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None
    performed_by_name: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


@router.get("/inventory/ledger", response_model=List[LedgerOut])
def list_ledger(
    medicine_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    txn_type: Optional[str] = None,
    store_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 500,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_stock_ledger")),
):
    q = db.query(PharmacyStockLedger, Medicine, PharmacyInventory, User).join(
        Medicine, Medicine.id == PharmacyStockLedger.medicine_id,
    ).outerjoin(
        PharmacyInventory, PharmacyInventory.id == PharmacyStockLedger.batch_id,
    ).outerjoin(User, User.id == PharmacyStockLedger.performed_by).filter(
        PharmacyStockLedger.hospital_id == current_user.hospital_id,
    )
    if store_id is not None:
        sid = resolve_store_id(db, current_user, store_id)
        q = q.filter(PharmacyStockLedger.store_id == sid)
    if medicine_id:
        q = q.filter(PharmacyStockLedger.medicine_id == medicine_id)
    if batch_id:
        q = q.filter(PharmacyStockLedger.batch_id == batch_id)
    if txn_type:
        q = q.filter(PharmacyStockLedger.txn_type == txn_type)
    if date_from:
        q = q.filter(PharmacyStockLedger.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(PharmacyStockLedger.created_at <= datetime.combine(date_to, datetime.max.time()))
    rows = q.order_by(PharmacyStockLedger.created_at.desc()).limit(limit).all()
    return [
        LedgerOut(
            id=led.id, medicine_id=led.medicine_id, medicine_name=med.name,
            batch_id=led.batch_id, batch_number=inv.batch_number if inv else None,
            txn_type=led.txn_type, qty_delta=led.qty_delta,
            reference_type=led.reference_type, reference_id=led.reference_id,
            performed_by_name=(f"{u.first_name} {u.last_name}" if u else None),
            notes=led.notes, created_at=led.created_at,
        ) for led, med, inv, u in rows
    ]


# ============================================================================
# Procurement / Purchase (Section E)
# ----------------------------------------------------------------------------
# `expiry_date` is re-enabled as a user-entered field per Pharmacy P0 #2.
# The frontend collects MM/YYYY and submits last-day-of-month as YYYY-MM-DD.
# For purchases that don't carry an expiry (older imports, non-perishable
# consumables), the column stays populated with this sentinel so the NOT NULL
# constraint is satisfied. FEFO sort treats the sentinel as "never expires".
# ============================================================================

_EXPIRY_SENTINEL = date(2099, 12, 31)

class PurchaseItemIn(BaseModel):
    medicine_id: int
    batch_number: str = Field(..., min_length=1, max_length=50)
    mrp: float = 0.0
    quantity: float = Field(..., gt=0)
    free_quantity: float = 0.0
    purchase_rate: float = Field(..., ge=0)
    rate_a: float = 0.0
    rate_b: float = 0.0
    strip_conversion_factor: int = Field(1, ge=1)
    discount_pct: float = 0.0
    # Ignored if sent — tax is always taken from the medicine's HSN at save time.
    hsn_id: Optional[int] = None
    expiry_date: Optional[date] = None

    @field_validator("mrp", "purchase_rate", "rate_a", "rate_b", "discount_pct", mode="before")
    @classmethod
    def _round_purchase_money(cls, v):
        if v is None or v == "":
            return 0.0
        return round_money(v)

    @field_validator("strip_conversion_factor", mode="before")
    @classmethod
    def _coerce_strip_factor(cls, v):
        try:
            n = int(v or 1)
        except (TypeError, ValueError):
            n = 1
        return max(1, n)


class PurchaseItemOut(PurchaseItemIn):
    id: int
    tax_amount: float
    line_total: float
    inventory_id: Optional[int] = None
    medicine_name: Optional[str] = None

    class Config: from_attributes = True


class PurchaseIn(BaseModel):
    entry_date: date
    supplier_id: int
    store_id: Optional[int] = None
    invoice_number: Optional[str] = None
    bill_date: Optional[date] = None
    payment_type: str = Field("cash", pattern="^(cash|credit)$")
    purchase_type: Optional[str] = None
    tax_mode: str = Field("exclusive", pattern="^(exclusive|inclusive)$")
    notes: Optional[str] = None
    items: List[PurchaseItemIn] = Field(default_factory=list)


class PurchaseEditIn(PurchaseIn):
    """Draft edits ignore `reason`; confirmed edits require it."""
    reason: Optional[str] = Field(None, max_length=500)


class PurchaseOut(BaseModel):
    id: int
    purchase_number: str
    entry_date: date
    supplier_id: int
    supplier_name: Optional[str] = None
    invoice_number: Optional[str] = None
    bill_date: Optional[date] = None
    payment_type: str
    purchase_type: Optional[str] = None
    tax_mode: str = "exclusive"
    status: str
    subtotal: float
    total_discount: float
    total_tax: float
    grand_total: float
    notes: Optional[str] = None
    items: List[PurchaseItemOut] = Field(default_factory=list)
    created_at: datetime
    confirmed_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    revoke_reason: Optional[str] = None
    edited_at: Optional[datetime] = None
    edit_reason: Optional[str] = None

    class Config: from_attributes = True


def _next_purchase_number(db: Session, hospital_id: int) -> str:
    """`PURCH-YYMMDD-NNNN` — N is the sequence within the day for this hospital."""
    today = date.today()
    prefix = f"PURCH-{today.strftime('%y%m%d')}-"
    last = db.query(PharmacyPurchase).filter(
        PharmacyPurchase.purchase_number.like(prefix + "%"),
        PharmacyPurchase.hospital_id == hospital_id,
    ).order_by(PharmacyPurchase.purchase_number.desc()).first()
    seq = 1
    if last:
        try:
            seq = int(last.purchase_number.rsplit("-", 1)[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}{seq:04d}"


def _date_range(date_from: Optional[date], date_to: Optional[date]) -> tuple:
    """Inclusive [start, end] datetime pair derived from date inputs.

    `date_to` becomes end-of-day (23:59:59.999999) so that same-day records
    are not dropped. Either bound may be None — callers should treat None as
    'no lower/upper bound' and skip the filter.
    """
    start = datetime.combine(date_from, datetime.min.time()) if date_from else None
    end = datetime.combine(date_to, datetime.max.time()) if date_to else None
    return start, end


def _effective_cost(qty: float, free: float, rate: float) -> float:
    """Per-unit effective cost when `free` units come bundled at no charge.

    Stock valuation should not include the free portion at its purchase rate,
    so we spread the paid total across paid + free units. `purchase_rate` on
    the inventory row keeps the gross rate (used as the master P-Rate);
    `cost_price` carries this effective cost (used by stock_value_cost).
    """
    total = (qty or 0) + (free or 0)
    if total <= 0:
        return rate or 0.0
    return round_money(((qty or 0) * (rate or 0)) / total)


def _hsn_row_for_purchase_item(db: Session, item) -> Optional[PharmacyHSN]:
    """Resolve HSN for a purchase line — medicine master is source of truth."""
    hsn_id = item.hsn_id
    if not hsn_id and getattr(item, "medicine_id", None):
        med = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
        if med and med.hsn_id:
            hsn_id = med.hsn_id
            if hasattr(item, "hsn_id"):
                item.hsn_id = hsn_id
    if not hsn_id:
        return None
    return db.query(PharmacyHSN).filter(PharmacyHSN.id == hsn_id).first()


def _compute_item_line(
    item: dict, hsn_row: Optional[PharmacyHSN], *, tax_mode: str = "exclusive",
) -> dict:
    """Returns line_total, tax_amount, discount_amount for a purchase item.

    Formula: base = qty × p_rate; discount applied first; tax per tax_mode.
    Free quantity is non-billable but tracked for inventory.
    """
    qty = float(item.get("quantity") or 0)
    rate = float(item.get("purchase_rate") or 0)
    disc = float(item.get("discount_pct") or 0)
    base = qty * rate
    base_after_disc = base * (1 - disc / 100.0)
    tax_pct = _hsn_total_tax_pct(hsn_row)
    _taxable, tax_amt, line_total = compute_line_tax(
        base_after_disc, tax_pct, tax_mode=tax_mode,
    )
    return {
        "line_total": line_total,
        "tax_amount": tax_amt,
        "discount_amount": round(base - base_after_disc, 2),
    }


def _recompute_purchase_totals(purchase: PharmacyPurchase, db: Session) -> None:
    subtotal = 0.0
    disc = 0.0
    tax = 0.0
    grand = 0.0
    tax_mode = getattr(purchase, "tax_mode", None) or "exclusive"
    for it in purchase.items:
        hsn_row = _hsn_row_for_purchase_item(db, it)
        comp = _compute_item_line({
            "quantity": it.quantity, "purchase_rate": it.purchase_rate, "discount_pct": it.discount_pct,
        }, hsn_row, tax_mode=tax_mode)
        it.tax_amount = comp["tax_amount"]
        it.line_total = comp["line_total"]
        # P2.1: snapshot per-component HSN rates so historical reports don't
        # drift when the HSN master is edited later.
        it.sgst_pct = (hsn_row.sgst_pct or 0) if hsn_row else 0.0
        it.cgst_pct = (hsn_row.cgst_pct or 0) if hsn_row else 0.0
        it.igst_pct = (hsn_row.igst_pct if hsn_row else 0.0) or (it.sgst_pct + it.cgst_pct)
        subtotal += (it.quantity or 0) * (it.purchase_rate or 0)
        disc += comp["discount_amount"]
        tax += comp["tax_amount"]
        grand += comp["line_total"]
    purchase.subtotal = round(subtotal, 2)
    purchase.total_discount = round(disc, 2)
    purchase.total_tax = round(tax, 2)
    purchase.grand_total = round(grand, 2)


def _batch_key(medicine_id: int, batch_number: str, expiry_date: date) -> tuple:
    return (medicine_id, batch_number, expiry_date or _EXPIRY_SENTINEL)


def _validate_purchase_items(items: List[PurchaseItemIn]) -> None:
    """Batch #, expiry, and qty are mandatory on every purchase line."""
    for idx, item in enumerate(items, 1):
        if not (item.batch_number or "").strip():
            raise HTTPException(status_code=400, detail=f"Line {idx}: batch number is required")
        if not item.expiry_date or item.expiry_date == _EXPIRY_SENTINEL:
            raise HTTPException(status_code=400, detail=f"Line {idx}: expiry date is required (MM/YYYY)")
        if not (item.quantity or 0) > 0:
            raise HTTPException(status_code=400, detail=f"Line {idx}: quantity must be > 0")


def _sold_qty_for_batch(db: Session, batch_id: Optional[int]) -> float:
    if not batch_id:
        return 0.0
    sold_total = db.query(sa_func.coalesce(sa_func.sum(PharmacyStockLedger.qty_delta), 0)).filter(
        PharmacyStockLedger.batch_id == batch_id,
        PharmacyStockLedger.txn_type.in_(("sale", "rx_dispense")),
    ).scalar() or 0
    return abs(float(sold_total))


def _validate_confirmed_purchase_edit(
    db: Session, purchase: PharmacyPurchase, new_items: List[PurchaseItemIn],
) -> None:
    """Ensure new lines do not drop below already sold/dispensed quantities."""
    new_map: dict = {}
    for item in new_items:
        key = _batch_key(item.medicine_id, item.batch_number, item.expiry_date or _EXPIRY_SENTINEL)
        recv = float((item.quantity or 0) + (item.free_quantity or 0))
        new_map[key] = new_map.get(key, 0.0) + recv

    for old in purchase.items:
        key = _batch_key(old.medicine_id, old.batch_number, old.expiry_date or _EXPIRY_SENTINEL)
        sold = _sold_qty_for_batch(db, old.inventory_id)
        new_recv = new_map.get(key)
        if new_recv is None:
            if sold > 0:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Cannot remove batch {old.batch_number} — "
                        f"{sold:g} unit(s) already sold or dispensed"
                    ),
                )
        elif new_recv + 1e-9 < sold:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Batch {old.batch_number} new quantity ({new_recv:g}) is below "
                    f"already sold/dispensed ({sold:g})"
                ),
            )


def _reverse_purchase_item_stock(
    db: Session, item: PharmacyPurchaseItem, purchase: PharmacyPurchase,
    user: User, reason: str,
) -> float:
    """Reverse the un-sold portion of a confirmed purchase line."""
    received = float((item.quantity or 0) + (item.free_quantity or 0))
    batch_id = item.inventory_id
    sold = _sold_qty_for_batch(db, batch_id)
    reversible = max(0.0, received - sold)
    if reversible <= 0 or not batch_id:
        return 0.0
    batch = db.query(PharmacyInventory).filter(PharmacyInventory.id == batch_id).first()
    if not batch:
        return 0.0
    take = min(reversible, float(batch.quantity_in_stock or 0))
    batch.quantity_in_stock = float(batch.quantity_in_stock or 0) - take
    if (batch.quantity_in_stock or 0) <= 0:
        batch.quantity_in_stock = 0
        batch.is_active = False
    if take > 0:
        db.add(PharmacyStockLedger(
            medicine_id=item.medicine_id, batch_id=batch.id,
            txn_type="purchase_edit_reverse", qty_delta=-take,
            reference_type="purchase", reference_id=purchase.id,
            performed_by=user.id, store_id=purchase.store_id,
            hospital_id=purchase.hospital_id,
            notes=f"Edit purchase {purchase.purchase_number}: {reason}",
        ))
    return take


def _apply_purchase_item_to_inventory(
    db: Session, item: PharmacyPurchaseItem, purchase: PharmacyPurchase,
    user: User, purchase_store_id: int, ledger_notes: str,
) -> PharmacyInventory:
    """Create or merge an inventory batch for a purchase line; write ledger entry."""
    item_expiry = item.expiry_date or _EXPIRY_SENTINEL
    existing = db.query(PharmacyInventory).filter(
        PharmacyInventory.medicine_id == item.medicine_id,
        PharmacyInventory.batch_number == item.batch_number,
        PharmacyInventory.expiry_date == item_expiry,
        PharmacyInventory.store_id == purchase_store_id,
        PharmacyInventory.hospital_id == user.hospital_id,
        PharmacyInventory.is_active == True,  # noqa: E712
    ).first()
    added_qty = (item.quantity or 0) + (item.free_quantity or 0)
    eff_cost = _effective_cost(item.quantity, item.free_quantity, item.purchase_rate)
    item_rate_a = float(getattr(item, "rate_a", 0) or 0)
    item_rate_b = float(getattr(item, "rate_b", 0) or 0)
    item_scf = max(1, int(getattr(item, "strip_conversion_factor", 0) or 1))
    sell_price = item_rate_a or item.mrp or item.purchase_rate
    if existing:
        existing.quantity_in_stock = (existing.quantity_in_stock or 0) + added_qty
        existing.mrp = item.mrp or existing.mrp
        existing.purchase_rate = item.purchase_rate or existing.purchase_rate
        if item_rate_a:
            existing.rate_a = item_rate_a
            existing.selling_price = item_rate_a
        elif item.mrp:
            existing.selling_price = item.mrp
        if item_rate_b:
            existing.rate_b = item_rate_b
        if item_scf:
            existing.strip_conversion_factor = item_scf
        if item.purchase_rate:
            existing.cost_price = eff_cost
        existing.supplier_id = purchase.supplier_id
        existing.purchase_id = purchase.id
        existing.hsn_id = item.hsn_id or existing.hsn_id
        existing.free_quantity = (existing.free_quantity or 0) + (item.free_quantity or 0)
        existing.discount_pct = item.discount_pct
        inv = existing
    else:
        inv = PharmacyInventory(
            medicine_id=item.medicine_id, batch_number=item.batch_number,
            expiry_date=item_expiry, quantity_in_stock=added_qty,
            cost_price=eff_cost, selling_price=sell_price,
            mrp=item.mrp, purchase_rate=item.purchase_rate,
            rate_a=item_rate_a, rate_b=item_rate_b, strip_conversion_factor=item_scf,
            free_quantity=item.free_quantity or 0, discount_pct=item.discount_pct,
            hsn_id=item.hsn_id, supplier_id=purchase.supplier_id,
            purchase_id=purchase.id, purchase_date=purchase.entry_date,
            store_id=purchase_store_id,
            is_active=True, hospital_id=user.hospital_id,
        )
        db.add(inv)
        db.flush()

    db.add(PharmacyStockLedger(
        medicine_id=item.medicine_id, batch_id=inv.id, txn_type="purchase",
        qty_delta=added_qty, reference_type="purchase", reference_id=purchase.id,
        performed_by=user.id, store_id=purchase_store_id,
        hospital_id=user.hospital_id,
        notes=ledger_notes,
    ))

    med = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
    if med:
        last = med.last_purchase_date
        if last is None or purchase.entry_date >= last:
            if item.purchase_rate:
                med.purchase_rate = item.purchase_rate
            if item.mrp:
                med.mrp = item.mrp
            if item_rate_a:
                med.rate_a = item_rate_a
                med.unit_price = item_rate_a
            if item_rate_b:
                med.rate_b = item_rate_b
            if item_scf > 1 or not med.strip_conversion_factor:
                med.strip_conversion_factor = item_scf
            med.last_purchase_date = purchase.entry_date

    return inv


def _shape_purchase(p: PharmacyPurchase, db: Session) -> PurchaseOut:
    items_out: List[PurchaseItemOut] = []
    for it in p.items:
        med = db.query(Medicine).filter(Medicine.id == it.medicine_id).first()
        items_out.append(PurchaseItemOut(
            id=it.id, medicine_id=it.medicine_id, medicine_name=med.name if med else None,
            batch_number=it.batch_number,
            expiry_date=it.expiry_date if it.expiry_date != _EXPIRY_SENTINEL else None,
            mrp=it.mrp or 0.0, quantity=it.quantity, free_quantity=it.free_quantity or 0.0,
            purchase_rate=it.purchase_rate,
            rate_a=getattr(it, "rate_a", 0) or 0.0,
            rate_b=getattr(it, "rate_b", 0) or 0.0,
            strip_conversion_factor=max(1, int(getattr(it, "strip_conversion_factor", 0) or 1)),
            discount_pct=it.discount_pct or 0.0,
            hsn_id=it.hsn_id, tax_amount=it.tax_amount or 0.0,
            line_total=it.line_total or 0.0, inventory_id=it.inventory_id,
        ))
    return PurchaseOut(
        id=p.id, purchase_number=p.purchase_number, entry_date=p.entry_date,
        supplier_id=p.supplier_id, supplier_name=(p.supplier.name if p.supplier else None),
        invoice_number=p.invoice_number, bill_date=p.bill_date,
        payment_type=p.payment_type, purchase_type=p.purchase_type,
        tax_mode=getattr(p, "tax_mode", None) or "exclusive",
        status=p.status,
        subtotal=p.subtotal or 0.0, total_discount=p.total_discount or 0.0,
        total_tax=p.total_tax or 0.0, grand_total=p.grand_total or 0.0,
        notes=p.notes, items=items_out,
        created_at=p.created_at, confirmed_at=p.confirmed_at,
        revoked_at=p.revoked_at, revoke_reason=p.revoke_reason,
        edited_at=p.edited_at, edit_reason=p.edit_reason,
    )


def _check_duplicate_invoice(
    db: Session, *, hospital_id: int, supplier_id: int,
    invoice_number: Optional[str], exclude_purchase_id: Optional[int] = None,
) -> None:
    """Reject a second purchase with the same (supplier, invoice_number).

    Blank/None invoice numbers are allowed to repeat — pharmacies sometimes
    enter cash purchases without an invoice number.
    """
    inv = (invoice_number or "").strip()
    if not inv:
        return
    q = db.query(PharmacyPurchase).filter(
        PharmacyPurchase.hospital_id == hospital_id,
        PharmacyPurchase.supplier_id == supplier_id,
        PharmacyPurchase.invoice_number == inv,
    )
    if exclude_purchase_id is not None:
        q = q.filter(PharmacyPurchase.id != exclude_purchase_id)
    dup = q.first()
    if dup:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invoice #{inv} already entered for this supplier "
                f"on {dup.entry_date} ({dup.purchase_number})."
            ),
        )


@router.post("/purchases", response_model=PurchaseOut, status_code=201)
def create_purchase(
    data: PurchaseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_purchase")),
):
    sup = db.query(PharmacySupplier).filter(
        PharmacySupplier.id == data.supplier_id,
        PharmacySupplier.hospital_id == current_user.hospital_id,
    ).first()
    if not sup:
        raise HTTPException(status_code=400, detail="Invalid supplier")

    _validate_purchase_items(data.items)

    _check_duplicate_invoice(
        db, hospital_id=current_user.hospital_id,
        supplier_id=data.supplier_id, invoice_number=data.invoice_number,
    )

    purchase_store_id = resolve_store_id(
        db, current_user, data.store_id, require_purchase_store=True,
    )

    purchase = PharmacyPurchase(
        purchase_number=_next_purchase_number(db, current_user.hospital_id),
        entry_date=data.entry_date, supplier_id=data.supplier_id,
        invoice_number=data.invoice_number, bill_date=data.bill_date,
        payment_type=data.payment_type, purchase_type=data.purchase_type,
        tax_mode=data.tax_mode or "exclusive",
        status="draft", notes=data.notes,
        created_by=current_user.id, store_id=purchase_store_id,
        hospital_id=current_user.hospital_id,
    )
    db.add(purchase)
    # P3.3: handle concurrent-draft race on the per-day sequence.
    _flush_with_number_retry(
        db, purchase,
        regen=lambda: _next_purchase_number(db, current_user.hospital_id),
        set_attr="purchase_number",
    )

    for item in data.items:
        med = db.query(Medicine).filter(
            Medicine.id == item.medicine_id, Medicine.hospital_id == current_user.hospital_id,
        ).first()
        if not med:
            raise HTTPException(status_code=400, detail=f"Invalid medicine_id {item.medicine_id}")
        row = PharmacyPurchaseItem(
            purchase_id=purchase.id, medicine_id=item.medicine_id,
            batch_number=item.batch_number,
            expiry_date=item.expiry_date or _EXPIRY_SENTINEL,
            mrp=item.mrp, quantity=item.quantity, free_quantity=item.free_quantity,
            purchase_rate=item.purchase_rate,
            rate_a=item.rate_a or med.rate_a or 0.0,
            rate_b=item.rate_b or med.rate_b or 0.0,
            strip_conversion_factor=item.strip_conversion_factor or med.strip_conversion_factor or 1,
            discount_pct=item.discount_pct,
            hsn_id=med.hsn_id,
        )
        db.add(row)
    db.flush()
    db.refresh(purchase)
    _recompute_purchase_totals(purchase, db)
    db.commit(); db.refresh(purchase)

    _audit(db, current_user, "create_purchase", "pharmacy_purchase", purchase.id,
           f"Drafted purchase {purchase.purchase_number} ({len(data.items)} items, ₹{purchase.grand_total})")
    return _shape_purchase(purchase, db)


@router.put("/purchases/{pid}", response_model=PurchaseOut)
def edit_purchase(
    pid: int, data: PurchaseEditIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "edit_purchase")),
):
    purchase = db.query(PharmacyPurchase).filter(
        PharmacyPurchase.id == pid,
        PharmacyPurchase.hospital_id == current_user.hospital_id,
    ).first()
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    if purchase.status not in ("draft", "confirmed"):
        raise HTTPException(status_code=400, detail=f"Cannot edit a {purchase.status} purchase")

    is_confirmed = purchase.status == "confirmed"
    reason = (data.reason or "").strip()
    if is_confirmed:
        if len(reason) < 2:
            raise HTTPException(status_code=400, detail="Reason is required to edit a confirmed purchase")
        if not data.items:
            raise HTTPException(status_code=400, detail="Cannot leave purchase empty")

    sup = db.query(PharmacySupplier).filter(
        PharmacySupplier.id == data.supplier_id,
        PharmacySupplier.hospital_id == current_user.hospital_id,
    ).first()
    if not sup:
        raise HTTPException(status_code=400, detail="Invalid supplier")

    _validate_purchase_items(data.items)

    _check_duplicate_invoice(
        db, hospital_id=current_user.hospital_id,
        supplier_id=data.supplier_id, invoice_number=data.invoice_number,
        exclude_purchase_id=purchase.id,
    )

    if is_confirmed:
        _validate_confirmed_purchase_edit(db, purchase, data.items)
        if data.store_id is not None:
            new_store = resolve_store_id(
                db, current_user, data.store_id, require_purchase_store=True,
            )
            if new_store != purchase.store_id:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot change store on a confirmed purchase",
                )
        for old in list(purchase.items):
            _reverse_purchase_item_stock(db, old, purchase, current_user, reason)

    purchase.entry_date = data.entry_date
    purchase.supplier_id = data.supplier_id
    purchase.invoice_number = data.invoice_number
    purchase.bill_date = data.bill_date
    purchase.payment_type = data.payment_type
    purchase.purchase_type = data.purchase_type
    purchase.tax_mode = data.tax_mode or "exclusive"
    purchase.notes = data.notes
    if data.store_id is not None and not is_confirmed:
        purchase.store_id = resolve_store_id(
            db, current_user, data.store_id, require_purchase_store=True,
        )

    for old in list(purchase.items):
        db.delete(old)
    db.flush()
    for item in data.items:
        med = db.query(Medicine).filter(
            Medicine.id == item.medicine_id, Medicine.hospital_id == current_user.hospital_id,
        ).first()
        if not med:
            raise HTTPException(status_code=400, detail=f"Invalid medicine_id {item.medicine_id}")
        db.add(PharmacyPurchaseItem(
            purchase_id=purchase.id, medicine_id=item.medicine_id,
            batch_number=item.batch_number,
            expiry_date=item.expiry_date or _EXPIRY_SENTINEL,
            mrp=item.mrp, quantity=item.quantity, free_quantity=item.free_quantity,
            purchase_rate=item.purchase_rate,
            rate_a=item.rate_a or med.rate_a or 0.0,
            rate_b=item.rate_b or med.rate_b or 0.0,
            strip_conversion_factor=item.strip_conversion_factor or med.strip_conversion_factor or 1,
            discount_pct=item.discount_pct,
            hsn_id=med.hsn_id,
        ))
    db.flush(); db.refresh(purchase)
    _recompute_purchase_totals(purchase, db)

    if is_confirmed:
        purchase_store_id = purchase.store_id or resolve_store_id(
            db, current_user, None, require_purchase_store=True,
        )
        purchase.store_id = purchase_store_id
        for item in purchase.items:
            inv = _apply_purchase_item_to_inventory(
                db, item, purchase, current_user, purchase_store_id,
                ledger_notes=f"Edited purchase {purchase.purchase_number}: {reason}",
            )
            item.inventory_id = inv.id
        purchase.edited_by = current_user.id
        purchase.edited_at = datetime.now()
        purchase.edit_reason = reason
        db.commit(); db.refresh(purchase)
        _audit(
            db, current_user, "edit_purchase", "pharmacy_purchase", purchase.id,
            f"Edited confirmed purchase {purchase.purchase_number}: {reason}",
        )
        return _shape_purchase(purchase, db)

    db.commit(); db.refresh(purchase)
    _audit(db, current_user, "edit_purchase", "pharmacy_purchase", purchase.id,
           f"Edited draft purchase {purchase.purchase_number}")
    return _shape_purchase(purchase, db)


@router.post("/purchases/{pid}/confirm", response_model=PurchaseOut)
def confirm_purchase(
    pid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "confirm_purchase")),
):
    """Commit a draft purchase to inventory.

    For each item: create a `pharmacy_inventory` batch row (or merge into an
    existing same-batch+same-medicine row), then write a `pharmacy_stock_ledger`
    entry of `txn_type='purchase'`. Sets purchase status='confirmed' and
    propagates each item's MRP and P-Rate back to the medicine master.
    """
    purchase = db.query(PharmacyPurchase).filter(
        PharmacyPurchase.id == pid,
        PharmacyPurchase.hospital_id == current_user.hospital_id,
    ).first()
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    if purchase.status != "draft":
        raise HTTPException(status_code=400, detail=f"Purchase already {purchase.status}")
    if not purchase.items:
        raise HTTPException(status_code=400, detail="Cannot confirm an empty purchase")

    purchase_store_id = purchase.store_id or resolve_store_id(
        db, current_user, None, require_purchase_store=True,
    )
    purchase.store_id = purchase_store_id

    _recompute_purchase_totals(purchase, db)  # safety re-calc

    for item in purchase.items:
        inv = _apply_purchase_item_to_inventory(
            db, item, purchase, current_user, purchase_store_id,
            ledger_notes=f"Confirmed purchase {purchase.purchase_number}",
        )
        item.inventory_id = inv.id

    purchase.status = "confirmed"
    purchase.confirmed_by = current_user.id
    purchase.confirmed_at = datetime.now()
    db.commit(); db.refresh(purchase)
    _audit(db, current_user, "confirm_purchase", "pharmacy_purchase", purchase.id,
           f"Confirmed purchase {purchase.purchase_number} — {len(purchase.items)} batches into stock")
    return _shape_purchase(purchase, db)


class RevokePurchaseIn(BaseModel):
    reason: str = Field(..., min_length=2, max_length=500)


class RevokeItemResult(BaseModel):
    medicine_id: int
    medicine_name: Optional[str] = None
    batch_number: str
    received_qty: float        # paid + free originally received from this purchase line
    sold_qty: float            # already sold / dispensed (cannot reverse)
    reversed_qty: float        # what we just took back from stock


class RevokePurchaseResult(BaseModel):
    id: int
    purchase_number: str
    status: str
    fully_reversed: bool
    items: List[RevokeItemResult]


@router.post("/purchases/{pid}/revoke", response_model=RevokePurchaseResult)
def revoke_purchase(
    pid: int,
    data: RevokePurchaseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "revoke_purchase")),
):
    """Proportional revoke of a confirmed purchase.

    For each item we reverse only the un-sold portion:
      received = item.quantity + item.free_quantity
      sold = sum of |qty_delta| for ledger entries of type sale / rx_dispense
             that reference this purchase's inventory batch
      reversed = max(0, received - sold)

    If `reversed == 0` for every item the call fails — nothing to take back.
    Otherwise stock is decremented (clamped at 0), the batch is deactivated
    if it hits zero, a reverse ledger entry is written per item, and
    purchase.status becomes `revoked` (nothing sold) or `revoked_partial`.

    If this purchase's entry_date was the master's `last_purchase_date` for a
    given medicine, that medicine's mrp / purchase_rate are rolled back to the
    next-most-recent confirmed (non-revoked) purchase's values.
    """
    purchase = db.query(PharmacyPurchase).filter(
        PharmacyPurchase.id == pid,
        PharmacyPurchase.hospital_id == current_user.hospital_id,
    ).first()
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    if purchase.status != "confirmed":
        raise HTTPException(status_code=400, detail=f"Cannot revoke a {purchase.status} purchase")
    if not purchase.items:
        raise HTTPException(status_code=400, detail="Purchase has no items")

    results: List[RevokeItemResult] = []
    any_sold = False
    any_reversed = False

    for item in purchase.items:
        received = float((item.quantity or 0) + (item.free_quantity or 0))
        batch_id = item.inventory_id
        sold = 0.0
        if batch_id:
            sold_total = db.query(sa_func.coalesce(sa_func.sum(PharmacyStockLedger.qty_delta), 0)).filter(
                PharmacyStockLedger.batch_id == batch_id,
                PharmacyStockLedger.txn_type.in_(("sale", "rx_dispense")),
            ).scalar() or 0
            sold = abs(float(sold_total))
        reversible = max(0.0, received - sold)
        med = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
        med_name = med.name if med else None

        if sold > 0:
            any_sold = True

        if reversible > 0 and batch_id:
            batch = db.query(PharmacyInventory).filter(PharmacyInventory.id == batch_id).first()
            if batch:
                # Clamp at 0 in case prior adjustments already drove stock below
                # what we'd want to reverse — never push qty_in_stock negative.
                take = min(reversible, float(batch.quantity_in_stock or 0))
                batch.quantity_in_stock = float(batch.quantity_in_stock or 0) - take
                if (batch.quantity_in_stock or 0) <= 0:
                    batch.quantity_in_stock = 0
                    batch.is_active = False
                db.add(PharmacyStockLedger(
                    medicine_id=item.medicine_id, batch_id=batch.id,
                    txn_type="purchase_revoke", qty_delta=-take,
                    reference_type="purchase", reference_id=purchase.id,
                    performed_by=current_user.id,
                    hospital_id=current_user.hospital_id,
                    notes=f"Revoke purchase {purchase.purchase_number}: {data.reason}",
                ))
                if take > 0:
                    any_reversed = True
                reversible = take  # actual reversed

        results.append(RevokeItemResult(
            medicine_id=item.medicine_id, medicine_name=med_name,
            batch_number=item.batch_number,
            received_qty=received, sold_qty=sold, reversed_qty=reversible,
        ))

    if not any_reversed:
        raise HTTPException(
            status_code=400,
            detail=(
                "Nothing to revoke — every item on this purchase has either "
                "already been fully sold/dispensed or its batch is empty."
            ),
        )

    # Roll back the medicine master price if this purchase was the latest source.
    # For each medicine touched, find the most recent OTHER confirmed purchase
    # and reapply its rates; if none exists, clear last_purchase_date.
    touched_med_ids = {item.medicine_id for item in purchase.items}
    for mid in touched_med_ids:
        med = db.query(Medicine).filter(Medicine.id == mid).first()
        if not med:
            continue
        if med.last_purchase_date and med.last_purchase_date == purchase.entry_date:
            prev = (
                db.query(PharmacyPurchase, PharmacyPurchaseItem)
                .join(PharmacyPurchaseItem, PharmacyPurchaseItem.purchase_id == PharmacyPurchase.id)
                .filter(
                    PharmacyPurchaseItem.medicine_id == mid,
                    PharmacyPurchase.hospital_id == current_user.hospital_id,
                    PharmacyPurchase.status == "confirmed",
                    PharmacyPurchase.id != purchase.id,
                )
                .order_by(PharmacyPurchase.entry_date.desc(), PharmacyPurchase.id.desc())
                .first()
            )
            if prev:
                _, prev_item = prev
                if prev_item.purchase_rate:
                    med.purchase_rate = prev_item.purchase_rate
                if prev_item.mrp:
                    med.mrp = prev_item.mrp
                med.last_purchase_date = prev[0].entry_date
            else:
                med.last_purchase_date = None

    purchase.status = "revoked_partial" if any_sold else "revoked"
    purchase.revoked_by = current_user.id
    purchase.revoked_at = datetime.now()
    purchase.revoke_reason = data.reason

    db.commit()
    db.refresh(purchase)
    _audit(
        db, current_user, "revoke_purchase", "pharmacy_purchase", purchase.id,
        f"Revoked purchase {purchase.purchase_number} "
        f"({'partial' if any_sold else 'full'}): {data.reason}",
    )
    return RevokePurchaseResult(
        id=purchase.id, purchase_number=purchase.purchase_number,
        status=purchase.status, fully_reversed=not any_sold, items=results,
    )


@router.get("/purchases", response_model=List[PurchaseOut])
def list_purchases(
    status: Optional[str] = None,
    supplier_id: Optional[int] = None,
    store_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_purchases")),
):
    q = db.query(PharmacyPurchase).filter(PharmacyPurchase.hospital_id == current_user.hospital_id)
    if store_id is not None:
        sid = resolve_store_id(db, current_user, store_id)
        q = q.filter(PharmacyPurchase.store_id == sid)
    if status:
        q = q.filter(PharmacyPurchase.status == status)
    if supplier_id:
        q = q.filter(PharmacyPurchase.supplier_id == supplier_id)
    if date_from:
        q = q.filter(PharmacyPurchase.entry_date >= date_from)
    if date_to:
        q = q.filter(PharmacyPurchase.entry_date <= date_to)
    rows = q.order_by(PharmacyPurchase.entry_date.desc(), PharmacyPurchase.id.desc()).limit(limit).all()
    return [_shape_purchase(p, db) for p in rows]


@router.get("/purchases/{pid}", response_model=PurchaseOut)
def get_purchase(
    pid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_purchases")),
):
    p = db.query(PharmacyPurchase).filter(
        PharmacyPurchase.id == pid,
        PharmacyPurchase.hospital_id == current_user.hospital_id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return _shape_purchase(p, db)


# ============================================================================
# POS Sales (Section F)
# ============================================================================

class SaleItemIn(BaseModel):
    medicine_id: int
    qty_tabs: float = 0.0
    qty_strips: float = 0.0
    # Legacy single-unit payload (still accepted for older clients)
    quantity: Optional[float] = None
    qty_unit: Optional[str] = Field(None, pattern="^(tablet|strip)$")
    free_quantity: float = 0.0
    batch_id: Optional[int] = None
    rate: Optional[float] = None    # optional override: strip rate (MRP-equivalent)
    rate_tier: str = Field("A", pattern="^[AB]$")
    discount_pct: float = 0.0
    barcode_scanned: bool = False

    @field_validator("rate", "discount_pct", mode="before")
    @classmethod
    def _round_sale_money(cls, v):
        if v is None or v == "":
            return None if v is None else 0.0
        return round_money(v)


class SaleItemOut(BaseModel):
    id: int
    medicine_id: int
    medicine_name: Optional[str] = None
    batch_id: int
    batch_number: Optional[str] = None
    quantity: float
    free_quantity: float
    sale_qty: Optional[float] = None
    sale_qty_unit: Optional[str] = None
    sale_qty_tabs: Optional[float] = None
    sale_qty_strips: Optional[float] = None
    qty_display: Optional[str] = None
    rate: float
    rate_tier: str
    discount_pct: float
    tax_pct: float
    line_total: float
    barcode_scanned: bool

    class Config: from_attributes = True


class SaleIn(BaseModel):
    payment_type: str = Field("cash", pattern="^(cash|credit)$")
    store_id: Optional[int] = None
    tax_mode: str = Field("exclusive", pattern="^(exclusive|inclusive)$")
    billing_mode: str = Field(
        "cash_at_pharmacy",
        pattern="^(inpatient_bill|cash_at_pharmacy)$",
        description="inpatient_bill: defer to admission bill; cash_at_pharmacy: collect now",
    )
    patient_phone: Optional[str] = None
    patient_ip_id: Optional[str] = None
    patient_name: Optional[str] = None
    patient_address: Optional[str] = None
    doctor_number: Optional[str] = None
    doctor_name: Optional[str] = None
    bill_discount_amount: float = 0.0
    items: List[SaleItemIn] = Field(..., min_length=1)

    @field_validator("bill_discount_amount", mode="before")
    @classmethod
    def _round_bill_discount(cls, v):
        if v is None or v == "":
            return 0.0
        return round_money(v)


class SaleEditIn(SaleIn):
    reason: str = Field(..., min_length=2, max_length=500)


class SaleOut(BaseModel):
    id: int
    sale_number: str
    sale_date: datetime
    payment_type: str
    patient_phone: Optional[str] = None
    patient_ip_id: Optional[str] = None
    patient_name: Optional[str] = None
    patient_address: Optional[str] = None
    doctor_number: Optional[str] = None
    doctor_name: Optional[str] = None
    subtotal: float
    discount_total: float
    tax_total: float
    grand_total: float
    tax_mode: str = "exclusive"
    status: str
    billing_mode: str = "cash_at_pharmacy"
    admission_id: Optional[int] = None
    inpatient_bill_id: Optional[int] = None
    items: List[SaleItemOut] = Field(default_factory=list)
    created_at: datetime

    class Config: from_attributes = True


def _parse_sale_item_qty(line: SaleItemIn, med: Medicine) -> tuple[float, float]:
    """Normalize POS line to (qty_tabs, qty_strips)."""
    tabs = float(line.qty_tabs or 0)
    strips = float(line.qty_strips or 0)
    if tabs > 0 or strips > 0:
        return tabs, strips
    # Legacy: single quantity + unit
    if line.quantity is not None and float(line.quantity) > 0:
        qty = float(line.quantity)
        if line.qty_unit == "strip":
            return 0.0, qty
        if line.qty_unit == "tablet":
            return qty, 0.0
        # Default unknown legacy to tablets
        return qty, 0.0
    return tabs, strips


def _next_sale_number(db: Session, hospital_id: int) -> str:
    today = date.today()
    prefix = f"SALE-{today.strftime('%y%m%d')}-"
    last = db.query(PharmacySale).filter(
        PharmacySale.sale_number.like(prefix + "%"),
        PharmacySale.hospital_id == hospital_id,
    ).order_by(PharmacySale.sale_number.desc()).first()
    seq = 1
    if last:
        try:
            seq = int(last.sale_number.rsplit("-", 1)[-1]) + 1
        except Exception:
            seq = 1
    return f"{prefix}{seq:04d}"


def _flush_with_number_retry(db: Session, target, *, regen, set_attr: str, retries: int = 3):
    """Flush `target` and, on a unique-constraint violation against `set_attr`,
    re-mint the number via `regen()` and try again up to `retries` times.

    Used for sale_number / purchase_number which are globally unique on the
    column but minted by a "MAX seq + 1" lookup that two concurrent inserts
    can race against.
    """
    last_err = None
    for _ in range(retries):
        try:
            db.flush()
            return
        except IntegrityError as e:
            last_err = e
            db.rollback()
            # IntegrityError invalidates `target` from the session; re-attach
            # with a freshly minted number and try again.
            setattr(target, set_attr, regen())
            db.add(target)
    raise last_err  # propagated, caller decides how to surface


def _pick_fifo_batches(db: Session, *, medicine_id: int, qty_needed: float, hospital_id: int, store_id: Optional[int] = None):
    """Return [(batch_row, qty_to_take), ...] picking nearest-expiry first
    (First-Expiry-First-Out). Ties on expiry break on insertion order, so
    older receipts of the same expiry date still flow out first. Sentinel
    expiry dates (no-expiry stock) sort to the back automatically.

    Function name keeps the historical _pick_fifo_batches for callsite
    compatibility but the policy is FEFO as of Pharmacy P0 #2.

    Raises 400 if total available across all active batches < qty_needed.
    """
    # P3.2: lock the candidate inventory rows for the duration of this tx so
    # two concurrent sales can't both read the same quantity and oversell. No-op
    # on SQLite (relies on BEGIN IMMEDIATE serialization); real effect on
    # Postgres/MySQL deployments.
    avail = db.query(PharmacyInventory).filter(
        PharmacyInventory.medicine_id == medicine_id,
        PharmacyInventory.hospital_id == hospital_id,
        PharmacyInventory.is_active == True,  # noqa: E712
        PharmacyInventory.quantity_in_stock > 0,
    )
    if store_id is not None:
        avail = avail.filter(PharmacyInventory.store_id == store_id)
    avail = avail.order_by(
        PharmacyInventory.expiry_date.asc(),
        PharmacyInventory.id.asc(),
    ).with_for_update().all()
    total = sum((b.quantity_in_stock or 0) for b in avail)
    if total < qty_needed:
        raise HTTPException(status_code=400,
                            detail=f"Insufficient stock for medicine {medicine_id}: need {qty_needed}, have {total}")
    picks = []
    remaining = qty_needed
    for b in avail:
        if remaining <= 0:
            break
        take = min(remaining, b.quantity_in_stock or 0)
        picks.append((b, take))
        remaining -= take
    return picks


def _shape_sale(s: PharmacySale, db: Session) -> SaleOut:
    items_out: List[SaleItemOut] = []
    for it in s.items:
        med = db.query(Medicine).filter(Medicine.id == it.medicine_id).first()
        batch = db.query(PharmacyInventory).filter(PharmacyInventory.id == it.batch_id).first()
        items_out.append(SaleItemOut(
            id=it.id, medicine_id=it.medicine_id,
            medicine_name=med.name if med else None,
            batch_id=it.batch_id, batch_number=batch.batch_number if batch else None,
            quantity=it.quantity, free_quantity=it.free_quantity or 0.0,
            sale_qty=it.sale_qty, sale_qty_unit=it.sale_qty_unit,
            sale_qty_tabs=it.sale_qty_tabs, sale_qty_strips=it.sale_qty_strips,
            qty_display=format_sale_qty_display(
                quantity=it.quantity or 0,
                sale_qty_tabs=it.sale_qty_tabs,
                sale_qty_strips=it.sale_qty_strips,
                sale_qty=it.sale_qty,
                sale_qty_unit=it.sale_qty_unit,
            ),
            rate=it.rate, rate_tier=it.rate_tier or "A",
            discount_pct=it.discount_pct or 0.0, tax_pct=it.tax_pct or 0.0,
            line_total=it.line_total or 0.0, barcode_scanned=bool(it.barcode_scanned),
        ))
    return SaleOut(
        id=s.id, sale_number=s.sale_number, sale_date=s.sale_date,
        payment_type=s.payment_type, patient_phone=s.patient_phone,
        patient_ip_id=s.patient_ip_id, patient_name=s.patient_name,
        patient_address=s.patient_address, doctor_number=s.doctor_number,
        doctor_name=s.doctor_name,
        subtotal=s.subtotal or 0.0, discount_total=s.discount_total or 0.0,
        tax_total=s.tax_total or 0.0, grand_total=s.grand_total or 0.0,
        tax_mode=getattr(s, "tax_mode", None) or "exclusive",
        status=s.status, items=items_out, created_at=s.created_at,
        billing_mode=getattr(s, "billing_mode", None) or "cash_at_pharmacy",
        admission_id=getattr(s, "admission_id", None),
        inpatient_bill_id=getattr(s, "inpatient_bill_id", None),
    )


def _resolve_sale_admission(
    db: Session,
    current_user: User,
    patient_ip_id: Optional[str],
    billing_mode: str,
) -> Optional[int]:
    """Validate patient/admission for POS sale; return admission_id or None."""
    if not patient_ip_id:
        if billing_mode == "inpatient_bill":
            raise HTTPException(
                status_code=400,
                detail="Select an admitted patient to charge medicines to the inpatient bill.",
            )
        return None
    from app.models.patient import Patient as _IPPatient
    from app.models.inpatient import Admission as _IPAdmission
    pat = db.query(_IPPatient).filter(
        _IPPatient.patient_id == patient_ip_id,
        _IPPatient.hospital_id == current_user.hospital_id,
    ).first()
    if not pat:
        raise HTTPException(
            status_code=400,
            detail=f"patient_ip_id {patient_ip_id} not found in this hospital",
        )
    active = db.query(_IPAdmission).filter(
        _IPAdmission.patient_id == pat.id,
        _IPAdmission.status == "admitted",
    ).first()
    if billing_mode == "inpatient_bill":
        if not active:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Patient {patient_ip_id} has no active admission. "
                    "Use cash-at-pharmacy or leave patient blank for walk-in sales."
                ),
            )
        return active.id
    if not active:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Patient {patient_ip_id} has no active admission. "
                "Leave patient_ip_id blank for OP / walk-in sales."
            ),
        )
    return None


def _restore_sale_items_stock(
    db: Session,
    sale: PharmacySale,
    current_user: User,
    reason: str,
    *,
    reference_type: str = "sale_edit",
) -> None:
    for it in list(sale.items):
        batch = db.query(PharmacyInventory).filter(
            PharmacyInventory.id == it.batch_id,
        ).with_for_update().first()
        if not batch:
            continue
        restore = (it.quantity or 0) + (it.free_quantity or 0)
        batch.quantity_in_stock = (batch.quantity_in_stock or 0) + restore
        db.add(PharmacyStockLedger(
            medicine_id=it.medicine_id, batch_id=batch.id, txn_type="return_in",
            qty_delta=restore, reference_type=reference_type, reference_id=sale.id,
            performed_by=current_user.id, store_id=sale.store_id,
            hospital_id=current_user.hospital_id,
            notes=f"Edit sale {sale.sale_number}: {reason}",
        ))


def _process_sale_lines(
    db: Session,
    sale: PharmacySale,
    lines: List[SaleItemIn],
    current_user: User,
    sale_store_id: int,
    tax_mode: str,
    tax_on_free: bool,
    bill_discount_amount: float,
    *,
    ledger_note: str,
) -> tuple[float, float, float, float]:
    subtotal = 0.0
    disc_total = 0.0
    tax_total = 0.0
    grand = 0.0

    for line in lines:
        med = db.query(Medicine).filter(
            Medicine.id == line.medicine_id,
            Medicine.hospital_id == current_user.hospital_id,
            Medicine.is_active == True,  # noqa: E712
        ).first()
        if not med:
            raise HTTPException(status_code=400, detail=f"Invalid medicine_id {line.medicine_id}")

        qty_tabs, qty_strips = _parse_sale_item_qty(line, med)
        if qty_tabs <= 0 and qty_strips <= 0:
            raise HTTPException(status_code=400, detail=f"Enter tab or strip qty for {med.name}")

        explicit_batch = None
        if line.batch_id:
            explicit_batch = db.query(PharmacyInventory).filter(
                PharmacyInventory.id == line.batch_id,
                PharmacyInventory.hospital_id == current_user.hospital_id,
                PharmacyInventory.is_active == True,  # noqa: E712
            ).with_for_update().first()
            if not explicit_batch:
                raise HTTPException(status_code=400, detail=f"Invalid batch_id {line.batch_id}")
            if explicit_batch.store_id != sale_store_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Batch {explicit_batch.batch_number} belongs to a different store",
                )
            if explicit_batch.medicine_id != med.id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Batch {explicit_batch.batch_number} is not for {med.name}",
                )

        base_qty_needed, rate_per_tab, strip_rate, qty_tabs, qty_strips = resolve_pos_sale_line(
            med,
            qty_tabs=qty_tabs,
            qty_strips=qty_strips,
            tier=line.rate_tier,
            override_strip_rate=line.rate,
            batch=explicit_batch,
        )
        if rate_per_tab <= 0:
            raise HTTPException(status_code=400,
                                detail=f"No MRP / rate set on medicine {med.name}")

        line_disc = float(line.discount_pct or 0)
        med_disc = float(med.item_discount_pct or 0)
        disc = line_disc + med_disc
        if disc > 100.0:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Discount exceeds 100% on {med.name}: "
                    f"line {line_disc}% + medicine default {med_disc}% = {disc}%. "
                    "Lower the line discount or clear the medicine's default."
                ),
            )
        hsn_row = db.query(PharmacyHSN).filter(PharmacyHSN.id == med.hsn_id).first() if med.hsn_id else None
        sgst_snap = (hsn_row.sgst_pct or 0) if hsn_row else 0.0
        cgst_snap = (hsn_row.cgst_pct or 0) if hsn_row else 0.0
        igst_snap = (hsn_row.igst_pct or (sgst_snap + cgst_snap)) if hsn_row else 0.0
        tax_pct = _hsn_total_tax_pct(hsn_row)

        picks = []
        qty_needed = base_qty_needed
        if explicit_batch is not None:
            if (explicit_batch.quantity_in_stock or 0) < qty_needed:
                raise HTTPException(status_code=400,
                                    detail=f"Batch {explicit_batch.batch_number} has only {explicit_batch.quantity_in_stock}, need {qty_needed}")
            picks.append((explicit_batch, qty_needed))
        else:
            picks = _pick_fifo_batches(
                db, medicine_id=med.id, qty_needed=qty_needed,
                hospital_id=current_user.hospital_id, store_id=sale_store_id,
            )

        free_total = float(line.free_quantity or 0)
        free_alloc = []
        if picks and free_total > 0:
            allocated = 0.0
            for i, (_b, take_q) in enumerate(picks):
                if i == len(picks) - 1:
                    portion = round(free_total - allocated, 2)
                else:
                    portion = round((take_q / qty_needed) * free_total, 2) if qty_needed else 0.0
                    allocated += portion
                free_alloc.append(portion)
        else:
            free_alloc = [0.0] * len(picks)

        first_batch_row = True
        for (batch, take_qty), free_for_batch in zip(picks, free_alloc):
            if explicit_batch is not None:
                batch_tab_rate = rate_per_tab
            else:
                _, batch_tab_rate, _, _, _ = resolve_pos_sale_line(
                    med,
                    qty_tabs=take_qty,
                    qty_strips=0,
                    tier=line.rate_tier,
                    override_strip_rate=line.rate,
                    batch=batch,
                )
                if batch_tab_rate <= 0:
                    batch_tab_rate = rate_per_tab
            base = take_qty * batch_tab_rate
            base_after_disc = base * (1 - disc / 100.0)
            if tax_on_free and free_for_batch:
                base_after_disc += free_for_batch * batch_tab_rate * (1 - disc / 100.0)
            _taxable, tax_amt, line_total = compute_line_tax(
                base_after_disc, tax_pct, tax_mode=tax_mode or "exclusive",
            )

            item_row = PharmacySaleItem(
                sale_id=sale.id, medicine_id=med.id, batch_id=batch.id,
                quantity=take_qty, free_quantity=free_for_batch,
                sale_qty_tabs=qty_tabs if first_batch_row else None,
                sale_qty_strips=qty_strips if first_batch_row else None,
                rate=batch_tab_rate, rate_tier=line.rate_tier,
                discount_pct=disc, tax_pct=tax_pct,
                sgst_pct=sgst_snap, cgst_pct=cgst_snap, igst_pct=igst_snap,
                line_total=line_total, barcode_scanned=line.barcode_scanned,
            )
            db.add(item_row)
            first_batch_row = False

            batch.quantity_in_stock = (batch.quantity_in_stock or 0) - take_qty - free_for_batch
            db.add(PharmacyStockLedger(
                medicine_id=med.id, batch_id=batch.id, txn_type="sale",
                qty_delta=-(take_qty + free_for_batch),
                reference_type="sale", reference_id=sale.id,
                performed_by=current_user.id, store_id=sale_store_id,
                hospital_id=current_user.hospital_id,
                notes=ledger_note,
            ))

            subtotal += base
            disc_total += base - base_after_disc
            tax_total += tax_amt
            grand += line_total

    bill_disc = round_money(min(float(bill_discount_amount or 0), grand))
    if bill_disc > 0:
        grand = round_money(grand - bill_disc)
        disc_total = round_money(disc_total + bill_disc)

    return subtotal, disc_total, tax_total, grand


@router.post("/sales", response_model=SaleOut, status_code=201)
def create_sale(
    data: SaleIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_sale")),
):
    """Create a POS sale.

    For each line: pick batch (FIFO if `batch_id` not specified), deduct
    `pharmacy_inventory.quantity_in_stock`, write a `pharmacy_stock_ledger`
    row of `txn_type='sale'`. Computes tax from each medicine's HSN code.

    A single requested line may span multiple batches when FIFO is used —
    each batch becomes its own `PharmacySaleItem` row so the inventory link
    is precise.
    """
    # P3.4: validate IP link when provided. patient_ip_id stores the Patient
    # UUID string (the historical column name is misleading); we cross-check
    # the patient is in this hospital and currently admitted.
    # P3.9: per-hospital flag for taxing free items. Read once up front so we
    # don't re-fetch the Hospital row per line.
    _hosp = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
    tax_on_free = bool(getattr(_hosp, "pharmacy_tax_on_free", False))

    billing_mode = data.billing_mode or "cash_at_pharmacy"
    ip_admission_id = _resolve_sale_admission(db, current_user, data.patient_ip_id, billing_mode)

    sale_store_id = resolve_store_id(db, current_user, data.store_id)

    sale = PharmacySale(
        sale_number=_next_sale_number(db, current_user.hospital_id),
        payment_type=data.payment_type,
        patient_phone=data.patient_phone, patient_ip_id=data.patient_ip_id,
        patient_name=data.patient_name, patient_address=data.patient_address,
        doctor_number=data.doctor_number, doctor_name=data.doctor_name,
        status="completed", created_by=current_user.id,
        store_id=sale_store_id,
        hospital_id=current_user.hospital_id,
        admission_id=ip_admission_id,
        billing_mode=billing_mode,
        tax_mode=data.tax_mode or "exclusive",
    )
    db.add(sale)
    # P3.3: two concurrent sales can compute the same MAX-seq and produce the
    # same sale_number. Retry-on-IntegrityError remints from the now-updated
    # MAX before any items have been attached to this sale.
    _flush_with_number_retry(
        db, sale,
        regen=lambda: _next_sale_number(db, current_user.hospital_id),
        set_attr="sale_number",
    )

    subtotal, disc_total, tax_total, grand = _process_sale_lines(
        db, sale, data.items, current_user, sale_store_id,
        data.tax_mode or "exclusive", tax_on_free,
        float(data.bill_discount_amount or 0),
        ledger_note=f"Sale {sale.sale_number}",
    )

    sale.subtotal = round(subtotal, 2)
    sale.discount_total = round(disc_total, 2)
    sale.tax_total = round(tax_total, 2)
    sale.grand_total = round(grand, 2)
    db.commit(); db.refresh(sale)
    _audit(db, current_user, "create_sale", "pharmacy_sale", sale.id,
           f"Created sale {sale.sale_number} (₹{sale.grand_total})")
    return _shape_sale(sale, db)


@router.put("/sales/{sid}", response_model=SaleOut)
def edit_sale(
    sid: int, data: SaleEditIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "edit_sale")),
):
    """Edit a completed sale: restore stock, replace lines, re-deduct inventory."""
    sale = db.query(PharmacySale).filter(
        PharmacySale.id == sid,
        PharmacySale.hospital_id == current_user.hospital_id,
    ).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    if sale.status != "completed":
        raise HTTPException(status_code=400, detail=f"Cannot edit a {sale.status} sale")

    reason = (data.reason or "").strip()
    if len(reason) < 2:
        raise HTTPException(status_code=400, detail="Reason is required to edit a sale")
    if not data.items:
        raise HTTPException(status_code=400, detail="Cannot leave sale empty")

    sale_store_id = sale.store_id or resolve_store_id(db, current_user, data.store_id)
    if data.store_id is not None and data.store_id != sale_store_id:
        raise HTTPException(status_code=400, detail="Cannot change store on an existing sale")

    _hosp = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
    tax_on_free = bool(getattr(_hosp, "pharmacy_tax_on_free", False))
    billing_mode = data.billing_mode or "cash_at_pharmacy"
    ip_admission_id = _resolve_sale_admission(db, current_user, data.patient_ip_id, billing_mode)

    bill_reversal = {}
    if (getattr(sale, "billing_mode", None) or "cash_at_pharmacy") == "inpatient_bill":
        from app.services.pharmacy_reversal import reverse_inpatient_pos_sale_bill
        bill_reversal = reverse_inpatient_pos_sale_bill(
            db, sale, user_id=current_user.id, reason=reason,
        )

    _restore_sale_items_stock(db, sale, current_user, reason)
    for old in list(sale.items):
        db.delete(old)
    db.flush()

    sale.payment_type = data.payment_type
    sale.patient_phone = data.patient_phone
    sale.patient_ip_id = data.patient_ip_id
    sale.patient_name = data.patient_name
    sale.patient_address = data.patient_address
    sale.doctor_number = data.doctor_number
    sale.doctor_name = data.doctor_name
    sale.tax_mode = data.tax_mode or "exclusive"
    sale.billing_mode = billing_mode
    sale.admission_id = ip_admission_id

    subtotal, disc_total, tax_total, grand = _process_sale_lines(
        db, sale, data.items, current_user, sale_store_id,
        data.tax_mode or "exclusive", tax_on_free,
        float(data.bill_discount_amount or 0),
        ledger_note=f"Edited sale {sale.sale_number}: {reason}",
    )

    sale.subtotal = round(subtotal, 2)
    sale.discount_total = round(disc_total, 2)
    sale.tax_total = round(tax_total, 2)
    sale.grand_total = round(grand, 2)
    db.commit(); db.refresh(sale)
    _audit(
        db, current_user, "edit_sale", "pharmacy_sale", sale.id,
        f"Edited sale {sale.sale_number}: {reason}",
        details=bill_reversal if bill_reversal else None,
    )
    return _shape_sale(sale, db)


@router.get("/sales", response_model=List[SaleOut])
def list_sales(
    status: Optional[str] = None,
    payment_type: Optional[str] = None,
    store_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_sales")),
):
    q = db.query(PharmacySale).filter(PharmacySale.hospital_id == current_user.hospital_id)
    if store_id is not None:
        sid = resolve_store_id(db, current_user, store_id)
        q = q.filter(PharmacySale.store_id == sid)
    if status:
        q = q.filter(PharmacySale.status == status)
    if payment_type:
        q = q.filter(PharmacySale.payment_type == payment_type)
    if date_from:
        q = q.filter(PharmacySale.sale_date >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(PharmacySale.sale_date <= datetime.combine(date_to, datetime.max.time()))
    if search:
        like = f"%{search.lower()}%"
        q = q.filter(or_(
            PharmacySale.sale_number.ilike(like),
            PharmacySale.patient_name.ilike(like),
            PharmacySale.patient_phone.ilike(like),
            PharmacySale.doctor_name.ilike(like),
        ))
    return [_shape_sale(s, db) for s in q.order_by(PharmacySale.sale_date.desc()).limit(limit).all()]


@router.get("/sales/{sid}", response_model=SaleOut)
def get_sale(
    sid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_sales")),
):
    s = db.query(PharmacySale).filter(
        PharmacySale.id == sid,
        PharmacySale.hospital_id == current_user.hospital_id,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Sale not found")
    return _shape_sale(s, db)


class VoidIn(BaseModel):
    reason: str = Field(..., min_length=2, max_length=500)


@router.post("/sales/{sid}/void", response_model=SaleOut)
def void_sale(
    sid: int, data: VoidIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "void_sale")),
):
    """Reverse a completed sale: restore qty to each batch + write reverse ledger entries.

    When the sale was deferred to an inpatient bill (`billing_mode=inpatient_bill`)
    and already included on an admission bill, bill lines are reversed per the
    hybrid policy in `app/services/pharmacy_reversal.py` (in-place on draft bills,
    credit-note on locked/final bills).
    """
    sale = db.query(PharmacySale).filter(
        PharmacySale.id == sid,
        PharmacySale.hospital_id == current_user.hospital_id,
    ).first()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    if sale.status != "completed":
        raise HTTPException(status_code=400, detail=f"Sale already {sale.status}")

    # P3.5: void window check.
    hosp = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
    window = int(getattr(hosp, "pharmacy_void_window_days", 0) or 0)
    if window > 0 and sale.sale_date:
        age = (datetime.now() - sale.sale_date).days
        if age > window:
            roles = set(getattr(current_user, "role_names", []) or [])
            has_bypass = (
                "super_admin" in roles or "hospital_admin" in roles
                or _user_has_permission(db, current_user, Modules.PHARMACY, "void_sale_legacy")
            )
            if not has_bypass:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Sale {sale.sale_number} is {age} days old; void window is "
                        f"{window} days. Ask an admin with `void_sale_legacy` to do it."
                    ),
                )

    for it in sale.items:
        batch = db.query(PharmacyInventory).filter(PharmacyInventory.id == it.batch_id).first()
        if not batch:
            continue
        restore = (it.quantity or 0) + (it.free_quantity or 0)
        batch.quantity_in_stock = (batch.quantity_in_stock or 0) + restore
        db.add(PharmacyStockLedger(
            medicine_id=it.medicine_id, batch_id=batch.id, txn_type="return_in",
            qty_delta=restore, reference_type="sale_void", reference_id=sale.id,
            performed_by=current_user.id, hospital_id=current_user.hospital_id,
            notes=f"Void sale {sale.sale_number}: {data.reason}",
        ))

    bill_reversal = {}
    if (getattr(sale, "billing_mode", None) or "cash_at_pharmacy") == "inpatient_bill":
        from app.services.pharmacy_reversal import reverse_inpatient_pos_sale_bill
        bill_reversal = reverse_inpatient_pos_sale_bill(
            db, sale, user_id=current_user.id, reason=data.reason,
        )

    sale.status = "voided"
    sale.voided_by = current_user.id
    sale.voided_at = datetime.now()
    sale.void_reason = data.reason
    db.commit(); db.refresh(sale)

    ip_note = ""
    if sale.patient_ip_id:
        if (getattr(sale, "billing_mode", None) or "") == "inpatient_bill":
            ip_note = f" (IP bill linkage: admission {sale.admission_id})"
        else:
            ip_note = f" (IP linkage: {sale.patient_ip_id} — paid at counter, not on IP bill)"
    _audit(db, current_user, "void_sale", "pharmacy_sale", sale.id,
           f"Voided sale {sale.sale_number}: {data.reason}{ip_note}",
           details=bill_reversal if bill_reversal else None)
    return _shape_sale(sale, db)


# ============================================================================
# Rx-linked dispensing (Section G)
# ============================================================================

class PendingRxItemOut(BaseModel):
    item_id: int
    medicine_id: int
    medicine_name: Optional[str] = None
    quantity_prescribed: float
    quantity_dispensed: float
    quantity_remaining: float
    unit_price: float = 0.0
    strip_conversion_factor: int = 1
    is_unmapped: bool = False
    dosage: Optional[str] = None
    duration: Optional[str] = None
    status: str


class PendingRxOut(BaseModel):
    id: int
    prescription_number: str
    prescription_date: datetime
    status: str
    notes: Optional[str] = None
    admission_id: Optional[int] = None
    patient_name: Optional[str] = None
    items: List[PendingRxItemOut] = Field(default_factory=list)


@router.get("/prescriptions/pending", response_model=List[PendingRxOut])
def list_pending_prescriptions(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_dispense_queue")),
):
    """List prescriptions awaiting (full or partial) dispensing."""
    from app.models.patient import Patient

    rxs = db.query(Prescription).filter(
        Prescription.status.in_(["pending", "partial"]),
    ).order_by(Prescription.prescription_date.desc()).limit(limit).all()

    out = []
    for rx in rxs:
        patient = db.query(Patient).filter(Patient.id == rx.patient_id).first()
        items = []
        for it in rx.items:
            med = db.query(Medicine).filter(Medicine.id == it.medicine_id).first()
            rem = float((it.quantity_prescribed or 0) - (it.quantity_dispensed or 0))
            items.append(PendingRxItemOut(
                item_id=it.id, medicine_id=it.medicine_id,
                medicine_name=med.name if med else None,
                quantity_prescribed=float(it.quantity_prescribed or 0),
                quantity_dispensed=float(it.quantity_dispensed or 0),
                quantity_remaining=rem,
                unit_price=float(it.unit_price or 0),
                strip_conversion_factor=int(med.strip_conversion_factor or 1) if med else 1,
                is_unmapped=bool(med and is_free_text_medicine(med)),
                dosage=it.dosage, duration=it.duration, status=it.status or "pending",
            ))
        out.append(PendingRxOut(
            id=rx.id, prescription_number=rx.prescription_number,
            prescription_date=rx.prescription_date, status=rx.status,
            notes=rx.notes,
            admission_id=rx.admission_id,
            patient_name=(
                f"{patient.first_name} {patient.last_name}" if patient else None
            ),
            items=items,
        ))
    return out


class DispenseItemIn(BaseModel):
    item_id: int
    qty_tabs: float = 0.0
    qty_strips: float = 0.0
    quantity: Optional[float] = None  # legacy
    qty_unit: Optional[str] = Field(None, pattern="^(tablet|strip)$")
    batch_id: Optional[int] = None


class DispenseIn(BaseModel):
    items: List[DispenseItemIn] = Field(..., min_length=1)
    store_id: Optional[int] = None
    notes: Optional[str] = None
    billing_mode: str = Field(
        "inpatient_bill",
        pattern="^(inpatient_bill|cash_at_pharmacy)$",
        description="inpatient_bill: charge on admission bill; cash_at_pharmacy: collect payment now",
    )
    payment_type: str = Field("cash", pattern="^(cash|credit)$")


class DispenseLineOut(BaseModel):
    item_id: int
    medicine_id: int
    medicine_name: Optional[str] = None
    batch_id: int
    batch_number: Optional[str] = None
    quantity: float
    unit_price: float = 0.0
    line_total: float = 0.0


class DispenseResultOut(BaseModel):
    prescription_id: int
    prescription_number: str
    status: str
    billing_mode: str
    pharmacy_sale_id: Optional[int] = None
    pharmacy_sale_number: Optional[str] = None
    grand_total: Optional[float] = None
    lines: List[DispenseLineOut]


@router.post("/prescriptions/{rx_id}/dispense", response_model=DispenseResultOut)
def dispense_prescription(
    rx_id: int, data: DispenseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "dispense_rx")),
):
    """Dispense one or more prescription items.

    For each requested item: deduct from inventory (FIFO unless batch_id given),
    write a `rx_dispense` ledger entry per batch consumed, advance
    `PrescriptionItem.quantity_dispensed` and `status`. The prescription's
    overall status is set to `dispensed` when all items are fully dispensed,
    `partial` otherwise.
    """
    # P3.1: scope to caller's hospital via the linked Patient. Prescription has
    # no direct hospital_id column, but Patient does. Without this join a user
    # could dispense against another hospital's Rx id and silently decrement
    # their own stock.
    from app.models.patient import Patient as _PatientForRx
    rx = (
        db.query(Prescription)
        .join(_PatientForRx, _PatientForRx.id == Prescription.patient_id)
        .filter(
            Prescription.id == rx_id,
            _PatientForRx.hospital_id == current_user.hospital_id,
        )
        .first()
    )
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    if rx.status in ("dispensed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Prescription already {rx.status}")
    if data.billing_mode == "cash_at_pharmacy" and rx.pharmacy_sale_id:
        raise HTTPException(status_code=400, detail="Prescription already paid at pharmacy counter")

    dispense_store_id = resolve_store_id(db, current_user, data.store_id)
    rx.dispense_store_id = dispense_store_id

    lines_out: List[DispenseLineOut] = []
    for req in data.items:
        rxi = db.query(PrescriptionItem).filter(
            PrescriptionItem.id == req.item_id,
            PrescriptionItem.prescription_id == rx.id,
        ).first()
        if not rxi:
            raise HTTPException(status_code=400, detail=f"Item {req.item_id} not on Rx {rx.id}")

        med = db.query(Medicine).filter(Medicine.id == rxi.medicine_id).first()
        qty_tabs = float(req.qty_tabs or 0)
        qty_strips = float(req.qty_strips or 0)
        if qty_tabs <= 0 and qty_strips <= 0 and req.quantity:
            if req.qty_unit == "strip":
                qty_strips = float(req.quantity)
            else:
                qty_tabs = float(req.quantity)
        base_qty = combined_base_qty(qty_tabs, qty_strips, med) if med else qty_tabs + qty_strips
        if base_qty <= 0:
            raise HTTPException(status_code=400, detail=f"Item {rxi.id}: enter tab or strip qty")
        remaining = float((rxi.quantity_prescribed or 0) - (rxi.quantity_dispensed or 0))
        if base_qty > remaining:
            raise HTTPException(status_code=400,
                                detail=f"Item {rxi.id}: cannot dispense {base_qty:g} tab(s) — only {remaining:g} remaining")

        unit_price = float(rxi.unit_price or 0)
        if unit_price <= 0 and med:
            unit_price = medicine_sale_rate(med)
        if unit_price <= 0:
            med_name = med.name if med else f"item #{rxi.id}"
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No price set for {med_name}. "
                    "Map it under Pharmacy → Unmapped Medicines before dispensing."
                ),
            )
        rxi.unit_price = unit_price
        rxi.total_price = unit_price * float(rxi.quantity_prescribed or 0)

        if req.batch_id:
            batch = db.query(PharmacyInventory).filter(
                PharmacyInventory.id == req.batch_id,
                PharmacyInventory.hospital_id == current_user.hospital_id,
                PharmacyInventory.store_id == dispense_store_id,
                PharmacyInventory.is_active == True,  # noqa: E712
            ).with_for_update().first()
            if not batch:
                raise HTTPException(status_code=400, detail=f"Invalid batch_id {req.batch_id}")
            if (batch.quantity_in_stock or 0) < base_qty:
                raise HTTPException(status_code=400,
                                    detail=f"Batch {batch.batch_number} has only {batch.quantity_in_stock}")
            picks = [(batch, base_qty)]
        else:
            picks = _pick_fifo_batches(
                db, medicine_id=rxi.medicine_id, qty_needed=base_qty,
                hospital_id=current_user.hospital_id, store_id=dispense_store_id,
            )

        for batch, take in picks:
            batch.quantity_in_stock = (batch.quantity_in_stock or 0) - take
            db.add(PharmacyStockLedger(
                medicine_id=rxi.medicine_id, batch_id=batch.id, txn_type="rx_dispense",
                qty_delta=-take, reference_type="prescription", reference_id=rx.id,
                performed_by=current_user.id, store_id=dispense_store_id,
                hospital_id=current_user.hospital_id,
                notes=f"Dispensed Rx {rx.prescription_number} item #{rxi.id}",
            ))
            line_total = unit_price * take
            lines_out.append(DispenseLineOut(
                item_id=rxi.id, medicine_id=rxi.medicine_id,
                medicine_name=med.name if med else None,
                batch_id=batch.id, batch_number=batch.batch_number, quantity=take,
                unit_price=unit_price, line_total=line_total,
            ))

        rxi.quantity_dispensed = (rxi.quantity_dispensed or 0) + base_qty
        if rxi.quantity_dispensed >= (rxi.quantity_prescribed or 0):
            rxi.status = "dispensed"
        else:
            rxi.status = "partial"

    db.flush()
    all_items = db.query(PrescriptionItem).filter(PrescriptionItem.prescription_id == rx.id).all()
    rx.total_amount = sum(float(i.unit_price or 0) * float(i.quantity_prescribed or 0) for i in all_items)
    if all(i.status == "dispensed" for i in all_items):
        rx.status = "dispensed"
        rx.dispensed_by_id = current_user.id
        rx.dispensed_date = datetime.now()
    else:
        rx.status = "partial"

    sale_id = None
    sale_number = None
    grand_total = None
    if data.billing_mode == "cash_at_pharmacy" and lines_out:
        patient = db.query(_PatientForRx).filter(_PatientForRx.id == rx.patient_id).first()
        doctor = db.query(User).filter(User.id == rx.doctor_id).first()
        sale = PharmacySale(
            sale_number=_next_sale_number(db, current_user.hospital_id),
            payment_type=data.payment_type,
            patient_ip_id=patient.patient_id if patient else None,
            patient_name=(
                f"{patient.first_name} {patient.last_name}" if patient else None
            ),
            doctor_name=(
                f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else None
            ),
            status="completed",
            created_by=current_user.id,
            hospital_id=current_user.hospital_id,
        )
        db.add(sale)
        _flush_with_number_retry(
            db, sale,
            regen=lambda: _next_sale_number(db, current_user.hospital_id),
            set_attr="sale_number",
        )
        subtotal = 0.0
        tax_total = 0.0
        for line in lines_out:
            med = db.query(Medicine).filter(Medicine.id == line.medicine_id).first()
            hsn_row = (
                db.query(PharmacyHSN).filter(PharmacyHSN.id == med.hsn_id).first()
                if med and med.hsn_id else None
            )
            tax_pct = _hsn_total_tax_pct(hsn_row)
            line_total = line.line_total
            tax_amt = line_total * tax_pct / 100.0
            subtotal += line_total
            tax_total += tax_amt
            db.add(PharmacySaleItem(
                sale_id=sale.id,
                medicine_id=line.medicine_id,
                batch_id=line.batch_id,
                quantity=line.quantity,
                rate=line.unit_price,
                rate_tier="A",
                tax_pct=tax_pct,
                sgst_pct=(hsn_row.sgst_pct or 0) if hsn_row else 0.0,
                cgst_pct=(hsn_row.cgst_pct or 0) if hsn_row else 0.0,
                igst_pct=(hsn_row.igst_pct or 0) if hsn_row else 0.0,
                line_total=line_total + tax_amt,
            ))
        sale.subtotal = subtotal
        sale.tax_total = tax_total
        sale.discount_total = 0.0
        sale.grand_total = subtotal + tax_total
        rx.pharmacy_sale_id = sale.id
        sale_id = sale.id
        sale_number = sale.sale_number
        grand_total = sale.grand_total

    db.commit()
    db.refresh(rx)
    _audit(
        db, current_user, "dispense_rx", "prescription", rx.id,
        f"Dispensed Rx {rx.prescription_number} ({len(lines_out)} batch lines, {data.billing_mode})",
        details={"notes": data.notes, "billing_mode": data.billing_mode} if data.notes else {"billing_mode": data.billing_mode},
    )
    return DispenseResultOut(
        prescription_id=rx.id, prescription_number=rx.prescription_number,
        status=rx.status, billing_mode=data.billing_mode,
        pharmacy_sale_id=sale_id, pharmacy_sale_number=sale_number,
        grand_total=grand_total, lines=lines_out,
    )


# ----------------------------------------------------------------------------
# Rx cancellation (Pharmacy P0 #1)
# ----------------------------------------------------------------------------

class CancelRxIn(BaseModel):
    reason: str = Field(..., min_length=2, max_length=500)


class CancelRxOut(BaseModel):
    prescription_id: int
    prescription_number: str
    status: str
    stock_ledger_rows_written: int
    parent_bill_id: Optional[int] = None
    bill_items_removed: int = 0
    credit_note_id: Optional[int] = None
    credit_note_number: Optional[str] = None
    reason: str


@router.post("/prescriptions/{rx_id}/cancel", response_model=CancelRxOut)
def cancel_prescription_route(
    rx_id: int,
    data: CancelRxIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "cancel_rx")),
):
    """Cancel a Prescription and reverse its side effects.

    Reverses any dispensed stock (writes `rx_cancel` ledger rows back to the
    original batches). If the Rx had already been included on an inpatient
    bill, the bill is handled per the hybrid policy in
    `app/services/pharmacy_reversal.py`:

      * Unlocked parent bill (draft, no payments, not "final" subtype) → bill
        items removed in place, parent totals decremented.
      * Locked parent bill → a credit-note Bill is emitted with negative
        line items; the original bill is left untouched.

    Always idempotency-safe in one direction only: a second cancel call on
    an already-cancelled Rx is rejected with 400.
    """
    from app.services.pharmacy_reversal import cancel_prescription
    summary = cancel_prescription(db, rx_id=rx_id, user=current_user, reason=data.reason)
    db.commit()
    return CancelRxOut(**summary)


# ============================================================================
# Reports & dashboard (Section H)
# ============================================================================

class DashboardSummaryOut(BaseModel):
    today_sales_total: float
    today_sales_count: int
    today_purchases_total: float
    today_purchases_count: int
    low_stock_count: int
    pending_rx_count: int
    # Pharmacy P0 #2 — number of batches with stock > 0 whose expiry falls
    # within the next 90 days (or already past). Drives the dashboard tile.
    expiring_soon_count: int = 0
    already_expired_count: int = 0


@router.get("/dashboard", response_model=DashboardSummaryOut)
def dashboard_summary(
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())
    hid = current_user.hospital_id
    report_store = resolve_report_store_filter(db, current_user, store_id)

    sales_filter = db.query(
        sa_func.coalesce(sa_func.sum(PharmacySale.grand_total), 0),
        sa_func.count(PharmacySale.id),
    ).filter(
        PharmacySale.hospital_id == hid, PharmacySale.status == "completed",
        PharmacySale.sale_date >= today_start, PharmacySale.sale_date <= today_end,
    )
    if report_store is not None:
        sales_filter = sales_filter.filter(PharmacySale.store_id == report_store)
    sales_q = sales_filter.one()

    purchases_filter = db.query(
        sa_func.coalesce(sa_func.sum(PharmacyPurchase.grand_total), 0),
        sa_func.count(PharmacyPurchase.id),
    ).filter(
        PharmacyPurchase.hospital_id == hid,
        PharmacyPurchase.status == "confirmed",
        PharmacyPurchase.entry_date == date.today(),
    )
    if report_store is not None:
        purchases_filter = purchases_filter.filter(PharmacyPurchase.store_id == report_store)
    purchases_q = purchases_filter.one()

    # Reuse the live inventory queries
    low = sum(1 for r in list_inventory(
        search=None, low_only=True, store_id=report_store, db=db, current_user=current_user,
    ))
    pending = db.query(Prescription).filter(Prescription.status.in_(["pending", "partial"])).count()

    today = date.today()
    expiring_threshold = today + timedelta(days=90)
    expiring_soon = db.query(sa_func.count(PharmacyInventory.id)).filter(
        PharmacyInventory.hospital_id == hid,
        PharmacyInventory.is_active == True,  # noqa: E712
        PharmacyInventory.quantity_in_stock > 0,
        PharmacyInventory.expiry_date <= expiring_threshold,
        PharmacyInventory.expiry_date < _EXPIRY_SENTINEL,
        *([PharmacyInventory.store_id == report_store] if report_store is not None else []),
    ).scalar() or 0
    already_expired = db.query(sa_func.count(PharmacyInventory.id)).filter(
        PharmacyInventory.hospital_id == hid,
        PharmacyInventory.is_active == True,  # noqa: E712
        PharmacyInventory.quantity_in_stock > 0,
        PharmacyInventory.expiry_date < today,
        *([PharmacyInventory.store_id == report_store] if report_store is not None else []),
    ).scalar() or 0

    return DashboardSummaryOut(
        today_sales_total=float(sales_q[0] or 0),
        today_sales_count=int(sales_q[1] or 0),
        today_purchases_total=float(purchases_q[0] or 0),
        today_purchases_count=int(purchases_q[1] or 0),
        low_stock_count=low,
        pending_rx_count=pending,
        expiring_soon_count=int(expiring_soon),
        already_expired_count=int(already_expired),
    )


class SalesReportRow(BaseModel):
    bucket: str          # date string or medicine/doctor name or payment-type
    sales_count: int
    items_count: int
    subtotal: float
    discount_total: float
    tax_total: float
    grand_total: float


@router.get("/reports/sales", response_model=List[SalesReportRow])
def sales_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    group_by: str = Query("day", pattern="^(day|medicine|doctor|payment_type)$"),
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    hid = current_user.hospital_id
    report_store = resolve_report_store_filter(db, current_user, store_id)
    q_sales = db.query(PharmacySale).filter(
        PharmacySale.hospital_id == hid,
        PharmacySale.status == "completed",
    )
    if report_store is not None:
        q_sales = q_sales.filter(PharmacySale.store_id == report_store)
    start, end = _date_range(date_from, date_to)
    if start:
        q_sales = q_sales.filter(PharmacySale.sale_date >= start)
    if end:
        q_sales = q_sales.filter(PharmacySale.sale_date <= end)

    sales = q_sales.all()

    # P2.3: pre-fetch medicine names once for group_by=medicine. Previously each
    # item triggered a per-row Medicine query.
    med_name_map: dict = {}
    if group_by == "medicine" and sales:
        med_ids = {it.medicine_id for s in sales for it in s.items}
        if med_ids:
            for mid, name in db.query(Medicine.id, Medicine.name).filter(
                Medicine.id.in_(med_ids),
            ).all():
                med_name_map[mid] = name

    # Group in Python — keeps logic clear and handles all four group modes uniformly
    buckets: dict = {}
    for s in sales:
        if group_by == "day":
            key = s.sale_date.date().isoformat() if s.sale_date else "?"
        elif group_by == "payment_type":
            key = s.payment_type or "—"
        elif group_by == "doctor":
            key = s.doctor_name or "(walk-in)"
        else:  # medicine — explode by item
            for it in s.items:
                k = med_name_map.get(it.medicine_id) or f"#{it.medicine_id}"
                b = buckets.setdefault(k, {"sales": set(), "items": 0, "sub": 0.0, "disc": 0.0, "tax": 0.0, "grand": 0.0})
                b["sales"].add(s.id); b["items"] += 1
                # per-item portion of totals
                b["sub"] += (it.quantity or 0) * (it.rate or 0)
                # discount + tax we estimate from line_total + tax_pct + discount_pct
                base = (it.quantity or 0) * (it.rate or 0)
                disc_amt = base * ((it.discount_pct or 0) / 100.0)
                b["disc"] += disc_amt
                b["tax"] += (base - disc_amt) * ((it.tax_pct or 0) / 100.0)
                b["grand"] += it.line_total or 0
            continue
        b = buckets.setdefault(key, {"sales": set(), "items": 0, "sub": 0.0, "disc": 0.0, "tax": 0.0, "grand": 0.0})
        b["sales"].add(s.id)
        b["items"] += len(s.items)
        b["sub"] += s.subtotal or 0
        b["disc"] += s.discount_total or 0
        b["tax"] += s.tax_total or 0
        b["grand"] += s.grand_total or 0

    out = []
    for k, v in buckets.items():
        out.append(SalesReportRow(
            bucket=k, sales_count=len(v["sales"]), items_count=v["items"],
            subtotal=round(v["sub"], 2), discount_total=round(v["disc"], 2),
            tax_total=round(v["tax"], 2), grand_total=round(v["grand"], 2),
        ))
    out.sort(key=lambda r: r.bucket)
    return out


class PurchasesReportRow(BaseModel):
    bucket: str
    purchases_count: int
    items_count: int
    subtotal: float
    discount_total: float
    tax_total: float
    grand_total: float


@router.get("/reports/purchases", response_model=List[PurchasesReportRow])
def purchases_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    supplier_id: Optional[int] = None,
    group_by: str = Query("day", pattern="^(day|supplier)$"),
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    report_store = resolve_report_store_filter(db, current_user, store_id)
    q = db.query(PharmacyPurchase).filter(
        PharmacyPurchase.hospital_id == current_user.hospital_id,
        PharmacyPurchase.status == "confirmed",
    )
    if report_store is not None:
        q = q.filter(PharmacyPurchase.store_id == report_store)
    if date_from:
        q = q.filter(PharmacyPurchase.entry_date >= date_from)
    if date_to:
        q = q.filter(PharmacyPurchase.entry_date <= date_to)
    if supplier_id:
        q = q.filter(PharmacyPurchase.supplier_id == supplier_id)
    rows = q.all()

    buckets: dict = {}
    for p in rows:
        key = p.entry_date.isoformat() if group_by == "day" else (p.supplier.name if p.supplier else "—")
        b = buckets.setdefault(key, {"count": 0, "items": 0, "sub": 0.0, "disc": 0.0, "tax": 0.0, "grand": 0.0})
        b["count"] += 1
        b["items"] += len(p.items)
        b["sub"] += p.subtotal or 0
        b["disc"] += p.total_discount or 0
        b["tax"] += p.total_tax or 0
        b["grand"] += p.grand_total or 0
    out = [PurchasesReportRow(
        bucket=k, purchases_count=v["count"], items_count=v["items"],
        subtotal=round(v["sub"], 2), discount_total=round(v["disc"], 2),
        tax_total=round(v["tax"], 2), grand_total=round(v["grand"], 2),
    ) for k, v in buckets.items()]
    out.sort(key=lambda r: r.bucket)
    return out


class StockOnHandRow(BaseModel):
    medicine_id: int
    medicine_code: str
    name: str
    total_stock: float
    batch_count: int
    nearest_expiry: Optional[date]
    stock_value_cost: float       # sum(qty * cost_price) across batches
    stock_value_mrp: float


@router.get("/reports/stock-on-hand", response_model=List[StockOnHandRow])
def stock_on_hand_report(
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    report_store = resolve_report_store_filter(db, current_user, store_id)
    inv_join = (PharmacyInventory.medicine_id == Medicine.id) & (PharmacyInventory.is_active == True)  # noqa: E712
    if report_store is not None:
        inv_join = inv_join & (PharmacyInventory.store_id == report_store)
    rows = db.query(
        Medicine.id, Medicine.medicine_code, Medicine.name,
        sa_func.coalesce(sa_func.sum(PharmacyInventory.quantity_in_stock), 0).label("total"),
        sa_func.count(PharmacyInventory.id).label("batches"),
        sa_func.min(PharmacyInventory.expiry_date).label("nearest"),
        sa_func.coalesce(sa_func.sum(PharmacyInventory.quantity_in_stock * PharmacyInventory.cost_price), 0).label("v_cost"),
        sa_func.coalesce(sa_func.sum(PharmacyInventory.quantity_in_stock * PharmacyInventory.mrp), 0).label("v_mrp"),
    ).outerjoin(
        PharmacyInventory, inv_join,
    ).filter(
        Medicine.hospital_id == current_user.hospital_id,
        Medicine.is_active == True,  # noqa: E712
    ).group_by(Medicine.id, Medicine.medicine_code, Medicine.name).order_by(Medicine.name).all()

    return [StockOnHandRow(
        medicine_id=r[0], medicine_code=r[1], name=r[2],
        total_stock=float(r[3] or 0), batch_count=int(r[4] or 0),
        nearest_expiry=r[5],
        stock_value_cost=round(float(r[6] or 0), 2),
        stock_value_mrp=round(float(r[7] or 0), 2),
    ) for r in rows]


class NarcoticRow(BaseModel):
    sale_date: datetime
    sale_number: str
    medicine_name: str
    quantity: float
    batch_number: Optional[str] = None
    patient_name: Optional[str] = None
    patient_phone: Optional[str] = None
    doctor_name: Optional[str] = None
    schedule: str    # which flag matched: narcotic / schedule_h / schedule_h1 / tramadol / controlled
    status: str      # P2.2: completed | voided — voided movements stay on the register


@router.get("/reports/narcotic-register", response_model=List[NarcoticRow])
def narcotic_register(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_narcotic_register")),
):
    """All sale lines for medicines flagged as narcotic / Schedule H / H1 / Tramadol / controlled.

    P2.2: voided sales remain on the register (with status='voided') — controlled
    substance compliance requires every movement be visible.
    """
    report_store = resolve_report_store_filter(db, current_user, store_id)
    q = db.query(PharmacySaleItem, PharmacySale, Medicine, PharmacyInventory).join(
        PharmacySale, PharmacySale.id == PharmacySaleItem.sale_id,
    ).join(
        Medicine, Medicine.id == PharmacySaleItem.medicine_id,
    ).outerjoin(
        PharmacyInventory, PharmacyInventory.id == PharmacySaleItem.batch_id,
    ).filter(
        PharmacySale.hospital_id == current_user.hospital_id,
        or_(
            Medicine.is_narcotic == True,        # noqa: E712
            Medicine.is_schedule_h == True,      # noqa: E712
            Medicine.is_schedule_h1 == True,     # noqa: E712
            Medicine.is_tramadol == True,        # noqa: E712
            Medicine.is_controlled == True,      # noqa: E712
        ),
    )
    if report_store is not None:
        q = q.filter(PharmacySale.store_id == report_store)
    start, end = _date_range(date_from, date_to)
    if start:
        q = q.filter(PharmacySale.sale_date >= start)
    if end:
        q = q.filter(PharmacySale.sale_date <= end)

    out = []
    for it, s, med, inv in q.order_by(PharmacySale.sale_date.desc()).all():
        # Pick the most specific schedule label
        sched = (
            "narcotic" if med.is_narcotic else
            "schedule_h1" if med.is_schedule_h1 else
            "schedule_h" if med.is_schedule_h else
            "tramadol" if med.is_tramadol else
            "controlled"
        )
        out.append(NarcoticRow(
            sale_date=s.sale_date, sale_number=s.sale_number,
            medicine_name=med.name, quantity=it.quantity,
            batch_number=inv.batch_number if inv else None,
            patient_name=s.patient_name, patient_phone=s.patient_phone,
            doctor_name=s.doctor_name, schedule=sched,
            status=s.status or "completed",
        ))
    return out


class TaxSummaryRow(BaseModel):
    hsn_code: str
    sgst_pct: float
    cgst_pct: float
    igst_pct: float
    taxable_value: float
    sgst_amount: float
    cgst_amount: float
    igst_amount: float
    total_tax: float


@router.get("/reports/tax-summary", response_model=List[TaxSummaryRow])
def tax_summary_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    """SGST / CGST breakdown across sale items, grouped by HSN code.

    P2.1: reads snapshot tax % from the sale item itself (not the live HSN
    master) so historical reports stay stable when rates are edited. Sale
    items written before the migration default to 0 on the snapshot columns;
    we fall back to the medicine's current HSN row in that case so legacy
    rows keep producing sensible output.
    """
    report_store = resolve_report_store_filter(db, current_user, store_id)
    q = db.query(PharmacySaleItem, PharmacySale, Medicine, PharmacyHSN).join(
        PharmacySale, PharmacySale.id == PharmacySaleItem.sale_id,
    ).join(
        Medicine, Medicine.id == PharmacySaleItem.medicine_id,
    ).outerjoin(
        PharmacyHSN, PharmacyHSN.id == Medicine.hsn_id,
    ).filter(
        PharmacySale.hospital_id == current_user.hospital_id,
        PharmacySale.status == "completed",
    )
    if report_store is not None:
        q = q.filter(PharmacySale.store_id == report_store)
    start, end = _date_range(date_from, date_to)
    if start:
        q = q.filter(PharmacySale.sale_date >= start)
    if end:
        q = q.filter(PharmacySale.sale_date <= end)

    buckets: dict = {}
    for it, s, med, hsn in q.all():
        # Prefer snapshot; fall back to current HSN master for pre-migration rows.
        snap_total = (it.sgst_pct or 0) + (it.cgst_pct or 0) + (it.igst_pct or 0)
        if snap_total > 0:
            sgst, cgst, igst = it.sgst_pct or 0, it.cgst_pct or 0, it.igst_pct or 0
        elif hsn is not None:
            sgst, cgst, igst = hsn.sgst_pct or 0, hsn.cgst_pct or 0, hsn.igst_pct or 0
        else:
            sgst = cgst = igst = 0
        code = hsn.code if hsn else "—"
        key = (code, sgst, cgst, igst)
        b = buckets.setdefault(key, {"taxable": 0.0, "sgst": 0.0, "cgst": 0.0, "igst": 0.0})
        base = (it.quantity or 0) * (it.rate or 0)
        taxable = base * (1 - (it.discount_pct or 0) / 100.0)
        b["taxable"] += taxable
        b["sgst"] += taxable * (sgst / 100.0)
        b["cgst"] += taxable * (cgst / 100.0)
        b["igst"] += taxable * (igst / 100.0)

    return [TaxSummaryRow(
        hsn_code=k[0], sgst_pct=k[1], cgst_pct=k[2], igst_pct=k[3],
        taxable_value=round(v["taxable"], 2),
        sgst_amount=round(v["sgst"], 2),
        cgst_amount=round(v["cgst"], 2),
        igst_amount=round(v["igst"], 2),
        total_tax=round(v["sgst"] + v["cgst"] + v["igst"], 2),
    ) for k, v in buckets.items()]


# ============================================================================
# Phase 2 reports — P2.4 daily closeout, P2.5 margin, P2.7 supplier aging,
# P2.8 movement (fast/slow movers).
# ============================================================================


class DailyClosePaymentBucket(BaseModel):
    payment_type: str
    sales_count: int
    grand_total: float


class DailyCloseRow(BaseModel):
    cashier_id: Optional[int]
    cashier_name: Optional[str] = None
    sales_count: int
    voided_count: int
    gross: float
    discount: float
    tax: float
    net: float
    by_payment: List[DailyClosePaymentBucket] = Field(default_factory=list)


@router.get("/reports/daily-closeout", response_model=List[DailyCloseRow])
def daily_closeout_report(
    date: Optional[date] = Query(None, description="Defaults to today (server local date)"),
    cashier_id: Optional[int] = None,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    """One row per cashier for the chosen day. Used to print an end-of-day
    closeout slip per counter operator. Voided sales are counted separately
    so a quick reconciliation against cash-in-hand is possible.
    """
    from datetime import date as _date_cls
    the_day = date or _date_cls.today()
    start = datetime.combine(the_day, datetime.min.time())
    end = datetime.combine(the_day, datetime.max.time())

    report_store = resolve_report_store_filter(db, current_user, store_id)
    q = db.query(PharmacySale).filter(
        PharmacySale.hospital_id == current_user.hospital_id,
        PharmacySale.sale_date >= start,
        PharmacySale.sale_date <= end,
    )
    if report_store is not None:
        q = q.filter(PharmacySale.store_id == report_store)
    if cashier_id is not None:
        q = q.filter(PharmacySale.created_by == cashier_id)
    sales = q.all()

    # Resolve cashier display names once
    user_ids = {s.created_by for s in sales if s.created_by}
    name_map: dict = {}
    if user_ids:
        for uid, fn, ln, un in db.query(User.id, User.first_name, User.last_name, User.username).filter(
            User.id.in_(user_ids),
        ).all():
            full = f"{fn or ''} {ln or ''}".strip() or un
            name_map[uid] = full

    # Accumulate per cashier
    by_cashier: dict = {}
    for s in sales:
        cid = s.created_by
        bucket = by_cashier.setdefault(cid, {
            "sales": 0, "voided": 0, "gross": 0.0, "disc": 0.0, "tax": 0.0, "net": 0.0,
            "by_pay": {},
        })
        if s.status == "voided":
            bucket["voided"] += 1
            # Voided sales do not count toward net cash — skip totals.
            continue
        bucket["sales"] += 1
        bucket["gross"] += s.subtotal or 0
        bucket["disc"] += s.discount_total or 0
        bucket["tax"] += s.tax_total or 0
        bucket["net"] += s.grand_total or 0
        pt = s.payment_type or "cash"
        pb = bucket["by_pay"].setdefault(pt, {"count": 0, "total": 0.0})
        pb["count"] += 1
        pb["total"] += s.grand_total or 0

    rows: List[DailyCloseRow] = []
    for cid, v in by_cashier.items():
        rows.append(DailyCloseRow(
            cashier_id=cid, cashier_name=name_map.get(cid),
            sales_count=v["sales"], voided_count=v["voided"],
            gross=round(v["gross"], 2), discount=round(v["disc"], 2),
            tax=round(v["tax"], 2), net=round(v["net"], 2),
            by_payment=[
                DailyClosePaymentBucket(
                    payment_type=pt, sales_count=pb["count"],
                    grand_total=round(pb["total"], 2),
                )
                for pt, pb in sorted(v["by_pay"].items())
            ],
        ))
    rows.sort(key=lambda r: (r.cashier_name or "", r.cashier_id or 0))
    return rows


class MarginRow(BaseModel):
    bucket: str             # day (YYYY-MM-DD) or medicine name
    units_sold: float
    revenue: float          # post-discount, pre-tax — what the customer paid for the goods
    cost: float             # sum of quantity * batch.cost_price
    margin: float
    margin_pct: float       # margin / revenue (0 if revenue == 0)


@router.get("/reports/margin", response_model=List[MarginRow])
def margin_report(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    group_by: str = Query("day", pattern="^(day|medicine)$"),
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    """Realized gross margin per medicine or per day.

    revenue = sum(quantity * rate * (1 - discount_pct/100))
    cost    = sum(quantity * batch.cost_price)
    margin  = revenue - cost; margin_pct = margin / revenue.

    Voided sales are excluded.
    """
    report_store = resolve_report_store_filter(db, current_user, store_id)
    q = db.query(PharmacySaleItem, PharmacySale, PharmacyInventory).join(
        PharmacySale, PharmacySale.id == PharmacySaleItem.sale_id,
    ).outerjoin(
        PharmacyInventory, PharmacyInventory.id == PharmacySaleItem.batch_id,
    ).filter(
        PharmacySale.hospital_id == current_user.hospital_id,
        PharmacySale.status == "completed",
    )
    if report_store is not None:
        q = q.filter(PharmacySale.store_id == report_store)
    start, end = _date_range(date_from, date_to)
    if start:
        q = q.filter(PharmacySale.sale_date >= start)
    if end:
        q = q.filter(PharmacySale.sale_date <= end)

    rows_raw = q.all()
    med_ids = {it.medicine_id for it, _, _ in rows_raw}
    med_names: dict = {}
    if med_ids:
        for mid, name in db.query(Medicine.id, Medicine.name).filter(
            Medicine.id.in_(med_ids),
        ).all():
            med_names[mid] = name

    buckets: dict = {}
    for it, s, batch in rows_raw:
        qty = float(it.quantity or 0)
        base = qty * float(it.rate or 0)
        revenue = base * (1 - float(it.discount_pct or 0) / 100.0)
        cost = qty * float((batch.cost_price if batch else 0) or 0)
        if group_by == "day":
            key = s.sale_date.date().isoformat() if s.sale_date else "?"
        else:
            key = med_names.get(it.medicine_id) or f"#{it.medicine_id}"
        b = buckets.setdefault(key, {"qty": 0.0, "rev": 0.0, "cost": 0.0})
        b["qty"] += qty
        b["rev"] += revenue
        b["cost"] += cost

    out: List[MarginRow] = []
    for k, v in buckets.items():
        margin = v["rev"] - v["cost"]
        pct = (margin / v["rev"] * 100.0) if v["rev"] > 0 else 0.0
        out.append(MarginRow(
            bucket=k, units_sold=round(v["qty"], 3),
            revenue=round(v["rev"], 2), cost=round(v["cost"], 2),
            margin=round(margin, 2), margin_pct=round(pct, 2),
        ))
    out.sort(key=lambda r: r.bucket)
    return out


class SupplierAgingRow(BaseModel):
    supplier_id: int
    supplier_name: str
    bucket_0_30: float
    bucket_31_60: float
    bucket_61_90: float
    bucket_90_plus: float
    total_outstanding: float


@router.get("/reports/supplier-aging", response_model=List[SupplierAgingRow])
def supplier_aging_report(
    as_of: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    """Creditor aging by age bucket for confirmed credit purchases.

    INTERIM: until P4.2 ships a `PharmacySupplierPayment` table, every confirmed
    credit purchase is treated as fully outstanding. Cash purchases are
    excluded. Revoked purchases are excluded.
    """
    from datetime import date as _date_cls
    today = as_of or _date_cls.today()

    rows = db.query(PharmacyPurchase, PharmacySupplier).join(
        PharmacySupplier, PharmacySupplier.id == PharmacyPurchase.supplier_id,
    ).filter(
        PharmacyPurchase.hospital_id == current_user.hospital_id,
        PharmacyPurchase.status == "confirmed",
        PharmacyPurchase.payment_type == "credit",
    ).all()

    by_sup: dict = {}
    for p, sup in rows:
        days = (today - p.entry_date).days if p.entry_date else 0
        amount = float(p.grand_total or 0)
        entry = by_sup.setdefault(sup.id, {
            "name": sup.name, "b0": 0.0, "b1": 0.0, "b2": 0.0, "b3": 0.0,
        })
        if days <= 30:
            entry["b0"] += amount
        elif days <= 60:
            entry["b1"] += amount
        elif days <= 90:
            entry["b2"] += amount
        else:
            entry["b3"] += amount

    out: List[SupplierAgingRow] = []
    for sid, v in by_sup.items():
        total = v["b0"] + v["b1"] + v["b2"] + v["b3"]
        out.append(SupplierAgingRow(
            supplier_id=sid, supplier_name=v["name"],
            bucket_0_30=round(v["b0"], 2), bucket_31_60=round(v["b1"], 2),
            bucket_61_90=round(v["b2"], 2), bucket_90_plus=round(v["b3"], 2),
            total_outstanding=round(total, 2),
        ))
    out.sort(key=lambda r: -r.total_outstanding)
    return out


class MovementRow(BaseModel):
    medicine_id: int
    medicine_name: str
    units_sold: float
    revenue: float
    stock_on_hand: float
    days_of_cover: Optional[float]   # None when no sales in the window
    abc_class: str                   # A / B / C


@router.get("/reports/movement", response_model=List[MovementRow])
def movement_report(
    days: int = Query(90, ge=1, le=365),
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    """Per-medicine sales velocity over the last `days` days, classified ABC
    by Pareto on revenue (top 80% revenue → A, next 15% → B, bottom 5% → C).
    """
    report_store = resolve_report_store_filter(db, current_user, store_id)
    window_start = datetime.now() - timedelta(days=days)
    q = db.query(PharmacySaleItem, PharmacySale).join(
        PharmacySale, PharmacySale.id == PharmacySaleItem.sale_id,
    ).filter(
        PharmacySale.hospital_id == current_user.hospital_id,
        PharmacySale.status == "completed",
        PharmacySale.sale_date >= window_start,
    )
    if report_store is not None:
        q = q.filter(PharmacySale.store_id == report_store)
    rows = q.all()

    by_med: dict = {}
    for it, s in rows:
        b = by_med.setdefault(it.medicine_id, {"qty": 0.0, "rev": 0.0})
        base = float(it.quantity or 0) * float(it.rate or 0)
        b["qty"] += float(it.quantity or 0)
        b["rev"] += base * (1 - float(it.discount_pct or 0) / 100.0)

    # Stock on hand per medicine, including the ones with zero sales (for slow movers).
    stock_map: dict = {}
    name_map: dict = {}
    inv_join = (PharmacyInventory.medicine_id == Medicine.id) & (PharmacyInventory.is_active == True)  # noqa: E712
    if report_store is not None:
        inv_join = inv_join & (PharmacyInventory.store_id == report_store)
    for mid, name, stock in db.query(
        Medicine.id, Medicine.name,
        sa_func.coalesce(sa_func.sum(PharmacyInventory.quantity_in_stock), 0),
    ).outerjoin(
        PharmacyInventory, inv_join,
    ).filter(
        Medicine.hospital_id == current_user.hospital_id,
        Medicine.is_active == True,  # noqa: E712
    ).group_by(Medicine.id, Medicine.name).all():
        stock_map[mid] = float(stock or 0)
        name_map[mid] = name

    # Ensure every active medicine appears (slow movers with 0 sales still listed)
    for mid in name_map:
        by_med.setdefault(mid, {"qty": 0.0, "rev": 0.0})

    # ABC classification by cumulative revenue.
    sorted_meds = sorted(by_med.items(), key=lambda kv: -kv[1]["rev"])
    total_rev = sum(v["rev"] for _, v in sorted_meds) or 0
    cum = 0.0
    abc_map: dict = {}
    for mid, v in sorted_meds:
        if total_rev <= 0:
            abc_map[mid] = "C"
            continue
        cum += v["rev"]
        share = cum / total_rev
        abc_map[mid] = "A" if share <= 0.80 else ("B" if share <= 0.95 else "C")

    out: List[MovementRow] = []
    for mid, v in sorted_meds:
        qty = v["qty"]
        stock = stock_map.get(mid, 0.0)
        per_day = qty / days if days > 0 else 0
        doc = (stock / per_day) if per_day > 0 else None
        out.append(MovementRow(
            medicine_id=mid, medicine_name=name_map.get(mid, f"#{mid}"),
            units_sold=round(qty, 3), revenue=round(v["rev"], 2),
            stock_on_hand=round(stock, 3),
            days_of_cover=round(doc, 1) if doc is not None else None,
            abc_class=abc_map.get(mid, "C"),
        ))
    return out


# ============================================================================
# PDFs (Section I)
# ----------------------------------------------------------------------------
# All four generators live in pdf_service.PDFService; the routes below shape
# the source rows into the dicts each generator expects and return the buffer
# as application/pdf with the standard `include_header` toggle.
# ============================================================================

def _hospital_info_for_pdf(db: Session, hospital_id: int) -> dict:
    h = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    return {
        "name": h.name if h else "PHARMACY",
        "address": getattr(h, "address", "") if h else "",
        "phone": getattr(h, "phone", "") if h else "",
        "email": getattr(h, "email", "") if h else "",
        "logo_url": getattr(h, "logo_url", "") if h else "",
    }


def _pdf_response(buffer, filename: str) -> StreamingResponse:
    return StreamingResponse(
        buffer, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.get("/sales/{sid}/invoice/pdf")
def sale_invoice_pdf(
    sid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_sales")),
):
    s = db.query(PharmacySale).filter(
        PharmacySale.id == sid,
        PharmacySale.hospital_id == current_user.hospital_id,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Sale not found")
    shaped = _shape_sale(s, db).model_dump()
    shaped["void_reason"] = s.void_reason
    shaped["store_name"] = _store_label(db, s.store_id)
    # Pharmacy sales link to an existing Patient by ip_id when applicable;
    # surface village/district so the address row renders in the invoice.
    try:
        from app.models.patient import Patient as _P
        if getattr(s, "patient_ip_id", None):
            _p = db.query(_P).filter(_P.patient_id == s.patient_ip_id).first()
            if _p:
                shaped["village"] = _p.village or ""
                shaped["district"] = _p.district or ""
    except Exception:
        pass
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    buf = pdf_service.generate_pharmacy_sale_invoice_pdf(shaped, hi, **pdf_gen_kwargs(db, current_user.hospital_id, 'pharmacy_sale_invoice'))
    return _pdf_response(buf, f"{s.sale_number}.pdf")


@router.get("/purchases/{pid}/pdf")
def purchase_pdf(
    pid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_purchases")),
):
    p = db.query(PharmacyPurchase).filter(
        PharmacyPurchase.id == pid,
        PharmacyPurchase.hospital_id == current_user.hospital_id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Purchase not found")
    shaped = _shape_purchase(p, db).model_dump()
    shaped["notes"] = p.notes
    shaped["store_name"] = _store_label(db, p.store_id)
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    buf = pdf_service.generate_pharmacy_purchase_pdf(shaped, hi, **pdf_gen_kwargs(db, current_user.hospital_id, 'pharmacy_purchase'))
    return _pdf_response(buf, f"{p.purchase_number}.pdf")


@router.get("/prescriptions/{rx_id}/dispense/pdf")
def dispense_slip_pdf(
    rx_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_dispense_queue")),
):
    rx = db.query(Prescription).filter(Prescription.id == rx_id).first()
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")

    # Build "lines" from the most recent dispense ledger entries for this Rx.
    led_rows = db.query(PharmacyStockLedger, PharmacyInventory, Medicine).join(
        PharmacyInventory, PharmacyInventory.id == PharmacyStockLedger.batch_id,
    ).join(
        Medicine, Medicine.id == PharmacyStockLedger.medicine_id,
    ).filter(
        PharmacyStockLedger.txn_type == "rx_dispense",
        PharmacyStockLedger.reference_type == "prescription",
        PharmacyStockLedger.reference_id == rx.id,
    ).order_by(PharmacyStockLedger.created_at.desc()).all()
    lines = [{
        "medicine_name": med.name,
        "batch_number": inv.batch_number if inv else None,
        "quantity": abs(led.qty_delta or 0),
    } for led, inv, med in led_rows]

    # Patient / doctor names (best-effort — Rx FKs point at patients + users)
    patient_name = None
    doctor_name = None
    patient_village = ""
    patient_district = ""
    try:
        from app.models.patient import Patient
        p_row = db.query(Patient).filter(Patient.id == rx.patient_id).first()
        if p_row:
            patient_name = f"{p_row.first_name} {p_row.last_name}".strip()
            patient_village = p_row.village or ""
            patient_district = p_row.district or ""
    except Exception:
        pass
    try:
        doc_row = db.query(User).filter(User.id == rx.doctor_id).first()
        if doc_row:
            doctor_name = f"Dr. {doc_row.first_name} {doc_row.last_name}".strip()
    except Exception:
        pass

    data = {
        "prescription_number": rx.prescription_number,
        "prescription_date": rx.prescription_date,
        "patient_name": patient_name,
        "doctor_name": doctor_name,
        "village": patient_village,
        "district": patient_district,
        "dispensed_by": f"{current_user.first_name} {current_user.last_name}",
        "store_name": _store_label(db, rx.dispense_store_id),
        "lines": lines,
        "notes": rx.notes,
    }
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    buf = pdf_service.generate_pharmacy_dispense_slip_pdf(data, hi, **pdf_gen_kwargs(db, current_user.hospital_id, 'pharmacy_dispense'))
    return _pdf_response(buf, f"dispense_{rx.prescription_number}.pdf")


@router.get("/reports/narcotic-register/pdf")
def narcotic_register_pdf(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_narcotic_register")),
):
    rows = narcotic_register(date_from=date_from, date_to=date_to, store_id=store_id,
                             db=db, current_user=current_user)
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    period = {
        "from": date_from.isoformat() if date_from else None,
        "to": date_to.isoformat() if date_to else None,
    }
    # Convert Pydantic rows → plain dicts for the generator
    row_dicts = [r.model_dump() for r in rows]
    buf = pdf_service.generate_narcotic_register_pdf(row_dicts, period, hi, **pdf_gen_kwargs(db, current_user.hospital_id, 'narcotic_register'))
    return _pdf_response(buf, "narcotic_register.pdf")


# ============================================================================
# Phase-2 report PDFs — all go through the generic tabular generator.
# ============================================================================

def _report_period(date_from: Optional[date], date_to: Optional[date]) -> dict:
    return {
        "from": date_from.isoformat() if date_from else None,
        "to": date_to.isoformat() if date_to else None,
    }


def _report_pdf_meta(
    db: Session,
    user: User,
    store_id: Optional[int],
    extra: Optional[dict] = None,
) -> dict:
    meta = dict(extra or {})
    report_store = resolve_report_store_filter(db, user, store_id)
    label = _store_label(db, report_store)
    if label:
        meta["Store"] = label
    return meta


@router.get("/reports/sales/pdf")
def sales_report_pdf(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    group_by: str = Query("day", pattern="^(day|medicine|doctor|payment_type)$"),
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = sales_report(date_from=date_from, date_to=date_to, group_by=group_by,
                        store_id=store_id, db=db, current_user=current_user)
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    cols = [
        {"key": "bucket", "label": group_by.replace("_", " ").title(), "width": 3},
        {"key": "sales_count", "label": "Sales", "align": "RIGHT", "width": 1},
        {"key": "items_count", "label": "Items", "align": "RIGHT", "width": 1},
        {"key": "subtotal", "label": "Subtotal", "align": "RIGHT", "width": 1.5},
        {"key": "discount_total", "label": "Discount", "align": "RIGHT", "width": 1.5},
        {"key": "tax_total", "label": "Tax", "align": "RIGHT", "width": 1.5},
        {"key": "grand_total", "label": "Grand Total", "align": "RIGHT", "width": 1.8},
    ]
    buf = pdf_service.generate_pharmacy_report_pdf(
        title="SALES REPORT", period=_report_period(date_from, date_to),
        columns=cols, rows=[r.model_dump() for r in rows],
        hospital_info=hi, **pdf_gen_kwargs(db, current_user.hospital_id, 'pharmacy_report'),
        meta=_report_pdf_meta(db, current_user, store_id, {"Group by": group_by}),
    )
    return _pdf_response(buf, "pharmacy_sales.pdf")


@router.get("/reports/purchases/pdf")
def purchases_report_pdf(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    supplier_id: Optional[int] = None,
    group_by: str = Query("day", pattern="^(day|supplier)$"),
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = purchases_report(date_from=date_from, date_to=date_to,
                            supplier_id=supplier_id, group_by=group_by,
                            store_id=store_id, db=db, current_user=current_user)
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    cols = [
        {"key": "bucket", "label": group_by.title(), "width": 3},
        {"key": "purchases_count", "label": "Purchases", "align": "RIGHT", "width": 1},
        {"key": "items_count", "label": "Items", "align": "RIGHT", "width": 1},
        {"key": "subtotal", "label": "Subtotal", "align": "RIGHT", "width": 1.5},
        {"key": "discount_total", "label": "Discount", "align": "RIGHT", "width": 1.5},
        {"key": "tax_total", "label": "Tax", "align": "RIGHT", "width": 1.5},
        {"key": "grand_total", "label": "Grand Total", "align": "RIGHT", "width": 1.8},
    ]
    buf = pdf_service.generate_pharmacy_report_pdf(
        title="PURCHASES REPORT", period=_report_period(date_from, date_to),
        columns=cols, rows=[r.model_dump() for r in rows],
        hospital_info=hi, **pdf_gen_kwargs(db, current_user.hospital_id, 'pharmacy_report'),
        meta=_report_pdf_meta(db, current_user, store_id, {"Group by": group_by}),
    )
    return _pdf_response(buf, "pharmacy_purchases.pdf")


@router.get("/reports/stock-on-hand/pdf")
def stock_on_hand_pdf(
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = stock_on_hand_report(store_id=store_id, db=db, current_user=current_user)
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    cols = [
        {"key": "medicine_code", "label": "Code", "width": 1.2},
        {"key": "name", "label": "Medicine", "width": 3},
        {"key": "total_stock", "label": "Qty", "align": "RIGHT", "width": 1},
        {"key": "batch_count", "label": "Batches", "align": "RIGHT", "width": 1},
        {"key": "nearest_expiry", "label": "Nearest Expiry", "width": 1.2,
         "formatter": lambda v: v.isoformat() if v else "—"},
        {"key": "stock_value_cost", "label": "Value @ Cost", "align": "RIGHT", "width": 1.4},
        {"key": "stock_value_mrp", "label": "Value @ MRP", "align": "RIGHT", "width": 1.4},
    ]
    buf = pdf_service.generate_pharmacy_report_pdf(
        title="STOCK ON HAND", period=None,
        columns=cols, rows=[r.model_dump() for r in rows],
        hospital_info=hi, **pdf_gen_kwargs(db, current_user.hospital_id, 'pharmacy_report'),
        meta=_report_pdf_meta(db, current_user, store_id),
    )
    return _pdf_response(buf, "pharmacy_stock.pdf")


@router.get("/reports/tax-summary/pdf")
def tax_summary_pdf(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = tax_summary_report(date_from=date_from, date_to=date_to, store_id=store_id,
                              db=db, current_user=current_user)
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    cols = [
        {"key": "hsn_code", "label": "HSN", "width": 1.3},
        {"key": "sgst_pct", "label": "SGST %", "align": "RIGHT", "width": 0.8},
        {"key": "cgst_pct", "label": "CGST %", "align": "RIGHT", "width": 0.8},
        {"key": "igst_pct", "label": "IGST %", "align": "RIGHT", "width": 0.8},
        {"key": "taxable_value", "label": "Taxable", "align": "RIGHT", "width": 1.5},
        {"key": "sgst_amount", "label": "SGST", "align": "RIGHT", "width": 1.2},
        {"key": "cgst_amount", "label": "CGST", "align": "RIGHT", "width": 1.2},
        {"key": "igst_amount", "label": "IGST", "align": "RIGHT", "width": 1.2},
        {"key": "total_tax", "label": "Total Tax", "align": "RIGHT", "width": 1.4},
    ]
    buf = pdf_service.generate_pharmacy_report_pdf(
        title="TAX SUMMARY", period=_report_period(date_from, date_to),
        columns=cols, rows=[r.model_dump() for r in rows],
        hospital_info=hi, **pdf_gen_kwargs(db, current_user.hospital_id, 'pharmacy_report'),
        meta=_report_pdf_meta(db, current_user, store_id),
    )
    return _pdf_response(buf, "pharmacy_tax_summary.pdf")


@router.get("/reports/daily-closeout/pdf")
def daily_closeout_pdf(
    date: Optional[date] = None,
    cashier_id: Optional[int] = None,
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = daily_closeout_report(date=date, cashier_id=cashier_id, store_id=store_id,
                                 db=db, current_user=current_user)
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    cols = [
        {"key": "cashier_name", "label": "Cashier", "width": 2.5,
         "formatter": lambda v: v or "(unknown)"},
        {"key": "sales_count", "label": "Sales", "align": "RIGHT", "width": 0.8},
        {"key": "voided_count", "label": "Voided", "align": "RIGHT", "width": 0.8},
        {"key": "gross", "label": "Gross", "align": "RIGHT", "width": 1.3},
        {"key": "discount", "label": "Discount", "align": "RIGHT", "width": 1.3},
        {"key": "tax", "label": "Tax", "align": "RIGHT", "width": 1.2},
        {"key": "net", "label": "Net", "align": "RIGHT", "width": 1.4},
        {"key": "by_payment", "label": "By Payment", "width": 2.5,
         "formatter": lambda v: ", ".join(
             f"{b['payment_type']}: ₹{b['grand_total']:.2f} ({b['sales_count']})"
             for b in (v or [])
         ) or "—"},
    ]
    from datetime import date as _d
    the_day = (date or _d.today()).isoformat()
    buf = pdf_service.generate_pharmacy_report_pdf(
        title="DAILY CLOSEOUT", period={"from": the_day, "to": the_day},
        columns=cols, rows=[r.model_dump() for r in rows],
        hospital_info=hi, **pdf_gen_kwargs(db, current_user.hospital_id, 'pharmacy_report'),
        meta=_report_pdf_meta(db, current_user, store_id),
    )
    return _pdf_response(buf, f"closeout_{the_day}.pdf")


@router.get("/reports/margin/pdf")
def margin_report_pdf(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    group_by: str = Query("day", pattern="^(day|medicine)$"),
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = margin_report(date_from=date_from, date_to=date_to, group_by=group_by,
                         store_id=store_id, db=db, current_user=current_user)
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    cols = [
        {"key": "bucket", "label": group_by.title(), "width": 3},
        {"key": "units_sold", "label": "Units", "align": "RIGHT", "width": 1},
        {"key": "revenue", "label": "Revenue", "align": "RIGHT", "width": 1.5},
        {"key": "cost", "label": "Cost", "align": "RIGHT", "width": 1.5},
        {"key": "margin", "label": "Margin", "align": "RIGHT", "width": 1.5},
        {"key": "margin_pct", "label": "Margin %", "align": "RIGHT", "width": 1.2},
    ]
    buf = pdf_service.generate_pharmacy_report_pdf(
        title="PROFIT / MARGIN", period=_report_period(date_from, date_to),
        columns=cols, rows=[r.model_dump() for r in rows],
        hospital_info=hi, **pdf_gen_kwargs(db, current_user.hospital_id, 'pharmacy_report'),
        meta=_report_pdf_meta(db, current_user, store_id, {"Group by": group_by}),
    )
    return _pdf_response(buf, "pharmacy_margin.pdf")


@router.get("/reports/supplier-aging/pdf")
def supplier_aging_pdf(
    as_of: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = supplier_aging_report(as_of=as_of, db=db, current_user=current_user)
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    cols = [
        {"key": "supplier_name", "label": "Supplier", "width": 3},
        {"key": "bucket_0_30", "label": "0–30 d", "align": "RIGHT", "width": 1.2},
        {"key": "bucket_31_60", "label": "31–60 d", "align": "RIGHT", "width": 1.2},
        {"key": "bucket_61_90", "label": "61–90 d", "align": "RIGHT", "width": 1.2},
        {"key": "bucket_90_plus", "label": "90+ d", "align": "RIGHT", "width": 1.2},
        {"key": "total_outstanding", "label": "Total", "align": "RIGHT", "width": 1.5},
    ]
    from datetime import date as _d
    the_day = (as_of or _d.today()).isoformat()
    buf = pdf_service.generate_pharmacy_report_pdf(
        title="SUPPLIER OUTSTANDING (AGING)",
        period={"from": "—", "to": the_day},
        columns=cols, rows=[r.model_dump() for r in rows],
        hospital_info=hi, **pdf_gen_kwargs(db, current_user.hospital_id, 'pharmacy_report'),
        meta={"Note": "Interim — payments tracking ships in P4.2"},
    )
    return _pdf_response(buf, "supplier_aging.pdf")


@router.get("/reports/movement/pdf")
def movement_report_pdf(
    days: int = Query(90, ge=1, le=365),
    store_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = movement_report(days=days, store_id=store_id, db=db, current_user=current_user)
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    cols = [
        {"key": "medicine_name", "label": "Medicine", "width": 3},
        {"key": "abc_class", "label": "ABC", "align": "CENTER", "width": 0.7},
        {"key": "units_sold", "label": "Units", "align": "RIGHT", "width": 1},
        {"key": "revenue", "label": "Revenue", "align": "RIGHT", "width": 1.4},
        {"key": "stock_on_hand", "label": "Stock", "align": "RIGHT", "width": 1},
        {"key": "days_of_cover", "label": "Days Cover", "align": "RIGHT", "width": 1.2,
         "formatter": lambda v: f"{v:.1f}" if v is not None else "∞"},
    ]
    buf = pdf_service.generate_pharmacy_report_pdf(
        title=f"MOVEMENT — Last {days} days", period=None,
        columns=cols, rows=[r.model_dump() for r in rows],
        hospital_info=hi, **pdf_gen_kwargs(db, current_user.hospital_id, 'pharmacy_report'),
        meta=_report_pdf_meta(db, current_user, store_id),
    )
    return _pdf_response(buf, "pharmacy_movement.pdf")
