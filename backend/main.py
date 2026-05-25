from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import uvicorn
import os

from app.utils.paths import get_uploads_dir, get_frontend_dir, is_bundled

from config.database import get_db, create_tables
from config.settings import settings
from app.utils.dependencies import get_current_user
from app.version import APP_VERSION

# Import all models to ensure proper relationship setup
from app.models.user import User, UserRole, UserPermission
from app.models.permissions import ModulePermission, RoleModulePermission, HospitalSettings, ModuleTemplate, ModuleRates
from app.models.system import SystemModule, SystemSettings
from app.models.hospital import Hospital, HospitalModule
from app.models.prescriptions_simple import SimplePrescription
from app.models.doctor_availability import DoctorAvailability, DoctorSpecialSchedule, DoctorAvailabilityStatus
from app.models.license import License
from app.models.inpatient import (
    RoomManagement, Admission, DischargeRecord, PatientVisit, InpatientRateConfig,
    OTSchedule, Bed, AdmissionDocument, NursingNote, VitalSigns, MedicationAdministration,
    AdmissionDeposit, AncillaryServiceCatalog, AdmissionAncillaryCharge, Procedure,
    SurgeryPackage, AdmissionPackage, InsurancePreAuth, InsurancePreAuthExpansion,
    TPACompany, BillSplit,
    BedTransferHistory, BedTurnoverLog, BedReservation, NurseAssignment, NurseShiftRoster,
    ConsentTemplate, Consent,
    FluidBalance, CriticalLabAlert,
)
from app.models.patient import PatientAllergy

# Import route modules
from app.routes import auth, patients, admin, system, module_admin, hospital_admin, appointments, prescriptions, medicines, consultations, prescriptions_simple, doctor_availability, lab, ehr, license, backup, referrals, audit, inpatient, outpatient_procedures
from app.middleware.license_middleware import LicenseMiddleware
from app.middleware.audit_middleware import AuditMiddleware
from app.middleware.maintenance import MaintenanceMiddleware

app = FastAPI(
    title=settings.app_name,
    description="Complete KT HEALTH ERP System",
    version=APP_VERSION
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (LAN access from any device + dev server)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-License-Status"],
)

# Middleware. Order matters: MaintenanceMiddleware runs first so writes get
# blocked before the audit middleware records them.
app.add_middleware(LicenseMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(MaintenanceMiddleware)

security = HTTPBearer()

@app.on_event("startup")
async def startup_event():
    from app.utils.config import is_setup_complete
    if is_setup_complete():
        create_tables()
        print("Database tables created successfully")
        # Run migrations under the schema-migrations tracker. A failed
        # migration is now LOUD: we abort startup instead of silently
        # serving a half-migrated DB. The recorded failure stays in
        # schema_migrations for the admin Diagnostics page.
        from config.database import engine as _engine
        from app.utils.schema_migrations import run_migration
        try:
            from migrate_patient_fields import migrate as _patient_migrate
            run_migration(_engine, "migrate_patient_fields", _patient_migrate)
        except Exception as e:
            raise RuntimeError(
                f"Schema migration migrate_patient_fields failed — refusing to boot. "
                f"See schema_migrations table for details. Error: {e}"
            )
        try:
            from migrate_inpatient_indexes import migrate_indexes as _idx_migrate
            run_migration(_engine, "migrate_inpatient_indexes", _idx_migrate)
        except Exception as e:
            raise RuntimeError(
                f"Schema migration migrate_inpatient_indexes failed — refusing to boot. Error: {e}"
            )
        try:
            from migrate_drop_incidents_diet import migrate_drop_incidents_diet as _drop_migrate
            run_migration(_engine, "migrate_drop_incidents_diet",
                          lambda: _drop_migrate(_engine))
        except Exception as e:
            raise RuntimeError(
                f"Schema migration migrate_drop_incidents_diet failed — refusing to boot. Error: {e}"
            )
        # Ensure role permissions exist (for installations that pre-date the wizard)
        _ensure_role_permissions()
        # Ensure all modules exist (add missing ones for upgrades)
        _ensure_modules()
        # Seed default payer schemes (Cash, Aarogyasri, Teachers, Govt Employee, Private Insurance, TPA)
        _ensure_payer_schemes()
        # Heal existing rows from the old `bill_type='procedure'` label to the
        # current `day_care` value, so the central billing dashboard groups them
        # under the right type after the rename.
        try:
            from config.database import get_db as _get_db
            from sqlalchemy import text as _sql_text
            _db = next(_get_db())
            res = _db.execute(_sql_text(
                "UPDATE bills SET bill_type = 'day_care' WHERE bill_type = 'procedure'"
            ))
            if res.rowcount:
                print(f"Renamed {res.rowcount} legacy 'procedure' bills to 'day_care'")
            _db.commit()
            _db.close()
        except Exception as _e:
            print(f"Warning: could not rename legacy procedure bills: {_e}")
        # Seed face-sheet + case-sheet consent templates with placeholder content
        _ensure_admission_consent_templates()
        # Cleanup old audit logs based on retention config
        try:
            from app.services.audit_service import cleanup_old_logs, get_retention_days
            from config.database import get_db as _get_db
            _db = next(_get_db())
            retention = get_retention_days(_db)
            deleted = cleanup_old_logs(_db, retention)
            if deleted > 0:
                print(f"Cleaned up {deleted} old audit log entries (>{retention} days)")
            _db.close()
        except Exception:
            pass
        # Start real-time mirror backup
        try:
            from app.utils.config import start_mirror_backup, get_backup_locations
            locations = get_backup_locations()
            if locations:
                start_mirror_backup(interval_seconds=60)
                print(f"Mirror backup started — syncing every 60s to {len(locations)} location(s)")
            else:
                print("No backup locations configured — mirror backup not started")
        except Exception as e:
            print(f"Mirror backup note: {e}")
        # Start scheduled snapshot backup
        try:
            from app.utils.config import start_snapshot_backup, load_config as _load_cfg
            _cfg = _load_cfg()
            snap_interval = _cfg.get("snapshot_interval_minutes", 30)
            if locations:
                start_snapshot_backup(interval_minutes=snap_interval)
                print(f"Snapshot backup started — every {snap_interval} min")
        except Exception as e:
            print(f"Snapshot backup note: {e}")
        # Start Google Drive backup thread
        try:
            from app.utils.config import start_gdrive_backup
            start_gdrive_backup(interval_minutes=10)
            print("Google Drive backup thread started — checking every 10 min")
        except Exception as e:
            print(f"Google Drive backup note: {e}")
        # Inpatient daily charges auto-post (one doctor visit per admitted
        # patient per day at the admitting doctor's fee). Idempotent — manually
        # recorded visits supersede the auto-post.
        try:
            from app.services.inpatient_daily_charges import start_daily_charges_thread
            start_daily_charges_thread(check_interval_seconds=3600)
            print("Inpatient daily-charges thread started — hourly check")
        except Exception as e:
            print(f"Daily-charges note: {e}")
    else:
        print("Setup not complete — first launch will apply install_seed.json via bootstrap_from_seed")


def _ensure_role_permissions():
    """Seed/update roles, module-permission catalog, and role permissions on every startup."""
    from config.database import SessionLocal
    from app.models.permissions import RoleModulePermission, ModulePermission
    from app.models.user import UserRole
    from app.services.db_seed import _seed_role_permissions, _seed_roles, _seed_module_permissions
    db = SessionLocal()
    try:
        # Ensure all system roles exist (heals pre-existing DBs that lack inpatient_admin etc.)
        _seed_roles(db, UserRole)
        # Ensure the module-permission catalog is fully populated
        _seed_module_permissions(db, ModulePermission)
        db.flush()
        # Always upsert role permissions (creates missing, updates existing)
        _seed_role_permissions(db, UserRole, RoleModulePermission)
        db.commit()
        print("Roles, module permissions, and role permissions synced")

        # Fix outpatient: make it toggleable (not always-on) for existing installs
        from app.models.system import SystemModule
        outpatient = db.query(SystemModule).filter(SystemModule.module_name == "outpatient").first()
        if outpatient and outpatient.is_always_enabled:
            outpatient.is_always_enabled = False
            db.commit()
            print("Updated outpatient module: now toggleable")
    except Exception as e:
        print(f"Warning: Could not seed role permissions: {e}")
        db.rollback()
    finally:
        db.close()


def _ensure_payer_schemes():
    """Seed default payer schemes per hospital, if missing. Idempotent."""
    from config.database import SessionLocal
    from app.models.inpatient import PayerScheme
    from app.models.hospital import Hospital
    defaults = [
        ("CASH",      "Cash",                          "cash"),
        ("PRIVATE",   "Private Insurance",             "private_insurance"),
        ("TPA",       "TPA (Third Party Administrator)", "tpa"),
        ("AAROGYASRI","Aarogyasri",                    "govt_scheme"),
        ("TEACHERS",  "Teachers' Health Scheme",       "govt_scheme"),
        ("EJHS",      "Employee Health Scheme",        "govt_scheme"),
    ]
    db = SessionLocal()
    try:
        hospitals = db.query(Hospital).all()
        for hospital in hospitals:
            for code, name, scheme_type in defaults:
                existing = db.query(PayerScheme).filter(
                    PayerScheme.hospital_id == hospital.id,
                    PayerScheme.code == code,
                ).first()
                if not existing:
                    db.add(PayerScheme(
                        hospital_id=hospital.id,
                        code=code, name=name, scheme_type=scheme_type,
                        active=True,
                    ))
        db.commit()
    except Exception as e:
        print(f"Warning: Could not seed payer schemes: {e}")
        db.rollback()
    finally:
        db.close()


_FACE_SHEET_PLACEHOLDER = """\
FACE SHEET — ADMISSION IDENTIFICATION

Patient: {{patient_name}}              Age / Sex: {{age}} / {{gender}}
Admission No: {{admission_number}}     Admission Date: {{admission_date}}
Ward / Room / Bed: {{ward}} / {{room}} / {{bed}}
Admitting Doctor: {{admitting_doctor}}
Referring Doctor: {{referring_doctor}}
Diagnosis on Admission: {{admission_reason}}

Responsible person (attendant):
Name: ____________________________________________
Relationship to patient: __________________________
Address: __________________________________________
Phone: ____________________________________________
ID Proof type / number: ___________________________

Declaration:
I confirm that the identification details above are correct to the best of
my knowledge and that I am the person responsible for this patient's stay
at the hospital.

Signature of patient / attendant: __________________   Date: __________
Signature of admitting officer:   __________________   Date: __________
"""

_CASE_SHEET_PLACEHOLDER = """\
CASE SHEET — DECLARATION & GENERAL CONSENT FOR TREATMENT

I, ______________________________________________ (patient / guardian),
admitted under Dr. ______________________________________ on
___________________ at this hospital, hereby acknowledge and declare:

 1. I have been informed in a language I understand about the patient's
    current condition, the proposed plan of care, the expected duration
    of admission, and the anticipated costs.

 2. I authorise the doctors, nurses, and other hospital staff to carry
    out such examinations, investigations, treatments, procedures, and
    administration of medicines/anaesthetics as they consider necessary
    during this admission.

 3. I understand that medicine is not an exact science and that no
    guarantee has been given to me regarding the outcome of treatment.
    Despite the best efforts of the treating team, complications may
    arise that are beyond anyone's control.

 4. I take responsibility for safekeeping of personal belongings,
    valuables, money, and electronic devices brought into the hospital.
    The hospital is not responsible for loss or damage to these items.

 5. I understand that the hospital follows infection-control, visiting,
    and safety protocols and I agree to abide by them.

 6. I agree to settle hospital dues as per the tariff communicated to
    me at the time of admission and as updated during the stay.

Patient signature: __________________________   Date: __________
Guardian signature (if patient is unable to sign): __________________________
Guardian relationship: __________________   ID proof: __________________
Witness signature: __________________________   Name: ________________
Counter-signed by admitting officer: __________________________
"""


def _ensure_admission_consent_templates():
    """Seed the face-sheet and case-sheet declaration templates per hospital.
    Idempotent — only creates rows when matching consent_type is missing.
    Content is placeholder; admin updates via the existing templates UI."""
    from config.database import SessionLocal
    from app.models.inpatient import ConsentTemplate
    from app.models.hospital import Hospital
    defaults = [
        ("face_sheet", "Face Sheet — Admission Identification", _FACE_SHEET_PLACEHOLDER),
        ("case_sheet_declaration", "Case Sheet — General Consent / Declaration", _CASE_SHEET_PLACEHOLDER),
    ]
    db = SessionLocal()
    try:
        hospitals = db.query(Hospital).all()
        for hospital in hospitals:
            for ctype, name, content in defaults:
                existing = db.query(ConsentTemplate).filter(
                    ConsentTemplate.hospital_id == hospital.id,
                    ConsentTemplate.consent_type == ctype,
                ).first()
                if not existing:
                    db.add(ConsentTemplate(
                        hospital_id=hospital.id,
                        consent_type=ctype,
                        template_name=name,
                        content=content,
                        language="english",
                        is_active=True,
                    ))
                elif existing.content and "[PLACEHOLDER CONTENT" in existing.content:
                    # One-shot cleanup of the bracketed placeholder banner
                    # left over from previous seeds. Preserves any edits the
                    # admin made to the rest of the template.
                    import re as _re
                    existing.content = _re.sub(
                        r"\[PLACEHOLDER CONTENT[^\]]*\]\s*\n?",
                        "",
                        existing.content,
                    )
        db.commit()
    except Exception as e:
        print(f"Warning: Could not seed admission consent templates: {e}")
        db.rollback()
    finally:
        db.close()


def _ensure_modules():
    """Ensure all required modules exist in the DB (for upgrades)."""
    from config.database import SessionLocal
    from app.models.system import SystemModule
    db = SessionLocal()
    try:
        required_modules = [
            ("outpatient", "Outpatient", True, False),
            ("inpatient", "Inpatient", False, False),
            ("lab", "Laboratory", False, False),
            ("pharmacy", "Pharmacy", False, False),
            ("ehr", "Electronic Health Records", True, False),
            ("billing", "Billing", True, True),
            ("admin", "Administration", True, True),
        ]
        for mod_name, display, default_enabled, always_on in required_modules:
            existing = db.query(SystemModule).filter(SystemModule.module_name == mod_name).first()
            if not existing:
                db.add(SystemModule(
                    module_name=mod_name, display_name=display,
                    description=f"{display} management",
                    is_enabled=default_enabled, is_always_enabled=always_on,
                ))
                print(f"  Added module: {mod_name}")
            else:
                # Sync is_always_enabled flag for existing modules (handles upgrades)
                if existing.is_always_enabled != always_on:
                    existing.is_always_enabled = always_on
                    print(f"  Updated module {mod_name}: is_always_enabled={always_on}")
        db.commit()
    except Exception as e:
        print(f"Warning: Module sync: {e}")
        db.rollback()
    finally:
        db.close()


@app.get("/")
async def root():
    # If frontend build exists, serve it
    frontend_index = os.path.join(get_frontend_dir(), "index.html")
    if os.path.isfile(frontend_index):
        return FileResponse(frontend_index)
    return {"message": "KT HEALTH ERP API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

@app.get("/profile")
async def get_user_profile(current_user: User = Depends(get_current_user)):
    return {
        "user_id": current_user.user_id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": f"{current_user.first_name} {current_user.last_name}",
        "role": current_user.role.name,
        "roles": current_user.role_names,
        "hospital_id": current_user.hospital_id,
        "is_active": current_user.is_active
    }

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(patients.router, prefix="/api/patients", tags=["Patients"])
app.include_router(admin.router, prefix="/api/admin", tags=["Administration"])
app.include_router(system.router, prefix="/api/system", tags=["System"])
app.include_router(module_admin.router, prefix="/api/modules", tags=["Module Administration"])
app.include_router(hospital_admin.router, prefix="/api/hospital", tags=["Hospital Administration"])
app.include_router(appointments.router, prefix="/api/appointments", tags=["Appointments"])
app.include_router(consultations.router, prefix="/api/consultations", tags=["Consultations"])
app.include_router(prescriptions.router, prefix="/api/prescriptions", tags=["Prescriptions"])
app.include_router(prescriptions_simple.router, prefix="/api/prescriptions-simple", tags=["Simple Prescriptions"])
app.include_router(medicines.router, prefix="/api/medicines", tags=["Medicines"])
app.include_router(doctor_availability.router, prefix="/api/doctor-availability", tags=["Doctor Availability"])
app.include_router(lab.router, prefix="/api/lab", tags=["Laboratory"])
# Additional module routers will be added as they are implemented
# app.include_router(pharmacy.router, prefix="/api/pharmacy", tags=["Pharmacy"])
# app.include_router(billing.router, prefix="/api/billing", tags=["Billing"])
app.include_router(ehr.router, prefix="/api/ehr", tags=["EHR"])
app.include_router(license.router, prefix="/api/license", tags=["License"])
app.include_router(backup.router, prefix="/api/backup", tags=["Backup"])
app.include_router(referrals.router, prefix="/api/referrals", tags=["Referrals"])
app.include_router(audit.router, prefix="/api/audit", tags=["Audit Logs"])
# app.include_router(outpatient.router, prefix="/api/outpatient", tags=["Outpatient"])
app.include_router(inpatient.router, prefix="/api/inpatient", tags=["Inpatient"])
app.include_router(outpatient_procedures.router, prefix="/api/outpatient", tags=["Outpatient Procedures"])

# Serve uploaded files
_uploads_dir = get_uploads_dir()
os.makedirs(_uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_uploads_dir), name="uploads")

# Serve React frontend build (for bundled mode or when build exists)
_frontend_dir = get_frontend_dir()
if os.path.isdir(_frontend_dir):
    # Mount static assets (JS/CSS/images)
    _static_dir = os.path.join(_frontend_dir, "static")
    if os.path.isdir(_static_dir):
        app.mount("/static", StaticFiles(directory=_static_dir), name="frontend_static")

    # SPA catch-all: serve index.html for non-API routes
    @app.get("/{full_path:path}")
    async def serve_spa(request: Request, full_path: str):
        # Don't intercept API routes or uploads
        if full_path.startswith("api/") or full_path.startswith("uploads/"):
            raise HTTPException(status_code=404)

        # Try to serve the exact file first (e.g., favicon.ico, manifest.json)
        file_path = os.path.join(_frontend_dir, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)

        # Otherwise serve index.html for SPA routing
        index_path = os.path.join(_frontend_dir, "index.html")
        if os.path.isfile(index_path):
            return FileResponse(index_path)
        raise HTTPException(status_code=404)

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["./"]
    )