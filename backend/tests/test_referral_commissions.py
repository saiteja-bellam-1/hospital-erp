"""Referral payouts follow the single referral saved on the patient."""
import uuid
from datetime import date, datetime

from app.models.billing import Bill
from app.models.lab import LabTest, LabTestCategory, PatientLabOrder
from app.models.outpatient import Appointment
from app.models.patient import Patient
from app.models.pharmacy import PharmacySale, PharmacySaleReturn
from app.models.referral import Referral, ReferralCommission, ReferralLabCategoryRate


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
    assert body["consultations"][0]["reference"] == f"OP-{suffix}"
    assert body["consultations"][0]["commission"] == 100
    assert body["consultations"][0]["commission_pct"] == 10
    assert len(body["lab_orders"]) == 1
    assert body["lab_orders"][0]["commission"] == 80
    assert len(body["inpatient_bills"]) == 2
    ip_by_ref = {row["reference"]: row for row in body["inpatient_bills"]}
    assert ip_by_ref[f"ADM-{suffix}"]["commission"] == 100
    assert ip_by_ref[f"ADM-INT-{suffix}"]["commission"] == 25
    assert len(body["pharmacy_sales"]) == 1
    assert body["pharmacy_sales"][0]["amount"] == 250
    assert body["pharmacy_sales"][0]["commission"] == 37.5

    board = client.get("/api/referrals/dashboard", headers=auth_headers)
    assert board.status_code == 200, board.text
    totals = board.json()
    assert totals["referral_count"] == 1
    assert totals["active_count"] == 1
    assert totals["revenue_generated"] == 4150
    assert totals["commission_earned"] == 342.5
    assert totals["commission_paid"] == 100
    assert totals["commission_due"] == 242.5


def _book(client, headers, patient, doctor_id, referred_by):
    res = client.post("/api/appointments/", headers=headers, json={
        "patient_id": patient.patient_id,
        "doctor_id": doctor_id,
        "appointment_date": "2026-07-29",
        "payment_status": "pending",
        "referred_by": referred_by,
        "override_availability": True,
        "override_reason": "referral test",
    })
    assert res.status_code == 200, res.text
    return res.json()


def test_blank_patient_referral_is_saved_from_the_booking(
    client, auth_headers, db_session, seed_data
):
    suffix = uuid.uuid4().hex[:8]
    ref_name = f"Dr Blank {suffix}"
    referral = Referral(name=ref_name, hospital_id=seed_data["hospital_id"], op_commission_pct=10)
    db_session.add(referral)
    patient = _patient(db_session, seed_data, "Chitra", None)
    db_session.commit()

    booked = _book(client, auth_headers, patient, seed_data["doctor_user_id"], ref_name)
    assert booked["referred_by"] == ref_name

    db_session.refresh(patient)
    assert patient.referred_by == ref_name

    details = client.get(f"/api/referrals/{referral.id}/details", headers=auth_headers)
    assert details.status_code == 200, details.text
    references = {row["reference"] for row in details.json()["consultations"]}
    assert booked["appointment_number"] in references


def test_existing_patient_referral_is_kept_when_booking_sends_another(
    client, auth_headers, db_session, seed_data
):
    suffix = uuid.uuid4().hex[:8]
    saved_name = f"Dr Saved {suffix}"
    other_name = f"Dr Other {suffix}"
    saved = Referral(name=saved_name, hospital_id=seed_data["hospital_id"], op_commission_pct=10)
    other = Referral(name=other_name, hospital_id=seed_data["hospital_id"], op_commission_pct=10)
    db_session.add_all([saved, other])
    patient = _patient(db_session, seed_data, "Deepa", saved_name)
    db_session.commit()

    booked = _book(client, auth_headers, patient, seed_data["doctor_user_id"], other_name)
    assert booked["referred_by"] == saved_name

    db_session.refresh(patient)
    assert patient.referred_by == saved_name

    saved_details = client.get(f"/api/referrals/{saved.id}/details", headers=auth_headers)
    other_details = client.get(f"/api/referrals/{other.id}/details", headers=auth_headers)
    assert saved_details.status_code == 200
    assert other_details.status_code == 200
    saved_refs = {row["reference"] for row in saved_details.json()["consultations"]}
    other_refs = {row["reference"] for row in other_details.json()["consultations"]}
    assert booked["appointment_number"] in saved_refs
    assert booked["appointment_number"] not in other_refs


def test_billing_admin_can_edit_a_referral_and_reception_cannot(client, auth_headers, db_session, seed_data):
    from app.models.user import User, UserRole
    from app.utils.auth import create_access_token

    created = client.post("/api/referrals", json={
        "name": f"Edit Gate {uuid.uuid4().hex[:6]}",
        "op_commission_pct": 10,
    }, headers=auth_headers)
    assert created.status_code == 200, created.text
    referral_id = created.json()["id"]

    reception = {"Authorization": f"Bearer {create_access_token(data={'sub': 'testreceptionist'})}"}
    blocked = client.put(f"/api/referrals/{referral_id}", json={"name": "Changed"}, headers=reception)
    assert blocked.status_code == 403

    billing_role = db_session.query(UserRole).filter_by(name="billing_admin").first()
    if billing_role is None:
        billing_role = UserRole(name="billing_admin", is_system_role=True)
        db_session.add(billing_role)
        db_session.flush()
    suffix = uuid.uuid4().hex[:6]
    billing_user = User(
        username=f"billadmin{suffix}",
        email=f"billadmin{suffix}@test.com",
        password_hash="x",
        first_name="Bill",
        last_name="Admin",
        role_id=billing_role.id,
        hospital_id=seed_data["hospital_id"],
        is_active=True,
    )
    db_session.add(billing_user)
    db_session.commit()

    billing = {"Authorization": f"Bearer {create_access_token(data={'sub': billing_user.username})}"}
    updated = client.put(
        f"/api/referrals/{referral_id}",
        json={"op_commission_pct": 12},
        headers=billing,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["op_commission_pct"] == 12


def _lab_test(db_session, seed_data, category, name, code):
    test = LabTest(
        test_code=code,
        name=name,
        category_id=category.id,
        cost=100,
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(test)
    db_session.flush()
    return test


def test_lab_commission_uses_category_rates_and_send_out_margin(
    client, auth_headers, db_session, seed_data
):
    suffix = uuid.uuid4().hex[:8]
    ref_name = f"Dr Lab {suffix}"
    referral = Referral(
        name=ref_name,
        hospital_id=seed_data["hospital_id"],
        lab_commission_pct=20,
    )
    db_session.add(referral)
    db_session.flush()

    hematology = LabTestCategory(name=f"Hematology {suffix}", hospital_id=seed_data["hospital_id"])
    biochemistry = LabTestCategory(name=f"Biochemistry {suffix}", hospital_id=seed_data["hospital_id"])
    db_session.add_all([hematology, biochemistry])
    db_session.flush()
    db_session.add(ReferralLabCategoryRate(
        referral_id=referral.id,
        category_id=hematology.id,
        commission_pct=10,
    ))

    heme = _lab_test(db_session, seed_data, hematology, f"CBC {suffix}", f"H{suffix[:5]}")
    chem = _lab_test(db_session, seed_data, biochemistry, f"LFT {suffix}", f"B{suffix[:5]}")
    patient = _patient(db_session, seed_data, "Esha", ref_name)

    db_session.add_all([
        PatientLabOrder(
            order_number=f"LAB-IN-{suffix}",
            patient_id=patient.id,
            test_id=heme.id,
            amount=400,
            payment_status="paid",
            fulfillment="in_house",
        ),
        PatientLabOrder(
            order_number=f"LAB-CHEM-{suffix}",
            patient_id=patient.id,
            test_id=chem.id,
            amount=500,
            payment_status="paid",
            fulfillment="in_house",
        ),
        PatientLabOrder(
            order_number=f"LAB-OUT-{suffix}",
            patient_id=patient.id,
            test_id=heme.id,
            amount=1000,
            partner_cost=700,
            payment_status="paid",
            fulfillment="send_out",
        ),
        PatientLabOrder(
            order_number=f"LAB-IN2-{suffix}",
            patient_id=patient.id,
            test_id=chem.id,
            amount=200,
            payment_status="paid",
            fulfillment="receive_in",
            bill_to="partner",
        ),
        PatientLabOrder(
            order_number=f"LAB-NOCOST-{suffix}",
            patient_id=patient.id,
            test_id=chem.id,
            amount=100,
            partner_cost=None,
            payment_status="paid",
            fulfillment="send_out",
        ),
        PatientLabOrder(
            order_number=f"LAB-ADM-{suffix}",
            patient_id=patient.id,
            test_id=heme.id,
            amount=800,
            payment_status="paid",
            fulfillment="in_house",
            admission_id=1,
        ),
    ])
    db_session.commit()

    response = client.get(f"/api/referrals/{referral.id}/details", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    summary = body["summary"]

    assert summary["lab_revenue"] == 2200
    assert summary["lab_commission_base"] == 1500
    assert summary["lab_commission"] == 230
    assert summary["total_lab_orders"] == 5
    assert len(body["lab_orders"]) == 5

    by_name = {row["category_name"]: row for row in summary["lab_by_category"]}
    assert by_name[hematology.name]["percent"] == 10
    assert by_name[hematology.name]["billed"] == 1400
    assert by_name[hematology.name]["base"] == 700
    assert by_name[hematology.name]["commission"] == 70
    assert by_name[hematology.name]["order_count"] == 2
    assert by_name[biochemistry.name]["percent"] == 20
    assert by_name[biochemistry.name]["billed"] == 800
    assert by_name[biochemistry.name]["base"] == 800
    assert by_name[biochemistry.name]["commission"] == 160

    send_out = next(row for row in body["lab_orders"] if row["reference"] == f"LAB-OUT-{suffix}")
    assert send_out["amount"] == 1000
    assert send_out["partner_cost"] == 700
    assert send_out["commission_base"] == 300
    assert send_out["commission_pct"] == 10
    assert send_out["commission"] == 30

    received = next(row for row in body["lab_orders"] if row["reference"] == f"LAB-IN2-{suffix}")
    assert received["commission_base"] == 200
    assert received["commission"] == 40

    missing_cost = next(row for row in body["lab_orders"] if row["reference"] == f"LAB-NOCOST-{suffix}")
    assert missing_cost["commission_base"] == 100
    assert missing_cost["commission"] == 20


def test_referral_category_rates_round_trip(client, auth_headers, db_session, seed_data):
    suffix = uuid.uuid4().hex[:8]
    category = LabTestCategory(name=f"Serology {suffix}", hospital_id=seed_data["hospital_id"])
    db_session.add(category)
    db_session.commit()

    listed = client.get("/api/referrals/lab-categories", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    names = {row["name"] for row in listed.json()}
    assert category.name in names

    created = client.post("/api/referrals", json={
        "name": f"Rate Cat {suffix}",
        "lab_commission_pct": 5,
        "category_rates": [{"category_id": category.id, "commission_pct": 12.5}],
    }, headers=auth_headers)
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["category_rates"][0]["category_id"] == category.id
    assert body["category_rates"][0]["commission_pct"] == 12.5
    assert body["category_rates"][0]["category_name"] == category.name

    cleared = client.put(
        f"/api/referrals/{body['id']}",
        json={"category_rates": []},
        headers=auth_headers,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["category_rates"] == []

    replaced = client.put(
        f"/api/referrals/{body['id']}",
        json={"category_rates": [{"category_id": category.id, "commission_pct": 8}]},
        headers=auth_headers,
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["category_rates"] == [{
        "category_id": category.id,
        "commission_pct": 8.0,
        "category_name": category.name,
    }]

    unknown = client.put(
        f"/api/referrals/{body['id']}",
        json={"category_rates": [{"category_id": 0, "commission_pct": 4}]},
        headers=auth_headers,
    )
    assert unknown.status_code == 400

    duplicate = client.put(
        f"/api/referrals/{body['id']}",
        json={"category_rates": [
            {"category_id": category.id, "commission_pct": 4},
            {"category_id": category.id, "commission_pct": 6},
        ]},
        headers=auth_headers,
    )
    assert duplicate.status_code == 400


def test_referral_rejects_commission_rate_above_100(client, auth_headers, db_session, seed_data):
    created = client.post("/api/referrals", json={
        "name": f"Rate Check {uuid.uuid4().hex[:6]}",
        "op_commission_pct": 150,
    }, headers=auth_headers)
    assert created.status_code == 422
