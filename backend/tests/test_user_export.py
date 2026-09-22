"""Tests for GET /api/admin/users/export/xlsx."""
from __future__ import annotations

import io

import openpyxl
import pytest

from app.models.user import User, UserRole
from app.utils.auth import create_access_token, get_password_hash


@pytest.fixture(scope="module")
def hospital_admin(TestSessionLocal, seed_data):
    session = TestSessionLocal()
    try:
        role = session.query(UserRole).filter_by(name="hospital_admin").first()
        if role is None:
            role = UserRole(name="hospital_admin", is_system_role=True)
            session.add(role)
            session.flush()
        user = session.query(User).filter_by(username="testhospadmin").first()
        if user is None:
            user = User(
                username="testhospadmin",
                password_hash=get_password_hash("hosp123"),
                email="hospadmin@test.com",
                first_name="Hosp",
                last_name="Admin",
                role_id=role.id,
                hospital_id=seed_data["hospital_id"],
                is_active=True,
            )
            session.add(user)
            session.commit()
        return {"Authorization": f"Bearer {create_access_token(data={'sub': 'testhospadmin'})}"}
    finally:
        session.close()


def _workbook(resp):
    return openpyxl.load_workbook(io.BytesIO(resp.content), data_only=True)


def _users_sheet_rows(wb):
    ws = wb["Users"]
    headers = None
    rows = []
    for row in ws.iter_rows(values_only=True):
        values = list(row)
        if values and values[0] == "username":
            headers = values
            continue
        if headers is not None:
            rows.append(dict(zip(headers, values)))
    return headers, rows


def test_users_export_xlsx(client, auth_headers, db_session):
    resp = client.get("/api/admin/users/export/xlsx", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "users_export_" in resp.headers.get("content-disposition", "")

    wb = _workbook(resp)
    assert "Users" in wb.sheetnames
    headers, rows = _users_sheet_rows(wb)
    assert headers is not None
    header_names = [h.lower() for h in headers if h]
    assert "username" in header_names
    assert "password" not in header_names
    assert "password_hash" not in header_names

    usernames = {row["username"] for row in rows}
    assert "testadmin" in usernames
    assert "testdoctor" in usernames
    assert "testreceptionist" in usernames

    doctor = next(row for row in rows if row["username"] == "testdoctor")
    assert doctor["role"] == "doctor"
    assert doctor["status"] == "Active"

    cell_text = " ".join(str(v) for row in rows for v in row.values() if v)
    for hashed in db_session.query(User.password_hash).all():
        if hashed[0]:
            assert hashed[0] not in cell_text
            assert hashed[0].encode() not in resp.content


def test_users_export_hides_super_admin_from_hospital_admin(client, hospital_admin):
    resp = client.get("/api/admin/users/export/xlsx", headers=hospital_admin)
    assert resp.status_code == 200, resp.text
    _, rows = _users_sheet_rows(_workbook(resp))
    usernames = {row["username"] for row in rows}
    assert "testadmin" not in usernames
    assert "testdoctor" in usernames


def test_users_export_requires_admin(client):
    resp = client.get("/api/admin/users/export/xlsx")
    assert resp.status_code in (401, 403)


def test_users_export_rejects_non_admin(client):
    token = create_access_token(data={"sub": "testdoctor"})
    resp = client.get(
        "/api/admin/users/export/xlsx",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
