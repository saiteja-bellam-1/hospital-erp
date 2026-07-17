import uuid
from datetime import datetime

from app.models.billing import Bill, BillItem


def test_inpatient_settlements_summary_groups_final_bill_items(
    client, auth_headers, seed_data, db_session
):
    suffix = uuid.uuid4().hex[:8]
    bill_date = datetime(2001, 1, 15, 12, 0, 0)

    final_bill = Bill(
        bill_number=f"TEST-SETTLE-{suffix}",
        patient_id=seed_data["patient_id"],
        bill_type="admission",
        bill_subtype="final",
        reference_id=987654,
        subtotal=1000,
        total_amount=1000,
        status="paid",
        bill_date=bill_date,
        created_by_id=seed_data["admin_user_id"],
        hospital_id=seed_data["hospital_id"],
    )
    interim_bill = Bill(
        bill_number=f"TEST-SETTLE-INT-{suffix}",
        patient_id=seed_data["patient_id"],
        bill_type="admission",
        bill_subtype="interim",
        reference_id=987654,
        subtotal=999,
        total_amount=999,
        status="paid",
        bill_date=bill_date,
        created_by_id=seed_data["admin_user_id"],
        hospital_id=seed_data["hospital_id"],
    )
    cancelled_bill = Bill(
        bill_number=f"TEST-SETTLE-CAN-{suffix}",
        patient_id=seed_data["patient_id"],
        bill_type="admission",
        bill_subtype="final",
        reference_id=987654,
        subtotal=999,
        total_amount=999,
        status="cancelled",
        bill_date=bill_date,
        created_by_id=seed_data["admin_user_id"],
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add_all([final_bill, interim_bill, cancelled_bill])
    db_session.flush()
    db_session.add_all([
        BillItem(
            bill_id=final_bill.id,
            item_type="lab_test",
            item_name="CBC",
            quantity=1,
            unit_price=250,
            total_price=250,
        ),
        BillItem(
            bill_id=final_bill.id,
            item_type="pharmacy",
            item_name="Medicines",
            quantity=1,
            unit_price=300,
            total_price=300,
        ),
        BillItem(
            bill_id=final_bill.id,
            item_type="food",
            item_name="Canteen meal",
            quantity=1,
            unit_price=150,
            total_price=150,
        ),
        BillItem(
            bill_id=final_bill.id,
            item_type="room_charge",
            item_name="Room",
            quantity=1,
            unit_price=300,
            total_price=300,
        ),
        BillItem(
            bill_id=interim_bill.id,
            item_type="lab_test",
            item_name="Excluded interim test",
            quantity=1,
            unit_price=999,
            total_price=999,
        ),
        BillItem(
            bill_id=cancelled_bill.id,
            item_type="pharmacy",
            item_name="Excluded cancelled medicine",
            quantity=1,
            unit_price=999,
            total_price=999,
        ),
    ])
    db_session.commit()

    response = client.get(
        "/api/hospital/inpatient-settlements-summary?from=2001-01-15&to=2001-01-15",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["bill_count"] == 1
    assert data["totals"] == {
        "lab": 250.0,
        "pharmacy": 300.0,
        "canteen": 150.0,
        "hospital": 300.0,
        "total": 1000.0,
    }
    assert data["bills"][0]["bill_number"] == final_bill.bill_number
    assert data["bills"][0]["patient_name"] == "John Doe"


def test_inpatient_settlements_summary_rejects_reversed_date_range(
    client, auth_headers, seed_data
):
    response = client.get(
        "/api/hospital/inpatient-settlements-summary?from=2001-01-16&to=2001-01-15",
        headers=auth_headers,
    )

    assert response.status_code == 400
