"""Pharmacy sales in the central billing ledger."""
from datetime import date, datetime


def _sale(db_session, seed_data, **overrides):
    from app.models.pharmacy import PharmacySale

    values = {
        "sale_number": f"SALE-TEST-{datetime.now().timestamp()}",
        "sale_date": datetime.now(),
        "payment_type": "cash",
        "patient_name": "Pharmacy Patient",
        "patient_phone": "9000000000",
        "subtotal": 250.0,
        "discount_total": 25.0,
        "tax_total": 0.0,
        "grand_total": 225.0,
        "status": "completed",
        "billing_mode": "cash_at_pharmacy",
        "hospital_id": seed_data["hospital_id"],
    }
    values.update(overrides)
    sale = PharmacySale(**values)
    db_session.add(sale)
    db_session.commit()
    return sale


class TestBillingPharmacy:
    def test_lists_counter_sale_and_updates_summary(
        self, client, auth_headers, db_session, seed_data
    ):
        sale = _sale(db_session, seed_data)
        today = date.today().isoformat()

        response = client.get(
            f"/api/hospital/billing?date_from={today}&date_to={today}&bill_type=pharmacy",
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        data = response.json()
        row = next(b for b in data["bills"] if b["id"] == f"PHARM-{sale.id}")
        assert row["reference"] == sale.sale_number
        assert row["type"] == "pharmacy"
        assert row["payment_status"] == "paid"
        assert row["amount"] == 225.0
        assert row["discount"] == 25.0
        assert data["summary"]["pharmacy_count"] == 1
        assert data["summary"]["total_paid"] == 225.0

    def test_excludes_sales_deferred_to_inpatient_bill(
        self, client, auth_headers, db_session, seed_data
    ):
        sale = _sale(
            db_session,
            seed_data,
            sale_number=f"SALE-IP-{datetime.now().timestamp()}",
            billing_mode="inpatient_bill",
        )
        today = date.today().isoformat()

        response = client.get(
            f"/api/hospital/billing?date_from={today}&date_to={today}&bill_type=pharmacy",
            headers=auth_headers,
        )

        assert response.status_code == 200, response.text
        assert all(b["id"] != f"PHARM-{sale.id}" for b in response.json()["bills"])
