"""Discharge summary workflow: doctor write, finalize, print gate, discharge lock."""

from io import BytesIO

from inpatient_test_helpers import API, discharge_active_admissions, ready_discharge_summary

_state: dict = {}


def _pdf_text(content: bytes) -> str:
    from PyPDF2 import PdfReader
    reader = PdfReader(BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


class TestDischargeSummaryWorkflow:
    def test_setup_room_and_admission(self, client, auth_headers, seed_data):
        discharge_active_admissions(client, auth_headers, seed_data["patient_id"])
        r = client.post(
            f"{API}/rooms",
            json={
                "room_number": "DS-1",
                "room_type": "general",
                "bed_count": 2,
                "room_charge_per_day": 500.0,
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        _state["room_id"] = r.json()["id"]

        r = client.post(
            f"{API}/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": _state["room_id"],
                "admission_type": "elective",
                "admission_reason": "Discharge summary test",
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        _state["admission_id"] = r.json()["id"]
        assert r.json()["status"] == "admitted"

    def test_normal_discharge_blocked_without_summary(self, client, auth_headers):
        r = client.post(
            f"{API}/admissions/{_state['admission_id']}/discharge",
            json={
                "discharge_type": "normal",
                "condition_on_discharge": "stable",
            },
            headers=auth_headers,
        )
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "discharge_summary_not_ready"

    def test_upsert_and_finalize_summary(self, client, auth_headers):
        r = client.put(
            f"{API}/admissions/{_state['admission_id']}/discharge-summary",
            json={
                "provisional_diagnosis": "Acute appendicitis",
                "course_in_hospital": "Uneventful recovery after lap appendectomy",
                "discharge_advice": "Soft diet for 3 days",
                "follow_up": "OPD in 7 days",
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "draft"

        r = client.get(
            f"{API}/admissions/{_state['admission_id']}/discharge-summary",
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text

        bad = client.post(
            f"{API}/admissions/{_state['admission_id']}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert bad.status_code == 400, bad.text

        client.put(
            f"{API}/admissions/{_state['admission_id']}/discharge-summary",
            json={"primary_diagnosis": "Acute appendicitis, post-op"},
            headers=auth_headers,
        )
        fin = client.post(
            f"{API}/admissions/{_state['admission_id']}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert fin.status_code == 200, fin.text
        assert fin.json()["status"] == "ready"

    def test_reopen_submitted_summary(self, client, auth_headers):
        adm_id = _state['admission_id']
        reopen = client.post(
            f"{API}/admissions/{adm_id}/discharge-summary/reopen",
            headers=auth_headers,
        )
        assert reopen.status_code == 200, reopen.text
        assert reopen.json()["status"] == "draft"

        bad = client.post(
            f"{API}/admissions/{adm_id}/discharge-summary/reopen",
            headers=auth_headers,
        )
        assert bad.status_code == 400, bad.text

    def test_pdf_preview_works_for_draft(self, client, auth_headers):
        adm_id = _state['admission_id']
        client.put(
            f"{API}/admissions/{adm_id}/discharge-summary",
            json={"primary_diagnosis": "Acute appendicitis"},
            headers=auth_headers,
        )
        preview = client.get(
            f"{API}/admissions/{adm_id}/discharge-summary/pdf/preview",
            headers=auth_headers,
        )
        assert preview.status_code == 200, preview.text
        assert "pdf" in preview.headers["content-type"].lower()

    def test_pdf_blocked_until_ready(self, client, auth_headers):
        adm_id = _state["admission_id"]
        draft_put = client.put(
            f"{API}/admissions/{adm_id}/discharge-summary",
            json={"primary_diagnosis": "Draft only"},
            headers=auth_headers,
        )
        assert draft_put.status_code == 200, draft_put.text

        blocked = client.get(
            f"{API}/admissions/{adm_id}/discharge-summary/pdf",
            headers=auth_headers,
        )
        assert blocked.status_code == 400, blocked.text

        ready_discharge_summary(client, adm_id, auth_headers)
        ok = client.get(
            f"{API}/admissions/{adm_id}/discharge-summary/pdf",
            headers=auth_headers,
        )
        assert ok.status_code == 200, ok.text
        assert "pdf" in ok.headers["content-type"].lower()

    def test_discharge_locks_summary(self, client, auth_headers):
        r = client.post(
            f"{API}/admissions/{_state['admission_id']}/discharge",
            json={
                "discharge_type": "normal",
                "condition_on_discharge": "stable",
                "force_outstanding_balance": True,
                "force_unacknowledged_alerts": True,
                "force_missing_consents": True,
                "force_no_final_bill": True,
                "override_reason": "test discharge",
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text

        summary = client.get(
            f"{API}/admissions/{_state['admission_id']}/discharge-summary",
            headers=auth_headers,
        )
        assert summary.status_code == 200, summary.text
        assert summary.json()["status"] == "locked"

        locked = client.put(
            f"{API}/admissions/{_state['admission_id']}/discharge-summary",
            json={"primary_diagnosis": "Should not save"},
            headers=auth_headers,
        )
        assert locked.status_code == 400, locked.text

    def test_death_discharge_bypasses_summary(self, client, auth_headers, seed_data):
        discharge_active_admissions(client, auth_headers, seed_data["patient_id"])
        r = client.post(
            f"{API}/rooms",
            json={
                "room_number": "DS-DEATH",
                "room_type": "general",
                "bed_count": 1,
                "room_charge_per_day": 500.0,
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        adm = client.post(
            f"{API}/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": r.json()["id"],
                "admission_type": "emergency",
            },
            headers=auth_headers,
        )
        assert adm.status_code == 201, adm.text
        death = client.post(
            f"{API}/admissions/{adm.json()['id']}/discharge",
            json={
                "discharge_type": "death",
                "condition_on_discharge": "critical",
                "force_outstanding_balance": True,
                "force_unacknowledged_alerts": True,
                "force_missing_consents": True,
                "override_reason": "test death bypass",
            },
            headers=auth_headers,
        )
        assert death.status_code == 201, death.text


class TestDischargeSummaryTemplate:
    """Hospital-wide block template: customize layout + preview."""

    def test_get_default_template(self, client, auth_headers):
        r = client.get(f"{API}/discharge-summary-template", headers=auth_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["version"] == 1
        assert data["document_title"] == "DISCHARGE SUMMARY"
        assert data.get("is_default") is True
        types = [b["type"] for b in data["blocks"]]
        assert "patient_info" in types
        assert "standard_section" in types
        assert "medications_table" in types
        assert "primary_diagnosis" in {
            b["field_key"] for b in data["blocks"] if b["type"] == "standard_section"
        }

    def test_save_custom_template_and_preview(self, client, auth_headers):
        base = client.get(f"{API}/discharge-summary-template", headers=auth_headers).json()
        blocks = [
            b for b in base["blocks"]
            if not (b.get("type") == "standard_section" and b.get("field_key") == "family_history")
        ]
        # Rename primary diagnosis
        for b in blocks:
            if b.get("type") == "standard_section" and b.get("field_key") == "primary_diagnosis":
                b["label"] = "Final Diagnosis"
        blocks.append({
            "id": "custom-1",
            "type": "custom_field",
            "field_key": "dialysis_notes",
            "label": "Dialysis Notes",
            "input": "textarea",
            "required": False,
        })
        blocks.append({
            "id": "static-1",
            "type": "static_text",
            "label": "Hospital Policy",
            "content": "Bring this summary to your next OPD visit.",
        })
        # Move course before primary diagnosis
        course = next(
            b for b in blocks
            if b.get("type") == "standard_section" and b.get("field_key") == "course_in_hospital"
        )
        primary = next(
            b for b in blocks
            if b.get("type") == "standard_section" and b.get("field_key") == "primary_diagnosis"
        )
        blocks.remove(course)
        blocks.insert(blocks.index(primary), course)

        payload = {
            "version": 1,
            "document_title": "CUSTOM DISCHARGE SUMMARY",
            "show_department_line": True,
            "blocks": blocks,
        }
        preview = client.post(
            f"{API}/discharge-summary-template/preview",
            json=payload,
            headers=auth_headers,
        )
        assert preview.status_code == 200, preview.text
        assert "pdf" in preview.headers["content-type"].lower()
        text = _pdf_text(preview.content)
        assert "Hospital Policy" in text
        assert "Dialysis Notes" in text or "Sample content for Dialysis" in text
        assert "Final Diagnosis" in text
        assert "Family History" not in text

        saved = client.put(
            f"{API}/discharge-summary-template",
            json=payload,
            headers=auth_headers,
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["is_default"] is False
        assert saved.json()["document_title"] == "CUSTOM DISCHARGE SUMMARY"

        got = client.get(f"{API}/discharge-summary-template", headers=auth_headers)
        assert got.status_code == 200
        assert got.json()["document_title"] == "CUSTOM DISCHARGE SUMMARY"
        assert "dialysis_notes" in {
            b["field_key"] for b in got.json()["blocks"] if b["type"] == "custom_field"
        }

    def test_custom_fields_on_summary_and_pdf(self, client, auth_headers, seed_data):
        discharge_active_admissions(client, auth_headers, seed_data["patient_id"])
        room = client.post(
            f"{API}/rooms",
            json={
                "room_number": "DS-TPL",
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
        adm_id = adm.json()["id"]

        # Ensure template has a required dialysis_notes custom field
        tpl = client.get(f"{API}/discharge-summary-template", headers=auth_headers).json()
        blocks = list(tpl["blocks"])
        found = False
        for b in blocks:
            if b.get("type") == "custom_field" and b.get("field_key") == "dialysis_notes":
                b["required"] = True
                b["label"] = "Dialysis Notes"
                found = True
        if not found:
            blocks.append({
                "id": "custom-dialysis",
                "type": "custom_field",
                "field_key": "dialysis_notes",
                "label": "Dialysis Notes",
                "input": "textarea",
                "required": True,
            })
        put = client.put(f"{API}/discharge-summary-template", json={
            "version": 1,
            "document_title": tpl["document_title"],
            "show_department_line": tpl.get("show_department_line", True),
            "blocks": blocks,
        }, headers=auth_headers)
        assert put.status_code == 200, put.text
        assert any(
            b.get("field_key") == "dialysis_notes" and b.get("required")
            for b in put.json()["blocks"] if b.get("type") == "custom_field"
        )

        # Finalize without required custom field should fail
        client.put(
            f"{API}/admissions/{adm_id}/discharge-summary",
            json={
                "primary_diagnosis": "CKD stage 5",
                "custom_fields": {},
            },
            headers=auth_headers,
        )
        bad = client.post(
            f"{API}/admissions/{adm_id}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert bad.status_code == 400, bad.text

        client.put(
            f"{API}/admissions/{adm_id}/discharge-summary",
            json={
                "primary_diagnosis": "CKD stage 5",
                "custom_fields": {"dialysis_notes": "HD thrice weekly via AV fistula"},
            },
            headers=auth_headers,
        )
        fin = client.post(
            f"{API}/admissions/{adm_id}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert fin.status_code == 200, fin.text
        assert fin.json().get("custom_fields", {}).get("dialysis_notes")

        pdf = client.get(
            f"{API}/admissions/{adm_id}/discharge-summary/pdf",
            headers=auth_headers,
        )
        assert pdf.status_code == 200, pdf.text
        text = _pdf_text(pdf.content)
        assert "Dialysis Notes" in text
        assert "HD thrice weekly" in text

    def test_reset_template(self, client, auth_headers):
        r = client.post(f"{API}/discharge-summary-template/reset", headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.json().get("is_default") is True
        assert r.json()["document_title"] == "DISCHARGE SUMMARY"


class TestDamaDischargeSummary:
    def test_dama_summary_requires_advice_and_prints_it(self, client, auth_headers, seed_data):
        discharge_active_admissions(client, auth_headers, seed_data["patient_id"])
        room = client.post(
            f"{API}/rooms",
            json={
                "room_number": "DS-DAMA",
                "room_type": "general",
                "bed_count": 1,
                "room_charge_per_day": 500.0,
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
                "admission_reason": "DAMA summary test",
            },
            headers=auth_headers,
        )
        assert adm.status_code == 201, adm.text
        admission_id = adm.json()["id"]

        incomplete = client.put(
            f"{API}/admissions/{admission_id}/discharge-summary",
            json={
                "primary_diagnosis": "Unresolved pneumonia",
                "discharge_type": "against_advice",
                "condition_on_discharge": "unchanged",
                "primary_doctor_id": seed_data["doctor_user_id"],
            },
            headers=auth_headers,
        )
        assert incomplete.status_code == 200, incomplete.text
        blocked = client.post(
            f"{API}/admissions/{admission_id}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert blocked.status_code == 400, blocked.text
        assert "Medical advice" in blocked.json()["detail"]

        complete = client.put(
            f"{API}/admissions/{admission_id}/discharge-summary",
            json={
                "primary_diagnosis": "Unresolved pneumonia",
                "discharge_type": "against_advice",
                "condition_on_discharge": "unchanged",
                "primary_doctor_id": seed_data["doctor_user_id"],
                "dama_medical_advice": "Stay for IV antibiotics for five more days",
                "dama_risks_explained": "Risk of sepsis if treatment is stopped",
                "dama_advice_acknowledged": True,
                "dama_absolves_acknowledged": True,
            },
            headers=auth_headers,
        )
        assert complete.status_code == 200, complete.text
        assert complete.json()["dama_advice_acknowledged"] is True
        fin = client.post(
            f"{API}/admissions/{admission_id}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert fin.status_code == 200, fin.text

        pdf = client.get(
            f"{API}/admissions/{admission_id}/discharge-summary/pdf",
            headers=auth_headers,
        )
        assert pdf.status_code == 200, pdf.text
        text = _pdf_text(pdf.content)
        assert "DISCHARGE AGAINST MEDICAL ADVICE" in text
        assert "Stay for IV antibiotics" in text
        assert "Risk of sepsis" in text
        assert "absolves the hospital" in text


def _admit(client, headers, seed_data, room_number, reason):
    discharge_active_admissions(client, headers, seed_data["patient_id"])
    room = client.post(
        f"{API}/rooms",
        json={
            "room_number": room_number,
            "room_type": "general",
            "bed_count": 1,
            "room_charge_per_day": 500.0,
        },
        headers=headers,
    )
    assert room.status_code == 201, room.text
    adm = client.post(
        f"{API}/admissions",
        json={
            "patient_id": seed_data["patient_id"],
            "admitting_doctor_id": seed_data["doctor_user_id"],
            "room_id": room.json()["id"],
            "admission_type": "elective",
            "admission_reason": reason,
        },
        headers=headers,
    )
    assert adm.status_code == 201, adm.text
    return adm.json()["id"]


class TestDeathAndTransferSummary:
    def test_death_summary_requires_cause_and_copies_to_mortality(self, client, auth_headers, seed_data):
        admission_id = _admit(client, auth_headers, seed_data, "DS-DEATH-SUM", "Death summary test")
        base = {
            "primary_diagnosis": "Septic shock",
            "discharge_type": "death",
            "condition_on_discharge": None,
            "primary_doctor_id": seed_data["doctor_user_id"],
        }
        incomplete = client.put(
            f"{API}/admissions/{admission_id}/discharge-summary",
            json=base,
            headers=auth_headers,
        )
        assert incomplete.status_code == 200, incomplete.text
        blocked = client.post(
            f"{API}/admissions/{admission_id}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert blocked.status_code == 400, blocked.text
        assert "Time of death" in blocked.json()["detail"]

        complete = client.put(
            f"{API}/admissions/{admission_id}/discharge-summary",
            json={
                **base,
                "time_of_death": "2026-10-14T06:30:00",
                "cause_of_death": "Septic shock following pneumonia",
            },
            headers=auth_headers,
        )
        assert complete.status_code == 200, complete.text
        fin = client.post(
            f"{API}/admissions/{admission_id}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert fin.status_code == 200, fin.text
        pdf = client.get(
            f"{API}/admissions/{admission_id}/discharge-summary/pdf",
            headers=auth_headers,
        )
        assert pdf.status_code == 200, pdf.text
        text = _pdf_text(pdf.content)
        assert "DEATH SUMMARY" in text
        assert "Septic shock following pneumonia" in text
        assert "Condition on Discharge" not in text

        discharged = client.post(
            f"{API}/admissions/{admission_id}/discharge",
            json={"discharge_type": "death"},
            headers=auth_headers,
        )
        assert discharged.status_code == 201, discharged.text
        assert discharged.json()["condition_on_discharge"] in (None, "")
        cert = client.get(
            f"{API}/admissions/{admission_id}/death-certificate/pdf",
            headers=auth_headers,
        )
        assert cert.status_code == 200, cert.text
        assert "Septic shock following pneumonia" in _pdf_text(cert.content)

    def test_transfer_summary_requires_destination(self, client, auth_headers, seed_data):
        admission_id = _admit(client, auth_headers, seed_data, "DS-XFER", "Transfer summary test")
        base = {
            "primary_diagnosis": "Polytrauma",
            "discharge_type": "transfer",
            "condition_on_discharge": "critical",
            "primary_doctor_id": seed_data["doctor_user_id"],
        }
        incomplete = client.put(
            f"{API}/admissions/{admission_id}/discharge-summary",
            json=base,
            headers=auth_headers,
        )
        assert incomplete.status_code == 200, incomplete.text
        blocked = client.post(
            f"{API}/admissions/{admission_id}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert blocked.status_code == 400, blocked.text
        assert "Receiving hospital" in blocked.json()["detail"]

        complete = client.put(
            f"{API}/admissions/{admission_id}/discharge-summary",
            json={
                **base,
                "transfer_facility": "City Trauma Centre",
                "transfer_reason": "Needs neurosurgical ICU",
                "transfer_contact": "Dr. Rao, neurosurgery",
            },
            headers=auth_headers,
        )
        assert complete.status_code == 200, complete.text
        fin = client.post(
            f"{API}/admissions/{admission_id}/discharge-summary/finalize",
            headers=auth_headers,
        )
        assert fin.status_code == 200, fin.text
        pdf = client.get(
            f"{API}/admissions/{admission_id}/discharge-summary/pdf",
            headers=auth_headers,
        )
        assert pdf.status_code == 200, pdf.text
        text = _pdf_text(pdf.content)
        assert "TRANSFER SUMMARY" in text
        assert "City Trauma Centre" in text
        assert "Needs neurosurgical ICU" in text
        assert "Dr. Rao" in text
