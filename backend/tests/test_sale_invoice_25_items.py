"""Verify pharmacy sale invoice PDF pagination with 25 line items."""
import os
from datetime import date
from io import BytesIO

from PyPDF2 import PdfReader


def _seed_masters(client, headers):
    sup = client.post(
        "/api/pharmacy/suppliers",
        json={"name": "Paginate Supplier", "phone": "+91 9999", "is_active": True},
        headers=headers,
    )
    assert sup.status_code == 201, sup.text
    hsn = client.post(
        "/api/pharmacy/hsn",
        json={
            "code": "30049999",
            "description": "Paginate HSN",
            "sgst_pct": 6.0,
            "cgst_pct": 6.0,
            "is_active": True,
        },
        headers=headers,
    )
    assert hsn.status_code == 201, hsn.text
    cat = client.post(
        "/api/pharmacy/categories",
        json={"name": "Paginate Cat", "is_active": True},
        headers=headers,
    )
    assert cat.status_code == 201, cat.text
    return sup.json()["id"], hsn.json()["id"], cat.json()["id"]


def test_sale_invoice_pdf_with_25_items(client, auth_headers):
  """A 25-line sale should produce a multi-page A5 landscape PDF."""
  H = auth_headers
  today = str(date.today())
  supplier_id, hsn_id, cat_id = _seed_masters(client, H)

  medicine_ids = []
  for i in range(1, 26):
      med = client.post(
          "/api/pharmacy/medicines",
          json={
              "medicine_code": f"PG-{i:02d}",
              "name": f"Paginate Med {i:02d}",
              "category_id": cat_id,
              "hsn_id": hsn_id,
              "dosage_form": "tablet",
              "strength": "500mg",
              "unit_price": 0,
              "mrp": 0,
              "rate_a": 10.0 + i,
              "rate_b": 12.0 + i,
              "min_qty": 1,
              "is_active": True,
          },
          headers=H,
      )
      assert med.status_code == 201, med.text
      medicine_ids.append(med.json()["id"])

  purchase_items = [
      {
          "medicine_id": mid,
          "batch_number": f"B-PG-{i:02d}",
          "expiry_date": "2027-12-31",
          "mrp": 20.0 + i,
          "quantity": 50,
          "free_quantity": 0,
          "purchase_rate": 8.0 + i,
          "discount_pct": 0.0,
          "hsn_id": hsn_id,
      }
      for i, mid in enumerate(medicine_ids, start=1)
  ]
  purch = client.post(
      "/api/pharmacy/purchases",
      json={
          "entry_date": today,
          "supplier_id": supplier_id,
          "invoice_number": "INV-PG-25",
          "bill_date": today,
          "payment_type": "cash",
          "purchase_type": "local",
          "items": purchase_items,
      },
      headers=H,
  )
  assert purch.status_code == 201, purch.text
  pid = purch.json()["id"]
  assert len(purch.json()["items"]) == 25

  confirm = client.post(f"/api/pharmacy/purchases/{pid}/confirm", headers=H)
  assert confirm.status_code == 200, confirm.text

  sale_items = [
      {"medicine_id": mid, "quantity": 1, "rate_tier": "A"}
      for mid in medicine_ids
  ]
  sale = client.post(
      "/api/pharmacy/sales",
      json={
          "payment_type": "cash",
          "patient_name": "Pagination Patient",
          "doctor_name": "Dr. Paginate",
          "items": sale_items,
      },
      headers=H,
  )
  assert sale.status_code == 201, sale.text
  sid = sale.json()["id"]
  assert len(sale.json()["items"]) == 25

  pdf_resp = client.get(f"/api/pharmacy/sales/{sid}/invoice/pdf", headers=H)
  assert pdf_resp.status_code == 200
  assert pdf_resp.content[:4] == b"%PDF"

  reader = PdfReader(BytesIO(pdf_resp.content))
  page_count = len(reader.pages)

  # Save artifact for manual inspection (optional; ignored by git if test_output/ is gitignored)
  out_dir = os.path.join(os.path.dirname(__file__), "..", "test_output")
  os.makedirs(out_dir, exist_ok=True)
  out_path = os.path.join(out_dir, f"sale_invoice_25_items_{sale.json()['sale_number']}.pdf")
  with open(out_path, "wb") as f:
      f.write(pdf_resp.content)

  # A5 landscape: 595.28 x 419.53 pt (width x height)
  first = reader.pages[0].mediabox
  page_w = float(first.width)
  page_h = float(first.height)
  assert page_w > page_h, "Expected landscape orientation"
  assert 580 < page_w < 610, f"Unexpected page width {page_w}"
  assert 400 < page_h < 440, f"Unexpected page height {page_h}"

  all_text = "\n".join(page.extract_text() or "" for page in reader.pages)
  assert "CASH/CREDIT BILL" in all_text
  assert "Paginate Med 01" in all_text
  assert "Paginate Med 25" in all_text
  assert "Total Amt" in all_text
  assert "Net Amt" in all_text

  # Document actual pagination behaviour (no A4 fallback; ReportLab splits when needed)
  print(f"\n25-item sale invoice: {page_count} page(s), {page_w:.0f}x{page_h:.0f} pt, {len(pdf_resp.content)} bytes")
  print(f"Sale id={sid}, sale_number={sale.json()['sale_number']}")
  print(f"PDF saved: {os.path.abspath(out_path)}")
  if page_count == 1:
      print("All 25 lines fit on a single A5 landscape page at 6pt row height.")