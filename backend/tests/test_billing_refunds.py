"""Tests for payment refund / reversal endpoints."""
from datetime import datetime


def _create_paid_bill(db_session, seed_data, total=1000.0, paid=1000.0):
    """Create a Bill with a single Payment of `paid` against it."""
    from app.models.billing import Bill, Payment
    bill = Bill(
        bill_number=f"BILL-{datetime.now().timestamp()}",
        patient_id=seed_data["patient_id"],
        bill_type="consultation",
        reference_id=0,
        subtotal=total,
        tax_amount=0,
        discount_amount=0,
        total_amount=total,
        status="paid" if paid >= total else ("partial" if paid > 0 else "pending"),
        bill_date=datetime.now(),
        created_by_id=seed_data["admin_user_id"],
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(bill)
    db_session.flush()
    pay = Payment(
        payment_number=f"PAY-{datetime.now().timestamp()}",
        bill_id=bill.id,
        amount_paid=paid,
        payment_method_name="cash",
        payment_date=datetime.now(),
        received_by_id=seed_data["admin_user_id"],
    )
    db_session.add(pay)
    db_session.commit()
    db_session.refresh(bill)
    db_session.refresh(pay)
    return bill, pay


class TestRefunds:

    def test_full_refund_flips_bill_to_pending(self, client, auth_headers, db_session, seed_data):
        bill, pay = _create_paid_bill(db_session, seed_data, total=1000, paid=1000)
        r = client.post(
            f"/api/hospital/billing/payments/{pay.id}/refund",
            json={"reason": "patient cancelled"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["amount_refunded"] == 1000.0
        assert body["bill_status"] == "pending"
        assert body["fully_reversed"] is True

    def test_partial_refund_keeps_bill_partial(self, client, auth_headers, db_session, seed_data):
        bill, pay = _create_paid_bill(db_session, seed_data, total=1000, paid=1000)
        r = client.post(
            f"/api/hospital/billing/payments/{pay.id}/refund",
            json={"amount": 400, "reason": "partial goodwill"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["amount_refunded"] == 400.0
        assert body["bill_status"] == "partial"
        assert body["net_paid"] == 600.0
        assert body["fully_reversed"] is False

    def test_cannot_overshoot_refund(self, client, auth_headers, db_session, seed_data):
        bill, pay = _create_paid_bill(db_session, seed_data, total=500, paid=500)
        r = client.post(
            f"/api/hospital/billing/payments/{pay.id}/refund",
            json={"amount": 600, "reason": "oops"},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_cannot_refund_twice_when_fully_refunded(self, client, auth_headers, db_session, seed_data):
        bill, pay = _create_paid_bill(db_session, seed_data, total=500, paid=500)
        r1 = client.post(
            f"/api/hospital/billing/payments/{pay.id}/refund",
            json={"reason": "first"},
            headers=auth_headers,
        )
        assert r1.status_code == 200
        r2 = client.post(
            f"/api/hospital/billing/payments/{pay.id}/refund",
            json={"reason": "second"},
            headers=auth_headers,
        )
        assert r2.status_code == 400

    def test_cannot_refund_a_refund_row(self, client, auth_headers, db_session, seed_data):
        bill, pay = _create_paid_bill(db_session, seed_data, total=500, paid=500)
        r = client.post(
            f"/api/hospital/billing/payments/{pay.id}/refund",
            json={"reason": "first"},
            headers=auth_headers,
        )
        refund_id = r.json()["refund_id"]
        r2 = client.post(
            f"/api/hospital/billing/payments/{refund_id}/refund",
            json={"reason": "no"},
            headers=auth_headers,
        )
        assert r2.status_code == 400

    def test_split_refund_two_partials_then_full(self, client, auth_headers, db_session, seed_data):
        bill, pay = _create_paid_bill(db_session, seed_data, total=1000, paid=1000)
        r1 = client.post(f"/api/hospital/billing/payments/{pay.id}/refund",
                         json={"amount": 300, "reason": "first"}, headers=auth_headers)
        r2 = client.post(f"/api/hospital/billing/payments/{pay.id}/refund",
                         json={"amount": 700, "reason": "rest"}, headers=auth_headers)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r2.json()["bill_status"] == "pending"
        assert r2.json()["fully_reversed"] is True

    def test_refund_receipt_pdf(self, client, auth_headers, db_session, seed_data):
        bill, pay = _create_paid_bill(db_session, seed_data, total=200, paid=200)
        r = client.post(f"/api/hospital/billing/payments/{pay.id}/refund",
                        json={"reason": "test pdf"}, headers=auth_headers)
        refund_id = r.json()["refund_id"]
        pdf = client.get(f"/api/hospital/billing/payments/{refund_id}/refund-receipt/pdf",
                         headers=auth_headers)
        assert pdf.status_code == 200
        assert pdf.content[:4] == b"%PDF"

    def test_bill_detail_marks_refund_rows(self, client, auth_headers, db_session, seed_data):
        bill, pay = _create_paid_bill(db_session, seed_data, total=400, paid=400)
        client.post(f"/api/hospital/billing/payments/{pay.id}/refund",
                    json={"amount": 100, "reason": "partial"}, headers=auth_headers)
        detail = client.get(f"/api/hospital/billing/bills/{bill.id}", headers=auth_headers)
        body = detail.json()
        kinds = [p["is_refund"] for p in body["payments"]]
        assert True in kinds and False in kinds
