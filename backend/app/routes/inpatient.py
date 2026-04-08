from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sqlfunc, and_, cast, Date
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, date
import io
import os
import uuid

from config.database import get_db
from app.models.user import User
from app.models.patient import Patient
from app.models.hospital import Hospital
from app.models.billing import Bill, BillItem
from app.models.inpatient import (
    RoomManagement, Admission, DischargeRecord,
    PatientVisit, InpatientRateConfig, OTSchedule, Bed, AdmissionDocument, NursingNote, DietOrder
)
from app.models.pharmacy import Prescription, PrescriptionItem, Medicine
from app.models.prescriptions_simple import SimplePrescription
from app.models.lab import PatientLabOrder, LabTest, LabReport
from app.utils.dependencies import get_current_user, require_permission
from app.utils.auth import Modules
from app.utils.pdf_service import pdf_service
from app.services.audit_service import log_action

router = APIRouter()

# ============================================================
# Pydantic Models
# ============================================================

# --- Room ---
class RoomCreate(BaseModel):
    room_number: str = Field(..., max_length=20)
    room_type: str = Field(..., pattern="^(general|private|icu|emergency|operation)$")
    floor: Optional[str] = None
    department: Optional[str] = None
    bed_count: int = Field(default=1, ge=1)
    room_charge_per_day: float = Field(..., ge=0)
    amenities: Optional[str] = None

class RoomUpdate(BaseModel):
    room_number: Optional[str] = None
    room_type: Optional[str] = None
    floor: Optional[str] = None
    department: Optional[str] = None
    bed_count: Optional[int] = Field(default=None, ge=1)
    room_charge_per_day: Optional[float] = Field(default=None, ge=0)
    amenities: Optional[str] = None

class RoomResponse(BaseModel):
    id: int
    room_number: str
    room_type: str
    floor: Optional[str]
    department: Optional[str]
    bed_count: int
    available_beds: int
    room_charge_per_day: float
    amenities: Optional[str]
    is_active: bool
    is_occupied: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    class Config:
        from_attributes = True

# --- Rate Config ---
class RateConfigUpdate(BaseModel):
    doctor_visit_rate: Optional[float] = Field(default=None, ge=0)
    nurse_visit_rate: Optional[float] = Field(default=None, ge=0)
    procedure_rate: Optional[float] = Field(default=None, ge=0)

class RateConfigResponse(BaseModel):
    id: int
    doctor_visit_rate: float
    nurse_visit_rate: float
    procedure_rate: float
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    class Config:
        from_attributes = True

# --- Admission ---
class AdmissionCreate(BaseModel):
    patient_id: int
    admitting_doctor_id: int
    room_id: int
    admission_type: str = Field(..., pattern="^(emergency|elective|transfer)$")
    admission_reason: Optional[str] = None
    condition_on_admission: Optional[str] = Field(default=None, pattern="^(stable|critical|serious)$")
    estimated_stay_days: Optional[int] = Field(default=None, ge=1)
    admission_notes: Optional[str] = None
    insurance_details: Optional[str] = None
    insurance_provider: Optional[str] = None
    policy_number: Optional[str] = None
    claim_reference: Optional[str] = None
    emergency_contact: Optional[str] = None
    attending_physician_id: Optional[int] = None
    bed_number: Optional[str] = None
    bed_id: Optional[int] = None

class AdmissionUpdate(BaseModel):
    room_id: Optional[int] = None
    admission_reason: Optional[str] = None
    condition_on_admission: Optional[str] = None
    estimated_stay_days: Optional[int] = None
    admission_notes: Optional[str] = None
    insurance_details: Optional[str] = None
    insurance_provider: Optional[str] = None
    policy_number: Optional[str] = None
    claim_reference: Optional[str] = None
    emergency_contact: Optional[str] = None
    attending_physician_id: Optional[int] = None
    bed_number: Optional[str] = None

class ClaimStatusUpdate(BaseModel):
    claim_status: str = Field(..., pattern="^(none|draft|submitted|approved|rejected)$")
    claim_amount: Optional[float] = Field(default=None, ge=0)
    claim_notes: Optional[str] = None
    insurance_provider: Optional[str] = None
    policy_number: Optional[str] = None
    claim_reference: Optional[str] = None

class AdmissionResponse(BaseModel):
    id: int
    admission_number: str
    patient_id: int
    admitting_doctor_id: int
    room_id: int
    admission_date: Optional[datetime]
    admission_type: str
    admission_reason: Optional[str]
    condition_on_admission: Optional[str]
    estimated_stay_days: Optional[int]
    status: str
    admission_notes: Optional[str]
    insurance_details: Optional[str]
    insurance_provider: Optional[str]
    policy_number: Optional[str]
    claim_reference: Optional[str]
    claim_status: Optional[str] = "none"
    claim_amount: Optional[float] = None
    claim_submitted_at: Optional[datetime] = None
    claim_notes: Optional[str] = None
    emergency_contact: Optional[str]
    attending_physician_id: Optional[int]
    bed_number: Optional[str]
    bed_id: Optional[int] = None
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    # Joined fields
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    room_number: Optional[str] = None
    room_type: Optional[str] = None
    bed_label: Optional[str] = None
    discharge_date: Optional[datetime] = None
    stay_days: Optional[int] = None
    class Config:
        from_attributes = True

class PaginatedAdmissionResponse(BaseModel):
    items: List[AdmissionResponse]
    total: int
    skip: int
    limit: int

# --- Visit ---
class VisitCreate(BaseModel):
    visit_type: str = Field(..., pattern="^(doctor_visit|nurse_visit|procedure)$")
    visitor_id: int
    notes: Optional[str] = None
    charge_amount: Optional[float] = None  # auto-populated from rate config if not provided

class VisitUpdate(BaseModel):
    notes: Optional[str] = None
    charge_amount: Optional[float] = Field(default=None, ge=0)

class VisitResponse(BaseModel):
    id: int
    admission_id: int
    patient_id: int
    visitor_id: int
    visit_type: str
    visit_datetime: Optional[datetime]
    notes: Optional[str]
    charge_amount: float
    billed: bool
    created_at: Optional[datetime]
    visitor_name: Optional[str] = None
    class Config:
        from_attributes = True

# --- Discharge ---
class DischargeCreate(BaseModel):
    discharge_type: str = Field(..., pattern="^(normal|against_advice|transfer|death)$")
    condition_on_discharge: Optional[str] = Field(default=None, pattern="^(stable|improved|unchanged|critical)$")
    discharge_summary: Optional[str] = None
    diagnosis_on_discharge: Optional[str] = None
    treatment_given: Optional[str] = None
    medications_prescribed: Optional[str] = None
    follow_up_instructions: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    diet_instructions: Optional[str] = None
    activity_restrictions: Optional[str] = None

class DischargeResponse(BaseModel):
    id: int
    admission_id: int
    discharge_date: Optional[datetime]
    discharge_type: str
    condition_on_discharge: Optional[str]
    discharge_summary: Optional[str]
    diagnosis_on_discharge: Optional[str]
    treatment_given: Optional[str]
    medications_prescribed: Optional[str]
    follow_up_instructions: Optional[str]
    follow_up_date: Optional[datetime]
    diet_instructions: Optional[str]
    activity_restrictions: Optional[str]
    total_stay_days: Optional[int]
    total_charges: Optional[float]
    created_at: Optional[datetime]
    class Config:
        from_attributes = True

# --- OT Schedule ---
class OTScheduleCreate(BaseModel):
    admission_id: Optional[int] = None
    patient_id: int
    surgeon_id: int
    anaesthetist_id: Optional[int] = None
    ot_room_number: str = Field(..., max_length=20)
    procedure_name: str = Field(..., max_length=200)
    scheduled_date: datetime
    estimated_duration_minutes: Optional[int] = Field(default=None, ge=1)
    pre_op_notes: Optional[str] = None

class OTScheduleUpdate(BaseModel):
    surgeon_id: Optional[int] = None
    anaesthetist_id: Optional[int] = None
    ot_room_number: Optional[str] = None
    procedure_name: Optional[str] = None
    scheduled_date: Optional[datetime] = None
    estimated_duration_minutes: Optional[int] = None
    pre_op_notes: Optional[str] = None
    post_op_notes: Optional[str] = None

class OTScheduleResponse(BaseModel):
    id: int
    admission_id: Optional[int]
    patient_id: int
    surgeon_id: int
    anaesthetist_id: Optional[int]
    ot_room_number: str
    procedure_name: str
    scheduled_date: datetime
    estimated_duration_minutes: Optional[int]
    status: str
    pre_op_notes: Optional[str]
    post_op_notes: Optional[str]
    created_at: Optional[datetime]
    # Joined fields
    patient_name: Optional[str] = None
    surgeon_name: Optional[str] = None
    class Config:
        from_attributes = True

# --- Bed ---
class BedCreate(BaseModel):
    bed_label: str = Field(..., max_length=20)

class BedUpdate(BaseModel):
    bed_label: Optional[str] = Field(default=None, max_length=20)
    status: Optional[str] = Field(default=None, pattern="^(available|occupied|maintenance)$")

class BedResponse(BaseModel):
    id: int
    room_id: int
    bed_label: str
    status: str
    current_admission_id: Optional[int] = None
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    class Config:
        from_attributes = True

# --- Admission Document ---
class DocumentResponse(BaseModel):
    id: int
    admission_id: int
    document_type: str
    document_name: str
    file_name: str
    file_size: Optional[int]
    mime_type: Optional[str]
    uploaded_by_name: Optional[str] = None
    notes: Optional[str]
    created_at: Optional[datetime]
    class Config:
        from_attributes = True


# --- Nursing Notes ---
class FinalizeBillRequest(BaseModel):
    discount_type: Optional[str] = Field(default=None, pattern="^(flat|percentage)$")
    discount_value: Optional[float] = Field(default=0, ge=0)
    tax_percentage: Optional[float] = Field(default=0, ge=0, le=100)

class NursingNoteCreate(BaseModel):
    shift: str = Field(..., pattern="^(morning|afternoon|night)$")
    note_type: str = Field(..., pattern="^(observation|medication|vitals|procedure|handover|general)$")
    content: str = Field(..., min_length=1)

class NursingNoteUpdate(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1)
    shift: Optional[str] = Field(default=None, pattern="^(morning|afternoon|night)$")
    note_type: Optional[str] = Field(default=None, pattern="^(observation|medication|vitals|procedure|handover|general)$")

class NursingNoteResponse(BaseModel):
    id: int
    admission_id: int
    patient_id: int
    nurse_id: int
    shift: str
    note_type: str
    content: str
    nurse_name: Optional[str] = None
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    class Config:
        from_attributes = True


# --- Diet Orders ---
class DietOrderCreate(BaseModel):
    diet_type: str = Field(..., pattern="^(regular|diabetic|liquid|soft|npo|low_salt|renal|cardiac)$")
    meal_instructions: Optional[str] = None
    allergies: Optional[str] = None
    notes: Optional[str] = None

class DietOrderUpdate(BaseModel):
    diet_type: Optional[str] = Field(default=None, pattern="^(regular|diabetic|liquid|soft|npo|low_salt|renal|cardiac)$")
    meal_instructions: Optional[str] = None
    allergies: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None

class DietOrderResponse(BaseModel):
    id: int
    admission_id: int
    patient_id: int
    diet_type: str
    meal_instructions: Optional[str]
    allergies: Optional[str]
    notes: Optional[str]
    is_active: bool
    ordered_by_name: Optional[str] = None
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    class Config:
        from_attributes = True


# ============================================================
# Helper: get hospital for current user
# ============================================================
def _get_hospital(db: Session, user: User):
    hospital = db.query(Hospital).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not configured")
    return hospital


def _admission_to_response(adm) -> dict:
    """Convert an Admission ORM object to a response dict with joined names.
    Expects relationships (patient, admitting_doctor, room, discharge) to be eager-loaded."""
    patient = adm.patient
    doctor = adm.admitting_doctor
    room = adm.room
    discharge_date = None
    stay_days = None
    if adm.discharge:
        discharge_date = adm.discharge.discharge_date
        if adm.admission_date and discharge_date:
            stay_days = (discharge_date - adm.admission_date).days
    elif adm.admission_date:
        stay_days = (datetime.now() - adm.admission_date).days
    return {
        **{c.name: getattr(adm, c.name) for c in adm.__table__.columns},
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
        "doctor_name": f"{doctor.first_name} {doctor.last_name}" if doctor else None,
        "room_number": room.room_number if room else None,
        "room_type": room.room_type if room else None,
        "bed_label": adm.bed.bed_label if adm.bed else None,
        "discharge_date": discharge_date,
        "stay_days": stay_days,
    }


# ============================================================
# Room Management
# ============================================================

@router.get("/rooms", response_model=List[RoomResponse])
async def list_rooms(
    room_type: Optional[str] = None,
    floor: Optional[str] = None,
    available_only: bool = False,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    query = db.query(RoomManagement).filter(RoomManagement.is_active == True)
    if room_type:
        query = query.filter(RoomManagement.room_type == room_type)
    if floor:
        query = query.filter(RoomManagement.floor == floor)
    if available_only:
        query = query.filter(RoomManagement.available_beds > 0)
    return query.order_by(RoomManagement.room_number).all()


@router.post("/rooms", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    room: RoomCreate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "admin")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    existing = db.query(RoomManagement).filter(
        RoomManagement.room_number == room.room_number,
        RoomManagement.is_active == True,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Room number already exists")

    db_room = RoomManagement(
        **room.model_dump(),
        available_beds=room.bed_count,
        hospital_id=hospital.id,
    )
    db.add(db_room)
    db.commit()
    db.refresh(db_room)
    log_action(db, current_user, "create_room", "inpatient", "Room", db_room.id,
               f"Created room {db_room.room_number} ({db_room.room_type})")
    return db_room


@router.put("/rooms/{room_id}", response_model=RoomResponse)
async def update_room(
    room_id: int,
    room: RoomUpdate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "admin")),
    db: Session = Depends(get_db),
):
    db_room = db.query(RoomManagement).filter(RoomManagement.id == room_id).first()
    if not db_room:
        raise HTTPException(status_code=404, detail="Room not found")

    update_data = room.model_dump(exclude_unset=True)

    # If bed_count changes, adjust available_beds proportionally
    if "bed_count" in update_data:
        occupied = db_room.bed_count - db_room.available_beds
        new_available = update_data["bed_count"] - occupied
        if new_available < 0:
            raise HTTPException(status_code=400, detail="Cannot reduce beds below currently occupied count")
        update_data["available_beds"] = new_available

    for key, value in update_data.items():
        setattr(db_room, key, value)
    db.commit()
    db.refresh(db_room)
    return db_room


@router.delete("/rooms/{room_id}")
async def delete_room(
    room_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "admin")),
    db: Session = Depends(get_db),
):
    db_room = db.query(RoomManagement).filter(RoomManagement.id == room_id).first()
    if not db_room:
        raise HTTPException(status_code=404, detail="Room not found")
    # Soft delete
    db_room.is_active = False
    db.commit()
    return {"message": "Room deactivated successfully"}


@router.get("/rooms/availability")
async def room_availability(
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    rooms = db.query(RoomManagement).filter(RoomManagement.is_active == True).all()
    summary = {}
    for room in rooms:
        rt = room.room_type
        if rt not in summary:
            summary[rt] = {"total_beds": 0, "occupied": 0, "available": 0}
        summary[rt]["total_beds"] += room.bed_count
        occupied = room.bed_count - room.available_beds
        summary[rt]["occupied"] += occupied
        summary[rt]["available"] += room.available_beds

    total_beds = sum(v["total_beds"] for v in summary.values())
    total_occupied = sum(v["occupied"] for v in summary.values())
    total_available = sum(v["available"] for v in summary.values())

    return {
        "by_type": summary,
        "total_beds": total_beds,
        "total_occupied": total_occupied,
        "total_available": total_available,
    }


# ============================================================
# Rate Config
# ============================================================

@router.get("/rate-config", response_model=RateConfigResponse)
async def get_rate_config(
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    config = db.query(InpatientRateConfig).filter(
        InpatientRateConfig.hospital_id == hospital.id
    ).first()
    if not config:
        config = InpatientRateConfig(
            hospital_id=hospital.id,
            doctor_visit_rate=0, nurse_visit_rate=0, procedure_rate=0,
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


@router.put("/rate-config", response_model=RateConfigResponse)
async def update_rate_config(
    data: RateConfigUpdate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "admin")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    config = db.query(InpatientRateConfig).filter(
        InpatientRateConfig.hospital_id == hospital.id
    ).first()
    if not config:
        config = InpatientRateConfig(hospital_id=hospital.id)
        db.add(config)
        db.commit()
        db.refresh(config)

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(config, key, value)
    db.commit()
    db.refresh(config)
    log_action(db, current_user, "update_rate_config", "inpatient", "RateConfig", config.id,
               "Updated inpatient rate configuration")
    return config


# ============================================================
# Bed Management
# ============================================================

@router.get("/rooms/{room_id}/beds", response_model=List[BedResponse])
async def list_beds(
    room_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    room = db.query(RoomManagement).filter(RoomManagement.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    beds = db.query(Bed).filter(Bed.room_id == room_id).order_by(Bed.bed_label).all()
    return beds


@router.post("/rooms/{room_id}/beds", response_model=BedResponse, status_code=status.HTTP_201_CREATED)
async def create_bed(
    room_id: int,
    data: BedCreate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    room = db.query(RoomManagement).filter(RoomManagement.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    # Check duplicate label in same room
    existing = db.query(Bed).filter(Bed.room_id == room_id, Bed.bed_label == data.bed_label).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Bed '{data.bed_label}' already exists in this room")
    bed = Bed(room_id=room_id, bed_label=data.bed_label, status="available")
    db.add(bed)
    # Update room bed counts
    room.bed_count = db.query(Bed).filter(Bed.room_id == room_id).count() + 1
    room.available_beds = db.query(Bed).filter(Bed.room_id == room_id, Bed.status == "available").count() + 1
    db.commit()
    db.refresh(bed)
    return bed


@router.patch("/beds/{bed_id}", response_model=BedResponse)
async def update_bed(
    bed_id: int,
    data: BedUpdate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    bed = db.query(Bed).filter(Bed.id == bed_id).first()
    if not bed:
        raise HTTPException(status_code=404, detail="Bed not found")
    if data.bed_label is not None:
        dup = db.query(Bed).filter(Bed.room_id == bed.room_id, Bed.bed_label == data.bed_label, Bed.id != bed_id).first()
        if dup:
            raise HTTPException(status_code=400, detail=f"Bed '{data.bed_label}' already exists in this room")
        bed.bed_label = data.bed_label
    if data.status is not None:
        if bed.current_admission_id and data.status != "occupied":
            raise HTTPException(status_code=400, detail="Cannot change status of occupied bed with active admission")
        bed.status = data.status
    db.commit()
    # Sync room counts
    room = db.query(RoomManagement).filter(RoomManagement.id == bed.room_id).first()
    if room:
        room.bed_count = db.query(Bed).filter(Bed.room_id == room.id).count()
        room.available_beds = db.query(Bed).filter(Bed.room_id == room.id, Bed.status == "available").count()
        db.commit()
    db.refresh(bed)
    return bed


@router.delete("/beds/{bed_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bed(
    bed_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "delete")),
    db: Session = Depends(get_db),
):
    bed = db.query(Bed).filter(Bed.id == bed_id).first()
    if not bed:
        raise HTTPException(status_code=404, detail="Bed not found")
    if bed.current_admission_id:
        raise HTTPException(status_code=400, detail="Cannot delete bed with active admission")
    room_id = bed.room_id
    db.delete(bed)
    db.commit()
    # Sync room counts
    room = db.query(RoomManagement).filter(RoomManagement.id == room_id).first()
    if room:
        room.bed_count = db.query(Bed).filter(Bed.room_id == room_id).count()
        room.available_beds = db.query(Bed).filter(Bed.room_id == room_id, Bed.status == "available").count()
        db.commit()


# ============================================================
# Admissions
# ============================================================

def _generate_admission_number(db: Session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"ADM-{today}-"
    last = db.query(Admission).filter(
        Admission.admission_number.like(f"{prefix}%")
    ).order_by(Admission.id.desc()).first()
    if last:
        seq = int(last.admission_number.split("-")[-1]) + 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


@router.post("/admissions", response_model=AdmissionResponse, status_code=status.HTTP_201_CREATED)
async def create_admission(
    data: AdmissionCreate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    # Validate patient
    patient = db.query(Patient).filter(Patient.id == data.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Validate doctor
    doctor = db.query(User).filter(User.id == data.admitting_doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Validate room & bed availability
    room = db.query(RoomManagement).filter(
        RoomManagement.id == data.room_id,
        RoomManagement.is_active == True,
    ).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.available_beds <= 0:
        raise HTTPException(status_code=400, detail="No beds available in this room")

    # Check for active admission for the same patient
    active = db.query(Admission).filter(
        Admission.patient_id == data.patient_id,
        Admission.status == "admitted",
    ).first()
    if active:
        raise HTTPException(status_code=400, detail="Patient already has an active admission")

    # Validate and assign structured bed if provided
    bed_obj = None
    if data.bed_id:
        bed_obj = db.query(Bed).filter(Bed.id == data.bed_id, Bed.room_id == data.room_id).first()
        if not bed_obj:
            raise HTTPException(status_code=404, detail="Bed not found in selected room")
        if bed_obj.status != "available":
            raise HTTPException(status_code=400, detail=f"Bed '{bed_obj.bed_label}' is not available")

    admission_number = _generate_admission_number(db)
    admission = Admission(
        **data.model_dump(),
        admission_number=admission_number,
    )
    db.add(admission)
    db.flush()  # get admission.id

    # Mark structured bed as occupied
    if bed_obj:
        bed_obj.status = "occupied"
        bed_obj.current_admission_id = admission.id
        admission.bed_number = bed_obj.bed_label  # sync legacy field

    # Sync room bed counts from Bed table if beds exist, otherwise use legacy decrement
    room_beds = db.query(Bed).filter(Bed.room_id == room.id).count()
    if room_beds > 0:
        room.available_beds = db.query(Bed).filter(Bed.room_id == room.id, Bed.status == "available").count()
        room.bed_count = room_beds
    else:
        room.available_beds -= 1
    if room.available_beds == 0:
        room.is_occupied = True

    db.commit()
    db.refresh(admission)

    log_action(db, current_user, "create_admission", "inpatient", "Admission", admission.id,
               f"Admitted patient {patient.first_name} {patient.last_name} ({admission_number})",
               details={"patient_id": data.patient_id, "room": room.room_number})

    # Re-fetch with eager-loaded relationships for response
    admission = db.query(Admission).options(
        joinedload(Admission.patient),
        joinedload(Admission.admitting_doctor),
        joinedload(Admission.room),
        joinedload(Admission.discharge),
        joinedload(Admission.bed),
    ).filter(Admission.id == admission.id).first()
    return _admission_to_response(admission)


@router.get("/admissions", response_model=PaginatedAdmissionResponse)
async def list_admissions(
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    base_query = db.query(Admission)
    if status_filter:
        base_query = base_query.filter(Admission.status == status_filter)
    else:
        base_query = base_query.filter(Admission.status == "admitted")
    total = base_query.count()
    admissions = base_query.options(
        joinedload(Admission.patient),
        joinedload(Admission.admitting_doctor),
        joinedload(Admission.room),
        joinedload(Admission.discharge),
    ).order_by(Admission.admission_date.desc()).offset(skip).limit(limit).all()
    return PaginatedAdmissionResponse(
        items=[_admission_to_response(a) for a in admissions],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/admissions/{admission_id}", response_model=AdmissionResponse)
async def get_admission(
    admission_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).options(
        joinedload(Admission.patient),
        joinedload(Admission.admitting_doctor),
        joinedload(Admission.room),
        joinedload(Admission.discharge),
        joinedload(Admission.bed),
    ).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    return _admission_to_response(admission)


@router.put("/admissions/{admission_id}", response_model=AdmissionResponse)
async def update_admission(
    admission_id: int,
    data: AdmissionUpdate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status != "admitted":
        raise HTTPException(status_code=400, detail="Cannot update a discharged/transferred admission")

    update_data = data.model_dump(exclude_unset=True)

    # Handle room transfer
    if "room_id" in update_data and update_data["room_id"] != admission.room_id:
        new_room = db.query(RoomManagement).filter(
            RoomManagement.id == update_data["room_id"],
            RoomManagement.is_active == True,
        ).first()
        if not new_room:
            raise HTTPException(status_code=404, detail="New room not found")
        if new_room.available_beds <= 0:
            raise HTTPException(status_code=400, detail="No beds available in new room")

        # Release old room bed
        old_room = db.query(RoomManagement).filter(RoomManagement.id == admission.room_id).first()
        if old_room:
            old_room.available_beds += 1
            old_room.is_occupied = old_room.available_beds == 0

        # Occupy new room bed
        new_room.available_beds -= 1
        if new_room.available_beds == 0:
            new_room.is_occupied = True

    for key, value in update_data.items():
        setattr(admission, key, value)
    db.commit()

    # Re-fetch with eager-loaded relationships for response
    admission = db.query(Admission).options(
        joinedload(Admission.patient),
        joinedload(Admission.admitting_doctor),
        joinedload(Admission.room),
        joinedload(Admission.discharge),
        joinedload(Admission.bed),
    ).filter(Admission.id == admission_id).first()
    return _admission_to_response(admission)


@router.get("/admissions/patient/{patient_id}", response_model=List[AdmissionResponse])
async def get_patient_admissions(
    patient_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    admissions = db.query(Admission).options(
        joinedload(Admission.patient),
        joinedload(Admission.admitting_doctor),
        joinedload(Admission.room),
        joinedload(Admission.discharge),
        joinedload(Admission.bed),
    ).filter(
        Admission.patient_id == patient_id
    ).order_by(Admission.admission_date.desc()).all()
    return [_admission_to_response(a) for a in admissions]


# ============================================================
# Insurance Claim Workflow
# ============================================================

VALID_CLAIM_TRANSITIONS = {
    "none": ["draft"],
    "draft": ["submitted", "none"],
    "submitted": ["approved", "rejected", "draft"],
    "approved": [],
    "rejected": ["draft"],
}

@router.put("/admissions/{admission_id}/claim-status", response_model=AdmissionResponse)
async def update_claim_status(
    admission_id: int,
    data: ClaimStatusUpdate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    """Update insurance claim status with workflow validation: none → draft → submitted → approved/rejected."""
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    current_status = admission.claim_status or "none"
    new_status = data.claim_status

    if new_status != current_status:
        allowed = VALID_CLAIM_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition claim from '{current_status}' to '{new_status}'. Allowed: {allowed}"
            )

    # Update fields
    admission.claim_status = new_status
    if data.claim_amount is not None:
        admission.claim_amount = data.claim_amount
    if data.claim_notes is not None:
        admission.claim_notes = data.claim_notes
    if data.insurance_provider is not None:
        admission.insurance_provider = data.insurance_provider
    if data.policy_number is not None:
        admission.policy_number = data.policy_number
    if data.claim_reference is not None:
        admission.claim_reference = data.claim_reference

    # Record submission timestamp
    if new_status == "submitted" and current_status != "submitted":
        admission.claim_submitted_at = datetime.now()

    db.commit()

    await log_action(
        db, current_user.id,
        f"insurance_claim_{new_status}",
        "admission", admission_id,
        {"admission_number": admission.admission_number, "claim_status": new_status,
         "claim_amount": data.claim_amount, "previous_status": current_status}
    )

    admission = db.query(Admission).options(
        joinedload(Admission.patient),
        joinedload(Admission.admitting_doctor),
        joinedload(Admission.room),
        joinedload(Admission.discharge),
        joinedload(Admission.bed),
    ).filter(Admission.id == admission_id).first()
    return _admission_to_response(admission)


# ============================================================
# Visits
# ============================================================

@router.post("/admissions/{admission_id}/visits", response_model=VisitResponse, status_code=status.HTTP_201_CREATED)
async def create_visit(
    admission_id: int,
    data: VisitCreate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status != "admitted":
        raise HTTPException(status_code=400, detail="Cannot add visits to a non-active admission")

    hospital = _get_hospital(db, current_user)

    # Auto-populate charge_amount from rate config if not provided
    charge = data.charge_amount
    if charge is None:
        config = db.query(InpatientRateConfig).filter(
            InpatientRateConfig.hospital_id == hospital.id
        ).first()
        rate_map = {
            "doctor_visit": float(config.doctor_visit_rate) if config else 0,
            "nurse_visit": float(config.nurse_visit_rate) if config else 0,
            "procedure": float(config.procedure_rate) if config else 0,
        }
        charge = rate_map.get(data.visit_type, 0)

    visitor = db.query(User).filter(User.id == data.visitor_id).first()

    visit = PatientVisit(
        admission_id=admission_id,
        patient_id=admission.patient_id,
        visitor_id=data.visitor_id,
        visit_type=data.visit_type,
        notes=data.notes,
        charge_amount=charge,
        created_by_id=current_user.id,
        hospital_id=hospital.id,
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)

    result = {c.name: getattr(visit, c.name) for c in visit.__table__.columns}
    result["visitor_name"] = f"{visitor.first_name} {visitor.last_name}" if visitor else None
    return result


@router.get("/admissions/{admission_id}/visits", response_model=List[VisitResponse])
async def list_visits(
    admission_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    visits = db.query(PatientVisit).options(
        joinedload(PatientVisit.visitor),
    ).filter(
        PatientVisit.admission_id == admission_id
    ).order_by(PatientVisit.visit_datetime.desc()).all()

    results = []
    for v in visits:
        row = {c.name: getattr(v, c.name) for c in v.__table__.columns}
        row["visitor_name"] = f"{v.visitor.first_name} {v.visitor.last_name}" if v.visitor else None
        results.append(row)
    return results


@router.put("/visits/{visit_id}", response_model=VisitResponse)
async def update_visit(
    visit_id: int,
    data: VisitUpdate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    visit = db.query(PatientVisit).filter(PatientVisit.id == visit_id).first()
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    if visit.billed:
        raise HTTPException(status_code=400, detail="Cannot modify a billed visit")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(visit, key, value)
    db.commit()
    db.refresh(visit)

    visitor = db.query(User).filter(User.id == visit.visitor_id).first()
    result = {c.name: getattr(visit, c.name) for c in visit.__table__.columns}
    result["visitor_name"] = f"{visitor.first_name} {visitor.last_name}" if visitor else None
    return result


@router.delete("/visits/{visit_id}")
async def delete_visit(
    visit_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    visit = db.query(PatientVisit).filter(PatientVisit.id == visit_id).first()
    if not visit:
        raise HTTPException(status_code=404, detail="Visit not found")
    if visit.billed:
        raise HTTPException(status_code=400, detail="Cannot delete a billed visit")
    db.delete(visit)
    db.commit()
    return {"message": "Visit deleted successfully"}


# ============================================================
# Discharge
# ============================================================

@router.post("/admissions/{admission_id}/discharge", response_model=DischargeResponse, status_code=status.HTTP_201_CREATED)
async def discharge_patient(
    admission_id: int,
    data: DischargeCreate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status != "admitted":
        raise HTTPException(status_code=400, detail="Patient is not currently admitted")

    # Calculate stay days
    stay_days = (datetime.now() - admission.admission_date).days
    if stay_days == 0:
        stay_days = 1

    # Calculate total charges (room + visits)
    room = db.query(RoomManagement).filter(RoomManagement.id == admission.room_id).first()
    room_charges = (room.room_charge_per_day * stay_days) if room else 0

    visits = db.query(PatientVisit).filter(PatientVisit.admission_id == admission_id).all()
    visit_charges = sum(float(v.charge_amount or 0) for v in visits)

    # Pharmacy charges from dispensed prescriptions
    pharmacy_prescriptions = db.query(Prescription).filter(
        Prescription.admission_id == admission_id,
        Prescription.status.in_(["dispensed", "partial"])
    ).all()
    pharmacy_charges = sum(float(rx.total_amount or 0) for rx in pharmacy_prescriptions)

    total_charges = room_charges + visit_charges + pharmacy_charges

    discharge = DischargeRecord(
        admission_id=admission_id,
        discharge_type=data.discharge_type,
        condition_on_discharge=data.condition_on_discharge,
        discharge_summary=data.discharge_summary,
        diagnosis_on_discharge=data.diagnosis_on_discharge,
        treatment_given=data.treatment_given,
        medications_prescribed=data.medications_prescribed,
        follow_up_instructions=data.follow_up_instructions,
        follow_up_date=data.follow_up_date,
        diet_instructions=data.diet_instructions,
        activity_restrictions=data.activity_restrictions,
        discharge_approved_by_id=current_user.id,
        total_stay_days=stay_days,
        total_charges=total_charges,
    )
    db.add(discharge)

    # Update admission status
    admission.status = "discharged"

    # Release structured bed if assigned
    if admission.bed_id:
        bed_obj = db.query(Bed).filter(Bed.id == admission.bed_id).first()
        if bed_obj:
            bed_obj.status = "available"
            bed_obj.current_admission_id = None

    # Sync room bed counts
    if room:
        room_beds = db.query(Bed).filter(Bed.room_id == room.id).count()
        if room_beds > 0:
            room.available_beds = db.query(Bed).filter(Bed.room_id == room.id, Bed.status == "available").count()
            room.bed_count = room_beds
        else:
            room.available_beds += 1
        room.is_occupied = room.available_beds == 0

    db.commit()
    db.refresh(discharge)

    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first()
    log_action(db, current_user, "discharge_patient", "inpatient", "Discharge", discharge.id,
               f"Discharged patient {patient.first_name} {patient.last_name} ({admission.admission_number})",
               details={"admission_id": admission_id, "stay_days": stay_days, "total_charges": total_charges})

    return discharge


@router.get("/admissions/{admission_id}/discharge", response_model=DischargeResponse)
async def get_discharge(
    admission_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    discharge = db.query(DischargeRecord).filter(
        DischargeRecord.admission_id == admission_id
    ).first()
    if not discharge:
        raise HTTPException(status_code=404, detail="Discharge record not found")
    return discharge


@router.get("/admissions/{admission_id}/discharge/pdf")
async def get_discharge_pdf(
    admission_id: int,
    include_header: bool = True,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    discharge = db.query(DischargeRecord).filter(
        DischargeRecord.admission_id == admission_id
    ).first()
    if not discharge:
        raise HTTPException(status_code=404, detail="Discharge record not found")

    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first()
    doctor = db.query(User).filter(User.id == admission.admitting_doctor_id).first()
    hospital = _get_hospital(db, current_user)

    hospital_info = {
        "name": hospital.name,
        "address": hospital.address or "",
        "phone": hospital.phone or "",
        "email": hospital.email or "",
        "logo_url": hospital.logo_url if hasattr(hospital, "logo_url") else "",
        "hospital_subname": hospital.hospital_subname if hasattr(hospital, "hospital_subname") else "",
    }

    discharge_data = {
        "admission_number": admission.admission_number,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "N/A",
        "patient_id": patient.patient_id if patient else "N/A",
        "age": patient.age if patient and hasattr(patient, "age") else "",
        "gender": patient.gender if patient else "",
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "N/A",
        "admission_date": admission.admission_date.strftime("%d/%m/%Y") if admission.admission_date else "",
        "discharge_date": discharge.discharge_date.strftime("%d/%m/%Y") if discharge.discharge_date else "",
        "discharge_type": discharge.discharge_type,
        "condition_on_admission": admission.condition_on_admission or "",
        "condition_on_discharge": discharge.condition_on_discharge or "",
        "diagnosis": discharge.diagnosis_on_discharge or "",
        "treatment": discharge.treatment_given or "",
        "discharge_summary": discharge.discharge_summary or "",
        "medications": discharge.medications_prescribed or "",
        "follow_up": discharge.follow_up_instructions or "",
        "follow_up_date": discharge.follow_up_date.strftime("%d/%m/%Y") if discharge.follow_up_date else "",
        "diet_instructions": discharge.diet_instructions or "",
        "activity_restrictions": discharge.activity_restrictions or "",
        "total_stay_days": discharge.total_stay_days or 0,
        "total_charges": discharge.total_charges or 0,
    }

    pdf_buffer = pdf_service.generate_discharge_summary_pdf(discharge_data, hospital_info, include_header=include_header)

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=discharge_{admission.admission_number}.pdf"}
    )


# ============================================================
# Admission Prescriptions (Pharmacy Integration)
# ============================================================

@router.get("/admissions/{admission_id}/prescriptions")
async def get_admission_prescriptions(
    admission_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    """Get all prescriptions linked to an admission (both full and simple)"""
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    results = []

    # Full prescriptions (pharmacy-linked)
    full_prescriptions = db.query(Prescription).filter(
        Prescription.admission_id == admission_id
    ).order_by(Prescription.prescription_date.desc()).all()

    for rx in full_prescriptions:
        doctor = db.query(User).filter(User.id == rx.doctor_id).first()
        items = db.query(PrescriptionItem).filter(
            PrescriptionItem.prescription_id == rx.id
        ).all()
        med_list = []
        for item in items:
            medicine = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
            med_list.append({
                "name": medicine.name if medicine else "Unknown",
                "dosage": item.dosage,
                "duration": item.duration,
                "quantity": item.quantity_prescribed,
                "quantity_dispensed": item.quantity_dispensed,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
                "status": item.status,
            })
        results.append({
            "id": rx.id,
            "type": "pharmacy",
            "prescription_number": rx.prescription_number,
            "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "N/A",
            "date": rx.prescription_date.isoformat() if rx.prescription_date else None,
            "status": rx.status,
            "total_amount": rx.total_amount or 0,
            "notes": rx.notes,
            "medicines": med_list,
        })

    # Simple prescriptions
    simple_prescriptions = db.query(SimplePrescription).filter(
        SimplePrescription.admission_id == admission_id
    ).order_by(SimplePrescription.prescription_date.desc()).all()

    for rx in simple_prescriptions:
        doctor = db.query(User).filter(User.id == rx.doctor_id).first()
        results.append({
            "id": rx.id,
            "type": "simple",
            "prescription_number": rx.prescription_id,
            "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "N/A",
            "date": rx.prescription_date.isoformat() if rx.prescription_date else None,
            "status": rx.status,
            "total_amount": 0,
            "notes": rx.notes,
            "medicines": rx.medicines or [],
        })

    return results


# ============================================================
# Billing
# ============================================================

@router.get("/admissions/{admission_id}/bill")
async def get_admission_bill(
    admission_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    room = db.query(RoomManagement).filter(RoomManagement.id == admission.room_id).first()
    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first()

    # Calculate stay days
    end_date = datetime.now()
    if admission.status == "discharged" and admission.discharge:
        end_date = admission.discharge.discharge_date or end_date
    stay_days = (end_date - admission.admission_date).days
    if stay_days == 0:
        stay_days = 1

    # Room charges
    room_charge_per_day = room.room_charge_per_day if room else 0
    room_total = room_charge_per_day * stay_days

    # Visit charges grouped by type
    visits = db.query(PatientVisit).options(
        joinedload(PatientVisit.visitor),
    ).filter(PatientVisit.admission_id == admission_id).all()
    visit_summary = {}
    for v in visits:
        vtype = v.visit_type
        if vtype not in visit_summary:
            visit_summary[vtype] = {"count": 0, "total": 0, "items": []}
        visit_summary[vtype]["count"] += 1
        visit_summary[vtype]["total"] += float(v.charge_amount or 0)
        visitor = v.visitor
        visit_summary[vtype]["items"].append({
            "id": v.id,
            "date": v.visit_datetime.isoformat() if v.visit_datetime else None,
            "visitor": f"{visitor.first_name} {visitor.last_name}" if visitor else "N/A",
            "amount": float(v.charge_amount or 0),
            "billed": v.billed,
            "notes": v.notes,
        })

    visit_total = sum(s["total"] for s in visit_summary.values())

    # Pharmacy/prescription charges
    pharmacy_prescriptions = db.query(Prescription).filter(
        Prescription.admission_id == admission_id,
        Prescription.status.in_(["dispensed", "partial"])
    ).all()
    pharmacy_total = sum(float(rx.total_amount or 0) for rx in pharmacy_prescriptions)

    # Lab charges
    lab_orders = db.query(PatientLabOrder).filter(
        PatientLabOrder.admission_id == admission_id,
        PatientLabOrder.status != "cancelled"
    ).all()
    lab_total = sum(float(o.amount or 0) for o in lab_orders)

    grand_total = room_total + visit_total + pharmacy_total + lab_total

    return {
        "admission_id": admission_id,
        "admission_number": admission.admission_number,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "N/A",
        "patient_id": patient.patient_id if patient else None,
        "admission_date": admission.admission_date.isoformat() if admission.admission_date else None,
        "status": admission.status,
        "stay_days": stay_days,
        "room": {
            "room_number": room.room_number if room else "N/A",
            "room_type": room.room_type if room else "N/A",
            "charge_per_day": room_charge_per_day,
            "total": room_total,
        },
        "visits": visit_summary,
        "visit_total": visit_total,
        "room_total": room_total,
        "pharmacy_total": pharmacy_total,
        "lab_total": lab_total,
        "grand_total": grand_total,
    }


@router.post("/admissions/{admission_id}/bill/finalize")
async def finalize_bill(
    admission_id: int,
    data: Optional[FinalizeBillRequest] = None,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first()
    hospital = _get_hospital(db, current_user)
    room = db.query(RoomManagement).filter(RoomManagement.id == admission.room_id).first()

    # Calculate stay
    end_date = datetime.now()
    if admission.status == "discharged" and admission.discharge:
        end_date = admission.discharge.discharge_date or end_date
    stay_days = max((end_date - admission.admission_date).days, 1)

    room_charge_per_day = room.room_charge_per_day if room else 0
    room_total = room_charge_per_day * stay_days

    # Get unbilled visits
    visits = db.query(PatientVisit).options(
        joinedload(PatientVisit.visitor),
    ).filter(
        PatientVisit.admission_id == admission_id,
        PatientVisit.billed == False,
    ).all()
    visit_total = sum(float(v.charge_amount or 0) for v in visits)

    # Pharmacy charges from dispensed prescriptions
    pharmacy_rxs = db.query(Prescription).filter(
        Prescription.admission_id == admission_id,
        Prescription.status.in_(["dispensed", "partial"])
    ).all()
    pharmacy_total = sum(float(rx.total_amount or 0) for rx in pharmacy_rxs)

    # Lab charges
    lab_orders = db.query(PatientLabOrder).filter(
        PatientLabOrder.admission_id == admission_id,
        PatientLabOrder.status != "cancelled"
    ).all()
    lab_total = sum(float(o.amount or 0) for o in lab_orders)

    subtotal = room_total + visit_total + pharmacy_total + lab_total

    # Calculate discount
    discount_amount = 0.0
    if data and data.discount_value and data.discount_value > 0:
        if data.discount_type == "percentage":
            discount_amount = round(subtotal * data.discount_value / 100, 2)
        else:
            discount_amount = min(data.discount_value, subtotal)

    # Calculate tax
    tax_amount = 0.0
    after_discount = subtotal - discount_amount
    if data and data.tax_percentage and data.tax_percentage > 0:
        tax_amount = round(after_discount * data.tax_percentage / 100, 2)

    grand_total = round(after_discount + tax_amount, 2)

    # Generate bill number
    today = datetime.now().strftime("%Y%m%d")
    bill_prefix = f"BILL-ADM-{today}-"
    last_bill = db.query(Bill).filter(
        Bill.bill_number.like(f"{bill_prefix}%")
    ).order_by(Bill.id.desc()).first()
    seq = (int(last_bill.bill_number.split("-")[-1]) + 1) if last_bill else 1
    bill_number = f"{bill_prefix}{seq:04d}"

    bill = Bill(
        bill_number=bill_number,
        patient_id=admission.patient_id,
        bill_type="admission",
        reference_id=admission.id,
        subtotal=subtotal,
        tax_amount=tax_amount,
        discount_amount=discount_amount,
        total_amount=grand_total,
        status="pending",
        created_by_id=current_user.id,
        hospital_id=hospital.id,
    )
    db.add(bill)
    db.flush()

    # Add bill items
    if room_total > 0:
        room_item = BillItem(
            bill_id=bill.id,
            item_type="room_charge",
            item_name=f"Room {room.room_number} ({room.room_type}) - {stay_days} days",
            quantity=stay_days,
            unit_price=room_charge_per_day,
            total_price=room_total,
        )
        db.add(room_item)

    for v in visits:
        visitor = v.visitor
        visit_item = BillItem(
            bill_id=bill.id,
            item_type=v.visit_type,
            item_name=f"{v.visit_type.replace('_', ' ').title()} - {visitor.first_name} {visitor.last_name}" if visitor else v.visit_type,
            quantity=1,
            unit_price=float(v.charge_amount or 0),
            total_price=float(v.charge_amount or 0),
        )
        db.add(visit_item)
        v.billed = True

    # Add pharmacy bill items
    for rx in pharmacy_rxs:
        rx_items = db.query(PrescriptionItem).filter(PrescriptionItem.prescription_id == rx.id).all()
        for item in rx_items:
            medicine = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
            med_item = BillItem(
                bill_id=bill.id,
                item_type="pharmacy",
                item_name=f"Rx: {medicine.name if medicine else 'Medicine'} ({item.dosage or ''})",
                quantity=item.quantity_dispensed or item.quantity_prescribed,
                unit_price=item.unit_price,
                total_price=item.total_price,
            )
            db.add(med_item)

    # Add lab bill items
    for lo in lab_orders:
        test = db.query(LabTest).filter(LabTest.id == lo.test_id).first()
        lab_item = BillItem(
            bill_id=bill.id,
            item_type="lab_test",
            item_name=f"Lab: {test.name if test else 'Test'} ({lo.order_number})",
            quantity=1,
            unit_price=float(lo.amount or 0),
            total_price=float(lo.amount or 0),
        )
        db.add(lab_item)

    db.commit()
    db.refresh(bill)

    log_action(db, current_user, "finalize_admission_bill", "inpatient", "Bill", bill.id,
               f"Finalized admission bill {bill_number} for {patient.first_name} {patient.last_name}",
               details={"admission_id": admission_id, "total": grand_total})

    return {
        "bill_id": bill.id,
        "bill_number": bill_number,
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "tax_amount": tax_amount,
        "total_amount": grand_total,
        "status": "pending",
        "message": "Bill finalized successfully",
    }


@router.get("/admissions/{admission_id}/bill/pdf")
async def get_bill_pdf(
    admission_id: int,
    include_header: bool = True,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    # Find the bill for this admission
    bill = db.query(Bill).filter(
        Bill.bill_type == "admission",
        Bill.reference_id == admission.id,
    ).order_by(Bill.id.desc()).first()

    if not bill:
        raise HTTPException(status_code=404, detail="No bill found for this admission. Finalize the bill first.")

    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first()
    hospital = _get_hospital(db, current_user)
    bill_items = db.query(BillItem).filter(BillItem.bill_id == bill.id).all()

    hospital_info = {
        "name": hospital.name,
        "address": hospital.address or "",
        "phone": hospital.phone or "",
        "email": hospital.email or "",
        "logo_url": hospital.logo_url if hasattr(hospital, "logo_url") else "",
        "hospital_subname": hospital.hospital_subname if hasattr(hospital, "hospital_subname") else "",
    }

    bill_data = {
        "bill_number": bill.bill_number,
        "bill_date": bill.bill_date.isoformat() if bill.bill_date else datetime.now().isoformat(),
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "N/A",
        "patient_id": patient.patient_id if patient else "N/A",
        "items": [
            {
                "description": item.item_name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total": item.total_price,
            }
            for item in bill_items
        ],
        "subtotal": bill.subtotal,
        "tax": bill.tax_amount,
        "discount": bill.discount_amount,
        "total": bill.total_amount,
        "status": bill.status,
    }

    pdf_buffer = pdf_service.generate_bill_pdf(bill_data, hospital_info, include_header=include_header)

    return StreamingResponse(
        io.BytesIO(pdf_buffer.getvalue()) if hasattr(pdf_buffer, "getvalue") else pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=bill_{bill.bill_number}.pdf"}
    )


# ============================================================
# Dashboard
# ============================================================

@router.get("/dashboard")
async def inpatient_dashboard(
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    # Bed summary
    rooms = db.query(RoomManagement).filter(RoomManagement.is_active == True).all()
    total_beds = sum(r.bed_count for r in rooms)
    total_available = sum(r.available_beds for r in rooms)
    total_occupied = total_beds - total_available

    by_type = {}
    for r in rooms:
        rt = r.room_type
        if rt not in by_type:
            by_type[rt] = {"total": 0, "occupied": 0, "available": 0}
        by_type[rt]["total"] += r.bed_count
        occupied = r.bed_count - r.available_beds
        by_type[rt]["occupied"] += occupied
        by_type[rt]["available"] += r.available_beds

    # Today's admissions
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_admissions = db.query(Admission).filter(
        Admission.admission_date >= today_start,
    ).count()

    # Pending discharges (admitted patients with estimated_stay_days exceeded)
    active_admissions = db.query(Admission).filter(Admission.status == "admitted").all()
    pending_discharges = 0
    for a in active_admissions:
        if a.estimated_stay_days:
            elapsed = (datetime.now() - a.admission_date).days
            if elapsed >= a.estimated_stay_days:
                pending_discharges += 1

    # Average stay days (from discharged patients)
    discharged = db.query(DischargeRecord).all()
    avg_stay = 0
    if discharged:
        total_stay = sum(d.total_stay_days or 0 for d in discharged)
        avg_stay = round(total_stay / len(discharged), 1)

    return {
        "total_beds": total_beds,
        "occupied": total_occupied,
        "available": total_available,
        "by_type": by_type,
        "today_admissions": today_admissions,
        "active_admissions": len(active_admissions),
        "pending_discharges": pending_discharges,
        "avg_stay_days": avg_stay,
    }


# ============================================================
# OT Schedule
# ============================================================

@router.post("/ot", response_model=OTScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_ot_schedule(
    data: OTScheduleCreate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)

    patient = db.query(Patient).filter(Patient.id == data.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    surgeon = db.query(User).filter(User.id == data.surgeon_id).first()
    if not surgeon:
        raise HTTPException(status_code=404, detail="Surgeon not found")

    ot = OTSchedule(
        **data.model_dump(),
        created_by_id=current_user.id,
        hospital_id=hospital.id,
    )
    db.add(ot)
    db.commit()
    db.refresh(ot)

    log_action(db, current_user, "create_ot_schedule", "inpatient", "OTSchedule", ot.id,
               f"Scheduled OT: {data.procedure_name} for {patient.first_name} {patient.last_name}")

    result = {c.name: getattr(ot, c.name) for c in ot.__table__.columns}
    result["patient_name"] = f"{patient.first_name} {patient.last_name}"
    result["surgeon_name"] = f"{surgeon.first_name} {surgeon.last_name}"
    return result


@router.get("/ot", response_model=List[OTScheduleResponse])
async def list_ot_schedules(
    schedule_date: Optional[date] = None,
    surgeon_id: Optional[int] = None,
    ot_status: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    query = db.query(OTSchedule).options(
        joinedload(OTSchedule.patient),
        joinedload(OTSchedule.surgeon),
    )
    if schedule_date:
        query = query.filter(cast(OTSchedule.scheduled_date, Date) == schedule_date)
    if surgeon_id:
        query = query.filter(OTSchedule.surgeon_id == surgeon_id)
    if ot_status:
        query = query.filter(OTSchedule.status == ot_status)

    schedules = query.order_by(OTSchedule.scheduled_date).all()
    results = []
    for ot in schedules:
        row = {c.name: getattr(ot, c.name) for c in ot.__table__.columns}
        row["patient_name"] = f"{ot.patient.first_name} {ot.patient.last_name}" if ot.patient else None
        row["surgeon_name"] = f"{ot.surgeon.first_name} {ot.surgeon.last_name}" if ot.surgeon else None
        results.append(row)
    return results


@router.put("/ot/{ot_id}", response_model=OTScheduleResponse)
async def update_ot_schedule(
    ot_id: int,
    data: OTScheduleUpdate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    ot = db.query(OTSchedule).filter(OTSchedule.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="OT schedule not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(ot, key, value)
    db.commit()

    # Re-fetch with eager-loaded relationships
    ot = db.query(OTSchedule).options(
        joinedload(OTSchedule.patient),
        joinedload(OTSchedule.surgeon),
    ).filter(OTSchedule.id == ot_id).first()
    result = {c.name: getattr(ot, c.name) for c in ot.__table__.columns}
    result["patient_name"] = f"{ot.patient.first_name} {ot.patient.last_name}" if ot.patient else None
    result["surgeon_name"] = f"{ot.surgeon.first_name} {ot.surgeon.last_name}" if ot.surgeon else None
    return result


@router.patch("/ot/{ot_id}/status")
async def update_ot_status(
    ot_id: int,
    new_status: str = Query(..., alias="status", pattern="^(scheduled|in_progress|completed|cancelled|postponed)$"),
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    ot = db.query(OTSchedule).filter(OTSchedule.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="OT schedule not found")
    ot.status = new_status
    db.commit()
    return {"message": f"OT schedule status updated to {new_status}"}


@router.get("/ot/today", response_model=List[OTScheduleResponse])
async def today_ot_schedules(
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    today = date.today()
    schedules = db.query(OTSchedule).options(
        joinedload(OTSchedule.patient),
        joinedload(OTSchedule.surgeon),
    ).filter(
        cast(OTSchedule.scheduled_date, Date) == today
    ).order_by(OTSchedule.scheduled_date).all()

    results = []
    for ot in schedules:
        row = {c.name: getattr(ot, c.name) for c in ot.__table__.columns}
        row["patient_name"] = f"{ot.patient.first_name} {ot.patient.last_name}" if ot.patient else None
        row["surgeon_name"] = f"{ot.surgeon.first_name} {ot.surgeon.last_name}" if ot.surgeon else None
        results.append(row)
    return results


# ============================================================
# Lab Orders for Admission
# ============================================================

@router.get("/admissions/{admission_id}/lab-orders")
async def get_admission_lab_orders(
    admission_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    """Get all lab orders linked to an admission."""
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    orders = db.query(PatientLabOrder).filter(
        PatientLabOrder.admission_id == admission_id
    ).order_by(PatientLabOrder.order_date.desc()).all()

    results = []
    for order in orders:
        test = db.query(LabTest).filter(LabTest.id == order.test_id).first()
        doctor = db.query(User).filter(User.id == order.doctor_id).first() if order.doctor_id else None
        report = db.query(LabReport).filter(LabReport.order_id == order.id).first()
        results.append({
            "id": order.id,
            "order_number": order.order_number,
            "test_id": order.test_id,
            "test_name": test.name if test else None,
            "test_code": test.test_code if test else None,
            "doctor_id": order.doctor_id,
            "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else None,
            "status": order.status,
            "priority": order.priority,
            "order_date": order.order_date,
            "completion_date": order.completion_date,
            "amount": order.amount or 0.0,
            "payment_status": order.payment_status or "pending",
            "has_report": report is not None,
            "report_id": report.id if report else None,
            "notes": order.notes,
            "sample_id": order.sample_id,
        })
    return results


@router.get("/admissions/{admission_id}/lab-tests-available")
async def get_available_lab_tests(
    admission_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    """Get available lab tests for ordering from inpatient context."""
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    tests = db.query(LabTest).filter(
        LabTest.hospital_id == current_user.hospital_id,
        LabTest.is_active == True
    ).order_by(LabTest.name).all()

    return [{"id": t.id, "name": t.name, "test_code": t.test_code, "cost": t.cost or 0.0, "category": t.category} for t in tests]


# ============================================================
# Admission Documents (file attachments)
# ============================================================

ALLOWED_DOC_TYPES = {"consent_form", "referral_letter", "insurance_doc", "lab_report", "discharge_summary", "other"}
ALLOWED_MIME_TYPES = {
    "application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp",
    "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/admissions/{admission_id}/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_admission_document(
    admission_id: int,
    file: UploadFile = File(...),
    document_type: str = Form(default="other"),
    document_name: str = Form(default=""),
    notes: str = Form(default=""),
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    if document_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid document type. Allowed: {ALLOWED_DOC_TYPES}")

    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail="File type not allowed. Supported: PDF, images, Word documents")

    # Read file content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large. Max 10MB")

    # Generate unique filename
    ext = os.path.splitext(file.filename)[1] if file.filename else ".bin"
    stored_name = f"adm_{admission_id}_{uuid.uuid4().hex[:8]}{ext}"
    rel_path = os.path.join("admission_docs", stored_name)

    # Save to uploads directory
    from app.utils.paths import get_uploads_dir
    upload_dir = os.path.join(get_uploads_dir(), "admission_docs")
    os.makedirs(upload_dir, exist_ok=True)
    full_path = os.path.join(upload_dir, stored_name)
    with open(full_path, "wb") as f:
        f.write(content)

    doc = AdmissionDocument(
        admission_id=admission_id,
        document_type=document_type,
        document_name=document_name or file.filename or "Untitled",
        file_name=stored_name,
        file_path=rel_path,
        file_size=len(content),
        mime_type=file.content_type,
        uploaded_by_id=current_user.id,
        notes=notes or None,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    uploader = db.query(User).filter(User.id == doc.uploaded_by_id).first()
    return {
        **{c.name: getattr(doc, c.name) for c in doc.__table__.columns},
        "uploaded_by_name": f"{uploader.first_name} {uploader.last_name}" if uploader else None,
    }


@router.get("/admissions/{admission_id}/documents", response_model=List[DocumentResponse])
async def list_admission_documents(
    admission_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    docs = db.query(AdmissionDocument).filter(
        AdmissionDocument.admission_id == admission_id
    ).order_by(AdmissionDocument.created_at.desc()).all()

    result = []
    for doc in docs:
        uploader = db.query(User).filter(User.id == doc.uploaded_by_id).first()
        result.append({
            **{c.name: getattr(doc, c.name) for c in doc.__table__.columns},
            "uploaded_by_name": f"{uploader.first_name} {uploader.last_name}" if uploader else None,
        })
    return result


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    doc = db.query(AdmissionDocument).filter(AdmissionDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    from app.utils.paths import get_uploads_dir
    full_path = os.path.join(get_uploads_dir(), doc.file_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        full_path,
        media_type=doc.mime_type or "application/octet-stream",
        filename=doc.document_name,
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "delete")),
    db: Session = Depends(get_db),
):
    doc = db.query(AdmissionDocument).filter(AdmissionDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete file from disk
    from app.utils.paths import get_uploads_dir
    full_path = os.path.join(get_uploads_dir(), doc.file_path)
    if os.path.exists(full_path):
        os.remove(full_path)

    db.delete(doc)
    db.commit()


# ============================================================
# Nursing Notes
# ============================================================

@router.post("/admissions/{admission_id}/nursing-notes", response_model=NursingNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_nursing_note(
    admission_id: int,
    data: NursingNoteCreate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    note = NursingNote(
        admission_id=admission_id,
        patient_id=admission.patient_id,
        nurse_id=current_user.id,
        shift=data.shift,
        note_type=data.note_type,
        content=data.content,
        hospital_id=hospital.id,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return NursingNoteResponse(
        **{c.name: getattr(note, c.name) for c in note.__table__.columns},
        nurse_name=f"{current_user.first_name} {current_user.last_name}",
    )


@router.get("/admissions/{admission_id}/nursing-notes", response_model=List[NursingNoteResponse])
async def list_nursing_notes(
    admission_id: int,
    shift: Optional[str] = Query(default=None, pattern="^(morning|afternoon|night)$"),
    note_type: Optional[str] = Query(default=None),
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    q = db.query(NursingNote).filter(NursingNote.admission_id == admission_id)
    if shift:
        q = q.filter(NursingNote.shift == shift)
    if note_type:
        q = q.filter(NursingNote.note_type == note_type)
    notes = q.order_by(NursingNote.created_at.desc()).all()

    result = []
    for n in notes:
        nurse = db.query(User).filter(User.id == n.nurse_id).first()
        result.append(NursingNoteResponse(
            **{c.name: getattr(n, c.name) for c in n.__table__.columns},
            nurse_name=f"{nurse.first_name} {nurse.last_name}" if nurse else None,
        ))
    return result


@router.put("/nursing-notes/{note_id}", response_model=NursingNoteResponse)
async def update_nursing_note(
    note_id: int,
    data: NursingNoteUpdate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    note = db.query(NursingNote).filter(NursingNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Nursing note not found")
    if note.nurse_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only edit your own notes")

    for field, value in data.dict(exclude_unset=True).items():
        setattr(note, field, value)
    db.commit()
    db.refresh(note)
    nurse = db.query(User).filter(User.id == note.nurse_id).first()
    return NursingNoteResponse(
        **{c.name: getattr(note, c.name) for c in note.__table__.columns},
        nurse_name=f"{nurse.first_name} {nurse.last_name}" if nurse else None,
    )


@router.delete("/nursing-notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_nursing_note(
    note_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "delete")),
    db: Session = Depends(get_db),
):
    note = db.query(NursingNote).filter(NursingNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Nursing note not found")
    db.delete(note)
    db.commit()


# ============================================================
# Diet Orders
# ============================================================

def _diet_to_response(d, db) -> dict:
    ordered_by = db.query(User).filter(User.id == d.ordered_by_id).first()
    return {
        **{c.name: getattr(d, c.name) for c in d.__table__.columns},
        "ordered_by_name": f"{ordered_by.first_name} {ordered_by.last_name}" if ordered_by else None,
    }


@router.post("/admissions/{admission_id}/diet-orders", response_model=DietOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_diet_order(
    admission_id: int,
    data: DietOrderCreate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    # Deactivate any existing active diet order for this admission
    db.query(DietOrder).filter(
        DietOrder.admission_id == admission_id,
        DietOrder.is_active == True,
    ).update({"is_active": False})

    order = DietOrder(
        admission_id=admission_id,
        patient_id=admission.patient_id,
        diet_type=data.diet_type,
        meal_instructions=data.meal_instructions,
        allergies=data.allergies,
        notes=data.notes,
        ordered_by_id=current_user.id,
        hospital_id=hospital.id,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return _diet_to_response(order, db)


@router.get("/admissions/{admission_id}/diet-orders", response_model=List[DietOrderResponse])
async def list_diet_orders(
    admission_id: int,
    active_only: bool = Query(default=False),
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    q = db.query(DietOrder).filter(DietOrder.admission_id == admission_id)
    if active_only:
        q = q.filter(DietOrder.is_active == True)
    orders = q.order_by(DietOrder.created_at.desc()).all()
    return [_diet_to_response(o, db) for o in orders]


@router.put("/diet-orders/{order_id}", response_model=DietOrderResponse)
async def update_diet_order(
    order_id: int,
    data: DietOrderUpdate,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "write")),
    db: Session = Depends(get_db),
):
    order = db.query(DietOrder).filter(DietOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Diet order not found")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(order, field, value)
    db.commit()
    db.refresh(order)
    return _diet_to_response(order, db)


@router.delete("/diet-orders/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_diet_order(
    order_id: int,
    current_user: User = Depends(require_permission(Modules.INPATIENT, "delete")),
    db: Session = Depends(get_db),
):
    order = db.query(DietOrder).filter(DietOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Diet order not found")
    db.delete(order)
    db.commit()


@router.get("/diet-orders/active", response_model=List[DietOrderResponse])
async def list_all_active_diet_orders(
    current_user: User = Depends(require_permission(Modules.INPATIENT, "read")),
    db: Session = Depends(get_db),
):
    """Get all active diet orders across all current admissions (for nurse dashboard)."""
    orders = db.query(DietOrder).join(Admission).filter(
        DietOrder.is_active == True,
        Admission.status == "admitted",
    ).order_by(DietOrder.created_at.desc()).all()
    result = []
    for o in orders:
        resp = _diet_to_response(o, db)
        adm = db.query(Admission).filter(Admission.id == o.admission_id).first()
        patient = db.query(Patient).filter(Patient.id == o.patient_id).first()
        resp["patient_name"] = f"{patient.first_name} {patient.last_name}" if patient else None
        resp["room_number"] = None
        resp["bed_label"] = None
        if adm:
            room = db.query(RoomManagement).filter(RoomManagement.id == adm.room_id).first()
            resp["room_number"] = room.room_number if room else None
            resp["bed_label"] = adm.bed.bed_label if adm.bed else adm.bed_number
            resp["admission_number"] = adm.admission_number
        result.append(resp)
    return result
