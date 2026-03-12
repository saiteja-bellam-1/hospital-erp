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

# Import all models to ensure proper relationship setup
from app.models.user import User, UserRole, UserPermission
from app.models.permissions import ModulePermission, RoleModulePermission, HospitalSettings, ModuleTemplate, ModuleRates
from app.models.system import SystemModule, SystemSettings
from app.models.hospital import Hospital, HospitalModule
from app.models.prescriptions_simple import SimplePrescription
from app.models.doctor_availability import DoctorAvailability, DoctorSpecialSchedule, DoctorAvailabilityStatus
from app.models.license import License

# Import route modules
from app.routes import auth, patients, admin, system, module_admin, hospital_admin, appointments, prescriptions, medicines, consultations, prescriptions_simple, doctor_availability, lab, ehr, license, setup, backup
from app.middleware.license_middleware import LicenseMiddleware

app = FastAPI(
    title=settings.app_name,
    description="Complete Hospital ERP System",
    version="1.0.0"
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

# License middleware
app.add_middleware(LicenseMiddleware)

security = HTTPBearer()

@app.on_event("startup")
async def startup_event():
    from app.utils.config import is_setup_complete
    if is_setup_complete():
        create_tables()
        print("Database tables created successfully")
        # Ensure role permissions exist (for installations that pre-date the wizard)
        _ensure_role_permissions()
    else:
        print("Setup not complete — waiting for setup wizard")


def _ensure_role_permissions():
    """Seed/update role permissions on every startup to keep them in sync."""
    from config.database import SessionLocal
    from app.models.permissions import RoleModulePermission
    from app.models.user import UserRole
    from app.routes.setup import _seed_role_permissions
    db = SessionLocal()
    try:
        # Always upsert role permissions (creates missing, updates existing)
        _seed_role_permissions(db, UserRole, RoleModulePermission)
        db.commit()
        print("Role permissions synced")

        # Ensure outpatient module is enabled (core module)
        from app.models.system import SystemModule
        outpatient = db.query(SystemModule).filter(SystemModule.module_name == "outpatient").first()
        if outpatient and not outpatient.is_enabled:
            outpatient.is_enabled = True
            outpatient.is_always_enabled = True
            db.commit()
            print("Enabled outpatient module")
    except Exception as e:
        print(f"Warning: Could not seed role permissions: {e}")
        db.rollback()
    finally:
        db.close()

@app.get("/")
async def root():
    # If frontend build exists, serve it
    frontend_index = os.path.join(get_frontend_dir(), "index.html")
    if os.path.isfile(frontend_index):
        return FileResponse(frontend_index)
    return {"message": "Hospital ERP API is running"}

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
app.include_router(setup.router, prefix="/api/setup", tags=["Setup Wizard"])
app.include_router(backup.router, prefix="/api/backup", tags=["Backup"])
# app.include_router(outpatient.router, prefix="/api/outpatient", tags=["Outpatient"])
# app.include_router(inpatient.router, prefix="/api/inpatient", tags=["Inpatient"])

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