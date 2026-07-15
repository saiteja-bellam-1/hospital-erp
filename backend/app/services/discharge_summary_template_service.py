"""Hospital-wide discharge summary layout template (block-based JSON)."""

from __future__ import annotations

import copy
import json
import re
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.permissions import HospitalSettings

SETTING_CATEGORY = "inpatient"
SETTING_KEY = "discharge_summary_template"

BLOCK_TYPES = frozenset({
    "patient_info",
    "consultants",
    "standard_section",
    "custom_field",
    "static_text",
    "medications_table",
    "follow_up",
    "condition_on_discharge",
    "signatures",
    "acknowledgement",
})

# Structural blocks that must appear at most once
UNIQUE_STRUCTURAL_TYPES = frozenset({
    "patient_info",
    "consultants",
    "medications_table",
    "follow_up",
    "condition_on_discharge",
    "signatures",
    "acknowledgement",
})

# Payload keys used by generate_discharge_summary_pdf / editor catalog
STANDARD_FIELD_KEYS = frozenset({
    "chief_complaints_hpi",
    "allergies_summary",
    "past_history",
    "family_history",
    "physical_examination",
    "provisional_diagnosis",
    "primary_diagnosis",
    "findings_at_admission",
    "investigations_summary",
    "course_in_hospital",
    "procedure_notes",
    "discharge_advice",
})

# Map standard field_key → AdmissionDischargeSummary attributes to check (any non-empty).
# None = system-derived (e.g. allergies); skip required validation.
STANDARD_FIELD_ATTRS: dict[str, Optional[tuple[str, ...]]] = {
    "chief_complaints_hpi": ("chief_complaint", "present_medical_history"),
    "allergies_summary": None,
    "past_history": ("past_history",),
    "family_history": ("family_history",),
    "physical_examination": ("physical_examination_notes",),
    "provisional_diagnosis": ("provisional_diagnosis",),
    "primary_diagnosis": ("primary_diagnosis",),
    "findings_at_admission": ("findings_at_admission",),
    "investigations_summary": ("investigations_summary",),
    "course_in_hospital": ("course_in_hospital",),
    "procedure_notes": ("procedure_notes",),
    "discharge_advice": ("discharge_advice",),
}

_FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_STANDARD_SECTION_DEFS = [
    ("chief_complaints_hpi", "Chief Complaints & History of Present Illness", False),
    ("allergies_summary", "Allergies", False),
    ("past_history", "Past History", False),
    ("family_history", "Family History", False),
    ("physical_examination", "Physical Examination", False),
    ("provisional_diagnosis", "Provisional Diagnosis", False),
    ("primary_diagnosis", "Primary Diagnosis", True),
    ("findings_at_admission", "Key Findings At The Time Of Admission", False),
    ("investigations_summary", "Summary Of Key Investigation", False),
    ("course_in_hospital", "Summary Of Hospital Course", False),
    ("procedure_notes", "Surgery / Procedure Notes", False),
    ("discharge_advice", "Recommendations At Discharge", False),
]


def _new_id() -> str:
    return str(uuid.uuid4())


def _block(block_type: str, **extra: Any) -> dict:
    b: dict[str, Any] = {"id": _new_id(), "type": block_type}
    b.update(extra)
    return b


def build_default_template() -> dict:
    """Yashoda-style layout matching the pre-template PDF section order."""
    blocks: list[dict] = [
        _block("patient_info"),
        _block("consultants", label="Chief Consultant(s)"),
    ]
    for field_key, label, required in _STANDARD_SECTION_DEFS:
        blocks.append(_block(
            "standard_section",
            field_key=field_key,
            label=label,
            required=required,
        ))
    blocks.extend([
        _block("medications_table", label="Take-Home Medications"),
        _block("follow_up", label="Review / Follow-up"),
        _block("condition_on_discharge"),
        _block("signatures"),
        _block("acknowledgement"),
    ])
    return {
        "version": 1,
        "document_title": "DISCHARGE SUMMARY",
        "show_department_line": True,
        "blocks": blocks,
        "is_default": True,
    }


DEFAULT_TEMPLATE = build_default_template()


def _deepcopy_default() -> dict:
    tpl = copy.deepcopy(build_default_template())
    tpl["is_default"] = True
    return tpl


def validate_template(payload: Any) -> dict:
    """Validate and normalize a template dict. Raises ValueError on bad input."""
    if not isinstance(payload, dict):
        raise ValueError("Template must be an object")

    version = payload.get("version", 1)
    if version != 1:
        raise ValueError("Unsupported template version")

    title = (payload.get("document_title") or "DISCHARGE SUMMARY").strip()
    if not title:
        raise ValueError("document_title is required")

    show_dept = payload.get("show_department_line", True)
    if not isinstance(show_dept, bool):
        raise ValueError("show_department_line must be a boolean")

    blocks_in = payload.get("blocks")
    if not isinstance(blocks_in, list) or not blocks_in:
        raise ValueError("blocks must be a non-empty list")

    seen_ids: set[str] = set()
    seen_standard_keys: set[str] = set()
    seen_custom_keys: set[str] = set()
    seen_structural: set[str] = set()
    normalized: list[dict] = []

    for i, raw in enumerate(blocks_in):
        if not isinstance(raw, dict):
            raise ValueError(f"Block {i} must be an object")
        btype = raw.get("type")
        if btype not in BLOCK_TYPES:
            raise ValueError(f"Unknown block type: {btype!r}")

        if btype in UNIQUE_STRUCTURAL_TYPES:
            if btype in seen_structural:
                raise ValueError(f"Duplicate block type not allowed: {btype}")
            seen_structural.add(btype)

        bid = str(raw.get("id") or _new_id()).strip() or _new_id()
        if bid in seen_ids:
            bid = _new_id()
        seen_ids.add(bid)

        block: dict[str, Any] = {"id": bid, "type": btype}

        if btype == "consultants":
            label = (raw.get("label") or "Chief Consultant(s)").strip()
            block["label"] = label or "Chief Consultant(s)"

        elif btype == "standard_section":
            field_key = (raw.get("field_key") or "").strip()
            if field_key not in STANDARD_FIELD_KEYS:
                raise ValueError(f"Invalid standard field_key: {field_key!r}")
            if field_key in seen_standard_keys:
                raise ValueError(f"Duplicate standard section: {field_key}")
            seen_standard_keys.add(field_key)
            label = (raw.get("label") or field_key).strip()
            if not label:
                raise ValueError(f"Label required for standard section {field_key}")
            block["field_key"] = field_key
            block["label"] = label
            block["required"] = bool(raw.get("required", False))

        elif btype == "custom_field":
            field_key = (raw.get("field_key") or "").strip().lower()
            if not _FIELD_KEY_RE.match(field_key):
                raise ValueError(
                    f"custom_field field_key must be a lowercase slug (got {field_key!r})"
                )
            if field_key in STANDARD_FIELD_KEYS:
                raise ValueError(f"custom_field key collides with standard key: {field_key}")
            if field_key in seen_custom_keys:
                raise ValueError(f"Duplicate custom field_key: {field_key}")
            seen_custom_keys.add(field_key)
            label = (raw.get("label") or field_key).strip()
            if not label:
                raise ValueError(f"Label required for custom field {field_key}")
            input_type = (raw.get("input") or "textarea").strip()
            if input_type not in ("textarea", "text"):
                raise ValueError("custom_field input must be 'textarea' or 'text'")
            block["field_key"] = field_key
            block["label"] = label
            block["input"] = input_type
            block["required"] = bool(raw.get("required", False))

        elif btype == "static_text":
            label = (raw.get("label") or "").strip()
            content = raw.get("content")
            if content is None:
                content = ""
            if not isinstance(content, str):
                raise ValueError("static_text content must be a string")
            if not content.strip():
                raise ValueError("static_text content cannot be empty")
            block["label"] = label
            block["content"] = content

        elif btype in ("medications_table", "follow_up"):
            default_label = (
                "Take-Home Medications" if btype == "medications_table" else "Review / Follow-up"
            )
            label = (raw.get("label") or default_label).strip()
            block["label"] = label or default_label

        normalized.append(block)

    return {
        "version": 1,
        "document_title": title,
        "show_department_line": show_dept,
        "blocks": normalized,
        "is_default": False,
    }


def get_template(db: Session) -> dict:
    row = (
        db.query(HospitalSettings)
        .filter(
            HospitalSettings.setting_category == SETTING_CATEGORY,
            HospitalSettings.setting_key == SETTING_KEY,
        )
        .first()
    )
    if not row or not (row.setting_value or "").strip():
        return _deepcopy_default()
    try:
        raw = json.loads(row.setting_value)
        tpl = validate_template(raw)
        tpl["is_default"] = False
        return tpl
    except (json.JSONDecodeError, ValueError, TypeError):
        return _deepcopy_default()


def save_template(db: Session, payload: Any, *, created_by: Optional[int] = None) -> dict:
    tpl = validate_template(payload)
    stored = {k: v for k, v in tpl.items() if k != "is_default"}
    value = json.dumps(stored)
    row = (
        db.query(HospitalSettings)
        .filter(
            HospitalSettings.setting_category == SETTING_CATEGORY,
            HospitalSettings.setting_key == SETTING_KEY,
        )
        .first()
    )
    if row:
        row.setting_value = value
        row.setting_type = "json"
        row.description = "Hospital-wide discharge summary layout template"
    else:
        db.add(
            HospitalSettings(
                setting_category=SETTING_CATEGORY,
                setting_key=SETTING_KEY,
                setting_value=value,
                setting_type="json",
                description="Hospital-wide discharge summary layout template",
                created_by=created_by,
            )
        )
    db.commit()
    tpl["is_default"] = False
    return tpl


def reset_template(db: Session) -> dict:
    row = (
        db.query(HospitalSettings)
        .filter(
            HospitalSettings.setting_category == SETTING_CATEGORY,
            HospitalSettings.setting_key == SETTING_KEY,
        )
        .first()
    )
    if row:
        db.delete(row)
        db.commit()
    return _deepcopy_default()


def standard_section_content(discharge_data: dict, field_key: str) -> str:
    """Resolve printable content for a standard field from the PDF payload."""
    if field_key == "chief_complaints_hpi":
        return (
            discharge_data.get("chief_complaints_hpi")
            or discharge_data.get("present_medical_history")
            or ""
        )
    if field_key == "physical_examination":
        return discharge_data.get("physical_examination") or ""
    if field_key == "primary_diagnosis":
        return discharge_data.get("primary_diagnosis") or discharge_data.get("diagnosis") or ""
    if field_key == "course_in_hospital":
        return discharge_data.get("course_in_hospital") or discharge_data.get("treatment") or ""
    return discharge_data.get(field_key) or ""


def coerce_custom_fields(value) -> dict:
    """Normalize custom_fields from DB/API into a dict of string values."""
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value) if value.strip() else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    if not isinstance(value, dict):
        return {}
    cleaned = {}
    for k, v in value.items():
        if not isinstance(k, str) or not k.strip():
            continue
        cleaned[k.strip()] = v if isinstance(v, str) else ("" if v is None else str(v))
    return cleaned


def validate_summary_against_template(summary, template: dict) -> Optional[str]:
    """Return an error message if required template blocks are empty, else None."""
    custom = coerce_custom_fields(getattr(summary, "custom_fields", None))
    for block in template.get("blocks") or []:
        if not block.get("required"):
            continue
        btype = block.get("type")
        label = block.get("label") or block.get("field_key") or "field"
        if btype == "standard_section":
            field_key = block.get("field_key")
            attrs = STANDARD_FIELD_ATTRS.get(field_key)
            if attrs is None:
                continue
            if any((getattr(summary, a, None) or "").strip() for a in attrs):
                continue
            return f"{label} is required before finalizing"
        if btype == "custom_field":
            field_key = block.get("field_key")
            val = custom.get(field_key) if field_key else None
            if not (val or "").strip() if isinstance(val, str) else not val:
                return f"{label} is required before finalizing"
    return None
