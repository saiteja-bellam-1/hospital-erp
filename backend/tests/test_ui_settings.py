"""Tests for hospital-wide UI settings (nav layout)."""
from app.utils.ui_settings import (
    DEFAULT_NAV_LAYOUT,
    get_ui_settings_payload,
    normalize_nav_layout,
    update_ui_settings,
)


def test_normalize_nav_layout():
    assert normalize_nav_layout(None) == DEFAULT_NAV_LAYOUT
    assert normalize_nav_layout("header") == "header"
    assert normalize_nav_layout("SIDEBAR") == "sidebar"
    assert normalize_nav_layout("nope") == DEFAULT_NAV_LAYOUT


def test_ui_settings_default_and_update(db_session):
    payload = get_ui_settings_payload(db_session, hospital_id=1)
    assert payload["nav_layout"] == "sidebar"

    updated = update_ui_settings(
        db_session,
        hospital_id=1,
        nav_layout="header",
        created_by=1,
    )
    db_session.commit()
    assert updated["nav_layout"] == "header"

    again = get_ui_settings_payload(db_session, hospital_id=1)
    assert again["nav_layout"] == "header"

    update_ui_settings(db_session, 1, nav_layout="sidebar", created_by=1)
    db_session.commit()
    assert get_ui_settings_payload(db_session, 1)["nav_layout"] == "sidebar"
