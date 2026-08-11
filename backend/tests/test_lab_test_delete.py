"""Lab test delete / recreate behavior.

Unused tests are hard-deleted. Tests with order history are soft-deleted
(is_active=False) and stripped from packages. Create/import/seed must not
treat soft-deleted codes as blocking duplicates.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.models.lab import (
    LabTest,
    LabTestCategory,
    LabTestParameter,
    LabTestPackage,
    LabTestPackageCategory,
    LabTestPackageItem,
    PatientLabOrder,
)
from app.models.user import User, UserRole
from app.utils.auth import create_access_token


@pytest.fixture()
def admin_headers(db_session, seed_data):
    role = db_session.query(UserRole).filter(UserRole.name == "lab_admin").first()
    if not role:
        role = UserRole(name="lab_admin", is_system_role=True)
        db_session.add(role)
        db_session.flush()
    user = db_session.query(User).filter(User.id == seed_data["admin_user_id"]).first()
    added = role not in user.roles
    if added:
        user.roles.append(role)
    db_session.commit()
    yield {"Authorization": f"Bearer {create_access_token(data={'sub': 'testadmin'})}"}
    if added:
        db_session.query(User).filter(User.id == seed_data["admin_user_id"]).first().roles.remove(role)
        db_session.commit()


def _unique(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}".upper()


def _make_category(db_session, hospital_id, name=None):
    cat = LabTestCategory(
        name=name or f"Cat-{uuid.uuid4().hex[:6]}",
        hospital_id=hospital_id,
        is_active=True,
    )
    db_session.add(cat)
    db_session.flush()
    return cat


def _make_test(db_session, hospital_id, *, code=None, name=None, cost=100.0):
    cat = _make_category(db_session, hospital_id)
    test = LabTest(
        test_code=code or _unique("T"),
        name=name or "Delete Me Test",
        category_id=cat.id,
        cost=cost,
        hospital_id=hospital_id,
        is_active=True,
    )
    db_session.add(test)
    db_session.flush()
    db_session.add(LabTestParameter(
        test_id=test.id, parameter_name="Hb", unit="g/dL", field_type="numeric",
    ))
    db_session.commit()
    db_session.refresh(test)
    return test


def test_hard_deletes_unused_test(client, admin_headers, db_session, seed_data):
    test = _make_test(db_session, seed_data["hospital_id"])
    tid = test.id

    resp = client.delete(f"/api/lab/tests/{tid}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted"] is True
    assert body["soft_deleted"] is False
    assert db_session.query(LabTest).filter(LabTest.id == tid).first() is None
    assert db_session.query(LabTestParameter).filter(LabTestParameter.test_id == tid).count() == 0


def test_soft_deletes_when_orders_exist(client, admin_headers, db_session, seed_data):
    test = _make_test(db_session, seed_data["hospital_id"])
    db_session.add(PatientLabOrder(
        order_number=_unique("ORD"),
        patient_id=seed_data["patient_id"],
        test_id=test.id,
        doctor_id=seed_data["doctor_user_id"],
        amount=test.cost,
        status="ordered",
        order_date=datetime.utcnow(),
    ))
    db_session.commit()

    resp = client.delete(f"/api/lab/tests/{test.id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted"] is False
    assert body["soft_deleted"] is True

    db_session.refresh(test)
    assert test.is_active is False


def test_delete_removes_package_membership(client, admin_headers, db_session, seed_data):
    test = _make_test(db_session, seed_data["hospital_id"])
    pkg_cat = LabTestPackageCategory(
        name=f"PkgCat-{uuid.uuid4().hex[:6]}",
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(pkg_cat)
    db_session.flush()
    pkg = LabTestPackage(
        package_code=_unique("PKG"),
        name="Combo",
        category_id=pkg_cat.id,
        package_price=200,
        actual_price=250,
        hospital_id=seed_data["hospital_id"],
    )
    db_session.add(pkg)
    db_session.flush()
    db_session.add(LabTestPackageItem(package_id=pkg.id, test_id=test.id))
    db_session.commit()

    resp = client.delete(f"/api/lab/tests/{test.id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert db_session.query(LabTestPackageItem).filter(
        LabTestPackageItem.test_id == test.id
    ).count() == 0


def test_create_reactivates_soft_deleted_code(client, admin_headers, db_session, seed_data):
    test = _make_test(db_session, seed_data["hospital_id"], code=_unique("R"))
    code = test.test_code
    category_id = test.category_id

    # Force soft-delete (as if it had history)
    test.is_active = False
    db_session.commit()

    resp = client.post("/api/lab/tests", headers=admin_headers, json={
        "test_code": code,
        "name": "Reborn Test",
        "category_id": category_id,
        "cost": 150,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == test.id
    assert body["name"] == "Reborn Test"
    assert body["is_active"] is True
    db_session.refresh(test)
    assert test.is_active is True
    assert test.cost == 150


def test_import_reactivates_inactive_code_even_on_skip(
    client, admin_headers, db_session, seed_data
):
    from tests.test_lab_test_import import _xlsx_bytes, _upload

    code = _unique("IMP")
    test = _make_test(db_session, seed_data["hospital_id"], code=code, name="Old Name")
    test.is_active = False
    db_session.commit()

    content = _xlsx_bytes([[code, "Imported Again", "ImportCat", "Blood", 333, "", "", ""]])
    resp = _upload(client, admin_headers, content, "reactivate.xlsx", on_duplicate="skip")
    assert resp.status_code == 200, resp.text
    summary = resp.json()
    assert summary["updated"] == 1
    assert summary["skipped"] == 0

    db_session.refresh(test)
    assert test.is_active is True
    assert test.name == "Imported Again"
    assert test.cost == 333
