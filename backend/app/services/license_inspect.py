"""Pure license-verification helpers.

This module deliberately does NOT import SQLAlchemy. It exists so the Inno
Setup wizard's ``dbcheck.exe`` (a stripped-down PyInstaller build with
``sqlalchemy`` excluded) can reuse signature + machine-binding + expiry
logic without dragging the ORM in.

`app.services.license_service` re-exports everything here, so backend code
continues to import from `license_service` as before.
"""
from __future__ import annotations

from datetime import datetime

from app.licensing.crypto import verify_license_file


# License status constants
STATUS_ACTIVE = "active"
STATUS_EXPIRING_SOON = "expiring_soon"
STATUS_GRACE_PERIOD = "grace_period"
STATUS_EXPIRED = "expired"
STATUS_NO_LICENSE = "no_license"
STATUS_MACHINE_MISMATCH = "machine_mismatch"

EXPIRING_SOON_DAYS = 30
GRACE_PERIOD_DAYS = 15


def compute_license_status(expires_at: datetime) -> str:
    now = datetime.utcnow()
    days_remaining = (expires_at - now).days

    if days_remaining > EXPIRING_SOON_DAYS:
        return STATUS_ACTIVE
    elif days_remaining > 0:
        return STATUS_EXPIRING_SOON
    elif days_remaining >= -GRACE_PERIOD_DAYS:
        return STATUS_GRACE_PERIOD
    else:
        return STATUS_EXPIRED


def verify_license_machine_binding(license_record) -> tuple[bool, str, str]:
    """Re-verify that a stored license is bound to THIS machine.

    Accepts anything that exposes a ``raw_license_data`` attribute — works
    for the SQLAlchemy ``License`` row in the backend and for a plain dict
    or shim object passed in from dbcheck.

    Returns (ok, license_machine_id, current_machine_id). ``ok`` is True when:
      - license has no machine_id (legacy/unbound license), or
      - the signed machine_id matches the current host's machine ID.
    """
    from app.utils.machine_id import get_machine_id

    current_machine_id = get_machine_id()
    raw = getattr(license_record, "raw_license_data", None)
    if not license_record or not raw:
        return True, "", current_machine_id

    try:
        license_data = verify_license_file(raw)
    except Exception:
        # Signature broken / tampered — treat as mismatch so non-admin users
        # are blocked, and admins are forced to re-upload.
        return False, "", current_machine_id

    license_machine_id = license_data.get("machine_id") or ""
    if not license_machine_id:
        return True, "", current_machine_id
    return (license_machine_id == current_machine_id), license_machine_id, current_machine_id


def seller_public_info(seller) -> dict | None:
    """Seller fields safe to return to the hospital UI.

    Drops embedded logo bytes. ``logo_url`` is the file written at upload time.
    """
    if not isinstance(seller, dict):
        return None
    out: dict = {}
    for key in ("name", "address", "phone", "email", "logo_url"):
        value = seller.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    if seller.get("logo") and "logo_url" not in out:
        out["has_logo"] = True
    return out or None


def resolve_support_contact(seller, support) -> dict | None:
    """Contact shown in the hospital app.

    A vendor license uses the seller block. A direct or customisation license
    uses the product support block written into the file by License Manager.
    """
    seller_info = seller_public_info(seller)
    if seller_info and seller_info.get("name"):
        seller_info.pop("has_logo", None)
        return seller_info
    support_info = seller_public_info(support)
    if not support_info or not support_info.get("name"):
        return None
    support_info.pop("logo_url", None)
    support_info.pop("has_logo", None)
    return support_info or None


def inspect_license_file(file_content: str) -> dict:
    """Dry-run: parse + verify a .lic file and report compatibility WITHOUT
    touching the database. Never raises on machine-ID mismatch — instead the
    mismatch is reported as a flag.
    """
    from app.utils.machine_id import get_machine_id

    try:
        license_data = verify_license_file(file_content)
    except ValueError as e:
        return {
            "valid_signature": False,
            "error": str(e),
        }

    license_machine_id = license_data.get("machine_id") or ""
    current_machine_id = get_machine_id()
    machine_match = (not license_machine_id) or (license_machine_id == current_machine_id)

    try:
        issued_at = datetime.fromisoformat(license_data["issued_at"]).replace(tzinfo=None)
        expires_at = datetime.fromisoformat(license_data["expires_at"]).replace(tzinfo=None)
        date_error = None
    except Exception as e:
        issued_at = None
        expires_at = None
        date_error = str(e)

    status = compute_license_status(expires_at) if expires_at else None
    days_remaining = (expires_at - datetime.utcnow()).days if expires_at else None

    return {
        "valid_signature": True,
        "machine_match": machine_match,
        "license_machine_id": license_machine_id,
        "current_machine_id": current_machine_id,
        "license_id": license_data.get("license_id"),
        "hospital_id": license_data.get("hospital_id"),
        "hospital_name": license_data.get("hospital_name"),
        "plan": license_data.get("plan"),
        "max_users": license_data.get("max_users"),
        "features": license_data.get("features", []),
        "seller_info": seller_public_info(license_data.get("seller")),
        "support_contact": resolve_support_contact(
            license_data.get("seller"),
            license_data.get("support"),
        ),
        "issued_at": issued_at.isoformat() if issued_at else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "status": status,
        "days_remaining": days_remaining,
        "date_error": date_error,
    }
