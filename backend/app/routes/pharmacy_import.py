"""Pharmacy bulk import/export routes (included under /api/pharmacy)."""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.pharmacy import Medicine, PharmacyPurchaseImportMapping
from app.models.user import User
from app.services.audit_service import log_action
from app.services.pharmacy_import import (
    build_masters_template,
    build_medicines_template,
    build_opening_stock_template,
    build_purchases_template,
    build_suppliers_template,
    export_masters_xlsx,
    export_medicines_xlsx,
    export_opening_stock_xlsx,
    export_suppliers_xlsx,
    import_masters,
    import_medicines,
    import_opening_stock,
    import_purchases,
    import_suppliers,
    inspect_medicines_import,
    inspect_purchase_import,
    upsert_medicine_import_alias,
)
from app.services.pharmacy_sales_import import (
    build_sales_template,
    import_sales,
    inspect_sales_import,
)
from app.utils.auth import Modules
from app.utils.dependencies import require_feature_permission, require_feature_permission_any
from config.database import get_db

router = APIRouter()


class PharmacyImportRowError(BaseModel):
    sheet: str = ""
    row: int = 0
    message: str


class PharmacyImportPreviewRow(BaseModel):
    row: int = 0
    key: str = ""
    name: str = ""
    status: str
    message: str = ""
    sheet: str = ""


class PurchaseImportFormItem(BaseModel):
    medicine_id: Optional[int] = None
    medicine_name: str = ""
    medicine_code: str = ""
    batch_number: str = ""
    expiry_date: Optional[str] = None
    mrp: float = 0
    quantity: float = 0
    free_quantity: float = 0
    purchase_rate: float = 0
    rate_a: float = 0
    rate_b: float = 0
    strip_conversion_factor: int = 1
    discount_pct: float = 0
    hsn_id: Optional[int] = None


class PurchaseImportFormHeader(BaseModel):
    supplier_id: Optional[int] = None
    invoice_number: str = ""
    entry_date: Optional[str] = None
    bill_date: Optional[str] = None
    payment_type: str = "credit"
    purchase_type: str = "local"
    tax_mode: str = "exclusive"
    notes: Optional[str] = None


class PurchaseImportForm(BaseModel):
    header: PurchaseImportFormHeader
    items: List[PurchaseImportFormItem] = []
    warnings: List[str] = []


class UnmatchedPurchaseMedicine(BaseModel):
    name: str
    medicine_code: Optional[str] = None
    pack_size: Optional[str] = None
    manufacturer: Optional[str] = None
    mrp: Optional[float] = None
    purchase_rate: Optional[float] = None
    hsn_code: Optional[str] = None
    strip_conversion_factor: Optional[int] = None
    row: Optional[int] = None


class PharmacyImportSummary(BaseModel):
    dry_run: bool
    total_rows: int
    created: int
    updated: int
    skipped: int
    error_count: int
    masters_created: List[str] = []
    errors: List[PharmacyImportRowError] = []
    preview: List[PharmacyImportPreviewRow] = []
    form: Optional[PurchaseImportForm] = None
    unmatched_medicines: List[UnmatchedPurchaseMedicine] = []


class PurchaseImportMappingIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    column_mapping: dict
    format_hint: Optional[str] = None
    default_row_start: Optional[int] = None
    default_row_end: Optional[int] = None


class PurchaseImportMappingOut(BaseModel):
    id: int
    name: str
    column_mapping: dict
    format_hint: Optional[str] = None
    default_row_start: Optional[int] = None
    default_row_end: Optional[int] = None

    class Config:
        from_attributes = True


def _xlsx_response(data: bytes, filename: str) -> StreamingResponse:
    import io
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _finalize_import(
    db: Session, user: User, summary: dict, *, action: str, resource_type: str,
) -> PharmacyImportSummary:
    dry_run = summary["dry_run"]
    if dry_run:
        db.rollback()
    else:
        db.commit()
        try:
            log_action(
                db, user, action, "pharmacy", resource_type, None,
                description=(
                    f"Pharmacy import: {summary['created']} created, "
                    f"{summary['updated']} updated, {summary['skipped']} skipped"
                ),
                details={
                    "created": summary["created"],
                    "updated": summary["updated"],
                    "skipped": summary["skipped"],
                    "error_count": summary["error_count"],
                    "masters_created": summary.get("masters_created", []),
                },
            )
        except Exception:
            pass
    return PharmacyImportSummary(**summary)


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    return content, file.filename or ""


def _normalize_on_duplicate(on_duplicate: str) -> str:
    if on_duplicate not in ("skip", "update"):
        return "skip"
    return on_duplicate


def _parse_column_mapping(raw: str) -> Optional[dict]:
    import json
    if not raw or not str(raw).strip():
        return None
    try:
        mapping = json.loads(raw)
        if not isinstance(mapping, dict):
            raise ValueError("column_mapping must be a JSON object")
        return mapping
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid column_mapping: {exc}") from exc


def _parse_name_aliases(raw: str) -> Optional[dict]:
    import json
    if not raw or not str(raw).strip():
        return None
    try:
        aliases = json.loads(raw)
        if not isinstance(aliases, dict):
            raise ValueError("name_aliases must be a JSON object")
        return aliases
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid name_aliases: {exc}") from exc


_VALID_IMPORT_KINDS = ("purchases", "medicines", "sales")


def _mapping_kind_clause(kind: str):
    if kind == "purchases":
        return or_(
            PharmacyPurchaseImportMapping.import_kind == "purchases",
            PharmacyPurchaseImportMapping.import_kind.is_(None),
        )
    return PharmacyPurchaseImportMapping.import_kind == kind


def _list_import_mappings(db: Session, hospital_id: int, kind: str):
    if kind not in _VALID_IMPORT_KINDS:
        raise HTTPException(status_code=400, detail="Invalid import mapping kind")
    return (
        db.query(PharmacyPurchaseImportMapping)
        .filter(
            PharmacyPurchaseImportMapping.hospital_id == hospital_id,
            _mapping_kind_clause(kind),
        )
        .order_by(PharmacyPurchaseImportMapping.name.asc())
        .all()
    )


def _save_import_mapping(
    db: Session, user: User, data: PurchaseImportMappingIn, kind: str,
) -> PharmacyPurchaseImportMapping:
    if kind not in _VALID_IMPORT_KINDS:
        raise HTTPException(status_code=400, detail="Invalid import mapping kind")
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Mapping name is required")
    if not isinstance(data.column_mapping, dict) or not data.column_mapping:
        raise HTTPException(status_code=400, detail="column_mapping is required")

    existing = db.query(PharmacyPurchaseImportMapping).filter(
        PharmacyPurchaseImportMapping.hospital_id == user.hospital_id,
        PharmacyPurchaseImportMapping.name == name,
        _mapping_kind_clause(kind),
    ).first()
    if existing:
        existing.column_mapping = data.column_mapping
        existing.format_hint = data.format_hint
        existing.default_row_start = data.default_row_start
        existing.default_row_end = data.default_row_end
        existing.import_kind = kind
        row = existing
    else:
        row = PharmacyPurchaseImportMapping(
            name=name,
            column_mapping=data.column_mapping,
            format_hint=data.format_hint,
            import_kind=kind,
            default_row_start=data.default_row_start,
            default_row_end=data.default_row_end,
            hospital_id=user.hospital_id,
            created_by=user.id,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _delete_import_mapping(db: Session, hospital_id: int, mapping_id: int, kind: str) -> None:
    row = db.query(PharmacyPurchaseImportMapping).filter(
        PharmacyPurchaseImportMapping.id == mapping_id,
        PharmacyPurchaseImportMapping.hospital_id == hospital_id,
        _mapping_kind_clause(kind),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Mapping not found")
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# Medicines
# ---------------------------------------------------------------------------

@router.get("/medicines/import/template")
def medicines_import_template(
    current_user: User = Depends(require_feature_permission_any(
        Modules.PHARMACY, "view_catalog", "manage_medicines",
    )),
):
    return _xlsx_response(build_medicines_template(), "pharmacy_medicines_import_template.xlsx")


@router.post("/medicines/import", response_model=PharmacyImportSummary)
async def medicines_import(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    on_duplicate: str = Form("skip"),
    column_mapping: str = Form(""),
    row_start: Optional[int] = Form(None),
    row_end: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_medicines")),
):
    content, filename = await _read_upload(file)
    on_duplicate = _normalize_on_duplicate(on_duplicate)
    mapping = _parse_column_mapping(column_mapping)
    if row_start is not None and row_end is not None and int(row_start) > int(row_end):
        raise HTTPException(status_code=400, detail="row_start cannot be greater than row_end")
    summary = import_medicines(
        db, current_user, content, filename,
        dry_run=dry_run, on_duplicate=on_duplicate,
        column_mapping=mapping, row_start=row_start, row_end=row_end,
    )
    summary["dry_run"] = dry_run
    return _finalize_import(db, current_user, summary, action="import_pharmacy_medicines", resource_type="medicine")


@router.post("/medicines/import/inspect")
async def medicines_import_inspect(
    file: UploadFile = File(...),
    row_start: Optional[int] = Form(None),
    row_end: Optional[int] = Form(None),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_medicines")),
):
    content, filename = await _read_upload(file)
    if row_start is not None and row_end is not None and int(row_start) > int(row_end):
        raise HTTPException(status_code=400, detail="row_start cannot be greater than row_end")
    return inspect_medicines_import(
        content, filename, row_start=row_start, row_end=row_end,
    )


@router.get("/medicines/import/mappings", response_model=List[PurchaseImportMappingOut])
def list_medicine_import_mappings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission_any(
        Modules.PHARMACY, "view_catalog", "manage_medicines",
    )),
):
    return _list_import_mappings(db, current_user.hospital_id, "medicines")


@router.post("/medicines/import/mappings", response_model=PurchaseImportMappingOut, status_code=201)
def save_medicine_import_mapping(
    data: PurchaseImportMappingIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_medicines")),
):
    return _save_import_mapping(db, current_user, data, "medicines")


@router.delete("/medicines/import/mappings/{mapping_id}", status_code=204)
def delete_medicine_import_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_medicines")),
):
    _delete_import_mapping(db, current_user.hospital_id, mapping_id, "medicines")
    return None


@router.get("/medicines/export/xlsx")
def medicines_export_xlsx(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission_any(
        Modules.PHARMACY, "view_catalog", "manage_medicines",
    )),
):
    data = export_medicines_xlsx(db, current_user.hospital_id)
    return _xlsx_response(data, "pharmacy_medicines_export.xlsx")


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------

@router.get("/suppliers/import/template")
def suppliers_import_template(
    current_user: User = Depends(require_feature_permission_any(
        Modules.PHARMACY, "view_catalog", "manage_suppliers",
    )),
):
    return _xlsx_response(build_suppliers_template(), "pharmacy_suppliers_import_template.xlsx")


@router.post("/suppliers/import", response_model=PharmacyImportSummary)
async def suppliers_import(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    on_duplicate: str = Form("skip"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_suppliers")),
):
    content, filename = await _read_upload(file)
    on_duplicate = _normalize_on_duplicate(on_duplicate)
    summary = import_suppliers(
        db, current_user, content, filename, dry_run=dry_run, on_duplicate=on_duplicate,
    )
    summary["dry_run"] = dry_run
    return _finalize_import(db, current_user, summary, action="import_pharmacy_suppliers", resource_type="pharmacy_supplier")


@router.get("/suppliers/export/xlsx")
def suppliers_export_xlsx(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission_any(
        Modules.PHARMACY, "view_catalog", "manage_suppliers",
    )),
):
    data = export_suppliers_xlsx(db, current_user.hospital_id)
    return _xlsx_response(data, "pharmacy_suppliers_export.xlsx")


# ---------------------------------------------------------------------------
# Masters
# ---------------------------------------------------------------------------

_MASTERS_READ_PERMS = (
    "view_catalog", "manage_medicines", "manage_companies", "manage_categories",
    "manage_salts", "manage_racks", "manage_uoms", "manage_hsn_tax",
)

_MASTERS_IMPORT_PERMS = ("manage_medicines", "manage_companies", "manage_categories")


@router.get("/masters/import/template")
def masters_import_template(
    current_user: User = Depends(require_feature_permission_any(Modules.PHARMACY, *_MASTERS_READ_PERMS)),
):
    return _xlsx_response(build_masters_template(), "pharmacy_masters_import_template.xlsx")


@router.post("/masters/import", response_model=PharmacyImportSummary)
async def masters_import(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    on_duplicate: str = Form("skip"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission_any(Modules.PHARMACY, *_MASTERS_IMPORT_PERMS)),
):
    content, filename = await _read_upload(file)
    on_duplicate = _normalize_on_duplicate(on_duplicate)
    summary = import_masters(
        db, current_user, content, filename, dry_run=dry_run, on_duplicate=on_duplicate,
    )
    summary["dry_run"] = dry_run
    return _finalize_import(db, current_user, summary, action="import_pharmacy_masters", resource_type="pharmacy_master")


@router.get("/masters/export/xlsx")
def masters_export_xlsx(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission_any(Modules.PHARMACY, *_MASTERS_READ_PERMS)),
):
    data = export_masters_xlsx(db, current_user.hospital_id)
    return _xlsx_response(data, "pharmacy_masters_export.xlsx")


# ---------------------------------------------------------------------------
# Opening stock
# ---------------------------------------------------------------------------

@router.get("/opening-stock/import/template")
def opening_stock_import_template(
    current_user: User = Depends(require_feature_permission_any(
        Modules.PHARMACY, "view_inventory", "adjust_stock",
    )),
):
    return _xlsx_response(build_opening_stock_template(), "pharmacy_opening_stock_import_template.xlsx")


@router.post("/opening-stock/import", response_model=PharmacyImportSummary)
async def opening_stock_import(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    on_duplicate: str = Form("skip"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "adjust_stock")),
):
    content, filename = await _read_upload(file)
    on_duplicate = _normalize_on_duplicate(on_duplicate)
    summary = import_opening_stock(
        db, current_user, content, filename, dry_run=dry_run, on_duplicate=on_duplicate,
    )
    summary["dry_run"] = dry_run
    return _finalize_import(db, current_user, summary, action="import_pharmacy_opening_stock", resource_type="pharmacy_inventory")


@router.get("/opening-stock/export/xlsx")
def opening_stock_export_xlsx(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission_any(
        Modules.PHARMACY, "view_inventory", "adjust_stock",
    )),
):
    data = export_opening_stock_xlsx(db, current_user.hospital_id)
    return _xlsx_response(data, "pharmacy_opening_stock_export.xlsx")


# ---------------------------------------------------------------------------
# Purchases
# ---------------------------------------------------------------------------

@router.get("/purchases/import/template")
def purchases_import_template(
    current_user: User = Depends(require_feature_permission_any(
        Modules.PHARMACY, "view_purchases", "create_purchase",
    )),
):
    return _xlsx_response(build_purchases_template(), "pharmacy_purchases_import_template.xlsx")


@router.post("/purchases/import/inspect")
async def purchases_import_inspect(
    file: UploadFile = File(...),
    row_start: Optional[int] = Form(None),
    row_end: Optional[int] = Form(None),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_purchase")),
):
    """Return file column names (from start row), suggested mapping, and targets."""
    content, filename = await _read_upload(file)
    if row_start is not None and row_end is not None and int(row_start) > int(row_end):
        raise HTTPException(status_code=400, detail="row_start cannot be greater than row_end")
    return inspect_purchase_import(
        content, filename,
        row_start=row_start,
        row_end=row_end,
    )


@router.get("/purchases/import/mappings", response_model=List[PurchaseImportMappingOut])
def list_purchase_import_mappings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission_any(
        Modules.PHARMACY, "view_purchases", "create_purchase",
    )),
):
    return _list_import_mappings(db, current_user.hospital_id, "purchases")


@router.post("/purchases/import/mappings", response_model=PurchaseImportMappingOut, status_code=201)
def save_purchase_import_mapping(
    data: PurchaseImportMappingIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_purchase")),
):
    return _save_import_mapping(db, current_user, data, "purchases")


@router.delete("/purchases/import/mappings/{mapping_id}", status_code=204)
def delete_purchase_import_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_purchase")),
):
    _delete_import_mapping(db, current_user.hospital_id, mapping_id, "purchases")
    return None


class PurchaseImportAliasIn(BaseModel):
    alias: str = Field(..., min_length=1, max_length=200)
    medicine_id: int


@router.post("/purchases/import/aliases")
def save_purchase_import_alias(
    data: PurchaseImportAliasIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission_any(
        Modules.PHARMACY, "create_purchase", "manage_medicines",
    )),
):
    med = db.query(Medicine).filter(
        Medicine.id == data.medicine_id,
        Medicine.hospital_id == current_user.hospital_id,
        Medicine.is_active == True,  # noqa: E712
    ).first()
    if not med:
        raise HTTPException(status_code=404, detail="Medicine not found")
    row = upsert_medicine_import_alias(
        db, current_user.hospital_id, med.id, data.alias,
    )
    db.commit()
    return {
        "id": row.id,
        "alias": row.alias_name,
        "medicine_id": med.id,
        "medicine_name": med.name,
        "medicine_code": med.medicine_code,
    }


@router.post("/purchases/import", response_model=PharmacyImportSummary)
async def purchases_import(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    on_duplicate: str = Form("skip"),
    column_mapping: str = Form(""),
    name_aliases: str = Form(""),
    supplier_id: Optional[int] = Form(None),
    invoice_number: str = Form(""),
    entry_date: Optional[str] = Form(None),
    bill_date: Optional[str] = Form(None),
    payment_type: Optional[str] = Form(None),
    row_start: Optional[int] = Form(None),
    row_end: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_purchase")),
):
    content, filename = await _read_upload(file)
    on_duplicate = _normalize_on_duplicate(on_duplicate)
    mapping = _parse_column_mapping(column_mapping)
    aliases = _parse_name_aliases(name_aliases)

    def _parse_opt_date(raw: Optional[str]) -> Optional[date]:
        if not raw or not str(raw).strip():
            return None
        try:
            return date.fromisoformat(str(raw).strip()[:10])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid date '{raw}' (use YYYY-MM-DD)") from exc

    parsed_entry = _parse_opt_date(entry_date)
    parsed_bill = _parse_opt_date(bill_date)
    pay = (payment_type or "").strip().lower() or None
    if pay and pay not in ("cash", "credit"):
        raise HTTPException(status_code=400, detail="payment_type must be cash or credit")
    if row_start is not None and row_end is not None and int(row_start) > int(row_end):
        raise HTTPException(status_code=400, detail="row_start cannot be greater than row_end")

    summary = import_purchases(
        db, current_user, content, filename,
        dry_run=dry_run, on_duplicate=on_duplicate, column_mapping=mapping,
        supplier_id=supplier_id,
        invoice_number=(invoice_number or "").strip() or None,
        entry_date=parsed_entry,
        bill_date=parsed_bill,
        payment_type=pay,
        row_start=row_start,
        row_end=row_end,
        name_aliases=aliases,
    )
    summary["dry_run"] = dry_run
    return _finalize_import(
        db, current_user, summary,
        action="import_pharmacy_purchases", resource_type="pharmacy_purchase",
    )


# ---------------------------------------------------------------------------
# Historical sales
# ---------------------------------------------------------------------------

@router.get("/sales/import/template")
def sales_import_template(
    current_user: User = Depends(require_feature_permission_any(
        Modules.PHARMACY, "view_sales", "create_sale",
    )),
):
    return _xlsx_response(build_sales_template(), "pharmacy_sales_import_template.xlsx")


@router.post("/sales/import", response_model=PharmacyImportSummary)
async def sales_import(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    on_duplicate: str = Form("skip"),
    affect_stock: bool = Form(False),
    column_mapping: str = Form(""),
    row_start: Optional[int] = Form(None),
    row_end: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_sale")),
):
    content, filename = await _read_upload(file)
    on_duplicate = _normalize_on_duplicate(on_duplicate)
    mapping = _parse_column_mapping(column_mapping)
    if row_start is not None and row_end is not None and int(row_start) > int(row_end):
        raise HTTPException(status_code=400, detail="row_start cannot be greater than row_end")
    summary = import_sales(
        db, current_user, content, filename,
        dry_run=dry_run, on_duplicate=on_duplicate, affect_stock=affect_stock,
        column_mapping=mapping, row_start=row_start, row_end=row_end,
    )
    summary["dry_run"] = dry_run
    return _finalize_import(
        db, current_user, summary,
        action="import_pharmacy_sales", resource_type="pharmacy_sale",
    )


@router.post("/sales/import/inspect")
async def sales_import_inspect(
    file: UploadFile = File(...),
    row_start: Optional[int] = Form(None),
    row_end: Optional[int] = Form(None),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_sale")),
):
    content, filename = await _read_upload(file)
    if row_start is not None and row_end is not None and int(row_start) > int(row_end):
        raise HTTPException(status_code=400, detail="row_start cannot be greater than row_end")
    return inspect_sales_import(
        content, filename, row_start=row_start, row_end=row_end,
    )


@router.get("/sales/import/mappings", response_model=List[PurchaseImportMappingOut])
def list_sales_import_mappings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission_any(
        Modules.PHARMACY, "view_sales", "create_sale",
    )),
):
    return _list_import_mappings(db, current_user.hospital_id, "sales")


@router.post("/sales/import/mappings", response_model=PurchaseImportMappingOut, status_code=201)
def save_sales_import_mapping(
    data: PurchaseImportMappingIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_sale")),
):
    return _save_import_mapping(db, current_user, data, "sales")


@router.delete("/sales/import/mappings/{mapping_id}", status_code=204)
def delete_sales_import_mapping(
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_sale")),
):
    _delete_import_mapping(db, current_user.hospital_id, mapping_id, "sales")
    return None
