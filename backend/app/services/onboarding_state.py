"""Derived progress for the optional post-install hospital onboarding wizard."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.hospital import Hospital
from app.models.inpatient import (
    AncillaryServiceCatalog,
    DoctorRoomTypeRate,
    RoomManagement,
    RoomTypeRateConfig,
)
from app.models.lab import LabTest
from app.models.license import License
from app.models.outpatient import OutpatientProcedure
from app.models.permissions import HospitalSettings
from app.models.pharmacy import Medicine, PharmacyInventory, PharmacySupplier
from app.models.system import SystemModule
from app.models.user import User
from app.services.license_service import get_current_license
from app.utils.config import get_backup_locations
from app.utils.paths import get_uploads_dir


def get_enabled_module_names(db: Session) -> set[str]:
    """Modules that are truly available right now.

    Mirrors ``/api/system/enabled-modules``: a module counts as enabled only
    when the admin toggle is on AND (there is no license yet, or the license
    lists the module in its features). Keeping this identical to the rest of
    the app is what makes the setup flow adapt to the modules a hospital
    actually has.
    """
    modules = db.query(SystemModule).all()
    license_record = get_current_license(db)
    licensed_features = set(license_record.features) if license_record and license_record.features else set()

    enabled: set[str] = set()
    for module in modules:
        if licensed_features:
            is_on = module.is_enabled and module.module_name in licensed_features
        else:
            is_on = module.is_enabled
        if is_on or module.is_always_enabled:
            enabled.add(module.module_name)
    return enabled


SETUP_CATEGORY = "onboarding"
MANUAL_COMPLETION_KEYS = {"print_settings", "role_permissions", "payer_schemes"}

STEP_DEFINITIONS = (
    {
        "key": "license_modules",
        "label": "License and modules",
        "description": "Confirm the license and choose the modules this hospital will use.",
        "required": True,
        "path": "/dashboard/license",
        "minutes": 5,
    },
    {
        "key": "hospital_profile",
        "label": "Hospital profile",
        "description": "Hospital name, address, contact details, registration and MRN prefix.",
        "required": True,
        "path": "/dashboard/hospital-admin",
        "minutes": 10,
    },
    {
        "key": "logo",
        "label": "Hospital logo",
        "description": "Upload a PNG, JPEG or WebP logo (maximum 2 MB).",
        "required": True,
        "path": "/dashboard/hospital-admin",
        "minutes": 5,
    },
    {
        "key": "print_settings",
        "label": "PDF and print settings",
        "description": "Review letterhead, footer, billing detail and prescription settings.",
        "required": True,
        "path": "/dashboard/print-settings",
        "minutes": 10,
    },
    {
        "key": "departments",
        "label": "Departments and wards",
        "description": "Create a consistent picklist for department and ward names.",
        "required": False,
        "path": "/dashboard/setup",
        "minutes": 5,
    },
    {
        "key": "users",
        "label": "Doctors, nurses and staff",
        "description": "Create users individually or use the downloadable sample files.",
        "required": True,
        "path": "/dashboard/admin",
        "minutes": 15,
    },
    {
        "key": "role_permissions",
        "label": "Role permissions",
        "description": "Review the default permissions and adjust them if necessary.",
        "required": False,
        "path": "/dashboard/admin",
        "minutes": 10,
    },
    {
        "key": "opd_registration_fee",
        "label": "OPD registration fee",
        "description": "Set the one-time fee charged when a new outpatient is registered.",
        "required": True,
        "path": "/dashboard/hospital-admin",
        "minutes": 3,
        "module": "outpatient",
    },
    {
        "key": "opd_procedures",
        "label": "OPD / day-care procedures",
        "description": "Create the outpatient procedure price list (optional for go-live).",
        "required": False,
        "path": "/dashboard/reception/procedures",
        "minutes": 10,
        "module": "outpatient",
    },
    {
        "key": "rooms_and_beds",
        "label": "Rooms and beds",
        "description": "Create wards, rooms and beds with daily room charges.",
        "required": True,
        "path": "/dashboard/inpatient/rooms",
        "minutes": 20,
        "module": "inpatient",
    },
    {
        "key": "room_type_nursing_rates",
        "label": "Nursing rates by room type",
        "description": "Set the default nursing visit charge for each room type.",
        "required": True,
        "path": "/dashboard/inpatient/billing-setup",
        "minutes": 10,
        "module": "inpatient",
    },
    {
        "key": "doctor_ip_rates",
        "label": "Doctor inpatient visit rates",
        "description": "Confirm each doctor's inpatient fee and optional room-type overrides.",
        "required": False,
        "path": "/dashboard/admin",
        "minutes": 10,
        "module": "inpatient",
    },
    {
        "key": "ancillary_catalog",
        "label": "Ancillary services",
        "description": "Imaging, oxygen, physiotherapy and other chargeable services.",
        "required": False,
        "path": "/dashboard/inpatient/billing-setup",
        "minutes": 15,
        "module": "inpatient",
    },
    {
        "key": "payer_schemes",
        "label": "Payer / payment types",
        "description": "Review Cash, TPA, insurance and government scheme options used on admissions.",
        "required": False,
        "path": "/dashboard/hospital-admin",
        "minutes": 5,
        "module": "inpatient",
    },
    {
        "key": "lab_catalogue",
        "label": "Laboratory catalogue",
        "description": "Import tests from Excel or install the starter catalogue.",
        "required": False,
        "path": "/dashboard/lab",
        "minutes": 15,
        "module": "lab",
    },
    {
        "key": "pharmacy_medicines",
        "label": "Pharmacy medicine catalogue",
        "description": "Import medicines from Excel. Categories, companies and other masters are created automatically when missing.",
        "required": True,
        "path": "/dashboard/pharmacy/medicines",
        "minutes": 20,
        "module": "pharmacy",
    },
    {
        "key": "pharmacy_suppliers",
        "label": "Pharmacy suppliers",
        "description": "Import supplier ledgers used for purchases and opening stock.",
        "required": True,
        "path": "/dashboard/pharmacy/suppliers",
        "minutes": 10,
        "module": "pharmacy",
    },
    {
        "key": "pharmacy_opening_stock",
        "label": "Pharmacy opening stock",
        "description": "Seed starting batches and quantities (optional — can wait until first purchase).",
        "required": False,
        "path": "/dashboard/pharmacy/inventory",
        "minutes": 15,
        "module": "pharmacy",
    },
    {
        "key": "backup",
        "label": "Backup",
        "description": "Choose at least one backup location and run a test backup.",
        "required": True,
        "path": "/dashboard/backup",
        "minutes": 10,
    },
)


def _setting(db: Session, key: str) -> HospitalSettings | None:
    return (
        db.query(HospitalSettings)
        .filter(
            HospitalSettings.setting_category == SETUP_CATEGORY,
            HospitalSettings.setting_key == key,
        )
        .first()
    )


def _json_value(row: HospitalSettings | None, default: Any = None) -> Any:
    if not row or not row.setting_value:
        return default
    try:
        return json.loads(row.setting_value)
    except (TypeError, json.JSONDecodeError):
        return default


def set_json_setting(
    db: Session,
    key: str,
    value: Any,
    *,
    user_id: int | None = None,
    description: str | None = None,
) -> None:
    row = _setting(db, key)
    encoded = json.dumps(value)
    if row:
        row.setting_value = encoded
        row.setting_type = "json"
        row.created_by = user_id
    else:
        db.add(
            HospitalSettings(
                setting_category=SETUP_CATEGORY,
                setting_key=key,
                setting_value=encoded,
                setting_type="json",
                description=description,
                created_by=user_id,
            )
        )


def _logo_exists(hospital: Hospital | None) -> bool:
    if not hospital or not hospital.logo_url:
        return False
    relative = hospital.logo_url.split("/uploads/", 1)[-1].replace("/", os.sep)
    return os.path.isfile(os.path.join(get_uploads_dir(), relative))


def _registration_fee_configured(db: Session) -> bool:
    return (
        db.query(HospitalSettings)
        .filter(
            HospitalSettings.setting_category == "billing",
            HospitalSettings.setting_key == "registration_fee",
        )
        .first()
        is not None
    )


def _doctor_ip_rates_ready(db: Session, hospital_id: int | None) -> bool:
    if not hospital_id:
        return False
    doctors = [
        user
        for user in db.query(User).filter(
            User.is_active.is_(True),
            User.hospital_id == hospital_id,
        ).all()
        if user.has_role("doctor")
    ]
    if not doctors:
        return False
    with_fee = 0
    for doctor in doctors:
        try:
            if float(doctor.inpatient_fee_inr or 0) > 0:
                with_fee += 1
        except (TypeError, ValueError):
            continue
    overrides = (
        db.query(DoctorRoomTypeRate)
        .filter(DoctorRoomTypeRate.hospital_id == hospital_id)
        .count()
    )
    return with_fee == len(doctors) or overrides > 0


def _derived_completion(db: Session, hospital: Hospital | None) -> dict[str, bool]:
    hospital_id = hospital.id if hospital else None
    print_configured = (
        db.query(HospitalSettings)
        .filter(HospitalSettings.setting_category == "print")
        .first()
        is not None
    )
    staff_count = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .filter(User.hospital_id == hospital_id)
        .count()
    )
    departments = _json_value(_setting(db, "departments"), [])
    return {
        "license_modules": db.query(License).count() > 0,
        "hospital_profile": bool(
            hospital and hospital.name and hospital.address and hospital.phone
        ),
        "logo": _logo_exists(hospital),
        "print_settings": print_configured,
        "departments": bool(departments),
        "users": staff_count > 1,
        "role_permissions": False,
        "opd_registration_fee": _registration_fee_configured(db),
        "opd_procedures": (
            db.query(OutpatientProcedure)
            .filter(OutpatientProcedure.hospital_id == hospital_id)
            .filter(OutpatientProcedure.is_active.is_(True))
            .count()
            > 0
        ),
        "rooms_and_beds": (
            db.query(RoomManagement)
            .filter(RoomManagement.hospital_id == hospital_id)
            .filter(RoomManagement.is_active.is_(True))
            .count()
            > 0
        ),
        "room_type_nursing_rates": (
            db.query(RoomTypeRateConfig)
            .filter(RoomTypeRateConfig.hospital_id == hospital_id)
            .filter(RoomTypeRateConfig.nursing_charge_per_visit.isnot(None))
            .count()
            > 0
        ),
        "doctor_ip_rates": _doctor_ip_rates_ready(db, hospital_id),
        "ancillary_catalog": (
            db.query(AncillaryServiceCatalog)
            .filter(AncillaryServiceCatalog.hospital_id == hospital_id)
            .filter(AncillaryServiceCatalog.is_active.is_(True))
            .count()
            > 0
        ),
        "payer_schemes": False,
        "lab_catalogue": (
            db.query(LabTest)
            .filter(LabTest.hospital_id == hospital_id)
            .count()
            > 0
        ),
        "pharmacy_medicines": (
            db.query(Medicine)
            .filter(Medicine.hospital_id == hospital_id)
            .filter(Medicine.is_active.is_(True))
            .count()
            > 0
        ),
        "pharmacy_suppliers": (
            db.query(PharmacySupplier)
            .filter(PharmacySupplier.hospital_id == hospital_id)
            .filter(PharmacySupplier.is_active.is_(True))
            .count()
            > 0
        ),
        "pharmacy_opening_stock": (
            db.query(PharmacyInventory)
            .filter(PharmacyInventory.hospital_id == hospital_id)
            .filter(PharmacyInventory.is_active.is_(True))
            .filter(PharmacyInventory.quantity_in_stock > 0)
            .count()
            > 0
        ),
        "backup": bool(get_backup_locations()),
    }


def get_onboarding_status(db: Session) -> dict[str, Any]:
    hospital = db.query(Hospital).filter(Hospital.is_active.is_(True)).first()
    enabled_modules = get_enabled_module_names(db)
    derived = _derived_completion(db, hospital)
    dismissed = bool(_json_value(_setting(db, "dismissed"), False))

    steps = []
    for definition in STEP_DEFINITIONS:
        module = definition.get("module")
        if module and module not in enabled_modules:
            continue
        manual = _json_value(_setting(db, f"step:{definition['key']}"), {}) or {}
        completed = bool(derived.get(definition["key"]) or manual.get("completed"))
        skipped = bool(manual.get("skipped")) and not completed
        steps.append({
            **definition,
            "completed": completed,
            "skipped": skipped,
            "can_mark_complete": definition["key"] in MANUAL_COMPLETION_KEYS,
        })

    required = [step for step in steps if step["required"]]
    complete_count = sum(1 for step in steps if step["completed"])
    required_complete = all(step["completed"] for step in required)
    return {
        "dismissed": dismissed,
        "completed": required_complete,
        "completed_count": complete_count,
        "total_count": len(steps),
        "required_completed_count": sum(1 for step in required if step["completed"]),
        "required_total_count": len(required),
        "steps": steps,
        "departments": _json_value(_setting(db, "departments"), []),
    }


def mark_step(
    db: Session, key: str, *, completed: bool, skipped: bool, user_id: int
) -> None:
    if key not in {step["key"] for step in STEP_DEFINITIONS}:
        raise KeyError(key)
    if completed and key not in MANUAL_COMPLETION_KEYS:
        raise ValueError(key)
    set_json_setting(
        db,
        f"step:{key}",
        {
            "completed": bool(completed),
            "skipped": bool(skipped),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        user_id=user_id,
        description=f"Onboarding state for {key}",
    )
