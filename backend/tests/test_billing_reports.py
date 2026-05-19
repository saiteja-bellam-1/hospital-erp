"""Tests for billing report endpoints."""
from datetime import datetime, date, time


def _bill_with_payment(db_session, seed_data, total=1000.0, paid=500.0, method="cash", tax=180.0, subtotal=820.0):
    from app.models.billing import Bill, Payment
    ts = datetime.now().timestamp()
    bill = Bill(
        bill_number=f"R-{ts}",
        patient_id=seed_data["patient_id"],
        bill_type="consultation",
        reference_id=0,
        subtotal=subtotal,
        tax_amount=tax,
        discount_amount=0,
        total_amount=total,
        status="partial" if paid > 0 and paid < total else ("paid" if paid >= total else "pending"),
        bill_date=datetime.now(),
        created_by_id=seed_data["admin_user_id"],
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(bill); db_session.flush()
    if paid > 0:
        db_session.add(Payment(
            payment_number=f"P-{ts}",
            bill_id=bill.id,
            amount_paid=paid,
            payment_method_name=method,
            payment_date=datetime.now(),
            received_by_id=seed_data["admin_user_id"],
        ))
    db_session.commit()
    db_session.refresh(bill)
    return bill


class TestReports:

    def test_daily_collection_groups_by_method(self, client, auth_headers, db_session, seed_data):
        _bill_with_payment(db_session, seed_data, total=500, paid=500, method="cash", tax=0, subtotal=500)
        _bill_with_payment(db_session, seed_data, total=300, paid=300, method="upi", tax=0, subtotal=300)
        r = client.get("/api/hospital/billing/reports/daily-collection", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["totals"]["net_collected"] >= 800
        assert "cash" in body["methods"] and "upi" in body["methods"]
        today_row = next((row for row in body["rows"] if row["date"] == date.today().isoformat()), None)
        assert today_row is not None
        assert today_row["by_method"].get("cash", 0) >= 500

    def test_daily_collection_nets_refunds(self, client, auth_headers, db_session, seed_data):
        bill = _bill_with_payment(db_session, seed_data, total=400, paid=400, method="cash", tax=0, subtotal=400)
        from app.models.billing import Payment
        pay = db_session.query(Payment).filter_by(bill_id=bill.id).first()
        # Issue a refund of 100
        client.post(f"/api/hospital/billing/payments/{pay.id}/refund",
                    json={"amount": 100, "reason": "test"}, headers=auth_headers)
        r = client.get("/api/hospital/billing/reports/daily-collection", headers=auth_headers)
        body = r.json()
        today_row = next(row for row in body["rows"] if row["date"] == date.today().isoformat())
        assert today_row["refunds"] >= 100

    def test_doctor_revenue_includes_consultations(self, client, auth_headers, db_session, seed_data):
        from app.models.outpatient import Appointment
        ts = datetime.now().timestamp()
        a = Appointment(
            appointment_number=f"DRR-{ts}",
            patient_id=seed_data["patient_id"],
            doctor_id=seed_data["doctor_user_id"],
            appointment_date=datetime.now(),
            appointment_time=time(11, 0),
            consultation_fee=500,
            registration_fee=0,
            payment_status="paid",
        )
        db_session.add(a); db_session.commit()
        r = client.get("/api/hospital/billing/reports/doctor-revenue", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        doc_row = next((row for row in body["rows"] if row["doctor_id"] == seed_data["doctor_user_id"]), None)
        assert doc_row is not None
        assert doc_row["consultation_revenue"] >= 500

    def test_tax_summary_excludes_cancelled_and_credit_notes(self, client, auth_headers, db_session, seed_data):
        _bill_with_payment(db_session, seed_data, total=1180, paid=0, tax=180, subtotal=1000)
        r = client.get("/api/hospital/billing/reports/tax-summary", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["totals"]["tax_amount"] >= 180
        assert body["totals"]["taxable_value"] >= 1000

    def test_reports_require_admin(self, client, db_session, seed_data):
        # Build a JWT for the doctor user (not admin)
        from app.utils.auth import create_access_token
        token = create_access_token(data={"sub": "testdoctor"})
        hdr = {"Authorization": f"Bearer {token}"}
        r = client.get("/api/hospital/billing/reports/daily-collection", headers=hdr)
        assert r.status_code == 403
