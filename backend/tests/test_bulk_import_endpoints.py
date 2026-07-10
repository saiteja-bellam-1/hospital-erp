"""Smoke tests for /api/admin/users/bulk-import-{doctors,nurses,staff}.

We reuse the session-scoped seed_data fixture (which gives us a hospital,
super_admin, and a doctor role) and ensure nurse / staff roles exist.
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


@pytest.fixture
def ensure_staff_roles(db_session):
    """Seed roles referenced by the staff CSV importer (and additional_roles)."""
    from app.models.user import UserRole
    from app.services.user_csv_import import INSTALLER_ALLOWED_ROLES

    for name in INSTALLER_ALLOWED_ROLES:
        if not db_session.query(UserRole).filter_by(name=name).first():
            db_session.add(UserRole(name=name, is_system_role=True))
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


@pytest.fixture
def ensure_valid_license(db_session):
    """Staff logins require a valid license (super_admin bypasses this)."""
    from datetime import datetime, timedelta
    from app.models.license import License

    if db_session.query(License).first():
        return
    db_session.add(License(
        license_id="TEST-LIC",
        hospital_id="TEST01",
        hospital_name="Test Hospital",
        plan="standard",
        max_users=100,
        features=[],
        issued_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=365),
        status="active",
        raw_license_data="",
    ))
    db_session.commit()


def _import_staff_csv(client, auth_headers, rows):
    """Helper: POST a staff CSV built from (username, email, role, additional_roles) tuples."""
    lines = ["username,email,first_name,last_name,role,password,phone,additional_roles"]
    for username, email, role, extras in rows:
        lines.append(
            f"{username},{email},First,Last,{role},Welcome@123,9000000001,{extras}"
        )
    csv = "\n".join(lines) + "\n"
    return client.post(
        "/api/admin/users/bulk-import-staff",
        headers=auth_headers,
        files={"file": ("staff.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )


def test_staff_bulk_import_happy_path(client, auth_headers, seed_data, ensure_staff_roles):
    uname = _unique("sbill")
    uname2 = _unique("srec")
    csv = (
        "username,email,first_name,last_name,role,password,phone,additional_roles\n"
        f"{uname},{uname}@h.in,Bulk,Bill,billing_admin,Welcome@123,9000077777,\n"
        f"{uname2},{uname2}@h.in,Bulk,Rec,receptionist,Welcome@123,,frontdesk\n"
    )
    resp = client.post(
        "/api/admin/users/bulk-import-staff",
        headers=auth_headers,
        files={"file": ("staff.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["created"] == 2
    assert uname in body["usernames"]
    assert uname2 in body["usernames"]


def test_staff_bulk_import_rejects_doctor_role(client, auth_headers, seed_data, ensure_staff_roles):
    uname = _unique("sbaddoc")
    csv = (
        "username,email,first_name,last_name,role,password,phone,additional_roles\n"
        f"{uname},{uname}@h.in,Bad,Doc,doctor,Welcome@123,,\n"
    )
    resp = client.post(
        "/api/admin/users/bulk-import-staff",
        headers=auth_headers,
        files={"file": ("staff.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["created"] == 0
    assert any("not allowed" in e["message"].lower() or "doctor" in e["message"].lower()
               for e in body["errors"])


def test_sample_endpoint_serves_csv(client, auth_headers):
    for role, expected in (
        ("doctor", "specialization,license_number"),
        ("nurse", "username,email,first_name"),
        ("staff", "role,password"),
    ):
        resp = client.get(f"/api/admin/users/bulk-import-sample/{role}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert expected in resp.text


def test_sample_endpoint_404_for_unknown_role(client, auth_headers):
    resp = client.get("/api/admin/users/bulk-import-sample/janitor", headers=auth_headers)
    assert resp.status_code == 404


def test_imported_staff_visible_in_user_list(client, auth_headers, seed_data, ensure_staff_roles):
    """Imported staff users must appear in the admin user list with correct roles."""
    uname = _unique("slist")
    resp = _import_staff_csv(
        client,
        auth_headers,
        [(uname, f"{uname}@h.in", "billing_admin", "")],
    )
    assert resp.json()["ok"] is True

    users_resp = client.get("/api/admin/users", headers=auth_headers)
    assert users_resp.status_code == 200
    users = users_resp.json()
    match = next((u for u in users if u["username"] == uname), None)
    assert match is not None, f"{uname} not found in user list"
    assert match["email"] == f"{uname}@h.in"
    assert match["first_name"] == "First"
    assert match["last_name"] == "Last"
    assert match["is_active"] is True
    assert match["user_role"]["name"] == "billing_admin"


def test_imported_staff_with_additional_roles_in_user_list(
    client, auth_headers, seed_data, ensure_staff_roles, ensure_valid_license,
):
    uname = _unique("sroles")
    resp = _import_staff_csv(
        client,
        auth_headers,
        [(uname, f"{uname}@h.in", "receptionist", "frontdesk")],
    )
    assert resp.json()["ok"] is True

    users_resp = client.get("/api/admin/users", headers=auth_headers)
    match = next((u for u in users_resp.json() if u["username"] == uname), None)
    assert match is not None
    # Primary role lives on user_role; user_roles lists only M2M extras.
    assert match["user_role"]["name"] == "receptionist"
    role_names = {r["name"] for r in match["user_roles"]}
    assert "frontdesk" in role_names

    login_resp = client.post(
        "/api/auth/login",
        json={"username": uname, "password": "Welcome@123"},
    )
    assert login_resp.status_code == 200, login_resp.text
    login_roles = set(login_resp.json()["user"]["roles"])
    assert "receptionist" in login_roles
    assert "frontdesk" in login_roles


def test_imported_staff_can_login_with_csv_password(
    client, auth_headers, seed_data, ensure_staff_roles, ensure_valid_license,
):
    """Imported staff must authenticate with the CSV password and return correct roles."""
    uname = _unique("slogin")
    resp = _import_staff_csv(
        client,
        auth_headers,
        [(uname, f"{uname}@h.in", "lab_technician", "")],
    )
    assert resp.json()["ok"] is True

    login_resp = client.post(
        "/api/auth/login",
        json={"username": uname, "password": "Welcome@123"},
    )
    assert login_resp.status_code == 200, login_resp.text
    body = login_resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["username"] == uname
    assert body["user"]["role"] == "lab_technician"
    assert "lab_technician" in body["user"]["roles"]
    assert body["user"]["must_change_password"] is True
    assert body["user"]["is_active"] is True


def test_imported_staff_password_verifies_in_db(
    client, auth_headers, seed_data, ensure_staff_roles, db_session,
):
    """Defence-in-depth: password hash in DB must match the CSV plaintext."""
    from app.models.user import User
    from app.utils.auth import verify_password

    uname = _unique("spwd")
    resp = _import_staff_csv(
        client,
        auth_headers,
        [(uname, f"{uname}@h.in", "pharmacist", "")],
    )
    assert resp.json()["ok"] is True

    user = db_session.query(User).filter_by(username=uname).one()
    assert user.must_change_password is True
    assert verify_password("Welcome@123", user.password_hash)
    assert user.role.name == "pharmacist"


def test_all_bulk_import_types_create_working_users(
    client, auth_headers, seed_data, ensure_nurse_role, ensure_staff_roles, ensure_valid_license,
):
    """End-to-end: doctor, nurse, and staff CSV imports all create login-capable users."""
    dr = _unique("e2edr")
    nr = _unique("e2enr")
    st = _unique("e2est")

    doctor_csv = (
        "username,email,first_name,last_name,password,phone,"
        "specialization,license_number\n"
        f"{dr},{dr}@h.in,E2E,Doctor,Welcome@123,,General,MCI-E2E\n"
    )
    nurse_csv = (
        "username,email,first_name,last_name,password,phone\n"
        f"{nr},{nr}@h.in,E2E,Nurse,Welcome@123,\n"
    )

    for endpoint, csv in (
        ("/api/admin/users/bulk-import-doctors", doctor_csv),
        ("/api/admin/users/bulk-import-nurses", nurse_csv),
    ):
        r = client.post(
            endpoint,
            headers=auth_headers,
            files={"file": ("u.csv", io.BytesIO(csv.encode("utf-8")), "text/csv")},
        )
        assert r.json()["ok"] is True, r.text

    staff_r = _import_staff_csv(
        client,
        auth_headers,
        [(st, f"{st}@h.in", "frontdesk", "")],
    )
    assert staff_r.json()["ok"] is True

    for username, expected_role in (
        (dr, "doctor"),
        (nr, "nurse"),
        (st, "frontdesk"),
    ):
        login = client.post(
            "/api/auth/login",
            json={"username": username, "password": "Welcome@123"},
        )
        assert login.status_code == 200, f"{username}: {login.text}"
        assert login.json()["user"]["role"] == expected_role
        assert login.json()["user"]["must_change_password"] is True
