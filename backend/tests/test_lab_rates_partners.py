"""Rate cards and third-party lab orders."""
import uuid

from app.models.lab import LabPartner, LabTest, LabTestCategory, LabTestRate, PatientLabOrder


def _category(db_session, hospital_id):
    category = LabTestCategory(name=f"Rates {uuid.uuid4().hex[:6]}", hospital_id=hospital_id)
    db_session.add(category)
    db_session.commit()
    return category


def test_rate_cards_and_booking_snapshot(client, auth_headers, db_session, seed_data):
    cards = client.get("/api/lab/rate-cards", headers=auth_headers)
    assert cards.status_code == 200, cards.text
    by_code = {c["code"]: c for c in cards.json()}
    assert set(by_code) == {"A", "B"}
    rate_b = by_code["B"]["id"]

    category = _category(db_session, seed_data["hospital_id"])
    created = client.post("/api/lab/tests", headers=auth_headers, json={
        "test_code": f"RT{uuid.uuid4().hex[:6].upper()}",
        "name": "Dual rate test",
        "category_id": category.id,
        "cost": 100,
        "rate_b": 70,
    })
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["cost"] == 100
    amounts = {r["code"]: r["amount"] for r in body["rates"]}
    assert amounts["A"] == 100
    assert amounts["B"] == 70

    booked = client.post("/api/lab/orders", headers=auth_headers, json={
        "patient_id": seed_data["patient_id"],
        "test_ids": [body["id"]],
        "rate_card_id": rate_b,
    })
    assert booked.status_code == 200, booked.text
    order = booked.json()[0]
    assert order["amount"] == 70
    assert order["rate_code"] == "B"
    assert order["bill_to"] == "patient"
    assert order["fulfillment"] == "in_house"

    stored = db_session.query(PatientLabOrder).filter_by(id=order["id"]).first()
    db_session.refresh(stored)
    assert stored.amount == 70


def test_receive_in_is_not_a_patient_bill(client, auth_headers, db_session, seed_data):
    category = _category(db_session, seed_data["hospital_id"])
    code = f"RI{uuid.uuid4().hex[:6].upper()}"
    created = client.post("/api/lab/tests", headers=auth_headers, json={
        "test_code": code,
        "name": "Receive in test",
        "category_id": category.id,
        "cost": 200,
        "rate_b": 120,
    })
    assert created.status_code == 200, created.text
    test_id = created.json()["id"]

    partner = client.post("/api/lab/partners", headers=auth_headers, json={
        "name": f"City Lab {uuid.uuid4().hex[:4]}",
        "partner_role": "receive_in",
    })
    assert partner.status_code == 200, partner.text

    received = client.post("/api/lab/orders/receive-in", headers=auth_headers, json={
        "partner_id": partner.json()["id"],
        "patient_id": seed_data["patient_id"],
        "test_ids": [test_id],
        "partner_reference": "EXT-1",
    })
    assert received.status_code == 200, received.text
    order = received.json()[0]
    assert order["fulfillment"] == "receive_in"
    assert order["bill_to"] == "partner"
    assert order["amount"] == 200
    assert order["status"] == "collected"
    assert order["partner_reference"] == "EXT-1"

    pending = client.get(
        f"/api/lab/orders/patient/{seed_data['patient_id']}/pending-payment",
        headers=auth_headers,
    )
    assert pending.status_code == 200
    assert all(row["id"] != order["id"] for row in pending.json())

    pay = client.put(
        f"/api/lab/orders/{order['id']}/payment",
        headers=auth_headers,
        json={"payment_method": "cash"},
    )
    assert pay.status_code == 400

    open_receivables = client.get(
        "/api/lab/partner-orders",
        headers=auth_headers,
        params={"fulfillment": "receive_in", "settlement": "unsettled"},
    )
    assert open_receivables.status_code == 200
    assert any(row["id"] == order["id"] for row in open_receivables.json())

    settled = client.post("/api/lab/partner-orders/settle", headers=auth_headers, json={
        "order_ids": [order["id"]],
        "invoice_ref": "INV-9",
    })
    assert settled.status_code == 200, settled.text
    stored = db_session.query(PatientLabOrder).filter_by(id=order["id"]).first()
    db_session.refresh(stored)
    assert stored.partner_settlement_status == "settled"
    assert stored.payment_status == "partner_settled"
    assert stored.partner_invoice_ref == "INV-9"
    assert db_session.query(LabTestRate).filter_by(test_id=test_id).count() == 2
    assert db_session.query(LabPartner).filter_by(id=partner.json()["id"]).first() is not None
    assert db_session.query(LabTest).filter_by(id=test_id).first().cost == 200
