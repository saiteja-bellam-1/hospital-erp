"""Barcode service and label PDF smoke tests."""
from app.services.barcode_service import (
    compute_ean13_check_digit,
    full_ean13,
    generate_patient_mrn_ean13,
    generate_pharmacy_item_ean13,
    generate_batch_ean13,
    normalize_scanned_barcode,
    validate_ean13,
)
from reportlab.lib.units import mm

from app.utils.label_pdf_service import LabelLayoutConfig, build_label_pdf, _label_positions


def test_ean13_check_digit_known():
    assert compute_ean13_check_digit("400638133393") == 1
    code = full_ean13("400638133393")
    assert code == "4006381333931"
    assert validate_ean13(code)


def test_internal_generators_valid_ean13():
    for fn, arg in (
        (generate_patient_mrn_ean13, 42),
        (generate_pharmacy_item_ean13, 99),
        (generate_batch_ean13, 501),
    ):
        code = fn(arg)
        assert len(code) == 13
        assert validate_ean13(code)


def test_normalize_scanned_barcode():
    assert normalize_scanned_barcode("4006381333931") == "4006381333931"
    assert normalize_scanned_barcode("400638133393") == "4006381333931"
    assert normalize_scanned_barcode("300000") is None
    assert normalize_scanned_barcode("000443") is None


def test_build_lab_label_pdf():
    layout = LabelLayoutConfig(width_mm=50, height_mm=30)
    pdf = build_label_pdf(
        [{
            "patient_name": "John Doe",
            "sample_id": "S-260828-0001",
            "mrn": "KTH-2026-00001",
            "sample_ean13": generate_patient_mrn_ean13(1),
            "mrn_ean13": generate_patient_mrn_ean13(2),
        }],
        layout,
        "lab_sample",
        lab_display_name="Test Lab",
    )
    assert pdf[:4] == b"%PDF"


def test_build_pharmacy_label_pdf():
    layout = LabelLayoutConfig(width_mm=38, height_mm=25)
    pdf = build_label_pdf(
        [{
            "name": "Paracetamol 500mg",
            "batch_number": "BATCH-A",
            "expiry_date": "2027-12-31",
            "batch_barcode": generate_batch_ean13(10),
        }],
        layout,
        "pharmacy_batch",
        pharmacy_display_name="Test Pharmacy",
    )
    assert pdf[:4] == b"%PDF"


def test_thermal_label_position_not_negative_with_margins():
    layout = LabelLayoutConfig(
        width_mm=38,
        height_mm=25,
        margin_top_mm=2.0,
        margin_left_mm=2.0,
        sheet_mode="thermal",
    )
    for x, y in _label_positions(layout):
        assert x >= 0
        assert y >= 0


def test_three_labels_across_one_thermal_row():
    """Three batches with 3-across roll land on one horizontal peel line."""
    layout = LabelLayoutConfig.from_dict({
        "width_mm": 38,
        "height_mm": 25,
        "labels_per_row": 3,
        "labels_per_column": 1,
        "gutter_mm": 2,
        "sheet_mode": "thermal",
    })
    positions = _label_positions(layout)
    assert len(positions) == 3
    ys = {round(y / mm, 2) for _, y in positions}
    assert len(ys) == 1, "all slots must share one row (same y)"
    xs = sorted(round(x / mm, 2) for x, _ in positions)
    assert xs == [0.0, 40.0, 80.0]

    labels = [
        {"name": f"Med {i}", "batch_number": f"B{i}", "expiry_date": "2027-01-01",
         "batch_barcode": generate_batch_ean13(i)}
        for i in (1, 2, 3)
    ]
    pdf = build_label_pdf(labels, layout, "pharmacy_batch", pharmacy_display_name="Test")
    assert pdf[:4] == b"%PDF"


def test_thermal_misconfigured_column_becomes_row():
    """labels_per_column=3 with row=1 is treated as 3 across (not stacked)."""
    layout = LabelLayoutConfig.from_dict({
        "width_mm": 38,
        "height_mm": 25,
        "labels_per_row": 1,
        "labels_per_column": 3,
        "sheet_mode": "thermal",
    })
    assert layout.labels_per_row == 3
    assert layout.labels_per_column == 1
    positions = _label_positions(layout)
    ys = {y for _, y in positions}
    assert len(ys) == 1


def test_build_pharmacy_label_pdf_with_margins():
    layout = LabelLayoutConfig(
        width_mm=38,
        height_mm=25,
        margin_top_mm=2.0,
        margin_left_mm=2.0,
        sheet_mode="thermal",
    )
    pdf = build_label_pdf(
        [{
            "name": "AZEE500",
            "batch_number": "JHGJGHJH",
            "expiry_date": "2027-01-31",
            "batch_barcode": generate_batch_ean13(10),
        }],
        layout,
        "pharmacy_batch",
        pharmacy_display_name="TANEESH PHARMACY",
    )
    assert pdf[:4] == b"%PDF"


def test_build_patient_file_label_pdf_with_ean13():
    code = generate_patient_mrn_ean13(42)
    layout = LabelLayoutConfig(width_mm=70, height_mm=40, sheet_mode="thermal")
    pdf = build_label_pdf(
        [{
            "patient_name": "Jane Doe",
            "mrn": "KTH-2026-00042",
            "mrn_ean13": code,
            "pat_type": "Self Paying",
            "age_gender": "32Y / F",
            "bill_date": "09-Sep-2026",
            "order_no": "APT-001",
            "ref_name": "Dr. Ref",
        }],
        layout,
        "patient_file",
    )
    assert pdf[:4] == b"%PDF"
    assert validate_ean13(code)


def test_build_patient_file_label_pdf_omits_order_when_blank():
    layout = LabelLayoutConfig(width_mm=70, height_mm=40, sheet_mode="thermal")
    pdf = build_label_pdf(
        [{
            "patient_name": "No Order Patient",
            "mrn": "KTH-2026-00001",
            "mrn_ean13": generate_patient_mrn_ean13(1),
            "pat_type": "Self Paying",
            "age_gender": "10Y / M",
            "bill_date": "09-Sep-2026",
            "order_no": "",
            "ref_name": "",
        }],
        layout,
        "patient_file",
    )
    assert pdf[:4] == b"%PDF"


def test_merge_label_layout_forces_single_thermal_1up():
    from app.utils.label_pdf_service import merge_label_layout, _page_size
    layout = merge_label_layout(
        {
            "width_mm": 38,
            "height_mm": 25,
            "labels_per_row": 3,
            "labels_per_column": 1,
            "gutter_mm": 2,
            "sheet_mode": "thermal",
        },
        {"width_mm": 50, "height_mm": 30},
        single_label=True,
    )
    assert layout.labels_per_row == 1
    assert layout.labels_per_column == 1
    assert layout.width_mm == 50
    assert layout.height_mm == 30
    page_w, page_h = _page_size(layout)
    assert abs(page_w / mm - 50) < 0.01
    assert abs(page_h / mm - 30) < 0.01


def test_merge_label_layout_honors_explicit_across_override():
    from app.utils.label_pdf_service import merge_label_layout, _page_size
    layout = merge_label_layout(
        {"width_mm": 38, "height_mm": 25, "labels_per_row": 1, "sheet_mode": "thermal"},
        {"width_mm": 38, "height_mm": 25, "labels_per_row": 3, "gutter_mm": 2},
        single_label=True,
    )
    assert layout.labels_per_row == 3
    assert layout.labels_per_column == 1
    page_w, page_h = _page_size(layout)
    assert abs(page_w / mm - (3 * 38 + 2 * 2)) < 0.01
    assert abs(page_h / mm - 25) < 0.01


def test_patient_file_label_endpoint(client, auth_headers, seed_data):
    pid = seed_data["patient_id"]
    res = client.get(
        f"/api/patients/{pid}/file-label.pdf",
        params={"source": "registration", "width_mm": 50, "height_mm": 25},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/pdf")
    assert res.content[:4] == b"%PDF"


def test_patient_file_label_invalid_patient_404(client, auth_headers, seed_data):
    res = client.get(
        "/api/patients/99999999/file-label.pdf",
        headers=auth_headers,
    )
    assert res.status_code == 404

