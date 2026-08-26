"""Cancel bills from Billing Management across modules (not only OP/lab)."""
from datetime import datetime


def _create_bill(db_session, seed_data, *, bill_type="physiotherapy", total=500.0, status="pending"):
    from app.models.billing import Bill, BillItem
    bill = Bill(
        bill_number=f"T-{bill_type[:3].upper()}-{datetime.now().timestamp()}",
        patient_id=seed_data["patient_id"],
        bill_type=bill_type,
        bill_subtype="final",
        reference_id=0,
        subtotal=total,
        tax_amount=0,
        discount_amount=0,
        total_amount=total,
        status=status,
        bill_date=datetime.now(),
        created_by_id=seed_data["admin_user_id"],
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(bill)
    db_session.flush()
    db_session.add(BillItem(
        bill_id=bill.id,
        item_type=bill_type,
        item_name=f"{bill_type} service",
        item_code=f"X-{bill.id}",
        quantity=1,
        unit_price=total,
        total_price=total,
    ))
    db_session.commit()
    db_session.refresh(bill)
    return bill


class TestCancelLedgerModules:

    def test_cancel_physiotherapy_bill(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, bill_type="physiotherapy", total=800)
        r = client.post(
            f"/api/hospital/billing/cancel/physiotherapy/{bill.id}",
            json={"reason": "Wrong patient"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        db_session.expire_all()
        assert bill.status == "cancelled"

    def test_cancel_day_care_bill(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, bill_type="day_care", total=1200)
        r = client.post(
            f"/api/hospital/billing/cancel/day_care/{bill.id}",
            json={"reason": "Duplicate"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        db_session.expire_all()
        assert bill.status == "cancelled"

    def test_cancel_pharmacy_ledger_bill(self, client, auth_headers, db_session, seed_data):
        bill = _create_bill(db_session, seed_data, bill_type="pharmacy", total=250)
        r = client.post(
            f"/api/hospital/billing/cancel/pharmacy/{bill.id}",
            json={"reason": "Catch-up correction"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        db_session.expire_all()
        assert bill.status == "cancelled"

    def test_cannot_cancel_paid_ledger_bill(self, client, auth_headers, db_session, seed_data):
        from app.models.billing import Payment
        bill = _create_bill(db_session, seed_data, bill_type="physiotherapy", total=500)
        db_session.add(Payment(
            payment_number=f"PAY-{datetime.now().timestamp()}",
            bill_id=bill.id,
            amount_paid=500,
            payment_method_name="cash",
            payment_date=datetime.now(),
            received_by_id=seed_data["admin_user_id"],
        ))
        db_session.commit()
        r = client.post(
            f"/api/hospital/billing/cancel/physiotherapy/{bill.id}",
            json={"reason": "Should fail"},
            headers=auth_headers,
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "bill_has_payments"

    def test_cancel_consolidated_releases_sources(self, client, auth_headers, db_session, seed_data):
        from app.models.outpatient import Appointment
        from app.models.lab import LabTest, PatientLabOrder, LabTestCategory
        from datetime import time

        ts = datetime.now().timestamp()
        apt = Appointment(
            appointment_number=f"APT-CX-{ts}",
            patient_id=seed_data["patient_id"],
            doctor_id=seed_data["doctor_user_id"],
            appointment_date=datetime.now(),
            appointment_time=time(11, 0),
            consultation_fee=200,
            registration_fee=0,
            payment_status="pending",
        )
        db_session.add(apt)
        db_session.commit()
        db_session.refresh(apt)

        cat = db_session.query(LabTestCategory).first()
        if not cat:
            cat = LabTestCategory(name="Hematology", hospital_id=seed_data["hospital_id"])
            db_session.add(cat)
            db_session.commit()
            db_session.refresh(cat)
        test = LabTest(
            name=f"CX-{ts}", test_code=f"CX{int(ts * 1000)}",
            category_id=cat.id, cost=300,
            hospital_id=seed_data["hospital_id"],
        )
        db_session.add(test)
        db_session.commit()
        db_session.refresh(test)
        order = PatientLabOrder(
            order_number=f"LO-CX-{ts}",
            patient_id=seed_data["patient_id"],
            test_id=test.id,
            payment_status="pending",
            status="pending",
            doctor_id=seed_data["doctor_user_id"],
        )
        db_session.add(order)
        db_session.commit()
        db_session.refresh(order)

        cons = client.post(
            "/api/hospital/billing/consolidate",
            json={
                "patient_id": seed_data["patient_id"],
                "consultation_ids": [apt.id],
                "lab_order_ids": [order.id],
            },
            headers=auth_headers,
        )
        assert cons.status_code == 200, cons.text
        bill_id = cons.json()["bill_id"]

        r = client.post(
            f"/api/hospital/billing/cancel/consolidated/{bill_id}",
            json={"reason": "Undo consolidation"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text

        db_session.expire_all()
        assert apt.payment_status == "pending"
        assert order.payment_status == "pending"

    def test_cancel_lab_group_cancels_all_orders(self, client, auth_headers, db_session, seed_data):
        from app.models.lab import LabTest, PatientLabOrder, LabTestCategory

        ts = datetime.now().timestamp()
        cat = db_session.query(LabTestCategory).first()
        if not cat:
            cat = LabTestCategory(name="Hematology", hospital_id=seed_data["hospital_id"])
            db_session.add(cat)
            db_session.commit()
            db_session.refresh(cat)
        gid = f"LBG-{int(ts * 1000)}"
        orders = []
        for i in range(2):
            test = LabTest(
                name=f"GRP-{ts}-{i}", test_code=f"G{int(ts * 1000)}{i}",
                category_id=cat.id, cost=100,
                hospital_id=seed_data["hospital_id"],
            )
            db_session.add(test)
            db_session.flush()
            order = PatientLabOrder(
                order_number=f"LO-G-{ts}-{i}",
                patient_id=seed_data["patient_id"],
                test_id=test.id,
                payment_status="pending",
                status="pending",
                doctor_id=seed_data["doctor_user_id"],
                lab_bill_group_id=gid,
                amount=100,
            )
            db_session.add(order)
            orders.append(order)
        db_session.commit()
        for o in orders:
            db_session.refresh(o)

        r = client.post(
            f"/api/hospital/billing/cancel/lab/{orders[0].id}?lab_bill_group_id={gid}",
            json={"reason": "Group cancel"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        db_session.expire_all()
        assert all(o.payment_status == "cancelled" for o in orders)
