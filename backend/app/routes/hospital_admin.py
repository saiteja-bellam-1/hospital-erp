from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import os
import uuid
import json

from config.database import get_db
from app.models.user import User
from app.models.hospital import Hospital
from app.models.permissions import HospitalSettings
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
    if current_user.role.name not in ['super_admin', 'hospital_admin']:
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
    if current_user.role.name == 'super_admin':
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