"""End-to-end catch-up bill generation across all modules + edge cases.

Covers: consultation, lab, pharmacy, canteen, misc, inpatient stay (with food),
append-charges, date/permission edges, and dual Service/Payment date wiring.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

import pytest

from app.models.billing import Bill, BillItem, Payment
from app.models.canteen import CanteenOrder, CanteenSale
from app.models.inpatient import Admission
from app.models.lab import LabTest, PatientLabOrder
from app.models.outpatient import Appointment
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

    def test_consultation_generates_bill_and_appointment(
        self, client, auth_headers, seed_data, db_session
    ):
        svc, pay = _dates(7, 6)
        res = client.post(
            "/api/admin/catch-up/consultation",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "doctor_id": seed_data["doctor_user_id"],
                "consultation_fee": 500,
                "registration_fee": 50,
                "service_date": svc,
                "payment_date": pay,
                "reason": "Missed OPD slip",
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] == 550.0
        bill, items, payment = _assert_paid_bill(
            db_session, body["bill_id"],
            bill_type="consultation", service_date=svc,
            payment_id=body["payment_id"], expected_total=550.0,
        )
        assert payment.payment_date.date().isoformat() == pay
        apt = db_session.query(Appointment).filter(Appointment.id == body["appointment_id"]).first()
        assert apt is not None
        assert apt.payment_status == "paid"
        assert any("consult" in (i.item_name or "").lower() or i.item_type == "consultation"
                   for i in items) or len(items) >= 1

    def test_lab_generates_orders_and_bill(self, client, auth_headers, seed_data, db_session):
        from app.models.lab import LabTestCategory

        hid = seed_data["hospital_id"]
        cat = LabTestCategory(name=f"CU-Cat-{uuid.uuid4().hex[:6]}", hospital_id=hid)
        db_session.add(cat)
        db_session.flush()
        test = LabTest(
            test_code=f"CU-{uuid.uuid4().hex[:6]}",
            name="CatchUp CBC",
            cost=350.0,
            category_id=cat.id,
            hospital_id=hid,
            is_active=True,
        )
        db_session.add(test)
        db_session.commit()

        svc, pay = _dates(8, 3)
        res = client.post(
            "/api/admin/catch-up/lab",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "doctor_id": seed_data["doctor_user_id"],
                "test_ids": [test.id],
                "service_date": svc,
                "payment_date": pay,
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] == 350.0
        _assert_paid_bill(
            db_session, body["bill_id"],
            bill_type="lab", service_date=svc,
            payment_id=body["payment_id"], expected_total=350.0,
        )
        orders = db_session.query(PatientLabOrder).filter(
            PatientLabOrder.id.in_(body["order_ids"])
        ).all()
        assert len(orders) == 1
        assert orders[0].payment_status == "paid"
        assert orders[0].status == "collected"
        assert orders[0].completion_date is None
        assert (orders[0].lab_bill_number or "").startswith("LB-CU-")
        assert orders[0].payment_date.date().isoformat() == pay
        assert orders[0].order_date.date().isoformat() == svc
        assert body.get("orders") and body["orders"][0]["id"] == orders[0].id
        assert body["orders"][0]["has_report"] is False

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

    def test_canteen_with_patient_generates_sale_and_bill(
        self, client, auth_headers, seed_data, db_session
    ):
        svc, pay = _dates(6, 5)
        res = client.post(
            "/api/admin/catch-up/canteen-sale",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": pay,
                "items": [
                    {"item_name": "Tea", "quantity": 2, "unit_price": 15},
                    {"item_name": "Idli", "quantity": 1, "unit_price": 40},
                ],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] == 70.0
        assert body["sale_id"]
        assert body["bill_id"]
        _assert_paid_bill(
            db_session, body["bill_id"],
            bill_type="canteen", service_date=svc,
            payment_id=body["payment_id"], expected_total=70.0,
        )
        sale = db_session.query(CanteenSale).filter(CanteenSale.id == body["sale_id"]).first()
        assert sale is not None
        assert sale.status == "completed"
        assert float(sale.grand_total) == pytest.approx(70.0)

    def test_canteen_walkin_without_patient_sale_only(
        self, client, auth_headers, seed_data, db_session
    ):
        svc, pay = _dates(2, 2)
        res = client.post(
            "/api/admin/catch-up/canteen-sale",
            headers=auth_headers,
            json={
                "customer_name": "Walk-in Guest",
                "service_date": svc,
                "payment_date": pay,
                "items": [{"item_name": "Coffee", "quantity": 1, "unit_price": 25}],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] == 25.0
        assert body["sale_id"]
        assert body["bill_id"] is None
        assert body["payment_id"] is None
        sale = db_session.query(CanteenSale).filter(CanteenSale.id == body["sale_id"]).first()
        assert sale is not None
        assert sale.customer_name == "Walk-in Guest"

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

        food = client.post(
            "/api/canteen/items",
            headers=auth_headers,
            json={"name": f"E2E Meal {uuid.uuid4().hex[:4]}", "price": 90.0, "is_veg": True},
        )
        assert food.status_code == 201, food.text
        food_id = food.json()["id"]

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
                "canteen_orders": [{
                    "serve_date": "2026-04-02",
                    "items": [{
                        "item_id": food_id,
                        "item_name": food.json()["name"],
                        "quantity": 2,
                        "unit_price": 90,
                    }],
                }],
                "pharmacy_lines": [
                    {"item_name": "Inj. NS", "quantity": 1, "unit_price": 50},
                ],
                "deposits": [],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        # 3d room 3000 + visit 400 + food 180 + pharm 50 = 3630
        assert body["total"] == pytest.approx(3630.0)
        assert body["is_catch_up"] is True

        bill = db_session.query(Bill).filter(Bill.id == body["bill_id"]).first()
        assert bill.status == "paid"
        assert bill.bill_date.date().isoformat() == svc
        items = db_session.query(BillItem).filter(BillItem.bill_id == body["bill_id"]).all()
        types = {it.item_type for it in items}
        assert "food" in types
        food_total = sum(float(i.total_price or 0) for i in items if i.item_type == "food")
        assert food_total == pytest.approx(180.0)

        orders = db_session.query(CanteenOrder).filter(
            CanteenOrder.admission_id == body["admission_id"]
        ).all()
        assert len(orders) == 1
        assert orders[0].billed is True
        assert orders[0].bill_id == body["bill_id"]

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

    def test_lab_unknown_test_ids(self, client, auth_headers, seed_data):
        svc, pay = _dates()
        res = client.post(
            "/api/admin/catch-up/lab",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "test_ids": [999999],
                "service_date": svc,
                "payment_date": pay,
            },
        )
        assert res.status_code == 400
        assert "Unknown lab test" in res.text

    def test_lab_empty_test_ids_422(self, client, auth_headers, seed_data):
        svc, pay = _dates()
        res = client.post(
            "/api/admin/catch-up/lab",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "test_ids": [],
                "service_date": svc,
                "payment_date": pay,
            },
        )
        assert res.status_code == 422

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
                "canteen_orders": [],
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
                "canteen_orders": [],
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
                "canteen_orders": [],
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
                "canteen_orders": [],
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
                "canteen_orders": [],
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

    def test_canteen_catalog_available(self, client, auth_headers):
        res = client.get("/api/admin/catch-up/canteen-catalog", headers=auth_headers)
        assert res.status_code == 200, res.text
        assert isinstance(res.json(), list)

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
    """Dry-run previews for all modules + pdf path on create responses."""

    def test_consultation_preview_and_pdf_meta(self, client, auth_headers, seed_data):
        svc, pay = _dates(4, 3)
        payload = {
            "patient_id": seed_data["patient_id"],
            "doctor_id": seed_data["doctor_user_id"],
            "consultation_fee": 400,
            "registration_fee": 100,
            "service_date": svc,
            "payment_date": pay,
        }
        prev = client.post(
            "/api/admin/catch-up/consultation/preview",
            headers=auth_headers,
            json=payload,
        )
        assert prev.status_code == 200, prev.text
        draft = prev.json()
        assert draft["bill_type"] == "consultation"
        assert draft["grand_total"] == 500.0
        assert len(draft["items"]) == 2
        assert draft["creates_central_bill"] is True

        created = client.post(
            "/api/admin/catch-up/consultation",
            headers=auth_headers,
            json=payload,
        )
        assert created.status_code == 200, created.text
        pdf = created.json()["pdf"]
        assert pdf["path"].startswith("/api/appointments/")
        assert pdf["path"].endswith("/bill/download")

    def test_lab_preview_and_pdf_meta(self, client, auth_headers, seed_data, db_session):
        from app.models.lab import LabTestCategory

        hid = seed_data["hospital_id"]
        cat = LabTestCategory(name=f"Prev-Cat-{uuid.uuid4().hex[:6]}", hospital_id=hid)
        db_session.add(cat)
        db_session.flush()
        test = LabTest(
            test_code=f"PV-{uuid.uuid4().hex[:6]}",
            name="Preview Lipid",
            cost=220.0,
            category_id=cat.id,
            hospital_id=hid,
            is_active=True,
        )
        db_session.add(test)
        db_session.commit()

        svc, pay = _dates(3, 2)
        payload = {
            "patient_id": seed_data["patient_id"],
            "test_ids": [test.id],
            "service_date": svc,
            "payment_date": pay,
        }
        prev = client.post("/api/admin/catch-up/lab/preview", headers=auth_headers, json=payload)
        assert prev.status_code == 200, prev.text
        assert prev.json()["grand_total"] == 220.0
        assert prev.json()["items"][0]["item_name"] == "Preview Lipid"

        created = client.post("/api/admin/catch-up/lab", headers=auth_headers, json=payload)
        assert created.status_code == 200, created.text
        body = created.json()
        assert body["lab_bill_group_id"]
        assert body["pdf"]["path"] == f"/api/lab/bills/{body['lab_bill_group_id']}/pdf"

    def test_pharmacy_misc_canteen_previews(self, client, auth_headers, seed_data):
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

        canteen = client.post(
            "/api/admin/catch-up/canteen-sale/preview",
            headers=auth_headers,
            json={
                "service_date": svc,
                "payment_date": pay,
                "items": [{"item_name": "Tea", "quantity": 3, "unit_price": 10}],
            },
        )
        assert canteen.status_code == 200, canteen.text
        assert canteen.json()["grand_total"] == 30.0
        assert canteen.json()["creates_central_bill"] is False
        assert any("no central bill" in w.lower() for w in canteen.json()["warnings"])

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
                "canteen_orders": [],
                "pharmacy_lines": [{"item_name": "ORS", "quantity": 2, "unit_price": 25}],
            },
        )
        assert prev.status_code == 200, prev.text
        draft = prev.json()
        assert draft["grand_total"] > 0
        assert isinstance(draft["items"], list)
        assert len(draft["items"]) >= 1
        assert any("ORS" in (i.get("item_name") or "") for i in draft["items"])


class TestCatchUpLabResultsAndReport:
    """Admin-owned catch-up lab: enter values + download clinical report."""

    def test_catch_up_lab_results_and_report_pdf(
        self, client, auth_headers, seed_data, db_session
    ):
        from app.models.lab import LabTestCategory, LabTestParameter, LabReport

        hid = seed_data["hospital_id"]
        cat = LabTestCategory(name=f"CU-RCat-{uuid.uuid4().hex[:6]}", hospital_id=hid)
        db_session.add(cat)
        db_session.flush()
        test = LabTest(
            test_code=f"CUR-{uuid.uuid4().hex[:6]}",
            name="CatchUp Glucose",
            cost=120.0,
            category_id=cat.id,
            hospital_id=hid,
            is_active=True,
        )
        db_session.add(test)
        db_session.flush()
        param = LabTestParameter(
            test_id=test.id,
            parameter_name="Fasting Glucose",
            unit="mg/dL",
            field_type="numeric",
            reference_min_default=70,
            reference_max_default=100,
            display_order=0,
            is_active=True,
        )
        db_session.add(param)
        db_session.commit()

        svc, pay = _dates(5, 4)
        created = client.post(
            "/api/admin/catch-up/lab",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "test_ids": [test.id],
                "service_date": svc,
                "payment_date": pay,
            },
        )
        assert created.status_code == 200, created.text
        body = created.json()
        order_id = body["order_ids"][0]
        assert body["orders"][0]["status"] == "collected"

        stored = client.get(
            "/api/admin/catch-up/lab/reports",
            headers=auth_headers,
        )
        assert stored.status_code == 200, stored.text
        stored_order = next(row for row in stored.json() if row["order_id"] == order_id)
        assert stored_order["test_name"] == "CatchUp Glucose"
        assert stored_order["service_date"] == svc
        assert stored_order["has_report"] is False
        assert stored_order["report_id"] is None

        form = client.get(
            f"/api/admin/catch-up/lab/orders/{order_id}/entry-form",
            headers=auth_headers,
        )
        assert form.status_code == 200, form.text
        form_body = form.json()
        assert form_body["order_id"] == order_id
        assert form_body["has_report"] is False
        assert len(form_body["parameters"]) == 1
        assert form_body["parameters"][0]["parameter_name"] == "Fasting Glucose"

        submitted = client.post(
            f"/api/admin/catch-up/lab/orders/{order_id}/results",
            headers=auth_headers,
            json={
                "results": [{
                    "parameter_id": param.id,
                    "value": "92",
                    "remarks": "",
                    "manual_abnormal": False,
                }],
                "interpretation": "Normal fasting glucose",
            },
        )
        assert submitted.status_code == 200, submitted.text
        sub = submitted.json()
        assert sub["report_id"]
        assert sub["pdf"]["path"] == f"/api/lab/reports/{sub['report_id']}/download"

        order = db_session.query(PatientLabOrder).filter(PatientLabOrder.id == order_id).first()
        assert order.status == "completed"
        assert order.completion_date is not None
        assert order.completion_date.date().isoformat() == svc
        report = db_session.query(LabReport).filter(LabReport.id == sub["report_id"]).first()
        assert report is not None
        assert report.report_date.date().isoformat() == svc

        stored = client.get(
            "/api/admin/catch-up/lab/reports",
            headers=auth_headers,
        )
        assert stored.status_code == 200, stored.text
        stored_report = next(row for row in stored.json() if row["order_id"] == order_id)
        assert stored_report["has_report"] is True
        assert stored_report["report_id"] == sub["report_id"]
        assert stored_report["report_date"] == svc
        assert stored_report["pdf"]["path"] == sub["pdf"]["path"]

        pdf = client.get(
            f"/api/lab/reports/{sub['report_id']}/download",
            headers=auth_headers,
        )
        assert pdf.status_code == 200, pdf.text
        assert pdf.headers.get("content-type", "").startswith("application/pdf")
        assert pdf.content[:4] == b"%PDF"

        # Non catch-up order rejected on catch-up entry endpoint
        other = PatientLabOrder(
            order_number=f"LAB-{uuid.uuid4().hex[:8].upper()}",
            patient_id=seed_data["patient_id"],
            test_id=test.id,
            status="collected",
            payment_status="paid",
            amount=120.0,
        )
        db_session.add(other)
        db_session.commit()
        bad = client.get(
            f"/api/admin/catch-up/lab/orders/{other.id}/entry-form",
            headers=auth_headers,
        )
        assert bad.status_code == 400
