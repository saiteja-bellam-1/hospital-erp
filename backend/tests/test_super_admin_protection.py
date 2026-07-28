"""Super admin (vendor account) lockdown tests.

The super_admin account is reserved for the software vendor: exactly one such
account exists (created by the installer seed), it is hidden from other admins
in the user list, and nobody — including hospital_admin — can alter, demote,
deactivate, or duplicate it through the API.
"""
from __future__ import annotations

import pytest

from app.models.user import User, UserRole
from app.utils.auth import create_access_token, get_password_hash


@pytest.fixture(scope="module")
def hospital_admin(TestSessionLocal, seed_data):
    """Get-or-create a hospital_admin user; return auth headers for it."""
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


@pytest.fixture(scope="module")
def role_ids(TestSessionLocal, seed_data, hospital_admin):
    session = TestSessionLocal()
    try:
        return {r.name: r.id for r in session.query(UserRole).all()}
    finally:
        session.close()


@pytest.fixture(scope="module")
def vendor_id(seed_data):
    """Integer id of the seeded super_admin (vendor) account."""
    return seed_data["admin_user_id"]


def _update_payload(**overrides):
    """UserUpdateRequest declares Optional fields without defaults, so every
    key must be present (null = leave unchanged)."""
    payload = {
        "username": None,
        "email": None,
        "first_name": None,
        "last_name": None,
        "phone": None,
        "license_number": None,
        "consultation_fee_inr": None,
        "inpatient_fee_inr": None,
        "emergency_fee_inr": None,
        "specialization": None,
        "qualification": None,
        "experience_years": None,
        "role_id": None,
        "is_active": None,
    }
    payload.update(overrides)
    return payload


@pytest.fixture(scope="module")
def normal_user(TestSessionLocal, seed_data, role_ids):
    """Get-or-create a plain receptionist used as a grant/archive target."""
    session = TestSessionLocal()
    try:
        user = session.query(User).filter_by(username="sa_guard_target").first()
        if user is None:
            user = User(
                username="sa_guard_target",
                password_hash=get_password_hash("target123"),
                email="sa_guard_target@test.com",
                first_name="Guard",
                last_name="Target",
                role_id=role_ids["receptionist"],
                hospital_id=seed_data["hospital_id"],
                is_active=True,
            )
            session.add(user)
            session.commit()
        return user.id
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------

class TestVendorAccountVisibility:
    def test_hidden_from_hospital_admin_user_list(self, client, hospital_admin, vendor_id):
        res = client.get("/api/admin/users", headers=hospital_admin)
        assert res.status_code == 200
        returned_ids = [u["id"] for u in res.json()]
        assert vendor_id not in returned_ids
        assert all(
            "super_admin" not in [r["name"] for r in (u.get("user_roles") or [u["user_role"]])]
            for u in res.json()
        )

    def test_visible_to_super_admin(self, client, auth_headers, vendor_id):
        res = client.get("/api/admin/users", headers=auth_headers)
        assert res.status_code == 200
        assert vendor_id in [u["id"] for u in res.json()]

    def test_hospital_admin_cannot_view_vendor_roles(self, client, hospital_admin, vendor_id):
        res = client.get(f"/api/admin/users/{vendor_id}/roles", headers=hospital_admin)
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# Immutability — hospital_admin cannot alter the vendor account
# ---------------------------------------------------------------------------

class TestVendorAccountImmutability:
    def test_cannot_edit_profile(self, client, hospital_admin, vendor_id):
        res = client.put(f"/api/admin/users/{vendor_id}", headers=hospital_admin,
                         json=_update_payload(first_name="Hijacked"))
        assert res.status_code == 403

    def test_cannot_change_username(self, client, hospital_admin, vendor_id):
        res = client.put(f"/api/admin/users/{vendor_id}", headers=hospital_admin,
                         json=_update_payload(username="hijackedadmin"))
        assert res.status_code == 403

    def test_cannot_deactivate(self, client, hospital_admin, vendor_id):
        res = client.put(f"/api/admin/users/{vendor_id}", headers=hospital_admin,
                         json=_update_payload(is_active=False))
        assert res.status_code == 403

    def test_cannot_demote_via_role_id(self, client, hospital_admin, vendor_id, role_ids):
        res = client.put(f"/api/admin/users/{vendor_id}", headers=hospital_admin,
                         json=_update_payload(role_id=role_ids["receptionist"]))
        assert res.status_code == 403

    def test_cannot_strip_roles(self, client, hospital_admin, vendor_id, role_ids):
        res = client.put(f"/api/admin/users/{vendor_id}/roles", headers=hospital_admin,
                         json={"role_ids": [role_ids["receptionist"]]})
        assert res.status_code == 403

    def test_cannot_reset_password(self, client, hospital_admin, vendor_id):
        res = client.put(f"/api/admin/users/{vendor_id}/reset-password", headers=hospital_admin,
                         json={"new_password": "hacked123"})
        assert res.status_code == 403

    def test_cannot_archive(self, client, hospital_admin, vendor_id):
        res = client.delete(f"/api/admin/users/{vendor_id}", headers=hospital_admin)
        assert res.status_code in (400, 403)

    def test_cannot_restore(self, client, hospital_admin, vendor_id):
        res = client.put(f"/api/admin/users/{vendor_id}/restore", headers=hospital_admin)
        assert res.status_code == 403

    def test_cannot_resubmit_vendor_roles_even_unchanged(
        self, client, hospital_admin, vendor_id, role_ids
    ):
        # Identical role set from a non-vendor caller is still rejected
        res = client.put(f"/api/admin/users/{vendor_id}/roles", headers=hospital_admin,
                         json={"role_ids": [role_ids["super_admin"]]})
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# Singleton — no second super admin through any API path
# ---------------------------------------------------------------------------

class TestSuperAdminSingleton:
    def test_hospital_admin_cannot_create_super_admin(self, client, hospital_admin, role_ids):
        res = client.post("/api/admin/users", headers=hospital_admin, json={
            "username": "secondsuper",
            "email": "secondsuper@test.com",
            "password": "pass1234",
            "first_name": "Second",
            "last_name": "Super",
            "role_id": role_ids["super_admin"],
        })
        assert res.status_code == 403

    def test_super_admin_cannot_create_second_super_admin(self, client, auth_headers, role_ids):
        res = client.post("/api/admin/users", headers=auth_headers, json={
            "username": "secondsuper2",
            "email": "secondsuper2@test.com",
            "password": "pass1234",
            "first_name": "Second",
            "last_name": "Super",
            "role_id": role_ids["super_admin"],
        })
        assert res.status_code == 403

    def test_cannot_grant_super_admin_role_to_normal_user(
        self, client, hospital_admin, normal_user, role_ids
    ):
        res = client.put(f"/api/admin/users/{normal_user}/roles", headers=hospital_admin,
                         json={"role_ids": [role_ids["super_admin"]]})
        assert res.status_code == 403

    def test_cannot_set_super_admin_role_id_on_normal_user(
        self, client, hospital_admin, normal_user, role_ids
    ):
        res = client.put(f"/api/admin/users/{normal_user}", headers=hospital_admin,
                         json=_update_payload(role_id=role_ids["super_admin"]))
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# Vendor self-service — profile editable, identity frozen
# ---------------------------------------------------------------------------

class TestVendorSelfService:
    def test_can_edit_own_profile_fields(self, client, auth_headers, vendor_id):
        res = client.put(f"/api/admin/users/{vendor_id}", headers=auth_headers,
                         json=_update_payload(phone="9000000001"))
        assert res.status_code == 200
        assert res.json()["phone"] == "9000000001"

    def test_cannot_change_own_username(self, client, auth_headers, vendor_id):
        res = client.put(f"/api/admin/users/{vendor_id}", headers=auth_headers,
                         json=_update_payload(username="renamedadmin"))
        assert res.status_code == 403

    def test_cannot_change_own_role(self, client, auth_headers, vendor_id, role_ids):
        res = client.put(f"/api/admin/users/{vendor_id}", headers=auth_headers,
                         json=_update_payload(role_id=role_ids["receptionist"]))
        assert res.status_code == 403

    def test_cannot_deactivate_self(self, client, auth_headers, vendor_id):
        res = client.put(f"/api/admin/users/{vendor_id}", headers=auth_headers,
                         json=_update_payload(is_active=False))
        assert res.status_code == 403

    def test_cannot_change_own_roles(self, client, auth_headers, vendor_id, role_ids):
        res = client.put(f"/api/admin/users/{vendor_id}/roles", headers=auth_headers,
                         json={"role_ids": [role_ids["super_admin"], role_ids["doctor"]]})
        assert res.status_code == 403

    def test_identical_own_roles_resubmit_is_noop(self, client, auth_headers, vendor_id, role_ids):
        # The shared user form always calls the roles endpoint after saving;
        # resubmitting the unchanged set must succeed so the vendor's own
        # profile edit flow keeps working.
        res = client.put(f"/api/admin/users/{vendor_id}/roles", headers=auth_headers,
                         json={"role_ids": [role_ids["super_admin"]]})
        assert res.status_code == 200
        assert [r["name"] for r in res.json()["roles"]] == ["super_admin"]


# ---------------------------------------------------------------------------
# Regression — normal admin flows keep working
# ---------------------------------------------------------------------------

class TestNormalAdminFlowsUnaffected:
    def test_hospital_admin_can_manage_normal_users(
        self, client, hospital_admin, role_ids, seed_data
    ):
        create = client.post("/api/admin/users", headers=hospital_admin, json={
            "username": "sa_guard_created",
            "email": "sa_guard_created@test.com",
            "password": "pass1234",
            "first_name": "Created",
            "last_name": "User",
            "role_id": role_ids["receptionist"],
        })
        assert create.status_code == 200, create.text
        created_id = create.json()["id"]

        update = client.put(f"/api/admin/users/{created_id}", headers=hospital_admin,
                            json=_update_payload(first_name="Updated"))
        assert update.status_code == 200
        assert update.json()["first_name"] == "Updated"

        archive = client.delete(f"/api/admin/users/{created_id}", headers=hospital_admin)
        assert archive.status_code == 200

        restore = client.put(f"/api/admin/users/{created_id}/restore", headers=hospital_admin)
        assert restore.status_code == 200

    def test_hospital_admin_can_reset_normal_user_password(
        self, client, hospital_admin, normal_user
    ):
        res = client.put(f"/api/admin/users/{normal_user}/reset-password", headers=hospital_admin,
                         json={"new_password": "newpass123"})
        assert res.status_code == 200
