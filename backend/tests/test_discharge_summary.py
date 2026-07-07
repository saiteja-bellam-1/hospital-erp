"""Discharge summary workflow: doctor write, finalize, print gate, discharge lock."""

from inpatient_test_helpers import API, discharge_active_admissions, ready_discharge_summary

_state: dict = {}


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
