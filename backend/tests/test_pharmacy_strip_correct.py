"""Force-correct batch Tabs/strip + stock without sold-qty gates."""
import uuid
from datetime import date

import pytest


@pytest.fixture()
def strip_setup(db_session, seed_data):
    from app.models.pharmacy import Medicine, MedicineCategory, PharmacyHSN, PharmacySupplier

    hid = seed_data["hospital_id"]
    cat = MedicineCategory(name=f"SCF-Cat-{uuid.uuid4().hex[:5]}", hospital_id=hid)
    db_session.add(cat)
    db_session.flush()
    hsn = PharmacyHSN(
        code=f"S{uuid.uuid4().hex[:4]}", sgst_pct=6, cgst_pct=6, hospital_id=hid,
    )
    db_session.add(hsn)
    db_session.flush()
    med = Medicine(
        medicine_code=f"SCF-{uuid.uuid4().hex[:6]}",
        name=f"SCF Med {uuid.uuid4().hex[:4]}",
        unit_price=10.0, rate_a=10.0, mrp=12.0,
        strip_conversion_factor=1,
        category_id=cat.id, hsn_id=hsn.id, hospital_id=hid,
    )
    db_session.add(med)
    db_session.flush()
    sup = PharmacySupplier(name=f"SCF-Sup-{uuid.uuid4().hex[:4]}", hospital_id=hid)
    db_session.add(sup)
    db_session.flush()
    db_session.commit()
    return {
        "medicine_id": med.id,
        "supplier_id": sup.id,
        "hsn_id": hsn.id,
    }


def test_correct_strip_stock_after_sale_bypasses_sold_gate(
    client, auth_headers, strip_setup, db_session,
):
    """Wrong SCF purchase + strip sale, then force-correct without voiding."""
    H = auth_headers
    today = date.today().isoformat()
    batch_no = f"B-SCF-{uuid.uuid4().hex[:5]}"

    # Purchase 10 strips with wrong Tabs/strip = 10 → 100 tabs credited
    r = client.post(
        "/api/pharmacy/purchases",
        headers=H,
        json={
            "entry_date": today,
            "supplier_id": strip_setup["supplier_id"],
            "invoice_number": f"INV-SCF-{uuid.uuid4().hex[:5]}",
            "bill_date": today,
            "payment_type": "cash",
            "purchase_type": "local",
            "items": [{
                "medicine_id": strip_setup["medicine_id"],
                "batch_number": batch_no,
                "expiry_date": "2028-12-31",
                "mrp": 20.0,
                "quantity": 10,
                "free_quantity": 0,
                "purchase_rate": 10.0,
                "discount_pct": 0,
                "hsn_id": strip_setup["hsn_id"],
                "strip_conversion_factor": 10,
            }],
        },
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert client.post(f"/api/pharmacy/purchases/{pid}/confirm", headers=H).status_code == 200

    batches = client.get(
        "/api/pharmacy/inventory/batches",
        params={"medicine_id": strip_setup["medicine_id"]},
        headers=H,
    ).json()
    batch = next(b for b in batches if b["batch_number"] == batch_no)
    assert batch["quantity_in_stock"] == 100
    assert batch["strip_conversion_factor"] == 10
    batch_id = batch["id"]

    # Sell 5 strips (= 50 tabs under wrong SCF)
    sale = client.post(
        "/api/pharmacy/sales",
        headers=H,
        json={
            "payment_type": "cash",
            "patient_name": "SCF Patient",
            "items": [{
                "medicine_id": strip_setup["medicine_id"],
                "batch_id": batch_id,
                "qty_strips": 5,
                "qty_tabs": 0,
                "rate_tier": "A",
            }],
        },
    )
    assert sale.status_code == 201, sale.text

    batches = client.get(
        "/api/pharmacy/inventory/batches",
        params={"medicine_id": strip_setup["medicine_id"]},
        headers=H,
    ).json()
    batch = next(b for b in batches if b["id"] == batch_id)
    assert batch["quantity_in_stock"] == 50

    # Purchase edit to SCF=1 would be blocked (10 tabs < 50 sold) — skip that path.
    # Force-correct: leave sale as-is; set SCF=1 and physical remaining = 5 tabs.
    corr = client.post(
        "/api/pharmacy/inventory/correct-strip-stock",
        headers=H,
        json={
            "batch_id": batch_id,
            "strip_conversion_factor": 1,
            "quantity_in_stock": 5,
            "reason": "Wrong Tabs/strip on purchase; leave sales, fix stock",
            "update_medicine_scf": True,
            "update_purchase_lines": True,
        },
    )
    assert corr.status_code == 200, corr.text
    body = corr.json()
    assert body["strip_conversion_factor"] == 1
    assert body["quantity_in_stock"] == 5
    assert body["qty_delta"] == -45
    assert body["medicine_updated"] is True
    assert body["purchase_lines_updated"] >= 1

    from app.models.pharmacy import Medicine, PharmacyInventory, PharmacyPurchaseItem

    inv = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == batch_id).one()
    assert inv.strip_conversion_factor == 1
    assert float(inv.quantity_in_stock) == 5

    med = db_session.query(Medicine).filter(Medicine.id == strip_setup["medicine_id"]).one()
    assert med.strip_conversion_factor == 1

    line = (
        db_session.query(PharmacyPurchaseItem)
        .filter(PharmacyPurchaseItem.inventory_id == batch_id)
        .one()
    )
    assert line.strip_conversion_factor == 1
