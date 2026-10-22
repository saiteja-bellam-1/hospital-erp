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

from app.utils.barcode_draw import (
    DOT_PT,
    MIN_MODULE_DOTS,
    barcode_module_ok,
    barcode_payload,
    dot_size_pt,
    measure_fitted_size,
    normalize_label_dpi,
    resolve_label_symbology,
)
from app.utils.label_pdf_service import (
    TEST_LABEL_BARCODE,
    LabelLayoutConfig,
    build_label_html,
    build_label_pdf,
    font_pt_for_band,
    pharmacy_sticker_bands,
    _label_positions,
)


def test_ean13_check_digit_known():
    assert compute_ean13_check_digit("400638133393") == 1
    code = full_ean13("400638133393")
    assert code == "4006381333931"
    assert validate_ean13(code)


def test_code128_payload_keeps_human_mrn():
    mrn = "KTH-2026-00042"
    assert barcode_payload(mrn, "code128") == mrn
    # Pure digit internal codes still collapse to digits.
    code = generate_patient_mrn_ean13(42)
    assert barcode_payload(code, "code128") == code
def test_internal_generators_valid_ean13():
    for fn, arg in (
        (generate_patient_mrn_ean13, 42),
        (generate_pharmacy_item_ean13, 99),
        (generate_batch_ean13, 501),
    ):
        code = fn(arg)
        assert len(code) == 13
        assert validate_ean13(code)


def test_barcode_lookup_codes_and_patient_search_clause():
    from app.services.barcode_service import (
        barcode_lookup_codes,
        generate_patient_mrn_ean13,
        looks_like_barcode_query,
    )
    from app.services.patient_service import patient_search_match_clause

    code = generate_patient_mrn_ean13(104)
    assert looks_like_barcode_query(code)
    assert code in barcode_lookup_codes(code)
    assert code[:12] in barcode_lookup_codes(code)
    clause = patient_search_match_clause(code)
    assert clause is not True


def test_patient_search_by_mrn_ean13(client, auth_headers, seed_data, TestSessionLocal):
    from app.models.patient import Patient
    from app.services.barcode_service import ensure_patient_mrn_ean13

    db = TestSessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.id == seed_data["patient_id"]).first()
        assert patient is not None
        code = ensure_patient_mrn_ean13(db, patient)
        db.commit()
    finally:
        db.close()

    res = client.post(
        "/api/patients/search",
        headers=auth_headers,
        json={"search_term": code, "sort_by": "name", "sort_order": "asc"},
    )
    assert res.status_code == 200
    patients = res.json().get("patients") or []
    assert any(p.get("id") == seed_data["patient_id"] for p in patients)


def test_lab_orders_search_by_barcode_query(client, auth_headers, seed_data):
    code = generate_patient_mrn_ean13(seed_data["patient_id"])
    res = client.get(
        "/api/lab/orders",
        params={"search": code},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_resolve_symbology_internal_vs_manufacturer():
    batch = generate_batch_ean13(10)
    assert resolve_label_symbology(batch) == "code128"
    assert resolve_label_symbology(generate_patient_mrn_ean13(5)) == "code128"
    assert resolve_label_symbology("4006381333931") == "ean13"


def test_fitted_barcode_stays_inside_box():
    batch = generate_batch_ean13(10)
    # Usable width on a 38 mm pharmacy sticker after side insets.
    max_w, max_h = 36 * mm, 10 * mm
    measured = measure_fitted_size(batch, max_w, max_h)
    assert measured is not None
    w, h, sym, module = measured
    assert sym == "code128"
    assert w <= max_w + 0.05
    assert h <= max_h + 0.05
    assert module + 1e-6 >= (MIN_MODULE_DOTS * DOT_PT) * 0.98
    assert barcode_module_ok(module)


def test_manufacturer_ean13_symbology_and_fit():
    code = "4006381333931"
    max_w, max_h = 36 * mm, 12 * mm
    measured = measure_fitted_size(code, max_w, max_h)
    assert measured is not None
    w, h, sym, _module = measured
    assert sym == "ean13"
    assert w <= max_w + 0.05
    assert h <= max_h + 0.05


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


def test_build_label_html_thermal_has_page_rule():
    layout = LabelLayoutConfig(width_mm=38, height_mm=25, sheet_mode="thermal")
    html = build_label_html(
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
    assert "@page" in html
    assert "38" in html
    assert "<svg" in html.lower()


def test_build_test_label_pdf_and_html():
    layout = LabelLayoutConfig(width_mm=50, height_mm=30, sheet_mode="thermal")
    pdf = build_label_pdf([{}], layout, "test")
    assert pdf[:4] == b"%PDF"
    html = build_label_html([{}], layout, "test")
    assert TEST_LABEL_BARCODE in html
    assert "@page" in html


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
    layout = LabelLayoutConfig(width_mm=70, height_mm=40, sheet_mode="thermal")
    pdf = build_label_pdf(
        [{
            "patient_name": "Jane Doe",
            "mrn": "KTH-2026-00042",
            "mrn_ean13": generate_patient_mrn_ean13(42),  # fallback only; MRN preferred
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
    assert barcode_payload("KTH-2026-00042", "code128") == "KTH-2026-00042"


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


def test_patient_file_label_html_endpoint(client, auth_headers, seed_data):
    pid = seed_data["patient_id"]
    res = client.get(
        f"/api/patients/{pid}/file-label.html",
        params={"source": "registration", "width_mm": 50, "height_mm": 25},
        headers=auth_headers,
    )
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert b"@page" in res.content
    assert b"<svg" in res.content.lower()


def test_pharmacy_type_scales_with_sticker_and_fills_it():
    """Text and bands are shares of the sticker, so a taller sticker gets larger type."""
    small = pharmacy_sticker_bands(38, 25, show_header=True)
    large = pharmacy_sticker_bands(70, 40, show_header=True)
    for bands, height in ((small, 25), (large, 40)):
        used = (
            bands.pad_y_mm * 2
            + bands.gap_mm * bands.gap_count
            + bands.header_mm
            + bands.barcode_mm
            + bands.footer_mm
        )
        assert abs(used - height) < 0.05
    name_small = font_pt_for_band(small.footer_mm / 3, 0.88)
    name_large = font_pt_for_band(large.footer_mm / 3, 0.88)
    assert name_small >= 9.0
    assert name_large > name_small * 1.4


def test_label_dpi_snaps_to_printer_head():
    assert normalize_label_dpi(300) == 300
    assert normalize_label_dpi(280) == 300
    assert normalize_label_dpi("nope") == 203
    layout = LabelLayoutConfig.from_dict({"width_mm": 50, "height_mm": 25, "dpi": 600})
    assert layout.dpi == 600
    code = generate_batch_ean13(10)
    measured = measure_fitted_size(code, 40 * mm, 10 * mm, dpi=300)
    assert measured is not None
    _w, _h, _sym, module = measured
    dots = module / dot_size_pt(300)
    assert abs(dots - round(dots)) < 0.08
    assert barcode_module_ok(module, 300)


def test_wide_barcode_uses_the_sticker_width():
    code = generate_batch_ean13(10)
    measured = measure_fitted_size(code, 90 * mm, 8 * mm)
    assert measured is not None
    w, h, _sym, _module = measured
    assert w >= 0.90 * 90 * mm
    assert h <= 8 * mm + 0.5


def test_pharmacy_html_font_and_barcode_follow_sticker():
    payload = {
        "name": "Paracetamol 500mg",
        "batch_number": "BATCH-A",
        "expiry_date": "2027-12-31",
        "batch_barcode": generate_batch_ean13(10),
    }
    small = build_label_html([payload], LabelLayoutConfig(width_mm=38, height_mm=25), "pharmacy_batch")
    large = build_label_html([payload], LabelLayoutConfig(width_mm=70, height_mm=40), "pharmacy_batch")
    assert 'width="' in small and "mm" in small.split('width="', 1)[1][:12]
    assert "font-size: 5.5pt" not in small
    assert "font-size: 7pt" not in small

    def name_pt(html):
        marker = ".name { font-size: "
        start = html.index(marker) + len(marker)
        return float(html[start:html.index("pt", start)])

    assert name_pt(large) > name_pt(small) * 1.4


def test_build_labels_still_pdf_after_band_fix():
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
    html = build_label_html(
        [{
            "name": "Paracetamol 500mg",
            "batch_number": "BATCH-A",
            "expiry_date": "2027-12-31",
            "batch_barcode": generate_batch_ean13(10),
        }],
        layout,
        "pharmacy_batch",
    )
    assert "zone-header" in html and "zone-footer" in html
