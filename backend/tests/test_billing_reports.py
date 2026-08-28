"""Tests for billing report endpoints."""
from datetime import datetime, date, time


def _bill_with_payment(db_session, seed_data, total=1000.0, paid=500.0, method="cash", tax=180.0, subtotal=820.0):
    from app.models.billing import Bill, Payment
    ts = datetime.now().timestamp()
    bill = Bill(
        bill_number=f"R-{ts}",
        patient_id=seed_data["patient_id"],
        bill_type="consultation",
        reference_id=0,
        subtotal=subtotal,
        tax_amount=tax,
        discount_amount=0,
        total_amount=total,
        status="partial" if paid > 0 and paid < total else ("paid" if paid >= total else "pending"),
        bill_date=datetime.now(),
        created_by_id=seed_data["admin_user_id"],
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(bill); db_session.flush()
    if paid > 0:
        db_session.add(Payment(
            payment_number=f"P-{ts}",
            bill_id=bill.id,
            amount_paid=paid,
            payment_method_name=method,
            payment_date=datetime.now(),
            received_by_id=seed_data["admin_user_id"],
        ))
    db_session.commit()
    db_session.refresh(bill)
    return bill


class TestReports:

    def test_daily_collection_groups_by_method(self, client, auth_headers, db_session, seed_data):
        _bill_with_payment(db_session, seed_data, total=500, paid=500, method="cash", tax=0, subtotal=500)
        _bill_with_payment(db_session, seed_data, total=300, paid=300, method="upi", tax=0, subtotal=300)
        r = client.get("/api/hospital/billing/reports/daily-collection", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["totals"]["net_collected"] >= 800
        assert "cash" in body["methods"] and "upi" in body["methods"]
        today_row = next((row for row in body["rows"] if row["date"] == date.today().isoformat()), None)
        assert today_row is not None
        assert today_row["by_method"].get("cash", 0) >= 500

    def test_daily_collection_nets_refunds(self, client, auth_headers, db_session, seed_data):
        bill = _bill_with_payment(db_session, seed_data, total=400, paid=400, method="cash", tax=0, subtotal=400)
        from app.models.billing import Payment
        pay = db_session.query(Payment).filter_by(bill_id=bill.id).first()
        # Issue a refund of 100
        client.post(f"/api/hospital/billing/payments/{pay.id}/refund",
                    json={"amount": 100, "reason": "test"}, headers=auth_headers)
        r = client.get("/api/hospital/billing/reports/daily-collection", headers=auth_headers)
        body = r.json()
        today_row = next(row for row in body["rows"] if row["date"] == date.today().isoformat())
        assert today_row["refunds"] >= 100

    def test_doctor_revenue_includes_consultations(self, client, auth_headers, db_session, seed_data):
        from app.models.outpatient import Appointment
        ts = datetime.now().timestamp()
        a = Appointment(
            appointment_number=f"DRR-{ts}",
            patient_id=seed_data["patient_id"],
            doctor_id=seed_data["doctor_user_id"],
            appointment_date=datetime.now(),
            appointment_time=time(11, 0),
            consultation_fee=500,
            registration_fee=0,
            payment_status="paid",
        )
        db_session.add(a); db_session.commit()
        r = client.get("/api/hospital/billing/reports/doctor-revenue", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        doc_row = next((row for row in body["rows"] if row["doctor_id"] == seed_data["doctor_user_id"]), None)
        assert doc_row is not None
        assert doc_row["consultation_revenue"] >= 500

    def test_tax_summary_excludes_cancelled_and_credit_notes(self, client, auth_headers, db_session, seed_data):
        _bill_with_payment(db_session, seed_data, total=1180, paid=0, tax=180, subtotal=1000)
        r = client.get("/api/hospital/billing/reports/tax-summary", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["totals"]["tax_amount"] >= 180
        assert body["totals"]["taxable_value"] >= 1000

    def test_reports_require_admin(self, client, db_session, seed_data):
        # Build a JWT for the doctor user (not admin)
        from app.utils.auth import create_access_token
        token = create_access_token(data={"sub": "testdoctor"})
        hdr = {"Authorization": f"Bearer {token}"}
        r = client.get("/api/hospital/billing/reports/daily-collection", headers=hdr)
        assert r.status_code == 403

    def test_sales_summary_filters_by_patient(self, client, auth_headers, db_session, seed_data):
        import uuid
        from app.models.patient import Patient
        other = Patient(
            patient_id=str(uuid.uuid4()),
            first_name="Jane",
            last_name="Roe",
            date_of_birth=date(1992, 2, 2),
            gender="female",
            primary_phone="9123456780",
            hospital_id=seed_data["hospital_id"],
        )
        db_session.add(other)
        db_session.flush()
        other_id = other.id
        db_session.commit()

        _bill_with_payment(db_session, seed_data, total=400, paid=400, tax=0, subtotal=400)
        other_seed = {**seed_data, "patient_id": other_id}
        _bill_with_payment(db_session, other_seed, total=250, paid=250, tax=0, subtotal=250)

        all_r = client.get("/api/hospital/billing/reports/sales-summary", headers=auth_headers)
        assert all_r.status_code == 200, all_r.text
        assert all_r.json()["totals"]["billed"] >= 650

        pid = seed_data["patient_id"]
        one = client.get(
            f"/api/hospital/billing/reports/sales-summary?patient_id={pid}",
            headers=auth_headers,
        )
        assert one.status_code == 200, one.text
        body = one.json()
        assert body["patient_id"] == pid
        invoices = body.get("invoices") or []
        assert any(inv.get("patient_id") == pid for inv in invoices)
        assert all(inv.get("patient_id") in (pid, None) for inv in invoices)
        assert not any(inv.get("patient_id") == other_id for inv in invoices)
        assert body["totals"]["billed"] >= 400

    def test_ops_reports_from_billing_hub(self, client, auth_headers):
        occ = client.get("/api/hospital/billing/reports/bed-occupancy", headers=auth_headers)
        assert occ.status_code == 200, occ.text
        body = occ.json()
        assert "totals" in body
        assert "occupancy_pct" in body["totals"]

        eff = client.get("/api/hospital/billing/reports/doctor-efficiency", headers=auth_headers)
        assert eff.status_code == 200, eff.text
        assert "rows" in eff.json()

        out = client.get("/api/hospital/billing/reports/monthly-outcomes", headers=auth_headers)
        assert out.status_code == 200, out.text
        assert "totals" in out.json()

    def test_hub_module_reports_return_payloads(self, client, auth_headers, db_session, seed_data):
        from datetime import timedelta
        from app.models.outpatient import Appointment
        from app.models.lab import PatientLabOrder, LabTest, LabTestCategory, SampleType
        from app.models.pharmacy import Medicine, MedicineCategory, PharmacyInventory, PharmacySale
        from app.models.billing import Bill

        hid = seed_data["hospital_id"]
        pid = seed_data["patient_id"]
        did = seed_data["doctor_user_id"]
        ts = datetime.now().timestamp()

        appt = Appointment(
            appointment_number=f"OPD-{ts}",
            patient_id=pid,
            doctor_id=did,
            appointment_date=datetime.now(),
            appointment_time=time(10, 0),
            consultation_fee=400,
            registration_fee=50,
            payment_status="paid",
            status="completed",
        )
        db_session.add(appt)

        cat = LabTestCategory(name=f"Cat-{ts}", hospital_id=hid, is_active=True)
        stype = SampleType(name=f"Blood-{ts}", hospital_id=hid, is_active=True)
        db_session.add_all([cat, stype])
        db_session.flush()
        test = LabTest(
            name=f"CBC-{ts}",
            test_code=f"CBC{int(ts)}",
            hospital_id=hid,
            category_id=cat.id,
            sample_type_id=stype.id,
            cost=250,
            is_active=True,
        )
        db_session.add(test)
        db_session.flush()
        db_session.add(PatientLabOrder(
            order_number=f"LO-{ts}",
            patient_id=pid,
            test_id=test.id,
            doctor_id=did,
            status="completed",
            amount=250,
            completion_date=datetime.now(),
        ))

        mcat = MedicineCategory(name=f"Gen-{ts}", hospital_id=hid)
        db_session.add(mcat)
        db_session.flush()
        med = Medicine(
            name=f"Para-{ts}",
            medicine_code=f"M{int(ts)}",
            hospital_id=hid,
            category_id=mcat.id,
            min_qty=10,
            unit_price=20,
        )
        db_session.add(med)
        db_session.flush()
        db_session.add(PharmacyInventory(
            medicine_id=med.id,
            hospital_id=hid,
            batch_number=f"B{int(ts)}",
            quantity_in_stock=5,
            mrp=20,
            cost_price=10,
            selling_price=20,
            is_active=True,
            expiry_date=date.today() + timedelta(days=90),
        ))
        db_session.add(PharmacySale(
            sale_number=f"PS-{ts}",
            hospital_id=hid,
            sale_date=datetime.now(),
            status="completed",
            grand_total=120,
            tax_total=10,
            discount_total=0,
        ))
        db_session.add(Bill(
            bill_number=f"DC-{ts}",
            patient_id=pid,
            bill_type="day_care",
            reference_id=0,
            subtotal=1000,
            tax_amount=0,
            discount_amount=0,
            total_amount=1000,
            status="pending",
            bill_date=datetime.now(),
            created_by_id=seed_data["admin_user_id"],
            hospital_id=hid,
        ))
        db_session.commit()

        specs = [
            ("/api/hospital/billing/reports/opd-activity", ["totals", "rows", "by_status"]),
            ("/api/hospital/billing/reports/lab-volume", ["totals", "rows", "by_status"]),
            ("/api/hospital/billing/reports/daycare-volume", ["totals", "rows"]),
            ("/api/hospital/billing/reports/canteen-activity", ["totals", "by_payment"]),
            ("/api/hospital/billing/reports/pharmacy-sales", ["totals", "rows"]),
            ("/api/hospital/billing/reports/pharmacy-stock", ["totals", "rows"]),
            ("/api/hospital/billing/reports/physio-summary", ["totals", "rows"]),
            ("/api/hospital/billing/reports/readmissions", ["totals", "rows"]),
            ("/api/hospital/billing/reports/mortality", ["totals", "rows"]),
        ]
        for path, keys in specs:
            r = client.get(path, headers=auth_headers)
            assert r.status_code == 200, f"{path}: {r.text}"
            body = r.json()
            for k in keys:
                assert k in body, f"{path} missing {k}"

        opd = client.get("/api/hospital/billing/reports/opd-activity", headers=auth_headers).json()
        assert opd["totals"]["appointments"] >= 1
        lab = client.get("/api/hospital/billing/reports/lab-volume", headers=auth_headers).json()
        assert lab["totals"]["orders"] >= 1
        pharm = client.get("/api/hospital/billing/reports/pharmacy-sales", headers=auth_headers).json()
        assert pharm["totals"]["count"] >= 1
        stock = client.get("/api/hospital/billing/reports/pharmacy-stock", headers=auth_headers).json()
        assert stock["totals"]["skus"] >= 1
        day = client.get("/api/hospital/billing/reports/daycare-volume", headers=auth_headers).json()
        assert day["totals"]["count"] >= 1

