"""Smoke tests for /api/admin/users/bulk-import-{doctors,nurses}.

We reuse the session-scoped seed_data fixture (which gives us a hospital,
super_admin, and a doctor role) and just ensure the nurse role exists.
Tests pick unique usernames so they don't collide with prior runs sharing the
session DB.
"""
from __future__ import annotations

import io
import uuid

import pytest


@pytest.fixture
def ensure_nurse_role(db_session):
    from app.models.user import UserRole
    if not db_session.query(UserRole).filter_by(name="nurse").first():
        db_session.add(UserRole(name="nurse", is_system_role=True))
        db_session.commit()


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6]}"


def test_doctor_bulk_import_happy_path(client, auth_headers, seed_data):
    uname = _unique("drbulk")
    csv = (
        "username,email,first_name,last_name,password,phone,"
        "specialization,license_number,qualification,consultation_fee_inr,"
        "inpatient_fee_inr,emergency_fee_inr,experience_years,"
        "default_consultation_duration\n"
        f"{uname},{uname}@h.in,Bulk,Doc,Welcome@123,9000099999,"
        "Cardiology,MCI-BULK,MBBS MD,800,2000,1500,12,15\n"
    )
    resp = client.post(
        "/api/admin/users/bulk-import-doctors",
        headers=auth_headers,
        files={"file": ("doctors.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["created"] == 1
    assert uname in body["usernames"]


def test_doctor_bulk_import_rejects_missing_columns(client, auth_headers, seed_data):
    csv = "username,email,first_name,last_name,password\nx,x@h.in,X,Y,Welcome@123\n"
    resp = client.post(
        "/api/admin/users/bulk-import-doctors",
        headers=auth_headers,
        files={"file": ("doctors.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["created"] == 0
    assert any("Missing required column" in e["message"] for e in body["errors"])


def test_nurse_bulk_import_happy_path(client, auth_headers, seed_data, ensure_nurse_role):
    uname = _unique("nbulk")
    csv = (
        "username,email,first_name,last_name,password,phone\n"
        f"{uname},{uname}@h.in,Bulk,Nurse,Welcome@123,9000088888\n"
    )
    resp = client.post(
        "/api/admin/users/bulk-import-nurses",
        headers=auth_headers,
        files={"file": ("nurses.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["created"] == 1


def test_bulk_import_blocks_on_duplicate(client, auth_headers, seed_data, ensure_nurse_role):
    # First create a nurse, then re-submit a CSV that re-uses the same username.
    uname = _unique("ndup")
    csv = (
        "username,email,first_name,last_name,password,phone\n"
        f"{uname},{uname}@h.in,N,One,Welcome@123,\n"
    )
    files = {"file": ("nurses.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")}
    first = client.post("/api/admin/users/bulk-import-nurses", headers=auth_headers, files=files)
    assert first.json()["ok"] is True

    files2 = {"file": ("nurses.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")}
    second = client.post("/api/admin/users/bulk-import-nurses", headers=auth_headers, files=files2)
    body = second.json()
    assert body["ok"] is False
    assert any("already exists" in e["message"] for e in body["errors"])


def test_sample_endpoint_serves_csv(client, auth_headers):
    for role, expected in (
        ("doctor", "specialization,license_number"),
        ("nurse", "username,email,first_name"),
    ):
        resp = client.get(f"/api/admin/users/bulk-import-sample/{role}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert expected in resp.text


def test_sample_endpoint_404_for_unknown_role(client, auth_headers):
    resp = client.get("/api/admin/users/bulk-import-sample/janitor", headers=auth_headers)
    assert resp.status_code == 404
