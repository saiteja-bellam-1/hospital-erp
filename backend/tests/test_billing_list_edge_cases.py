"""Billing list + lab bill-number edge cases.

Covers:
1. Concurrent-style lab bookings get distinct lab_bill_numbers (no same-ref dupes)
2. Rapid double-submit of reception book / package book is rejected
3. Pay-all is idempotent (second call finds nothing pending)
4. Single-order pay is idempotent
5. Central billing list hides consolidated source rows (keeps CB-* only)
6. Central billing list hides inpatient lab orders (charged on admission bill)
7. Two same-second groups never share a displayed reference in GET /billing
"""

from datetime import datetime, date, time
import uuid

from app.routes.lab import _new_lab_bill_group


def _ensure_lab_category(db_session, hospital_id):
    from app.models.lab import LabTestCategory
    cat = db_session.query(LabTestCategory).filter_by(hospital_id=hospital_id).first()
    if not cat:
        cat = LabTestCategory(name="Hematology", hospital_id=hospital_id)
        db_session.add(cat)
        db_session.commit()
        db_session.refresh(cat)
    return cat


def _make_test(db_session, seed_data, name_prefix="CBC"):
    from app.models.lab import LabTest
    cat = _ensure_lab_category(db_session, seed_data["hospital_id"])
    ts = uuid.uuid4().hex[:8]
    test = LabTest(
        name=f"{name_prefix}-{ts}",
        test_code=f"{name_prefix[:3].upper()}{ts}",
        category_id=cat.id,
        cost=250.0,
        hospital_id=seed_data["hospital_id"],
        is_active=True,
    )
    db_session.add(test)
    db_session.commit()
    db_session.refresh(test)
    return test


def _make_opd_lab_order(
    db_session,
    seed_data,
    *,
    payment_status="pending",
    admission_id=None,
    lab_bill_group_id=None,
    lab_bill_number=None,
    amount=250.0,
):
    from app.models.lab import PatientLabOrder
    test = _make_test(db_session, seed_data)
    order = PatientLabOrder(
        order_number=f"LAB-{uuid.uuid4().hex[:8].upper()}",
        patient_id=seed_data["patient_id"],
        test_id=test.id,
        doctor_id=seed_data["doctor_user_id"],
        status="ordered",
        amount=amount,
        payment_status=payment_status,
        order_date=datetime.now(),
        admission_id=admission_id,
        lab_bill_group_id=lab_bill_group_id,
        lab_bill_number=lab_bill_number,
    )
    db_session.add(order)
    db_session.commit()
    db_session.refresh(order)
    return order


def _make_appt(db_session, seed_data, *, payment_status="pending", fee=300.0):
    from app.models.outpatient import Appointment
    a = Appointment(
        appointment_number=f"APT-{uuid.uuid4().hex[:8].upper()}",
        patient_id=seed_data["patient_id"],
        doctor_id=seed_data["doctor_user_id"],
        appointment_date=datetime.now(),
        appointment_time=time(10, 0),
        consultation_fee=fee,
        registration_fee=0,
        final_amount=fee,
        payment_status=payment_status,
        created_at=datetime.now(),
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def _billing_list(client, auth_headers, **params):
    today = date.today().isoformat()
    q = {"date_from": today, "date_to": today, **params}
    r = client.get("/api/hospital/billing", params=q, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["bills"]


class TestLabBillNumberUniqueness:
    def test_helper_produces_unique_numbers_same_second(self):
        nums = {_new_lab_bill_group("LB")[1] for _ in range(50)}
        assert len(nums) == 50
        for n in nums:
            assert n.startswith("LB-")
            parts = n.split("-")
            assert len(parts) == 3
            assert len(parts[2]) == 8

    def test_two_forced_bookings_get_distinct_numbers_when_spaced(
        self, client, auth_headers, db_session, seed_data, monkeypatch
    ):
        """If rapid-guard is bypassed (spaced bookings), numbers still differ."""
        from app.routes import lab as lab_routes

        monkeypatch.setattr(lab_routes, "_RAPID_BOOK_WINDOW_SECONDS", 0.0)

        t1 = _make_test(db_session, seed_data, "UNIQ1")
        t2 = _make_test(db_session, seed_data, "UNIQ2")

        r1 = client.post(
            "/api/lab/orders/reception-book",
            json={
                "patient_id": seed_data["patient_id"],
                "test_ids": [t1.id],
                "payment_method": "cash",
                "force": True,
            },
            headers=auth_headers,
        )
        assert r1.status_code == 200, r1.text

        r2 = client.post(
            "/api/lab/orders/reception-book",
            json={
                "patient_id": seed_data["patient_id"],
                "test_ids": [t2.id],
                "payment_method": "cash",
                "force": True,
            },
            headers=auth_headers,
        )
        assert r2.status_code == 200, r2.text

        from app.models.lab import PatientLabOrder
        db_session.expire_all()
        o1 = (
            db_session.query(PatientLabOrder)
            .filter_by(patient_id=seed_data["patient_id"], test_id=t1.id)
            .order_by(PatientLabOrder.id.desc())
            .first()
        )
        o2 = (
            db_session.query(PatientLabOrder)
            .filter_by(patient_id=seed_data["patient_id"], test_id=t2.id)
            .order_by(PatientLabOrder.id.desc())
            .first()
        )
        assert o1.lab_bill_number and o2.lab_bill_number
        assert o1.lab_bill_number != o2.lab_bill_number
        assert o1.lab_bill_group_id != o2.lab_bill_group_id

    def test_same_second_collision_pattern_no_longer_dupes_in_list(
        self, client, auth_headers, db_session, seed_data
    ):
        """Simulate the old bug: two groups, same timestamp-style number → two list rows.
        With the new allocator, planting two groups with distinct numbers yields two refs;
        planting the OLD colliding pattern still shows two rows (different ids) — the
        fix is that new bookings never create that pattern.
        """
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        # Old colliding pattern (what we must not generate anymore)
        old_num = f"LB-{stamp}-{seed_data['patient_id']}"
        g1, g2 = str(uuid.uuid4()), str(uuid.uuid4())
        _make_opd_lab_order(
            db_session, seed_data,
            payment_status="paid",
            lab_bill_group_id=g1,
            lab_bill_number=old_num,
        )
        _make_opd_lab_order(
            db_session, seed_data,
            payment_status="paid",
            lab_bill_group_id=g2,
            lab_bill_number=old_num,
        )
        bills = _billing_list(client, auth_headers, bill_type="lab")
        refs = [b["reference"] for b in bills if b.get("reference") == old_num]
        # Legacy colliding data still surfaces as two rows (different LBG ids) —
        # documenting the historical bug shape. New bookings use unique numbers.
        assert len(refs) == 2

        # New allocator never produces that shape
        n1 = _new_lab_bill_group("LB")[1]
        n2 = _new_lab_bill_group("LB")[1]
        assert n1 != n2
        assert n1.split("-")[-1] != str(seed_data["patient_id"])


class TestLabDoubleSubmitGuards:
    def test_rapid_repeat_reception_book_rejected(
        self, client, auth_headers, db_session, seed_data
    ):
        test = _make_test(db_session, seed_data, "RAPID")
        payload = {
            "patient_id": seed_data["patient_id"],
            "test_ids": [test.id],
            "payment_method": "cash",
            "force": True,
        }
        r1 = client.post("/api/lab/orders/reception-book", json=payload, headers=auth_headers)
        assert r1.status_code == 200, r1.text

        r2 = client.post("/api/lab/orders/reception-book", json=payload, headers=auth_headers)
        assert r2.status_code == 409, r2.text
        detail = r2.json()["detail"]
        assert "moments ago" in (detail.get("message") if isinstance(detail, dict) else str(detail))

        from app.models.lab import PatientLabOrder
        db_session.expire_all()
        count = (
            db_session.query(PatientLabOrder)
            .filter_by(patient_id=seed_data["patient_id"], test_id=test.id)
            .filter(PatientLabOrder.status != "cancelled")
            .count()
        )
        assert count == 1

    def test_pay_all_second_call_is_noop(
        self, client, auth_headers, db_session, seed_data
    ):
        o1 = _make_opd_lab_order(db_session, seed_data, payment_status="pending", amount=100)
        o2 = _make_opd_lab_order(db_session, seed_data, payment_status="pending", amount=150)

        r1 = client.post(
            f"/api/lab/orders/patient/{seed_data['patient_id']}/bill",
            json={"payment_method": "cash"},
            headers=auth_headers,
        )
        assert r1.status_code == 200, r1.text

        db_session.expire_all()
        from app.models.lab import PatientLabOrder
        for oid in (o1.id, o2.id):
            row = db_session.query(PatientLabOrder).get(oid)
            assert row.payment_status == "paid"
            assert row.lab_bill_group_id
            assert row.lab_bill_number
        shared_num = db_session.query(PatientLabOrder).get(o1.id).lab_bill_number
        assert db_session.query(PatientLabOrder).get(o2.id).lab_bill_number == shared_num

        r2 = client.post(
            f"/api/lab/orders/patient/{seed_data['patient_id']}/bill",
            json={"payment_method": "cash"},
            headers=auth_headers,
        )
        assert r2.status_code == 404

    def test_single_pay_second_call_rejected(
        self, client, auth_headers, db_session, seed_data
    ):
        order = _make_opd_lab_order(db_session, seed_data, payment_status="pending")
        r1 = client.put(
            f"/api/lab/orders/{order.id}/payment",
            json={"payment_method": "upi"},
            headers=auth_headers,
        )
        assert r1.status_code == 200, r1.text
        assert r1.json()["lab_bill_number"]

        r2 = client.put(
            f"/api/lab/orders/{order.id}/payment",
            json={"payment_method": "upi"},
            headers=auth_headers,
        )
        assert r2.status_code == 400
        assert "already" in r2.json()["detail"].lower()


class TestBillingListExclusions:
    def test_consolidated_sources_hidden_cb_shown(
        self, client, auth_headers, db_session, seed_data
    ):
        apt = _make_appt(db_session, seed_data, payment_status="pending", fee=200)
        lab = _make_opd_lab_order(db_session, seed_data, payment_status="pending", amount=300)

        r = client.post(
            "/api/hospital/billing/consolidate",
            json={
                "patient_id": seed_data["patient_id"],
                "consultation_ids": [apt.id],
                "lab_order_ids": [lab.id],
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        cb_id = r.json()["bill_id"]
        cb_number = r.json()["bill_number"]

        bills = _billing_list(client, auth_headers)
        ids = {b["id"] for b in bills}
        refs = {b["reference"] for b in bills}

        assert f"APT-{apt.id}" not in ids
        assert f"LAB-{lab.id}" not in ids
        # Ungrouped pending would be LAB-*; after consolidate status changes
        assert f"CONS-{cb_id}" in ids
        assert cb_number in refs

    def test_inpatient_lab_orders_excluded_from_lab_tab(
        self, client, auth_headers, db_session, seed_data
    ):
        from app.models.inpatient import Admission, RoomManagement

        room = RoomManagement(
            room_number=f"EDGE-{uuid.uuid4().hex[:4]}",
            room_type="general",
            floor="1",
            department="General",
            bed_count=1,
            available_beds=1,
            room_charge_per_day=1000.0,
            hospital_id=seed_data["hospital_id"],
            is_active=True,
        )
        db_session.add(room)
        db_session.commit()
        db_session.refresh(room)

        adm = Admission(
            admission_number=f"ADM-{uuid.uuid4().hex[:8].upper()}",
            patient_id=seed_data["patient_id"],
            admitting_doctor_id=seed_data["doctor_user_id"],
            room_id=room.id,
            admission_date=datetime.now(),
            admission_type="elective",
            status="admitted",
        )
        db_session.add(adm)
        db_session.commit()
        db_session.refresh(adm)

        ip_order = _make_opd_lab_order(
            db_session, seed_data,
            payment_status="pending",
            admission_id=adm.id,
            amount=400,
        )
        opd_order = _make_opd_lab_order(
            db_session, seed_data,
            payment_status="paid",
            lab_bill_group_id=str(uuid.uuid4()),
            lab_bill_number=_new_lab_bill_group("LB")[1],
            amount=250,
        )

        bills = _billing_list(client, auth_headers, bill_type="lab")
        lab_ids = {b["id"] for b in bills}
        lab_bill_ids = {b.get("bill_id") for b in bills}

        assert f"LAB-{ip_order.id}" not in lab_ids
        assert ip_order.id not in lab_bill_ids
        assert f"LBG-{opd_order.lab_bill_group_id}" in lab_ids

    def test_distinct_new_lab_groups_appear_once_each(
        self, client, auth_headers, db_session, seed_data
    ):
        g1, n1 = _new_lab_bill_group("LB")
        g2, n2 = _new_lab_bill_group("LB")
        assert n1 != n2
        _make_opd_lab_order(
            db_session, seed_data,
            payment_status="paid",
            lab_bill_group_id=g1,
            lab_bill_number=n1,
        )
        _make_opd_lab_order(
            db_session, seed_data,
            payment_status="paid",
            lab_bill_group_id=g2,
            lab_bill_number=n2,
        )
        bills = _billing_list(client, auth_headers, bill_type="lab")
        matching = [b for b in bills if b["reference"] in (n1, n2)]
        assert len(matching) == 2
        assert {b["reference"] for b in matching} == {n1, n2}
        assert {b["id"] for b in matching} == {f"LBG-{g1}", f"LBG-{g2}"}
