"""Purchase CSV import — vendor H/T/F format + named template grouping."""
from datetime import date
from pathlib import Path

import pytest

from app.services.pharmacy_import import (
    _group_named_purchase_rows,
    _looks_like_vendor_purchase,
    _parse_csv_rows,
    _parse_pack_scf,
    _parse_vendor_purchase_blocks,
    _strip_excel_formula,
    _suggest_purchase_mapping,
    inspect_purchase_import,
)


SAMPLE_VENDOR = Path("/Users/saiteja/Downloads/1808.csv")


def test_strip_excel_formula():
    assert _strip_excel_formula('="000008"') == "000008"
    assert _strip_excel_formula('="3338.06"') == "3338.06"
    assert _strip_excel_formula("AF-200") == "AF-200"
    assert _strip_excel_formula(None) is None


def test_parse_pack_scf():
    assert _parse_pack_scf("1*10") == 10
    assert _parse_pack_scf("5*1") == 1
    assert _parse_pack_scf("1*15") == 15
    assert _parse_pack_scf("1*30ML") == 30
    assert _parse_pack_scf("") is None


@pytest.mark.skipif(not SAMPLE_VENDOR.exists(), reason="sample 1808.csv not present")
def test_parse_vasu_pharma_csv():
    content = SAMPLE_VENDOR.read_bytes()
    rows = _parse_csv_rows(content)
    assert _looks_like_vendor_purchase(rows)
    blocks = _parse_vendor_purchase_blocks(rows)
    assert len(blocks) == 1
    block = blocks[0]
    assert block["invoice_number"] == "2026-27/TAX/1808"
    assert block["bill_date"] == date(2026, 8, 1)
    assert block["purchase_type"] == "Direct"
    assert block["place_of_supply"] == "KHAMMAM"
    assert block["supplier_name"] == "VASU PHARMA"
    assert len(block["items"]) == 47

    first = block["items"][0]
    assert first["medicine_name"] == "AF-200"
    assert first["medicine_code"] == "000008"
    assert first["pack_size"] == "5*1"
    assert first["batch_number"] == "HAH022603"
    assert first["expiry_date"] == date(2028, 1, 31)
    assert first["purchase_rate"] == pytest.approx(58.82)  # PTR
    assert first["mrp"] == pytest.approx(77.2)
    assert first["rate_a"] == pytest.approx(77.2)  # MRP
    assert first["rate_b"] == pytest.approx(77.2)  # MRP
    assert first["quantity"] == pytest.approx(20.0)
    assert first["hsn_code"] == "30049029"
    assert first["strip_conversion_factor"] == 1
    assert first["cgst_pct"] == pytest.approx(2.5)
    assert first["sgst_pct"] == pytest.approx(2.5)

    normaxin = [i for i in block["items"] if i["medicine_name"] == "NORMAXIN TAB"]
    assert len(normaxin) == 2
    assert {i["batch_number"] for i in normaxin} == {"HNX042680", "HNX042682"}

    footer = block["footer"]
    assert footer is not None
    assert footer["taxable"] == pytest.approx(133522.0)
    assert footer["cgst"] == pytest.approx(3338.06)
    assert footer["sgst"] == pytest.approx(3338.06)
    assert footer["invoice_value"] == pytest.approx(127896.0)
    assert "Invoice value" in (block["notes"] or "")


@pytest.mark.skipif(not SAMPLE_VENDOR.exists(), reason="sample 1808.csv not present")
def test_inspect_and_mapped_vendor_csv():
    content = SAMPLE_VENDOR.read_bytes()
    info = inspect_purchase_import(content, "1808.csv")
    assert info["format_hint"] == "vendor_htf"
    assert any(h.lower() == "cl1" for h in info["headers"])
    suggested = info["suggested_mapping"]
    by_lower = {k.lower(): v for k, v in suggested.items()}
    assert by_lower.get("cl1") == "record_type"
    assert by_lower.get("cl3") == "supplier_or_invoice"
    assert by_lower.get("cl11") == "purchase_rate"
    assert by_lower.get("cl13") == "mrp"

    rows = _parse_csv_rows(content)
    blocks = _parse_vendor_purchase_blocks(rows, column_mapping=suggested)
    assert len(blocks) == 1
    assert blocks[0]["items"][0]["purchase_rate"] == pytest.approx(58.82)
    assert blocks[0]["items"][0]["rate_a"] == pytest.approx(77.2)


def test_suggest_flat_headers():
    mapping = _suggest_purchase_mapping([
        "Supplier", "Invoice", "Item Name", "Batch", "Expiry", "Qty", "PTR", "MRP",
    ])
    assert mapping["Supplier"] == "supplier_name"
    assert mapping["Invoice"] == "invoice_number"
    assert mapping["Item Name"] == "medicine_name"
    assert mapping["Batch"] == "batch_number"
    assert mapping["PTR"] == "purchase_rate"
    assert mapping["MRP"] == "mrp"


def test_named_template_grouping():
    rows = [
        {
            "_row": 2,
            "supplier_name": "Acme",
            "invoice_number": "INV-1",
            "entry_date": "2026-08-01",
            "bill_date": "2026-08-01",
            "payment_type": "credit",
            "medicine_code": "M1",
            "medicine_name": "Med One",
            "batch_number": "B1",
            "expiry_date": "2028-01-31",
            "quantity": "10",
            "purchase_rate": "5",
            "mrp": "8",
        },
        {
            "_row": 3,
            "supplier_name": "Acme",
            "invoice_number": "INV-1",
            "medicine_code": "M2",
            "medicine_name": "Med Two",
            "batch_number": "B2",
            "expiry_date": "2028-06-30",
            "quantity": "5",
            "purchase_rate": "12",
            "mrp": "15",
        },
        {
            "_row": 4,
            "supplier_name": "Acme",
            "invoice_number": "INV-2",
            "medicine_code": "M1",
            "batch_number": "B3",
            "expiry_date": "2029-01-01",
            "quantity": "1",
            "purchase_rate": "5",
        },
    ]
    blocks = _group_named_purchase_rows(rows)
    assert len(blocks) == 2
    assert blocks[0]["invoice_number"] == "INV-1"
    assert len(blocks[0]["items"]) == 2
    assert blocks[1]["invoice_number"] == "INV-2"
    assert len(blocks[1]["items"]) == 1


def test_get_or_create_medicine_autocreates_with_hsn(db_session, seed_data):
    from app.models.pharmacy import Medicine, PharmacyHSN, MedicineCategory, PharmacyCompany
    from app.services.pharmacy_import import _MasterResolver, _get_or_create_medicine_for_purchase

    hid = seed_data["hospital_id"]
    resolver = _MasterResolver(db_session, hid)
    cache = {}
    item = {
        "medicine_code": "NEW001",
        "medicine_name": "BrandNewTablet",
        "pack_size": "1*10",
        "manufacturer": "Acme Labs Pvt Ltd",
        "mrp": 100.0,
        "purchase_rate": 80.0,
        "rate_a": 100.0,
        "rate_b": 100.0,
        "strip_conversion_factor": 10,
        "hsn_code": "30049099",
        "cgst_pct": 2.5,
        "sgst_pct": 2.5,
    }
    # Ensure medicine does not already exist
    assert not db_session.query(Medicine).filter(
        Medicine.hospital_id == hid, Medicine.name == "BrandNewTablet",
    ).first()

    med, created, err = _get_or_create_medicine_for_purchase(
        db_session, hid, item, resolver=resolver, cache=cache,
    )
    assert err is None
    assert created is True
    assert med is not None
    assert med.name == "BrandNewTablet"
    assert med.medicine_code == "NEW001"
    assert med.mrp == pytest.approx(100.0)
    assert med.purchase_rate == pytest.approx(80.0)
    assert med.rate_a == pytest.approx(100.0)
    assert med.rate_b == pytest.approx(100.0)
    assert med.strip_conversion_factor == 10
    assert med.packaging == "1*10"
    assert med.hsn_id is not None
    assert med.company_id is not None
    assert med.category_id is not None

    cat = db_session.query(MedicineCategory).filter(MedicineCategory.id == med.category_id).first()
    assert cat.name == "General"

    hsn = db_session.query(PharmacyHSN).filter(PharmacyHSN.id == med.hsn_id).first()
    assert hsn.code == "30049099"
    assert hsn.cgst_pct == pytest.approx(2.5)
    assert hsn.sgst_pct == pytest.approx(2.5)

    co = db_session.query(PharmacyCompany).filter(PharmacyCompany.id == med.company_id).first()
    assert co.name == "Acme Labs Pvt Ltd"

    # Second call finds existing — not recreated
    med2, created2, err2 = _get_or_create_medicine_for_purchase(
        db_session, hid, item, resolver=resolver, cache={},
    )
    assert err2 is None
    assert created2 is False
    assert med2.id == med.id

    assert any(m.startswith("medicine:") for m in resolver.masters_created)
    assert any(m.startswith("hsn:") for m in resolver.masters_created)


def test_filter_rows_by_line():
    from app.services.pharmacy_import import _filter_rows_by_line
    rows = [{"_row": 2}, {"_row": 5}, {"_row": 9}]
    assert [r["_row"] for r in _filter_rows_by_line(rows, 5, 9)] == [5, 9]
    assert [r["_row"] for r in _filter_rows_by_line(rows, None, 5)] == [2, 5]
    assert [r["_row"] for r in _filter_rows_by_line(rows, 9, None)] == [9]


def test_inspect_returns_row_bounds():
    from pathlib import Path
    from app.services.pharmacy_import import inspect_purchase_import
    sample = Path("/Users/saiteja/Downloads/1808.csv")
    if not sample.exists():
        pytest.skip("sample 1808.csv not present")
    info = inspect_purchase_import(sample.read_bytes(), "1808.csv")
    assert info["min_row"] >= 2
    assert info["max_row"] >= info["min_row"]
    assert info["row_count"] > 0
