"""Referral payouts follow the referral saved on the patient at registration."""
import uuid
from datetime import date, datetime

from app.models.billing import Bill
from app.models.lab import LabTest, LabTestCategory, PatientLabOrder
from app.models.outpatient import Appointment
from app.models.patient import Patient
from app.models.pharmacy import PharmacySale, PharmacySaleReturn
from app.models.referral import Referral, ReferralCommission


def _patient(db_session, seed_data, name, referred_by):
    patient = Patient(
        patient_id=str(uuid.uuid4()),
        first_name=name,
        last_name="Referred",
        date_of_birth=date(1991, 3, 3),
        gender="female",
        primary_phone=f"9{uuid.uuid4().int % 10**9:09d}",
        referred_by=referred_by,
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(patient)
    db_session.flush()
    return patient


def test_referral_payout_uses_patient_referral_across_op_lab_ip_pharmacy(
    client, auth_headers, db_session, seed_data
):
    suffix = uuid.uuid4().hex[:8]
    ref_name = f"Dr Rao {suffix}"
    other_name = f"Other Ref {suffix}"

    referral = Referral(
        name=ref_name,
        hospital_id=seed_data["hospital_id"],
        op_commission_pct=10,
        lab_commission_pct=20,
        ip_commission_pct=5,
        pharmacy_commission_pct=15,
    )
    db_session.add(referral)
    db_session.flush()

    patient = _patient(db_session, seed_data, "Asha", ref_name)
    other = _patient(db_session, seed_data, "Bina", other_name)

    db_session.add_all([
        Appointment(
            appointment_number=f"OP-{suffix}",
            patient_id=patient.id,
            doctor_id=seed_data["doctor_user_id"],
            appointment_date=datetime.now(),
            consultation_fee=1000,
            final_amount=1000,
            payment_status="paid",
            referred_by="someone else",
        ),
        Appointment(
            appointment_number=f"OP-CX-{suffix}",
            patient_id=patient.id,
            doctor_id=seed_data["doctor_user_id"],
            appointment_date=datetime.now(),
            final_amount=500,
            payment_status="paid",
            status="cancelled",
        ),
        Appointment(
            appointment_number=f"OP-OTHER-{suffix}",
            patient_id=other.id,
            doctor_id=seed_data["doctor_user_id"],
            appointment_date=datetime.now(),
            final_amount=800,
            payment_status="paid",
            referred_by=ref_name,
        ),
    ])

    category = LabTestCategory(name=f"Cat {suffix}", hospital_id=seed_data["hospital_id"])
    db_session.add(category)
    db_session.flush()
    test = LabTest(
        test_code=f"T{suffix[:6]}",
        name=f"CBC {suffix}",
        category_id=category.id,
        cost=400,
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(test)
    db_session.flush()
    db_session.add_all([
        PatientLabOrder(
            order_number=f"LAB-{suffix}",
            patient_id=patient.id,
            test_id=test.id,
            amount=400,
            payment_status="paid",
        ),
        PatientLabOrder(
            order_number=f"LAB-IP-{suffix}",
            patient_id=patient.id,
            test_id=test.id,
            amount=800,
            payment_status="paid",
            admission_id=1,
        ),
    ])

    db_session.add_all([
        Bill(
            bill_number=f"ADM-{suffix}",
            patient_id=patient.id,
            bill_type="admission",
            bill_subtype="final",
            subtotal=2000,
            total_amount=2000,
            status="paid",
            created_by_id=seed_data["admin_user_id"],
            hospital_id=seed_data["hospital_id"],
        ),
        Bill(
            bill_number=f"ADM-INT-{suffix}",
            patient_id=patient.id,
            bill_type="admission",
            bill_subtype="interim",
            subtotal=500,
            total_amount=500,
            status="paid",
            created_by_id=seed_data["admin_user_id"],
            hospital_id=seed_data["hospital_id"],
        ),
        Bill(
            bill_number=f"ADM-ADV-{suffix}",
            patient_id=patient.id,
            bill_type="admission",
            bill_subtype="advance_receipt",
            subtotal=1000,
            total_amount=1000,
            status="paid",
            created_by_id=seed_data["admin_user_id"],
            hospital_id=seed_data["hospital_id"],
        ),
        Bill(
            bill_number=f"ADM-CX-{suffix}",
            patient_id=patient.id,
            bill_type="admission",
            bill_subtype="final",
            subtotal=9000,
            total_amount=9000,
            status="cancelled",
            created_by_id=seed_data["admin_user_id"],
            hospital_id=seed_data["hospital_id"],
        ),
    ])

    sale = PharmacySale(
        sale_number=f"SALE-{suffix}",
        sale_date=datetime.now(),
        patient_ip_id=patient.patient_id,
        patient_name="Asha Referred",
        grand_total=300,
        status="completed",
        billing_mode="cash_at_pharmacy",
        hospital_id=seed_data["hospital_id"],
    )
    ip_sale = PharmacySale(
        sale_number=f"SALE-IP-{suffix}",
        sale_date=datetime.now(),
        patient_ip_id=patient.patient_id,
        grand_total=700,
        status="completed",
        billing_mode="inpatient_bill",
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add_all([sale, ip_sale])
    db_session.flush()
    db_session.add(PharmacySaleReturn(
        return_number=f"RET-{suffix}",
        return_date=date.today(),
        sale_id=sale.id,
        grand_total=50,
        status="confirmed",
        hospital_id=seed_data["hospital_id"],
    ))
    db_session.add(ReferralCommission(
        referral_id=referral.id,
        amount=100,
        payment_method="cash",
        paid_by_id=seed_data["admin_user_id"],
        hospital_id=seed_data["hospital_id"],
    ))
    db_session.commit()

    response = client.get(f"/api/referrals/{referral.id}/details", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    summary = body["summary"]

    assert summary["op_revenue"] == 1000
    assert summary["lab_revenue"] == 400
    assert summary["ip_revenue"] == 2500
    assert summary["pharmacy_revenue"] == 250
    assert summary["op_commission"] == 100
    assert summary["lab_commission"] == 80
    assert summary["ip_commission"] == 125
    assert summary["pharmacy_commission"] == 37.5
    assert summary["total_commission_earned"] == 342.5
    assert summary["total_commission_paid"] == 100
    assert summary["commission_balance"] == 242.5
    assert len(body["consultations"]) == 1
    assert len(body["lab_orders"]) == 1
    assert len(body["inpatient_bills"]) == 2
    assert len(body["pharmacy_sales"]) == 1
    assert body["pharmacy_sales"][0]["amount"] == 250


def test_referral_rejects_commission_rate_above_100(client, auth_headers, db_session, seed_data):
    created = client.post("/api/referrals", json={
        "name": f"Rate Check {uuid.uuid4().hex[:6]}",
        "op_commission_pct": 150,
    }, headers=auth_headers)
    assert created.status_code == 422
