"""Sales return, purchase return (challan/DN), and supplier payments tests."""

import uuid
from datetime import date

import pytest


@pytest.fixture()
def returns_setup(db_session, seed_data):
    from app.models.pharmacy import (
        MedicineCategory, Medicine, PharmacySupplier, PharmacyHSN, PharmacyStore,
    )
    hid = seed_data["hospital_id"]
    master = db_session.query(PharmacyStore).filter(
        PharmacyStore.hospital_id == hid,
        PharmacyStore.is_default == True,  # noqa: E712
    ).first()
    if not master:
        master = PharmacyStore(
            hospital_id=hid, name="Main Store", code="MAIN",
            is_default=True, is_active=True, can_receive_supplier_purchase=True,
        )
        db_session.add(master)
        db_session.flush()

    cat = MedicineCategory(name=f"RetCat-{uuid.uuid4().hex[:5]}", hospital_id=hid)
    db_session.add(cat)
    db_session.flush()
    hsn = PharmacyHSN(code=f"T{uuid.uuid4().hex[:4]}", sgst_pct=6, cgst_pct=6, hospital_id=hid)
    db_session.add(hsn)
    db_session.flush()
    med = Medicine(
        medicine_code=f"RM{uuid.uuid4().hex[:6]}",
        name=f"RetMed-{uuid.uuid4().hex[:4]}",
        unit_price=20.0, rate_a=25.0, category_id=cat.id, hsn_id=hsn.id,
        hospital_id=hid,
    )
    db_session.add(med)
    db_session.flush()
    sup = PharmacySupplier(name=f"RetSup-{uuid.uuid4().hex[:4]}", hospital_id=hid)
    db_session.add(sup)
    db_session.flush()
    db_session.commit()
    return {
        "medicine_id": med.id,
        "supplier_id": sup.id,
        "hsn_id": hsn.id,
        "store_id": master.id,
    }


def _confirm_purchase(client, headers, setup, *, qty=50, rate=10.0, payment_type="credit", invoice=None):
    body = {
        "entry_date": date.today().isoformat(),
        "supplier_id": setup["supplier_id"],
        "invoice_number": invoice or f"INV-{uuid.uuid4().hex[:6]}",
        "payment_type": payment_type,
        "purchase_type": "local",
        "store_id": setup["store_id"],
        "items": [{
            "medicine_id": setup["medicine_id"],
            "batch_number": f"B-{uuid.uuid4().hex[:5]}",
            "expiry_date": "2028-12-31",
            "mrp": 30.0,
            "quantity": qty,
            "free_quantity": 0,
            "purchase_rate": rate,
            "discount_pct": 0,
            "hsn_id": setup["hsn_id"],
        }],
    }
    p = client.post("/api/pharmacy/purchases", headers=headers, json=body)
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    c = client.post(f"/api/pharmacy/purchases/{pid}/confirm", headers=headers)
    assert c.status_code == 200, c.text
    detail = client.get(f"/api/pharmacy/purchases/{pid}", headers=headers).json()
    return detail


def _make_sale(client, headers, setup, *, qty=5, rate=25.0, batch_id=None):
    item = {"medicine_id": setup["medicine_id"], "quantity": qty, "rate": rate, "rate_tier": "A"}
    if batch_id:
        item["batch_id"] = batch_id
    r = client.post("/api/pharmacy/sales", headers=headers, json={
        "payment_type": "cash",
        "patient_name": "Return Patient",
        "store_id": setup["store_id"],
        "items": [item],
    })
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_sales_return_restock_and_credit_note_pdf(client, auth_headers, returns_setup, db_session):
    from app.models.pharmacy import PharmacyInventory, PharmacyStockLedger

    H = auth_headers
    purchase = _confirm_purchase(client, H, returns_setup, qty=40)
    batch_id = purchase["items"][0]["inventory_id"]
    sale = _make_sale(client, H, returns_setup, qty=6, batch_id=batch_id)
    sale_item = sale["items"][0]

    before = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == batch_id).one()
    stock_before = float(before.quantity_in_stock)

    draft = client.post("/api/pharmacy/sale-returns", headers=H, json={
        "sale_id": sale["id"],
        "store_id": returns_setup["store_id"],
        "reason": "Patient unused tabs",
        "items": [{
            "sale_item_id": sale_item["id"],
            "medicine_id": returns_setup["medicine_id"],
            "batch_id": batch_id,
            "quantity": 2,
            "rate": 25.0,
            "restock": True,
        }],
    })
    assert draft.status_code == 201, draft.text
    rid = draft.json()["id"]
    assert draft.json()["status"] == "draft"

    # Confirm does not move stock until confirm
    mid = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == batch_id).one()
    assert float(mid.quantity_in_stock) == stock_before

    conf = client.post(f"/api/pharmacy/sale-returns/{rid}/confirm", headers=H, json={
        "settlement_method": "cash",
        "settlement_amount": draft.json()["grand_total"],
        "settlement_reference": "CASH-1",
    })
    assert conf.status_code == 200, conf.text
    assert conf.json()["status"] == "confirmed"
    assert conf.json()["settlement_method"] == "cash"

    db_session.expire_all()
    after = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == batch_id).one()
    assert abs(float(after.quantity_in_stock) - (stock_before + 2)) < 0.001

    led = db_session.query(PharmacyStockLedger).filter(
        PharmacyStockLedger.reference_type == "sale_return",
        PharmacyStockLedger.reference_id == rid,
        PharmacyStockLedger.txn_type == "sale_return",
    ).all()
    assert len(led) == 1
    assert float(led[0].qty_delta) == 2.0

    pdf = client.get(f"/api/pharmacy/sale-returns/{rid}/credit-note/pdf", headers=H)
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"].startswith("application/pdf")


def test_sales_return_open_without_sale(client, auth_headers, returns_setup, db_session):
    from app.models.pharmacy import PharmacyInventory, PharmacyStockLedger

    H = auth_headers
    purchase = _confirm_purchase(client, H, returns_setup, qty=20, invoice=f"INV-{uuid.uuid4().hex[:5]}")
    batch_id = purchase["items"][0]["inventory_id"]
    before = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == batch_id).one()
    stock_before = float(before.quantity_in_stock)

    draft = client.post("/api/pharmacy/sale-returns", headers=H, json={
        "patient_name": "Walk-in",
        "store_id": returns_setup["store_id"],
        "reason": "No bill — unused tablets",
        "items": [{
            "medicine_id": returns_setup["medicine_id"],
            "batch_id": batch_id,
            "quantity": 3,
            "rate": 20.0,
            "restock": True,
        }],
    })
    assert draft.status_code == 201, draft.text
    body = draft.json()
    assert body.get("sale_id") in (None, 0)
    rid = body["id"]
    conf = client.post(f"/api/pharmacy/sale-returns/{rid}/confirm", headers=H, json={
        "settlement_method": "cash",
        "settlement_amount": body["grand_total"],
    })
    assert conf.status_code == 200, conf.text
    assert conf.json()["status"] == "confirmed"

    db_session.expire_all()
    after = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == batch_id).one()
    assert abs(float(after.quantity_in_stock) - (stock_before + 3)) < 0.001
    led = db_session.query(PharmacyStockLedger).filter(
        PharmacyStockLedger.reference_type == "sale_return",
        PharmacyStockLedger.reference_id == rid,
    ).all()
    assert len(led) == 1
    assert float(led[0].qty_delta) == 3.0


def test_sales_return_rejects_sale_item_without_sale(client, auth_headers, returns_setup):
    H = auth_headers
    purchase = _confirm_purchase(client, H, returns_setup, qty=10, invoice=f"INV-{uuid.uuid4().hex[:5]}")
    batch_id = purchase["items"][0]["inventory_id"]
    draft = client.post("/api/pharmacy/sale-returns", headers=H, json={
        "store_id": returns_setup["store_id"],
        "items": [{
            "sale_item_id": 999999,
            "medicine_id": returns_setup["medicine_id"],
            "batch_id": batch_id,
            "quantity": 1,
            "rate": 20.0,
        }],
    })
    assert draft.status_code == 400, draft.text


def test_purchase_return_challan_stock_out_and_debit_note_allocate(
    client, auth_headers, returns_setup, db_session,
):
    from app.models.pharmacy import PharmacyInventory, PharmacyStockLedger

    H = auth_headers
    p1 = _confirm_purchase(client, H, returns_setup, qty=30, rate=10.0, invoice=f"A-{uuid.uuid4().hex[:5]}")
    p2 = _confirm_purchase(client, H, returns_setup, qty=20, rate=12.0, invoice=f"B-{uuid.uuid4().hex[:5]}")
    batch_id = p1["items"][0]["inventory_id"]

    before = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == batch_id).one()
    stock_before = float(before.quantity_in_stock)

    draft = client.post("/api/pharmacy/purchase-returns", headers=H, json={
        "supplier_id": returns_setup["supplier_id"],
        "purchase_id": p1["id"],
        "store_id": returns_setup["store_id"],
        "reason": "Damaged goods",
        "items": [{
            "purchase_item_id": p1["items"][0]["id"],
            "medicine_id": returns_setup["medicine_id"],
            "batch_id": batch_id,
            "quantity": 5,
            "purchase_rate": 10.0,
        }],
    })
    assert draft.status_code == 201, draft.text
    rid = draft.json()["id"]

    conf = client.post(f"/api/pharmacy/purchase-returns/{rid}/confirm", headers=H)
    assert conf.status_code == 200, conf.text

    # Confirm does not reduce stock
    db_session.expire_all()
    mid = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == batch_id).one()
    assert float(mid.quantity_in_stock) == stock_before

    challan = client.post(f"/api/pharmacy/purchase-returns/{rid}/challan", headers=H, json={
        "transporter": "Self",
        "vehicle": "TN-01",
    })
    assert challan.status_code == 200, challan.text
    assert challan.json()["has_challan"] is True
    assert challan.json()["status"] == "challan_created"

    db_session.expire_all()
    after = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == batch_id).one()
    assert abs(float(after.quantity_in_stock) - (stock_before - 5)) < 0.001

    led = db_session.query(PharmacyStockLedger).filter(
        PharmacyStockLedger.txn_type == "return_out",
        PharmacyStockLedger.batch_id == batch_id,
    ).order_by(PharmacyStockLedger.id.desc()).first()
    assert led is not None
    assert float(led.qty_delta) == -5.0

    # Cancel blocked after challan
    cancel = client.post(f"/api/pharmacy/purchase-returns/{rid}/cancel", headers=H, json={"reason": "oops"})
    assert cancel.status_code == 400

    # Partial CN + DN → partial (pending amount remains)
    cn = client.post(f"/api/pharmacy/purchase-returns/{rid}/supplier-credit-note", headers=H, json={
        "supplier_credit_note_number": "SCN-99",
        "supplier_credit_note_amount": 30.0,
    })
    assert cn.status_code == 200, cn.text
    assert cn.json()["status"] == "cn_recorded"
    assert abs(cn.json()["pending_cn_amount"] - 20.0) < 0.01

    dn = client.post(f"/api/pharmacy/purchase-returns/{rid}/debit-note", headers=H, json={})
    assert dn.status_code == 200, dn.text
    assert dn.json()["status"] == "partial"
    assert abs(dn.json()["debit_note"]["amount"] - 30.0) < 0.01
    dn_id = dn.json()["debit_note"]["id"]

    # Top-up CN to full cover, then DN → completed
    cn2 = client.post(f"/api/pharmacy/purchase-returns/{rid}/supplier-credit-note", headers=H, json={
        "supplier_credit_note_number": "SCN-100",
        "supplier_credit_note_amount": 20.0,
    })
    assert cn2.status_code == 200, cn2.text
    assert abs(cn2.json()["pending_cn_amount"]) < 0.01

    dn2 = client.post(f"/api/pharmacy/purchase-returns/{rid}/debit-note", headers=H, json={})
    assert dn2.status_code == 200, dn2.text
    assert dn2.json()["status"] == "completed"
    assert len(dn2.json()["debit_notes"]) == 2
    assert len(dn2.json()["credit_notes"]) == 2

    # Over-allocate fails
    bad = client.post(f"/api/pharmacy/debit-notes/{dn_id}/allocate", headers=H, json={
        "allocations": [{"purchase_id": p1["id"], "amount": 9999}],
    })
    assert bad.status_code == 400

    # Allocate across two purchases
    ok = client.post(f"/api/pharmacy/debit-notes/{dn_id}/allocate", headers=H, json={
        "allocations": [
            {"purchase_id": p1["id"], "amount": 20.0},
            {"purchase_id": p2["id"], "amount": 10.0},
        ],
    })
    assert ok.status_code == 200, ok.text
    assert len(ok.json()["allocations"]) == 2

    pdf = client.get(f"/api/pharmacy/debit-notes/{dn_id}/pdf", headers=H)
    assert pdf.status_code == 200


def test_challan_insufficient_stock(client, auth_headers, returns_setup, db_session):
    from app.models.pharmacy import PharmacyInventory

    H = auth_headers
    p1 = _confirm_purchase(client, H, returns_setup, qty=10, invoice=f"C-{uuid.uuid4().hex[:5]}")
    batch_id = p1["items"][0]["inventory_id"]
    inv = db_session.query(PharmacyInventory).filter(PharmacyInventory.id == batch_id).one()
    inv.quantity_in_stock = 1
    db_session.commit()

    draft = client.post("/api/pharmacy/purchase-returns", headers=H, json={
        "supplier_id": returns_setup["supplier_id"],
        "store_id": returns_setup["store_id"],
        "items": [{
            "medicine_id": returns_setup["medicine_id"],
            "batch_id": batch_id,
            "quantity": 5,
            "purchase_rate": 10.0,
        }],
    }).json()
    client.post(f"/api/pharmacy/purchase-returns/{draft['id']}/confirm", headers=H)
    challan = client.post(f"/api/pharmacy/purchase-returns/{draft['id']}/challan", headers=H, json={})
    assert challan.status_code == 400
    assert "Insufficient" in challan.json()["detail"]


def test_supplier_payment_and_aging(client, auth_headers, returns_setup):
    H = auth_headers
    p1 = _confirm_purchase(client, H, returns_setup, qty=10, rate=100.0, invoice=f"P-{uuid.uuid4().hex[:5]}")
    # grand_total exclusive 10*100 + 12% = 1120
    aging_before = client.get("/api/pharmacy/reports/supplier-aging", headers=H).json()
    row = next((r for r in aging_before if r["supplier_id"] == returns_setup["supplier_id"]), None)
    assert row is not None
    before_total = row["total_outstanding"]

    pay = client.post("/api/pharmacy/supplier-payments", headers=H, json={
        "supplier_id": returns_setup["supplier_id"],
        "amount": 200.0,
        "mode": "neft",
        "reference": "UTR-1",
        "allocations": [{"purchase_id": p1["id"], "amount": 200.0}],
    })
    assert pay.status_code == 201, pay.text

    aging_after = client.get("/api/pharmacy/reports/supplier-aging", headers=H).json()
    row2 = next((r for r in aging_after if r["supplier_id"] == returns_setup["supplier_id"]), None)
    assert row2 is not None
    assert abs(row2["total_outstanding"] - (before_total - 200.0)) < 0.05

    payables = client.get(
        f"/api/pharmacy/suppliers/{returns_setup['supplier_id']}/payables", headers=H,
    ).json()
    assert payables["payment_total"] >= 200.0
    purchased = next(p for p in payables["purchases"] if p["purchase_id"] == p1["id"])
    assert abs(purchased["allocated"] - 200.0) < 0.01
