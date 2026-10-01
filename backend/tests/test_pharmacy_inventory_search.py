"""Search on pharmacy inventory tabs matches the columns each tab shows."""
import uuid
from datetime import date, timedelta


def _suffix():
    return uuid.uuid4().hex[:6].upper()


def _create_catalog(client, headers, tag):
    supplier = client.post(
        "/api/pharmacy/suppliers",
        json={"name": f"Sup {tag}", "phone": "9000000000", "is_active": True},
        headers=headers,
    )
    assert supplier.status_code == 201, supplier.text
    hsn = client.post(
        "/api/pharmacy/hsn",
        json={
            "code": f"HS{tag[:6]}",
            "description": f"HSN {tag}",
            "sgst_pct": 6.0,
            "cgst_pct": 6.0,
            "is_active": True,
        },
        headers=headers,
    )
    assert hsn.status_code == 201, hsn.text
    category = client.post(
        "/api/pharmacy/categories",
        json={"name": f"Cat {tag}", "is_active": True},
        headers=headers,
    )
    assert category.status_code == 201, category.text
    return supplier.json()["id"], hsn.json()["id"], category.json()["id"]


def _create_medicine(client, headers, *, code, name, manufacturer, category_id, hsn_id, min_qty):
    response = client.post(
        "/api/pharmacy/medicines",
        json={
            "medicine_code": code,
            "name": name,
            "manufacturer": manufacturer,
            "category_id": category_id,
            "hsn_id": hsn_id,
            "dosage_form": "tablet",
            "unit_price": 0,
            "mrp": 10,
            "rate_a": 8,
            "min_qty": min_qty,
            "is_active": True,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _confirm_purchase(client, headers, *, supplier_id, medicine_id, hsn_id, batch, qty, expiry):
    today = str(date.today())
    draft = client.post(
        "/api/pharmacy/purchases",
        json={
            "entry_date": today,
            "supplier_id": supplier_id,
            "invoice_number": f"INV-{batch}",
            "bill_date": today,
            "payment_type": "credit",
            "purchase_type": "local",
            "items": [{
                "medicine_id": medicine_id,
                "batch_number": batch,
                "expiry_date": expiry,
                "mrp": 10.0,
                "quantity": qty,
                "free_quantity": 0,
                "purchase_rate": 5.0,
                "hsn_id": hsn_id,
            }],
        },
        headers=headers,
    )
    assert draft.status_code == 201, draft.text
    confirmed = client.post(
        f"/api/pharmacy/purchases/{draft.json()['id']}/confirm",
        headers=headers,
    )
    assert confirmed.status_code == 200, confirmed.text


def test_inventory_tabs_search_by_displayed_fields(client, auth_headers):
    tag = _suffix()
    supplier_id, hsn_id, category_id = _create_catalog(client, auth_headers, tag)
    alpha_name = f"ZqAlpha {tag}"
    beta_name = f"ZqBeta {tag}"
    alpha_code = f"A{tag}"[:20]
    beta_code = f"B{tag}"[:20]
    alpha_mfr = f"MfrA{tag}"
    alpha_batch = f"BA{tag}"
    beta_batch = f"BB{tag}"

    alpha_id = _create_medicine(
        client, auth_headers,
        code=alpha_code, name=alpha_name, manufacturer=alpha_mfr,
        category_id=category_id, hsn_id=hsn_id, min_qty=20,
    )
    beta_id = _create_medicine(
        client, auth_headers,
        code=beta_code, name=beta_name, manufacturer=f"MfrB{tag}",
        category_id=category_id, hsn_id=hsn_id, min_qty=0,
    )
    soon = str(date.today() + timedelta(days=15))
    later = str(date.today() + timedelta(days=400))
    _confirm_purchase(
        client, auth_headers,
        supplier_id=supplier_id, medicine_id=alpha_id, hsn_id=hsn_id,
        batch=alpha_batch, qty=2, expiry=soon,
    )
    _confirm_purchase(
        client, auth_headers,
        supplier_id=supplier_id, medicine_id=beta_id, hsn_id=hsn_id,
        batch=beta_batch, qty=5, expiry=later,
    )

    stock = client.get(
        "/api/pharmacy/inventory",
        params={"search": alpha_mfr},
        headers=auth_headers,
    )
    assert stock.status_code == 200, stock.text
    stock_ids = {row["medicine_id"] for row in stock.json()}
    assert alpha_id in stock_ids
    assert beta_id not in stock_ids

    by_supplier = client.get(
        "/api/pharmacy/inventory",
        params={"search": f"Sup {tag}"},
        headers=auth_headers,
    )
    assert by_supplier.status_code == 200, by_supplier.text
    supplier_ids = {row["medicine_id"] for row in by_supplier.json()}
    assert {alpha_id, beta_id} <= supplier_ids

    low = client.get(
        "/api/pharmacy/inventory/low-stock",
        params={"search": alpha_code},
        headers=auth_headers,
    )
    assert low.status_code == 200, low.text
    low_ids = {row["medicine_id"] for row in low.json()}
    assert low_ids == {alpha_id}

    low_miss = client.get(
        "/api/pharmacy/inventory/low-stock",
        params={"search": beta_name},
        headers=auth_headers,
    )
    assert low_miss.status_code == 200
    assert low_miss.json() == []

    batches = client.get(
        "/api/pharmacy/inventory/batches",
        params={"search": beta_batch},
        headers=auth_headers,
    )
    assert batches.status_code == 200, batches.text
    batch_numbers = {row["batch_number"] for row in batches.json()}
    assert batch_numbers == {beta_batch}

    expiring = client.get(
        "/api/pharmacy/inventory/expiring",
        params={"days": 90, "search": alpha_name},
        headers=auth_headers,
    )
    assert expiring.status_code == 200, expiring.text
    expiring_batches = {row["batch_number"] for row in expiring.json()}
    assert expiring_batches == {alpha_batch}

    expiring_miss = client.get(
        "/api/pharmacy/inventory/expiring",
        params={"days": 90, "search": beta_batch},
        headers=auth_headers,
    )
    assert expiring_miss.status_code == 200
    assert expiring_miss.json() == []

    ledger = client.get(
        "/api/pharmacy/inventory/ledger",
        params={"search": alpha_batch, "txn_type": "purchase"},
        headers=auth_headers,
    )
    assert ledger.status_code == 200, ledger.text
    assert ledger.json()
    assert all(row["batch_number"] == alpha_batch for row in ledger.json())
    assert all(row["medicine_name"] == alpha_name for row in ledger.json())
