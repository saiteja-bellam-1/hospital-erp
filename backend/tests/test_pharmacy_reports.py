"""
Phase 2 tests — pharmacy reporting expansion + regressions.

P2.1 sale items snapshot HSN rates; tax-summary stays stable if rates change later.
P2.2 narcotic register includes voided sales (status='voided' on the row).
P2.3 sales report group_by=medicine returns one bucket per medicine without N+1.
P2.4 daily-closeout report.
P2.5 margin report (revenue vs cost vs margin %).
P2.7 supplier-aging report buckets.
P2.8 movement report — ABC classification + days-of-cover.
"""

import uuid
from datetime import date, datetime, timedelta

import pytest


@pytest.fixture()
def reports_setup(db_session, seed_data):
    """One medicine + supplier + a confirmed purchase (so we have stock + cost)."""
    from app.models.pharmacy import (
        MedicineCategory, Medicine, PharmacySupplier, PharmacyHSN,
    )
    hid = seed_data["hospital_id"]

    cat = MedicineCategory(name=f"RCat-{uuid.uuid4().hex[:5]}", hospital_id=hid)
    db_session.add(cat); db_session.flush()
    hsn = PharmacyHSN(code=f"R{uuid.uuid4().hex[:4]}", sgst_pct=6, cgst_pct=6,
                     hospital_id=hid)
    db_session.add(hsn); db_session.flush()
    med = Medicine(
        medicine_code=f"R{uuid.uuid4().hex[:6]}", name=f"RMed-{uuid.uuid4().hex[:4]}",
        unit_price=20.0, rate_a=25.0, category_id=cat.id, hsn_id=hsn.id,
        is_narcotic=True, hospital_id=hid,
    )
    db_session.add(med); db_session.flush()
    sup = PharmacySupplier(name=f"RSup-{uuid.uuid4().hex[:4]}", hospital_id=hid)
    db_session.add(sup); db_session.flush()
    db_session.commit()
    return {"category_id": cat.id, "medicine_id": med.id,
            "supplier_id": sup.id, "hsn_id": hsn.id, "hsn_code": hsn.code}


def _confirm_purchase(client, headers, setup, *, qty=20, rate=10.0, mrp=25.0,
                      invoice=None, entry_date=None, payment_type="cash"):
    body = {
        "entry_date": (entry_date or date.today()).isoformat(),
        "supplier_id": setup["supplier_id"],
        "invoice_number": invoice or f"INV-{uuid.uuid4().hex[:6]}",
        "bill_date": None, "payment_type": payment_type, "purchase_type": "local",
        "notes": None,
        "items": [{
            "medicine_id": setup["medicine_id"],
            "batch_number": f"B-{uuid.uuid4().hex[:5]}",
            "mrp": mrp, "quantity": qty, "free_quantity": 0,
            "purchase_rate": rate, "discount_pct": 0,
            "hsn_id": setup["hsn_id"],
        }],
    }
    p = client.post("/api/pharmacy/purchases", headers=headers, json=body).json()
    client.post(f"/api/pharmacy/purchases/{p['id']}/confirm", headers=headers)
    return p


def _make_sale(client, headers, setup, *, qty=2, rate=25.0):
    return client.post("/api/pharmacy/sales", headers=headers, json={
        "payment_type": "cash",
        "items": [{
            "medicine_id": setup["medicine_id"], "quantity": qty,
            "rate": rate, "rate_tier": "A",
        }],
    })


# --------------------------------------------------------------------------
# P2.1 — tax snapshot is stable when HSN master changes
# --------------------------------------------------------------------------

def test_tax_summary_uses_snapshot(client, auth_headers, reports_setup, db_session):
    from app.models.pharmacy import PharmacyHSN

    _confirm_purchase(client, auth_headers, reports_setup, qty=10, rate=10.0)
    s = _make_sale(client, auth_headers, reports_setup, qty=2, rate=100.0)
    assert s.status_code == 201, s.text

    # Snapshot was 6+6=12% at sale time; baseline taxable = 200, tax = 24.
    r1 = client.get("/api/pharmacy/reports/tax-summary", headers=auth_headers).json()
    baseline = next((row for row in r1 if row["hsn_code"] == reports_setup["hsn_code"]), None)
    assert baseline is not None, r1
    assert abs(baseline["taxable_value"] - 200.0) < 0.01
    assert abs(baseline["total_tax"] - 24.0) < 0.01

    # Drastically change HSN master rates AFTER the sale.
    hsn = db_session.query(PharmacyHSN).filter(PharmacyHSN.id == reports_setup["hsn_id"]).first()
    hsn.sgst_pct = 50
    hsn.cgst_pct = 50
    db_session.commit()

    r2 = client.get("/api/pharmacy/reports/tax-summary", headers=auth_headers).json()
    after = next((row for row in r2 if row["hsn_code"] == reports_setup["hsn_code"]), None)
    assert after is not None, "snapshot rates should still appear on the historical row"
    assert abs(after["total_tax"] - 24.0) < 0.01, "historical tax must not drift"


# --------------------------------------------------------------------------
# P2.2 — voided narcotic sale stays on the register
# --------------------------------------------------------------------------

def test_voided_narcotic_remains_on_register(client, auth_headers, reports_setup):
    _confirm_purchase(client, auth_headers, reports_setup, qty=20, rate=10.0)
    sale = _make_sale(client, auth_headers, reports_setup, qty=3).json()

    v = client.post(f"/api/pharmacy/sales/{sale['id']}/void",
                    headers=auth_headers, json={"reason": "test void"})
    assert v.status_code == 200, v.text

    rows = client.get("/api/pharmacy/reports/narcotic-register",
                      headers=auth_headers).json()
    match = [r for r in rows if r["sale_number"] == sale["sale_number"]]
    assert match, "voided narcotic sale must remain on the register"
    assert match[0]["status"] == "voided"


# --------------------------------------------------------------------------
# P2.3 — group_by=medicine returns one bucket per medicine
# --------------------------------------------------------------------------

def test_sales_report_by_medicine(client, auth_headers, reports_setup):
    _confirm_purchase(client, auth_headers, reports_setup, qty=20, rate=10.0)
    for _ in range(3):
        _make_sale(client, auth_headers, reports_setup, qty=1, rate=30.0)

    rows = client.get("/api/pharmacy/reports/sales",
                      params={"group_by": "medicine"},
                      headers=auth_headers).json()
    assert isinstance(rows, list) and rows
    # At least one bucket has sales_count >= 3 for the medicine just sold.
    assert any(r["sales_count"] >= 3 for r in rows)


# --------------------------------------------------------------------------
# P2.4 — daily closeout: one row per cashier with cash/credit split
# --------------------------------------------------------------------------

def test_daily_closeout(client, auth_headers, reports_setup):
    _confirm_purchase(client, auth_headers, reports_setup, qty=20, rate=10.0)
    _make_sale(client, auth_headers, reports_setup, qty=1, rate=50.0)
    _make_sale(client, auth_headers, reports_setup, qty=1, rate=70.0)

    rows = client.get("/api/pharmacy/reports/daily-closeout",
                      headers=auth_headers).json()
    assert rows, "expected at least one cashier row for today"
    row = rows[0]
    assert row["sales_count"] >= 2
    assert row["net"] >= 120.0
    assert any(b["payment_type"] == "cash" for b in row["by_payment"])


# --------------------------------------------------------------------------
# P2.5 — margin report: revenue > cost, margin_pct sane
# --------------------------------------------------------------------------

def test_margin_report(client, auth_headers, reports_setup, db_session):
    from app.models.pharmacy import Medicine
    med = db_session.query(Medicine).filter(Medicine.id == reports_setup["medicine_id"]).first()

    # Stock in at ₹10/unit cost. Sell at ₹30/unit. Margin per unit = ₹20 (66.67%).
    _confirm_purchase(client, auth_headers, reports_setup, qty=10, rate=10.0)
    s = _make_sale(client, auth_headers, reports_setup, qty=5, rate=30.0)
    assert s.status_code == 201, s.text

    rows = client.get("/api/pharmacy/reports/margin",
                      params={"group_by": "medicine"},
                      headers=auth_headers).json()
    row = next((r for r in rows if r["bucket"] == med.name), None)
    assert row is not None, f"medicine {med.name} not in report rows: {rows}"
    assert row["revenue"] >= 150.0
    assert row["cost"] >= 50.0
    assert row["margin"] > 0
    assert 50 < row["margin_pct"] < 80


# --------------------------------------------------------------------------
# P2.7 — supplier aging: credit purchase shows up in correct bucket
# --------------------------------------------------------------------------

def test_supplier_aging_buckets(client, auth_headers, reports_setup):
    today = date.today()
    _confirm_purchase(client, auth_headers, reports_setup, qty=5, rate=10.0,
                      payment_type="credit", entry_date=today)
    _confirm_purchase(client, auth_headers, reports_setup, qty=5, rate=20.0,
                      payment_type="credit", entry_date=today - timedelta(days=120))
    # cash purchase should be excluded
    _confirm_purchase(client, auth_headers, reports_setup, qty=5, rate=5.0,
                      payment_type="cash", entry_date=today)

    rows = client.get("/api/pharmacy/reports/supplier-aging",
                      headers=auth_headers).json()
    row = next((r for r in rows if r["supplier_id"] == reports_setup["supplier_id"]), None)
    assert row is not None, rows
    assert row["bucket_0_30"] > 0, "today's credit purchase must hit 0–30 bucket"
    assert row["bucket_90_plus"] > 0, "120-day-old purchase must hit 90+ bucket"


# --------------------------------------------------------------------------
# P2.8 — movement report: ABC labels assigned, days-of-cover present
# --------------------------------------------------------------------------

def test_movement_report(client, auth_headers, reports_setup):
    _confirm_purchase(client, auth_headers, reports_setup, qty=30, rate=10.0)
    for _ in range(4):
        _make_sale(client, auth_headers, reports_setup, qty=2, rate=25.0)

    rows = client.get("/api/pharmacy/reports/movement",
                      params={"days": 30},
                      headers=auth_headers).json()
    target = next((r for r in rows if r["medicine_id"] == reports_setup["medicine_id"]), None)
    assert target is not None, rows
    assert target["units_sold"] >= 8
    assert target["abc_class"] in ("A", "B", "C")
    # 22 in stock, 8 sold over 30 days → days_of_cover ≈ 82.5
    assert target["days_of_cover"] is not None
    assert target["days_of_cover"] > 0


# --------------------------------------------------------------------------
# PDFs: smoke — every report PDF endpoint returns 200 + application/pdf.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/pharmacy/reports/sales/pdf",
    "/api/pharmacy/reports/purchases/pdf",
    "/api/pharmacy/reports/stock-on-hand/pdf",
    "/api/pharmacy/reports/tax-summary/pdf",
    "/api/pharmacy/reports/daily-closeout/pdf",
    "/api/pharmacy/reports/margin/pdf",
    "/api/pharmacy/reports/supplier-aging/pdf",
    "/api/pharmacy/reports/movement/pdf",
])
def test_report_pdf_smoke(client, auth_headers, reports_setup, path):
    _confirm_purchase(client, auth_headers, reports_setup, qty=5, rate=10.0)
    r = client.get(path, headers=auth_headers)
    assert r.status_code == 200, (path, r.text[:200])
    assert r.headers["content-type"].startswith("application/pdf"), path
    assert len(r.content) > 500, "PDF body suspiciously small"
