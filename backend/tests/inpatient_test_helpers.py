"""Shared helpers for inpatient API tests."""

API = "/api/inpatient"


def ready_discharge_summary(client, admission_id, headers):
    """Create and finalize a discharge summary so normal discharge can proceed."""
    put = client.put(
        f"{API}/admissions/{admission_id}/discharge-summary",
        json={
            "primary_diagnosis": "Test diagnosis",
            "course_in_hospital": "Uneventful stay",
            "discharge_advice": "Rest and follow up",
        },
        headers=headers,
    )
    assert put.status_code == 200, put.text
    fin = client.post(
        f"{API}/admissions/{admission_id}/discharge-summary/finalize",
        headers=headers,
    )
    assert fin.status_code == 200, fin.text
    return fin.json()


def discharge_active_admissions(client, headers, patient_id, discharge_type="against_advice"):
    """Discharge any admitted admissions for a patient (test cleanup)."""
    r = client.get(f"{API}/admissions/patient/{patient_id}", headers=headers)
    if r.status_code != 200:
        return
    for adm in r.json():
        if adm.get("status") == "admitted":
            if discharge_type == "normal":
                ready_discharge_summary(client, adm["id"], headers)
            client.post(
                f"{API}/admissions/{adm['id']}/discharge",
                json={
                    "discharge_type": discharge_type,
                    "condition_on_discharge": "stable",
                    "force_outstanding_balance": True,
                    "force_unacknowledged_alerts": True,
                    "force_missing_consents": True,
                    "override_reason": "test cleanup",
                },
                headers=headers,
            )
