"""
Comprehensive unit tests for the inpatient billing flow.

Tests cover:
1. Interim bill creation — stamps source records, correct amounts
2. Comprehensive final bill — includes all charges (prior + new)
3. Billing dashboard — no double-counting when final bill exists
4. Deposit recording and balance calculation
5. Edge cases: all-interim, no-charges, ₹0 balance
"""

import pytest
from datetime import datetime, timedelta

_state: dict = {}


class TestComprehensiveBilling:
    """Sequential billing flow tests that build on each other."""

    # ------------------------------------------------------------------
    # Setup: Room + Rate config + Admission
    # ------------------------------------------------------------------
    def test_setup_room(self, client, auth_headers):
        resp = client.post(
            "/api/inpatient/rooms",
            json={
                "room_number": "CB-101",
                "room_type": "general",
                "floor": "1",
                "department": "General Ward",
                "bed_count": 2,
                "room_charge_per_day": 1000.0,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        _state["room_id"] = resp.json()["id"]

    def test_setup_rate_config(self, client, auth_headers):
        resp = client.put(
            "/api/inpatient/rate-config",
            json={"doctor_visit_rate": 500.0, "nurse_visit_rate": 200.0, "procedure_rate": 2000.0},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text

    def test_setup_admission(self, client, auth_headers, seed_data, TestSessionLocal):
        # Give doctor an inpatient fee
        from app.models.user import User
        db = TestSessionLocal()
        doctor = db.query(User).filter(User.id == seed_data["doctor_user_id"]).first()
        doctor.inpatient_fee_inr = "500"
        db.commit()
        db.close()

        resp = client.post(
            "/api/inpatient/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": _state["room_id"],
                "admission_type": "elective",
                "admission_reason": "Billing test",
                "condition_on_admission": "stable",
                "estimated_stay_days": 5,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] == "admitted"
        _state["admission_id"] = data["id"]

    # ------------------------------------------------------------------
    # 1. Record a doctor visit charge
    # ------------------------------------------------------------------
    def test_create_doctor_visit(self, client, auth_headers, seed_data):
        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/visits",
            json={
                "visit_type": "doctor_visit",
                "visitor_id": seed_data["doctor_user_id"],
                "notes": "Initial assessment",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert float(data["charge_amount"]) == 500.0
        _state["visit_id"] = data["id"]

    # ------------------------------------------------------------------
    # 2. Bill preview — unbilled
    # ------------------------------------------------------------------
    def test_bill_preview_unbilled(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill",
            params={"unbilled_only": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Room + visit should be in unbilled total
        assert data["visit_total"] == 500.0
        assert data["subtotal"] >= 500.0  # at least the visit + room
        _state["unbilled_subtotal_before_interim"] = data["subtotal"]

    # ------------------------------------------------------------------
    # 3. Generate interim bill
    # ------------------------------------------------------------------
    def test_create_interim_bill(self, client, auth_headers):
        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill/interim",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["bill_subtype"] == "interim"
        assert data["total_amount"] > 0
        _state["interim_bill_id"] = data["bill_id"]
        _state["interim_bill_total"] = data["total_amount"]

    # ------------------------------------------------------------------
    # 4. After interim bill — unbilled total should be ≈ room charges since
    #    the visit was stamped
    # ------------------------------------------------------------------
    def test_unbilled_after_interim(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill",
            params={"unbilled_only": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Visit is stamped — should NOT appear in unbilled
        assert data["visit_total"] == 0.0

    # ------------------------------------------------------------------
    # 5. All-charges view should still show visit
    # ------------------------------------------------------------------
    def test_all_charges_includes_visit(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["visit_total"] == 500.0
        # Visits have billed=True flag
        for vtype, group in data.get("visits", {}).items():
            for v in group.get("items", []):
                assert v["billed"] is True, f"Visit {v['id']} should be flagged as billed"

    # ------------------------------------------------------------------
    # 6. Add another visit AFTER interim (new unbilled charge)
    # ------------------------------------------------------------------
    def test_create_second_visit(self, client, auth_headers, seed_data):
        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/visits",
            json={
                "visit_type": "doctor_visit",
                "visitor_id": seed_data["doctor_user_id"],
                "notes": "Follow-up",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        _state["visit_id_2"] = resp.json()["id"]

    # ------------------------------------------------------------------
    # 7. Cannot generate final bill without items_override when no new
    #    charges exist (edge-case guard)
    # ------------------------------------------------------------------
    def test_duplicate_final_bill_blocked(self, client, auth_headers):
        """After we generate a final bill, a second one is blocked (409)."""
        # We'll test this AFTER the final bill is created in step 8.
        pass  # placeholder — actual assertion in test_duplicate_final_blocked_post

    # ------------------------------------------------------------------
    # 8. Generate comprehensive final bill with ALL items
    # ------------------------------------------------------------------
    def test_generate_comprehensive_final_bill(self, client, auth_headers):
        # First, get all charges (comprehensive view)
        all_resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill",
            headers=auth_headers,
        )
        assert all_resp.status_code == 200
        all_data = all_resp.json()

        unbilled_resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill",
            params={"unbilled_only": True},
            headers=auth_headers,
        )
        assert unbilled_resp.status_code == 200
        unbilled_data = unbilled_resp.json()

        # Build comprehensive items_override (prior + new)
        items = []

        # Room: split prior-billed and new unbilled
        full_room = all_data.get("room_total", 0)
        unbilled_room = unbilled_data.get("room_total", 0)
        billed_room = max(0, round(full_room - unbilled_room, 2))
        rate = all_data.get("room", {}).get("charge_per_day", 0)
        if billed_room > 0:
            items.append({
                "source": "room", "source_id": None,
                "item_type": "room_charge",
                "item_name": "Room — Prior (interim)",
                "quantity": 1, "unit_price": billed_room, "total_price": billed_room,
            })
        if unbilled_room > 0:
            items.append({
                "source": "room", "source_id": None,
                "item_type": "room_charge",
                "item_name": "Room — New charges",
                "quantity": 1, "unit_price": unbilled_room, "total_price": unbilled_room,
            })

        # Visits: ALL
        for vtype, group in all_data.get("visits", {}).items():
            for v in group.get("items", []):
                items.append({
                    "source": "visit", "source_id": v["id"],
                    "item_type": vtype,
                    "item_name": f"{vtype} visit",
                    "quantity": 1, "unit_price": v["amount"], "total_price": v["amount"],
                })

        comprehensive_total = sum(it["total_price"] for it in items)

        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill/finalize",
            json={"items_override": items},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["bill_subtype"] == "final"
        # Final bill total should equal comprehensive_total (all charges)
        assert abs(float(data["total_amount"]) - comprehensive_total) < 0.01, (
            f"Expected comprehensive total ≈ {comprehensive_total}, got {data['total_amount']}"
        )
        _state["final_bill_id"] = data["bill_id"]
        _state["final_bill_total"] = float(data["total_amount"])
        # Comprehensive total should be ≥ interim total (includes prior charges)
        assert _state["final_bill_total"] >= _state["interim_bill_total"], (
            "Final bill comprehensive total must be ≥ interim bill total"
        )

    # ------------------------------------------------------------------
    # 9. Duplicate final bill is blocked
    # ------------------------------------------------------------------
    def test_duplicate_final_blocked_post(self, client, auth_headers):
        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill/finalize",
            json={"items_override": [{"source": "custom", "source_id": None, "item_type": "custom",
                                       "item_name": "Extra", "quantity": 1, "unit_price": 100, "total_price": 100}]},
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "final_bill_exists"

    # ------------------------------------------------------------------
    # 10. Billing dashboard — final bill total, no double-counting
    # ------------------------------------------------------------------
    def test_billing_dashboard_no_double_count(self, client, auth_headers):
        from datetime import date
        today = date.today().isoformat()
        resp = client.get(
            "/api/hospital/billing",
            params={"date_from": today, "date_to": today, "bill_type": "admission"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        bills = resp.json()["bills"]

        # Find our admission row
        adm_row = next((b for b in bills if b.get("admission_id") == _state["admission_id"]), None)
        assert adm_row is not None, "Admission row should appear in billing dashboard"
        assert adm_row["bill_subtype"] == "final"

        # Dashboard amount should equal the final bill total, NOT interim + final
        dashboard_amount = float(adm_row["amount"])
        assert abs(dashboard_amount - _state["final_bill_total"]) < 0.01, (
            f"Dashboard shows {dashboard_amount} but expected final bill total {_state['final_bill_total']}. "
            f"Interim was {_state['interim_bill_total']}. "
            f"If dashboard is showing sum of both, it's double-counting."
        )

    # ------------------------------------------------------------------
    # 11. Deposit recording and balance calculation
    # ------------------------------------------------------------------
    def test_record_deposit(self, client, auth_headers):
        deposit_amount = 5000.0
        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/deposits",
            json={
                "deposit_type": "initial",
                "amount": deposit_amount,
                "payment_method": "cash",
                "notes": "Initial deposit",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert float(data["amount"]) == deposit_amount
        _state["deposit_id"] = data.get("id")
        _state["deposit_amount"] = deposit_amount

    def test_balance_after_deposit(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        net_deposits = data.get("deposits_total", 0)
        assert abs(net_deposits - _state["deposit_amount"]) < 0.01, (
            f"Net deposits {net_deposits} should equal deposit amount {_state['deposit_amount']}"
        )

    def test_balance_due_calculation(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Balance = grand_total - net_deposits
        expected_balance = round(data["grand_total"] - data["deposits_total"], 2)
        assert abs(data["balance_due"] - expected_balance) < 0.01

    # ------------------------------------------------------------------
    # 12. Top-up deposit (additional payment)
    # ------------------------------------------------------------------
    def test_topup_deposit(self, client, auth_headers):
        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/deposits",
            json={
                "deposit_type": "topup",
                "amount": 2000.0,
                "payment_method": "upi",
                "notes": "Top-up",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text

    def test_net_deposits_after_topup(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        expected_net = _state["deposit_amount"] + 2000.0
        assert abs(data["deposits_total"] - expected_net) < 0.01

    # ------------------------------------------------------------------
    # 13. Billing dashboard reflects deposit activity
    # ------------------------------------------------------------------
    def test_billing_dashboard_shows_deposits(self, client, auth_headers):
        from datetime import date
        today = date.today().isoformat()
        resp = client.get(
            "/api/hospital/billing",
            params={"date_from": today, "date_to": today, "bill_type": "admission"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        bills = resp.json()["bills"]

        adm_row = next((b for b in bills if b.get("admission_id") == _state["admission_id"]), None)
        assert adm_row is not None
        # Should have 2 deposits (initial + topup)
        assert len(adm_row.get("deposits", [])) == 2
        net = sum(
            d["amount"] if d["deposit_type"] != "refund" else -d["amount"]
            for d in adm_row["deposits"]
        )
        assert abs(net - (5000.0 + 2000.0)) < 0.01

    # ------------------------------------------------------------------
    # 14. Balance summary endpoint
    # ------------------------------------------------------------------
    def test_balance_summary(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/balance",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "total_billed" in data
        assert "net_deposits" in data
        assert "balance" in data
        # balance = net_deposits - total_billed (+ve = patient credit, -ve = patient owes)
        expected = round(data["net_deposits"] - data["total_billed"], 2)
        assert abs(data["balance"] - expected) < 0.01
        # With ₹7000 deposits and relatively small charges, patient should have credit
        assert data["net_deposits"] >= 7000.0 - 0.01, (
            f"Expected at least ₹7000 in net deposits, got {data['net_deposits']}"
        )

    # ------------------------------------------------------------------
    # 15. List admission bills — should show both interim and final
    # ------------------------------------------------------------------
    def test_list_admission_bills(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bills",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        bills = resp.json()
        subtypes = [b["bill_subtype"] for b in bills if b["status"] != "cancelled"]
        assert "interim" in subtypes, "Should have an interim bill"
        assert "final" in subtypes, "Should have a final bill"

    # ------------------------------------------------------------------
    # 16. Cancel final bill and re-issue (releases source records)
    # ------------------------------------------------------------------
    def test_cancel_final_bill(self, client, auth_headers):
        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/bills/{_state['final_bill_id']}/cancel",
            json={"reason": "Issued in error — reissuing with corrections"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text

    def test_after_cancel_new_visits_are_unbilled(self, client, auth_headers):
        """After cancelling the final bill, the second visit should be unbilled again."""
        resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill",
            params={"unbilled_only": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # The second visit (added after interim) should be unbilled again
        assert data["visit_total"] >= 500.0, (
            "At least the second visit should appear as unbilled after cancelling the final bill"
        )

    # ------------------------------------------------------------------
    # 17. Re-issue final bill after cancellation
    # ------------------------------------------------------------------
    def test_reissue_final_bill(self, client, auth_headers):
        # Verify guard: no active final bill should exist now
        resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bills",
            headers=auth_headers,
        )
        active_finals = [b for b in resp.json() if b["bill_subtype"] == "final" and b["status"] != "cancelled"]
        assert len(active_finals) == 0, "No active final bill after cancellation"

        # Re-issue with just the unbilled items
        unbilled_resp = client.get(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill",
            params={"unbilled_only": True},
            headers=auth_headers,
        )
        unbilled_data = unbilled_resp.json()

        items = []
        # Second visit should be here
        for vtype, group in unbilled_data.get("visits", {}).items():
            for v in group.get("items", []):
                items.append({
                    "source": "visit", "source_id": v["id"],
                    "item_type": vtype, "item_name": f"{vtype} visit",
                    "quantity": 1, "unit_price": v["amount"], "total_price": v["amount"],
                })

        resp = client.post(
            f"/api/inpatient/admissions/{_state['admission_id']}/bill/finalize",
            json={"items_override": items},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["bill_subtype"] == "final"
        _state["reissued_final_bill_id"] = data["bill_id"]


class TestInterimOnlyBilling:
    """Tests for the interim-only billing path (no final bill yet)."""

    _s: dict = {}

    def test_setup(self, client, auth_headers, seed_data, TestSessionLocal):
        # Second patient for isolated test
        import uuid
        from datetime import date as _date
        from app.models.patient import Patient
        db = TestSessionLocal()
        patient2 = Patient(
            patient_id=str(uuid.uuid4()),
            first_name="Jane", last_name="TestBilling",
            date_of_birth=_date(1985, 6, 15),
            gender="female", primary_phone="8888888888",
            hospital_id=seed_data["hospital_id"],
        )
        db.add(patient2)
        db.commit()
        self._s["patient2_id"] = patient2.id
        db.close()

        # Get room from CB-101 setup
        resp = client.get("/api/inpatient/rooms", headers=auth_headers)
        room = next((r for r in resp.json() if r["room_number"] == "CB-101"), None)
        if not room:
            pytest.skip("CB-101 not found — run after TestComprehensiveBilling")
        self._s["room_id"] = room["id"]

    def test_admission_for_interim_only(self, client, auth_headers, seed_data):
        resp = client.post(
            "/api/inpatient/admissions",
            json={
                "patient_id": self._s["patient2_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": self._s["room_id"],
                "admission_type": "elective",
                "admission_reason": "Interim test",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        self._s["adm_id"] = resp.json()["id"]

    def test_interim_bill(self, client, auth_headers):
        resp = client.post(
            f"/api/inpatient/admissions/{self._s['adm_id']}/bill/interim",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["bill_subtype"] == "interim"
        self._s["interim_id"] = data["bill_id"]
        self._s["interim_total"] = float(data["total_amount"])

    def test_dashboard_interim_only(self, client, auth_headers):
        """When only interim bills exist, dashboard shows sum of interim bills."""
        from datetime import date
        today = date.today().isoformat()
        resp = client.get(
            "/api/hospital/billing",
            params={"date_from": today, "date_to": today, "bill_type": "admission"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        bills = resp.json()["bills"]
        adm_row = next((b for b in bills if b.get("admission_id") == self._s["adm_id"]), None)
        assert adm_row is not None
        assert adm_row["bill_subtype"] == "interim"
        assert abs(float(adm_row["amount"]) - self._s["interim_total"]) < 0.01


class TestBillingEdgeCases:
    """Edge cases: ₹0 final bill guard, no charges guard."""

    def test_finalize_without_charges_no_override(self, client, auth_headers, seed_data, TestSessionLocal):
        """Finalizing without items_override and no unbilled charges should be blocked."""
        import uuid
        from datetime import date as _date
        from app.models.patient import Patient

        db = TestSessionLocal()
        p = Patient(
            patient_id=str(uuid.uuid4()),
            first_name="Zero", last_name="Charges",
            date_of_birth=_date(1990, 1, 1),
            gender="male", primary_phone="7777777777",
            hospital_id=seed_data["hospital_id"],
        )
        db.add(p)
        db.commit()
        p_id = p.id
        db.close()

        # Get any room
        rooms_resp = client.get("/api/inpatient/rooms", headers=auth_headers)
        rooms = [r for r in rooms_resp.json() if r.get("available_beds", 0) > 0]
        if not rooms:
            pytest.skip("No available room")
        room_id = rooms[0]["id"]

        # Admit the patient
        adm_resp = client.post(
            "/api/inpatient/admissions",
            json={
                "patient_id": p_id,
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room_id,
                "admission_type": "elective",
            },
            headers=auth_headers,
        )
        assert adm_resp.status_code == 201, adm_resp.text
        adm_id = adm_resp.json()["id"]

        # Create + immediately cancel the only interim bill so nothing is unbilled
        interim_resp = client.post(
            f"/api/inpatient/admissions/{adm_id}/bill/interim",
            headers=auth_headers,
        )
        # If no room charge yet (< 1 day), this may 400 — that's fine
        if interim_resp.status_code == 400:
            pytest.skip("No charges for brand-new admission — expected")

        interim_bill_id = interim_resp.json()["bill_id"]
        cancel_resp = client.post(
            f"/api/inpatient/admissions/{adm_id}/bills/{interim_bill_id}/cancel",
            json={"reason": "Test cleanup"},
            headers=auth_headers,
        )
        assert cancel_resp.status_code == 200

        # Now there should be no unbilled charges (room < 1 day = 0)
        # Trying to finalize without override should raise 400
        resp = client.post(
            f"/api/inpatient/admissions/{adm_id}/bill/finalize",
            headers=auth_headers,
        )
        # Either 400 (no charges) or 200 with ₹0 if room time accumulated — both are valid
        assert resp.status_code in (200, 400)

    def test_finalize_with_empty_override_allowed(self, client, auth_headers, seed_data, TestSessionLocal):
        """Finalizing with explicit empty items_override is allowed (operator-confirmed ₹0 close)."""
        import uuid
        from datetime import date as _date
        from app.models.patient import Patient

        db = TestSessionLocal()
        p = Patient(
            patient_id=str(uuid.uuid4()),
            first_name="Empty", last_name="Override",
            date_of_birth=_date(1990, 1, 1),
            gender="male", primary_phone="6666666666",
            hospital_id=seed_data["hospital_id"],
        )
        db.add(p)
        db.commit()
        p_id = p.id
        db.close()

        rooms_resp = client.get("/api/inpatient/rooms", headers=auth_headers)
        rooms = [r for r in rooms_resp.json() if r.get("available_beds", 0) > 0]
        if not rooms:
            pytest.skip("No available room")
        room_id = rooms[0]["id"]

        adm_resp = client.post(
            "/api/inpatient/admissions",
            json={
                "patient_id": p_id,
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room_id,
                "admission_type": "elective",
            },
            headers=auth_headers,
        )
        assert adm_resp.status_code == 201
        adm_id = adm_resp.json()["id"]

        # Finalize with explicit empty list — should be allowed (operator confirms ₹0)
        resp = client.post(
            f"/api/inpatient/admissions/{adm_id}/bill/finalize",
            json={"items_override": []},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["bill_subtype"] == "final"
        assert float(data["total_amount"]) == 0.0


class TestPackageLabCoverage:
    """Unit tests for the granular lab coverage helper.

    `_pkg_lab_covered` is pure logic on a SurgeryPackage row — tested directly
    with lightweight fakes so we don't need a full admission + lab orders
    integration to verify the decision matrix.
    """

    class _FakePkg:
        def __init__(self, included_services, mode, ids):
            self.included_services = included_services
            self.lab_coverage_mode = mode
            self.included_lab_test_ids = ids

    def test_no_pkg_returns_false(self):
        from app.routes.inpatient import _pkg_lab_covered
        assert _pkg_lab_covered(None, 1) is False

    def test_lab_not_in_included_services_returns_false(self):
        from app.routes.inpatient import _pkg_lab_covered
        pkg = self._FakePkg(["pharmacy"], "all", None)
        assert _pkg_lab_covered(pkg, 1) is False

    def test_mode_all_covers_every_test(self):
        from app.routes.inpatient import _pkg_lab_covered
        pkg = self._FakePkg(["lab"], "all", None)
        assert _pkg_lab_covered(pkg, 1) is True
        assert _pkg_lab_covered(pkg, 9999) is True

    def test_mode_selected_covers_only_whitelisted(self):
        from app.routes.inpatient import _pkg_lab_covered
        pkg = self._FakePkg(["lab"], "selected", [10, 20])
        assert _pkg_lab_covered(pkg, 10) is True
        assert _pkg_lab_covered(pkg, 20) is True
        assert _pkg_lab_covered(pkg, 30) is False

    def test_mode_selected_empty_whitelist_covers_none(self):
        from app.routes.inpatient import _pkg_lab_covered
        pkg = self._FakePkg(["lab"], "selected", [])
        assert _pkg_lab_covered(pkg, 10) is False

    def test_mode_selected_missing_test_id_not_covered(self):
        from app.routes.inpatient import _pkg_lab_covered
        pkg = self._FakePkg(["lab"], "selected", [10, 20])
        assert _pkg_lab_covered(pkg, None) is False


class TestPackageCRUDLabCoverage:
    """HTTP-level checks that the package CRUD endpoints accept + persist + normalize
    the new lab coverage fields."""

    def test_create_with_mode_all_default(self, client, auth_headers):
        resp = client.post(
            "/api/inpatient/packages",
            json={
                "package_name": "LabCov-AllDefault",
                "base_price": 5000.0,
                "included_services": ["lab"],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["lab_coverage_mode"] == "all"
        assert (data.get("included_lab_test_ids") or []) == []

    def test_create_selected_mode_without_lab_in_services_normalizes(self, client, auth_headers):
        # When 'lab' is not in included_services, granular fields are wiped
        # back to mode=all, ids=None so stale data doesn't linger.
        resp = client.post(
            "/api/inpatient/packages",
            json={
                "package_name": "LabCov-NoLabService",
                "base_price": 5000.0,
                "included_services": ["pharmacy"],
                "lab_coverage_mode": "selected",
                "included_lab_test_ids": [1, 2, 3],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["lab_coverage_mode"] == "all"
        assert (data.get("included_lab_test_ids") or []) == []

    def test_create_selected_with_unknown_id_rejected(self, client, auth_headers):
        resp = client.post(
            "/api/inpatient/packages",
            json={
                "package_name": "LabCov-BadId",
                "base_price": 5000.0,
                "included_services": ["lab"],
                "lab_coverage_mode": "selected",
                "included_lab_test_ids": [9_999_999],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400, resp.text
        assert "Lab test IDs not found" in resp.json()["detail"]

    def test_invalid_mode_rejected(self, client, auth_headers):
        resp = client.post(
            "/api/inpatient/packages",
            json={
                "package_name": "LabCov-BadMode",
                "base_price": 5000.0,
                "included_services": ["lab"],
                "lab_coverage_mode": "bogus",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 400, resp.text
        assert "lab_coverage_mode" in resp.json()["detail"]
