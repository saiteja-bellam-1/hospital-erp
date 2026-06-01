"""Hospital-wide PDF print settings (letterhead on generated documents)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.permissions import HospitalSettings

PRINT_SETTING_CATEGORY = "print"
PRINT_INCLUDE_HEADER_KEY = "include_header_on_pdfs"


def _parse_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    v = str(value).strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def get_hospital_pdf_include_header(db: Session, hospital_id: int | None) -> bool:
    """Whether PDFs for this hospital should include the letterhead block."""
    if not hospital_id:
        return True
    row = (
        db.query(HospitalSettings)
        .filter(
            HospitalSettings.setting_category == PRINT_SETTING_CATEGORY,
            HospitalSettings.setting_key == PRINT_INCLUDE_HEADER_KEY,
        )
        .first()
    )
    return _parse_bool(row.setting_value if row else None, default=True)


def set_hospital_pdf_include_header(
    db: Session,
    *,
    include_header: bool,
    created_by: int | None = None,
) -> None:
    existing = (
        db.query(HospitalSettings)
        .filter(
            HospitalSettings.setting_category == PRINT_SETTING_CATEGORY,
            HospitalSettings.setting_key == PRINT_INCLUDE_HEADER_KEY,
        )
        .first()
    )
    value = "true" if include_header else "false"
    if existing:
        existing.setting_value = value
        existing.setting_type = "boolean"
    else:
        db.add(
            HospitalSettings(
                setting_category=PRINT_SETTING_CATEGORY,
                setting_key=PRINT_INCLUDE_HEADER_KEY,
                setting_value=value,
                setting_type="boolean",
                description="Show hospital letterhead on all generated PDFs",
                created_by=created_by,
            )
        )
