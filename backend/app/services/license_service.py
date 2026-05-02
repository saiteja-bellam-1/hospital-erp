from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.license import License
from app.licensing.crypto import verify_license_file

# License status constants
STATUS_ACTIVE = "active"
STATUS_EXPIRING_SOON = "expiring_soon"
STATUS_GRACE_PERIOD = "grace_period"
STATUS_EXPIRED = "expired"


def _build_gdrive_config(license_data: dict):
    """Extract Google Drive backup config from license data (OAuth only)."""
    if license_data.get("gdrive_backup_enabled") and license_data.get("gdrive_refresh_token"):
        return {
            "enabled": True,
            "folder_id": license_data.get("gdrive_folder_id"),
            "refresh_token": license_data["gdrive_refresh_token"],
            "client_id": license_data.get("gdrive_client_id"),
            "client_secret": license_data.get("gdrive_client_secret"),
        }
    return None
STATUS_NO_LICENSE = "no_license"

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


def get_current_license(db: Session) -> License | None:
    """Get the most recent license from DB."""
    return db.query(License).order_by(License.id.desc()).first()


def get_license_status(db: Session) -> dict:
    """Get current license status info for API responses."""
    license_record = get_current_license(db)
    if not license_record:
        return {
            "status": STATUS_NO_LICENSE,
            "message": "No license installed",
            "days_remaining": 0,
            "expires_at": None,
            "plan": None,
            "max_users": 0,
            "features": [],
        }

    status = compute_license_status(license_record.expires_at)
    days_remaining = (license_record.expires_at - datetime.utcnow()).days

    # Update status in DB if changed
    if license_record.status != status:
        license_record.status = status
        db.commit()

    return {
        "status": status,
        "message": _status_message(status, days_remaining),
        "days_remaining": days_remaining,
        "expires_at": license_record.expires_at.isoformat(),
        "plan": license_record.plan,
        "max_users": license_record.max_users,
        "features": license_record.features or [],
        "hospital_name": license_record.hospital_name,
        "license_id": license_record.license_id,
        "issued_at": license_record.issued_at.isoformat(),
        "seller_info": license_record.seller_info,
    }


def inspect_license_file(file_content: str) -> dict:
    """Dry-run: parse + verify a .lic file and report compatibility WITHOUT
    touching the database.

    Returns a structured payload the UI can display before the user commits to
    applying the license. Never raises on machine-ID mismatch — instead the
    mismatch is reported as a flag so the caller can decide what to do (offer
    rebind, etc).
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
        "seller_info": license_data.get("seller"),
        "issued_at": issued_at.isoformat() if issued_at else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "status": status,
        "days_remaining": days_remaining,
        "date_error": date_error,
    }


def upload_license(db: Session, file_content: str, uploaded_by: int = None) -> dict:
    """Verify and store a new license file."""
    from app.utils.machine_id import get_machine_id

    # Verify signature and parse
    license_data = verify_license_file(file_content)

    # Validate machine_id if present in license
    license_machine_id = license_data.get("machine_id")
    if license_machine_id:
        current_machine_id = get_machine_id()
        if license_machine_id != current_machine_id:
            raise ValueError(
                f"This license is not valid for this machine. "
                f"License is for machine '{license_machine_id}', "
                f"but this machine is '{current_machine_id}'."
            )

    # Parse dates (strip timezone to keep everything as naive UTC)
    issued_at = datetime.fromisoformat(license_data["issued_at"]).replace(tzinfo=None)
    expires_at = datetime.fromisoformat(license_data["expires_at"]).replace(tzinfo=None)

    # Validate dates
    if expires_at <= issued_at:
        raise ValueError("License expiry date must be after issue date")

    status = compute_license_status(expires_at)

    # Check if this license_id already exists (re-upload)
    existing = db.query(License).filter(
        License.license_id == license_data["license_id"]
    ).first()

    if existing:
        # Update existing record
        existing.hospital_id = license_data.get("hospital_id", existing.hospital_id)
        existing.hospital_name = license_data.get("hospital_name", existing.hospital_name)
        existing.plan = license_data.get("plan", existing.plan)
        existing.max_users = license_data.get("max_users", existing.max_users)
        existing.features = license_data.get("features", existing.features)
        existing.seller_info = license_data.get("seller", existing.seller_info)
        existing.gdrive_config = _build_gdrive_config(license_data)
        existing.issued_at = issued_at
        existing.expires_at = expires_at
        existing.status = status
        existing.raw_license_data = file_content
        existing.uploaded_by = uploaded_by
        db.commit()
    else:
        # Create new license record
        new_license = License(
            license_id=license_data["license_id"],
            hospital_id=license_data.get("hospital_id", ""),
            hospital_name=license_data.get("hospital_name", ""),
            plan=license_data.get("plan", "standard"),
            max_users=license_data.get("max_users", 50),
            features=license_data.get("features", []),
            seller_info=license_data.get("seller", None),
            gdrive_config=_build_gdrive_config(license_data),
            issued_at=issued_at,
            expires_at=expires_at,
            status=status,
            raw_license_data=file_content,
            uploaded_by=uploaded_by,
        )
        db.add(new_license)
        db.commit()

    # Auto-disable modules not included in the new license
    _sync_modules_with_license(db, license_data.get("features", []))

    return get_license_status(db)


def _sync_modules_with_license(db: Session, licensed_features: list):
    """Disable modules that are not in the license. Enable licensed ones if they were disabled due to licensing."""
    from app.models.system import SystemModule
    if not licensed_features:
        return
    licensed_set = set(licensed_features)
    modules = db.query(SystemModule).all()
    for module in modules:
        if module.is_always_enabled:
            continue
        if module.module_name not in licensed_set and module.is_enabled:
            module.is_enabled = False
    db.commit()


def is_license_valid_for_login(db: Session, role_name: str) -> tuple[bool, str]:
    """Check if a user with the given role is allowed to log in.
    Super_admin and hospital_admin are always allowed (to upload/renew license).
    Returns (allowed, reason).
    """
    if role_name in ("super_admin", "hospital_admin"):
        return True, ""

    license_record = get_current_license(db)
    if not license_record:
        return False, "No valid license installed. Contact your administrator."

    status = compute_license_status(license_record.expires_at)
    if status == STATUS_EXPIRED:
        return False, "License has expired. Contact your administrator to renew."

    return True, ""


def _status_message(status: str, days_remaining: int) -> str:
    if status == STATUS_ACTIVE:
        return f"License active. {days_remaining} days remaining."
    elif status == STATUS_EXPIRING_SOON:
        return f"License expiring in {days_remaining} days. Please renew soon."
    elif status == STATUS_GRACE_PERIOD:
        grace_left = GRACE_PERIOD_DAYS + days_remaining  # days_remaining is negative
        return f"License expired! Grace period: {grace_left} days remaining. Renew immediately."
    else:
        return "License has expired. System access is restricted."
