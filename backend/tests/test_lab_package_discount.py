"""Lab package booking with an extra operator discount at reception."""

import uuid

from app.models.lab import (
    LabTest,
    LabTestCategory,
    LabTestPackage,
    LabTestPackageCategory,
    LabTestPackageItem,
    PatientLabOrder,
)


def _make_package(db_session, seed_data, *, package_price=800.0, costs=(500.0, 500.0)):
    hospital_id = seed_data["hospital_id"]
    ts = uuid.uuid4().hex[:8]

    test_cat = db_session.query(LabTestCategory).filter_by(hospital_id=hospital_id).first()
    if not test_cat:
        test_cat = LabTestCategory(name="General", hospital_id=hospital_id)
        db_session.add(test_cat)
        db_session.flush()

    pkg_cat = db_session.query(LabTestPackageCategory).filter_by(hospital_id=hospital_id).first()
    if not pkg_cat:
        pkg_cat = LabTestPackageCategory(name="Health Check", hospital_id=hospital_id, is_active=True)
        db_session.add(pkg_cat)
        db_session.flush()

    tests = []
    for i, cost in enumerate(costs):
        t = LabTest(
            name=f"PkgTest-{i}-{ts}",
            test_code=f"PT{i}{ts}",
            category_id=test_cat.id,
            cost=cost,
            hospital_id=hospital_id,
            is_active=True,
        )
        db_session.add(t)
        tests.append(t)
    db_session.flush()

    actual = sum(costs)
    pkg = LabTestPackage(
        package_code=f"PKG{ts}",
        name=f"Discount Package {ts}",
        category_id=pkg_cat.id,
        package_price=package_price,
        actual_price=actual,
        hospital_id=hospital_id,
        is_active=True,
    )
    db_session.add(pkg)
    db_session.flush()
    for t in tests:
        db_session.add(LabTestPackageItem(package_id=pkg.id, test_id=t.id))
    db_session.commit()
    db_session.refresh(pkg)
    return pkg


def test_book_package_with_extra_discount(client, auth_headers, db_session, seed_data):
    pkg = _make_package(db_session, seed_data, package_price=800.0, costs=(500.0, 500.0))
    extra = 100.0
    expected_paid = 700.0  # 800 - 100

    res = client.post(
        f"/api/lab/packages/{pkg.id}/book",
        headers=auth_headers,
        json={
            "patient_id": seed_data["patient_id"],
            "payment_method": "cash",
            "discount_amount": extra,
            "force": True,
        },
    )
    assert res.status_code == 200, res.text
    assert res.headers.get("content-type", "").startswith("application/pdf")
    order_ids = [int(x) for x in (res.headers.get("x-order-ids") or "").split(",") if x]
    assert len(order_ids) == 2

    orders = (
        db_session.query(PatientLabOrder)
        .filter(PatientLabOrder.id.in_(order_ids))
        .all()
    )
    paid = round(sum(o.amount or 0 for o in orders), 2)
    assert paid == expected_paid
    assert all(o.payment_status == "paid" for o in orders)
    assert len({o.lab_bill_group_id for o in orders}) == 1

    # Reprint must preserve operator discount via stored order amounts
    group_id = orders[0].lab_bill_group_id
    reprint = client.get(f"/api/lab/bills/{group_id}/pdf", headers=auth_headers)
    assert reprint.status_code == 200

    regen = client.post(
        "/api/lab/orders/regenerate-bill",
        headers=auth_headers,
        json={"order_ids": order_ids},
    )
    assert regen.status_code == 200


def test_book_package_discount_capped_at_package_price(client, auth_headers, db_session, seed_data):
    pkg = _make_package(db_session, seed_data, package_price=500.0, costs=(300.0, 300.0))

    res = client.post(
        f"/api/lab/packages/{pkg.id}/book",
        headers=auth_headers,
        json={
            "patient_id": seed_data["patient_id"],
            "payment_method": "upi",
            "discount_amount": 9999,
            "force": True,
        },
    )
    assert res.status_code == 200, res.text
    order_ids = [int(x) for x in (res.headers.get("x-order-ids") or "").split(",") if x]
    orders = (
        db_session.query(PatientLabOrder)
        .filter(PatientLabOrder.id.in_(order_ids))
        .all()
    )
    assert round(sum(o.amount or 0 for o in orders), 2) == 0.0
