"""
End-to-end smoke tests for the Inpatient module.

Tests the core happy-path flow:
  Room → Rate Config → Admission → Visit → OT Schedule →
  Bill Preview → Bill Finalize → Discharge → Dashboard

All tests run sequentially and share state via module-scoped variables
so that each step builds on the previous one (true E2E).
"""

import pytest
from datetime import datetime, timedelta

# Shared state across the ordered tests
_state: dict = {}


class TestInpatientE2E:
    """Ordered E2E smoke test for the inpatient module."""

    # ------------------------------------------------------------------
    # 1. Room creation
    # ------------------------------------------------------------------
    def test_create_room(self, client, auth_headers, seed_data):
        resp = client.post(
            "/api/inpatient/rooms",
            json={
                "room_number": "R-101",
                "room_type": "general",
                "floor": "1",
                "department": "General Ward",
                "bed_count": 4,
                "room_charge_per_day": 500.0,
                "amenities": "AC, TV",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["room_number"] == "R-101"
        assert data["bed_count"] == 4
        assert data["available_beds"] == 4
        assert data["is_occupied"] is False
        _state["room_id"] = data["id"]

    # ------------------------------------------------------------------
    # 2. Rate config
    # ------------------------------------------------------------------
    def test_update_rate_config(self, client, auth_headers):
        resp = client.put(
            "/api/inpatient/rate-config",
            json={
                "doctor_visit_rate": 300.0,
                "nurse_visit_rate": 100.0,
                "procedure_rate": 1500.0,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert float(data["doctor_visit_rate"]) == 300.0
        assert float(data["nurse_visit_rate"]) == 100.0
        assert float(data["procedure_rate"]) == 1500.0

    def test_get_rate_config(self, client, auth_headers):
        resp = client.get("/api/inpatient/rate-config", headers=auth_headers)
        assert resp.status_code == 200
        assert float(resp.json()["doctor_visit_rate"]) == 300.0

    # ------------------------------------------------------------------
    # 3. Admission
    # ------------------------------------------------------------------
    def test_create_admission(self, client, auth_headers, seed_data):
        resp = client.post(
            "/api/inpatient/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": _state["room_id"],
                "admission_type": "elective",
                "admission_reason": "Observation",
                "condition_on_admission": "stable",
                "estimated_stay_days": 3,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] == "admitted"
        assert data["admission_number"].startswith("ADM-")
        _state["admission_id"] = data["id"]

    def test_admission_decrements_beds(self, client, auth_headers):
        """After admission, available_beds should have decreased by 1."""
        resp = client.get("/api/inpatient/rooms", headers=auth_headers)
        assert resp.status_code == 200
        room = next(r for r in resp.json() if r["id"] == _state["room_id"])
        assert room["available_beds"] == 3  # was 4, now 3

    def test_duplicate_admission_blocked(self, client, auth_headers, seed_data):
        """Cannot admit the same patient twice while already admitted."""
        resp = client.post(
            "/api/inpatient/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": _state["room_id"],
                "admission_type": "emergency",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400

    # ------------------------------------------------------------------
    # 4. Visit
    # ------------------------------------------------------------------
    def test_create_visit(self, client, auth_headers, seed_data, TestSessionLocal):
        # Visits now auto-fill charge_amount from the visiting user's
        # inpatient_fee_inr (the hospital-wide rate config is deprecated).
        # Set the seed doctor's fee so the auto-fill has a value to read.
        from app.models.user import User
        db = TestSessionLocal()
        doctor = db.query(User).filter(User.id == seed_data["doctor_user_id"]).first()
        doctor.inpatient_fee_inr = "300"
        db.commit()
        db.close()

        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/visits",
            json={
                "visit_type": "doctor_visit",
                "visitor_id": seed_data["doctor_user_id"],
                "notes": "Routine checkup",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["visit_type"] == "doctor_visit"
        # charge auto-populated from the visiting user's inpatient_fee_inr
        assert float(data["charge_amount"]) == 300.0
        assert data["billed"] is False
        _state["visit_id"] = data["id"]

    def test_list_visits(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/visits",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        visits = resp.json()
        assert len(visits) >= 1

    # ------------------------------------------------------------------
    # 5. OT Schedule
    # ------------------------------------------------------------------
    def test_create_ot_schedule(self, client, auth_headers, seed_data):
        scheduled = (datetime.now() + timedelta(days=1)).isoformat()
        resp = client.post(
            "/api/inpatient/ot",
            json={
                "admission_id": _state["admission_id"],
                "patient_id": seed_data["patient_id"],
                "surgeon_id": seed_data["doctor_user_id"],
                "ot_room_number": "OT-1",
                "procedure_name": "Appendectomy",
                "scheduled_date": scheduled,
                "estimated_duration_minutes": 90,
                "pre_op_notes": "NPO from midnight",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] == "scheduled"
        assert data["procedure_name"] == "Appendectomy"
        _state["ot_id"] = data["id"]

    def test_list_ot_schedules(self, client, auth_headers):
        resp = client.get("/api/inpatient/ot", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_auto_post_today_creates_doctor_visit(self, client, auth_headers):
        """Manual trigger of the daily auto-post should create a doctor_visit."""
        before = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/visits",
            headers=auth_headers,
        ).json()
        before_ids = {v["id"] for v in before}

        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/auto-post-today",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        # First call may post, or may be a no-op if create_visit already covered today.
        # Idempotency check: a second call must NEVER post again.
        resp2 = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/auto-post-today",
            headers=auth_headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["posted"] is False


    # ------------------------------------------------------------------
    # 6. Bill preview
    # ------------------------------------------------------------------
    def test_bill_preview(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "grand_total" in data
        assert "room" in data
        assert "visits" in data
        assert data["grand_total"] > 0

    # ------------------------------------------------------------------
    # 7. Bill finalize
    # ------------------------------------------------------------------
    def test_finalize_bill(self, client, auth_headers):
        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill/finalize",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["bill_number"].startswith("BILL-ADM-")
        assert data["total_amount"] > 0
        _state["bill_number"] = data["bill_number"]

    def test_visit_marked_billed_after_finalize(self, client, auth_headers):
        """After bill finalize, visits should be marked as billed."""
        resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/visits",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        for visit in resp.json():
            assert visit["billed"] is True

    def test_duplicate_finalize_rejected(self, client, auth_headers):
        """A second finalize while an active final bill exists must 409."""
        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill/finalize",
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["code"] == "final_bill_exists"

    def test_cancel_bill_releases_source_items_and_allows_refinalize(self, client, auth_headers):
        """Cancelling the final bill must reset visit.billed and clear bill_id;
        the admission must then be finalisable again."""
        bills_resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bills",
            headers=auth_headers,
        )
        assert bills_resp.status_code == 200
        final_bill = next(b for b in bills_resp.json() if b["bill_subtype"] == "final" and b["status"] != "cancelled")

        cancel_resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/bills/{final_bill['id']}/cancel",
            json={"reason": "Smoke test — wrong discount"},
            headers=auth_headers,
        )
        assert cancel_resp.status_code == 200, cancel_resp.text
        released = cancel_resp.json()["released"]
        assert released["visits"] >= 1

        # Visits should be available for re-billing
        visits_resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/visits",
            headers=auth_headers,
        )
        for visit in visits_resp.json():
            assert visit["billed"] is False

        # Re-finalise — should succeed because the prior bill is cancelled
        refinal = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill/finalize",
            headers=auth_headers,
        )
        assert refinal.status_code == 200, refinal.text

    # ------------------------------------------------------------------
    # 8. Discharge
    # ------------------------------------------------------------------
    def test_discharge_blocked_when_balance_negative(self, client, auth_headers):
        """A normal discharge with an unpaid bill must be blocked unless forced."""
        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/discharge",
            json={
                "discharge_type": "normal",
                "condition_on_discharge": "stable",
                "discharge_summary": "Patient recovered well",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        assert body["detail"]["code"] == "outstanding_balance"

    def test_discharge_force_requires_reason(self, client, auth_headers):
        """force_outstanding_balance without override_reason is rejected."""
        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/discharge",
            json={
                "discharge_type": "normal",
                "condition_on_discharge": "stable",
                "force_outstanding_balance": True, "force_unacknowledged_alerts": True, "force_missing_consents": True,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400, resp.text

    def test_discharge(self, client, auth_headers):
        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/discharge",
            json={
                "discharge_type": "normal",
                "condition_on_discharge": "stable",
                "discharge_summary": "Patient recovered well",
                "follow_up_instructions": "Return in 1 week",
                "force_outstanding_balance": True, "force_unacknowledged_alerts": True, "force_missing_consents": True,
                "override_reason": "Smoke test — bill will be settled post-exit",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["discharge_type"] == "normal"
        assert data["total_stay_days"] >= 1
        assert data["total_charges"] > 0

    def test_discharge_increments_beds(self, client, auth_headers):
        """After discharge, available_beds should be restored."""
        resp = client.get("/api/inpatient/rooms", headers=auth_headers)
        assert resp.status_code == 200
        room = next(r for r in resp.json() if r["id"] == _state["room_id"])
        assert room["available_beds"] == 4  # back to original

    def test_admission_status_discharged(self, client, auth_headers):
        """Admission status should now be 'discharged'."""
        resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "discharged"

    # ------------------------------------------------------------------
    # 9. Dashboard
    # ------------------------------------------------------------------
    def test_dashboard(self, client, auth_headers):
        resp = client.get("/api/inpatient/dashboard", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "total_beds" in data
        assert "occupied" in data
        assert "available" in data
        assert "by_type" in data
        assert "today_admissions" in data
        assert "active_admissions" in data
        assert "avg_stay_days" in data
        # After discharge, our room beds should all be available
        assert data["total_beds"] >= 4
        assert data["active_admissions"] == 0


# ======================================================================
# Phase 1 expansion: Vitals, Allergies, Medication Administration Record
# ======================================================================

_phase1: dict = {}


class TestInpatientPhase1:
    """Vitals → Allergies → MAR end-to-end. Self-contained: creates its own
    room/admission/medicine so it doesn't interfere with the original E2E."""

    def test_setup_room_and_admission(self, client, auth_headers, seed_data):
        # Room
        r = client.post(
            "/api/inpatient/rooms",
            json={"room_number": "P1-201", "room_type": "icu", "bed_count": 2,
                  "room_charge_per_day": 2000.0},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        _phase1["room_id"] = r.json()["id"]

        # Admission
        a = client.post(
            "/api/inpatient/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": _phase1["room_id"],
                "admission_type": "elective",
                "admission_reason": "Phase 1 smoke test",
                "condition_on_admission": "stable",
            },
            headers=auth_headers,
        )
        assert a.status_code == 201, a.text
        _phase1["admission_id"] = a.json()["id"]
        _phase1["patient_id"] = seed_data["patient_id"]

    # ------------------------------------------------------------------
    # Vitals
    # ------------------------------------------------------------------
    def test_record_vitals_normal(self, client, auth_headers):
        r = client.post(
            f"/api/inpatient/admissions/{_phase1['admission_id']}/vitals",
            json={"bp_systolic": 120, "bp_diastolic": 80, "heart_rate": 72,
                  "respiratory_rate": 16, "temperature_c": 36.8, "spo2": 98,
                  "pain_score": 2, "shift": "morning"},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["bp_systolic"] == 120
        assert data["is_abnormal"] is False
        assert data["abnormal_flags"] in (None, [])
        _phase1["normal_vital_id"] = data["id"]

    def test_record_vitals_abnormal_flagged(self, client, auth_headers):
        # SpO2 too low + temp elevated → abnormal
        r = client.post(
            f"/api/inpatient/admissions/{_phase1['admission_id']}/vitals",
            json={"bp_systolic": 160, "bp_diastolic": 100, "spo2": 88,
                  "temperature_c": 39.2, "shift": "afternoon"},
            headers=auth_headers,
        )
        assert r.status_code == 201
        data = r.json()
        assert data["is_abnormal"] is True
        flags = set(data["abnormal_flags"] or [])
        assert "spo2" in flags
        assert "temperature_c" in flags
        assert "bp_systolic" in flags

    def test_list_vitals_returns_recent_first(self, client, auth_headers):
        r = client.get(
            f"/api/inpatient/admissions/{_phase1['admission_id']}/vitals",
            headers=auth_headers,
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 2
        # Sorted desc by recorded_at
        ts = [row["recorded_at"] for row in rows]
        assert ts == sorted(ts, reverse=True)

    def test_latest_vitals_returns_latest_entry(self, client, auth_headers):
        r = client.get(
            f"/api/inpatient/admissions/{_phase1['admission_id']}/vitals/latest",
            headers=auth_headers,
        )
        assert r.status_code == 200
        # The most recent one we recorded was abnormal
        assert r.json()["is_abnormal"] is True

    # ------------------------------------------------------------------
    # Allergies (patient-level)
    # ------------------------------------------------------------------
    def test_record_drug_allergy(self, client, auth_headers):
        r = client.post(
            f"/api/patients/{_phase1['patient_id']}/allergies",
            json={"allergy_type": "drug", "allergen": "Penicillin",
                  "severity": "severe", "reaction": "Rash and swelling"},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["allergen"] == "Penicillin"
        assert data["severity"] == "severe"
        _phase1["allergy_id"] = data["id"]

    def test_duplicate_allergy_rejected(self, client, auth_headers):
        r = client.post(
            f"/api/patients/{_phase1['patient_id']}/allergies",
            json={"allergy_type": "drug", "allergen": "Penicillin",
                  "severity": "moderate"},
            headers=auth_headers,
        )
        assert r.status_code == 409

    def test_list_active_allergies(self, client, auth_headers):
        r = client.get(
            f"/api/patients/{_phase1['patient_id']}/allergies",
            headers=auth_headers,
        )
        assert r.status_code == 200
        rows = r.json()
        assert any(a["allergen"] == "Penicillin" for a in rows)

    def test_soft_delete_allergy(self, client, auth_headers):
        r = client.delete(
            f"/api/patients/allergies/{_phase1['allergy_id']}",
            headers=auth_headers,
        )
        assert r.status_code == 204
        # active_only list should now be empty for this allergen
        r2 = client.get(
            f"/api/patients/{_phase1['patient_id']}/allergies",
            params={"active_only": True},
            headers=auth_headers,
        )
        assert all(a["id"] != _phase1["allergy_id"] for a in r2.json())

    # ------------------------------------------------------------------
    # MAR — needs a prescription with frequency
    # ------------------------------------------------------------------
    def test_setup_prescription_for_mar(self, client, auth_headers, seed_data, db_session):
        from app.models.pharmacy import Medicine, MedicineCategory, Prescription, PrescriptionItem

        # Create medicine + category directly (faster than going through the API)
        cat = MedicineCategory(name="Antipyretic", hospital_id=seed_data["hospital_id"])
        db_session.add(cat); db_session.flush()

        med = Medicine(
            medicine_code="MED-001", name="Paracetamol", unit_price=2.0,
            category_id=cat.id, hospital_id=seed_data["hospital_id"],
        )
        db_session.add(med); db_session.flush()
        _phase1["medicine_id"] = med.id

        rx = Prescription(
            prescription_number="RX-PHASE1-001",
            patient_id=_phase1["patient_id"],
            doctor_id=seed_data["doctor_user_id"],
            admission_id=_phase1["admission_id"],
            status="pending",
        )
        db_session.add(rx); db_session.flush()

        item = PrescriptionItem(
            prescription_id=rx.id,
            medicine_id=med.id,
            quantity_prescribed=12,
            dosage="500mg",
            duration="2 days",
            unit_price=2.0,
            total_price=24.0,
            frequency="Q8H",
            route="oral",
            is_prn=False,
        )
        db_session.add(item); db_session.commit()
        _phase1["prescription_item_id"] = item.id

    def test_generate_mar_creates_scheduled_doses(self, client, auth_headers):
        r = client.post(
            f"/api/inpatient/admissions/{_phase1['admission_id']}/mar/generate",
            params={"horizon_hours": 24},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Q8H = 3 times per day → expect at least 1 dose in next 24h
        assert data["created"] >= 1
        # Idempotency: second call should skip them
        r2 = client.post(
            f"/api/inpatient/admissions/{_phase1['admission_id']}/mar/generate",
            params={"horizon_hours": 24},
            headers=auth_headers,
        )
        assert r2.json()["created"] == 0
        assert r2.json()["skipped_existing"] >= data["created"]

    def test_list_mar_history_returns_doses(self, client, auth_headers):
        # Use /history to avoid date-window edge cases (Q8H generated near
        # a day boundary may have all slots on the next calendar date).
        r = client.get(
            f"/api/inpatient/admissions/{_phase1['admission_id']}/mar/history",
            headers=auth_headers,
        )
        assert r.status_code == 200
        doses = r.json()
        assert len(doses) >= 1
        assert all(d["status"] == "scheduled" for d in doses)
        _phase1["first_dose_id"] = doses[0]["id"]

    def test_administer_dose(self, client, auth_headers):
        r = client.post(
            f"/api/inpatient/mar/{_phase1['first_dose_id']}/administer",
            json={"status": "given", "dose_given": "500mg", "route": "oral"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "given"
        assert r.json()["administered_by_id"] is not None

    def test_cannot_administer_twice(self, client, auth_headers):
        r = client.post(
            f"/api/inpatient/mar/{_phase1['first_dose_id']}/administer",
            json={"status": "given"},
            headers=auth_headers,
        )
        assert r.status_code == 409

    def test_record_prn_dose(self, client, auth_headers):
        r = client.post(
            f"/api/inpatient/admissions/{_phase1['admission_id']}/mar/prn",
            json={
                "prescription_item_id": _phase1["prescription_item_id"],
                "dose_given": "500mg",
                "route": "oral",
                "prn_indication": "Headache",
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["is_prn"] is True
        assert data["status"] == "given"
        assert data["prn_indication"] == "Headache"
        assert data["scheduled_time"] is None


# ======================================================================
# Phase 2: Deposits, OT charges, ancillary, interim billing, packages,
# pre-auth, TPA + bill splits.
# ======================================================================

_phase2: dict = {}


class TestInpatientPhase2:
    """Self-contained Phase 2 flow. Creates its own room+admission so it
    doesn't interfere with Phase 1 or the original E2E."""

    def test_setup_room_and_admission(self, client, auth_headers, seed_data):
        # If an earlier test class left the patient with an active admission, discharge it first
        existing = client.get(
            f"/api/inpatient/admissions/patient/{seed_data['patient_id']}",
            headers=auth_headers,
        )
        if existing.status_code == 200:
            for adm in existing.json():
                if adm.get("status") == "admitted":
                    client.post(
                        f"/api/inpatient/admissions/{adm['id']}/discharge",
                        json={"discharge_type": "normal", "condition_on_discharge": "stable",
                              "discharge_summary": "Auto-discharged for Phase 2 setup",
                              "force_outstanding_balance": True, "force_unacknowledged_alerts": True, "force_missing_consents": True, "override_reason": "test cleanup"},
                        headers=auth_headers,
                    )

        r = client.post(
            "/api/inpatient/rooms",
            json={"room_number": "P2-301", "room_type": "private", "bed_count": 1,
                  "room_charge_per_day": 1500.0},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        _phase2["room_id"] = r.json()["id"]

        a = client.post(
            "/api/inpatient/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": _phase2["room_id"],
                "admission_type": "elective",
                "admission_reason": "Phase 2 smoke test",
                "condition_on_admission": "stable",
            },
            headers=auth_headers,
        )
        assert a.status_code == 201, a.text
        _phase2["admission_id"] = a.json()["id"]

    # ------------------------------------------------------------------
    # Deposits & balance
    # ------------------------------------------------------------------
    def test_create_deposit(self, client, auth_headers):
        r = client.post(
            f"/api/inpatient/admissions/{_phase2['admission_id']}/deposits",
            json={"amount": 10000.0, "payment_method": "cash", "deposit_type": "initial", "reference_number": "R-001"},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["deposit_type"] == "initial"
        assert r.json()["amount"] == 10000.0

    def test_balance_after_deposit(self, client, auth_headers):
        r = client.get(
            f"/api/inpatient/admissions/{_phase2['admission_id']}/balance",
            headers=auth_headers,
        )
        assert r.status_code == 200
        b = r.json()
        assert b["net_deposits"] == 10000.0
        assert b["total_billed"] == 0.0
        assert b["balance"] == 10000.0

    def test_top_up_deposit(self, client, auth_headers):
        r = client.post(
            f"/api/inpatient/admissions/{_phase2['admission_id']}/deposits",
            json={"amount": 5000.0, "payment_method": "upi", "deposit_type": "topup"},
            headers=auth_headers,
        )
        assert r.status_code == 201
        r2 = client.get(f"/api/inpatient/admissions/{_phase2['admission_id']}/balance", headers=auth_headers)
        assert r2.json()["net_deposits"] == 15000.0

    # ------------------------------------------------------------------
    # Ancillary catalog + charges
    # ------------------------------------------------------------------
    def test_create_ancillary_service(self, client, auth_headers):
        r = client.post(
            "/api/inpatient/ancillary-services",
            json={"service_name": "X-Ray Chest", "category": "imaging",
                  "default_charge": 500.0, "charge_unit": "per_session"},
            headers=auth_headers,
        )
        assert r.status_code == 201
        _phase2["service_id"] = r.json()["id"]

    def test_add_ancillary_charge_to_admission(self, client, auth_headers):
        r = client.post(
            f"/api/inpatient/admissions/{_phase2['admission_id']}/ancillary-charges",
            json={"service_id": _phase2["service_id"], "quantity": 2, "unit_price": 500.0},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["total_amount"] == 1000.0
        assert data["billed"] is False
        _phase2["ancillary_charge_id"] = data["id"]

    # ------------------------------------------------------------------
    # OT charges
    # ------------------------------------------------------------------
    def test_create_completed_ot(self, client, auth_headers, seed_data):
        from datetime import datetime, timedelta
        r = client.post(
            "/api/inpatient/ot",
            json={
                "admission_id": _phase2["admission_id"],
                "patient_id": seed_data["patient_id"],
                "surgeon_id": seed_data["doctor_user_id"],
                "ot_room_number": "OT-1",
                "procedure_name": "Test procedure",
                "scheduled_date": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
                "estimated_duration_minutes": 60,
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        _phase2["ot_id"] = r.json()["id"]
        # Mark completed
        r2 = client.patch(
            f"/api/inpatient/ot/{_phase2['ot_id']}/status",
            params={"status": "completed"},
            headers=auth_headers,
        )
        assert r2.status_code == 200

    def test_update_ot_charges(self, client, auth_headers):
        r = client.put(
            f"/api/inpatient/ot/{_phase2['ot_id']}/charges",
            json={"surgeon_fee": 8000.0, "anaesthetist_fee": 3000.0,
                  "ot_room_charge": 2000.0, "consumables_charge": 1500.0},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["total_charges"] == 14500.0

    # ------------------------------------------------------------------
    # Bill preview includes OT + ancillary
    # ------------------------------------------------------------------
    def test_bill_preview_includes_ot_and_ancillary(self, client, auth_headers):
        r = client.get(
            f"/api/inpatient/admissions/{_phase2['admission_id']}/bill",
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ot_total"] == 14500.0
        assert data["ancillary_total"] == 1000.0
        # Room is at least 1 day
        assert data["room_total"] >= 1500.0

    # ------------------------------------------------------------------
    # Interim billing
    # ------------------------------------------------------------------
    def test_interim_bill_consumes_items(self, client, auth_headers):
        r = client.post(
            f"/api/inpatient/admissions/{_phase2['admission_id']}/bill/interim",
            json={"discount_value": 0, "tax_percentage": 0},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["bill_subtype"] == "interim"
        assert data["total_amount"] > 0
        _phase2["interim_bill_id"] = data["bill_id"]
        _phase2["interim_total"] = data["total_amount"]

    def test_interim_bill_marks_items_billed(self, client, auth_headers):
        # Unbilled preview should now return zero for OT + ancillary
        r = client.get(
            f"/api/inpatient/admissions/{_phase2['admission_id']}/bill",
            params={"unbilled_only": True},
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ot_total"] == 0.0
        assert data["ancillary_total"] == 0.0

    def test_second_interim_fails_without_new_charges(self, client, auth_headers):
        r = client.post(
            f"/api/inpatient/admissions/{_phase2['admission_id']}/bill/interim",
            json={},
            headers=auth_headers,
        )
        assert r.status_code == 400  # nothing new to bill

    def test_list_admission_bills(self, client, auth_headers):
        r = client.get(
            f"/api/inpatient/admissions/{_phase2['admission_id']}/bills",
            headers=auth_headers,
        )
        assert r.status_code == 200
        bills = r.json()
        assert len(bills) == 1
        assert bills[0]["bill_subtype"] == "interim"

    def test_balance_reflects_bill(self, client, auth_headers):
        r = client.get(f"/api/inpatient/admissions/{_phase2['admission_id']}/balance", headers=auth_headers)
        b = r.json()
        assert b["total_billed"] == _phase2["interim_total"]
        assert b["balance"] == round(15000.0 - _phase2["interim_total"], 2)

    # ------------------------------------------------------------------
    # Refund (only if balance is positive)
    # ------------------------------------------------------------------
    def test_refund_issued(self, client, auth_headers):
        r_bal = client.get(f"/api/inpatient/admissions/{_phase2['admission_id']}/balance", headers=auth_headers)
        balance = r_bal.json()["balance"]
        if balance <= 0:
            pytest.skip("No credit balance to refund in this scenario")
        r = client.post(
            f"/api/inpatient/admissions/{_phase2['admission_id']}/refund",
            json={"amount": min(balance, 100.0), "payment_method": "cash"},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["deposit_type"] == "refund"

    def test_refund_over_balance_rejected(self, client, auth_headers):
        r = client.post(
            f"/api/inpatient/admissions/{_phase2['admission_id']}/refund",
            json={"amount": 999999.0, "payment_method": "cash"},
            headers=auth_headers,
        )
        assert r.status_code == 409

    # ------------------------------------------------------------------
    # Surgery packages
    # ------------------------------------------------------------------
    def test_create_package(self, client, auth_headers):
        r = client.post(
            "/api/inpatient/packages",
            json={
                "package_name": "Cataract Surgery",
                "package_code": "CAT-001",
                "base_price": 25000.0,
                "included_room_type": "general",
                "included_stay_days": 2,
                "included_services": ["room", "ot", "pharmacy"],
                "excess_per_day_charge": 1500.0,
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        _phase2["package_id"] = r.json()["id"]

    def test_apply_package_to_new_admission(self, client, auth_headers, seed_data):
        # Discharge the earlier Phase 2 admission so the patient can be re-admitted
        r_disch = client.post(
            f"/api/inpatient/admissions/{_phase2['admission_id']}/discharge",
            json={
                "discharge_type": "normal",
                "condition_on_discharge": "stable",
                "discharge_summary": "Phase 2 smoke test complete",
                "force_outstanding_balance": True, "force_unacknowledged_alerts": True, "force_missing_consents": True,
                "override_reason": "test",
            },
            headers=auth_headers,
        )
        assert r_disch.status_code in (200, 201), r_disch.text

        # New admission dedicated to package test
        r_room = client.post(
            "/api/inpatient/rooms",
            json={"room_number": "P2-PKG", "room_type": "general", "bed_count": 1, "room_charge_per_day": 500.0},
            headers=auth_headers,
        )
        assert r_room.status_code == 201, r_room.text
        room_id = r_room.json()["id"]
        r_adm = client.post(
            "/api/inpatient/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room_id,
                "admission_type": "elective",
                "admission_reason": "Package test",
            },
            headers=auth_headers,
        )
        assert r_adm.status_code == 201, r_adm.text
        adm_id = r_adm.json()["id"]
        _phase2["pkg_admission_id"] = adm_id

        r = client.post(
            f"/api/inpatient/admissions/{adm_id}/package",
            json={"package_id": _phase2["package_id"]},
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["agreed_price"] == 25000.0

    def test_bill_uses_package_mode(self, client, auth_headers):
        r = client.get(
            f"/api/inpatient/admissions/{_phase2['pkg_admission_id']}/bill",
            headers=auth_headers,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["package"] is not None
        assert data["package"]["agreed_price"] == 25000.0
        assert data["grand_total"] >= 25000.0

    # ------------------------------------------------------------------
    # Pre-authorisation
    # ------------------------------------------------------------------
    def test_create_preauth(self, client, auth_headers, seed_data):
        r = client.post(
            "/api/inpatient/preauth",
            json={
                "patient_id": seed_data["patient_id"],
                "admission_id": _phase2["admission_id"],
                "insurance_provider": "Star Health",
                "policy_number": "POL-123",
                "requested_amount": 50000.0,
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "requested"
        _phase2["preauth_id"] = r.json()["id"]

    def test_approve_preauth(self, client, auth_headers):
        r = client.post(
            f"/api/inpatient/preauth/{_phase2['preauth_id']}/decision",
            json={"status": "approved", "approved_amount": 45000.0,
                  "validity_days": 30, "approval_reference": "APP-9999"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"
        assert r.json()["approved_amount"] == 45000.0

    def test_request_preauth_expansion(self, client, auth_headers):
        r = client.post(
            f"/api/inpatient/preauth/{_phase2['preauth_id']}/expansion-request",
            json={"requested_amount": 15000.0, "reason": "Extended stay"},
            headers=auth_headers,
        )
        assert r.status_code == 201

    # ------------------------------------------------------------------
    # TPA + bill splits
    # ------------------------------------------------------------------
    def test_create_tpa(self, client, auth_headers):
        r = client.post(
            "/api/inpatient/tpa",
            json={"tpa_name": "MediAssist", "tpa_code": "MA-01",
                  "default_discount_percent": 10.0, "email": "tpa@test.com"},
            headers=auth_headers,
        )
        assert r.status_code == 201
        _phase2["tpa_id"] = r.json()["id"]

    def test_split_interim_bill(self, client, auth_headers):
        bill_total = _phase2["interim_total"]
        insurance_part = round(bill_total * 0.7, 2)
        cash_part = round(bill_total - insurance_part, 2)

        r = client.post(
            f"/api/inpatient/bills/{_phase2['interim_bill_id']}/split",
            json={
                "splits": [
                    {"payer_type": "tpa", "payer_name": "MediAssist", "tpa_id": _phase2["tpa_id"], "amount": insurance_part},
                    {"payer_type": "cash", "payer_name": "Patient", "amount": cash_part},
                ],
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert len(r.json()) == 2

    def test_split_mismatched_total_rejected(self, client, auth_headers):
        r = client.post(
            f"/api/inpatient/bills/{_phase2['interim_bill_id']}/split",
            json={
                "splits": [
                    {"payer_type": "cash", "payer_name": "Patient", "amount": 1.0},
                ],
            },
            headers=auth_headers,
        )
        assert r.status_code == 400

    def test_tpa_outstanding(self, client, auth_headers):
        r = client.get("/api/inpatient/tpa/outstanding", headers=auth_headers)
        assert r.status_code == 200
        assert any(row["tpa_id"] == _phase2["tpa_id"] for row in r.json())


# ======================================================================
# Phase 3: Bed transfer history, housekeeping, reservations, nurse assignments
# ======================================================================

_phase3: dict = {}


class TestInpatientPhase3:
    """Self-contained Phase 3 flow."""

    def test_setup_rooms_with_beds(self, client, auth_headers, seed_data):
        # Ensure patient is not currently admitted (phase 1/2 may have left admissions)
        existing = client.get(
            f"/api/inpatient/admissions/patient/{seed_data['patient_id']}",
            headers=auth_headers,
        )
        if existing.status_code == 200:
            for adm in existing.json():
                if adm.get("status") == "admitted":
                    client.post(
                        f"/api/inpatient/admissions/{adm['id']}/discharge",
                        json={"discharge_type": "normal", "condition_on_discharge": "stable",
                              "discharge_summary": "Auto-discharged for Phase 3 setup",
                              "force_outstanding_balance": True, "force_unacknowledged_alerts": True, "force_missing_consents": True, "override_reason": "test cleanup"},
                        headers=auth_headers,
                    )

        # Two rooms in different departments (for ward_change detection)
        r1 = client.post("/api/inpatient/rooms",
            json={"room_number": "P3-A-1", "room_type": "general", "department": "Ward A",
                  "bed_count": 1, "room_charge_per_day": 600.0},
            headers=auth_headers)
        r2 = client.post("/api/inpatient/rooms",
            json={"room_number": "P3-B-1", "room_type": "general", "department": "Ward B",
                  "bed_count": 1, "room_charge_per_day": 700.0},
            headers=auth_headers)
        assert r1.status_code == 201 and r2.status_code == 201
        _phase3["room_a_id"] = r1.json()["id"]
        _phase3["room_b_id"] = r2.json()["id"]

        # Add a structured bed to each room
        b1 = client.post(f"/api/inpatient/rooms/{_phase3['room_a_id']}/beds",
            json={"bed_label": "A1"}, headers=auth_headers)
        b2 = client.post(f"/api/inpatient/rooms/{_phase3['room_b_id']}/beds",
            json={"bed_label": "B1"}, headers=auth_headers)
        assert b1.status_code == 201 and b2.status_code == 201
        _phase3["bed_a_id"] = b1.json()["id"]
        _phase3["bed_b_id"] = b2.json()["id"]

    def test_admit_to_ward_a(self, client, auth_headers, seed_data):
        r = client.post("/api/inpatient/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": _phase3["room_a_id"],
                "bed_id": _phase3["bed_a_id"],
                "admission_type": "elective",
                "admission_reason": "Phase 3 smoke test",
            }, headers=auth_headers)
        assert r.status_code == 201, r.text
        _phase3["admission_id"] = r.json()["id"]

    # ------------------------------------------------------------------
    # Bed transfer auto-log
    # ------------------------------------------------------------------
    def test_transfer_requires_reason(self, client, auth_headers):
        r = client.put(f"/api/inpatient/admissions/{_phase3['admission_id']}",
            json={"room_id": _phase3["room_b_id"]}, headers=auth_headers)
        assert r.status_code == 400
        assert "transfer_reason" in r.json()["detail"]

    def test_transfer_with_reason_logs_history(self, client, auth_headers):
        r = client.put(f"/api/inpatient/admissions/{_phase3['admission_id']}",
            json={"room_id": _phase3["room_b_id"], "bed_id": _phase3["bed_b_id"],
                  "transfer_reason": "Patient requested window bed"},
            headers=auth_headers)
        assert r.status_code == 200, r.text

        h = client.get(f"/api/inpatient/admissions/{_phase3['admission_id']}/transfers",
            headers=auth_headers)
        assert h.status_code == 200
        history = h.json()
        assert len(history) == 1
        assert history[0]["transfer_type"] == "ward_change"  # different departments
        assert history[0]["reason"] == "Patient requested window bed"
        assert history[0]["status"] == "completed"

    # ------------------------------------------------------------------
    # Inter-ward transfer with pending + accept flow
    # ------------------------------------------------------------------
    def test_initiate_pending_ward_transfer(self, client, auth_headers):
        # Create another room to transfer into
        r_room = client.post("/api/inpatient/rooms",
            json={"room_number": "P3-C-1", "room_type": "private", "department": "Ward C",
                  "bed_count": 1, "room_charge_per_day": 1000.0},
            headers=auth_headers)
        _phase3["room_c_id"] = r_room.json()["id"]

        r = client.post(f"/api/inpatient/admissions/{_phase3['admission_id']}/transfer-ward",
            json={"to_room_id": _phase3["room_c_id"],
                  "reason": "Post-op move",
                  "transfer_note": "BP stable. Keep NBM till morning. Wound clean."},
            headers=auth_headers)
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "pending"
        _phase3["pending_transfer_id"] = r.json()["id"]

    def test_pending_transfer_appears_in_list(self, client, auth_headers):
        r = client.get("/api/inpatient/transfers/pending", headers=auth_headers)
        assert r.status_code == 200
        assert any(t["id"] == _phase3["pending_transfer_id"] for t in r.json())

    def test_duplicate_pending_rejected(self, client, auth_headers):
        r = client.post(f"/api/inpatient/admissions/{_phase3['admission_id']}/transfer-ward",
            json={"to_room_id": _phase3["room_c_id"], "reason": "Again",
                  "transfer_note": "duplicate"}, headers=auth_headers)
        assert r.status_code == 409

    def test_accept_pending_transfer_moves_admission(self, client, auth_headers):
        r = client.patch(f"/api/inpatient/transfers/{_phase3['pending_transfer_id']}/accept",
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "accepted"

        # Verify admission's room is now room_c
        adm = client.get(f"/api/inpatient/admissions/{_phase3['admission_id']}", headers=auth_headers)
        assert adm.json()["room_id"] == _phase3["room_c_id"]

    # ------------------------------------------------------------------
    # Housekeeping: discharge auto-sets bed to 'cleaning'
    # ------------------------------------------------------------------
    def test_discharge_triggers_cleaning_status(self, client, auth_headers):
        # Discharge and check that the structured bed ended up in 'cleaning'
        # First, move back to bed_b_id so we have a structured bed to observe
        # (room_c doesn't have a structured bed from _phase3 state).
        # Actually, admission.bed_id may be b_id from earlier move.
        r_disch = client.post(
            f"/api/inpatient/admissions/{_phase3['admission_id']}/discharge",
            json={"discharge_type": "normal", "condition_on_discharge": "stable",
                  "discharge_summary": "Phase 3 test discharge",
                  "force_outstanding_balance": True, "force_unacknowledged_alerts": True, "force_missing_consents": True, "override_reason": "test"},
            headers=auth_headers,
        )
        assert r_disch.status_code == 201, r_disch.text

        # Check the cleaning list
        r = client.get("/api/inpatient/beds/needs-cleaning", headers=auth_headers)
        assert r.status_code == 200
        cleaning_bed_ids = {b["bed_id"] for b in r.json()}
        # bed_b_id should be in cleaning (admission was on it at discharge time)
        assert _phase3["bed_b_id"] in cleaning_bed_ids

    def test_mark_bed_clean_removes_from_list(self, client, auth_headers):
        r = client.patch(f"/api/inpatient/beds/{_phase3['bed_b_id']}/status",
            json={"status": "available"}, headers=auth_headers)
        assert r.status_code == 200

        r2 = client.get("/api/inpatient/beds/needs-cleaning", headers=auth_headers)
        assert _phase3["bed_b_id"] not in {b["bed_id"] for b in r2.json()}

    def test_turnover_stats_nonempty(self, client, auth_headers):
        r = client.get("/api/inpatient/beds/turnover-stats", headers=auth_headers)
        assert r.status_code == 200
        stats = r.json()
        assert stats["turnover_count"] >= 1

    # ------------------------------------------------------------------
    # Reservations
    # ------------------------------------------------------------------
    def test_create_reservation(self, client, auth_headers, seed_data):
        from datetime import datetime, timedelta
        r = client.post("/api/inpatient/reservations",
            json={
                "patient_id": seed_data["patient_id"],
                "room_type": "general",
                "reserved_for_date": (datetime.utcnow() + timedelta(days=1)).isoformat(),
                "reservation_reason": "elective",
                "notes": "Pre-booked for elective surgery",
            }, headers=auth_headers)
        assert r.status_code == 201, r.text
        _phase3["reservation_id"] = r.json()["id"]

    def test_reservation_requires_target(self, client, auth_headers, seed_data):
        from datetime import datetime
        r = client.post("/api/inpatient/reservations",
            json={"patient_id": seed_data["patient_id"],
                  "reserved_for_date": datetime.utcnow().isoformat(),
                  "reservation_reason": "elective"},
            headers=auth_headers)
        assert r.status_code == 400

    def test_convert_reservation_to_admission(self, client, auth_headers, seed_data):
        r = client.post(f"/api/inpatient/reservations/{_phase3['reservation_id']}/convert",
            json={
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "admission_type": "elective",
                "admission_reason": "Converted from reservation",
                "condition_on_admission": "stable",
            }, headers=auth_headers)
        assert r.status_code == 200, r.text
        _phase3["pkg_admission_id"] = r.json()["admission_id"]

        # Reservation status is now 'converted'
        r2 = client.get("/api/inpatient/reservations",
            params={"active_only": False}, headers=auth_headers)
        match = next(x for x in r2.json() if x["id"] == _phase3["reservation_id"])
        assert match["status"] == "converted"

    # ------------------------------------------------------------------
    # Nurse assignments
    # ------------------------------------------------------------------
    def test_create_nurse_user(self, client, auth_headers, db_session):
        from app.models.user import User, UserRole
        nurse_role = db_session.query(UserRole).filter(UserRole.name == "nurse").first()
        if not nurse_role:
            nurse_role = UserRole(name="nurse", is_system_role=True)
            db_session.add(nurse_role)
            db_session.flush()
        from app.utils.auth import get_password_hash
        nurse = User(
            username="testnurse",
            password_hash=get_password_hash("nurse123"),
            email="nurse@test.com",
            first_name="Test",
            last_name="Nurse",
            role_id=nurse_role.id,
            is_active=True,
        )
        db_session.add(nurse)
        db_session.commit()
        _phase3["nurse_id"] = nurse.id

    def test_assign_nurse_to_admission(self, client, auth_headers):
        r = client.post(f"/api/inpatient/admissions/{_phase3['pkg_admission_id']}/assign-nurse",
            json={"nurse_id": _phase3["nurse_id"], "shift": "morning", "is_primary": True},
            headers=auth_headers)
        assert r.status_code == 201, r.text
        _phase3["assignment_id"] = r.json()["id"]
        assert r.json()["is_primary"] is True

    def test_duplicate_assignment_rejected(self, client, auth_headers):
        r = client.post(f"/api/inpatient/admissions/{_phase3['pkg_admission_id']}/assign-nurse",
            json={"nurse_id": _phase3["nurse_id"], "shift": "morning"},
            headers=auth_headers)
        assert r.status_code == 409

    def test_list_nurse_assignments(self, client, auth_headers):
        r = client.get(f"/api/inpatient/admissions/{_phase3['pkg_admission_id']}/nurse-assignments",
            headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_my_patients_view(self, client, auth_headers):
        # Create a JWT for the nurse user
        from app.utils.auth import create_access_token
        nurse_token = create_access_token(data={"sub": "testnurse"})
        nurse_headers = {"Authorization": f"Bearer {nurse_token}"}
        r = client.get("/api/inpatient/nurses/my-patients",
            params={"shift": "morning"}, headers=nurse_headers)
        assert r.status_code == 200, r.text
        patients = r.json()
        assert any(p["admission_id"] == _phase3["pkg_admission_id"] for p in patients)

    def test_delete_nurse_assignment(self, client, auth_headers):
        r = client.delete(f"/api/inpatient/nurse-assignments/{_phase3['assignment_id']}",
            headers=auth_headers)
        assert r.status_code == 204


# ======================================================================
# Phase 4: Consents, incidents, readmission, mortality
# ======================================================================

_phase4: dict = {}


class TestInpatientPhase4:
    """Self-contained Phase 4 flow."""

    def test_setup_room_and_admission(self, client, auth_headers, seed_data):
        # Ensure the patient has a recent discharge so readmission detection fires.
        # First discharge any active admission.
        existing = client.get(
            f"/api/inpatient/admissions/patient/{seed_data['patient_id']}",
            headers=auth_headers,
        )
        has_discharge = False
        if existing.status_code == 200:
            for adm in existing.json():
                if adm.get("status") == "admitted":
                    client.post(
                        f"/api/inpatient/admissions/{adm['id']}/discharge",
                        json={"discharge_type": "normal", "condition_on_discharge": "stable",
                              "discharge_summary": "Auto-discharged for Phase 4 setup",
                              "force_outstanding_balance": True, "force_unacknowledged_alerts": True, "force_missing_consents": True, "override_reason": "test cleanup"},
                        headers=auth_headers,
                    )
                    has_discharge = True
                elif adm.get("status") == "discharged":
                    has_discharge = True

        # If patient has no discharge history (running Phase 4 in isolation),
        # create+discharge a warm-up admission so readmission detection has something to find.
        if not has_discharge:
            r_warm_room = client.post("/api/inpatient/rooms",
                json={"room_number": "P4-warm", "room_type": "general", "bed_count": 1,
                      "room_charge_per_day": 100.0}, headers=auth_headers)
            warm_room_id = r_warm_room.json()["id"]
            r_warm = client.post("/api/inpatient/admissions",
                json={"patient_id": seed_data["patient_id"],
                      "admitting_doctor_id": seed_data["doctor_user_id"],
                      "room_id": warm_room_id, "admission_type": "elective"},
                headers=auth_headers)
            warm_id = r_warm.json()["id"]
            client.post(f"/api/inpatient/admissions/{warm_id}/discharge",
                json={"discharge_type": "normal", "condition_on_discharge": "stable",
                      "discharge_summary": "warm-up",
                      "force_outstanding_balance": True, "force_unacknowledged_alerts": True, "force_missing_consents": True, "override_reason": "test"},
                headers=auth_headers)

        r_room = client.post("/api/inpatient/rooms",
            json={"room_number": "P4-1", "room_type": "general", "bed_count": 1,
                  "room_charge_per_day": 800.0},
            headers=auth_headers)
        _phase4["room_id"] = r_room.json()["id"]

        r = client.post("/api/inpatient/admissions",
            json={"patient_id": seed_data["patient_id"],
                  "admitting_doctor_id": seed_data["doctor_user_id"],
                  "room_id": _phase4["room_id"],
                  "admission_type": "elective",
                  "admission_reason": "Phase 4 smoke test"},
            headers=auth_headers)
        assert r.status_code == 201, r.text
        _phase4["admission_id"] = r.json()["id"]

    # ------------------------------------------------------------------
    # Readmission detection (this admission follows phase 3's discharge)
    # ------------------------------------------------------------------
    def test_admission_flagged_as_readmission(self, client, auth_headers):
        r = client.get(f"/api/inpatient/admissions/{_phase4['admission_id']}",
            headers=auth_headers)
        data = r.json()
        # Previous phases discharged the same patient recently → should be a readmission
        assert data["is_readmission"] is True
        assert data["previous_admission_id"] is not None
        assert data["days_since_last_discharge"] is not None
        assert data["days_since_last_discharge"] <= 30

    def test_readmission_list_includes_this(self, client, auth_headers):
        r = client.get("/api/inpatient/reports/readmissions", headers=auth_headers)
        assert r.status_code == 200
        assert any(x["admission_id"] == _phase4["admission_id"] for x in r.json())

    # ------------------------------------------------------------------
    # Consents
    # ------------------------------------------------------------------
    def test_create_consent_template(self, client, auth_headers):
        r = client.post("/api/inpatient/consent-templates",
            json={"consent_type": "surgical",
                  "template_name": "General surgical consent",
                  "content": "I understand the risks of surgery including bleeding and infection."},
            headers=auth_headers)
        assert r.status_code == 201, r.text
        _phase4["template_id"] = r.json()["id"]

    def test_record_consent(self, client, auth_headers):
        r = client.post(f"/api/inpatient/admissions/{_phase4['admission_id']}/consents",
            json={"consent_type": "surgical",
                  "template_id": _phase4["template_id"],
                  "procedure_name": "Appendectomy",
                  "patient_signature": "John Doe",
                  "signed_by": "patient"},
            headers=auth_headers)
        assert r.status_code == 201, r.text
        _phase4["consent_id"] = r.json()["id"]
        assert r.json()["withdrawn_at"] is None

    def test_consent_guardian_requires_name(self, client, auth_headers):
        r = client.post(f"/api/inpatient/admissions/{_phase4['admission_id']}/consents",
            json={"consent_type": "anaesthesia",
                  "procedure_name": "GA",
                  "patient_signature": "Mary Doe",
                  "signed_by": "guardian"},
            headers=auth_headers)
        assert r.status_code == 400

    def test_withdraw_consent(self, client, auth_headers):
        # Create a second consent to withdraw
        r = client.post(f"/api/inpatient/admissions/{_phase4['admission_id']}/consents",
            json={"consent_type": "blood_transfusion",
                  "patient_signature": "John Doe",
                  "signed_by": "patient"},
            headers=auth_headers)
        cid = r.json()["id"]
        r2 = client.post(f"/api/inpatient/consents/{cid}/withdraw",
            json={"withdrawal_reason": "Patient changed mind"},
            headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["withdrawn_at"] is not None

        # Double-withdraw should fail
        r3 = client.post(f"/api/inpatient/consents/{cid}/withdraw",
            json={"withdrawal_reason": "again"},
            headers=auth_headers)
        assert r3.status_code == 409

    def test_consent_pdf(self, client, auth_headers):
        r = client.get(f"/api/inpatient/consents/{_phase4['consent_id']}/pdf",
            headers=auth_headers)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert len(r.content) > 1000  # real PDF, not empty

    # ------------------------------------------------------------------
    # Incidents
    # ------------------------------------------------------------------
    def test_report_incident(self, client, auth_headers):
        from datetime import datetime
        r = client.post("/api/inpatient/incidents",
            json={"incident_type": "fall", "severity": "medium",
                  "incident_date": datetime.utcnow().isoformat(),
                  "admission_id": _phase4["admission_id"],
                  "description": "Patient slipped near bathroom",
                  "immediate_action": "Examined, no injuries",
                  "location": "Ward A bathroom"},
            headers=auth_headers)
        assert r.status_code == 201, r.text
        _phase4["incident_id"] = r.json()["id"]
        assert r.json()["status"] == "reported"

    def test_list_incidents_filters(self, client, auth_headers):
        r = client.get("/api/inpatient/incidents",
            params={"severity": "medium", "incident_type": "fall"},
            headers=auth_headers)
        assert r.status_code == 200
        assert any(i["id"] == _phase4["incident_id"] for i in r.json())

    def test_investigate_incident_state_machine(self, client, auth_headers):
        # reported → investigating
        r1 = client.post(f"/api/inpatient/incidents/{_phase4['incident_id']}/investigate",
            json={"new_status": "investigating",
                  "investigation_notes": "Reviewing CCTV"},
            headers=auth_headers)
        assert r1.status_code == 200
        assert r1.json()["status"] == "investigating"

        # investigating → resolved with root cause
        r2 = client.post(f"/api/inpatient/incidents/{_phase4['incident_id']}/investigate",
            json={"new_status": "resolved",
                  "root_cause": "Wet floor, no signage",
                  "corrective_actions": "Added anti-slip mat and warning sign"},
            headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["status"] == "resolved"
        assert r2.json()["root_cause"] == "Wet floor, no signage"

        # resolved → closed (final)
        r3 = client.post(f"/api/inpatient/incidents/{_phase4['incident_id']}/investigate",
            json={"new_status": "closed"},
            headers=auth_headers)
        assert r3.status_code == 200
        assert r3.json()["closed_at"] is not None

        # closed → anything fails
        r4 = client.post(f"/api/inpatient/incidents/{_phase4['incident_id']}/investigate",
            json={"new_status": "investigating"},
            headers=auth_headers)
        assert r4.status_code == 400

    def test_incident_monthly_report(self, client, auth_headers):
        r = client.get("/api/inpatient/incidents/reports/monthly", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert data["by_type"].get("fall", 0) >= 1

    # ------------------------------------------------------------------
    # Mortality (discharge with type='death')
    # ------------------------------------------------------------------
    def test_discharge_as_death(self, client, auth_headers):
        r = client.post(f"/api/inpatient/admissions/{_phase4['admission_id']}/discharge",
            json={"discharge_type": "death",
                  "condition_on_discharge": "critical",
                  "discharge_summary": "Patient expired despite resuscitation",
                  "diagnosis_on_discharge": "Cardiac arrest"},
            headers=auth_headers)
        assert r.status_code == 201, r.text

    def test_mortality_rejected_for_non_death(self, client, auth_headers, seed_data):
        # Create a new admission + discharge normally, then try mortality
        r_room = client.post("/api/inpatient/rooms",
            json={"room_number": "P4-2", "room_type": "general", "bed_count": 1,
                  "room_charge_per_day": 400.0}, headers=auth_headers)
        room_id = r_room.json()["id"]
        r_adm = client.post("/api/inpatient/admissions",
            json={"patient_id": seed_data["patient_id"],
                  "admitting_doctor_id": seed_data["doctor_user_id"],
                  "room_id": room_id, "admission_type": "elective"},
            headers=auth_headers)
        adm_id = r_adm.json()["id"]
        client.post(f"/api/inpatient/admissions/{adm_id}/discharge",
            json={"discharge_type": "normal", "condition_on_discharge": "stable",
                  "discharge_summary": "routine",
                  "force_outstanding_balance": True, "force_unacknowledged_alerts": True, "force_missing_consents": True, "override_reason": "test"},
            headers=auth_headers)

        r = client.put(f"/api/inpatient/admissions/{adm_id}/discharge/mortality",
            json={"cause_of_death": "x"}, headers=auth_headers)
        assert r.status_code == 400

    def test_update_mortality_details(self, client, auth_headers):
        from datetime import datetime
        r = client.put(
            f"/api/inpatient/admissions/{_phase4['admission_id']}/discharge/mortality",
            json={
                "cause_of_death": "Acute myocardial infarction",
                "time_of_death": datetime.utcnow().isoformat(),
                "death_certificate_number": "DC-2026-001",
                "mlc_required": False,
                "autopsy_done": False,
                "body_handed_over_to": "Spouse",
                "body_handover_relationship": "Wife",
            }, headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.json()["cause_of_death"] == "Acute myocardial infarction"

    def test_mortality_list(self, client, auth_headers):
        r = client.get("/api/inpatient/reports/mortality", headers=auth_headers)
        assert r.status_code == 200
        rows = r.json()
        assert any(x["admission_id"] == _phase4["admission_id"] for x in rows)
        ours = next(x for x in rows if x["admission_id"] == _phase4["admission_id"])
        assert ours["cause_of_death"] == "Acute myocardial infarction"

    def test_death_certificate_pdf(self, client, auth_headers):
        r = client.get(
            f"/api/inpatient/admissions/{_phase4['admission_id']}/death-certificate/pdf",
            headers=auth_headers)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert len(r.content) > 1000


# ======================================================================
# DAMA — Discharge Against Medical Advice
# ======================================================================

_dama: dict = {}


class TestDAMAFlow:
    def test_setup_admission_and_discharge_against_advice(self, client, auth_headers, seed_data):
        # Clear any active admission
        existing = client.get(f"/api/inpatient/admissions/patient/{seed_data['patient_id']}",
            headers=auth_headers)
        if existing.status_code == 200:
            for adm in existing.json():
                if adm.get("status") == "admitted":
                    client.post(
                        f"/api/inpatient/admissions/{adm['id']}/discharge",
                        json={"discharge_type": "normal", "condition_on_discharge": "stable",
                              "discharge_summary": "DAMA setup cleanup",
                              "force_outstanding_balance": True, "force_unacknowledged_alerts": True,
                              "force_missing_consents": True, "override_reason": "test"},
                        headers=auth_headers)
        r_room = client.post("/api/inpatient/rooms",
            json={"room_number": "DAMA-1", "room_type": "general", "bed_count": 1,
                  "room_charge_per_day": 800.0},
            headers=auth_headers)
        assert r_room.status_code == 201
        r_adm = client.post("/api/inpatient/admissions",
            json={"patient_id": seed_data["patient_id"],
                  "admitting_doctor_id": seed_data["doctor_user_id"],
                  "room_id": r_room.json()["id"], "admission_type": "elective",
                  "admission_reason": "DAMA test"},
            headers=auth_headers)
        assert r_adm.status_code == 201, r_adm.text
        _dama["admission_id"] = r_adm.json()["id"]
        _dama["doctor_id"] = seed_data["doctor_user_id"]
        # Discharge against advice — death/AMA discharges skip the safety gates
        r_disc = client.post(f"/api/inpatient/admissions/{_dama['admission_id']}/discharge",
            json={"discharge_type": "against_advice", "condition_on_discharge": "unchanged",
                  "discharge_summary": "Patient demanded discharge; advised against."},
            headers=auth_headers)
        assert r_disc.status_code == 201, r_disc.text

    def test_dama_requires_both_acknowledgements(self, client, auth_headers):
        r = client.post(f"/api/inpatient/admissions/{_dama['admission_id']}/dama",
            json={
                "attending_doctor_id": _dama["doctor_id"],
                "medical_advice_given": "Continue IV antibiotics for 48 more hours",
                "risks_explained": "Sepsis, organ failure, death",
                "patient_acknowledges_advice": True,
                "patient_absolves_hospital": False,
                "primary_signature": "John Doe",
                "witness_name": "Nurse Smith",
                "witness_signature": "Nurse Smith",
            },
            headers=auth_headers)
        assert r.status_code == 400, r.text

    def test_dama_record_creates_and_pdf_renders(self, client, auth_headers):
        r = client.post(f"/api/inpatient/admissions/{_dama['admission_id']}/dama",
            json={
                "attending_doctor_id": _dama["doctor_id"],
                "medical_advice_given": "Continue IV antibiotics for 48 more hours.",
                "risks_explained": "Sepsis, organ failure, possible death.",
                "language_used": "english",
                "patient_acknowledges_advice": True,
                "patient_absolves_hospital": True,
                "signed_by": "patient",
                "primary_signature": "John Doe",
                "primary_signature_type": "typed",
                "witness_name": "Nurse Smith",
                "witness_designation": "Senior Nurse",
                "witness_signature": "Nurse Smith",
                "witness_signature_type": "typed",
                "notes": "Patient was lucid and articulate at signing.",
            },
            headers=auth_headers)
        assert r.status_code == 201, r.text
        assert r.json()["signed_by"] == "patient"
        # Duplicate filing rejected
        r2 = client.post(f"/api/inpatient/admissions/{_dama['admission_id']}/dama",
            json={
                "attending_doctor_id": _dama["doctor_id"],
                "medical_advice_given": "x", "risks_explained": "y",
                "patient_acknowledges_advice": True, "patient_absolves_hospital": True,
                "primary_signature": "X", "witness_name": "Y", "witness_signature": "Z",
            },
            headers=auth_headers)
        assert r2.status_code == 409
        # PDF
        r_pdf = client.get(f"/api/inpatient/admissions/{_dama['admission_id']}/dama/pdf",
            headers=auth_headers)
        assert r_pdf.status_code == 200
        assert r_pdf.headers["content-type"] == "application/pdf"
        assert len(r_pdf.content) > 1000


# ======================================================================
# E1 — Daily census report
# ======================================================================


class TestDailyCensus:
    def test_census_json(self, client, auth_headers):
        r = client.get("/api/inpatient/reports/census", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "totals" in data
        assert "by_department" in data
        assert "by_room_type" in data
        t = data["totals"]
        assert t["total_beds"] >= 0
        assert t["occupied"] >= 0

    def test_census_pdf(self, client, auth_headers):
        r = client.get("/api/inpatient/reports/census/pdf", headers=auth_headers)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert len(r.content) > 1000


# ======================================================================
# D1 — Room rate snapshotting per stay segment
# ======================================================================

_rate_snap: dict = {}


class TestRoomRateSnapshot:
    def test_admission_snapshots_initial_rate(self, client, auth_headers, seed_data):
        # Clear any active admission
        existing = client.get(f"/api/inpatient/admissions/patient/{seed_data['patient_id']}",
            headers=auth_headers)
        if existing.status_code == 200:
            for adm in existing.json():
                if adm.get("status") == "admitted":
                    client.post(f"/api/inpatient/admissions/{adm['id']}/discharge",
                        json={"discharge_type": "normal", "condition_on_discharge": "stable",
                              "discharge_summary": "rate snapshot setup",
                              "force_outstanding_balance": True, "force_unacknowledged_alerts": True,
                              "force_missing_consents": True, "override_reason": "test"},
                        headers=auth_headers)
        r_room = client.post("/api/inpatient/rooms",
            json={"room_number": "RATE-1", "room_type": "general", "bed_count": 1,
                  "room_charge_per_day": 1000.0},
            headers=auth_headers)
        assert r_room.status_code == 201
        _rate_snap["room_id"] = r_room.json()["id"]
        r_adm = client.post("/api/inpatient/admissions",
            json={"patient_id": seed_data["patient_id"],
                  "admitting_doctor_id": seed_data["doctor_user_id"],
                  "room_id": r_room.json()["id"], "admission_type": "elective",
                  "admission_reason": "Rate snapshot test"},
            headers=auth_headers)
        assert r_adm.status_code == 201, r_adm.text
        _rate_snap["admission_id"] = r_adm.json()["id"]

        # Bill preview should reflect the initial rate
        r_bill = client.get(f"/api/inpatient/admissions/{_rate_snap['admission_id']}/bill",
            headers=auth_headers)
        assert r_bill.status_code == 200
        data = r_bill.json()
        assert data["room"]["charge_per_day"] == 1000.0
        assert "rate_segments" in data["room"]
        assert len(data["room"]["rate_segments"]) >= 1
        assert data["room"]["rate_segments"][0]["rate"] == 1000.0

    def test_room_rate_change_does_not_rerate_existing_stay(self, client, auth_headers):
        # Bump the room rate after admission
        r = client.put(f"/api/inpatient/rooms/{_rate_snap['room_id']}",
            json={"room_charge_per_day": 5000.0}, headers=auth_headers)
        assert r.status_code == 200, r.text
        # Bill must still use the snapshotted 1000.0 rate, not the new 5000.0
        r_bill = client.get(f"/api/inpatient/admissions/{_rate_snap['admission_id']}/bill",
            headers=auth_headers)
        assert r_bill.status_code == 200
        data = r_bill.json()
        assert data["room"]["rate_segments"][0]["rate"] == 1000.0


# ======================================================================
# LOA — Leave of Absence (pass-out)
# ======================================================================

_loa: dict = {}


class TestLOAFlow:
    def test_setup_admission(self, client, auth_headers, seed_data):
        existing = client.get(f"/api/inpatient/admissions/patient/{seed_data['patient_id']}",
            headers=auth_headers)
        if existing.status_code == 200:
            for adm in existing.json():
                if adm.get("status") == "admitted":
                    client.post(f"/api/inpatient/admissions/{adm['id']}/discharge",
                        json={"discharge_type": "normal", "condition_on_discharge": "stable",
                              "discharge_summary": "loa setup",
                              "force_outstanding_balance": True, "force_unacknowledged_alerts": True,
                              "force_missing_consents": True, "override_reason": "test"},
                        headers=auth_headers)
        r_room = client.post("/api/inpatient/rooms",
            json={"room_number": "LOA-1", "room_type": "general", "bed_count": 1,
                  "room_charge_per_day": 1000.0},
            headers=auth_headers)
        assert r_room.status_code == 201
        r_adm = client.post("/api/inpatient/admissions",
            json={"patient_id": seed_data["patient_id"],
                  "admitting_doctor_id": seed_data["doctor_user_id"],
                  "room_id": r_room.json()["id"], "admission_type": "elective",
                  "admission_reason": "LOA test"},
            headers=auth_headers)
        assert r_adm.status_code == 201, r_adm.text
        _loa["admission_id"] = r_adm.json()["id"]
        _loa["doctor_id"] = seed_data["doctor_user_id"]

    def test_create_loa(self, client, auth_headers):
        from datetime import datetime as _dt, timedelta as _td
        r = client.post(f"/api/inpatient/admissions/{_loa['admission_id']}/loa",
            json={
                "start_datetime": _dt.utcnow().isoformat(),
                "expected_return_datetime": (_dt.utcnow() + _td(days=2)).isoformat(),
                "reason": "Family wedding",
                "approved_by_doctor_id": _loa["doctor_id"],
            },
            headers=auth_headers)
        assert r.status_code == 201, r.text
        _loa["loa_id"] = r.json()["id"]

    def test_overlapping_loa_rejected(self, client, auth_headers):
        from datetime import datetime as _dt, timedelta as _td
        r = client.post(f"/api/inpatient/admissions/{_loa['admission_id']}/loa",
            json={
                "start_datetime": _dt.utcnow().isoformat(),
                "expected_return_datetime": (_dt.utcnow() + _td(days=1)).isoformat(),
                "reason": "Overlap",
                "approved_by_doctor_id": _loa["doctor_id"],
            },
            headers=auth_headers)
        assert r.status_code == 409

    def test_discharge_blocked_during_loa(self, client, auth_headers):
        r = client.post(f"/api/inpatient/admissions/{_loa['admission_id']}/discharge",
            json={"discharge_type": "normal", "condition_on_discharge": "stable",
                  "discharge_summary": "x"},
            headers=auth_headers)
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "active_loa"

    def test_loa_return_then_discharge_allowed(self, client, auth_headers):
        r1 = client.patch(f"/api/inpatient/loa/{_loa['loa_id']}/return",
            json={}, headers=auth_headers)
        assert r1.status_code == 200, r1.text
        # Now discharge succeeds (no bills → balance is zero, no outstanding gate)
        r2 = client.post(f"/api/inpatient/admissions/{_loa['admission_id']}/discharge",
            json={"discharge_type": "normal", "condition_on_discharge": "stable",
                  "discharge_summary": "Returned from LOA, ready to go home"},
            headers=auth_headers)
        assert r2.status_code == 201, r2.text


# ======================================================================
# E2 — Monthly outcomes report
# ======================================================================


class TestMonthlyOutcomes:
    def test_monthly_outcomes_default_window(self, client, auth_headers):
        r = client.get("/api/inpatient/reports/monthly-outcomes", headers=auth_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "month" in data
        assert "totals" in data
        assert "mortality" in data
        assert "readmissions" in data
        assert "length_of_stay" in data
        # Required totals keys
        for k in ("admissions", "discharges", "deaths", "readmissions",
                  "mortality_rate_pct", "readmission_rate_pct",
                  "average_daily_occupancy", "average_occupancy_pct"):
            assert k in data["totals"]

    def test_monthly_outcomes_explicit_month(self, client, auth_headers):
        r = client.get("/api/inpatient/reports/monthly-outcomes?month=2026-04",
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.json()["month"] == "2026-04"

    def test_monthly_outcomes_invalid_month(self, client, auth_headers):
        r = client.get("/api/inpatient/reports/monthly-outcomes?month=not-a-month",
            headers=auth_headers)
        assert r.status_code == 400

    def test_monthly_outcomes_pdf(self, client, auth_headers):
        r = client.get("/api/inpatient/reports/monthly-outcomes/pdf",
            headers=auth_headers)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert len(r.content) > 1000


# ======================================================================
# E3 — Doctor productivity report
# ======================================================================


class TestDoctorProductivity:
    def test_doctor_productivity_default_window(self, client, auth_headers):
        from datetime import date as _d, timedelta as _td
        today = _d.today()
        start = (today - _td(days=30)).isoformat()
        end = today.isoformat()
        r = client.get(f"/api/inpatient/reports/doctor-productivity?date_from={start}&date_to={end}",
            headers=auth_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "rows" in data
        assert "doctor_count" in data
        # At least one doctor should have activity from prior tests
        assert data["doctor_count"] >= 1
        for row in data["rows"]:
            for k in ("doctor_id", "doctor_name", "admissions", "discharges",
                      "deaths", "readmissions_30d", "ot_as_surgeon",
                      "ot_as_anaesthetist", "visits", "average_los_days",
                      "visit_fees_billed", "ot_surgeon_fees", "ot_anaesthetist_fees",
                      "total_billed_attributable"):
                assert k in row

    def test_doctor_productivity_invalid_range(self, client, auth_headers):
        r = client.get("/api/inpatient/reports/doctor-productivity?date_from=2026-05-01&date_to=2026-04-01",
            headers=auth_headers)
        assert r.status_code == 400

    def test_doctor_productivity_csv(self, client, auth_headers):
        from datetime import date as _d, timedelta as _td
        today = _d.today()
        start = (today - _td(days=30)).isoformat()
        end = today.isoformat()
        r = client.get(f"/api/inpatient/reports/doctor-productivity/csv?date_from={start}&date_to={end}",
            headers=auth_headers)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/csv")
        body = r.content.decode("utf-8")
        assert "doctor_id" in body
        assert "total_billed_attributable" in body

    def test_doctor_productivity_pdf(self, client, auth_headers):
        from datetime import date as _d, timedelta as _td
        today = _d.today()
        start = (today - _td(days=30)).isoformat()
        end = today.isoformat()
        r = client.get(f"/api/inpatient/reports/doctor-productivity/pdf?date_from={start}&date_to={end}",
            headers=auth_headers)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert len(r.content) > 1000


# ======================================================================
# A2/A3 — Code-blue + Shift handover
# ======================================================================


class TestCodeBlueAndHandover:
    def test_log_code_blue(self, client, auth_headers):
        from datetime import datetime as _dt
        r = client.post("/api/inpatient/code-blue",
            json={
                "event_type": "code_blue",
                "event_datetime": _dt.utcnow().isoformat(),
                "location": "ICU bed 3",
                "response_time_seconds": 45,
                "team_members": "Dr A, Nurse B, Tech C",
                "interventions": "CPR, defibrillation x2, intubated",
                "outcome": "rosc",
            },
            headers=auth_headers)
        assert r.status_code == 201, r.text
        assert r.json()["outcome"] == "rosc"

    def test_invalid_outcome_rejected(self, client, auth_headers):
        from datetime import datetime as _dt
        r = client.post("/api/inpatient/code-blue",
            json={"event_datetime": _dt.utcnow().isoformat(),
                  "location": "x", "outcome": "miracle"},
            headers=auth_headers)
        assert r.status_code == 400

    def test_code_blue_monthly_stats(self, client, auth_headers):
        r = client.get("/api/inpatient/reports/code-blue", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["total_events"] >= 1
        assert "by_outcome" in d


# ======================================================================
# Diet — meal log + kitchen ticket
# ======================================================================

_diet: dict = {}


class TestDietMealLog:
    def test_setup_admission_and_diet_order(self, client, auth_headers, seed_data):
        existing = client.get(f"/api/inpatient/admissions/patient/{seed_data['patient_id']}",
            headers=auth_headers)
        if existing.status_code == 200:
            for adm in existing.json():
                if adm.get("status") == "admitted":
                    client.post(f"/api/inpatient/admissions/{adm['id']}/discharge",
                        json={"discharge_type": "normal", "condition_on_discharge": "stable",
                              "discharge_summary": "diet setup",
                              "force_outstanding_balance": True, "force_unacknowledged_alerts": True,
                              "force_missing_consents": True, "override_reason": "test"},
                        headers=auth_headers)
        r_room = client.post("/api/inpatient/rooms",
            json={"room_number": "DIET-1", "room_type": "general", "bed_count": 1,
                  "room_charge_per_day": 800.0, "department": "Medical Ward A"},
            headers=auth_headers)
        assert r_room.status_code == 201
        r_adm = client.post("/api/inpatient/admissions",
            json={"patient_id": seed_data["patient_id"],
                  "admitting_doctor_id": seed_data["doctor_user_id"],
                  "room_id": r_room.json()["id"], "admission_type": "elective",
                  "admission_reason": "Diet test"},
            headers=auth_headers)
        assert r_adm.status_code == 201, r_adm.text
        _diet["admission_id"] = r_adm.json()["id"]
        # Order a diabetic diet
        r_order = client.post(
            f"/api/inpatient/admissions/{_diet['admission_id']}/diet-orders",
            json={"diet_type": "diabetic", "meal_instructions": "Low sugar; 4 meals/day",
                  "allergies": "Peanuts"},
            headers=auth_headers)
        assert r_order.status_code == 201, r_order.text
        _diet["order_id"] = r_order.json()["id"]

    def test_log_meal_creates_then_idempotent(self, client, auth_headers):
        # First call creates
        r1 = client.post(f"/api/inpatient/diet-orders/{_diet['order_id']}/meal-log",
            json={"meal_time": "lunch", "status": "served", "notes": "Ate well"},
            headers=auth_headers)
        assert r1.status_code == 201, r1.text
        first_id = r1.json()["id"]
        # Same slot updates instead of duplicating
        r2 = client.post(f"/api/inpatient/diet-orders/{_diet['order_id']}/meal-log",
            json={"meal_time": "lunch", "status": "partial", "notes": "Ate half"},
            headers=auth_headers)
        assert r2.status_code == 201
        assert r2.json()["id"] == first_id
        assert r2.json()["status"] == "partial"

    def test_invalid_meal_time_rejected(self, client, auth_headers):
        r = client.post(f"/api/inpatient/diet-orders/{_diet['order_id']}/meal-log",
            json={"meal_time": "midnight_snack", "status": "served"},
            headers=auth_headers)
        assert r.status_code == 400

    def test_kitchen_ticket_pdf_renders(self, client, auth_headers):
        r = client.get("/api/inpatient/diet/kitchen-ticket/pdf?meal_time=lunch",
            headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert len(r.content) > 1000


# ======================================================================
# ICU add-ons: I/O fluid balance + critical lab alerts
# ======================================================================

_icu: dict = {}


class TestIcuAddons:
    def test_setup_room_and_admission(self, client, auth_headers, seed_data):
        existing = client.get(
            f"/api/inpatient/admissions/patient/{seed_data['patient_id']}",
            headers=auth_headers,
        )
        if existing.status_code == 200:
            for adm in existing.json():
                if adm.get("status") == "admitted":
                    client.post(
                        f"/api/inpatient/admissions/{adm['id']}/discharge",
                        json={"discharge_type": "normal", "condition_on_discharge": "stable",
                              "discharge_summary": "Auto-discharge for ICU setup",
                              "force_outstanding_balance": True, "force_unacknowledged_alerts": True, "force_missing_consents": True, "override_reason": "test cleanup"},
                        headers=auth_headers,
                    )

        r_room = client.post("/api/inpatient/rooms",
            json={"room_number": "ICU-1", "room_type": "icu", "bed_count": 1,
                  "room_charge_per_day": 3000.0}, headers=auth_headers)
        _icu["room_id"] = r_room.json()["id"]
        r = client.post("/api/inpatient/admissions",
            json={"patient_id": seed_data["patient_id"],
                  "admitting_doctor_id": seed_data["doctor_user_id"],
                  "room_id": _icu["room_id"], "admission_type": "emergency"},
            headers=auth_headers)
        assert r.status_code == 201, r.text
        _icu["admission_id"] = r.json()["id"]

    # I/O fluid balance
    def test_record_intake(self, client, auth_headers):
        r = client.post(f"/api/inpatient/admissions/{_icu['admission_id']}/io",
            json={"io_type": "intake", "category": "iv", "amount_ml": 500, "shift": "morning"},
            headers=auth_headers)
        assert r.status_code == 201, r.text

    def test_record_output(self, client, auth_headers):
        r = client.post(f"/api/inpatient/admissions/{_icu['admission_id']}/io",
            json={"io_type": "output", "category": "urine", "amount_ml": 350, "shift": "morning"},
            headers=auth_headers)
        assert r.status_code == 201

    def test_invalid_category_rejected(self, client, auth_headers):
        r = client.post(f"/api/inpatient/admissions/{_icu['admission_id']}/io",
            json={"io_type": "intake", "category": "urine", "amount_ml": 100, "shift": "morning"},
            headers=auth_headers)
        assert r.status_code == 400

    def test_balance_summary(self, client, auth_headers):
        r = client.get(f"/api/inpatient/admissions/{_icu['admission_id']}/io/balance",
            headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total_intake_ml"] == 500
        assert data["total_output_ml"] == 350
        assert data["net_balance_ml"] == 150
        assert data["by_shift"]["morning"]["intake"] == 500

    def test_list_io_entries(self, client, auth_headers):
        r = client.get(f"/api/inpatient/admissions/{_icu['admission_id']}/io",
            headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()) == 2

    # Critical lab alerts
    def test_set_critical_thresholds(self, client, auth_headers, db_session, seed_data):
        from app.models.lab import LabTest, LabTestCategory, LabTestParameter
        cat = LabTestCategory(name="Biochemistry", hospital_id=seed_data["hospital_id"])
        db_session.add(cat); db_session.flush()
        test = LabTest(name="Potassium", test_code="K", category_id=cat.id, cost=100.0,
                       hospital_id=seed_data["hospital_id"])
        db_session.add(test); db_session.flush()
        param = LabTestParameter(test_id=test.id, parameter_name="Potassium",
                                 unit="mmol/L", field_type="numeric")
        db_session.add(param); db_session.commit()
        _icu["param_id"] = param.id
        _icu["test_id"] = test.id

        r = client.post(f"/api/inpatient/lab-parameters/{param.id}/critical-thresholds",
            json={"critical_low": 3.0, "critical_high": 6.0}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["critical_low"] == 3.0

    def test_scan_triggers_critical_alert(self, client, auth_headers, db_session, seed_data):
        from app.models.lab import PatientLabOrder
        order = PatientLabOrder(
            order_number="LAB-ICU-001",
            patient_id=seed_data["patient_id"],
            test_id=_icu["test_id"],
            doctor_id=seed_data["doctor_user_id"],
            admission_id=_icu["admission_id"],
            status="completed", amount=100.0,
        )
        db_session.add(order); db_session.commit()
        _icu["lab_order_id"] = order.id

        r = client.post(f"/api/inpatient/lab-orders/{order.id}/scan-critical",
            json={str(_icu["param_id"]): 7.2}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["new_alerts"] == 1

    def test_idempotent_scan(self, client, auth_headers):
        r = client.post(f"/api/inpatient/lab-orders/{_icu['lab_order_id']}/scan-critical",
            json={str(_icu["param_id"]): 7.2}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["new_alerts"] == 0

    def test_list_critical_alerts(self, client, auth_headers):
        r = client.get("/api/inpatient/critical-alerts",
            params={"admission_id": _icu["admission_id"]}, headers=auth_headers)
        assert r.status_code == 200
        alerts = r.json()
        assert len(alerts) >= 1
        _icu["alert_id"] = alerts[0]["id"]
        assert alerts[0]["status"] == "new"
        assert alerts[0]["parameter_name"] == "Potassium"

    def test_acknowledge_alert(self, client, auth_headers):
        r = client.patch(f"/api/inpatient/critical-alerts/{_icu['alert_id']}/acknowledge",
            json={"mark_addressed": False}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "acknowledged"

    def test_address_alert(self, client, auth_headers):
        r = client.patch(f"/api/inpatient/critical-alerts/{_icu['alert_id']}/acknowledge",
            json={"mark_addressed": True, "addressed_notes": "Administered Kayexalate"},
            headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "addressed"

    def test_double_address_rejected(self, client, auth_headers):
        r = client.patch(f"/api/inpatient/critical-alerts/{_icu['alert_id']}/acknowledge",
            json={"mark_addressed": True}, headers=auth_headers)
        assert r.status_code == 409

    def test_scan_in_range_no_alert(self, client, auth_headers, db_session, seed_data):
        from app.models.lab import PatientLabOrder
        order2 = PatientLabOrder(
            order_number="LAB-ICU-002",
            patient_id=seed_data["patient_id"],
            test_id=_icu["test_id"],
            doctor_id=seed_data["doctor_user_id"],
            admission_id=_icu["admission_id"],
            status="completed", amount=100.0,
        )
        db_session.add(order2); db_session.commit()

        r = client.post(f"/api/inpatient/lab-orders/{order2.id}/scan-critical",
            json={str(_icu["param_id"]): 4.5},  # within 3.0-6.0
            headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["new_alerts"] == 0


# ======================================================================
# Role boundary tests — verify granular permissions reject cross-role access
# ======================================================================

_boundary: dict = {}


@pytest.fixture(scope="session")
def boundary_setup(TestSessionLocal, seed_data):
    """Seed nurse + billing_admin + doctor users with specific role-permission grants.
    Grants match the matrix in setup_hospital_roles.py."""
    from app.models.user import User, UserRole
    from app.models.permissions import RoleModulePermission
    from app.models.inpatient import RoomManagement, Admission
    from app.utils.auth import get_password_hash

    db_session = TestSessionLocal()
    roles = {}
    for name in ("nurse", "billing_admin", "doctor_v2"):
        r = db_session.query(UserRole).filter(UserRole.name == name).first()
        if not r:
            r = UserRole(name=name, is_system_role=True)
            db_session.add(r)
            db_session.flush()
        roles[name] = r

    # Seed role-module permissions per the matrix
    grants = {
        "nurse": [
            "view_occupancy", "record_vitals", "view_vitals", "record_io", "view_io",
            "administer_medications", "view_mar",
            "manage_nursing_notes", "manage_diet_orders", "manage_allergies", "record_visits",
            "record_consent", "report_incident", "acknowledge_critical_alert",
            "accept_ward_transfer", "manage_housekeeping", "view_roster", "view_documents",
        ],
        "billing_admin": [
            "view_occupancy", "view_bill", "generate_interim_bill", "finalize_bill",
            "manage_packages", "manage_ancillary_charges",
            "receive_deposits", "issue_refunds", "manage_bill_splits",
            "update_claim_status", "manage_preauth",
            "manage_ancillary_catalog", "manage_surgery_packages", "manage_tpa",
            "view_documents",
        ],
        "doctor_v2": [
            "view_occupancy", "admit_patients", "update_admission", "discharge_patients",
            "record_mortality", "record_vitals", "view_vitals", "record_io", "view_io",
            "administer_medications", "view_mar",
            "manage_nursing_notes", "manage_diet_orders", "manage_allergies", "record_visits",
            "order_labs", "prescribe_medications", "schedule_ot",
            "record_consent", "withdraw_consent",
            "transfer_beds", "initiate_ward_transfer", "accept_ward_transfer",
            "report_incident", "acknowledge_critical_alert",
            "view_bill", "view_readmissions", "view_mortality",
            "upload_documents", "view_documents",
        ],
    }
    for role_name, perms in grants.items():
        existing = db_session.query(RoleModulePermission).filter(
            RoleModulePermission.role_id == roles[role_name].id,
            RoleModulePermission.module_name == "inpatient",
        ).first()
        if existing:
            existing.permissions = perms
        else:
            db_session.add(RoleModulePermission(
                role_id=roles[role_name].id,
                module_name="inpatient",
                permissions=perms,
            ))

    # Users
    users = {}
    for role_name, username in [("nurse", "boundary_nurse"),
                                 ("billing_admin", "boundary_biller"),
                                 ("doctor_v2", "boundary_doc")]:
        u = db_session.query(User).filter(User.username == username).first()
        if not u:
            u = User(
                username=username,
                password_hash=get_password_hash("pw"),
                email=f"{username}@test.com",
                first_name=username, last_name="Test",
                role_id=roles[role_name].id,
                is_active=True,
            )
            db_session.add(u)
            db_session.flush()
        users[role_name] = u
    db_session.commit()

    # Create a fresh admission so we have an ID to test against
    # (use the doctor_v2 user as admitting doctor)
    # First discharge any active admission for the seed patient
    active = db_session.query(Admission).filter(
        Admission.patient_id == seed_data["patient_id"],
        Admission.status == "admitted",
    ).first()
    if active:
        active.status = "discharged"
        db_session.commit()

    room = RoomManagement(
        room_number="BOUND-1", room_type="general", bed_count=1,
        available_beds=1, room_charge_per_day=500.0,
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(room); db_session.flush()

    import uuid
    admission = Admission(
        admission_number=f"BND-{uuid.uuid4().hex[:8]}",
        patient_id=seed_data["patient_id"],
        admitting_doctor_id=seed_data["doctor_user_id"],
        room_id=room.id,
        admission_type="elective",
        status="admitted",
    )
    db_session.add(admission); db_session.commit()

    from app.utils.auth import create_access_token
    result = {
        "admission_id": admission.id,
        "room_id": room.id,
        "nurse_headers": {"Authorization": f"Bearer {create_access_token(data={'sub': 'boundary_nurse'})}"},
        "biller_headers": {"Authorization": f"Bearer {create_access_token(data={'sub': 'boundary_biller'})}"},
        "doc_headers": {"Authorization": f"Bearer {create_access_token(data={'sub': 'boundary_doc'})}"},
    }
    db_session.close()
    return result


class TestRoleBoundaries:
    """Each role should succeed on in-scope actions and get 403 on out-of-scope ones."""

    # ----- Nurse -----
    def test_nurse_can_record_vitals(self, client, boundary_setup):
        r = client.post(
            f"/api/inpatient/admissions/{boundary_setup['admission_id']}/vitals",
            json={"bp_systolic": 110, "heart_rate": 80, "shift": "morning"},
            headers=boundary_setup["nurse_headers"],
        )
        assert r.status_code == 201, r.text

    def test_nurse_can_record_io(self, client, boundary_setup):
        r = client.post(
            f"/api/inpatient/admissions/{boundary_setup['admission_id']}/io",
            json={"io_type": "intake", "category": "oral", "amount_ml": 200, "shift": "morning"},
            headers=boundary_setup["nurse_headers"],
        )
        assert r.status_code == 201, r.text

    def test_nurse_cannot_finalize_bill(self, client, boundary_setup):
        r = client.post(
            f"/api/inpatient/admissions/{boundary_setup['admission_id']}/bill/finalize",
            json={}, headers=boundary_setup["nurse_headers"],
        )
        assert r.status_code == 403

    def test_nurse_cannot_issue_refund(self, client, boundary_setup):
        r = client.post(
            f"/api/inpatient/admissions/{boundary_setup['admission_id']}/refund",
            json={"amount": 100, "payment_method": "cash"},
            headers=boundary_setup["nurse_headers"],
        )
        assert r.status_code == 403

    def test_nurse_cannot_apply_package(self, client, boundary_setup):
        r = client.post(
            f"/api/inpatient/admissions/{boundary_setup['admission_id']}/package",
            json={"package_id": 9999},
            headers=boundary_setup["nurse_headers"],
        )
        assert r.status_code == 403

    def test_nurse_cannot_discharge(self, client, boundary_setup):
        r = client.post(
            f"/api/inpatient/admissions/{boundary_setup['admission_id']}/discharge",
            json={"discharge_type": "normal", "condition_on_discharge": "stable",
                  "discharge_summary": "x",
                  "force_outstanding_balance": True, "force_unacknowledged_alerts": True, "force_missing_consents": True, "override_reason": "test"},
            headers=boundary_setup["nurse_headers"],
        )
        assert r.status_code == 403

    def test_nurse_cannot_close_incident(self, client, boundary_setup):
        # First get an incident id — nurse can report, so let's use that to get one
        from datetime import datetime
        r_report = client.post("/api/inpatient/incidents",
            json={"incident_type": "fall", "severity": "low",
                  "incident_date": datetime.utcnow().isoformat(),
                  "description": "Test fall",
                  "admission_id": boundary_setup["admission_id"]},
            headers=boundary_setup["nurse_headers"])
        assert r_report.status_code == 201, r_report.text
        incident_id = r_report.json()["id"]

        # Nurse cannot investigate
        r = client.post(f"/api/inpatient/incidents/{incident_id}/investigate",
            json={"new_status": "closed"},
            headers=boundary_setup["nurse_headers"])
        assert r.status_code == 403

    # ----- Billing admin -----
    def test_billing_admin_can_finalize_bill(self, client, boundary_setup):
        # Add a small charge first so the bill isn't empty
        r0 = client.post(
            f"/api/inpatient/admissions/{boundary_setup['admission_id']}/ancillary-charges",
            json={"service_id": 0, "quantity": 1},  # will likely 404 due to service_id=0, that's OK
            headers=boundary_setup["biller_headers"],
        )
        # The above may 404. Let's just try finalize — if subtotal is 0 it will 400, but 400 != 403
        r = client.post(
            f"/api/inpatient/admissions/{boundary_setup['admission_id']}/bill/finalize",
            json={}, headers=boundary_setup["biller_headers"],
        )
        # Either 200 (bill finalized), 400 (no charges), or other business error — crucially NOT 403
        assert r.status_code != 403, f"Billing admin should not be forbidden, got {r.status_code}: {r.text}"

    def test_billing_admin_cannot_record_vitals(self, client, boundary_setup):
        r = client.post(
            f"/api/inpatient/admissions/{boundary_setup['admission_id']}/vitals",
            json={"bp_systolic": 120, "shift": "morning"},
            headers=boundary_setup["biller_headers"],
        )
        assert r.status_code == 403

    def test_billing_admin_cannot_discharge(self, client, boundary_setup):
        r = client.post(
            f"/api/inpatient/admissions/{boundary_setup['admission_id']}/discharge",
            json={"discharge_type": "normal", "condition_on_discharge": "stable",
                  "discharge_summary": "x",
                  "force_outstanding_balance": True, "force_unacknowledged_alerts": True, "force_missing_consents": True, "override_reason": "test"},
            headers=boundary_setup["biller_headers"],
        )
        assert r.status_code == 403

    def test_billing_admin_cannot_administer_medication(self, client, boundary_setup):
        r = client.post(
            f"/api/inpatient/admissions/{boundary_setup['admission_id']}/mar/generate",
            headers=boundary_setup["biller_headers"],
        )
        assert r.status_code == 403

    def test_billing_admin_can_receive_deposit(self, client, boundary_setup):
        r = client.post(
            f"/api/inpatient/admissions/{boundary_setup['admission_id']}/deposits",
            json={"amount": 500, "payment_method": "cash", "deposit_type": "topup"},
            headers=boundary_setup["biller_headers"],
        )
        assert r.status_code == 201, r.text

    # ----- Doctor -----
    def test_doctor_can_order_labs_and_prescribe(self, client, boundary_setup):
        # These endpoints don't exist as inpatient-specific yet (labs go through /api/lab),
        # but prescribe_medications permission is still defined. We verify it can do
        # MAR-related actions.
        r = client.post(
            f"/api/inpatient/admissions/{boundary_setup['admission_id']}/mar/generate",
            headers=boundary_setup["doc_headers"],
        )
        # Doctor has administer_medications → should not be 403
        assert r.status_code != 403, r.text

    def test_doctor_cannot_finalize_bill(self, client, boundary_setup):
        r = client.post(
            f"/api/inpatient/admissions/{boundary_setup['admission_id']}/bill/finalize",
            json={}, headers=boundary_setup["doc_headers"],
        )
        assert r.status_code == 403

    def test_doctor_cannot_manage_tpa(self, client, boundary_setup):
        r = client.post("/api/inpatient/tpa",
            json={"tpa_name": "ShouldFail"},
            headers=boundary_setup["doc_headers"],
        )
        assert r.status_code == 403


# ======================================================================
# Nurse shift roster — duty schedule independent of patient assignments
# ======================================================================

_roster: dict = {}


class TestNurseRoster:
    """Validates roster CRUD, bulk-assign, conflict prevention, coverage,
    on-duty filter, and view/manage permission boundaries."""

    def test_setup_nurses(self, client, auth_headers, db_session, seed_data):
        from app.models.user import User, UserRole
        from app.utils.auth import get_password_hash

        nurse_role = db_session.query(UserRole).filter(UserRole.name == "nurse").first()
        if not nurse_role:
            nurse_role = UserRole(name="nurse", is_system_role=True)
            db_session.add(nurse_role); db_session.flush()

        nurse_ids = []
        for username, fname in [("roster_nurse_1", "Alpha"),
                                 ("roster_nurse_2", "Bravo"),
                                 ("roster_nurse_3", "Charlie")]:
            u = db_session.query(User).filter(User.username == username).first()
            if not u:
                u = User(username=username,
                         password_hash=get_password_hash("pw"),
                         email=f"{username}@test.com",
                         first_name=fname, last_name="Nurse",
                         role_id=nurse_role.id, is_active=True)
                db_session.add(u); db_session.flush()
            nurse_ids.append(u.id)
        db_session.commit()
        _roster["nurse_ids"] = nurse_ids

    def test_create_roster_entry(self, client, auth_headers):
        from datetime import date, timedelta
        target = date.today() + timedelta(days=1)
        _roster["target_date"] = target.isoformat()
        r = client.post("/api/inpatient/roster",
            json={"nurse_id": _roster["nurse_ids"][0],
                  "roster_date": target.isoformat(),
                  "shift": "morning",
                  "status": "working"},
            headers=auth_headers)
        assert r.status_code == 201, r.text
        _roster["entry_id"] = r.json()["id"]
        assert r.json()["status"] == "working"

    def test_double_booking_rejected(self, client, auth_headers):
        r = client.post("/api/inpatient/roster",
            json={"nurse_id": _roster["nurse_ids"][0],
                  "roster_date": _roster["target_date"],
                  "shift": "morning",
                  "status": "off"},
            headers=auth_headers)
        assert r.status_code == 409
        assert "already rostered" in r.json()["detail"].lower()

    def test_bulk_assign_week(self, client, auth_headers):
        from datetime import date, timedelta
        start = date.today() + timedelta(days=2)
        end = start + timedelta(days=4)
        r = client.post("/api/inpatient/roster/bulk",
            json={"nurse_ids": _roster["nurse_ids"][1:],  # 2 nurses
                  "from_date": start.isoformat(),
                  "to_date": end.isoformat(),
                  "shifts": ["morning", "afternoon"],
                  "status": "working"},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        # 2 nurses × 5 days × 2 shifts = 20 entries
        assert r.json()["created"] == 20
        assert r.json()["skipped"] == 0

    def test_bulk_skip_existing(self, client, auth_headers):
        from datetime import date, timedelta
        start = date.today() + timedelta(days=2)
        end = start + timedelta(days=4)
        r = client.post("/api/inpatient/roster/bulk",
            json={"nurse_ids": _roster["nurse_ids"][1:],
                  "from_date": start.isoformat(),
                  "to_date": end.isoformat(),
                  "shifts": ["morning"],
                  "status": "leave"},  # different status
            headers=auth_headers)
        # All would conflict, skipped (no overwrite)
        assert r.json()["created"] == 0
        assert r.json()["skipped"] == 10  # 2 × 5 days × 1 shift

    def test_bulk_overwrite(self, client, auth_headers):
        from datetime import date, timedelta
        start = date.today() + timedelta(days=2)
        r = client.post("/api/inpatient/roster/bulk",
            json={"nurse_ids": [_roster["nurse_ids"][1]],
                  "from_date": start.isoformat(),
                  "to_date": start.isoformat(),
                  "shifts": ["morning"],
                  "status": "leave",
                  "overwrite": True},
            headers=auth_headers)
        assert r.json()["overwritten"] == 1

    def test_list_roster_filtering(self, client, auth_headers):
        from datetime import date, timedelta
        start = date.today() + timedelta(days=2)
        end = start + timedelta(days=4)
        r = client.get("/api/inpatient/roster",
            params={"from_date": start.isoformat(), "to_date": end.isoformat(), "shift": "morning"},
            headers=auth_headers)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 9  # 2 nurses × 5 days × 1 shift = 10 minus 1 leave (still listed)
        assert all(row["shift"] == "morning" for row in rows)

    def test_grid_endpoint(self, client, auth_headers):
        from datetime import date, timedelta
        start = date.today() + timedelta(days=2)
        end = start + timedelta(days=2)
        r = client.get("/api/inpatient/roster/grid",
            params={"from_date": start.isoformat(), "to_date": end.isoformat()},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "nurses" in data
        assert "dates" in data
        assert "cells" in data
        assert len(data["dates"]) == 3
        assert "morning" in data["shifts"]

    def test_coverage_endpoint(self, client, auth_headers):
        from datetime import date, timedelta
        start = date.today() + timedelta(days=2)
        end = start + timedelta(days=4)
        r = client.get("/api/inpatient/roster/coverage",
            params={"from_date": start.isoformat(), "to_date": end.isoformat(),
                    "min_per_shift": 3},
            headers=auth_headers)
        assert r.status_code == 200, r.text
        shifts = r.json()["shifts"]
        # Bulk assigned 2 nurses → understaffed when min is 3
        morning_entries = [s for s in shifts if s["shift"] == "morning"]
        assert any(s["is_understaffed"] for s in morning_entries)

    def test_on_duty_endpoint(self, client, auth_headers):
        from datetime import date, timedelta
        start = date.today() + timedelta(days=2)
        r = client.get("/api/inpatient/roster/on-duty",
            params={"target_date": start.isoformat(), "shift": "afternoon"},
            headers=auth_headers)
        assert r.status_code == 200
        # Both nurses bulk-assigned to afternoon, all 'working' → both returned
        assert len(r.json()) == 2

    def test_on_duty_excludes_leave(self, client, auth_headers):
        # Nurse 2 had morning overwritten to 'leave' on day 0 → excluded
        from datetime import date, timedelta
        start = date.today() + timedelta(days=2)
        r = client.get("/api/inpatient/roster/on-duty",
            params={"target_date": start.isoformat(), "shift": "morning"},
            headers=auth_headers)
        on_duty_ids = {row["nurse_id"] for row in r.json()}
        assert _roster["nurse_ids"][1] not in on_duty_ids
        assert _roster["nurse_ids"][2] in on_duty_ids  # still working

    def test_update_roster_entry(self, client, auth_headers):
        r = client.put(f"/api/inpatient/roster/{_roster['entry_id']}",
            json={"status": "on_call", "notes": "Backup for emergencies"},
            headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "on_call"
        assert r.json()["notes"] == "Backup for emergencies"

    def test_delete_roster_entry(self, client, auth_headers):
        r = client.delete(f"/api/inpatient/roster/{_roster['entry_id']}",
            headers=auth_headers)
        assert r.status_code == 204

    def test_invalid_date_range(self, client, auth_headers):
        from datetime import date, timedelta
        r = client.post("/api/inpatient/roster/bulk",
            json={"nurse_ids": [_roster["nurse_ids"][0]],
                  "from_date": (date.today() + timedelta(days=5)).isoformat(),
                  "to_date": date.today().isoformat(),  # before from_date
                  "shifts": ["morning"],
                  "status": "working"},
            headers=auth_headers)
        assert r.status_code == 400

    # Permission boundaries (uses boundary_setup fixture from earlier)
    def test_nurse_can_view_roster(self, client, boundary_setup):
        from datetime import date, timedelta
        r = client.get("/api/inpatient/roster",
            params={"from_date": date.today().isoformat(),
                    "to_date": (date.today() + timedelta(days=7)).isoformat()},
            headers=boundary_setup["nurse_headers"])
        assert r.status_code == 200, r.text

    def test_nurse_cannot_manage_roster(self, client, boundary_setup):
        from datetime import date, timedelta
        r = client.post("/api/inpatient/roster",
            json={"nurse_id": 1, "roster_date": (date.today() + timedelta(days=10)).isoformat(),
                  "shift": "morning", "status": "working"},
            headers=boundary_setup["nurse_headers"])
        assert r.status_code == 403

    def test_billing_admin_cannot_view_roster(self, client, boundary_setup):
        from datetime import date, timedelta
        r = client.get("/api/inpatient/roster",
            params={"from_date": date.today().isoformat(),
                    "to_date": (date.today() + timedelta(days=7)).isoformat()},
            headers=boundary_setup["biller_headers"])
        # Billing admin doesn't have view_roster
        assert r.status_code == 403


# ============================================================
# Rate management refactor (per-user inpatient fee + procedure catalog)
# ============================================================

@pytest.fixture(scope="session")
def rate_setup(TestSessionLocal, seed_data):
    """Seed nurse role so we can create nurse users in the rate tests."""
    from app.models.user import UserRole
    db = TestSessionLocal()
    try:
        for name in ("nurse",):
            r = db.query(UserRole).filter(UserRole.name == name).first()
            if not r:
                db.add(UserRole(name=name, is_system_role=True))
        db.commit()
        nurse_role_id = db.query(UserRole).filter(UserRole.name == "nurse").first().id
        doctor_role_id = db.query(UserRole).filter(UserRole.name == "doctor").first().id
        return {"nurse_role_id": nurse_role_id, "doctor_role_id": doctor_role_id}
    finally:
        db.close()


class TestRateRefactor:
    """User creation must require inpatient_fee_inr for doctor/nurse roles;
    PatientVisit charge auto-fills from the visiting user's inpatient_fee_inr;
    OT scheduling auto-fills procedure / surgeon / anaesthetist charges."""

    def test_create_doctor_user_without_fee_rejected(self, client, auth_headers, rate_setup):
        r = client.post("/api/admin/users", json={
            "username": "doctor_no_fee",
            "email": "doctor_no_fee@test.com",
            "password": "x",
            "first_name": "No", "last_name": "Fee",
            "role_id": rate_setup["doctor_role_id"],
        }, headers=auth_headers)
        assert r.status_code == 400, r.text
        assert "inpatient" in r.json()["detail"].lower()

    def test_create_doctor_user_with_zero_fee_rejected(self, client, auth_headers, rate_setup):
        r = client.post("/api/admin/users", json={
            "username": "doctor_zero_fee",
            "email": "doctor_zero_fee@test.com",
            "password": "x",
            "first_name": "Zero", "last_name": "Fee",
            "role_id": rate_setup["doctor_role_id"],
            "inpatient_fee_inr": "0",
        }, headers=auth_headers)
        assert r.status_code == 400

    def test_create_doctor_user_with_fee_succeeds(self, client, auth_headers, rate_setup):
        r = client.post("/api/admin/users", json={
            "username": "doctor_with_fee",
            "email": "doctor_with_fee@test.com",
            "password": "x",
            "first_name": "Has", "last_name": "Fee",
            "role_id": rate_setup["doctor_role_id"],
            "inpatient_fee_inr": "750",
        }, headers=auth_headers)
        assert r.status_code == 200, r.text

    def test_create_nurse_user_without_fee_rejected(self, client, auth_headers, rate_setup):
        r = client.post("/api/admin/users", json={
            "username": "nurse_no_fee",
            "email": "nurse_no_fee@test.com",
            "password": "x",
            "first_name": "Nurse", "last_name": "NoFee",
            "role_id": rate_setup["nurse_role_id"],
        }, headers=auth_headers)
        assert r.status_code == 400

    def test_create_nurse_user_with_fee_succeeds(self, client, auth_headers, rate_setup):
        r = client.post("/api/admin/users", json={
            "username": "nurse_with_fee",
            "email": "nurse_with_fee@test.com",
            "password": "x",
            "first_name": "Nurse", "last_name": "HasFee",
            "role_id": rate_setup["nurse_role_id"],
            "inpatient_fee_inr": "200",
        }, headers=auth_headers)
        assert r.status_code == 200, r.text

    # --- Procedure catalog CRUD ---

    def test_procedure_crud(self, client, auth_headers):
        # Create
        r = client.post("/api/inpatient/procedures",
            json={"name": "Appendectomy", "default_rate": 15000, "description": "Standard"},
            headers=auth_headers)
        assert r.status_code == 201, r.text
        pid = r.json()["id"]

        # List (active_only)
        r = client.get("/api/inpatient/procedures", headers=auth_headers)
        assert r.status_code == 200
        names = [p["name"] for p in r.json()]
        assert "Appendectomy" in names

        # Update
        r = client.put(f"/api/inpatient/procedures/{pid}",
            json={"default_rate": 18000}, headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["default_rate"] == 18000

        # Soft-delete
        r = client.delete(f"/api/inpatient/procedures/{pid}", headers=auth_headers)
        assert r.status_code == 204

        # No longer listed in active_only
        r = client.get("/api/inpatient/procedures", headers=auth_headers)
        assert "Appendectomy" not in [p["name"] for p in r.json()]

        # Listed when active_only=false
        r = client.get("/api/inpatient/procedures?active_only=false", headers=auth_headers)
        assert "Appendectomy" in [p["name"] for p in r.json()]

    def test_procedure_duplicate_name_rejected(self, client, auth_headers):
        client.post("/api/inpatient/procedures",
            json={"name": "Cholecystectomy", "default_rate": 20000},
            headers=auth_headers)
        r = client.post("/api/inpatient/procedures",
            json={"name": "Cholecystectomy", "default_rate": 25000},
            headers=auth_headers)
        assert r.status_code == 400

    # --- Visit charge auto-fill ---

    def test_visit_charge_pulls_from_user_inpatient_fee(self, client, auth_headers, seed_data, TestSessionLocal):
        # Set the seed doctor's inpatient_fee_inr
        from app.models.user import User
        from app.models.inpatient import RoomManagement, Admission
        import uuid as _uuid
        db = TestSessionLocal()
        doctor = db.query(User).filter(User.id == seed_data["doctor_user_id"]).first()
        doctor.inpatient_fee_inr = "350"
        db.commit()

        # Make sure we have an active admission to attach the visit to
        active = db.query(Admission).filter(
            Admission.patient_id == seed_data["patient_id"],
            Admission.status == "admitted",
        ).first()
        if not active:
            room = RoomManagement(
                room_number=f"RATE-{_uuid.uuid4().hex[:6]}", room_type="general",
                bed_count=1, available_beds=1, room_charge_per_day=400.0,
                hospital_id=seed_data["hospital_id"],
            )
            db.add(room); db.flush()
            active = Admission(
                admission_number=f"RT-{_uuid.uuid4().hex[:8]}",
                patient_id=seed_data["patient_id"],
                admitting_doctor_id=seed_data["doctor_user_id"],
                room_id=room.id,
                admission_type="elective",
                status="admitted",
            )
            db.add(active); db.commit()
        admission_id = active.id
        db.close()

        r = client.post(f"/api/inpatient/admissions/{admission_id}/visits",
            json={"visit_type": "doctor_visit", "visitor_id": seed_data["doctor_user_id"]},
            headers=auth_headers)
        assert r.status_code == 201, r.text
        assert float(r.json()["charge_amount"]) == 350.0

    # --- OT auto-fill from catalog and user fees ---

    def test_ot_autofills_procedure_and_doctor_fees(self, client, auth_headers, seed_data, TestSessionLocal):
        from app.models.user import User
        # Update doctor's fee
        db = TestSessionLocal()
        doctor = db.query(User).filter(User.id == seed_data["doctor_user_id"]).first()
        doctor.inpatient_fee_inr = "500"
        db.commit()
        db.close()

        # Add a procedure to the catalog
        rp = client.post("/api/inpatient/procedures",
            json={"name": "Hernia Repair", "default_rate": 12000},
            headers=auth_headers)
        assert rp.status_code == 201
        proc_id = rp.json()["id"]

        # Schedule an OT referencing the procedure + the doctor as both surgeon and anaesthetist
        from datetime import datetime, timedelta
        r = client.post("/api/inpatient/ot", json={
            "patient_id": seed_data["patient_id"],
            "surgeon_id": seed_data["doctor_user_id"],
            "anaesthetist_id": seed_data["doctor_user_id"],
            "ot_room_number": "OT-1",
            "procedure_name": "Hernia Repair",
            "procedure_id": proc_id,
            "scheduled_date": (datetime.utcnow() + timedelta(days=1)).isoformat(),
        }, headers=auth_headers)
        assert r.status_code == 201, r.text
        body = r.json()
        assert float(body["procedure_charge"]) == 12000.0
        assert float(body["surgeon_fee"]) == 500.0
        assert float(body["anaesthetist_fee"]) == 500.0

    def test_ot_freetext_procedure_no_autofill(self, client, auth_headers, seed_data):
        # Free-text procedure (no procedure_id) — procedure_charge should stay 0
        from datetime import datetime, timedelta
        r = client.post("/api/inpatient/ot", json={
            "patient_id": seed_data["patient_id"],
            "surgeon_id": seed_data["doctor_user_id"],
            "ot_room_number": "OT-2",
            "procedure_name": "Custom one-off procedure",
            "scheduled_date": (datetime.utcnow() + timedelta(days=2)).isoformat(),
        }, headers=auth_headers)
        assert r.status_code == 201, r.text
        assert float(r.json()["procedure_charge"]) == 0.0
        assert r.json()["procedure_id"] is None


# ============================================================
# B7 — Emergency / casualty workflow
# ============================================================
class TestEmergencyAdmission:
    def _fresh_room(self, client, auth_headers, label):
        r = client.post("/api/inpatient/rooms", json={
            "room_number": label, "room_type": "emergency",
            "ward_name": "Casualty", "bed_count": 2, "room_charge_per_day": 1500,
        }, headers=auth_headers)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def test_quick_admit_creates_stub_patient(self, client, auth_headers, seed_data):
        room_id = self._fresh_room(client, auth_headers, "ER-Q1")
        r = client.post("/api/inpatient/admissions/quick-admit", json={
            "first_name": "UNKNOWN MALE-1",
            "admitting_doctor_id": seed_data["doctor_user_id"],
            "room_id": room_id,
            "triage_level": 1,
            "chief_complaint": "Unconscious, RTA suspected",
            "arrival_mode": "ambulance",
            "ambulance_details": "AP-09-AB-1234, paramedic Ravi",
            "is_mlc": True,
            "mlc_type": "rta",
            "police_station_informed": "Madhapur PS",
            "condition_on_admission": "critical",
        }, headers=auth_headers)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["admission_type"] == "emergency"
        assert body["triage_level"] == 1
        assert body["is_mlc"] is True
        assert body["mlc_type"] == "rta"
        assert body["mlc_informed_at"] is not None
        assert body["registration_complete"] is False

    def test_mlc_requires_valid_type(self, client, auth_headers, seed_data):
        room_id = self._fresh_room(client, auth_headers, "ER-Q2")
        r = client.post("/api/inpatient/admissions/quick-admit", json={
            "first_name": "Test",
            "admitting_doctor_id": seed_data["doctor_user_id"],
            "room_id": room_id,
            "triage_level": 2,
            "is_mlc": True,
            "mlc_type": "not_a_real_type",
        }, headers=auth_headers)
        assert r.status_code == 422  # pydantic pattern rejects

    def test_triage_level_out_of_range(self, client, auth_headers, seed_data):
        room_id = self._fresh_room(client, auth_headers, "ER-Q3")
        r = client.post("/api/inpatient/admissions/quick-admit", json={
            "first_name": "Test",
            "admitting_doctor_id": seed_data["doctor_user_id"],
            "room_id": room_id,
            "triage_level": 9,
        }, headers=auth_headers)
        assert r.status_code == 422

    def test_emergency_fields_round_trip_via_normal_admit(self, client, auth_headers, seed_data, TestSessionLocal):
        # Create a fresh patient
        from app.models.patient import Patient
        import uuid
        db = TestSessionLocal()
        p = Patient(first_name="ER", last_name="Patient",
                    primary_phone="9999999999", patient_id=str(uuid.uuid4()),
                    age=30, gender="male", hospital_id=1)
        db.add(p); db.commit(); pid = p.id; db.close()

        room_id = self._fresh_room(client, auth_headers, "ER-Q4")
        r = client.post("/api/inpatient/admissions", json={
            "patient_id": pid,
            "admitting_doctor_id": seed_data["doctor_user_id"],
            "room_id": room_id,
            "admission_type": "emergency",
            "triage_level": 3,
            "chief_complaint": "Chest pain",
            "arrival_mode": "walk_in",
        }, headers=auth_headers)
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["triage_level"] == 3
        assert body["arrival_mode"] == "walk_in"
        assert body["registration_complete"] is True  # patient was full

    def test_add_mlc_later_via_update(self, client, auth_headers, seed_data, TestSessionLocal):
        # Create patient + emergency admission without MLC, then mark MLC after
        from app.models.patient import Patient
        import uuid
        db = TestSessionLocal()
        p = Patient(first_name="Late", last_name="MLC",
                    primary_phone="8888888888", patient_id=str(uuid.uuid4()),
                    age=40, gender="female", hospital_id=1)
        db.add(p); db.commit(); pid = p.id; db.close()

        room_id = self._fresh_room(client, auth_headers, "ER-Q5")
        r = client.post("/api/inpatient/admissions", json={
            "patient_id": pid,
            "admitting_doctor_id": seed_data["doctor_user_id"],
            "room_id": room_id,
            "admission_type": "emergency",
            "triage_level": 4,
        }, headers=auth_headers)
        assert r.status_code == 201
        adm_id = r.json()["id"]

        u = client.put(f"/api/inpatient/admissions/{adm_id}", json={
            "is_mlc": True,
            "mlc_type": "assault",
            "mlc_number": "MLC-2026-001",
            "police_station_informed": "Cyberabad PS",
        }, headers=auth_headers)
        assert u.status_code == 200, u.text
        body = u.json()
        assert body["is_mlc"] is True
        assert body["mlc_number"] == "MLC-2026-001"
        assert body["mlc_informed_at"] is not None


# ============================================================
# B7.5 / B7.6 / B7.7 / B7.8 — MLC PDF, Observation, Waiver, Triage queue
# ============================================================
class TestEmergencyExtras:
    def _fresh_room(self, client, auth_headers, label):
        r = client.post("/api/inpatient/rooms", json={
            "room_number": label, "room_type": "emergency",
            "ward_name": "Casualty", "bed_count": 2, "room_charge_per_day": 1500,
        }, headers=auth_headers)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def test_mlc_pdf_generates(self, client, auth_headers, seed_data):
        room_id = self._fresh_room(client, auth_headers, "ER-PDF1")
        r = client.post("/api/inpatient/admissions/quick-admit", json={
            "first_name": "MLC", "admitting_doctor_id": seed_data["doctor_user_id"],
            "room_id": room_id, "triage_level": 2,
            "is_mlc": True, "mlc_type": "rta", "mlc_number": "MLC-001",
            "police_station_informed": "Test PS",
        }, headers=auth_headers)
        assert r.status_code == 201
        adm_id = r.json()["id"]
        pdf = client.get(f"/api/inpatient/admissions/{adm_id}/mlc/pdf", headers=auth_headers)
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content[:4] == b"%PDF"

    def test_mlc_pdf_rejects_non_mlc(self, client, auth_headers, seed_data):
        room_id = self._fresh_room(client, auth_headers, "ER-PDF2")
        r = client.post("/api/inpatient/admissions/quick-admit", json={
            "first_name": "Not-MLC", "admitting_doctor_id": seed_data["doctor_user_id"],
            "room_id": room_id, "triage_level": 4,
        }, headers=auth_headers)
        assert r.status_code == 201
        adm_id = r.json()["id"]
        pdf = client.get(f"/api/inpatient/admissions/{adm_id}/mlc/pdf", headers=auth_headers)
        assert pdf.status_code == 400

    def test_observation_skips_room_charge(self, client, auth_headers, seed_data):
        room_id = self._fresh_room(client, auth_headers, "ER-OBS1")
        r = client.post("/api/inpatient/admissions/quick-admit", json={
            "first_name": "Obs", "admitting_doctor_id": seed_data["doctor_user_id"],
            "room_id": room_id, "triage_level": 3,
            "is_observation": True,
        }, headers=auth_headers)
        assert r.status_code == 201
        adm_id = r.json()["id"]
        # Bill preview — room_total must be 0 even though some stay days elapsed
        bp = client.get(f"/api/inpatient/admissions/{adm_id}/bill", headers=auth_headers)
        assert bp.status_code == 200, bp.text
        assert float(bp.json().get("room_total", 0)) == 0.0

    def test_deposit_waiver_allows_discharge_with_balance(self, client, auth_headers, seed_data, TestSessionLocal):
        from app.models.patient import Patient
        import uuid
        db = TestSessionLocal()
        p = Patient(first_name="Waiver", last_name="Case",
                    primary_phone="7777777777", patient_id=str(uuid.uuid4()),
                    age=55, gender="male", hospital_id=1)
        db.add(p); db.commit(); pid = p.id; db.close()
        room_id = self._fresh_room(client, auth_headers, "ER-WAV1")
        r = client.post("/api/inpatient/admissions", json={
            "patient_id": pid, "admitting_doctor_id": seed_data["doctor_user_id"],
            "room_id": room_id, "admission_type": "emergency",
            "triage_level": 2,
            "deposit_waived": True, "deposit_waiver_reason": "Charity case",
        }, headers=auth_headers)
        assert r.status_code == 201
        adm_id = r.json()["id"]
        # Discharge without paying — should succeed (waiver soft-passes)
        d = client.post(f"/api/inpatient/admissions/{adm_id}/discharge", json={
            "discharge_type": "normal",
            "condition_on_discharge": "stable",
            "force_unacknowledged_alerts": True,
            "force_missing_consents": True,
        }, headers=auth_headers)
        assert d.status_code in (200, 201), d.text

    def test_triage_queue_sorted_by_acuity(self, client, auth_headers, seed_data):
        # Three fresh ER admits with different triage levels — verify ordering
        room1 = self._fresh_room(client, auth_headers, "ER-TQ-A")
        room2 = self._fresh_room(client, auth_headers, "ER-TQ-B")
        room3 = self._fresh_room(client, auth_headers, "ER-TQ-C")
        for (rid, name, t) in [(room1, "Triage-Low", 5), (room2, "Triage-Hi", 1), (room3, "Triage-Mid", 3)]:
            r = client.post("/api/inpatient/admissions/quick-admit", json={
                "first_name": name, "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": rid, "triage_level": t,
            }, headers=auth_headers)
            assert r.status_code == 201, r.text

        q = client.get("/api/inpatient/admissions/triage-queue", headers=auth_headers)
        assert q.status_code == 200, q.text
        items = q.json()["items"]
        # Filter to the three we just created (others may be present from prior tests)
        names = [i["patient_name"] for i in items if i["patient_name"] in ("Triage-Hi UNKNOWN", "Triage-Mid UNKNOWN", "Triage-Low UNKNOWN")]
        assert names.index("Triage-Hi UNKNOWN") < names.index("Triage-Mid UNKNOWN") < names.index("Triage-Low UNKNOWN")
        for i in items:
            assert "elapsed_minutes" in i




# ============================================================
# B6 — Body release / mortuary / post-mortem
# ============================================================
class TestBodyRelease:
    def _admit_and_die(self, client, auth_headers, seed_data, label, mlc=False):
        rr = client.post("/api/inpatient/rooms", json={
            "room_number": label, "room_type": "general", "ward_name": "W1",
            "bed_count": 1, "room_charge_per_day": 1000,
        }, headers=auth_headers)
        assert rr.status_code == 201, rr.text
        room_id = rr.json()["id"]
        # Fresh patient
        from app.models.patient import Patient
        import uuid
        from app.models.inpatient import Admission as _A
        # Create via admission API
        if mlc:
            r = client.post("/api/inpatient/admissions/quick-admit", json={
                "first_name": "Decedent-" + label, "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room_id, "triage_level": 1, "is_mlc": True, "mlc_type": "rta",
                "mlc_number": "MLC-" + label, "police_station_informed": "Test PS",
            }, headers=auth_headers)
        else:
            # Make a stub patient then admit
            pid_resp = client.post("/api/inpatient/admissions/quick-admit", json={
                "first_name": "Decedent-" + label, "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room_id, "triage_level": 3,
            }, headers=auth_headers)
            r = pid_resp
        assert r.status_code == 201, r.text
        adm_id = r.json()["id"]
        # Discharge as death
        d = client.post(f"/api/inpatient/admissions/{adm_id}/discharge", json={
            "discharge_type": "death", "condition_on_discharge": "critical",
            "force_outstanding_balance": True, "force_unacknowledged_alerts": True,
            "force_missing_consents": True, "override_reason": "test",
        }, headers=auth_headers)
        assert d.status_code in (200, 201), d.text
        return adm_id

    def test_get_creates_record_with_mlc_defaults(self, client, auth_headers, seed_data):
        adm_id = self._admit_and_die(client, auth_headers, seed_data, "BR-MLC", mlc=True)
        r = client.get(f"/api/inpatient/admissions/{adm_id}/body-release", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["police_noc_required"] is True
        assert body["post_mortem_required"] is True
        assert body["body_in_mortuary_at"] is not None

    def test_release_blocked_without_noc(self, client, auth_headers, seed_data):
        adm_id = self._admit_and_die(client, auth_headers, seed_data, "BR-NOCBLK", mlc=True)
        # Mark PM done so only NOC gate fires
        client.put(f"/api/inpatient/admissions/{adm_id}/body-release",
            json={"pm_completed_at": "2026-05-01T10:00:00", "pm_report_received": True}, headers=auth_headers)
        r = client.post(f"/api/inpatient/admissions/{adm_id}/body-release/release", json={
            "released_to_name": "Son", "released_to_relationship": "son",
            "released_to_id_proof_type": "aadhar", "released_to_id_proof_number": "1234",
            "witness_name": "Cousin",
        }, headers=auth_headers)
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "missing_police_noc"

    def test_release_succeeds_with_noc_and_pm(self, client, auth_headers, seed_data):
        adm_id = self._admit_and_die(client, auth_headers, seed_data, "BR-OK", mlc=True)
        client.put(f"/api/inpatient/admissions/{adm_id}/body-release", json={
            "pm_completed_at": "2026-05-01T10:00:00", "pm_report_received": True,
            "police_noc_received": True, "police_noc_number": "NOC-1",
        }, headers=auth_headers)
        r = client.post(f"/api/inpatient/admissions/{adm_id}/body-release/release", json={
            "released_to_name": "Wife", "released_to_relationship": "wife",
            "released_to_id_proof_type": "aadhar", "released_to_id_proof_number": "5678",
            "witness_name": "Brother",
        }, headers=auth_headers)
        assert r.status_code == 200, r.text
        assert r.json()["body_released"] is True
        # Locked after release
        r2 = client.put(f"/api/inpatient/admissions/{adm_id}/body-release", json={"mortuary_slot": "M9"}, headers=auth_headers)
        assert r2.status_code == 400

    def test_force_release_requires_reason(self, client, auth_headers, seed_data):
        adm_id = self._admit_and_die(client, auth_headers, seed_data, "BR-FORCE", mlc=True)
        # Try forcing without reason → 400
        r = client.post(f"/api/inpatient/admissions/{adm_id}/body-release/release", json={
            "released_to_name": "Son", "released_to_relationship": "son",
            "released_to_id_proof_type": "aadhar", "released_to_id_proof_number": "1234",
            "witness_name": "Cousin",
            "force_missing_noc": True, "force_missing_pm": True,
        }, headers=auth_headers)
        assert r.status_code == 400

    def test_release_pdf_generates(self, client, auth_headers, seed_data):
        adm_id = self._admit_and_die(client, auth_headers, seed_data, "BR-PDF", mlc=False)
        # Non-MLC: defaults make NOC and PM not required, can release directly
        r = client.post(f"/api/inpatient/admissions/{adm_id}/body-release/release", json={
            "released_to_name": "Daughter", "released_to_relationship": "daughter",
            "released_to_id_proof_type": "voter", "released_to_id_proof_number": "VTR-1",
            "witness_name": "Friend",
        }, headers=auth_headers)
        assert r.status_code == 200, r.text
        pdf = client.get(f"/api/inpatient/admissions/{adm_id}/body-release/pdf", headers=auth_headers)
        assert pdf.status_code == 200
        assert pdf.headers["content-type"] == "application/pdf"
        assert pdf.content[:4] == b"%PDF"
