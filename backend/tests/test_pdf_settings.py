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
    DEFAULT_LETTERHEAD_GAP_MM,
    PRINT_INCLUDE_HEADER_KEY,
    PRINT_LETTERHEAD_GAP_MM_KEY,
    PRINT_REPORT_OVERRIDES_KEY,
    PRINT_SETTING_CATEGORY,
    get_hospital_pdf_include_header,
    get_letterhead_gap_mm,
    get_report_header_overrides,
    pdf_gen_kwargs,
    resolve_include_header,
    resolve_print_options,
    set_hospital_pdf_include_header,
    set_letterhead_gap_mm,
    set_report_header_overrides,
    update_print_settings,
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


def test_letterhead_gap_default_and_custom(db_session):
    assert get_letterhead_gap_mm(db_session, 1) == DEFAULT_LETTERHEAD_GAP_MM
    set_letterhead_gap_mm(db_session, gap_mm=42, created_by=1)
    db_session.commit()
    assert get_letterhead_gap_mm(db_session, 1) == 42.0


def test_report_header_overrides(db_session):
    set_report_header_overrides(
        db_session,
        overrides={"prescription": "off", "lab_report": "on", "bogus": "on"},
        created_by=1,
    )
    db_session.commit()
    ov = get_report_header_overrides(db_session, 1)
    assert ov == {"prescription": "off", "lab_report": "on"}


def test_resolve_include_header_per_report(db_session):
    set_hospital_pdf_include_header(db_session, include_header=True, created_by=1)
    set_report_header_overrides(
        db_session, overrides={"prescription": "off"}, created_by=1
    )
    db_session.commit()
    assert resolve_include_header(
        global_default=True, report_type="prescription", overrides={"prescription": "off"}
    ) is False
    assert resolve_include_header(
        global_default=True, report_type="opd_bill", overrides={"prescription": "off"}
    ) is True


def test_resolve_print_options_uses_gap(db_session):
    set_hospital_pdf_include_header(db_session, include_header=False, created_by=1)
    set_letterhead_gap_mm(db_session, gap_mm=40, created_by=1)
    db_session.commit()
    opts = resolve_print_options(db_session, 1, "opd_bill")
    assert opts.include_header is False
    assert opts.letterhead_gap_pt > 0


def test_pdf_gen_kwargs_shape(db_session):
    set_hospital_pdf_include_header(db_session, include_header=True, created_by=1)
    db_session.commit()
    kw = pdf_gen_kwargs(db_session, 1, "lab_report")
    assert "include_header" in kw
    assert "letterhead_gap_pt" in kw


def test_resolve_print_options_draft(db_session):
    from app.utils.pdf_settings import resolve_print_options_draft

    opts = resolve_print_options_draft(
        include_header_on_pdfs=True,
        letterhead_gap_mm=45,
        report_header_overrides={"prescription": "off"},
        report_type="prescription",
    )
    assert opts.include_header is False
    assert opts.letterhead_gap_pt > 0


def test_generate_print_preview_pdf(db_session):
    from app.utils.print_preview import generate_print_preview_pdf

    buf = generate_print_preview_pdf(
        db_session,
        1,
        report_type="opd_bill",
        include_header_on_pdfs=False,
        letterhead_gap_mm=40,
    )
    data = buf.getvalue()
    assert data[:4] == b"%PDF"


def test_update_print_settings_payload(db_session):
    payload = update_print_settings(
        db_session,
        1,
        include_header_on_pdfs=False,
        letterhead_gap_mm=30,
        report_header_overrides={"opd_bill": "on"},
        created_by=1,
    )
    assert payload["include_header_on_pdfs"] is False
    assert payload["letterhead_gap_mm"] == 30.0
    assert payload["report_header_overrides"]["opd_bill"] == "on"
    assert any(r["key"] == "prescription" for r in payload["report_catalog"])
