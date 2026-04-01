from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func, cast, Date
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date, timedelta
import os
import uuid
import json

from config.database import get_db
from app.models.user import User
from app.models.hospital import Hospital
from app.models.permissions import HospitalSettings
from app.models.patient import Patient
from app.models.outpatient import Appointment
from app.models.ehr import Consultation
from app.models.lab import PatientLabOrder, LabTest, LabTestCategory
from app.utils.dependencies import get_current_user

from app.utils.paths import get_uploads_dir

UPLOAD_DIR = os.path.join(get_uploads_dir(), "module-config")

router = APIRouter()

# Pydantic models for API requests/responses
class HospitalInfoResponse(BaseModel):
    id: int
    hospital_id: str
    name: str
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    postal_code: Optional[str]
    country: Optional[str]
    phone: Optional[str]
    fax: Optional[str]
    email: Optional[str]
    website: Optional[str]
    license_number: Optional[str]
    registration_number: Optional[str]
    tax_id: Optional[str]
    logo_url: Optional[str]
    description: Optional[str]
    established_date: Optional[datetime]
    is_active: bool

class HospitalInfoUpdateRequest(BaseModel):
    name: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    postal_code: Optional[str]
    country: Optional[str]
    phone: Optional[str]
    fax: Optional[str]
    email: Optional[str]
    website: Optional[str]
    license_number: Optional[str]
    registration_number: Optional[str]
    tax_id: Optional[str]
    logo_url: Optional[str]
    description: Optional[str]
    established_date: Optional[datetime]

class DoctorProfileUpdateRequest(BaseModel):
    license_number: Optional[str]
    consultation_fee_inr: Optional[str]
    inpatient_fee_inr: Optional[str]
    emergency_fee_inr: Optional[str]
    specialization: Optional[str]
    qualification: Optional[str]
    experience_years: Optional[int]

class DoctorProfileResponse(BaseModel):
    id: int
    user_id: str
    username: str
    first_name: str
    last_name: str
    email: str
    phone: Optional[str]
    license_number: Optional[str]
    consultation_fee_inr: Optional[str]
    inpatient_fee_inr: Optional[str]
    emergency_fee_inr: Optional[str]
    specialization: Optional[str]
    qualification: Optional[str]
    experience_years: Optional[int]
    is_active: bool

def require_hospital_admin(current_user: User = Depends(get_current_user)):
    """Dependency to ensure only hospital admin or super admin can access these endpoints"""
    if not any(r in current_user.role_names for r in ['super_admin', 'hospital_admin']):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hospital admin access required"
        )
    return current_user

# HOSPITAL INFORMATION ENDPOINTS
@router.get("/info", response_model=HospitalInfoResponse)
async def get_hospital_info(
    current_user: User = Depends(require_hospital_admin),
    db: Session = Depends(get_db)
):
    """Get hospital information"""
    # For single hospital system, get the first hospital
    hospital = db.query(Hospital).first()
    if not hospital:
        # Create default hospital if none exists
        hospital = Hospital(
            hospital_id="HOSP-001",
            name="General Hospital",
            address="123 Main Street",
            city="New York",
            state="NY",
            country="USA",
            phone="+1-555-0123",
            email="admin@generalhospital.com",
            license_number="LIC-2024-001",
            is_active=True
        )
        db.add(hospital)
        db.commit()
        db.refresh(hospital)
    
    return hospital

class HospitalInfoPartialUpdateRequest(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    fax: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    license_number: Optional[str] = None
    registration_number: Optional[str] = None
    tax_id: Optional[str] = None
    logo_url: Optional[str] = None
    description: Optional[str] = None
    established_date: Optional[datetime] = None

@router.put("/info", response_model=HospitalInfoResponse)
async def update_hospital_info(
    hospital_data: HospitalInfoPartialUpdateRequest,
    current_user: User = Depends(require_hospital_admin),
    db: Session = Depends(get_db)
):
    """Update hospital information"""
    hospital = db.query(Hospital).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hospital not found"
        )
    
    # Update fields that are provided
    if hospital_data.name is not None:
        hospital.name = hospital_data.name
    if hospital_data.address is not None:
        hospital.address = hospital_data.address
    if hospital_data.city is not None:
        hospital.city = hospital_data.city
    if hospital_data.state is not None:
        hospital.state = hospital_data.state
    if hospital_data.postal_code is not None:
        hospital.postal_code = hospital_data.postal_code
    if hospital_data.country is not None:
        hospital.country = hospital_data.country
    if hospital_data.phone is not None:
        hospital.phone = hospital_data.phone
    if hospital_data.fax is not None:
        hospital.fax = hospital_data.fax
    if hospital_data.email is not None:
        hospital.email = hospital_data.email
    if hospital_data.website is not None:
        hospital.website = hospital_data.website
    if hospital_data.license_number is not None:
        hospital.license_number = hospital_data.license_number
    if hospital_data.registration_number is not None:
        hospital.registration_number = hospital_data.registration_number
    if hospital_data.tax_id is not None:
        hospital.tax_id = hospital_data.tax_id
    if hospital_data.logo_url is not None:
        hospital.logo_url = hospital_data.logo_url
    if hospital_data.description is not None:
        hospital.description = hospital_data.description
    if hospital_data.established_date is not None:
        hospital.established_date = hospital_data.established_date
    
    db.commit()
    db.refresh(hospital)
    return hospital

# DOCTOR MANAGEMENT ENDPOINTS
@router.get("/doctors", response_model=List[DoctorProfileResponse])
async def get_all_doctors(
    current_user: User = Depends(require_hospital_admin),
    db: Session = Depends(get_db)
):
    """Get all doctors in the hospital"""
    # Super admin can see all doctors, hospital admin sees only their hospital's doctors
    if current_user.has_role('super_admin'):
        doctors = db.query(User).join(User.role).filter(
            User.role.has(name='doctor')
        ).all()
    else:
        doctors = db.query(User).join(User.role).filter(
            User.role.has(name='doctor'),
            User.hospital_id == current_user.hospital_id
        ).all()
    
    return [
        DoctorProfileResponse(
            id=doctor.id,
            user_id=doctor.user_id,
            username=doctor.username,
            first_name=doctor.first_name,
            last_name=doctor.last_name,
            email=doctor.email,
            phone=doctor.phone,
            license_number=doctor.license_number,
            consultation_fee_inr=doctor.consultation_fee_inr,
            inpatient_fee_inr=doctor.inpatient_fee_inr,
            emergency_fee_inr=doctor.emergency_fee_inr,
            specialization=doctor.specialization,
            qualification=doctor.qualification,
            experience_years=doctor.experience_years,
            is_active=doctor.is_active
        )
        for doctor in doctors
    ]

@router.put("/doctors/{doctor_id}/profile", response_model=DoctorProfileResponse)
async def update_doctor_profile(
    doctor_id: int,
    profile_data: DoctorProfileUpdateRequest,
    current_user: User = Depends(require_hospital_admin),
    db: Session = Depends(get_db)
):
    """Update doctor profile including consultation fees"""
    doctor = db.query(User).filter(User.id == doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    # Verify it's a doctor
    if doctor.role.name != 'doctor':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a doctor"
        )
    
    # Update profile fields
    if profile_data.license_number is not None:
        doctor.license_number = profile_data.license_number
    if profile_data.consultation_fee_inr is not None:
        doctor.consultation_fee_inr = profile_data.consultation_fee_inr
    if profile_data.inpatient_fee_inr is not None:
        doctor.inpatient_fee_inr = profile_data.inpatient_fee_inr
    if profile_data.emergency_fee_inr is not None:
        doctor.emergency_fee_inr = profile_data.emergency_fee_inr
    if profile_data.specialization is not None:
        doctor.specialization = profile_data.specialization
    if profile_data.qualification is not None:
        doctor.qualification = profile_data.qualification
    if profile_data.experience_years is not None:
        doctor.experience_years = profile_data.experience_years
    
    db.commit()
    db.refresh(doctor)
    
    return DoctorProfileResponse(
        id=doctor.id,
        user_id=doctor.user_id,
        username=doctor.username,
        first_name=doctor.first_name,
        last_name=doctor.last_name,
        email=doctor.email,
        phone=doctor.phone,
        consultation_fee=doctor.consultation_fee,
        specialization=doctor.specialization,
        qualification=doctor.qualification,
        experience_years=doctor.experience_years,
        is_active=doctor.is_active
    )

# MODULE CONFIGURATION ENDPOINTS
@router.get("/module-settings/{module_name}")
async def get_module_settings(
    module_name: str,
    current_user: User = Depends(require_hospital_admin),
    db: Session = Depends(get_db)
):
    """Get configuration settings for a specific module"""
    settings = db.query(HospitalSettings).filter(
        HospitalSettings.setting_category == module_name
    ).all()
    
    return [
        {
            "id": setting.id,
            "setting_key": setting.setting_key,
            "setting_value": setting.setting_value,
            "setting_type": setting.setting_type,
            "description": setting.description
        }
        for setting in settings
    ]

class ModuleSettingRequest(BaseModel):
    setting_key: str
    setting_value: str
    setting_type: str = "string"
    description: Optional[str] = None

@router.post("/module-settings/{module_name}")
async def create_or_update_module_setting(
    module_name: str,
    setting_data: ModuleSettingRequest,
    current_user: User = Depends(require_hospital_admin),
    db: Session = Depends(get_db)
):
    """Create or update a module setting"""
    # Check if setting already exists
    existing_setting = db.query(HospitalSettings).filter(
        HospitalSettings.setting_category == module_name,
        HospitalSettings.setting_key == setting_data.setting_key
    ).first()
    
    if existing_setting:
        # Update existing
        existing_setting.setting_value = setting_data.setting_value
        existing_setting.setting_type = setting_data.setting_type
        existing_setting.description = setting_data.description
        db.commit()
        db.refresh(existing_setting)
        return {
            "id": existing_setting.id,
            "setting_key": existing_setting.setting_key,
            "setting_value": existing_setting.setting_value,
            "setting_type": existing_setting.setting_type,
            "description": existing_setting.description,
            "message": "Setting updated successfully"
        }
    else:
        # Create new
        setting = HospitalSettings(
            setting_category=module_name,
            setting_key=setting_data.setting_key,
            setting_value=setting_data.setting_value,
            setting_type=setting_data.setting_type,
            description=setting_data.description,
            created_by=current_user.id
        )
        
        db.add(setting)
        db.commit()
        db.refresh(setting)
        return {
            "id": setting.id,
            "setting_key": setting.setting_key,
            "setting_value": setting.setting_value,
            "setting_type": setting.setting_type,
            "description": setting.description,
            "message": "Setting created successfully"
        }


# FILE UPLOAD ENDPOINT
@router.post("/upload-file")
async def upload_module_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_hospital_admin),
):
    """Upload a file (logo, signature image) for module config."""
    allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, and WebP images are allowed")

    # Max 2MB
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size must be under 2MB")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "png"
    filename = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(content)

    file_url = f"/uploads/module-config/{filename}"
    return {"url": file_url, "filename": filename}


# STRUCTURED MODULE CONFIG ENDPOINTS

# Lab config fields
LAB_CONFIG_FIELDS = [
    "provider_name", "provider_address", "provider_city", "provider_state",
    "provider_pincode", "provider_phone", "provider_email", "provider_logo",
    "registration_number", "nabl_number", "license_number",
    "pathologist_name", "pathologist_qualification", "signature_image",
]

# Pharmacy config fields (same as lab + pharmacy-specific)
PHARMACY_CONFIG_FIELDS = LAB_CONFIG_FIELDS + [
    "drug_license_number", "pharmacist_name", "gst_number",
]


class ModuleConfigUpdate(BaseModel):
    config: dict  # Key-value pairs of config fields


@router.get("/module-config/{module_name}")
async def get_module_config(
    module_name: str,
    current_user: User = Depends(require_hospital_admin),
    db: Session = Depends(get_db),
):
    """Get structured config for a module (lab, pharmacy)."""
    if module_name not in ("lab", "pharmacy"):
        raise HTTPException(status_code=400, detail="Config only available for lab and pharmacy")

    settings = db.query(HospitalSettings).filter(
        HospitalSettings.setting_category == f"{module_name}_config"
    ).all()

    config = {}
    for s in settings:
        config[s.setting_key] = s.setting_value

    return {"module": module_name, "config": config}


@router.put("/module-config/{module_name}")
async def update_module_config(
    module_name: str,
    data: ModuleConfigUpdate,
    current_user: User = Depends(require_hospital_admin),
    db: Session = Depends(get_db),
):
    """Save structured config for a module (lab, pharmacy)."""
    if module_name not in ("lab", "pharmacy"):
        raise HTTPException(status_code=400, detail="Config only available for lab and pharmacy")

    allowed_fields = LAB_CONFIG_FIELDS if module_name == "lab" else PHARMACY_CONFIG_FIELDS
    category = f"{module_name}_config"

    for key, value in data.config.items():
        if key not in allowed_fields:
            continue

        existing = db.query(HospitalSettings).filter(
            HospitalSettings.setting_category == category,
            HospitalSettings.setting_key == key,
        ).first()

        if existing:
            existing.setting_value = str(value)
        else:
            db.add(HospitalSettings(
                setting_category=category,
                setting_key=key,
                setting_value=str(value),
                setting_type="string",
                created_by=current_user.id,
            ))

    db.commit()
    return {"message": f"{module_name.title()} configuration saved successfully"}


# REGISTRATION FEE ENDPOINTS
@router.get("/registration-fee")
async def get_registration_fee(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the current patient registration fee"""
    setting = db.query(HospitalSettings).filter(
        HospitalSettings.setting_category == "billing",
        HospitalSettings.setting_key == "registration_fee"
    ).first()
    return {"registration_fee": float(setting.setting_value) if setting else 0.0}


class RegistrationFeeRequest(BaseModel):
    registration_fee: float


@router.put("/registration-fee")
async def set_registration_fee(
    data: RegistrationFeeRequest,
    current_user: User = Depends(require_hospital_admin),
    db: Session = Depends(get_db)
):
    """Set the patient registration fee (hospital admin only)"""
    existing = db.query(HospitalSettings).filter(
        HospitalSettings.setting_category == "billing",
        HospitalSettings.setting_key == "registration_fee"
    ).first()

    if existing:
        existing.setting_value = str(data.registration_fee)
    else:
        db.add(HospitalSettings(
            setting_category="billing",
            setting_key="registration_fee",
            setting_value=str(data.registration_fee),
            setting_type="number",
            description="One-time registration fee for new patients",
            created_by=current_user.id,
        ))

    db.commit()
    return {"message": "Registration fee updated", "registration_fee": data.registration_fee}


@router.get("/dashboard-overview")
async def get_dashboard_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aggregated dashboard data for hospital admin."""
    import traceback
    if not any(r in current_user.role_names for r in ("super_admin", "hospital_admin")):
        raise HTTPException(status_code=403, detail="Not authorized")

    try:
        return _get_dashboard_data(current_user, db)
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


def _get_dashboard_data(current_user, db):
    hospital_id = current_user.hospital_id
    today = date.today()
    week_ago = today - timedelta(days=7)
    month_start = today.replace(day=1)

    # --- Patient Stats ---
    total_patients = db.query(sql_func.count(Patient.id)).filter(
        Patient.hospital_id == hospital_id
    ).scalar() or 0

    new_patients_today = db.query(sql_func.count(Patient.id)).filter(
        Patient.hospital_id == hospital_id,
        cast(Patient.created_at, Date) == today
    ).scalar() or 0

    new_patients_this_month = db.query(sql_func.count(Patient.id)).filter(
        Patient.hospital_id == hospital_id,
        cast(Patient.created_at, Date) >= month_start
    ).scalar() or 0

    # --- Appointment Stats ---
    today_appointments = db.query(Appointment).filter(
        Appointment.doctor.has(hospital_id=hospital_id),
        cast(Appointment.appointment_date, Date) == today
    ).all()

    total_today = len(today_appointments)
    appt_by_status = {}
    for a in today_appointments:
        appt_by_status[a.status] = appt_by_status.get(a.status, 0) + 1

    # Revenue today from appointments
    revenue_today = sum(a.final_amount or 0 for a in today_appointments if a.payment_status == 'paid')
    revenue_pending = sum(a.final_amount or 0 for a in today_appointments if a.payment_status in ('pending', 'partial'))

    # Monthly revenue
    month_appointments = db.query(Appointment).filter(
        Appointment.doctor.has(hospital_id=hospital_id),
        cast(Appointment.appointment_date, Date) >= month_start,
        Appointment.payment_status == 'paid'
    ).all()
    revenue_this_month = sum(a.final_amount or 0 for a in month_appointments)

    # Doctor performance today
    doctor_stats = {}
    for a in today_appointments:
        doc_name = f"Dr. {a.doctor.first_name} {a.doctor.last_name}" if a.doctor else "Unknown"
        if doc_name not in doctor_stats:
            doctor_stats[doc_name] = {"appointments": 0, "completed": 0, "revenue": 0, "specialization": getattr(a.doctor, 'specialization', '') or ''}
        doctor_stats[doc_name]["appointments"] += 1
        if a.status == 'completed':
            doctor_stats[doc_name]["completed"] += 1
        if a.payment_status == 'paid':
            doctor_stats[doc_name]["revenue"] += a.final_amount or 0

    # --- Lab Stats ---
    lab_orders_today = db.query(sql_func.count(PatientLabOrder.id)).filter(
        PatientLabOrder.patient.has(hospital_id=hospital_id),
        cast(PatientLabOrder.order_date, Date) == today
    ).scalar() or 0

    lab_pending = db.query(sql_func.count(PatientLabOrder.id)).filter(
        PatientLabOrder.patient.has(hospital_id=hospital_id),
        PatientLabOrder.status.in_(["ordered", "collected", "processing"])
    ).scalar() or 0

    lab_completed_today = db.query(sql_func.count(PatientLabOrder.id)).filter(
        PatientLabOrder.patient.has(hospital_id=hospital_id),
        PatientLabOrder.status == "completed",
        cast(PatientLabOrder.completion_date, Date) == today
    ).scalar() or 0

    lab_revenue_today = db.query(sql_func.coalesce(sql_func.sum(PatientLabOrder.amount), 0)).filter(
        PatientLabOrder.patient.has(hospital_id=hospital_id),
        PatientLabOrder.payment_status == "paid",
        cast(PatientLabOrder.payment_date, Date) == today
    ).scalar() or 0

    lab_revenue_month = db.query(sql_func.coalesce(sql_func.sum(PatientLabOrder.amount), 0)).filter(
        PatientLabOrder.patient.has(hospital_id=hospital_id),
        PatientLabOrder.payment_status == "paid",
        cast(PatientLabOrder.payment_date, Date) >= month_start
    ).scalar() or 0

    # --- Consultation Stats ---
    consultations_today = db.query(sql_func.count(Consultation.id)).join(
        User, Consultation.doctor_id == User.id
    ).filter(
        User.hospital_id == hospital_id,
        cast(Consultation.consultation_date, Date) == today
    ).scalar() or 0

    # --- Staff Stats ---
    total_doctors = db.query(sql_func.count(User.id)).filter(
        User.hospital_id == hospital_id, User.role.has(name="doctor"), User.is_active == True
    ).scalar() or 0

    total_staff = db.query(sql_func.count(User.id)).filter(
        User.hospital_id == hospital_id, User.is_active == True
    ).scalar() or 0

    # --- Recent appointments (last 5 completed) ---
    recent_appointments = db.query(Appointment).filter(
        Appointment.doctor.has(hospital_id=hospital_id),
        Appointment.status == "completed",
    ).order_by(Appointment.updated_at.desc()).limit(5).all()

    recent_activity = []
    for a in recent_appointments:
        recent_activity.append({
            "type": "appointment",
            "patient": f"{a.patient.first_name} {a.patient.last_name}" if a.patient else "Unknown",
            "doctor": f"Dr. {a.doctor.first_name} {a.doctor.last_name}" if a.doctor else "Unknown",
            "status": a.status,
            "time": a.updated_at.isoformat() if a.updated_at else a.created_at.isoformat(),
            "amount": a.final_amount or 0,
        })

    # --- Pending lab orders (last 5) ---
    pending_labs = db.query(PatientLabOrder).filter(
        PatientLabOrder.patient.has(hospital_id=hospital_id),
        PatientLabOrder.status.in_(["ordered", "collected", "processing"])
    ).order_by(PatientLabOrder.order_date.desc()).limit(5).all()

    pending_lab_list = []
    for lo in pending_labs:
        pending_lab_list.append({
            "order_number": lo.order_number,
            "patient": f"{lo.patient.first_name} {lo.patient.last_name}" if lo.patient else "Unknown",
            "test": lo.test.name if lo.test else "Unknown",
            "status": lo.status,
            "payment_status": lo.payment_status,
            "ordered_at": lo.order_date.isoformat() if lo.order_date else "",
        })

    # --- Weekly trend (appointments per day for last 7 days) ---
    weekly_trend = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        count = db.query(sql_func.count(Appointment.id)).filter(
            Appointment.doctor.has(hospital_id=hospital_id),
            cast(Appointment.appointment_date, Date) == d
        ).scalar() or 0
        weekly_trend.append({"date": d.isoformat(), "day": d.strftime("%a"), "count": count})

    return {
        "patients": {
            "total": total_patients,
            "new_today": new_patients_today,
            "new_this_month": new_patients_this_month,
        },
        "appointments": {
            "total_today": total_today,
            "by_status": appt_by_status,
            "consultations_today": consultations_today,
        },
        "revenue": {
            "today": revenue_today,
            "today_pending": revenue_pending,
            "this_month": revenue_this_month,
            "lab_today": float(lab_revenue_today),
            "lab_this_month": float(lab_revenue_month),
        },
        "lab": {
            "orders_today": lab_orders_today,
            "pending": lab_pending,
            "completed_today": lab_completed_today,
        },
        "staff": {
            "total_doctors": total_doctors,
            "total_staff": total_staff,
        },
        "doctor_performance": [
            {"name": name, **stats} for name, stats in doctor_stats.items()
        ],
        "recent_activity": recent_activity,
        "pending_labs": pending_lab_list,
        "weekly_trend": weekly_trend,
    }


@router.get("/billing")
async def get_all_bills(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    patient_search: Optional[str] = None,
    bill_type: Optional[str] = None,
    payment_status: Optional[str] = None,
    doctor_id: Optional[int] = None,
    referred_by: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Centralised billing view — all appointment + lab bills with filters."""
    if not any(r in current_user.role_names for r in ['super_admin', 'hospital_admin']):
        raise HTTPException(status_code=403, detail="Not authorized")

    hospital_id = current_user.hospital_id
    today = date.today()
    d_from = date_from or today.isoformat()
    d_to = date_to or today.isoformat()

    bills = []

    # --- Appointment bills ---
    apt_query = db.query(Appointment).join(Patient).filter(
        Patient.hospital_id == hospital_id,
        sql_func.date(Appointment.created_at) >= d_from,
        sql_func.date(Appointment.created_at) <= d_to,
    )
    if payment_status:
        apt_query = apt_query.filter(Appointment.payment_status == payment_status)
    if patient_search:
        q = f"%{patient_search}%"
        apt_query = apt_query.filter(
            (Patient.first_name.ilike(q)) | (Patient.last_name.ilike(q)) | (Patient.primary_phone.ilike(q))
        )
    if bill_type and bill_type not in ('appointment', 'consultation'):
        apt_query = apt_query.filter(False)  # skip
    if doctor_id:
        apt_query = apt_query.filter(Appointment.doctor_id == doctor_id)
    if referred_by:
        apt_query = apt_query.filter(Appointment.referred_by.ilike(f"%{referred_by}%"))

    for apt in apt_query.order_by(Appointment.created_at.desc()).all():
        p = apt.patient
        doctor = db.query(User).filter(User.id == apt.doctor_id).first() if apt.doctor_id else None
        bills.append({
            "id": f"APT-{apt.id}",
            "type": "consultation",
            "date": apt.created_at.isoformat() if apt.created_at else "",
            "patient_name": f"{p.first_name} {p.last_name}" if p else "Unknown",
            "patient_phone": p.primary_phone if p else "",
            "patient_id": p.patient_id if p else "",
            "_doctor_id": apt.doctor_id,
            "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "",
            "reference": apt.appointment_number,
            "items": f"Consultation{' + Registration' if apt.registration_fee else ''}",
            "subtotal": (apt.consultation_fee or 0) + (apt.registration_fee or 0),
            "discount": apt.discount_amount or 0,
            "amount": apt.final_amount or 0,
            "payment_status": apt.payment_status or "pending",
            "payment_method": apt.payment_method or "",
            "referred_by": apt.referred_by or "",
        })

    # --- Lab order bills ---
    lab_query = db.query(PatientLabOrder).join(Patient).filter(
        Patient.hospital_id == hospital_id,
        sql_func.date(PatientLabOrder.order_date) >= d_from,
        sql_func.date(PatientLabOrder.order_date) <= d_to,
    )
    if payment_status:
        lab_query = lab_query.filter(PatientLabOrder.payment_status == payment_status)
    if patient_search:
        q = f"%{patient_search}%"
        lab_query = lab_query.filter(
            (Patient.first_name.ilike(q)) | (Patient.last_name.ilike(q)) | (Patient.primary_phone.ilike(q))
        )
    if bill_type and bill_type != 'lab':
        lab_query = lab_query.filter(False)
    if doctor_id:
        lab_query = lab_query.filter(PatientLabOrder.doctor_id == doctor_id)
    if referred_by:
        lab_query = lab_query.filter(PatientLabOrder.referred_by.ilike(f"%{referred_by}%"))

    for lo in lab_query.order_by(PatientLabOrder.order_date.desc()).all():
        p = db.query(Patient).filter(Patient.id == lo.patient_id).first()
        test = db.query(LabTest).filter(LabTest.id == lo.test_id).first()
        lab_doctor = db.query(User).filter(User.id == lo.doctor_id).first() if lo.doctor_id else None
        source = "Package" if lo.package_id else "Appointment" if lo.appointment_id else "Direct"
        bills.append({
            "id": f"LAB-{lo.id}",
            "type": "lab",
            "date": lo.order_date.isoformat() if lo.order_date else "",
            "patient_name": f"{p.first_name} {p.last_name}" if p else "Unknown",
            "patient_phone": p.primary_phone if p else "",
            "patient_id": p.patient_id if p else "",
            "_doctor_id": lo.doctor_id,
            "doctor_name": f"Dr. {lab_doctor.first_name} {lab_doctor.last_name}" if lab_doctor else "",
            "reference": lo.order_number,
            "items": f"{test.name if test else 'Lab Test'} ({source})",
            "subtotal": lo.amount or 0,
            "discount": 0,
            "amount": lo.amount or 0,
            "payment_status": lo.payment_status or "pending",
            "payment_method": lo.payment_method or "",
            "referred_by": lo.referred_by or "",
        })

    # Sort all by date descending
    bills.sort(key=lambda b: b["date"], reverse=True)

    # Summary
    total_billed = sum(b["amount"] for b in bills)
    total_paid = sum(b["amount"] for b in bills if b["payment_status"] == "paid")
    total_pending = sum(b["amount"] for b in bills if b["payment_status"] != "paid")
    apt_count = sum(1 for b in bills if b["type"] == "consultation")
    lab_count = sum(1 for b in bills if b["type"] == "lab")

    # Extract unique doctors from bills for filter dropdown
    doctor_ids_seen = set()
    doctor_list = []
    for b in bills:
        if b.get("doctor_name") and b.get("_doctor_id") and b["_doctor_id"] not in doctor_ids_seen:
            doctor_ids_seen.add(b["_doctor_id"])
            doctor_list.append({"id": b["_doctor_id"], "name": b["doctor_name"]})
    # Also fetch doctors with doctor role who may not have bills yet
    from app.models.user import UserRole
    doctor_role = db.query(UserRole).filter(UserRole.name == 'doctor').first()
    if doctor_role:
        doc_users = db.query(User).filter(
            User.hospital_id == hospital_id,
            User.is_active == True,
            User.roles.any(id=doctor_role.id)
        ).all()
        for d in doc_users:
            if d.id not in doctor_ids_seen:
                doctor_ids_seen.add(d.id)
                doctor_list.append({"id": d.id, "name": f"Dr. {d.first_name} {d.last_name}"})

    # Fetch referrals for filter dropdown
    from app.models.referral import Referral
    try:
        referral_list = [{"id": r.id, "name": r.name} for r in
            db.query(Referral).filter(Referral.hospital_id == hospital_id, Referral.is_active == True).all()]
    except Exception:
        referral_list = []

    # Remove internal _doctor_id from bill output
    for b in bills:
        b.pop("_doctor_id", None)

    return {
        "bills": bills,
        "summary": {
            "total_bills": len(bills),
            "total_billed": total_billed,
            "total_paid": total_paid,
            "total_pending": total_pending,
            "appointment_count": apt_count,
            "lab_count": lab_count,
        },
        "doctors": doctor_list,
        "referrals": referral_list,
    }