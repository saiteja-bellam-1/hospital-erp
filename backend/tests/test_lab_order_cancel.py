"""Reception cancellation of uncollected outpatient lab orders."""

import uuid

from app.models.lab import LabTest, LabTestCategory, PatientLabOrder
from app.models.user import User, UserRole
from app.utils.auth import create_access_token, get_password_hash


def _reception_headers(db_session, seed_data):
    role = db_session.query(UserRole).filter_by(name="receptionist").first()
    if role is None:
        role = UserRole(name="receptionist", is_system_role=True)
        db_session.add(role)
        db_session.flush()

    user = db_session.query(User).filter_by(username="labcancelreception").first()
    if user is None:
        user = User(
            username="labcancelreception",
            password_hash=get_password_hash("reception123"),
            email="labcancelreception@test.com",
            first_name="Reception",
            last_name="Desk",
            role_id=role.id,
            hospital_id=seed_data["hospital_id"],
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()

    token = create_access_token(data={"sub": user.username})
    return {"Authorization": f"Bearer {token}"}, user


def _make_order(db_session, seed_data, *, status="ordered", payment_status="pending"):
    suffix = uuid.uuid4().hex[:8]
    category = db_session.query(LabTestCategory).filter_by(
        hospital_id=seed_data["hospital_id"]
    ).first()
    if category is None:
        category = LabTestCategory(
            name=f"Cancellation tests {suffix}",
            hospital_id=seed_data["hospital_id"],
        )
        db_session.add(category)
        db_session.flush()

    test = LabTest(
        name=f"Cancellation test {suffix}",
        test_code=f"CAN{suffix}",
        category_id=category.id,
        cost=250.0,
        hospital_id=seed_data["hospital_id"],
        is_active=True,
    )
    db_session.add(test)
    db_session.flush()

    order = PatientLabOrder(
        order_number=f"LAB-CAN-{suffix}",
        patient_id=seed_data["patient_id"],
        test_id=test.id,
        doctor_id=seed_data["doctor_user_id"],
        status=status,
        payment_status=payment_status,
        amount=250.0,
        priority="normal",
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def test_reception_cancels_order_and_doctor_sees_status(
    client, db_session, seed_data
):
    headers, receptionist = _reception_headers(db_session, seed_data)
    order = _make_order(db_session, seed_data)

    response = client.post(
        f"/api/lab/orders/{order.id}/cancel",
        headers=headers,
        json={"reason": "Patient declined the test"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["payment_status"] == "cancelled"
    assert body["cancelled_reason"] == "Patient declined the test"
    assert body["cancelled_by_name"] == "Reception Desk"
    assert body["cancelled_at"] is not None

    db_session.refresh(order)
    assert order.cancelled_by == receptionist.id

    doctor_token = create_access_token(data={"sub": "testdoctor"})
    doctor_response = client.get(
        "/api/lab/orders",
        headers={"Authorization": f"Bearer {doctor_token}"},
    )
    assert doctor_response.status_code == 200, doctor_response.text
    matching = [item for item in doctor_response.json() if item["id"] == order.id]
    assert len(matching) == 1
    assert matching[0]["status"] == "cancelled"
    assert matching[0]["cancelled_reason"] == "Patient declined the test"


def test_reception_cannot_cancel_collected_order(client, db_session, seed_data):
    headers, _ = _reception_headers(db_session, seed_data)
    order = _make_order(
        db_session,
        seed_data,
        status="collected",
        payment_status="paid",
    )

    response = client.post(
        f"/api/lab/orders/{order.id}/cancel",
        headers=headers,
        json={"reason": "Patient request"},
    )

    assert response.status_code == 400
    assert "Only orders that have not been sample-collected" in response.json()["detail"]
    db_session.refresh(order)
    assert order.status == "collected"


def test_doctor_cannot_use_reception_cancel_endpoint(client, db_session, seed_data):
    order = _make_order(db_session, seed_data)
    doctor_token = create_access_token(data={"sub": "testdoctor"})

    response = client.post(
        f"/api/lab/orders/{order.id}/cancel",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"reason": "Not permitted"},
    )

    assert response.status_code == 403
    db_session.refresh(order)
    assert order.status == "ordered"
