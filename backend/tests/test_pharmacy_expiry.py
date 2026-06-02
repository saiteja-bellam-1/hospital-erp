"""
Pharmacy P0 #2 — Expiry tracking, FEFO and write-off.

Covers:
  T1 — Purchase carries user-entered expiry; inventory row stores it.
  T2 — Same medicine + same batch_number but different expiry → tracked as two
       distinct inventory rows (no merge).
  T3 — Sale picks nearest-expiry batch first (FEFO), not insertion order.
  T4 — /inventory/expiring returns batches within the window, excludes
       sentinel-expiry stock.
  T5 — /inventory/expire-writeoff zeros the batch, writes an
       `expiry_writeoff` ledger row, and is idempotent on zero-stock batches.
  T6 — Dashboard summary surfaces expiring_soon_count + already_expired_count.
"""

from __future__ import annotations

from datetime import date, timedelta
import pytest

from app.models.pharmacy import PharmacyInventory, PharmacyStockLedger


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def expiry_seed(client, auth_headers, seed_data):
    H = auth_headers

    sup = client.post("/api/pharmacy/suppliers",
                      json={"name": "Exp Supplier", "phone": "x", "is_active": True},
                      headers=H)
    assert sup.status_code == 201, sup.text

    hsn = client.post("/api/pharmacy/hsn",
                      json={"code": "30049055", "description": "Exp HSN",
                            "sgst_pct": 6.0, "cgst_pct": 6.0, "is_active": True},
                      headers=H)
    assert hsn.status_code == 201, hsn.text

    cat = client.post("/api/pharmacy/categories",
                      json={"name": "Exp Cat", "is_active": True}, headers=H)
    assert cat.status_code == 201, cat.text

    med = client.post("/api/pharmacy/medicines",
                      json={"medicine_code": "EXP-MED", "name": "Exp Med",
                            "category_id": cat.json()["id"],
                            "hsn_id": hsn.json()["id"],
                            "dosage_form": "tablet", "strength": "100mg",
                            "unit_price": 0, "mrp": 50.0,
                            "rate_a": 40.0, "rate_b": 45.0,
                            "min_qty": 5, "is_active": True},
                      headers=H)
    assert med.status_code == 201, med.text

    return {
        "supplier_id": sup.json()["id"],
        "hsn_id": hsn.json()["id"],
        "medicine_id": med.json()["id"],
    }


def _confirm_purchase(client, H, supplier_id, hsn_id, medicine_id,
                       batch_number, qty, expiry_date, invoice_number):
    today = str(date.today())
    body = {
        "entry_date": today,
        "supplier_id": supplier_id,
        "invoice_number": invoice_number,
        "bill_date": today,
        "payment_type": "credit",
        "purchase_type": "local",
        "items": [{
            "medicine_id": medicine_id,
            "batch_number": batch_number,
            "expiry_date": expiry_date.isoformat(),
            "mrp": 50.0, "quantity": qty, "free_quantity": 0,
            "purchase_rate": 30.0, "discount_pct": 0,
            "hsn_id": hsn_id,
        }],
    }
    p = client.post("/api/pharmacy/purchases", json=body, headers=H)
    assert p.status_code == 201, p.text
    r = client.post(f"/api/pharmacy/purchases/{p.json()['id']}/confirm", headers=H)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# T1 + T2 — Expiry stored, distinct-expiry → distinct inventory rows
# ---------------------------------------------------------------------------

def test_purchase_stores_expiry_and_does_not_merge_distinct_expiry(
    client, auth_headers, db_session, expiry_seed,
):
    H = auth_headers
    far = date.today() + timedelta(days=400)
    nearer = date.today() + timedelta(days=120)

    _confirm_purchase(client, H, expiry_seed["supplier_id"], expiry_seed["hsn_id"],
                      expiry_seed["medicine_id"], "EXP-B-FAR", 50, far, "EXP-INV-FAR")
    _confirm_purchase(client, H, expiry_seed["supplier_id"], expiry_seed["hsn_id"],
                      expiry_seed["medicine_id"], "EXP-B-FAR", 30, nearer, "EXP-INV-NEAR")

    rows = (
        db_session.query(PharmacyInventory)
        .filter(PharmacyInventory.medicine_id == expiry_seed["medicine_id"],
                PharmacyInventory.batch_number == "EXP-B-FAR")
        .all()
    )
    assert len(rows) == 2, "different expiry must NOT merge into one row"
    by_exp = {r.expiry_date: r for r in rows}
    assert far in by_exp and nearer in by_exp
    assert by_exp[far].quantity_in_stock == 50
    assert by_exp[nearer].quantity_in_stock == 30


# ---------------------------------------------------------------------------
# T3 — FEFO: sale picks the nearest-expiry batch first
# ---------------------------------------------------------------------------

def test_sale_picks_fefo_not_fifo(
    client, auth_headers, db_session, expiry_seed,
):
    """Setup: two batches of the *same* medicine — first-created has FAR
    expiry, second has NEAR expiry. A sale of 10 should deplete the NEAR one,
    not the FAR one (FIFO would have done the opposite)."""
    H = auth_headers

    # New medicine to avoid stock from the previous test interfering.
    cat = client.post("/api/pharmacy/categories",
                      json={"name": "FEFO Cat", "is_active": True}, headers=H)
    assert cat.status_code == 201, cat.text
    med = client.post("/api/pharmacy/medicines",
                      json={"medicine_code": "FEFO-MED", "name": "FEFO Med",
                            "category_id": cat.json()["id"],
                            "hsn_id": expiry_seed["hsn_id"],
                            "dosage_form": "tablet", "strength": "10mg",
                            "unit_price": 0, "mrp": 20.0,
                            "rate_a": 18.0, "rate_b": 19.0,
                            "min_qty": 0, "is_active": True},
                      headers=H)
    assert med.status_code == 201, med.text
    medicine_id = med.json()["id"]

    far = date.today() + timedelta(days=365)
    near = date.today() + timedelta(days=60)
    # FAR first (lower id), NEAR second (higher id) — under FIFO the FAR row
    # would be drained first; FEFO must drain the NEAR row.
    _confirm_purchase(client, H, expiry_seed["supplier_id"], expiry_seed["hsn_id"],
                      medicine_id, "FEFO-A", 40, far, "FEFO-INV-A")
    _confirm_purchase(client, H, expiry_seed["supplier_id"], expiry_seed["hsn_id"],
                      medicine_id, "FEFO-B", 40, near, "FEFO-INV-B")

    r = client.post("/api/pharmacy/sales",
                    json={"payment_type": "cash",
                          "items": [{"medicine_id": medicine_id,
                                     "quantity": 10, "rate_tier": "A"}]},
                    headers=H)
    assert r.status_code == 201, r.text

    rows = (
        db_session.query(PharmacyInventory)
        .filter(PharmacyInventory.medicine_id == medicine_id)
        .all()
    )
    by_batch = {b.batch_number: b for b in rows}
    assert by_batch["FEFO-B"].quantity_in_stock == 30, "near-expiry batch should be drained"
    assert by_batch["FEFO-A"].quantity_in_stock == 40, "far-expiry batch should be untouched"


# ---------------------------------------------------------------------------
# T4 — /inventory/expiring
# ---------------------------------------------------------------------------

def test_expiring_endpoint_filters_by_window(
    client, auth_headers, expiry_seed,
):
    H = auth_headers
    # T1 created a batch with expiry today+120 ("EXP-B-FAR" near). Window 150
    # must include it; window 30 must not.
    r150 = client.get("/api/pharmacy/inventory/expiring",
                      params={"days": 150}, headers=H)
    assert r150.status_code == 200
    batches_150 = [b["batch_number"] for b in r150.json()]
    assert "EXP-B-FAR" in batches_150  # the near-expiry copy is at +120

    r30 = client.get("/api/pharmacy/inventory/expiring",
                     params={"days": 30}, headers=H)
    assert r30.status_code == 200
    batches_30 = [b["batch_number"] for b in r30.json()]
    assert "EXP-B-FAR" not in batches_30

    # Sentinel-expiry stock must never appear, even at the widest window.
    rmax = client.get("/api/pharmacy/inventory/expiring",
                      params={"days": 3650}, headers=H).json()
    assert all(b["expiry_date"] != "2099-12-31" for b in rmax)


# ---------------------------------------------------------------------------
# T5 — /inventory/expire-writeoff
# ---------------------------------------------------------------------------

def test_writeoff_zeros_stock_and_writes_ledger(
    client, auth_headers, db_session, expiry_seed,
):
    H = auth_headers
    # Create a fresh batch we don't mind destroying.
    expired = date.today() - timedelta(days=10)
    _confirm_purchase(client, H, expiry_seed["supplier_id"], expiry_seed["hsn_id"],
                      expiry_seed["medicine_id"], "WO-B1", 25, expired, "WO-INV-1")

    inv = (db_session.query(PharmacyInventory)
           .filter(PharmacyInventory.batch_number == "WO-B1")
           .first())
    assert inv is not None
    assert inv.quantity_in_stock == 25
    batch_id = inv.id

    r = client.post("/api/pharmacy/inventory/expire-writeoff",
                    json={"batch_ids": [batch_id],
                          "reason": "Past expiry — destroyed per SOP"},
                    headers=H)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["batches_written_off"] == 1
    assert body["total_qty_written_off"] == 25
    assert body["ledger_rows"] == 1

    db_session.refresh(inv)
    assert inv.quantity_in_stock == 0

    led = (db_session.query(PharmacyStockLedger)
           .filter(PharmacyStockLedger.batch_id == batch_id,
                   PharmacyStockLedger.txn_type == "expiry_writeoff")
           .all())
    assert len(led) == 1
    assert led[0].qty_delta == -25

    # Second call is a no-op (batch is already zero).
    r2 = client.post("/api/pharmacy/inventory/expire-writeoff",
                     json={"batch_ids": [batch_id], "reason": "double tap"},
                     headers=H)
    assert r2.status_code == 201
    assert r2.json()["batches_written_off"] == 0


# ---------------------------------------------------------------------------
# T6 — Dashboard surfaces expiring + already-expired counts
# ---------------------------------------------------------------------------

def test_dashboard_surfaces_expiring_counts(client, auth_headers):
    H = auth_headers
    r = client.get("/api/pharmacy/dashboard", headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "expiring_soon_count" in body
    assert "already_expired_count" in body
    assert isinstance(body["expiring_soon_count"], int)
    assert isinstance(body["already_expired_count"], int)
