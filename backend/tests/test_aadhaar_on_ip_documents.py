"""Aadhaar capture and inpatient document printing."""
import io

import pytest

from app.utils.aadhaar import format_aadhaar_display, normalize_aadhaar

AADHAAR = "234567890123"
DISPLAY = "2345 6789 0123"
HOSPITAL = {
    "name": "Test Hospital",
    "address": "1 Test Road",
    "phone": "9999999999",
    "email": "test@hospital.test",
}


def _pdf_text(buffer) -> str:
    data = buffer.getvalue() if hasattr(buffer, "getvalue") else buffer
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def test_normalize_aadhaar():
    assert normalize_aadhaar("2345 6789 0123") == AADHAAR
    assert normalize_aadhaar("2345-6789-0123") == AADHAAR
    assert normalize_aadhaar("") is None
    assert normalize_aadhaar(None) is None
    assert format_aadhaar_display(AADHAAR) == DISPLAY
    with pytest.raises(ValueError):
        normalize_aadhaar("12345")
    with pytest.raises(ValueError):
        normalize_aadhaar("012345678901")
    with pytest.raises(ValueError):
        normalize_aadhaar("23456789012A")


def test_ip_documents_print_aadhaar_when_present():
    from app.utils.pdf_service import pdf_service
    from app.utils.print_preview import (
        _sample_admission_detail,
        _sample_consent,
        _sample_discharge_summary,
        _sample_gate_pass,
        _sample_inpatient_bill,
    )

    documents = {
        "inpatient bill": pdf_service.generate_inpatient_bill_pdf(
            _sample_inpatient_bill(), HOSPITAL, include_header=False,
        ),
        "discharge summary": pdf_service.generate_discharge_summary_pdf(
            _sample_discharge_summary(), HOSPITAL, include_header=False,
        ),
        "admission detail": pdf_service.generate_admission_detail_pdf(
            _sample_admission_detail(), HOSPITAL, include_header=False,
        ),
        "consent": pdf_service.generate_consent_pdf(
            _sample_consent(), HOSPITAL, include_header=False,
        ),
        "gate pass": pdf_service.generate_gate_pass_pdf(
            _sample_gate_pass(), HOSPITAL, include_header=False,
        ),
        "case sheet": pdf_service.generate_admission_case_sheet_pdf(
            {
                "patient_name": "Sample Patient",
                "mrn": "MRN-PREVIEW",
                "aadhaar_number": AADHAAR,
                "age": "45",
                "gender": "Female",
                "primary_phone": "9999999999",
                "admission_number": "ADM-PREVIEW",
                "admission_date": "13/10/2026",
                "doctor_name": "Dr. Sample",
                "ward_bed": "General / 101",
            },
            HOSPITAL,
            include_header=False,
        ),
        "death certificate": pdf_service.generate_death_certificate_pdf(
            {
                "patient_name": "Sample Patient",
                "mrn": "MRN-PREVIEW",
                "aadhaar_number": AADHAAR,
                "age": "45",
                "gender": "F",
                "admission_number": "ADM-PREVIEW",
            },
            HOSPITAL,
            include_header=False,
        ),
        "dama": pdf_service.generate_dama_pdf(
            {
                "patient_name": "Sample Patient",
                "mrn": "MRN-PREVIEW",
                "aadhaar_number": AADHAAR,
                "age": "45",
                "gender": "F",
                "admission_number": "ADM-PREVIEW",
                "doctor_name": "Dr. Sample",
                "medical_advice_given": "Stay",
                "risks_explained": "Risk",
                "language_used": "english",
            },
            HOSPITAL,
            include_header=False,
        ),
        "deposit": pdf_service.generate_deposit_receipt_pdf(
            {
                "deposit_number": "DEP-1",
                "amount": 1000,
                "deposit_type": "advance",
                "payment_method": "cash",
                "patient_name": "Sample Patient",
                "mrn": "MRN-PREVIEW",
                "aadhaar_number": AADHAAR,
                "admission_number": "ADM-PREVIEW",
            },
            HOSPITAL,
            include_header=False,
        ),
        "handover": pdf_service.generate_handover_pdf(
            {
                "patient_name": "Sample Patient",
                "mrn": "MRN-PREVIEW",
                "aadhaar_number": AADHAAR,
                "admission_number": "ADM-PREVIEW",
                "from_shift": "morning",
            },
            HOSPITAL,
            include_header=False,
        ),
        "mlc": pdf_service.generate_mlc_register_pdf(
            {
                "patient_name": "Sample Patient",
                "aadhaar_number": AADHAAR,
                "age": "45",
                "gender": "F",
                "admission_number": "ADM-PREVIEW",
            },
            HOSPITAL,
            include_header=False,
        ),
        "body release": pdf_service.generate_body_release_pdf(
            {
                "patient_name": "Sample Patient",
                "mrn": "MRN-PREVIEW",
                "aadhaar_number": AADHAAR,
                "age": "45",
                "gender": "F",
                "admission_number": "ADM-PREVIEW",
            },
            HOSPITAL,
            include_header=False,
        ),
    }

    for name, buffer in documents.items():
        text = _pdf_text(buffer)
        assert DISPLAY in text, f"{name} did not print Aadhaar"


def test_ip_document_omits_blank_aadhaar():
    from app.utils.pdf_service import pdf_service
    from app.utils.print_preview import _sample_discharge_summary

    payload = _sample_discharge_summary()
    payload.pop("aadhaar_number", None)
    text = _pdf_text(pdf_service.generate_discharge_summary_pdf(
        payload, HOSPITAL, include_header=False,
    ))
    assert "Aadhaar" not in text


def test_register_patient_stores_aadhaar(client, auth_headers):
    created = client.post(
        "/api/patients/",
        headers=auth_headers,
        json={
            "first_name": "Aadhaar",
            "last_name": "Patient",
            "age": 40,
            "gender": "Male",
            "primary_phone": "9000001111",
            "aadhaar_number": "2345 6789 0123",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["aadhaar_number"] == AADHAAR

    fetched = client.get(f"/api/patients/{body['patient_id']}", headers=auth_headers)
    assert fetched.status_code == 200
    assert fetched.json()["aadhaar_number"] == AADHAAR

    rejected = client.post(
        "/api/patients/",
        headers=auth_headers,
        json={
            "first_name": "Bad",
            "last_name": "Aadhaar",
            "age": 30,
            "primary_phone": "9000002222",
            "aadhaar_number": "12345",
        },
    )
    assert rejected.status_code == 422
