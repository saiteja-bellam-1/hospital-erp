"""Excel export of the user roster. Passwords must never appear in the file."""
from io import BytesIO

import pytest
from openpyxl import load_workbook

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
        token = create_access_token(data={"sub": "testhospadmin"})
        return {"Authorization": f"Bearer {token}"}
    finally:
        session.close()


def _sheet(client, headers):
    res = client.get("/api/admin/users/export/xlsx", headers=headers)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    wb = load_workbook(BytesIO(res.content))
    sheet = wb.active
    header = [cell.value for cell in sheet[1]]
    rows = list(sheet.iter_rows(min_row=2, values_only=True))
    return header, rows


def test_export_includes_roster_without_passwords(client, auth_headers):
    header, rows = _sheet(client, auth_headers)
    assert header[:4] == ["username", "email", "first_name", "last_name"]
    # Importer-compatible: password column exists but is always blank.
    pw = header.index("password")
    assert all(not row[pw] for row in rows)
    by_username = {row[0]: row for row in rows}
    assert "testadmin" in by_username
    assert "testdoctor" in by_username
    assert by_username["testdoctor"][2:4] == ("Dr", "Smith")
    assert by_username["testdoctor"][header.index("role")] == "doctor"
    joined = " ".join(str(cell or "") for row in rows for cell in row).lower()
    assert "doctor123" not in joined
    assert "admin123" not in joined


def test_hospital_admin_export_hides_vendor_account(client, hospital_admin):
    header, rows = _sheet(client, hospital_admin)
    usernames = {row[0] for row in rows}
    assert "testadmin" not in usernames
    assert "testdoctor" in usernames
    assert all(not row[header.index("password")] for row in rows)


def test_non_admin_cannot_export_users(client):
    token = create_access_token(data={"sub": "testreceptionist"})
    res = client.get(
        "/api/admin/users/export/xlsx",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


def _upload(client, headers, wb):
    buf = BytesIO()
    wb.save(buf)
    return client.post(
        "/api/admin/users/bulk-import",
        headers=headers,
        files={"file": ("users.xlsx", buf.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    ).json()


def test_exported_file_round_trips_into_import(client, auth_headers):
    """Export -> rename identities -> import must be accepted (was: missing role/password)."""
    res = client.get("/api/admin/users/export/xlsx", headers=auth_headers)
    wb = load_workbook(BytesIO(res.content))
    sheet = wb.active
    header = [c.value for c in sheet[1]]
    u, e, r = header.index("username"), header.index("email"), header.index("role")
    keep = []
    for row in list(sheet.iter_rows(min_row=2)):
        if row[r].value == "doctor":
            row[u].value = "rt_" + row[u].value
            row[e].value = "rt_" + row[e].value
            keep.append(row[u].value)
    assert keep, "fixture must contain a doctor"
    for row in list(sheet.iter_rows(min_row=2)):
        if not str(row[u].value).startswith("rt_"):
            sheet.delete_rows(row[0].row)
    # Doctors need specialization/license in the import; make sure they're present.
    for row in sheet.iter_rows(min_row=2):
        row[header.index("specialization")].value = row[header.index("specialization")].value or "General"
        row[header.index("license_number")].value = row[header.index("license_number")].value or "LIC-RT-1"
    out = _upload(client, auth_headers, wb)
    assert out["ok"], out
    assert set(out["usernames"]) == set(keep)
    # Blank password => temp password generated for every row.
    assert set(out["generated_passwords"]) == set(keep)
    assert all(len(p) >= 8 for p in out["generated_passwords"].values())


def test_import_rejects_super_admin_row(client, auth_headers):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["username", "email", "first_name", "last_name", "role"])
    ws.append(["sa_x", "sa_x@t.com", "S", "A", "super_admin"])
    out = _upload(client, auth_headers, wb)
    assert out["ok"] is False
    assert any(err["field"] == "role" for err in out["errors"])
