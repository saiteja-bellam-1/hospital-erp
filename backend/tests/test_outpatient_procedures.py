"""Tests for the outpatient procedures catalog + bill builder."""
from datetime import datetime


def _create_proc(client, headers, name="X-ray Chest", price=350.0, code="XR-001"):
    return client.post("/api/outpatient/procedures",
        json={"name": name, "code": code, "default_price": price, "category": "Imaging"},
        headers=headers)


class TestProcedureCatalog:

    def test_admin_can_create_and_list_procedure(self, client, auth_headers):
        r = _create_proc(client, auth_headers, name="Dental Cleaning", price=500, code="DC-001")
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "Dental Cleaning"
        assert body["default_price"] == 500.0

        listed = client.get("/api/outpatient/procedures", headers=auth_headers).json()
        assert any(p["name"] == "Dental Cleaning" for p in listed)

    def test_non_admin_cannot_create_procedure(self, client, db_session, seed_data):
        from app.utils.auth import create_access_token
        # doctor user from seed
        token = create_access_token(data={"sub": "testdoctor"})
        hdr = {"Authorization": f"Bearer {token}"}
        r = client.post("/api/outpatient/procedures",
            json={"name": "Y", "default_price": 100}, headers=hdr)
        assert r.status_code == 403

    def test_update_and_deactivate(self, client, auth_headers):
        c = _create_proc(client, auth_headers, name="IV Drip", price=200, code="IV-1")
        pid = c.json()["id"]
        u = client.patch(f"/api/outpatient/procedures/{pid}",
            json={"name": "IV Drip Plus", "default_price": 250, "is_active": True},
            headers=auth_headers)
        assert u.status_code == 200 and u.json()["name"] == "IV Drip Plus"

        d = client.delete(f"/api/outpatient/procedures/{pid}", headers=auth_headers)
        assert d.status_code == 204
        # Listing without include_inactive hides it
        names = [p["name"] for p in client.get("/api/outpatient/procedures", headers=auth_headers).json()]
        assert "IV Drip Plus" not in names
        names_all = [p["name"] for p in client.get(
            "/api/outpatient/procedures?include_inactive=true", headers=auth_headers).json()]
        assert "IV Drip Plus" in names_all


class TestProcedureBills:

    def test_create_bill_from_catalog(self, client, auth_headers, seed_data):
        c = _create_proc(client, auth_headers, name="Nebulisation", price=400)
        pid = c.json()["id"]
        r = client.post("/api/outpatient/procedure-bills",
            json={
                "patient_id": seed_data["patient_id"],
                "items": [{"procedure_id": pid, "quantity": 2}],
            }, headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["subtotal"] == 800.0
        assert body["total_amount"] == 800.0
        assert body["bill_number"].startswith("PROC-")

    def test_create_bill_with_freeform_line(self, client, auth_headers, seed_data):
        r = client.post("/api/outpatient/procedure-bills",
            json={
                "patient_id": seed_data["patient_id"],
                "items": [
                    {"item_name": "Custom service", "quantity": 1, "unit_price": 999.99},
                ],
            }, headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.json()["subtotal"] == 999.99

    def test_create_bill_with_discount_and_tax(self, client, auth_headers, seed_data):
        c = _create_proc(client, auth_headers, name="ECG", price=300)
        r = client.post("/api/outpatient/procedure-bills",
            json={
                "patient_id": seed_data["patient_id"],
                "items": [{"procedure_id": c.json()["id"], "quantity": 4}],
                "discount_amount": 200,
                "tax_percentage": 5,
            }, headers=auth_headers)
        body = r.json()
        # subtotal 1200, discount 200, taxable 1000, tax 5% = 50, total = 1200 - 200 + 50 = 1050
        assert body["subtotal"] == 1200.0
        assert body["discount_amount"] == 200.0
        assert body["tax_amount"] == 50.0
        assert body["total_amount"] == 1050.0

    def test_zero_total_rejected(self, client, auth_headers, seed_data):
        r = client.post("/api/outpatient/procedure-bills",
            json={
                "patient_id": seed_data["patient_id"],
                "items": [{"item_name": "Free service", "quantity": 1, "unit_price": 0}],
            }, headers=auth_headers)
        assert r.status_code == 400

    def test_freeform_requires_name_and_price(self, client, auth_headers, seed_data):
        r = client.post("/api/outpatient/procedure-bills",
            json={
                "patient_id": seed_data["patient_id"],
                "items": [{"quantity": 1}],
            }, headers=auth_headers)
        assert r.status_code == 400

    def test_recent_bills_listing(self, client, auth_headers, seed_data):
        c = _create_proc(client, auth_headers, name="Suture", price=150)
        client.post("/api/outpatient/procedure-bills",
            json={"patient_id": seed_data["patient_id"],
                  "items": [{"procedure_id": c.json()["id"], "quantity": 1}]},
            headers=auth_headers)
        r = client.get("/api/outpatient/procedure-bills", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) >= 1
        assert all("bill_number" in row and "patient_name" in row for row in r.json())

    def test_procedure_bill_is_paid_by_default(self, client, auth_headers, db_session, seed_data):
        c = _create_proc(client, auth_headers, name="Vaccination", price=750)
        r = client.post("/api/outpatient/procedure-bills",
            json={"patient_id": seed_data["patient_id"],
                  "items": [{"procedure_id": c.json()["id"], "quantity": 1}],
                  "payment_method": "upi"},
            headers=auth_headers)
        bill_id = r.json()["bill_id"]
        # Bill row + payment row should reflect a settled receipt
        from app.models.billing import Bill, Payment
        bill = db_session.query(Bill).filter(Bill.id == bill_id).first()
        assert bill.status == "paid"
        payments = db_session.query(Payment).filter(Payment.bill_id == bill_id).all()
        assert len(payments) == 1
        assert payments[0].amount_paid == 750.0
        assert payments[0].payment_method_name == "upi"

    def test_procedure_bill_surfaces_in_central_billing(self, client, auth_headers, seed_data):
        c = _create_proc(client, auth_headers, name="X-ray Knee", price=600)
        client.post("/api/outpatient/procedure-bills",
            json={"patient_id": seed_data["patient_id"],
                  "items": [{"procedure_id": c.json()["id"], "quantity": 1}]},
            headers=auth_headers)
        # Central /api/hospital/billing should now include procedure bills
        from datetime import date as _date
        today = _date.today().isoformat()
        r = client.get(f"/api/hospital/billing?date_from={today}&date_to={today}", headers=auth_headers)
        assert r.status_code == 200
        types = {b["type"] for b in r.json()["bills"]}
        assert "day_care" in types
