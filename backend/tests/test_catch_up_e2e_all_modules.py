"""End-to-end catch-up bill generation across remaining modules + edge cases.

Covers: pharmacy, misc, inpatient stay, append-charges, date/permission
edges, and dual Service/Payment date wiring.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.billing import Bill, BillItem, Payment
from app.models.inpatient import Admission
from app.models.pharmacy import (
    Medicine,
    MedicineCategory,
    PharmacyHSN,
    PharmacyInventory,
    PharmacySale,
    PharmacySupplier,
)


def _dates(svc_offset=5, pay_offset=2):
    svc = (date.today() - timedelta(days=svc_offset)).isoformat()
    pay = (date.today() - timedelta(days=pay_offset)).isoformat()
    return svc, pay


def _assert_paid_bill(db, bill_id, *, bill_type, service_date, payment_id, expected_total=None):
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    assert bill is not None
    assert bill.bill_type == bill_type
    assert bill.status == "paid"
    assert bill.bill_date.date().isoformat() == service_date
    items = db.query(BillItem).filter(BillItem.bill_id == bill_id).all()
    assert len(items) >= 1
    if expected_total is not None:
        assert float(bill.total_amount) == pytest.approx(float(expected_total))
        assert sum(float(i.total_price or 0) for i in items) == pytest.approx(float(expected_total))
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    assert payment is not None
    assert float(payment.amount_paid) == pytest.approx(float(bill.total_amount or 0))
    return bill, items, payment


class TestCatchUpAllModulesBillGeneration:
    """Happy-path bill generation for every catch-up module type."""

    def test_pharmacy_financial_only_generates_bill(
        self, client, auth_headers, seed_data, db_session
    ):
        svc, pay = _dates(4, 1)
        res = client.post(
            "/api/admin/catch-up/pharmacy-sale",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": pay,
                "affect_stock": False,
                "items": [
                    {"item_name": "Tab. Aspirin", "quantity": 10, "unit_price": 2.5},
                    {"item_name": "Syrup Cough", "quantity": 1, "unit_price": 85},
                ],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] == 110.0
        assert body["sale_id"] is None  # financial-only: no PharmacySale
        bill, items, payment = _assert_paid_bill(
            db_session, body["bill_id"],
            bill_type="pharmacy", service_date=svc,
            payment_id=body["payment_id"], expected_total=110.0,
        )
        assert payment.payment_date.date().isoformat() == pay
        assert len(items) == 2



    def test_misc_multi_line_bill(self, client, auth_headers, seed_data, db_session):
        svc, pay = _dates(9, 1)
        res = client.post(
            "/api/admin/catch-up/misc-bill",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": pay,
                "payment_method": "upi",
                "items": [
                    {"item_name": "Dressing", "quantity": 2, "unit_price": 100},
                    {"item_name": "Certificate", "quantity": 1, "unit_price": 50},
                ],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] == 250.0
        bill, items, payment = _assert_paid_bill(
            db_session, body["bill_id"],
            bill_type="catch_up", service_date=svc,
            payment_id=body["payment_id"], expected_total=250.0,
        )
        assert payment.payment_method_name == "upi"
        assert payment.payment_date.date().isoformat() == pay
        assert len(items) == 2

    def test_inpatient_stay_with_food_on_bill(
        self, client, auth_headers, seed_data, db_session
    ):
        room = client.post(
            "/api/inpatient/rooms",
            headers=auth_headers,
            json={
                "room_number": f"CU-E2E-{uuid.uuid4().hex[:4]}",
                "room_type": "general",
                "floor": "1",
                "department": "General Ward",
                "bed_count": 2,
                "room_charge_per_day": 1000.0,
            },
        )
        assert room.status_code == 201, room.text
        room_id = room.json()["id"]

        admit = datetime(2026, 4, 1, 10, 0, 0)
        disc = datetime(2026, 4, 4, 10, 0, 0)  # 3 days
        svc, pay = "2026-04-04", "2026-04-04"
        res = client.post(
            "/api/admin/catch-up/inpatient-stay",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room_id,
                "admission_date": admit.isoformat(),
                "discharge_date": disc.isoformat(),
                "service_date": svc,
                "payment_date": pay,
                "visits": [{
                    "visit_type": "doctor_visit",
                    "visitor_id": seed_data["doctor_user_id"],
                    "visit_datetime": (admit + timedelta(days=1)).isoformat(),
                    "charge_amount": 400,
                }],
                "pharmacy_lines": [
                    {"item_name": "Inj. NS", "quantity": 1, "unit_price": 50},
                ],
                "deposits": [],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        # 3d room 3000 + visit 400 + pharm 50 = 3450
        assert body["total"] == pytest.approx(3450.0)
        assert body["is_catch_up"] is True

        bill = db_session.query(Bill).filter(Bill.id == body["bill_id"]).first()
        assert bill.status == "paid"
        assert bill.bill_date.date().isoformat() == svc
        items = db_session.query(BillItem).filter(BillItem.bill_id == body["bill_id"]).all()
        payment = db_session.query(Payment).filter(Payment.id == body["payment_id"]).first()
        assert payment.payment_date.date().isoformat() == pay

        adm = db_session.query(Admission).filter(Admission.id == body["admission_id"]).first()
        assert adm.is_catch_up is True
        assert adm.status == "discharged"
        assert adm.bed_id is None


class TestCatchUpEdgeCases:
    def test_future_service_date_rejected(self, client, auth_headers, seed_data):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        today = date.today().isoformat()
        res = client.post(
            "/api/admin/catch-up/misc-bill",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": tomorrow,
                "payment_date": today,
                "items": [{"item_name": "X", "quantity": 1, "unit_price": 10}],
            },
        )
        assert res.status_code == 400

    def test_future_payment_date_rejected(self, client, auth_headers, seed_data):
        today = date.today().isoformat()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        res = client.post(
            "/api/admin/catch-up/misc-bill",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": today,
                "payment_date": tomorrow,
                "items": [{"item_name": "X", "quantity": 1, "unit_price": 10}],
            },
        )
        assert res.status_code == 400

    def test_lookback_over_365_rejected(self, client, auth_headers, seed_data):
        old = (date.today() - timedelta(days=400)).isoformat()
        today = date.today().isoformat()
        res = client.post(
            "/api/admin/catch-up/misc-bill",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": old,
                "payment_date": today,
                "items": [{"item_name": "X", "quantity": 1, "unit_price": 10}],
            },
        )
        assert res.status_code == 400

    def test_unknown_patient_404(self, client, auth_headers, seed_data):
        svc, pay = _dates()
        res = client.post(
            "/api/admin/catch-up/misc-bill",
            headers=auth_headers,
            json={
                "patient_id": 999999,
                "service_date": svc,
                "payment_date": pay,
                "items": [{"item_name": "X", "quantity": 1, "unit_price": 10}],
            },
        )
        assert res.status_code == 404



    def test_pharmacy_affect_stock_requires_batch(self, client, auth_headers, seed_data):
        svc, pay = _dates()
        res = client.post(
            "/api/admin/catch-up/pharmacy-sale",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": pay,
                "affect_stock": True,
                "items": [{
                    "item_name": "Med",
                    "quantity": 1,
                    "unit_price": 10,
                    # missing medicine_id / batch_id
                }],
            },
        )
        assert res.status_code == 400
        assert "affect_stock" in res.text.lower() or "batch" in res.text.lower()

    def test_pharmacy_financial_requires_patient(self, client, auth_headers, seed_data):
        svc, pay = _dates()
        res = client.post(
            "/api/admin/catch-up/pharmacy-sale",
            headers=auth_headers,
            json={
                "service_date": svc,
                "payment_date": pay,
                "affect_stock": False,
                "items": [{"item_name": "Med", "quantity": 1, "unit_price": 10}],
            },
        )
        assert res.status_code == 400
        assert "patient_id" in res.text.lower()

    def test_pharmacy_insufficient_stock(self, client, auth_headers, seed_data, db_session):
        hid = seed_data["hospital_id"]
        cat = MedicineCategory(name=f"E2E-{uuid.uuid4().hex[:6]}", hospital_id=hid)
        db_session.add(cat)
        db_session.flush()
        hsn = PharmacyHSN(code=f"H{uuid.uuid4().hex[:4]}", sgst_pct=6, cgst_pct=6, hospital_id=hid)
        db_session.add(hsn)
        db_session.flush()
        med = Medicine(
            medicine_code=f"M{uuid.uuid4().hex[:6]}",
            name=f"LowStock-{uuid.uuid4().hex[:4]}",
            unit_price=10.0,
            category_id=cat.id,
            hsn_id=hsn.id,
            hospital_id=hid,
        )
        db_session.add(med)
        db_session.flush()
        sup = PharmacySupplier(name=f"S-{uuid.uuid4().hex[:4]}", hospital_id=hid)
        db_session.add(sup)
        db_session.commit()

        purchase = client.post(
            "/api/pharmacy/purchases",
            headers=auth_headers,
            json={
                "entry_date": date.today().isoformat(),
                "supplier_id": sup.id,
                "invoice_number": f"E2E-{uuid.uuid4().hex[:6]}",
                "payment_type": "cash",
                "purchase_type": "local",
                "items": [{
                    "medicine_id": med.id,
                    "batch_number": f"B-{uuid.uuid4().hex[:5]}",
                    "mrp": 30.0,
                    "quantity": 2,
                    "free_quantity": 0,
                    "purchase_rate": 20.0,
                    "discount_pct": 0,
                    "hsn_id": hsn.id,
                    "expiry_date": "2030-12-31",
                }],
            },
        )
        assert purchase.status_code in (200, 201), purchase.text
        conf = client.post(
            f"/api/pharmacy/purchases/{purchase.json()['id']}/confirm",
            headers=auth_headers,
        )
        assert conf.status_code == 200, conf.text
        batch = (
            db_session.query(PharmacyInventory)
            .filter(PharmacyInventory.medicine_id == med.id)
            .first()
        )
        assert batch is not None

        svc, pay = _dates(1, 1)
        res = client.post(
            "/api/admin/catch-up/pharmacy-sale",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": pay,
                "affect_stock": True,
                "items": [{
                    "item_name": med.name,
                    "quantity": 99,
                    "unit_price": 25,
                    "medicine_id": med.id,
                    "batch_id": batch.id,
                }],
            },
        )
        assert res.status_code == 400
        assert "Insufficient stock" in res.text or "stock" in res.text.lower()

    def test_inpatient_discharge_before_admit_rejected(
        self, client, auth_headers, seed_data
    ):
        room = client.post(
            "/api/inpatient/rooms",
            headers=auth_headers,
            json={
                "room_number": f"CU-BAD-{uuid.uuid4().hex[:4]}",
                "room_type": "general",
                "floor": "1",
                "department": "General Ward",
                "bed_count": 1,
                "room_charge_per_day": 500.0,
            },
        )
        assert room.status_code == 201, room.text
        svc, pay = _dates()
        res = client.post(
            "/api/admin/catch-up/inpatient-stay",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room.json()["id"],
                "admission_date": "2026-05-10T10:00:00",
                "discharge_date": "2026-05-08T10:00:00",
                "service_date": svc,
                "payment_date": pay,
                "visits": [],
                                "deposits": [],
            },
        )
        assert res.status_code == 400

    def test_inpatient_observation_skips_room_rent(
        self, client, auth_headers, seed_data, db_session
    ):
        room = client.post(
            "/api/inpatient/rooms",
            headers=auth_headers,
            json={
                "room_number": f"CU-OBS-{uuid.uuid4().hex[:4]}",
                "room_type": "general",
                "floor": "1",
                "department": "General Ward",
                "bed_count": 1,
                "room_charge_per_day": 2000.0,
            },
        )
        assert room.status_code == 201, room.text
        admit = datetime(2026, 3, 1, 8, 0, 0)
        disc = datetime(2026, 3, 2, 8, 0, 0)
        svc, pay = "2026-03-02", "2026-03-02"
        res = client.post(
            "/api/admin/catch-up/inpatient-stay",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room.json()["id"],
                "admission_date": admit.isoformat(),
                "discharge_date": disc.isoformat(),
                "service_date": svc,
                "payment_date": pay,
                "is_observation": True,
                "visits": [{
                    "visit_type": "doctor_visit",
                    "visitor_id": seed_data["doctor_user_id"],
                    "visit_datetime": admit.isoformat(),
                    "charge_amount": 300,
                }],
                                "deposits": [],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        # Observation: no room rent, only visit 300
        assert body["total"] == pytest.approx(300.0)
        items = db_session.query(BillItem).filter(BillItem.bill_id == body["bill_id"]).all()
        assert not any(i.item_type == "room_charge" for i in items)

    def test_append_charges_requires_at_least_one_line(
        self, client, auth_headers, seed_data
    ):
        room = client.post(
            "/api/inpatient/rooms",
            headers=auth_headers,
            json={
                "room_number": f"CU-APP0-{uuid.uuid4().hex[:4]}",
                "room_type": "general",
                "floor": "1",
                "department": "General Ward",
                "bed_count": 1,
                "room_charge_per_day": 500.0,
            },
        )
        assert room.status_code == 201, room.text
        admit = datetime.now() - timedelta(days=5)
        disc = datetime.now() - timedelta(days=3)
        svc = disc.date().isoformat()
        create = client.post(
            "/api/admin/catch-up/inpatient-stay",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room.json()["id"],
                "admission_date": admit.isoformat(),
                "discharge_date": disc.isoformat(),
                "service_date": svc,
                "payment_date": svc,
                "visits": [],
                                "deposits": [],
            },
        )
        assert create.status_code == 200, create.text
        adm_id = create.json()["admission_id"]

        empty = client.post(
            f"/api/admin/catch-up/inpatient/{adm_id}/append-charges",
            headers=auth_headers,
            json={
                "service_date": date.today().isoformat(),
                "payment_date": date.today().isoformat(),
                "visits": [],
                "ancillary": [],
                "pharmacy_lines": [],
            },
        )
        assert empty.status_code == 400

    def test_append_rejects_non_catch_up_admission(
        self, client, auth_headers, seed_data, db_session
    ):
        # Create a normal (non catch-up) discharged admission via minimal room + stay
        # is harder; instead stamp a catch-up stay then clear the flag.
        room = client.post(
            "/api/inpatient/rooms",
            headers=auth_headers,
            json={
                "room_number": f"CU-NCU-{uuid.uuid4().hex[:4]}",
                "room_type": "general",
                "floor": "1",
                "department": "General Ward",
                "bed_count": 1,
                "room_charge_per_day": 400.0,
            },
        )
        assert room.status_code == 201, room.text
        admit = datetime.now() - timedelta(days=6)
        disc = datetime.now() - timedelta(days=4)
        svc = disc.date().isoformat()
        create = client.post(
            "/api/admin/catch-up/inpatient-stay",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room.json()["id"],
                "admission_date": admit.isoformat(),
                "discharge_date": disc.isoformat(),
                "service_date": svc,
                "payment_date": svc,
                "visits": [],
                                "deposits": [],
            },
        )
        assert create.status_code == 200, create.text
        adm_id = create.json()["admission_id"]
        adm = db_session.query(Admission).filter(Admission.id == adm_id).first()
        adm.is_catch_up = False
        db_session.commit()

        res = client.post(
            f"/api/admin/catch-up/inpatient/{adm_id}/append-charges",
            headers=auth_headers,
            json={
                "service_date": date.today().isoformat(),
                "payment_date": date.today().isoformat(),
                "pharmacy_lines": [
                    {"item_name": "Extra gauze", "quantity": 1, "unit_price": 20},
                ],
            },
        )
        assert res.status_code == 400
        assert "catch-up" in res.text.lower()

    def test_history_lists_catch_up_actions(self, client, auth_headers, seed_data):
        svc, pay = _dates(3, 3)
        client.post(
            "/api/admin/catch-up/misc-bill",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": pay,
                "items": [{"item_name": "Hist entry", "quantity": 1, "unit_price": 11}],
            },
        )
        res = client.get("/api/admin/catch-up/history", headers=auth_headers)
        assert res.status_code == 200, res.text
        rows = res.json()
        assert isinstance(rows, list)
        assert any(r.get("action", "").startswith("catch_up_") for r in rows)


    def test_reports_see_catch_up_by_dual_dates(
        self, client, auth_headers, seed_data, db_session
    ):
        svc = (date.today() - timedelta(days=12)).isoformat()
        pay = (date.today() - timedelta(days=3)).isoformat()
        res = client.post(
            "/api/admin/catch-up/misc-bill",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": pay,
                "payment_method": "cash",
                "items": [{"item_name": "E2E report line", "quantity": 1, "unit_price": 333}],
            },
        )
        assert res.status_code == 200, res.text
        total = res.json()["total"]

        coll = client.get(
            "/api/hospital/billing/reports/daily-collection",
            headers=auth_headers,
            params={"date_from": pay, "date_to": pay},
        )
        assert coll.status_code == 200
        row = next((r for r in coll.json()["rows"] if r["date"] == pay), None)
        assert row is not None
        assert row["by_method"].get("cash", 0) >= total

        tax = client.get(
            "/api/hospital/billing/reports/tax-summary",
            headers=auth_headers,
            params={"date_from": svc, "date_to": svc},
        )
        assert tax.status_code == 200
        trow = next((r for r in tax.json()["rows"] if r["date"] == svc), None)
        assert trow is not None
        assert trow["bill_count"] >= 1


class TestCatchUpPharmacyStockBill:
    def test_affect_stock_sale_and_bill(self, client, auth_headers, seed_data, db_session):
        hid = seed_data["hospital_id"]
        cat = MedicineCategory(name=f"E2ES-{uuid.uuid4().hex[:6]}", hospital_id=hid)
        db_session.add(cat)
        db_session.flush()
        hsn = PharmacyHSN(code=f"H{uuid.uuid4().hex[:4]}", sgst_pct=6, cgst_pct=6, hospital_id=hid)
        db_session.add(hsn)
        db_session.flush()
        med = Medicine(
            medicine_code=f"M{uuid.uuid4().hex[:6]}",
            name=f"StockMed-{uuid.uuid4().hex[:4]}",
            unit_price=10.0,
            category_id=cat.id,
            hsn_id=hsn.id,
            hospital_id=hid,
        )
        db_session.add(med)
        db_session.flush()
        sup = PharmacySupplier(name=f"SS-{uuid.uuid4().hex[:4]}", hospital_id=hid)
        db_session.add(sup)
        db_session.commit()

        purchase = client.post(
            "/api/pharmacy/purchases",
            headers=auth_headers,
            json={
                "entry_date": date.today().isoformat(),
                "supplier_id": sup.id,
                "invoice_number": f"STK-{uuid.uuid4().hex[:6]}",
                "payment_type": "cash",
                "purchase_type": "local",
                "items": [{
                    "medicine_id": med.id,
                    "batch_number": f"SB-{uuid.uuid4().hex[:5]}",
                    "mrp": 40.0,
                    "quantity": 15,
                    "free_quantity": 0,
                    "purchase_rate": 22.0,
                    "discount_pct": 0,
                    "hsn_id": hsn.id,
                    "expiry_date": "2031-06-30",
                }],
            },
        )
        assert purchase.status_code in (200, 201), purchase.text
        conf = client.post(
            f"/api/pharmacy/purchases/{purchase.json()['id']}/confirm",
            headers=auth_headers,
        )
        assert conf.status_code == 200, conf.text
        batch = (
            db_session.query(PharmacyInventory)
            .filter(PharmacyInventory.medicine_id == med.id)
            .first()
        )
        before = int(batch.quantity_in_stock or 0)

        svc, pay = _dates(1, 1)
        res = client.post(
            "/api/admin/catch-up/pharmacy-sale",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": pay,
                "affect_stock": True,
                "items": [{
                    "item_name": med.name,
                    "quantity": 5,
                    "unit_price": 30,
                    "medicine_id": med.id,
                    "batch_id": batch.id,
                }],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["sale_id"]
        assert body["total"] == 150.0
        _assert_paid_bill(
            db_session, body["bill_id"],
            bill_type="pharmacy", service_date=svc,
            payment_id=body["payment_id"], expected_total=150.0,
        )
        sale = db_session.query(PharmacySale).filter(PharmacySale.id == body["sale_id"]).first()
        assert sale is not None
        assert sale.status == "completed"
        db_session.refresh(batch)
        assert int(batch.quantity_in_stock or 0) == before - 5


class TestCatchUpBillPreviewAndPdf:
    """Dry-run previews for remaining modules + pdf path on create responses."""

    def test_pharmacy_misc_previews(self, client, auth_headers, seed_data):
        svc, pay = _dates(2, 1)

        ph = client.post(
            "/api/admin/catch-up/pharmacy-sale/preview",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": pay,
                "items": [{"item_name": "Tab X", "quantity": 2, "unit_price": 15}],
            },
        )
        assert ph.status_code == 200, ph.text
        assert ph.json()["grand_total"] == 30.0

        misc = client.post(
            "/api/admin/catch-up/misc-bill/preview",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": pay,
                "items": [{"item_name": "Dressing", "quantity": 1, "unit_price": 80}],
            },
        )
        assert misc.status_code == 200, misc.text
        assert misc.json()["grand_total"] == 80.0

        created = client.post(
            "/api/admin/catch-up/misc-bill",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": pay,
                "items": [{"item_name": "Dressing", "quantity": 1, "unit_price": 80}],
            },
        )
        assert created.status_code == 200, created.text
        assert created.json()["pdf"]["path"] == (
            f"/api/hospital/billing/bills/{created.json()['bill_id']}/pdf"
        )

    def test_inpatient_preview_includes_items(self, client, auth_headers, seed_data, db_session):
        room = client.post(
            "/api/inpatient/rooms",
            headers=auth_headers,
            json={
                "room_number": f"PV-{uuid.uuid4().hex[:4]}",
                "room_type": "general",
                "floor": "1",
                "department": "General Ward",
                "bed_count": 1,
                "room_charge_per_day": 1000.0,
            },
        )
        assert room.status_code == 201, room.text
        room_id = room.json()["id"]

        svc, pay = _dates(6, 5)
        admit = (datetime.now() - timedelta(days=6)).replace(hour=10, minute=0, second=0, microsecond=0)
        discharge = (datetime.now() - timedelta(days=5)).replace(hour=18, minute=0, second=0, microsecond=0)
        prev = client.post(
            "/api/admin/catch-up/inpatient-stay/preview",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room_id,
                "admission_date": admit.isoformat(),
                "discharge_date": discharge.isoformat(),
                "service_date": svc,
                "payment_date": pay,
                "is_observation": False,
                "visits": [],
                "ancillary": [],
                "pharmacy_lines": [{"item_name": "ORS", "quantity": 2, "unit_price": 25}],
            },
        )
        assert prev.status_code == 200, prev.text
        draft = prev.json()
        assert draft["grand_total"] > 0
        assert isinstance(draft["items"], list)
        assert len(draft["items"]) >= 1
        assert any("ORS" in (i.get("item_name") or "") for i in draft["items"])
