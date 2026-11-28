"""Hardening tests: NEWS2, audited deletes, discharge immutability, MAR lifecycle."""
import json
from datetime import datetime, timedelta

from inpatient_test_helpers import discharge_active_admissions
from app.models.audit import AuditLog
from app.models.inpatient import MedicationAdministration
from app.services.early_warning import compute_news2
from app.services.mar_service import purge_future_scheduled_doses

API = "/api/inpatient"
_s: dict = {}


class TestNews2Pure:
    def test_all_normal_is_zero(self):
        r = compute_news2({"respiratory_rate": 16, "spo2": 98, "bp_systolic": 120,
                           "heart_rate": 70, "temperature_c": 37.0,
                           "consciousness": "alert", "on_supplemental_o2": False})
        assert r["score"] == 0 and r["risk"] == "low" and not r["partial"]

    def test_single_red_flag_is_low_medium(self):
        r = compute_news2({"respiratory_rate": 7, "spo2": 98, "bp_systolic": 120,
                           "heart_rate": 70, "temperature_c": 37.0, "consciousness": "alert"})
        assert r["score"] == 3 and r["risk"] == "low_medium" and r["red_flag"]

    def test_medium_and_high(self):
        base = {"respiratory_rate": 22, "spo2": 93, "bp_systolic": 105,
                "heart_rate": 100, "temperature_c": 38.5, "consciousness": "alert"}
        r = compute_news2(base)          # 2+2+1+1+1 = 7
        assert r["score"] == 7 and r["risk"] == "high"
        r = compute_news2({**base, "heart_rate": 80, "temperature_c": 37.0})  # 2+2+1 = 5
        assert r["score"] == 5 and r["risk"] == "medium"

    def test_oxygen_and_consciousness_and_partial(self):
        r = compute_news2({"spo2": 97, "on_supplemental_o2": True, "consciousness": "confusion"})
        assert r["score"] == 5 and r["partial"]


class TestHardeningApi:
    def test_setup(self, client, auth_headers, seed_data):
        discharge_active_admissions(client, auth_headers, seed_data["patient_id"])
        room = client.post(f"{API}/rooms", json={"room_number": "HD-1", "room_type": "general",
                           "bed_count": 2, "room_charge_per_day": 500.0}, headers=auth_headers)
        adm = client.post(f"{API}/admissions", json={
            "patient_id": seed_data["patient_id"], "admitting_doctor_id": seed_data["doctor_user_id"],
            "room_id": room.json()["id"], "admission_type": "elective",
            "admission_reason": "hardening"}, headers=auth_headers)
        assert adm.status_code == 201, adm.text
        _s["adm"] = adm.json()["id"]

    def test_vitals_compute_news2_and_alert_board(self, client, auth_headers):
        r = client.post(f"{API}/admissions/{_s['adm']}/vitals", json={
            "respiratory_rate": 24, "spo2": 92, "bp_systolic": 100, "heart_rate": 115,
            "temperature_c": 38.6, "consciousness": "alert", "on_supplemental_o2": False},
            headers=auth_headers)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["news2_score"] == 2 + 2 + 2 + 2 + 1 and body["news2_risk"] == "high"
        assert body["news2_escalation"]
        _s["vital"] = body["id"]
        board = client.get(f"{API}/early-warnings", headers=auth_headers).json()
        assert any(b["admission_id"] == _s["adm"] and b["news2_risk"] == "high" for b in board)

    def test_vitals_edit_recomputes_and_is_audited(self, client, auth_headers, db_session):
        r = client.put(f"{API}/vitals/{_s['vital']}", json={"heart_rate": 80, "respiratory_rate": 16,
                       "spo2": 98, "temperature_c": 37.0, "bp_systolic": 120}, headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.json()["news2_risk"] == "low"
        row = db_session.query(AuditLog).filter(AuditLog.action == "update_vitals").first()
        assert row and "changes" in json.loads(row.details)

    def test_delete_vitals_leaves_snapshot(self, client, auth_headers, db_session):
        r = client.delete(f"{API}/vitals/{_s['vital']}", headers=auth_headers)
        assert r.status_code == 204
        row = (db_session.query(AuditLog).filter(AuditLog.action == "delete_vitalsigns")
               .order_by(AuditLog.id.desc()).first())
        assert row, "delete must be audited"
        assert json.loads(row.details)["deleted_row"]["id"] == _s["vital"]

    def test_log_action_accepts_positional_details(self, db_session):
        from app.services.audit_service import log_action
        log_action(db_session, None, "t_positional", "inpatient", "X", 1, "d", {"k": 1})
        row = db_session.query(AuditLog).filter(AuditLog.action == "t_positional").first()
        assert row is not None and json.loads(row.details) == {"k": 1}

    def test_purge_only_removes_untouched_future_doses(self, db_session):
        from app.models.inpatient import Admission
        from app.models.hospital import Hospital
        adm = db_session.query(Admission).get(_s["adm"])
        hid = db_session.query(Hospital).first().id
        now = datetime.now()

        def mk(status, when, given=False):
            m = MedicationAdministration(
                admission_id=adm.id, patient_id=adm.patient_id, scheduled_time=when,
                status=status, hospital_id=hid,
                administered_at=now if given else None)
            db_session.add(m)
            return m
        future_open = mk("scheduled", now + timedelta(hours=3))
        future_given = mk("given", now + timedelta(hours=4), given=True)
        past_open = mk("scheduled", now - timedelta(hours=3))
        db_session.commit()
        ids = (future_open.id, future_given.id, past_open.id)

        removed = purge_future_scheduled_doses(db_session, admission_id=adm.id, from_time=now)
        db_session.commit()
        assert removed == 1
        left = {m.id for m in db_session.query(MedicationAdministration)
                .filter(MedicationAdministration.admission_id == adm.id).all()}
        assert ids[0] not in left and ids[1] in left and ids[2] in left
        # unbounded purge is refused
        assert purge_future_scheduled_doses(db_session) == 0

    def test_discharged_admission_record_is_immutable(self, client, auth_headers):
        note = client.post(f"{API}/admissions/{_s['adm']}/nursing-notes", json={
            "shift": "morning", "note_type": "observation", "content": "pre-discharge"},
            headers=auth_headers)
        assert note.status_code == 201, note.text
        d = client.post(f"{API}/admissions/{_s['adm']}/discharge", json={
            "discharge_type": "against_advice", "condition_on_discharge": "stable",
            "force_outstanding_balance": True, "force_unacknowledged_alerts": True,
            "force_missing_consents": True, "override_reason": "test"}, headers=auth_headers)
        assert d.status_code in (200, 201), d.text
        r = client.delete(f"{API}/nursing-notes/{note.json()['id']}", headers=auth_headers)
        assert r.status_code == 409, r.text
