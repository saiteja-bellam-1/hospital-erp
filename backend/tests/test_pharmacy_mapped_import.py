"""Mapped letter-column import for medicines catalog and historical sales."""
from types import SimpleNamespace

from app.models.pharmacy import Medicine, MedicineCategory, PharmacySale
from app.services.pharmacy_import import (
    import_medicines,
    inspect_medicines_import,
)
from app.services.pharmacy_sales_import import import_sales, inspect_sales_import


def _csv(*rows):
    return ("\n".join(rows) + "\n").encode("utf-8")


def _user(seed_data):
    return SimpleNamespace(
        hospital_id=seed_data["hospital_id"],
        id=seed_data["admin_user_id"],
        role_names=["super_admin"],
        role=None,
        roles=[],
    )


def test_inspect_medicines_detects_template_headers():
    content = _csv(
        "medicine_code,name,category,mrp",
        "PCM500,Paracetamol,General,25",
    )
    info = inspect_medicines_import(content, "meds.csv", row_start=1)
    assert info["file_line_count"] == 2
    assert info["header_detected"] is True
    assert info["suggested_row_start"] == 2
    assert info["suggested_letter_mapping"]["medicine_code"] == "A"
    assert info["suggested_letter_mapping"]["name"] == "B"
    assert info["suggested_letter_mapping"]["category"] == "C"
    assert info["suggested_letter_mapping"]["mrp"] == "D"


def test_import_medicines_named_headers_still_works(db_session, seed_data):
    content = _csv(
        "medicine_code,name,category,mrp,purchase_rate,rate_a",
        "MAP-PCM,Paracetamol 500,General,25,18,20",
    )
    summary = import_medicines(
        db_session, _user(seed_data), content, "meds.csv",
        dry_run=False, on_duplicate="skip",
    )
    assert summary["created"] == 1
    assert summary["error_count"] == 0
    med = db_session.query(Medicine).filter(Medicine.medicine_code == "MAP-PCM").first()
    assert med is not None
    assert med.name == "Paracetamol 500"


def test_import_medicines_letter_mapping(db_session, seed_data):
    content = _csv(
        "SKU,Item Name,Group,MRP",
        "MAP-AMOX,Amoxicillin 250,Antibiotics,80",
    )
    mapping = {
        "medicine_code": "A",
        "name": "B",
        "category": "C",
        "mrp": "D",
    }
    summary = import_medicines(
        db_session, _user(seed_data), content, "vendor.csv",
        dry_run=False, on_duplicate="skip",
        column_mapping=mapping, row_start=2,
    )
    assert summary["created"] == 1
    med = db_session.query(Medicine).filter(Medicine.medicine_code == "MAP-AMOX").first()
    assert med is not None
    assert med.name == "Amoxicillin 250"
    cat = db_session.query(MedicineCategory).filter(MedicineCategory.id == med.category_id).first()
    assert cat.name == "Antibiotics"


def test_inspect_sales_detects_template_headers():
    content = _csv(
        "sale_number,sale_date,medicine_name,quantity",
        "S1,2025-06-15,AF-200,10",
    )
    info = inspect_sales_import(content, "sales.csv", row_start=1)
    assert info["header_detected"] is True
    assert info["suggested_letter_mapping"]["sale_date"] == "B"
    assert info["suggested_letter_mapping"]["medicine_name"] == "C"
    assert info["suggested_letter_mapping"]["quantity"] == "D"


def test_import_sales_returns_unmatched_medicines(db_session, seed_data):
    content = _csv(
        "sale_date,medicine_name,quantity",
        "2025-06-15,MISSING-TAB,10",
    )
    mapping = {"sale_date": "A", "medicine_name": "B", "quantity": "C"}
    summary = import_sales(
        db_session, _user(seed_data), content, "sales.csv",
        dry_run=True, affect_stock=False,
        column_mapping=mapping, row_start=2,
    )
    names = [u["name"] for u in summary["unmatched_medicines"]]
    assert "MISSING-TAB" in names
    assert summary["created"] == 0
    assert summary["error_count"] >= 1


def test_import_sales_letter_mapping_success(db_session, seed_data):
    hid = seed_data["hospital_id"]
    cat = MedicineCategory(name="Sales Import Cat", hospital_id=hid, is_active=True)
    db_session.add(cat)
    db_session.flush()
    med = Medicine(
        medicine_code="SALE-AF200", name="AF-200", category_id=cat.id,
        unit_price=7.72, mrp=77.2, hospital_id=hid, is_active=True,
    )
    db_session.add(med)
    db_session.flush()

    content = _csv(
        "Date,Item,Qty,Bill",
        "2025-06-15,AF-200,10,SALE-LEGACY-MAP",
    )
    mapping = {
        "sale_date": "A",
        "medicine_name": "B",
        "quantity": "C",
        "sale_number": "D",
    }
    summary = import_sales(
        db_session, _user(seed_data), content, "sales.csv",
        dry_run=False, affect_stock=False,
        column_mapping=mapping, row_start=2,
    )
    assert summary["unmatched_medicines"] == []
    assert summary["created"] == 1
    sale = db_session.query(PharmacySale).filter(
        PharmacySale.sale_number == "SALE-LEGACY-MAP",
    ).first()
    assert sale is not None
    assert sale.stock_affected is False


def test_medicine_and_sales_mappings_are_isolated(client, auth_headers):
    med_payload = {
        "name": "Vendor catalog",
        "column_mapping": {"medicine_code": "A", "name": "B", "category": "C"},
    }
    sale_payload = {
        "name": "Vendor catalog",
        "column_mapping": {"sale_date": "A", "quantity": "B", "medicine_name": "C"},
    }
    med = client.post(
        "/api/pharmacy/medicines/import/mappings",
        headers=auth_headers, json=med_payload,
    )
    sale = client.post(
        "/api/pharmacy/sales/import/mappings",
        headers=auth_headers, json=sale_payload,
    )
    assert med.status_code == 201, med.text
    assert sale.status_code == 201, sale.text
    assert med.json()["id"] != sale.json()["id"]

    med_list = client.get("/api/pharmacy/medicines/import/mappings", headers=auth_headers)
    sale_list = client.get("/api/pharmacy/sales/import/mappings", headers=auth_headers)
    assert med_list.status_code == 200
    assert sale_list.status_code == 200
    assert any(r["name"] == "Vendor catalog" for r in med_list.json())
    assert any(r["name"] == "Vendor catalog" for r in sale_list.json())
    assert all(r.get("column_mapping", {}).get("medicine_code") == "A"
               or "medicine_code" in (r.get("column_mapping") or {})
               for r in med_list.json() if r["name"] == "Vendor catalog")
