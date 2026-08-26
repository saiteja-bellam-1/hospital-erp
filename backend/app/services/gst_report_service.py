"""Hospital-wide sales, purchase, and GST registers for the Billing hub.

Ledgers stay separate (appointments / lab orders / bills / pharmacy POS /
purchases). This module unions them for reports and applies the IP-pharmacy
double-count rule: taxable outward GST is pharmacy_sales; admission bill
pharmacy lines are the same supply and are excluded from inpatient billed
when pharmacy_ip sales are counted.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sql_func

from app.models.billing import Bill, BillItem, Payment
from app.models.patient import Patient
from app.models.outpatient import Appointment
from app.models.lab import PatientLabOrder
from app.models.pharmacy import (
    PharmacySale, PharmacySaleItem, PharmacyHSN, Medicine,
    PharmacyPurchase, PharmacyPurchaseItem, PharmacySupplier,
    PharmacySaleReturn, PharmacySaleReturnItem,
    PharmacyPurchaseReturn, PharmacyPurchaseReturnItem,
)
from app.models.canteen import CanteenSale
from app.services.gst_classification import (
    MODULE_LABELS, ALL_MODULES, SAC_HEALTHCARE, TAX_EXEMPT, TAX_TAXABLE,
    module_for_bill_type, is_pharmacy_sourced_item, split_gst_amounts,
)


SKIP_APT_STATUS = frozenset({"cancelled", "deleted", "consolidated", "no_show"})
SKIP_LAB_STATUS = frozenset({"cancelled", "deleted", "consolidated"})
SKIP_BILL_STATUS = frozenset({"cancelled"})
SKIP_BILL_SUBTYPES = frozenset({"interim", "advance_receipt"})
SKIP_BILL_TYPES = frozenset({"credit_note"})


def _as_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def parse_date_range(date_from: Optional[str], date_to: Optional[str]):
    today = date.today()
    d_to = date.fromisoformat(date_to) if date_to else today
    d_from = date.fromisoformat(date_from) if date_from else (d_to - timedelta(days=30))
    return d_from, d_to


def _in_range(value, d_from: date, d_to: date) -> bool:
    d = _as_date(value)
    if d is None:
        return False
    return d_from <= d <= d_to


def _money(v) -> float:
    return round(float(v or 0), 2)


def _empty_totals():
    return {
        "billed": 0.0, "discount": 0.0, "tax": 0.0, "net": 0.0,
        "collected": 0.0, "outstanding": 0.0, "count": 0,
    }


def _add_totals(dest, billed, discount, tax, collected, count=1):
    billed = _money(billed)
    discount = _money(discount)
    tax = _money(tax)
    collected = _money(collected)
    net = _money(billed - discount + tax) if tax else _money(billed - discount)
    # For rows where billed already includes tax (pharmacy grand), net = billed.
    dest["billed"] = _money(dest["billed"] + billed)
    dest["discount"] = _money(dest["discount"] + discount)
    dest["tax"] = _money(dest["tax"] + tax)
    dest["collected"] = _money(dest["collected"] + collected)
    dest["count"] += count


def _finalize_totals(t):
    t["net"] = _money(t["billed"])
    t["outstanding"] = _money(max(t["billed"] - t["collected"], 0))
    # Effective tax % of pre-tax bill value (billed treated as tax-inclusive).
    taxable = _money(max(t["billed"] - t["tax"], 0)) if t["tax"] else _money(t["billed"])
    t["taxable"] = taxable
    t["tax_pct"] = _effective_tax_pct(t["tax"], taxable)
    return t


def _payments_total(bill) -> float:
    return _money(sum(float(p.amount_paid or 0) for p in (bill.payments or [])))


def _effective_tax_pct(tax, taxable) -> float:
    """Tax as % of taxable (pre-tax) bill value."""
    taxable = float(taxable or 0)
    tax = float(tax or 0)
    if abs(taxable) < 1e-9 or abs(tax) < 1e-9:
        return 0.0
    return round(abs(tax) / abs(taxable) * 100.0, 2)


def _rate_key(rate) -> str:
    """Stable JSON key for a GST rate, e.g. 5.0 -> '5'."""
    r = round(float(rate or 0), 2)
    if r == int(r):
        return str(int(r))
    return f"{r:g}"


def _rate_label_from_pcts(rates) -> str:
    """Unique GST rates on a bill, e.g. '5%, 12%'."""
    uniq = sorted({
        round(float(r or 0), 2)
        for r in (rates or [])
        if r is not None and float(r or 0) > 0
    })
    if not uniq:
        return "0%"
    return ", ".join(f"{r:g}%" for r in uniq)


def _line_gst_rate(item) -> float:
    """Total GST % for rate-column bucketing (snapshot or legacy).

    HSN / purchase / sale lines store IGST as the interstate *alternative*
    (SGST+CGST), not an additive third component. Prefer CGST+SGST; use IGST
    only when both halves are zero — same rule as split_gst_amounts / billing.
    """
    sgst = float(getattr(item, "sgst_pct", 0) or 0)
    cgst = float(getattr(item, "cgst_pct", 0) or 0)
    igst = float(getattr(item, "igst_pct", 0) or 0)
    if sgst or cgst:
        return sgst + cgst
    if igst > 0:
        return igst
    for attr in ("tax_pct", "tax_percentage"):
        v = getattr(item, attr, None)
        if v is not None and float(v or 0) > 0:
            return float(v)
    return 0.0


def _empty_rate_bucket():
    return {"taxable": 0.0, "tax": 0.0, "amount": 0.0}


def _add_to_rate_map(dest: dict, rate, taxable, tax):
    key = _rate_key(rate)
    b = dest.setdefault(key, _empty_rate_bucket())
    taxable = _money(taxable)
    tax = _money(tax)
    b["taxable"] = _money(b["taxable"] + taxable)
    b["tax"] = _money(b["tax"] + tax)
    b["amount"] = _money(b["amount"] + taxable + tax)


def _merge_rate_maps(dest: dict, src: dict, sign: float = 1.0):
    for key, vals in (src or {}).items():
        b = dest.setdefault(key, _empty_rate_bucket())
        b["taxable"] = _money(b["taxable"] + sign * float(vals.get("taxable") or 0))
        b["tax"] = _money(b["tax"] + sign * float(vals.get("tax") or 0))
        b["amount"] = _money(b["amount"] + sign * float(vals.get("amount") or 0))


def _collect_rate_columns(*row_lists) -> list:
    rates = set()
    for rows in row_lists:
        for row in (rows or []):
            for k in (row.get("tax_by_rate") or {}):
                rates.add(round(float(k), 2))
    out = []
    for r in sorted(rates):
        out.append(int(r) if r == int(r) else r)
    return out


def _sale_items_by_rate(items, tax_mode: str = "exclusive") -> dict:
    """tax_by_rate for pharmacy POS lines (taxable bill amount per GST %)."""
    from app.utils.pharmacy_pricing import compute_line_tax

    by_rate = {}
    for it in items or []:
        rate = _line_gst_rate(it)
        base = float(it.quantity or 0) * float(it.rate or 0)
        gross = base * (1 - float(it.discount_pct or 0) / 100.0)
        taxable, tax_amt, _line = compute_line_tax(gross, rate, tax_mode=tax_mode or "exclusive")
        _add_to_rate_map(by_rate, rate, taxable, tax_amt)
    return by_rate


def _bill_items_by_rate(items) -> dict:
    """tax_by_rate for hospital BillItem lines."""
    by_rate = {}
    for it in items or []:
        rate = _line_gst_rate(it)
        qty = float(it.quantity or 1)
        unit = float(it.unit_price or 0)
        disc = float(it.discount_percentage or 0)
        gross = qty * unit * (1 - disc / 100.0)
        line_tax = (
            float(it.sgst_amount or 0)
            + float(it.cgst_amount or 0)
            + float(it.igst_amount or 0)
        )
        if line_tax <= 0 and rate > 0:
            line_tax = _money(gross * rate / 100.0)
        # Prefer total_price as billed line amount when present
        total = float(it.total_price or 0)
        if total > 0 and line_tax > 0 and abs(total - (gross + line_tax)) < 0.05:
            taxable = _money(total - line_tax)
        elif total > 0 and rate <= 0:
            taxable = _money(total)
            line_tax = 0.0
        else:
            taxable = _money(gross)
        _add_to_rate_map(by_rate, rate, taxable, line_tax)
    return by_rate


def _purchase_items_by_rate(items) -> dict:
    by_rate = {}
    for it in items or []:
        taxable, sgst, cgst, igst = _purchase_taxable_and_gst(it)
        rate = _line_gst_rate(it)
        _add_to_rate_map(by_rate, rate, taxable, sgst + cgst + igst)
    return by_rate


def _invoice_row(module, inv_date, number, billed, discount, tax, collected,
                 party="", gstin="", hsn="", taxable=None, tax_rates="",
                 tax_by_rate=None, extra=None):
    billed = _money(billed)
    collected = _money(collected)
    tax = _money(tax)
    # Prefer explicit taxable; otherwise treat billed as tax-inclusive grand total.
    if taxable is None:
        taxable_val = _money(max(billed - tax, 0)) if tax else billed
    else:
        taxable_val = _money(taxable)
    tax_pct = _effective_tax_pct(tax, taxable_val)
    by_rate = tax_by_rate or {}
    if not by_rate:
        # Single bucket from header totals (OPD/lab/canteen / header-only tax).
        _add_to_rate_map(by_rate, tax_pct if tax_pct > 0 else 0, taxable_val, tax)
    rates_label = tax_rates or _rate_label_from_pcts(
        [float(k) for k in by_rate.keys() if float(k) > 0]
    )
    return {
        "module": module,
        "module_label": MODULE_LABELS.get(module, module),
        "date": inv_date.isoformat() if hasattr(inv_date, "isoformat") else str(inv_date or ""),
        "number": number or "",
        "party": party or "",
        "gstin": gstin or "",
        "hsn_sac": hsn or "",
        "billed": billed,
        "discount": _money(discount),
        "taxable": taxable_val,
        "tax": tax,
        "tax_pct": tax_pct,
        "tax_rates": rates_label,
        "tax_by_rate": by_rate,
        "net": billed,
        "collected": collected,
        "outstanding": _money(max(billed - collected, 0)),
        **(extra or {}),
    }


def collect_sales_invoices(db: Session, hospital_id: int, d_from: date, d_to: date) -> list:
    """Invoice-level rows across modules. One row per source document."""
    rows = []

    # OPD appointments
    apts = db.query(Appointment).join(Patient).filter(
        Patient.hospital_id == hospital_id,
        sql_func.date(Appointment.appointment_date) >= d_from,
        sql_func.date(Appointment.appointment_date) <= d_to,
    ).all()
    for a in apts:
        if (a.payment_status or "") in SKIP_APT_STATUS:
            continue
        billed = _money(a.final_amount) if a.final_amount else _money(
            (a.consultation_fee or 0) + (a.registration_fee or 0) - (a.discount_amount or 0)
        )
        collected = billed if (a.payment_status or "") == "paid" else 0.0
        if (a.payment_status or "") == "partial":
            collected = 0.0
        p = a.patient
        name = f"{p.first_name} {p.last_name}" if p else ""
        gstin = getattr(p, "gstin", None) if p else None
        rows.append(_invoice_row(
            "opd", _as_date(a.appointment_date), a.appointment_number,
            billed, a.discount_amount or 0, 0, collected,
            party=name, gstin=gstin or "", hsn=SAC_HEALTHCARE,
            extra={"tax_category": TAX_EXEMPT, "status": a.payment_status},
        ))

    # Lab (OPD only — IP lab is on the admission bill)
    lab_orders = db.query(PatientLabOrder).join(Patient).filter(
        Patient.hospital_id == hospital_id,
        sql_func.date(PatientLabOrder.created_at) >= d_from,
        sql_func.date(PatientLabOrder.created_at) <= d_to,
        PatientLabOrder.inpatient_bill_id.is_(None),
    ).all()
    grouped = {}
    ungrouped = []
    for lo in lab_orders:
        if (lo.payment_status or "") in SKIP_LAB_STATUS:
            continue
        gid = getattr(lo, "lab_bill_group_id", None)
        if gid:
            grouped.setdefault(gid, []).append(lo)
        else:
            ungrouped.append(lo)

    def _lab_row(orders, number, when):
        billed = _money(sum(float(o.amount or 0) for o in orders))
        status = orders[0].payment_status
        collected = billed if status == "paid" else 0.0
        p = orders[0].patient
        name = f"{p.first_name} {p.last_name}" if p else ""
        gstin = getattr(p, "gstin", None) if p else None
        rows.append(_invoice_row(
            "lab", _as_date(when), number, billed, 0, 0, collected,
            party=name, gstin=gstin or "", hsn=SAC_HEALTHCARE,
            extra={"tax_category": TAX_EXEMPT, "status": status},
        ))

    for gid, orders in grouped.items():
        _lab_row(orders, orders[0].lab_bill_number or gid, orders[0].created_at)
    for lo in ungrouped:
        _lab_row([lo], lo.order_number, lo.created_at)

    # Hospital bills (admission / day care / physio / catch-up / consultation ledger)
    bills = (
        db.query(Bill)
        .options(joinedload(Bill.items), joinedload(Bill.payments), joinedload(Bill.patient))
        .filter(
            Bill.hospital_id == hospital_id,
            sql_func.date(Bill.bill_date) >= d_from,
            sql_func.date(Bill.bill_date) <= d_to,
        )
        .all()
    )
    for b in bills:
        if (b.status or "") in SKIP_BILL_STATUS:
            continue
        if (b.bill_type or "") in SKIP_BILL_TYPES:
            continue
        if (b.bill_subtype or "final") in SKIP_BILL_SUBTYPES:
            continue
        module = module_for_bill_type(b.bill_type)
        billed = _money(b.total_amount)
        discount = _money(b.discount_amount)
        tax = _money(b.tax_amount)
        collected = _payments_total(b)
        if module == "inpatient":
            pharm = _money(sum(
                float(it.total_price or 0) for it in (b.items or [])
                if is_pharmacy_sourced_item(it)
            ))
            billed = _money(max(billed - pharm, 0))
            # collected stays on the admission bill as a whole; cap to billed
            collected = _money(min(collected, billed)) if billed else 0.0
        elif module == "pharmacy":
            # Catch-up / ledger pharmacy bills (not POS)
            pass
        p = b.patient
        name = f"{p.first_name} {p.last_name}" if p else ""
        gstin = (b.customer_gstin or getattr(p, "gstin", None) or "") if p or b.customer_gstin else ""
        cat = TAX_EXEMPT
        hsn = SAC_HEALTHCARE
        if module == "pharmacy":
            cat = TAX_TAXABLE
            hsn = ""
        taxable = _money(max((b.subtotal or 0) - (b.discount_amount or 0), 0))
        if taxable <= 0 and tax:
            taxable = _money(max(billed - tax, 0))
        by_rate = _bill_items_by_rate(b.items or [])
        # If lines had no amounts but header has tax, keep a single bucket.
        if not by_rate and (taxable or tax):
            _add_to_rate_map(by_rate, _effective_tax_pct(tax, taxable), taxable, tax)
        rows.append(_invoice_row(
            module, _as_date(b.bill_date), b.bill_number,
            billed, discount, tax, collected,
            party=name, gstin=gstin or "", hsn=hsn,
            taxable=taxable,
            tax_by_rate=by_rate,
            extra={"tax_category": cat, "status": b.status, "bill_id": b.id},
        ))

    # Pharmacy POS
    sales = db.query(PharmacySale).options(joinedload(PharmacySale.items)).filter(
        PharmacySale.hospital_id == hospital_id,
        PharmacySale.status == "completed",
        sql_func.date(PharmacySale.sale_date) >= d_from,
        sql_func.date(PharmacySale.sale_date) <= d_to,
    ).all()
    for s in sales:
        mode = s.billing_mode or "cash_at_pharmacy"
        module = "pharmacy_ip" if mode == "inpatient_bill" else "pharmacy"
        billed = _money(s.grand_total)
        collected = billed if module == "pharmacy" and (s.payment_type or "cash") != "credit" else 0.0
        if module == "pharmacy" and (s.payment_type or "cash") == "credit":
            collected = 0.0
        gstin = s.customer_gstin or ""
        tax = _money(s.tax_total or 0)
        taxable = _money(max(billed - tax, 0))
        by_rate = _sale_items_by_rate(s.items or [], tax_mode=getattr(s, "tax_mode", None) or "exclusive")
        if not by_rate and (taxable or tax):
            _add_to_rate_map(by_rate, _effective_tax_pct(tax, taxable), taxable, tax)
        rows.append(_invoice_row(
            module, _as_date(s.sale_date), s.sale_number,
            billed, s.discount_total or 0, tax, collected,
            party=s.patient_name or "", gstin=gstin, hsn="",
            taxable=taxable,
            tax_by_rate=by_rate,
            extra={"tax_category": TAX_TAXABLE, "status": s.status, "sale_id": s.id},
        ))

    # Canteen POS
    canteen = db.query(CanteenSale).filter(
        CanteenSale.hospital_id == hospital_id,
        CanteenSale.status == "completed",
        sql_func.date(CanteenSale.sale_date) >= d_from,
        sql_func.date(CanteenSale.sale_date) <= d_to,
    ).all()
    for s in canteen:
        billed = _money(s.grand_total)
        rows.append(_invoice_row(
            "canteen", _as_date(s.sale_date), s.sale_number,
            billed, s.discount_amount or 0, 0, billed,
            party=s.customer_name or "", hsn="",
            extra={"tax_category": TAX_EXEMPT, "status": s.status},
        ))

    return rows


def sales_summary(db: Session, hospital_id: int, d_from: date, d_to: date,
                  module: Optional[str] = None, group_by: str = "day") -> dict:
    invoices = collect_sales_invoices(db, hospital_id, d_from, d_to)
    if module and module != "all":
        invoices = [r for r in invoices if r["module"] == module]

    by_module = {m: _empty_totals() for m in ALL_MODULES}
    by_module_rates = {m: {} for m in ALL_MODULES}
    for r in invoices:
        t = by_module.setdefault(r["module"], _empty_totals())
        _add_totals(t, r["billed"], r["discount"], r["tax"], r["collected"])
        _merge_rate_maps(by_module_rates.setdefault(r["module"], {}), r.get("tax_by_rate") or {})

    module_rows = []
    for m in ALL_MODULES:
        t = _finalize_totals(by_module.get(m, _empty_totals()))
        if t["count"] == 0 and t["billed"] == 0:
            continue
        module_rows.append({
            "module": m,
            "module_label": MODULE_LABELS[m],
            "tax_by_rate": by_module_rates.get(m) or {},
            **t,
        })

    buckets = defaultdict(lambda: _empty_totals())
    bucket_rates = defaultdict(dict)
    for r in invoices:
        if group_by == "payment_method":
            key = r.get("status") or "—"
        elif group_by == "module":
            key = r["module_label"]
        else:
            key = r["date"] or "unknown"
        _add_totals(buckets[key], r["billed"], r["discount"], r["tax"], r["collected"])
        _merge_rate_maps(bucket_rates[key], r.get("tax_by_rate") or {})

    grouped = []
    for key in sorted(buckets.keys()):
        grouped.append({
            "bucket": key,
            "tax_by_rate": bucket_rates.get(key) or {},
            **_finalize_totals(buckets[key]),
        })

    totals = _empty_totals()
    totals_rates = {}
    for r in invoices:
        _add_totals(totals, r["billed"], r["discount"], r["tax"], r["collected"])
        _merge_rate_maps(totals_rates, r.get("tax_by_rate") or {})
    _finalize_totals(totals)
    totals["tax_by_rate"] = totals_rates

    rate_cols = _collect_rate_columns(invoices, module_rows, grouped)

    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "module": module or "all",
        "group_by": group_by,
        "tax_rate_columns": rate_cols,
        "by_module": module_rows,
        "rows": grouped,
        "invoices": invoices,
        "totals": totals,
    }


def outstanding_by_module(db: Session, hospital_id: int, d_from: date, d_to: date) -> dict:
    summary = sales_summary(db, hospital_id, d_from, d_to, module=None)
    rows = [
        {
            "module": m["module"],
            "module_label": m["module_label"],
            "billed": m["billed"],
            "collected": m["collected"],
            "outstanding": m["outstanding"],
            "count": m["count"],
        }
        for m in summary["by_module"]
        if m["outstanding"] > 0
    ]
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "rows": rows,
        "totals": {
            "billed": summary["totals"]["billed"],
            "collected": summary["totals"]["collected"],
            "outstanding": summary["totals"]["outstanding"],
        },
    }


def _purchase_taxable_and_gst(item) -> tuple:
    base = float(item.quantity or 0) * float(item.purchase_rate or 0)
    taxable = base * (1 - float(item.discount_pct or 0) / 100.0)
    sgst, cgst, igst = split_gst_amounts(
        taxable, item.sgst_pct, item.cgst_pct, item.igst_pct,
    )
    return taxable, sgst, cgst, igst


def purchase_summary(db: Session, hospital_id: int, d_from: date, d_to: date,
                     group_by: str = "day") -> dict:
    purchases = (
        db.query(PharmacyPurchase)
        .options(joinedload(PharmacyPurchase.items), joinedload(PharmacyPurchase.supplier))
        .filter(
            PharmacyPurchase.hospital_id == hospital_id,
            PharmacyPurchase.status == "confirmed",
            PharmacyPurchase.entry_date >= d_from,
            PharmacyPurchase.entry_date <= d_to,
        )
        .all()
    )
    returns = (
        db.query(PharmacyPurchaseReturn)
        .options(joinedload(PharmacyPurchaseReturn.items), joinedload(PharmacyPurchaseReturn.supplier))
        .filter(
            PharmacyPurchaseReturn.hospital_id == hospital_id,
            PharmacyPurchaseReturn.return_date >= d_from,
            PharmacyPurchaseReturn.return_date <= d_to,
            PharmacyPurchaseReturn.status.notin_(("draft", "cancelled")),
        )
        .all()
    )

    invoices = []
    for p in purchases:
        taxable = sgst = cgst = igst = 0.0
        for it in p.items or []:
            t, s, c, i = _purchase_taxable_and_gst(it)
            taxable += t; sgst += s; cgst += c; igst += i
        supplier = p.supplier
        gstin = ""
        name = ""
        if supplier:
            name = supplier.name or ""
            gstin = supplier.gstin_no or supplier.gstin or ""
        total_tax = sgst + cgst + igst
        by_rate = _purchase_items_by_rate(p.items or [])
        invoices.append({
            "kind": "purchase",
            "date": p.entry_date.isoformat() if p.entry_date else "",
            "number": p.purchase_number,
            "invoice_number": p.invoice_number or "",
            "supplier": name,
            "gstin": gstin,
            "taxable": _money(taxable),
            "sgst": _money(sgst),
            "cgst": _money(cgst),
            "igst": _money(igst),
            "total_tax": _money(total_tax),
            "tax_pct": _effective_tax_pct(total_tax, taxable),
            "tax_rates": _rate_label_from_pcts([float(k) for k in by_rate.keys()]),
            "tax_by_rate": by_rate,
            "grand_total": _money(p.grand_total),
            "status": p.status,
        })

    return_rows = []
    for r in returns:
        taxable = sgst = cgst = igst = 0.0
        by_rate = {}
        for it in r.items or []:
            base = float(it.quantity or 0) * float(it.purchase_rate or 0)
            t = base * (1 - float(it.discount_pct or 0) / 100.0)
            s, c, i = split_gst_amounts(t, it.sgst_pct, it.cgst_pct, it.igst_pct)
            taxable += t; sgst += s; cgst += c; igst += i
            _add_to_rate_map(by_rate, _line_gst_rate(it), t, s + c + i)
        # Negate amounts for returns
        by_rate_neg = {}
        for k, v in by_rate.items():
            by_rate_neg[k] = {
                "taxable": _money(-v["taxable"]),
                "tax": _money(-v["tax"]),
                "amount": _money(-v["amount"]),
            }
        supplier = getattr(r, "supplier", None)
        gstin = ""
        name = ""
        if supplier:
            name = supplier.name or ""
            gstin = supplier.gstin_no or supplier.gstin or ""
        total_tax = sgst + cgst + igst
        return_rows.append({
            "kind": "purchase_return",
            "date": r.return_date.isoformat() if r.return_date else "",
            "number": r.return_number,
            "invoice_number": "",
            "supplier": name,
            "gstin": gstin,
            "taxable": _money(-taxable),
            "sgst": _money(-sgst),
            "cgst": _money(-cgst),
            "igst": _money(-igst),
            "total_tax": _money(-total_tax),
            "tax_pct": _effective_tax_pct(total_tax, taxable),
            "tax_rates": _rate_label_from_pcts([float(k) for k in by_rate.keys()]),
            "tax_by_rate": by_rate_neg,
            "grand_total": _money(-(r.grand_total or 0)),
            "status": r.status,
        })

    buckets = defaultdict(lambda: {
        "count": 0, "taxable": 0.0, "sgst": 0.0, "cgst": 0.0, "igst": 0.0,
        "total_tax": 0.0, "grand_total": 0.0,
    })
    bucket_rates = defaultdict(dict)
    for row in invoices + return_rows:
        key = row["supplier"] if group_by == "supplier" else (row["date"] or "unknown")
        b = buckets[key]
        b["count"] += 1
        for k in ("taxable", "sgst", "cgst", "igst", "total_tax", "grand_total"):
            b[k] = _money(b[k] + row[k])
        _merge_rate_maps(bucket_rates[key], row.get("tax_by_rate") or {})

    grouped = []
    for k, v in sorted(buckets.items(), key=lambda kv: kv[0]):
        row = {"bucket": k, **{kk: _money(vv) if isinstance(vv, float) else vv for kk, vv in v.items()}}
        row["tax_pct"] = _effective_tax_pct(row["total_tax"], row["taxable"])
        row["tax_by_rate"] = bucket_rates.get(k) or {}
        grouped.append(row)
    totals_rates = {}
    for row in invoices + return_rows:
        _merge_rate_maps(totals_rates, row.get("tax_by_rate") or {})
    totals = {
        "count": len(invoices) + len(return_rows),
        "taxable": _money(sum(r["taxable"] for r in invoices + return_rows)),
        "sgst": _money(sum(r["sgst"] for r in invoices + return_rows)),
        "cgst": _money(sum(r["cgst"] for r in invoices + return_rows)),
        "igst": _money(sum(r["igst"] for r in invoices + return_rows)),
        "total_tax": _money(sum(r["total_tax"] for r in invoices + return_rows)),
        "grand_total": _money(sum(r["grand_total"] for r in invoices + return_rows)),
        "tax_by_rate": totals_rates,
    }
    totals["tax_pct"] = _effective_tax_pct(totals["total_tax"], totals["taxable"])
    rate_cols = _collect_rate_columns(invoices, return_rows, grouped)
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "group_by": group_by,
        "tax_rate_columns": rate_cols,
        "rows": grouped,
        "invoices": invoices,
        "returns": return_rows,
        "totals": totals,
    }


def _sale_line_tax(item, hsn) -> tuple:
    """taxable, sgst_pct, cgst_pct, igst_pct, sgst, cgst, igst, hsn_code"""
    snap_total = (item.sgst_pct or 0) + (item.cgst_pct or 0) + (item.igst_pct or 0)
    if snap_total > 0:
        sgst, cgst, igst = item.sgst_pct or 0, item.cgst_pct or 0, item.igst_pct or 0
    elif hsn is not None:
        sgst, cgst, igst = hsn.sgst_pct or 0, hsn.cgst_pct or 0, hsn.igst_pct or 0
    else:
        sgst = cgst = igst = 0
    code = hsn.code if hsn else "—"
    base = (item.quantity or 0) * (item.rate or 0)
    taxable = base * (1 - (item.discount_pct or 0) / 100.0)
    sa, ca, ia = split_gst_amounts(taxable, sgst, cgst, igst)
    return taxable, sgst, cgst, igst, sa, ca, ia, code


def _attach_supplier_gstin(payload: dict, db: Session, hospital_id: int,
                           module: Optional[str] = None) -> dict:
    from app.services.gst_return_forms import resolve_hospital, supplier_gstin_fields
    hospital = resolve_hospital(db, hospital_id)
    payload.update(supplier_gstin_fields(db, hospital, module))
    return payload


def _pharmacy_row_module(sale) -> str:
    mode = getattr(sale, "billing_mode", None) or "cash_at_pharmacy"
    return "pharmacy_ip" if mode == "inpatient_bill" else "pharmacy"


def _module_matches(selected: Optional[str], row_module: str) -> bool:
    from app.services.gst_classification import module_in_gst_scope, normalize_gst_scope
    return module_in_gst_scope(normalize_gst_scope(selected), row_module)


def gst_outward_hsn(db: Session, hospital_id: int, d_from: date, d_to: date,
                    module: Optional[str] = None) -> dict:
    q = db.query(PharmacySaleItem, PharmacySale, Medicine, PharmacyHSN).join(
        PharmacySale, PharmacySale.id == PharmacySaleItem.sale_id,
    ).join(
        Medicine, Medicine.id == PharmacySaleItem.medicine_id,
    ).outerjoin(
        PharmacyHSN, PharmacyHSN.id == Medicine.hsn_id,
    ).filter(
        PharmacySale.hospital_id == hospital_id,
        PharmacySale.status == "completed",
        sql_func.date(PharmacySale.sale_date) >= d_from,
        sql_func.date(PharmacySale.sale_date) <= d_to,
    )
    buckets = {}
    for it, sale, med, hsn in q.all():
        if not _module_matches(module, _pharmacy_row_module(sale)):
            continue
        taxable, sgst, cgst, igst, sa, ca, ia, code = _sale_line_tax(it, hsn)
        key = (code, sgst, cgst, igst)
        b = buckets.setdefault(key, {
            "hsn_code": code, "sgst_pct": sgst, "cgst_pct": cgst, "igst_pct": igst,
            "qty": 0.0, "taxable_value": 0.0, "sgst_amount": 0.0, "cgst_amount": 0.0,
            "igst_amount": 0.0, "total_tax": 0.0,
        })
        b["qty"] += float(it.quantity or 0)
        b["taxable_value"] += taxable
        b["sgst_amount"] += sa
        b["cgst_amount"] += ca
        b["igst_amount"] += ia

    # Sale returns as negatives
    rq = db.query(PharmacySaleReturnItem, PharmacySaleReturn, Medicine, PharmacyHSN).join(
        PharmacySaleReturn, PharmacySaleReturn.id == PharmacySaleReturnItem.sale_return_id,
    ).join(
        Medicine, Medicine.id == PharmacySaleReturnItem.medicine_id,
    ).outerjoin(
        PharmacyHSN, PharmacyHSN.id == Medicine.hsn_id,
    ).filter(
        PharmacySaleReturn.hospital_id == hospital_id,
        PharmacySaleReturn.status.notin_(("draft", "cancelled")),
        PharmacySaleReturn.return_date >= d_from,
        PharmacySaleReturn.return_date <= d_to,
    )
    for it, ret, med, hsn in rq.all():
        orig = getattr(ret, "sale", None)
        if orig and not _module_matches(module, _pharmacy_row_module(orig)):
            continue
        if not orig and module and module not in ("all", "pharmacy"):
            continue
        snap_total = (it.sgst_pct or 0) + (it.cgst_pct or 0) + (it.igst_pct or 0)
        if snap_total > 0:
            sgst, cgst, igst = it.sgst_pct or 0, it.cgst_pct or 0, it.igst_pct or 0
        elif hsn is not None:
            sgst, cgst, igst = hsn.sgst_pct or 0, hsn.cgst_pct or 0, hsn.igst_pct or 0
        else:
            sgst = cgst = igst = 0
        code = hsn.code if hsn else "—"
        base = (it.quantity or 0) * (it.rate or 0)
        taxable = base * (1 - (it.discount_pct or 0) / 100.0)
        sa, ca, ia = split_gst_amounts(taxable, sgst, cgst, igst)
        key = (code, sgst, cgst, igst)
        b = buckets.setdefault(key, {
            "hsn_code": code, "sgst_pct": sgst, "cgst_pct": cgst, "igst_pct": igst,
            "qty": 0.0, "taxable_value": 0.0, "sgst_amount": 0.0, "cgst_amount": 0.0,
            "igst_amount": 0.0, "total_tax": 0.0,
        })
        b["qty"] -= float(it.quantity or 0)
        b["taxable_value"] -= taxable
        b["sgst_amount"] -= sa
        b["cgst_amount"] -= ca
        b["igst_amount"] -= ia

    rows = []
    for v in buckets.values():
        v["taxable_value"] = _money(v["taxable_value"])
        v["sgst_amount"] = _money(v["sgst_amount"])
        v["cgst_amount"] = _money(v["cgst_amount"])
        v["igst_amount"] = _money(v["igst_amount"])
        v["qty"] = _money(v["qty"])
        v["total_tax"] = _money(v["sgst_amount"] + v["cgst_amount"] + v["igst_amount"])
        rows.append(v)
    rows.sort(key=lambda r: r["hsn_code"] or "")
    totals = {
        "taxable_value": _money(sum(r["taxable_value"] for r in rows)),
        "sgst_amount": _money(sum(r["sgst_amount"] for r in rows)),
        "cgst_amount": _money(sum(r["cgst_amount"] for r in rows)),
        "igst_amount": _money(sum(r["igst_amount"] for r in rows)),
        "total_tax": _money(sum(r["total_tax"] for r in rows)),
    }
    return _attach_supplier_gstin(
        {"date_from": d_from.isoformat(), "date_to": d_to.isoformat(), "rows": rows, "totals": totals},
        db, hospital_id, module,
    )


def gst_inward_hsn(db: Session, hospital_id: int, d_from: date, d_to: date,
                   module: Optional[str] = None) -> dict:
    empty = {
        "date_from": d_from.isoformat(), "date_to": d_to.isoformat(),
        "rows": [],
        "totals": {
            "taxable_value": 0.0, "sgst_amount": 0.0, "cgst_amount": 0.0,
            "igst_amount": 0.0, "total_tax": 0.0,
        },
    }
    if module and module not in ("all", "pharmacy"):
        from app.services.gst_classification import scope_has_inward_books, normalize_gst_scope
        if not scope_has_inward_books(normalize_gst_scope(module)):
            return _attach_supplier_gstin(empty, db, hospital_id, module)
    q = db.query(PharmacyPurchaseItem, PharmacyPurchase, Medicine, PharmacyHSN).join(
        PharmacyPurchase, PharmacyPurchase.id == PharmacyPurchaseItem.purchase_id,
    ).join(
        Medicine, Medicine.id == PharmacyPurchaseItem.medicine_id,
    ).outerjoin(
        PharmacyHSN, PharmacyHSN.id == Medicine.hsn_id,
    ).filter(
        PharmacyPurchase.hospital_id == hospital_id,
        PharmacyPurchase.status == "confirmed",
        PharmacyPurchase.entry_date >= d_from,
        PharmacyPurchase.entry_date <= d_to,
    )
    buckets = {}
    for it, purch, med, hsn in q.all():
        taxable, sgst_a, cgst_a, igst_a = _purchase_taxable_and_gst(it)
        code = hsn.code if hsn else "—"
        key = (code, it.sgst_pct or 0, it.cgst_pct or 0, it.igst_pct or 0)
        b = buckets.setdefault(key, {
            "hsn_code": code, "sgst_pct": it.sgst_pct or 0, "cgst_pct": it.cgst_pct or 0,
            "igst_pct": it.igst_pct or 0, "qty": 0.0, "taxable_value": 0.0,
            "sgst_amount": 0.0, "cgst_amount": 0.0, "igst_amount": 0.0, "total_tax": 0.0,
        })
        b["qty"] += float(it.quantity or 0)
        b["taxable_value"] += taxable
        b["sgst_amount"] += sgst_a
        b["cgst_amount"] += cgst_a
        b["igst_amount"] += igst_a

    rows = []
    for v in buckets.values():
        for k in ("taxable_value", "sgst_amount", "cgst_amount", "igst_amount", "qty"):
            v[k] = _money(v[k])
        v["total_tax"] = _money(v["sgst_amount"] + v["cgst_amount"] + v["igst_amount"])
        rows.append(v)
    rows.sort(key=lambda r: r["hsn_code"] or "")
    totals = {
        "taxable_value": _money(sum(r["taxable_value"] for r in rows)),
        "sgst_amount": _money(sum(r["sgst_amount"] for r in rows)),
        "cgst_amount": _money(sum(r["cgst_amount"] for r in rows)),
        "igst_amount": _money(sum(r["igst_amount"] for r in rows)),
        "total_tax": _money(sum(r["total_tax"] for r in rows)),
    }
    return _attach_supplier_gstin(
        {"date_from": d_from.isoformat(), "date_to": d_to.isoformat(), "rows": rows, "totals": totals},
        db, hospital_id, module,
    )


def gst_b2b_b2c(db: Session, hospital_id: int, d_from: date, d_to: date,
                module: Optional[str] = None) -> dict:
    """Pharmacy outward split: B2B when customer GSTIN is present, else B2C rate-wise."""
    q = db.query(PharmacySaleItem, PharmacySale, Medicine, PharmacyHSN).join(
        PharmacySale, PharmacySale.id == PharmacySaleItem.sale_id,
    ).join(
        Medicine, Medicine.id == PharmacySaleItem.medicine_id,
    ).outerjoin(
        PharmacyHSN, PharmacyHSN.id == Medicine.hsn_id,
    ).filter(
        PharmacySale.hospital_id == hospital_id,
        PharmacySale.status == "completed",
        sql_func.date(PharmacySale.sale_date) >= d_from,
        sql_func.date(PharmacySale.sale_date) <= d_to,
    )
    b2b = []
    b2c_buckets = {}
    for it, sale, med, hsn in q.all():
        if not _module_matches(module, _pharmacy_row_module(sale)):
            continue
        taxable, sgst, cgst, igst, sa, ca, ia, code = _sale_line_tax(it, hsn)
        gstin = (sale.customer_gstin or "").strip()
        rate = sgst + cgst if (sgst or cgst) else igst
        rec = {
            "date": _as_date(sale.sale_date).isoformat() if _as_date(sale.sale_date) else "",
            "number": sale.sale_number,
            "party": sale.patient_name or "",
            "gstin": gstin,
            "hsn_code": code,
            "taxable_value": _money(taxable),
            "sgst_pct": sgst, "cgst_pct": cgst, "igst_pct": igst,
            "sgst_amount": _money(sa), "cgst_amount": _money(ca), "igst_amount": _money(ia),
            "total_tax": _money(sa + ca + ia),
        }
        if gstin:
            b2b.append(rec)
        else:
            key = (rate, sgst, cgst, igst)
            b = b2c_buckets.setdefault(key, {
                "rate": rate, "sgst_pct": sgst, "cgst_pct": cgst, "igst_pct": igst,
                "invoice_count": 0, "taxable_value": 0.0,
                "sgst_amount": 0.0, "cgst_amount": 0.0, "igst_amount": 0.0,
                "_invoices": set(),
            })
            b["_invoices"].add(sale.id)
            b["taxable_value"] += taxable
            b["sgst_amount"] += sa
            b["cgst_amount"] += ca
            b["igst_amount"] += ia

    b2c = []
    for v in b2c_buckets.values():
        inv = v.pop("_invoices")
        b2c.append({
            **{k: _money(val) if isinstance(val, float) else val for k, val in v.items()},
            "invoice_count": len(inv),
            "total_tax": _money(v["sgst_amount"] + v["cgst_amount"] + v["igst_amount"]),
        })
    b2c.sort(key=lambda r: r["rate"])
    return _attach_supplier_gstin(
        {
            "date_from": d_from.isoformat(),
            "date_to": d_to.isoformat(),
            "b2b": b2b,
            "b2c": b2c,
            "totals": {
                "b2b_count": len(b2b),
                "b2b_taxable": _money(sum(r["taxable_value"] for r in b2b)),
                "b2b_tax": _money(sum(r["total_tax"] for r in b2b)),
                "b2c_taxable": _money(sum(r["taxable_value"] for r in b2c)),
                "b2c_tax": _money(sum(r["total_tax"] for r in b2c)),
            },
        },
        db, hospital_id, module,
    )


def gst_exempt_register(db: Session, hospital_id: int, d_from: date, d_to: date,
                        module: Optional[str] = None) -> dict:
    invoices = collect_sales_invoices(db, hospital_id, d_from, d_to)
    rows = [
        r for r in invoices
        if r.get("tax_category") == TAX_EXEMPT
        and r["module"] not in ("pharmacy", "pharmacy_ip")
    ]
    if module and module != "all":
        from app.services.gst_classification import gst_scope_modules, normalize_gst_scope
        mods = gst_scope_modules(normalize_gst_scope(module))
        if mods is not None:
            rows = [r for r in rows if r["module"] in mods]
        else:
            rows = [r for r in rows if r["module"] == module]
    by_module = defaultdict(lambda: {"count": 0, "taxable_value": 0.0})
    for r in rows:
        b = by_module[r["module"]]
        b["count"] += 1
        b["taxable_value"] += r["billed"]
    summary = [
        {"module": m, "module_label": MODULE_LABELS.get(m, m),
         "count": v["count"], "taxable_value": _money(v["taxable_value"])}
        for m, v in by_module.items()
    ]
    summary.sort(key=lambda r: r["module"])
    return _attach_supplier_gstin(
        {
            "date_from": d_from.isoformat(),
            "date_to": d_to.isoformat(),
            "module": module or "all",
            "sac": SAC_HEALTHCARE,
            "rows": [{**r, "sac": SAC_HEALTHCARE} for r in rows],
            "by_module": summary,
            "totals": {
                "count": len(rows),
                "taxable_value": _money(sum(r["billed"] for r in rows)),
            },
        },
        db, hospital_id, module,
    )


def gst_cdnr(db: Session, hospital_id: int, d_from: date, d_to: date) -> dict:
    """Sale returns + hospital credit notes."""
    returns = db.query(PharmacySaleReturn).filter(
        PharmacySaleReturn.hospital_id == hospital_id,
        PharmacySaleReturn.status.notin_(("draft", "cancelled")),
        PharmacySaleReturn.return_date >= d_from,
        PharmacySaleReturn.return_date <= d_to,
    ).all()
    rows = []
    for r in returns:
        rows.append({
            "kind": "sale_return",
            "date": r.return_date.isoformat() if r.return_date else "",
            "number": r.return_number,
            "party": "",
            "gstin": "",
            "taxable_value": _money(-(r.subtotal or 0)),
            "tax": _money(-(r.tax_total or 0)),
            "grand_total": _money(-(r.grand_total or 0)),
        })
    notes = db.query(Bill).filter(
        Bill.hospital_id == hospital_id,
        Bill.bill_type == "credit_note",
        Bill.status != "cancelled",
        sql_func.date(Bill.bill_date) >= d_from,
        sql_func.date(Bill.bill_date) <= d_to,
    ).all()
    for b in notes:
        p = b.patient
        name = f"{p.first_name} {p.last_name}" if p else ""
        rows.append({
            "kind": "credit_note",
            "date": _as_date(b.bill_date).isoformat() if _as_date(b.bill_date) else "",
            "number": b.bill_number,
            "party": name,
            "gstin": b.customer_gstin or (getattr(p, "gstin", None) or ""),
            "taxable_value": _money(b.total_amount),
            "tax": _money(b.tax_amount),
            "grand_total": _money(b.total_amount),
        })
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "rows": rows,
        "totals": {
            "count": len(rows),
            "taxable_value": _money(sum(r["taxable_value"] for r in rows)),
            "tax": _money(sum(r["tax"] for r in rows)),
        },
    }


def gst_legacy_tax(db: Session, hospital_id: int, d_from: date, d_to: date) -> dict:
    """Hospital bills with a flat tax_amount and no GST component stamp."""
    bills = db.query(Bill).options(joinedload(Bill.items)).filter(
        Bill.hospital_id == hospital_id,
        Bill.status != "cancelled",
        Bill.bill_type != "credit_note",
        sql_func.date(Bill.bill_date) >= d_from,
        sql_func.date(Bill.bill_date) <= d_to,
        Bill.tax_amount > 0,
    ).all()
    rows = []
    for b in bills:
        stamped = any(
            (it.sgst_amount or 0) or (it.cgst_amount or 0) or (it.igst_amount or 0)
            for it in (b.items or [])
        )
        if stamped:
            continue
        rows.append({
            "date": _as_date(b.bill_date).isoformat() if _as_date(b.bill_date) else "",
            "number": b.bill_number,
            "bill_type": b.bill_type,
            "taxable_value": _money(max((b.subtotal or 0) - (b.discount_amount or 0), 0)),
            "tax_amount": _money(b.tax_amount),
        })
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "rows": rows,
        "totals": {
            "count": len(rows),
            "taxable_value": _money(sum(r["taxable_value"] for r in rows)),
            "tax_amount": _money(sum(r["tax_amount"] for r in rows)),
        },
    }


def gstr3b_summary(db: Session, hospital_id: int, d_from: date, d_to: date,
                   module: Optional[str] = None) -> dict:
    """Form GSTR-3B working paper plus legacy flat keys for older UI."""
    from app.services.gst_return_forms import gstr3b_form, resolve_hospital
    hospital = resolve_hospital(db, hospital_id)
    return gstr3b_form(db, hospital, d_from, d_to, module=module)

# ---------------------------------------------------------------------------
# Sales / Purchase summary PDF & Excel helpers
# ---------------------------------------------------------------------------

def rate_column_label(rate) -> str:
    r = round(float(rate or 0), 2)
    if r == 0:
        return "Exempt"
    if r == int(r):
        return f"{int(r)}%"
    return f"{r:g}%"


def flatten_tax_rate_rows(rows: list, rate_columns: list, field: str = "amount") -> list:
    """Copy rows and add rate_<pct> keys with billed amounts at each GST rate."""
    out = []
    for r in rows or []:
        row = dict(r)
        by = r.get("tax_by_rate") or {}
        for rate in rate_columns or []:
            key = _rate_key(rate)
            bucket = by.get(key) or by.get(str(rate)) or {}
            val = bucket.get(field) if bucket else None
            row[f"rate_{key}"] = _money(val) if val is not None else None
        out.append(row)
    return out


def sales_summary_export_columns(rate_columns: list) -> list:
    cols = [
        {"key": "date", "label": "Date", "width": 1.2},
        {"key": "number", "label": "Number", "width": 1.6},
        {"key": "module_label", "label": "Module", "width": 1.3},
        {"key": "party", "label": "Party", "width": 2.2},
    ]
    for rate in rate_columns or []:
        key = _rate_key(rate)
        cols.append({
            "key": f"rate_{key}",
            "label": rate_column_label(rate),
            "align": "RIGHT",
            "width": 1.3,
        })
    cols.extend([
        {"key": "tax", "label": "Tax", "align": "RIGHT", "width": 1.2},
        {"key": "billed", "label": "Grand", "align": "RIGHT", "width": 1.3},
        {"key": "status", "label": "Status", "width": 1.0},
    ])
    return cols


def purchase_summary_export_columns(rate_columns: list) -> list:
    cols = [
        {"key": "date", "label": "Date", "width": 1.2},
        {"key": "number", "label": "GRN", "width": 1.4},
        {"key": "invoice_number", "label": "Supplier Inv", "width": 1.4},
        {"key": "supplier", "label": "Supplier", "width": 2.0},
        {"key": "gstin", "label": "GSTIN", "width": 1.5},
    ]
    for rate in rate_columns or []:
        key = _rate_key(rate)
        cols.append({
            "key": f"rate_{key}",
            "label": rate_column_label(rate),
            "align": "RIGHT",
            "width": 1.3,
        })
    cols.extend([
        {"key": "total_tax", "label": "Tax", "align": "RIGHT", "width": 1.2},
        {"key": "grand_total", "label": "Grand", "align": "RIGHT", "width": 1.3},
    ])
    return cols


def grouped_sales_export_columns(rate_columns: list, bucket_label: str = "Bucket") -> list:
    cols = [
        {"key": "bucket", "label": bucket_label, "width": 2.0},
        {"key": "count", "label": "Bills", "align": "RIGHT", "width": 0.9},
    ]
    for rate in rate_columns or []:
        key = _rate_key(rate)
        cols.append({
            "key": f"rate_{key}",
            "label": rate_column_label(rate),
            "align": "RIGHT",
            "width": 1.3,
        })
    cols.extend([
        {"key": "tax", "label": "Tax", "align": "RIGHT", "width": 1.2},
        {"key": "billed", "label": "Grand", "align": "RIGHT", "width": 1.3},
        {"key": "collected", "label": "Collected", "align": "RIGHT", "width": 1.3},
    ])
    return cols


def grouped_purchase_export_columns(rate_columns: list, bucket_label: str = "Bucket") -> list:
    cols = [
        {"key": "bucket", "label": bucket_label, "width": 2.0},
        {"key": "count", "label": "Docs", "align": "RIGHT", "width": 0.9},
    ]
    for rate in rate_columns or []:
        key = _rate_key(rate)
        cols.append({
            "key": f"rate_{key}",
            "label": rate_column_label(rate),
            "align": "RIGHT",
            "width": 1.3,
        })
    cols.extend([
        {"key": "sgst", "label": "SGST", "align": "RIGHT", "width": 1.1},
        {"key": "cgst", "label": "CGST", "align": "RIGHT", "width": 1.1},
        {"key": "igst", "label": "IGST", "align": "RIGHT", "width": 1.1},
        {"key": "total_tax", "label": "Tax", "align": "RIGHT", "width": 1.2},
        {"key": "grand_total", "label": "Grand", "align": "RIGHT", "width": 1.3},
    ])
    return cols


# ---------------------------------------------------------------------------
# GST Reports page — Excel / PDF working papers
# ---------------------------------------------------------------------------

HSN_EXPORT_COLUMNS = [
    {"key": "hsn_code", "label": "HSN", "width": 1.4},
    {"key": "qty", "label": "Qty", "align": "RIGHT", "width": 1.0},
    {"key": "sgst_pct", "label": "SGST %", "align": "RIGHT", "width": 1.0},
    {"key": "cgst_pct", "label": "CGST %", "align": "RIGHT", "width": 1.0},
    {"key": "igst_pct", "label": "IGST %", "align": "RIGHT", "width": 1.0},
    {"key": "taxable_value", "label": "Taxable", "align": "RIGHT", "width": 1.3},
    {"key": "sgst_amount", "label": "SGST", "align": "RIGHT", "width": 1.2},
    {"key": "cgst_amount", "label": "CGST", "align": "RIGHT", "width": 1.2},
    {"key": "igst_amount", "label": "IGST", "align": "RIGHT", "width": 1.2},
    {"key": "total_tax", "label": "Total tax", "align": "RIGHT", "width": 1.3},
]

B2B_EXPORT_COLUMNS = [
    {"key": "date", "label": "Date", "width": 1.2},
    {"key": "number", "label": "Invoice", "width": 1.5},
    {"key": "party", "label": "Customer", "width": 2.0},
    {"key": "gstin", "label": "GSTIN", "width": 1.6},
    {"key": "hsn_code", "label": "HSN", "width": 1.2},
    {"key": "taxable_value", "label": "Taxable", "align": "RIGHT", "width": 1.3},
    {"key": "sgst_amount", "label": "SGST", "align": "RIGHT", "width": 1.1},
    {"key": "cgst_amount", "label": "CGST", "align": "RIGHT", "width": 1.1},
    {"key": "igst_amount", "label": "IGST", "align": "RIGHT", "width": 1.1},
    {"key": "total_tax", "label": "Tax", "align": "RIGHT", "width": 1.2},
]

B2C_EXPORT_COLUMNS = [
    {"key": "rate", "label": "Rate %", "align": "RIGHT", "width": 1.0},
    {"key": "invoice_count", "label": "Invoices", "align": "RIGHT", "width": 1.0},
    {"key": "taxable_value", "label": "Taxable", "align": "RIGHT", "width": 1.3},
    {"key": "sgst_amount", "label": "SGST", "align": "RIGHT", "width": 1.2},
    {"key": "cgst_amount", "label": "CGST", "align": "RIGHT", "width": 1.2},
    {"key": "igst_amount", "label": "IGST", "align": "RIGHT", "width": 1.2},
]

EXEMPT_MODULE_COLUMNS = [
    {"key": "module_label", "label": "Module", "width": 2.0},
    {"key": "count", "label": "Bills", "align": "RIGHT", "width": 1.0},
    {"key": "taxable_value", "label": "Exempt value", "align": "RIGHT", "width": 1.5},
]

EXEMPT_INVOICE_COLUMNS = [
    {"key": "date", "label": "Date", "width": 1.2},
    {"key": "number", "label": "Invoice / ref", "width": 1.6},
    {"key": "module_label", "label": "Module", "width": 1.4},
    {"key": "party", "label": "Patient", "width": 2.0},
    {"key": "gstin", "label": "GSTIN", "width": 1.5},
    {"key": "hsn_sac", "label": "SAC", "width": 1.1},
    {"key": "billed", "label": "Exempt value", "align": "RIGHT", "width": 1.4},
]


def _with_total_row(rows: list, totals: dict, first_key: str, first_label: str = "Total") -> list:
    out = list(rows or [])
    if totals:
        out.append({first_key: first_label, **totals})
    return out


def gst_working_paper_export(kind: str, data: dict) -> dict:
    """Columns + rows for GST Reports page Excel/PDF (not GSTR-3B form)."""
    data = data or {}
    if kind == "outward":
        return {
            "title": "OUTWARD HSN",
            "filename_slug": "gst_outward_hsn",
            "sheets": [{
                "title": "Outward HSN",
                "columns": HSN_EXPORT_COLUMNS,
                "rows": _with_total_row(data.get("rows") or [], data.get("totals") or {}, "hsn_code"),
            }],
        }
    if kind == "inward":
        return {
            "title": "INWARD HSN",
            "filename_slug": "gst_inward_hsn",
            "sheets": [{
                "title": "Inward HSN",
                "columns": HSN_EXPORT_COLUMNS,
                "rows": _with_total_row(data.get("rows") or [], data.get("totals") or {}, "hsn_code"),
            }],
        }
    if kind == "b2b":
        return {
            "title": "B2B / B2C",
            "filename_slug": "gst_b2b_b2c",
            "sheets": [
                {
                    "title": "B2B invoices",
                    "columns": B2B_EXPORT_COLUMNS,
                    "rows": data.get("b2b") or [],
                },
                {
                    "title": "B2C rate-wise",
                    "columns": B2C_EXPORT_COLUMNS,
                    "rows": data.get("b2c") or [],
                },
            ],
        }
    if kind == "exempt":
        sac = data.get("sac") or SAC_HEALTHCARE
        return {
            "title": f"EXEMPT (SAC {sac})",
            "filename_slug": "gst_exempt",
            "sheets": [
                {
                    "title": f"Exempt by module (SAC {sac})",
                    "columns": EXEMPT_MODULE_COLUMNS,
                    "rows": _with_total_row(
                        data.get("by_module") or [], data.get("totals") or {}, "module_label",
                    ),
                },
                {
                    "title": "Exempt invoices",
                    "columns": EXEMPT_INVOICE_COLUMNS,
                    "rows": data.get("rows") or [],
                },
            ],
        }
    raise ValueError(f"Unknown GST working paper kind: {kind}")
