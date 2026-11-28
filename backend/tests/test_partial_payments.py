"""Partial payments / payment status across non-Bill invoicing flows.

Covers the service_payments ledger: booking with a partial amount, collecting
the balance later (possibly with another method), bill JSON/PDF paid/balance,
and the reports that read collections.
"""
from datetime import date

import pytest

from app.models.patient import Patient
from app.models.user import User
from app.models.billing import ServicePayment
from app.services import service_payments as sp


@pytest.fixture()
def doctor_500(db_session, seed_data):
    doctor = db_session.query(User).filter(User.id == seed_data["doctor_user_id"]).first()
    doctor.consultation_fee_inr = "₹500"
    db_session.commit()
    return seed_data


@pytest.fixture()
def patient_uuid(db_session, seed_data):
    return db_session.query(Patient).filter(Patient.id == seed_data["patient_id"]).first().patient_id


def _book(client, headers, patient_uuid, doctor_id, **overrides):
    payload = {
        "patient_id": patient_uuid,
        "doctor_id": doctor_id,
        "appointment_date": date.today().isoformat(),
        "payment_status": "paid",
        "payment_method": "cash",
        "override_availability": True,
        "override_reason": "test",
    }
    payload.update(overrides)
    res = client.post("/api/appointments/", headers=headers, json=payload)
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_derive_status(self):
        assert sp.derive_status(500, 0) == "pending"
        assert sp.derive_status(500, 200) == "partial"
        assert sp.derive_status(500, 500) == "paid"
        assert sp.derive_status(0, 0) == "paid"

    def test_resolve_initial_amount(self):
        assert sp.resolve_initial_amount(500, None, "paid") == 500
        assert sp.resolve_initial_amount(500, None, None) == 500
        assert sp.resolve_initial_amount(500, None, "pending") == 0
        assert sp.resolve_initial_amount(500, 200, "paid") == 200
        with pytest.raises(Exception):
            sp.resolve_initial_amount(500, 600, None)
        with pytest.raises(Exception):
            sp.resolve_initial_amount(500, None, "partial")


# ---------------------------------------------------------------------------
# OP appointments
# ---------------------------------------------------------------------------

class TestAppointmentPartial:
    def test_full_payment_default(self, client, auth_headers, doctor_500, patient_uuid):
        apt = _book(client, auth_headers, patient_uuid, doctor_500["doctor_user_id"])
        assert apt["payment_status"] == "paid"
        assert apt["amount_paid"] == 500.0
        bill = client.get(f"/api/appointments/{apt['id']}/bill", headers=auth_headers).json()
        assert bill["amount_paid"] == 500.0
        assert bill["balance_due"] == 0.0

    def test_partial_then_collect_balance(self, client, auth_headers, doctor_500, patient_uuid, db_session):
        apt = _book(client, auth_headers, patient_uuid, doctor_500["doctor_user_id"], amount_paid=200)
        assert apt["payment_status"] == "partial"
        assert apt["amount_paid"] == 200.0

        bill = client.get(f"/api/appointments/{apt['id']}/bill", headers=auth_headers).json()
        assert bill["amount_paid"] == 200.0
        assert bill["balance_due"] == 300.0
        assert bill["payment_status"] == "partial"

        # Over-collection is rejected.
        res = client.post(f"/api/appointments/{apt['id']}/payments", headers=auth_headers,
                          json={"amount": 400, "payment_method": "upi"})
        assert res.status_code == 400

        res = client.post(f"/api/appointments/{apt['id']}/payments", headers=auth_headers,
                          json={"amount": 300, "payment_method": "upi"})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["payment_state"] == "paid"
        assert body["balance_due"] == 0.0
        assert [p["amount"] for p in body["payments"]] == [200.0, 300.0]
        assert [p["payment_method"] for p in body["payments"]] == ["cash", "upi"]

        res = client.post(f"/api/appointments/{apt['id']}/payments", headers=auth_headers,
                          json={"amount": 1, "payment_method": "cash"})
        assert res.status_code == 400

    def test_pay_later(self, client, auth_headers, doctor_500, patient_uuid):
        apt = _book(client, auth_headers, patient_uuid, doctor_500["doctor_user_id"], payment_status="pending")
        assert apt["payment_status"] == "pending"
        assert apt["amount_paid"] == 0.0
        pdf = client.get(f"/api/appointments/{apt['id']}/bill/download", headers=auth_headers)
        assert pdf.status_code == 200
        assert pdf.content[:4] == b"%PDF"

    def test_generic_update_to_paid_records_balance(self, client, auth_headers, doctor_500, patient_uuid, db_session):
        apt = _book(client, auth_headers, patient_uuid, doctor_500["doctor_user_id"], amount_paid=100)
        res = client.put(f"/api/appointments/{apt['id']}", headers=auth_headers,
                         json={"payment_status": "paid", "payment_method": "card"})
        assert res.status_code == 200, res.text
        assert res.json()["payment_status"] == "paid"
        rows = db_session.query(ServicePayment).filter_by(source_type="appointment", source_id=apt["id"]).all()
        assert sorted(r.amount for r in rows) == [100.0, 400.0]

    def test_amount_over_fee_rejected(self, client, auth_headers, doctor_500, patient_uuid):
        res = client.post("/api/appointments/", headers=auth_headers, json={
            "patient_id": patient_uuid, "doctor_id": doctor_500["doctor_user_id"],
            "appointment_date": date.today().isoformat(), "payment_status": "paid",
            "amount_paid": 900, "override_availability": True, "override_reason": "t",
        })
        assert res.status_code == 400


# ---------------------------------------------------------------------------
# Lab
# ---------------------------------------------------------------------------

from tests.test_billing_list_edge_cases import _make_test, _make_opd_lab_order, _billing_list  # noqa: E402
from app.models.lab import PatientLabOrder  # noqa: E402


def _orders_by_group(db_session, group_id):
    db_session.expire_all()
    return db_session.query(PatientLabOrder).filter_by(lab_bill_group_id=group_id).order_by(PatientLabOrder.id).all()


class TestLabPartial:
    def test_reception_book_partial_with_discount(self, client, auth_headers, db_session, seed_data):
        t1 = _make_test(db_session, seed_data, "PPA")  # 250
        t2 = _make_test(db_session, seed_data, "PPB")  # 250
        res = client.post("/api/lab/orders/reception-book", headers=auth_headers, json={
            "patient_id": seed_data["patient_id"], "test_ids": [t1.id, t2.id],
            "payment_method": "cash", "discount_amount": 100, "amount_paid": 150, "force": True,
        })
        assert res.status_code == 200, res.text
        oid = int(res.headers["X-Order-Ids"].split(",")[0])
        db_session.expire_all()
        gid = db_session.get(PatientLabOrder, oid).lab_bill_group_id
        orders = _orders_by_group(db_session, gid)
        assert sum(o.discount_amount for o in orders) == 100
        assert sum(o.amount_paid for o in orders) == 150
        assert {o.payment_status for o in orders} <= {"paid", "partial", "pending"}

        info = client.get(f"/api/lab/bills/{gid}/payments", headers=auth_headers).json()
        assert info["total_amount"] == 400
        assert info["amount_paid"] == 150
        assert info["balance_due"] == 250
        assert info["payment_state"] == "partial"

        # Billing list row reflects partial with real paid / balance.
        row = next(b for b in _billing_list(client, auth_headers, bill_type="lab") if b.get("lab_bill_group_id") == gid)
        assert row["payment_status"] == "partial"
        assert row["amount"] == 400
        assert row["amount_paid"] == 150
        assert row["balance_due"] == 250

        # Reprint shows balance (PDF builds without error).
        pdf = client.get(f"/api/lab/bills/{gid}/pdf", headers=auth_headers)
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

        # Over-collection rejected; exact balance accepted with another method.
        assert client.post(f"/api/lab/bills/{gid}/payments", headers=auth_headers,
                           json={"amount": 300, "payment_method": "upi"}).status_code == 400
        res = client.post(f"/api/lab/bills/{gid}/payments", headers=auth_headers,
                          json={"amount": 250, "payment_method": "upi"})
        assert res.status_code == 200, res.text
        assert res.json()["payment_state"] == "paid"
        assert {o.payment_status for o in _orders_by_group(db_session, gid)} == {"paid"}

    def test_reception_book_default_is_full_payment(self, client, auth_headers, db_session, seed_data):
        t1 = _make_test(db_session, seed_data, "PPF")
        res = client.post("/api/lab/orders/reception-book", headers=auth_headers, json={
            "patient_id": seed_data["patient_id"], "test_ids": [t1.id],
            "payment_method": "card", "force": True,
        })
        assert res.status_code == 200, res.text
        oid = int(res.headers["X-Order-Ids"])
        db_session.expire_all()
        o = db_session.get(PatientLabOrder, oid)
        assert o.payment_status == "paid"
        assert o.amount_paid == 250
        assert o.payment_date is not None

    def test_pay_later_at_booking(self, client, auth_headers, db_session, seed_data):
        t1 = _make_test(db_session, seed_data, "PPL")
        res = client.post("/api/lab/orders/reception-book", headers=auth_headers, json={
            "patient_id": seed_data["patient_id"], "test_ids": [t1.id],
            "payment_method": "cash", "payment_status": "pending", "force": True,
        })
        assert res.status_code == 200, res.text
        oid = int(res.headers["X-Order-Ids"])
        db_session.expire_all()
        o = db_session.get(PatientLabOrder, oid)
        assert o.payment_status == "pending"
        assert o.amount_paid == 0

    def test_pay_and_download_partial(self, client, auth_headers, db_session, seed_data):
        # clear other pending orders for this patient so the call is scoped
        db_session.query(PatientLabOrder).filter(
            PatientLabOrder.patient_id == seed_data["patient_id"],
            PatientLabOrder.payment_status == "pending",
        ).update({PatientLabOrder.payment_status: "cancelled"}, synchronize_session=False)
        db_session.commit()
        o1 = _make_opd_lab_order(db_session, seed_data, amount=100)
        o2 = _make_opd_lab_order(db_session, seed_data, amount=150)
        res = client.post(f"/api/lab/orders/patient/{seed_data['patient_id']}/bill", headers=auth_headers,
                          json={"payment_method": "cash", "amount_paid": 120})
        assert res.status_code == 200, res.text
        db_session.expire_all()
        a, b = db_session.get(PatientLabOrder, o1.id), db_session.get(PatientLabOrder, o2.id)
        assert round(a.amount_paid + b.amount_paid, 2) == 120
        assert a.lab_bill_group_id == b.lab_bill_group_id

        # Part-paid orders show in the reception "pending payment" list.
        pend = client.get(f"/api/lab/orders/patient/{seed_data['patient_id']}/pending-payment", headers=auth_headers).json()
        assert {o1.id, o2.id} & {p["id"] for p in pend}
        assert round(sum(p["balance_due"] for p in pend if p["id"] in (o1.id, o2.id)), 2) == 130

    def test_single_order_partial(self, client, auth_headers, db_session, seed_data):
        o = _make_opd_lab_order(db_session, seed_data, amount=300)
        res = client.put(f"/api/lab/orders/{o.id}/payment", headers=auth_headers,
                         json={"payment_method": "cash", "amount_paid": 100})
        assert res.status_code == 200, res.text
        assert res.json()["payment_status"] == "partial"
        assert res.json()["balance_due"] == 200
        res = client.put(f"/api/lab/orders/{o.id}/payment", headers=auth_headers,
                         json={"payment_method": "upi"})
        assert res.status_code == 200, res.text
        assert res.json()["payment_status"] == "paid"
        assert client.put(f"/api/lab/orders/{o.id}/payment", headers=auth_headers,
                          json={"payment_method": "upi"}).status_code == 400

    def test_legacy_paid_order_untouched(self, client, auth_headers, db_session, seed_data):
        o = _make_opd_lab_order(db_session, seed_data, amount=200, payment_status="paid")
        assert o.amount_paid is None
        assert sp.effective_paid(sp.LAB_ORDER, o) == 200
        assert sp.balance_due(sp.LAB_ORDER, o) == 0


# ---------------------------------------------------------------------------
# Pharmacy
# ---------------------------------------------------------------------------

import uuid  # noqa: E402
from datetime import datetime  # noqa: E402


@pytest.fixture()
def stocked_medicine(client, auth_headers):
    H = auth_headers
    tag = uuid.uuid4().hex[:6]
    sup = client.post("/api/pharmacy/suppliers", json={"name": f"PP Sup {tag}", "is_active": True}, headers=H)
    assert sup.status_code == 201, sup.text
    hsn = client.post("/api/pharmacy/hsn", json={"code": f"3004{tag[:4]}", "description": "PP",
                                                 "sgst_pct": 0.0, "cgst_pct": 0.0, "is_active": True}, headers=H)
    assert hsn.status_code == 201, hsn.text
    cat = client.post("/api/pharmacy/categories", json={"name": f"PP Cat {tag}", "is_active": True}, headers=H)
    comp = client.post("/api/pharmacy/companies", json={"name": f"PP Co {tag}", "is_active": True}, headers=H)
    med = client.post("/api/pharmacy/medicines", json={
        "medicine_code": f"PP-{tag}", "name": f"PP Med {tag}",
        "category_id": cat.json()["id"], "company_id": comp.json()["id"], "hsn_id": hsn.json()["id"],
        "dosage_form": "tablet", "strength": "1mg", "unit_price": 0, "mrp": 0,
        "rate_a": 10.0, "rate_b": 10.0, "min_qty": 1, "is_active": True,
    }, headers=H)
    assert med.status_code == 201, med.text
    mid = med.json()["id"]
    pur = client.post("/api/pharmacy/purchases", json={
        "entry_date": date.today().isoformat(), "supplier_id": sup.json()["id"],
        "invoice_number": f"INV-PP-{tag}", "bill_date": None, "payment_type": "cash", "purchase_type": "local",
        "items": [{"medicine_id": mid, "batch_number": f"B-PP-{tag}", "expiry_date": "2030-12-31",
                   "mrp": 20.0, "quantity": 100, "free_quantity": 0, "purchase_rate": 5.0,
                   "discount_pct": 0, "hsn_id": hsn.json()["id"]}],
    }, headers=H)
    assert pur.status_code == 201, pur.text
    assert client.post(f"/api/pharmacy/purchases/{pur.json()['id']}/confirm", headers=H).status_code == 200
    return mid


def _sell(client, headers, mid, qty=10, **extra):
    body = {"payment_type": "cash", "patient_name": "PP Buyer", "patient_phone": "9111111111",
            "items": [{"medicine_id": mid, "quantity": qty, "rate_tier": "A"}]}
    body.update(extra)
    r = client.post("/api/pharmacy/sales", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


class TestPharmacyPartial:
    def test_cash_sale_full_by_default(self, client, auth_headers, stocked_medicine):
        sale = _sell(client, auth_headers, stocked_medicine)
        assert sale["payment_state"] == "paid"
        assert sale["amount_paid"] == sale["grand_total"]
        assert sale["balance_due"] == 0

    def test_partial_sale_then_settle(self, client, auth_headers, stocked_medicine):
        sale = _sell(client, auth_headers, stocked_medicine, amount_paid=40, payment_method="upi")
        g = sale["grand_total"]
        assert sale["payment_state"] == "partial"
        assert sale["payment_type"] == "credit"
        assert sale["amount_paid"] == 40
        assert round(sale["balance_due"], 2) == round(g - 40, 2)

        row = next(b for b in _billing_list(client, auth_headers, bill_type="pharmacy") if b["id"] == f"PHARM-{sale['id']}")
        assert row["payment_status"] == "partial"
        assert row["amount_paid"] == 40

        pdf = client.get(f"/api/pharmacy/sales/{sale['id']}/invoice/pdf", headers=auth_headers)
        assert pdf.status_code == 200

        r = client.post(f"/api/pharmacy/sales/{sale['id']}/payments", headers=auth_headers,
                        json={"amount": g - 40, "payment_method": "cash"})
        assert r.status_code == 200, r.text
        assert r.json()["payment_state"] == "paid"
        got = client.get(f"/api/pharmacy/sales/{sale['id']}", headers=auth_headers).json()
        assert got["payment_type"] == "cash"

    def test_credit_sale_collect_later(self, client, auth_headers, stocked_medicine):
        sale = _sell(client, auth_headers, stocked_medicine, payment_type="credit")
        assert sale["payment_state"] == "pending"
        assert sale["amount_paid"] == 0
        r = client.post(f"/api/pharmacy/sales/{sale['id']}/payments", headers=auth_headers,
                        json={"amount": 10, "payment_method": "cash"})
        assert r.status_code == 200, r.text
        assert r.json()["payment_state"] == "partial"

    def test_legacy_credit_sale_collect(self, client, auth_headers, db_session, seed_data):
        from app.models.pharmacy import PharmacySale
        s = PharmacySale(sale_number=f"SALE-PP-{uuid.uuid4().hex[:6]}", sale_date=datetime.now(),
                         payment_type="credit", grand_total=300.0, subtotal=300.0, status="completed",
                         billing_mode="cash_at_pharmacy", hospital_id=seed_data["hospital_id"])
        db_session.add(s); db_session.commit()
        assert sp.balance_due(sp.PHARMACY_SALE, s) == 300
        r = client.post(f"/api/pharmacy/sales/{s.id}/payments", headers=auth_headers,
                        json={"amount": 300, "payment_method": "card"})
        assert r.status_code == 200, r.text
        assert r.json()["payment_state"] == "paid"


# ---------------------------------------------------------------------------
# Canteen + procedures
# ---------------------------------------------------------------------------

class TestCanteenPartial:
    def test_canteen_partial_then_collect(self, client, auth_headers):
        item = client.post("/api/canteen/items", headers=auth_headers,
                           json={"name": f"PP Meal {uuid.uuid4().hex[:4]}", "price": 50.0, "is_veg": True})
        assert item.status_code == 201, item.text
        sale = client.post("/api/canteen/sales", headers=auth_headers, json={
            "payment_type": "cash", "amount_paid": 30,
            "items": [{"item_id": item.json()["id"], "quantity": 2}],
        })
        assert sale.status_code == 201, sale.text
        body = sale.json()
        assert body["payment_state"] == "partial"
        assert body["balance_due"] == 70
        pdf = client.get(f"/api/canteen/sales/{body['id']}/receipt/pdf", headers=auth_headers)
        assert pdf.status_code == 200

        row = next(b for b in _billing_list(client, auth_headers, bill_type="canteen") if b["id"] == f"CAN-{body['id']}")
        assert row["payment_status"] == "partial"

        r = client.post(f"/api/canteen/sales/{body['id']}/payments", headers=auth_headers,
                        json={"amount": 70, "payment_method": "upi"})
        assert r.status_code == 200, r.text
        assert r.json()["payment_state"] == "paid"
        assert r.json()["payment_type"] == "upi"


class TestProcedurePartial:
    def _bill(self, client, headers, seed_data, **extra):
        body = {"patient_id": seed_data["patient_id"],
                "items": [{"item_name": "Dressing", "quantity": 1, "unit_price": 400}],
                "payment_method": "cash"}
        body.update(extra)
        r = client.post("/api/outpatient/procedure-bills", headers=headers, json=body)
        return r

    def test_full_default(self, client, auth_headers, seed_data):
        r = self._bill(client, auth_headers, seed_data)
        assert r.status_code in (200, 201), r.text
        assert r.json()["status"] == "paid"

    def test_partial_and_pay_later(self, client, auth_headers, seed_data):
        r = self._bill(client, auth_headers, seed_data, amount_paid=150)
        assert r.status_code in (200, 201), r.text
        b = r.json()
        assert b["status"] == "partial" and b["balance_due"] == 250
        r = client.post(f"/api/hospital/billing/bills/{b['bill_id']}/payment", headers=auth_headers,
                        json={"amount_paid": 250, "payment_method": "upi"})
        assert r.status_code == 200, r.text

        r = self._bill(client, auth_headers, seed_data, payment_status="pending")
        assert r.json()["status"] == "pending"
        assert r.json()["amount_paid"] == 0


class TestUnifiedRowCollect:
    def test_collect_on_appointment_row(self, client, auth_headers, doctor_500, patient_uuid):
        apt = _book(client, auth_headers, patient_uuid, doctor_500["doctor_user_id"], payment_status="pending")
        rid = f"APT-{apt['id']}"
        info = client.get(f"/api/hospital/billing/rows/{rid}/payments", headers=auth_headers).json()
        assert info["balance_due"] == 500 and info["payment_state"] == "pending"
        r = client.post(f"/api/hospital/billing/rows/{rid}/payments", headers=auth_headers,
                        json={"amount": 125, "payment_method": "card"})
        assert r.status_code == 200, r.text
        assert r.json()["payment_state"] == "partial"
        row = next(b for b in _billing_list(client, auth_headers, bill_type="consultation") if b["id"] == rid)
        assert row["payment_status"] == "partial" and row["balance_due"] == 375

    def test_unknown_row(self, client, auth_headers):
        assert client.get("/api/hospital/billing/rows/BILL-1/payments", headers=auth_headers).status_code == 400


# ---------------------------------------------------------------------------
# Reports read real collections
# ---------------------------------------------------------------------------

from datetime import timedelta  # noqa: E402
from app.services.collection_by_method import collection_by_method  # noqa: E402


def _cbm(db_session, seed_data, day, sources=None):
    return collection_by_method(db_session, seed_data["hospital_id"], day, day,
                                sources=sources or {"opd", "lab"})


class TestReportsPartial:
    def test_collection_by_method_splits_methods(self, client, auth_headers, db_session, doctor_500, patient_uuid, seed_data):
        today = date.today()
        before = _cbm(db_session, seed_data, today, {"opd"})["by_method"]
        apt = _book(client, auth_headers, patient_uuid, doctor_500["doctor_user_id"], amount_paid=200)
        client.post(f"/api/appointments/{apt['id']}/payments", headers=auth_headers,
                    json={"amount": 300, "payment_method": "upi"})
        db_session.expire_all()
        after = _cbm(db_session, seed_data, today, {"opd"})["by_method"]
        assert round(after.get("cash", 0) - before.get("cash", 0), 2) == 200
        assert round(after.get("upi", 0) - before.get("upi", 0), 2) == 300

    def test_balance_collected_another_day_lands_on_that_day(self, client, auth_headers, db_session, seed_data):
        o = _make_opd_lab_order(db_session, seed_data, amount=500)
        client.put(f"/api/lab/orders/{o.id}/payment", headers=auth_headers,
                   json={"payment_method": "cash", "amount_paid": 100})
        db_session.expire_all()
        yday = date.today() - timedelta(days=3)
        row = db_session.query(ServicePayment).filter_by(source_type="lab_order", source_id=o.id).one()
        row.payment_date = datetime.combine(yday, datetime.min.time()).replace(hour=10)
        db_session.commit()
        got = _cbm(db_session, seed_data, yday, {"lab"})
        assert got["by_method"].get("cash", 0) >= 100

    def test_billing_summary_counts_partial_paid(self, client, auth_headers, db_session, doctor_500, patient_uuid):
        today = date.today().isoformat()
        q = {"date_from": today, "date_to": today, "bill_type": "consultation"}
        s0 = client.get("/api/hospital/billing", params=q, headers=auth_headers).json()["summary"]
        _book(client, auth_headers, patient_uuid, doctor_500["doctor_user_id"], amount_paid=150)
        s1 = client.get("/api/hospital/billing", params=q, headers=auth_headers).json()["summary"]
        assert round(s1["total_paid"] - s0["total_paid"], 2) == 150
        assert round(s1["total_pending"] - s0["total_pending"], 2) == 350
        assert round(s1["received_total"] - s0["received_total"], 2) == 150

    def test_gst_invoice_collected_is_partial(self, client, auth_headers, db_session, doctor_500, patient_uuid, seed_data):
        from app.services.gst_report_service import collect_sales_invoices
        apt = _book(client, auth_headers, patient_uuid, doctor_500["doctor_user_id"], amount_paid=120)
        db_session.expire_all()
        rows = collect_sales_invoices(db_session, seed_data["hospital_id"], date.today(), date.today())
        r = next(x for x in rows if x.get("number") == apt["appointment_number"] or x.get("invoice_number") == apt["appointment_number"])
        assert r["collected"] == 120
        assert r["outstanding"] == 380

    def test_consolidate_bills_only_balance(self, client, auth_headers, db_session, doctor_500, patient_uuid, seed_data):
        apt = _book(client, auth_headers, patient_uuid, doctor_500["doctor_user_id"], amount_paid=200)
        r = client.post("/api/hospital/billing/consolidate", headers=auth_headers,
                        json={"patient_id": seed_data["patient_id"], "consultation_ids": [apt["id"]]})
        assert r.status_code == 200, r.text
        assert r.json()["total_amount"] == 300
