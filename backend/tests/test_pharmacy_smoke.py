"""
Pharmacy module smoke test.

Covers the core flow exercised in production:
  1. Create catalog masters (supplier, HSN, category).
  2. Create a medicine that FKs to them.
  3. Draft → confirm a purchase. Verify inventory batch + ledger row.
  4. Sell from FIFO inventory. Verify inventory deducted + ledger.
  5. Void the sale. Verify inventory restored + reverse ledger.

All requests use the super_admin token from the shared conftest, which bypasses
module-enabled + license-feature + role-permission checks. This focuses the
smoke on business logic, not auth plumbing (already covered in module B–H
inline backend smokes during build).
"""
import pytest
from datetime import date, timedelta


@pytest.fixture(scope="module")
def pharmacy_seed(client, auth_headers, seed_data):
    """Returns a dict of IDs created for the pharmacy flow."""
    H = auth_headers

    sup = client.post(
        "/api/pharmacy/suppliers",
        json={"name": "Smoke Supplier", "phone": "+91 0000", "is_active": True},
        headers=H,
    )
    assert sup.status_code == 201, sup.text
    supplier_id = sup.json()["id"]

    hsn = client.post(
        "/api/pharmacy/hsn",
        json={"code": "30049099", "description": "Smoke HSN",
              "sgst_pct": 6.0, "cgst_pct": 6.0, "is_active": True},
        headers=H,
    )
    assert hsn.status_code == 201, hsn.text
    hsn_id = hsn.json()["id"]

    cat = client.post(
        "/api/pharmacy/categories",
        json={"name": "Smoke Cat", "is_active": True},
        headers=H,
    )
    assert cat.status_code == 201, cat.text
    cat_id = cat.json()["id"]

    med = client.post(
        "/api/pharmacy/medicines",
        json={
            "medicine_code": "SMK-1", "name": "Smoke Med",
            "category_id": cat_id, "hsn_id": hsn_id,
            "dosage_form": "tablet", "strength": "500mg",
            "unit_price": 0, "mrp": 0, "rate_a": 20.0, "rate_b": 25.0,
            "min_qty": 5, "is_active": True,
        },
        headers=H,
    )
    assert med.status_code == 201, med.text
    medicine_id = med.json()["id"]

    return {
        "supplier_id": supplier_id, "hsn_id": hsn_id,
        "category_id": cat_id, "medicine_id": medicine_id,
    }


def test_pharmacy_health(client, auth_headers):
    r = client.get("/api/pharmacy/health", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["module"] == "pharmacy"


def test_catalog_creation(pharmacy_seed):
    """Master tables seed and link via FKs (verified inside the fixture)."""
    assert pharmacy_seed["medicine_id"] > 0


def test_purchase_confirm_creates_inventory_and_ledger(
    client, auth_headers, pharmacy_seed,
):
    H = auth_headers
    today = str(date.today())

    # 1. Draft (no expiry_date — that field has been removed)
    r = client.post(
        "/api/pharmacy/purchases",
        json={
            "entry_date": today, "supplier_id": pharmacy_seed["supplier_id"],
            "invoice_number": "INV-SMK-1", "bill_date": today,
            "payment_type": "credit", "purchase_type": "local",
            "items": [{
                "medicine_id": pharmacy_seed["medicine_id"],
                "batch_number": "B-SMK-1",
                "expiry_date": "2027-12-31",
                "mrp": 25.0, "quantity": 100, "free_quantity": 10,
                "purchase_rate": 15.0, "discount_pct": 5.0,
                "hsn_id": pharmacy_seed["hsn_id"],
            }],
        },
        headers=H,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    pid = body["id"]
    assert body["status"] == "draft"
    # 100 × 15 = 1500; − 5% = 1425; + 12% tax = 1596
    assert abs(body["subtotal"] - 1500.0) < 0.01
    assert abs(body["total_discount"] - 75.0) < 0.01
    assert abs(body["total_tax"] - 171.0) < 0.01
    assert abs(body["grand_total"] - 1596.0) < 0.01

    # 2. Confirm
    r = client.post(f"/api/pharmacy/purchases/{pid}/confirm", headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "confirmed"

    # 3. Inventory batch created with qty = 110 (100 + 10 free)
    r = client.get(
        "/api/pharmacy/inventory/batches",
        params={"medicine_id": pharmacy_seed["medicine_id"]},
        headers=H,
    )
    assert r.status_code == 200
    batch = next((b for b in r.json() if b["batch_number"] == "B-SMK-1"), None)
    assert batch is not None
    assert batch["quantity_in_stock"] == 110
    assert batch["purchase_id"] == pid

    # 4. Ledger has a "purchase" entry for +110
    r = client.get(
        "/api/pharmacy/inventory/ledger",
        params={"medicine_id": pharmacy_seed["medicine_id"], "txn_type": "purchase"},
        headers=H,
    )
    assert r.status_code == 200
    led = r.json()
    assert any(l["qty_delta"] == 110 and l["batch_number"] == "B-SMK-1" for l in led)

    # 5. Edit-after-confirm is rejected
    r = client.put(f"/api/pharmacy/purchases/{pid}", json={
        "entry_date": today, "supplier_id": pharmacy_seed["supplier_id"],
        "payment_type": "cash", "items": [],
    }, headers=H)
    assert r.status_code == 400
    assert "confirmed" in r.json()["detail"]


def test_sale_fifo_deducts_and_void_restores(client, auth_headers, pharmacy_seed):
    H = auth_headers

    # 1. Sale of 30 — single batch has 110 → deducts to 80
    r = client.post(
        "/api/pharmacy/sales",
        json={
            "payment_type": "cash",
            "patient_name": "Smoke Patient", "patient_phone": "1112223",
            "doctor_name": "Dr. Smoke",
            "items": [{
                "medicine_id": pharmacy_seed["medicine_id"],
                "quantity": 30, "rate_tier": "A",
            }],
        },
        headers=H,
    )
    assert r.status_code == 201, r.text
    sale = r.json()
    sid = sale["id"]
    # rate_a = 20, qty 30 → subtotal 600; HSN 12% → tax 72; grand 672
    assert abs(sale["subtotal"] - 600.0) < 0.01
    assert abs(sale["tax_total"] - 72.0) < 0.01
    assert abs(sale["grand_total"] - 672.0) < 0.01

    # 2. Inventory shows 80 remaining
    r = client.get(
        "/api/pharmacy/inventory/batches",
        params={"medicine_id": pharmacy_seed["medicine_id"]},
        headers=H,
    )
    batch = next(b for b in r.json() if b["batch_number"] == "B-SMK-1")
    assert batch["quantity_in_stock"] == 80

    # 3. Ledger has a "sale" entry for -30
    r = client.get(
        "/api/pharmacy/inventory/ledger",
        params={"medicine_id": pharmacy_seed["medicine_id"], "txn_type": "sale"},
        headers=H,
    )
    assert any(l["qty_delta"] == -30 for l in r.json())

    # 4. Over-sell guard: try 200 → 400
    r = client.post(
        "/api/pharmacy/sales",
        json={"payment_type": "cash", "items": [{
            "medicine_id": pharmacy_seed["medicine_id"], "quantity": 200,
        }]},
        headers=H,
    )
    assert r.status_code == 400
    assert "Insufficient stock" in r.json()["detail"]

    # 5. Void restores qty → 110 again
    r = client.post(
        f"/api/pharmacy/sales/{sid}/void",
        json={"reason": "smoke test"},
        headers=H,
    )
    assert r.status_code == 200
    assert r.json()["status"] == "voided"

    r = client.get(
        "/api/pharmacy/inventory/batches",
        params={"medicine_id": pharmacy_seed["medicine_id"]},
        headers=H,
    )
    batch = next(b for b in r.json() if b["batch_number"] == "B-SMK-1")
    assert batch["quantity_in_stock"] == 110

    # 6. Reverse ledger row was written
    r = client.get(
        "/api/pharmacy/inventory/ledger",
        params={"medicine_id": pharmacy_seed["medicine_id"], "txn_type": "return_in"},
        headers=H,
    )
    assert any(l["qty_delta"] == 30 for l in r.json())

    # 7. Double-void is blocked
    r = client.post(
        f"/api/pharmacy/sales/{sid}/void",
        json={"reason": "again"},
        headers=H,
    )
    assert r.status_code == 400


def test_outpatient_prescription_loads_and_sells_through_pos(
    client, auth_headers, pharmacy_seed, db_session, seed_data,
):
    from app.models.patient import Patient
    from app.models.pharmacy import Prescription, PrescriptionItem

    patient = db_session.query(Patient).filter(
        Patient.id == seed_data["patient_id"]
    ).first()
    lookup = client.get(
        "/api/prescriptions/medicines-lookup",
        params={"q": "Smoke Med"},
        headers=auth_headers,
    )
    assert lookup.status_code == 200, lookup.text
    assert any(
        medicine["id"] == pharmacy_seed["medicine_id"]
        for medicine in lookup.json()
    )

    filled = client.post(
        "/api/prescriptions-simple/",
        json={
            "patient_id": patient.patient_id,
            "medicines": [{
                "medicine_id": pharmacy_seed["medicine_id"],
                "name": "Smoke Med",
                "dosage": "1 tablet",
                "duration": "5 days",
                "quantity": "5",
            }],
            "diagnosis": "POS integration smoke",
        },
        headers=auth_headers,
    )
    assert filled.status_code == 200, filled.text

    pending = client.get(
        "/api/pharmacy/prescriptions/pending",
        params={"patient_id": patient.patient_id},
        headers=auth_headers,
    )
    assert pending.status_code == 200, pending.text
    rx = next(
        row for row in pending.json()
        if row["prescription_number"] == filled.json()["prescription_id"]
    )
    item = rx["items"][0]
    assert item["medicine_id"] == pharmacy_seed["medicine_id"]
    assert item["quantity_remaining"] == 5

    sale = client.post(
        "/api/pharmacy/sales",
        json={
            "payment_type": "cash",
            "billing_mode": "cash_at_pharmacy",
            "patient_ip_id": patient.patient_id,
            "patient_name": f"{patient.first_name} {patient.last_name}",
            "prescription_id": rx["id"],
            "items": [{
                "medicine_id": item["medicine_id"],
                "prescription_item_id": item["item_id"],
                "qty_tabs": 3,
                "rate_tier": "A",
            }],
        },
        headers=auth_headers,
    )
    assert sale.status_code == 201, sale.text

    db_session.expire_all()
    pharmacy_rx = db_session.query(Prescription).filter(
        Prescription.id == rx["id"]
    ).first()
    pharmacy_item = db_session.query(PrescriptionItem).filter(
        PrescriptionItem.id == item["item_id"]
    ).first()
    assert pharmacy_rx.status == "partial"
    assert pharmacy_rx.pharmacy_sale_id == sale.json()["id"]
    assert pharmacy_item.quantity_dispensed == 3


def test_multi_batch_rates_on_purchase_and_sale(client, auth_headers, pharmacy_seed):
    """Each batch keeps its own MRP / P-Rate / Rate A / qty-per-strip."""
    H = auth_headers
    today = str(date.today())
    med_id = pharmacy_seed["medicine_id"]

    r = client.post(
        "/api/pharmacy/purchases",
        json={
            "entry_date": today, "supplier_id": pharmacy_seed["supplier_id"],
            "invoice_number": "INV-BATCH-RATES", "bill_date": today,
            "payment_type": "cash",
            "items": [
                {
                    "medicine_id": med_id, "batch_number": "B-RATE-A",
                    "expiry_date": "2028-06-30",
                    "mrp": 30.0, "quantity": 20, "free_quantity": 0,
                    "purchase_rate": 18.0, "rate_a": 28.0, "rate_b": 30.0,
                    "strip_conversion_factor": 10, "discount_pct": 0,
                },
                {
                    "medicine_id": med_id, "batch_number": "B-RATE-B",
                    "expiry_date": "2028-12-31",
                    "mrp": 40.0, "quantity": 20, "free_quantity": 0,
                    "purchase_rate": 22.0, "rate_a": 36.0, "rate_b": 38.0,
                    "strip_conversion_factor": 15, "discount_pct": 0,
                },
            ],
        },
        headers=H,
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert client.post(f"/api/pharmacy/purchases/{pid}/confirm", headers=H).status_code == 200

    r = client.get(
        "/api/pharmacy/inventory/batches",
        params={"medicine_id": med_id},
        headers=H,
    )
    by_batch = {b["batch_number"]: b for b in r.json()}
    assert by_batch["B-RATE-A"]["rate_a"] == 28.0
    assert by_batch["B-RATE-A"]["purchase_rate"] == 18.0
    assert by_batch["B-RATE-A"]["mrp"] == 30.0
    assert by_batch["B-RATE-A"]["strip_conversion_factor"] == 10
    assert by_batch["B-RATE-B"]["rate_a"] == 36.0
    assert by_batch["B-RATE-B"]["strip_conversion_factor"] == 15

    # Sell 1 strip from B-RATE-A → 10 tabs × (28/10) = ₹28
    r = client.post(
        "/api/pharmacy/sales",
        json={
            "payment_type": "cash",
            "items": [{
                "medicine_id": med_id,
                "qty_tabs": 0, "qty_strips": 1, "rate_tier": "A",
                "batch_id": by_batch["B-RATE-A"]["id"],
            }],
        },
        headers=H,
    )
    assert r.status_code == 201, r.text
    assert abs(r.json()["subtotal"] - 28.0) < 0.01

    # Sell 1 strip from B-RATE-B → 15 tabs × (36/15) = ₹36
    r = client.post(
        "/api/pharmacy/sales",
        json={
            "payment_type": "cash",
            "items": [{
                "medicine_id": med_id,
                "qty_tabs": 0, "qty_strips": 1, "rate_tier": "A",
                "batch_id": by_batch["B-RATE-B"]["id"],
            }],
        },
        headers=H,
    )
    assert r.status_code == 201, r.text
    assert abs(r.json()["subtotal"] - 36.0) < 0.01


def test_stock_adjustment_writes_ledger(client, auth_headers, pharmacy_seed):
    H = auth_headers
    r = client.get(
        "/api/pharmacy/inventory/batches",
        params={"medicine_id": pharmacy_seed["medicine_id"]},
        headers=H,
    )
    batch = next(b for b in r.json() if b["batch_number"] == "B-SMK-1")
    bid = batch["id"]
    qty_before = batch["quantity_in_stock"]

    r = client.post(
        "/api/pharmacy/inventory/adjust",
        json={"batch_id": bid, "qty_change": -3.0, "reason": "Damage"},
        headers=H,
    )
    assert r.status_code == 201
    assert r.json()["new_quantity"] == qty_before - 3

    # Negative-stock guard
    r = client.post(
        "/api/pharmacy/inventory/adjust",
        json={"batch_id": bid, "qty_change": -99999, "reason": "Test"},
        headers=H,
    )
    assert r.status_code == 400


def test_dashboard_and_reports_respond(client, auth_headers):
    H = auth_headers
    assert client.get("/api/pharmacy/dashboard", headers=H).status_code == 200
    assert client.get("/api/pharmacy/reports/sales", headers=H).status_code == 200
    assert client.get("/api/pharmacy/reports/purchases", headers=H).status_code == 200
    assert client.get("/api/pharmacy/reports/stock-on-hand", headers=H).status_code == 200
    assert client.get("/api/pharmacy/reports/tax-summary", headers=H).status_code == 200


def test_pdf_generators_return_valid_pdf(client, auth_headers, pharmacy_seed, db_session):
    """PDFs must start with the %PDF magic-bytes and be non-trivial in size."""
    H = auth_headers

    # 1. Purchase PDF
    r = client.get("/api/pharmacy/purchases", headers=H)
    if r.json():
        pid = r.json()[0]["id"]
        pdf = client.get(f"/api/pharmacy/purchases/{pid}/pdf", headers=H)
        assert pdf.status_code == 200
        assert pdf.content[:4] == b"%PDF"
        assert len(pdf.content) > 1000

    # 2. Sale PDF — find a voided sale from the earlier test
    r = client.get("/api/pharmacy/sales", headers=H)
    if r.json():
        sid = r.json()[0]["id"]
        pdf = client.get(f"/api/pharmacy/sales/{sid}/invoice/pdf", headers=H)
        assert pdf.status_code == 200
        assert pdf.content[:4] == b"%PDF"

    # 3. Narcotic register — empty register still renders
    pdf = client.get("/api/pharmacy/reports/narcotic-register/pdf", headers=H)
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"

    # 4. Hospital print setting off still returns valid PDF
    if r.json():
        from app.utils.pdf_settings import set_hospital_pdf_include_header

        set_hospital_pdf_include_header(db_session, include_header=False, created_by=1)
        db_session.commit()
        sid = r.json()[0]["id"]
        pdf = client.get(f"/api/pharmacy/sales/{sid}/invoice/pdf", headers=H)
        assert pdf.status_code == 200
        assert pdf.content[:4] == b"%PDF"
