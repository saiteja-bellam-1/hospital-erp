"""Pharmacy bulk import/export routes (included under /api/pharmacy)."""
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "manage_medicines")),
):
    content, filename = await _read_upload(file)
    on_duplicate = _normalize_on_duplicate(on_duplicate)
    summary = import_medicines(
        db, current_user, content, filename, dry_run=dry_run, on_duplicate=on_duplicate,
    )
    summary["dry_run"] = dry_run
    return _finalize_import(db, current_user, summary, action="import_pharmacy_medicines", resource_type="medicine")


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


@router.post("/purchases/import", response_model=PharmacyImportSummary)
async def purchases_import(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
    on_duplicate: str = Form("skip"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_feature_permission(Modules.PHARMACY, "create_purchase")),
):
    content, filename = await _read_upload(file)
    on_duplicate = _normalize_on_duplicate(on_duplicate)
    summary = import_purchases(
        db, current_user, content, filename, dry_run=dry_run, on_duplicate=on_duplicate,
    )
    summary["dry_run"] = dry_run
    return _finalize_import(
        db, current_user, summary,
        action="import_pharmacy_purchases", resource_type="pharmacy_purchase",
    )
