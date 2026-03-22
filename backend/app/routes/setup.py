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


@router.get("/debug-permissions")
async def debug_permissions():
    """Diagnostic endpoint to check role permissions state."""
    from config.database import SessionLocal
    from app.models.permissions import RoleModulePermission
    from app.models.user import UserRole
    from app.models.system import SystemModule

    db = SessionLocal()
    try:
        roles = db.query(UserRole).all()
        role_perms = db.query(RoleModulePermission).all()
        modules = db.query(SystemModule).all()

        return {
            "roles": [{"id": r.id, "name": r.name} for r in roles],
            "role_permissions_count": len(role_perms),
            "role_permissions": [
                {
                    "role_id": rp.role_id,
                    "module": rp.module_name,
                    "permissions": rp.permissions,
                }
                for rp in role_perms
            ],
            "modules": [
                {
                    "name": m.module_name,
                    "enabled": m.is_enabled,
                    "always_enabled": m.is_always_enabled,
                }
                for m in modules
            ],
        }
    finally:
        db.close()


@router.get("/browse-folder")
async def browse_folder():
    """Open a native OS folder picker dialog and return the selected path."""
    import subprocess
    import sys
    import platform

    folder = ""

    try:
        if platform.system() == "Darwin":
            # macOS: use AppleScript — activate Finder to bring dialog to front
            script = (
                'tell application "Finder"\n'
                '  activate\n'
                'end tell\n'
                'set theFolder to choose folder with prompt "Select Folder"\n'
                'return POSIX path of theFolder'
            )
            proc = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=120,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                folder = proc.stdout.strip().rstrip("/")

        elif platform.system() == "Windows":
            # Windows: create a hidden topmost form as dialog owner so it appears in front
            ps_script = (
                'Add-Type -AssemblyName System.Windows.Forms; '
                '[System.Windows.Forms.Application]::EnableVisualStyles(); '
                '$top = New-Object System.Windows.Forms.Form; '
                '$top.TopMost = $true; '
                '$top.MinimizeBox = $false; '
                '$top.MaximizeBox = $false; '
                '$top.Width = 0; $top.Height = 0; '
                '$top.StartPosition = "Manual"; '
                '$top.Location = New-Object System.Drawing.Point(-1000,-1000); '
                '$top.Show(); $top.BringToFront(); '
                '$f = New-Object System.Windows.Forms.FolderBrowserDialog; '
                '$f.Description = "Select Folder"; '
                '$f.ShowNewFolderButton = $true; '
                '$result = $f.ShowDialog($top); '
                '$top.Close(); '
                'if ($result -eq [System.Windows.Forms.DialogResult]::OK) { '
                '  $f.SelectedPath '
                '}'
            )
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-STA", "-Command", ps_script],
                capture_output=True, text=True, timeout=120,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                folder = proc.stdout.strip()

        else:
            # Linux: try zenity, then kdialog, then tkinter as fallback
            for cmd in [
                ["zenity", "--file-selection", "--directory", "--title=Select Folder"],
                ["kdialog", "--getexistingdirectory", "."],
            ]:
                try:
                    proc = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=120,
                    )
                    if proc.returncode == 0 and proc.stdout.strip():
                        folder = proc.stdout.strip()
                        break
                except FileNotFoundError:
                    continue

    except (subprocess.TimeoutExpired, Exception):
        pass

    return {"path": folder}


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
        db_path = os.path.join(db_dir, "kthealth_erp.db")
    else:
        db_path = os.path.join(get_data_dir(), "kthealth_erp.db")

    # Validate backup locations
    valid_backup_locations = []
    failed_backup_locations = []
    for loc in setup_data.backup_locations:
        loc = loc.strip()
        if loc:
            expanded = os.path.expanduser(loc)
            try:
                os.makedirs(expanded, exist_ok=True)
                valid_backup_locations.append(expanded)
            except Exception as e:
                failed_backup_locations.append({"path": loc, "error": str(e)})

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

    # Reinitialize the global DB engine to point at the new path
    from config.database import reinitialize_engine
    reinitialize_engine()

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
        "failed_backup_locations": failed_backup_locations,
    }


def _init_database_and_seed(setup_data: SetupRequest, db_path: str):
    """Initialize DB at the given path and seed with roles, hospital, admin user."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from config.database import Base

    # Import ALL models so Base.metadata knows about them
    from app.models.user import User, UserRole, UserPermission  # noqa
    from app.models.permissions import ModulePermission, RoleModulePermission, HospitalSettings, ModuleTemplate, ModuleRates  # noqa
    from app.models.system import SystemModule, SystemSettings  # noqa
    from app.models.hospital import Hospital, HospitalModule  # noqa
    from app.models.prescriptions_simple import SimplePrescription  # noqa
    from app.models.doctor_availability import DoctorAvailability, DoctorSpecialSchedule, DoctorAvailabilityStatus  # noqa
    from app.models.license import License  # noqa
    from app.models.lab import LabTestCategory, LabTest, LabTestParameter, LabReport, PatientLabOrder  # noqa
    from app.models.lab import LabTestPackageCategory, LabTestPackage  # noqa
    from app.models.billing import PaymentMethod, Bill, BillItem, Payment  # noqa
    from app.models.ehr import Consultation  # noqa
    from app.models.outpatient import Appointment  # noqa
    from app.models.patient import Patient  # noqa
    from app.models.referral import Referral  # noqa

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    # Run column migrations for any new columns added after initial table creation
    try:
        from sqlalchemy import text
        from migrate_patient_fields import NEW_COLUMNS
        with engine.connect() as conn:
            for table, col, col_type in NEW_COLUMNS:
                result = conn.execute(text(f"PRAGMA table_info({table})"))
                existing = {row[1] for row in result.fetchall()}
                if col not in existing:
                    try:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                    except Exception:
                        pass
            conn.commit()
    except Exception:
        pass  # Migrations are best-effort during setup

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
            ("outpatient", "Outpatient", True, False),       # Enabled by default, toggleable
            ("inpatient", "Inpatient", False, False),         # Disabled by default, toggleable
            ("lab", "Laboratory", False, False),              # Disabled by default, toggleable
            ("pharmacy", "Pharmacy", False, False),           # Disabled by default, toggleable
            ("ehr", "Electronic Health Records", True, False),# Enabled by default, toggleable
            ("billing", "Billing", True, True),               # Always enabled
            ("admin", "Administration", True, True),          # Always enabled
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
        existing_by_name = db.query(User).filter(User.username == setup_data.admin_username).first()
        existing_by_email = db.query(User).filter(User.email == setup_data.admin_email).first()
        if not existing_by_name and not existing_by_email:
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
            db.flush()  # Flush now before seeding permissions to avoid autoflush issues

        # 5. Create role-module permissions for all roles
        with db.no_autoflush:
            _seed_role_permissions(db, UserRole, RoleModulePermission)

        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
        engine.dispose()


def _seed_role_permissions(db, UserRole, RoleModulePermission):
    """Create RoleModulePermission records so each role can access its modules."""
    role_permissions_map = {
        "super_admin": {
            "admin": ["manage_users", "manage_roles", "manage_modules", "view_system_reports", "manage_settings"],
            "lab": ["manage_tests", "set_rates", "view_reports", "create_reports", "manage_equipment", "manage_templates"],
            "pharmacy": ["manage_inventory", "set_drug_rates", "dispense_medications", "view_prescriptions", "manage_suppliers", "generate_reports"],
            "billing": ["manage_rates", "process_payments", "generate_invoices", "view_financial_reports", "manage_insurance", "handle_refunds"],
            "outpatient": ["schedule_appointments", "manage_schedules", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "inpatient": ["manage_beds", "admit_patients", "discharge_patients", "manage_wards", "set_room_rates", "view_occupancy"],
            "ehr": ["view_records", "edit_records", "create_prescriptions", "manage_templates", "view_history", "generate_reports"],
        },
        "hospital_admin": {
            "admin": ["manage_users", "manage_roles", "view_system_reports", "manage_settings"],
            "lab": ["view_reports", "create_reports"],
            "pharmacy": ["view_prescriptions", "generate_reports"],
            "billing": ["view_financial_reports", "manage_insurance", "process_payments", "generate_invoices"],
            "outpatient": ["schedule_appointments", "manage_schedules", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "inpatient": ["view_occupancy"],
            "ehr": ["view_records", "edit_records", "view_history", "generate_reports"],
        },
        "doctor": {
            "ehr": ["view_records", "edit_records", "create_prescriptions", "view_history", "generate_reports"],
            "lab": ["view_reports", "create_reports"],
            "pharmacy": ["view_prescriptions"],
            "outpatient": ["view_appointments", "view_patients", "schedule_appointments", "update_appointments", "register_patients", "manage_queues", "cancel_appointments"],
            "inpatient": ["admit_patients", "discharge_patients", "view_occupancy"],
        },
        "nurse": {
            "ehr": ["view_records", "edit_records", "view_history"],
            "inpatient": ["view_occupancy"],
            "outpatient": ["manage_queues", "view_appointments"],
        },
        "receptionist": {
            "outpatient": ["schedule_appointments", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "billing": ["process_payments", "generate_invoices", "view_financial_reports"],
            "ehr": ["view_records", "view_history"],
        },
        "lab_admin": {
            "lab": ["manage_tests", "set_rates", "view_reports", "create_reports", "manage_equipment", "manage_templates"],
        },
        "lab_technician": {
            "lab": ["view_reports", "create_reports"],
        },
        "pharmacist": {
            "pharmacy": ["dispense_medications", "view_prescriptions", "manage_inventory"],
        },
    }

    for role_name, module_perms in role_permissions_map.items():
        role = db.query(UserRole).filter(UserRole.name == role_name).first()
        if not role:
            continue
        for module_name, permissions in module_perms.items():
            existing = db.query(RoleModulePermission).filter(
                RoleModulePermission.role_id == role.id,
                RoleModulePermission.module_name == module_name,
            ).first()
            if existing:
                existing.permissions = permissions
            else:
                db.add(RoleModulePermission(
                    role_id=role.id,
                    module_name=module_name,
                    permissions=permissions,
                ))


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
