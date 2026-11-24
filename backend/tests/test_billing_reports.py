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

    def test_revenue_reports_include_lab_pharmacy_patients_and_referrals(
        self, client, auth_headers, db_session, seed_data,
    ):
        from datetime import timedelta
        from app.models.billing import Bill
        from app.models.lab import PatientLabOrder, LabTest, LabTestCategory, SampleType
        from app.models.patient import Patient
        from app.models.pharmacy import PharmacySale, PharmacySaleReturn
        from app.models.referral import Referral

        hid = seed_data["hospital_id"]
        pid = seed_data["patient_id"]
        did = seed_data["doctor_user_id"]
        ts = datetime.now().timestamp()

        def pick(body, doctor_id=None, name=None):
            for row in body.get("rows") or []:
                if doctor_id is not None and row.get("doctor_id") == doctor_id:
                    return row
                if name is not None and row.get("doctor_name") == name:
                    return row
            return {}

        def num(row, key):
            return float((row or {}).get(key) or 0)

        base_doc = client.get("/api/hospital/billing/reports/doctor-revenue", headers=auth_headers).json()
        base_ip = client.get(
            "/api/hospital/billing/reports/doctor-revenue?module=pharmacy_ip",
            headers=auth_headers,
        ).json()
        base_patient = client.get(
            f"/api/hospital/billing/reports/patient-revenue?patient_id={pid}",
            headers=auth_headers,
        ).json()
        base_doc_row = pick(base_doc, doctor_id=did)
        base_unassigned = pick(base_doc, name="(Unassigned)")
        base_ip_row = pick(base_ip, doctor_id=did)
        base_prow = (base_patient.get("rows") or [{}])[0]

        patient = db_session.query(Patient).filter_by(id=pid).one()
        previous_referred_by = patient.referred_by
        patient.referred_by = "City Clinic"

        cat = LabTestCategory(name=f"Rev-{ts}", hospital_id=hid, is_active=True)
        stype = SampleType(name=f"Serum-{ts}", hospital_id=hid, is_active=True)
        db_session.add_all([cat, stype])
        db_session.flush()
        test = LabTest(
            name=f"LFT-{ts}",
            test_code=f"LFT{int(ts)}",
            hospital_id=hid,
            category_id=cat.id,
            sample_type_id=stype.id,
            cost=250,
            is_active=True,
        )
        db_session.add(test)
        db_session.flush()

        admission_bill = Bill(
            bill_number=f"ADM-REV-{ts}",
            patient_id=pid,
            bill_type="admission",
            subtotal=1000,
            tax_amount=0,
            discount_amount=0,
            total_amount=1000,
            status="pending",
            bill_date=datetime.now(),
            created_by_id=seed_data["admin_user_id"],
            hospital_id=hid,
        )
        other_bill = Bill(
            bill_number=f"DC-REV-{ts}",
            patient_id=pid,
            bill_type="day_care",
            subtotal=75,
            tax_amount=0,
            discount_amount=0,
            total_amount=75,
            status="paid",
            bill_date=datetime.now(),
            created_by_id=seed_data["admin_user_id"],
            hospital_id=hid,
        )
        db_session.add_all([admission_bill, other_bill])
        db_session.flush()

        db_session.add(PatientLabOrder(
            order_number=f"LO-OPEN-{ts}",
            patient_id=pid,
            test_id=test.id,
            doctor_id=did,
            status="completed",
            amount=250,
            order_date=datetime.now(),
        ))
        db_session.add(PatientLabOrder(
            order_number=f"LO-IP-{ts}",
            patient_id=pid,
            test_id=test.id,
            doctor_id=did,
            status="completed",
            amount=800,
            order_date=datetime.now(),
            inpatient_bill_id=admission_bill.id,
        ))
        counter = PharmacySale(
            sale_number=f"PS-OP-{ts}",
            hospital_id=hid,
            sale_date=datetime.now(),
            status="completed",
            grand_total=120,
            patient_ip_id=patient.patient_id,
            patient_name="John Doe",
            doctor_name="Dr. Smith",
            billing_mode="cash_at_pharmacy",
        )
        ip_sale = PharmacySale(
            sale_number=f"PS-IP-{ts}",
            hospital_id=hid,
            sale_date=datetime.now(),
            status="completed",
            grand_total=400,
            patient_ip_id=patient.patient_id,
            doctor_name="Dr. Smith",
            billing_mode="inpatient_bill",
            inpatient_bill_id=admission_bill.id,
        )
        old_sale = PharmacySale(
            sale_number=f"PS-OLD-{ts}",
            hospital_id=hid,
            sale_date=datetime.now() - timedelta(days=120),
            status="completed",
            grand_total=999,
            patient_ip_id=patient.patient_id,
            doctor_name="Dr. Smith",
            billing_mode="cash_at_pharmacy",
        )
        db_session.add_all([counter, ip_sale, old_sale])
        db_session.flush()
        db_session.add(PharmacySaleReturn(
            return_number=f"RET-{ts}",
            return_date=date.today(),
            sale_id=counter.id,
            grand_total=20,
            status="confirmed",
            hospital_id=hid,
        ))
        referral = Referral(
            name="City Clinic",
            phone="9000011122",
            hospital_id=hid,
        )
        db_session.add(referral)
        db_session.commit()
        referral_id = referral.id

        doctor = client.get("/api/hospital/billing/reports/doctor-revenue", headers=auth_headers)
        assert doctor.status_code == 200, doctor.text
        doc_rows = doctor.json()["rows"]
        doc = next(row for row in doc_rows if row["doctor_id"] == did)
        assert num(doc, "lab_revenue") == num(base_doc_row, "lab_revenue") + 250
        assert num(doc, "lab_count") == num(base_doc_row, "lab_count") + 1
        assert num(doc, "pharmacy_revenue") == num(base_doc_row, "pharmacy_revenue") + 100
        assert num(doc, "pharmacy_count") == num(base_doc_row, "pharmacy_count") + 1
        assert num(doc, "pharmacy_ip_revenue") == num(base_doc_row, "pharmacy_ip_revenue") + 400
        assert num(doc, "pharmacy_ip_count") == num(base_doc_row, "pharmacy_ip_count") + 1
        assert num(doc, "admission_revenue") == num(base_doc_row, "admission_revenue")
        unassigned = next(row for row in doc_rows if row["doctor_name"] == "(Unassigned)")
        assert num(unassigned, "admission_revenue") == num(base_unassigned, "admission_revenue") + 600

        ip_only = client.get(
            "/api/hospital/billing/reports/doctor-revenue?module=pharmacy_ip",
            headers=auth_headers,
        )
        assert ip_only.status_code == 200, ip_only.text
        ip_doc = next(row for row in ip_only.json()["rows"] if row["doctor_id"] == did)
        assert num(ip_doc, "pharmacy_revenue") == num(base_ip_row, "pharmacy_revenue") + 400
        assert num(ip_doc, "lab_revenue") == 0

        patient_report = client.get(
            f"/api/hospital/billing/reports/patient-revenue?patient_id={pid}",
            headers=auth_headers,
        )
        assert patient_report.status_code == 200, patient_report.text
        prow = patient_report.json()["rows"][0]
        assert prow["patient_id"] == pid
        assert num(prow, "lab_revenue") == num(base_prow, "lab_revenue") + 250
        assert num(prow, "pharmacy_revenue") == num(base_prow, "pharmacy_revenue") + 100
        assert num(prow, "pharmacy_ip_revenue") == num(base_prow, "pharmacy_ip_revenue") + 400
        assert num(prow, "admission_revenue") == num(base_prow, "admission_revenue") + 600
        assert num(prow, "other_revenue") == num(base_prow, "other_revenue") + 75
        assert prow["total_revenue"] == round(
            num(prow, "consultation_revenue") + num(prow, "lab_revenue") + num(prow, "pharmacy_revenue")
            + num(prow, "pharmacy_ip_revenue") + num(prow, "admission_revenue") + num(prow, "other_revenue"),
            2,
        )

        referral_report = client.get(
            "/api/hospital/billing/reports/referral-revenue",
            headers=auth_headers,
        )
        assert referral_report.status_code == 200, referral_report.text
        city = next(row for row in referral_report.json()["rows"] if row["referral_id"] == referral_id)
        assert city["referral_name"] == "City Clinic"
        assert city["patient_count"] == 1
        assert city["pharmacy_revenue"] == prow["pharmacy_revenue"]
        assert city["pharmacy_ip_revenue"] == prow["pharmacy_ip_revenue"]
        assert city["lab_revenue"] == prow["lab_revenue"]
        assert city["admission_revenue"] == prow["admission_revenue"]
        assert city["total_revenue"] == round(
            city["consultation_revenue"] + city["lab_revenue"] + city["pharmacy_revenue"]
            + city["pharmacy_ip_revenue"] + city["admission_revenue"],
            2,
        )

        one = client.get(
            f"/api/hospital/billing/reports/referral-revenue?referral_id={referral_id}",
            headers=auth_headers,
        )
        assert one.status_code == 200, one.text
        assert len(one.json()["rows"]) == 1
        assert one.json()["totals"]["grand_total"] == city["total_revenue"]

        patient.referred_by = previous_referred_by
        db_session.delete(referral)
        db_session.commit()


class TestBillingDashboard:

    def test_dashboard_summarizes_billed_and_receipts(self, client, auth_headers, db_session, seed_data):
        bill = _bill_with_payment(
            db_session, seed_data, total=500, paid=200, method="cash", tax=0, subtotal=500,
        )
        today = date.today().isoformat()
        r = client.get(
            f"/api/hospital/billing/dashboard?date_from={today}&date_to={today}",
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["date_from"] == today
        assert body["totals"]["billed"] >= 500
        assert body["totals"]["collected"] >= 200
        assert body["totals"]["outstanding"] >= 300
        assert body["totals"]["net_receipts"] >= 200
        assert body["by_method"].get("cash", 0) >= 200
        assert any(row["number"] == bill.bill_number for row in body["recent"])
        assert any(row["number"] == bill.bill_number for row in body["outstanding_invoices"])
        assert "invoices" not in body

    def test_dashboard_forbidden_for_receptionist(self, client, seed_data):
        from app.utils.auth import create_access_token
        token = create_access_token(data={"sub": "testreceptionist"})
        r = client.get(
            "/api/hospital/billing/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403

