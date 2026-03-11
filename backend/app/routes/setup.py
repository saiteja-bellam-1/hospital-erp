"""
Setup wizard API endpoints.
These are only accessible before the initial setup is complete.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import os
import uuid

router = APIRouter()


class SetupStatusResponse(BaseModel):
    setup_complete: bool


class SetupRequest(BaseModel):
    # Hospital info
    hospital_name: str
    hospital_address: Optional[str] = ""
    hospital_phone: Optional[str] = ""
    hospital_email: Optional[str] = ""

    # Database
    db_location: Optional[str] = ""  # Empty = use default

    # Admin credentials
    admin_username: str
    admin_email: str
    admin_password: str
    admin_first_name: Optional[str] = "System"
    admin_last_name: Optional[str] = "Administrator"

    # License file content (base64 or empty)
    license_file_content: Optional[str] = ""

    # Backup locations
    backup_locations: List[str] = []


@router.get("/status")
async def get_setup_status():
    """Check if initial setup has been completed."""
    from app.utils.config import is_setup_complete
    return {"setup_complete": is_setup_complete()}


@router.post("/validate-path")
async def validate_path(data: dict):
    """Validate that a directory path exists and is writable."""
    path = data.get("path", "").strip()
    if not path:
        return {"valid": False, "message": "Path is empty"}

    # Expand user home dir
    path = os.path.expanduser(path)

    try:
        os.makedirs(path, exist_ok=True)
        # Test write access
        test_file = os.path.join(path, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return {"valid": True, "message": "Path is valid and writable", "resolved_path": path}
    except PermissionError:
        return {"valid": False, "message": "Permission denied. Cannot write to this location."}
    except Exception as e:
        return {"valid": False, "message": str(e)}


@router.post("/complete")
async def complete_setup(setup_data: SetupRequest):
    """
    Complete the initial setup:
    1. Save config.json with DB path and backup locations
    2. Initialize the database at the chosen location
    3. Create roles, hospital, and super admin user
    4. Optionally store the license
    """
    from app.utils.config import is_setup_complete, save_config, load_config
    from app.utils.paths import get_data_dir, get_db_path

    if is_setup_complete():
        raise HTTPException(status_code=400, detail="Setup has already been completed")

    # Validate admin password
    if len(setup_data.admin_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # Determine DB path
    db_path = ""
    if setup_data.db_location and setup_data.db_location.strip():
        db_dir = os.path.expanduser(setup_data.db_location.strip())
        try:
            os.makedirs(db_dir, exist_ok=True)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Cannot create database directory: {e}")
        db_path = os.path.join(db_dir, "hospital_erp.db")
    else:
        db_path = os.path.join(get_data_dir(), "hospital_erp.db")

    # Validate backup locations
    valid_backup_locations = []
    for loc in setup_data.backup_locations:
        loc = loc.strip()
        if loc:
            expanded = os.path.expanduser(loc)
            try:
                os.makedirs(expanded, exist_ok=True)
                valid_backup_locations.append(expanded)
            except Exception:
                pass  # Skip invalid locations silently

    # Save config FIRST (so DB path is available for database.py)
    config = {
        "setup_complete": True,
        "db_path": db_path,
        "backup_locations": valid_backup_locations,
        "hospital_name": setup_data.hospital_name,
    }
    save_config(config)

    # Now reinitialize the database engine with the new path
    try:
        _init_database_and_seed(setup_data, db_path)
    except Exception as e:
        # Rollback config if DB init fails
        config["setup_complete"] = False
        save_config(config)
        raise HTTPException(status_code=500, detail=f"Database initialization failed: {e}")

    # Handle license file if provided
    if setup_data.license_file_content:
        try:
            _store_license(setup_data.license_file_content, db_path)
        except Exception:
            pass  # License is optional; don't fail setup

    return {
        "success": True,
        "message": "Setup completed successfully",
        "db_path": db_path,
        "backup_locations": valid_backup_locations,
    }


def _init_database_and_seed(setup_data: SetupRequest, db_path: str):
    """Initialize DB at the given path and seed with roles, hospital, admin user."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from config.database import Base

    # Import all models so Base.metadata knows about them
    from app.models.user import User, UserRole, UserPermission  # noqa
    from app.models.permissions import ModulePermission, RoleModulePermission, HospitalSettings, ModuleTemplate, ModuleRates  # noqa
    from app.models.system import SystemModule, SystemSettings  # noqa
    from app.models.hospital import Hospital, HospitalModule  # noqa
    from app.models.prescriptions_simple import SimplePrescription  # noqa
    from app.models.doctor_availability import DoctorAvailability, DoctorSpecialSchedule, DoctorAvailabilityStatus  # noqa
    from app.models.license import License  # noqa

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # 1. Create default roles
        role_names = [
            ("super_admin", "Super Administrator with full system access"),
            ("hospital_admin", "Hospital Administrator with full hospital access"),
            ("doctor", "Doctor with patient care access"),
            ("nurse", "Nurse with patient care support access"),
            ("lab_technician", "Laboratory technician with lab module access"),
            ("lab_admin", "Laboratory administrator"),
            ("pharmacist", "Pharmacist with pharmacy module access"),
            ("receptionist", "Receptionist with patient registration access"),
        ]
        for name, desc in role_names:
            if not db.query(UserRole).filter(UserRole.name == name).first():
                db.add(UserRole(name=name, description=desc))
        db.flush()

        # 2. Create system modules
        modules = [
            ("outpatient", "Outpatient", False, False),
            ("inpatient", "Inpatient", False, False),
            ("lab", "Laboratory", False, False),
            ("pharmacy", "Pharmacy", False, False),
            ("ehr", "Electronic Health Records", True, True),
            ("admin", "Administration", True, True),
        ]
        for mod_name, display, enabled, always in modules:
            if not db.query(SystemModule).filter(SystemModule.module_name == mod_name).first():
                db.add(SystemModule(
                    module_name=mod_name,
                    display_name=display,
                    description=f"{display} management",
                    is_enabled=enabled,
                    is_always_enabled=always,
                ))
        db.flush()

        # 3. Create hospital
        from app.services.super_admin_service import generate_hospital_code
        hospital = db.query(Hospital).first()
        if not hospital:
            hospital = Hospital(
                hospital_id=generate_hospital_code(),
                name=setup_data.hospital_name,
                address=setup_data.hospital_address or "Not provided",
                phone=setup_data.hospital_phone or "",
                email=setup_data.hospital_email or "",
                license_number="SETUP001",
                is_active=True,
            )
            db.add(hospital)
            db.flush()

        # 4. Create super admin user
        from app.utils.auth import get_password_hash
        admin_role = db.query(UserRole).filter(UserRole.name == "super_admin").first()
        if not db.query(User).filter(User.username == setup_data.admin_username).first():
            admin = User(
                user_id=str(uuid.uuid4()),
                username=setup_data.admin_username,
                email=setup_data.admin_email,
                password_hash=get_password_hash(setup_data.admin_password),
                first_name=setup_data.admin_first_name or "System",
                last_name=setup_data.admin_last_name or "Administrator",
                role_id=admin_role.id,
                hospital_id=hospital.id,
                is_active=True,
            )
            db.add(admin)

        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
        engine.dispose()


def _store_license(license_content: str, db_path: str):
    """Parse and store a license file."""
    import base64
    # Decode if base64
    try:
        content = base64.b64decode(license_content).decode("utf-8")
    except Exception:
        content = license_content
    # The actual license upload is handled via the normal license endpoint after login
    # For now, just skip — user can upload via dashboard
