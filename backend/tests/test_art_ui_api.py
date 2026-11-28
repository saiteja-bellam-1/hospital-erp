"""Endpoints added for the fertility screens: staff picker, case and cycle detail, queue, appointments."""
from datetime import date

from app.services.db_seed import _ART_FRONTDESK
from tests.test_art_fixes import _close_benches, _consent, _couple, _embryo_cycle, _freeze, _lab_centre, _release_benches, _single, _witnessed  # noqa: F401
from tests.test_art_module import _doctor_can_witness, _headers, _user  # noqa: F401


def test_staff_lists_witness_flags(client, seed_data, db_session):
    admin = _headers("testadmin")
    res = client.get("/api/art/staff", headers=admin)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["me"] == seed_data["admin_user_id"]
    doctor = next(p for p in body["staff"] if p["id"] == seed_data["doctor_user_id"])
    assert doctor["can_witness_lab"] is True
    receptionist = next(p for p in body["staff"] if "receptionist" in p["roles"])
    assert receptionist["can_witness_lab"] is False


def test_cycle_details_and_protocol_reason(client, seed_data, db_session):
    admin = _headers("testadmin")
    case_id = _single(client, admin, "Usha", "9100000301")
    cycle = client.post(f"/api/art/cases/{case_id}/cycles", headers=admin, json={
        "cycle_type": "oi", "billing_mode": "itemised", "protocol": "letrozole",
    }).json()
    url = f"/api/art/cycles/{cycle['id']}"
    set_doc = client.patch(url, headers=admin, json={"clinician_id": seed_data["doctor_user_id"]})
    assert set_doc.status_code == 200 and set_doc.json()["clinician_id"] == seed_data["doctor_user_id"]
    client.post(f"{url}/stimulation", headers=admin, json={"day_number": 3})
    no_reason = client.patch(url, headers=admin, json={"protocol": "gonadotropin"})
    assert no_reason.status_code == 400
    with_reason = client.patch(url, headers=admin, json={"protocol": "gonadotropin", "protocol_change_reason": "No response"})
    assert with_reason.status_code == 200
    assert with_reason.json()["protocol_change_reason"] == "No response"
    assert client.patch(url, headers=admin, json={"clinician_id": 999999}).status_code == 404


def test_case_and_cycle_show_appointments_and_frozen(client, seed_data, db_session):
    admin = _headers("testadmin")
    _lab_centre(client, admin)
    case_id = _couple(client, admin, "Veda", "9100000311")
    _consent(client, admin, case_id, "embryo_freeze")
    cycle_id, (embryo, _) = _embryo_cycle(client, admin, seed_data, case_id, db_session=db_session)
    _freeze(client, admin, seed_data, embryo)
    appt = client.post("/api/art/appointments", headers=admin, json={
        "case_id": case_id, "cycle_id": cycle_id, "kind": "scan", "scheduled_date": date.today().isoformat(),
        "scheduled_time": "09:15",
    }).json()
    case = client.get(f"/api/art/cases/{case_id}", headers=admin).json()
    assert case["appointments"][0]["scheduled_time"] == "09:15"
    cycle = client.get(f"/api/art/cycles/{cycle_id}", headers=admin).json()
    assert [a["id"] for a in cycle["appointments"]] == [appt["id"]]
    assert [s["id"] for s in cycle["frozen_for_case"]] == [embryo]
    assert cycle["retrieval_mii"] is not None

    cancelled = client.post(f"/api/art/appointments/{appt['id']}/cancel", headers=admin)
    assert cancelled.status_code == 200
    assert client.post(f"/api/art/appointments/{appt['id']}/cancel", headers=admin).status_code == 400
    assert client.post(f"/api/art/appointments/{appt['id']}/complete", headers=admin).status_code == 400

    # A FET cycle lists the embryo thawed into it.
    thawed = client.post(f"/api/art/specimens/{embryo}/thaw", headers=admin, json=_witnessed(seed_data)).json()
    fet = client.get(f"/api/art/cycles/{thawed['cycle_id']}", headers=admin).json()
    assert [s["id"] for s in fet["specimens"]] == [embryo]


def test_queue_names_status_and_no_double_check_in(client, seed_data, db_session):
    admin = _headers("testadmin")
    desk = _headers(_user(db_session, seed_data["hospital_id"], "artfrontdesk", "art_frontdesk", _ART_FRONTDESK).username)
    case_id = _single(client, admin, "Wamiqa", "9100000321")
    first = client.post("/api/art/queue", headers=desk, json={"case_id": case_id})
    assert first.status_code == 200, first.text
    assert client.post("/api/art/queue", headers=desk, json={"case_id": case_id}).status_code == 400
    board = client.get("/api/art/board", headers=desk).json()
    row = next(r for r in board["queue"] if r["case_id"] == case_id)
    assert row["name"] == "Wamiqa Fertility"
    assert client.post(f"/api/art/queue/{row['id']}/status", headers=desk, json={"status": "called"}).status_code == 200
    assert client.post(f"/api/art/queue/{row['id']}/status", headers=desk, json={"status": "gone"}).status_code == 400
    client.post(f"/api/art/queue/{row['id']}/status", headers=desk, json={"status": "done"})
    assert client.post("/api/art/queue", headers=desk, json={"case_id": case_id}).status_code == 200


def test_cryo_inventory_bank_units_and_tank_logs(client, seed_data, db_session):
    from app.services.db_seed import _ART_COUNSELLOR
    admin = _headers("testadmin")
    _lab_centre(client, admin)
    case_id = _couple(client, admin, "Xena", "9100000331")
    _consent(client, admin, case_id, "embryo_freeze")
    _, (embryo,) = _embryo_cycle(client, admin, seed_data, case_id, embryos=1, db_session=db_session)
    _freeze(client, admin, seed_data, embryo, position="7")
    donor = client.post("/api/art/donors", headers=admin, json={"donor_type": "sperm", "legal_name": "Hidden Name"}).json()
    client.post(f"/api/art/donors/{donor['id']}/screening", headers=admin, json={k: "non_reactive" for k in ("hiv", "hbsag", "hcv", "vdrl")})
    client.post(f"/api/art/donors/{donor['id']}/clear", headers=admin)
    client.post("/api/art/bank/units", headers=admin, json={"donor_id": donor["id"], "sample_code": "INV-1", "tank": "B9"})

    inventory = client.get("/api/art/cryo/inventory", headers=admin)
    assert inventory.status_code == 200, inventory.text
    rows = inventory.json()
    mine = next(r for r in rows if r["kind"] == "patient" and r["id"] == embryo)
    assert mine["position"] == "7" and mine["name"] == "Xena Fertility"
    straw = next(r for r in rows if r["kind"] == "bank" and r["code"] == "INV-1")
    assert straw["donor_code"] == donor["donor_code"]
    assert "Hidden Name" not in inventory.text

    units = client.get("/api/art/bank/units", headers=admin).json()
    assert any(u["sample_code"] == "INV-1" and u["status"] == "stored" for u in units)
    assert "Hidden Name" not in str(units)

    client.post("/api/art/cryo/tank-log", headers=admin, json={"tank_name": "T1", "nitrogen_level": "low", "alarm": True})
    logs = client.get("/api/art/cryo/tank-logs", headers=admin).json()
    assert logs[0]["alarm"] is True and logs[0]["tank_name"] == "T1"

    counsellor = _headers(_user(db_session, seed_data["hospital_id"], "artcounsel", "art_counsellor", _ART_COUNSELLOR).username)
    assert client.get("/api/art/cryo/inventory", headers=counsellor).status_code == 403
    assert client.get("/api/art/bank/units", headers=counsellor).status_code == 403


def test_art_actions_are_audited_and_grievance_close_once(client, seed_data, db_session):
    from app.models.audit import AuditLog
    admin = _headers("testadmin")
    client.get("/api/art/donors", headers=admin)
    client.post("/api/art/cryo/tank-log", headers=admin, json={"tank_name": "T2"})
    g = client.post("/api/art/grievances", headers=admin, json={"complainant_name": "A", "summary": "B"}).json()
    assert client.post(f"/api/art/grievances/{g['id']}/close", headers=admin, json={"resolution": " "}).status_code == 400
    assert client.post(f"/api/art/grievances/{g['id']}/close", headers=admin, json={"resolution": "Sorted"}).status_code == 200
    assert client.post(f"/api/art/grievances/{g['id']}/close", headers=admin, json={"resolution": "Again"}).status_code == 400
    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.category == "art")}
    assert {"view_art_donor_identity", "art_tank_log", "open_art_grievance", "close_art_grievance"} <= actions
