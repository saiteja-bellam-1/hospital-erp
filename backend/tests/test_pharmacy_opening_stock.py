"""Manual opening-stock entry from the pharmacy inventory screen."""
import uuid
from datetime import date

import pytest


@pytest.fixture()
def opening_setup(db_session, seed_data):
    from app.models.pharmacy import Medicine, MedicineCategory, PharmacyHSN

    hid = seed_data["hospital_id"]
    cat = MedicineCategory(name=f"OS-Cat-{uuid.uuid4().hex[:5]}", hospital_id=hid)
    db_session.add(cat)
    db_session.flush()
    hsn = PharmacyHSN(
        code=f"O{uuid.uuid4().hex[:4]}", sgst_pct=6, cgst_pct=6, hospital_id=hid,
    )
    db_session.add(hsn)
    db_session.flush()
    med = Medicine(
        medicine_code=f"OS-{uuid.uuid4().hex[:6]}",
        name=f"Opening Med {uuid.uuid4().hex[:4]}",
        unit_price=18.0,
        mrp=25.0,
        purchase_rate=12.0,
        rate_a=20.0,
        rate_b=19.0,
        strip_conversion_factor=10,
        category_id=cat.id,
        hsn_id=hsn.id,
        hospital_id=hid,
    )
    db_session.add(med)
    db_session.flush()
    db_session.commit()
    return {"medicine_id": med.id, "hsn_id": hsn.id, "medicine_code": med.medicine_code}


def test_enter_opening_stock_creates_batch_and_ledger(client, auth_headers, opening_setup, db_session):
    batch_no = f"OS-{uuid.uuid4().hex[:5]}"
    res = client.post(
        "/api/pharmacy/opening-stock",
        headers=auth_headers,
        json={
            "lines": [{
                "medicine_id": opening_setup["medicine_id"],
                "batch_number": batch_no,
                "expiry_date": "2028-06-30",
                "quantity": 100,
                "notes": "Go-live count",
            }],
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["created"] == 1
    row = body["batches"][0]
    assert row["batch_number"] == batch_no
    assert row["quantity_in_stock"] == 100
    assert row["medicine_id"] == opening_setup["medicine_id"]

    from app.models.pharmacy import PharmacyInventory, PharmacyStockLedger

    inv = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == row["id"]).one()
    assert inv.quantity_in_stock == 100
    assert inv.mrp == 25.0
    assert inv.purchase_rate == 12.0
    assert inv.rate_a == 20.0
    assert inv.strip_conversion_factor == 10
    assert inv.hsn_id == opening_setup["hsn_id"]
    assert inv.expiry_date == date(2028, 6, 30)
    assert inv.batch_barcode

    led = (
        db_session.query(PharmacyStockLedger)
        .filter(PharmacyStockLedger.batch_id == inv.id)
        .one()
    )
    assert led.txn_type == "opening_stock"
    assert led.qty_delta == 100
    assert led.reference_type == "opening_stock"
    assert led.notes == "Go-live count"


def test_enter_opening_stock_rejects_existing_batch(client, auth_headers, opening_setup):
    batch_no = f"OS-{uuid.uuid4().hex[:5]}"
    payload = {
        "lines": [{
            "medicine_id": opening_setup["medicine_id"],
            "batch_number": batch_no,
            "expiry_date": "2028-01-31",
            "quantity": 10,
            "mrp": 30,
            "purchase_rate": 15,
            "rate_a": 22,
        }],
    }
    first = client.post("/api/pharmacy/opening-stock", headers=auth_headers, json=payload)
    assert first.status_code == 201, first.text

    again = client.post("/api/pharmacy/opening-stock", headers=auth_headers, json=payload)
    assert again.status_code == 409, again.text
    assert "already exists" in again.json()["detail"]

    batches = client.get(
        "/api/pharmacy/inventory/batches",
        params={"medicine_id": opening_setup["medicine_id"]},
        headers=auth_headers,
    ).json()
    matches = [b for b in batches if b["batch_number"] == batch_no]
    assert len(matches) == 1
    assert matches[0]["quantity_in_stock"] == 10
    assert matches[0]["mrp"] == 30


def test_enter_opening_stock_rejects_unknown_medicine(client, auth_headers):
    res = client.post(
        "/api/pharmacy/opening-stock",
        headers=auth_headers,
        json={
            "lines": [{
                "medicine_id": 99999999,
                "batch_number": "MISSING",
                "expiry_date": "2028-01-31",
                "quantity": 5,
            }],
        },
    )
    assert res.status_code == 400, res.text
    assert "medicine not found" in res.json()["detail"]
