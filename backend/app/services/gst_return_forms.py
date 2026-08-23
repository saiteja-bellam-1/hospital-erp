"""Official GSTR-1 / GSTR-2 books / GSTR-3B / GSTR-9 working papers.

Tax math is reused from gst_report_service. These builders only reshape
books of account into GSTN / Form GSTR-3B tables. They are not GSTN uploads.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sql_func

from app.models.billing import Bill
from app.models.hospital import Hospital
from app.models.pharmacy import (
    PharmacySale, PharmacySaleItem, PharmacyHSN, Medicine,
    PharmacySaleReturn, PharmacySaleReturnItem,
    PharmacyPurchase,
    PharmacySupplierCreditNote,
)
from app.services.gst_classification import (
    SAC_HEALTHCARE, split_gst_amounts,
    module_for_bill_type, is_pharmacy_sourced_item,
    effective_tax_category, effective_hsn_sac,
    normalize_gst_scope, gst_scope_label,
    module_in_gst_scope, config_bucket_for_scope, scope_has_inward_books,
    scope_includes_pharmacy_docs, scope_includes_hospital_credit_notes,
)
from app.services import gst_report_service as reports


DISCLAIMER = (
    "Working paper from KT HEALTH ERP books of account. "
    "This is not a GSTN JSON or offline-utility upload. "
    "Copy figures into the GST portal."
)

B2CL_INVOICE_THRESHOLD = 100000.0
DEFAULT_UQC = "OTH-OTHERS"

GST_STATE_NAMES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana", "07": "Delhi",
    "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar",
    "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland",
    "14": "Manipur", "15": "Mizoram", "16": "Tripura", "17": "Meghalaya",
    "18": "Assam", "19": "West Bengal", "20": "Jharkhand",
    "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "Andaman and Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
    "97": "Other Territory",
}

MONTH_NAMES = (
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = calendar.monthrange(int(year), int(month))[1]
    return date(int(year), int(month), 1), date(int(year), int(month), last)


def fy_bounds(fy_start: int) -> tuple[date, date]:
    y = int(fy_start)
    return date(y, 4, 1), date(y + 1, 3, 31)


def parse_return_period(
    year: Optional[int] = None,
    month: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> tuple[date, date]:
    if year and month:
        return month_bounds(year, month)
    return reports.parse_date_range(date_from, date_to)


def period_label(d_from: date, d_to: date) -> str:
    if d_from.year == d_to.year and d_from.month == d_to.month and d_from.day == 1:
        last = calendar.monthrange(d_from.year, d_from.month)[1]
        if d_to.day == last:
            return f"{MONTH_NAMES[d_from.month]} {d_from.year}"
    return f"{d_from.isoformat()} to {d_to.isoformat()}"


def fy_label(fy_start: int) -> str:
    y = int(fy_start)
    return f"FY {y}-{str(y + 1)[-2:]} (Apr {y} – Mar {y + 1})"


def hospital_state_code(hospital: Optional[Hospital]) -> str:
    if hospital is None:
        return ""
    code = (getattr(hospital, "gst_state_code", None) or "").strip()
    if len(code) >= 2:
        return code[:2]
    gstin = (getattr(hospital, "gstin", None) or getattr(hospital, "tax_id", None) or "").strip()
    if len(gstin) >= 2 and gstin[:2].isdigit():
        return gstin[:2]
    return ""


def hospital_gstin(hospital: Optional[Hospital]) -> str:
    if hospital is None:
        return ""
    return (getattr(hospital, "gstin", None) or getattr(hospital, "tax_id", None) or "").strip()


def _module_config_map(db: Session, config_module: str) -> dict:
    from app.models.permissions import HospitalSettings
    rows = db.query(HospitalSettings).filter(
        HospitalSettings.setting_category == f"{config_module}_config"
    ).all()
    return {s.setting_key: (s.setting_value or "") for s in rows}


def _config_gstin(db: Session, config_module: str) -> str:
    """GSTIN stored on the module itself (not the hospital fallback)."""
    return (_module_config_map(db, config_module).get("gst_number") or "").strip()


def _setting_on(val) -> bool:
    return str(val or "").strip().lower() in ("1", "true", "yes", "on")


def resolve_config_gstin(
    cfg: dict,
    hospital_val: str,
    *,
    config_module: Optional[str] = None,
) -> tuple[str, str]:
    """GSTIN to print for a lab/pharmacy filing.

    Own ``gst_number`` wins. If it is blank, use the hospital GSTIN only when
    ``use_hospital_gstin`` is on. A missing flag means in-house (no provider
    name) uses the hospital GSTIN; a third party stays blank.
    """
    own = (cfg.get("gst_number") or "").strip()
    if own:
        source = f"{config_module}_config" if config_module else "config"
        return own, source
    flag = cfg.get("use_hospital_gstin")
    if flag is not None and str(flag).strip() != "":
        use_hospital = _setting_on(flag)
    else:
        use_hospital = not (cfg.get("provider_name") or "").strip()
    if use_hospital and (hospital_val or "").strip():
        return hospital_val.strip(), "hospital"
    return "", "none"


def config_module_for(module: Optional[str]) -> Optional[str]:
    """Lab / pharmacy module-config bucket that stores a GSTIN, if any."""
    return config_bucket_for_scope(normalize_gst_scope(module))


def supplier_gstin_fields(
    db: Session,
    hospital: Optional[Hospital],
    module: Optional[str] = None,
) -> dict:
    """GSTIN for the selected GST filing group.

    Lab and pharmacy store their own GST number on the module config page
    (third-party / separate registration). If that number is blank, GSTIN is
    the hospital's only when the module opted in; otherwise it stays empty.
    Hospital GST covers every other module. ``gstins`` lists every distinct
    registration on file (own numbers only).
    """
    selected = normalize_gst_scope(module)
    hospital_val = hospital_gstin(hospital)
    cfg_name = config_bucket_for_scope(selected)
    gstin = hospital_val
    source = "hospital"
    label = "Hospital"
    if cfg_name:
        resolved, res_source = resolve_config_gstin(
            _module_config_map(db, cfg_name), hospital_val, config_module=cfg_name,
        )
        gstin = resolved
        source = res_source
        label = gst_scope_label(selected)
    elif selected == "hospital":
        label = "Hospital"

    gstins = []
    if hospital_val:
        gstins.append({
            "module": "hospital",
            "label": "Hospital",
            "gstin": hospital_val,
            "source": "hospital",
        })
    for key, disp in (("pharmacy", "Pharmacy"), ("lab", "Laboratory")):
        val = _config_gstin(db, key)
        if val and val != hospital_val:
            gstins.append({
                "module": key,
                "label": disp,
                "gstin": val,
                "source": f"{key}_config",
            })

    return {
        "gstin": gstin,
        "gstin_source": source,
        "gstin_label": label,
        "module": selected or "all",
        "module_label": gst_scope_label(selected),
        "gstins": gstins,
    }


def place_of_supply_label(code: str) -> str:
    code = (code or "").strip()[:2]
    if not code:
        return ""
    name = GST_STATE_NAMES.get(code, "")
    return f"{code}-{name}" if name else code


def hospital_meta(hospital: Optional[Hospital], d_from: date, d_to: date,
                  module: Optional[str] = None, db: Optional[Session] = None) -> dict:
    selected = normalize_gst_scope(module)
    gstin = hospital_gstin(hospital)
    extra = {}
    if db is not None:
        extra = supplier_gstin_fields(db, hospital, selected)
        if "gstin" in extra:
            gstin = extra.get("gstin") or ""
    code = hospital_state_code(hospital)
    if gstin and len(gstin) >= 2 and gstin[:2].isdigit():
        code = gstin[:2]
    meta = {
        "name": getattr(hospital, "name", None) or "",
        "gstin": gstin,
        "state_code": code,
        "place_of_supply": place_of_supply_label(code),
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "period_label": period_label(d_from, d_to),
        "module": selected or "all",
        "module_label": gst_scope_label(selected),
    }
    for key in ("gstin_source", "gstin_label", "gstins"):
        if key in extra:
            meta[key] = extra[key]
    return meta


def normalize_module(module: Optional[str]) -> Optional[str]:
    """GST filter: all / hospital / lab / pharmacy, or a single billing module."""
    return normalize_gst_scope(module)


def module_included(selected: Optional[str], row_module: str) -> bool:
    return module_in_gst_scope(selected, row_module)


def pharmacy_sale_module(sale) -> str:
    mode = getattr(sale, "billing_mode", None) or "cash_at_pharmacy"
    return "pharmacy_ip" if mode == "inpatient_bill" else "pharmacy"


def has_inward_books(selected: Optional[str]) -> bool:
    """Pharmacy GRN is the only inward GST register; it files on Pharmacy GST."""
    return scope_has_inward_books(selected)


def _gstin_state(gstin: str) -> str:
    g = (gstin or "").strip()
    if len(g) >= 2 and g[:2].isdigit():
        return g[:2]
    return ""


def _combined_rate(sgst: float, cgst: float, igst: float) -> float:
    if sgst or cgst:
        return reports._money(float(sgst or 0) + float(cgst or 0))
    return reports._money(igst or 0)


def _empty_tax() -> dict:
    return {
        "taxable": 0.0, "igst": 0.0, "cgst": 0.0, "sgst": 0.0, "cess": 0.0,
        "invoice_value": 0.0,
    }


def _add_tax(dest: dict, taxable=0, igst=0, cgst=0, sgst=0, cess=0, invoice_value=0):
    dest["taxable"] = reports._money(dest.get("taxable", 0) + taxable)
    dest["igst"] = reports._money(dest.get("igst", 0) + igst)
    dest["cgst"] = reports._money(dest.get("cgst", 0) + cgst)
    dest["sgst"] = reports._money(dest.get("sgst", 0) + sgst)
    dest["cess"] = reports._money(dest.get("cess", 0) + cess)
    dest["invoice_value"] = reports._money(dest.get("invoice_value", 0) + invoice_value)


def _money_tax(t: dict) -> dict:
    return {k: reports._money(v) for k, v in t.items()}


# ---------------------------------------------------------------------------
# Pharmacy outward lines
# ---------------------------------------------------------------------------

def _iter_sale_lines(db: Session, hospital_id: int, d_from: date, d_to: date):
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
    for it, sale, med, hsn in q.all():
        taxable, sgst, cgst, igst, sa, ca, ia, code = reports._sale_line_tax(it, hsn)
        yield {
            "sale": sale,
            "item": it,
            "hsn_code": code if code != "—" else (getattr(hsn, "code", None) or ""),
            "hsn_desc": (getattr(hsn, "description", None) or "") or (code if code != "—" else ""),
            "qty": float(it.quantity or 0),
            "taxable": taxable,
            "sgst_pct": sgst, "cgst_pct": cgst, "igst_pct": igst,
            "sgst": sa, "cgst": ca, "igst": ia,
            "rate": _combined_rate(sgst, cgst, igst),
            "line_value": reports._money(taxable + sa + ca + ia),
        }


def _iter_return_lines(db: Session, hospital_id: int, d_from: date, d_to: date):
    q = db.query(PharmacySaleReturnItem, PharmacySaleReturn, Medicine, PharmacyHSN).join(
        PharmacySaleReturn, PharmacySaleReturn.id == PharmacySaleReturnItem.sale_return_id,
    ).join(
        Medicine, Medicine.id == PharmacySaleReturnItem.medicine_id,
    ).outerjoin(
        PharmacyHSN, PharmacyHSN.id == Medicine.hsn_id,
    ).options(joinedload(PharmacySaleReturn.sale)).filter(
        PharmacySaleReturn.hospital_id == hospital_id,
        PharmacySaleReturn.status.notin_(("draft", "cancelled")),
        PharmacySaleReturn.return_date >= d_from,
        PharmacySaleReturn.return_date <= d_to,
    )
    for it, ret, med, hsn in q.all():
        snap = (it.sgst_pct or 0) + (it.cgst_pct or 0) + (it.igst_pct or 0)
        if snap > 0:
            sgst, cgst, igst = it.sgst_pct or 0, it.cgst_pct or 0, it.igst_pct or 0
        elif hsn is not None:
            sgst, cgst, igst = hsn.sgst_pct or 0, hsn.cgst_pct or 0, hsn.igst_pct or 0
        else:
            sgst = cgst = igst = 0
        code = hsn.code if hsn else ""
        base = (it.quantity or 0) * (it.rate or 0)
        taxable = base * (1 - (it.discount_pct or 0) / 100.0)
        sa, ca, ia = split_gst_amounts(taxable, sgst, cgst, igst)
        orig = ret.sale
        gstin = (getattr(orig, "customer_gstin", None) or "").strip() if orig else ""
        yield {
            "ret": ret,
            "item": it,
            "gstin": gstin,
            "party": ret.patient_name or (getattr(orig, "patient_name", None) or ""),
            "hsn_code": code,
            "hsn_desc": (getattr(hsn, "description", None) or "") or code,
            "qty": float(it.quantity or 0),
            "taxable": taxable,
            "sgst_pct": sgst, "cgst_pct": cgst, "igst_pct": igst,
            "sgst": sa, "cgst": ca, "igst": ia,
            "rate": _combined_rate(sgst, cgst, igst),
            "line_value": reports._money(taxable + sa + ca + ia),
        }


def classify_supply(gstin: str, invoice_value: float, hospital: Optional[Hospital]) -> tuple[str, str]:
    """Return (bucket, place_of_supply_code). bucket: b2b | b2cl | b2cs."""
    gstin = (gstin or "").strip()
    home = hospital_state_code(hospital)
    if gstin:
        return "b2b", _gstin_state(gstin) or home
    pos = home
    inv = float(invoice_value or 0)
    if pos and home and pos != home and inv > B2CL_INVOICE_THRESHOLD:
        return "b2cl", pos
    return "b2cs", pos


def _classify_outward(sale: PharmacySale, hospital: Optional[Hospital]) -> tuple[str, str]:
    return classify_supply(sale.customer_gstin or "", sale.grand_total, hospital)


def _fmt_inv_date(value) -> str:
    d = reports._as_date(value)
    return d.isoformat() if d else ""


def _iter_bill_lines(db: Session, hospital_id: int, d_from: date, d_to: date, selected: Optional[str]):
    """Hospital bill lines (lab / OPD / IP / canteen / …) with GST stamps.

    Pharmacy-sourced lines on admission bills are skipped — those supplies
    already sit on pharmacy POS (pharmacy_ip).
    """
    bills = (
        db.query(Bill)
        .options(joinedload(Bill.items), joinedload(Bill.patient))
        .filter(
            Bill.hospital_id == hospital_id,
            sql_func.date(Bill.bill_date) >= d_from,
            sql_func.date(Bill.bill_date) <= d_to,
        )
        .all()
    )
    for bill in bills:
        if (bill.status or "") in reports.SKIP_BILL_STATUS:
            continue
        if (bill.bill_type or "") in reports.SKIP_BILL_TYPES:
            continue
        if (bill.bill_subtype or "final") in reports.SKIP_BILL_SUBTYPES:
            continue
        mod = module_for_bill_type(bill.bill_type)
        if not module_included(selected, mod):
            continue
        p = bill.patient
        gstin = (bill.customer_gstin or (getattr(p, "gstin", None) or "") or "").strip()
        party = f"{p.first_name} {p.last_name}" if p else ""
        any_line_tax = False
        for it in bill.items or []:
            if is_pharmacy_sourced_item(it):
                continue
            sgst = float(it.sgst_pct or 0)
            cgst = float(it.cgst_pct or 0)
            igst = float(it.igst_pct or 0)
            sa = float(it.sgst_amount or 0)
            ca = float(it.cgst_amount or 0)
            ia = float(it.igst_amount or 0)
            qty = float(it.quantity or 1)
            unit = float(it.unit_price or 0)
            disc = float(it.discount_percentage or 0)
            gross = qty * unit * (1 - disc / 100.0)
            line_tax = sa + ca + ia
            total = float(it.total_price or 0)
            rate = reports._line_gst_rate(it)
            if rate > 0 and (sgst + cgst + igst) <= 0:
                # tax_percentage stamped without CGST/SGST split — intra-state default.
                sgst = reports._money(rate / 2.0)
                cgst = reports._money(rate - sgst)
                igst = 0.0
            if total > 0 and line_tax > 0 and abs(total - (gross + line_tax)) < 0.05:
                taxable = reports._money(total - line_tax)
            elif line_tax > 0:
                taxable = reports._money(max(gross, total - line_tax) if total else gross)
            elif rate > 0 and total > 0 and gross > 0 and total > gross + 0.04:
                taxable = reports._money(gross)
            else:
                taxable = reports._money(total or gross)
            if rate <= 0 and line_tax > 0 and taxable:
                rate = reports._money(line_tax / taxable * 100.0)
            if line_tax <= 0 and rate > 0 and taxable:
                sa, ca, ia = split_gst_amounts(taxable, sgst, cgst, igst)
                line_tax = sa + ca + ia
            if rate > 0 or line_tax > 0:
                any_line_tax = True
            cat = effective_tax_category(it)
            code = effective_hsn_sac(it) or SAC_HEALTHCARE
            yield {
                "bill": bill,
                "module": mod,
                "gstin": gstin,
                "party": party,
                "hsn_code": code,
                "hsn_desc": code,
                "qty": qty,
                "taxable": taxable,
                "sgst_pct": sgst, "cgst_pct": cgst, "igst_pct": igst,
                "sgst": sa, "cgst": ca, "igst": ia,
                "rate": rate,
                "line_value": reports._money(taxable + sa + ca + ia),
                "tax_category": cat,
                "invoice_value": reports._money(bill.total_amount),
            }
        header_tax = float(bill.tax_amount or 0)
        if not any_line_tax and header_tax > 0:
            billed = float(bill.total_amount or 0)
            taxable = reports._money(max((bill.subtotal or 0) - (bill.discount_amount or 0), billed - header_tax))
            rate = reports._effective_tax_pct(header_tax, taxable)
            sgst = reports._money(rate / 2.0) if rate else 0.0
            cgst = reports._money(rate - sgst) if rate else 0.0
            sa, ca, ia = split_gst_amounts(taxable, sgst, cgst, 0.0)
            yield {
                "bill": bill,
                "module": mod,
                "gstin": gstin,
                "party": party,
                "hsn_code": SAC_HEALTHCARE,
                "hsn_desc": SAC_HEALTHCARE,
                "qty": 1.0,
                "taxable": taxable,
                "sgst_pct": sgst, "cgst_pct": cgst, "igst_pct": 0.0,
                "sgst": sa, "cgst": ca, "igst": ia,
                "rate": rate,
                "line_value": reports._money(taxable + sa + ca + ia),
                "tax_category": "taxable",
                "invoice_value": reports._money(billed),
            }


def _hsn_key(code, desc, rate, uqc=DEFAULT_UQC):
    return (code or "", desc or code or "", uqc, reports._money(rate or 0))


def _hsn_bucket():
    return {
        "qty": 0.0, "total_value": 0.0, "taxable_value": 0.0,
        "igst": 0.0, "cgst": 0.0, "sgst": 0.0, "cess": 0.0,
    }


def _add_hsn(dest, key, qty, total_value, taxable, igst, cgst, sgst, sign=1.0):
    b = dest.setdefault(key, _hsn_bucket())
    b["qty"] += sign * qty
    b["total_value"] += sign * total_value
    b["taxable_value"] += sign * taxable
    b["igst"] += sign * igst
    b["cgst"] += sign * cgst
    b["sgst"] += sign * sgst


def _hsn_rows(buckets: dict) -> list:
    rows = []
    for (code, desc, uqc, rate), b in buckets.items():
        rows.append({
            "hsn": code,
            "description": desc or code,
            "uqc": uqc,
            "qty": reports._money(b["qty"]),
            "total_value": reports._money(b["total_value"]),
            "rate": rate,
            "taxable_value": reports._money(b["taxable_value"]),
            "igst": reports._money(b["igst"]),
            "cgst": reports._money(b["cgst"]),
            "sgst": reports._money(b["sgst"]),
            "cess": 0.0,
        })
    rows.sort(key=lambda r: (r["hsn"] or "", r["rate"]))
    return rows


def _hsn_summary(rows: list) -> dict:
    return {
        "hsn_count": len({r["hsn"] for r in rows if r["hsn"]}),
        "total_value": reports._money(sum(r["total_value"] for r in rows)),
        "taxable_value": reports._money(sum(r["taxable_value"] for r in rows)),
        "igst": reports._money(sum(r["igst"] for r in rows)),
        "cgst": reports._money(sum(r["cgst"] for r in rows)),
        "sgst": reports._money(sum(r["sgst"] for r in rows)),
        "cess": 0.0,
    }


def _docs_series(numbers: list[str], cancelled: int = 0) -> dict:
    nums = [n for n in numbers if n]
    if not nums:
        return {"from": "", "to": "", "total": 0, "cancelled": cancelled}
    ordered = sorted(nums)
    return {
        "from": ordered[0],
        "to": ordered[-1],
        "total": len(nums),
        "cancelled": cancelled,
    }


# ---------------------------------------------------------------------------
# GSTR-1
# ---------------------------------------------------------------------------

def gstr1_return(db: Session, hospital: Optional[Hospital], d_from: date, d_to: date,
                 module: Optional[str] = None) -> dict:
    hid = hospital.id if hospital else 0
    home = hospital_state_code(hospital)
    selected = normalize_module(module)

    b2b_rate_rows = []  # invoice × rate
    b2cl_rate_rows = []
    b2cs_buckets = {}
    hsn_b2b = {}
    hsn_b2c = {}
    nil_exempt = {
        "inter_reg": _empty_tax(),
        "intra_reg": _empty_tax(),
        "inter_unreg": _empty_tax(),
        "intra_unreg": _empty_tax(),
    }
    taxable_bill_ids = set()

    def _add_nil(gstin, pos, taxable, invoice_value):
        if gstin:
            key = "intra_reg" if (not pos or pos == home) else "inter_reg"
        else:
            key = "intra_unreg" if (not pos or pos == home) else "inter_unreg"
        _add_tax(nil_exempt[key], taxable=taxable, invoice_value=invoice_value)

    def _push_taxable(bucket, pos, rec, line):
        hkey = _hsn_key(line["hsn_code"], line["hsn_desc"], line["rate"])
        if bucket == "b2b":
            b2b_rate_rows.append(rec)
            _add_hsn(hsn_b2b, hkey, line["qty"], line["line_value"], line["taxable"],
                     line["igst"], line["cgst"], line["sgst"])
        elif bucket == "b2cl":
            b2cl_rate_rows.append({
                "invoice_number": rec["invoice_number"],
                "invoice_date": rec["invoice_date"],
                "invoice_value": rec["invoice_value"],
                "place_of_supply": rec["place_of_supply"],
                "applicable_pct": "",
                "rate": rec["rate"],
                "taxable_value": rec["taxable_value"],
                "cess": 0.0,
                "ecommerce_gstin": "",
                "igst": rec["igst"],
            })
            _add_hsn(hsn_b2c, hkey, line["qty"], line["line_value"], line["taxable"],
                     line["igst"], line["cgst"], line["sgst"])
        else:
            pos_label = place_of_supply_label(pos) or place_of_supply_label(home)
            key = (pos_label, rec["rate"])
            b = b2cs_buckets.setdefault(key, {
                "type": "OE",
                "place_of_supply": pos_label,
                "applicable_pct": "",
                "rate": rec["rate"],
                "taxable_value": 0.0,
                "cess": 0.0,
                "ecommerce_gstin": "",
                "igst": 0.0, "cgst": 0.0, "sgst": 0.0,
            })
            b["taxable_value"] += line["taxable"]
            b["igst"] += line["igst"]
            b["cgst"] += line["cgst"]
            b["sgst"] += line["sgst"]
            _add_hsn(hsn_b2c, hkey, line["qty"], line["line_value"], line["taxable"],
                     line["igst"], line["cgst"], line["sgst"])

    for line in _iter_sale_lines(db, hid, d_from, d_to):
        sale = line["sale"]
        if not module_included(selected, pharmacy_sale_module(sale)):
            continue
        bucket, pos = _classify_outward(sale, hospital)
        gstin = (sale.customer_gstin or "").strip()
        rate = line["rate"]
        hkey = _hsn_key(line["hsn_code"], line["hsn_desc"], rate)

        if rate <= 0:
            _add_nil(gstin, pos, line["taxable"], line["line_value"])
            _add_hsn(hsn_b2b if bucket == "b2b" else hsn_b2c, hkey,
                     line["qty"], line["line_value"], line["taxable"],
                     line["igst"], line["cgst"], line["sgst"])
            continue

        rec = {
            "gstin": gstin,
            "receiver_name": sale.patient_name or "",
            "invoice_number": sale.sale_number,
            "invoice_date": _fmt_inv_date(sale.sale_date),
            "invoice_value": reports._money(sale.grand_total),
            "place_of_supply": place_of_supply_label(pos),
            "place_of_supply_code": pos,
            "reverse_charge": "N",
            "applicable_pct": "",
            "invoice_type": "Regular",
            "ecommerce_gstin": "",
            "rate": rate,
            "taxable_value": reports._money(line["taxable"]),
            "igst": reports._money(line["igst"]),
            "cgst": reports._money(line["cgst"]),
            "sgst": reports._money(line["sgst"]),
            "cess": 0.0,
        }
        _push_taxable(bucket, pos, rec, line)

    bill_lines = list(_iter_bill_lines(db, hid, d_from, d_to, selected))
    for line in bill_lines:
        bill = line["bill"]
        gstin = line["gstin"]
        bucket, pos = classify_supply(gstin, line["invoice_value"], hospital)
        rate = line["rate"]
        hkey = _hsn_key(line["hsn_code"], line["hsn_desc"], rate)
        if rate <= 0:
            continue
        taxable_bill_ids.add(bill.id)
        rec = {
            "gstin": gstin,
            "receiver_name": line["party"],
            "invoice_number": bill.bill_number,
            "invoice_date": _fmt_inv_date(bill.bill_date),
            "invoice_value": line["invoice_value"],
            "place_of_supply": place_of_supply_label(pos),
            "place_of_supply_code": pos,
            "reverse_charge": "N",
            "applicable_pct": "",
            "invoice_type": "Regular",
            "ecommerce_gstin": "",
            "rate": rate,
            "taxable_value": reports._money(line["taxable"]),
            "igst": reports._money(line["igst"]),
            "cgst": reports._money(line["cgst"]),
            "sgst": reports._money(line["sgst"]),
            "cess": 0.0,
        }
        _push_taxable(bucket, pos, rec, line)

    # Exempt lines on mixed bills (already counted as taxable for other lines)
    for line in bill_lines:
        bill = line["bill"]
        if bill.id not in taxable_bill_ids:
            continue
        if line["rate"] > 0:
            continue
        gstin = line["gstin"]
        _bucket, pos = classify_supply(gstin, line["invoice_value"], hospital)
        _add_nil(gstin, pos, line["taxable"], line["line_value"])

    # Collapse B2B/B2CL to invoice × rate (sum lines of same rate)
    def _collapse_invoice_rate(rows, keys):
        grouped = {}
        for r in rows:
            k = tuple(r[x] for x in keys)
            g = grouped.get(k)
            if g is None:
                grouped[k] = dict(r)
            else:
                g["taxable_value"] = reports._money(g["taxable_value"] + r["taxable_value"])
                for taxk in ("igst", "cgst", "sgst", "cess"):
                    if taxk in g and taxk in r:
                        g[taxk] = reports._money(g[taxk] + r[taxk])
        return list(grouped.values())

    b2b_rows = _collapse_invoice_rate(
        b2b_rate_rows,
        ("gstin", "invoice_number", "rate"),
    )
    b2cl_rows = _collapse_invoice_rate(
        b2cl_rate_rows,
        ("invoice_number", "rate"),
    )
    b2cs_rows = []
    for v in b2cs_buckets.values():
        b2cs_rows.append({
            **v,
            "taxable_value": reports._money(v["taxable_value"]),
            "igst": reports._money(v["igst"]),
            "cgst": reports._money(v["cgst"]),
            "sgst": reports._money(v["sgst"]),
            "cess": 0.0,
        })
    b2cs_rows.sort(key=lambda r: (r["place_of_supply"], r["rate"]))

    # Credit / debit notes
    cdnr_rows = []
    cdnur_rows = []
    cdn_taxable = _empty_tax()
    cdn_taxable_b2b = _empty_tax()
    cdn_taxable_b2c = _empty_tax()

    return_headers = {}
    include_pharmacy_cdn = scope_includes_pharmacy_docs(selected)
    for line in _iter_return_lines(db, hid, d_from, d_to):
        ret = line["ret"]
        orig = ret.sale
        if orig and not module_included(selected, pharmacy_sale_module(orig)):
            continue
        if not orig and not include_pharmacy_cdn:
            continue
        return_headers[ret.id] = ret
        gstin = line["gstin"]
        orig = ret.sale
        bucket = "b2b"
        pos = home
        if orig:
            bucket, pos = _classify_outward(orig, hospital)
        elif gstin:
            pos = _gstin_state(gstin) or home
            bucket = "b2b"
        else:
            bucket = "b2cs"
        hkey = _hsn_key(line["hsn_code"], line["hsn_desc"], line["rate"])
        _add_hsn(
            hsn_b2b if bucket == "b2b" else hsn_b2c, hkey,
            line["qty"], line["line_value"], line["taxable"],
            line["igst"], line["cgst"], line["sgst"], sign=-1,
        )
        _add_tax(
            cdn_taxable, taxable=line["taxable"], igst=line["igst"],
            cgst=line["cgst"], sgst=line["sgst"], invoice_value=line["line_value"],
        )
        if bucket == "b2b":
            _add_tax(cdn_taxable_b2b, taxable=line["taxable"], igst=line["igst"],
                     cgst=line["cgst"], sgst=line["sgst"])
        else:
            _add_tax(cdn_taxable_b2c, taxable=line["taxable"], igst=line["igst"],
                     cgst=line["cgst"], sgst=line["sgst"])

        note = {
            "gstin": gstin,
            "receiver_name": line["party"],
            "note_number": ret.return_number,
            "note_date": ret.return_date.isoformat() if ret.return_date else "",
            "note_type": "C",
            "place_of_supply": place_of_supply_label(pos),
            "reverse_charge": "N",
            "note_supply_type": "Regular",
            "note_value": reports._money(ret.grand_total),
            "applicable_pct": "",
            "rate": line["rate"],
            "taxable_value": reports._money(line["taxable"]),
            "cess": 0.0,
            "igst": reports._money(line["igst"]),
            "cgst": reports._money(line["cgst"]),
            "sgst": reports._money(line["sgst"]),
        }
        if gstin:
            cdnr_rows.append(note)
        else:
            ur = "B2CL" if bucket == "b2cl" else "B2CS"
            cdnur_rows.append({
                "ur_type": ur,
                "note_number": note["note_number"],
                "note_date": note["note_date"],
                "note_type": "C",
                "place_of_supply": note["place_of_supply"],
                "note_value": note["note_value"],
                "applicable_pct": "",
                "rate": note["rate"],
                "taxable_value": note["taxable_value"],
                "cess": 0.0,
            })

    # Hospital credit notes (healthcare — usually exempt; follow parent module)
    notes = db.query(Bill).options(joinedload(Bill.patient), joinedload(Bill.items)).filter(
        Bill.hospital_id == hid,
        Bill.bill_type == "credit_note",
        Bill.status != "cancelled",
        sql_func.date(Bill.bill_date) >= d_from,
        sql_func.date(Bill.bill_date) <= d_to,
    ).all()
    include_hospital_cdn = scope_includes_hospital_credit_notes(selected)
    parent_ids = [b.parent_bill_id for b in notes if b.parent_bill_id]
    parents = {}
    if parent_ids:
        parents = {p.id: p for p in db.query(Bill).filter(Bill.id.in_(parent_ids)).all()}
    included_hospital_cns = []
    for b in notes:
        if not include_hospital_cdn:
            continue
        parent = parents.get(b.parent_bill_id) if b.parent_bill_id else None
        if selected:
            if not parent:
                continue
            if not module_included(selected, module_for_bill_type(parent.bill_type)):
                continue
        included_hospital_cns.append(b)
        p = b.patient
        gstin = (b.customer_gstin or (getattr(p, "gstin", None) or "") or "").strip()
        name = f"{p.first_name} {p.last_name}" if p else ""
        pos = _gstin_state(gstin) or home
        item_sgst = sum(float(it.sgst_amount or 0) for it in (b.items or []))
        item_cgst = sum(float(it.cgst_amount or 0) for it in (b.items or []))
        item_igst = sum(float(it.igst_amount or 0) for it in (b.items or []))
        item_tax = item_sgst + item_cgst + item_igst
        header_tax = float(b.tax_amount or 0)
        note_value = reports._money(b.total_amount)
        if item_tax > 0:
            taxable = reports._money(abs(note_value) - item_tax)
            sgst, cgst, igst = item_sgst, item_cgst, item_igst
            rate = reports._money(item_tax / taxable * 100.0) if taxable else 0.0
        elif header_tax:
            taxable = reports._money(max(abs(note_value) - abs(header_tax), 0))
            rate = reports._effective_tax_pct(header_tax, taxable)
            sgst, cgst, igst = split_gst_amounts(taxable, rate / 2.0, rate / 2.0, 0.0)
        else:
            taxable = note_value
            sgst = cgst = igst = 0.0
            rate = 0.0
        note = {
            "gstin": gstin,
            "receiver_name": name,
            "note_number": b.bill_number,
            "note_date": _fmt_inv_date(b.bill_date),
            "note_type": "C",
            "place_of_supply": place_of_supply_label(pos),
            "reverse_charge": "N",
            "note_supply_type": "Regular",
            "note_value": note_value,
            "applicable_pct": "",
            "rate": rate,
            "taxable_value": taxable,
            "cess": 0.0,
            "igst": reports._money(igst),
            "cgst": reports._money(cgst),
            "sgst": reports._money(sgst),
        }
        if gstin:
            cdnr_rows.append(note)
        else:
            cdnur_rows.append({
                "ur_type": "B2CS",
                "note_number": note["note_number"],
                "note_date": note["note_date"],
                "note_type": "C",
                "place_of_supply": note["place_of_supply"],
                "note_value": note["note_value"],
                "applicable_pct": "",
                "rate": note["rate"],
                "taxable_value": note["taxable_value"],
                "cess": 0.0,
            })

    cdnr_rows = _collapse_invoice_rate(cdnr_rows, ("gstin", "note_number", "rate"))
    cdnur_rows = _collapse_invoice_rate(cdnur_rows, ("ur_type", "note_number", "rate"))

    # Exempt healthcare (SAC 9993) — skip bills already reported as taxable
    exempt = reports.gst_exempt_register(db, hid, d_from, d_to, module=selected or "all")
    for r in exempt.get("rows") or []:
        if r.get("bill_id") in taxable_bill_ids:
            continue
        gstin = (r.get("gstin") or "").strip()
        pos = _gstin_state(gstin) or home
        val = float(r.get("billed") or r.get("taxable_value") or 0)
        _add_nil(gstin, pos, val, val)

    exemp_rows = [
        {
            "description": "Inter-State supplies to registered persons",
            "nil": nil_exempt["inter_reg"]["taxable"],
            "exempt": 0.0,
            "non_gst": 0.0,
        },
        {
            "description": "Intra-State supplies to registered persons",
            "nil": nil_exempt["intra_reg"]["taxable"],
            "exempt": 0.0,
            "non_gst": 0.0,
        },
        {
            "description": "Inter-State supplies to unregistered persons",
            "nil": nil_exempt["inter_unreg"]["taxable"],
            "exempt": 0.0,
            "non_gst": 0.0,
        },
        {
            "description": "Intra-State supplies to unregistered persons",
            "nil": nil_exempt["intra_unreg"]["taxable"],
            "exempt": 0.0,
            "non_gst": 0.0,
        },
    ]
    exemp_summary = {
        "nil": reports._money(sum(r["nil"] for r in exemp_rows)),
        "exempt": 0.0,
        "non_gst": 0.0,
    }

    hsn_b2b_rows = _hsn_rows(hsn_b2b)
    hsn_b2c_rows = _hsn_rows(hsn_b2c)

    # Documents issued
    completed_nums, voided_nums = [], []
    if scope_includes_pharmacy_docs(selected):
        sales_all = db.query(PharmacySale).filter(
            PharmacySale.hospital_id == hid,
            sql_func.date(PharmacySale.sale_date) >= d_from,
            sql_func.date(PharmacySale.sale_date) <= d_to,
        ).all()
        for s in sales_all:
            if not module_included(selected, pharmacy_sale_module(s)):
                continue
            if (s.status or "") == "completed":
                completed_nums.append(s.sale_number)
            elif (s.status or "") == "voided":
                voided_nums.append(s.sale_number)
    pharm_docs = _docs_series(completed_nums + voided_nums, cancelled=len(voided_nums))

    cn_nums = [r.return_number for r in return_headers.values()]
    cn_nums += [b.bill_number for b in included_hospital_cns if b.bill_number]
    cn_docs = _docs_series(cn_nums, cancelled=0)

    bill_nums = [r.get("number") for r in (exempt.get("rows") or []) if r.get("number")]
    hosp_docs = _docs_series(bill_nums, cancelled=0)

    docs_rows = []
    if pharm_docs["total"]:
        docs_rows.append({
            "nature": "Invoices for outward supply",
            **pharm_docs,
        })
    if hosp_docs["total"]:
        docs_rows.append({
            "nature": "Invoices for outward supply (healthcare)",
            **hosp_docs,
        })
    if cn_docs["total"]:
        docs_rows.append({
            "nature": "Credit Note",
            **cn_docs,
        })

    def _sum_rows(rows, *keys):
        return {k: reports._money(sum(float(r.get(k) or 0) for r in rows)) for k in keys}

    b2b_sum = _sum_rows(b2b_rows, "invoice_value", "taxable_value", "igst", "cgst", "sgst", "cess")
    b2b_sum["recipients"] = len({r["gstin"] for r in b2b_rows if r.get("gstin")})
    b2b_sum["invoices"] = len({r["invoice_number"] for r in b2b_rows})
    b2cl_sum = _sum_rows(b2cl_rows, "invoice_value", "taxable_value", "cess", "igst")
    b2cl_sum["invoices"] = len({r["invoice_number"] for r in b2cl_rows})
    b2cs_sum = _sum_rows(b2cs_rows, "taxable_value", "cess", "igst", "cgst", "sgst")

    outward_taxable = reports._money(
        b2b_sum.get("taxable_value", 0) + b2cl_sum.get("taxable_value", 0) + b2cs_sum.get("taxable_value", 0)
        - cdn_taxable["taxable"]
    )
    outward_igst = reports._money(
        b2b_sum.get("igst", 0) + b2cl_sum.get("igst", 0) + b2cs_sum.get("igst", 0) - cdn_taxable["igst"]
    )
    outward_cgst = reports._money(
        b2b_sum.get("cgst", 0) + b2cs_sum.get("cgst", 0) - cdn_taxable["cgst"]
    )
    outward_sgst = reports._money(
        b2b_sum.get("sgst", 0) + b2cs_sum.get("sgst", 0) - cdn_taxable["sgst"]
    )

    return {
        "kind": "gstr1",
        "disclaimer": DISCLAIMER,
        "hospital": hospital_meta(hospital, d_from, d_to, module=selected, db=db),
        "b2b": {"rows": b2b_rows, "summary": b2b_sum},
        "b2cl": {"rows": b2cl_rows, "summary": b2cl_sum},
        "b2cs": {"rows": b2cs_rows, "summary": b2cs_sum},
        "cdnr": {
            "rows": cdnr_rows,
            "summary": {
                "recipients": len({r["gstin"] for r in cdnr_rows if r.get("gstin")}),
                "notes": len({r["note_number"] for r in cdnr_rows}),
                "note_value": reports._money(sum(r.get("note_value") or 0 for r in cdnr_rows)),
                "taxable_value": reports._money(sum(r.get("taxable_value") or 0 for r in cdnr_rows)),
                "cess": 0.0,
            },
        },
        "cdnur": {
            "rows": cdnur_rows,
            "summary": {
                "notes": len({r["note_number"] for r in cdnur_rows}),
                "note_value": reports._money(sum(r.get("note_value") or 0 for r in cdnur_rows)),
                "taxable_value": reports._money(sum(r.get("taxable_value") or 0 for r in cdnur_rows)),
                "cess": 0.0,
            },
        },
        "exp": {"rows": []},
        "at": {"rows": []},
        "atadj": {"rows": []},
        "exemp": {"rows": exemp_rows, "summary": exemp_summary},
        "hsn_b2b": {"rows": hsn_b2b_rows, "summary": _hsn_summary(hsn_b2b_rows)},
        "hsn_b2c": {"rows": hsn_b2c_rows, "summary": _hsn_summary(hsn_b2c_rows)},
        "docs": {"rows": docs_rows},
        "totals": {
            "outward_taxable": outward_taxable,
            "outward_igst": outward_igst,
            "outward_cgst": outward_cgst,
            "outward_sgst": outward_sgst,
            "outward_tax": reports._money(outward_igst + outward_cgst + outward_sgst),
            "exempt_value": exemp_summary["nil"],
            "cdn_taxable": cdn_taxable["taxable"],
            "cdn_tax": reports._money(cdn_taxable["igst"] + cdn_taxable["cgst"] + cdn_taxable["sgst"]),
        },
    }


# ---------------------------------------------------------------------------
# GSTR-2 books (inward working paper for 2A/2B matching)
# ---------------------------------------------------------------------------

def gstr2_books(db: Session, hospital: Optional[Hospital], d_from: date, d_to: date,
                module: Optional[str] = None) -> dict:
    hid = hospital.id if hospital else 0
    home = hospital_state_code(hospital)
    selected = normalize_module(module)
    empty_itc = {"taxable": 0.0, "igst": 0.0, "cgst": 0.0, "sgst": 0.0, "total": 0.0}
    if not has_inward_books(selected):
        meta = hospital_meta(hospital, d_from, d_to, module=selected, db=db)
        return {
            "kind": "gstr2",
            "disclaimer": DISCLAIMER + " Inward GST in this product is pharmacy purchases (GRN). This module has no purchase register.",
            "hospital": meta,
            "b2b": {"rows": []},
            "unregistered": {"rows": []},
            "cdn": {"rows": []},
            "hsn": {"rows": [], "summary": _hsn_summary([])},
            "composition_inward": {"inter": 0.0, "intra": 0.0},
            "itc": empty_itc,
            "supplier_summary": [],
            "inward_note": (
                "IP pharmacy sales have no separate purchase register. Use Pharmacy GST for GRN ITC."
                if selected == "pharmacy_ip"
                else f"No inward books for {gst_scope_label(selected)}. Pharmacy GRN files on Pharmacy GST."
            ),
        }
    purchases = reports.purchase_summary(db, hid, d_from, d_to, group_by="supplier")
    inward_hsn = reports.gst_inward_hsn(db, hid, d_from, d_to)

    b2b = []
    unreg = []
    composition_inward = _empty_tax()
    composition_inward["intra"] = 0.0
    composition_inward["inter"] = 0.0

    purch_rows = (
        db.query(PharmacyPurchase)
        .options(joinedload(PharmacyPurchase.supplier), joinedload(PharmacyPurchase.items))
        .filter(
            PharmacyPurchase.hospital_id == hid,
            PharmacyPurchase.status == "confirmed",
            PharmacyPurchase.entry_date >= d_from,
            PharmacyPurchase.entry_date <= d_to,
        )
        .all()
    )
    for p in purch_rows:
        supplier = p.supplier
        gstin = ""
        name = ""
        ledger = ""
        state_code = ""
        if supplier:
            name = supplier.name or ""
            gstin = (supplier.gstin_no or supplier.gstin or "").strip()
            ledger = (supplier.ledger_type or "").strip().lower()
            state_code = (supplier.state_code or "").strip()[:2] or _gstin_state(gstin)
        pos = state_code or _gstin_state(gstin) or home
        taxable = sgst = cgst = igst = 0.0
        for it in p.items or []:
            t, s, c, i = reports._purchase_taxable_and_gst(it)
            taxable += t
            sgst += s
            cgst += c
            igst += i
        inv_date = p.bill_date or p.entry_date
        row = {
            "gstin": gstin,
            "supplier": name,
            "invoice_number": p.invoice_number or p.purchase_number,
            "invoice_date": inv_date.isoformat() if inv_date else "",
            "grn_number": p.purchase_number,
            "place_of_supply": place_of_supply_label(pos),
            "place_of_supply_code": pos,
            "taxable": reports._money(taxable),
            "igst": reports._money(igst),
            "cgst": reports._money(cgst),
            "sgst": reports._money(sgst),
            "cess": 0.0,
            "invoice_value": reports._money(p.grand_total),
            "total_tax": reports._money(sgst + cgst + igst),
            "match_key": f"{gstin}|{p.invoice_number or p.purchase_number}|{reports._money(sgst + cgst + igst)}",
            "ledger_type": ledger,
        }
        if ledger == "composition":
            if pos and home and pos != home:
                composition_inward["inter"] = reports._money(composition_inward["inter"] + taxable)
            else:
                composition_inward["intra"] = reports._money(composition_inward["intra"] + taxable)
        if gstin:
            b2b.append(row)
        else:
            unreg.append(row)

    cdn = []
    for r in purchases.get("returns") or []:
        gstin = (r.get("gstin") or "").strip()
        pos = _gstin_state(gstin) or home
        cdn.append({
            "gstin": gstin,
            "supplier": r.get("supplier") or "",
            "note_number": r.get("number") or "",
            "note_date": r.get("date") or "",
            "note_type": "C",
            "place_of_supply": place_of_supply_label(pos),
            "taxable": r.get("taxable") or 0,
            "igst": r.get("igst") or 0,
            "cgst": r.get("cgst") or 0,
            "sgst": r.get("sgst") or 0,
            "cess": 0.0,
            "note_value": r.get("grand_total") or 0,
            "total_tax": r.get("total_tax") or 0,
            "match_key": f"{gstin}|{r.get('number') or ''}|{r.get('total_tax') or 0}",
        })

    # Supplier credit notes recorded against returns
    scn = db.query(PharmacySupplierCreditNote).filter(
        PharmacySupplierCreditNote.hospital_id == hid,
        PharmacySupplierCreditNote.credit_note_date >= d_from,
        PharmacySupplierCreditNote.credit_note_date <= d_to,
    ).all() if hasattr(PharmacySupplierCreditNote, "hospital_id") else []
    for cn in scn:
        cdn.append({
            "gstin": "",
            "supplier": "",
            "note_number": cn.credit_note_number,
            "note_date": cn.credit_note_date.isoformat() if cn.credit_note_date else "",
            "note_type": "C",
            "place_of_supply": place_of_supply_label(home),
            "taxable": reports._money(cn.amount),
            "igst": 0.0, "cgst": 0.0, "sgst": 0.0, "cess": 0.0,
            "note_value": reports._money(cn.amount),
            "total_tax": 0.0,
            "match_key": f"|{cn.credit_note_number}|0",
        })

    itc = {
        "taxable": reports._money(sum(r["taxable"] for r in b2b + unreg) + sum(r["taxable"] for r in purchases.get("returns") or [])),
        "igst": reports._money(sum(r["igst"] for r in b2b + unreg) + sum((r.get("igst") or 0) for r in purchases.get("returns") or [])),
        "cgst": reports._money(sum(r["cgst"] for r in b2b + unreg) + sum((r.get("cgst") or 0) for r in purchases.get("returns") or [])),
        "sgst": reports._money(sum(r["sgst"] for r in b2b + unreg) + sum((r.get("sgst") or 0) for r in purchases.get("returns") or [])),
    }
    itc["total"] = reports._money(itc["igst"] + itc["cgst"] + itc["sgst"])

    hsn_rows = [
        {
            "hsn": r["hsn_code"],
            "description": r["hsn_code"],
            "uqc": DEFAULT_UQC,
            "qty": r.get("qty") or 0,
            "rate": _combined_rate(r.get("sgst_pct") or 0, r.get("cgst_pct") or 0, r.get("igst_pct") or 0),
            "taxable_value": r.get("taxable_value") or 0,
            "igst": r.get("igst_amount") or 0,
            "cgst": r.get("cgst_amount") or 0,
            "sgst": r.get("sgst_amount") or 0,
            "cess": 0.0,
            "total_value": reports._money((r.get("taxable_value") or 0) + (r.get("total_tax") or 0)),
        }
        for r in inward_hsn.get("rows") or []
    ]

    return {
        "kind": "gstr2",
        "disclaimer": (
            DISCLAIMER
            + " GSTR-2A/2B are auto-drafted on the GST portal from supplier filings; "
            "use this purchase register to match those downloads."
        ),
        "hospital": hospital_meta(hospital, d_from, d_to, module=selected, db=db),
        "b2b": {"rows": b2b},
        "unregistered": {"rows": unreg},
        "cdn": {"rows": cdn},
        "hsn": {"rows": hsn_rows, "summary": _hsn_summary(hsn_rows)},
        "composition_inward": {
            "inter": composition_inward["inter"],
            "intra": composition_inward["intra"],
        },
        "itc": itc,
        "supplier_summary": purchases.get("rows") or [],
        "inward_note": "",
    }


# ---------------------------------------------------------------------------
# GSTR-3B
# ---------------------------------------------------------------------------

def _tax_row(taxable=0, igst=0, cgst=0, sgst=0, cess=0) -> dict:
    return {
        "taxable": reports._money(taxable),
        "igst": reports._money(igst),
        "cgst": reports._money(cgst),
        "sgst": reports._money(sgst),
        "cess": reports._money(cess),
    }


def gstr3b_form(
    db: Session,
    hospital: Optional[Hospital],
    d_from: date,
    d_to: date,
    *,
    gstr1: Optional[dict] = None,
    gstr2: Optional[dict] = None,
    module: Optional[str] = None,
) -> dict:
    selected = normalize_module(module)
    gstr1 = gstr1 or gstr1_return(db, hospital, d_from, d_to, module=selected)
    gstr2 = gstr2 or gstr2_books(db, hospital, d_from, d_to, module=selected)
    t1 = gstr1["totals"]
    itc = gstr2["itc"]

    table_3_1 = {
        "a": _tax_row(t1["outward_taxable"], t1["outward_igst"], t1["outward_cgst"], t1["outward_sgst"]),
        "b": _tax_row(),
        "c": _tax_row(t1["exempt_value"]),
        "d": _tax_row(),
        "e": _tax_row(),
    }

    # 3.2 interstate unregistered from B2CL
    table_3_2 = []
    pos_buckets = defaultdict(lambda: {"taxable": 0.0, "igst": 0.0})
    for r in gstr1["b2cl"]["rows"]:
        pos_buckets[r.get("place_of_supply") or ""]["taxable"] += r.get("taxable_value") or 0
        pos_buckets[r.get("place_of_supply") or ""]["igst"] += r.get("igst") or 0
    for pos, v in pos_buckets.items():
        table_3_2.append({
            "place_of_supply": pos,
            "taxable": reports._money(v["taxable"]),
            "igst": reports._money(v["igst"]),
        })

    zero = _tax_row()
    all_other = _tax_row(itc["taxable"], itc["igst"], itc["cgst"], itc["sgst"])
    reversed_other = _tax_row()  # not auto-computed
    net_itc = _tax_row(
        all_other["taxable"] - reversed_other["taxable"],
        all_other["igst"] - reversed_other["igst"],
        all_other["cgst"] - reversed_other["cgst"],
        all_other["sgst"] - reversed_other["sgst"],
    )
    table_4 = {
        "a1_import_goods": zero,
        "a2_import_services": zero,
        "a3_rcm": zero,
        "a4_isd": zero,
        "a5_all_other": all_other,
        "b1_rules": zero,
        "b2_others": reversed_other,
        "c_net": net_itc,
        "d1_reclaimed": zero,
        "d2_ineligible": zero,
        "footnote": "ITC reversal (rules 38/42/43) and ineligible ITC under section 17(5) are not auto-computed.",
    }

    comp = gstr2["composition_inward"]
    table_5 = {
        "composition_nil_exempt": {"inter": comp["inter"], "intra": comp["intra"]},
        "non_gst": {"inter": 0.0, "intra": 0.0},
    }

    def _pay_head(payable, itc_avail):
        payable = reports._money(max(payable, 0))
        itc_use = reports._money(min(payable, max(itc_avail, 0)))
        cash = reports._money(payable - itc_use)
        return {"payable": payable, "itc": itc_use, "cash": cash, "tds_tcs": 0.0, "interest": 0.0, "late_fee": 0.0}

    table_6_1 = {
        "igst": _pay_head(table_3_1["a"]["igst"], net_itc["igst"]),
        "cgst": _pay_head(table_3_1["a"]["cgst"], net_itc["cgst"]),
        "sgst": _pay_head(table_3_1["a"]["sgst"], net_itc["sgst"]),
        "cess": _pay_head(0, 0),
    }
    table_6_2 = {"tds": _tax_row(), "tcs": _tax_row()}

    tax_payable = reports._money(
        table_6_1["igst"]["cash"] + table_6_1["cgst"]["cash"] + table_6_1["sgst"]["cash"]
    )
    check = {
        "gstr1_3b_taxable_match": abs(table_3_1["a"]["taxable"] - t1["outward_taxable"]) < 0.05,
        "gstr1_3b_tax_match": abs(
            table_3_1["a"]["igst"] + table_3_1["a"]["cgst"] + table_3_1["a"]["sgst"]
            - t1["outward_tax"]
        ) < 0.05,
        "itc_matches_gstr2": abs(net_itc["sgst"] + net_itc["cgst"] + net_itc["igst"] - itc["total"]) < 0.05,
    }

    # Legacy keys used by GstReportsPage / old audit Excel
    legacy = {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "outward_taxable": table_3_1["a"]["taxable"],
        "outward_sgst": table_3_1["a"]["sgst"],
        "outward_cgst": table_3_1["a"]["cgst"],
        "outward_igst": table_3_1["a"]["igst"],
        "outward_tax": t1["outward_tax"],
        "inward_taxable": itc["taxable"],
        "itc_sgst": net_itc["sgst"],
        "itc_cgst": net_itc["cgst"],
        "itc_igst": net_itc["igst"],
        "itc_total": reports._money(net_itc["igst"] + net_itc["cgst"] + net_itc["sgst"]),
        "exempt_value": table_3_1["c"]["taxable"],
        "tax_payable": reports._money(t1["outward_tax"] - (net_itc["igst"] + net_itc["cgst"] + net_itc["sgst"])),
    }

    return {
        "kind": "gstr3b",
        "disclaimer": DISCLAIMER,
        "hospital": hospital_meta(hospital, d_from, d_to, module=selected, db=db),
        "table_3_1": table_3_1,
        "table_3_2": table_3_2,
        "table_4": table_4,
        "table_5": table_5,
        "table_6_1": table_6_1,
        "table_6_2": table_6_2,
        "cash_payable": tax_payable,
        "check": check,
        **legacy,
    }


# ---------------------------------------------------------------------------
# GSTR-9 annual
# ---------------------------------------------------------------------------

def _sum_hsn(rows_a: list, rows_b: list) -> list:
    buckets = {}
    for r in (rows_a or []) + (rows_b or []):
        key = (r.get("hsn") or r.get("hsn_code") or "", r.get("rate") or 0, r.get("uqc") or DEFAULT_UQC)
        b = buckets.setdefault(key, {
            "hsn": key[0], "description": r.get("description") or key[0],
            "uqc": key[2], "rate": key[1],
            "qty": 0.0, "total_value": 0.0, "taxable_value": 0.0,
            "igst": 0.0, "cgst": 0.0, "sgst": 0.0, "cess": 0.0,
        })
        for k in ("qty", "total_value", "taxable_value", "igst", "cgst", "sgst", "cess"):
            b[k] = reports._money(b[k] + float(r.get(k) or 0))
    rows = list(buckets.values())
    rows.sort(key=lambda r: (r["hsn"], r["rate"]))
    return rows


def gstr9_annual(db: Session, hospital: Optional[Hospital], fy_start: int,
                 module: Optional[str] = None) -> dict:
    d_from, d_to = fy_bounds(fy_start)
    selected = normalize_module(module)
    gstr1 = gstr1_return(db, hospital, d_from, d_to, module=selected)
    gstr2 = gstr2_books(db, hospital, d_from, d_to, module=selected)
    gstr3b = gstr3b_form(db, hospital, d_from, d_to, gstr1=gstr1, gstr2=gstr2, module=selected)
    t1 = gstr1["totals"]
    a = gstr3b["table_3_1"]["a"]
    c = gstr3b["table_3_1"]["c"]
    itc = gstr3b["table_4"]["c_net"]
    pay = gstr3b["table_6_1"]

    table_4 = {
        "b2b": {
            "taxable": gstr1["b2b"]["summary"].get("taxable_value", 0),
            "igst": gstr1["b2b"]["summary"].get("igst", 0),
            "cgst": gstr1["b2b"]["summary"].get("cgst", 0),
            "sgst": gstr1["b2b"]["summary"].get("sgst", 0),
        },
        "b2c": {
            "taxable": reports._money(
                (gstr1["b2cs"]["summary"].get("taxable_value") or 0)
                + (gstr1["b2cl"]["summary"].get("taxable_value") or 0)
            ),
            "igst": reports._money(
                (gstr1["b2cs"]["summary"].get("igst") or 0)
                + (gstr1["b2cl"]["summary"].get("igst") or 0)
            ),
            "cgst": gstr1["b2cs"]["summary"].get("cgst", 0),
            "sgst": gstr1["b2cs"]["summary"].get("sgst", 0),
        },
        "nil_exempt": {"taxable": c["taxable"], "igst": 0.0, "cgst": 0.0, "sgst": 0.0},
        "credit_notes": {
            "taxable": t1["cdn_taxable"],
            "tax": t1["cdn_tax"],
        },
        "net_outward": a,
    }
    table_6 = {
        "itc_available": gstr3b["table_4"]["a5_all_other"],
        "itc_reversed": gstr3b["table_4"]["b2_others"],
        "net_itc": itc,
    }
    table_9 = {
        "igst": pay["igst"],
        "cgst": pay["cgst"],
        "sgst": pay["sgst"],
        "cess": pay["cess"],
    }
    hsn_out = _sum_hsn(gstr1["hsn_b2b"]["rows"], gstr1["hsn_b2c"]["rows"])
    hsn_in = gstr2["hsn"]["rows"]

    meta = hospital_meta(hospital, d_from, d_to, module=selected, db=db)
    meta["fy_start"] = int(fy_start)
    meta["fy_label"] = fy_label(fy_start)
    meta["period_label"] = fy_label(fy_start)

    return {
        "kind": "gstr9",
        "disclaimer": DISCLAIMER + " Annual working paper; interest, late fee, DRC and prior-year amendments are omitted.",
        "hospital": meta,
        "table_4": table_4,
        "table_6": table_6,
        "table_9": table_9,
        "table_17_hsn_outward": {"rows": hsn_out, "summary": _hsn_summary(hsn_out)},
        "table_18_hsn_inward": {"rows": hsn_in, "summary": gstr2["hsn"]["summary"]},
        "gstr3b": gstr3b,
    }


def resolve_hospital(db: Session, hospital_id: Optional[int]) -> Optional[Hospital]:
    if hospital_id:
        h = db.query(Hospital).filter(Hospital.id == hospital_id).first()
        if h:
            return h
    return db.query(Hospital).first()
