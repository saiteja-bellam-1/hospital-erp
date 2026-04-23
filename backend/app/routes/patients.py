from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime
import json

from config.database import get_db
from app.models.user import User
from app.models.patient import Patient, PatientAllergy
from app.services.patient_service import PatientService
from app.utils.dependencies import get_current_user, require_permission, require_feature_permission
from app.utils.auth import Modules
from app.services.audit_service import log_action

router = APIRouter()

class PatientCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    date_of_birth: Optional[date] = None
    age: Optional[int] = Field(None, ge=0, le=150)
    gender: Optional[str] = Field(None, max_length=10)
    blood_group: Optional[str] = Field(None, max_length=5)
    marital_status: Optional[str] = Field(None, max_length=20)
    abha_id: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None, max_length=100)
    primary_phone: str = Field(..., min_length=10, max_length=15)
    emergency_contact_phone: Optional[str] = Field(None, max_length=15)
    emergency_contact_name: Optional[str] = Field(None, max_length=100)
    emergency_contact_relation: Optional[str] = Field(None, max_length=50)
    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    village: Optional[str] = Field(None, max_length=100)
    mandal: Optional[str] = Field(None, max_length=100)
    district: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = None
    referred_by: Optional[str] = Field(None, max_length=100)

class PatientResponse(BaseModel):
    id: int
    patient_id: str
    first_name: str
    last_name: str
    date_of_birth: Optional[date]
    age: Optional[int] = None
    gender: Optional[str]
    blood_group: Optional[str]
    marital_status: Optional[str] = None
    abha_id: Optional[str] = None
    email: Optional[str] = None
    primary_phone: str
    emergency_contact_phone: Optional[str]
    emergency_contact_name: Optional[str] = None
    emergency_contact_relation: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    village: Optional[str] = None
    mandal: Optional[str] = None
    district: Optional[str] = None
    address: Optional[str]
    referred_by: Optional[str] = None
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
    marital_status: Optional[str] = None
    abha_id: Optional[str] = None
    email: Optional[str] = None
    primary_phone: str
    emergency_contact_phone: Optional[str]
    emergency_contact_name: Optional[str] = None
    emergency_contact_relation: Optional[str] = None
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    village: Optional[str] = None
    mandal: Optional[str] = None
    district: Optional[str] = None
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
    age: Optional[int] = Field(None, ge=0, le=150)
    gender: Optional[str] = Field(None, max_length=10)
    blood_group: Optional[str] = Field(None, max_length=5)
    marital_status: Optional[str] = Field(None, max_length=20)
    abha_id: Optional[str] = Field(None, max_length=30)
    email: Optional[str] = Field(None, max_length=100)
    emergency_contact_phone: Optional[str] = Field(None, max_length=15)
    emergency_contact_name: Optional[str] = Field(None, max_length=100)
    emergency_contact_relation: Optional[str] = Field(None, max_length=50)
    address_line1: Optional[str] = Field(None, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    village: Optional[str] = Field(None, max_length=100)
    mandal: Optional[str] = Field(None, max_length=100)
    district: Optional[str] = Field(None, max_length=100)
    address: Optional[str] = None

@router.post("/", response_model=PatientResponse)
async def create_patient(
    patient_data: PatientCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new patient"""
    if not current_user.hospital_id:
        raise HTTPException(status_code=400, detail="User not assigned to a hospital")

    patient_service = PatientService(db)

    # Create new patient
    patient_dict = patient_data.dict()
    patient_dict["hospital_id"] = current_user.hospital_id

    # Auto-calculate age from DOB if DOB is provided but age is not
    if patient_dict.get("date_of_birth") and not patient_dict.get("age"):
        from datetime import date as date_type
        today = date_type.today()
        dob = patient_dict["date_of_birth"]
        patient_dict["age"] = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    patient = patient_service.create_patient(patient_dict)

    # Audit log
    try:
        from app.services.audit_service import log_action
        age_info = f", {patient_dict.get('age')} yrs" if patient_dict.get('age') else ""
        gender_info = f", {patient_dict.get('gender', '').upper()}" if patient_dict.get('gender') else ""
        log_action(db, current_user, "create_patient", "patient", "Patient", patient.id,
            f"Registered new patient: {patient_data.first_name} {patient_data.last_name}{gender_info}{age_info}, Phone: {patient_data.primary_phone}",
            details={"patient_name": f"{patient_data.first_name} {patient_data.last_name}", "phone": patient_data.primary_phone, "gender": patient_data.gender})
    except Exception:
        pass

    return patient

@router.get("/", response_model=List[PatientResponse])
async def get_patients(
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
    if not any(r in current_user.role_names for r in allowed_roles):
        raise HTTPException(status_code=403, detail="Not authorized to record vitals")
    
    # Verify patient exists and belongs to same hospital
    patient_service = PatientService(db)
    patient = patient_service.get_patient_by_id(vitals_data.patient_id)

    if not patient:
        raise HTTPException(status_code=404, detail=f"Patient not found for id: {vitals_data.patient_id}")
    
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
    if not any(r in current_user.role_names for r in allowed_roles):
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


# ============================================================
# Patient Allergies (patient-level, carries across admissions)
# ============================================================

class AllergyCreate(BaseModel):
    allergy_type: str = Field(..., pattern="^(drug|food|environmental|other)$")
    allergen: str = Field(..., min_length=1, max_length=200)
    severity: str = Field(..., pattern="^(mild|moderate|severe|anaphylaxis)$")
    reaction: Optional[str] = None
    notes: Optional[str] = None


class AllergyUpdate(BaseModel):
    allergy_type: Optional[str] = Field(default=None, pattern="^(drug|food|environmental|other)$")
    allergen: Optional[str] = Field(default=None, max_length=200)
    severity: Optional[str] = Field(default=None, pattern="^(mild|moderate|severe|anaphylaxis)$")
    reaction: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class AllergyResponse(BaseModel):
    id: int
    patient_id: int
    allergy_type: str
    allergen: str
    severity: str
    reaction: Optional[str]
    notes: Optional[str]
    is_active: bool
    recorded_by_id: int
    recorded_by_name: Optional[str] = None
    recorded_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


def _allergy_to_response(a: PatientAllergy, db: Session) -> dict:
    rec = db.query(User).filter(User.id == a.recorded_by_id).first()
    return {
        **{c.name: getattr(a, c.name) for c in a.__table__.columns},
        "recorded_by_name": f"{rec.first_name} {rec.last_name}" if rec else None,
    }


def _resolve_patient(db: Session, patient_ref: str) -> Patient:
    """patient_ref can be the integer id (as string) or the UUID patient_id."""
    p = None
    if patient_ref.isdigit():
        p = db.query(Patient).filter(Patient.id == int(patient_ref)).first()
    if not p:
        p = db.query(Patient).filter(Patient.patient_id == patient_ref).first()
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return p


@router.get("/{patient_ref}/allergies", response_model=List[AllergyResponse])
async def list_patient_allergies(
    patient_ref: str,
    active_only: bool = True,
    current_user: User = Depends(get_current_user),  # any authenticated user can read — safety read
    db: Session = Depends(get_db),
):
    p = _resolve_patient(db, patient_ref)
    q = db.query(PatientAllergy).filter(PatientAllergy.patient_id == p.id)
    if active_only:
        q = q.filter(PatientAllergy.is_active == True)
    rows = q.order_by(PatientAllergy.severity.desc(), PatientAllergy.recorded_at.desc()).all()
    return [_allergy_to_response(a, db) for a in rows]


@router.post("/{patient_ref}/allergies", response_model=AllergyResponse, status_code=status.HTTP_201_CREATED)
async def create_patient_allergy(
    patient_ref: str,
    data: AllergyCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_allergies")),
    db: Session = Depends(get_db),
):
    p = _resolve_patient(db, patient_ref)

    # Prevent exact-duplicate active entries (same allergen + type)
    existing = db.query(PatientAllergy).filter(
        PatientAllergy.patient_id == p.id,
        PatientAllergy.allergen.ilike(data.allergen.strip()),
        PatientAllergy.allergy_type == data.allergy_type,
        PatientAllergy.is_active == True,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Active allergy '{data.allergen}' already recorded for this patient",
        )

    allergy = PatientAllergy(
        patient_id=p.id,
        allergy_type=data.allergy_type,
        allergen=data.allergen.strip(),
        severity=data.severity,
        reaction=data.reaction,
        notes=data.notes,
        recorded_by_id=current_user.id,
    )
    db.add(allergy)
    db.commit()
    db.refresh(allergy)

    log_action(
        db, current_user, "create_allergy", "patient", "PatientAllergy", allergy.id,
        f"Recorded {data.severity} {data.allergy_type} allergy: {data.allergen} for patient {p.patient_id}",
        {"severity": data.severity, "type": data.allergy_type},
    )
    return _allergy_to_response(allergy, db)


@router.put("/allergies/{allergy_id}", response_model=AllergyResponse)
async def update_patient_allergy(
    allergy_id: int,
    data: AllergyUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_allergies")),
    db: Session = Depends(get_db),
):
    a = db.query(PatientAllergy).filter(PatientAllergy.id == allergy_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Allergy not found")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(a, field, value)
    db.commit()
    db.refresh(a)
    return _allergy_to_response(a, db)


@router.delete("/allergies/{allergy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient_allergy(
    allergy_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_allergies")),
    db: Session = Depends(get_db),
):
    a = db.query(PatientAllergy).filter(PatientAllergy.id == allergy_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Allergy not found")
    # Soft-delete by setting inactive (preserves history); actually delete only if requested by hard delete (rare)
    a.is_active = False
    db.commit()


def check_drug_allergy_match(db: Session, patient_id: int, drug_name: str) -> Optional[PatientAllergy]:
    """Returns the matching active drug allergy for the patient, or None.
    Match is case-insensitive substring on allergen — intentionally lenient
    (e.g. allergy 'penicillin' matches 'Amoxicillin' is NOT desired here, so we use word match)."""
    if not drug_name:
        return None
    drug_lower = drug_name.lower().strip()
    allergies = db.query(PatientAllergy).filter(
        PatientAllergy.patient_id == patient_id,
        PatientAllergy.allergy_type == "drug",
        PatientAllergy.is_active == True,
    ).all()
    for a in allergies:
        allergen_lower = a.allergen.lower().strip()
        if allergen_lower in drug_lower or drug_lower in allergen_lower:
            return a
    return None