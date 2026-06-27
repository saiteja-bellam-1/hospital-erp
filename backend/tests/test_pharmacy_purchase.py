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
