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


def test_parse_ddmmyyyy_vendor_formats():
    from app.services.pharmacy_import import _parse_ddmmyyyy
    assert _parse_ddmmyyyy("31012028") == date(2028, 1, 31)  # Vasu DDMMYYYY
    assert _parse_ddmmyyyy("1032028") == date(2028, 3, 1)    # Marg DMMYYYY
    assert _parse_ddmmyyyy(1032028) == date(2028, 3, 1)
    assert _parse_ddmmyyyy(1032028.0) == date(2028, 3, 1)
    assert _parse_ddmmyyyy("2082026") == date(2026, 8, 2)
    assert _parse_ddmmyyyy("1112028") == date(2028, 11, 1)
    assert _parse_ddmmyyyy("2028-03-01") == date(2028, 3, 1)
    assert _parse_ddmmyyyy("03/2028") == date(2028, 3, 1)
    assert _parse_ddmmyyyy("03/28") == date(2028, 3, 1)


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
    assert info["file_line_count"] > 0
    assert info["required_fields"] == [
        "medicine_name", "batch_number", "quantity",
        "purchase_rate", "mrp", "discount_pct", "expiry_date",
    ]

    from app.services.pharmacy_import import (
        _line_items_from_letter_grid,
        _normalize_letter_mapping,
        _parse_purchase_grid,
    )
    grid = _parse_purchase_grid(content, "1808.csv", row_start=2)
    letter_map = _normalize_letter_mapping({
        "record_type": "A",
        "medicine_name": "F",
        "batch_number": "I",
        "quantity": "P",
        "purchase_rate": "K",
        "free_quantity": "Q",
        "expiry_date": "J",
        "mrp": "M",
    })
    items = _line_items_from_letter_grid(grid, letter_map)
    assert items[0]["medicine_name"] == "AF-200"
    assert items[0]["purchase_rate"] == pytest.approx(58.82)
    assert items[0]["mrp"] == pytest.approx(77.2)
    assert items[0]["rate_a"] == pytest.approx(77.2)


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
    assert info["file_line_count"] >= info["row_count"]
    assert info["row_count"] > 0
    assert info["min_row"] >= 1
    assert info["max_row"] >= info["min_row"]


def _csv_line(*cols):
    return ",".join(str(c) for c in cols) + "\n"


def test_import_blocks_unmatched_medicines(db_session, seed_data):
    from types import SimpleNamespace

    from app.models.pharmacy import Medicine, MedicineCategory, PharmacySupplier
    from app.services.pharmacy_import import import_purchases

    hid = seed_data["hospital_id"]
    cat = MedicineCategory(name="Import Match Cat", hospital_id=hid, is_active=True)
    db_session.add(cat)
    db_session.flush()
    known = Medicine(
        medicine_code="IMP-AF200", name="AF-200", category_id=cat.id,
        unit_price=0, hospital_id=hid, is_active=True,
    )
    db_session.add(known)
    supplier = PharmacySupplier(name="Import Match Supplier", hospital_id=hid, is_active=True)
    db_session.add(supplier)
    db_session.flush()

    # A=type F=name I=batch J=expiry K=PTR M=MRP P=qty Q=free R=discount
    csv = (
        _csv_line("T", "x", "x", "x", "x", "AF-200", "x", "x", "HAH1", "31012028", "58.82", "x", "77.2", "x", "x", "20", "2", "0")
        + _csv_line("T", "x", "x", "x", "x", "UNKNOWN-MED", "x", "x", "B2", "31012028", "10", "x", "12", "x", "x", "5", "0", "0")
    )
    mapping = {
        "record_type": "A",
        "medicine_name": "F",
        "batch_number": "I",
        "expiry_date": "J",
        "purchase_rate": "K",
        "mrp": "M",
        "quantity": "P",
        "free_quantity": "Q",
        "discount_pct": "R",
    }
    user = SimpleNamespace(hospital_id=hid, id=seed_data["admin_user_id"])
    summary = import_purchases(
        db_session, user, csv.encode(), "test.csv",
        dry_run=True, on_duplicate="skip",
        column_mapping=mapping,
        supplier_id=supplier.id,
        invoice_number="INV-1",
        row_start=1,
    )
    unknown = next(u for u in summary["unmatched_medicines"] if u.get("name") == "UNKNOWN-MED")
    assert unknown["name"] == "UNKNOWN-MED"
    assert summary.get("form") is None
    assert summary["error_count"] >= 1


def test_import_maps_stock_to_existing_medicine(db_session, seed_data):
    from types import SimpleNamespace

    from app.models.pharmacy import Medicine, MedicineCategory, PharmacySupplier
    from app.services.pharmacy_import import import_purchases

    hid = seed_data["hospital_id"]
    cat = MedicineCategory(name="Import Stock Cat", hospital_id=hid, is_active=True)
    db_session.add(cat)
    db_session.flush()
    known = Medicine(
        medicine_code="IMP-STK1", name="Stocked Tablet", category_id=cat.id,
        unit_price=0, mrp=77.2, hospital_id=hid, is_active=True,
    )
    db_session.add(known)
    supplier = PharmacySupplier(name="Import Stock Supplier", hospital_id=hid, is_active=True)
    db_session.add(supplier)
    db_session.flush()

    csv = _csv_line(
        "T", "x", "x", "x", "x", "Stocked Tablet", "x", "x", "HAH1", "31012028",
        "58.82", "x", "77.2", "x", "x", "20", "2", "0",
    )
    mapping = {
        "record_type": "A",
        "medicine_name": "F",
        "batch_number": "I",
        "expiry_date": "J",
        "purchase_rate": "K",
        "quantity": "P",
        "free_quantity": "Q",
        "mrp": "M",
        "discount_pct": "R",
    }
    user = SimpleNamespace(hospital_id=hid, id=seed_data["admin_user_id"])
    summary = import_purchases(
        db_session, user, csv.encode(), "test.csv",
        dry_run=True, on_duplicate="skip",
        column_mapping=mapping,
        supplier_id=supplier.id,
        invoice_number="INV-1",
        row_start=1,
    )
    assert summary["unmatched_medicines"] == []
    assert summary.get("form") is not None
    item = summary["form"]["items"][0]
    assert item["medicine_id"] == known.id
    assert item["batch_number"] == "HAH1"
    assert item["quantity"] == pytest.approx(20.0)
    assert item["purchase_rate"] == pytest.approx(58.82)
    assert item["free_quantity"] == pytest.approx(2.0)
    assert item["expiry_date"] == "2028-01-31"


def test_import_name_alias_maps_typo_to_existing(db_session, seed_data):
    from types import SimpleNamespace

    from app.models.pharmacy import Medicine, MedicineCategory, PharmacySupplier
    from app.services.pharmacy_import import import_purchases, upsert_medicine_import_alias

    hid = seed_data["hospital_id"]
    cat = MedicineCategory(name="Alias Cat", hospital_id=hid, is_active=True)
    db_session.add(cat)
    db_session.flush()
    known = Medicine(
        medicine_code="IMP-AFTY", name="AF-200", category_id=cat.id,
        unit_price=0, hospital_id=hid, is_active=True,
    )
    db_session.add(known)
    supplier = PharmacySupplier(name="Alias Supplier", hospital_id=hid, is_active=True)
    db_session.add(supplier)
    db_session.flush()

    csv = _csv_line(
        "T", "x", "x", "x", "x", "AF 200 TAB", "x", "x", "HAH1", "31012028",
        "58.82", "x", "77.2", "x", "x", "20", "2", "0",
    )
    mapping = {
        "record_type": "A",
        "medicine_name": "F",
        "batch_number": "I",
        "expiry_date": "J",
        "purchase_rate": "K",
        "quantity": "P",
        "mrp": "M",
        "discount_pct": "R",
    }
    user = SimpleNamespace(hospital_id=hid, id=seed_data["admin_user_id"])
    unmatched = import_purchases(
        db_session, user, csv.encode(), "test.csv",
        dry_run=True, on_duplicate="skip",
        column_mapping=mapping,
        supplier_id=supplier.id,
        invoice_number="INV-ALIAS",
        row_start=1,
    )
    assert unmatched.get("form") is None
    assert any(u.get("name") == "AF 200 TAB" for u in unmatched["unmatched_medicines"])

    mapped = import_purchases(
        db_session, user, csv.encode(), "test.csv",
        dry_run=True, on_duplicate="skip",
        column_mapping=mapping,
        supplier_id=supplier.id,
        invoice_number="INV-ALIAS",
        row_start=1,
        name_aliases={"AF 200 TAB": known.id},
    )
    assert mapped["unmatched_medicines"] == []
    assert mapped["form"]["items"][0]["medicine_id"] == known.id

    persist = import_purchases(
        db_session, user, csv.encode(), "test.csv",
        dry_run=True, on_duplicate="skip",
        column_mapping=mapping,
        supplier_id=supplier.id,
        invoice_number="INV-ALIAS-2",
        row_start=1,
    )
    assert persist.get("form") is None
    upsert_medicine_import_alias(db_session, hid, known.id, "AF 200 TAB")
    db_session.flush()
    persisted = import_purchases(
        db_session, user, csv.encode(), "test.csv",
        dry_run=True, on_duplicate="skip",
        column_mapping=mapping,
        supplier_id=supplier.id,
        invoice_number="INV-ALIAS-2",
        row_start=1,
    )
    assert persisted["unmatched_medicines"] == []
    assert persisted["form"]["items"][0]["medicine_id"] == known.id


def test_excel_col_letter_and_letter_mapping():
    from app.services.pharmacy_import import (
        _excel_col_letter,
        _normalize_letter_mapping,
        _parse_excel_col_letter,
    )
    assert _excel_col_letter(0) == "A"
    assert _excel_col_letter(5) == "F"
    assert _excel_col_letter(25) == "Z"
    assert _excel_col_letter(26) == "AA"
    assert _parse_excel_col_letter(" f ") == "F"
    assert _parse_excel_col_letter("CL6") is None
    mapped = _normalize_letter_mapping({
        "medicine_name": "F",
        "batch_number": "i",
        "quantity": "P",
    })
    assert mapped["medicine_name"] == "F"
    assert mapped["batch_number"] == "I"
    from_old = _normalize_letter_mapping({"CL6": "medicine_name", "CL9": "batch_number"})
    assert from_old["medicine_name"] == "F"
    assert from_old["batch_number"] == "I"
