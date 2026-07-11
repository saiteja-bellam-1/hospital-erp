"""Admin catch-up bills — dates, permission, misc + IP reconstruction."""

from datetime import date, datetime, timedelta

import pytest

from app.models.billing import Bill, Payment
from app.models.inpatient import Admission, RoomManagement
from app.services.catch_up_service import assert_catch_up_dates
from app.utils.auth import create_access_token, get_password_hash
from fastapi import HTTPException


def test_assert_catch_up_dates_rejects_future():
    tomorrow = date.today() + timedelta(days=1)
    with pytest.raises(HTTPException) as ei:
        assert_catch_up_dates(tomorrow, date.today())
    assert ei.value.status_code == 400


def test_assert_catch_up_dates_rejects_too_old():
    old = date.today() - timedelta(days=400)
    with pytest.raises(HTTPException) as ei:
        assert_catch_up_dates(old, date.today())
    assert ei.value.status_code == 400


def test_assert_catch_up_dates_ok():
    d = date.today() - timedelta(days=10)
    assert_catch_up_dates(d, d)  # no raise


class TestCatchUpPermission:
    def test_receptionist_forbidden(self, client, seed_data, db_session):
        from app.models.user import User, UserRole

        role = db_session.query(UserRole).filter_by(name="receptionist").first()
        if role is None:
            role = UserRole(name="receptionist", is_system_role=True)
            db_session.add(role)
            db_session.flush()
        user = User(
            username="catchup_reception",
            password_hash=get_password_hash("pass123"),
            email="cu_rec@test.com",
            first_name="Rec",
            last_name="User",
            role_id=role.id,
            hospital_id=seed_data["hospital_id"],
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()

        token = create_access_token(data={"sub": "catchup_reception"})
        headers = {"Authorization": f"Bearer {token}"}
        today = date.today().isoformat()
        res = client.post(
            "/api/admin/catch-up/misc-bill",
            headers=headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": today,
                "payment_date": today,
                "items": [{"item_name": "X", "quantity": 1, "unit_price": 10}],
            },
        )
        assert res.status_code == 403, res.text


class TestCatchUpMiscAndConsultation:
    def test_misc_bill_with_optional_reason_omitted(self, client, auth_headers, seed_data, db_session):
        svc = (date.today() - timedelta(days=5)).isoformat()
        pay = (date.today() - timedelta(days=4)).isoformat()
        res = client.post(
            "/api/admin/catch-up/misc-bill",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": pay,
                "payment_method": "cash",
                "items": [
                    {"item_name": "Manual procedure", "quantity": 1, "unit_price": 250.0},
                ],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] == 250.0
        bill = db_session.query(Bill).filter(Bill.id == body["bill_id"]).first()
        assert bill is not None
        assert bill.bill_type == "catch_up"
        assert bill.bill_date.date().isoformat() == svc
        payment = db_session.query(Payment).filter(Payment.id == body["payment_id"]).first()
        assert payment is not None
        assert payment.payment_date.date().isoformat() == pay

    def test_consultation_catch_up(self, client, auth_headers, seed_data, db_session):
        svc = (date.today() - timedelta(days=3)).isoformat()
        pay = svc
        res = client.post(
            "/api/admin/catch-up/consultation",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "doctor_id": seed_data["doctor_user_id"],
                "consultation_fee": 400,
                "registration_fee": 50,
                "service_date": svc,
                "payment_date": pay,
                "reason": "Missed OPD entry",
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["total"] == 450.0
        bill = db_session.query(Bill).filter(Bill.id == body["bill_id"]).first()
        assert bill.bill_type == "consultation"
        assert bill.bill_date.date().isoformat() == svc


class TestCatchUpInpatient:
    def test_inpatient_stay_reconstruction(self, client, auth_headers, seed_data, db_session):
        # Create a room first
        room = client.post(
            "/api/inpatient/rooms",
            headers=auth_headers,
            json={
                "room_number": "CU-201",
                "room_type": "general",
                "floor": "2",
                "department": "General Ward",
                "bed_count": 2,
                "room_charge_per_day": 1000.0,
            },
        )
        assert room.status_code == 201, room.text
        room_id = room.json()["id"]
        available_before = (
            db_session.query(RoomManagement).filter(RoomManagement.id == room_id).first().available_beds
        )

        admit_dt = datetime.now() - timedelta(days=3)
        discharge_dt = datetime.now() - timedelta(days=1)
        svc = discharge_dt.date().isoformat()
        pay = discharge_dt.date().isoformat()

        res = client.post(
            "/api/admin/catch-up/inpatient-stay",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room_id,
                "admission_date": admit_dt.isoformat(),
                "discharge_date": discharge_dt.isoformat(),
                "admission_type": "elective",
                "service_date": svc,
                "payment_date": pay,
                "visits": [
                    {
                        "visit_type": "doctor_visit",
                        "visitor_id": seed_data["doctor_user_id"],
                        "visit_datetime": (admit_dt + timedelta(days=1)).isoformat(),
                        "charge_amount": 500,
                    }
                ],
                "ancillary": [],
                "canteen_orders": [],
                "deposits": [],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["is_catch_up"] is True
        assert body["status"] == "discharged"
        assert body["total"] > 0

        adm = db_session.query(Admission).filter(Admission.id == body["admission_id"]).first()
        db_session.refresh(adm)
        assert adm.is_catch_up is True
        assert adm.status == "discharged"
        assert adm.bed_id is None

        room_after = db_session.query(RoomManagement).filter(RoomManagement.id == room_id).first()
        db_session.refresh(room_after)
        assert room_after.available_beds == available_before

        bill = db_session.query(Bill).filter(Bill.id == body["bill_id"]).first()
        assert bill.bill_type == "admission"
        assert bill.bill_date.date().isoformat() == svc

        # Auto-post should skip catch-up admissions
        from app.services.inpatient_daily_charges import auto_post_daily_visits_for_admission
        # Force status admitted temporarily to verify skip flag
        adm.status = "admitted"
        db_session.commit()
        posted = auto_post_daily_visits_for_admission(db_session, adm)
        assert posted is None
        adm.status = "discharged"
        db_session.commit()

    def test_inpatient_all_charge_fields_generate_bill(self, client, auth_headers, seed_data, db_session):
        """Exercise every IP catch-up input: visits, nurse, ancillary, food, meds, package."""
        from app.models.billing import BillItem
        from app.models.canteen import CanteenOrder
        from app.models.inpatient import (
            AdmissionAncillaryCharge,
            AdmissionPackage,
            PatientVisit,
        )
        from app.models.pharmacy import PharmacySale
        from app.models.user import User, UserRole
        from app.utils.auth import get_password_hash

        # Nurse user
        nurse_role = db_session.query(UserRole).filter_by(name="nurse").first()
        if nurse_role is None:
            nurse_role = UserRole(name="nurse", is_system_role=True)
            db_session.add(nurse_role)
            db_session.flush()
        nurse = User(
            username="catchup_nurse_full",
            password_hash=get_password_hash("pass123"),
            email="cu_nurse@test.com",
            first_name="Nurse",
            last_name="CatchUp",
            role_id=nurse_role.id,
            hospital_id=seed_data["hospital_id"],
            is_active=True,
            inpatient_fee_inr="150",
        )
        db_session.add(nurse)
        db_session.commit()
        nurse_id = nurse.id

        room = client.post(
            "/api/inpatient/rooms",
            headers=auth_headers,
            json={
                "room_number": "CU-ALL-301",
                "room_type": "private",
                "floor": "3",
                "department": "General Ward",
                "bed_count": 1,
                "room_charge_per_day": 2000.0,
            },
        )
        assert room.status_code == 201, room.text
        room_id = room.json()["id"]

        anc = client.post(
            "/api/inpatient/ancillary-services",
            headers=auth_headers,
            json={
                "service_name": "Oxygen Cylinder CatchUp",
                "category": "oxygen",
                "default_charge": 300.0,
                "charge_unit": "per_day",
            },
        )
        assert anc.status_code == 201, anc.text
        ancillary_id = anc.json()["id"]

        pkg = client.post(
            "/api/inpatient/packages",
            headers=auth_headers,
            json={
                "package_name": "CatchUp Hernia Package",
                "package_code": "CU-HERN",
                "base_price": 15000.0,
                "included_stay_days": 0,
                "included_services": [],
            },
        )
        assert pkg.status_code == 201, pkg.text
        package_id = pkg.json()["id"]

        food_item = client.post(
            "/api/canteen/items",
            headers=auth_headers,
            json={"name": "CatchUp Meal Tray", "price": 120.0, "is_veg": True, "is_active": True},
        )
        assert food_item.status_code == 201, food_item.text
        food_item_id = food_item.json()["id"]

        admit_dt = datetime.now() - timedelta(days=4)
        discharge_dt = datetime.now() - timedelta(days=1)
        svc = discharge_dt.date().isoformat()
        pay = discharge_dt.date().isoformat()
        mid = admit_dt + timedelta(days=1)

        preview = client.post(
            "/api/admin/catch-up/inpatient-stay/preview",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room_id,
                "admission_date": admit_dt.isoformat(),
                "discharge_date": discharge_dt.isoformat(),
                "service_date": svc,
                "payment_date": pay,
                "is_observation": False,
                "visits": [
                    {
                        "visit_type": "doctor_visit",
                        "visitor_id": seed_data["doctor_user_id"],
                        "visit_datetime": mid.isoformat(),
                        "charge_amount": 500,
                    },
                    {
                        "visit_type": "nurse_visit",
                        "visitor_id": nurse_id,
                        "visit_datetime": (mid + timedelta(hours=2)).isoformat(),
                        "charge_amount": 150,
                    },
                ],
                "ancillary": [
                    {
                        "service_id": ancillary_id,
                        "quantity": 2,
                        "unit_price": 300,
                        "charged_at": mid.isoformat(),
                    }
                ],
                "canteen_orders": [
                    {
                        "serve_date": mid.date().isoformat(),
                        "items": [
                            {
                                "item_id": food_item_id,
                                "item_name": "CatchUp Meal Tray",
                                "quantity": 2,
                                "unit_price": 120,
                            }
                        ],
                    }
                ],
                "pharmacy_lines": [
                    {"item_name": "Inj. Ceftriaxone 1g", "quantity": 3, "unit_price": 80},
                    {"item_name": "Tab. Paracetamol 500mg", "quantity": 10, "unit_price": 2},
                ],
                "surgery_package_id": package_id,
                "surgery_package_price": 15000,
            },
        )
        assert preview.status_code == 200, preview.text
        prev = preview.json()
        assert prev["stay_days"] == 3
        assert prev["room_total"] == 6000.0  # 3 * 2000
        assert prev["visit_total"] == 650.0  # 500 + 150
        assert prev["ancillary_total"] == 600.0  # 2 * 300
        assert prev["food_total"] == 240.0  # 2 * 120
        assert prev["pharmacy_total"] == 260.0  # 3*80 + 10*2
        assert prev["package_total"] == 15000.0
        # Preview sums components (package overlay may differ on real bill)
        assert prev["grand_total"] == pytest.approx(6000 + 650 + 600 + 240 + 260 + 15000)

        res = client.post(
            "/api/admin/catch-up/inpatient-stay",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room_id,
                "admission_date": admit_dt.isoformat(),
                "discharge_date": discharge_dt.isoformat(),
                "admission_type": "elective",
                "admission_reason": "Full-field catch-up test",
                "service_date": svc,
                "payment_date": pay,
                "payment_method": "cash",
                "reason": "E2E all IP fields",
                "is_observation": False,
                "visits": [
                    {
                        "visit_type": "doctor_visit",
                        "visitor_id": seed_data["doctor_user_id"],
                        "visit_datetime": mid.isoformat(),
                        "charge_amount": 500,
                        "notes": "Ward round",
                    },
                    {
                        "visit_type": "nurse_visit",
                        "visitor_id": nurse_id,
                        "visit_datetime": (mid + timedelta(hours=2)).isoformat(),
                        "charge_amount": 150,
                        "notes": "Vitals",
                    },
                ],
                "ancillary": [
                    {
                        "service_id": ancillary_id,
                        "quantity": 2,
                        "unit_price": 300,
                        "charged_at": mid.isoformat(),
                        "notes": "O2",
                    }
                ],
                "canteen_orders": [
                    {
                        "serve_date": mid.date().isoformat(),
                        "notes": "Lunch",
                        "items": [
                            {
                                "item_id": food_item_id,
                                "item_name": "CatchUp Meal Tray",
                                "quantity": 2,
                                "unit_price": 120,
                            }
                        ],
                    }
                ],
                "pharmacy_lines": [
                    {"item_name": "Inj. Ceftriaxone 1g", "quantity": 3, "unit_price": 80},
                    {"item_name": "Tab. Paracetamol 500mg", "quantity": 10, "unit_price": 2},
                ],
                "surgery_package_id": package_id,
                "surgery_package_price": 15000,
                "deposits": [],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "discharged"
        assert body["is_catch_up"] is True
        assert body["bill_id"]
        assert body["bill_number"]
        assert body["total"] > 0

        admission_id = body["admission_id"]
        bill_id = body["bill_id"]

        # Source rows persisted
        visits = db_session.query(PatientVisit).filter(PatientVisit.admission_id == admission_id).all()
        assert len(visits) == 2
        assert {v.visit_type for v in visits} == {"doctor_visit", "nurse_visit"}

        ancs = db_session.query(AdmissionAncillaryCharge).filter(
            AdmissionAncillaryCharge.admission_id == admission_id
        ).all()
        assert len(ancs) == 1
        assert float(ancs[0].total_amount) == 600.0

        foods = db_session.query(CanteenOrder).filter(CanteenOrder.admission_id == admission_id).all()
        assert len(foods) == 1
        assert foods[0].status == "delivered"

        sales = db_session.query(PharmacySale).filter(
            PharmacySale.admission_id == admission_id,
            PharmacySale.billing_mode == "inpatient_bill",
        ).all()
        assert len(sales) == 1
        assert float(sales[0].grand_total) == 260.0

        ap = db_session.query(AdmissionPackage).filter(
            AdmissionPackage.admission_id == admission_id
        ).first()
        assert ap is not None
        assert float(ap.agreed_price) == 15000.0

        bill = db_session.query(Bill).filter(Bill.id == bill_id).first()
        db_session.refresh(bill)
        assert bill.bill_type == "admission"
        assert bill.status == "paid"
        assert bill.bill_date.date().isoformat() == svc

        items = db_session.query(BillItem).filter(BillItem.bill_id == bill_id).all()
        assert len(items) >= 1
        types = {it.item_type for it in items}
        # Package fee should appear; other lines depend on package overlay
        assert "package" in types or any("Package" in (it.item_name or "") for it in items)
        assert float(bill.total_amount) == pytest.approx(float(body["total"]))

        payment = db_session.query(Payment).filter(Payment.id == body["payment_id"]).first()
        assert payment is not None
        assert payment.payment_date.date().isoformat() == pay
        assert float(payment.amount_paid) == pytest.approx(float(bill.total_amount))


class TestCatchUpReports:
    def test_daily_collection_uses_payment_date(self, client, auth_headers, seed_data, db_session):
        svc = (date.today() - timedelta(days=10)).isoformat()
        pay = (date.today() - timedelta(days=2)).isoformat()
        res = client.post(
            "/api/admin/catch-up/misc-bill",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": pay,
                "payment_method": "upi",
                "items": [{"item_name": "Report smoke misc", "quantity": 1, "unit_price": 777.0}],
            },
        )
        assert res.status_code == 200, res.text
        total = res.json()["total"]

        r_pay = client.get(
            "/api/hospital/billing/reports/daily-collection",
            headers=auth_headers,
            params={"date_from": pay, "date_to": pay},
        )
        assert r_pay.status_code == 200, r_pay.text
        body = r_pay.json()
        row = next((x for x in body["rows"] if x["date"] == pay), None)
        assert row is not None
        assert row["by_method"].get("upi", 0) >= total

        r_svc = client.get(
            "/api/hospital/billing/reports/daily-collection",
            headers=auth_headers,
            params={"date_from": svc, "date_to": svc},
        )
        assert r_svc.status_code == 200
        if svc != pay:
            svc_row = next((x for x in r_svc.json()["rows"] if x["date"] == svc), None)
            if svc_row:
                assert svc_row["by_method"].get("upi", 0) < total

    def test_tax_summary_uses_service_date(self, client, auth_headers, seed_data, db_session):
        svc = (date.today() - timedelta(days=8)).isoformat()
        pay = (date.today() - timedelta(days=1)).isoformat()
        res = client.post(
            "/api/admin/catch-up/misc-bill",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": pay,
                "items": [{"item_name": "Tax smoke", "quantity": 1, "unit_price": 500.0}],
            },
        )
        assert res.status_code == 200, res.text
        bill_id = res.json()["bill_id"]
        bill = db_session.query(Bill).filter(Bill.id == bill_id).first()

        r = client.get(
            "/api/hospital/billing/reports/tax-summary",
            headers=auth_headers,
            params={"date_from": svc, "date_to": svc},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        row = next((x for x in body["rows"] if x["date"] == svc), None)
        assert row is not None
        assert row["bill_count"] >= 1
        assert row["taxable_value"] >= float(bill.subtotal or 0)


class TestCatchUpPharmacyStock:
    def test_pharmacy_affect_stock_deducts_batch(self, client, auth_headers, seed_data, db_session):
        import uuid
        from app.models.pharmacy import (
            Medicine,
            MedicineCategory,
            PharmacyHSN,
            PharmacyInventory,
            PharmacySupplier,
        )

        hid = seed_data["hospital_id"]
        cat = MedicineCategory(name=f"CU-Cat-{uuid.uuid4().hex[:6]}", hospital_id=hid)
        db_session.add(cat)
        db_session.flush()
        hsn = PharmacyHSN(code=f"H{uuid.uuid4().hex[:4]}", sgst_pct=6, cgst_pct=6, hospital_id=hid)
        db_session.add(hsn)
        db_session.flush()
        med = Medicine(
            medicine_code=f"M{uuid.uuid4().hex[:6]}",
            name=f"CU-Med-{uuid.uuid4().hex[:4]}",
            unit_price=10.0,
            category_id=cat.id,
            hsn_id=hsn.id,
            hospital_id=hid,
        )
        db_session.add(med)
        db_session.flush()
        sup = PharmacySupplier(name=f"CU-Sup-{uuid.uuid4().hex[:4]}", hospital_id=hid)
        db_session.add(sup)
        db_session.commit()

        purchase = client.post(
            "/api/pharmacy/purchases",
            headers=auth_headers,
            json={
                "entry_date": date.today().isoformat(),
                "supplier_id": sup.id,
                "invoice_number": f"CU-INV-{uuid.uuid4().hex[:6]}",
                "payment_type": "cash",
                "purchase_type": "local",
                "items": [{
                    "medicine_id": med.id,
                    "batch_number": f"CUB-{uuid.uuid4().hex[:5]}",
                    "mrp": 40.0,
                    "quantity": 20,
                    "free_quantity": 0,
                    "purchase_rate": 25.0,
                    "discount_pct": 0,
                    "hsn_id": hsn.id,
                    "expiry_date": "2030-12-31",
                }],
            },
        )
        assert purchase.status_code in (200, 201), purchase.text
        pid = purchase.json()["id"]
        conf = client.post(f"/api/pharmacy/purchases/{pid}/confirm", headers=auth_headers)
        assert conf.status_code == 200, conf.text

        batch = (
            db_session.query(PharmacyInventory)
            .filter(PharmacyInventory.medicine_id == med.id)
            .first()
        )
        assert batch is not None
        before = int(batch.quantity_in_stock or 0)
        assert before >= 20

        svc = (date.today() - timedelta(days=1)).isoformat()
        res = client.post(
            "/api/admin/catch-up/pharmacy-sale",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "service_date": svc,
                "payment_date": svc,
                "affect_stock": True,
                "items": [{
                    "item_name": med.name,
                    "quantity": 4,
                    "unit_price": 35.0,
                    "medicine_id": med.id,
                    "batch_id": batch.id,
                }],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["sale_id"]
        assert body["total"] == 140.0

        db_session.refresh(batch)
        assert int(batch.quantity_in_stock or 0) == before - 4


class TestCatchUpAppendCharges:
    def test_append_charges_reopens_and_refinalizes(self, client, auth_headers, seed_data, db_session):
        from app.models.inpatient import AdmissionAncillaryCharge, AncillaryServiceCatalog

        room = client.post(
            "/api/inpatient/rooms",
            headers=auth_headers,
            json={
                "room_number": "CU-APP-401",
                "room_type": "general",
                "floor": "4",
                "department": "General Ward",
                "bed_count": 2,
                "room_charge_per_day": 800.0,
            },
        )
        assert room.status_code == 201, room.text
        room_id = room.json()["id"]

        admit_dt = datetime.now() - timedelta(days=4)
        discharge_dt = datetime.now() - timedelta(days=2)
        svc = discharge_dt.date().isoformat()
        pay = discharge_dt.date().isoformat()

        create = client.post(
            "/api/admin/catch-up/inpatient-stay",
            headers=auth_headers,
            json={
                "patient_id": seed_data["patient_id"],
                "admitting_doctor_id": seed_data["doctor_user_id"],
                "room_id": room_id,
                "admission_date": admit_dt.isoformat(),
                "discharge_date": discharge_dt.isoformat(),
                "service_date": svc,
                "payment_date": pay,
                "visits": [],
                "ancillary": [],
                "canteen_orders": [],
                "pharmacy_lines": [],
                "deposits": [],
            },
        )
        assert create.status_code == 200, create.text
        created = create.json()
        admission_id = created["admission_id"]
        old_bill_id = created["bill_id"]
        old_total = float(created["total"])

        svc_cat = AncillaryServiceCatalog(
            hospital_id=seed_data["hospital_id"],
            service_name="Append Dressing",
            category="consumable",
            default_charge=250.0,
            is_active=True,
        )
        db_session.add(svc_cat)
        db_session.commit()

        append_svc = (date.today() - timedelta(days=1)).isoformat()
        append = client.post(
            f"/api/admin/catch-up/inpatient/{admission_id}/append-charges",
            headers=auth_headers,
            json={
                "service_date": append_svc,
                "payment_date": append_svc,
                "reason": "Forgot dressing charge",
                "ancillary": [{
                    "service_id": svc_cat.id,
                    "quantity": 1,
                    "unit_price": 250.0,
                }],
                "pharmacy_lines": [
                    {"item_name": "Gauze pack", "quantity": 2, "unit_price": 40.0},
                ],
            },
        )
        assert append.status_code == 200, append.text
        body = append.json()
        assert body["cancelled_bill_id"] == old_bill_id
        assert body["bill_id"] != old_bill_id
        assert body["total"] > old_total

        old_bill = db_session.query(Bill).filter(Bill.id == old_bill_id).first()
        db_session.refresh(old_bill)
        assert old_bill.status == "cancelled"

        new_bill = db_session.query(Bill).filter(Bill.id == body["bill_id"]).first()
        db_session.refresh(new_bill)
        assert new_bill.status == "paid"
        assert new_bill.bill_date.date().isoformat() == append_svc

        ancs = db_session.query(AdmissionAncillaryCharge).filter(
            AdmissionAncillaryCharge.admission_id == admission_id
        ).all()
        assert len(ancs) >= 1
        assert any(float(a.total_amount or 0) == 250.0 for a in ancs)
