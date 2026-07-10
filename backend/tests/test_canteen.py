"""Canteen catalog + IP order + billing smoke tests."""

import pytest
from datetime import date


_state: dict = {}


class TestCanteenCatalog:
    def test_create_category_and_item(self, client, auth_headers):
        cat = client.post(
            "/api/canteen/categories",
            headers=auth_headers,
            json={"name": "Breakfast", "sort_order": 1},
        )
        assert cat.status_code == 201, cat.text
        _state["category_id"] = cat.json()["id"]

        item = client.post(
            "/api/canteen/items",
            headers=auth_headers,
            json={
                "name": "Idli Plate",
                "category_id": _state["category_id"],
                "price": 40.0,
                "is_veg": True,
                "is_active": True,
            },
        )
        assert item.status_code == 201, item.text
        _state["item_id"] = item.json()["id"]
        assert float(item.json()["price"]) == 40.0

        listed = client.get(
            "/api/canteen/items",
            headers=auth_headers,
            params={"active_only": True},
        )
        assert listed.status_code == 200
        assert any(i["name"] == "Idli Plate" for i in listed.json())


class TestCanteenOrders:
    def test_setup_room_and_admission(self, client, auth_headers, seed_data):
        room = client.post(
            "/api/inpatient/rooms",
            json={
                "room_number": "CN-101",
                "room_type": "general",
                "floor": "1",
                "department": "General Ward",
                "bed_count": 2,
                "room_charge_per_day": 1000.0,
            },
            headers=auth_headers,
        )
        assert room.status_code == 201, room.text
        room_id = room.json()["id"]

        adm = client.post(
            "/api/inpatient/admissions",
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room_id,
                "admission_type": "elective",
                "admission_reason": "Canteen test",
                "condition_on_admission": "stable",
            },
            headers=auth_headers,
        )
        assert adm.status_code == 201, adm.text
        _state["admission_id"] = adm.json()["id"]

    def test_place_order_and_bill_preview(self, client, auth_headers):
        item_id = _state.get("item_id")
        admission_id = _state.get("admission_id")
        if not item_id or not admission_id:
            pytest.skip("catalog/admission setup missing")

        order = client.post(
            "/api/canteen/orders",
            headers=auth_headers,
            json={
                "admission_id": admission_id,
                "notes": "soft diet",
                "items": [{"item_id": item_id, "quantity": 2}],
            },
        )
        assert order.status_code == 201, order.text
        body = order.json()
        _state["order_id"] = body["id"]
        assert body["status"] == "pending"
        assert float(body["total"]) == 80.0

        bill = client.get(
            f"/api/inpatient/admissions/{admission_id}/bill",
            headers=auth_headers,
            params={"unbilled_only": True},
        )
        assert bill.status_code == 200, bill.text
        data = bill.json()
        assert float(data.get("food_total") or 0) >= 80.0
        entries = data.get("food_entries") or []
        assert any(
            e.get("source") == "canteen" and e.get("item_name") == "Idli Plate"
            for e in entries
        )

    def test_status_and_cancel(self, client, auth_headers):
        order_id = _state.get("order_id")
        admission_id = _state.get("admission_id")
        if not order_id:
            pytest.skip("order missing")

        prep = client.patch(
            f"/api/canteen/orders/{order_id}/status",
            headers=auth_headers,
            json={"status": "preparing"},
        )
        assert prep.status_code == 200, prep.text
        assert prep.json()["status"] == "preparing"

        cancel = client.post(
            f"/api/canteen/orders/{order_id}/cancel",
            headers=auth_headers,
            json={"reason": "patient refused"},
        )
        assert cancel.status_code == 200, cancel.text
        assert cancel.json()["status"] == "cancelled"

        bill2 = client.get(
            f"/api/inpatient/admissions/{admission_id}/bill",
            headers=auth_headers,
            params={"unbilled_only": True},
        )
        entries2 = bill2.json().get("food_entries") or []
        assert not any(e.get("order_id") == order_id for e in entries2)

    def test_cannot_cancel_delivered(self, client, auth_headers):
        item_id = _state.get("item_id")
        admission_id = _state.get("admission_id")
        if not item_id or not admission_id:
            pytest.skip("setup missing")

        order = client.post(
            "/api/canteen/orders",
            headers=auth_headers,
            json={
                "admission_id": admission_id,
                "items": [{"item_id": item_id, "quantity": 1}],
            },
        )
        assert order.status_code == 201, order.text
        oid = order.json()["id"]

        for st in ("preparing", "ready", "delivered"):
            r = client.patch(
                f"/api/canteen/orders/{oid}/status",
                headers=auth_headers,
                json={"status": st},
            )
            assert r.status_code == 200, r.text

        cancel = client.post(
            f"/api/canteen/orders/{oid}/cancel",
            headers=auth_headers,
            json={"reason": "too late"},
        )
        assert cancel.status_code == 400


class TestCanteenPOS:
    def test_create_sale_and_receipt(self, client, auth_headers):
        item_id = _state.get("item_id")
        if not item_id:
            # Ensure catalog item exists
            item = client.post(
                "/api/canteen/items",
                headers=auth_headers,
                json={"name": "Tea POS", "price": 15.0, "is_veg": True},
            )
            assert item.status_code == 201, item.text
            item_id = item.json()["id"]
            _state["item_id"] = item_id

        sale = client.post(
            "/api/canteen/sales",
            headers=auth_headers,
            json={
                "payment_type": "cash",
                "customer_name": "Walk-in Guest",
                "discount_amount": 5,
                "items": [{"item_id": item_id, "quantity": 2}],
            },
        )
        assert sale.status_code == 201, sale.text
        body = sale.json()
        _state["sale_id"] = body["id"]
        assert body["sale_number"].startswith("CNT-")
        assert body["status"] == "completed"
        assert float(body["subtotal"]) > 0
        assert float(body["grand_total"]) == float(body["subtotal"]) - 5

        pdf = client.get(
            f"/api/canteen/sales/{body['id']}/receipt/pdf",
            headers=auth_headers,
        )
        assert pdf.status_code == 200, pdf.text
        assert pdf.headers.get("content-type", "").startswith("application/pdf")
        assert pdf.content[:4] == b"%PDF"

    def test_void_sale(self, client, auth_headers):
        sale_id = _state.get("sale_id")
        if not sale_id:
            pytest.skip("sale missing")
        void = client.post(
            f"/api/canteen/sales/{sale_id}/void",
            headers=auth_headers,
            json={"reason": "test void"},
        )
        assert void.status_code == 200, void.text
        assert void.json()["status"] == "voided"

        again = client.post(
            f"/api/canteen/sales/{sale_id}/void",
            headers=auth_headers,
            json={"reason": "again"},
        )
        assert again.status_code == 400
