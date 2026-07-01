"""HSN master validation and purchase tax derivation from medicine."""

import uuid

import pytest


def test_duplicate_hsn_code_rejected(client, auth_headers):
    code = f"30{uuid.uuid4().hex[:6]}"
    body = {"code": code, "description": "Test HSN", "sgst_pct": 6, "cgst_pct": 6}
    r1 = client.post("/api/pharmacy/hsn", headers=auth_headers, json=body)
    assert r1.status_code == 201, r1.text

    r2 = client.post("/api/pharmacy/hsn", headers=auth_headers, json=body)
    assert r2.status_code == 400
    assert "already exists" in r2.json()["detail"].lower()


def test_duplicate_hsn_code_case_insensitive(client, auth_headers):
    code = f"30{uuid.uuid4().hex[:6]}"
    r1 = client.post("/api/pharmacy/hsn", headers=auth_headers,
                     json={"code": code.lower(), "sgst_pct": 6, "cgst_pct": 6})
    assert r1.status_code == 201, r1.text

    r2 = client.post("/api/pharmacy/hsn", headers=auth_headers,
                     json={"code": code.upper(), "sgst_pct": 6, "cgst_pct": 6})
    assert r2.status_code == 400


def test_purchase_tax_from_medicine_hsn(client, auth_headers, db_session, seed_data):
    from app.models.pharmacy import MedicineCategory, Medicine, PharmacySupplier, PharmacyHSN

    hid = seed_data["hospital_id"]
    cat = MedicineCategory(name=f"Cat-{uuid.uuid4().hex[:6]}", hospital_id=hid)
    db_session.add(cat)
    db_session.flush()

    hsn = PharmacyHSN(code=f"H{uuid.uuid4().hex[:4]}", sgst_pct=9, cgst_pct=9, hospital_id=hid)
    db_session.add(hsn)
    db_session.flush()

    other_hsn = PharmacyHSN(code=f"H{uuid.uuid4().hex[:4]}", sgst_pct=1, cgst_pct=1, hospital_id=hid)
    db_session.add(other_hsn)
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
            "mrp": 30.0,
            "quantity": 10,
            "free_quantity": 0,
            "purchase_rate": 20.0,
            "discount_pct": 0,
            "hsn_id": other_hsn.id,
        }],
    }
    r = client.post("/api/pharmacy/purchases", headers=auth_headers, json=payload)
    assert r.status_code == 201, r.text
    item = r.json()["items"][0]
    assert item["hsn_id"] == hsn.id
    # 10 × 20 = 200 base; 18% tax (9+9) = 36
    assert abs(item["tax_amount"] - 36.0) < 0.01
