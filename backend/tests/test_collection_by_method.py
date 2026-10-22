"""Receipts by tender include tills that do not write a central Payment row."""
import uuid
from datetime import date, datetime

from app.services.collection_by_method import collection_by_method, sources_for


def _totals(db, hospital_id, on, **kwargs):
    return collection_by_method(db, hospital_id, on, on, **kwargs)


def _method(body, name):
    return float((body.get("by_method") or {}).get(name, 0))


class TestCollectionByMethod:

    def test_counts_each_till_once(self, db_session, seed_data):
        from app.models.billing import Bill, Payment
        from app.models.canteen import CanteenSale
        from app.models.inpatient import Admission, AdmissionDeposit, RoomManagement
        from app.models.lab import PatientLabOrder
        from app.models.outpatient import Appointment
        from app.models.pharmacy import PharmacySale

        hid = seed_data["hospital_id"]
        # Keep this off "today" so it does not change the live billing-list tests.
        on = date(2020, 6, 15)
        now = datetime(2020, 6, 15, 10, 30)
        before = _totals(db_session, hid, on, sources=sources_for())
        lab_before = _totals(db_session, hid, on, sources=sources_for(module="lab"))
        canteen_before = _totals(db_session, hid, on, sources=sources_for(module="canteen"))
        stamp = uuid.uuid4().hex[:8]

        apt = Appointment(
            appointment_number=f"APT-COL-{stamp}",
            patient_id=seed_data["patient_id"],
            doctor_id=seed_data["doctor_user_id"],
            appointment_date=now,
            consultation_fee=111,
            registration_fee=0,
            final_amount=111,
            payment_status="paid",
            payment_method="cash",
            payment_date=now,
        )
        db_session.add(apt)
        db_session.flush()
        # Catch-up style: the same visit also has a Payment. Count it once.
        bill = Bill(
            bill_number=f"CU-COL-{stamp}",
            patient_id=seed_data["patient_id"],
            bill_type="consultation",
            reference_id=apt.id,
            subtotal=111,
            total_amount=111,
            status="paid",
            bill_date=now,
            created_by_id=seed_data["admin_user_id"],
            hospital_id=hid,
        )
        db_session.add(bill)
        db_session.flush()
        db_session.add(Payment(
            payment_number=f"PAY-COL-{stamp}",
            bill_id=bill.id,
            amount_paid=111,
            payment_method_name="cash",
            payment_date=now,
            received_by_id=seed_data["admin_user_id"],
        ))

        db_session.add(PatientLabOrder(
            order_number=f"LAB-COL-{stamp}",
            patient_id=seed_data["patient_id"],
            test_id=1,
            amount=80,
            payment_status="paid",
            payment_method="upi",
            payment_date=now,
            order_date=now,
        ))
        db_session.add(PharmacySale(
            sale_number=f"S-COL-{stamp}",
            sale_date=now,
            payment_type="cash",
            grand_total=40,
            subtotal=40,
            status="completed",
            billing_mode="cash_at_pharmacy",
            hospital_id=hid,
        ))
        db_session.add(PharmacySale(
            sale_number=f"S-CR-{stamp}",
            sale_date=now,
            payment_type="credit",
            grand_total=90,
            subtotal=90,
            status="completed",
            billing_mode="cash_at_pharmacy",
            hospital_id=hid,
        ))
        db_session.add(CanteenSale(
            hospital_id=hid,
            sale_number=f"CAN-COL-{stamp}",
            sale_date=now,
            payment_type="card",
            subtotal=25,
            grand_total=25,
            status="completed",
        ))

        room = RoomManagement(
            room_number=f"C{stamp[:4]}",
            room_type="general",
            room_charge_per_day=100,
            hospital_id=hid,
        )
        db_session.add(room)
        db_session.flush()
        admission = Admission(
            admission_number=f"ADM-COL-{stamp}",
            patient_id=seed_data["patient_id"],
            admitting_doctor_id=seed_data["doctor_user_id"],
            room_id=room.id,
            admission_type="elective",
        )
        db_session.add(admission)
        db_session.flush()
        db_session.add(AdmissionDeposit(
            admission_id=admission.id,
            deposit_number=f"DEP-COL-{stamp}",
            amount=60,
            deposit_type="initial",
            payment_method="upi",
            received_by_id=seed_data["admin_user_id"],
            received_at=now,
            hospital_id=hid,
        ))
        db_session.add(AdmissionDeposit(
            admission_id=admission.id,
            deposit_number=f"DEP-SCH-{stamp}",
            amount=500,
            deposit_type="initial",
            payment_method="scheme_approval",
            received_by_id=seed_data["admin_user_id"],
            received_at=now,
            hospital_id=hid,
        ))
        adm_bill = Bill(
            bill_number=f"ADM-BILL-{stamp}",
            patient_id=seed_data["patient_id"],
            bill_type="admission",
            reference_id=admission.id,
            subtotal=60,
            total_amount=60,
            status="paid",
            bill_date=now,
            created_by_id=seed_data["admin_user_id"],
            hospital_id=hid,
        )
        db_session.add(adm_bill)
        db_session.flush()
        db_session.add(Payment(
            payment_number=f"PAY-ADM-{stamp}",
            bill_id=adm_bill.id,
            amount_paid=60,
            payment_method_name="upi",
            payment_date=now,
            notes="Catch-up inpatient settlement",
            received_by_id=seed_data["admin_user_id"],
        ))
        db_session.add(Payment(
            payment_number=f"PAY-TPA-{stamp}",
            bill_id=adm_bill.id,
            amount_paid=55,
            payment_method_name="online",
            payment_date=now,
            notes="Bill split #1 (tpa: Star) marked received",
            received_by_id=seed_data["admin_user_id"],
        ))
        db_session.commit()

        after = _totals(db_session, hid, on, sources=sources_for())
        assert round(_method(after, "cash") - _method(before, "cash"), 2) == 151  # 111 + 40
        assert round(_method(after, "upi") - _method(before, "upi"), 2) == 140  # 80 lab + 60 deposit
        assert round(_method(after, "card") - _method(before, "card"), 2) == 25
        assert round(_method(after, "insurance") - _method(before, "insurance"), 2) == 55
        assert "scheme_approval" not in after["methods"]
        assert "credit" not in after["methods"]

        lab_only = _totals(db_session, hid, on, sources=sources_for(module="lab"))
        canteen_only = _totals(db_session, hid, on, sources=sources_for(module="canteen"))
        assert round(_method(lab_only, "upi") - _method(lab_before, "upi"), 2) == 80
        assert round(_method(lab_only, "card") - _method(lab_before, "card"), 2) == 0
        assert round(_method(canteen_only, "card") - _method(canteen_before, "card"), 2) == 25
        assert round(_method(canteen_only, "upi") - _method(canteen_before, "upi"), 2) == 0

    def test_billing_list_shows_canteen_and_day_care_method(self, client, auth_headers, db_session, seed_data):
        from app.models.billing import Bill, Payment
        from app.models.canteen import CanteenSale

        now = datetime.now()
        stamp = uuid.uuid4().hex[:8]
        sale = CanteenSale(
            hospital_id=seed_data["hospital_id"],
            sale_number=f"CAN-UI-{stamp}",
            sale_date=now,
            payment_type="upi",
            customer_name="Walk In",
            subtotal=18,
            grand_total=18,
            status="completed",
        )
        db_session.add(sale)
        day_bill = Bill(
            bill_number=f"DC-COL-{stamp}",
            patient_id=seed_data["patient_id"],
            bill_type="day_care",
            reference_id=0,
            subtotal=200,
            total_amount=200,
            status="paid",
            bill_date=now,
            created_by_id=seed_data["admin_user_id"],
            hospital_id=seed_data["hospital_id"],
        )
        db_session.add(day_bill)
        db_session.flush()
        db_session.add(Payment(
            payment_number=f"PAY-DC-{stamp}",
            bill_id=day_bill.id,
            amount_paid=200,
            payment_method_name="card",
            payment_date=now,
            received_by_id=seed_data["admin_user_id"],
        ))
        db_session.commit()

        today = date.today().isoformat()
        listed = client.get(
            "/api/hospital/billing",
            params={"date_from": today, "date_to": today, "bill_type": "canteen"},
            headers=auth_headers,
        )
        assert listed.status_code == 200, listed.text
        body = listed.json()
        row = next(b for b in body["bills"] if b["id"] == f"CAN-{sale.id}")
        assert row["payment_method"] == "upi"
        assert row["type"] == "canteen"
        assert body["summary"]["received_by_method"]["upi"] >= 18

        day = client.get(
            "/api/hospital/billing",
            params={"date_from": today, "date_to": today, "bill_type": "day_care"},
            headers=auth_headers,
        )
        assert day.status_code == 200, day.text
        day_row = next(b for b in day.json()["bills"] if b["reference"] == day_bill.bill_number)
        assert day_row["payment_method"] == "card"
        assert day.json()["summary"]["received_by_method"]["card"] >= 200
