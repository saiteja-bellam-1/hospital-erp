"""Regression tests for pharmacy billing/inventory audit fixes (2026-08)."""

import uuid
from datetime import date

import pytest


@pytest.fixture()
def audit_setup(db_session, seed_data):
    from app.models.pharmacy import MedicineCategory, Medicine, PharmacySupplier, PharmacyHSN

    hid = seed_data["hospital_id"]
    cat = MedicineCategory(name=f"ACat-{uuid.uuid4().hex[:5]}", hospital_id=hid)
    db_session.add(cat)
    db_session.flush()
    hsn = PharmacyHSN(code=f"A{uuid.uuid4().hex[:4]}", sgst_pct=6, cgst_pct=6, hospital_id=hid)
    db_session.add(hsn)
    db_session.flush()
    med = Medicine(
        medicine_code=f"A{uuid.uuid4().hex[:6]}",
        name=f"AMed-{uuid.uuid4().hex[:4]}",
        unit_price=10.0,
        rate_a=10.0,
        mrp=10.0,
        strip_conversion_factor=1,
        category_id=cat.id,
        hsn_id=hsn.id,
        hospital_id=hid,
    )
    db_session.add(med)
    db_session.flush()
    sup = PharmacySupplier(name=f"ASup-{uuid.uuid4().hex[:4]}", hospital_id=hid)
    db_session.add(sup)
    db_session.flush()
    db_session.commit()
    return {
        "medicine_id": med.id,
        "supplier_id": sup.id,
        "hsn_id": hsn.id,
        "hospital_id": hid,
    }


def _confirm_purchase(client, headers, setup, *, qty=100, rate=5.0, batch=None):
    body = {
        "entry_date": date.today().isoformat(),
        "supplier_id": setup["supplier_id"],
        "invoice_number": f"INV-{uuid.uuid4().hex[:6]}",
        "bill_date": None,
        "payment_type": "cash",
        "purchase_type": "local",
        "notes": None,
        "items": [{
            "medicine_id": setup["medicine_id"],
            "batch_number": batch or f"B-{uuid.uuid4().hex[:5]}",
            "expiry_date": "2028-12-31",
            "mrp": 10.0,
            "quantity": qty,
            "free_quantity": 0,
            "purchase_rate": rate,
            "discount_pct": 0,
            "hsn_id": setup["hsn_id"],
            "rate_a": 10.0,
            "strip_conversion_factor": 1,
        }],
    }
    p = client.post("/api/pharmacy/purchases", headers=headers, json=body).json()
    c = client.post(f"/api/pharmacy/purchases/{p['id']}/confirm", headers=headers)
    assert c.status_code == 200, c.text
    return p["id"]


def test_void_then_revoke_purchase_fully_reverses(client, auth_headers, audit_setup, db_session):
    """Sold qty must net out return_in so revoke after void clears phantom stock."""
    from app.models.pharmacy import PharmacyInventory

    pid = _confirm_purchase(client, auth_headers, audit_setup, qty=50)
    sale = client.post("/api/pharmacy/sales", headers=auth_headers, json={
        "payment_type": "cash",
        "tax_mode": "exclusive",
        "items": [{"medicine_id": audit_setup["medicine_id"], "quantity": 20, "rate": 10.0}],
    })
    assert sale.status_code == 201, sale.text
    sid = sale.json()["id"]
    void = client.post(f"/api/pharmacy/sales/{sid}/void", headers=auth_headers, json={"reason": "audit void"})
    assert void.status_code == 200, void.text

    rev = client.post(
        f"/api/pharmacy/purchases/{pid}/revoke",
        headers=auth_headers,
        json={"reason": "audit revoke"},
    )
    assert rev.status_code == 200, rev.text
    assert rev.json()["fully_reversed"] is True

    db_session.expire_all()
    batches = db_session.query(PharmacyInventory).filter(
        PharmacyInventory.medicine_id == audit_setup["medicine_id"],
    ).all()
    assert sum(float(b.quantity_in_stock or 0) for b in batches) == 0


def test_bill_discount_persisted_and_edit_restores(client, auth_headers, audit_setup):
    _confirm_purchase(client, auth_headers, audit_setup, qty=30)
    created = client.post("/api/pharmacy/sales", headers=auth_headers, json={
        "payment_type": "cash",
        "tax_mode": "exclusive",
        "bill_discount_amount": 5.0,
        "items": [{"medicine_id": audit_setup["medicine_id"], "quantity": 10, "rate": 10.0}],
    })
    assert created.status_code == 201, created.text
    body = created.json()
    assert float(body["bill_discount_amount"]) == pytest.approx(5.0)
    assert float(body["grand_total"]) < float(body["subtotal"]) + float(body["tax_total"])

    got = client.get(f"/api/pharmacy/sales/{body['id']}", headers=auth_headers)
    assert float(got.json()["bill_discount_amount"]) == pytest.approx(5.0)


def test_strip_exact_tabs_match_strip_price(client, auth_headers, audit_setup, db_session):
    """scf=3, strip ₹10, sell 3 tabs → ₹10.00 not ₹9.99."""
    from app.models.pharmacy import Medicine

    med = db_session.query(Medicine).filter(Medicine.id == audit_setup["medicine_id"]).first()
    med.strip_conversion_factor = 3
    med.rate_a = 10.0
    med.mrp = 10.0
    db_session.commit()

    _confirm_purchase(client, auth_headers, audit_setup, qty=30)
    r = client.post("/api/pharmacy/sales", headers=auth_headers, json={
        "payment_type": "cash",
        "tax_mode": "exclusive",
        "items": [{
            "medicine_id": audit_setup["medicine_id"],
            "qty_tabs": 3,
            "qty_strips": 0,
            "rate": 10.0,
        }],
    })
    assert r.status_code == 201, r.text
    # exclusive 12% GST on 10 → grand 11.20
    assert float(r.json()["subtotal"]) == pytest.approx(10.0, abs=0.01)


def test_sale_has_store_id_on_cash_dispense_path_not_applicable_without_rx(client, auth_headers, audit_setup):
    _confirm_purchase(client, auth_headers, audit_setup, qty=10)
    r = client.post("/api/pharmacy/sales", headers=auth_headers, json={
        "payment_type": "cash",
        "items": [{"medicine_id": audit_setup["medicine_id"], "quantity": 1, "rate": 10.0}],
    })
    assert r.status_code == 201, r.text
    assert r.json().get("store_id") is not None
