"""Tests for blank prescription issue + download."""
from __future__ import annotations

import io
from datetime import datetime, time

from app.models.outpatient import Appointment
from app.models.patient import Patient
from app.models.prescriptions_simple import SimplePrescription


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    from PyPDF2 import PdfReader
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _create_appointment(db_session, seed_data) -> Appointment:
    apt = Appointment(
        appointment_number=f"APT-TEST-{datetime.now().strftime('%H%M%S%f')}",
        patient_id=seed_data["patient_id"],
        doctor_id=seed_data["doctor_user_id"],
        appointment_date=datetime.now(),
        appointment_time=time(10, 0),
        duration_minutes=10,
        appointment_type="consultation",
        status="scheduled",
        consultation_fee=0,
    )
    db_session.add(apt)
    db_session.commit()
    db_session.refresh(apt)
    return apt


def test_issue_blank_prescription_creates_record(client, auth_headers, db_session, seed_data):
    patient = db_session.query(Patient).filter(Patient.id == seed_data["patient_id"]).first()
    appointment = _create_appointment(db_session, seed_data)
    assert patient is not None

    response = client.post(
        "/api/prescriptions-simple/blank",
        json={
            "patient_id": patient.patient_id,
            "doctor_id": seed_data["doctor_user_id"],
            "appointment_id": appointment.id,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"
    rx_id = response.headers["x-prescription-id"]
    assert rx_id == f"RX-{appointment.appointment_number}"

    row = db_session.query(SimplePrescription).filter(
        SimplePrescription.prescription_id == rx_id
    ).first()
    assert row is not None
    assert row.status == "blank"
    assert row.medicines == []
    assert row.appointment_id == appointment.id


def test_blank_prescription_layout(client, auth_headers, db_session, seed_data):
    """Blank Rx: section headers only (no ruled blank lines); Rx + appointment on slip."""
    patient = db_session.query(Patient).filter(Patient.id == seed_data["patient_id"]).first()
    patient.referred_by = "Dr. Referral Test"
    appointment = _create_appointment(db_session, seed_data)
    db_session.commit()

    response = client.post(
        "/api/prescriptions-simple/blank",
        json={
            "patient_id": patient.patient_id,
            "doctor_id": seed_data["doctor_user_id"],
            "appointment_id": appointment.id,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    text = _extract_pdf_text(response.content)
    rx_id = response.headers["x-prescription-id"]

    assert "Rx No" in text
    assert rx_id in text
    assert appointment.appointment_number in text
    assert "Reg. No" not in text
    assert "Referred By" in text
    assert "Dr. Referral Test" in text
    assert "Vitals" in text
    assert "Height" in text
    assert "Weight" in text
    assert "Pulse" in text
    assert "SpO2" in text
    assert "Medicines" in text
    assert "Diagnosis" in text
    assert "Instructions" not in text
    assert "Appointment Reason" not in text
    # No long ruled placeholder lines
    assert "_" * 20 not in text

    vitals_pos = text.find("Vitals")
    medicines_pos = text.find("Medicines")
    diagnosis_pos = text.find("Diagnosis")
    assert vitals_pos < medicines_pos < diagnosis_pos


def test_doctor_save_reuses_blank_prescription_id(client, auth_headers, db_session, seed_data):
    """Doctor POST fills the same Rx record created by reception blank print."""
    patient = db_session.query(Patient).filter(Patient.id == seed_data["patient_id"]).first()
    appointment = _create_appointment(db_session, seed_data)

    blank = client.post(
        "/api/prescriptions-simple/blank",
        json={
            "patient_id": patient.patient_id,
            "doctor_id": seed_data["doctor_user_id"],
            "appointment_id": appointment.id,
        },
        headers=auth_headers,
    )
    assert blank.status_code == 200
    blank_rx_id = blank.headers["x-prescription-id"]

    filled = client.post(
        "/api/prescriptions-simple/",
        json={
            "patient_id": patient.patient_id,
            "appointment_id": appointment.id,
            "medicines": [
                {
                    "name": "Paracetamol 500mg",
                    "dosage": "1 tab twice daily",
                    "duration": "3 days",
                }
            ],
            "diagnosis": "Fever",
            "notes": "Rest and fluids",
        },
        headers=auth_headers,
    )
    assert filled.status_code == 200
    data = filled.json()
    assert data["prescription_id"] == blank_rx_id
    assert data["status"] == "active"
    assert len(data["medicines"]) == 1

    rows = db_session.query(SimplePrescription).filter(
        SimplePrescription.appointment_id == appointment.id
    ).all()
    assert len(rows) == 1
    assert rows[0].prescription_id == blank_rx_id


def test_issue_blank_prescription_requires_doctor(client, auth_headers, db_session, seed_data):
    patient = db_session.query(Patient).filter(Patient.id == seed_data["patient_id"]).first()
    response = client.post(
        "/api/prescriptions-simple/blank",
        json={"patient_id": patient.patient_id},
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_doctor_put_fills_blank_prescription_and_download_shows_medicines(
    client, auth_headers, db_session, seed_data
):
    """PUT on a reception-issued blank Rx must produce a filled PDF, not blank layout."""
    patient = db_session.query(Patient).filter(Patient.id == seed_data["patient_id"]).first()
    appointment = _create_appointment(db_session, seed_data)

    blank = client.post(
        "/api/prescriptions-simple/blank",
        json={
            "patient_id": patient.patient_id,
            "doctor_id": seed_data["doctor_user_id"],
            "appointment_id": appointment.id,
        },
        headers=auth_headers,
    )
    assert blank.status_code == 200
    blank_rx_id = blank.headers["x-prescription-id"]

    filled = client.put(
        f"/api/prescriptions-simple/{blank_rx_id}",
        json={
            "medicines": [
                {
                    "name": "Paracetamol 500mg",
                    "dosage": "1 tab twice daily",
                    "duration": "3 days",
                }
            ],
            "diagnosis": "Fever",
            "notes": "Rest and fluids",
        },
        headers=auth_headers,
    )
    assert filled.status_code == 200
    data = filled.json()
    assert data["status"] == "active"
    assert len(data["medicines"]) == 1

    download = client.get(
        f"/api/prescriptions-simple/{blank_rx_id}/download",
        headers=auth_headers,
    )
    assert download.status_code == 200
    text = _extract_pdf_text(download.content)
    assert "Paracetamol 500mg" in text
    assert "Fever" in text


def test_download_blank_prescription_by_id(client, auth_headers, db_session, seed_data):
    """Blank forms must use the dedicated blank download API, not /{id}/download."""
    patient = db_session.query(Patient).filter(Patient.id == seed_data["patient_id"]).first()
    appointment = _create_appointment(db_session, seed_data)
    issue = client.post(
        "/api/prescriptions-simple/blank",
        json={
            "patient_id": patient.patient_id,
            "doctor_id": seed_data["doctor_user_id"],
            "appointment_id": appointment.id,
        },
        headers=auth_headers,
    )
    rx_id = issue.headers["x-prescription-id"]

    download = client.get(
        f"/api/prescriptions-simple/{rx_id}/download",
        headers=auth_headers,
    )
    assert download.status_code == 409

    blank_download = client.get(
        "/api/prescriptions-simple/blank/download",
        params={
            "patient_id": patient.patient_id,
            "doctor_id": seed_data["doctor_user_id"],
            "appointment_id": appointment.id,
        },
        headers=auth_headers,
    )
    assert blank_download.status_code == 200
    assert blank_download.headers["content-type"] == "application/pdf"
    assert blank_download.content[:4] == b"%PDF"
