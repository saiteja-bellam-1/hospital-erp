"""License gating for branding and document customisations."""


def test_enabled_modules_omits_customisation_without_license(client, auth_headers, seed_data):
    res = client.get("/api/system/enabled-modules", headers=auth_headers)
    assert res.status_code == 200
    by_name = {row["module_name"]: row["is_enabled"] for row in res.json()}
    assert by_name.get("customisation") is False


def test_enabled_modules_includes_customisation_when_licensed(
    client, auth_headers, customisation_license, seed_data
):
    res = client.get("/api/system/enabled-modules", headers=auth_headers)
    assert res.status_code == 200
    by_name = {row["module_name"]: row["is_enabled"] for row in res.json()}
    assert by_name.get("customisation") is True


def test_unlicensed_branding_ignores_stored_custom_name(client, db_session, seed_data):
    from app.models.hospital import Hospital

    hospital = db_session.query(Hospital).first()
    hospital.name = "Stored Custom Name"
    hospital.logo_url = "/uploads/module-config/x.png"
    hospital.favicon_url = "/uploads/module-config/y.png"
    db_session.commit()

    res = client.get("/api/hospital/branding/public")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "KT HEALTH ERP"
    assert data["logo_url"] is None
    assert data["favicon_url"] is None
    assert data["customisation_licensed"] is False


def test_print_settings_get_reports_license_flag(client, auth_headers, seed_data):
    res = client.get("/api/hospital/print-settings", headers=auth_headers)
    assert res.status_code == 200
    assert res.json()["customisation_licensed"] is False


def test_print_settings_put_letterhead_requires_license(client, auth_headers, seed_data):
    res = client.put(
        "/api/hospital/print-settings",
        headers=auth_headers,
        json={"letterhead_gap_mm": 40},
    )
    assert res.status_code == 403
    assert "not included" in res.json()["detail"].lower()


def test_print_settings_put_labels_allowed_without_license(client, auth_headers, seed_data):
    res = client.put(
        "/api/hospital/print-settings",
        headers=auth_headers,
        json={
            "lab_label_settings": {
                "width_mm": 50,
                "height_mm": 30,
                "labels_per_row": 1,
                "labels_per_column": 1,
                "margin_top_mm": 2,
                "margin_left_mm": 2,
                "gutter_mm": 2,
                "sheet_mode": "thermal",
                "sheet_width_mm": 210,
                "sheet_height_mm": 297,
                "show_lab_name": True,
                "lab_name_override": None,
            }
        },
    )
    assert res.status_code == 200


def test_print_settings_put_letterhead_when_licensed(
    client, auth_headers, customisation_license, seed_data
):
    res = client.put(
        "/api/hospital/print-settings",
        headers=auth_headers,
        json={"include_header_on_pdfs": True},
    )
    assert res.status_code == 200


def test_print_settings_preview_requires_license(client, auth_headers, seed_data):
    res = client.post(
        "/api/hospital/print-settings/preview",
        headers=auth_headers,
        json={"report_type": "opd_bill"},
    )
    assert res.status_code == 403
