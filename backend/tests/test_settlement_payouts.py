import uuid
from datetime import datetime

from app.models.billing import Bill, BillItem


def _seed_final_bill(db_session, seed_data, *, bill_date, lab=250, pharmacy=300, food=150, room=300):
    suffix = uuid.uuid4().hex[:8]
    bill = Bill(
        bill_number=f"TEST-PAYOUT-{suffix}",
        patient_id=seed_data["patient_id"],
        bill_type="admission",
        bill_subtype="final",
        reference_id=555001,
        subtotal=lab + pharmacy + food + room,
        total_amount=lab + pharmacy + food + room,
        status="paid",
        bill_date=bill_date,
        created_by_id=seed_data["admin_user_id"],
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(bill)
    db_session.flush()
    db_session.add_all([
        BillItem(bill_id=bill.id, item_type="lab_test", item_name="CBC", quantity=1, unit_price=lab, total_price=lab),
        BillItem(bill_id=bill.id, item_type="pharmacy", item_name="Meds", quantity=1, unit_price=pharmacy, total_price=pharmacy),
        BillItem(bill_id=bill.id, item_type="food", item_name="Meal", quantity=1, unit_price=food, total_price=food),
        BillItem(bill_id=bill.id, item_type="room_charge", item_name="Room", quantity=1, unit_price=room, total_price=room),
    ])
    db_session.commit()
    return bill


def test_settlement_config_and_summary_preview(client, auth_headers, seed_data, db_session):
    _seed_final_bill(db_session, seed_data, bill_date=datetime(2002, 3, 10, 12, 0, 0))

    # Configure lab payout at 60%.
    resp = client.put("/api/hospital/settlement-config", json={"lab": 60}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"]["lab"] == 60

    summary = client.get(
        "/api/hospital/inpatient-settlements-summary?from=2002-03-10&to=2002-03-10",
        headers=auth_headers,
    ).json()
    lab_unit = next(u for u in summary["units"] if u["unit"] == "lab")
    assert lab_unit["gross_amount"] == 250.0
    assert lab_unit["payout_percentage"] == 60
    assert lab_unit["payout_amount"] == 150.0
    assert lab_unit["hospital_share"] == 100.0


def test_record_settlement_and_overlap_guard(client, auth_headers, seed_data, db_session):
    _seed_final_bill(db_session, seed_data, bill_date=datetime(2002, 4, 5, 12, 0, 0))
    client.put("/api/hospital/settlement-config", json={"pharmacy": 100}, headers=auth_headers)

    created = client.post(
        "/api/hospital/settlements",
        json={"unit": "pharmacy", "from": "2002-04-01", "to": "2002-04-30"},
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["unit"] == "pharmacy"
    assert body["gross_amount"] == 300.0
    assert body["payout_amount"] == 300.0
    assert body["status"] == "paid"
    settlement_id = body["id"]

    # Overlapping period for the same unit is rejected.
    overlap = client.post(
        "/api/hospital/settlements",
        json={"unit": "pharmacy", "from": "2002-04-15", "to": "2002-05-15"},
        headers=auth_headers,
    )
    assert overlap.status_code == 409

    # A different unit for the same period is allowed.
    other = client.post(
        "/api/hospital/settlements",
        json={"unit": "lab", "from": "2002-04-01", "to": "2002-04-30"},
        headers=auth_headers,
    )
    assert other.status_code == 200, other.text

    # PDF statement is served.
    pdf = client.get(f"/api/hospital/settlements/{settlement_id}/pdf", headers=auth_headers)
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"

    # Cancel frees the period to be settled again.
    cancelled = client.post(
        f"/api/hospital/settlements/{settlement_id}/cancel",
        json={"reason": "mistake"},
        headers=auth_headers,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    resettle = client.post(
        "/api/hospital/settlements",
        json={"unit": "pharmacy", "from": "2002-04-01", "to": "2002-04-30"},
        headers=auth_headers,
    )
    assert resettle.status_code == 200, resettle.text


def test_record_settlement_rejects_zero_revenue(client, auth_headers, seed_data):
    resp = client.post(
        "/api/hospital/settlements",
        json={"unit": "canteen", "from": "1990-01-01", "to": "1990-01-31"},
        headers=auth_headers,
    )
    assert resp.status_code == 400
