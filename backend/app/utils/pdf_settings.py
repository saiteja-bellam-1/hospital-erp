"""Hospital-wide PDF print settings (letterhead, gap, per-report overrides)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.permissions import HospitalSettings

PRINT_SETTING_CATEGORY = "print"
PRINT_INCLUDE_HEADER_KEY = "include_header_on_pdfs"
PRINT_INCLUDE_FOOTER_KEY = "include_footer_on_pdfs"
PRINT_LETTERHEAD_GAP_MM_KEY = "letterhead_gap_mm"
PRINT_REPORT_OVERRIDES_KEY = "report_header_overrides"
PRINT_REPORT_FOOTER_OVERRIDES_KEY = "report_footer_overrides"

# Reports where staff-name / signature footers can be toggled (phase 1: reception + lab).
FOOTER_REPORT_KEYS = frozenset({"opd_bill", "lab_bill", "lab_report"})
PRINT_DETAILED_BILLING_KEY = "detailed_billing_on_pdfs"
PRINT_PRESCRIPTION_INCLUDE_VITALS_KEY = "prescription_include_vitals"
PRINT_PRESCRIPTION_VITAL_FIELDS_KEY = "prescription_vital_fields"
PRINT_PRESCRIPTION_VITALS_LAYOUT_KEY = "prescription_vitals_layout"
PRINT_PRESCRIPTION_VITALS_COLUMN_WIDTH_KEY = "prescription_vitals_column_width_in"
# Legacy key (percent); still read for migration when inches not set.
PRINT_PRESCRIPTION_VITALS_COLUMN_WIDTH_PCT_KEY = "prescription_vitals_column_width_pct"

DEFAULT_LETTERHEAD_GAP_MM = 35.0  # ~100 pt
MIN_LETTERHEAD_GAP_MM = 0.0
MAX_LETTERHEAD_GAP_MM = 80.0
MM_TO_PT = 72.0 / 25.4
INCH_TO_PT = 72.0

# show = print vitals; blank = reserve empty left column; remove = medicines full width
PRESCRIPTION_VITALS_LAYOUTS = frozenset({"show", "blank", "remove"})
DEFAULT_PRESCRIPTION_VITALS_LAYOUT = "show"

# Prescription PDF margins are 40pt each side on A4 (see pdf_service.generate_prescription_pdf).
_A4_WIDTH_PT = 595.27
_PRESCRIPTION_SIDE_MARGIN_PT = 40.0
PRESCRIPTION_USABLE_WIDTH_IN = (_A4_WIDTH_PT - 2 * _PRESCRIPTION_SIDE_MARGIN_PT) / INCH_TO_PT
MIN_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN = 0.5  # fixed minimum
MAX_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN = round(PRESCRIPTION_USABLE_WIDTH_IN * 0.40, 2)  # 40% of usable
DEFAULT_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN = 1.75  # ~former 25% default

OverrideValue = str  # "inherit" | "on" | "off"

# Catalog of vitals that can appear on the prescription left column.
# Order here is the default display order when the hospital has not customized.
PRESCRIPTION_VITAL_CATALOG: list[dict[str, str]] = [
    {"key": "height", "label": "Height", "unit": "cms"},
    {"key": "weight", "label": "Weight", "unit": "Kg"},
    {"key": "blood_pressure", "label": "Blood Pressure", "unit": ""},
    {"key": "heart_rate", "label": "Pulse", "unit": "/min"},
    {"key": "temperature", "label": "Temperature", "unit": "°F"},
    {"key": "respiratory_rate", "label": "Resp. Rate", "unit": "/min"},
    {"key": "spo2", "label": "SpO2", "unit": "%"},
    {"key": "bmi", "label": "BMI", "unit": ""},
    {"key": "pain_scale", "label": "Pain Score", "unit": ""},
]
VALID_PRESCRIPTION_VITAL_KEYS = {v["key"] for v in PRESCRIPTION_VITAL_CATALOG}
DEFAULT_PRESCRIPTION_VITAL_FIELDS: list[str] = [
    "height",
    "weight",
    "blood_pressure",
    "heart_rate",
    "temperature",
    "respiratory_rate",
    "spo2",
]

REPORT_CATALOG: list[dict[str, str]] = [
    {"key": "opd_bill", "label": "OPD Bill", "module": "outpatient"},
    {"key": "doctor_appointments", "label": "Doctor Appointments List", "module": "outpatient"},
    {"key": "prescription", "label": "Prescription", "module": "outpatient"},
    {"key": "lab_report", "label": "Lab Report", "module": "laboratory"},
    {"key": "lab_bill", "label": "Lab Bill", "module": "laboratory"},
    {"key": "inpatient_bill", "label": "Inpatient Bill", "module": "inpatient"},
    {"key": "discharge_summary", "label": "Discharge Summary", "module": "inpatient"},
    {"key": "admission_detail", "label": "Detailed Admission Summary", "module": "inpatient"},
    {"key": "deposit_receipt", "label": "Deposit Receipt", "module": "inpatient"},
    {"key": "gate_pass", "label": "Gate Pass", "module": "inpatient"},
    {"key": "consent", "label": "Consent Form", "module": "inpatient"},
    {"key": "death_certificate", "label": "Death Certificate", "module": "inpatient"},
    {"key": "dama", "label": "DAMA Form", "module": "inpatient"},
    {"key": "mlc_register", "label": "MLC Register", "module": "inpatient"},
    {"key": "body_release", "label": "Body Release", "module": "inpatient"},
    {"key": "refund_receipt", "label": "Refund Receipt", "module": "billing"},
    {"key": "credit_note", "label": "Credit Note", "module": "billing"},
    {"key": "settlement_statement", "label": "Settlement Statement", "module": "billing"},
    {"key": "census", "label": "Census Report", "module": "inpatient"},
    {"key": "handover", "label": "Handover Report", "module": "inpatient"},
    {"key": "monthly_outcomes", "label": "Monthly Outcomes", "module": "inpatient"},
    {"key": "doctor_productivity", "label": "Doctor Productivity", "module": "inpatient"},
    {"key": "pharmacy_sale_invoice", "label": "Pharmacy Sale Invoice", "module": "pharmacy"},
    {"key": "canteen_sale_receipt", "label": "Canteen Sale Receipt", "module": "canteen"},
    {"key": "pharmacy_purchase", "label": "Pharmacy Purchase", "module": "pharmacy"},
    {"key": "pharmacy_dispense", "label": "Dispense Slip", "module": "pharmacy"},
    {"key": "narcotic_register", "label": "Narcotic Register", "module": "pharmacy"},
    {"key": "pharmacy_report", "label": "Pharmacy Reports", "module": "pharmacy"},
]

VALID_REPORT_KEYS = {r["key"] for r in REPORT_CATALOG}
VALID_OVERRIDE_VALUES = {"inherit", "on", "off"}


@dataclass(frozen=True)
class PrintOptions:
    include_header: bool
    letterhead_gap_pt: float
    include_footer: bool = True


def _parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    v = str(value).strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def _get_setting_row(db: Session, key: str) -> HospitalSettings | None:
    return (
        db.query(HospitalSettings)
        .filter(
            HospitalSettings.setting_category == PRINT_SETTING_CATEGORY,
            HospitalSettings.setting_key == key,
        )
        .first()
    )


def _upsert_setting(
    db: Session,
    *,
    key: str,
    value: str,
    setting_type: str,
    description: str,
    created_by: int | None = None,
) -> None:
    existing = _get_setting_row(db, key)
    if existing:
        existing.setting_value = value
        existing.setting_type = setting_type
    else:
        db.add(
            HospitalSettings(
                setting_category=PRINT_SETTING_CATEGORY,
                setting_key=key,
                setting_value=value,
                setting_type=setting_type,
                description=description,
                created_by=created_by,
            )
        )


def mm_to_pt(mm: float) -> float:
    return float(mm) * MM_TO_PT


def pt_to_mm(pt: float) -> float:
    return float(pt) / MM_TO_PT


def clamp_letterhead_gap_mm(mm: float) -> float:
    return max(MIN_LETTERHEAD_GAP_MM, min(MAX_LETTERHEAD_GAP_MM, float(mm)))


def get_hospital_detailed_billing(db: Session, hospital_id: int | None) -> bool:
    """When True, bill PDFs show net total, paid amount, and balance rows."""
    if not hospital_id:
        return True
    row = _get_setting_row(db, PRINT_DETAILED_BILLING_KEY)
    return _parse_bool(row.setting_value if row else None, default=True)


def set_hospital_detailed_billing(
    db: Session,
    *,
    detailed_billing: bool,
    created_by: int | None = None,
) -> None:
    _upsert_setting(
        db,
        key=PRINT_DETAILED_BILLING_KEY,
        value="true" if detailed_billing else "false",
        setting_type="boolean",
        description="Show net total, paid amount, and balance on bill PDFs",
        created_by=created_by,
    )


def get_prescription_include_vitals(db: Session, hospital_id: int | None) -> bool:
    """When True, prescription PDFs include printed vitals (layout == show)."""
    return get_prescription_vitals_layout(db, hospital_id) == "show"


def set_prescription_include_vitals(
    db: Session,
    *,
    include_vitals: bool,
    created_by: int | None = None,
) -> None:
    """Legacy helper — maps boolean to show/blank layout."""
    set_prescription_vitals_layout(
        db,
        layout="show" if include_vitals else "blank",
        created_by=created_by,
    )


def normalize_prescription_vitals_layout(raw: Any) -> str:
    if raw is None:
        return DEFAULT_PRESCRIPTION_VITALS_LAYOUT
    v = str(raw).strip().lower()
    if v in PRESCRIPTION_VITALS_LAYOUTS:
        return v
    if v in ("1", "true", "yes", "on"):
        return "show"
    if v in ("0", "false", "no", "off"):
        return "blank"
    return DEFAULT_PRESCRIPTION_VITALS_LAYOUT


def get_prescription_vitals_layout(db: Session, hospital_id: int | None) -> str:
    """Prescription left-column mode: show | blank | remove."""
    if not hospital_id:
        return DEFAULT_PRESCRIPTION_VITALS_LAYOUT
    row = _get_setting_row(db, PRINT_PRESCRIPTION_VITALS_LAYOUT_KEY)
    if row and row.setting_value is not None:
        return normalize_prescription_vitals_layout(row.setting_value)
    # Backward compat: older installs only stored the boolean include flag
    legacy = _get_setting_row(db, PRINT_PRESCRIPTION_INCLUDE_VITALS_KEY)
    if legacy and legacy.setting_value is not None:
        return "show" if _parse_bool(legacy.setting_value, default=True) else "blank"
    return DEFAULT_PRESCRIPTION_VITALS_LAYOUT


def set_prescription_vitals_layout(
    db: Session,
    *,
    layout: str,
    created_by: int | None = None,
) -> str:
    cleaned = normalize_prescription_vitals_layout(layout)
    _upsert_setting(
        db,
        key=PRINT_PRESCRIPTION_VITALS_LAYOUT_KEY,
        value=cleaned,
        setting_type="string",
        description="Prescription vitals column: show, blank (pre-printed), or remove",
        created_by=created_by,
    )
    # Keep legacy boolean in sync for any older readers
    _upsert_setting(
        db,
        key=PRINT_PRESCRIPTION_INCLUDE_VITALS_KEY,
        value="true" if cleaned == "show" else "false",
        setting_type="boolean",
        description="Show vitals column on prescription PDFs",
        created_by=created_by,
    )
    return cleaned


def clamp_prescription_vitals_column_width_in(inches: float) -> float:
    return max(
        MIN_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN,
        min(MAX_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN, float(inches)),
    )


def get_prescription_vitals_column_width_in(db: Session, hospital_id: int | None) -> float:
    """Left column width in inches (show/blank layouts)."""
    if not hospital_id:
        return DEFAULT_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN
    row = _get_setting_row(db, PRINT_PRESCRIPTION_VITALS_COLUMN_WIDTH_KEY)
    if row and row.setting_value is not None:
        try:
            return clamp_prescription_vitals_column_width_in(float(row.setting_value))
        except (TypeError, ValueError):
            return DEFAULT_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN
    # Migrate legacy percent setting → inches
    legacy = _get_setting_row(db, PRINT_PRESCRIPTION_VITALS_COLUMN_WIDTH_PCT_KEY)
    if legacy and legacy.setting_value is not None:
        try:
            pct = float(legacy.setting_value)
            return clamp_prescription_vitals_column_width_in(
                PRESCRIPTION_USABLE_WIDTH_IN * (pct / 100.0)
            )
        except (TypeError, ValueError):
            pass
    return DEFAULT_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN


def set_prescription_vitals_column_width_in(
    db: Session,
    *,
    width_in: float,
    created_by: int | None = None,
) -> float:
    clamped = clamp_prescription_vitals_column_width_in(width_in)
    _upsert_setting(
        db,
        key=PRINT_PRESCRIPTION_VITALS_COLUMN_WIDTH_KEY,
        value=str(clamped),
        setting_type="number",
        description="Prescription left (vitals) column width in inches",
        created_by=created_by,
    )
    return clamped


def normalize_prescription_vital_fields(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return list(DEFAULT_PRESCRIPTION_VITAL_FIELDS)
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in raw:
        key = str(item).strip()
        if key not in VALID_PRESCRIPTION_VITAL_KEYS or key in seen:
            continue
        cleaned.append(key)
        seen.add(key)
    return cleaned if cleaned else list(DEFAULT_PRESCRIPTION_VITAL_FIELDS)


def get_prescription_vital_fields(db: Session, hospital_id: int | None) -> list[str]:
    """Ordered list of vital keys to show on the prescription vitals column."""
    if not hospital_id:
        return list(DEFAULT_PRESCRIPTION_VITAL_FIELDS)
    row = _get_setting_row(db, PRINT_PRESCRIPTION_VITAL_FIELDS_KEY)
    if not row or not row.setting_value:
        return list(DEFAULT_PRESCRIPTION_VITAL_FIELDS)
    try:
        raw = json.loads(row.setting_value)
    except (json.JSONDecodeError, TypeError):
        return list(DEFAULT_PRESCRIPTION_VITAL_FIELDS)
    return normalize_prescription_vital_fields(raw)


def set_prescription_vital_fields(
    db: Session,
    *,
    vital_fields: list[str],
    created_by: int | None = None,
) -> list[str]:
    cleaned = normalize_prescription_vital_fields(vital_fields)
    _upsert_setting(
        db,
        key=PRINT_PRESCRIPTION_VITAL_FIELDS_KEY,
        value=json.dumps(cleaned),
        setting_type="json",
        description="Ordered vital fields shown on prescription PDFs",
        created_by=created_by,
    )
    return cleaned


def resolve_prescription_vital_field_defs(vital_fields: list[str] | None) -> list[dict[str, str]]:
    """Map selected vital keys to catalog entries (label/unit), preserving order."""
    keys = normalize_prescription_vital_fields(vital_fields)
    by_key = {v["key"]: v for v in PRESCRIPTION_VITAL_CATALOG}
    return [by_key[k] for k in keys if k in by_key]


def get_hospital_pdf_include_header(db: Session, hospital_id: int | None) -> bool:
    """Whether PDFs for this hospital should include the letterhead block (global default)."""
    if not hospital_id:
        return True
    row = _get_setting_row(db, PRINT_INCLUDE_HEADER_KEY)
    return _parse_bool(row.setting_value if row else None, default=True)


def get_letterhead_gap_mm(db: Session, hospital_id: int | None) -> float:
    if not hospital_id:
        return DEFAULT_LETTERHEAD_GAP_MM
    row = _get_setting_row(db, PRINT_LETTERHEAD_GAP_MM_KEY)
    if not row or row.setting_value is None:
        return DEFAULT_LETTERHEAD_GAP_MM
    try:
        return clamp_letterhead_gap_mm(float(row.setting_value))
    except (TypeError, ValueError):
        return DEFAULT_LETTERHEAD_GAP_MM


def get_report_header_overrides(db: Session, hospital_id: int | None) -> dict[str, OverrideValue]:
    if not hospital_id:
        return {}
    row = _get_setting_row(db, PRINT_REPORT_OVERRIDES_KEY)
    if not row or not row.setting_value:
        return {}
    try:
        raw = json.loads(row.setting_value)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, OverrideValue] = {}
    for key, val in raw.items():
        if key not in VALID_REPORT_KEYS:
            continue
        v = str(val).strip().lower()
        if v in VALID_OVERRIDE_VALUES:
            cleaned[key] = v
    return cleaned


def get_hospital_pdf_include_footer(db: Session, hospital_id: int | None) -> bool:
    """Whether PDFs should include staff-name footers (global default)."""
    if not hospital_id:
        return True
    row = _get_setting_row(db, PRINT_INCLUDE_FOOTER_KEY)
    return _parse_bool(row.setting_value if row else None, default=True)


def get_report_footer_overrides(db: Session, hospital_id: int | None) -> dict[str, OverrideValue]:
    if not hospital_id:
        return {}
    row = _get_setting_row(db, PRINT_REPORT_FOOTER_OVERRIDES_KEY)
    if not row or not row.setting_value:
        return {}
    try:
        raw = json.loads(row.setting_value)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, OverrideValue] = {}
    for key, val in raw.items():
        if key not in FOOTER_REPORT_KEYS:
            continue
        v = str(val).strip().lower()
        if v in VALID_OVERRIDE_VALUES:
            cleaned[key] = v
    return cleaned


def resolve_include_header(
    *,
    global_default: bool,
    report_type: str | None,
    overrides: dict[str, OverrideValue],
    query_include_header: bool | None = None,
) -> bool:
    """Resolve letterhead on/off: query override → per-report → global default.

    A request-time ``include_header`` query wins so preview dialogs can toggle
    letterhead for a single print without changing hospital Print Settings.
    """
    if query_include_header is not None:
        return query_include_header
    if report_type and report_type in overrides:
        ov = overrides[report_type]
        if ov == "on":
            return True
        if ov == "off":
            return False
    return global_default


def resolve_include_footer(
    *,
    global_default: bool,
    report_type: str | None,
    overrides: dict[str, OverrideValue],
) -> bool:
    """Resolve staff-footer on/off for reception/lab reports."""
    if report_type not in FOOTER_REPORT_KEYS:
        return True
    if report_type and report_type in overrides:
        ov = overrides[report_type]
        if ov == "on":
            return True
        if ov == "off":
            return False
    return global_default


def resolve_print_options(
    db: Session,
    hospital_id: int | None,
    report_type: str | None = None,
    *,
    query_include_header: bool | None = None,
) -> PrintOptions:
    global_default = get_hospital_pdf_include_header(db, hospital_id)
    overrides = get_report_header_overrides(db, hospital_id)
    footer_default = get_hospital_pdf_include_footer(db, hospital_id)
    footer_overrides = get_report_footer_overrides(db, hospital_id)
    gap_mm = get_letterhead_gap_mm(db, hospital_id)
    include_header = resolve_include_header(
        global_default=global_default,
        report_type=report_type,
        overrides=overrides,
        query_include_header=query_include_header,
    )
    include_footer = resolve_include_footer(
        global_default=footer_default,
        report_type=report_type,
        overrides=footer_overrides,
    )
    return PrintOptions(
        include_header=include_header,
        letterhead_gap_pt=mm_to_pt(gap_mm),
        include_footer=include_footer,
    )


def get_print_settings_payload(db: Session, hospital_id: int | None) -> dict[str, Any]:
    footer_catalog = [r for r in REPORT_CATALOG if r["key"] in FOOTER_REPORT_KEYS]
    return {
        "include_header_on_pdfs": get_hospital_pdf_include_header(db, hospital_id),
        "include_footer_on_pdfs": get_hospital_pdf_include_footer(db, hospital_id),
        "detailed_billing_on_pdfs": get_hospital_detailed_billing(db, hospital_id),
        "prescription_include_vitals": get_prescription_include_vitals(db, hospital_id),
        "prescription_vitals_layout": get_prescription_vitals_layout(db, hospital_id),
        "prescription_vitals_column_width_in": get_prescription_vitals_column_width_in(
            db, hospital_id
        ),
        "prescription_vitals_column_width_min_in": MIN_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN,
        "prescription_vitals_column_width_max_in": MAX_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN,
        "prescription_vital_fields": get_prescription_vital_fields(db, hospital_id),
        "prescription_vital_catalog": PRESCRIPTION_VITAL_CATALOG,
        "letterhead_gap_mm": get_letterhead_gap_mm(db, hospital_id),
        "report_catalog": REPORT_CATALOG,
        "footer_report_catalog": footer_catalog,
        "report_header_overrides": get_report_header_overrides(db, hospital_id),
        "report_footer_overrides": get_report_footer_overrides(db, hospital_id),
    }


def set_hospital_pdf_include_header(
    db: Session,
    *,
    include_header: bool,
    created_by: int | None = None,
) -> None:
    _upsert_setting(
        db,
        key=PRINT_INCLUDE_HEADER_KEY,
        value="true" if include_header else "false",
        setting_type="boolean",
        description="Default: show hospital letterhead on generated PDFs",
        created_by=created_by,
    )


def set_letterhead_gap_mm(
    db: Session,
    *,
    gap_mm: float,
    created_by: int | None = None,
) -> float:
    clamped = clamp_letterhead_gap_mm(gap_mm)
    _upsert_setting(
        db,
        key=PRINT_LETTERHEAD_GAP_MM_KEY,
        value=str(clamped),
        setting_type="number",
        description="Top gap (mm) when letterhead is off, for pre-printed stationery",
        created_by=created_by,
    )
    return clamped


def set_report_header_overrides(
    db: Session,
    *,
    overrides: dict[str, str],
    created_by: int | None = None,
) -> dict[str, OverrideValue]:
    cleaned: dict[str, OverrideValue] = {}
    for key, val in overrides.items():
        if key not in VALID_REPORT_KEYS:
            continue
        v = str(val).strip().lower()
        if v in VALID_OVERRIDE_VALUES:
            cleaned[key] = v
    _upsert_setting(
        db,
        key=PRINT_REPORT_OVERRIDES_KEY,
        value=json.dumps(cleaned),
        setting_type="json",
        description="Per-report letterhead overrides (inherit/on/off)",
        created_by=created_by,
    )
    return cleaned


def set_hospital_pdf_include_footer(
    db: Session,
    *,
    include_footer: bool,
    created_by: int | None = None,
) -> None:
    _upsert_setting(
        db,
        key=PRINT_INCLUDE_FOOTER_KEY,
        value="true" if include_footer else "false",
        setting_type="boolean",
        description="Default: show staff names and signatures on PDF footers",
        created_by=created_by,
    )


def set_report_footer_overrides(
    db: Session,
    *,
    overrides: dict[str, str],
    created_by: int | None = None,
) -> dict[str, OverrideValue]:
    cleaned: dict[str, OverrideValue] = {}
    for key, val in overrides.items():
        if key not in FOOTER_REPORT_KEYS:
            continue
        v = str(val).strip().lower()
        if v in VALID_OVERRIDE_VALUES:
            cleaned[key] = v
    _upsert_setting(
        db,
        key=PRINT_REPORT_FOOTER_OVERRIDES_KEY,
        value=json.dumps(cleaned),
        setting_type="json",
        description="Per-report staff-footer overrides (inherit/on/off)",
        created_by=created_by,
    )
    return cleaned


def resolve_print_options_draft(
    *,
    include_header_on_pdfs: bool,
    letterhead_gap_mm: float,
    report_header_overrides: dict[str, str],
    report_type: str,
    include_footer_on_pdfs: bool = True,
    report_footer_overrides: dict[str, str] | None = None,
) -> PrintOptions:
    """Resolve print options from unsaved form values (preview / draft mode)."""
    cleaned: dict[str, OverrideValue] = {}
    for key, val in (report_header_overrides or {}).items():
        if key not in VALID_REPORT_KEYS:
            continue
        v = str(val).strip().lower()
        if v in VALID_OVERRIDE_VALUES:
            cleaned[key] = v
    footer_cleaned: dict[str, OverrideValue] = {}
    for key, val in (report_footer_overrides or {}).items():
        if key not in FOOTER_REPORT_KEYS:
            continue
        v = str(val).strip().lower()
        if v in VALID_OVERRIDE_VALUES:
            footer_cleaned[key] = v
    include_header = resolve_include_header(
        global_default=include_header_on_pdfs,
        report_type=report_type,
        overrides=cleaned,
    )
    include_footer = resolve_include_footer(
        global_default=include_footer_on_pdfs,
        report_type=report_type,
        overrides=footer_cleaned,
    )
    gap_mm = clamp_letterhead_gap_mm(letterhead_gap_mm)
    return PrintOptions(
        include_header=include_header,
        letterhead_gap_pt=mm_to_pt(gap_mm),
        include_footer=include_footer,
    )


def pdf_gen_kwargs(
    db: Session,
    hospital_id: int | None,
    report_type: str,
    *,
    query_include_header: bool | None = None,
) -> dict[str, float | bool | list[str]]:
    """Kwargs to pass into PDFService.generate_* methods."""
    opts = resolve_print_options(
        db, hospital_id, report_type, query_include_header=query_include_header
    )
    kw: dict[str, float | bool | list[str]] = {
        "include_header": opts.include_header,
        "letterhead_gap_pt": opts.letterhead_gap_pt,
    }
    if report_type in FOOTER_REPORT_KEYS:
        kw["include_footer"] = opts.include_footer
    if report_type == "prescription":
        layout = get_prescription_vitals_layout(db, hospital_id)
        kw["vitals_layout"] = layout
        kw["include_vitals"] = layout == "show"
        kw["vital_fields"] = get_prescription_vital_fields(db, hospital_id)
        kw["vitals_column_width_in"] = get_prescription_vitals_column_width_in(
            db, hospital_id
        )
    return kw


def bill_pdf_gen_kwargs(
    db: Session,
    hospital_id: int | None,
    report_type: str,
    *,
    query_include_header: bool | None = None,
) -> dict[str, float | bool]:
    """Print kwargs for itemised bill PDFs (OPD, lab, inpatient)."""
    return {
        **pdf_gen_kwargs(
            db, hospital_id, report_type, query_include_header=query_include_header
        ),
        "detailed_billing": get_hospital_detailed_billing(db, hospital_id),
    }


def update_print_settings(
    db: Session,
    hospital_id: int | None,
    *,
    include_header_on_pdfs: bool | None = None,
    include_footer_on_pdfs: bool | None = None,
    detailed_billing_on_pdfs: bool | None = None,
    prescription_include_vitals: bool | None = None,
    prescription_vitals_layout: str | None = None,
    prescription_vitals_column_width_in: float | None = None,
    prescription_vital_fields: list[str] | None = None,
    letterhead_gap_mm: float | None = None,
    report_header_overrides: dict[str, str] | None = None,
    report_footer_overrides: dict[str, str] | None = None,
    created_by: int | None = None,
) -> dict[str, Any]:
    if include_header_on_pdfs is not None:
        set_hospital_pdf_include_header(
            db, include_header=include_header_on_pdfs, created_by=created_by
        )
    if include_footer_on_pdfs is not None:
        set_hospital_pdf_include_footer(
            db, include_footer=include_footer_on_pdfs, created_by=created_by
        )
    if detailed_billing_on_pdfs is not None:
        set_hospital_detailed_billing(
            db, detailed_billing=detailed_billing_on_pdfs, created_by=created_by
        )
    if prescription_vitals_layout is not None:
        set_prescription_vitals_layout(
            db, layout=prescription_vitals_layout, created_by=created_by
        )
    elif prescription_include_vitals is not None:
        set_prescription_include_vitals(
            db, include_vitals=prescription_include_vitals, created_by=created_by
        )
    if prescription_vitals_column_width_in is not None:
        set_prescription_vitals_column_width_in(
            db,
            width_in=prescription_vitals_column_width_in,
            created_by=created_by,
        )
    if prescription_vital_fields is not None:
        set_prescription_vital_fields(
            db, vital_fields=prescription_vital_fields, created_by=created_by
        )
    if letterhead_gap_mm is not None:
        set_letterhead_gap_mm(db, gap_mm=letterhead_gap_mm, created_by=created_by)
    if report_header_overrides is not None:
        set_report_header_overrides(
            db, overrides=report_header_overrides, created_by=created_by
        )
    if report_footer_overrides is not None:
        set_report_footer_overrides(
            db, overrides=report_footer_overrides, created_by=created_by
        )
    return get_print_settings_payload(db, hospital_id)
