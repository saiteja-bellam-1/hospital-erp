"""Edge cases + end-to-end for hospital-wide discharge summary templates."""

from io import BytesIO

from inpatient_test_helpers import API, discharge_active_admissions

from app.services.discharge_summary_template_service import (
    build_default_template,
    coerce_custom_fields,
    validate_template,
)


def _pdf_text(content: bytes) -> str:
    from PyPDF2 import PdfReader
    reader = PdfReader(BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def _admit(client, auth_headers, seed_data, room_number):
    discharge_active_admissions(client, auth_headers, seed_data["patient_id"])
    room = client.post(
        f"{API}/rooms",
        json={
            "room_number": room_number,
            "room_type": "general",
            "bed_count": 1,
            "room_charge_per_day": 400.0,
        },
        headers=auth_headers,
    )
    assert room.status_code == 201, room.text
    adm = client.post(
        f"{API}/admissions",
        json={
            "patient_id": seed_data["patient_id"],
            "admitting_doctor_id": seed_data["doctor_user_id"],
            "room_id": room.json()["id"],
            "admission_type": "elective",
        },
        headers=auth_headers,
    )
    assert adm.status_code == 201, adm.text
    return adm.json()["id"]


class TestTemplateValidationEdges:
    def test_reject_empty_blocks(self):
        try:
            validate_template({
                "version": 1,
                "document_title": "X",
                "show_department_line": True,
                "blocks": [],
            })
            assert False, "expected ValueError"
        except ValueError as e:
            assert "non-empty" in str(e).lower() or "blocks" in str(e).lower()

    def test_reject_duplicate_structural(self):
        tpl = build_default_template()
        tpl["blocks"].append({"id": "dup", "type": "patient_info"})
        try:
            validate_template(tpl)
            assert False, "expected ValueError"
        except ValueError as e:
            assert "Duplicate" in str(e)

    def test_reject_empty_static_text(self):
        try:
            validate_template({
                "version": 1,
                "document_title": "X",
                "show_department_line": True,
                "blocks": [{
                    "id": "1",
                    "type": "static_text",
                    "label": "Note",
                    "content": "   ",
                }],
            })
            assert False, "expected ValueError"
        except ValueError as e:
            assert "empty" in str(e).lower()

    def test_coerce_custom_fields_json_string(self):
        assert coerce_custom_fields('{"a": "1"}') == {"a": "1"}
        assert coerce_custom_fields(None) == {}
        assert coerce_custom_fields([1, 2]) == {}
        assert coerce_custom_fields({"x": 5}) == {"x": "5"}


class TestTemplateApiEdges:
    def test_put_invalid_template_returns_400(self, client, auth_headers):
        client.post(f"{API}/discharge-summary-template/reset", headers=auth_headers)
        bad = client.put(
            f"{API}/discharge-summary-template",
            json={
                "version": 1,
                "document_title": "X",
                "show_department_line": True,
                "blocks": [
                    {"id": "1", "type": "patient_info"},
                    {"id": "2", "type": "patient_info"},
                ],
            },
            headers=auth_headers,
        )
        assert bad.status_code == 400, bad.text

    def test_preview_without_body_uses_saved_template(self, client, auth_headers):
        client.post(f"{API}/discharge-summary-template/reset", headers=auth_headers)
        r = client.post(f"{API}/discharge-summary-template/preview", headers=auth_headers)
        assert r.status_code == 200, r.text
        assert "pdf" in r.headers["content-type"].lower()
        assert r.content[:4] == b"%PDF"

    def test_preview_rejects_invalid_draft(self, client, auth_headers):
        r = client.post(
            f"{API}/discharge-summary-template/preview",
            json={
                "version": 1,
                "document_title": "X",
                "show_department_line": True,
                "blocks": [],
            },
            headers=auth_headers,
        )
        assert r.status_code == 400, r.text

    def test_html_special_chars_in_preview(self, client, auth_headers):
        tpl = build_default_template()
        tpl["document_title"] = "A & B <C>"
        tpl["blocks"] = [
            b for b in tpl["blocks"]
            if b["type"] in ("patient_info", "signatures")
        ]
        tpl["blocks"].append({
            "id": "st",
            "type": "static_text",
            "label": "Note <tag>",
            "content": "Vitamins A & B < C",
        })
        r = client.post(
            f"{API}/discharge-summary-template/preview",
            json={
                "version": 1,
                "document_title": tpl["document_title"],
                "show_department_line": True,
                "blocks": tpl["blocks"],
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        text = _pdf_text(r.content)
        assert "Vitamins A & B" in text or "Vitamins A &amp; B" in text or "A & B" in text
        assert "Note" in text


class TestTemplateE2E:
    """Full admin customize → doctor write → finalize → print → discharge."""

    def test_remove_primary_diagnosis_allows_finalize_without_it(
        self, client, auth_headers, seed_data,
    ):
        client.post(f"{API}/discharge-summary-template/reset", headers=auth_headers)
        base = client.get(f"{API}/discharge-summary-template", headers=auth_headers).json()
        blocks = [
            b for b in base["blocks"]
            if not (
                b.get("type") == "standard_section"
                and b.get("field_key") == "primary_diagnosis"
            )
        ]
        # Require course instead
        for b in blocks:
            if b.get("type") == "standard_section" and b.get("field_key") == "course_in_hospital":
                b["required"] = True
        put = client.put(
            f"{API}/discharge-summary-template",
            json={
                "version": 1,
                "document_title": base["document_title"],
                "show_department_line": True,
                "blocks": blocks,
            },
            headers=auth_headers,
        )
        assert put.status_code == 200, put.text

        adm_id = _admit(client, auth_headers, seed_data, "E2E-NO-PDX")
        # No primary diagnosis — should still finalize if course present
        client.put(
            f"{API}/admissions/{adm_id}/discharge-summary",
            json={"course_in_hospital": "Recovered well"},
            headers=auth_headers,
        )
        fin = client.post(
            f"{API}/admissions/{adm_id}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert fin.status_code == 200, fin.text

        # Missing required course should fail
        client.post(
            f"{API}/admissions/{adm_id}/discharge-summary/reopen",
            headers=auth_headers,
        )
        client.put(
            f"{API}/admissions/{adm_id}/discharge-summary",
            json={"course_in_hospital": ""},
            headers=auth_headers,
        )
        bad = client.post(
            f"{API}/admissions/{adm_id}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert bad.status_code == 400, bad.text

    def test_empty_custom_field_omitted_from_pdf(self, client, auth_headers, seed_data):
        client.post(f"{API}/discharge-summary-template/reset", headers=auth_headers)
        base = client.get(f"{API}/discharge-summary-template", headers=auth_headers).json()
        blocks = list(base["blocks"])
        blocks.append({
            "id": "cf-empty",
            "type": "custom_field",
            "field_key": "optional_note",
            "label": "Optional Note Section",
            "input": "textarea",
            "required": False,
        })
        client.put(
            f"{API}/discharge-summary-template",
            json={
                "version": 1,
                "document_title": "DISCHARGE SUMMARY",
                "show_department_line": True,
                "blocks": blocks,
            },
            headers=auth_headers,
        )

        adm_id = _admit(client, auth_headers, seed_data, "E2E-EMPTY-CF")
        client.put(
            f"{API}/admissions/{adm_id}/discharge-summary",
            json={
                "primary_diagnosis": "Viral fever",
                "custom_fields": {"optional_note": "   "},
            },
            headers=auth_headers,
        )
        fin = client.post(
            f"{API}/admissions/{adm_id}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert fin.status_code == 200, fin.text
        pdf = client.get(
            f"{API}/admissions/{adm_id}/discharge-summary/pdf",
            headers=auth_headers,
        )
        assert pdf.status_code == 200
        text = _pdf_text(pdf.content)
        assert "Optional Note Section" not in text
        assert "Viral fever" in text

    def test_full_flow_customize_write_print_discharge(
        self, client, auth_headers, seed_data,
    ):
        client.post(f"{API}/discharge-summary-template/reset", headers=auth_headers)
        base = client.get(f"{API}/discharge-summary-template", headers=auth_headers).json()
        # Slim template: patient, consultants, renamed diagnosis, custom, static, signatures
        blocks = [
            {"id": "pi", "type": "patient_info"},
            {"id": "co", "type": "consultants", "label": "Treating Team"},
            {
                "id": "pd",
                "type": "standard_section",
                "field_key": "primary_diagnosis",
                "label": "Discharge Diagnosis",
                "required": True,
            },
            {
                "id": "cf",
                "type": "custom_field",
                "field_key": "ward_instruction",
                "label": "Ward Instruction",
                "input": "textarea",
                "required": True,
            },
            {
                "id": "st",
                "type": "static_text",
                "label": "Hospital Note",
                "content": "Bring this summary to OPD.",
            },
            {"id": "med", "type": "medications_table", "label": "Home Medicines"},
            {"id": "sig", "type": "signatures"},
        ]
        saved = client.put(
            f"{API}/discharge-summary-template",
            json={
                "version": 1,
                "document_title": "E2E DISCHARGE SUMMARY",
                "show_department_line": False,
                "blocks": blocks,
            },
            headers=auth_headers,
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["is_default"] is False

        # Preview reflects draft
        preview = client.post(
            f"{API}/discharge-summary-template/preview",
            json=saved.json(),
            headers=auth_headers,
        )
        assert preview.status_code == 200
        ptext = _pdf_text(preview.content)
        assert "Hospital Note" in ptext
        assert "Bring this summary to OPD" in ptext
        assert "Discharge Diagnosis" in ptext
        assert "Ward Instruction" in ptext

        adm_id = _admit(client, auth_headers, seed_data, "E2E-FULL")

        # Required custom missing → 400
        client.put(
            f"{API}/admissions/{adm_id}/discharge-summary",
            json={"primary_diagnosis": "UTI"},
            headers=auth_headers,
        )
        assert client.post(
            f"{API}/admissions/{adm_id}/discharge-summary/finalize",
            headers=auth_headers,
        ).status_code == 400

        upsert = client.put(
            f"{API}/admissions/{adm_id}/discharge-summary",
            json={
                "primary_diagnosis": "UTI",
                "custom_fields": {"ward_instruction": "Force fluids"},
                "take_home_medications": [{
                    "medicine_name": "Ciprofloxacin 500mg",
                    "dosage": "1 tablet",
                    "frequency": "BD",
                    "duration": "5 days",
                    "quantity": 10,
                }],
            },
            headers=auth_headers,
        )
        assert upsert.status_code == 200, upsert.text
        assert upsert.json()["custom_fields"]["ward_instruction"] == "Force fluids"

        # Draft preview works
        draft_pdf = client.get(
            f"{API}/admissions/{adm_id}/discharge-summary/pdf/preview",
            headers=auth_headers,
        )
        assert draft_pdf.status_code == 200

        fin = client.post(
            f"{API}/admissions/{adm_id}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert fin.status_code == 200, fin.text
        assert fin.json()["status"] == "ready"

        pdf = client.get(
            f"{API}/admissions/{adm_id}/discharge-summary/pdf",
            headers=auth_headers,
        )
        assert pdf.status_code == 200
        text = _pdf_text(pdf.content)
        assert "E2E DISCHARGE SUMMARY" in text or "DISCHARGE SUMMARY" in text
        assert "Discharge Diagnosis" in text
        assert "UTI" in text
        assert "Ward Instruction" in text
        assert "Force fluids" in text
        assert "Hospital Note" in text
        assert "Ciprofloxacin" in text
        assert "Family History" not in text  # removed from template
        assert "Treating Team" in text

        # Discharge locks summary
        disc = client.post(
            f"{API}/admissions/{adm_id}/discharge",
            json={
                "discharge_type": "normal",
                "condition_on_discharge": "stable",
                "force_outstanding_balance": True,
                "force_unacknowledged_alerts": True,
                "force_missing_consents": True,
                "force_no_final_bill": True,
                "override_reason": "e2e template test",
            },
            headers=auth_headers,
        )
        assert disc.status_code == 201, disc.text
        summary = client.get(
            f"{API}/admissions/{adm_id}/discharge-summary",
            headers=auth_headers,
        )
        assert summary.json()["status"] == "locked"

        # Locked PDF still printable
        locked_pdf = client.get(
            f"{API}/admissions/{adm_id}/discharge-summary/pdf",
            headers=auth_headers,
        )
        assert locked_pdf.status_code == 200

        # Reset template for other tests
        client.post(f"{API}/discharge-summary-template/reset", headers=auth_headers)

    def test_whitespace_required_custom_rejected(self, client, auth_headers, seed_data):
        client.post(f"{API}/discharge-summary-template/reset", headers=auth_headers)
        base = client.get(f"{API}/discharge-summary-template", headers=auth_headers).json()
        blocks = list(base["blocks"])
        blocks.append({
            "id": "req-ws",
            "type": "custom_field",
            "field_key": "must_fill",
            "label": "Must Fill",
            "input": "text",
            "required": True,
        })
        client.put(
            f"{API}/discharge-summary-template",
            json={
                "version": 1,
                "document_title": "DISCHARGE SUMMARY",
                "show_department_line": True,
                "blocks": blocks,
            },
            headers=auth_headers,
        )
        adm_id = _admit(client, auth_headers, seed_data, "E2E-WS")
        client.put(
            f"{API}/admissions/{adm_id}/discharge-summary",
            json={
                "primary_diagnosis": "OK",
                "custom_fields": {"must_fill": "  \n  "},
            },
            headers=auth_headers,
        )
        bad = client.post(
            f"{API}/admissions/{adm_id}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert bad.status_code == 400, bad.text
        client.post(f"{API}/discharge-summary-template/reset", headers=auth_headers)
