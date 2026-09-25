"""Lab dashboard stats: payment gate for technicians vs ungated admin unpaid OPD."""

from __future__ import annotations

import uuid
from datetime import datetime

from app.models.lab import (
    LabTest,
    LabTestCategory,
    LabTestPackage,
    LabTestPackageCategory,
    LabTestParameter,
    PatientLabOrder,
    SampleType,
)
from app.models.license import License
from app.models.permissions import RoleModulePermission
from app.models.system import SystemModule
from app.models.user import User, UserRole
from app.utils.auth import create_access_token, get_password_hash


def _enable_lab_access(db_session):
    mod = db_session.query(SystemModule).filter_by(module_name="lab").first()
    if mod is None:
        db_session.add(SystemModule(
            module_name="lab",
            display_name="Laboratory",
            is_enabled=True,
        ))
    elif not mod.is_enabled:
        mod.is_enabled = True

    lic = db_session.query(License).order_by(License.id.desc()).first()
    if lic and lic.features is not None:
        feats = list(lic.features or [])
        if "lab" not in feats:
            lic.features = feats + ["lab"]
    db_session.commit()


def _tech_headers(db_session, seed_data):
    _enable_lab_access(db_session)
    role = db_session.query(UserRole).filter_by(name="lab_technician").first()
    if role is None:
        role = UserRole(name="lab_technician", is_system_role=True)
        db_session.add(role)
        db_session.flush()

    existing_perm = db_session.query(RoleModulePermission).filter_by(
        role_id=role.id, module_name="lab",
    ).first()
    if existing_perm is None:
        db_session.add(RoleModulePermission(
            role_id=role.id,
            module_name="lab",
            permissions=["view_reports", "create_reports"],
        ))
    elif "view_reports" not in (existing_perm.permissions or []):
        existing_perm.permissions = list(existing_perm.permissions or []) + ["view_reports"]

    user = db_session.query(User).filter_by(username="labdashtech").first()
    if user is None:
        user = User(
            username="labdashtech",
            password_hash=get_password_hash("tech123"),
            email="labdashtech@test.com",
            first_name="Lab",
            last_name="Tech",
            role_id=role.id,
            hospital_id=seed_data["hospital_id"],
            is_active=True,
        )
        db_session.add(user)
        db_session.flush()
        user.roles.append(role)
    db_session.commit()
    token = create_access_token(data={"sub": user.username})
    return {"Authorization": f"Bearer {token}"}


def _stats(client, headers):
    res = client.get("/api/lab/stats", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _seed_catalog_and_orders(db_session, seed_data):
    suffix = uuid.uuid4().hex[:8]
    hid = seed_data["hospital_id"]

    category = LabTestCategory(name=f"Dash cat {suffix}", hospital_id=hid, is_active=True)
    db_session.add(category)
    db_session.flush()

    sample = SampleType(name=f"Dash sample {suffix}", hospital_id=hid, is_active=True)
    db_session.add(sample)
    db_session.flush()

    pkg_cat = LabTestPackageCategory(
        name=f"Dash pkg cat {suffix}", hospital_id=hid, is_active=True,
    )
    db_session.add(pkg_cat)
    db_session.flush()

    pkg = LabTestPackage(
        package_code=f"DP{suffix[:6]}",
        name=f"Dash package {suffix}",
        category_id=pkg_cat.id,
        package_price=100.0,
        actual_price=120.0,
        hospital_id=hid,
        is_active=True,
    )
    db_session.add(pkg)

    missing = LabTest(
        name=f"Dash missing params {suffix}",
        test_code=f"DM{suffix[:6]}",
        category_id=category.id,
        cost=10.0,
        hospital_id=hid,
        is_active=True,
        sample_type_id=sample.id,
    )
    db_session.add(missing)

    test = LabTest(
        name=f"Dash CBC {suffix}",
        test_code=f"DC{suffix[:6]}",
        category_id=category.id,
        cost=250.0,
        hospital_id=hid,
        is_active=True,
        sample_type_id=sample.id,
    )
    db_session.add(test)
    db_session.flush()

    db_session.add(LabTestParameter(
        test_id=test.id,
        parameter_name="Hemoglobin",
        field_type="numeric",
        display_order=1,
        is_active=True,
    ))

    def order(**kwargs):
        o = PatientLabOrder(
            order_number=f"LAB-D-{uuid.uuid4().hex[:10]}",
            patient_id=seed_data["patient_id"],
            test_id=test.id,
            doctor_id=seed_data["doctor_user_id"],
            amount=250.0,
            **kwargs,
        )
        db_session.add(o)
        return o

    order(status="ordered", payment_status="pending", priority="normal")
    order(status="ordered", payment_status="paid", priority="normal")
    order(
        status="ordered",
        payment_status="pending",
        priority="normal",
        admission_id=1,
    )
    order(status="processing", payment_status="paid", priority="stat")
    order(
        status="completed",
        payment_status="paid",
        priority="normal",
        completion_date=datetime.now(),
    )
    db_session.commit()


def test_lab_stats_technician_payment_gate_vs_admin_unpaid(
    client, db_session, seed_data, auth_headers,
):
    before = _stats(client, auth_headers)
    _seed_catalog_and_orders(db_session, seed_data)
    admin = _stats(client, auth_headers)
    tech = _stats(client, _tech_headers(db_session, seed_data))

    assert admin["unpaid_opd_count"] == before["unpaid_opd_count"] + 1
    assert admin["ordered_count"] == before["ordered_count"] + 3
    assert admin["ipd_pending_count"] == before["ipd_pending_count"] + 1
    assert admin["urgent_count"] == before["urgent_count"] + 1
    assert admin["completed_today"] == before["completed_today"] + 1
    assert admin["orders_today"] == before["orders_today"] + 5
    assert admin["tests_missing_parameters"] == before["tests_missing_parameters"] + 1
    assert admin["total_sample_types"] == before["total_sample_types"] + 1
    assert admin["total_packages"] == before["total_packages"] + 1

    # Technician pipeline hides unpaid OPD; IPD still counts; unpaid card is ungated.
    assert tech["ordered_count"] == admin["ordered_count"] - admin["unpaid_opd_count"]
    assert tech["pending_orders"] == admin["pending_orders"] - admin["unpaid_opd_count"]
    assert tech["ipd_pending_count"] == admin["ipd_pending_count"]
    assert tech["unpaid_opd_count"] == admin["unpaid_opd_count"]
    assert tech["tests_missing_parameters"] == admin["tests_missing_parameters"]
    assert tech["completed_today"] == admin["completed_today"]


def test_lab_technician_can_read_stats(client, db_session, seed_data, auth_headers):
    headers = _tech_headers(db_session, seed_data)
    body = _stats(client, headers)
    for key in (
        "ordered_count", "collected_count", "processing_count", "urgent_count",
        "orders_today", "ipd_pending_count", "unpaid_opd_count",
        "total_sample_types", "total_packages", "tests_missing_parameters",
        "pending_orders", "completed_today",
    ):
        assert key in body
        assert isinstance(body[key], int)
