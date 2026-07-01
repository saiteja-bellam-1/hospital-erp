"""Medicine and purchase prices are stored and computed to 2 decimal places."""

import uuid

from app.utils.pharmacy_pricing import round_money, tab_sale_rate, cost_pcs_from_mrp


def test_round_money_two_decimals():
    assert round_money(12.345) == 12.35
    assert round_money(12.344) == 12.34
    assert round_money(None) == 0.0


def test_cost_pcs_from_mrp_rounds():
    # 100 / 3 tabs → 33.33 per tab
    assert cost_pcs_from_mrp(100.0, 3) == 33.33


def test_medicine_create_rounds_prices(client, auth_headers, db_session, seed_data):
    from app.models.pharmacy import MedicineCategory, Medicine

    hid = seed_data["hospital_id"]
    cat = MedicineCategory(name=f"Cat-{uuid.uuid4().hex[:6]}", hospital_id=hid)
    db_session.add(cat)
    db_session.commit()

    code = f"M{uuid.uuid4().hex[:6]}"
    r = client.post("/api/pharmacy/medicines", headers=auth_headers, json={
        "medicine_code": code,
        "name": "Decimal Med",
        "category_id": cat.id,
        "mrp": 99.999,
        "purchase_rate": 45.556,
        "rate_a": 12.345,
        "rate_b": 11.111,
        "strip_conversion_factor": 3,
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["mrp"] == 100.0
    assert data["purchase_rate"] == 45.56
    assert data["rate_a"] == 12.35
    assert data["rate_b"] == 11.11
    assert data["cost_pcs"] == 33.33

    db_session.expire_all()
    med = db_session.query(Medicine).filter(Medicine.medicine_code == code).first()
    assert tab_sale_rate(med) == 4.12  # 12.35 / 3


def test_purchase_line_prices_rounded(client, auth_headers, db_session, seed_data):
    from app.models.pharmacy import MedicineCategory, Medicine, PharmacySupplier, PharmacyHSN

    hid = seed_data["hospital_id"]
    cat = MedicineCategory(name=f"Cat-{uuid.uuid4().hex[:6]}", hospital_id=hid)
    db_session.add(cat)
    db_session.flush()
    hsn = PharmacyHSN(code=f"H{uuid.uuid4().hex[:4]}", sgst_pct=6, cgst_pct=6, hospital_id=hid)
    db_session.add(hsn)
    db_session.flush()
    med = Medicine(
        medicine_code=f"M{uuid.uuid4().hex[:6]}", name=f"Med-{uuid.uuid4().hex[:4]}",
        unit_price=10.0, category_id=cat.id, hsn_id=hsn.id, hospital_id=hid,
    )
    db_session.add(med)
    db_session.flush()
    sup = PharmacySupplier(name=f"Sup-{uuid.uuid4().hex[:4]}", hospital_id=hid)
    db_session.add(sup)
    db_session.commit()

    payload = {
        "entry_date": "2026-01-15",
        "supplier_id": sup.id,
        "invoice_number": f"INV-{uuid.uuid4().hex[:6]}",
        "payment_type": "cash",
        "items": [{
            "medicine_id": med.id,
            "batch_number": f"B-{uuid.uuid4().hex[:5]}",
            "mrp": 25.999,
            "quantity": 10,
            "free_quantity": 0,
            "purchase_rate": 18.876,
            "discount_pct": 5.555,
        }],
    }
    r = client.post("/api/pharmacy/purchases", headers=auth_headers, json=payload)
    assert r.status_code == 201, r.text
    item = r.json()["items"][0]
    assert item["mrp"] == 26.0
    assert item["purchase_rate"] == 18.88
    assert item["discount_pct"] == 5.55
