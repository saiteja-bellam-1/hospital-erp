from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.license import License
from app.licensing.crypto import verify_license_file

# Re-export pure helpers + status constants from license_inspect so this
# module's public surface is unchanged for every backend consumer. The pure
# helpers live in a SQLAlchemy-free module so the Inno Setup wizard's
# dbcheck.exe can import them without dragging the ORM into its PyInstaller
# build.
from app.services.license_inspect import (
    STATUS_ACTIVE,
    STATUS_EXPIRING_SOON,
    STATUS_GRACE_PERIOD,
    STATUS_EXPIRED,
    STATUS_NO_LICENSE,
    STATUS_MACHINE_MISMATCH,
    EXPIRING_SOON_DAYS,
    GRACE_PERIOD_DAYS,
    compute_license_status,
    verify_license_machine_binding,
    inspect_license_file,
    resolve_support_contact,
    seller_public_info,
)


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


# Optional paid add-on (not a SystemModule). Issued from License Manager.
FEATURE_CUSTOMISATION = "customisation"


def get_current_license(db: Session) -> License | None:
    """Get the most recent license from DB."""
    return db.query(License).order_by(License.id.desc()).first()


def _license_authoritative(license_record) -> bool:
    """A paid license wins over the trial only while it is still usable here.

    Expired and machine-mismatched rows do not count. Grace period does.
    """
    if not license_record:
        return False
    if compute_license_status(license_record.expires_at) == STATUS_EXPIRED:
        return False
    binding_ok, _, _ = verify_license_machine_binding(license_record)
    return bool(binding_ok)


def licensed_feature_names(db: Session) -> set | None:
    """Module names the current grant allows.

    ``None`` means there is no feature filter: no usable license and no active
    trial. Callers then keep today's no-license behavior (admin toggle only).
    An active trial allows every product module and not the paid add-ons.
    """
    from app.services.trial import STATUS_TRIAL, TRIAL_FEATURES, trial_status

    record = get_current_license(db)
    if _license_authoritative(record):
        return set(record.features or [])
    trial = trial_status(touch=False)
    if trial.get("status") == STATUS_TRIAL:
        return set(TRIAL_FEATURES)
    if record and record.features:
        return set(record.features)
    return None


def license_denies_module(db: Session, module: str) -> bool:
    """True when this module is outside the current license or trial grant."""
    names = licensed_feature_names(db)
    if names is None:
        return False
    return module not in names


def license_has_feature(db: Session, feature: str) -> bool:
    """True when the installed license lists ``feature`` in its features array."""
    license_record = get_current_license(db)
    features = license_record.features if license_record and license_record.features else []
    return feature in features


def license_allows_customisation(db: Session) -> bool:
    """White-label branding (app name, logo, favicon) requires this license add-on.

    Document / print customisations (letterhead, bills, vitals, etc.) are always
    available and are not gated by this feature.
    """
    return license_has_feature(db, FEATURE_CUSTOMISATION)


def build_rebind_request_payload(
    raw_license_data: str,
    *,
    license_id: str | None = None,
    hospital_id: str | None = None,
    hospital_name: str | None = None,
    requested_by: str = "",
) -> dict:
    """Build a ``.rebind.json`` request payload from a signed ``.lic`` string.

    Shared by two callers:
      - the License Management page, where the license is already installed in
        the running DB, and
      - the Backup restore flow, where the license is read straight out of a
        backup ``.db`` that was created on another machine (so it can never be
        loaded into the running app because of the machine-binding guard).

    Metadata (license_id / hospital_id / hospital_name) falls back to the
    values inside the signed payload when explicit values aren't supplied. The
    ``license_signature_proof_sha256`` lets the vendor's License Manager
    confirm the requester actually holds the original signed ``.lic`` before
    re-issuing.
    """
    import hashlib
    from datetime import datetime as _dt
    from app.utils.machine_id import get_machine_id_full

    try:
        signed = verify_license_file(raw_license_data)
    except Exception:
        signed = {}

    machine = get_machine_id_full()
    new_machine_id = machine["machine_id"]
    old_machine_id = signed.get("machine_id", "") or ""
    proof = hashlib.sha256(raw_license_data.encode("utf-8")).hexdigest()

    return {
        "request_type": "license_rebind",
        "request_version": 1,
        "license_id": license_id or signed.get("license_id"),
        "hospital_id": hospital_id or signed.get("hospital_id"),
        "hospital_name": hospital_name or signed.get("hospital_name"),
        "old_machine_id": old_machine_id,
        "new_machine_id": new_machine_id,
        "new_machine_hostname": machine.get("hostname"),
        "new_machine_os": machine.get("os"),
        "requested_by": requested_by,
        "requested_at": _dt.utcnow().isoformat() + "Z",
        "license_signature_proof_sha256": proof,
    }


def _no_license_status() -> dict:
    return {
        "status": STATUS_NO_LICENSE,
        "message": "No license installed",
        "days_remaining": 0,
        "expires_at": None,
        "plan": None,
        "max_users": 0,
        "features": [],
        "support_contact": None,
    }


def _trial_status_payload(trial: dict, *, expired: bool) -> dict:
    from app.services.trial import STATUS_TRIAL, STATUS_TRIAL_EXPIRED, TRIAL_FEATURES

    days = int(trial.get("days_remaining") or 0)
    if expired:
        message = (
            "Trial ended on this computer. "
            "Upload a license from License Management to restore staff access."
        )
        status = STATUS_TRIAL_EXPIRED
        days = 0
    else:
        message = (
            f"Trial active. {days} days remaining. "
            "Upload a license to keep access after the trial ends."
        )
        status = STATUS_TRIAL
    return {
        "status": status,
        "message": message,
        "days_remaining": days,
        "expires_at": trial.get("expires_at"),
        "plan": "trial",
        "max_users": 0,
        "features": list(TRIAL_FEATURES),
        "hospital_name": None,
        "license_id": None,
        "issued_at": trial.get("started_at"),
        "seller_info": None,
        "support_contact": None,
        "machine_match": True,
    }


def _license_record_status(db: Session, license_record) -> dict:
    status = compute_license_status(license_record.expires_at)
    days_remaining = (license_record.expires_at - datetime.utcnow()).days

    # Re-verify machine binding at runtime — catches "DB copied to a new
    # machine" scenarios that the upload-time check can't see.
    binding_ok, license_machine_id, current_machine_id = verify_license_machine_binding(license_record)
    if not binding_ok:
        status = STATUS_MACHINE_MISMATCH

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
        "seller_info": seller_public_info(license_record.seller_info),
        "support_contact": resolve_support_contact(
            license_record.seller_info,
            license_record.support_info,
        ),
        "machine_match": binding_ok,
        "license_machine_id": license_machine_id,
        "current_machine_id": current_machine_id,
    }


def get_license_status(db: Session) -> dict:
    """Get current license status info for API responses.

    A usable paid license wins. Otherwise an active trial unlocks every
    product module. An expired trial on this PC stays expired across reinstalls.
    """
    from app.services.trial import STATUS_TRIAL, STATUS_TRIAL_EXPIRED, trial_status

    license_record = get_current_license(db)
    if _license_authoritative(license_record):
        return _license_record_status(db, license_record)

    trial = trial_status(touch=True)
    if trial.get("status") == STATUS_TRIAL:
        return _trial_status_payload(trial, expired=False)
    if license_record:
        return _license_record_status(db, license_record)
    if trial.get("status") == STATUS_TRIAL_EXPIRED:
        return _trial_status_payload(trial, expired=True)
    return _no_license_status()


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

    # Features from the currently-installed license (if any), used so we only
    # auto-enable modules that are *newly* covered by this upload — not ones
    # an admin previously turned off while already licensed.
    prior = get_current_license(db)
    previous_features = list(prior.features or []) if prior else []

    # Check if this license_id already exists (re-upload)
    existing = db.query(License).filter(
        License.license_id == license_data["license_id"]
    ).first()

    from app.utils.vendor_logo import materialize_seller

    raw_seller = license_data.get("seller")
    seller_info = materialize_seller(raw_seller if isinstance(raw_seller, dict) else None)
    support_info = None
    if not seller_info:
        support_info = resolve_support_contact(None, license_data.get("support"))

    if existing:
        # Update existing record
        existing.hospital_id = license_data.get("hospital_id", existing.hospital_id)
        existing.hospital_name = license_data.get("hospital_name", existing.hospital_name)
        existing.plan = license_data.get("plan", existing.plan)
        existing.max_users = license_data.get("max_users", existing.max_users)
        existing.features = license_data.get("features", existing.features)
        existing.seller_info = seller_info
        existing.support_info = support_info
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
            seller_info=seller_info,
            support_info=support_info,
            gdrive_config=_build_gdrive_config(license_data),
            issued_at=issued_at,
            expires_at=expires_at,
            status=status,
            raw_license_data=file_content,
            uploaded_by=uploaded_by,
        )
        db.add(new_license)
        db.commit()

    # Heal missing SystemModule rows + disable dropped features + enable newly
    # licensed ones (e.g. physiotherapy added on renew after an app upgrade).
    _sync_modules_with_license(
        db,
        license_data.get("features", []),
        previous_features=previous_features,
    )

    return get_license_status(db)


def _sync_modules_with_license(
    db: Session,
    licensed_features: list,
    previous_features: list | None = None,
):
    """Align system_modules with license features (create / enable / disable)."""
    from app.services.system_modules import sync_modules_with_license

    sync_modules_with_license(
        db,
        licensed_features or [],
        previous_features=previous_features,
    )


def is_license_valid_for_login(db: Session, role_name: str) -> tuple[bool, str]:
    """Check if a user with the given role is allowed to log in.
    Super_admin and hospital_admin are always allowed (to upload/renew license).
    Returns (allowed, reason).
    """
    if role_name in ("super_admin", "hospital_admin"):
        return True, ""

    from app.services.trial import STATUS_TRIAL, STATUS_TRIAL_EXPIRED, trial_status

    license_record = get_current_license(db)
    if _license_authoritative(license_record):
        return True, ""

    trial = trial_status(touch=False)
    if trial.get("status") == STATUS_TRIAL:
        return True, ""

    if license_record:
        status = compute_license_status(license_record.expires_at)
        if status == STATUS_EXPIRED:
            return False, "License has expired. Contact your administrator to renew."

        binding_ok, _, _ = verify_license_machine_binding(license_record)
        if not binding_ok:
            return False, (
                "This database appears to have been moved to a different computer. "
                "The installed license is not valid for this machine. "
                "Contact your administrator to request a license rebind."
            )
        return True, ""

    if trial.get("status") == STATUS_TRIAL_EXPIRED:
        return False, (
            "The 14-day trial on this computer has ended. "
            "Contact your administrator to install a license."
        )

    return False, "No valid license installed. Contact your administrator."


def _status_message(status: str, days_remaining: int) -> str:
    if status == STATUS_ACTIVE:
        return f"License active. {days_remaining} days remaining."
    elif status == STATUS_EXPIRING_SOON:
        return f"License expiring in {days_remaining} days. Please renew soon."
    elif status == STATUS_GRACE_PERIOD:
        grace_left = GRACE_PERIOD_DAYS + days_remaining  # days_remaining is negative
        return f"License expired! Grace period: {grace_left} days remaining. Renew immediately."
    elif status == STATUS_MACHINE_MISMATCH:
        return (
            "License is not valid for this machine. The database appears to have been "
            "moved to a different computer. Request a rebind license from your vendor."
        )
    else:
        return "License has expired. System access is restricted."
