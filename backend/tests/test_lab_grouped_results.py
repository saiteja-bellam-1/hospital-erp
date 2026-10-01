"""Grouped lab result entry for tests that share one collected sample."""
from datetime import datetime

import pytest

from app.models.lab import (
    LabTestCategory, LabTest, LabTestParameter, PatientLabOrder, LabReport,
)
from app.models.user import UserRole, User
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


_seq = 0


def _stamp():
    global _seq
    _seq += 1
    return f"{datetime.now().strftime('%H%M%S%f')}{_seq}"


def _make_test(db, hospital_id, category, name):
    test = LabTest(
        test_code=f"G-{_stamp()}",
        name=name,
        category_id=category.id,
        cost=50.0,
        hospital_id=hospital_id,
        sample_type="Blood",
        is_active=True,
    )
    db.add(test)
    db.flush()
    param = LabTestParameter(
        test_id=test.id,
        parameter_name=f"{name} value",
        unit="mg/dL",
        field_type="numeric",
        reference_min_default=1,
        reference_max_default=10,
        display_order=0,
        is_active=True,
    )
    db.add(param)
    db.flush()
    return test, param


def _make_order(db, patient_id, test, sample_id, status="collected"):
    order = PatientLabOrder(
        order_number=f"LAB-{_stamp()}",
        patient_id=patient_id,
        test_id=test.id,
        status=status,
        amount=50.0,
        payment_status="paid",
        sample_id=sample_id,
    )
    db.add(order)
    db.flush()
    return order


@pytest.fixture()
def shared_sample(db_session, seed_data):
    hospital_id = seed_data["hospital_id"]
    cat = LabTestCategory(name=f"Grp-{_stamp()}", hospital_id=hospital_id)
    db_session.add(cat)
    db_session.flush()
    test_a, param_a = _make_test(db_session, hospital_id, cat, "Glucose")
    test_b, param_b = _make_test(db_session, hospital_id, cat, "Urea")
    test_c, param_c = _make_test(db_session, hospital_id, cat, "Creatinine")
    sample_id = f"S-{_stamp()}"
    order_a = _make_order(db_session, seed_data["patient_id"], test_a, sample_id, "collected")
    order_b = _make_order(db_session, seed_data["patient_id"], test_b, sample_id, "processing")
    other = _make_order(db_session, seed_data["patient_id"], test_c, f"S-other-{_stamp()}", "collected")
    db_session.commit()
    return {
        "sample_id": sample_id,
        "a": order_a,
        "b": order_b,
        "other": other,
        "param_a": param_a,
        "param_b": param_b,
        "param_c": param_c,
    }


def test_grouped_entry_form_returns_open_siblings_on_same_sample(
    client, admin_headers, shared_sample
):
    res = client.get(
        f"/api/lab/orders/{shared_sample['a'].id}/grouped-entry-form",
        headers=admin_headers,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["sample_id"] == shared_sample["sample_id"]
    ids = [t["order_id"] for t in body["tests"]]
    assert ids[0] == shared_sample["a"].id
    assert set(ids) == {shared_sample["a"].id, shared_sample["b"].id}
    assert shared_sample["other"].id not in ids
    glucose = next(t for t in body["tests"] if t["order_id"] == shared_sample["a"].id)
    assert glucose["parameters"][0]["id"] == shared_sample["param_a"].id


def test_grouped_entry_form_drops_completed_sibling(client, db_session, admin_headers, shared_sample):
    report = LabReport(
        order_id=shared_sample["b"].id,
        result_values=[{"parameter_id": shared_sample["param_b"].id, "value": "4"}],
        technician_id=1,
    )
    shared_sample["b"].status = "completed"
    db_session.add(report)
    db_session.commit()

    res = client.get(
        f"/api/lab/orders/{shared_sample['a'].id}/grouped-entry-form",
        headers=admin_headers,
    )
    assert res.status_code == 200, res.text
    ids = [t["order_id"] for t in res.json()["tests"]]
    assert ids == [shared_sample["a"].id]


def test_grouped_entry_form_ignores_orders_not_yet_collected(
    client, db_session, seed_data, admin_headers, shared_sample
):
    waiting = _make_order(
        db_session,
        seed_data["patient_id"],
        db_session.query(LabTest).filter(LabTest.id == shared_sample["a"].test_id).first(),
        shared_sample["sample_id"],
        status="ordered",
    )
    db_session.commit()
    res = client.get(
        f"/api/lab/orders/{shared_sample['a'].id}/grouped-entry-form",
        headers=admin_headers,
    )
    assert res.status_code == 200, res.text
    ids = [t["order_id"] for t in res.json()["tests"]]
    assert waiting.id not in ids


def test_grouped_submit_writes_one_report_per_test(client, db_session, admin_headers, shared_sample):
    payload = {
        "orders": [
            {
                "order_id": shared_sample["a"].id,
                "results": [{
                    "parameter_id": shared_sample["param_a"].id,
                    "value": "5.5",
                    "remarks": "ok",
                    "manual_abnormal": False,
                }],
                "interpretation": "Glucose note",
            },
            {
                "order_id": shared_sample["b"].id,
                "results": [{
                    "parameter_id": shared_sample["param_b"].id,
                    "value": "20",
                    "remarks": "",
                    "manual_abnormal": True,
                }],
                "interpretation": "Urea note",
            },
        ]
    }
    res = client.post("/api/lab/orders/grouped-results", json=payload, headers=admin_headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["report_ids"]) == 2

    db_session.expire_all()
    for order_id, expected_value, note in (
        (shared_sample["a"].id, "5.5", "Glucose note"),
        (shared_sample["b"].id, "20", "Urea note"),
    ):
        order = db_session.query(PatientLabOrder).filter(PatientLabOrder.id == order_id).one()
        assert order.status == "completed"
        report = db_session.query(LabReport).filter(LabReport.order_id == order_id).one()
        assert report.interpretation == note
        assert report.result_values[0]["value"] == expected_value

    other = db_session.query(PatientLabOrder).filter(
        PatientLabOrder.id == shared_sample["other"].id
    ).one()
    assert other.status == "collected"
    assert db_session.query(LabReport).filter(LabReport.order_id == other.id).first() is None


def test_grouped_submit_rejects_partial_set_and_writes_nothing(
    client, db_session, admin_headers, shared_sample
):
    payload = {
        "orders": [{
            "order_id": shared_sample["a"].id,
            "results": [{
                "parameter_id": shared_sample["param_a"].id,
                "value": "5",
                "manual_abnormal": False,
            }],
        }]
    }
    res = client.post("/api/lab/orders/grouped-results", json=payload, headers=admin_headers)
    assert res.status_code == 400, res.text
    assert "every open test" in res.json()["detail"]

    db_session.expire_all()
    for order_id, status in (
        (shared_sample["a"].id, "collected"),
        (shared_sample["b"].id, "processing"),
    ):
        order = db_session.query(PatientLabOrder).filter(PatientLabOrder.id == order_id).one()
        assert order.status == status
        assert db_session.query(LabReport).filter(LabReport.order_id == order_id).first() is None


def test_grouped_submit_rejects_blank_section(client, db_session, admin_headers, shared_sample):
    payload = {
        "orders": [
            {
                "order_id": shared_sample["a"].id,
                "results": [{
                    "parameter_id": shared_sample["param_a"].id,
                    "value": "5",
                    "manual_abnormal": False,
                }],
            },
            {
                "order_id": shared_sample["b"].id,
                "results": [{
                    "parameter_id": shared_sample["param_b"].id,
                    "value": "   ",
                    "manual_abnormal": False,
                }],
            },
        ]
    }
    res = client.post("/api/lab/orders/grouped-results", json=payload, headers=admin_headers)
    assert res.status_code == 400, res.text
    assert "Urea" in res.json()["detail"]
    db_session.expire_all()
    assert db_session.query(LabReport).filter(
        LabReport.order_id == shared_sample["a"].id
    ).first() is None


def test_grouped_submit_rejects_parameter_from_another_test(
    client, admin_headers, shared_sample
):
    payload = {
        "orders": [
            {
                "order_id": shared_sample["a"].id,
                "results": [{
                    "parameter_id": shared_sample["param_b"].id,
                    "value": "5",
                    "manual_abnormal": False,
                }],
            },
            {
                "order_id": shared_sample["b"].id,
                "results": [{
                    "parameter_id": shared_sample["param_b"].id,
                    "value": "4",
                    "manual_abnormal": False,
                }],
            },
        ]
    }
    res = client.post("/api/lab/orders/grouped-results", json=payload, headers=admin_headers)
    assert res.status_code == 400, res.text
    assert "does not belong" in res.json()["detail"]


def test_grouped_submit_rejects_mixed_samples(client, admin_headers, shared_sample):
    payload = {
        "orders": [
            {
                "order_id": shared_sample["a"].id,
                "results": [{
                    "parameter_id": shared_sample["param_a"].id,
                    "value": "5",
                    "manual_abnormal": False,
                }],
            },
            {
                "order_id": shared_sample["other"].id,
                "results": [{
                    "parameter_id": shared_sample["param_c"].id,
                    "value": "1",
                    "manual_abnormal": False,
                }],
            },
        ]
    }
    res = client.post("/api/lab/orders/grouped-results", json=payload, headers=admin_headers)
    assert res.status_code == 400, res.text
    assert "one collected sample" in res.json()["detail"]


def test_single_result_endpoint_still_completes_one_order(
    client, db_session, admin_headers, shared_sample
):
    res = client.post(
        f"/api/lab/orders/{shared_sample['a'].id}/results",
        json={
            "results": [{
                "parameter_id": shared_sample["param_a"].id,
                "value": "7",
                "manual_abnormal": False,
            }],
            "interpretation": "solo",
        },
        headers=admin_headers,
    )
    assert res.status_code == 200, res.text
    db_session.expire_all()
    done = db_session.query(PatientLabOrder).filter(
        PatientLabOrder.id == shared_sample["a"].id
    ).one()
    still_open = db_session.query(PatientLabOrder).filter(
        PatientLabOrder.id == shared_sample["b"].id
    ).one()
    assert done.status == "completed"
    assert still_open.status == "processing"
