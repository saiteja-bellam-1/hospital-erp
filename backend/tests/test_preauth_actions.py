"""Pre-auth upload, expansion decision, download, and delete."""


def _create_preauth(client, auth_headers, seed_data, amount=50000.0):
    r = client.post(
        "/api/inpatient/preauth",
        json={
            "patient_id": seed_data["patient_id"],
            "insurance_provider": "Star Health",
            "policy_number": "POL-UI",
            "requested_amount": amount,
        },
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


class TestPreauthActions:
    def test_upload_and_download_document(self, client, auth_headers, seed_data):
        preauth = _create_preauth(client, auth_headers, seed_data)
        pid = preauth["id"]

        up = client.post(
            f"/api/inpatient/preauth/{pid}/upload-document",
            files={"file": ("approval.pdf", b"%PDF-1.4 test letter", "application/pdf")},
            headers=auth_headers,
        )
        assert up.status_code == 200, up.text
        path = up.json()["document_path"]
        assert path.startswith("preauth_docs/")

        listed = client.get(f"/api/inpatient/preauth/{pid}", headers=auth_headers)
        assert listed.status_code == 200
        assert listed.json()["approval_document_path"] == path

        dl = client.get(f"/api/inpatient/preauth/{pid}/document", headers=auth_headers)
        assert dl.status_code == 200, dl.text
        assert dl.content.startswith(b"%PDF-1.4")

    def test_expansion_decision_rolls_up_amount(self, client, auth_headers, seed_data):
        preauth = _create_preauth(client, auth_headers, seed_data, amount=40000.0)
        pid = preauth["id"]

        dec = client.post(
            f"/api/inpatient/preauth/{pid}/decision",
            json={"status": "approved", "approved_amount": 35000.0, "validity_days": 15},
            headers=auth_headers,
        )
        assert dec.status_code == 200, dec.text

        exp = client.post(
            f"/api/inpatient/preauth/{pid}/expansion-request",
            json={"requested_amount": 8000.0, "reason": "ICU stay"},
            headers=auth_headers,
        )
        assert exp.status_code == 201, exp.text
        exp_id = exp.json()["id"]

        decided = client.post(
            f"/api/inpatient/preauth/expansions/{exp_id}/decision",
            json={"status": "approved", "approved_amount": 7500.0},
            headers=auth_headers,
        )
        assert decided.status_code == 200, decided.text
        assert decided.json()["status"] == "approved"

        parent = client.get(f"/api/inpatient/preauth/{pid}", headers=auth_headers)
        assert parent.status_code == 200
        body = parent.json()
        assert body["status"] == "expanded"
        assert body["approved_amount"] == 42500.0

    def test_delete_requested_preauth(self, client, auth_headers, seed_data):
        preauth = _create_preauth(client, auth_headers, seed_data, amount=12000.0)
        pid = preauth["id"]
        gone = client.delete(f"/api/inpatient/preauth/{pid}", headers=auth_headers)
        assert gone.status_code == 204, gone.text
        missing = client.get(f"/api/inpatient/preauth/{pid}", headers=auth_headers)
        assert missing.status_code == 404
