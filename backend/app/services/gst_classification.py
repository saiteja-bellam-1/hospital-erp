"""GST classification for hospital bill lines and report unions.

Healthcare services default to GST-exempt SAC 9993. Pharmacy medicines are
taxable via HSN. Intra-state supplies use CGST+SGST; IGST is used only when
CGST/SGST snapshots are both zero.
"""
from sqlalchemy import event

SAC_HEALTHCARE = "9993"

TAX_EXEMPT = "exempt"
TAX_TAXABLE = "taxable"
TAX_NIL = "nil"

# item_type values that are taxable goods (HSN), not healthcare services.
TAXABLE_ITEM_TYPES = frozenset({
    "pharmacy",
    "medicine",
    "medicines",
    "drug",
    "consumable",
    "implant",
})

# item_type / bill_type → module key used by billing hub reports.
BILL_TYPE_TO_MODULE = {
    "consultation": "opd",
    "outpatient": "opd",
    "lab": "lab",
    "admission": "inpatient",
    "day_care": "day_care",
    "procedure": "day_care",
    "physiotherapy": "physiotherapy",
    "canteen": "canteen",
    "catch_up": "catch_up",
    "pharmacy": "pharmacy",
    "consolidated": "opd",
}

MODULE_LABELS = {
    "opd": "OPD",
    "lab": "Lab",
    "inpatient": "Inpatient",
    "pharmacy": "Pharmacy",
    "pharmacy_ip": "Pharmacy (IP)",
    "day_care": "Day Care",
    "physiotherapy": "Physiotherapy",
    "canteen": "Canteen",
    "catch_up": "Catch-up",
}

ALL_MODULES = tuple(MODULE_LABELS.keys())

# GST filing groups: Lab and Pharmacy keep their own GSTIN; everything else
# is one Hospital GST return (OPD, IP, day care, physio, canteen, catch-up).
PHARMACY_GST_MODULES = frozenset({"pharmacy", "pharmacy_ip"})
LAB_GST_MODULES = frozenset({"lab"})
HOSPITAL_GST_MODULES = frozenset(
    m for m in MODULE_LABELS if m not in PHARMACY_GST_MODULES and m not in LAB_GST_MODULES
)
GST_SCOPE_MODULES = {
    "hospital": HOSPITAL_GST_MODULES,
    "lab": LAB_GST_MODULES,
    "pharmacy": PHARMACY_GST_MODULES,
}
GST_SCOPE_LABELS = {
    "hospital": "Hospital GST",
    "lab": "Lab GST",
    "pharmacy": "Pharmacy GST",
}


def normalize_gst_scope(module: str | None) -> str | None:
    """GST filter key: None (all), hospital / lab / pharmacy, or a single module."""
    m = (module or "").strip().lower()
    if not m or m == "all":
        return None
    if m in GST_SCOPE_MODULES or m in MODULE_LABELS:
        return m
    return None


def gst_scope_modules(scope: str | None) -> frozenset | None:
    """Billing modules covered by a GST filter. None means every module."""
    if not scope:
        return None
    if scope in GST_SCOPE_MODULES:
        return GST_SCOPE_MODULES[scope]
    if scope in MODULE_LABELS:
        return frozenset({scope})
    return None


def module_in_gst_scope(scope: str | None, row_module: str) -> bool:
    mods = gst_scope_modules(scope)
    if mods is None:
        return True
    return row_module in mods


def gst_scope_label(scope: str | None) -> str:
    if not scope:
        return "All GST registrations"
    if scope in GST_SCOPE_LABELS:
        return GST_SCOPE_LABELS[scope]
    return MODULE_LABELS.get(scope, "All modules")


def config_bucket_for_scope(scope: str | None) -> str | None:
    """Module-settings bucket that stores this filing's GSTIN, if any."""
    if scope == "lab" or gst_scope_modules(scope) == LAB_GST_MODULES:
        return "lab"
    mods = gst_scope_modules(scope)
    if scope in ("pharmacy", "pharmacy_ip") or (mods and mods & PHARMACY_GST_MODULES):
        return "pharmacy"
    return None


def scope_has_inward_books(scope: str | None) -> bool:
    """Pharmacy GRN is the only inward register; it belongs on Pharmacy GST."""
    mods = gst_scope_modules(scope)
    if mods is None:
        return True
    return "pharmacy" in mods


def scope_includes_pharmacy_docs(scope: str | None) -> bool:
    mods = gst_scope_modules(scope)
    if mods is None:
        return True
    return bool(mods & PHARMACY_GST_MODULES)


def scope_includes_hospital_credit_notes(scope: str | None) -> bool:
    mods = gst_scope_modules(scope)
    if mods is None:
        return True
    return bool(mods - PHARMACY_GST_MODULES)

PHARMACY_SOURCE_REF_TYPES = frozenset({
    "prescription_item",
    "pharmacy_sale",
    "pharmacy_sale_item",
})


def classify_item_type(item_type: str | None) -> dict:
    """Return default GST stamp for a hospital bill line."""
    kind = (item_type or "").strip().lower()
    if kind in TAXABLE_ITEM_TYPES:
        return {
            "tax_category": TAX_TAXABLE,
            "hsn_sac": None,
            "sgst_pct": 0.0,
            "cgst_pct": 0.0,
            "igst_pct": 0.0,
        }
    return {
        "tax_category": TAX_EXEMPT,
        "hsn_sac": SAC_HEALTHCARE,
        "sgst_pct": 0.0,
        "cgst_pct": 0.0,
        "igst_pct": 0.0,
    }


def split_gst_amounts(taxable: float, sgst_pct: float, cgst_pct: float, igst_pct: float) -> tuple:
    """Return (sgst_amt, cgst_amt, igst_amt). Prefer CGST+SGST over IGST."""
    taxable = float(taxable or 0)
    sgst_pct = float(sgst_pct or 0)
    cgst_pct = float(cgst_pct or 0)
    igst_pct = float(igst_pct or 0)
    if sgst_pct or cgst_pct:
        return (
            round(taxable * sgst_pct / 100.0, 2),
            round(taxable * cgst_pct / 100.0, 2),
            0.0,
        )
    return 0.0, 0.0, round(taxable * igst_pct / 100.0, 2)


def gst_fields_from_hsn(hsn, taxable: float) -> dict:
    """Stamp kwargs for a taxable medicine line given a PharmacyHSN row."""
    sgst = float(getattr(hsn, "sgst_pct", 0) or 0) if hsn else 0.0
    cgst = float(getattr(hsn, "cgst_pct", 0) or 0) if hsn else 0.0
    igst = float(getattr(hsn, "igst_pct", 0) or 0) if hsn else 0.0
    if sgst or cgst:
        igst = 0.0
    sgst_amt, cgst_amt, igst_amt = split_gst_amounts(taxable, sgst, cgst, igst)
    return {
        "tax_category": TAX_TAXABLE,
        "hsn_sac": getattr(hsn, "code", None) if hsn else None,
        "sgst_pct": sgst,
        "cgst_pct": cgst,
        "igst_pct": igst,
        "sgst_amount": sgst_amt,
        "cgst_amount": cgst_amt,
        "igst_amount": igst_amt,
    }


def gst_fields_for_item(item_type: str | None, *, hsn=None, taxable: float = 0.0) -> dict:
    base = classify_item_type(item_type)
    if base["tax_category"] == TAX_TAXABLE and hsn is not None:
        return gst_fields_from_hsn(hsn, taxable)
    return {
        **base,
        "sgst_amount": 0.0,
        "cgst_amount": 0.0,
        "igst_amount": 0.0,
    }


def module_for_bill_type(bill_type: str | None) -> str:
    return BILL_TYPE_TO_MODULE.get((bill_type or "").strip().lower(), "catch_up")


def bill_types_for_module(module: str | None) -> list[str]:
    """Ledger bill_type values that map to a billing-hub module key."""
    m = (module or "").strip().lower()
    if not m or m == "all":
        return []
    return [bt for bt, mapped in BILL_TYPE_TO_MODULE.items() if mapped == m]


def is_pharmacy_sourced_item(item) -> bool:
    item_type = (getattr(item, "item_type", None) or "").strip().lower()
    ref = (getattr(item, "source_ref_type", None) or "").strip().lower()
    if ref in PHARMACY_SOURCE_REF_TYPES:
        return True
    return item_type in TAXABLE_ITEM_TYPES


def effective_tax_category(item) -> str:
    stored = (getattr(item, "tax_category", None) or "").strip().lower()
    if stored:
        return stored
    return classify_item_type(getattr(item, "item_type", None))["tax_category"]


def effective_hsn_sac(item) -> str | None:
    stored = getattr(item, "hsn_sac", None)
    if stored:
        return stored
    return classify_item_type(getattr(item, "item_type", None)).get("hsn_sac")


def register_bill_gst_listeners():
    """Stamp GST defaults on new BillItem rows. Safe to call once."""
    from app.models.billing import BillItem

    if getattr(BillItem, "_gst_listeners_registered", False):
        return
    BillItem._gst_listeners_registered = True

    @event.listens_for(BillItem, "before_insert")
    def _stamp_bill_item(mapper, connection, target):
        if not getattr(target, "tax_category", None):
            fields = gst_fields_for_item(
                target.item_type,
                taxable=float(getattr(target, "total_price", 0) or 0),
            )
            for key, value in fields.items():
                if getattr(target, key, None) in (None, ""):
                    setattr(target, key, value)
