"""Tests for credit note issuance endpoints."""
from datetime import datetime


def _create_bill(db_session, seed_data, total=1000.0, status="pending"):
    from app.models.billing import Bill
    bill = Bill(
        bill_number=f"BILL-{datetime.now().timestamp()}",
        patient_id=seed_data["patient_id"],
        bill_type="consultation",
        reference_id=0,
        subtotal=total,
        tax_amount=0,
        discount_amount=0,
        total_amount=total,
        status=status,
        bill_date=datetime.now(),
        created_by_id=seed_data["admin_user_id"],
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(bill)
    db_session.commit()
    db_session.refresh(bill)
    return bill


class TestCreditNotes:

    def test_issue_credit_note_creates_negative_bill_and_payment(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, total=1000)
        r = client.post(
            f"/api/hospital/billing/bills/{bill.id}/credit-note",
            json={
                "items": [{"item_name": "Consult fee adjustment", "quantity": 1, "unit_price": 200}],
                "reason": "billing error",
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["amount"] == 200.0
        assert body["parent_bill_id"] == bill.id
        assert body["parent_balance_due"] == 800.0
        assert body["parent_bill_status"] == "partial"

    def test_full_credit_note_flips_bill_to_paid(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, total=500)
        r = client.post(
            f"/api/hospital/billing/bills/{bill.id}/credit-note",
            json={"items": [{"item_name": "Full waiver", "quantity": 1, "unit_price": 500}],
                  "reason": "goodwill waiver"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["parent_bill_status"] == "paid"
        assert r.json()["parent_balance_due"] == 0.0

    def test_overshoot_credit_note_rejected(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, total=300)
        r = client.post(
            f"/api/hospital/billing/bills/{bill.id}/credit-note",
            json={"items": [{"item_name": "Too much", "quantity": 1, "unit_price": 400}],
                  "reason": "oops"},
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_multiple_credit_notes_accumulate(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, total=1000)
        client.post(f"/api/hospital/billing/bills/{bill.id}/credit-note",
                    json={"items": [{"item_name": "first", "quantity": 1, "unit_price": 300}], "reason": "first"},
                    headers=auth_headers)
        r2 = client.post(f"/api/hospital/billing/bills/{bill.id}/credit-note",
                         json={"items": [{"item_name": "second", "quantity": 1, "unit_price": 400}], "reason": "more"},
                         headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["parent_balance_due"] == 300.0

    def test_cannot_credit_note_a_credit_note(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, total=500)
        r = client.post(f"/api/hospital/billing/bills/{bill.id}/credit-note",
                        json={"items": [{"item_name": "x", "quantity": 1, "unit_price": 100}], "reason": "first"},
                        headers=auth_headers)
        cn_id = r.json()["credit_note_id"]
        r2 = client.post(f"/api/hospital/billing/bills/{cn_id}/credit-note",
                         json={"items": [{"item_name": "x", "quantity": 1, "unit_price": 10}], "reason": "nope"},
                         headers=auth_headers)
        assert r2.status_code == 400

    def test_cannot_credit_note_cancelled_bill(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, total=500, status="cancelled")
        r = client.post(f"/api/hospital/billing/bills/{bill.id}/credit-note",
                        json={"items": [{"item_name": "x", "quantity": 1, "unit_price": 100}], "reason": "test"},
                        headers=auth_headers)
        assert r.status_code == 400

    def test_credit_note_pdf(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, total=500)
        r = client.post(f"/api/hospital/billing/bills/{bill.id}/credit-note",
                        json={"items": [{"item_name": "y", "quantity": 1, "unit_price": 100}], "reason": "pdf test"},
                        headers=auth_headers)
        cn_id = r.json()["credit_note_id"]
        pdf = client.get(f"/api/hospital/billing/bills/{cn_id}/credit-note/pdf", headers=auth_headers)
        assert pdf.status_code == 200
        assert pdf.content[:4] == b"%PDF"
