"""
Phase 1 hardening tests for the pharmacy purchase flow.

Covers:
  P1.1 duplicate (supplier, invoice_number) rejected on create AND edit;
       blank invoice numbers may repeat.
  P1.2 edit_purchase validates supplier belongs to current hospital.
  P1.3 confirm_purchase does NOT clobber Medicine.mrp/purchase_rate when an
       older back-dated entry is confirmed after a newer one.
  P1.4 cost_price stays in sync with purchase_rate when a batch is merged.
  P1.5 cost_price is the effective rate (paid spread over paid + free), so
       stock_value_cost no longer counts free units at gross rate.
  P1.6 revoke_purchase: full happy path, partial-sale path, master rollback.
  P1.7 edit_confirmed_purchase: requires reason, updates inventory, blocks invalid qty.
"""

import uuid
from datetime import date, timedelta

import pytest


# --------------------------------------------------------------------------
# Local fixture — pharmacy needs a supplier + category + medicine + hsn row.
# Scoped to the module so each test gets a fresh medicine (and we can sanity
# test cross-hospital flows without bleeding state).
# --------------------------------------------------------------------------

@pytest.fixture()
def pharmacy_setup(db_session, seed_data):
    from app.models.pharmacy import (
        MedicineCategory, Medicine, PharmacySupplier, PharmacyHSN,
    )
    hid = seed_data["hospital_id"]

    cat = MedicineCategory(name=f"Cat-{uuid.uuid4().hex[:6]}", hospital_id=hid)
    db_session.add(cat); db_session.flush()

    hsn = PharmacyHSN(code=f"H{uuid.uuid4().hex[:4]}", sgst_pct=6, cgst_pct=6, hospital_id=hid)
    db_session.add(hsn); db_session.flush()

    med = Medicine(
        medicine_code=f"M{uuid.uuid4().hex[:6]}", name=f"Med-{uuid.uuid4().hex[:4]}",
        unit_price=10.0, category_id=cat.id, hsn_id=hsn.id, hospital_id=hid,
    )
    db_session.add(med); db_session.flush()

    sup = PharmacySupplier(name=f"Sup-{uuid.uuid4().hex[:4]}", hospital_id=hid)
    db_session.add(sup); db_session.flush()

    db_session.commit()
    return {"category_id": cat.id, "medicine_id": med.id, "supplier_id": sup.id, "hsn_id": hsn.id}


def _purchase_payload(setup, *, invoice_number=None, entry_date=None, qty=10, free=0, rate=20.0, mrp=30.0):
    return {
        "entry_date": (entry_date or date.today()).isoformat(),
        "supplier_id": setup["supplier_id"],
        "invoice_number": invoice_number,
        "bill_date": None,
        "payment_type": "cash",
        "purchase_type": "local",
        "notes": None,
        "items": [{
            "medicine_id": setup["medicine_id"],
            "batch_number": f"B-{uuid.uuid4().hex[:5]}",
            "expiry_date": (date.today() + timedelta(days=365)).isoformat(),
            "mrp": mrp, "quantity": qty, "free_quantity": free,
            "purchase_rate": rate, "discount_pct": 0,
            "hsn_id": setup["hsn_id"],
        }],
    }


# --------------------------------------------------------------------------
# P1.1
# --------------------------------------------------------------------------

def test_duplicate_invoice_rejected_on_create(client, auth_headers, pharmacy_setup):
    inv = f"INV-{uuid.uuid4().hex[:6]}"
    r1 = client.post("/api/pharmacy/purchases", headers=auth_headers,
                     json=_purchase_payload(pharmacy_setup, invoice_number=inv))
    assert r1.status_code == 201, r1.text

    r2 = client.post("/api/pharmacy/purchases", headers=auth_headers,
                     json=_purchase_payload(pharmacy_setup, invoice_number=inv))
    assert r2.status_code == 400
    assert "already entered" in r2.json()["detail"].lower()


def test_blank_invoice_may_repeat(client, auth_headers, pharmacy_setup):
    """Cash purchases without an invoice number must not be rejected."""
    r1 = client.post("/api/pharmacy/purchases", headers=auth_headers,
                     json=_purchase_payload(pharmacy_setup, invoice_number=None))
    r2 = client.post("/api/pharmacy/purchases", headers=auth_headers,
                     json=_purchase_payload(pharmacy_setup, invoice_number=""))
    assert r1.status_code == 201 and r2.status_code == 201


def test_duplicate_invoice_rejected_on_edit(client, auth_headers, pharmacy_setup):
    inv_a = f"INV-{uuid.uuid4().hex[:6]}"
    inv_b = f"INV-{uuid.uuid4().hex[:6]}"
    r1 = client.post("/api/pharmacy/purchases", headers=auth_headers,
                     json=_purchase_payload(pharmacy_setup, invoice_number=inv_a))
    r2 = client.post("/api/pharmacy/purchases", headers=auth_headers,
                     json=_purchase_payload(pharmacy_setup, invoice_number=inv_b))
    pid_b = r2.json()["id"]

    # Edit B to take A's invoice → expect 400.
    body = _purchase_payload(pharmacy_setup, invoice_number=inv_a)
    rE = client.put(f"/api/pharmacy/purchases/{pid_b}", headers=auth_headers, json=body)
    assert rE.status_code == 400, rE.text

    # Editing B back to its own invoice must still succeed.
    body2 = _purchase_payload(pharmacy_setup, invoice_number=inv_b)
    rE2 = client.put(f"/api/pharmacy/purchases/{pid_b}", headers=auth_headers, json=body2)
    assert rE2.status_code == 200, rE2.text


# --------------------------------------------------------------------------
# P1.2
# --------------------------------------------------------------------------

def test_edit_purchase_rejects_cross_hospital_supplier(client, auth_headers, pharmacy_setup, db_session):
    from app.models.hospital import Hospital
    from app.models.pharmacy import PharmacySupplier

    other = Hospital(hospital_id=str(uuid.uuid4()), name=f"Other-{uuid.uuid4().hex[:4]}")
    db_session.add(other); db_session.flush()
    foreign = PharmacySupplier(name="Foreign", hospital_id=other.id)
    db_session.add(foreign); db_session.flush()
    db_session.commit()
    foreign_id = foreign.id

    r = client.post("/api/pharmacy/purchases", headers=auth_headers,
                    json=_purchase_payload(pharmacy_setup, invoice_number=f"INV-{uuid.uuid4().hex[:6]}"))
    pid = r.json()["id"]
    body = _purchase_payload(pharmacy_setup)
    body["supplier_id"] = foreign_id
    rE = client.put(f"/api/pharmacy/purchases/{pid}", headers=auth_headers, json=body)
    assert rE.status_code == 400, rE.text
    assert "supplier" in rE.json()["detail"].lower()


# --------------------------------------------------------------------------
# P1.3
# --------------------------------------------------------------------------

def test_back_dated_confirm_does_not_clobber_master(client, auth_headers, pharmacy_setup, db_session):
    from app.models.pharmacy import Medicine

    # Newer purchase first — sets master to (rate=20, mrp=30)
    p1 = client.post("/api/pharmacy/purchases", headers=auth_headers,
                     json=_purchase_payload(pharmacy_setup,
                                            invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
                                            entry_date=date.today(),
                                            rate=20.0, mrp=30.0)).json()
    assert client.post(f"/api/pharmacy/purchases/{p1['id']}/confirm",
                       headers=auth_headers).status_code == 200

    # Older back-dated purchase — must NOT overwrite master.
    p2 = client.post("/api/pharmacy/purchases", headers=auth_headers,
                     json=_purchase_payload(pharmacy_setup,
                                            invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
                                            entry_date=date.today() - timedelta(days=10),
                                            rate=5.0, mrp=8.0)).json()
    assert client.post(f"/api/pharmacy/purchases/{p2['id']}/confirm",
                       headers=auth_headers).status_code == 200

    db_session.expire_all()
    med = db_session.query(Medicine).filter(Medicine.id == pharmacy_setup["medicine_id"]).first()
    assert med.purchase_rate == 20.0, "back-dated purchase should not lower master rate"
    assert med.mrp == 30.0, "back-dated purchase should not lower master MRP"


# --------------------------------------------------------------------------
# P1.4 + P1.5
# --------------------------------------------------------------------------

def test_cost_price_synced_and_excludes_free_on_merge(client, auth_headers, pharmacy_setup, db_session):
    from app.models.pharmacy import PharmacyInventory

    batch_no = f"BX-{uuid.uuid4().hex[:5]}"

    def confirm(rate, free, mrp):
        body = _purchase_payload(pharmacy_setup,
                                 invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
                                 qty=10, free=free, rate=rate, mrp=mrp)
        body["items"][0]["batch_number"] = batch_no
        p = client.post("/api/pharmacy/purchases", headers=auth_headers, json=body).json()
        return client.post(f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers)

    # First receipt: 10 paid + 0 free at ₹20 → cost_price = 20.0
    assert confirm(20.0, 0, 30.0).status_code == 200
    db_session.expire_all()
    inv = db_session.query(PharmacyInventory).filter(PharmacyInventory.batch_number == batch_no).first()
    assert inv is not None and abs(inv.cost_price - 20.0) < 1e-6

    # Second receipt merges same batch — 10 paid + 2 free at ₹30.
    # Effective cost = (10 * 30) / (10 + 2) = 25.0 — strictly less than gross 30.
    assert confirm(30.0, 2, 35.0).status_code == 200
    db_session.expire_all()
    inv = db_session.query(PharmacyInventory).filter(PharmacyInventory.batch_number == batch_no).first()
    assert abs(inv.cost_price - 25.0) < 1e-6, f"expected 25.0, got {inv.cost_price}"
    # purchase_rate keeps the latest gross rate (used as master P-Rate default)
    assert abs(inv.purchase_rate - 30.0) < 1e-6


# --------------------------------------------------------------------------
# P1.6
# --------------------------------------------------------------------------

def test_revoke_full(client, auth_headers, pharmacy_setup, db_session):
    from app.models.pharmacy import PharmacyInventory

    p = client.post("/api/pharmacy/purchases", headers=auth_headers,
                    json=_purchase_payload(pharmacy_setup,
                                           invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
                                           qty=10, free=2)).json()
    client.post(f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers)

    r = client.post(f"/api/pharmacy/purchases/{p['id']}/revoke", headers=auth_headers,
                    json={"reason": "wrong supplier"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "revoked"
    assert body["fully_reversed"] is True
    assert body["items"][0]["reversed_qty"] == 12
    assert body["items"][0]["sold_qty"] == 0


def test_revoke_partial_after_sale(client, auth_headers, pharmacy_setup, db_session):
    from app.models.pharmacy import PharmacyInventory

    p = client.post("/api/pharmacy/purchases", headers=auth_headers,
                    json=_purchase_payload(pharmacy_setup,
                                           invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
                                           qty=10, free=0, rate=20.0, mrp=30.0)).json()
    client.post(f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers)

    # Sell 3 of the 10 units.
    sale = client.post("/api/pharmacy/sales", headers=auth_headers, json={
        "payment_type": "cash",
        "items": [{
            "medicine_id": pharmacy_setup["medicine_id"], "quantity": 3,
            "rate": 25.0, "rate_tier": "A",
        }],
    })
    assert sale.status_code == 201, sale.text

    r = client.post(f"/api/pharmacy/purchases/{p['id']}/revoke", headers=auth_headers,
                    json={"reason": "partial wrong entry"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "revoked_partial"
    assert body["fully_reversed"] is False
    item = body["items"][0]
    assert item["sold_qty"] == 3
    assert item["reversed_qty"] == 7


def test_revoke_nothing_left_to_reverse(client, auth_headers, pharmacy_setup):
    p = client.post("/api/pharmacy/purchases", headers=auth_headers,
                    json=_purchase_payload(pharmacy_setup,
                                           invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
                                           qty=2)).json()
    client.post(f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers)

    sale = client.post("/api/pharmacy/sales", headers=auth_headers, json={
        "payment_type": "cash",
        "items": [{"medicine_id": pharmacy_setup["medicine_id"], "quantity": 2, "rate": 25.0}],
    })
    assert sale.status_code == 201

    r = client.post(f"/api/pharmacy/purchases/{p['id']}/revoke", headers=auth_headers,
                    json={"reason": "everything already sold"})
    assert r.status_code == 400
    assert "nothing to revoke" in r.json()["detail"].lower()


# --------------------------------------------------------------------------
# P1.7 — confirmed purchase edit
# --------------------------------------------------------------------------

def test_edit_confirmed_requires_reason(client, auth_headers, pharmacy_setup):
    p = client.post("/api/pharmacy/purchases", headers=auth_headers,
                    json=_purchase_payload(pharmacy_setup,
                                           invoice_number=f"INV-{uuid.uuid4().hex[:6]}")).json()
    client.post(f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers)

    body = _purchase_payload(pharmacy_setup, invoice_number=p["invoice_number"])
    body["items"][0]["batch_number"] = p["items"][0]["batch_number"]
    r = client.put(f"/api/pharmacy/purchases/{p['id']}", headers=auth_headers, json=body)
    assert r.status_code == 400
    assert "reason" in r.json()["detail"].lower()


def test_edit_confirmed_updates_header_and_totals(client, auth_headers, pharmacy_setup, db_session):
    from app.models.pharmacy import PharmacyPurchase

    inv = f"INV-{uuid.uuid4().hex[:6]}"
    p = client.post("/api/pharmacy/purchases", headers=auth_headers,
                    json=_purchase_payload(pharmacy_setup, invoice_number=inv,
                                           rate=20.0, mrp=30.0, qty=10)).json()
    client.post(f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers)

    body = _purchase_payload(pharmacy_setup, invoice_number=inv, rate=25.0, mrp=35.0, qty=12)
    body["items"][0]["batch_number"] = p["items"][0]["batch_number"]
    body["reason"] = "invoice rate correction"
    body["notes"] = "corrected per supplier bill"
    r = client.put(f"/api/pharmacy/purchases/{p['id']}", headers=auth_headers, json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "confirmed"
    assert data["notes"] == "corrected per supplier bill"
    assert data["edit_reason"] == "invoice rate correction"
    assert data["items"][0]["quantity"] == 12
    assert data["grand_total"] > p["grand_total"]

    db_session.expire_all()
    row = db_session.query(PharmacyPurchase).filter(PharmacyPurchase.id == p["id"]).first()
    assert row.edit_reason == "invoice rate correction"
    assert row.edited_by is not None


def test_edit_confirmed_updates_purchase_ledger_in_place(
    client, auth_headers, pharmacy_setup, db_session,
):
    """Qty edit updates the single purchase ledger row — no reverse/−old +new."""
    from app.models.pharmacy import PharmacyInventory, PharmacyStockLedger

    inv_no = f"INV-{uuid.uuid4().hex[:6]}"
    p = client.post("/api/pharmacy/purchases", headers=auth_headers,
                    json=_purchase_payload(pharmacy_setup, invoice_number=inv_no, qty=10)).json()
    batch = p["items"][0]["batch_number"]
    assert client.post(
        f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers,
    ).status_code == 200

    body = _purchase_payload(pharmacy_setup, invoice_number=inv_no, qty=12)
    body["items"][0]["batch_number"] = batch
    body["items"][0]["expiry_date"] = p["items"][0]["expiry_date"]
    body["reason"] = "invoice qty correction"
    r = client.put(f"/api/pharmacy/purchases/{p['id']}", headers=auth_headers, json=body)
    assert r.status_code == 200, r.text

    db_session.expire_all()
    inv = db_session.query(PharmacyInventory).filter(
        PharmacyInventory.batch_number == batch,
    ).first()
    assert inv is not None
    assert inv.quantity_in_stock == 12

    ledgers = db_session.query(PharmacyStockLedger).filter(
        PharmacyStockLedger.batch_id == inv.id,
        PharmacyStockLedger.reference_type == "purchase",
        PharmacyStockLedger.reference_id == p["id"],
    ).all()
    assert len(ledgers) == 1
    assert ledgers[0].txn_type == "purchase"
    assert ledgers[0].qty_delta == 12
    assert "invoice qty correction" in (ledgers[0].notes or "").lower()

    reverse_rows = db_session.query(PharmacyStockLedger).filter(
        PharmacyStockLedger.batch_id == inv.id,
        PharmacyStockLedger.txn_type == "purchase_edit_reverse",
    ).count()
    assert reverse_rows == 0


def test_edit_confirmed_collapses_legacy_reverse_recreate(
    client, auth_headers, pharmacy_setup, db_session,
):
    """Re-editing a purchase that still has legacy reverse rows collapses them."""
    from app.models.pharmacy import PharmacyInventory, PharmacyStockLedger

    inv_no = f"INV-{uuid.uuid4().hex[:6]}"
    p = client.post("/api/pharmacy/purchases", headers=auth_headers,
                    json=_purchase_payload(pharmacy_setup, invoice_number=inv_no, qty=10)).json()
    batch = p["items"][0]["batch_number"]
    assert client.post(
        f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers,
    ).status_code == 200

    db_session.expire_all()
    inv = db_session.query(PharmacyInventory).filter(
        PharmacyInventory.batch_number == batch,
    ).first()
    # Simulate legacy reverse-then-recreate leftover rows.
    db_session.add(PharmacyStockLedger(
        medicine_id=pharmacy_setup["medicine_id"], batch_id=inv.id,
        txn_type="purchase_edit_reverse", qty_delta=-10,
        reference_type="purchase", reference_id=p["id"],
        hospital_id=inv.hospital_id, store_id=inv.store_id,
        notes="legacy reverse",
    ))
    db_session.add(PharmacyStockLedger(
        medicine_id=pharmacy_setup["medicine_id"], batch_id=inv.id,
        txn_type="purchase", qty_delta=10,
        reference_type="purchase", reference_id=p["id"],
        hospital_id=inv.hospital_id, store_id=inv.store_id,
        notes="legacy re-credit",
    ))
    db_session.commit()

    body = _purchase_payload(pharmacy_setup, invoice_number=inv_no, qty=12)
    body["items"][0]["batch_number"] = batch
    body["items"][0]["expiry_date"] = p["items"][0]["expiry_date"]
    body["reason"] = "cleanup after legacy edits"
    r = client.put(f"/api/pharmacy/purchases/{p['id']}", headers=auth_headers, json=body)
    assert r.status_code == 200, r.text

    db_session.expire_all()
    inv = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == inv.id).first()
    assert inv.quantity_in_stock == 12

    ledgers = (
        db_session.query(PharmacyStockLedger)
        .filter(
            PharmacyStockLedger.batch_id == inv.id,
            PharmacyStockLedger.reference_type == "purchase",
            PharmacyStockLedger.reference_id == p["id"],
        )
        .order_by(PharmacyStockLedger.id.asc())
        .all()
    )
    assert len(ledgers) == 1
    assert ledgers[0].txn_type == "purchase"
    assert ledgers[0].qty_delta == 12


def test_delete_legacy_ledger_reverse_and_duplicate_purchase(
    client, auth_headers, pharmacy_setup, db_session,
):
    """Operators can delete reverse / duplicate purchase credits without touching stock."""
    from app.models.pharmacy import PharmacyInventory, PharmacyStockLedger

    inv_no = f"INV-{uuid.uuid4().hex[:6]}"
    p = client.post("/api/pharmacy/purchases", headers=auth_headers,
                    json=_purchase_payload(pharmacy_setup, invoice_number=inv_no, qty=10)).json()
    batch = p["items"][0]["batch_number"]
    assert client.post(
        f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers,
    ).status_code == 200

    db_session.expire_all()
    inv = db_session.query(PharmacyInventory).filter(
        PharmacyInventory.batch_number == batch,
    ).first()
    stock_before = float(inv.quantity_in_stock)

    reverse = PharmacyStockLedger(
        medicine_id=pharmacy_setup["medicine_id"], batch_id=inv.id,
        txn_type="purchase_edit_reverse", qty_delta=-10,
        reference_type="purchase", reference_id=p["id"],
        hospital_id=inv.hospital_id, store_id=inv.store_id,
        notes="legacy reverse",
    )
    dup = PharmacyStockLedger(
        medicine_id=pharmacy_setup["medicine_id"], batch_id=inv.id,
        txn_type="purchase", qty_delta=10,
        reference_type="purchase", reference_id=p["id"],
        hospital_id=inv.hospital_id, store_id=inv.store_id,
        notes="legacy re-credit",
    )
    db_session.add(reverse)
    db_session.add(dup)
    db_session.commit()
    reverse_id, dup_id = reverse.id, dup.id

    listed = client.get(
        "/api/pharmacy/inventory/ledger",
        headers=auth_headers,
        params={"medicine_id": pharmacy_setup["medicine_id"], "batch_id": inv.id},
    ).json()
    by_id = {row["id"]: row for row in listed}
    assert by_id[reverse_id]["can_delete"] is True
    assert by_id[dup_id]["can_delete"] is True
    # Only one purchase credit would not be deletable — with a duplicate both are.
    purchase_only = [
        row for row in listed
        if row["txn_type"] == "purchase" and row["reference_id"] == p["id"]
    ]
    assert len(purchase_only) == 2
    assert all(row["can_delete"] for row in purchase_only)

    r = client.delete(f"/api/pharmacy/inventory/ledger/{reverse_id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    r = client.delete(f"/api/pharmacy/inventory/ledger/{dup_id}", headers=auth_headers)
    assert r.status_code == 200, r.text

    db_session.expire_all()
    inv = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == inv.id).first()
    assert float(inv.quantity_in_stock) == stock_before

    remaining = db_session.query(PharmacyStockLedger).filter(
        PharmacyStockLedger.batch_id == inv.id,
        PharmacyStockLedger.reference_type == "purchase",
        PharmacyStockLedger.reference_id == p["id"],
    ).all()
    assert len(remaining) == 1
    assert remaining[0].txn_type == "purchase"
    assert remaining[0].qty_delta == 10

    # Sole remaining purchase credit cannot be deleted.
    r = client.delete(f"/api/pharmacy/inventory/ledger/{remaining[0].id}", headers=auth_headers)
    assert r.status_code == 400
    assert "only purchase credit" in r.json()["detail"].lower()

    # Sales / other txn types cannot be deleted.
    sale_led = PharmacyStockLedger(
        medicine_id=pharmacy_setup["medicine_id"], batch_id=inv.id,
        txn_type="sale", qty_delta=-1,
        reference_type="sale", reference_id=1,
        hospital_id=inv.hospital_id, store_id=inv.store_id,
    )
    db_session.add(sale_led)
    db_session.commit()
    r = client.delete(f"/api/pharmacy/inventory/ledger/{sale_led.id}", headers=auth_headers)
    assert r.status_code == 400


def test_edit_confirmed_blocks_qty_below_sold(client, auth_headers, pharmacy_setup):
    p = client.post("/api/pharmacy/purchases", headers=auth_headers,
                    json=_purchase_payload(pharmacy_setup,
                                           invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
                                           qty=10)).json()
    batch = p["items"][0]["batch_number"]
    client.post(f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers)

    sale = client.post("/api/pharmacy/sales", headers=auth_headers, json={
        "payment_type": "cash",
        "items": [{"medicine_id": pharmacy_setup["medicine_id"], "quantity": 4, "rate": 25.0}],
    })
    assert sale.status_code == 201

    body = _purchase_payload(pharmacy_setup, invoice_number=p["invoice_number"], qty=3)
    body["items"][0]["batch_number"] = batch
    body["reason"] = "try to shrink below sold"
    r = client.put(f"/api/pharmacy/purchases/{p['id']}", headers=auth_headers, json=body)
    assert r.status_code == 400
    assert "sold" in r.json()["detail"].lower() or "dispensed" in r.json()["detail"].lower()


# --------------------------------------------------------------------------
# Strip conversion — purchase qty is strips; stock is base tablets
# --------------------------------------------------------------------------

def test_purchase_credits_stock_as_strips_times_tabs_per_strip(
    client, auth_headers, pharmacy_setup, db_session,
):
    """Buying 10 strips × 10 tabs/strip must credit 100 tablets (Gabanist-style)."""
    from app.models.pharmacy import PharmacyInventory, PharmacyStockLedger

    body = _purchase_payload(
        pharmacy_setup,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        qty=10, free=0, rate=80.5, mrp=100.0,
    )
    body["items"][0]["strip_conversion_factor"] = 10
    body["items"][0]["rate_a"] = 90.0
    p = client.post("/api/pharmacy/purchases", headers=auth_headers, json=body).json()
    assert client.post(
        f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers,
    ).status_code == 200

    db_session.expire_all()
    inv = db_session.query(PharmacyInventory).filter(
        PharmacyInventory.batch_number == body["items"][0]["batch_number"],
    ).first()
    assert inv is not None
    assert inv.quantity_in_stock == 100
    assert inv.strip_conversion_factor == 10
    # P-Rate stays per-strip; cost_price is per tablet (80.5 / 10)
    assert abs(inv.purchase_rate - 80.5) < 1e-6
    assert abs(inv.cost_price - 8.05) < 1e-6

    led = db_session.query(PharmacyStockLedger).filter(
        PharmacyStockLedger.batch_id == inv.id,
        PharmacyStockLedger.txn_type == "purchase",
    ).one()
    assert led.qty_delta == 100

    # Sell 1 strip → 10 tabs remaining stock 90
    sale = client.post("/api/pharmacy/sales", headers=auth_headers, json={
        "payment_type": "cash",
        "items": [{
            "medicine_id": pharmacy_setup["medicine_id"],
            "qty_tabs": 0, "qty_strips": 1, "rate_tier": "A",
        }],
    })
    assert sale.status_code == 201, sale.text
    db_session.expire_all()
    inv = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == inv.id).first()
    assert inv.quantity_in_stock == 90


def test_revoke_uses_strip_converted_received_qty(
    client, auth_headers, pharmacy_setup, db_session,
):
    from app.models.pharmacy import PharmacyInventory

    body = _purchase_payload(
        pharmacy_setup,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        qty=5, free=1, rate=20.0, mrp=30.0,
    )
    body["items"][0]["strip_conversion_factor"] = 10
    p = client.post("/api/pharmacy/purchases", headers=auth_headers, json=body).json()
    client.post(f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers)

    db_session.expire_all()
    inv = db_session.query(PharmacyInventory).filter(
        PharmacyInventory.batch_number == body["items"][0]["batch_number"],
    ).first()
    assert inv.quantity_in_stock == 60  # (5+1) × 10

    r = client.post(
        f"/api/pharmacy/purchases/{p['id']}/revoke",
        headers=auth_headers, json={"reason": "wrong strip entry"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["received_qty"] == 60
    assert r.json()["items"][0]["reversed_qty"] == 60
    db_session.expire_all()
    inv = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == inv.id).first()
    assert inv.quantity_in_stock == 0


# --------------------------------------------------------------------------
# Delete revoked purchases
# --------------------------------------------------------------------------

def test_delete_revoked_purchase(client, auth_headers, pharmacy_setup, db_session):
    from app.models.pharmacy import PharmacyPurchase, PharmacyInventory

    p = client.post("/api/pharmacy/purchases", headers=auth_headers,
                    json=_purchase_payload(pharmacy_setup,
                                           invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
                                           qty=10)).json()
    client.post(f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers)
    client.post(f"/api/pharmacy/purchases/{p['id']}/revoke", headers=auth_headers,
                json={"reason": "cleanup"})

    r = client.delete(f"/api/pharmacy/purchases/{p['id']}", headers=auth_headers)
    assert r.status_code == 204, r.text

    db_session.expire_all()
    assert db_session.query(PharmacyPurchase).filter(PharmacyPurchase.id == p["id"]).first() is None
    # Batches remain (purchase_id cleared); stock was already reversed to 0.
    inv = db_session.query(PharmacyInventory).filter(
        PharmacyInventory.medicine_id == pharmacy_setup["medicine_id"],
    ).first()
    assert inv is not None
    assert inv.purchase_id is None
    assert float(inv.quantity_in_stock or 0) == 0


def test_delete_revoked_partial_keeps_sale_batch(client, auth_headers, pharmacy_setup, db_session):
    from app.models.pharmacy import PharmacyPurchase, PharmacySaleItem

    p = client.post("/api/pharmacy/purchases", headers=auth_headers,
                    json=_purchase_payload(pharmacy_setup,
                                           invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
                                           qty=10)).json()
    client.post(f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers)
    sale = client.post("/api/pharmacy/sales", headers=auth_headers, json={
        "payment_type": "cash",
        "items": [{"medicine_id": pharmacy_setup["medicine_id"], "quantity": 3, "rate": 25.0}],
    })
    assert sale.status_code == 201, sale.text
    client.post(f"/api/pharmacy/purchases/{p['id']}/revoke", headers=auth_headers,
                json={"reason": "partial cleanup"})

    r = client.delete(f"/api/pharmacy/purchases/{p['id']}", headers=auth_headers)
    assert r.status_code == 204, r.text

    db_session.expire_all()
    assert db_session.query(PharmacyPurchase).filter(PharmacyPurchase.id == p["id"]).first() is None
    assert db_session.query(PharmacySaleItem).filter(
        PharmacySaleItem.medicine_id == pharmacy_setup["medicine_id"],
    ).count() == 1


def test_delete_confirmed_purchase_rejected(client, auth_headers, pharmacy_setup):
    p = client.post("/api/pharmacy/purchases", headers=auth_headers,
                    json=_purchase_payload(pharmacy_setup,
                                           invoice_number=f"INV-{uuid.uuid4().hex[:6]}")).json()
    client.post(f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers)

    r = client.delete(f"/api/pharmacy/purchases/{p['id']}", headers=auth_headers)
    assert r.status_code == 400
    assert "revoked" in r.json()["detail"].lower()


def test_purge_soft_deleted_medicine(client, auth_headers, pharmacy_setup, db_session):
    from app.models.pharmacy import Medicine

    mid = pharmacy_setup["medicine_id"]
    # Soft-delete first
    r = client.delete(f"/api/pharmacy/medicines/{mid}", headers=auth_headers)
    assert r.status_code == 204, r.text
    db_session.expire_all()
    assert db_session.query(Medicine).filter(Medicine.id == mid).first().is_active is False

    # Permanent purge (no stock/sales — medicine never purchased)
    r = client.delete(f"/api/pharmacy/medicines/{mid}", headers=auth_headers,
                      params={"permanent": True})
    assert r.status_code == 204, r.text
    db_session.expire_all()
    assert db_session.query(Medicine).filter(Medicine.id == mid).first() is None


def test_purge_medicine_blocked_when_stock_remains(client, auth_headers, pharmacy_setup):
    mid = pharmacy_setup["medicine_id"]
    p = client.post("/api/pharmacy/purchases", headers=auth_headers,
                    json=_purchase_payload(pharmacy_setup,
                                           invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
                                           qty=5)).json()
    client.post(f"/api/pharmacy/purchases/{p['id']}/confirm", headers=auth_headers)

    assert client.delete(f"/api/pharmacy/medicines/{mid}", headers=auth_headers).status_code == 204
    r = client.delete(f"/api/pharmacy/medicines/{mid}", headers=auth_headers,
                      params={"permanent": True})
    assert r.status_code == 400
    detail = r.json()["detail"].lower()
    assert "stock" in detail or "purchase" in detail


def test_purchase_bill_discount_amount_after_tax(client, auth_headers, pharmacy_setup):
    """Global ₹ discount is taken off grand after line GST, not off each line."""
    body = _purchase_payload(pharmacy_setup, invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
                             qty=10, rate=20.0)
    body["tax_mode"] = "exclusive"
    body["bill_discount_amount"] = 50
    r = client.post("/api/pharmacy/purchases", headers=auth_headers, json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    # 10 × 20 = 200; HSN 6+6 = 12% exclusive → tax 24, lines grand 224; −50 = 174
    assert data["subtotal"] == pytest.approx(200)
    assert data["total_tax"] == pytest.approx(24)
    assert data["bill_discount_amount"] == pytest.approx(50)
    assert data["grand_total"] == pytest.approx(174)
    assert data["total_discount"] == pytest.approx(50)

    got = client.get(f"/api/pharmacy/purchases/{data['id']}", headers=auth_headers).json()
    assert got["bill_discount_amount"] == pytest.approx(50)
    assert got["grand_total"] == pytest.approx(174)


def test_purchase_bill_discount_pct_wins_over_amount(client, auth_headers, pharmacy_setup):
    body = _purchase_payload(pharmacy_setup, invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
                             qty=10, rate=20.0)
    body["tax_mode"] = "exclusive"
    body["bill_discount_pct"] = 10
    body["bill_discount_amount"] = 9999
    r = client.post("/api/pharmacy/purchases", headers=auth_headers, json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    # 10% of 224 = 22.40
    assert data["bill_discount_pct"] == pytest.approx(10)
    assert data["bill_discount_amount"] == pytest.approx(22.4)
    assert data["grand_total"] == pytest.approx(201.6)


def test_medicine_purchase_history(client, auth_headers, pharmacy_setup):
    """Confirmed purchase lines appear on medicine purchase-history (newest first)."""
    batch_a = f"B-A-{uuid.uuid4().hex[:4]}"
    batch_b = f"B-B-{uuid.uuid4().hex[:4]}"
    body_a = _purchase_payload(
        pharmacy_setup,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        entry_date=date.today() - timedelta(days=2),
        qty=10,
        free=2,
        rate=95.55,
    )
    body_a["items"][0]["batch_number"] = batch_a
    r_a = client.post("/api/pharmacy/purchases", headers=auth_headers, json=body_a)
    assert r_a.status_code == 201, r_a.text
    assert client.post(f"/api/pharmacy/purchases/{r_a.json()['id']}/confirm",
                       headers=auth_headers).status_code == 200

    body_b = _purchase_payload(
        pharmacy_setup,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        entry_date=date.today() - timedelta(days=1),
        qty=5,
        rate=88.0,
    )
    body_b["items"][0]["batch_number"] = batch_b
    r_b = client.post("/api/pharmacy/purchases", headers=auth_headers, json=body_b)
    assert r_b.status_code == 201, r_b.text
    assert client.post(f"/api/pharmacy/purchases/{r_b.json()['id']}/confirm",
                       headers=auth_headers).status_code == 200

    mid = pharmacy_setup["medicine_id"]
    hist = client.get(f"/api/pharmacy/medicines/{mid}/purchase-history", headers=auth_headers)
    assert hist.status_code == 200, hist.text
    rows = hist.json()
    assert len(rows) >= 2
    assert rows[0]["batch_number"] == batch_b
    assert rows[0]["quantity"] == pytest.approx(5)
    assert rows[0]["quantity_in_stock"] > 0

    older = next(r for r in rows if r["batch_number"] == batch_a)
    assert older["quantity"] == pytest.approx(10)
    assert older["free_quantity"] == pytest.approx(2)
    assert older["purchase_rate"] == pytest.approx(95.55)

    draft = client.post(
        "/api/pharmacy/purchases",
        headers=auth_headers,
        json=_purchase_payload(pharmacy_setup, invoice_number=f"INV-{uuid.uuid4().hex[:6]}"),
    )
    assert draft.status_code == 201
    draft_batch = draft.json()["items"][0]["batch_number"]
    hist2 = client.get(f"/api/pharmacy/medicines/{mid}/purchase-history", headers=auth_headers)
    assert not any(r["batch_number"] == draft_batch for r in hist2.json())
