"""Hospital PDF appearance: type, paper, and which blocks print.

Unset values match the PDFs the app already generates (Helvetica, A4,
standard margins, every section on).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator

TYPEFACES = frozenset({"helvetica", "times"})
SIZES = frozenset({"compact", "standard", "large"})
ACCENTS = frozenset({"black", "navy", "teal", "maroon"})
PAPERS = frozenset({"a4", "letter"})
MARGINS = frozenset({"compact", "standard", "wide"})
SPACINGS = frozenset({"tight", "standard", "roomy"})
PADDINGS = frozenset({"tight", "standard", "roomy"})
LINE_SPACINGS = frozenset({"tight", "standard", "open"})
ALIGNS = frozenset({"left", "center", "right"})

DEFAULT_TYPEFACE = "helvetica"
DEFAULT_SIZE = "standard"
DEFAULT_ACCENT = "black"
DEFAULT_PAPER = "a4"
DEFAULT_MARGINS = "standard"
DEFAULT_SPACING = "standard"
DEFAULT_PADDING = "standard"
DEFAULT_LINE_SPACING = "standard"
DEFAULT_TITLE_ALIGN = "center"
DEFAULT_BODY_ALIGN = "left"

FONT_SCALE = {"compact": 0.9, "standard": 1.0, "large": 1.15}
MARGIN_FACTOR = {"compact": 0.75, "standard": 1.0, "wide": 1.35}
SPACING_FACTOR = {"tight": 0.55, "standard": 1.0, "roomy": 1.7}
PADDING_FACTOR = {"tight": 0.55, "standard": 1.0, "roomy": 1.6}
LINE_FACTOR = {"tight": 0.9, "standard": 1.0, "open": 1.35}
ALIGN_TO_TA = {"left": 0, "center": 1, "right": 2}
ACCENT_HEX = {
    "navy": "#1B3A4B",
    "teal": "#0E6B6B",
    "maroon": "#6E2430",
}

# ReportLab base-14 faces. Body copy is authored as Helvetica; Times is the
# only other face that keeps <b> / <i> working without embedding a font file.
_FONT_MAP = {
    "Helvetica": "Times-Roman",
    "Helvetica-Bold": "Times-Bold",
    "Helvetica-Oblique": "Times-Italic",
    "Helvetica-BoldOblique": "Times-BoldItalic",
}

# True = printed today. False = available on the record, omitted until turned on.
SECTION_DEFAULTS: dict[str, dict[str, bool]] = {
    "bill": {
        "phone": True,
        "address": True,
        "referral": True,
        "token": True,
        "item_code": True,
        "amount_in_words": True,
        "quantity": False,
        "email": False,
        "aadhaar": False,
        "blood_group": False,
        "abha": False,
        "emergency_contact": False,
        "gstin": False,
    },
    "prescription": {
        "phone": True,
        "address": True,
        "referral": True,
        "diagnosis": True,
        "medicines": True,
        "instructions": True,
        "signature": True,
        "email": False,
        "aadhaar": False,
        "abha": False,
        "emergency_contact": False,
        "allergies": False,
        "medicine_notes": False,
    },
    "lab_report": {
        "reference_range": True,
        "remarks": True,
        "method": True,
        "email": False,
        "aadhaar": False,
        "blood_group": False,
        "abha": False,
        "emergency_contact": False,
        "sample_type": False,
    },
}

SECTION_GROUPS: dict[str, tuple[str, ...]] = {
    group: tuple(fields) for group, fields in SECTION_DEFAULTS.items()
}

PDF_LAYOUT_CATALOG: dict[str, Any] = {
    "typefaces": [
        {"value": "helvetica", "label": "Helvetica", "description": "Current print face."},
        {"value": "times", "label": "Times", "description": "Serif face for a more formal look."},
    ],
    "sizes": [
        {"value": "compact", "label": "Compact", "description": "Slightly smaller type."},
        {"value": "standard", "label": "Standard", "description": "Current type size."},
        {"value": "large", "label": "Large", "description": "Easier to read on the page."},
    ],
    "accents": [
        {"value": "black", "label": "Black", "swatch": "#111111"},
        {"value": "navy", "label": "Navy", "swatch": "#1B3A4B"},
        {"value": "teal", "label": "Teal", "swatch": "#0E6B6B"},
        {"value": "maroon", "label": "Maroon", "swatch": "#6E2430"},
    ],
    "papers": [
        {"value": "a4", "label": "A4", "description": "Current paper size."},
        {"value": "letter", "label": "Letter", "description": "US Letter (8.5 × 11 in)."},
    ],
    "margins": [
        {"value": "compact", "label": "Narrow", "description": "More content on the page."},
        {"value": "standard", "label": "Standard", "description": "Current margins."},
        {"value": "wide", "label": "Wide", "description": "More space around the content."},
    ],
    "spacings": [
        {"value": "tight", "label": "Tight", "description": "Less space between blocks."},
        {"value": "standard", "label": "Standard", "description": "Current space between blocks."},
        {"value": "roomy", "label": "Roomy", "description": "More space between blocks."},
    ],
    "paddings": [
        {"value": "tight", "label": "Tight", "description": "Text sits closer to the box edge."},
        {"value": "standard", "label": "Standard", "description": "Current padding inside tables."},
        {"value": "roomy", "label": "Roomy", "description": "More air inside each row."},
    ],
    "line_spacings": [
        {"value": "tight", "label": "Tight", "description": "Lines sit closer together."},
        {"value": "standard", "label": "Standard", "description": "Current line spacing."},
        {"value": "open", "label": "Open", "description": "More space between lines."},
    ],
    "aligns": [
        {"value": "left", "label": "Left"},
        {"value": "center", "label": "Centre"},
        {"value": "right", "label": "Right"},
    ],
    "sections": [
        {
            "group": "bill",
            "label": "Bills",
            "hint": "OPD bills, lab bills, and inpatient bills. Token and item code apply to OPD and lab bills.",
            "fields": [
                {"key": "phone", "label": "Patient phone"},
                {"key": "address", "label": "Patient address"},
                {"key": "referral", "label": "Doctor or referral"},
                {"key": "token", "label": "Token number"},
                {"key": "item_code", "label": "Item code column"},
                {"key": "amount_in_words", "label": "Amount in words"},
                {"key": "quantity", "label": "Quantity column", "optional": True},
                {"key": "email", "label": "Patient email", "optional": True},
                {"key": "aadhaar", "label": "Aadhaar", "optional": True},
                {"key": "blood_group", "label": "Blood group", "optional": True},
                {"key": "abha", "label": "ABHA ID", "optional": True},
                {"key": "emergency_contact", "label": "Emergency contact", "optional": True},
                {"key": "gstin", "label": "Patient GSTIN", "optional": True},
            ],
        },
        {
            "group": "prescription",
            "label": "Prescriptions",
            "hint": "Vitals stay on the Prescription tab. These switches cover the other blocks.",
            "fields": [
                {"key": "phone", "label": "Patient phone"},
                {"key": "address", "label": "Patient address"},
                {"key": "referral", "label": "Referred by"},
                {"key": "diagnosis", "label": "Diagnosis"},
                {"key": "medicines", "label": "Medicines"},
                {"key": "instructions", "label": "Instructions and follow-up"},
                {"key": "signature", "label": "Doctor signature"},
                {"key": "email", "label": "Patient email", "optional": True},
                {"key": "aadhaar", "label": "Aadhaar", "optional": True},
                {"key": "abha", "label": "ABHA ID", "optional": True},
                {"key": "emergency_contact", "label": "Emergency contact", "optional": True},
                {"key": "allergies", "label": "Allergies", "optional": True},
                {"key": "medicine_notes", "label": "Notes under each medicine", "optional": True},
            ],
        },
        {
            "group": "lab_report",
            "label": "Lab reports",
            "hint": "Single and combined reports. Patient details and the result value always print.",
            "fields": [
                {"key": "reference_range", "label": "Biological reference range"},
                {"key": "remarks", "label": "Parameter remarks"},
                {"key": "method", "label": "Method column"},
                {"key": "email", "label": "Patient email", "optional": True},
                {"key": "aadhaar", "label": "Aadhaar", "optional": True},
                {"key": "blood_group", "label": "Blood group", "optional": True},
                {"key": "abha", "label": "ABHA ID", "optional": True},
                {"key": "emergency_contact", "label": "Emergency contact", "optional": True},
                {"key": "sample_type", "label": "Sample type", "optional": True},
            ],
        },
    ],
}


def _default_sections() -> dict[str, dict[str, bool]]:
    return {group: dict(fields) for group, fields in SECTION_DEFAULTS.items()}


def _section_default(group: str, key: str) -> bool:
    return bool(SECTION_DEFAULTS.get(group, {}).get(key, True))


@dataclass(frozen=True)
class PdfLayout:
    typeface: str = DEFAULT_TYPEFACE
    size: str = DEFAULT_SIZE
    accent: str = DEFAULT_ACCENT
    paper: str = DEFAULT_PAPER
    margins: str = DEFAULT_MARGINS
    spacing: str = DEFAULT_SPACING
    padding: str = DEFAULT_PADDING
    line_spacing: str = DEFAULT_LINE_SPACING
    title_align: str = DEFAULT_TITLE_ALIGN
    body_align: str = DEFAULT_BODY_ALIGN
    sections: dict[str, dict[str, bool]] | None = None

    def __post_init__(self) -> None:
        if self.sections is None:
            object.__setattr__(self, "sections", _default_sections())

    @property
    def style_is_default(self) -> bool:
        return (
            self.typeface == DEFAULT_TYPEFACE
            and self.size == DEFAULT_SIZE
            and self.accent == DEFAULT_ACCENT
        )

    @property
    def format_is_default(self) -> bool:
        return self.paper == DEFAULT_PAPER and self.margins == DEFAULT_MARGINS

    @property
    def font_scale(self) -> float:
        return FONT_SCALE[self.size]

    @property
    def margin_factor(self) -> float:
        return MARGIN_FACTOR[self.margins]

    @property
    def accent_hex(self) -> str | None:
        return ACCENT_HEX.get(self.accent)

    @property
    def pagesize(self):
        from reportlab.lib.pagesizes import A4, letter

        return letter if self.paper == "letter" else A4

    def map_font(self, font_name: str) -> str:
        if self.typeface != "times" or not isinstance(font_name, str):
            return font_name
        return _FONT_MAP.get(font_name, font_name)

    @property
    def spacing_factor(self) -> float:
        return SPACING_FACTOR[self.spacing]

    @property
    def padding_factor(self) -> float:
        return PADDING_FACTOR[self.padding]

    @property
    def line_factor(self) -> float:
        return LINE_FACTOR[self.line_spacing]

    @property
    def rhythm_is_default(self) -> bool:
        return (
            self.spacing == DEFAULT_SPACING
            and self.padding == DEFAULT_PADDING
            and self.line_spacing == DEFAULT_LINE_SPACING
        )

    @property
    def align_is_default(self) -> bool:
        return self.title_align == DEFAULT_TITLE_ALIGN and self.body_align == DEFAULT_BODY_ALIGN

    def section_on(self, group: str, key: str) -> bool:
        group_map = (self.sections or {}).get(group) or {}
        if key not in group_map:
            return _section_default(group, key)
        return bool(group_map[key])

    def to_dict(self) -> dict[str, Any]:
        return {
            "typeface": self.typeface,
            "size": self.size,
            "accent": self.accent,
            "paper": self.paper,
            "margins": self.margins,
            "spacing": self.spacing,
            "padding": self.padding,
            "line_spacing": self.line_spacing,
            "title_align": self.title_align,
            "body_align": self.body_align,
            "sections": {
                group: {key: bool((self.sections or {}).get(group, {}).get(key, _section_default(group, key)))
                        for key in keys}
                for group, keys in SECTION_GROUPS.items()
            },
        }


def default_pdf_layout() -> PdfLayout:
    return PdfLayout(sections=_default_sections())


def _choice(value: Any, allowed: frozenset[str], fallback: str) -> str:
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in allowed:
            return cleaned
    return fallback


def normalize_pdf_layout(payload: Any) -> PdfLayout:
    """Drop unknown keys and fill anything missing with the current print look."""
    if payload is None:
        return default_pdf_layout()
    if not isinstance(payload, dict):
        raise ValueError("pdf_layout must be an object")

    sections_in = payload.get("sections") if isinstance(payload.get("sections"), dict) else {}
    sections: dict[str, dict[str, bool]] = {}
    for group, keys in SECTION_GROUPS.items():
        raw_group = sections_in.get(group) if isinstance(sections_in.get(group), dict) else {}
        sections[group] = {}
        for key in keys:
            if key in raw_group:
                sections[group][key] = bool(raw_group[key])
            else:
                sections[group][key] = _section_default(group, key)

    return PdfLayout(
        typeface=_choice(payload.get("typeface"), TYPEFACES, DEFAULT_TYPEFACE),
        size=_choice(payload.get("size"), SIZES, DEFAULT_SIZE),
        accent=_choice(payload.get("accent"), ACCENTS, DEFAULT_ACCENT),
        paper=_choice(payload.get("paper"), PAPERS, DEFAULT_PAPER),
        margins=_choice(payload.get("margins"), MARGINS, DEFAULT_MARGINS),
        spacing=_choice(payload.get("spacing"), SPACINGS, DEFAULT_SPACING),
        padding=_choice(payload.get("padding"), PADDINGS, DEFAULT_PADDING),
        line_spacing=_choice(payload.get("line_spacing"), LINE_SPACINGS, DEFAULT_LINE_SPACING),
        title_align=_choice(payload.get("title_align"), ALIGNS, DEFAULT_TITLE_ALIGN),
        body_align=_choice(payload.get("body_align"), ALIGNS, DEFAULT_BODY_ALIGN),
        sections=sections,
    )


_active: ContextVar[PdfLayout | None] = ContextVar("pdf_layout", default=None)


def active_pdf_layout() -> PdfLayout | None:
    return _active.get()


def section_on(group: str, key: str) -> bool:
    layout = _active.get()
    if layout is None:
        return _section_default(group, key)
    return layout.section_on(group, key)


def extra_patient_pdf_fields(patient) -> dict[str, str]:
    """Fields the record already stores that the standard PDF leaves off."""
    if patient is None:
        return {
            "patient_email": "",
            "aadhaar_number": "",
            "patient_blood_group": "",
            "abha_id": "",
            "emergency_contact": "",
            "gstin": "",
        }
    name = (getattr(patient, "emergency_contact_name", None) or "").strip()
    phone = (getattr(patient, "emergency_contact_phone", None) or "").strip()
    relation = (getattr(patient, "emergency_contact_relation", None) or "").strip()
    who = name
    if relation:
        who = f"{who} ({relation})" if who else relation
    if phone:
        who = f"{who} · {phone}" if who else phone
    return {
        "patient_email": (getattr(patient, "email", None) or "").strip(),
        "aadhaar_number": (getattr(patient, "aadhaar_number", None) or "").strip(),
        "patient_blood_group": (getattr(patient, "blood_group", None) or "").strip(),
        "abha_id": (getattr(patient, "abha_id", None) or "").strip(),
        "emergency_contact": who,
        "gstin": (getattr(patient, "gstin", None) or "").strip(),
    }


def stamp_patient_pdf_fields(payload: dict, patient) -> dict:
    """Copy optional print fields onto a bill or report payload."""
    extras = extra_patient_pdf_fields(patient)
    payload.update(extras)
    nested = payload.get("patient")
    if isinstance(nested, dict):
        nested.update(extras)
    return payload


@contextmanager
def use_pdf_layout(layout: PdfLayout | dict | None) -> Iterator[None]:
    resolved: PdfLayout | None
    if layout is None:
        resolved = None
    elif isinstance(layout, PdfLayout):
        resolved = layout
    else:
        resolved = normalize_pdf_layout(layout)
    token = _active.set(resolved)
    try:
        yield
    finally:
        _active.reset(token)
