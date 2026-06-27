"""Helpers for multi-store pharmacy scoping."""
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.hospital import Hospital
from app.models.pharmacy import PharmacyStore, PharmacyUserStore
from app.models.user import User


ADMIN_ROLES = frozenset({"super_admin", "hospital_admin", "pharmacy_admin"})


def is_multi_store_enabled(db: Session, hospital_id: int) -> bool:
    hosp = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    return bool(hosp and getattr(hosp, "pharmacy_multi_store_enabled", False))


def requires_store_assignment(db: Session, hospital_id: int) -> bool:
    """True when staff must be explicitly assigned to a store (no master fallback)."""
    hosp = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    if not hosp or not getattr(hosp, "pharmacy_multi_store_enabled", False):
        return False
    return bool(getattr(hosp, "pharmacy_require_store_assignment", False))


def get_default_store(db: Session, hospital_id: int) -> PharmacyStore:
    store = db.query(PharmacyStore).filter(
        PharmacyStore.hospital_id == hospital_id,
        PharmacyStore.is_default == True,  # noqa: E712
        PharmacyStore.is_active == True,  # noqa: E712
    ).first()
    if store:
        return store
    store = db.query(PharmacyStore).filter(
        PharmacyStore.hospital_id == hospital_id,
        PharmacyStore.store_type == "master",
        PharmacyStore.is_active == True,  # noqa: E712
    ).order_by(PharmacyStore.id.asc()).first()
    if store:
        return store
    store = PharmacyStore(
        code="MAIN",
        name="Main Pharmacy",
        store_type="master",
        can_receive_supplier_purchase=True,
        is_active=True,
        is_default=True,
        hospital_id=hospital_id,
    )
    db.add(store)
    db.flush()
    return store


def user_is_store_admin(user: User) -> bool:
    role_names = set(getattr(user, "role_names", None) or [])
    if user.role and user.role.name:
        role_names.add(user.role.name)
    for r in getattr(user, "roles", None) or []:
        if r.name:
            role_names.add(r.name)
    return bool(role_names & ADMIN_ROLES)


def get_user_store_ids(db: Session, user: User) -> Optional[List[int]]:
    """Return assigned store ids, or None if user has unrestricted access."""
    if user_is_store_admin(user):
        return None
    rows = db.query(PharmacyUserStore.store_id).filter(
        PharmacyUserStore.user_id == user.id,
        PharmacyUserStore.hospital_id == user.hospital_id,
    ).all()
    if not rows:
        if requires_store_assignment(db, user.hospital_id):
            return []
        default = get_default_store(db, user.hospital_id)
        return [default.id]
    return [r[0] for r in rows]


def user_can_access_store(db: Session, user: User, store_id: int) -> bool:
    store = db.query(PharmacyStore).filter(
        PharmacyStore.id == store_id,
        PharmacyStore.hospital_id == user.hospital_id,
        PharmacyStore.is_active == True,  # noqa: E712
    ).first()
    if not store:
        return False
    allowed = get_user_store_ids(db, user)
    if allowed is None:
        return True
    return store_id in allowed


def resolve_store_id(
    db: Session,
    user: User,
    store_id: Optional[int],
    *,
    require_purchase_store: bool = False,
) -> int:
    """Resolve the active store for a pharmacy operation."""
    allowed = get_user_store_ids(db, user)
    if allowed is not None and len(allowed) == 0:
        raise HTTPException(
            status_code=403,
            detail="No pharmacy store assigned to your account. Contact your pharmacy administrator.",
        )

    if store_id is not None:
        store = db.query(PharmacyStore).filter(
            PharmacyStore.id == store_id,
            PharmacyStore.hospital_id == user.hospital_id,
            PharmacyStore.is_active == True,  # noqa: E712
        ).first()
        if not store:
            raise HTTPException(status_code=400, detail="Invalid store_id")
        if not user_can_access_store(db, user, store.id):
            raise HTTPException(status_code=403, detail="You do not have access to this pharmacy store")
        if require_purchase_store and not store.can_receive_supplier_purchase:
            raise HTTPException(status_code=400, detail="This store cannot receive supplier purchases")
        return store.id

    if allowed and len(allowed) == 1:
        return allowed[0]
    if allowed is not None and len(allowed) > 1:
        raise HTTPException(status_code=400, detail="store_id is required — select your pharmacy store")
    default = get_default_store(db, user.hospital_id)
    if allowed and default.id not in allowed and allowed:
        return allowed[0]
    return default.id


def user_has_pharmacy_permission(db: Session, user: User, permission_name: str) -> bool:
    """Check whether any of the user's roles grant a pharmacy permission."""
    if user_is_store_admin(user):
        return True
    from app.models.permissions import RoleModulePermission
    role_ids = [r.id for r in (getattr(user, "roles", None) or [])]
    if user.role_id and user.role_id not in role_ids:
        role_ids.append(user.role_id)
    for rid in role_ids:
        rp = db.query(RoleModulePermission).filter(
            RoleModulePermission.role_id == rid,
            RoleModulePermission.module_name == "pharmacy",
        ).first()
        if rp and rp.permissions and permission_name in rp.permissions:
            return True
    return False


def resolve_report_store_filter(
    db: Session,
    user: User,
    store_id: Optional[int],
) -> Optional[int]:
    """Return store_id to filter reports, or None for all stores."""
    if user_has_pharmacy_permission(db, user, "view_all_stores"):
        if store_id is not None:
            return resolve_store_id(db, user, store_id)
        return None
    return resolve_store_id(db, user, store_id)


def list_accessible_stores(db: Session, user: User, *, active_only: bool = True) -> List[PharmacyStore]:
    q = db.query(PharmacyStore).filter(PharmacyStore.hospital_id == user.hospital_id)
    if active_only:
        q = q.filter(PharmacyStore.is_active == True)  # noqa: E712
    allowed = get_user_store_ids(db, user)
    if allowed is not None:
        if not allowed:
            return []
        q = q.filter(PharmacyStore.id.in_(allowed))
    return q.order_by(PharmacyStore.store_type.asc(), PharmacyStore.name.asc()).all()


def get_master_store_id(db: Session, hospital_id: int) -> Optional[int]:
    master = db.query(PharmacyStore).filter(
        PharmacyStore.hospital_id == hospital_id,
        PharmacyStore.store_type == "master",
        PharmacyStore.is_active == True,  # noqa: E712
    ).order_by(PharmacyStore.is_default.desc(), PharmacyStore.id.asc()).first()
    return master.id if master else None


def sum_store_stock(db: Session, *, medicine_id: int, hospital_id: int, store_id: Optional[int]) -> float:
    from app.models.pharmacy import PharmacyInventory
    from sqlalchemy import func as sa_func

    if store_id is None:
        return 0.0
    total = db.query(sa_func.coalesce(sa_func.sum(PharmacyInventory.quantity_in_stock), 0)).filter(
        PharmacyInventory.medicine_id == medicine_id,
        PharmacyInventory.hospital_id == hospital_id,
        PharmacyInventory.store_id == store_id,
        PharmacyInventory.is_active == True,  # noqa: E712
        PharmacyInventory.quantity_in_stock > 0,
    ).scalar()
    return float(total or 0)
