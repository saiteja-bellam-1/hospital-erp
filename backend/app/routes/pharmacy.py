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
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.hospital import Hospital
from app.utils.pdf_service import pdf_service

from config.database import get_db
from app.utils.pdf_settings import get_hospital_pdf_include_header
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
    Prescription,
    PrescriptionItem,
)
from sqlalchemy import func as sa_func
from app.utils.auth import Modules
from app.utils.dependencies import get_current_user, require_feature_permission
from app.services.audit_service import log_action


router = APIRouter()


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
    strip_conversion_factor: int = 1

    # Master FKs
    company_id: Optional[int] = None
    rack_id: Optional[int] = None
    salt_id: Optional[int] = None
    uom_id: Optional[int] = None

    # Stock thresholds (Section D)
    min_qty: int = 0
    max_qty: int = 0
    reorder_qty: int = 0


class MedicineOut(MedicineIn):
    id: int

    class Config:
        from_attributes = True


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


@router.get("/medicines/lookup", response_model=List[MedicineOut])
def lookup_medicine(
    q: Optional[str] = None,
    barcode: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_catalog")),
):
    """Lightweight search used by sales counter (name / code / barcode)."""
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
    return query.order_by(Medicine.name).limit(limit).all()


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
    return row


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
    igst_pct: float = 0.0
    is_active: bool = True


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


@router.post("/hsn", response_model=HSNOut, status_code=201)
def create_hsn(
    data: HSNIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_hsn_tax")),
):
    row = PharmacyHSN(hospital_id=current_user.hospital_id, **data.model_dump())
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
    for k, v in data.model_dump().items():
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
        row.unit_price = data.rate_a
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
    quantity_in_stock: float
    mrp: float
    purchase_rate: float
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_inventory")),
):
    """Per-medicine stock summary across batches with low-stock flag."""
    # Aggregate stock + nearest expiry per medicine
    agg = db.query(
        PharmacyInventory.medicine_id,
        sa_func.sum(PharmacyInventory.quantity_in_stock).label("total"),
        sa_func.count(PharmacyInventory.id).label("batches"),
    ).filter(
        PharmacyInventory.hospital_id == current_user.hospital_id,
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
    active_only: bool = True,
    limit: int = 500,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_inventory")),
):
    q = db.query(PharmacyInventory, Medicine, PharmacySupplier).join(
        Medicine, Medicine.id == PharmacyInventory.medicine_id,
    ).outerjoin(PharmacySupplier, PharmacySupplier.id == PharmacyInventory.supplier_id).filter(
        PharmacyInventory.hospital_id == current_user.hospital_id,
    )
    if active_only:
        q = q.filter(PharmacyInventory.is_active == True)  # noqa: E712
    if medicine_id:
        q = q.filter(PharmacyInventory.medicine_id == medicine_id)
    if supplier_id:
        q = q.filter(PharmacyInventory.supplier_id == supplier_id)
    rows = q.order_by(PharmacyInventory.id.asc()).limit(limit).all()
    return [
        BatchOut(
            id=inv.id, medicine_id=inv.medicine_id, medicine_name=med.name,
            batch_number=inv.batch_number,
            quantity_in_stock=inv.quantity_in_stock, mrp=inv.mrp or 0.0,
            purchase_rate=inv.purchase_rate or 0.0, selling_price=inv.selling_price or 0.0,
            free_quantity=inv.free_quantity or 0,
            supplier_id=inv.supplier_id, supplier_name=sup.name if sup else None,
            purchase_id=inv.purchase_id, hsn_id=inv.hsn_id, is_active=inv.is_active,
        ) for inv, med, sup in rows
    ]


@router.get("/inventory/low-stock", response_model=List[InventoryRowOut])
def list_low_stock(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_low_stock")),
):
    """All medicines whose total stock ≤ min_qty (and min_qty > 0)."""
    # Reuse list_inventory with low_only=True
    return list_inventory(search=None, low_only=True, db=db, current_user=current_user)


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
        performed_by=current_user.id, hospital_id=current_user.hospital_id,
    )
    db.add(adj)
    db.flush()  # need adj.id for the ledger reference
    led = PharmacyStockLedger(
        medicine_id=batch.medicine_id, batch_id=batch.id,
        txn_type="adjustment", qty_delta=data.qty_change,
        reference_type="adjustment", reference_id=adj.id,
        performed_by=current_user.id, notes=data.reason,
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
    rows = (
        db.query(PharmacyInventory, Medicine)
        .join(Medicine, Medicine.id == PharmacyInventory.medicine_id)
        .filter(
            PharmacyInventory.hospital_id == current_user.hospital_id,
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
    discount_pct: float = 0.0
    hsn_id: Optional[int] = None
    # Last-day-of-month for the batch's expiry. Optional only for backward
    # compatibility with the prior "no expiry" UI; frontends should always send
    # this for perishable medicines.
    expiry_date: Optional[date] = None


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
    invoice_number: Optional[str] = None
    bill_date: Optional[date] = None
    payment_type: str = Field("cash", pattern="^(cash|credit)$")
    purchase_type: Optional[str] = None
    notes: Optional[str] = None
    items: List[PurchaseItemIn] = Field(default_factory=list)


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
    return ((qty or 0) * (rate or 0)) / total


def _compute_item_line(item: dict, hsn_row: Optional[PharmacyHSN]) -> dict:
    """Returns (line_total, tax_amount) for a purchase item.

    Formula: base = qty × p_rate; discount applied first; tax applied on
    discounted base. Free quantity is non-billable but tracked for inventory.
    """
    qty = float(item.get("quantity") or 0)
    rate = float(item.get("purchase_rate") or 0)
    disc = float(item.get("discount_pct") or 0)
    base = qty * rate
    base_after_disc = base * (1 - disc / 100.0)
    tax_pct = 0.0
    if hsn_row:
        tax_pct = (hsn_row.sgst_pct or 0) + (hsn_row.cgst_pct or 0) + (hsn_row.igst_pct or 0)
    tax_amt = base_after_disc * (tax_pct / 100.0)
    return {
        "line_total": round(base_after_disc + tax_amt, 2),
        "tax_amount": round(tax_amt, 2),
        "discount_amount": round(base - base_after_disc, 2),
    }


def _recompute_purchase_totals(purchase: PharmacyPurchase, db: Session) -> None:
    subtotal = 0.0
    disc = 0.0
    tax = 0.0
    grand = 0.0
    for it in purchase.items:
        hsn_row = db.query(PharmacyHSN).filter(PharmacyHSN.id == it.hsn_id).first() if it.hsn_id else None
        comp = _compute_item_line({
            "quantity": it.quantity, "purchase_rate": it.purchase_rate, "discount_pct": it.discount_pct,
        }, hsn_row)
        it.tax_amount = comp["tax_amount"]
        it.line_total = comp["line_total"]
        # P2.1: snapshot per-component HSN rates so historical reports don't
        # drift when the HSN master is edited later.
        it.sgst_pct = (hsn_row.sgst_pct or 0) if hsn_row else 0.0
        it.cgst_pct = (hsn_row.cgst_pct or 0) if hsn_row else 0.0
        it.igst_pct = (hsn_row.igst_pct or 0) if hsn_row else 0.0
        subtotal += (it.quantity or 0) * (it.purchase_rate or 0)
        disc += comp["discount_amount"]
        tax += comp["tax_amount"]
        grand += comp["line_total"]
    purchase.subtotal = round(subtotal, 2)
    purchase.total_discount = round(disc, 2)
    purchase.total_tax = round(tax, 2)
    purchase.grand_total = round(grand, 2)


def _shape_purchase(p: PharmacyPurchase, db: Session) -> PurchaseOut:
    items_out: List[PurchaseItemOut] = []
    for it in p.items:
        med = db.query(Medicine).filter(Medicine.id == it.medicine_id).first()
        items_out.append(PurchaseItemOut(
            id=it.id, medicine_id=it.medicine_id, medicine_name=med.name if med else None,
            batch_number=it.batch_number,
            mrp=it.mrp or 0.0, quantity=it.quantity, free_quantity=it.free_quantity or 0.0,
            purchase_rate=it.purchase_rate, discount_pct=it.discount_pct or 0.0,
            hsn_id=it.hsn_id, tax_amount=it.tax_amount or 0.0,
            line_total=it.line_total or 0.0, inventory_id=it.inventory_id,
        ))
    return PurchaseOut(
        id=p.id, purchase_number=p.purchase_number, entry_date=p.entry_date,
        supplier_id=p.supplier_id, supplier_name=(p.supplier.name if p.supplier else None),
        invoice_number=p.invoice_number, bill_date=p.bill_date,
        payment_type=p.payment_type, purchase_type=p.purchase_type, status=p.status,
        subtotal=p.subtotal or 0.0, total_discount=p.total_discount or 0.0,
        total_tax=p.total_tax or 0.0, grand_total=p.grand_total or 0.0,
        notes=p.notes, items=items_out,
        created_at=p.created_at, confirmed_at=p.confirmed_at,
        revoked_at=p.revoked_at, revoke_reason=p.revoke_reason,
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

    _check_duplicate_invoice(
        db, hospital_id=current_user.hospital_id,
        supplier_id=data.supplier_id, invoice_number=data.invoice_number,
    )

    purchase = PharmacyPurchase(
        purchase_number=_next_purchase_number(db, current_user.hospital_id),
        entry_date=data.entry_date, supplier_id=data.supplier_id,
        invoice_number=data.invoice_number, bill_date=data.bill_date,
        payment_type=data.payment_type, purchase_type=data.purchase_type,
        status="draft", notes=data.notes,
        created_by=current_user.id, hospital_id=current_user.hospital_id,
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
            purchase_rate=item.purchase_rate, discount_pct=item.discount_pct,
            hsn_id=item.hsn_id,
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
    pid: int, data: PurchaseIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "edit_purchase")),
):
    purchase = db.query(PharmacyPurchase).filter(
        PharmacyPurchase.id == pid,
        PharmacyPurchase.hospital_id == current_user.hospital_id,
    ).first()
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")
    if purchase.status != "draft":
        raise HTTPException(status_code=400, detail=f"Cannot edit a {purchase.status} purchase")

    sup = db.query(PharmacySupplier).filter(
        PharmacySupplier.id == data.supplier_id,
        PharmacySupplier.hospital_id == current_user.hospital_id,
    ).first()
    if not sup:
        raise HTTPException(status_code=400, detail="Invalid supplier")

    _check_duplicate_invoice(
        db, hospital_id=current_user.hospital_id,
        supplier_id=data.supplier_id, invoice_number=data.invoice_number,
        exclude_purchase_id=purchase.id,
    )

    purchase.entry_date = data.entry_date
    purchase.supplier_id = data.supplier_id
    purchase.invoice_number = data.invoice_number
    purchase.bill_date = data.bill_date
    purchase.payment_type = data.payment_type
    purchase.purchase_type = data.purchase_type
    purchase.notes = data.notes

    # Replace items wholesale — simpler than diffing and the draft is editable only
    for old in list(purchase.items):
        db.delete(old)
    db.flush()
    for item in data.items:
        db.add(PharmacyPurchaseItem(
            purchase_id=purchase.id, medicine_id=item.medicine_id,
            batch_number=item.batch_number,
            expiry_date=item.expiry_date or _EXPIRY_SENTINEL,
            mrp=item.mrp, quantity=item.quantity, free_quantity=item.free_quantity,
            purchase_rate=item.purchase_rate, discount_pct=item.discount_pct,
            hsn_id=item.hsn_id,
        ))
    db.flush(); db.refresh(purchase)
    _recompute_purchase_totals(purchase, db)
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

    _recompute_purchase_totals(purchase, db)  # safety re-calc

    for item in purchase.items:
        # Merge into an existing inventory row only if the medicine, batch
        # number AND expiry date all match — different expiry means it is
        # physically a different lot even if the manufacturer reused the batch
        # number, so it should be tracked separately for FEFO and write-off.
        item_expiry = item.expiry_date or _EXPIRY_SENTINEL
        existing = db.query(PharmacyInventory).filter(
            PharmacyInventory.medicine_id == item.medicine_id,
            PharmacyInventory.batch_number == item.batch_number,
            PharmacyInventory.expiry_date == item_expiry,
            PharmacyInventory.hospital_id == current_user.hospital_id,
            PharmacyInventory.is_active == True,  # noqa: E712
        ).first()
        added_qty = (item.quantity or 0) + (item.free_quantity or 0)
        # P1.5: drop free portion from per-unit valuation. purchase_rate keeps
        # the gross rate (defaults next purchase); cost_price gets the effective.
        eff_cost = _effective_cost(item.quantity, item.free_quantity, item.purchase_rate)
        if existing:
            existing.quantity_in_stock = (existing.quantity_in_stock or 0) + added_qty
            existing.mrp = item.mrp or existing.mrp
            existing.purchase_rate = item.purchase_rate or existing.purchase_rate
            # P1.4: keep cost_price in sync (was previously only set on insert).
            # P1.5: cost_price = effective cost (drops free portion). Latest-cost
            # policy → newest receipt's effective cost wins.
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
                cost_price=eff_cost, selling_price=item.mrp or item.purchase_rate,
                mrp=item.mrp, purchase_rate=item.purchase_rate,
                free_quantity=item.free_quantity or 0, discount_pct=item.discount_pct,
                hsn_id=item.hsn_id, supplier_id=purchase.supplier_id,
                purchase_id=purchase.id, purchase_date=purchase.entry_date,
                is_active=True, hospital_id=current_user.hospital_id,
            )
            db.add(inv); db.flush()
        item.inventory_id = inv.id

        # Ledger
        db.add(PharmacyStockLedger(
            medicine_id=item.medicine_id, batch_id=inv.id, txn_type="purchase",
            qty_delta=added_qty, reference_type="purchase", reference_id=purchase.id,
            performed_by=current_user.id, hospital_id=current_user.hospital_id,
            notes=f"Confirmed purchase {purchase.purchase_number}",
        ))

        # Push P-Rate + MRP back to medicine master so future purchases default in.
        # P1.3: only update if this purchase's entry_date is at least as recent as
        # the last purchase that touched the master — back-dated entries must not
        # clobber a newer master price.
        med = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
        if med:
            last = med.last_purchase_date
            if last is None or purchase.entry_date >= last:
                if item.purchase_rate:
                    med.purchase_rate = item.purchase_rate
                if item.mrp:
                    med.mrp = item.mrp
                med.last_purchase_date = purchase.entry_date

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
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_purchases")),
):
    q = db.query(PharmacyPurchase).filter(PharmacyPurchase.hospital_id == current_user.hospital_id)
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
    quantity: float = Field(..., gt=0)
    free_quantity: float = 0.0
    batch_id: Optional[int] = None  # explicit batch; if None → FIFO by expiry
    rate: Optional[float] = None    # overrides medicine.rate_a/b if set
    rate_tier: str = Field("A", pattern="^[AB]$")
    discount_pct: float = 0.0
    barcode_scanned: bool = False


class SaleItemOut(BaseModel):
    id: int
    medicine_id: int
    medicine_name: Optional[str] = None
    batch_id: int
    batch_number: Optional[str] = None
    quantity: float
    free_quantity: float
    rate: float
    rate_tier: str
    discount_pct: float
    tax_pct: float
    line_total: float
    barcode_scanned: bool

    class Config: from_attributes = True


class SaleIn(BaseModel):
    payment_type: str = Field("cash", pattern="^(cash|credit)$")
    patient_phone: Optional[str] = None
    patient_ip_id: Optional[str] = None
    patient_name: Optional[str] = None
    patient_address: Optional[str] = None
    doctor_number: Optional[str] = None
    doctor_name: Optional[str] = None
    items: List[SaleItemIn] = Field(..., min_length=1)


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
    status: str
    items: List[SaleItemOut] = Field(default_factory=list)
    created_at: datetime

    class Config: from_attributes = True


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


def _pick_fifo_batches(db: Session, *, medicine_id: int, qty_needed: float, hospital_id: int):
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
    ).order_by(
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
        status=s.status, items=items_out, created_at=s.created_at,
    )


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

    if data.patient_ip_id:
        from app.models.patient import Patient as _IPPatient
        from app.models.inpatient import Admission as _IPAdmission
        pat = db.query(_IPPatient).filter(
            _IPPatient.patient_id == data.patient_ip_id,
            _IPPatient.hospital_id == current_user.hospital_id,
        ).first()
        if not pat:
            raise HTTPException(
                status_code=400,
                detail=f"patient_ip_id {data.patient_ip_id} not found in this hospital",
            )
        active = db.query(_IPAdmission).filter(
            _IPAdmission.patient_id == pat.id,
            _IPAdmission.status == "admitted",
        ).first()
        if not active:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Patient {data.patient_ip_id} has no active admission. "
                    "Leave patient_ip_id blank for OP / walk-in sales."
                ),
            )

    sale = PharmacySale(
        sale_number=_next_sale_number(db, current_user.hospital_id),
        payment_type=data.payment_type,
        patient_phone=data.patient_phone, patient_ip_id=data.patient_ip_id,
        patient_name=data.patient_name, patient_address=data.patient_address,
        doctor_number=data.doctor_number, doctor_name=data.doctor_name,
        status="completed", created_by=current_user.id,
        hospital_id=current_user.hospital_id,
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

    subtotal = 0.0
    disc_total = 0.0
    tax_total = 0.0
    grand = 0.0

    for line in data.items:
        med = db.query(Medicine).filter(
            Medicine.id == line.medicine_id,
            Medicine.hospital_id == current_user.hospital_id,
            Medicine.is_active == True,  # noqa: E712
        ).first()
        if not med:
            raise HTTPException(status_code=400, detail=f"Invalid medicine_id {line.medicine_id}")

        # Determine effective rate
        rate = line.rate if line.rate is not None else (
            med.rate_b if line.rate_tier == "B" else med.rate_a
        )
        if not rate:
            # Fall back to legacy unit_price if no tiered rate is set
            rate = med.unit_price or 0.0
        if rate <= 0:
            raise HTTPException(status_code=400,
                                detail=f"No price set on medicine {med.name}")

        # P3.7: surface stacking instead of silently clamping at 100. The user
        # can either lower their line discount or unset the medicine-level one.
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
        igst_snap = (hsn_row.igst_pct or 0) if hsn_row else 0.0
        tax_pct = sgst_snap + cgst_snap + igst_snap

        # Resolve batch(es): explicit batch_id or FIFO across as many as needed
        picks = []
        qty_needed = float(line.quantity)
        if line.batch_id:
            # P3.2: lock the batch row during this sale.
            batch = db.query(PharmacyInventory).filter(
                PharmacyInventory.id == line.batch_id,
                PharmacyInventory.hospital_id == current_user.hospital_id,
                PharmacyInventory.is_active == True,  # noqa: E712
            ).with_for_update().first()
            if not batch:
                raise HTTPException(status_code=400, detail=f"Invalid batch_id {line.batch_id}")
            if (batch.quantity_in_stock or 0) < qty_needed:
                raise HTTPException(status_code=400,
                                    detail=f"Batch {batch.batch_number} has only {batch.quantity_in_stock}, need {qty_needed}")
            picks.append((batch, qty_needed))
        else:
            picks = _pick_fifo_batches(
                db, medicine_id=med.id, qty_needed=qty_needed,
                hospital_id=current_user.hospital_id,
            )

        # P3.8: distribute free_quantity across picked batches so that the per-
        # batch portions sum to free_total exactly. Rounding each portion to 2dp
        # independently used to drift by ±0.01 across batches.
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

        for (batch, take_qty), free_for_batch in zip(picks, free_alloc):
            base = take_qty * rate
            base_after_disc = base * (1 - disc / 100.0)
            # P3.9: include free portion in taxable base when the hospital opts in.
            if tax_on_free and free_for_batch:
                base_after_disc += free_for_batch * rate * (1 - disc / 100.0)
            tax_amt = base_after_disc * (tax_pct / 100.0)
            line_total = round(base_after_disc + tax_amt, 2)

            item_row = PharmacySaleItem(
                sale_id=sale.id, medicine_id=med.id, batch_id=batch.id,
                quantity=take_qty, free_quantity=free_for_batch,
                rate=rate, rate_tier=line.rate_tier,
                discount_pct=disc, tax_pct=tax_pct,
                sgst_pct=sgst_snap, cgst_pct=cgst_snap, igst_pct=igst_snap,
                line_total=line_total, barcode_scanned=line.barcode_scanned,
            )
            db.add(item_row)

            # Deduct inventory + ledger
            batch.quantity_in_stock = (batch.quantity_in_stock or 0) - take_qty - free_for_batch
            db.add(PharmacyStockLedger(
                medicine_id=med.id, batch_id=batch.id, txn_type="sale",
                qty_delta=-(take_qty + free_for_batch),
                reference_type="sale", reference_id=sale.id,
                performed_by=current_user.id, hospital_id=current_user.hospital_id,
                notes=f"Sale {sale.sale_number}",
            ))

            subtotal += base
            disc_total += base - base_after_disc
            tax_total += tax_amt
            grand += line_total

    sale.subtotal = round(subtotal, 2)
    sale.discount_total = round(disc_total, 2)
    sale.tax_total = round(tax_total, 2)
    sale.grand_total = round(grand, 2)
    db.commit(); db.refresh(sale)
    _audit(db, current_user, "create_sale", "pharmacy_sale", sale.id,
           f"Created sale {sale.sale_number} (₹{sale.grand_total})")
    return _shape_sale(sale, db)


@router.get("/sales", response_model=List[SaleOut])
def list_sales(
    status: Optional[str] = None,
    payment_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    search: Optional[str] = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_sales")),
):
    q = db.query(PharmacySale).filter(PharmacySale.hospital_id == current_user.hospital_id)
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

    P3.5: rejects sales older than `hospital.pharmacy_void_window_days` (when > 0)
    unless the caller also has the `void_sale_legacy` permission.

    POS sales never appear on an inpatient bill — `_persist_bill()` in
    routes/inpatient.py only emits BillItem rows from Prescription records, not
    from PharmacySale. So voiding a POS sale (even one with `patient_ip_id`
    set) does not need to touch any inpatient bill. The audit log still flags
    the IP linkage for human reconciliation in case the patient's counter
    purchase was being tracked off-bill.

    For Rx-driven dispenses against an admitted patient, use the Rx cancel
    flow (POST /api/pharmacy/prescriptions/{id}/cancel) — that path is wired
    to reverse stock AND issue a credit-note when the bill is locked.
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

    sale.status = "voided"
    sale.voided_by = current_user.id
    sale.voided_at = datetime.now()
    sale.void_reason = data.reason
    db.commit(); db.refresh(sale)

    # POS sales aren't on inpatient bills (only Prescriptions are), so there
    # is no IP bill line to reverse here. Still log the IP tag so the floor
    # team can reconcile if the patient was tracking the counter purchase.
    ip_note = f" (IP linkage: {sale.patient_ip_id} — POS sale, not on IP bill)" if sale.patient_ip_id else ""
    _audit(db, current_user, "void_sale", "pharmacy_sale", sale.id,
           f"Voided sale {sale.sale_number}: {data.reason}{ip_note}")
    return _shape_sale(sale, db)


# ============================================================================
# Rx-linked dispensing (Section G)
# ----------------------------------------------------------------------------
# Reuses existing Prescription / PrescriptionItem models. NOT integrated with
# inpatient billing (no Prescription.inpatient_bill_id wiring) — that's a
# later phase.
# ============================================================================

class PendingRxItemOut(BaseModel):
    item_id: int
    medicine_id: int
    medicine_name: Optional[str] = None
    quantity_prescribed: float
    quantity_dispensed: float
    quantity_remaining: float
    dosage: Optional[str] = None
    duration: Optional[str] = None
    status: str


class PendingRxOut(BaseModel):
    id: int
    prescription_number: str
    prescription_date: datetime
    status: str
    notes: Optional[str] = None
    items: List[PendingRxItemOut] = Field(default_factory=list)


@router.get("/prescriptions/pending", response_model=List[PendingRxOut])
def list_pending_prescriptions(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_dispense_queue")),
):
    """List prescriptions awaiting (full or partial) dispensing."""
    rxs = db.query(Prescription).filter(
        Prescription.status.in_(["pending", "partial"]),
    ).order_by(Prescription.prescription_date.desc()).limit(limit).all()

    out = []
    for rx in rxs:
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
                dosage=it.dosage, duration=it.duration, status=it.status or "pending",
            ))
        out.append(PendingRxOut(
            id=rx.id, prescription_number=rx.prescription_number,
            prescription_date=rx.prescription_date, status=rx.status,
            notes=rx.notes, items=items,
        ))
    return out


class DispenseItemIn(BaseModel):
    item_id: int                     # PrescriptionItem.id
    quantity: float = Field(..., gt=0)
    batch_id: Optional[int] = None  # FIFO if None


class DispenseIn(BaseModel):
    items: List[DispenseItemIn] = Field(..., min_length=1)
    notes: Optional[str] = None


class DispenseLineOut(BaseModel):
    item_id: int
    medicine_id: int
    medicine_name: Optional[str] = None
    batch_id: int
    batch_number: Optional[str] = None
    quantity: float


class DispenseResultOut(BaseModel):
    prescription_id: int
    prescription_number: str
    status: str
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

    lines_out: List[DispenseLineOut] = []
    for req in data.items:
        rxi = db.query(PrescriptionItem).filter(
            PrescriptionItem.id == req.item_id,
            PrescriptionItem.prescription_id == rx.id,
        ).first()
        if not rxi:
            raise HTTPException(status_code=400, detail=f"Item {req.item_id} not on Rx {rx.id}")
        remaining = float((rxi.quantity_prescribed or 0) - (rxi.quantity_dispensed or 0))
        if req.quantity > remaining:
            raise HTTPException(status_code=400,
                                detail=f"Item {rxi.id}: cannot dispense {req.quantity} — only {remaining} remaining")

        # Resolve batch picks: explicit or FIFO
        if req.batch_id:
            # P3.2: lock the batch row for the duration of this dispense.
            batch = db.query(PharmacyInventory).filter(
                PharmacyInventory.id == req.batch_id,
                PharmacyInventory.hospital_id == current_user.hospital_id,
                PharmacyInventory.is_active == True,  # noqa: E712
            ).with_for_update().first()
            if not batch:
                raise HTTPException(status_code=400, detail=f"Invalid batch_id {req.batch_id}")
            if (batch.quantity_in_stock or 0) < req.quantity:
                raise HTTPException(status_code=400,
                                    detail=f"Batch {batch.batch_number} has only {batch.quantity_in_stock}")
            picks = [(batch, req.quantity)]
        else:
            picks = _pick_fifo_batches(
                db, medicine_id=rxi.medicine_id, qty_needed=req.quantity,
                hospital_id=current_user.hospital_id,
            )

        med = db.query(Medicine).filter(Medicine.id == rxi.medicine_id).first()
        for batch, take in picks:
            batch.quantity_in_stock = (batch.quantity_in_stock or 0) - take
            db.add(PharmacyStockLedger(
                medicine_id=rxi.medicine_id, batch_id=batch.id, txn_type="rx_dispense",
                qty_delta=-take, reference_type="prescription", reference_id=rx.id,
                performed_by=current_user.id, hospital_id=current_user.hospital_id,
                notes=f"Dispensed Rx {rx.prescription_number} item #{rxi.id}",
            ))
            lines_out.append(DispenseLineOut(
                item_id=rxi.id, medicine_id=rxi.medicine_id,
                medicine_name=med.name if med else None,
                batch_id=batch.id, batch_number=batch.batch_number, quantity=take,
            ))

        rxi.quantity_dispensed = (rxi.quantity_dispensed or 0) + req.quantity
        if rxi.quantity_dispensed >= (rxi.quantity_prescribed or 0):
            rxi.status = "dispensed"
        else:
            rxi.status = "partial"

    # Recompute overall Rx status
    db.flush()
    all_items = db.query(PrescriptionItem).filter(PrescriptionItem.prescription_id == rx.id).all()
    if all(i.status == "dispensed" for i in all_items):
        rx.status = "dispensed"
        rx.dispensed_by_id = current_user.id
        rx.dispensed_date = datetime.now()
    else:
        rx.status = "partial"

    db.commit(); db.refresh(rx)
    _audit(db, current_user, "dispense_rx", "prescription", rx.id,
           f"Dispensed against Rx {rx.prescription_number} ({len(lines_out)} batch lines)",
           details={"notes": data.notes} if data.notes else None)
    return DispenseResultOut(
        prescription_id=rx.id, prescription_number=rx.prescription_number,
        status=rx.status, lines=lines_out,
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())
    hid = current_user.hospital_id

    sales_q = db.query(
        sa_func.coalesce(sa_func.sum(PharmacySale.grand_total), 0),
        sa_func.count(PharmacySale.id),
    ).filter(
        PharmacySale.hospital_id == hid, PharmacySale.status == "completed",
        PharmacySale.sale_date >= today_start, PharmacySale.sale_date <= today_end,
    ).one()

    purchases_q = db.query(
        sa_func.coalesce(sa_func.sum(PharmacyPurchase.grand_total), 0),
        sa_func.count(PharmacyPurchase.id),
    ).filter(
        PharmacyPurchase.hospital_id == hid,
        PharmacyPurchase.status == "confirmed",
        PharmacyPurchase.entry_date == date.today(),
    ).one()

    # Reuse the live inventory queries
    low = sum(1 for r in list_inventory(search=None, low_only=True, db=db, current_user=current_user))
    pending = db.query(Prescription).filter(Prescription.status.in_(["pending", "partial"])).count()

    today = date.today()
    expiring_threshold = today + timedelta(days=90)
    expiring_soon = db.query(sa_func.count(PharmacyInventory.id)).filter(
        PharmacyInventory.hospital_id == hid,
        PharmacyInventory.is_active == True,  # noqa: E712
        PharmacyInventory.quantity_in_stock > 0,
        PharmacyInventory.expiry_date <= expiring_threshold,
        PharmacyInventory.expiry_date < _EXPIRY_SENTINEL,
    ).scalar() or 0
    already_expired = db.query(sa_func.count(PharmacyInventory.id)).filter(
        PharmacyInventory.hospital_id == hid,
        PharmacyInventory.is_active == True,  # noqa: E712
        PharmacyInventory.quantity_in_stock > 0,
        PharmacyInventory.expiry_date < today,
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    hid = current_user.hospital_id
    q_sales = db.query(PharmacySale).filter(
        PharmacySale.hospital_id == hid,
        PharmacySale.status == "completed",
    )
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    q = db.query(PharmacyPurchase).filter(
        PharmacyPurchase.hospital_id == current_user.hospital_id,
        PharmacyPurchase.status == "confirmed",
    )
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = db.query(
        Medicine.id, Medicine.medicine_code, Medicine.name,
        sa_func.coalesce(sa_func.sum(PharmacyInventory.quantity_in_stock), 0).label("total"),
        sa_func.count(PharmacyInventory.id).label("batches"),
        sa_func.min(PharmacyInventory.expiry_date).label("nearest"),
        sa_func.coalesce(sa_func.sum(PharmacyInventory.quantity_in_stock * PharmacyInventory.cost_price), 0).label("v_cost"),
        sa_func.coalesce(sa_func.sum(PharmacyInventory.quantity_in_stock * PharmacyInventory.mrp), 0).label("v_mrp"),
    ).outerjoin(
        PharmacyInventory, (PharmacyInventory.medicine_id == Medicine.id) & (PharmacyInventory.is_active == True),  # noqa: E712
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_narcotic_register")),
):
    """All sale lines for medicines flagged as narcotic / Schedule H / H1 / Tramadol / controlled.

    P2.2: voided sales remain on the register (with status='voided') — controlled
    substance compliance requires every movement be visible.
    """
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

    q = db.query(PharmacySale).filter(
        PharmacySale.hospital_id == current_user.hospital_id,
        PharmacySale.sale_date >= start,
        PharmacySale.sale_date <= end,
    )
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    """Realized gross margin per medicine or per day.

    revenue = sum(quantity * rate * (1 - discount_pct/100))
    cost    = sum(quantity * batch.cost_price)
    margin  = revenue - cost; margin_pct = margin / revenue.

    Voided sales are excluded.
    """
    q = db.query(PharmacySaleItem, PharmacySale, PharmacyInventory).join(
        PharmacySale, PharmacySale.id == PharmacySaleItem.sale_id,
    ).outerjoin(
        PharmacyInventory, PharmacyInventory.id == PharmacySaleItem.batch_id,
    ).filter(
        PharmacySale.hospital_id == current_user.hospital_id,
        PharmacySale.status == "completed",
    )
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    """Per-medicine sales velocity over the last `days` days, classified ABC
    by Pareto on revenue (top 80% revenue → A, next 15% → B, bottom 5% → C).
    """
    window_start = datetime.now() - timedelta(days=days)
    rows = db.query(PharmacySaleItem, PharmacySale).join(
        PharmacySale, PharmacySale.id == PharmacySaleItem.sale_id,
    ).filter(
        PharmacySale.hospital_id == current_user.hospital_id,
        PharmacySale.status == "completed",
        PharmacySale.sale_date >= window_start,
    ).all()

    by_med: dict = {}
    for it, s in rows:
        b = by_med.setdefault(it.medicine_id, {"qty": 0.0, "rev": 0.0})
        base = float(it.quantity or 0) * float(it.rate or 0)
        b["qty"] += float(it.quantity or 0)
        b["rev"] += base * (1 - float(it.discount_pct or 0) / 100.0)

    # Stock on hand per medicine, including the ones with zero sales (for slow movers).
    stock_map: dict = {}
    name_map: dict = {}
    for mid, name, stock in db.query(
        Medicine.id, Medicine.name,
        sa_func.coalesce(sa_func.sum(PharmacyInventory.quantity_in_stock), 0),
    ).outerjoin(
        PharmacyInventory, (PharmacyInventory.medicine_id == Medicine.id) & (PharmacyInventory.is_active == True),  # noqa: E712
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
    buf = pdf_service.generate_pharmacy_sale_invoice_pdf(shaped, hi, include_header=get_hospital_pdf_include_header(db, current_user.hospital_id))
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
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    buf = pdf_service.generate_pharmacy_purchase_pdf(shaped, hi, include_header=get_hospital_pdf_include_header(db, current_user.hospital_id))
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
        "lines": lines,
        "notes": rx.notes,
    }
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    buf = pdf_service.generate_pharmacy_dispense_slip_pdf(data, hi, include_header=get_hospital_pdf_include_header(db, current_user.hospital_id))
    return _pdf_response(buf, f"dispense_{rx.prescription_number}.pdf")


@router.get("/reports/narcotic-register/pdf")
def narcotic_register_pdf(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_narcotic_register")),
):
    rows = narcotic_register(date_from=date_from, date_to=date_to,
                             db=db, current_user=current_user)
    hi = _hospital_info_for_pdf(db, current_user.hospital_id)
    period = {
        "from": date_from.isoformat() if date_from else None,
        "to": date_to.isoformat() if date_to else None,
    }
    # Convert Pydantic rows → plain dicts for the generator
    row_dicts = [r.model_dump() for r in rows]
    buf = pdf_service.generate_narcotic_register_pdf(row_dicts, period, hi, include_header=get_hospital_pdf_include_header(db, current_user.hospital_id))
    return _pdf_response(buf, "narcotic_register.pdf")


# ============================================================================
# Phase-2 report PDFs — all go through the generic tabular generator.
# ============================================================================

def _report_period(date_from: Optional[date], date_to: Optional[date]) -> dict:
    return {
        "from": date_from.isoformat() if date_from else None,
        "to": date_to.isoformat() if date_to else None,
    }


@router.get("/reports/sales/pdf")
def sales_report_pdf(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    group_by: str = Query("day", pattern="^(day|medicine|doctor|payment_type)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = sales_report(date_from=date_from, date_to=date_to, group_by=group_by,
                        db=db, current_user=current_user)
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
        hospital_info=hi, include_header=get_hospital_pdf_include_header(db, current_user.hospital_id),
        meta={"Group by": group_by},
    )
    return _pdf_response(buf, "pharmacy_sales.pdf")


@router.get("/reports/purchases/pdf")
def purchases_report_pdf(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    supplier_id: Optional[int] = None,
    group_by: str = Query("day", pattern="^(day|supplier)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = purchases_report(date_from=date_from, date_to=date_to,
                            supplier_id=supplier_id, group_by=group_by,
                            db=db, current_user=current_user)
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
        hospital_info=hi, include_header=get_hospital_pdf_include_header(db, current_user.hospital_id),
        meta={"Group by": group_by},
    )
    return _pdf_response(buf, "pharmacy_purchases.pdf")


@router.get("/reports/stock-on-hand/pdf")
def stock_on_hand_pdf(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = stock_on_hand_report(db=db, current_user=current_user)
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
        hospital_info=hi, include_header=get_hospital_pdf_include_header(db, current_user.hospital_id),
    )
    return _pdf_response(buf, "pharmacy_stock.pdf")


@router.get("/reports/tax-summary/pdf")
def tax_summary_pdf(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = tax_summary_report(date_from=date_from, date_to=date_to,
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
        hospital_info=hi, include_header=get_hospital_pdf_include_header(db, current_user.hospital_id),
    )
    return _pdf_response(buf, "pharmacy_tax_summary.pdf")


@router.get("/reports/daily-closeout/pdf")
def daily_closeout_pdf(
    date: Optional[date] = None,
    cashier_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = daily_closeout_report(date=date, cashier_id=cashier_id,
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
        hospital_info=hi, include_header=get_hospital_pdf_include_header(db, current_user.hospital_id),
    )
    return _pdf_response(buf, f"closeout_{the_day}.pdf")


@router.get("/reports/margin/pdf")
def margin_report_pdf(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    group_by: str = Query("day", pattern="^(day|medicine)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = margin_report(date_from=date_from, date_to=date_to, group_by=group_by,
                         db=db, current_user=current_user)
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
        hospital_info=hi, include_header=get_hospital_pdf_include_header(db, current_user.hospital_id),
        meta={"Group by": group_by},
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
        hospital_info=hi, include_header=get_hospital_pdf_include_header(db, current_user.hospital_id),
        meta={"Note": "Interim — payments tracking ships in P4.2"},
    )
    return _pdf_response(buf, "supplier_aging.pdf")


@router.get("/reports/movement/pdf")
def movement_report_pdf(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "view_reports")),
):
    rows = movement_report(days=days, db=db, current_user=current_user)
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
        hospital_info=hi, include_header=get_hospital_pdf_include_header(db, current_user.hospital_id),
    )
    return _pdf_response(buf, "pharmacy_movement.pdf")
