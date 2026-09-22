"""EHR patient chart/search should fall back to stored age when DOB is missing."""

import uuid
from datetime import date

from app.models.patient import Patient
from app.utils.patient_age import compute_age_parts_from_dob


def _make_patient(db_session, seed_data, **overrides):
    values = {
        "patient_id": str(uuid.uuid4()),
        "first_name": "NoDob",
        "last_name": "Patient",
        "gender": "female",
        "primary_phone": "9000000001",
        "hospital_id": seed_data["hospital_id"],
        "is_active": True,
    }
    values.update(overrides)
    patient = Patient(**values)
    db_session.add(patient)
    db_session.commit()
    db_session.refresh(patient)
    return patient


def test_history_uses_stored_age_when_no_dob(client, auth_headers, db_session, seed_data):
    patient = _make_patient(db_session, seed_data, age=42, age_months=6, date_of_birth=None)

    res = client.get(f"/api/ehr/patient/{patient.patient_id}/history", headers=auth_headers)
    assert res.status_code == 200, res.text
    info = res.json()["patient"]
    assert info["date_of_birth"] is None
    assert info["age"] == 42
    assert info["age_months"] == 6


def test_search_uses_stored_age_when_no_dob(client, auth_headers, db_session, seed_data):
    patient = _make_patient(
        db_session,
        seed_data,
        first_name="AgeOnly",
        last_name="Search",
        age=55,
        age_months=0,
        date_of_birth=None,
        primary_phone="9000000002",
    )

    res = client.get("/api/ehr/patients/search?q=AgeOnly", headers=auth_headers)
    assert res.status_code == 200, res.text
    match = next(p for p in res.json() if p["patient_id"] == patient.patient_id)
    assert match["date_of_birth"] is None
    assert match["age"] == 55
    assert match["age_months"] == 0


def test_history_prefers_dob_over_stored_age(client, auth_headers, db_session, seed_data):
    patient = db_session.query(Patient).filter(Patient.id == seed_data["patient_id"]).first()
    expected_years, expected_months, _ = compute_age_parts_from_dob(patient.date_of_birth or date(1990, 1, 1))

    res = client.get(f"/api/ehr/patient/{patient.patient_id}/history", headers=auth_headers)
    assert res.status_code == 200, res.text
    info = res.json()["patient"]
    assert info["age"] == expected_years
    assert info["age_months"] == expected_months
