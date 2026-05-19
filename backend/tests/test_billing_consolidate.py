"""Tests for consolidated billing endpoints."""
from datetime import datetime


def _make_appt(db_session, seed_data, fee=300.0, reg=100.0):
    from app.models.outpatient import Appointment
    from datetime import time
    ts = datetime.now().timestamp()
    a = Appointment(
        appointment_number=f"APT-{ts}",
        patient_id=seed_data["patient_id"],
        doctor_id=seed_data["doctor_user_id"],
        appointment_date=datetime.now(),
        appointment_time=time(10, 0),
        consultation_fee=fee,
        registration_fee=reg,
        payment_status="pending",
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def _make_lab(db_session, seed_data, cost=500.0):
    from app.models.lab import LabTest, PatientLabOrder, LabTestCategory
    cat = db_session.query(LabTestCategory).first()
    if not cat:
        cat = LabTestCategory(name="Hematology", hospital_id=seed_data["hospital_id"])
        db_session.add(cat); db_session.commit(); db_session.refresh(cat)
    ts = datetime.now().timestamp()
    test = LabTest(
        name=f"CBC-{ts}", test_code=f"CBC{int(ts*1000)}",
        category_id=cat.id, cost=cost,
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(test); db_session.commit(); db_session.refresh(test)
    order = PatientLabOrder(
        order_number=f"LO-{ts}",
        patient_id=seed_data["patient_id"],
        test_id=test.id,
        payment_status="pending",
        status="pending",
        doctor_id=seed_data["doctor_user_id"],
    )
    db_session.add(order); db_session.commit(); db_session.refresh(order)
    return order


class TestConsolidate:

    def test_preview_lists_pending_items(self, client, auth_headers, db_session, seed_data):
        a = _make_appt(db_session, seed_data, fee=300, reg=50)
        o = _make_lab(db_session, seed_data, cost=400)
        r = client.get(f"/api/hospital/billing/consolidate/preview?patient_id={seed_data['patient_id']}",
                       headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        consult_ids = [c["id"] for c in body["consultations"]]
        lab_ids = [l["id"] for l in body["lab_orders"]]
        assert a.id in consult_ids
        assert o.id in lab_ids
        assert body["totals"]["grand"] >= 350 + 400

    def test_create_consolidates_selected(self, client, auth_headers, db_session, seed_data):
        a = _make_appt(db_session, seed_data, fee=200, reg=0)
        o = _make_lab(db_session, seed_data, cost=300)
        r = client.post("/api/hospital/billing/consolidate",
                        json={
                            "patient_id": seed_data["patient_id"],
                            "consultation_ids": [a.id],
                            "lab_order_ids": [o.id],
                        }, headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_amount"] == 500.0
        assert body["consultations_count"] == 1 and body["lab_orders_count"] == 1

        # Source items marked consolidated and excluded from next preview
        db_session.expire_all()
        from app.models.outpatient import Appointment
        from app.models.lab import PatientLabOrder
        a2 = db_session.query(Appointment).filter_by(id=a.id).first()
        o2 = db_session.query(PatientLabOrder).filter_by(id=o.id).first()
        assert a2.payment_status == "consolidated"
        assert o2.payment_status == "consolidated"

        # Bill detail returns 2 items
        detail = client.get(f"/api/hospital/billing/bills/{body['bill_id']}", headers=auth_headers)
        assert detail.status_code == 200
        assert len(detail.json()["items"]) == 2

    def test_empty_selection_rejected(self, client, auth_headers, db_session, seed_data):
        r = client.post("/api/hospital/billing/consolidate",
                        json={"patient_id": seed_data["patient_id"],
                              "consultation_ids": [], "lab_order_ids": []},
                        headers=auth_headers)
        assert r.status_code == 400

    def test_consolidated_bill_shows_in_billing_list(self, client, auth_headers, db_session, seed_data):
        a = _make_appt(db_session, seed_data, fee=150, reg=0)
        r = client.post("/api/hospital/billing/consolidate",
                        json={"patient_id": seed_data["patient_id"],
                              "consultation_ids": [a.id], "lab_order_ids": []},
                        headers=auth_headers)
        assert r.status_code == 200

    def test_already_consolidated_item_skipped_silently(self, client, auth_headers, db_session, seed_data):
        a = _make_appt(db_session, seed_data, fee=200, reg=0)
        client.post("/api/hospital/billing/consolidate",
                    json={"patient_id": seed_data["patient_id"],
                          "consultation_ids": [a.id], "lab_order_ids": []},
                    headers=auth_headers)
        # Second attempt — only the already-consolidated row, no zero-amount Bill should be created
        r2 = client.post("/api/hospital/billing/consolidate",
                         json={"patient_id": seed_data["patient_id"],
                               "consultation_ids": [a.id], "lab_order_ids": []},
                         headers=auth_headers)
        assert r2.status_code == 400  # zero billable
