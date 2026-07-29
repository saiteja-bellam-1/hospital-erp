"""Emergency consultation fee — OP appointment booking.

Booking with priority="emergency" charges the doctor's emergency_fee_inr
(replacing the regular consultation fee, falling back to it when unset),
even for follow-up type visits. Fee changes on unpaid appointments recalc.
"""

import pytest

from app.models.patient import Patient
from app.models.user import User


@pytest.fixture()
def doctor_fees(db_session, seed_data):
    """Give the seeded doctor both regular and emergency rates."""
    doctor = db_session.query(User).filter(User.id == seed_data["doctor_user_id"]).first()
    doctor.consultation_fee_inr = "₹500"
    doctor.emergency_fee_inr = "₹1000"
    db_session.commit()
    return seed_data


@pytest.fixture()
def patient_uuid(db_session, seed_data):
    patient = db_session.query(Patient).filter(Patient.id == seed_data["patient_id"]).first()
    return patient.patient_id


def _book(client, headers, patient_uuid, doctor_id, **overrides):
    payload = {
        "patient_id": patient_uuid,
        "doctor_id": doctor_id,
        "appointment_date": "2026-07-29",
        "payment_status": "pending",
    }
    payload.update(overrides)
    res = client.post("/api/appointments/", headers=headers, json=payload)
    assert res.status_code == 200, res.text
    return res.json()


class TestEmergencyFee:
    def test_emergency_booking_charges_emergency_fee(self, client, auth_headers, doctor_fees, patient_uuid):
        apt = _book(client, auth_headers, patient_uuid, doctor_fees["doctor_user_id"], priority="emergency")
        assert apt["priority"] == "emergency"
        assert apt["consultation_fee"] == 1000.0
        assert apt["final_amount"] == 1000.0

    def test_normal_booking_charges_regular_fee(self, client, auth_headers, doctor_fees, patient_uuid):
        apt = _book(client, auth_headers, patient_uuid, doctor_fees["doctor_user_id"], priority="normal")
        assert apt["consultation_fee"] == 500.0

    def test_followup_is_free(self, client, auth_headers, doctor_fees, patient_uuid):
        apt = _book(client, auth_headers, patient_uuid, doctor_fees["doctor_user_id"], appointment_type="followup")
        assert apt["consultation_fee"] == 0.0

    def test_emergency_overrides_free_followup(self, client, auth_headers, doctor_fees, patient_uuid):
        apt = _book(client, auth_headers, patient_uuid, doctor_fees["doctor_user_id"],
                    priority="emergency", appointment_type="followup")
        assert apt["consultation_fee"] == 1000.0

    def test_emergency_falls_back_to_regular_fee(self, client, auth_headers, doctor_fees, patient_uuid, db_session):
        doctor = db_session.query(User).filter(User.id == doctor_fees["doctor_user_id"]).first()
        doctor.emergency_fee_inr = None
        db_session.commit()
        apt = _book(client, auth_headers, patient_uuid, doctor_fees["doctor_user_id"], priority="emergency")
        assert apt["consultation_fee"] == 500.0
        doctor.emergency_fee_inr = "₹1000"
        db_session.commit()

    def test_bill_labels_emergency_consultation_fee(self, client, auth_headers, doctor_fees, patient_uuid):
        apt = _book(client, auth_headers, patient_uuid, doctor_fees["doctor_user_id"], priority="emergency")
        res = client.get(f"/api/appointments/{apt['id']}/bill", headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["items"][0]["item_name"].startswith("Emergency Consultation Fee")

    def test_priority_change_recalcs_unpaid_appointment(self, client, auth_headers, doctor_fees, patient_uuid):
        apt = _book(client, auth_headers, patient_uuid, doctor_fees["doctor_user_id"])
        assert apt["consultation_fee"] == 500.0
        res = client.put(f"/api/appointments/{apt['id']}", headers=auth_headers, json={"priority": "emergency"})
        assert res.status_code == 200
        assert res.json()["consultation_fee"] == 1000.0
        assert res.json()["final_amount"] == 1000.0

    def test_priority_change_keeps_paid_bill_untouched(self, client, auth_headers, doctor_fees, patient_uuid):
        apt = _book(client, auth_headers, patient_uuid, doctor_fees["doctor_user_id"], payment_status="paid")
        res = client.put(f"/api/appointments/{apt['id']}", headers=auth_headers, json={"priority": "emergency"})
        assert res.status_code == 200
        assert res.json()["consultation_fee"] == 500.0
