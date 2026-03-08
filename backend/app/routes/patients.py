from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime
import json

from config.database import get_db
from app.models.user import User
from app.models.patient import Patient
from app.services.patient_service import PatientService
from app.utils.dependencies import get_current_user, require_permission
from app.utils.auth import Modules

router = APIRouter()

class PatientCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=10)
    blood_group: Optional[str] = Field(None, max_length=5)
    primary_phone: str = Field(..., min_length=10, max_length=15)
    emergency_contact_phone: Optional[str] = Field(None, max_length=15)
    address: Optional[str] = None

class PatientResponse(BaseModel):
    id: int
    patient_id: str
    first_name: str
    last_name: str
    date_of_birth: Optional[date]
    gender: Optional[str]
    blood_group: Optional[str]
    primary_phone: str
    emergency_contact_phone: Optional[str]
    address: Optional[str]
    is_active: bool
    
    class Config:
        from_attributes = True

class PatientSearchResponse(BaseModel):
    id: int
    patient_id: str
    first_name: str
    last_name: str
    date_of_birth: Optional[date]
    age: Optional[int]
    gender: Optional[str]
    blood_group: Optional[str]
    primary_phone: str
    emergency_contact_phone: Optional[str]
    address: Optional[str]
    is_active: bool
    created_at: datetime
    last_appointment_date: Optional[datetime]
    total_appointments: int
    recent_visit_status: Optional[str]
    
    class Config:
        from_attributes = True

class PatientSearchFilters(BaseModel):
    search_term: Optional[str] = None
    min_age: Optional[int] = None
    max_age: Optional[int] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    has_recent_appointments: Optional[bool] = None
    sort_by: Optional[str] = "name"  # name, age, last_visit, created_at
    sort_order: Optional[str] = "asc"  # asc, desc

class SearchResultsMetadata(BaseModel):
    total_count: int
    page: int
    per_page: int
    total_pages: int

class PatientSearchResults(BaseModel):
    patients: List[PatientSearchResponse]
    metadata: SearchResultsMetadata

class PatientUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=10)
    blood_group: Optional[str] = Field(None, max_length=5)
    emergency_contact_phone: Optional[str] = Field(None, max_length=15)
    address: Optional[str] = None

@router.post("/", response_model=PatientResponse)
async def create_patient(
    patient_data: PatientCreate,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Create a new patient or return existing patient by phone number"""
    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="User not assigned to a hospital")
    
    patient_service = PatientService(db)
    
    # Check if patient already exists with this phone number
    existing_patient = patient_service.get_patient_by_phone(patient_data.primary_phone)
    if existing_patient:
        if existing_patient.hospital_id != current_user.hospital_id:
            raise HTTPException(status_code=400, detail="Patient belongs to different hospital")
        return existing_patient
    
    # Create new patient
    patient_dict = patient_data.dict()
    patient_dict["hospital_id"] = current_user.hospital_id
    
    patient = patient_service.create_patient(patient_dict)
    return patient

@router.get("/", response_model=List[PatientResponse])
async def get_patients(
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get list of patients with optional search"""
    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="User not assigned to a hospital")
    
    patient_service = PatientService(db)
    
    if search:
        patients = patient_service.search_patients(search, current_user.hospital_id)
    else:
        # For now, return all patients (in production, implement pagination)
        patients = patient_service.search_patients("", current_user.hospital_id)
    
    # Apply pagination
    return patients[skip:skip + limit]

@router.post("/search", response_model=PatientSearchResults)
async def search_patients_advanced(
    filters: PatientSearchFilters,
    page: int = 1,
    per_page: int = 20,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Advanced patient search with filters and metadata"""
    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="User not assigned to a hospital")
    
    patient_service = PatientService(db)
    
    filter_dict = filters.dict()
    patients_data, metadata = patient_service.advanced_search_patients(
        filter_dict, current_user.hospital_id, page, per_page
    )
    
    return PatientSearchResults(
        patients=patients_data,
        metadata=metadata
    )

@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: str,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get patient by ID"""
    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="User not assigned to a hospital")
    
    patient_service = PatientService(db)
    patient = patient_service.get_patient_by_id(patient_id)
    
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    if patient.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return patient

@router.put("/{patient_id}", response_model=PatientResponse)
async def update_patient(
    patient_id: str,
    patient_update: PatientUpdate,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Update patient information"""
    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="User not assigned to a hospital")
    
    patient_service = PatientService(db)
    patient = patient_service.get_patient_by_id(patient_id)
    
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    if patient.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    update_data = {k: v for k, v in patient_update.dict().items() if v is not None}
    updated_patient = patient_service.update_patient(patient_id, update_data)
    
    return updated_patient

@router.get("/phone/{phone}", response_model=Optional[PatientResponse])
async def get_patient_by_phone(
    phone: str,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get patient by phone number"""
    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="User not assigned to a hospital")
    
    patient_service = PatientService(db)
    patient = patient_service.get_patient_by_phone(phone)
    
    if not patient:
        return None
    
    if patient.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return patient

# Vitals Models and Endpoints
class VitalsCreate(BaseModel):
    patient_id: str = Field(..., description="Patient UUID")
    vital_signs: str = Field(..., description="JSON string containing vital signs data")
    notes: Optional[str] = Field(None, max_length=1000)
    recorded_by_role: Optional[str] = Field(None, description="Role of person recording vitals")

class VitalsResponse(BaseModel):
    id: int
    patient_id: str
    vital_signs: dict
    notes: Optional[str]
    recorded_by: str
    recorded_by_role: Optional[str]
    recorded_at: datetime
    
    class Config:
        from_attributes = True

@router.post("/vitals", response_model=VitalsResponse)
async def record_patient_vitals(
    vitals_data: VitalsCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Record patient vital signs - accessible by nurses, doctors, and receptionists"""
    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="User not assigned to a hospital")
    
    # Check if user role is allowed to record vitals
    allowed_roles = ['nurse', 'doctor', 'receptionist', 'super_admin', 'hospital_admin']
    if current_user.role.name not in allowed_roles:
        raise HTTPException(status_code=403, detail="Not authorized to record vitals")
    
    # Verify patient exists and belongs to same hospital
    patient_service = PatientService(db)
    patient = patient_service.get_patient_by_id(vitals_data.patient_id)
    
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    if patient.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Parse vital signs JSON
    try:
        vital_signs_dict = json.loads(vitals_data.vital_signs)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid vital signs JSON format")
    
    # For now, we'll store this as a medical note in consultations or create a simple vitals log
    # Since we don't have a dedicated vitals table, let's create a consultation record
    from app.models.ehr import Consultation
    import uuid
    
    consultation = Consultation(
        consultation_number=f"VIT-{uuid.uuid4().hex[:8].upper()}",
        patient_id=patient.id,
        doctor_id=current_user.id,
        consultation_type="vitals_recording",
        chief_complaint="Vital signs recording",
        vital_signs=vitals_data.vital_signs,
        status="completed",
        notes=vitals_data.notes or "Vital signs recorded"
    )
    
    db.add(consultation)
    db.commit()
    db.refresh(consultation)
    
    # Return formatted response
    return VitalsResponse(
        id=consultation.id,
        patient_id=vitals_data.patient_id,
        vital_signs=vital_signs_dict,
        notes=vitals_data.notes,
        recorded_by=f"{current_user.first_name} {current_user.last_name}",
        recorded_by_role=vitals_data.recorded_by_role or current_user.role.name,
        recorded_at=consultation.created_at
    )

@router.get("/{patient_id}/vitals", response_model=List[VitalsResponse])
async def get_patient_vitals(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get patient's vital signs history"""
    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="User not assigned to a hospital")
    
    # Check if user role is allowed to view vitals
    allowed_roles = ['nurse', 'doctor', 'receptionist', 'super_admin', 'hospital_admin']
    if current_user.role.name not in allowed_roles:
        raise HTTPException(status_code=403, detail="Not authorized to view vitals")
    
    # Verify patient exists and belongs to same hospital
    patient_service = PatientService(db)
    patient = patient_service.get_patient_by_id(patient_id)
    
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    if patient.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get vitals from consultations
    from app.models.ehr import Consultation
    vitals_consultations = db.query(Consultation).filter(
        Consultation.patient_id == patient.id,
        Consultation.consultation_type == "vitals_recording"
    ).order_by(Consultation.created_at.desc()).all()
    
    vitals_list = []
    for consultation in vitals_consultations:
        try:
            vital_signs_dict = json.loads(consultation.vital_signs) if consultation.vital_signs else {}
        except:
            vital_signs_dict = {}
        
        # Get recorder info
        recorder = db.query(User).filter(User.id == consultation.doctor_id).first()
        recorder_name = f"{recorder.first_name} {recorder.last_name}" if recorder else "Unknown"
        
        vitals_list.append(VitalsResponse(
            id=consultation.id,
            patient_id=patient_id,
            vital_signs=vital_signs_dict,
            notes=consultation.notes,
            recorded_by=recorder_name,
            recorded_by_role=recorder.role.name if recorder else "unknown",
            recorded_at=consultation.created_at
        ))
    
    return vitals_list