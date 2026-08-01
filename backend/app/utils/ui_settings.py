"""Hospital-wide UI chrome settings (nav layout, etc.)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.permissions import HospitalSettings

UI_SETTING_CATEGORY = "ui"
NAV_LAYOUT_KEY = "nav_layout"

VALID_NAV_LAYOUTS = frozenset({"sidebar", "header"})
DEFAULT_NAV_LAYOUT = "sidebar"


def _get_setting_row(db: Session, key: str) -> HospitalSettings | None:
    return (
        db.query(HospitalSettings)
        .filter(
            HospitalSettings.setting_category == UI_SETTING_CATEGORY,
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
                setting_category=UI_SETTING_CATEGORY,
                setting_key=key,
                setting_value=value,
                setting_type=setting_type,
                description=description,
                created_by=created_by,
            )
        )


def normalize_nav_layout(value: str | None) -> str:
    if value and str(value).strip().lower() in VALID_NAV_LAYOUTS:
        return str(value).strip().lower()
    return DEFAULT_NAV_LAYOUT


def get_ui_settings_payload(db: Session, hospital_id: int | None = None) -> dict[str, Any]:
    """Return hospital-wide UI settings. hospital_id reserved for multi-tenant later."""
    _ = hospital_id
    row = _get_setting_row(db, NAV_LAYOUT_KEY)
    nav_layout = normalize_nav_layout(row.setting_value if row else None)
    return {"nav_layout": nav_layout}


def update_ui_settings(
    db: Session,
    hospital_id: int | None,
    *,
    nav_layout: str | None = None,
    created_by: int | None = None,
) -> dict[str, Any]:
    _ = hospital_id
    if nav_layout is not None:
        layout = normalize_nav_layout(nav_layout)
        if layout not in VALID_NAV_LAYOUTS:
            raise ValueError(f"Invalid nav_layout: {nav_layout}")
        _upsert_setting(
            db,
            key=NAV_LAYOUT_KEY,
            value=layout,
            setting_type="string",
            description="App navigation chrome: sidebar or header",
            created_by=created_by,
        )
        db.flush()
    return get_ui_settings_payload(db, hospital_id)
