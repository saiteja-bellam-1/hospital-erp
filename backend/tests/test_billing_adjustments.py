"""Tests for billing discount/tax adjustment endpoints."""
import pytest


def _create_bill(db_session, seed_data, subtotal=1000.0):
    """Create a minimal Bill row directly so the test focuses on adjustment logic."""
    from app.models.billing import Bill
    from datetime import datetime
    bill = Bill(
        bill_number=f"TEST-{datetime.now().timestamp()}",
        patient_id=seed_data["patient_id"],
        bill_type="consultation",
        reference_id=0,
        subtotal=subtotal,
        tax_amount=0,
        discount_amount=0,
        total_amount=subtotal,
        status="pending",
        bill_date=datetime.now(),
        created_by_id=seed_data["admin_user_id"],
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(bill)
    db_session.commit()
    db_session.refresh(bill)
    return bill


class TestBillingAdjustments:

    def test_apply_percentage_discount(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, subtotal=1000.0)
        r = client.patch(
            f"/api/hospital/billing/bills/{bill.id}/discount",
            json={"discount_percentage": 10, "reason": "loyalty"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["discount_amount"] == 100.0
        assert body["total_amount"] == 900.0

    def test_apply_flat_discount(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, subtotal=2000.0)
        r = client.patch(
            f"/api/hospital/billing/bills/{bill.id}/discount",
            json={"discount_amount": 250, "reason": "goodwill"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["total_amount"] == 1750.0

    def test_apply_tax_after_discount(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, subtotal=1000.0)
        client.patch(
            f"/api/hospital/billing/bills/{bill.id}/discount",
            json={"discount_percentage": 10, "reason": "test"},
            headers=auth_headers,
        )
        r = client.patch(
            f"/api/hospital/billing/bills/{bill.id}/tax",
            json={"tax_percentage": 18, "reason": "gst"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # 1000 - 100 = 900, tax 18% = 162, total = 1000 + 162 - 100 = 1062
        assert body["tax_amount"] == 162.0
        assert body["total_amount"] == 1062.0

    def test_discount_exceeding_subtotal_rejected(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, subtotal=500.0)
        r = client.patch(
            f"/api/hospital/billing/bills/{bill.id}/discount",
            json={"discount_amount": 600, "reason": "test"},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_discount_requires_amount_or_percent(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, subtotal=500.0)
        r = client.patch(
            f"/api/hospital/billing/bills/{bill.id}/discount",
            json={"reason": "test"},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_cannot_modify_cancelled_bill(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, subtotal=500.0)
        bill.status = "cancelled"
        db_session.commit()
        r = client.patch(
            f"/api/hospital/billing/bills/{bill.id}/discount",
            json={"discount_amount": 50, "reason": "test"},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_cannot_modify_bill_with_payments(self, client, auth_headers, db_session, seed_data):
        from app.models.billing import Payment
        from datetime import datetime
        bill = _create_bill(db_session, seed_data, subtotal=500.0)
        pay = Payment(
            payment_number=f"P-{datetime.now().timestamp()}",
            bill_id=bill.id,
            amount_paid=100,
            payment_method_name="cash",
            received_by_id=seed_data["admin_user_id"],
        )
        db_session.add(pay)
        bill.status = "partial"
        db_session.commit()
        r = client.patch(
            f"/api/hospital/billing/bills/{bill.id}/tax",
            json={"tax_percentage": 5, "reason": "test"},
            headers=auth_headers,
        )
        assert r.status_code == 400
        assert "payments" in r.json()["detail"].lower()
