"""Pharmacy historical sales CSV/XLSX import."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.hospital import Hospital
from app.models.pharmacy import PharmacyInventory, PharmacySale, PharmacyStore
from app.models.user import User
from app.services.pharmacy_import import (
    _append_instructions,
    _cell_float,
    _cell_str,
    _empty_summary,
    _find_medicine_for_purchase,
    _merge_unmatched_medicines,
    _unmatched_catalog_entry,
    _workbook_bytes,
    inspect_letter_import,
    resolve_mapped_rows,
)
from app.services.pharmacy_store_service import resolve_store_id

SALE_HEADERS = [
    "sale_number", "sale_date", "payment_type", "tax_mode", "store_code",
    "patient_name", "patient_phone", "patient_address", "doctor_name", "doctor_number",
    "bill_discount_amount",
    "medicine_code", "medicine_name", "batch_number",
    "quantity", "qty_unit", "rate", "discount_pct", "rate_tier",
]

REQUIRED_SALE_LETTER_FIELDS = ["sale_date", "quantity"]
_VALID_SALE_TARGETS = set(SALE_HEADERS)
SALE_REQUIRE_ANY = [["medicine_code", "medicine_name"]]

SALE_IMPORT_ALIASES = [
    ("sale_number", ["sale_number", "bill_no", "bill_number", "invoice_number", "invoice_no"]),
    ("sale_date", ["sale_date", "date", "bill_date", "invoice_date"]),
    ("payment_type", ["payment_type", "payment"]),
    ("tax_mode", ["tax_mode"]),
    ("store_code", ["store_code", "store"]),
    ("patient_name", ["patient_name", "patient", "customer", "customer_name"]),
    ("patient_phone", ["patient_phone", "phone", "mobile"]),
    ("patient_address", ["patient_address", "address"]),
    ("doctor_name", ["doctor_name", "doctor", "prescriber"]),
    ("doctor_number", ["doctor_number"]),
    ("bill_discount_amount", ["bill_discount_amount", "bill_discount"]),
    ("medicine_code", ["medicine_code", "item_code", "product_code", "sku"]),
    ("medicine_name", ["medicine_name", "item_name", "item", "product", "product_name"]),
    ("batch_number", ["batch_number", "batch", "batch_no", "lot"]),
    ("quantity", ["quantity", "qty"]),
    ("qty_unit", ["qty_unit", "unit"]),
    ("rate", ["rate", "sale_rate", "selling_rate", "mrp", "rate_a"]),
    ("discount_pct", ["discount_pct", "discount", "disc"]),
    ("rate_tier", ["rate_tier", "tier"]),
]


def inspect_sales_import(
    content: bytes, filename: str, *,
    row_start: Optional[int] = None,
    row_end: Optional[int] = None,
) -> dict:
    return inspect_letter_import(
        content, filename,
        row_start=row_start, row_end=row_end,
        required_fields=REQUIRED_SALE_LETTER_FIELDS,
        aliases=SALE_IMPORT_ALIASES,
    )


def _cell_datetime(v) -> Optional[datetime]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime.combine(v, time.min)
    s = _cell_str(v)
    if s is None:
        return None
    s = s.strip()
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None)
    except ValueError as exc:
        raise ValueError(
            f"'{s}' is not a valid date/time (use YYYY-MM-DD or YYYY-MM-DD HH:MM)"
        ) from exc


def build_sales_template() -> bytes:
    def build(wb) -> None:
        ws = wb.active
        ws.title = "Sales"
        ws.append(SALE_HEADERS)
        ws.append([
            "SALE-LEGACY-001", "2025-06-15 10:30", "cash", "inclusive", "",
            "Ravi Kumar", "9876543210", "", "Dr. Sharma", "",
            0,
            "AF200", "AF-200", "BATCH01",
            10, "tablet", 7.72, 0, "A",
        ])
        ws.append([
            "SALE-LEGACY-001", "2025-06-15 10:30", "cash", "inclusive", "",
            "Ravi Kumar", "9876543210", "", "Dr. Sharma", "",
            0,
            "PCM500", "Paracetamol 500", "BATCH02",
            2, "strip", 20.0, 0, "A",
        ])
        ws.append([
            "SALE-LEGACY-002", "2025-06-16", "credit", "inclusive", "",
            "Walk-in", "", "", "", "",
            0,
            "AF200", "", "",
            5, "tablet", "", 0, "A",
        ])
        _append_instructions(wb, [
            "KT HEALTH ERP — Pharmacy Sales Import",
            "",
            "Import historical POS sales into Sales History.",
            "Medicines must already exist (import catalog first).",
            "",
            "Grouping: rows that share the same sale_number become one sale.",
            "Leave sale_number blank to auto-generate one sale per row.",
            "",
            "Required columns:",
            "  sale_date (YYYY-MM-DD or YYYY-MM-DD HH:MM)",
            "  medicine_code OR medicine_name",
            "  quantity (> 0)",
            "",
            "Optional: payment_type (cash|credit), tax_mode (inclusive|exclusive),",
            "  store_code, patient_*, doctor_*, bill_discount_amount,",
            "  batch_number, qty_unit (tablet|strip, default tablet),",
            "  rate (override), discount_pct, rate_tier (A|B).",
            "",
            "Stock option (chosen in the import dialog, not in the file):",
            "  Deduct stock — requires available batch stock (batch_number or FIFO).",
            "  Record only — creates sales without changing inventory",
            "    (batch_number optional; uses a HIST-IMPORT placeholder batch).",
            "",
            "Duplicate sale_number: skipped (sales are not updated in place).",
        ])

    return _workbook_bytes(build)


def _resolve_store_code(db: Session, user: User, store_code: Optional[str]) -> int:
    if not store_code:
        return resolve_store_id(db, user, None)
    store = db.query(PharmacyStore).filter(
        PharmacyStore.hospital_id == user.hospital_id,
        PharmacyStore.code == store_code,
        PharmacyStore.is_active == True,  # noqa: E712
    ).first()
    if not store:
        raise ValueError(f"Unknown store_code '{store_code}'")
    return resolve_store_id(db, user, store.id)


def _find_batch(
    db: Session, *, medicine_id: int, hospital_id: int, store_id: int, batch_number: str,
) -> Optional[PharmacyInventory]:
    return db.query(PharmacyInventory).filter(
        PharmacyInventory.medicine_id == medicine_id,
        PharmacyInventory.hospital_id == hospital_id,
        PharmacyInventory.store_id == store_id,
        PharmacyInventory.batch_number == batch_number,
        PharmacyInventory.is_active == True,  # noqa: E712
    ).first()


def _group_sale_rows(rows: List[dict]) -> "OrderedDict[str, List[dict]]":
    groups: "OrderedDict[str, List[dict]]" = OrderedDict()
    for row in rows:
        sale_no = _cell_str(row.get("sale_number"))
        key = sale_no if sale_no else f"__auto_{row.get('_row')}"
        groups.setdefault(key, []).append(row)
    return groups


@dataclass
class _PendingLine:
    medicine_id: int
    medicine_label: str
    batch_id: Optional[int]
    qty_tabs: float
    qty_strips: float
    rate: Optional[float]
    discount_pct: float
    rate_tier: str


@dataclass
class _PendingSale:
    row_num: int
    sale_number: Optional[str]
    sale_date: datetime
    payment_type: str
    tax_mode: str
    store_id: int
    patient_name: Optional[str]
    patient_phone: Optional[str]
    patient_address: Optional[str]
    doctor_name: Optional[str]
    doctor_number: Optional[str]
    bill_discount_amount: float
    lines: List[_PendingLine] = field(default_factory=list)


def import_sales(
    db: Session,
    user: User,
    content: bytes,
    filename: str,
    *,
    dry_run: bool = False,
    affect_stock: bool = False,
    on_duplicate: str = "skip",
    column_mapping: Optional[dict] = None,
    row_start: Optional[int] = None,
    row_end: Optional[int] = None,
) -> dict:
    """Import historical pharmacy sales into Sales History.

    affect_stock=True deducts inventory (like live POS).
    affect_stock=False records the sale only (stock_affected=False).
    Unmatched catalog names are returned in ``unmatched_medicines``.
    """
    from app.routes.pharmacy import SaleItemIn, _next_sale_number, _process_sale_lines

    summary = _empty_summary(dry_run=dry_run)
    try:
        rows = resolve_mapped_rows(
            content, filename,
            column_mapping=column_mapping,
            valid_targets=_VALID_SALE_TARGETS,
            required_fields=REQUIRED_SALE_LETTER_FIELDS,
            named_sheet_names=["Sales", "Sheet1"],
            row_start=row_start,
            row_end=row_end,
            require_any=SALE_REQUIRE_ANY if column_mapping else None,
        )
    except HTTPException as exc:
        summary["errors"].append({"sheet": "Sales", "row": 0, "message": str(exc.detail)})
        summary["error_count"] = 1
        return summary
    if not rows:
        raise HTTPException(status_code=400, detail="No data rows found in the file")

    summary["total_rows"] = len(rows)
    on_duplicate = on_duplicate if on_duplicate in ("skip", "update") else "skip"
    med_cache: dict = {}
    groups = _group_sale_rows(rows)
    pending: List[_PendingSale] = []
    unmatched_entries: List[dict] = []

    for group_key, group_rows in groups.items():
        first = group_rows[0]
        row_num = int(first.get("_row") or 0)
        preview_key = group_key if not str(group_key).startswith("__auto_") else ""
        patient_label = _cell_str(first.get("patient_name")) or "—"

        try:
            sale_dt = _cell_datetime(first.get("sale_date"))
            if not sale_dt:
                raise ValueError("sale_date is required")

            payment_type = (_cell_str(first.get("payment_type")) or "cash").lower()
            if payment_type not in ("cash", "credit"):
                raise ValueError("payment_type must be cash or credit")

            tax_mode = (_cell_str(first.get("tax_mode")) or "inclusive").lower()
            if tax_mode not in ("inclusive", "exclusive"):
                raise ValueError("tax_mode must be inclusive or exclusive")

            bill_disc = _cell_float(first.get("bill_discount_amount")) or 0.0
            if bill_disc < 0:
                raise ValueError("bill_discount_amount cannot be negative")

            store_id = _resolve_store_code(db, user, _cell_str(first.get("store_code")))

            provided_number = None if str(group_key).startswith("__auto_") else group_key
            if provided_number:
                existing = db.query(PharmacySale).filter(
                    PharmacySale.sale_number == provided_number,
                    PharmacySale.hospital_id == user.hospital_id,
                ).first()
                if existing:
                    if on_duplicate == "skip":
                        summary["skipped"] += 1
                        summary["preview"].append({
                            "row": row_num,
                            "key": provided_number,
                            "name": patient_label,
                            "status": "skip",
                            "message": "Sale number already exists",
                        })
                        continue
                    raise ValueError(
                        "Updating existing sales is not supported — "
                        "change sale_number or leave duplicates to skip"
                    )

            lines: List[_PendingLine] = []
            for lr in group_rows:
                med_code = _cell_str(lr.get("medicine_code"))
                med_name = _cell_str(lr.get("medicine_name"))
                if not med_code and not med_name:
                    raise ValueError("medicine_code or medicine_name is required")

                med, med_err = _find_medicine_for_purchase(
                    db, user.hospital_id,
                    medicine_code=med_code, medicine_name=med_name, pack_size=None,
                    cache=med_cache,
                )
                if not med:
                    label = med_name or med_code or "Unknown"
                    rate_val = None
                    try:
                        rate_val = _cell_float(lr.get("rate"))
                    except ValueError:
                        rate_val = None
                    unmatched_entries.append(_unmatched_catalog_entry(
                        {
                            "medicine_code": med_code,
                            "medicine_name": med_name,
                            "mrp": rate_val,
                            "purchase_rate": None,
                        },
                        label,
                        int(lr.get("_row") or row_num),
                    ))
                    raise ValueError(med_err or "Medicine not found")

                qty = _cell_float(lr.get("quantity"))
                if qty is None or qty <= 0:
                    raise ValueError(f"quantity must be > 0 for {med.name}")

                qty_unit = (_cell_str(lr.get("qty_unit")) or "tablet").lower()
                if qty_unit not in ("tablet", "strip"):
                    raise ValueError("qty_unit must be tablet or strip")

                rate = _cell_float(lr.get("rate"))
                disc = _cell_float(lr.get("discount_pct")) or 0.0
                if disc < 0 or disc > 100:
                    raise ValueError("discount_pct must be between 0 and 100")

                rate_tier = (_cell_str(lr.get("rate_tier")) or "A").upper()
                if rate_tier not in ("A", "B"):
                    raise ValueError("rate_tier must be A or B")

                batch_number = _cell_str(lr.get("batch_number"))
                batch_id = None
                if batch_number:
                    batch = _find_batch(
                        db,
                        medicine_id=med.id,
                        hospital_id=user.hospital_id,
                        store_id=store_id,
                        batch_number=batch_number,
                    )
                    if not batch:
                        raise ValueError(
                            f"Batch '{batch_number}' not found for {med.medicine_code} "
                            f"in the selected store"
                        )
                    if affect_stock:
                        # qty check deferred to _process_sale_lines (needs tab/strip convert)
                        pass
                    batch_id = batch.id

                lines.append(_PendingLine(
                    medicine_id=med.id,
                    medicine_label=med.medicine_code or med.name,
                    batch_id=batch_id,
                    qty_tabs=qty if qty_unit == "tablet" else 0.0,
                    qty_strips=qty if qty_unit == "strip" else 0.0,
                    rate=rate,
                    discount_pct=disc,
                    rate_tier=rate_tier,
                ))

            if not lines:
                raise ValueError("Sale has no line items")

            pending.append(_PendingSale(
                row_num=row_num,
                sale_number=provided_number,
                sale_date=sale_dt,
                payment_type=payment_type,
                tax_mode=tax_mode,
                store_id=store_id,
                patient_name=_cell_str(first.get("patient_name")),
                patient_phone=_cell_str(first.get("patient_phone")),
                patient_address=_cell_str(first.get("patient_address")),
                doctor_name=_cell_str(first.get("doctor_name")),
                doctor_number=_cell_str(first.get("doctor_number")),
                bill_discount_amount=bill_disc,
                lines=lines,
            ))
        except Exception as exc:
            summary["error_count"] += 1
            msg = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
            summary["errors"].append({"sheet": "Sales", "row": row_num, "message": msg})
            summary["preview"].append({
                "row": row_num,
                "key": preview_key,
                "name": patient_label,
                "status": "error",
                "message": msg,
            })

    if unmatched_entries:
        summary["unmatched_medicines"] = _merge_unmatched_medicines(
            summary.get("unmatched_medicines") or [], unmatched_entries,
        )

    if not pending and summary["error_count"] > 0:
        return summary

    _hosp = db.query(Hospital).filter(Hospital.id == user.hospital_id).first()
    tax_on_free = bool(getattr(_hosp, "pharmacy_tax_on_free", False)) if _hosp else False

    for ps in pending:
        nested = db.begin_nested()
        try:
            sale_number = ps.sale_number or _next_sale_number(db, user.hospital_id)
            sale = PharmacySale(
                sale_number=sale_number,
                sale_date=ps.sale_date,
                payment_type=ps.payment_type,
                patient_phone=ps.patient_phone,
                patient_name=ps.patient_name,
                patient_address=ps.patient_address,
                doctor_number=ps.doctor_number,
                doctor_name=ps.doctor_name,
                status="completed",
                billing_mode="cash_at_pharmacy",
                tax_mode=ps.tax_mode,
                stock_affected=bool(affect_stock),
                created_by=user.id,
                store_id=ps.store_id,
                hospital_id=user.hospital_id,
            )
            db.add(sale)
            db.flush()

            sale_items = [
                SaleItemIn(
                    medicine_id=ln.medicine_id,
                    batch_id=ln.batch_id,
                    qty_tabs=ln.qty_tabs,
                    qty_strips=ln.qty_strips,
                    rate=ln.rate,
                    discount_pct=ln.discount_pct,
                    rate_tier=ln.rate_tier,
                )
                for ln in ps.lines
            ]
            subtotal, disc_total, tax_total, grand, bill_disc_applied = _process_sale_lines(
                db, sale, sale_items, user, ps.store_id,
                ps.tax_mode, tax_on_free, ps.bill_discount_amount,
                ledger_note=f"Imported sale {sale.sale_number}",
                affect_stock=bool(affect_stock),
            )
            sale.subtotal = round(subtotal, 2)
            sale.discount_total = round(disc_total, 2)
            sale.bill_discount_amount = round(bill_disc_applied, 2)
            sale.tax_total = round(tax_total, 2)
            sale.grand_total = round(grand, 2)

            labels = [
                f"{ln.medicine_label}×{ln.qty_tabs or ln.qty_strips}"
                for ln in ps.lines[:3]
            ]
            summary["created"] += 1
            summary["preview"].append({
                "row": ps.row_num,
                "key": sale_number,
                "name": ps.patient_name or "—",
                "status": "new",
                "message": (
                    f"{len(ps.lines)} item(s); ₹{sale.grand_total:.2f}"
                    + ("; stock deducted" if affect_stock else "; no stock change")
                    + (f" — {', '.join(labels)}" if labels else "")
                ),
            })
            nested.commit()
        except Exception as exc:
            nested.rollback()
            summary["error_count"] += 1
            msg = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
            summary["errors"].append({"sheet": "Sales", "row": ps.row_num, "message": msg})
            summary["preview"].append({
                "row": ps.row_num,
                "key": ps.sale_number or "",
                "name": ps.patient_name or "—",
                "status": "error",
                "message": msg,
            })

    if unmatched_entries:
        summary["unmatched_medicines"] = _merge_unmatched_medicines(
            summary.get("unmatched_medicines") or [], unmatched_entries,
        )
    return summary
