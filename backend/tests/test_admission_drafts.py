"""Admission draft workflow: save, activate, complete, cancel."""

import pytest

from inpatient_test_helpers import discharge_active_admissions

API = "/api/inpatient"

_draft: dict = {}


def _discharge_active(client, headers, patient_id):
    discharge_active_admissions(client, headers, patient_id)


class TestAdmissionDraftWorkflow:
    def test_setup_room(self, client, auth_headers, seed_data):
        _discharge_active(client, auth_headers, seed_data["patient_id"])
        # Cancel any leftover drafts from a prior failed run
        listed = client.get(f"{API}/admissions", params={"status": "draft"}, headers=auth_headers)
        for adm in listed.json().get("items", []):
            if adm.get("patient_id") == seed_data["patient_id"]:
                client.post(
                    f"{API}/admissions/{adm['id']}/cancel",
                    json={"reason": "test cleanup"},
                    headers=auth_headers,
                )
        r = client.post(
            f"{API}/rooms",
            json={
                "room_number": "DRF-1",
                "room_type": "general",
                "bed_count": 2,
                "room_charge_per_day": 500.0,
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        _draft["room_id"] = r.json()["id"]
        rooms = client.get(f"{API}/rooms", headers=auth_headers).json()
        room = next(x for x in rooms if x["id"] == _draft["room_id"])
        _draft["beds_before"] = room["available_beds"]

    def test_save_draft_does_not_claim_bed(self, client, auth_headers, seed_data):
        r = client.post(
            f"{API}/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": _draft["room_id"],
                "admission_type": "elective",
                "admission_reason": "Draft workflow test",
                "save_as_draft": True,
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["status"] == "draft"
        _draft["admission_id"] = data["id"]
        rooms = client.get(f"{API}/rooms", headers=auth_headers).json()
        room = next(x for x in rooms if x["id"] == _draft["room_id"])
        assert room["available_beds"] == _draft["beds_before"]

    def test_list_drafts(self, client, auth_headers):
        r = client.get(f"{API}/admissions", params={"status": "draft"}, headers=auth_headers)
        assert r.status_code == 200
        ids = [a["id"] for a in r.json()["items"]]
        assert _draft["admission_id"] in ids

    def test_activate_claims_bed(self, client, auth_headers):
        r = client.post(
            f"{API}/admissions/{_draft['admission_id']}/activate",
            json={"deposit_amount": 1000, "deposit_method": "cash"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "draft"
        rooms = client.get(f"{API}/rooms", headers=auth_headers).json()
        room = next(x for x in rooms if x["id"] == _draft["room_id"])
        assert room["available_beds"] == _draft["beds_before"] - 1

    def test_complete_promotes_to_admitted(self, client, auth_headers):
        r = client.post(
            f"{API}/admissions/{_draft['admission_id']}/complete-admission",
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "admitted"
        client.post(
            f"{API}/admissions/{_draft['admission_id']}/discharge",
            json={
                "discharge_type": "against_advice",
                "condition_on_discharge": "stable",
                "discharge_summary": "Draft workflow test cleanup",
                "override_reason": "test cleanup",
            },
            headers=auth_headers,
        )

    def test_cancel_draft_releases_bed(self, client, auth_headers, seed_data):
        _discharge_active(client, auth_headers, seed_data["patient_id"])
        r = client.post(
            f"{API}/rooms",
            json={
                "room_number": "DRF-CANCEL",
                "room_type": "general",
                "bed_count": 2,
                "room_charge_per_day": 500.0,
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        room_id = r.json()["id"]
        rooms = client.get(f"{API}/rooms", headers=auth_headers).json()
        room = next(x for x in rooms if x["id"] == room_id)
        beds_before = room["available_beds"]

        r = client.post(
            f"{API}/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room_id,
                "admission_type": "elective",
                "save_as_draft": True,
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        adm_id = r.json()["id"]

        act = client.post(
            f"{API}/admissions/{adm_id}/activate",
            json={"deposit_waived": True},
            headers=auth_headers,
        )
        assert act.status_code == 200, act.text

        rooms_mid = client.get(f"{API}/rooms", headers=auth_headers).json()
        room_mid = next(x for x in rooms_mid if x["id"] == room_id)
        assert room_mid["available_beds"] == beds_before - 1

        cancel = client.post(
            f"{API}/admissions/{adm_id}/cancel",
            json={"reason": "Patient left"},
            headers=auth_headers,
        )
        assert cancel.status_code == 200, cancel.text
        body = cancel.json()
        assert body["status"] == "cancelled"
        assert body.get("cancellation_reason") == "Patient left"

        rooms_after = client.get(f"{API}/rooms", headers=auth_headers).json()
        room_after = next(x for x in rooms_after if x["id"] == room_id)
        assert room_after["available_beds"] == beds_before

        listed = client.get(f"{API}/admissions", params={"status": "draft"}, headers=auth_headers)
        assert adm_id not in [a["id"] for a in listed.json()["items"]]
