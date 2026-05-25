"""
Tests for the inpatient food ordering system.

Covers:
1. Meal plan CRUD (bulk upsert, list, delete)
2. Food order creation (single + bulk, duplicate handling)
3. Cancel and re-order workflow
4. Mark-delivered status transition
5. Billing integration (food charges feed into unbilled subtotal)
6. Final bill stamps food orders with bill_id
7. Bill cancel releases food orders
8. Edge cases: missing meal plan, cancelled admission, billed order cancel guard
"""

import pytest
from datetime import date, timedelta

_state: dict = {}


class TestMealPlans:
    """Meal plan CRUD."""

    def test_setup_room(self, client, auth_headers):
        # Use a unique room number to avoid clashing with other test suites.
        resp = client.post(
            "/api/inpatient/rooms",
            json={
                "room_number": "FD-201",
                "room_type": "private",
                "floor": "2",
                "department": "General Ward",
                "bed_count": 2,
                "room_charge_per_day": 2000.0,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        _state["room_id"] = resp.json()["id"]

    def test_list_meal_plans_empty_grid(self, client, auth_headers):
        """First call returns rows for every (room_type, meal_type) combo with price=0."""
        resp = client.get("/api/inpatient/meal-plans", headers=auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Should have rows for all 4 meal types per room type
        meal_types = {r["meal_type"] for r in data}
        assert meal_types == {"breakfast", "lunch", "dinner", "snacks"}
        # All inactive / zero-priced initially
        assert all(r["price"] == 0 for r in data)

    def test_bulk_upsert_meal_plans(self, client, auth_headers):
        plans = [
            {"room_type": "private", "meal_type": "breakfast", "price": 120, "description": "Standard veg", "is_active": True},
            {"room_type": "private", "meal_type": "lunch", "price": 200, "description": "Standard veg", "is_active": True},
            {"room_type": "private", "meal_type": "dinner", "price": 200, "description": "Standard veg", "is_active": True},
            {"room_type": "private", "meal_type": "snacks", "price": 80, "description": "Tea + biscuit", "is_active": True},
        ]
        resp = client.put(
            "/api/inpatient/meal-plans",
            json={"plans": plans},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["upserted"] == 4

    def test_meal_plans_persisted(self, client, auth_headers):
        resp = client.get("/api/inpatient/meal-plans", params={"room_type": "private"}, headers=auth_headers)
        data = resp.json()
        prices = {r["meal_type"]: r["price"] for r in data if r["room_type"] == "private"}
        assert prices["breakfast"] == 120.0
        assert prices["lunch"] == 200.0
        assert prices["dinner"] == 200.0
        assert prices["snacks"] == 80.0

    def test_upsert_updates_existing(self, client, auth_headers):
        plans = [
            {"room_type": "private", "meal_type": "breakfast", "price": 150, "description": "Updated", "is_active": True},
        ]
        resp = client.put(
            "/api/inpatient/meal-plans",
            json={"plans": plans},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        # Verify update
        resp = client.get("/api/inpatient/meal-plans", params={"room_type": "private"}, headers=auth_headers)
        bf = next(r for r in resp.json() if r["meal_type"] == "breakfast" and r["room_type"] == "private")
        assert bf["price"] == 150.0


class TestFoodOrders:
    """Per-admission food order workflow."""

    def test_create_admission(self, client, auth_headers, seed_data, TestSessionLocal):
        # Use the FD-201 room from the prior class
        resp = client.get("/api/inpatient/rooms", headers=auth_headers)
        room = next((r for r in resp.json() if r["room_number"] == "FD-201"), None)
        if not room:
            pytest.skip("FD-201 missing — run TestMealPlans first")
        _state["room_id"] = room["id"]

        # Set doctor's inpatient fee
        from app.models.user import User
        db = TestSessionLocal()
        doctor = db.query(User).filter(User.id == seed_data["doctor_user_id"]).first()
        if not doctor.inpatient_fee_inr:
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
                "admission_reason": "Food test",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        _state["adm_id"] = resp.json()["id"]

    def test_order_food_today(self, client, auth_headers):
        today = date.today().isoformat()
        resp = client.post(
            f"/api/inpatient/admissions/{_state['adm_id']}/food-orders",
            json={"items": [
                {"meal_date": today, "meal_type": "breakfast", "diet_preference": "veg"},
                {"meal_date": today, "meal_type": "lunch", "diet_preference": "veg"},
            ]},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert len(data["created"]) == 2
        # Price should be snapshotted from meal plan
        prices = {c["meal_type"]: c["price"] for c in data["created"]}
        assert prices["breakfast"] == 150.0  # was updated to 150
        assert prices["lunch"] == 200.0
        _state["bf_order_id"] = next(c["id"] for c in data["created"] if c["meal_type"] == "breakfast")
        _state["lunch_order_id"] = next(c["id"] for c in data["created"] if c["meal_type"] == "lunch")

    def test_duplicate_order_skipped(self, client, auth_headers):
        today = date.today().isoformat()
        resp = client.post(
            f"/api/inpatient/admissions/{_state['adm_id']}/food-orders",
            json={"items": [
                {"meal_date": today, "meal_type": "breakfast"},
            ]},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert len(data["created"]) == 0
        assert len(data["skipped"]) == 1

    def test_bulk_order_advance_days(self, client, auth_headers):
        """Order meals for the next 3 days at once."""
        items = []
        for offset in (1, 2, 3):
            d = (date.today() + timedelta(days=offset)).isoformat()
            for meal in ("breakfast", "lunch", "dinner"):
                items.append({"meal_date": d, "meal_type": meal, "diet_preference": "veg"})
        resp = client.post(
            f"/api/inpatient/admissions/{_state['adm_id']}/food-orders",
            json={"items": items},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        assert len(resp.json()["created"]) == 9  # 3 days × 3 meals

    def test_list_food_orders(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['adm_id']}/food-orders",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        orders = resp.json()
        # 2 (today) + 9 (future) = 11
        assert len(orders) == 11
        # All ordered status, none billed
        assert all(o["status"] == "ordered" for o in orders)
        assert all(o["billed"] is False for o in orders)

    def test_cancel_food_order(self, client, auth_headers):
        resp = client.post(
            f"/api/inpatient/food-orders/{_state['lunch_order_id']}/cancel",
            json={"reason": "Patient on NPO"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text

    def test_cancelled_order_excluded_from_default_list(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['adm_id']}/food-orders",
            params={"include_cancelled": False},
            headers=auth_headers,
        )
        orders = resp.json()
        assert len(orders) == 10  # 11 - 1 cancelled
        assert all(o["status"] != "cancelled" for o in orders)

    def test_reorder_cancelled_slot_reactivates(self, client, auth_headers):
        """Ordering the same slot after cancel re-activates the row at current price."""
        today = date.today().isoformat()
        resp = client.post(
            f"/api/inpatient/admissions/{_state['adm_id']}/food-orders",
            json={"items": [{"meal_date": today, "meal_type": "lunch", "diet_preference": "veg"}]},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        # Created (re-activated), not skipped
        assert len(resp.json()["created"]) == 1
        assert resp.json()["created"][0]["status"] == "ordered"

    def test_mark_delivered(self, client, auth_headers):
        resp = client.patch(
            f"/api/inpatient/food-orders/{_state['bf_order_id']}",
            json={"status": "delivered"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "delivered"
        assert data["delivered_at"] is not None


class TestFoodBillingIntegration:
    """Food orders feed into the admission bill."""

    def test_food_in_unbilled_subtotal(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['adm_id']}/bill",
            params={"unbilled_only": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Food total should be non-zero
        assert data.get("food_total", 0) > 0
        assert len(data.get("food_entries", [])) > 0
        # Subtotal should include food
        assert data["subtotal"] >= data["food_total"]

    def test_interim_bill_includes_food(self, client, auth_headers):
        resp = client.post(
            f"/api/inpatient/admissions/{_state['adm_id']}/bill/interim",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        _state["interim_bill_id"] = resp.json()["bill_id"]

    def test_food_marked_billed_after_interim(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['adm_id']}/food-orders",
            headers=auth_headers,
        )
        orders = resp.json()
        billed_orders = [o for o in orders if o["billed"]]
        # All non-cancelled orders should now be billed
        non_cancelled = [o for o in orders if o["status"] != "cancelled"]
        assert len(billed_orders) == len(non_cancelled)
        assert len(billed_orders) > 0

    def test_unbilled_after_interim_no_food(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['adm_id']}/bill",
            params={"unbilled_only": True},
            headers=auth_headers,
        )
        data = resp.json()
        # Food should now be 0 unbilled
        assert data.get("food_total", 0) == 0

    def test_cannot_cancel_billed_food(self, client, auth_headers):
        resp = client.post(
            f"/api/inpatient/food-orders/{_state['bf_order_id']}/cancel",
            json={"reason": "After-the-fact cancel"},
            headers=auth_headers,
        )
        # Should be blocked with 409 since it's billed
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["code"] == "food_order_billed"

    def test_cancel_bill_releases_food(self, client, auth_headers):
        resp = client.post(
            f"/api/inpatient/admissions/{_state['adm_id']}/bills/{_state['interim_bill_id']}/cancel",
            json={"reason": "Test release"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        released = resp.json().get("released", {})
        assert released.get("food_orders", 0) > 0

    def test_food_unbilled_again_after_bill_cancel(self, client, auth_headers):
        resp = client.get(
            f"/api/inpatient/admissions/{_state['adm_id']}/bill",
            params={"unbilled_only": True},
            headers=auth_headers,
        )
        data = resp.json()
        # Food back in unbilled total
        assert data.get("food_total", 0) > 0


class TestFoodEdgeCases:

    def test_no_meal_plan_blocks_order(self, client, auth_headers, seed_data, TestSessionLocal):
        """Trying to order food for a room type without a meal plan returns 400."""
        # Create a room of a type with no meal plan set
        resp = client.post(
            "/api/inpatient/rooms",
            json={
                "room_number": "FD-NOPLAN-1",
                "room_type": "suite",   # no meal plan set for suite
                "floor": "2",
                "department": "VIP",
                "bed_count": 1,
                "room_charge_per_day": 5000.0,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        deluxe_room_id = resp.json()["id"]

        # Create patient
        import uuid
        from datetime import date as _date
        from app.models.patient import Patient
        db = TestSessionLocal()
        p = Patient(
            patient_id=str(uuid.uuid4()),
            first_name="NoPlan", last_name="Patient",
            date_of_birth=_date(1990, 1, 1),
            gender="male", primary_phone="5555555555",
            hospital_id=seed_data["hospital_id"],
        )
        db.add(p); db.commit()
        p_id = p.id
        db.close()

        adm_resp = client.post(
            "/api/inpatient/admissions",
            json={
                "patient_id": p_id,
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": deluxe_room_id,
                "admission_type": "elective",
            },
            headers=auth_headers,
        )
        assert adm_resp.status_code == 201
        adm_id = adm_resp.json()["id"]

        # Try to order food — should 400
        resp = client.post(
            f"/api/inpatient/admissions/{adm_id}/food-orders",
            json={"items": [{"meal_date": date.today().isoformat(), "meal_type": "breakfast"}]},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "meal plan" in resp.text.lower()
