"""Pharmacy role permission boundary tests."""
import pytest

from app.utils.auth import create_access_token, get_password_hash
from app.services.db_seed import (
    _PHARMACIST_DEFAULT,
    _PHARMACY_POS_OPERATOR,
    _PHARMACY_TRANSFER_CLERK,
)


_pharmacy_perm_ctx: dict = {}


@pytest.fixture(scope="module")
def pharmacy_perm_setup(seed_data, TestSessionLocal):
    from app.models.hospital import Hospital
    from app.models.user import User, UserRole
    from app.models.permissions import RoleModulePermission
    from app.models.system import SystemModule
    from app.models.pharmacy import PharmacyStore, PharmacyUserStore

    db = TestSessionLocal()
    try:
        mod = db.query(SystemModule).filter(SystemModule.module_name == "pharmacy").first()
        if not mod:
            mod = SystemModule(
                module_name="pharmacy", display_name="Pharmacy",
                description="Pharmacy", is_enabled=True, is_always_enabled=False,
            )
            db.add(mod)
        else:
            mod.is_enabled = True

        hosp = db.query(Hospital).filter(Hospital.id == seed_data["hospital_id"]).first()
        hosp.pharmacy_multi_store_enabled = True
        hosp.pharmacy_require_store_assignment = True

        pharmacist_role = db.query(UserRole).filter(UserRole.name == "pharmacist").first()
        if not pharmacist_role:
            pharmacist_role = UserRole(name="pharmacist", is_system_role=True)
            db.add(pharmacist_role)
            db.flush()

        transfer_role = db.query(UserRole).filter(UserRole.name == "pharmacy_transfer_clerk").first()
        if not transfer_role:
            transfer_role = UserRole(name="pharmacy_transfer_clerk", is_system_role=True)
            db.add(transfer_role)
            db.flush()

        pos_role = db.query(UserRole).filter(UserRole.name == "pharmacy_pos_operator").first()
        if not pos_role:
            pos_role = UserRole(name="pharmacy_pos_operator", is_system_role=True)
            db.add(pos_role)
            db.flush()

        for role_name, perms in (
            ("pharmacist", list(_PHARMACIST_DEFAULT)),
            ("pharmacy_transfer_clerk", list(_PHARMACY_TRANSFER_CLERK)),
            ("pharmacy_pos_operator", list(_PHARMACY_POS_OPERATOR)),
        ):
            role = db.query(UserRole).filter(UserRole.name == role_name).first()
            existing = db.query(RoleModulePermission).filter(
                RoleModulePermission.role_id == role.id,
                RoleModulePermission.module_name == "pharmacy",
            ).first()
            if existing:
                existing.permissions = perms
            else:
                db.add(RoleModulePermission(
                    role_id=role.id, module_name="pharmacy", permissions=perms,
                ))

        users = {}
        for role_name, username in (
            ("pharmacist", "perm_pharmacist"),
            ("pharmacy_transfer_clerk", "perm_transfer_clerk"),
            ("pharmacist", "perm_sat_pharmacist"),
            ("pharmacy_pos_operator", "perm_pos_unassigned"),
            ("pharmacy_pos_operator", "perm_pos_satellite"),
        ):
            role = db.query(UserRole).filter(UserRole.name == role_name).first()
            user = db.query(User).filter(User.username == username).first()
            if not user:
                user = User(
                    username=username,
                    password_hash=get_password_hash("test123"),
                    email=f"{username}@test.com",
                    first_name=username, last_name="User",
                    role_id=role.id, hospital_id=seed_data["hospital_id"],
                    is_active=True,
                )
                db.add(user)
                db.flush()
            users[username] = user.id

        master = db.query(PharmacyStore).filter(
            PharmacyStore.hospital_id == seed_data["hospital_id"],
            PharmacyStore.is_default == True,  # noqa: E712
        ).first()
        if not master:
            master = PharmacyStore(
                code="MAIN", name="Main Pharmacy", store_type="master",
                can_receive_supplier_purchase=True, is_active=True, is_default=True,
                hospital_id=seed_data["hospital_id"],
            )
            db.add(master)
            db.flush()

        satellite = db.query(PharmacyStore).filter(
            PharmacyStore.hospital_id == seed_data["hospital_id"],
            PharmacyStore.code == "SAT-1",
        ).first()
        if not satellite:
            satellite = PharmacyStore(
                code="SAT-1", name="Satellite Ward", store_type="satellite",
                parent_store_id=master.id, can_receive_supplier_purchase=False,
                is_active=True, is_default=False, hospital_id=seed_data["hospital_id"],
            )
            db.add(satellite)
            db.flush()

        sat_user_id = users["perm_sat_pharmacist"]
        db.query(PharmacyUserStore).filter(
            PharmacyUserStore.user_id == sat_user_id,
        ).delete(synchronize_session=False)
        db.add(PharmacyUserStore(
            user_id=sat_user_id, store_id=satellite.id,
            hospital_id=seed_data["hospital_id"],
        ))

        master_pharmacist_id = users["perm_pharmacist"]
        db.query(PharmacyUserStore).filter(
            PharmacyUserStore.user_id == master_pharmacist_id,
        ).delete(synchronize_session=False)
        db.add(PharmacyUserStore(
            user_id=master_pharmacist_id, store_id=master.id,
            hospital_id=seed_data["hospital_id"],
        ))

        pos_sat_id = users["perm_pos_satellite"]
        db.query(PharmacyUserStore).filter(
            PharmacyUserStore.user_id == pos_sat_id,
        ).delete(synchronize_session=False)
        db.add(PharmacyUserStore(
            user_id=pos_sat_id, store_id=satellite.id,
            hospital_id=seed_data["hospital_id"],
        ))

        db.commit()
        _pharmacy_perm_ctx.update({
            "pharmacist_headers": {"Authorization": f"Bearer {create_access_token({'sub': 'perm_pharmacist'})}"},
            "transfer_clerk_headers": {"Authorization": f"Bearer {create_access_token({'sub': 'perm_transfer_clerk'})}"},
            "sat_pharmacist_headers": {"Authorization": f"Bearer {create_access_token({'sub': 'perm_sat_pharmacist'})}"},
            "pos_unassigned_headers": {"Authorization": f"Bearer {create_access_token({'sub': 'perm_pos_unassigned'})}"},
            "pos_satellite_headers": {"Authorization": f"Bearer {create_access_token({'sub': 'perm_pos_satellite'})}"},
            "master_store_id": master.id,
            "satellite_store_id": satellite.id,
        })
    finally:
        db.close()
    yield _pharmacy_perm_ctx


@pytest.fixture
def perm_headers(pharmacy_perm_setup):
    return pharmacy_perm_setup


def test_pharmacist_can_access_inventory(client, perm_headers):
    r = client.get("/api/pharmacy/inventory", headers=perm_headers["pharmacist_headers"])
    assert r.status_code == 200


def test_pharmacist_can_access_reports(client, perm_headers):
    r = client.get("/api/pharmacy/reports/sales", headers=perm_headers["pharmacist_headers"])
    assert r.status_code == 200


def test_pharmacist_denied_manage_stores(client, perm_headers):
    r = client.get("/api/pharmacy/stores", headers=perm_headers["pharmacist_headers"])
    assert r.status_code == 403


def test_pharmacist_denied_confirm_transfer(client, perm_headers):
    r = client.post(
        "/api/pharmacy/transfers/99999/confirm",
        headers=perm_headers["pharmacist_headers"],
    )
    assert r.status_code == 403


def test_pharmacist_denied_revoke_transfer(client, perm_headers):
    r = client.post(
        "/api/pharmacy/transfers/99999/revoke",
        json={"reason": "test revoke"},
        headers=perm_headers["pharmacist_headers"],
    )
    assert r.status_code == 403


def test_transfer_clerk_can_list_transfers(client, perm_headers):
    r = client.get("/api/pharmacy/transfers", headers=perm_headers["transfer_clerk_headers"])
    assert r.status_code == 200


def test_transfer_clerk_can_confirm_transfer(client, perm_headers):
    r = client.post(
        "/api/pharmacy/transfers/99999/confirm",
        headers=perm_headers["transfer_clerk_headers"],
    )
    assert r.status_code != 403


def test_transfer_clerk_denied_revoke_transfer(client, perm_headers):
    r = client.post(
        "/api/pharmacy/transfers/99999/revoke",
        json={"reason": "test revoke"},
        headers=perm_headers["transfer_clerk_headers"],
    )
    assert r.status_code == 403


def test_pharmacist_denied_create_store(client, perm_headers):
    r = client.post(
        "/api/pharmacy/stores",
        json={
            "code": "BLK-X", "name": "Block X", "store_type": "satellite",
            "parent_store_id": perm_headers["master_store_id"],
        },
        headers=perm_headers["pharmacist_headers"],
    )
    assert r.status_code == 403


def test_pharmacist_denied_assign_user_stores(client, perm_headers, seed_data):
    r = client.put(
        f"/api/pharmacy/users/{seed_data['admin_user_id']}/stores",
        json={"store_ids": [perm_headers["master_store_id"]]},
        headers=perm_headers["pharmacist_headers"],
    )
    assert r.status_code == 403


def test_satellite_pharmacist_can_access_own_store(client, perm_headers):
    sid = perm_headers["satellite_store_id"]
    r = client.get(
        f"/api/pharmacy/inventory?store_id={sid}",
        headers=perm_headers["sat_pharmacist_headers"],
    )
    assert r.status_code == 200


def test_satellite_pharmacist_denied_other_store(client, perm_headers):
    sid = perm_headers["master_store_id"]
    r = client.get(
        f"/api/pharmacy/inventory?store_id={sid}",
        headers=perm_headers["sat_pharmacist_headers"],
    )
    assert r.status_code == 403
    assert "access" in r.json()["detail"].lower()


def test_unassigned_pos_operator_denied_inventory(client, perm_headers):
    r = client.get("/api/pharmacy/inventory", headers=perm_headers["pos_unassigned_headers"])
    assert r.status_code == 403


def test_pos_operator_denied_inventory_without_permission(client, perm_headers):
    sid = perm_headers["satellite_store_id"]
    r = client.get(
        f"/api/pharmacy/inventory?store_id={sid}",
        headers=perm_headers["pos_satellite_headers"],
    )
    assert r.status_code == 403


def test_pos_operator_can_lookup_with_store_stock(client, perm_headers):
    sid = perm_headers["satellite_store_id"]
    r = client.get(
        "/api/pharmacy/medicines/lookup",
        params={"q": "RMed", "store_id": sid},
        headers=perm_headers["pos_satellite_headers"],
    )
    assert r.status_code == 200
    if r.json():
        assert "store_stock_qty" in r.json()[0]
