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
    assert block["transporter"] == "SRMT"
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

    # Two NORMAXIN TAB batches both present
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
