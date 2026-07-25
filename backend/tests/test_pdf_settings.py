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
    DEFAULT_PRESCRIPTION_VITAL_FIELDS,
    DEFAULT_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN,
    MAX_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN,
    MIN_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN,
    PRINT_DETAILED_BILLING_KEY,
    PRINT_INCLUDE_HEADER_KEY,
    PRINT_LETTERHEAD_GAP_MM_KEY,
    PRINT_REPORT_OVERRIDES_KEY,
    PRINT_SETTING_CATEGORY,
    bill_pdf_gen_kwargs,
    get_hospital_detailed_billing,
    get_hospital_pdf_include_header,
    get_hospital_pdf_include_footer,
    get_letterhead_gap_mm,
    get_prescription_include_vitals,
    get_prescription_vital_fields,
    get_prescription_vitals_column_width_in,
    get_prescription_vitals_layout,
    get_report_footer_overrides,
    get_report_header_overrides,
    normalize_prescription_vital_fields,
    pdf_gen_kwargs,
    resolve_include_footer,
    resolve_include_header,
    resolve_print_options,
    set_hospital_detailed_billing,
    set_hospital_pdf_include_footer,
    set_hospital_pdf_include_header,
    set_letterhead_gap_mm,
    set_prescription_include_vitals,
    set_prescription_vital_fields,
    set_prescription_vitals_column_width_in,
    set_prescription_vitals_layout,
    set_report_footer_overrides,
    set_report_header_overrides,
    update_print_settings,
)


def test_default_detailed_billing_true_when_unset(db_session):
    assert get_hospital_detailed_billing(db_session, 1) is True


def test_set_and_read_detailed_billing_false(db_session):
    set_hospital_detailed_billing(db_session, detailed_billing=False, created_by=1)
    db_session.commit()
    assert get_hospital_detailed_billing(db_session, 1) is False


def test_bill_pdf_gen_kwargs_includes_detailed_billing(db_session):
    set_hospital_detailed_billing(db_session, detailed_billing=False, created_by=1)
    db_session.commit()
    kw = bill_pdf_gen_kwargs(db_session, 1, "opd_bill")
    assert kw["detailed_billing"] is False
    assert "include_header" in kw


def test_generate_bill_pdf_simple_layout_hides_net_total(db_session):
    from app.utils.pdf_service import PDFService
    from io import BytesIO

    try:
        from PyPDF2 import PdfReader
    except ImportError:
        pytest.skip("PyPDF2 not installed")

    svc = PDFService()
    bill = {
        "bill_number": "T-1",
        "bill_date": "2026-01-01T00:00:00",
        "patient_name": "Test Patient",
        "payment_method": "Cash",
        "items": [{"item_name": "Consultation", "item_code": "C", "total_price": 1500}],
        "subtotal": 1500,
        "discount_amount": 100,
        "total_amount": 1400,
        "amount_paid": 1400,
        "balance_due": 0,
    }
    hi = {"name": "Test Hospital", "address": "", "phone": "", "email": ""}
    buf = svc.generate_bill_pdf(bill, hi, include_header=False, detailed_billing=False)
    text = "".join(PdfReader(BytesIO(buf.getvalue())).pages[0].extract_text() or "")
    assert "Sub Total" in text
    assert "Discount" in text
    assert "Total Amt" in text
    assert text.index("Sub Total") < text.index("Discount") < text.index("Total Amt")
    assert "Net Total" not in text
    assert "Paid Amt" not in text


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


def test_pdf_gen_kwargs_discharge_summary_respects_overrides(db_session):
    set_hospital_pdf_include_header(db_session, include_header=True, created_by=1)
    set_report_header_overrides(
        db_session, overrides={"discharge_summary": "off"}, created_by=1,
    )
    db_session.commit()
    kw = pdf_gen_kwargs(db_session, 1, "discharge_summary")
    assert kw["include_header"] is False

    set_hospital_pdf_include_header(db_session, include_header=False, created_by=1)
    set_report_header_overrides(db_session, overrides={}, created_by=1)
    db_session.commit()
    assert pdf_gen_kwargs(db_session, 1, "discharge_summary")["include_header"] is False
    assert pdf_gen_kwargs(
        db_session, 1, "discharge_summary", query_include_header=True,
    )["include_header"] is True


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
        detailed_billing_on_pdfs=False,
        letterhead_gap_mm=40,
    )
    data = buf.getvalue()
    assert data[:4] == b"%PDF"


def test_update_print_settings_payload(db_session):
    payload = update_print_settings(
        db_session,
        1,
        include_header_on_pdfs=False,
        detailed_billing_on_pdfs=False,
        letterhead_gap_mm=30,
        report_header_overrides={"opd_bill": "on"},
        created_by=1,
    )
    assert payload["include_header_on_pdfs"] is False
    assert payload["detailed_billing_on_pdfs"] is False
    assert payload["letterhead_gap_mm"] == 30.0
    assert payload["report_header_overrides"]["opd_bill"] == "on"
    assert any(r["key"] == "prescription" for r in payload["report_catalog"])


def test_default_include_footer_true_when_unset(db_session):
    assert get_hospital_pdf_include_footer(db_session, 1) is True


def test_set_and_read_include_footer_false(db_session):
    set_hospital_pdf_include_footer(db_session, include_footer=False, created_by=1)
    db_session.commit()
    assert get_hospital_pdf_include_footer(db_session, 1) is False


def test_report_footer_overrides_limited_to_reception_lab(db_session):
    set_report_footer_overrides(
        db_session,
        overrides={"opd_bill": "off", "lab_report": "on", "prescription": "off"},
        created_by=1,
    )
    db_session.commit()
    ov = get_report_footer_overrides(db_session, 1)
    assert ov == {"opd_bill": "off", "lab_report": "on"}


def test_pdf_gen_kwargs_include_footer_for_lab_and_bills(db_session):
    set_hospital_pdf_include_footer(db_session, include_footer=False, created_by=1)
    set_report_footer_overrides(db_session, overrides={}, created_by=1)
    db_session.commit()
    assert pdf_gen_kwargs(db_session, 1, "opd_bill")["include_footer"] is False
    assert pdf_gen_kwargs(db_session, 1, "lab_report")["include_footer"] is False
    assert "include_footer" not in pdf_gen_kwargs(db_session, 1, "prescription")


def test_generate_bill_pdf_hides_staff_footer_when_disabled(db_session):
    from io import BytesIO

    from PyPDF2 import PdfReader

    from app.utils.pdf_service import PDFService

    svc = PDFService()
    bill = {
        "bill_number": "T-FOOT-1",
        "bill_date": "2026-01-01T00:00:00",
        "patient_name": "Test Patient",
        "payment_method": "Cash",
        "items": [{"item_name": "Consultation", "item_code": "C", "total_price": 500}],
        "subtotal": 500,
        "discount_amount": 0,
        "amount_paid": 500,
        "balance_due": 0,
        "prepared_by": "Reception User",
    }
    hi = {"name": "Test Hospital", "address": "", "phone": "", "email": ""}
    on_text = "".join(
        PdfReader(BytesIO(svc.generate_bill_pdf(bill, hi, include_header=False, include_footer=True).getvalue()))
        .pages[0].extract_text() or ""
    )
    off_text = "".join(
        PdfReader(BytesIO(svc.generate_bill_pdf(bill, hi, include_header=False, include_footer=False).getvalue()))
        .pages[0].extract_text() or ""
    )
    assert "Prepared by" in on_text
    assert "Prepared by" not in off_text


def test_generate_lab_report_pdf_hides_technician_when_disabled(db_session):
    from io import BytesIO

    from PyPDF2 import PdfReader

    from app.utils.pdf_service import PDFService

    svc = PDFService()
    report = {
        "order_number": "LAB-1",
        "report_date": "2026-01-01T00:00:00",
        "patient_name": "Test Patient",
        "patient_age": 30,
        "patient_gender": "male",
        "test_name": "CBC",
        "technician_name": "Lab Tech One",
        "results": [],
    }
    hi = {"name": "Test Hospital", "address": "", "phone": "", "email": ""}
    on_text = "".join(
        PdfReader(BytesIO(svc.generate_lab_report_pdf(report, hi, {}, include_header=False, include_footer=True).getvalue()))
        .pages[0].extract_text() or ""
    )
    off_text = "".join(
        PdfReader(BytesIO(svc.generate_lab_report_pdf(report, hi, {}, include_header=False, include_footer=False).getvalue()))
        .pages[0].extract_text() or ""
    )
    assert "Lab Technician" in on_text
    assert "Lab Technician" not in off_text


def test_default_prescription_vitals_settings(db_session):
    assert get_prescription_include_vitals(db_session, 1) is True
    assert get_prescription_vitals_layout(db_session, 1) == "show"
    assert get_prescription_vitals_column_width_in(db_session, 1) == DEFAULT_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN
    assert get_prescription_vital_fields(db_session, 1) == list(DEFAULT_PRESCRIPTION_VITAL_FIELDS)


def test_set_and_read_prescription_vitals_settings(db_session):
    set_prescription_vitals_layout(db_session, layout="blank", created_by=1)
    set_prescription_vitals_column_width_in(db_session, width_in=2.0, created_by=1)
    set_prescription_vital_fields(
        db_session,
        vital_fields=["blood_pressure", "heart_rate", "spo2", "bogus"],
        created_by=1,
    )
    db_session.commit()
    assert get_prescription_include_vitals(db_session, 1) is False
    assert get_prescription_vitals_layout(db_session, 1) == "blank"
    assert get_prescription_vitals_column_width_in(db_session, 1) == 2.0
    assert get_prescription_vital_fields(db_session, 1) == [
        "blood_pressure",
        "heart_rate",
        "spo2",
    ]


def test_legacy_include_vitals_false_maps_to_blank(db_session):
    set_prescription_include_vitals(db_session, include_vitals=False, created_by=1)
    db_session.commit()
    assert get_prescription_vitals_layout(db_session, 1) == "blank"


def test_vitals_column_width_clamped_to_min_and_40pct_max(db_session):
    assert set_prescription_vitals_column_width_in(db_session, width_in=0.1, created_by=1) == MIN_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN
    assert set_prescription_vitals_column_width_in(db_session, width_in=99, created_by=1) == MAX_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN
    db_session.commit()
    assert get_prescription_vitals_column_width_in(db_session, 1) == MAX_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN


def test_normalize_prescription_vital_fields_falls_back_on_empty():
    assert normalize_prescription_vital_fields([]) == list(DEFAULT_PRESCRIPTION_VITAL_FIELDS)
    assert normalize_prescription_vital_fields(None) == list(DEFAULT_PRESCRIPTION_VITAL_FIELDS)


def test_pdf_gen_kwargs_includes_prescription_vitals(db_session):
    set_prescription_vitals_layout(db_session, layout="remove", created_by=1)
    set_prescription_vitals_column_width_in(db_session, width_in=1.5, created_by=1)
    set_prescription_vital_fields(
        db_session, vital_fields=["temperature", "weight"], created_by=1
    )
    db_session.commit()
    kw = pdf_gen_kwargs(db_session, 1, "prescription")
    assert kw["include_vitals"] is False
    assert kw["vitals_layout"] == "remove"
    assert kw["vitals_column_width_in"] == 1.5
    assert kw["vital_fields"] == ["temperature", "weight"]
    assert "include_vitals" not in pdf_gen_kwargs(db_session, 1, "opd_bill")


def test_generate_prescription_pdf_respects_vital_settings(db_session):
    from io import BytesIO

    from PyPDF2 import PdfReader

    from app.utils.pdf_service import PDFService

    svc = PDFService()
    rx = {
        "prescription_number": "RX-1",
        "prescription_date": "2026-01-01T00:00:00",
        "patient_name": "Test Patient",
        "patient_age": 30,
        "patient_gender": "M",
        "doctor_name": "Dr. Test",
        "doctor_specialization": "General",
        "items": [
            {
                "medicine_name": "Paracetamol",
                "dosage": "1 tablet",
                "duration": "3 days",
                "frequency_schedule": "1-0-1",
                "food_timing": "after_food",
            }
        ],
        "vitals": {
            "vital_signs": {
                "height": "170",
                "weight": "70",
                "blood_pressure": "120/80",
                "heart_rate": "72",
                "temperature": "98.6",
                "oxygen_saturation": "98",
                "bmi": "24.2",
                "pain_scale": "3",
            }
        },
        "lab_tests": [],
    }
    hi = {"name": "Test Hospital", "address": "", "phone": "", "email": ""}

    all_text = "".join(
        PdfReader(
            BytesIO(
                svc.generate_prescription_pdf(
                    rx, hi, include_header=False, vitals_layout="show"
                ).getvalue()
            )
        ).pages[0].extract_text()
        or ""
    )
    assert "Vitals" in all_text
    assert "120/80" in all_text

    subset_text = "".join(
        PdfReader(
            BytesIO(
                svc.generate_prescription_pdf(
                    rx,
                    hi,
                    include_header=False,
                    vitals_layout="show",
                    vital_fields=["blood_pressure", "pain_scale"],
                ).getvalue()
            )
        ).pages[0].extract_text()
        or ""
    )
    assert "120/80" in subset_text
    assert "Pain Score" in subset_text or "3" in subset_text
    assert "170" not in subset_text
    assert "98.6" not in subset_text

    blank_text = "".join(
        PdfReader(
            BytesIO(
                svc.generate_prescription_pdf(
                    rx, hi, include_header=False, vitals_layout="blank"
                ).getvalue()
            )
        ).pages[0].extract_text()
        or ""
    )
    assert "Vitals" not in blank_text
    assert "120/80" not in blank_text
    assert "Paracetamol" in blank_text

    remove_text = "".join(
        PdfReader(
            BytesIO(
                svc.generate_prescription_pdf(
                    rx, hi, include_header=False, vitals_layout="remove"
                ).getvalue()
            )
        ).pages[0].extract_text()
        or ""
    )
    assert "Vitals" not in remove_text
    assert "120/80" not in remove_text
    assert "Paracetamol" in remove_text


def test_update_print_settings_persists_prescription_vitals(db_session):
    payload = update_print_settings(
        db_session,
        1,
        prescription_vitals_layout="blank",
        prescription_vitals_column_width_in=2.0,
        prescription_vital_fields=["bmi", "spo2"],
        created_by=1,
    )
    db_session.commit()
    assert payload["prescription_include_vitals"] is False
    assert payload["prescription_vitals_layout"] == "blank"
    assert payload["prescription_vitals_column_width_in"] == 2.0
    assert payload["prescription_vitals_column_width_min_in"] == MIN_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN
    assert payload["prescription_vitals_column_width_max_in"] == MAX_PRESCRIPTION_VITALS_COLUMN_WIDTH_IN
    assert payload["prescription_vital_fields"] == ["bmi", "spo2"]
    assert "prescription_vital_catalog" in payload
