"""Tests for hospital-wide PDF print settings."""
from __future__ import annotations

import os
import sys

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.models.permissions import HospitalSettings
from app.utils.pdf_settings import (
    PRINT_INCLUDE_HEADER_KEY,
    PRINT_SETTING_CATEGORY,
    get_hospital_pdf_include_header,
    set_hospital_pdf_include_header,
)


def test_default_include_header_true_when_unset(db_session):
    assert get_hospital_pdf_include_header(db_session, 1) is True


def test_set_and_read_include_header_false(db_session):
    set_hospital_pdf_include_header(db_session, include_header=False, created_by=1)
    db_session.commit()
    assert get_hospital_pdf_include_header(db_session, 1) is False
    row = db_session.query(HospitalSettings).filter(
        HospitalSettings.setting_category == PRINT_SETTING_CATEGORY,
        HospitalSettings.setting_key == PRINT_INCLUDE_HEADER_KEY,
    ).first()
    assert row is not None
    assert row.setting_value == "false"
