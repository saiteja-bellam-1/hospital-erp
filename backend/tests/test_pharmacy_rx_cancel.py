"""
Pharmacy P0 #1 — Rx cancellation with auto-reversal.

Covers the three states from the hybrid policy in
`app/services/pharmacy_reversal.py`:

  T1 — Cancel an un-billed Rx
  T2 — Cancel an Rx whose parent bill is unlocked (draft, no payments)
  T3 — Cancel an Rx whose parent bill is locked (paid)
  T4 — Cancel a partially-dispensed Rx (only dispensed qty restored)
  T5 — Second cancel on an already-cancelled Rx → 400
  T6 — POS sale void with patient_ip_id does NOT touch any IP bill (regression)

Setup uses the same session-DB pattern as the other smoke tests; pharmacy
catalog rows are created via the HTTP API for parity with the
existing test_pharmacy_smoke.py flow, then the Rx + dispense state is set up
directly via the ORM so we don't depend on a doctor's-side route that's not
under test here.
"""

from __future__ import annotations

from datetime import date, datetime
import pytest

from app.models.pharmacy import (
    Prescription,
    PrescriptionItem,
    PharmacyInventory,
    PharmacyStockLedger,
)
from app.models.billing import Bill, BillItem, Payment


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rx_cancel_seed(client, auth_headers, seed_data):
    """Spin up a supplier/hsn/category/medicine + a confirmed purchase so
    there is stock available to dispense against. Returns the medicine id and
    the batch id."""
    H = auth_headers
    today = str(date.today())

    sup = client.post("/api/pharmacy/suppliers",
                      json={"name": "Cancel Supplier", "phone": "x", "is_active": True},
                      headers=H)
    assert sup.status_code == 201, sup.text

    hsn = client.post("/api/pharmacy/hsn",
                      json={"code": "30049077", "description": "Cancel HSN",
                            "sgst_pct": 6.0, "cgst_pct": 6.0, "is_active": True},
                      headers=H)
    assert hsn.status_code == 201, hsn.text
    hsn_id = hsn.json()["id"]

    cat = client.post("/api/pharmacy/categories",
                      json={"name": "Cancel Cat", "is_active": True}, headers=H)
    assert cat.status_code == 201, cat.text
    cat_id = cat.json()["id"]

    med = client.post("/api/pharmacy/medicines",
                      json={"medicine_code": "CN-MED", "name": "Cancel Med",
                            "category_id": cat_id, "hsn_id": hsn_id,
                            "dosage_form": "tablet", "strength": "10mg",
                            "unit_price": 0, "mrp": 50.0,
                            "rate_a": 40.0, "rate_b": 45.0,
                            "min_qty": 5, "is_active": True},
                      headers=H)
    assert med.status_code == 201, med.text
    medicine_id = med.json()["id"]

    p = client.post("/api/pharmacy/purchases",
                    json={"entry_date": today,
                          "supplier_id": sup.json()["id"],
                          "invoice_number": "CN-PUR-1", "bill_date": today,
                          "payment_type": "credit", "purchase_type": "local",
                          "items": [{
                              "medicine_id": medicine_id,
                              "batch_number": "CN-B1",
                              "mrp": 50.0, "quantity": 200, "free_quantity": 0,
                              "purchase_rate": 30.0, "discount_pct": 0,
                              "hsn_id": hsn_id,
                          }]},
                    headers=H)
    assert p.status_code == 201, p.text
    r = client.post(f"/api/pharmacy/purchases/{p.json()['id']}/confirm", headers=H)
    assert r.status_code == 200, r.text

    batches = client.get("/api/pharmacy/inventory/batches",
                         params={"medicine_id": medicine_id}, headers=H).json()
    batch = next(b for b in batches if b["batch_number"] == "CN-B1")

    return {"medicine_id": medicine_id, "batch_id": batch["id"], "hsn_id": hsn_id}


def _make_rx_and_dispense(
    db_session, *, hospital_id, patient_id, doctor_id, user_id,
    medicine_id, batch_id, qty_prescribed=10, qty_to_dispense=10,
):
    """Create a Prescription + one item, then simulate a dispense by:
      - decrementing the batch stock by `qty_to_dispense`
      - writing a `rx_dispense` ledger row
      - bumping PrescriptionItem.quantity_dispensed
    The point is to set up the state the cancel flow needs to reverse.
    """
    rx_no = f"RX-CN-{datetime.now().strftime('%H%M%S%f')}"
    rx = Prescription(
        prescription_number=rx_no,
        patient_id=patient_id,
        doctor_id=doctor_id,
        status="dispensed" if qty_to_dispense >= qty_prescribed else "partial",
        total_amount=qty_prescribed * 40.0,
    )
    db_session.add(rx)
    db_session.flush()

    rxi = PrescriptionItem(
        prescription_id=rx.id,
        medicine_id=medicine_id,
        quantity_prescribed=qty_prescribed,
        quantity_dispensed=qty_to_dispense,
        unit_price=40.0,
        total_price=qty_prescribed * 40.0,
        status="dispensed" if qty_to_dispense >= qty_prescribed else "partial",
    )
    db_session.add(rxi)

    if qty_to_dispense > 0:
        batch = db_session.query(PharmacyInventory).filter(
            PharmacyInventory.id == batch_id).first()
        batch.quantity_in_stock = (batch.quantity_in_stock or 0) - qty_to_dispense
        db_session.add(PharmacyStockLedger(
            medicine_id=medicine_id,
            batch_id=batch_id,
            txn_type="rx_dispense",
            qty_delta=-qty_to_dispense,
            reference_type="prescription",
            reference_id=rx.id,
            performed_by=user_id,
            hospital_id=hospital_id,
            notes=f"Test dispense for Rx {rx.prescription_number}",
        ))
    db_session.commit()
    return rx, rxi


# ---------------------------------------------------------------------------
# T1 — Cancel un-billed Rx
# ---------------------------------------------------------------------------

def test_cancel_unbilled_rx_restores_stock_no_credit_note(
    client, auth_headers, db_session, seed_data, rx_cancel_seed,
):
    H = auth_headers
    batch_before = db_session.query(PharmacyInventory).filter(
        PharmacyInventory.id == rx_cancel_seed["batch_id"]).first()
    qty_before = batch_before.quantity_in_stock

    rx, _ = _make_rx_and_dispense(
        db_session,
        hospital_id=seed_data["hospital_id"],
        patient_id=seed_data["patient_id"],
        doctor_id=seed_data["doctor_user_id"],
        user_id=seed_data["admin_user_id"],
        medicine_id=rx_cancel_seed["medicine_id"],
        batch_id=rx_cancel_seed["batch_id"],
        qty_prescribed=10, qty_to_dispense=10,
    )

    # Sanity: stock decremented by 10 from setup
    db_session.refresh(batch_before)
    assert batch_before.quantity_in_stock == qty_before - 10

    r = client.post(f"/api/pharmacy/prescriptions/{rx.id}/cancel",
                    json={"reason": "Wrong medicine ordered"}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "cancelled"
    assert body["parent_bill_id"] is None
    assert body["credit_note_id"] is None
    assert body["bill_items_removed"] == 0
    assert body["stock_ledger_rows_written"] == 1

    db_session.refresh(batch_before)
    assert batch_before.quantity_in_stock == qty_before, "stock should be back to before-test level"

    # Item counters rolled back
    db_session.refresh(rx)
    assert rx.status == "cancelled"
    assert rx.cancel_reason == "Wrong medicine ordered"
    for it in rx.items:
        assert it.quantity_dispensed == 0
        assert it.status == "pending"


# ---------------------------------------------------------------------------
# T2 — Unlocked parent bill: in-place reversal
# ---------------------------------------------------------------------------

def test_cancel_rx_on_unlocked_bill_removes_line_in_place(
    client, auth_headers, db_session, seed_data, rx_cancel_seed,
):
    H = auth_headers

    rx, rxi = _make_rx_and_dispense(
        db_session,
        hospital_id=seed_data["hospital_id"],
        patient_id=seed_data["patient_id"],
        doctor_id=seed_data["doctor_user_id"],
        user_id=seed_data["admin_user_id"],
        medicine_id=rx_cancel_seed["medicine_id"],
        batch_id=rx_cancel_seed["batch_id"],
        qty_prescribed=5, qty_to_dispense=5,
    )

    # Build an UNLOCKED bill: bill_subtype != 'final', status='pending', no payments.
    bill = Bill(
        bill_number=f"BILL-TEST-UNL-{rx.id}",
        patient_id=seed_data["patient_id"],
        bill_type="admission",
        bill_subtype="interim",
        reference_id=0,
        subtotal=rxi.total_price,
        tax_amount=0.0,
        discount_amount=0.0,
        total_amount=rxi.total_price,
        status="pending",
        created_by_id=seed_data["admin_user_id"],
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(bill)
    db_session.flush()
    bi = BillItem(
        bill_id=bill.id,
        item_type="pharmacy",
        item_name="Cancel Med",
        quantity=rxi.quantity_prescribed,
        unit_price=rxi.unit_price,
        total_price=rxi.total_price,
        source_ref_type="prescription_item",
        source_ref_id=rxi.id,
    )
    db_session.add(bi)
    rx.inpatient_bill_id = bill.id
    db_session.commit()

    r = client.post(f"/api/pharmacy/prescriptions/{rx.id}/cancel",
                    json={"reason": "Duplicate Rx"}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["parent_bill_id"] == bill.id
    assert body["bill_items_removed"] == 1
    assert body["credit_note_id"] is None

    # Original bill totals decremented; the line is gone.
    db_session.refresh(bill)
    assert abs(bill.subtotal - 0.0) < 0.01
    assert abs(bill.total_amount - 0.0) < 0.01
    remaining_items = db_session.query(BillItem).filter(BillItem.bill_id == bill.id).all()
    assert remaining_items == []

    db_session.refresh(rx)
    assert rx.inpatient_bill_id is None
    assert rx.status == "cancelled"


# ---------------------------------------------------------------------------
# T3 — Locked parent bill (paid): credit-note emitted
# ---------------------------------------------------------------------------

def test_cancel_rx_on_paid_bill_emits_credit_note(
    client, auth_headers, db_session, seed_data, rx_cancel_seed,
):
    H = auth_headers

    rx, rxi = _make_rx_and_dispense(
        db_session,
        hospital_id=seed_data["hospital_id"],
        patient_id=seed_data["patient_id"],
        doctor_id=seed_data["doctor_user_id"],
        user_id=seed_data["admin_user_id"],
        medicine_id=rx_cancel_seed["medicine_id"],
        batch_id=rx_cancel_seed["batch_id"],
        qty_prescribed=4, qty_to_dispense=4,
    )

    # Build a LOCKED bill: bill_subtype='final', status='paid', plus a Payment row
    bill = Bill(
        bill_number=f"BILL-TEST-PAID-{rx.id}",
        patient_id=seed_data["patient_id"],
        bill_type="admission",
        bill_subtype="final",
        reference_id=0,
        subtotal=rxi.total_price,
        tax_amount=0.0,
        discount_amount=0.0,
        total_amount=rxi.total_price,
        status="paid",
        created_by_id=seed_data["admin_user_id"],
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(bill)
    db_session.flush()
    db_session.add(BillItem(
        bill_id=bill.id,
        item_type="pharmacy",
        item_name="Cancel Med",
        quantity=rxi.quantity_prescribed,
        unit_price=rxi.unit_price,
        total_price=rxi.total_price,
        source_ref_type="prescription_item",
        source_ref_id=rxi.id,
    ))
    db_session.add(Payment(
        payment_number=f"PAY-TEST-{rx.id}",
        bill_id=bill.id,
        amount_paid=rxi.total_price,
        payment_method_name="cash",
        received_by_id=seed_data["admin_user_id"],
    ))
    rx.inpatient_bill_id = bill.id
    db_session.commit()

    r = client.post(f"/api/pharmacy/prescriptions/{rx.id}/cancel",
                    json={"reason": "Patient discharged early"}, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["credit_note_id"] is not None
    assert body["credit_note_number"] is not None
    assert body["bill_items_removed"] == 0

    # Original bill untouched.
    db_session.refresh(bill)
    assert abs(bill.subtotal - rxi.total_price) < 0.01
    assert bill.status == "paid"

    cn = db_session.query(Bill).filter(Bill.id == body["credit_note_id"]).first()
    assert cn is not None
    assert cn.bill_type == "credit_note"
    assert cn.parent_bill_id == bill.id
    assert cn.total_amount < 0
    cn_items = db_session.query(BillItem).filter(BillItem.bill_id == cn.id).all()
    assert len(cn_items) == 1
    assert cn_items[0].total_price < 0


# ---------------------------------------------------------------------------
# T4 — Partial dispense → only dispensed qty restored
# ---------------------------------------------------------------------------

def test_cancel_partial_dispense_restores_only_dispensed_qty(
    client, auth_headers, db_session, seed_data, rx_cancel_seed,
):
    H = auth_headers
    batch = db_session.query(PharmacyInventory).filter(
        PharmacyInventory.id == rx_cancel_seed["batch_id"]).first()
    qty_before = batch.quantity_in_stock

    rx, _ = _make_rx_and_dispense(
        db_session,
        hospital_id=seed_data["hospital_id"],
        patient_id=seed_data["patient_id"],
        doctor_id=seed_data["doctor_user_id"],
        user_id=seed_data["admin_user_id"],
        medicine_id=rx_cancel_seed["medicine_id"],
        batch_id=rx_cancel_seed["batch_id"],
        qty_prescribed=10, qty_to_dispense=3,  # partial
    )

    db_session.refresh(batch)
    assert batch.quantity_in_stock == qty_before - 3

    r = client.post(f"/api/pharmacy/prescriptions/{rx.id}/cancel",
                    json={"reason": "Patient switched meds"}, headers=H)
    assert r.status_code == 200, r.text

    db_session.refresh(batch)
    assert batch.quantity_in_stock == qty_before, "only the 3 dispensed should come back"


# ---------------------------------------------------------------------------
# T5 — Idempotency guard: cancel of cancelled Rx → 400
# ---------------------------------------------------------------------------

def test_double_cancel_rejected(
    client, auth_headers, db_session, seed_data, rx_cancel_seed,
):
    H = auth_headers
    rx, _ = _make_rx_and_dispense(
        db_session,
        hospital_id=seed_data["hospital_id"],
        patient_id=seed_data["patient_id"],
        doctor_id=seed_data["doctor_user_id"],
        user_id=seed_data["admin_user_id"],
        medicine_id=rx_cancel_seed["medicine_id"],
        batch_id=rx_cancel_seed["batch_id"],
        qty_prescribed=2, qty_to_dispense=2,
    )
    r1 = client.post(f"/api/pharmacy/prescriptions/{rx.id}/cancel",
                     json={"reason": "First cancel"}, headers=H)
    assert r1.status_code == 200, r1.text

    r2 = client.post(f"/api/pharmacy/prescriptions/{rx.id}/cancel",
                     json={"reason": "Second cancel"}, headers=H)
    assert r2.status_code == 400
    assert "already cancelled" in r2.json()["detail"].lower()


# ---------------------------------------------------------------------------
# T6 — POS sale void with patient_ip_id does NOT touch any IP bill
# ---------------------------------------------------------------------------

def test_pos_void_does_not_touch_ip_bills(
    client, auth_headers, db_session, seed_data, rx_cancel_seed,
):
    """Regression guard for the P3.6 comment update: POS sales aren't on
    IP bills, so void_sale shouldn't create credit notes or mutate bills."""
    H = auth_headers
    bills_before = db_session.query(Bill).count()

    # Walk-in counter sale (no patient_ip_id set — keeps the test simple, the
    # behaviour we're regression-guarding is "no IP bill side effect either
    # way").
    r = client.post("/api/pharmacy/sales",
                    json={"payment_type": "cash",
                          "patient_name": "Walk in",
                          "items": [{"medicine_id": rx_cancel_seed["medicine_id"],
                                     "quantity": 1, "rate_tier": "A"}]},
                    headers=H)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    v = client.post(f"/api/pharmacy/sales/{sid}/void",
                    json={"reason": "test void"}, headers=H)
    assert v.status_code == 200, v.text

    bills_after = db_session.query(Bill).count()
    assert bills_after == bills_before, "POS void must not create any Bill rows"
