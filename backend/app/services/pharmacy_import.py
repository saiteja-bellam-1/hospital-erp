"""Pharmacy bulk import/export — medicines, suppliers, masters, opening stock, purchases."""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Callable, Dict, List, Optional, Tuple

import openpyxl
from fastapi import HTTPException
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.pharmacy import (
    Medicine,
    MedicineCategory,
    PharmacyCompany,
    PharmacyHSN,
    PharmacyInventory,
    PharmacyPurchase,
    PharmacyPurchaseItem,
    PharmacyRack,
    PharmacySalt,
    PharmacyStockAdjustment,
    PharmacyStockLedger,
    PharmacyStore,
    PharmacySupplier,
    PharmacyUoM,
)
from app.models.user import User
from app.services.pharmacy_store_service import get_master_store_id
from app.utils.pharmacy_pricing import (
    apply_cost_pcs_from_mrp,
    apply_medicine_price_rounding,
    compute_line_tax,
    round_money,
)

# ---------------------------------------------------------------------------
# Column headers (import / export shape)
# ---------------------------------------------------------------------------

MEDICINE_HEADERS = [
    "medicine_code", "name", "category", "generic_name", "dosage_form", "strength",
    "mrp", "purchase_rate", "rate_a", "rate_b", "unit_price", "default_discount_pct",
    "item_discount_pct", "barcode", "packaging", "strip_conversion_factor", "rate_unit",
    "decimal_supported", "requires_prescription", "is_narcotic", "is_high_alert",
    "is_schedule_h", "is_schedule_h1", "is_tramadol", "is_controlled", "is_active", "is_hidden",
    "min_qty", "max_qty", "reorder_qty", "description", "side_effects", "contraindications",
    "storage_conditions", "manufacturer", "company", "rack_code", "salt", "uom", "hsn_code",
    "sgst_pct", "cgst_pct",
]

SUPPLIER_HEADERS = [
    "name", "mobile", "phone_office", "phone", "email", "address", "pin_code", "state",
    "state_code", "country", "gstin_no", "gstin", "gst_heading", "dl_number", "dl_expiry",
    "pan_number", "contact_person", "designation", "ledger_type", "ledger_category",
    "account_group", "opening_balance", "opening_balance_dr_cr", "is_active", "is_hidden",
    "website", "vat_number", "food_license_no", "narco_sch_h_billing", "bill_import",
    "color_tag", "station", "balancing_method",
]

MASTER_SHEETS: Dict[str, List[str]] = {
    "Categories": ["name", "description", "is_active"],
    "Companies": ["name", "contact", "is_active"],
    "Salts": ["name", "description", "is_active"],
    "Racks": ["code", "location", "description", "is_active"],
    "UoMs": ["name", "abbreviation", "decimal_supported", "is_active"],
    "HSN": ["code", "description", "sgst_pct", "cgst_pct", "igst_pct", "is_active"],
    "Stores": [
        "code", "name", "store_type", "parent_code", "location", "description",
        "can_receive_supplier_purchase", "is_active", "is_default",
    ],
}

OPENING_STOCK_HEADERS = [
    "medicine_code", "batch_number", "expiry_date", "quantity", "store_code",
    "mrp", "purchase_rate", "rate_a", "rate_b", "cost_price", "selling_price",
    "supplier_name", "hsn_code", "strip_conversion_factor", "free_quantity",
    "discount_pct", "notes",
]

# Flat named-header template (one row per line item; header fields repeat).
# Vendor distributor CSVs (H/T/F + CL1..CL31) are also accepted — see
# `_parse_vendor_purchase_blocks`.
PURCHASE_HEADERS = [
    "supplier_name", "invoice_number", "entry_date", "bill_date",
    "payment_type", "purchase_type", "tax_mode", "store_code", "notes",
    "medicine_code", "medicine_name", "batch_number", "expiry_date",
    "quantity", "free_quantity", "mrp", "purchase_rate", "rate_a", "rate_b",
    "strip_conversion_factor", "discount_pct", "pack_size", "hsn_code",
]

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _norm_header(h) -> str:
    if h is None:
        return ""
    return str(h).strip().lower().replace(" ", "_")


def _cell_str(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s != "" else None


def _cell_float(v) -> Optional[float]:
    s = _cell_str(v)
    if s is None:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        raise ValueError(f"'{s}' is not a valid number")


def _cell_int(v) -> Optional[int]:
    f = _cell_float(v)
    if f is None:
        return None
    if f != int(f):
        raise ValueError(f"'{v}' is not a valid integer")
    return int(f)


def _cell_bool(v) -> bool:
    s = (_cell_str(v) or "").lower()
    return s in {"1", "true", "yes", "y"}


def _cell_date(v) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _cell_str(v)
    if s is None:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError as exc:
        raise ValueError(f"'{s}' is not a valid date (use YYYY-MM-DD)") from exc


def _row_is_empty(r) -> bool:
    return not any(c is not None and str(c).strip() != "" for c in r)


def _key_skipped(key: Optional[str]) -> bool:
    return not key or key.startswith("#")


def _read_xlsx_sheet(wb, preferred_names: List[str], *, fallback_first: bool = False) -> List[dict]:
    lower_map = {name.lower(): name for name in wb.sheetnames}
    ws = None
    for pn in preferred_names:
        if pn.lower() in lower_map:
            ws = wb[lower_map[pn.lower()]]
            break
    if ws is None:
        if fallback_first and wb.sheetnames:
            ws = wb[wb.sheetnames[0]]
        else:
            return []
    rows = list(ws.iter_rows(values_only=True))
    header_idx = next((i for i, r in enumerate(rows) if not _row_is_empty(r)), None)
    if header_idx is None:
        return []
    headers = [_norm_header(c) for c in rows[header_idx]]
    out: List[dict] = []
    for j in range(header_idx + 1, len(rows)):
        r = rows[j]
        if _row_is_empty(r):
            continue
        rowdict: dict = {}
        for k, h in enumerate(headers):
            if not h:
                continue
            rowdict[h] = r[k] if k < len(r) else None
        rowdict["_row"] = j + 1
        out.append(rowdict)
    return out


def _parse_xlsx_sheet(content: bytes, sheet_names: List[str], *, fallback_first: bool = False) -> List[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    return _read_xlsx_sheet(wb, sheet_names, fallback_first=fallback_first)


def _parse_xlsx_multi(content: bytes, sheet_name_list: List[str]) -> Dict[str, List[dict]]:
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    return {name: _read_xlsx_sheet(wb, [name]) for name in sheet_name_list}


def _parse_csv_rows(content: bytes) -> List[dict]:
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows: List[dict] = []
    for i, raw in enumerate(reader):
        rowdict = {_norm_header(k): v for k, v in raw.items() if k is not None}
        rowdict["_row"] = i + 2
        rows.append(rowdict)
    return rows


def _parse_upload(content: bytes, filename: str, sheet_names: List[str], *, multi: bool = False):
    fn = (filename or "").lower()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if fn.endswith(".csv"):
        if multi:
            raise HTTPException(status_code=400, detail="CSV supports a single data sheet only. Use .xlsx for multi-sheet imports.")
        return _parse_csv_rows(content)
    if fn.endswith(".xlsx"):
        if multi:
            return _parse_xlsx_multi(content, sheet_name_list=sheet_names)
        return _parse_xlsx_sheet(content, sheet_names, fallback_first=True)
    raise HTTPException(status_code=400, detail="Unsupported file type. Upload a .xlsx or .csv file.")


def _normalize_hsn_tax(sgst_pct: float, cgst_pct: float) -> Tuple[float, float, float]:
    sgst = float(sgst_pct or 0)
    cgst = float(cgst_pct or 0)
    return sgst, cgst, round(sgst + cgst, 4)


def _workbook_bytes(build_fn: Callable[[openpyxl.Workbook], None]) -> bytes:
    wb = openpyxl.Workbook()
    build_fn(wb)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _append_instructions(wb: openpyxl.Workbook, lines: List[str]) -> None:
    if "Instructions" in wb.sheetnames:
        ws = wb["Instructions"]
    else:
        ws = wb.create_sheet("Instructions")
    for line in lines:
        ws.append([line])


def _export_bool(v: bool) -> str:
    return "true" if v else "false"


def _export_date(v: Optional[date]) -> str:
    if v is None:
        return ""
    return v.isoformat()


def _empty_summary(*, dry_run: bool) -> dict:
    return {
        "dry_run": dry_run,
        "total_rows": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "error_count": 0,
        "masters_created": [],
        "errors": [],
        "preview": [],
    }


# ---------------------------------------------------------------------------
# Master resolver (auto-create FK targets during medicine import)
# ---------------------------------------------------------------------------

class _MasterResolver:
    def __init__(self, db: Session, hospital_id: int):
        self.db = db
        self.hospital_id = hospital_id
        self.masters_created: List[str] = []
        self._categories = {
            c.name.strip().lower(): c
            for c in db.query(MedicineCategory).filter(MedicineCategory.hospital_id == hospital_id).all()
        }
        self._companies = {
            c.name.strip().lower(): c
            for c in db.query(PharmacyCompany).filter(PharmacyCompany.hospital_id == hospital_id).all()
        }
        self._salts = {
            s.name.strip().lower(): s
            for s in db.query(PharmacySalt).filter(PharmacySalt.hospital_id == hospital_id).all()
        }
        self._racks = {
            r.code.strip().lower(): r
            for r in db.query(PharmacyRack).filter(PharmacyRack.hospital_id == hospital_id).all()
        }
        self._uoms = {
            u.name.strip().lower(): u
            for u in db.query(PharmacyUoM).filter(PharmacyUoM.hospital_id == hospital_id).all()
        }
        self._hsn: Dict[Tuple[str, float, float], PharmacyHSN] = {}
        for h in db.query(PharmacyHSN).filter(PharmacyHSN.hospital_id == hospital_id).all():
            self._hsn[(h.code.strip().lower(), h.sgst_pct or 0, h.cgst_pct or 0)] = h
        self._hsn_by_code: Dict[str, List[PharmacyHSN]] = {}
        for h in db.query(PharmacyHSN).filter(
            PharmacyHSN.hospital_id == hospital_id,
            PharmacyHSN.is_active == True,  # noqa: E712
        ).all():
            self._hsn_by_code.setdefault(h.code.strip().lower(), []).append(h)

    def _track(self, kind: str, key: str) -> None:
        label = f"{kind}:{key}"
        if label not in self.masters_created:
            self.masters_created.append(label)

    def category(self, name: str) -> MedicineCategory:
        key = name.strip().lower()
        row = self._categories.get(key)
        if row:
            return row
        row = MedicineCategory(name=name.strip(), hospital_id=self.hospital_id, is_active=True)
        self.db.add(row)
        self.db.flush()
        self._categories[key] = row
        self._track("category", name.strip())
        return row

    def company(self, name: str) -> PharmacyCompany:
        key = name.strip().lower()
        row = self._companies.get(key)
        if row:
            return row
        row = PharmacyCompany(name=name.strip(), hospital_id=self.hospital_id, is_active=True)
        self.db.add(row)
        self.db.flush()
        self._companies[key] = row
        self._track("company", name.strip())
        return row

    def salt(self, name: str) -> PharmacySalt:
        key = name.strip().lower()
        row = self._salts.get(key)
        if row:
            return row
        row = PharmacySalt(name=name.strip(), hospital_id=self.hospital_id, is_active=True)
        self.db.add(row)
        self.db.flush()
        self._salts[key] = row
        self._track("salt", name.strip())
        return row

    def rack(self, code: str) -> PharmacyRack:
        key = code.strip().lower()
        row = self._racks.get(key)
        if row:
            return row
        row = PharmacyRack(code=code.strip(), hospital_id=self.hospital_id, is_active=True)
        self.db.add(row)
        self.db.flush()
        self._racks[key] = row
        self._track("rack", code.strip())
        return row

    def uom(self, name: str) -> PharmacyUoM:
        key = name.strip().lower()
        row = self._uoms.get(key)
        if row:
            return row
        row = PharmacyUoM(name=name.strip(), hospital_id=self.hospital_id, is_active=True)
        self.db.add(row)
        self.db.flush()
        self._uoms[key] = row
        self._track("uom", name.strip())
        return row

    def hsn(self, code: str, sgst: Optional[float], cgst: Optional[float]) -> PharmacyHSN:
        code_key = code.strip().lower()
        if sgst is not None or cgst is not None:
            s, c, igst = _normalize_hsn_tax(sgst or 0, cgst or 0)
        else:
            matches = self._hsn_by_code.get(code_key) or []
            if matches:
                return matches[0]
            s, c, igst = 0.0, 0.0, 0.0
        cache_key = (code_key, s, c)
        row = self._hsn.get(cache_key)
        if row:
            return row
        row = PharmacyHSN(
            code=code.strip(), sgst_pct=s, cgst_pct=c, igst_pct=igst,
            hospital_id=self.hospital_id, is_active=True,
        )
        self.db.add(row)
        self.db.flush()
        self._hsn[cache_key] = row
        self._hsn_by_code.setdefault(code_key, []).append(row)
        self._track("hsn", f"{code.strip()}({s}+{c})")
        return row


# ---------------------------------------------------------------------------
# Medicine import / export
# ---------------------------------------------------------------------------

def _find_medicine(db: Session, hospital_id: int, code: str) -> Tuple[Optional[Medicine], Optional[Medicine]]:
    active = db.query(Medicine).filter(
        Medicine.medicine_code == code,
        Medicine.hospital_id == hospital_id,
        Medicine.is_active == True,  # noqa: E712
    ).first()
    inactive = db.query(Medicine).filter(
        Medicine.medicine_code == code,
        Medicine.hospital_id == hospital_id,
        Medicine.is_active == False,  # noqa: E712
    ).first()
    return active, inactive


def _apply_medicine_row(med: Medicine, row: dict, resolver: _MasterResolver) -> None:
    med.name = _cell_str(row.get("name")) or med.name
    cat_name = _cell_str(row.get("category"))
    if cat_name:
        med.category_id = resolver.category(cat_name).id

    for field in (
        "generic_name", "dosage_form", "strength", "description", "side_effects",
        "contraindications", "storage_conditions", "manufacturer", "barcode", "packaging",
    ):
        val = _cell_str(row.get(field))
        if val is not None:
            setattr(med, field, val)

    for field in ("mrp", "purchase_rate", "rate_a", "rate_b", "unit_price",
                  "default_discount_pct", "item_discount_pct"):
        val = _cell_float(row.get(field))
        if val is not None:
            setattr(med, field, val)

    rate_a = med.rate_a or 0
    unit_price = med.unit_price or 0
    if rate_a and not unit_price:
        med.unit_price = rate_a
    elif unit_price and not rate_a:
        med.rate_a = unit_price

    scf = _cell_int(row.get("strip_conversion_factor"))
    if scf is not None:
        med.strip_conversion_factor = max(1, scf)

    rate_unit = (_cell_str(row.get("rate_unit")) or med.rate_unit or "tablet").lower()
    if rate_unit in ("tablet", "strip"):
        med.rate_unit = rate_unit

    for field in (
        "decimal_supported", "requires_prescription", "is_narcotic", "is_high_alert",
        "is_schedule_h", "is_schedule_h1", "is_tramadol", "is_controlled", "is_active", "is_hidden",
    ):
        if row.get(field) is not None and _cell_str(row.get(field)) is not None:
            setattr(med, field, _cell_bool(row.get(field)))

    for field in ("min_qty", "max_qty", "reorder_qty"):
        val = _cell_int(row.get(field))
        if val is not None:
            setattr(med, field, val)

    company_name = _cell_str(row.get("company"))
    if company_name:
        med.company_id = resolver.company(company_name).id

    rack_code = _cell_str(row.get("rack_code"))
    if rack_code:
        med.rack_id = resolver.rack(rack_code).id

    salt_name = _cell_str(row.get("salt"))
    if salt_name:
        med.salt_id = resolver.salt(salt_name).id

    uom_name = _cell_str(row.get("uom"))
    if uom_name:
        med.uom_id = resolver.uom(uom_name).id

    hsn_code = _cell_str(row.get("hsn_code"))
    if hsn_code:
        sgst = _cell_float(row.get("sgst_pct"))
        cgst = _cell_float(row.get("cgst_pct"))
        med.hsn_id = resolver.hsn(hsn_code, sgst, cgst).id

    apply_medicine_price_rounding(med)
    apply_cost_pcs_from_mrp(med)


def import_medicines(
    db: Session, user: User, content: bytes, filename: str,
    *, dry_run: bool, on_duplicate: str,
) -> dict:
    summary = _empty_summary(dry_run=dry_run)
    rows = _parse_upload(content, filename, ["Medicines"])
    hospital_id = user.hospital_id
    resolver = _MasterResolver(db, hospital_id)

    for row in rows:
        rownum = row.get("_row", 0)
        code = _cell_str(row.get("medicine_code"))
        if _key_skipped(code):
            continue
        summary["total_rows"] += 1
        name = _cell_str(row.get("name"))
        category = _cell_str(row.get("category"))
        row_errs: List[str] = []
        if not name:
            row_errs.append("Missing name")
        if not category:
            row_errs.append("Missing category")
        try:
            for f in ("mrp", "purchase_rate", "rate_a", "rate_b", "unit_price",
                      "default_discount_pct", "item_discount_pct", "sgst_pct", "cgst_pct"):
                if row.get(f) is not None and _cell_str(row.get(f)) is not None:
                    _cell_float(row.get(f))
            for f in ("min_qty", "max_qty", "reorder_qty", "strip_conversion_factor"):
                if row.get(f) is not None and _cell_str(row.get(f)) is not None:
                    _cell_int(row.get(f))
        except ValueError as exc:
            row_errs.append(str(exc))

        if row_errs:
            msg = "; ".join(row_errs)
            summary["errors"].append({"sheet": "Medicines", "row": rownum, "message": msg})
            summary["preview"].append({
                "row": rownum, "key": code or "", "name": name or "", "status": "error",
                "message": msg, "sheet": "Medicines",
            })
            continue

        active, inactive = _find_medicine(db, hospital_id, code)
        target = active or inactive

        if active and on_duplicate == "skip":
            summary["skipped"] += 1
            summary["preview"].append({
                "row": rownum, "key": code, "name": name, "status": "skip",
                "message": "Medicine code already exists (active)", "sheet": "Medicines",
            })
            continue

        if target and on_duplicate == "update":
            if not active and inactive:
                inactive.is_active = True
            _apply_medicine_row(target, row, resolver)
            summary["updated"] += 1
            summary["preview"].append({
                "row": rownum, "key": code, "name": name, "status": "update", "sheet": "Medicines",
            })
        elif not target:
            cat = resolver.category(category)
            med = Medicine(
                medicine_code=code, name=name, category_id=cat.id,
                hospital_id=hospital_id, unit_price=0.0,
            )
            _apply_medicine_row(med, row, resolver)
            db.add(med)
            db.flush()
            summary["created"] += 1
            summary["preview"].append({
                "row": rownum, "key": code, "name": name, "status": "new", "sheet": "Medicines",
            })
        else:
            summary["skipped"] += 1
            summary["preview"].append({
                "row": rownum, "key": code, "name": name, "status": "skip",
                "message": "Inactive medicine exists; use on_duplicate=update to reactivate",
                "sheet": "Medicines",
            })

    summary["masters_created"] = resolver.masters_created
    summary["error_count"] = len(summary["errors"])
    return summary


def export_medicines_xlsx(db: Session, hospital_id: int) -> bytes:
    meds = (
        db.query(Medicine)
        .filter(Medicine.hospital_id == hospital_id, Medicine.is_active == True)  # noqa: E712
        .order_by(Medicine.name)
        .all()
    )

    def build(wb: openpyxl.Workbook) -> None:
        ws = wb.active
        ws.title = "Medicines"
        ws.append(MEDICINE_HEADERS)
        for med in meds:
            cat = db.query(MedicineCategory).filter(MedicineCategory.id == med.category_id).first()
            company = db.query(PharmacyCompany).filter(PharmacyCompany.id == med.company_id).first() if med.company_id else None
            rack = db.query(PharmacyRack).filter(PharmacyRack.id == med.rack_id).first() if med.rack_id else None
            salt = db.query(PharmacySalt).filter(PharmacySalt.id == med.salt_id).first() if med.salt_id else None
            uom = db.query(PharmacyUoM).filter(PharmacyUoM.id == med.uom_id).first() if med.uom_id else None
            hsn = db.query(PharmacyHSN).filter(PharmacyHSN.id == med.hsn_id).first() if med.hsn_id else None
            ws.append([
                med.medicine_code, med.name, cat.name if cat else "",
                med.generic_name or "", med.dosage_form or "", med.strength or "",
                med.mrp or 0, med.purchase_rate or 0, med.rate_a or 0, med.rate_b or 0,
                med.unit_price or 0, med.default_discount_pct or 0, med.item_discount_pct or 0,
                med.barcode or "", med.packaging or "", med.strip_conversion_factor or 1,
                med.rate_unit or "tablet",
                _export_bool(bool(med.decimal_supported)), _export_bool(bool(med.requires_prescription)),
                _export_bool(bool(med.is_narcotic)), _export_bool(bool(med.is_high_alert)),
                _export_bool(bool(med.is_schedule_h)), _export_bool(bool(med.is_schedule_h1)),
                _export_bool(bool(med.is_tramadol)), _export_bool(bool(med.is_controlled)),
                _export_bool(bool(med.is_active)), _export_bool(bool(med.is_hidden)),
                med.min_qty or 0, med.max_qty or 0, med.reorder_qty or 0,
                med.description or "", med.side_effects or "", med.contraindications or "",
                med.storage_conditions or "", med.manufacturer or "",
                company.name if company else "", rack.code if rack else "",
                salt.name if salt else "", uom.name if uom else "",
                hsn.code if hsn else "", hsn.sgst_pct if hsn else "", hsn.cgst_pct if hsn else "",
            ])

    return _workbook_bytes(build)


def build_medicines_template() -> bytes:
    def build(wb: openpyxl.Workbook) -> None:
        ws = wb.active
        ws.title = "Medicines"
        ws.append(MEDICINE_HEADERS)
        ws.append([
            "PCM500", "Paracetamol 500mg", "General", "Paracetamol", "tablet", "500mg",
            25, 18, 20, 0, 20, 0, 0, "8901234567890", "10x10", 10, "tablet",
            "false", "false", "false", "false", "false", "false", "false", "false",
            "true", "false", 10, 500, 50, "", "", "", "Store below 25C",
            "", "Cipla Ltd", "R-A1", "Paracetamol", "TAB", "30049099", 6, 6,
        ])
        ws.append([
            "AMOX250", "Amoxicillin 250mg", "Antibiotics", "Amoxicillin", "capsule", "250mg",
            80, 55, 65, 0, 65, 5, 0, "", "10 caps", 10, "strip",
            "false", "true", "false", "false", "false", "false", "false", "false",
            "true", "false", 5, 200, 20, "", "", "", "",
            "", "Sun Pharma", "R-B2", "Amoxicillin", "CAP", "30041010", 6, 6,
        ])
        _append_instructions(wb, [
            "KT HEALTH ERP — Medicine Import Template",
            "",
            "Required: medicine_code, name, category",
            "Upsert key: medicine_code (per hospital)",
            "on_duplicate=skip (default) skips active duplicates; on_duplicate=update updates or reactivates",
            "Categories, companies, salts, racks, UoMs, HSN auto-created when missing",
            "Bool columns: true/false, 1/0, yes/no",
            "rate_a and unit_price are kept in sync when only one is provided",
        ])

    return _workbook_bytes(build)


# ---------------------------------------------------------------------------
# Supplier import / export
# ---------------------------------------------------------------------------

def _apply_supplier_row(sup: PharmacySupplier, row: dict) -> None:
    for field in (
        "mobile", "phone_office", "phone", "email", "address", "pin_code", "state",
        "state_code", "country", "gstin_no", "gstin", "gst_heading", "dl_number",
        "pan_number", "contact_person", "designation", "ledger_type", "ledger_category",
        "account_group", "website", "vat_number", "food_license_no",
        "narco_sch_h_billing", "bill_import", "color_tag", "station", "balancing_method",
    ):
        val = _cell_str(row.get(field))
        if val is not None:
            setattr(sup, field, val)

    if row.get("opening_balance") is not None and _cell_str(row.get("opening_balance")) is not None:
        sup.opening_balance = _cell_float(row.get("opening_balance")) or 0

    dr_cr = _cell_str(row.get("opening_balance_dr_cr"))
    if dr_cr in ("Dr", "Cr"):
        sup.opening_balance_dr_cr = dr_cr

    if row.get("dl_expiry") is not None and _cell_str(row.get("dl_expiry")) is not None:
        sup.dl_expiry = _cell_date(row.get("dl_expiry"))

    for field in ("is_active", "is_hidden"):
        if row.get(field) is not None and _cell_str(row.get(field)) is not None:
            setattr(sup, field, _cell_bool(row.get(field)))


def import_suppliers(
    db: Session, user: User, content: bytes, filename: str,
    *, dry_run: bool, on_duplicate: str,
) -> dict:
    summary = _empty_summary(dry_run=dry_run)
    rows = _parse_upload(content, filename, ["Suppliers"])
    hospital_id = user.hospital_id

    for row in rows:
        rownum = row.get("_row", 0)
        name = _cell_str(row.get("name"))
        if _key_skipped(name):
            continue
        summary["total_rows"] += 1
        if not name:
            msg = "Missing name"
            summary["errors"].append({"sheet": "Suppliers", "row": rownum, "message": msg})
            summary["preview"].append({
                "row": rownum, "key": "", "name": "", "status": "error", "message": msg, "sheet": "Suppliers",
            })
            continue

        existing = db.query(PharmacySupplier).filter(
            PharmacySupplier.hospital_id == hospital_id,
            PharmacySupplier.is_active == True,  # noqa: E712
            sa_func.lower(PharmacySupplier.name) == name.lower(),
        ).first()

        if existing and on_duplicate == "skip":
            summary["skipped"] += 1
            summary["preview"].append({
                "row": rownum, "key": name, "name": name, "status": "skip",
                "message": "Supplier already exists", "sheet": "Suppliers",
            })
            continue

        try:
            if existing and on_duplicate == "update":
                _apply_supplier_row(existing, row)
                summary["updated"] += 1
                summary["preview"].append({
                    "row": rownum, "key": name, "name": name, "status": "update", "sheet": "Suppliers",
                })
            elif not existing:
                sup = PharmacySupplier(name=name, hospital_id=hospital_id)
                _apply_supplier_row(sup, row)
                db.add(sup)
                db.flush()
                summary["created"] += 1
                summary["preview"].append({
                    "row": rownum, "key": name, "name": name, "status": "new", "sheet": "Suppliers",
                })
        except ValueError as exc:
            msg = str(exc)
            summary["errors"].append({"sheet": "Suppliers", "row": rownum, "message": msg})
            summary["preview"].append({
                "row": rownum, "key": name, "name": name, "status": "error", "message": msg, "sheet": "Suppliers",
            })

    summary["error_count"] = len(summary["errors"])
    return summary


def export_suppliers_xlsx(db: Session, hospital_id: int) -> bytes:
    rows = (
        db.query(PharmacySupplier)
        .filter(PharmacySupplier.hospital_id == hospital_id, PharmacySupplier.is_active == True)  # noqa: E712
        .order_by(PharmacySupplier.name)
        .all()
    )

    def build(wb: openpyxl.Workbook) -> None:
        ws = wb.active
        ws.title = "Suppliers"
        ws.append(SUPPLIER_HEADERS)
        for sup in rows:
            ws.append([
                sup.name, sup.mobile or "", sup.phone_office or "", sup.phone or "",
                sup.email or "", sup.address or "", sup.pin_code or "", sup.state or "",
                sup.state_code or "", sup.country or "India", sup.gstin_no or sup.gstin or "",
                sup.gstin or "", sup.gst_heading or "local", sup.dl_number or "",
                _export_date(sup.dl_expiry), sup.pan_number or "", sup.contact_person or "",
                sup.designation or "", sup.ledger_type or "unregistered",
                sup.ledger_category or "OTHERS", sup.account_group or "Sundry Creditors",
                sup.opening_balance or 0, sup.opening_balance_dr_cr or "Dr",
                _export_bool(bool(sup.is_active)), _export_bool(bool(sup.is_hidden)),
                sup.website or "", sup.vat_number or "", sup.food_license_no or "",
                sup.narco_sch_h_billing or "allow_all", sup.bill_import or "mobile",
                sup.color_tag or "normal", sup.station or "", sup.balancing_method or "bill_by_bill",
            ])

    return _workbook_bytes(build)


def build_suppliers_template() -> bytes:
    def build(wb: openpyxl.Workbook) -> None:
        ws = wb.active
        ws.title = "Suppliers"
        ws.append(SUPPLIER_HEADERS)
        ws.append([
            "MedSupply Co", "9876543210", "040-1234567", "", "sales@medsupply.example",
            "12 Industrial Area", "500001", "Telangana", "36", "India",
            "36AABCM1234A1Z5", "", "local", "DL-TS-12345", "2027-12-31",
            "AABCM1234A", "Ravi Kumar", "Manager", "registered", "OTHERS",
            "Sundry Creditors", 0, "Dr", "true", "false",
            "", "", "", "allow_all", "mobile", "normal", "Hyderabad", "bill_by_bill",
        ])
        _append_instructions(wb, [
            "KT HEALTH ERP — Supplier Import Template",
            "",
            "Required: name",
            "Upsert key: name (case-insensitive, active suppliers only)",
            "on_duplicate=skip | update",
        ])

    return _workbook_bytes(build)


# ---------------------------------------------------------------------------
# Masters import / export
# ---------------------------------------------------------------------------

def _upsert_master_row(
    db: Session, hospital_id: int, sheet: str, row: dict,
    caches: dict, summary: dict, on_duplicate: str,
) -> None:
    rownum = row.get("_row", 0)

    if sheet == "Categories":
        name = _cell_str(row.get("name"))
        if _key_skipped(name):
            return
        summary["total_rows"] += 1
        if not name:
            _add_error(summary, sheet, rownum, "Missing name", key="")
            return
        key = name.lower()
        existing = caches["categories"].get(key)
        if existing and on_duplicate == "skip":
            summary["skipped"] += 1
            summary["preview"].append({"row": rownum, "key": name, "name": name, "status": "skip", "sheet": sheet})
            return
        if existing:
            if _cell_str(row.get("description")) is not None:
                existing.description = _cell_str(row.get("description"))
            if row.get("is_active") is not None and _cell_str(row.get("is_active")) is not None:
                existing.is_active = _cell_bool(row.get("is_active"))
            summary["updated"] += 1
            summary["preview"].append({"row": rownum, "key": name, "name": name, "status": "update", "sheet": sheet})
        else:
            obj = MedicineCategory(
                name=name, hospital_id=hospital_id,
                description=_cell_str(row.get("description")),
                is_active=_cell_bool(row.get("is_active")) if _cell_str(row.get("is_active")) else True,
            )
            db.add(obj)
            db.flush()
            caches["categories"][key] = obj
            summary["created"] += 1
            summary["preview"].append({"row": rownum, "key": name, "name": name, "status": "new", "sheet": sheet})

    elif sheet == "Companies":
        name = _cell_str(row.get("name"))
        if _key_skipped(name):
            return
        summary["total_rows"] += 1
        if not name:
            _add_error(summary, sheet, rownum, "Missing name", key="")
            return
        key = name.lower()
        existing = caches["companies"].get(key)
        if existing and on_duplicate == "skip":
            summary["skipped"] += 1
            summary["preview"].append({"row": rownum, "key": name, "name": name, "status": "skip", "sheet": sheet})
            return
        if existing:
            if _cell_str(row.get("contact")) is not None:
                existing.contact = _cell_str(row.get("contact"))
            if row.get("is_active") is not None and _cell_str(row.get("is_active")) is not None:
                existing.is_active = _cell_bool(row.get("is_active"))
            summary["updated"] += 1
            summary["preview"].append({"row": rownum, "key": name, "name": name, "status": "update", "sheet": sheet})
        else:
            obj = PharmacyCompany(
                name=name, hospital_id=hospital_id,
                contact=_cell_str(row.get("contact")),
                is_active=_cell_bool(row.get("is_active")) if _cell_str(row.get("is_active")) else True,
            )
            db.add(obj)
            db.flush()
            caches["companies"][key] = obj
            summary["created"] += 1
            summary["preview"].append({"row": rownum, "key": name, "name": name, "status": "new", "sheet": sheet})

    elif sheet == "Salts":
        name = _cell_str(row.get("name"))
        if _key_skipped(name):
            return
        summary["total_rows"] += 1
        if not name:
            _add_error(summary, sheet, rownum, "Missing name", key="")
            return
        key = name.lower()
        existing = caches["salts"].get(key)
        if existing and on_duplicate == "skip":
            summary["skipped"] += 1
            summary["preview"].append({"row": rownum, "key": name, "name": name, "status": "skip", "sheet": sheet})
            return
        if existing:
            if _cell_str(row.get("description")) is not None:
                existing.description = _cell_str(row.get("description"))
            if row.get("is_active") is not None and _cell_str(row.get("is_active")) is not None:
                existing.is_active = _cell_bool(row.get("is_active"))
            summary["updated"] += 1
            summary["preview"].append({"row": rownum, "key": name, "name": name, "status": "update", "sheet": sheet})
        else:
            obj = PharmacySalt(
                name=name, hospital_id=hospital_id,
                description=_cell_str(row.get("description")),
                is_active=_cell_bool(row.get("is_active")) if _cell_str(row.get("is_active")) else True,
            )
            db.add(obj)
            db.flush()
            caches["salts"][key] = obj
            summary["created"] += 1
            summary["preview"].append({"row": rownum, "key": name, "name": name, "status": "new", "sheet": sheet})

    elif sheet == "Racks":
        code = _cell_str(row.get("code"))
        if _key_skipped(code):
            return
        summary["total_rows"] += 1
        if not code:
            _add_error(summary, sheet, rownum, "Missing code", key="")
            return
        key = code.lower()
        existing = caches["racks"].get(key)
        if existing and on_duplicate == "skip":
            summary["skipped"] += 1
            summary["preview"].append({"row": rownum, "key": code, "name": code, "status": "skip", "sheet": sheet})
            return
        if existing:
            for f in ("location", "description"):
                if _cell_str(row.get(f)) is not None:
                    setattr(existing, f, _cell_str(row.get(f)))
            if row.get("is_active") is not None and _cell_str(row.get("is_active")) is not None:
                existing.is_active = _cell_bool(row.get("is_active"))
            summary["updated"] += 1
            summary["preview"].append({"row": rownum, "key": code, "name": code, "status": "update", "sheet": sheet})
        else:
            obj = PharmacyRack(
                code=code, hospital_id=hospital_id,
                location=_cell_str(row.get("location")),
                description=_cell_str(row.get("description")),
                is_active=_cell_bool(row.get("is_active")) if _cell_str(row.get("is_active")) else True,
            )
            db.add(obj)
            db.flush()
            caches["racks"][key] = obj
            summary["created"] += 1
            summary["preview"].append({"row": rownum, "key": code, "name": code, "status": "new", "sheet": sheet})

    elif sheet == "UoMs":
        name = _cell_str(row.get("name"))
        if _key_skipped(name):
            return
        summary["total_rows"] += 1
        if not name:
            _add_error(summary, sheet, rownum, "Missing name", key="")
            return
        key = name.lower()
        existing = caches["uoms"].get(key)
        if existing and on_duplicate == "skip":
            summary["skipped"] += 1
            summary["preview"].append({"row": rownum, "key": name, "name": name, "status": "skip", "sheet": sheet})
            return
        if existing:
            if _cell_str(row.get("abbreviation")) is not None:
                existing.abbreviation = _cell_str(row.get("abbreviation"))
            if row.get("decimal_supported") is not None and _cell_str(row.get("decimal_supported")) is not None:
                existing.decimal_supported = _cell_bool(row.get("decimal_supported"))
            if row.get("is_active") is not None and _cell_str(row.get("is_active")) is not None:
                existing.is_active = _cell_bool(row.get("is_active"))
            summary["updated"] += 1
            summary["preview"].append({"row": rownum, "key": name, "name": name, "status": "update", "sheet": sheet})
        else:
            obj = PharmacyUoM(
                name=name, hospital_id=hospital_id,
                abbreviation=_cell_str(row.get("abbreviation")),
                decimal_supported=_cell_bool(row.get("decimal_supported")) if _cell_str(row.get("decimal_supported")) else False,
                is_active=_cell_bool(row.get("is_active")) if _cell_str(row.get("is_active")) else True,
            )
            db.add(obj)
            db.flush()
            caches["uoms"][key] = obj
            summary["created"] += 1
            summary["preview"].append({"row": rownum, "key": name, "name": name, "status": "new", "sheet": sheet})

    elif sheet == "HSN":
        code = _cell_str(row.get("code"))
        if _key_skipped(code):
            return
        summary["total_rows"] += 1
        if not code:
            _add_error(summary, sheet, rownum, "Missing code", key="")
            return
        try:
            sgst, cgst, igst = _normalize_hsn_tax(
                _cell_float(row.get("sgst_pct")) or 0,
                _cell_float(row.get("cgst_pct")) or 0,
            )
            if row.get("igst_pct") is not None and _cell_str(row.get("igst_pct")) is not None:
                igst = _cell_float(row.get("igst_pct")) or igst
        except ValueError as exc:
            _add_error(summary, sheet, rownum, str(exc), key=code)
            return
        cache_key = (code.lower(), sgst, cgst)
        existing = caches["hsn"].get(cache_key)
        if existing and on_duplicate == "skip":
            summary["skipped"] += 1
            summary["preview"].append({"row": rownum, "key": code, "name": code, "status": "skip", "sheet": sheet})
            return
        if existing:
            if _cell_str(row.get("description")) is not None:
                existing.description = _cell_str(row.get("description"))
            existing.igst_pct = igst
            if row.get("is_active") is not None and _cell_str(row.get("is_active")) is not None:
                existing.is_active = _cell_bool(row.get("is_active"))
            summary["updated"] += 1
            summary["preview"].append({"row": rownum, "key": code, "name": code, "status": "update", "sheet": sheet})
        else:
            obj = PharmacyHSN(
                code=code, hospital_id=hospital_id, sgst_pct=sgst, cgst_pct=cgst, igst_pct=igst,
                description=_cell_str(row.get("description")),
                is_active=_cell_bool(row.get("is_active")) if _cell_str(row.get("is_active")) else True,
            )
            db.add(obj)
            db.flush()
            caches["hsn"][cache_key] = obj
            summary["created"] += 1
            summary["preview"].append({"row": rownum, "key": code, "name": code, "status": "new", "sheet": sheet})

    elif sheet == "Stores":
        code = _cell_str(row.get("code"))
        if _key_skipped(code):
            return
        summary["total_rows"] += 1
        if not code:
            _add_error(summary, sheet, rownum, "Missing code", key="")
            return
        name = _cell_str(row.get("name")) or code
        key = code.lower()
        existing = caches["stores"].get(key)
        if existing and on_duplicate == "skip":
            summary["skipped"] += 1
            summary["preview"].append({"row": rownum, "key": code, "name": name, "status": "skip", "sheet": sheet})
            return

        store_type = (_cell_str(row.get("store_type")) or "master").lower()
        if store_type not in ("master", "satellite"):
            _add_error(summary, sheet, rownum, f"Invalid store_type '{store_type}'", key=code)
            return

        parent_code = _cell_str(row.get("parent_code"))
        parent_id = None
        if parent_code:
            parent = caches["stores"].get(parent_code.lower())
            if not parent:
                _add_error(summary, sheet, rownum, f"Unknown parent_code '{parent_code}'", key=code)
                return
            parent_id = parent.id

        is_default = _cell_bool(row.get("is_default")) if _cell_str(row.get("is_default")) else False
        if is_default:
            for s in caches["stores"].values():
                s.is_default = False

        if existing:
            existing.name = name
            existing.store_type = store_type
            existing.parent_store_id = parent_id
            if _cell_str(row.get("location")) is not None:
                existing.location = _cell_str(row.get("location"))
            if _cell_str(row.get("description")) is not None:
                existing.description = _cell_str(row.get("description"))
            if row.get("can_receive_supplier_purchase") is not None and _cell_str(row.get("can_receive_supplier_purchase")) is not None:
                existing.can_receive_supplier_purchase = _cell_bool(row.get("can_receive_supplier_purchase"))
            if row.get("is_active") is not None and _cell_str(row.get("is_active")) is not None:
                existing.is_active = _cell_bool(row.get("is_active"))
            existing.is_default = is_default
            summary["updated"] += 1
            summary["preview"].append({"row": rownum, "key": code, "name": name, "status": "update", "sheet": sheet})
        else:
            obj = PharmacyStore(
                code=code, name=name, store_type=store_type, parent_store_id=parent_id,
                location=_cell_str(row.get("location")),
                description=_cell_str(row.get("description")),
                can_receive_supplier_purchase=(
                    _cell_bool(row.get("can_receive_supplier_purchase"))
                    if _cell_str(row.get("can_receive_supplier_purchase")) else False
                ),
                is_active=_cell_bool(row.get("is_active")) if _cell_str(row.get("is_active")) else True,
                is_default=is_default,
                hospital_id=hospital_id,
            )
            db.add(obj)
            db.flush()
            caches["stores"][key] = obj
            summary["created"] += 1
            summary["preview"].append({"row": rownum, "key": code, "name": name, "status": "new", "sheet": sheet})


def _add_error(summary: dict, sheet: str, rownum: int, message: str, *, key: str) -> None:
    summary["errors"].append({"sheet": sheet, "row": rownum, "message": message})
    summary["preview"].append({
        "row": rownum, "key": key, "name": key, "status": "error", "message": message, "sheet": sheet,
    })


def _load_master_caches(db: Session, hospital_id: int) -> dict:
    return {
        "categories": {c.name.strip().lower(): c for c in db.query(MedicineCategory).filter(MedicineCategory.hospital_id == hospital_id).all()},
        "companies": {c.name.strip().lower(): c for c in db.query(PharmacyCompany).filter(PharmacyCompany.hospital_id == hospital_id).all()},
        "salts": {s.name.strip().lower(): s for s in db.query(PharmacySalt).filter(PharmacySalt.hospital_id == hospital_id).all()},
        "racks": {r.code.strip().lower(): r for r in db.query(PharmacyRack).filter(PharmacyRack.hospital_id == hospital_id).all()},
        "uoms": {u.name.strip().lower(): u for u in db.query(PharmacyUoM).filter(PharmacyUoM.hospital_id == hospital_id).all()},
        "hsn": {(h.code.strip().lower(), h.sgst_pct or 0, h.cgst_pct or 0): h for h in db.query(PharmacyHSN).filter(PharmacyHSN.hospital_id == hospital_id).all()},
        "stores": {s.code.strip().lower(): s for s in db.query(PharmacyStore).filter(PharmacyStore.hospital_id == hospital_id).all()},
    }


def import_masters(
    db: Session, user: User, content: bytes, filename: str,
    *, dry_run: bool, on_duplicate: str,
) -> dict:
    summary = _empty_summary(dry_run=dry_run)
    hospital_id = user.hospital_id
    caches = _load_master_caches(db, hospital_id)

    parsed = _parse_upload(content, filename, list(MASTER_SHEETS.keys()), multi=True)
    if isinstance(parsed, list):
        parsed = {"Categories": parsed}

    for sheet in MASTER_SHEETS:
        for row in parsed.get(sheet, []):
            try:
                _upsert_master_row(db, hospital_id, sheet, row, caches, summary, on_duplicate)
            except ValueError as exc:
                _add_error(summary, sheet, row.get("_row", 0), str(exc), key=_cell_str(row.get("name")) or _cell_str(row.get("code")) or "")

    summary["error_count"] = len(summary["errors"])
    return summary


def export_masters_xlsx(db: Session, hospital_id: int) -> bytes:
    def build(wb: openpyxl.Workbook) -> None:
        wb.remove(wb.active)
        for sheet_name, headers in MASTER_SHEETS.items():
            ws = wb.create_sheet(sheet_name)
            ws.append(headers)
            if sheet_name == "Categories":
                for r in db.query(MedicineCategory).filter(MedicineCategory.hospital_id == hospital_id, MedicineCategory.is_active == True).order_by(MedicineCategory.name).all():  # noqa: E712
                    ws.append([r.name, r.description or "", _export_bool(bool(r.is_active))])
            elif sheet_name == "Companies":
                for r in db.query(PharmacyCompany).filter(PharmacyCompany.hospital_id == hospital_id, PharmacyCompany.is_active == True).order_by(PharmacyCompany.name).all():  # noqa: E712
                    ws.append([r.name, r.contact or "", _export_bool(bool(r.is_active))])
            elif sheet_name == "Salts":
                for r in db.query(PharmacySalt).filter(PharmacySalt.hospital_id == hospital_id, PharmacySalt.is_active == True).order_by(PharmacySalt.name).all():  # noqa: E712
                    ws.append([r.name, r.description or "", _export_bool(bool(r.is_active))])
            elif sheet_name == "Racks":
                for r in db.query(PharmacyRack).filter(PharmacyRack.hospital_id == hospital_id, PharmacyRack.is_active == True).order_by(PharmacyRack.code).all():  # noqa: E712
                    ws.append([r.code, r.location or "", r.description or "", _export_bool(bool(r.is_active))])
            elif sheet_name == "UoMs":
                for r in db.query(PharmacyUoM).filter(PharmacyUoM.hospital_id == hospital_id, PharmacyUoM.is_active == True).order_by(PharmacyUoM.name).all():  # noqa: E712
                    ws.append([r.name, r.abbreviation or "", _export_bool(bool(r.decimal_supported)), _export_bool(bool(r.is_active))])
            elif sheet_name == "HSN":
                for r in db.query(PharmacyHSN).filter(PharmacyHSN.hospital_id == hospital_id, PharmacyHSN.is_active == True).order_by(PharmacyHSN.code).all():  # noqa: E712
                    ws.append([r.code, r.description or "", r.sgst_pct or 0, r.cgst_pct or 0, r.igst_pct or 0, _export_bool(bool(r.is_active))])
            elif sheet_name == "Stores":
                for r in db.query(PharmacyStore).filter(PharmacyStore.hospital_id == hospital_id, PharmacyStore.is_active == True).order_by(PharmacyStore.code).all():  # noqa: E712
                    parent_code = ""
                    if r.parent_store_id:
                        p = db.query(PharmacyStore).filter(PharmacyStore.id == r.parent_store_id).first()
                        parent_code = p.code if p else ""
                    ws.append([
                        r.code, r.name, r.store_type, parent_code, r.location or "", r.description or "",
                        _export_bool(bool(r.can_receive_supplier_purchase)), _export_bool(bool(r.is_active)),
                        _export_bool(bool(r.is_default)),
                    ])

    return _workbook_bytes(build)


def build_masters_template() -> bytes:
    def build(wb: openpyxl.Workbook) -> None:
        wb.remove(wb.active)
        samples = {
            "Categories": [["General", "General medicines", "true"], ["Antibiotics", "", "true"]],
            "Companies": [["Cipla Ltd", "Mumbai", "true"]],
            "Salts": [["Paracetamol", "", "true"]],
            "Racks": [["R-A1", "Aisle A", "", "true"]],
            "UoMs": [["Tablet", "TAB", "false", "true"]],
            "HSN": [["30049099", "Medicaments", 6, 6, 12, "true"]],
            "Stores": [["MAIN", "Main Pharmacy", "master", "", "Ground floor", "", "true", "true", "true"]],
        }
        for sheet_name, headers in MASTER_SHEETS.items():
            ws = wb.create_sheet(sheet_name)
            ws.append(headers)
            for sample in samples.get(sheet_name, []):
                ws.append(sample)
        _append_instructions(wb, [
            "KT HEALTH ERP — Pharmacy Masters Import",
            "",
            "Sheets: Categories, Companies, Salts, Racks, UoMs, HSN, Stores",
            "Each sheet upserts independently; total_rows counts all sheets",
            "HSN upsert key: code + sgst_pct + cgst_pct (igst defaults to sgst+cgst if blank)",
            "Stores: only one is_default=true per hospital — importing default clears others",
        ])

    return _workbook_bytes(build)


# ---------------------------------------------------------------------------
# Opening stock import / export
# ---------------------------------------------------------------------------

def _resolve_store_id(db: Session, hospital_id: int, store_code: Optional[str], store_cache: dict) -> Optional[int]:
    if store_code:
        key = store_code.strip().lower()
        row = store_cache.get(key)
        if not row:
            row = db.query(PharmacyStore).filter(
                PharmacyStore.hospital_id == hospital_id,
                sa_func.lower(PharmacyStore.code) == key,
            ).first()
            if row:
                store_cache[key] = row
        return row.id if row else None
    return get_master_store_id(db, hospital_id)


def import_opening_stock(
    db: Session, user: User, content: bytes, filename: str,
    *, dry_run: bool, on_duplicate: str,
) -> dict:
    summary = _empty_summary(dry_run=dry_run)
    rows = _parse_upload(content, filename, ["OpeningStock"])
    hospital_id = user.hospital_id
    store_cache: Dict[str, PharmacyStore] = {
        s.code.strip().lower(): s
        for s in db.query(PharmacyStore).filter(PharmacyStore.hospital_id == hospital_id).all()
    }
    medicine_cache: Dict[str, Medicine] = {}

    for row in rows:
        rownum = row.get("_row", 0)
        med_code = _cell_str(row.get("medicine_code"))
        if _key_skipped(med_code):
            continue
        summary["total_rows"] += 1
        batch_number = _cell_str(row.get("batch_number"))
        row_errs: List[str] = []
        if not batch_number:
            row_errs.append("Missing batch_number")

        expiry = None
        qty = None
        try:
            expiry = _cell_date(row.get("expiry_date"))
            if expiry is None:
                row_errs.append("Missing or invalid expiry_date")
            qty_val = _cell_float(row.get("quantity"))
            if qty_val is None:
                row_errs.append("Missing quantity")
            elif qty_val <= 0:
                row_errs.append("quantity must be > 0")
            else:
                qty = int(qty_val) if qty_val == int(qty_val) else qty_val
        except ValueError as exc:
            row_errs.append(str(exc))

        if row_errs:
            msg = "; ".join(row_errs)
            summary["errors"].append({"sheet": "OpeningStock", "row": rownum, "message": msg})
            summary["preview"].append({
                "row": rownum, "key": med_code or "", "name": batch_number or "",
                "status": "error", "message": msg, "sheet": "OpeningStock",
            })
            continue

        med_key = med_code.lower()
        med = medicine_cache.get(med_key)
        if not med:
            med = db.query(Medicine).filter(
                Medicine.hospital_id == hospital_id,
                Medicine.medicine_code == med_code,
                Medicine.is_active == True,  # noqa: E712
            ).first()
            if med:
                medicine_cache[med_key] = med
        if not med:
            msg = f"Medicine '{med_code}' not found — import medicines first"
            summary["errors"].append({"sheet": "OpeningStock", "row": rownum, "message": msg})
            summary["preview"].append({
                "row": rownum, "key": med_code, "name": batch_number, "status": "error",
                "message": msg, "sheet": "OpeningStock",
            })
            continue

        store_code = _cell_str(row.get("store_code"))
        store_id = _resolve_store_id(db, hospital_id, store_code, store_cache)
        if not store_id:
            msg = f"Store not found: '{store_code or '(default master)'}'"
            summary["errors"].append({"sheet": "OpeningStock", "row": rownum, "message": msg})
            summary["preview"].append({
                "row": rownum, "key": med_code, "name": batch_number, "status": "error",
                "message": msg, "sheet": "OpeningStock",
            })
            continue

        existing = db.query(PharmacyInventory).filter(
            PharmacyInventory.medicine_id == med.id,
            PharmacyInventory.batch_number == batch_number,
            PharmacyInventory.store_id == store_id,
            PharmacyInventory.hospital_id == hospital_id,
            PharmacyInventory.is_active == True,  # noqa: E712
        ).first()

        if existing and on_duplicate == "skip":
            summary["skipped"] += 1
            summary["preview"].append({
                "row": rownum, "key": med_code, "name": batch_number, "status": "skip",
                "message": "Batch already exists", "sheet": "OpeningStock",
            })
            continue

        mrp = _cell_float(row.get("mrp"))
        purchase_rate = _cell_float(row.get("purchase_rate"))
        rate_a = _cell_float(row.get("rate_a"))
        rate_b = _cell_float(row.get("rate_b"))
        cost_price = _cell_float(row.get("cost_price"))
        selling_price = _cell_float(row.get("selling_price"))
        scf = _cell_int(row.get("strip_conversion_factor"))
        free_qty = _cell_int(row.get("free_quantity")) or 0
        discount_pct = _cell_float(row.get("discount_pct")) or 0.0
        notes = _cell_str(row.get("notes")) or "Opening stock import"

        if rate_a is None:
            rate_a = med.rate_a or 0
        if mrp is None:
            mrp = med.mrp or 0
        if purchase_rate is None:
            purchase_rate = med.purchase_rate or 0
        if selling_price is None:
            selling_price = rate_a or mrp or med.rate_a or 0
        if cost_price is None:
            cost_price = purchase_rate or med.purchase_rate or 0
        if scf is None:
            scf = max(1, int(med.strip_conversion_factor or 1))

        supplier_id = None
        supplier_name = _cell_str(row.get("supplier_name"))
        if supplier_name:
            sup = db.query(PharmacySupplier).filter(
                PharmacySupplier.hospital_id == hospital_id,
                sa_func.lower(PharmacySupplier.name) == supplier_name.lower(),
                PharmacySupplier.is_active == True,  # noqa: E712
            ).first()
            if sup:
                supplier_id = sup.id

        hsn_id = med.hsn_id
        hsn_code = _cell_str(row.get("hsn_code"))
        if hsn_code:
            resolver = _MasterResolver(db, hospital_id)
            hsn_id = resolver.hsn(hsn_code, _cell_float(row.get("sgst_pct")), _cell_float(row.get("cgst_pct"))).id
            summary["masters_created"].extend(resolver.masters_created)

        if existing and on_duplicate == "update":
            old_qty = existing.quantity_in_stock or 0
            new_qty = int(qty)
            if new_qty < 0:
                msg = "Resulting quantity cannot be negative"
                summary["errors"].append({"sheet": "OpeningStock", "row": rownum, "message": msg})
                summary["preview"].append({
                    "row": rownum, "key": med_code, "name": batch_number, "status": "error",
                    "message": msg, "sheet": "OpeningStock",
                })
                continue
            delta = new_qty - old_qty
            existing.quantity_in_stock = new_qty
            existing.expiry_date = expiry
            existing.mrp = mrp or existing.mrp
            existing.purchase_rate = purchase_rate or existing.purchase_rate
            existing.rate_a = rate_a or existing.rate_a
            existing.rate_b = rate_b if rate_b is not None else existing.rate_b
            existing.cost_price = cost_price
            existing.selling_price = selling_price
            existing.strip_conversion_factor = scf
            existing.free_quantity = free_qty
            existing.discount_pct = discount_pct
            existing.supplier_id = supplier_id or existing.supplier_id
            existing.hsn_id = hsn_id or existing.hsn_id
            reason = f"Opening stock import (set qty to {new_qty}, was {old_qty})"
            adj = PharmacyStockAdjustment(
                medicine_id=med.id, batch_id=existing.id, qty_change=delta,
                reason=reason, performed_by=user.id, store_id=store_id, hospital_id=hospital_id,
            )
            db.add(adj)
            db.flush()
            db.add(PharmacyStockLedger(
                medicine_id=med.id, batch_id=existing.id, txn_type="opening_stock",
                qty_delta=delta, reference_type="opening_stock_import", reference_id=adj.id,
                performed_by=user.id, store_id=store_id, hospital_id=hospital_id, notes=notes,
            ))
            summary["updated"] += 1
            summary["preview"].append({
                "row": rownum, "key": med_code, "name": batch_number, "status": "update", "sheet": "OpeningStock",
            })
        else:
            inv = PharmacyInventory(
                medicine_id=med.id, batch_number=batch_number, expiry_date=expiry,
                quantity_in_stock=int(qty), cost_price=cost_price, selling_price=selling_price,
                mrp=mrp or 0, purchase_rate=purchase_rate or 0, rate_a=rate_a or 0,
                rate_b=rate_b or 0, strip_conversion_factor=scf, free_quantity=free_qty,
                discount_pct=discount_pct, hsn_id=hsn_id, supplier_id=supplier_id,
                store_id=store_id, is_active=True, hospital_id=hospital_id,
            )
            db.add(inv)
            db.flush()
            reason = "Opening stock import"
            adj = PharmacyStockAdjustment(
                medicine_id=med.id, batch_id=inv.id, qty_change=int(qty),
                reason=reason, performed_by=user.id, store_id=store_id, hospital_id=hospital_id,
            )
            db.add(adj)
            db.flush()
            db.add(PharmacyStockLedger(
                medicine_id=med.id, batch_id=inv.id, txn_type="opening_stock",
                qty_delta=int(qty), reference_type="opening_stock_import", reference_id=adj.id,
                performed_by=user.id, store_id=store_id, hospital_id=hospital_id, notes=notes,
            ))
            summary["created"] += 1
            summary["preview"].append({
                "row": rownum, "key": med_code, "name": batch_number, "status": "new", "sheet": "OpeningStock",
            })

    summary["error_count"] = len(summary["errors"])
    return summary


def export_opening_stock_xlsx(db: Session, hospital_id: int) -> bytes:
    batches = (
        db.query(PharmacyInventory, Medicine, PharmacyStore, PharmacySupplier)
        .join(Medicine, Medicine.id == PharmacyInventory.medicine_id)
        .outerjoin(PharmacyStore, PharmacyStore.id == PharmacyInventory.store_id)
        .outerjoin(PharmacySupplier, PharmacySupplier.id == PharmacyInventory.supplier_id)
        .filter(
            PharmacyInventory.hospital_id == hospital_id,
            PharmacyInventory.is_active == True,  # noqa: E712
            PharmacyInventory.quantity_in_stock > 0,
        )
        .order_by(Medicine.medicine_code, PharmacyInventory.batch_number)
        .all()
    )

    def build(wb: openpyxl.Workbook) -> None:
        ws = wb.active
        ws.title = "OpeningStock"
        ws.append(OPENING_STOCK_HEADERS)
        for inv, med, store, sup in batches:
            hsn_code = ""
            if inv.hsn_id:
                hsn = db.query(PharmacyHSN).filter(PharmacyHSN.id == inv.hsn_id).first()
                hsn_code = hsn.code if hsn else ""
            ws.append([
                med.medicine_code, inv.batch_number, _export_date(inv.expiry_date),
                inv.quantity_in_stock, store.code if store else "",
                inv.mrp or 0, inv.purchase_rate or 0, inv.rate_a or 0, inv.rate_b or 0,
                inv.cost_price or 0, inv.selling_price or 0,
                sup.name if sup else "", hsn_code, inv.strip_conversion_factor or 1,
                inv.free_quantity or 0, inv.discount_pct or 0, "",
            ])

    return _workbook_bytes(build)


def build_opening_stock_template() -> bytes:
    def build(wb: openpyxl.Workbook) -> None:
        ws = wb.active
        ws.title = "OpeningStock"
        ws.append(OPENING_STOCK_HEADERS)
        ws.append([
            "PCM500", "BATCH001", "2027-06-30", 100, "MAIN",
            25, 18, 20, 0, 18, 20, "MedSupply Co", "30049099", 10, 0, 0,
            "Initial stock",
        ])
        _append_instructions(wb, [
            "KT HEALTH ERP — Opening Stock Import",
            "",
            "Required: medicine_code, batch_number, expiry_date (YYYY-MM-DD), quantity (>0)",
            "Medicine must already exist — this import does NOT create medicines",
            "store_code optional — defaults to master store",
            "on_duplicate=update sets quantity_in_stock to the NEW absolute value (not a delta)",
            "Ledger records the difference between old and new quantity",
        ])

    return _workbook_bytes(build)


# ---------------------------------------------------------------------------
# Purchases (vendor H/T/F CSV or named-header template)
# ---------------------------------------------------------------------------

# Vendor tax-invoice CSV column map (CL1..CL31), aligned to PDF line headers:
# Item Name, Pack Size, Batch No., Expiry, QTY, Package, MRP, PTR, Rate,
# Taxable, CGST%/Amt, IGST%/Amt, SGST%/Amt, HSN Code.
#
# Pricing policy for vendor imports:
#   PTR (CL11) → purchase_rate
#   MRP (CL13) → mrp, rate_a, and rate_b
#   Rate (CL12) is ignored (distributor net rate; not used for our purchase entry)
_VENDOR_T_MAP = {
    "record_type": "cl1",
    "supplier_name": "cl3",
    "item_code": "cl5",
    "item_name": "cl6",
    "pack_size": "cl7",
    "manufacturer": "cl8",
    "batch_number": "cl9",
    "expiry_raw": "cl10",
    "ptr": "cl11",
    "distributor_rate": "cl12",
    "mrp": "cl13",
    "quantity": "cl16",
    "free_quantity": "cl17",
    "discount_raw": "cl19",
    "taxable": "cl22",
    "cgst_pct": "cl23",
    "cgst_amt": "cl24",
    "igst_pct": "cl25",
    "igst_amt": "cl26",
    "sgst_pct": "cl27",
    "sgst_amt": "cl28",
    "hsn_code": "cl31",
}


def _strip_excel_formula(v) -> Optional[str]:
    """Normalize Excel-exported cells like `=\"000008\"` or `=\"3338.06\"`."""
    s = _cell_str(v)
    if s is None:
        return None
    if s.startswith("="):
        s = s[1:].strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in ("\"", "'"):
            s = s[1:-1]
    return s.strip() if s.strip() else None


def _parse_ddmmyyyy(v) -> Optional[date]:
    """Parse DDMMYYYY (vendor CSV) or fall back to ISO / MM/YYYY."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = _strip_excel_formula(v)
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    if len(digits) == 8:
        dd, mm, yyyy = int(digits[0:2]), int(digits[2:4]), int(digits[4:8])
        return date(yyyy, mm, dd)
    if len(digits) == 6:
        # MMYYYY → last day of month is unknown; use day 1
        mm, yyyy = int(digits[0:2]), int(digits[2:6])
        return date(yyyy, mm, 1)
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    # MM/YYYY or MM-YYYY
    m = re.match(r"^(\d{1,2})[/-](\d{4})$", s)
    if m:
        return date(int(m.group(2)), int(m.group(1)), 1)
    raise ValueError(f"'{s}' is not a valid date")


def _parse_pack_scf(pack: Optional[str]) -> Optional[int]:
    """`1*10` → 10, `5*1` → 1. Non-numeric pack units (e.g. 30ML) → None."""
    if not pack:
        return None
    parts = re.split(r"[*xX×]", pack.strip())
    if len(parts) < 2:
        return None
    m = re.match(r"^(\d+)", parts[-1].strip())
    if not m:
        return None
    n = int(m.group(1))
    return n if n >= 1 else None


def _looks_like_vendor_purchase(rows: List[dict]) -> bool:
    if not rows:
        return False
    keys = {k for k in rows[0].keys() if k != "_row"}
    if "cl1" in keys and "cl6" in keys:
        return True
    for row in rows[:5]:
        typ = (_strip_excel_formula(row.get("cl1")) or "").upper()
        if typ in ("H", "T", "F"):
            return True
    return False


def _vendor_cell(row: dict, key: str):
    col = _VENDOR_T_MAP.get(key, key)
    return row.get(col)


def _parse_vendor_purchase_blocks(rows: List[dict]) -> List[dict]:
    """Group H / T / F rows into one block per invoice."""
    blocks: List[dict] = []
    current: Optional[dict] = None

    def _finish():
        nonlocal current
        if current is not None:
            blocks.append(current)
            current = None

    for row in rows:
        typ = (_strip_excel_formula(row.get("cl1")) or "").upper()
        rownum = row.get("_row", 0)
        if typ == "H":
            _finish()
            inv = _strip_excel_formula(row.get("cl3"))
            bill_date = None
            try:
                bill_date = _parse_ddmmyyyy(row.get("cl4"))
            except ValueError:
                bill_date = None
            current = {
                "invoice_number": inv,
                "bill_date": bill_date,
                "entry_date": bill_date or date.today(),
                "purchase_type": _strip_excel_formula(row.get("cl7")),
                "transporter": _strip_excel_formula(row.get("cl11")),
                "place_of_supply": _strip_excel_formula(row.get("cl14")),
                "supplier_name": None,
                "payment_type": "credit",
                "tax_mode": "exclusive",
                "store_code": None,
                "notes": None,
                "footer": None,
                "items": [],
                "_header_row": rownum,
            }
        elif typ == "T":
            if current is None:
                # Orphan T without H — start an implicit block
                current = {
                    "invoice_number": None,
                    "bill_date": None,
                    "entry_date": date.today(),
                    "purchase_type": None,
                    "transporter": None,
                    "place_of_supply": None,
                    "supplier_name": None,
                    "payment_type": "credit",
                    "tax_mode": "exclusive",
                    "store_code": None,
                    "notes": None,
                    "footer": None,
                    "items": [],
                    "_header_row": rownum,
                }
            supplier = _strip_excel_formula(_vendor_cell(row, "supplier_name"))
            if supplier and not current.get("supplier_name"):
                current["supplier_name"] = supplier
            item_name = _strip_excel_formula(_vendor_cell(row, "item_name"))
            batch = _strip_excel_formula(_vendor_cell(row, "batch_number"))
            if not item_name and not batch:
                continue
            expiry = None
            try:
                expiry = _parse_ddmmyyyy(_vendor_cell(row, "expiry_raw"))
            except ValueError:
                expiry = None
            qty = _cell_float(_strip_excel_formula(_vendor_cell(row, "quantity")) or _vendor_cell(row, "quantity"))
            free = _cell_float(
                _strip_excel_formula(_vendor_cell(row, "free_quantity")) or _vendor_cell(row, "free_quantity")
            ) or 0.0
            ptr = _cell_float(_strip_excel_formula(_vendor_cell(row, "ptr")) or _vendor_cell(row, "ptr"))
            mrp = _cell_float(_strip_excel_formula(_vendor_cell(row, "mrp")) or _vendor_cell(row, "mrp"))
            disc_raw = _cell_float(
                _strip_excel_formula(_vendor_cell(row, "discount_raw")) or _vendor_cell(row, "discount_raw")
            ) or 0.0
            # Vendor Disc column is an amount (PDF "Disc."); convert to % of PTR×qty
            discount_pct = 0.0
            if disc_raw and qty and ptr:
                base = qty * ptr
                if base > 0:
                    discount_pct = round((disc_raw / base) * 100.0, 4)
            pack = _strip_excel_formula(_vendor_cell(row, "pack_size"))
            current["items"].append({
                "_row": rownum,
                "medicine_code": _strip_excel_formula(_vendor_cell(row, "item_code")),
                "medicine_name": item_name,
                "pack_size": pack,
                "manufacturer": _strip_excel_formula(_vendor_cell(row, "manufacturer")),
                "batch_number": batch,
                "expiry_date": expiry,
                "quantity": qty,
                "free_quantity": free,
                "mrp": mrp,
                "purchase_rate": ptr,
                "rate_a": mrp,
                "rate_b": mrp,
                "strip_conversion_factor": _parse_pack_scf(pack),
                "discount_pct": discount_pct,
                "hsn_code": _strip_excel_formula(_vendor_cell(row, "hsn_code")),
            })
        elif typ == "F":
            if current is None:
                continue
            taxable = _cell_float(_strip_excel_formula(row.get("cl2")) or row.get("cl2"))
            cgst = _cell_float(_strip_excel_formula(row.get("cl5")) or row.get("cl5"))
            sgst = _cell_float(_strip_excel_formula(row.get("cl7")) or row.get("cl7"))
            round_off = _cell_float(_strip_excel_formula(row.get("cl21")) or row.get("cl21"))
            invoice_value = _cell_float(_strip_excel_formula(row.get("cl22")) or row.get("cl22"))
            current["footer"] = {
                "taxable": taxable,
                "cgst": cgst,
                "sgst": sgst,
                "round_off": round_off,
                "invoice_value": invoice_value,
            }
            note_bits = []
            if invoice_value is not None:
                note_bits.append(f"Invoice value ₹{invoice_value:.2f}")
            if taxable is not None:
                note_bits.append(f"taxable ₹{taxable:.2f}")
            if cgst is not None or sgst is not None:
                note_bits.append(f"CGST ₹{(cgst or 0):.2f} / SGST ₹{(sgst or 0):.2f}")
            if round_off:
                note_bits.append(f"round-off {round_off}")
            if current.get("transporter"):
                note_bits.append(f"transporter {current['transporter']}")
            if current.get("place_of_supply"):
                note_bits.append(f"place of supply {current['place_of_supply']}")
            if note_bits:
                current["notes"] = "Imported from vendor CSV — " + "; ".join(note_bits)
            _finish()
        else:
            continue

    _finish()
    return blocks


def _group_named_purchase_rows(rows: List[dict]) -> List[dict]:
    """Group flat named-header rows by (supplier_name, invoice_number)."""
    groups: Dict[Tuple[str, str], dict] = {}
    order: List[Tuple[str, str]] = []
    for row in rows:
        supplier = _cell_str(row.get("supplier_name"))
        invoice = _cell_str(row.get("invoice_number"))
        med_code = _cell_str(row.get("medicine_code"))
        med_name = _cell_str(row.get("medicine_name") or row.get("item_name"))
        if _key_skipped(med_code) and _key_skipped(med_name):
            # Allow skip only when both empty; treat #-prefixed as skip
            if (med_code and med_code.startswith("#")) or (med_name and med_name.startswith("#")):
                continue
            if not med_code and not med_name:
                continue
        key = ((supplier or "").lower(), (invoice or "").lower())
        if key not in groups:
            bill_date = None
            entry_date = None
            try:
                bill_date = _cell_date(row.get("bill_date"))
            except ValueError:
                bill_date = None
            try:
                entry_date = _cell_date(row.get("entry_date"))
            except ValueError:
                entry_date = None
            groups[key] = {
                "invoice_number": invoice,
                "bill_date": bill_date,
                "entry_date": entry_date or bill_date or date.today(),
                "purchase_type": _cell_str(row.get("purchase_type")),
                "supplier_name": supplier,
                "payment_type": (_cell_str(row.get("payment_type")) or "credit").lower(),
                "tax_mode": (_cell_str(row.get("tax_mode")) or "exclusive").lower(),
                "store_code": _cell_str(row.get("store_code")),
                "notes": _cell_str(row.get("notes")),
                "footer": None,
                "items": [],
                "_header_row": row.get("_row", 0),
            }
            order.append(key)
        try:
            expiry = _cell_date(row.get("expiry_date"))
        except ValueError:
            try:
                expiry = _parse_ddmmyyyy(row.get("expiry_date"))
            except ValueError:
                expiry = None
        pack = _cell_str(row.get("pack_size"))
        scf = _cell_int(row.get("strip_conversion_factor"))
        if scf is None:
            scf = _parse_pack_scf(pack)
        groups[key]["items"].append({
            "_row": row.get("_row", 0),
            "medicine_code": med_code,
            "medicine_name": med_name,
            "pack_size": pack,
            "manufacturer": _cell_str(row.get("manufacturer")),
            "batch_number": _cell_str(row.get("batch_number")),
            "expiry_date": expiry,
            "quantity": _cell_float(row.get("quantity")),
            "free_quantity": _cell_float(row.get("free_quantity")) or 0.0,
            "mrp": _cell_float(row.get("mrp")),
            "purchase_rate": _cell_float(row.get("purchase_rate")),
            "rate_a": _cell_float(row.get("rate_a")),
            "rate_b": _cell_float(row.get("rate_b")),
            "strip_conversion_factor": scf,
            "discount_pct": _cell_float(row.get("discount_pct")) or 0.0,
            "hsn_code": _cell_str(row.get("hsn_code")),
        })
    return [groups[k] for k in order]


def _resolve_purchase_store_id(
    db: Session, hospital_id: int, store_code: Optional[str], store_cache: dict,
) -> Optional[int]:
    if store_code:
        return _resolve_store_id(db, hospital_id, store_code, store_cache)
    # Prefer a purchase-capable store, then master.
    purchase_store = db.query(PharmacyStore).filter(
        PharmacyStore.hospital_id == hospital_id,
        PharmacyStore.is_active == True,  # noqa: E712
        PharmacyStore.can_receive_supplier_purchase == True,  # noqa: E712
    ).order_by(PharmacyStore.is_default.desc(), PharmacyStore.id.asc()).first()
    if purchase_store:
        return purchase_store.id
    return get_master_store_id(db, hospital_id)


def _find_supplier_by_name(db: Session, hospital_id: int, name: str) -> Optional[PharmacySupplier]:
    return db.query(PharmacySupplier).filter(
        PharmacySupplier.hospital_id == hospital_id,
        sa_func.lower(PharmacySupplier.name) == name.strip().lower(),
        PharmacySupplier.is_active == True,  # noqa: E712
    ).first()


def _find_medicine_for_purchase(
    db: Session, hospital_id: int, *,
    medicine_code: Optional[str], medicine_name: Optional[str], pack_size: Optional[str],
    cache: dict,
) -> Tuple[Optional[Medicine], Optional[str]]:
    """Return (medicine, error_message). Match code first, then name (+ pack)."""
    if medicine_code:
        key = f"code:{medicine_code.lower()}"
        if key in cache:
            return cache[key], None
        med = db.query(Medicine).filter(
            Medicine.hospital_id == hospital_id,
            Medicine.medicine_code == medicine_code,
            Medicine.is_active == True,  # noqa: E712
        ).first()
        if med:
            cache[key] = med
            return med, None
        # Vendor item codes rarely match our medicine_code — fall through to name.

    if not medicine_name:
        return None, "Missing medicine_code / medicine_name"

    key = f"name:{medicine_name.lower()}"
    if key in cache and cache[key] is not None and not isinstance(cache[key], list):
        return cache[key], None

    matches = db.query(Medicine).filter(
        Medicine.hospital_id == hospital_id,
        sa_func.lower(Medicine.name) == medicine_name.strip().lower(),
        Medicine.is_active == True,  # noqa: E712
    ).all()
    if not matches:
        return None, f"Medicine '{medicine_name}' not found — import medicines first"
    if len(matches) == 1:
        cache[key] = matches[0]
        return matches[0], None

    if pack_size:
        pack_norm = pack_size.replace(" ", "").lower()
        narrowed = [
            m for m in matches
            if (m.packaging or "").replace(" ", "").lower() == pack_norm
            or pack_norm in (m.packaging or "").replace(" ", "").lower()
            or pack_norm in (m.strength or "").replace(" ", "").lower()
        ]
        if len(narrowed) == 1:
            cache[key] = narrowed[0]
            return narrowed[0], None

    codes = ", ".join(m.medicine_code for m in matches[:5])
    return None, (
        f"Ambiguous medicine name '{medicine_name}' "
        f"({len(matches)} matches: {codes}). Set medicine_code or packaging."
    )


def _next_purchase_number_import(db: Session, hospital_id: int) -> str:
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


def _recompute_purchase_totals_import(purchase: PharmacyPurchase, db: Session) -> None:
    subtotal = 0.0
    disc = 0.0
    tax = 0.0
    grand = 0.0
    tax_mode = getattr(purchase, "tax_mode", None) or "exclusive"
    for it in purchase.items:
        hsn_row = None
        if it.hsn_id:
            hsn_row = db.query(PharmacyHSN).filter(PharmacyHSN.id == it.hsn_id).first()
        elif it.medicine_id:
            med = db.query(Medicine).filter(Medicine.id == it.medicine_id).first()
            if med and med.hsn_id:
                it.hsn_id = med.hsn_id
                hsn_row = db.query(PharmacyHSN).filter(PharmacyHSN.id == med.hsn_id).first()
        qty = float(it.quantity or 0)
        rate = float(it.purchase_rate or 0)
        disc_pct = float(it.discount_pct or 0)
        base = qty * rate
        base_after = base * (1 - disc_pct / 100.0)
        tax_pct = 0.0
        if hsn_row:
            tax_pct = float(hsn_row.sgst_pct or 0) + float(hsn_row.cgst_pct or 0)
            if not tax_pct:
                tax_pct = float(hsn_row.igst_pct or 0)
        _taxable, tax_amt, line_total = compute_line_tax(base_after, tax_pct, tax_mode=tax_mode)
        it.tax_amount = tax_amt
        it.line_total = line_total
        it.sgst_pct = (hsn_row.sgst_pct or 0) if hsn_row else 0.0
        it.cgst_pct = (hsn_row.cgst_pct or 0) if hsn_row else 0.0
        it.igst_pct = (hsn_row.igst_pct if hsn_row else 0.0) or (it.sgst_pct + it.cgst_pct)
        subtotal += base
        disc += round(base - base_after, 2)
        tax += tax_amt
        grand += line_total
    purchase.subtotal = round(subtotal, 2)
    purchase.total_discount = round(disc, 2)
    purchase.total_tax = round(tax, 2)
    purchase.grand_total = round(grand, 2)


def _find_existing_purchase(
    db: Session, hospital_id: int, supplier_id: int, invoice_number: Optional[str],
) -> Optional[PharmacyPurchase]:
    inv = (invoice_number or "").strip()
    if not inv:
        return None
    return db.query(PharmacyPurchase).filter(
        PharmacyPurchase.hospital_id == hospital_id,
        PharmacyPurchase.supplier_id == supplier_id,
        PharmacyPurchase.invoice_number == inv,
    ).first()


def import_purchases(
    db: Session, user: User, content: bytes, filename: str,
    *, dry_run: bool, on_duplicate: str,
) -> dict:
    """Import purchase invoices as **draft** purchases.

    Accepts:
    - Vendor distributor CSV (H/T/F rows, CL1..CL31 headers) — e.g. Vasu Pharma export
    - Named-header .xlsx/.csv matching PURCHASE_HEADERS
    """
    summary = _empty_summary(dry_run=dry_run)
    rows = _parse_upload(content, filename, ["Purchases", "Purchase"])
    hospital_id = user.hospital_id

    if _looks_like_vendor_purchase(rows):
        blocks = _parse_vendor_purchase_blocks(rows)
    else:
        blocks = _group_named_purchase_rows(rows)

    if not blocks:
        summary["errors"].append({
            "sheet": "Purchases", "row": 0,
            "message": "No purchase rows found. Use vendor H/T/F CSV or the purchases template.",
        })
        summary["error_count"] = 1
        return summary

    store_cache: Dict[str, PharmacyStore] = {
        s.code.strip().lower(): s
        for s in db.query(PharmacyStore).filter(PharmacyStore.hospital_id == hospital_id).all()
    }
    medicine_cache: dict = {}
    supplier_cache: Dict[str, PharmacySupplier] = {}

    for block in blocks:
        items = block.get("items") or []
        if not items:
            continue

        # Count each line toward total_rows for preview parity with other imports
        for _ in items:
            summary["total_rows"] += 1

        supplier_name = block.get("supplier_name")
        invoice_number = block.get("invoice_number")
        header_row = block.get("_header_row") or (items[0].get("_row") if items else 0)
        preview_key = invoice_number or f"row-{header_row}"

        if not supplier_name:
            msg = "Missing supplier_name (vendor CSV CL3 / template supplier_name)"
            summary["errors"].append({"sheet": "Purchases", "row": header_row, "message": msg})
            summary["preview"].append({
                "row": header_row, "key": preview_key, "name": "",
                "status": "error", "message": msg, "sheet": "Purchases",
            })
            continue

        sup_key = supplier_name.lower()
        supplier = supplier_cache.get(sup_key)
        if not supplier:
            supplier = _find_supplier_by_name(db, hospital_id, supplier_name)
            if supplier:
                supplier_cache[sup_key] = supplier
        if not supplier:
            msg = f"Supplier '{supplier_name}' not found — import suppliers first"
            summary["errors"].append({"sheet": "Purchases", "row": header_row, "message": msg})
            summary["preview"].append({
                "row": header_row, "key": preview_key, "name": supplier_name,
                "status": "error", "message": msg, "sheet": "Purchases",
            })
            continue

        payment_type = (block.get("payment_type") or "credit").lower()
        if payment_type not in ("cash", "credit"):
            payment_type = "credit"
        tax_mode = (block.get("tax_mode") or "exclusive").lower()
        if tax_mode not in ("exclusive", "inclusive"):
            tax_mode = "exclusive"

        store_id = _resolve_purchase_store_id(db, hospital_id, block.get("store_code"), store_cache)
        if not store_id:
            msg = f"Store not found: '{block.get('store_code') or '(purchase/master store)'}'"
            summary["errors"].append({"sheet": "Purchases", "row": header_row, "message": msg})
            summary["preview"].append({
                "row": header_row, "key": preview_key, "name": supplier_name,
                "status": "error", "message": msg, "sheet": "Purchases",
            })
            continue

        existing = _find_existing_purchase(db, hospital_id, supplier.id, invoice_number)
        if existing and on_duplicate == "skip":
            summary["skipped"] += 1
            summary["preview"].append({
                "row": header_row, "key": preview_key, "name": supplier_name,
                "status": "skip",
                "message": f"Invoice already exists as {existing.purchase_number}",
                "sheet": "Purchases",
            })
            continue
        if existing and existing.status != "draft":
            msg = (
                f"Invoice #{invoice_number} already exists as {existing.purchase_number} "
                f"({existing.status}) — only draft purchases can be updated"
            )
            summary["errors"].append({"sheet": "Purchases", "row": header_row, "message": msg})
            summary["preview"].append({
                "row": header_row, "key": preview_key, "name": supplier_name,
                "status": "error", "message": msg, "sheet": "Purchases",
            })
            continue

        # Resolve all line items first; fail the whole invoice if any line errors
        resolved: List[dict] = []
        line_errors: List[str] = []
        for item in items:
            rownum = item.get("_row") or header_row
            batch = (item.get("batch_number") or "").strip()
            qty = item.get("quantity")
            expiry = item.get("expiry_date")
            rate = item.get("purchase_rate")
            errs: List[str] = []
            if not batch:
                errs.append("Missing batch_number")
            if not expiry:
                errs.append("Missing or invalid expiry_date")
            if qty is None or qty <= 0:
                errs.append("quantity must be > 0")
            if rate is None or rate < 0:
                errs.append("Missing purchase_rate (vendor CSV PTR / CL11)")

            med, med_err = _find_medicine_for_purchase(
                db, hospital_id,
                medicine_code=item.get("medicine_code"),
                medicine_name=item.get("medicine_name"),
                pack_size=item.get("pack_size"),
                cache=medicine_cache,
            )
            # If code miss but name hit inside helper — ok. If code provided but
            # only name works, helper already fell through. If both fail:
            if med_err and not med:
                # Retry name-only when vendor code didn't match
                if item.get("medicine_code") and item.get("medicine_name"):
                    med, med_err = _find_medicine_for_purchase(
                        db, hospital_id,
                        medicine_code=None,
                        medicine_name=item.get("medicine_name"),
                        pack_size=item.get("pack_size"),
                        cache=medicine_cache,
                    )
            if not med:
                errs.append(med_err or "Medicine not found")

            if errs:
                msg = f"Line {rownum}: " + "; ".join(errs)
                line_errors.append(msg)
                summary["errors"].append({"sheet": "Purchases", "row": rownum, "message": msg})
                summary["preview"].append({
                    "row": rownum,
                    "key": item.get("medicine_code") or item.get("medicine_name") or "",
                    "name": batch or "",
                    "status": "error", "message": msg, "sheet": "Purchases",
                })
                continue

            scf = item.get("strip_conversion_factor") or med.strip_conversion_factor or 1
            scf = max(1, int(scf))
            resolved.append({
                "row": rownum,
                "medicine": med,
                "batch_number": batch,
                "expiry_date": expiry,
                "quantity": float(qty),
                "free_quantity": float(item.get("free_quantity") or 0),
                "mrp": round_money(item.get("mrp") or med.mrp or 0),
                "purchase_rate": round_money(rate),
                "rate_a": round_money(
                    item.get("rate_a") if item.get("rate_a") is not None else (med.rate_a or 0)
                ),
                "rate_b": round_money(
                    item.get("rate_b") if item.get("rate_b") is not None else (med.rate_b or 0)
                ),
                "strip_conversion_factor": scf,
                "discount_pct": float(item.get("discount_pct") or 0),
            })

        if line_errors:
            # Don't create a partial purchase for this invoice
            continue
        if not resolved:
            continue

        if existing and on_duplicate == "update":
            for old in list(existing.items):
                db.delete(old)
            db.flush()
            purchase = existing
            purchase.entry_date = block.get("entry_date") or purchase.entry_date
            purchase.bill_date = block.get("bill_date") or purchase.bill_date
            purchase.payment_type = payment_type
            purchase.purchase_type = block.get("purchase_type") or purchase.purchase_type
            purchase.tax_mode = tax_mode
            purchase.notes = block.get("notes") or purchase.notes
            purchase.store_id = store_id
            status = "update"
        else:
            purchase = PharmacyPurchase(
                purchase_number=_next_purchase_number_import(db, hospital_id),
                entry_date=block.get("entry_date") or date.today(),
                supplier_id=supplier.id,
                invoice_number=invoice_number,
                bill_date=block.get("bill_date"),
                payment_type=payment_type,
                purchase_type=block.get("purchase_type"),
                tax_mode=tax_mode,
                status="draft",
                notes=block.get("notes"),
                created_by=user.id,
                store_id=store_id,
                hospital_id=hospital_id,
            )
            db.add(purchase)
            db.flush()
            # Avoid unique collisions on concurrent imports
            for _attempt in range(3):
                clash = db.query(PharmacyPurchase).filter(
                    PharmacyPurchase.purchase_number == purchase.purchase_number,
                    PharmacyPurchase.id != purchase.id,
                ).first()
                if not clash:
                    break
                purchase.purchase_number = _next_purchase_number_import(db, hospital_id)
                db.flush()
            status = "new"

        for r in resolved:
            db.add(PharmacyPurchaseItem(
                purchase_id=purchase.id,
                medicine_id=r["medicine"].id,
                batch_number=r["batch_number"],
                expiry_date=r["expiry_date"],
                mrp=r["mrp"],
                quantity=r["quantity"],
                free_quantity=r["free_quantity"],
                purchase_rate=r["purchase_rate"],
                rate_a=r["rate_a"],
                rate_b=r["rate_b"],
                strip_conversion_factor=r["strip_conversion_factor"],
                discount_pct=r["discount_pct"],
                hsn_id=r["medicine"].hsn_id,
            ))
        db.flush()
        db.refresh(purchase)
        _recompute_purchase_totals_import(purchase, db)

        if status == "new":
            summary["created"] += 1
        else:
            summary["updated"] += 1
        summary["preview"].append({
            "row": header_row,
            "key": preview_key,
            "name": f"{supplier_name} — {len(resolved)} items — ₹{purchase.grand_total:.2f}",
            "status": status,
            "message": f"Draft {purchase.purchase_number}",
            "sheet": "Purchases",
        })

    summary["error_count"] = len(summary["errors"])
    return summary


def build_purchases_template() -> bytes:
    def build(wb: openpyxl.Workbook) -> None:
        ws = wb.active
        ws.title = "Purchases"
        ws.append(PURCHASE_HEADERS)
        ws.append([
            "VASU PHARMA", "2026-27/TAX/1808", "2026-08-01", "2026-08-01",
            "credit", "Direct", "exclusive", "", "Sample import row",
            "AF200", "AF-200", "HAH022603", "2028-01-31",
            20, 0, 77.20, 58.82, 77.20, 77.20, 1, 0, "5*1", "30049029",
        ])
        _append_instructions(wb, [
            "KT HEALTH ERP — Purchase Import",
            "",
            "Creates DRAFT purchases (review then Confirm in Purchases).",
            "Supplier and medicines must already exist.",
            "",
            "Option A — Named template (this sheet):",
            "  Required: supplier_name, medicine_code OR medicine_name, batch_number,",
            "  expiry_date (YYYY-MM-DD), quantity, purchase_rate",
            "  Rows with the same supplier_name + invoice_number become one purchase.",
            "",
            "Option B — Vendor distributor CSV (e.g. Vasu Pharma tax-invoice export):",
            "  Upload the H/T/F CSV as-is (CL1..CL31). Header (H) has invoice # + date;",
            "  detail (T) rows map: Item Name→medicine, Pack Size, Batch, Expiry,",
            "  QTY, Package(free), MRP→mrp/rate_a/rate_b, PTR→purchase_rate, HSN.",
            "  Footer (F) invoice value is stored in purchase notes for reconciliation.",
            "",
            "Tax % is taken from each medicine's HSN master (not from the CSV GST columns).",
            "on_duplicate=skip leaves existing invoices alone; update replaces draft lines only.",
        ])

    return _workbook_bytes(build)
