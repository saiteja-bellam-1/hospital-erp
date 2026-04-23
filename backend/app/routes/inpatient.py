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
    PatientVisit, InpatientRateConfig, OTSchedule, Bed, AdmissionDocument, NursingNote, DietOrder,
    VitalSigns, MedicationAdministration,
    AdmissionDeposit, AncillaryServiceCatalog, AdmissionAncillaryCharge, Procedure,
    SurgeryPackage, AdmissionPackage, InsurancePreAuth, InsurancePreAuthExpansion,
    TPACompany, BillSplit,
)
from app.models.pharmacy import Prescription, PrescriptionItem, Medicine
from app.models.prescriptions_simple import SimplePrescription
from app.models.lab import PatientLabOrder, LabTest, LabReport
from app.utils.dependencies import get_current_user, require_permission, require_feature_permission
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
    bed_id: Optional[int] = None
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
    # Required when the update changes room/bed — used to populate BedTransferHistory
    transfer_reason: Optional[str] = None

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
    # Phase 4 — readmission metadata
    is_readmission: Optional[bool] = False
    previous_admission_id: Optional[int] = None
    days_since_last_discharge: Optional[int] = None
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
    procedure_id: Optional[int] = None  # If set, auto-fills procedure_charge from catalog
    scheduled_date: datetime
    estimated_duration_minutes: Optional[int] = Field(default=None, ge=1)
    pre_op_notes: Optional[str] = None

class OTScheduleUpdate(BaseModel):
    surgeon_id: Optional[int] = None
    anaesthetist_id: Optional[int] = None
    ot_room_number: Optional[str] = None
    procedure_name: Optional[str] = None
    procedure_id: Optional[int] = None
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
    procedure_id: Optional[int] = None
    scheduled_date: datetime
    estimated_duration_minutes: Optional[int]
    status: str
    pre_op_notes: Optional[str]
    post_op_notes: Optional[str]
    surgeon_fee: Optional[float] = 0.0
    anaesthetist_fee: Optional[float] = 0.0
    ot_room_charge: Optional[float] = 0.0
    equipment_charge: Optional[float] = 0.0
    consumables_charge: Optional[float] = 0.0
    procedure_charge: Optional[float] = 0.0
    other_charges: Optional[float] = 0.0
    total_charges: Optional[float] = 0.0
    billed: Optional[bool] = False
    bill_id: Optional[int] = None
    created_at: Optional[datetime]
    # Joined fields
    patient_name: Optional[str] = None
    surgeon_name: Optional[str] = None
    class Config:
        from_attributes = True


class OTChargesUpdate(BaseModel):
    surgeon_fee: Optional[float] = Field(default=None, ge=0)
    anaesthetist_fee: Optional[float] = Field(default=None, ge=0)
    ot_room_charge: Optional[float] = Field(default=None, ge=0)
    equipment_charge: Optional[float] = Field(default=None, ge=0)
    consumables_charge: Optional[float] = Field(default=None, ge=0)
    procedure_charge: Optional[float] = Field(default=None, ge=0)
    other_charges: Optional[float] = Field(default=None, ge=0)

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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_beds")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_beds")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_beds")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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
#
# DEPRECATED — Hospital-wide doctor/nurse/procedure rates have been replaced by:
#   * per-user `inpatient_fee_inr` for doctor and nurse visits
#   * the Procedure catalog (see /procedures endpoints) for OT charges
# These endpoints are kept temporarily for backwards compatibility with older
# frontends. Remove once no client reads them.

@router.get("/rate-config", response_model=RateConfigResponse)
async def get_rate_config(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "set_room_rates")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_beds")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_beds")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_beds")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "admit_patients")),
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

    # Phase 4: Readmission detection — flag if patient has a discharge in the last 30 days
    is_readmission = False
    previous_admission_id = None
    days_since = None
    last_discharge = db.query(DischargeRecord).join(Admission).filter(
        Admission.patient_id == data.patient_id,
    ).order_by(DischargeRecord.discharge_date.desc()).first()
    if last_discharge and last_discharge.discharge_date:
        days_since = (datetime.now(last_discharge.discharge_date.tzinfo) - last_discharge.discharge_date).days \
            if last_discharge.discharge_date.tzinfo else (datetime.now() - last_discharge.discharge_date).days
        if days_since is not None and days_since <= 30:
            is_readmission = True
            previous_admission_id = last_discharge.admission_id

    admission = Admission(
        **data.model_dump(),
        admission_number=admission_number,
        is_readmission=is_readmission,
        previous_admission_id=previous_admission_id,
        days_since_last_discharge=days_since,
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "update_admission")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status != "admitted":
        raise HTTPException(status_code=400, detail="Cannot update a discharged/transferred admission")

    update_data = data.model_dump(exclude_unset=True)
    transfer_reason = update_data.pop("transfer_reason", None)
    hospital = _get_hospital(db, current_user)

    room_changed = "room_id" in update_data and update_data["room_id"] != admission.room_id
    bed_changed = "bed_id" in update_data and update_data["bed_id"] != admission.bed_id
    old_room_id = admission.room_id
    old_bed_id = admission.bed_id

    # Handle room transfer
    if room_changed:
        if not transfer_reason:
            raise HTTPException(status_code=400, detail="transfer_reason is required when changing room")
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

    if bed_changed and not room_changed and not transfer_reason:
        raise HTTPException(status_code=400, detail="transfer_reason is required when changing bed")

    for key, value in update_data.items():
        setattr(admission, key, value)

    # Record transfer history for room or bed change
    if room_changed or bed_changed:
        new_room_id = admission.room_id  # already updated via setattr
        new_bed_id = admission.bed_id
        # Detect ward (department) change for transfer_type
        new_room = db.query(RoomManagement).filter(RoomManagement.id == new_room_id).first()
        old_room = db.query(RoomManagement).filter(RoomManagement.id == old_room_id).first() if old_room_id else None
        if room_changed and new_room and old_room and (old_room.department or "") != (new_room.department or ""):
            ttype = "ward_change"
        elif room_changed:
            ttype = "room_change"
        else:
            ttype = "bed_change"

        history = BedTransferHistory(
            admission_id=admission.id,
            from_room_id=old_room_id,
            from_bed_id=old_bed_id,
            to_room_id=new_room_id,
            to_bed_id=new_bed_id,
            transfer_type=ttype,
            reason=transfer_reason,
            transferred_by_id=current_user.id,
            status="completed",
            hospital_id=hospital.id,
        )
        db.add(history)

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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "update_claim_status")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_visits")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status != "admitted":
        raise HTTPException(status_code=400, detail="Cannot add visits to a non-active admission")

    hospital = _get_hospital(db, current_user)

    visitor = db.query(User).filter(User.id == data.visitor_id).first()

    # Auto-populate charge_amount from the visiting user's inpatient_fee_inr if not provided.
    # Doctor and nurse visits both read the same column on User; procedure visits don't auto-fill
    # (those flow through OT scheduling instead).
    charge = data.charge_amount
    if charge is None:
        if visitor and data.visit_type in ("doctor_visit", "nurse_visit"):
            try:
                charge = float(visitor.inpatient_fee_inr) if visitor.inpatient_fee_inr else 0
            except (ValueError, TypeError):
                charge = 0
        else:
            charge = 0

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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_visits")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_visits")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "discharge_patients")),
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

    # Release structured bed if assigned — move to 'cleaning' so housekeeping can take over
    if admission.bed_id:
        bed_obj = db.query(Bed).filter(Bed.id == admission.bed_id).first()
        if bed_obj:
            # Import lazily to avoid circular resolution issues during module load
            from app.models.inpatient import BedTurnoverLog as _BTL
            old_status = bed_obj.status or "occupied"
            bed_obj.status = "cleaning"
            bed_obj.current_admission_id = None
            db.add(_BTL(
                bed_id=bed_obj.id,
                status_from=old_status,
                status_to="cleaning",
                changed_by_id=current_user.id,
                notes="Auto-triggered by patient discharge",
            ))

    # Sync room bed counts — beds in 'cleaning' do NOT count as available
    if room:
        room_beds = db.query(Bed).filter(Bed.room_id == room.id).count()
        if room_beds > 0:
            room.available_beds = db.query(Bed).filter(Bed.room_id == room.id, Bed.status == "available").count()
            room.bed_count = room_beds
        else:
            # Legacy path (no structured Bed records): increment directly
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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
                "id": item.id,
                "medicine_id": item.medicine_id,
                "name": medicine.name if medicine else "Unknown",
                "dosage": item.dosage,
                "duration": item.duration,
                "quantity": item.quantity_prescribed,
                "quantity_dispensed": item.quantity_dispensed,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
                "status": item.status,
                "frequency": item.frequency,
                "schedule_times": item.schedule_times,
                "duration_days": item.duration_days,
                "route": item.route,
                "is_prn": item.is_prn,
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

def _compute_admission_charges(db: Session, admission: Admission, unbilled_only: bool = False) -> dict:
    """Compute the full breakdown of charges for an admission.

    When `unbilled_only=True`, returns only items not yet attached to a bill —
    used for interim billing and the `unbilled_only=true` preview. Room charge
    accounts for what was already billed on previous bills (so interim bills
    don't double-bill the room).
    """
    room = db.query(RoomManagement).filter(RoomManagement.id == admission.room_id).first()
    end_date = datetime.now(admission.admission_date.tzinfo) if admission.admission_date and admission.admission_date.tzinfo else datetime.now()
    if admission.status == "discharged" and admission.discharge:
        end_date = admission.discharge.discharge_date or end_date
    stay_days = max((end_date - admission.admission_date).days, 1) if admission.admission_date else 1
    room_charge_per_day = float(room.room_charge_per_day) if room else 0.0
    full_room_total = room_charge_per_day * stay_days

    # How much room time has been billed already?
    billed_room_total = 0.0
    if unbilled_only:
        prev_room_items = db.query(BillItem).join(Bill, Bill.id == BillItem.bill_id).filter(
            Bill.bill_type == "admission",
            Bill.reference_id == admission.id,
            Bill.status != "cancelled",
            BillItem.item_type == "room_charge",
        ).all()
        billed_room_total = sum(float(it.total_price or 0) for it in prev_room_items)
    room_total = max(full_room_total - billed_room_total, 0.0) if unbilled_only else full_room_total

    # Visits
    visits_q = db.query(PatientVisit).options(joinedload(PatientVisit.visitor)).filter(
        PatientVisit.admission_id == admission.id,
    )
    if unbilled_only:
        visits_q = visits_q.filter(PatientVisit.bill_id.is_(None), PatientVisit.billed == False)
    visits = visits_q.all()
    visit_total = sum(float(v.charge_amount or 0) for v in visits)
    visit_summary = {}
    for v in visits:
        vtype = v.visit_type
        if vtype not in visit_summary:
            visit_summary[vtype] = {"count": 0, "total": 0.0, "items": []}
        visit_summary[vtype]["count"] += 1
        visit_summary[vtype]["total"] += float(v.charge_amount or 0)
        visit_summary[vtype]["items"].append({
            "id": v.id,
            "date": v.visit_datetime.isoformat() if v.visit_datetime else None,
            "visitor": f"{v.visitor.first_name} {v.visitor.last_name}" if v.visitor else "N/A",
            "amount": float(v.charge_amount or 0),
            "billed": bool(v.billed) or bool(v.bill_id),
            "notes": v.notes,
        })

    # OT charges
    ot_q = db.query(OTSchedule).filter(
        OTSchedule.admission_id == admission.id,
        OTSchedule.status == "completed",
    )
    if unbilled_only:
        ot_q = ot_q.filter(OTSchedule.billed == False)
    ot_entries = ot_q.all()
    ot_total = sum(o.total_charges for o in ot_entries)
    ot_breakdown = [
        {
            "id": o.id,
            "procedure": o.procedure_name,
            "date": o.scheduled_date.isoformat() if o.scheduled_date else None,
            "total": o.total_charges,
            "billed": bool(o.billed),
            "components": {
                "surgeon_fee": float(o.surgeon_fee or 0),
                "anaesthetist_fee": float(o.anaesthetist_fee or 0),
                "ot_room_charge": float(o.ot_room_charge or 0),
                "equipment_charge": float(o.equipment_charge or 0),
                "consumables_charge": float(o.consumables_charge or 0),
                "procedure_charge": float(o.procedure_charge or 0),
                "other_charges": float(o.other_charges or 0),
            },
        }
        for o in ot_entries
    ]

    # Ancillary charges
    anc_q = db.query(AdmissionAncillaryCharge).filter(AdmissionAncillaryCharge.admission_id == admission.id)
    if unbilled_only:
        anc_q = anc_q.filter(AdmissionAncillaryCharge.billed == False)
    anc_entries = anc_q.all()
    ancillary_total = sum(float(c.total_amount or 0) for c in anc_entries)
    ancillary_breakdown = [_ancillary_to_response(c, db) for c in anc_entries]

    # Pharmacy
    rx_q = db.query(Prescription).filter(
        Prescription.admission_id == admission.id,
        Prescription.status.in_(["dispensed", "partial"]),
    )
    if unbilled_only:
        rx_q = rx_q.filter(Prescription.inpatient_bill_id.is_(None))
    pharmacy_rxs = rx_q.all()
    pharmacy_total = sum(float(rx.total_amount or 0) for rx in pharmacy_rxs)

    # Lab
    lab_q = db.query(PatientLabOrder).filter(
        PatientLabOrder.admission_id == admission.id,
        PatientLabOrder.status != "cancelled",
    )
    if unbilled_only:
        lab_q = lab_q.filter(PatientLabOrder.inpatient_bill_id.is_(None))
    lab_orders = lab_q.all()
    lab_total = sum(float(o.amount or 0) for o in lab_orders)

    subtotal = room_total + visit_total + ot_total + ancillary_total + pharmacy_total + lab_total

    return {
        "stay_days": stay_days,
        "room": {
            "room_number": room.room_number if room else "N/A",
            "room_type": room.room_type if room else "N/A",
            "charge_per_day": room_charge_per_day,
            "total": room_total,
            "full_total": full_room_total,
            "billed_so_far": billed_room_total,
        },
        "visits": visit_summary,
        "visit_total": visit_total,
        "ot_entries": ot_breakdown,
        "ot_total": ot_total,
        "ancillary_entries": ancillary_breakdown,
        "ancillary_total": ancillary_total,
        "pharmacy_total": pharmacy_total,
        "lab_total": lab_total,
        "room_total": room_total,
        "subtotal": subtotal,
        # Source records (used by bill creation to tag with bill_id)
        "_visits": visits,
        "_ot": ot_entries,
        "_ancillary": anc_entries,
        "_pharmacy_rxs": pharmacy_rxs,
        "_lab_orders": lab_orders,
        "_room_unbilled_total": room_total if unbilled_only else 0.0,
        "_room_charge_per_day": room_charge_per_day,
        "_room": room,
    }


@router.get("/admissions/{admission_id}/bill")
async def get_admission_bill(
    admission_id: int,
    unbilled_only: bool = Query(default=False, description="Show only items not yet attached to a finalised/interim bill"),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_bill")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first()

    breakdown = _compute_admission_charges(db, admission, unbilled_only=unbilled_only)

    # Package mode
    pkg_assignment = db.query(AdmissionPackage).filter(AdmissionPackage.admission_id == admission_id).first()
    package_block = None
    if pkg_assignment:
        pkg = db.query(SurgeryPackage).filter(SurgeryPackage.id == pkg_assignment.package_id).first()
        package_block = {
            "package_id": pkg.id if pkg else None,
            "package_name": pkg.package_name if pkg else None,
            "package_code": pkg.package_code if pkg else None,
            "agreed_price": pkg_assignment.agreed_price,
            "included_room_type": pkg.included_room_type if pkg else None,
            "included_stay_days": pkg.included_stay_days if pkg else 0,
            "included_services": pkg.included_services if pkg else [],
            "excess_per_day_charge": float(pkg.excess_per_day_charge or 0) if pkg else 0,
        }
        # Excess calculation
        excess_days = max(breakdown["stay_days"] - (pkg.included_stay_days or 0), 0)
        excess_room = excess_days * float(pkg.excess_per_day_charge or 0)
        included = set(pkg.included_services or [])
        excess_total = excess_room
        if "doctor_visit" not in included and "visits" not in included:
            excess_total += breakdown["visit_total"]
        if "pharmacy" not in included:
            excess_total += breakdown["pharmacy_total"]
        if "lab" not in included:
            excess_total += breakdown["lab_total"]
        if "ancillary" not in included:
            excess_total += breakdown["ancillary_total"]
        if "ot" not in included and "surgery" not in included:
            excess_total += breakdown["ot_total"]
        package_block["excess_days"] = excess_days
        package_block["excess_room"] = excess_room
        package_block["excess_total"] = round(excess_total, 2)
        package_block["grand_total"] = round(pkg_assignment.agreed_price + excess_total, 2)

    grand_total = (package_block["grand_total"] if package_block else breakdown["subtotal"])

    # Strip private keys before responding
    response_breakdown = {k: v for k, v in breakdown.items() if not k.startswith("_")}

    return {
        "admission_id": admission_id,
        "admission_number": admission.admission_number,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "N/A",
        "patient_id": patient.patient_id if patient else None,
        "admission_date": admission.admission_date.isoformat() if admission.admission_date else None,
        "status": admission.status,
        "unbilled_only": unbilled_only,
        "package": package_block,
        **response_breakdown,
        "grand_total": grand_total,
    }


@router.get("/admissions/{admission_id}/bills")
async def list_admission_bills(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_bill")),
    db: Session = Depends(get_db),
):
    """All Bill records (interim + final) for an admission, oldest-first."""
    bills = db.query(Bill).filter(
        Bill.bill_type == "admission",
        Bill.reference_id == admission_id,
    ).order_by(Bill.bill_date.asc()).all()
    return [
        {
            "id": b.id,
            "bill_number": b.bill_number,
            "bill_subtype": b.bill_subtype or "final",
            "bill_date": b.bill_date.isoformat() if b.bill_date else None,
            "subtotal": float(b.subtotal or 0),
            "discount_amount": float(b.discount_amount or 0),
            "tax_amount": float(b.tax_amount or 0),
            "total_amount": float(b.total_amount or 0),
            "status": b.status,
            "item_count": db.query(BillItem).filter(BillItem.bill_id == b.id).count(),
        }
        for b in bills
    ]


def _create_admission_bill_record(
    db: Session, admission: Admission, hospital, current_user: User,
    breakdown: dict, discount_value: float, discount_type: str, tax_percentage: float,
    bill_subtype: str,
) -> Bill:
    """Persist a Bill + BillItems and tag source records with bill_id.
    `breakdown` is the dict returned by _compute_admission_charges(... unbilled_only=True)."""
    subtotal = breakdown["subtotal"]
    discount_amount = 0.0
    if discount_value and discount_value > 0:
        if discount_type == "percentage":
            discount_amount = round(subtotal * discount_value / 100, 2)
        else:
            discount_amount = min(discount_value, subtotal)
    after_discount = subtotal - discount_amount
    tax_amount = 0.0
    if tax_percentage and tax_percentage > 0:
        tax_amount = round(after_discount * tax_percentage / 100, 2)
    grand_total = round(after_discount + tax_amount, 2)

    today = datetime.now().strftime("%Y%m%d")
    prefix = f"BILL-ADM-{today}-"
    last = db.query(Bill).filter(Bill.bill_number.like(f"{prefix}%")).order_by(Bill.id.desc()).first()
    seq = (int(last.bill_number.split("-")[-1]) + 1) if last else 1
    bill_number = f"{prefix}{seq:04d}"

    bill = Bill(
        bill_number=bill_number,
        patient_id=admission.patient_id,
        bill_type="admission",
        bill_subtype=bill_subtype,
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

    room = breakdown["_room"]
    if breakdown["room_total"] > 0 and room:
        days_in_this_bill = round(breakdown["room_total"] / breakdown["_room_charge_per_day"], 2) if breakdown["_room_charge_per_day"] else 0
        db.add(BillItem(
            bill_id=bill.id,
            item_type="room_charge",
            item_name=f"Room {room.room_number} ({room.room_type}) - {days_in_this_bill} days",
            quantity=int(days_in_this_bill) if days_in_this_bill.is_integer() else 1,
            unit_price=breakdown["_room_charge_per_day"],
            total_price=breakdown["room_total"],
        ))

    for v in breakdown["_visits"]:
        visitor = v.visitor
        db.add(BillItem(
            bill_id=bill.id,
            item_type=v.visit_type,
            item_name=f"{v.visit_type.replace('_', ' ').title()} - {visitor.first_name} {visitor.last_name}" if visitor else v.visit_type,
            quantity=1,
            unit_price=float(v.charge_amount or 0),
            total_price=float(v.charge_amount or 0),
        ))
        v.billed = True
        v.bill_id = bill.id

    for ot in breakdown["_ot"]:
        db.add(BillItem(
            bill_id=bill.id,
            item_type="ot_procedure",
            item_name=f"OT: {ot.procedure_name}",
            quantity=1,
            unit_price=ot.total_charges,
            total_price=ot.total_charges,
        ))
        ot.billed = True
        ot.bill_id = bill.id

    for c in breakdown["_ancillary"]:
        svc = db.query(AncillaryServiceCatalog).filter(AncillaryServiceCatalog.id == c.service_id).first()
        db.add(BillItem(
            bill_id=bill.id,
            item_type="ancillary",
            item_name=f"{svc.service_name if svc else 'Service'} ({svc.category if svc else ''})",
            quantity=int(c.quantity) if float(c.quantity).is_integer() else 1,
            unit_price=float(c.unit_price or 0),
            total_price=float(c.total_amount or 0),
        ))
        c.billed = True
        c.bill_id = bill.id

    for rx in breakdown["_pharmacy_rxs"]:
        rx_items = db.query(PrescriptionItem).filter(PrescriptionItem.prescription_id == rx.id).all()
        for item in rx_items:
            medicine = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
            db.add(BillItem(
                bill_id=bill.id,
                item_type="pharmacy",
                item_name=f"Rx: {medicine.name if medicine else 'Medicine'} ({item.dosage or ''})",
                quantity=item.quantity_dispensed or item.quantity_prescribed,
                unit_price=item.unit_price,
                total_price=item.total_price,
            ))
        rx.inpatient_bill_id = bill.id

    for lo in breakdown["_lab_orders"]:
        test = db.query(LabTest).filter(LabTest.id == lo.test_id).first()
        db.add(BillItem(
            bill_id=bill.id,
            item_type="lab_test",
            item_name=f"Lab: {test.name if test else 'Test'} ({lo.order_number})",
            quantity=1,
            unit_price=float(lo.amount or 0),
            total_price=float(lo.amount or 0),
        ))
        lo.inpatient_bill_id = bill.id

    db.commit()
    db.refresh(bill)
    return bill


@router.post("/admissions/{admission_id}/bill/finalize")
async def finalize_bill(
    admission_id: int,
    data: Optional[FinalizeBillRequest] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "finalize_bill")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first()
    hospital = _get_hospital(db, current_user)

    breakdown = _compute_admission_charges(db, admission, unbilled_only=True)
    if breakdown["subtotal"] <= 0:
        raise HTTPException(status_code=400, detail="No outstanding charges to finalize")

    bill = _create_admission_bill_record(
        db, admission, hospital, current_user, breakdown,
        discount_value=(data.discount_value if data else 0) or 0,
        discount_type=(data.discount_type if data else "flat") or "flat",
        tax_percentage=(data.tax_percentage if data else 0) or 0,
        bill_subtype="final",
    )

    log_action(db, current_user, "finalize_admission_bill", "inpatient", "Bill", bill.id,
               f"Finalized admission bill {bill.bill_number} for {patient.first_name} {patient.last_name}",
               details={"admission_id": admission_id, "total": float(bill.total_amount)})

    return {
        "bill_id": bill.id,
        "bill_number": bill.bill_number,
        "bill_subtype": bill.bill_subtype,
        "subtotal": float(bill.subtotal),
        "discount_amount": float(bill.discount_amount or 0),
        "tax_amount": float(bill.tax_amount or 0),
        "total_amount": float(bill.total_amount),
        "status": bill.status,
        "message": "Bill finalized successfully",
    }


@router.post("/admissions/{admission_id}/bill/interim")
async def create_interim_bill(
    admission_id: int,
    data: Optional[FinalizeBillRequest] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "generate_interim_bill")),
    db: Session = Depends(get_db),
):
    """Create an interim bill snapshot of currently unbilled charges. Subsequent
    interim/final bills will exclude items already on this one."""
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    hospital = _get_hospital(db, current_user)

    breakdown = _compute_admission_charges(db, admission, unbilled_only=True)
    if breakdown["subtotal"] <= 0:
        raise HTTPException(status_code=400, detail="No new unbilled charges since the last bill")

    bill = _create_admission_bill_record(
        db, admission, hospital, current_user, breakdown,
        discount_value=(data.discount_value if data else 0) or 0,
        discount_type=(data.discount_type if data else "flat") or "flat",
        tax_percentage=(data.tax_percentage if data else 0) or 0,
        bill_subtype="interim",
    )

    log_action(db, current_user, "create_interim_bill", "inpatient", "Bill", bill.id,
               f"Generated interim bill {bill.bill_number} (Rs.{float(bill.total_amount):,.2f})",
               {"admission_id": admission_id, "total": float(bill.total_amount)})

    return {
        "bill_id": bill.id,
        "bill_number": bill.bill_number,
        "bill_subtype": bill.bill_subtype,
        "subtotal": float(bill.subtotal),
        "discount_amount": float(bill.discount_amount or 0),
        "tax_amount": float(bill.tax_amount or 0),
        "total_amount": float(bill.total_amount),
        "status": bill.status,
    }


@router.get("/admissions/{admission_id}/bill/pdf")
async def get_bill_pdf(
    admission_id: int,
    include_header: bool = True,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_bill")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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

def _user_inpatient_fee(user: Optional[User]) -> float:
    """Parse a user's inpatient_fee_inr (stored as String) to a float, or 0 on missing/invalid."""
    if not user or not user.inpatient_fee_inr:
        return 0.0
    try:
        return float(user.inpatient_fee_inr)
    except (ValueError, TypeError):
        return 0.0


@router.post("/ot", response_model=OTScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_ot_schedule(
    data: OTScheduleCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "schedule_ot")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)

    patient = db.query(Patient).filter(Patient.id == data.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    surgeon = db.query(User).filter(User.id == data.surgeon_id).first()
    if not surgeon:
        raise HTTPException(status_code=404, detail="Surgeon not found")

    anaesthetist = None
    if data.anaesthetist_id:
        anaesthetist = db.query(User).filter(User.id == data.anaesthetist_id).first()

    # Resolve procedure from catalog (if procedure_id given). Free-text fallback when not set.
    procedure = None
    if data.procedure_id:
        procedure = db.query(Procedure).filter(Procedure.id == data.procedure_id).first()
        if not procedure:
            raise HTTPException(status_code=404, detail="Procedure not found in catalog")

    ot = OTSchedule(
        **data.model_dump(),
        created_by_id=current_user.id,
        hospital_id=hospital.id,
        # Auto-fill charges from catalog + user fees (sub-decisions A & B). Editable later via OTChargesUpdate.
        procedure_charge=float(procedure.default_rate) if procedure else 0.0,
        surgeon_fee=_user_inpatient_fee(surgeon),
        anaesthetist_fee=_user_inpatient_fee(anaesthetist),
    )
    db.add(ot)
    db.commit()
    db.refresh(ot)

    log_action(db, current_user, "create_ot_schedule", "inpatient", "OTSchedule", ot.id,
               f"Scheduled OT: {data.procedure_name} for {patient.first_name} {patient.last_name}")

    result = {c.name: getattr(ot, c.name) for c in ot.__table__.columns}
    result["total_charges"] = ot.total_charges
    result["patient_name"] = f"{patient.first_name} {patient.last_name}"
    result["surgeon_name"] = f"{surgeon.first_name} {surgeon.last_name}"
    return result


@router.get("/ot", response_model=List[OTScheduleResponse])
async def list_ot_schedules(
    schedule_date: Optional[date] = None,
    surgeon_id: Optional[int] = None,
    ot_status: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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
        row = _ot_to_response(ot)
        results.append(row)
    return results


def _ot_to_response(ot: OTSchedule) -> dict:
    row = {c.name: getattr(ot, c.name) for c in ot.__table__.columns}
    row["total_charges"] = ot.total_charges
    row["patient_name"] = f"{ot.patient.first_name} {ot.patient.last_name}" if ot.patient else None
    row["surgeon_name"] = f"{ot.surgeon.first_name} {ot.surgeon.last_name}" if ot.surgeon else None
    return row


@router.put("/ot/{ot_id}", response_model=OTScheduleResponse)
async def update_ot_schedule(
    ot_id: int,
    data: OTScheduleUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "schedule_ot")),
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
    return _ot_to_response(ot)


@router.put("/ot/{ot_id}/charges", response_model=OTScheduleResponse)
async def update_ot_charges(
    ot_id: int,
    data: OTChargesUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_ot_charges")),
    db: Session = Depends(get_db),
):
    """Set fees + consumables charges on a completed OT procedure. These flow
    into the admission bill the next time it is generated/finalised."""
    ot = db.query(OTSchedule).filter(OTSchedule.id == ot_id).first()
    if not ot:
        raise HTTPException(status_code=404, detail="OT schedule not found")
    if ot.billed:
        raise HTTPException(status_code=409, detail="OT charges already billed; create a corrective entry instead")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(ot, key, value)
    db.commit()

    ot = db.query(OTSchedule).options(
        joinedload(OTSchedule.patient),
        joinedload(OTSchedule.surgeon),
    ).filter(OTSchedule.id == ot_id).first()

    log_action(db, current_user, "update_ot_charges", "inpatient", "OTSchedule", ot.id,
               f"Set OT charges (Rs.{ot.total_charges:,.2f}) for {ot.procedure_name}",
               {"total": ot.total_charges})
    return _ot_to_response(ot)


@router.patch("/ot/{ot_id}/status")
async def update_ot_status(
    ot_id: int,
    new_status: str = Query(..., alias="status", pattern="^(scheduled|in_progress|completed|cancelled|postponed)$"),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "schedule_ot")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    today = date.today()
    schedules = db.query(OTSchedule).options(
        joinedload(OTSchedule.patient),
        joinedload(OTSchedule.surgeon),
    ).filter(
        cast(OTSchedule.scheduled_date, Date) == today
    ).order_by(OTSchedule.scheduled_date).all()

    results = [_ot_to_response(ot) for ot in schedules]
    return results


# ============================================================
# Lab Orders for Admission
# ============================================================

@router.get("/admissions/{admission_id}/lab-orders")
async def get_admission_lab_orders(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "upload_documents")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_documents")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_documents")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "delete_documents")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_nursing_notes")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_nursing_notes")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_nursing_notes")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_nursing_notes")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_diet_orders")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_diet_orders")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_diet_orders")),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_diet_orders")),
    db: Session = Depends(get_db),
):
    order = db.query(DietOrder).filter(DietOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Diet order not found")
    db.delete(order)
    db.commit()


@router.get("/diet-orders/active", response_model=List[DietOrderResponse])
async def list_all_active_diet_orders(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_diet_orders")),
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


# ============================================================
# Vital Signs
# ============================================================

# Adult reference ranges. Used for abnormal flagging only — not clinical decisions.
VITAL_RANGES = {
    "bp_systolic":      (90, 140),
    "bp_diastolic":     (60, 90),
    "heart_rate":       (60, 100),
    "respiratory_rate": (12, 20),
    "temperature_c":    (36.1, 37.5),
    "spo2":             (95, 100),
    "blood_glucose":    (70, 140),
    "pain_score":       (0, 3),
    "gcs_score":        (14, 15),
}


def _evaluate_vitals(vitals_dict: dict) -> tuple[bool, list]:
    """Return (is_abnormal, list_of_flagged_field_names). Skips None values."""
    flags = []
    for field, (lo, hi) in VITAL_RANGES.items():
        val = vitals_dict.get(field)
        if val is None:
            continue
        if val < lo or val > hi:
            flags.append(field)
    return (len(flags) > 0, flags)


class VitalSignsCreate(BaseModel):
    recorded_at: Optional[datetime] = None
    shift: Optional[str] = Field(default=None, pattern="^(morning|afternoon|night)$")
    bp_systolic: Optional[int] = Field(default=None, ge=40, le=300)
    bp_diastolic: Optional[int] = Field(default=None, ge=20, le=200)
    heart_rate: Optional[int] = Field(default=None, ge=20, le=300)
    respiratory_rate: Optional[int] = Field(default=None, ge=4, le=80)
    temperature_c: Optional[float] = Field(default=None, ge=25.0, le=45.0)
    spo2: Optional[int] = Field(default=None, ge=40, le=100)
    blood_glucose: Optional[float] = Field(default=None, ge=10, le=1000)
    pain_score: Optional[int] = Field(default=None, ge=0, le=10)
    gcs_score: Optional[int] = Field(default=None, ge=3, le=15)
    weight_kg: Optional[float] = Field(default=None, ge=0.5, le=500)
    height_cm: Optional[float] = Field(default=None, ge=20, le=250)
    position: Optional[str] = Field(default=None, max_length=30)
    notes: Optional[str] = None


class VitalSignsUpdate(BaseModel):
    bp_systolic: Optional[int] = None
    bp_diastolic: Optional[int] = None
    heart_rate: Optional[int] = None
    respiratory_rate: Optional[int] = None
    temperature_c: Optional[float] = None
    spo2: Optional[int] = None
    blood_glucose: Optional[float] = None
    pain_score: Optional[int] = None
    gcs_score: Optional[int] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    position: Optional[str] = None
    notes: Optional[str] = None
    shift: Optional[str] = None


class VitalSignsResponse(BaseModel):
    id: int
    admission_id: int
    patient_id: int
    recorded_by_id: int
    recorded_by_name: Optional[str] = None
    recorded_at: datetime
    shift: Optional[str]
    bp_systolic: Optional[int]
    bp_diastolic: Optional[int]
    heart_rate: Optional[int]
    respiratory_rate: Optional[int]
    temperature_c: Optional[float]
    spo2: Optional[int]
    blood_glucose: Optional[float]
    pain_score: Optional[int]
    gcs_score: Optional[int]
    weight_kg: Optional[float]
    height_cm: Optional[float]
    position: Optional[str]
    notes: Optional[str]
    is_abnormal: bool
    abnormal_flags: Optional[List[str]]

    class Config:
        from_attributes = True


def _vital_to_response(v, db) -> dict:
    rec = db.query(User).filter(User.id == v.recorded_by_id).first()
    return {
        **{c.name: getattr(v, c.name) for c in v.__table__.columns},
        "recorded_by_name": f"{rec.first_name} {rec.last_name}" if rec else None,
    }


@router.post("/admissions/{admission_id}/vitals", response_model=VitalSignsResponse, status_code=status.HTTP_201_CREATED)
async def record_vitals(
    admission_id: int,
    data: VitalSignsCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_vitals")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    payload = data.dict(exclude_unset=True)
    is_abnormal, flags = _evaluate_vitals(payload)

    vitals = VitalSigns(
        admission_id=admission_id,
        patient_id=admission.patient_id,
        recorded_by_id=current_user.id,
        recorded_at=payload.pop("recorded_at", None) or datetime.utcnow(),
        is_abnormal=is_abnormal,
        abnormal_flags=flags or None,
        hospital_id=hospital.id,
        **payload,
    )
    db.add(vitals)
    db.commit()
    db.refresh(vitals)

    log_action(
        db, current_user, "record_vitals", "inpatient", "VitalSigns", vitals.id,
        f"Recorded vitals for admission {admission.admission_number}",
        {"abnormal": is_abnormal, "flags": flags},
    )
    return _vital_to_response(vitals, db)


@router.get("/admissions/{admission_id}/vitals", response_model=List[VitalSignsResponse])
async def list_vitals(
    admission_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_vitals")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(VitalSigns)
        .filter(VitalSigns.admission_id == admission_id)
        .order_by(VitalSigns.recorded_at.desc())
        .limit(limit)
        .all()
    )
    return [_vital_to_response(v, db) for v in rows]


@router.get("/admissions/{admission_id}/vitals/latest", response_model=Optional[VitalSignsResponse])
async def latest_vitals(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_vitals")),
    db: Session = Depends(get_db),
):
    v = (
        db.query(VitalSigns)
        .filter(VitalSigns.admission_id == admission_id)
        .order_by(VitalSigns.recorded_at.desc())
        .first()
    )
    return _vital_to_response(v, db) if v else None


@router.put("/vitals/{vital_id}", response_model=VitalSignsResponse)
async def update_vitals(
    vital_id: int,
    data: VitalSignsUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_vitals")),
    db: Session = Depends(get_db),
):
    v = db.query(VitalSigns).filter(VitalSigns.id == vital_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Vitals record not found")

    for field, value in data.dict(exclude_unset=True).items():
        setattr(v, field, value)

    # Re-evaluate abnormal status with merged values
    merged = {col.name: getattr(v, col.name) for col in v.__table__.columns}
    is_abnormal, flags = _evaluate_vitals(merged)
    v.is_abnormal = is_abnormal
    v.abnormal_flags = flags or None

    db.commit()
    db.refresh(v)
    return _vital_to_response(v, db)


@router.delete("/vitals/{vital_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vitals(
    vital_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_vitals")),
    db: Session = Depends(get_db),
):
    v = db.query(VitalSigns).filter(VitalSigns.id == vital_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Vitals record not found")
    db.delete(v)
    db.commit()


# ============================================================
# Medication Administration Record (MAR)
# ============================================================

# Frequency code → list of HH:MM strings for a 24-hour schedule.
# Used when a PrescriptionItem has frequency set but no explicit schedule_times.
FREQUENCY_DEFAULTS = {
    "ONCE": ["09:00"],
    "STAT": ["09:00"],
    "OD":   ["09:00"],
    "QD":   ["09:00"],
    "HS":   ["22:00"],          # at bedtime
    "BD":   ["08:00", "20:00"],
    "BID":  ["08:00", "20:00"],
    "TDS":  ["08:00", "14:00", "20:00"],
    "TID":  ["08:00", "14:00", "20:00"],
    "QID":  ["06:00", "12:00", "18:00", "00:00"],
    "Q4H":  ["04:00", "08:00", "12:00", "16:00", "20:00", "00:00"],
    "Q6H":  ["06:00", "12:00", "18:00", "00:00"],
    "Q8H":  ["08:00", "16:00", "00:00"],
    "Q12H": ["08:00", "20:00"],
}


def _resolve_schedule_times(item: PrescriptionItem) -> list:
    if item.is_prn:
        return []
    if item.schedule_times:
        return list(item.schedule_times)
    if item.frequency:
        return FREQUENCY_DEFAULTS.get(item.frequency.upper(), [])
    return []


class MARAdministerRequest(BaseModel):
    status: str = Field(..., pattern="^(given|missed|refused|held)$")
    administered_at: Optional[datetime] = None
    dose_given: Optional[str] = None
    route: Optional[str] = None
    site: Optional[str] = None
    reason_if_not_given: Optional[str] = None
    notes: Optional[str] = None
    witness_id: Optional[int] = None


class MARPRNRequest(BaseModel):
    prescription_item_id: Optional[int] = None
    medicine_id: Optional[int] = None
    dose_given: str = Field(..., min_length=1, max_length=100)
    route: Optional[str] = None
    site: Optional[str] = None
    notes: Optional[str] = None
    prn_indication: Optional[str] = None
    administered_at: Optional[datetime] = None


class MARResponse(BaseModel):
    id: int
    admission_id: int
    patient_id: int
    prescription_item_id: Optional[int]
    medicine_id: Optional[int]
    medicine_name: Optional[str] = None
    dosage: Optional[str] = None
    scheduled_time: Optional[datetime]
    administered_at: Optional[datetime]
    administered_by_id: Optional[int]
    administered_by_name: Optional[str] = None
    status: str
    dose_given: Optional[str]
    route: Optional[str]
    site: Optional[str]
    reason_if_not_given: Optional[str]
    notes: Optional[str]
    is_prn: bool
    prn_indication: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


def _mar_to_response(m: MedicationAdministration, db: Session) -> dict:
    pi = m.prescription_item
    medicine = None
    dosage = None
    if pi:
        medicine = db.query(Medicine).filter(Medicine.id == pi.medicine_id).first()
        dosage = pi.dosage
    elif m.medicine_id:
        medicine = db.query(Medicine).filter(Medicine.id == m.medicine_id).first()
    administrator = None
    if m.administered_by_id:
        administrator = db.query(User).filter(User.id == m.administered_by_id).first()
    return {
        **{c.name: getattr(m, c.name) for c in m.__table__.columns},
        "medicine_name": medicine.name if medicine else None,
        "dosage": dosage,
        "administered_by_name": (
            f"{administrator.first_name} {administrator.last_name}" if administrator else None
        ),
    }


@router.post("/admissions/{admission_id}/mar/generate")
async def generate_mar(
    admission_id: int,
    horizon_hours: int = Query(default=24, ge=1, le=168),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "administer_medications")),
    db: Session = Depends(get_db),
):
    """Materialise scheduled doses for the next `horizon_hours` for this admission's
    active prescriptions. Idempotent — skips dose slots that already exist."""
    hospital = _get_hospital(db, current_user)
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    from datetime import timedelta
    now = datetime.now()
    horizon_end = now + timedelta(hours=horizon_hours)

    # Active prescriptions for this admission (not cancelled)
    prescriptions = db.query(Prescription).filter(
        Prescription.admission_id == admission_id,
        Prescription.status != "cancelled",
    ).all()

    created = 0
    skipped = 0
    for pres in prescriptions:
        for item in pres.items:
            if item.is_prn:
                continue
            times = _resolve_schedule_times(item)
            if not times:
                continue

            # Generate dose timestamps from now → horizon_end at each scheduled HH:MM
            day = now.date()
            while True:
                day_dt = datetime.combine(day, datetime.min.time())
                if day_dt > horizon_end:
                    break
                for tstr in times:
                    try:
                        hh, mm = [int(x) for x in tstr.split(":")]
                    except Exception:
                        continue
                    slot = day_dt.replace(hour=hh, minute=mm)
                    if slot < now or slot > horizon_end:
                        continue

                    existing = db.query(MedicationAdministration).filter(
                        MedicationAdministration.admission_id == admission_id,
                        MedicationAdministration.prescription_item_id == item.id,
                        MedicationAdministration.scheduled_time == slot,
                    ).first()
                    if existing:
                        skipped += 1
                        continue

                    dose = MedicationAdministration(
                        admission_id=admission_id,
                        patient_id=admission.patient_id,
                        prescription_item_id=item.id,
                        medicine_id=item.medicine_id,
                        scheduled_time=slot,
                        status="scheduled",
                        route=item.route,
                        is_prn=False,
                        hospital_id=hospital.id,
                    )
                    db.add(dose)
                    created += 1
                day = day + timedelta(days=1)

    db.commit()
    return {"created": created, "skipped_existing": skipped, "horizon_hours": horizon_hours}


@router.get("/admissions/{admission_id}/mar", response_model=List[MARResponse])
async def list_mar_today(
    admission_id: int,
    target_date: Optional[date] = Query(default=None, description="Defaults to today"),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_mar")),
    db: Session = Depends(get_db),
):
    """Return scheduled + administered doses for a given day (default today),
    plus any PRN doses given on that day."""
    from datetime import timedelta
    day = target_date or date.today()
    day_start = datetime.combine(day, datetime.min.time())
    day_end = day_start + timedelta(days=1)

    rows = db.query(MedicationAdministration).filter(
        MedicationAdministration.admission_id == admission_id,
    ).filter(
        # scheduled doses for this day OR PRN doses administered on this day
        ((MedicationAdministration.scheduled_time >= day_start) &
         (MedicationAdministration.scheduled_time < day_end)) |
        ((MedicationAdministration.is_prn == True) &
         (MedicationAdministration.administered_at >= day_start) &
         (MedicationAdministration.administered_at < day_end))
    ).order_by(
        MedicationAdministration.scheduled_time.asc().nullsfirst(),
        MedicationAdministration.administered_at.asc(),
    ).all()
    return [_mar_to_response(m, db) for m in rows]


@router.get("/admissions/{admission_id}/mar/history", response_model=List[MARResponse])
async def list_mar_history(
    admission_id: int,
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_mar")),
    db: Session = Depends(get_db),
):
    rows = db.query(MedicationAdministration).filter(
        MedicationAdministration.admission_id == admission_id,
    ).order_by(
        MedicationAdministration.scheduled_time.desc().nullslast(),
        MedicationAdministration.administered_at.desc(),
    ).limit(limit).all()
    return [_mar_to_response(m, db) for m in rows]


@router.post("/mar/{mar_id}/administer", response_model=MARResponse)
async def administer_dose(
    mar_id: int,
    data: MARAdministerRequest,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "administer_medications")),
    db: Session = Depends(get_db),
):
    m = db.query(MedicationAdministration).filter(MedicationAdministration.id == mar_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="MAR entry not found")
    if m.status in ("given", "refused", "missed"):
        raise HTTPException(status_code=409, detail=f"Dose already {m.status}")

    m.status = data.status
    m.administered_by_id = current_user.id
    m.administered_at = data.administered_at or datetime.utcnow()
    if data.dose_given:
        m.dose_given = data.dose_given
    if data.route:
        m.route = data.route
    if data.site:
        m.site = data.site
    if data.reason_if_not_given:
        m.reason_if_not_given = data.reason_if_not_given
    if data.notes:
        m.notes = data.notes
    if data.witness_id:
        m.witness_id = data.witness_id

    db.commit()
    db.refresh(m)

    log_action(
        db, current_user, "administer_medication", "inpatient", "MedicationAdministration", m.id,
        f"Marked dose as '{data.status}' for admission #{m.admission_id}",
        {"status": data.status, "is_prn": m.is_prn},
    )
    return _mar_to_response(m, db)


@router.post("/admissions/{admission_id}/mar/prn", response_model=MARResponse, status_code=status.HTTP_201_CREATED)
async def record_prn_dose(
    admission_id: int,
    data: MARPRNRequest,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "administer_medications")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    if not data.prescription_item_id and not data.medicine_id:
        raise HTTPException(status_code=400, detail="prescription_item_id or medicine_id required")

    pi = None
    if data.prescription_item_id:
        pi = db.query(PrescriptionItem).filter(PrescriptionItem.id == data.prescription_item_id).first()
        if not pi:
            raise HTTPException(status_code=404, detail="Prescription item not found")

    m = MedicationAdministration(
        admission_id=admission_id,
        patient_id=admission.patient_id,
        prescription_item_id=pi.id if pi else None,
        medicine_id=(pi.medicine_id if pi else data.medicine_id),
        scheduled_time=None,
        administered_at=data.administered_at or datetime.utcnow(),
        administered_by_id=current_user.id,
        status="given",
        dose_given=data.dose_given,
        route=data.route or (pi.route if pi else None),
        site=data.site,
        notes=data.notes,
        is_prn=True,
        prn_indication=data.prn_indication,
        hospital_id=hospital.id,
    )
    db.add(m)
    db.commit()
    db.refresh(m)

    log_action(
        db, current_user, "administer_prn", "inpatient", "MedicationAdministration", m.id,
        f"Recorded PRN dose for admission #{admission_id}",
        {"medicine_id": m.medicine_id, "indication": data.prn_indication},
    )
    return _mar_to_response(m, db)


@router.delete("/mar/{mar_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mar(
    mar_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "administer_medications")),
    db: Session = Depends(get_db),
):
    m = db.query(MedicationAdministration).filter(MedicationAdministration.id == mar_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="MAR entry not found")
    if m.status == "given":
        raise HTTPException(status_code=409, detail="Cannot delete an administered dose; record an amendment in nursing notes instead")
    db.delete(m)
    db.commit()


# ============================================================
# Admission Deposits & Running Balance
# ============================================================

def _generate_deposit_number(db: Session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"DEP-{today}-"
    last = db.query(AdmissionDeposit).filter(
        AdmissionDeposit.deposit_number.like(f"{prefix}%")
    ).order_by(AdmissionDeposit.id.desc()).first()
    seq = (int(last.deposit_number.split("-")[-1]) + 1) if last else 1
    return f"{prefix}{seq:04d}"


def _admission_balance_summary(db: Session, admission: Admission) -> dict:
    """Compute deposits/charges/balance for an admission. Positive balance =
    patient has unused credit (refund due on discharge); negative = patient owes."""
    deposits = db.query(AdmissionDeposit).filter(
        AdmissionDeposit.admission_id == admission.id
    ).all()
    total_collected = sum(float(d.amount) for d in deposits if d.deposit_type != "refund")
    total_refunded = sum(abs(float(d.amount)) for d in deposits if d.deposit_type == "refund")
    net_deposits = total_collected - total_refunded

    bills = db.query(Bill).filter(
        Bill.bill_type == "admission",
        Bill.reference_id == admission.id,
        Bill.status != "cancelled",
    ).all()
    total_billed = sum(float(b.total_amount or 0) for b in bills)
    total_paid = 0.0
    for b in bills:
        for p in (b.payments or []):
            total_paid += float(p.amount_paid or 0)

    return {
        "admission_id": admission.id,
        "admission_number": admission.admission_number,
        "total_collected": round(total_collected, 2),
        "total_refunded": round(total_refunded, 2),
        "net_deposits": round(net_deposits, 2),
        "total_billed": round(total_billed, 2),
        "total_paid": round(total_paid, 2),
        "balance": round(net_deposits - total_billed, 2),  # +ve = credit, -ve = patient owes
        "deposit_count": len(deposits),
        "bill_count": len(bills),
    }


class DepositCreate(BaseModel):
    amount: float = Field(..., gt=0)
    payment_method: str = Field(default="cash", pattern="^(cash|card|upi|cheque|online|bank_transfer)$")
    deposit_type: str = Field(default="initial", pattern="^(initial|topup)$")
    reference_number: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None


class RefundCreate(BaseModel):
    amount: float = Field(..., gt=0)  # always positive; stored as-is, type='refund' marks it
    payment_method: str = Field(default="cash", pattern="^(cash|card|upi|cheque|online|bank_transfer)$")
    reference_number: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None


class DepositResponse(BaseModel):
    id: int
    admission_id: int
    deposit_number: str
    amount: float
    deposit_type: str
    payment_method: str
    reference_number: Optional[str]
    notes: Optional[str]
    received_by_id: int
    received_by_name: Optional[str] = None
    received_at: datetime

    class Config:
        from_attributes = True


def _deposit_to_response(d: AdmissionDeposit, db: Session) -> dict:
    rec = db.query(User).filter(User.id == d.received_by_id).first()
    return {
        **{c.name: getattr(d, c.name) for c in d.__table__.columns},
        "received_by_name": f"{rec.first_name} {rec.last_name}" if rec else None,
    }


@router.post("/admissions/{admission_id}/deposits", response_model=DepositResponse, status_code=status.HTTP_201_CREATED)
async def create_deposit(
    admission_id: int,
    data: DepositCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "receive_deposits")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    deposit = AdmissionDeposit(
        admission_id=admission_id,
        deposit_number=_generate_deposit_number(db),
        amount=data.amount,
        deposit_type=data.deposit_type,
        payment_method=data.payment_method,
        reference_number=data.reference_number,
        notes=data.notes,
        received_by_id=current_user.id,
        hospital_id=hospital.id,
    )
    db.add(deposit)
    db.commit()
    db.refresh(deposit)
    log_action(db, current_user, "create_deposit", "inpatient", "AdmissionDeposit", deposit.id,
               f"Received Rs.{data.amount:,.2f} {data.deposit_type} for admission {admission.admission_number}",
               {"amount": data.amount, "type": data.deposit_type})
    return _deposit_to_response(deposit, db)


@router.get("/admissions/{admission_id}/deposits", response_model=List[DepositResponse])
async def list_deposits(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_bill")),
    db: Session = Depends(get_db),
):
    rows = db.query(AdmissionDeposit).filter(
        AdmissionDeposit.admission_id == admission_id
    ).order_by(AdmissionDeposit.received_at.desc()).all()
    return [_deposit_to_response(d, db) for d in rows]


@router.get("/admissions/{admission_id}/balance")
async def get_admission_balance(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_bill")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    return _admission_balance_summary(db, admission)


@router.post("/admissions/{admission_id}/refund", response_model=DepositResponse, status_code=status.HTTP_201_CREATED)
async def create_refund(
    admission_id: int,
    data: RefundCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "issue_refunds")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    summary = _admission_balance_summary(db, admission)
    if data.amount > summary["balance"] + 0.01:
        raise HTTPException(
            status_code=409,
            detail=f"Refund of Rs.{data.amount:,.2f} exceeds available credit of Rs.{summary['balance']:,.2f}",
        )

    deposit = AdmissionDeposit(
        admission_id=admission_id,
        deposit_number=_generate_deposit_number(db),
        amount=data.amount,  # stored positive; deposit_type marks it as refund
        deposit_type="refund",
        payment_method=data.payment_method,
        reference_number=data.reference_number,
        notes=data.notes,
        received_by_id=current_user.id,
        hospital_id=hospital.id,
    )
    db.add(deposit)
    db.commit()
    db.refresh(deposit)
    log_action(db, current_user, "issue_refund", "inpatient", "AdmissionDeposit", deposit.id,
               f"Refunded Rs.{data.amount:,.2f} for admission {admission.admission_number}",
               {"amount": data.amount})
    return _deposit_to_response(deposit, db)


@router.delete("/deposits/{deposit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deposit(
    deposit_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "receive_deposits")),
    db: Session = Depends(get_db),
):
    """Delete a deposit entry (e.g. recorded in error). Only deposits not older
    than 24 hours can be deleted to preserve audit integrity."""
    d = db.query(AdmissionDeposit).filter(AdmissionDeposit.id == deposit_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Deposit not found")
    age_hours = (datetime.now(d.received_at.tzinfo) - d.received_at).total_seconds() / 3600
    if age_hours > 24:
        raise HTTPException(status_code=409, detail="Deposit older than 24h cannot be deleted; issue a refund instead")
    db.delete(d)
    db.commit()


# ============================================================
# TPA Companies + Bill Splits
# ============================================================

class TPACreate(BaseModel):
    tpa_name: str = Field(..., min_length=1, max_length=200)
    tpa_code: Optional[str] = Field(default=None, max_length=50)
    address: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=15)
    email: Optional[str] = Field(default=None, max_length=100)
    default_discount_percent: float = Field(default=0.0, ge=0, le=100)
    contract_details: Optional[str] = None


class TPAUpdate(BaseModel):
    tpa_name: Optional[str] = None
    tpa_code: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    default_discount_percent: Optional[float] = Field(default=None, ge=0, le=100)
    contract_details: Optional[str] = None
    is_active: Optional[bool] = None


class TPAResponse(BaseModel):
    id: int
    tpa_name: str
    tpa_code: Optional[str]
    address: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    default_discount_percent: float
    contract_details: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/tpa", response_model=List[TPAResponse])
async def list_tpa(
    active_only: bool = True,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    q = db.query(TPACompany)
    if active_only:
        q = q.filter(TPACompany.is_active == True)
    return q.order_by(TPACompany.tpa_name).all()


@router.post("/tpa", response_model=TPAResponse, status_code=status.HTTP_201_CREATED)
async def create_tpa(
    data: TPACreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_tpa")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    tpa = TPACompany(hospital_id=hospital.id, **data.model_dump())
    db.add(tpa)
    db.commit()
    db.refresh(tpa)
    return tpa


@router.put("/tpa/{tpa_id}", response_model=TPAResponse)
async def update_tpa(
    tpa_id: int,
    data: TPAUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_tpa")),
    db: Session = Depends(get_db),
):
    tpa = db.query(TPACompany).filter(TPACompany.id == tpa_id).first()
    if not tpa:
        raise HTTPException(status_code=404, detail="TPA not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(tpa, k, v)
    db.commit()
    db.refresh(tpa)
    return tpa


@router.delete("/tpa/{tpa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tpa(
    tpa_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_tpa")),
    db: Session = Depends(get_db),
):
    tpa = db.query(TPACompany).filter(TPACompany.id == tpa_id).first()
    if not tpa:
        raise HTTPException(status_code=404, detail="TPA not found")
    tpa.is_active = False
    db.commit()


# --- Bill splits ---

class BillSplitItem(BaseModel):
    payer_type: str = Field(..., pattern="^(cash|insurance|tpa)$")
    payer_name: str = Field(..., min_length=1, max_length=200)
    tpa_id: Optional[int] = None
    amount: float = Field(..., ge=0)
    notes: Optional[str] = None


class BillSplitCreate(BaseModel):
    splits: List[BillSplitItem] = Field(..., min_length=1)


class BillSplitResponse(BaseModel):
    id: int
    bill_id: int
    payer_type: str
    payer_name: str
    tpa_id: Optional[int]
    tpa_name: Optional[str] = None
    amount: float
    payment_status: str
    payment_date: Optional[datetime]
    payment_reference: Optional[str]
    notes: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


def _split_to_response(s: BillSplit, db: Session) -> dict:
    tpa = db.query(TPACompany).filter(TPACompany.id == s.tpa_id).first() if s.tpa_id else None
    return {
        **{c.name: getattr(s, c.name) for c in s.__table__.columns},
        "tpa_name": tpa.tpa_name if tpa else None,
    }


@router.post("/bills/{bill_id}/split", response_model=List[BillSplitResponse])
async def set_bill_split(
    bill_id: int,
    data: BillSplitCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_bill_splits")),
    db: Session = Depends(get_db),
):
    """Replace all bill splits with a fresh set. Sum of split amounts must
    equal the bill total (within rounding tolerance)."""
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")

    total = round(sum(s.amount for s in data.splits), 2)
    bill_total = round(float(bill.total_amount or 0), 2)
    if abs(total - bill_total) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Split total Rs.{total:,.2f} does not match bill total Rs.{bill_total:,.2f}",
        )

    # For 'tpa' payer, tpa_id is required and must reference an active TPA
    for s in data.splits:
        if s.payer_type == "tpa":
            if not s.tpa_id:
                raise HTTPException(status_code=400, detail="tpa_id required when payer_type='tpa'")
            tpa = db.query(TPACompany).filter(TPACompany.id == s.tpa_id, TPACompany.is_active == True).first()
            if not tpa:
                raise HTTPException(status_code=404, detail=f"TPA #{s.tpa_id} not found or inactive")

    # Wipe existing and create fresh
    db.query(BillSplit).filter(BillSplit.bill_id == bill_id).delete()
    for s in data.splits:
        db.add(BillSplit(
            bill_id=bill_id,
            payer_type=s.payer_type,
            payer_name=s.payer_name,
            tpa_id=s.tpa_id,
            amount=s.amount,
            notes=s.notes,
        ))
    db.commit()
    rows = db.query(BillSplit).filter(BillSplit.bill_id == bill_id).all()
    log_action(db, current_user, "set_bill_split", "billing", "Bill", bill.id,
               f"Bill {bill.bill_number} split across {len(data.splits)} payers")
    return [_split_to_response(s, db) for s in rows]


@router.get("/bills/{bill_id}/split", response_model=List[BillSplitResponse])
async def get_bill_split(
    bill_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_bill")),
    db: Session = Depends(get_db),
):
    rows = db.query(BillSplit).filter(BillSplit.bill_id == bill_id).all()
    return [_split_to_response(s, db) for s in rows]


@router.patch("/bill-splits/{split_id}/payment")
async def record_split_payment(
    split_id: int,
    payment_reference: Optional[str] = None,
    notes: Optional[str] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_bill_splits")),
    db: Session = Depends(get_db),
):
    """Mark a split (cash/insurance/tpa) as received."""
    s = db.query(BillSplit).filter(BillSplit.id == split_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Split not found")
    s.payment_status = "received"
    s.payment_date = datetime.utcnow()
    if payment_reference:
        s.payment_reference = payment_reference
    if notes:
        s.notes = (s.notes or "") + ("\n" if s.notes else "") + notes
    db.commit()
    return _split_to_response(s, db)


@router.get("/tpa/outstanding")
async def tpa_outstanding(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_bill")),
    db: Session = Depends(get_db),
):
    """Aggregate of pending TPA receivables grouped by TPA."""
    rows = db.query(BillSplit).filter(
        BillSplit.payer_type == "tpa",
        BillSplit.payment_status == "pending",
    ).all()
    by_tpa: dict = {}
    for s in rows:
        key = s.tpa_id or 0
        if key not in by_tpa:
            tpa = db.query(TPACompany).filter(TPACompany.id == s.tpa_id).first() if s.tpa_id else None
            by_tpa[key] = {
                "tpa_id": s.tpa_id,
                "tpa_name": tpa.tpa_name if tpa else (s.payer_name or "Unknown"),
                "outstanding_amount": 0.0,
                "split_count": 0,
            }
        by_tpa[key]["outstanding_amount"] += float(s.amount or 0)
        by_tpa[key]["split_count"] += 1
    return list(by_tpa.values())


# ============================================================
# Insurance Pre-Authorisations
# ============================================================

PREAUTH_STATUSES = {"requested", "approved", "rejected", "expansion_requested", "expanded", "expired"}


class PreAuthCreate(BaseModel):
    admission_id: Optional[int] = None
    patient_id: int
    insurance_provider: str = Field(..., min_length=1, max_length=200)
    policy_number: Optional[str] = Field(default=None, max_length=100)
    tpa_id: Optional[int] = None
    requested_amount: float = Field(..., gt=0)
    notes: Optional[str] = None


class PreAuthDecision(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected|expired)$")
    approved_amount: Optional[float] = Field(default=None, ge=0)
    validity_days: Optional[int] = Field(default=None, ge=0)
    approval_reference: Optional[str] = None
    notes: Optional[str] = None


class PreAuthExpansionCreate(BaseModel):
    requested_amount: float = Field(..., gt=0)
    reason: Optional[str] = None


class PreAuthExpansionDecision(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")
    approved_amount: Optional[float] = Field(default=None, ge=0)


class PreAuthExpansionResponse(BaseModel):
    id: int
    preauth_id: int
    requested_amount: float
    approved_amount: float
    status: str
    requested_at: datetime
    decided_at: Optional[datetime]
    document_path: Optional[str]
    reason: Optional[str]

    class Config:
        from_attributes = True


class PreAuthResponse(BaseModel):
    id: int
    admission_id: Optional[int]
    admission_number: Optional[str] = None
    patient_id: int
    patient_name: Optional[str] = None
    insurance_provider: str
    policy_number: Optional[str]
    tpa_id: Optional[int]
    tpa_name: Optional[str] = None
    requested_amount: float
    approved_amount: float
    status: str
    request_date: datetime
    approval_date: Optional[datetime]
    validity_days: Optional[int]
    approval_reference: Optional[str]
    approval_document_path: Optional[str]
    notes: Optional[str]
    expansions: List[PreAuthExpansionResponse] = []

    class Config:
        from_attributes = True


def _preauth_to_response(p: InsurancePreAuth, db: Session) -> dict:
    patient = db.query(Patient).filter(Patient.id == p.patient_id).first()
    admission = db.query(Admission).filter(Admission.id == p.admission_id).first() if p.admission_id else None
    tpa = db.query(TPACompany).filter(TPACompany.id == p.tpa_id).first() if p.tpa_id else None
    return {
        **{c.name: getattr(p, c.name) for c in p.__table__.columns},
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
        "admission_number": admission.admission_number if admission else None,
        "tpa_name": tpa.tpa_name if tpa else None,
        "expansions": [
            {col.name: getattr(e, col.name) for col in e.__table__.columns}
            for e in (p.expansions or [])
        ],
    }


@router.post("/preauth", response_model=PreAuthResponse, status_code=status.HTTP_201_CREATED)
async def create_preauth(
    data: PreAuthCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_preauth")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    if data.admission_id:
        adm = db.query(Admission).filter(Admission.id == data.admission_id).first()
        if not adm:
            raise HTTPException(status_code=404, detail="Admission not found")
    patient = db.query(Patient).filter(Patient.id == data.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    p = InsurancePreAuth(
        admission_id=data.admission_id,
        patient_id=data.patient_id,
        insurance_provider=data.insurance_provider,
        policy_number=data.policy_number,
        tpa_id=data.tpa_id,
        requested_amount=data.requested_amount,
        status="requested",
        notes=data.notes,
        created_by_id=current_user.id,
        hospital_id=hospital.id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    log_action(db, current_user, "create_preauth", "inpatient", "InsurancePreAuth", p.id,
               f"Requested pre-auth Rs.{data.requested_amount:,.2f} from {data.insurance_provider}")
    return _preauth_to_response(p, db)


@router.get("/preauth", response_model=List[PreAuthResponse])
async def list_preauths(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    admission_id: Optional[int] = None,
    patient_id: Optional[int] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    q = db.query(InsurancePreAuth).options(joinedload(InsurancePreAuth.expansions))
    if status_filter:
        q = q.filter(InsurancePreAuth.status == status_filter)
    if admission_id:
        q = q.filter(InsurancePreAuth.admission_id == admission_id)
    if patient_id:
        q = q.filter(InsurancePreAuth.patient_id == patient_id)
    rows = q.order_by(InsurancePreAuth.request_date.desc()).all()
    return [_preauth_to_response(p, db) for p in rows]


@router.get("/preauth/{preauth_id}", response_model=PreAuthResponse)
async def get_preauth(
    preauth_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    p = db.query(InsurancePreAuth).options(joinedload(InsurancePreAuth.expansions)).filter(InsurancePreAuth.id == preauth_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Pre-auth not found")
    return _preauth_to_response(p, db)


@router.post("/preauth/{preauth_id}/decision", response_model=PreAuthResponse)
async def record_preauth_decision(
    preauth_id: int,
    data: PreAuthDecision,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_preauth")),
    db: Session = Depends(get_db),
):
    """Record the insurer's decision (approved/rejected/expired)."""
    p = db.query(InsurancePreAuth).filter(InsurancePreAuth.id == preauth_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Pre-auth not found")
    if p.status not in ("requested", "expansion_requested"):
        raise HTTPException(status_code=409, detail=f"Pre-auth in '{p.status}' state cannot be re-decided directly")

    p.status = data.status
    p.approved_amount = data.approved_amount or 0.0
    p.approval_date = datetime.utcnow() if data.status == "approved" else p.approval_date
    p.validity_days = data.validity_days
    p.approval_reference = data.approval_reference
    if data.notes:
        p.notes = (p.notes or "") + ("\n" if p.notes else "") + data.notes
    db.commit()
    db.refresh(p)
    log_action(db, current_user, "preauth_decision", "inpatient", "InsurancePreAuth", p.id,
               f"Pre-auth {data.status}: Rs.{(data.approved_amount or 0):,.2f}")
    return _preauth_to_response(p, db)


@router.post("/preauth/{preauth_id}/upload-document")
async def upload_preauth_document(
    preauth_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_preauth")),
    db: Session = Depends(get_db),
):
    p = db.query(InsurancePreAuth).filter(InsurancePreAuth.id == preauth_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Pre-auth not found")

    upload_dir = os.path.join(get_uploads_dir(), "preauth_docs")
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1]
    stored_name = f"preauth_{preauth_id}_{uuid.uuid4().hex}{ext}"
    full_path = os.path.join(upload_dir, stored_name)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 10MB)")
    with open(full_path, "wb") as f:
        f.write(contents)
    p.approval_document_path = f"preauth_docs/{stored_name}"
    db.commit()
    return {"document_path": p.approval_document_path}


@router.post("/preauth/{preauth_id}/expansion-request", response_model=PreAuthExpansionResponse, status_code=status.HTTP_201_CREATED)
async def request_preauth_expansion(
    preauth_id: int,
    data: PreAuthExpansionCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_preauth")),
    db: Session = Depends(get_db),
):
    p = db.query(InsurancePreAuth).filter(InsurancePreAuth.id == preauth_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Pre-auth not found")
    if p.status not in ("approved", "expanded"):
        raise HTTPException(status_code=409, detail="Can only request expansion on an approved pre-auth")

    exp = InsurancePreAuthExpansion(
        preauth_id=preauth_id,
        requested_amount=data.requested_amount,
        reason=data.reason,
        status="requested",
        requested_by_id=current_user.id,
    )
    p.status = "expansion_requested"
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return {col.name: getattr(exp, col.name) for col in exp.__table__.columns}


@router.post("/preauth/expansions/{expansion_id}/decision", response_model=PreAuthExpansionResponse)
async def record_expansion_decision(
    expansion_id: int,
    data: PreAuthExpansionDecision,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_preauth")),
    db: Session = Depends(get_db),
):
    exp = db.query(InsurancePreAuthExpansion).filter(InsurancePreAuthExpansion.id == expansion_id).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Expansion request not found")

    exp.status = data.status
    exp.approved_amount = data.approved_amount or 0.0
    exp.decided_at = datetime.utcnow()

    # Roll up to parent pre-auth
    parent = db.query(InsurancePreAuth).filter(InsurancePreAuth.id == exp.preauth_id).first()
    if parent and data.status == "approved":
        parent.approved_amount = (parent.approved_amount or 0) + (data.approved_amount or 0)
        parent.status = "expanded"
    elif parent and data.status == "rejected":
        parent.status = "approved"  # roll back to approved state, expansion failed
    db.commit()
    db.refresh(exp)
    return {col.name: getattr(exp, col.name) for col in exp.__table__.columns}


@router.delete("/preauth/{preauth_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preauth(
    preauth_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_preauth")),
    db: Session = Depends(get_db),
):
    p = db.query(InsurancePreAuth).filter(InsurancePreAuth.id == preauth_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Pre-auth not found")
    db.delete(p)
    db.commit()


# ============================================================
# Surgery Packages
# ============================================================

PKG_INCLUDED_OPTIONS = {"room", "doctor_visit", "nurse_visit", "procedure", "ot", "surgery", "pharmacy", "lab", "ancillary"}


class PackageCreate(BaseModel):
    package_name: str = Field(..., min_length=1, max_length=200)
    package_code: Optional[str] = Field(default=None, max_length=50)
    base_price: float = Field(..., ge=0)
    included_room_type: Optional[str] = Field(default=None, max_length=30)
    included_stay_days: int = Field(default=0, ge=0)
    included_services: Optional[List[str]] = None
    excess_per_day_charge: float = Field(default=0.0, ge=0)
    description: Optional[str] = None


class PackageUpdate(BaseModel):
    package_name: Optional[str] = None
    package_code: Optional[str] = None
    base_price: Optional[float] = Field(default=None, ge=0)
    included_room_type: Optional[str] = None
    included_stay_days: Optional[int] = Field(default=None, ge=0)
    included_services: Optional[List[str]] = None
    excess_per_day_charge: Optional[float] = Field(default=None, ge=0)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PackageResponse(BaseModel):
    id: int
    package_name: str
    package_code: Optional[str]
    base_price: float
    included_room_type: Optional[str]
    included_stay_days: int
    included_services: Optional[List[str]] = None
    excess_per_day_charge: float
    description: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/packages", response_model=List[PackageResponse])
async def list_packages(
    active_only: bool = True,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    q = db.query(SurgeryPackage)
    if active_only:
        q = q.filter(SurgeryPackage.is_active == True)
    return q.order_by(SurgeryPackage.package_name).all()


@router.post("/packages", response_model=PackageResponse, status_code=status.HTTP_201_CREATED)
async def create_package(
    data: PackageCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_surgery_packages")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    if data.included_services:
        unknown = set(data.included_services) - PKG_INCLUDED_OPTIONS
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown included_services: {', '.join(unknown)}")
    pkg = SurgeryPackage(hospital_id=hospital.id, **data.model_dump())
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return pkg


@router.put("/packages/{package_id}", response_model=PackageResponse)
async def update_package(
    package_id: int,
    data: PackageUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_surgery_packages")),
    db: Session = Depends(get_db),
):
    pkg = db.query(SurgeryPackage).filter(SurgeryPackage.id == package_id).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    update = data.model_dump(exclude_unset=True)
    if "included_services" in update and update["included_services"]:
        unknown = set(update["included_services"]) - PKG_INCLUDED_OPTIONS
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown included_services: {', '.join(unknown)}")
    for k, v in update.items():
        setattr(pkg, k, v)
    db.commit()
    db.refresh(pkg)
    return pkg


@router.delete("/packages/{package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_package(
    package_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_surgery_packages")),
    db: Session = Depends(get_db),
):
    pkg = db.query(SurgeryPackage).filter(SurgeryPackage.id == package_id).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    pkg.is_active = False
    db.commit()


class ApplyPackageRequest(BaseModel):
    package_id: int
    agreed_price: Optional[float] = Field(default=None, ge=0)  # defaults to package.base_price
    notes: Optional[str] = None


class AdmissionPackageResponse(BaseModel):
    id: int
    admission_id: int
    package_id: int
    package_name: Optional[str] = None
    agreed_price: float
    applied_at: datetime
    applied_by_id: int
    notes: Optional[str]

    class Config:
        from_attributes = True


@router.post("/admissions/{admission_id}/package", response_model=AdmissionPackageResponse, status_code=status.HTTP_201_CREATED)
async def apply_package(
    admission_id: int,
    data: ApplyPackageRequest,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_packages")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    existing = db.query(AdmissionPackage).filter(AdmissionPackage.admission_id == admission_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Admission already has a package; remove it first")

    pkg = db.query(SurgeryPackage).filter(SurgeryPackage.id == data.package_id).first()
    if not pkg or not pkg.is_active:
        raise HTTPException(status_code=404, detail="Package not found or inactive")

    ap = AdmissionPackage(
        admission_id=admission_id,
        package_id=pkg.id,
        agreed_price=data.agreed_price if data.agreed_price is not None else float(pkg.base_price),
        applied_by_id=current_user.id,
        notes=data.notes,
    )
    db.add(ap)
    db.commit()
    db.refresh(ap)
    log_action(db, current_user, "apply_package", "inpatient", "AdmissionPackage", ap.id,
               f"Applied package '{pkg.package_name}' (Rs.{ap.agreed_price:,.2f}) to admission {admission.admission_number}")
    return {**{c.name: getattr(ap, c.name) for c in ap.__table__.columns}, "package_name": pkg.package_name}


@router.get("/admissions/{admission_id}/package", response_model=Optional[AdmissionPackageResponse])
async def get_admission_package(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_bill")),
    db: Session = Depends(get_db),
):
    ap = db.query(AdmissionPackage).filter(AdmissionPackage.admission_id == admission_id).first()
    if not ap:
        return None
    pkg = db.query(SurgeryPackage).filter(SurgeryPackage.id == ap.package_id).first()
    return {**{c.name: getattr(ap, c.name) for c in ap.__table__.columns}, "package_name": pkg.package_name if pkg else None}


@router.delete("/admissions/{admission_id}/package", status_code=status.HTTP_204_NO_CONTENT)
async def remove_admission_package(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_packages")),
    db: Session = Depends(get_db),
):
    ap = db.query(AdmissionPackage).filter(AdmissionPackage.admission_id == admission_id).first()
    if not ap:
        raise HTTPException(status_code=404, detail="No package on this admission")
    db.delete(ap)
    db.commit()


# ============================================================
# Ancillary Service Catalog (admin) + Per-admission charges
# ============================================================

ANCILLARY_CATEGORIES = {"imaging", "physiotherapy", "dialysis", "oxygen", "equipment", "consumable", "procedure", "other"}
ANCILLARY_UNITS = {"per_session", "per_hour", "per_day", "per_unit"}


class AncillaryServiceCreate(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=200)
    service_code: Optional[str] = Field(default=None, max_length=50)
    category: str = Field(..., pattern=f"^({'|'.join(ANCILLARY_CATEGORIES)})$")
    default_charge: float = Field(..., ge=0)
    charge_unit: str = Field(default="per_session", pattern=f"^({'|'.join(ANCILLARY_UNITS)})$")
    description: Optional[str] = None


class AncillaryServiceUpdate(BaseModel):
    service_name: Optional[str] = None
    service_code: Optional[str] = None
    category: Optional[str] = None
    default_charge: Optional[float] = Field(default=None, ge=0)
    charge_unit: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class AncillaryServiceResponse(BaseModel):
    id: int
    service_name: str
    service_code: Optional[str]
    category: str
    default_charge: float
    charge_unit: str
    description: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/ancillary-services", response_model=List[AncillaryServiceResponse])
async def list_ancillary_services(
    active_only: bool = True,
    category: Optional[str] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    q = db.query(AncillaryServiceCatalog)
    if active_only:
        q = q.filter(AncillaryServiceCatalog.is_active == True)
    if category:
        q = q.filter(AncillaryServiceCatalog.category == category)
    return q.order_by(AncillaryServiceCatalog.category, AncillaryServiceCatalog.service_name).all()


@router.post("/ancillary-services", response_model=AncillaryServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_ancillary_service(
    data: AncillaryServiceCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_ancillary_catalog")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    svc = AncillaryServiceCatalog(hospital_id=hospital.id, **data.model_dump())
    db.add(svc)
    db.commit()
    db.refresh(svc)
    return svc


@router.put("/ancillary-services/{service_id}", response_model=AncillaryServiceResponse)
async def update_ancillary_service(
    service_id: int,
    data: AncillaryServiceUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_ancillary_catalog")),
    db: Session = Depends(get_db),
):
    svc = db.query(AncillaryServiceCatalog).filter(AncillaryServiceCatalog.id == service_id).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(svc, k, v)
    db.commit()
    db.refresh(svc)
    return svc


@router.delete("/ancillary-services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ancillary_service(
    service_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_ancillary_catalog")),
    db: Session = Depends(get_db),
):
    svc = db.query(AncillaryServiceCatalog).filter(AncillaryServiceCatalog.id == service_id).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    svc.is_active = False  # soft-delete to preserve historical charges
    db.commit()


# ============================================================
# Procedure Catalog (admin) — used by OT scheduling
# ============================================================

class ProcedureCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    default_rate: float = Field(..., ge=0)
    description: Optional[str] = None


class ProcedureUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    default_rate: Optional[float] = Field(default=None, ge=0)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class ProcedureResponse(BaseModel):
    id: int
    name: str
    default_rate: float
    description: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/procedures", response_model=List[ProcedureResponse])
async def list_procedures(
    active_only: bool = True,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_procedures")),
    db: Session = Depends(get_db),
):
    q = db.query(Procedure)
    if active_only:
        q = q.filter(Procedure.is_active == True)
    return q.order_by(Procedure.name).all()


@router.post("/procedures", response_model=ProcedureResponse, status_code=status.HTTP_201_CREATED)
async def create_procedure(
    data: ProcedureCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_procedures")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    # Reject duplicate names (catalog should be unique per hospital)
    existing = db.query(Procedure).filter(
        Procedure.hospital_id == hospital.id,
        Procedure.name == data.name,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Procedure '{data.name}' already exists")
    proc = Procedure(hospital_id=hospital.id, **data.model_dump())
    db.add(proc)
    db.commit()
    db.refresh(proc)
    return proc


@router.put("/procedures/{procedure_id}", response_model=ProcedureResponse)
async def update_procedure(
    procedure_id: int,
    data: ProcedureUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_procedures")),
    db: Session = Depends(get_db),
):
    proc = db.query(Procedure).filter(Procedure.id == procedure_id).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procedure not found")
    payload = data.model_dump(exclude_unset=True)
    new_name = payload.get("name")
    if new_name and new_name != proc.name:
        clash = db.query(Procedure).filter(
            Procedure.hospital_id == proc.hospital_id,
            Procedure.name == new_name,
            Procedure.id != procedure_id,
        ).first()
        if clash:
            raise HTTPException(status_code=400, detail=f"Procedure '{new_name}' already exists")
    for k, v in payload.items():
        setattr(proc, k, v)
    db.commit()
    db.refresh(proc)
    return proc


@router.delete("/procedures/{procedure_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_procedure(
    procedure_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_procedures")),
    db: Session = Depends(get_db),
):
    proc = db.query(Procedure).filter(Procedure.id == procedure_id).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procedure not found")
    proc.is_active = False  # soft-delete to preserve historical OT references
    db.commit()


# --- Per-admission ancillary charges ---

class AncillaryChargeCreate(BaseModel):
    service_id: int
    quantity: float = Field(default=1.0, gt=0)
    unit_price: Optional[float] = Field(default=None, ge=0)  # falls back to service.default_charge
    notes: Optional[str] = None
    performed_by_id: Optional[int] = None
    charged_at: Optional[datetime] = None


class AncillaryChargeUpdate(BaseModel):
    quantity: Optional[float] = Field(default=None, gt=0)
    unit_price: Optional[float] = Field(default=None, ge=0)
    notes: Optional[str] = None


class AncillaryChargeResponse(BaseModel):
    id: int
    admission_id: int
    service_id: int
    service_name: Optional[str] = None
    category: Optional[str] = None
    quantity: float
    unit_price: float
    total_amount: float
    notes: Optional[str]
    charged_at: datetime
    performed_by_id: Optional[int]
    performed_by_name: Optional[str] = None
    billed: bool
    bill_id: Optional[int]

    class Config:
        from_attributes = True


def _ancillary_to_response(c: AdmissionAncillaryCharge, db: Session) -> dict:
    svc = db.query(AncillaryServiceCatalog).filter(AncillaryServiceCatalog.id == c.service_id).first()
    perf = db.query(User).filter(User.id == c.performed_by_id).first() if c.performed_by_id else None
    return {
        **{col.name: getattr(c, col.name) for col in c.__table__.columns},
        "service_name": svc.service_name if svc else None,
        "category": svc.category if svc else None,
        "performed_by_name": f"{perf.first_name} {perf.last_name}" if perf else None,
    }


@router.post("/admissions/{admission_id}/ancillary-charges", response_model=AncillaryChargeResponse, status_code=status.HTTP_201_CREATED)
async def create_ancillary_charge(
    admission_id: int,
    data: AncillaryChargeCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_ancillary_charges")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    svc = db.query(AncillaryServiceCatalog).filter(
        AncillaryServiceCatalog.id == data.service_id,
        AncillaryServiceCatalog.is_active == True,
    ).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Ancillary service not found or inactive")

    unit_price = data.unit_price if data.unit_price is not None else float(svc.default_charge)
    total = round(data.quantity * unit_price, 2)

    charge = AdmissionAncillaryCharge(
        admission_id=admission_id,
        service_id=svc.id,
        quantity=data.quantity,
        unit_price=unit_price,
        total_amount=total,
        notes=data.notes,
        performed_by_id=data.performed_by_id or current_user.id,
        charged_at=data.charged_at or datetime.utcnow(),
        hospital_id=hospital.id,
        created_by_id=current_user.id,
    )
    db.add(charge)
    db.commit()
    db.refresh(charge)
    log_action(db, current_user, "create_ancillary_charge", "inpatient", "AdmissionAncillaryCharge", charge.id,
               f"Added ancillary charge {svc.service_name} (Rs.{total:,.2f}) to admission {admission.admission_number}",
               {"service_id": svc.id, "amount": total})
    return _ancillary_to_response(charge, db)


@router.get("/admissions/{admission_id}/ancillary-charges", response_model=List[AncillaryChargeResponse])
async def list_ancillary_charges(
    admission_id: int,
    unbilled_only: bool = False,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_bill")),
    db: Session = Depends(get_db),
):
    q = db.query(AdmissionAncillaryCharge).filter(AdmissionAncillaryCharge.admission_id == admission_id)
    if unbilled_only:
        q = q.filter(AdmissionAncillaryCharge.billed == False)
    rows = q.order_by(AdmissionAncillaryCharge.charged_at.desc()).all()
    return [_ancillary_to_response(c, db) for c in rows]


@router.put("/ancillary-charges/{charge_id}", response_model=AncillaryChargeResponse)
async def update_ancillary_charge(
    charge_id: int,
    data: AncillaryChargeUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_ancillary_charges")),
    db: Session = Depends(get_db),
):
    c = db.query(AdmissionAncillaryCharge).filter(AdmissionAncillaryCharge.id == charge_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Charge not found")
    if c.billed:
        raise HTTPException(status_code=409, detail="Charge already billed; cannot modify")

    update = data.model_dump(exclude_unset=True)
    for k, v in update.items():
        setattr(c, k, v)
    # Recompute total
    c.total_amount = round((c.quantity or 0) * (c.unit_price or 0), 2)
    db.commit()
    db.refresh(c)
    return _ancillary_to_response(c, db)


@router.delete("/ancillary-charges/{charge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ancillary_charge(
    charge_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_ancillary_charges")),
    db: Session = Depends(get_db),
):
    c = db.query(AdmissionAncillaryCharge).filter(AdmissionAncillaryCharge.id == charge_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Charge not found")
    if c.billed:
        raise HTTPException(status_code=409, detail="Cannot delete a charge already on a bill")
    db.delete(c)
    db.commit()


@router.get("/deposits/{deposit_id}/receipt/pdf")
async def get_deposit_receipt_pdf(
    deposit_id: int,
    include_header: bool = True,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_bill")),
    db: Session = Depends(get_db),
):
    d = db.query(AdmissionDeposit).filter(AdmissionDeposit.id == deposit_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Deposit not found")
    admission = db.query(Admission).filter(Admission.id == d.admission_id).first()
    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first() if admission else None
    hospital = _get_hospital(db, current_user)

    deposit_data = {
        "deposit_number": d.deposit_number,
        "amount": float(d.amount),
        "deposit_type": d.deposit_type,
        "payment_method": d.payment_method,
        "reference_number": d.reference_number,
        "notes": d.notes,
        "received_at": d.received_at.strftime("%d/%m/%Y %H:%M") if d.received_at else "",
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "—",
        "patient_id": patient.patient_id if patient else "—",
        "admission_number": admission.admission_number if admission else "—",
    }
    hospital_info = {
        "name": hospital.name,
        "address": hospital.address or "",
        "phone": hospital.phone or "",
        "email": hospital.email or "",
        "logo_url": getattr(hospital, "logo_url", "") or "",
        "hospital_subname": getattr(hospital, "hospital_subname", "") or "",
    }
    pdf_buffer = pdf_service.generate_deposit_receipt_pdf(deposit_data, hospital_info, include_header=include_header)
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="receipt-{d.deposit_number}.pdf"'},
    )


# ============================================================
# Phase 3 — Operational Workflow
# ============================================================

from app.models.inpatient import (  # noqa: E402  (kept local to avoid circular issues at top)
    BedTransferHistory, BedTurnoverLog, BedReservation, NurseAssignment, NurseShiftRoster,
    ConsentTemplate, Consent, Incident,
    FluidBalance, CriticalLabAlert,
)
from app.models.lab import LabTestParameter  # noqa: E402


# ---------- Bed Transfer History (list + inter-ward transfer with accept flow) ----------

class TransferHistoryResponse(BaseModel):
    id: int
    admission_id: int
    from_room_id: Optional[int]
    from_room_number: Optional[str] = None
    from_bed_id: Optional[int]
    from_bed_label: Optional[str] = None
    to_room_id: int
    to_room_number: Optional[str] = None
    to_bed_id: Optional[int]
    to_bed_label: Optional[str] = None
    transfer_type: str
    reason: str
    transfer_note: Optional[str]
    status: str
    transferred_at: datetime
    transferred_by_id: int
    transferred_by_name: Optional[str] = None
    accepting_doctor_id: Optional[int]
    accepting_nurse_id: Optional[int]
    accepted_at: Optional[datetime]

    class Config:
        from_attributes = True


def _transfer_to_response(t: BedTransferHistory, db: Session) -> dict:
    from_room = db.query(RoomManagement).filter(RoomManagement.id == t.from_room_id).first() if t.from_room_id else None
    to_room = db.query(RoomManagement).filter(RoomManagement.id == t.to_room_id).first()
    from_bed = db.query(Bed).filter(Bed.id == t.from_bed_id).first() if t.from_bed_id else None
    to_bed = db.query(Bed).filter(Bed.id == t.to_bed_id).first() if t.to_bed_id else None
    tb = db.query(User).filter(User.id == t.transferred_by_id).first()
    return {
        **{c.name: getattr(t, c.name) for c in t.__table__.columns},
        "from_room_number": from_room.room_number if from_room else None,
        "to_room_number": to_room.room_number if to_room else None,
        "from_bed_label": from_bed.bed_label if from_bed else None,
        "to_bed_label": to_bed.bed_label if to_bed else None,
        "transferred_by_name": f"{tb.first_name} {tb.last_name}" if tb else None,
    }


@router.get("/admissions/{admission_id}/transfers", response_model=List[TransferHistoryResponse])
async def list_admission_transfers(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    rows = db.query(BedTransferHistory).filter(
        BedTransferHistory.admission_id == admission_id
    ).order_by(BedTransferHistory.transferred_at.desc()).all()
    return [_transfer_to_response(t, db) for t in rows]


class WardTransferRequest(BaseModel):
    to_room_id: int
    to_bed_id: Optional[int] = None
    reason: str = Field(..., min_length=1)
    transfer_note: str = Field(..., min_length=1)
    accepting_doctor_id: Optional[int] = None
    accepting_nurse_id: Optional[int] = None


@router.post("/admissions/{admission_id}/transfer-ward", response_model=TransferHistoryResponse, status_code=status.HTTP_201_CREATED)
async def initiate_ward_transfer(
    admission_id: int,
    data: WardTransferRequest,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "initiate_ward_transfer")),
    db: Session = Depends(get_db),
):
    """Initiate a structured inter-ward transfer in a pending state. A nurse or
    doctor on the receiving ward must accept it before the bed/room actually
    changes on the admission."""
    hospital = _get_hospital(db, current_user)
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status != "admitted":
        raise HTTPException(status_code=400, detail="Patient is not currently admitted")

    new_room = db.query(RoomManagement).filter(RoomManagement.id == data.to_room_id).first()
    if not new_room or not new_room.is_active:
        raise HTTPException(status_code=404, detail="Target room not found")

    # Reject if a pending transfer already exists
    pending = db.query(BedTransferHistory).filter(
        BedTransferHistory.admission_id == admission_id,
        BedTransferHistory.status == "pending",
    ).first()
    if pending:
        raise HTTPException(status_code=409, detail="Another transfer is already pending acceptance")

    t = BedTransferHistory(
        admission_id=admission_id,
        from_room_id=admission.room_id,
        from_bed_id=admission.bed_id,
        to_room_id=data.to_room_id,
        to_bed_id=data.to_bed_id,
        transfer_type="ward_change",
        reason=data.reason,
        transfer_note=data.transfer_note,
        status="pending",
        transferred_by_id=current_user.id,
        accepting_doctor_id=data.accepting_doctor_id,
        accepting_nurse_id=data.accepting_nurse_id,
        hospital_id=hospital.id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    log_action(db, current_user, "initiate_ward_transfer", "inpatient", "BedTransferHistory", t.id,
               f"Ward transfer pending for admission {admission.admission_number}",
               {"to_room_id": data.to_room_id, "reason": data.reason})
    return _transfer_to_response(t, db)


@router.patch("/transfers/{transfer_id}/accept", response_model=TransferHistoryResponse)
async def accept_ward_transfer(
    transfer_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "accept_ward_transfer")),
    db: Session = Depends(get_db),
):
    """Accepting staff on the receiving ward confirms the transfer. This is when
    the admission is actually moved (bed/room change + availability updates)."""
    t = db.query(BedTransferHistory).filter(BedTransferHistory.id == transfer_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if t.status != "pending":
        raise HTTPException(status_code=409, detail=f"Transfer is in '{t.status}' state")

    admission = db.query(Admission).filter(Admission.id == t.admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission no longer exists")

    new_room = db.query(RoomManagement).filter(RoomManagement.id == t.to_room_id).first()
    if not new_room or new_room.available_beds <= 0:
        raise HTTPException(status_code=400, detail="No beds available in target room")

    # Move bed accounting
    old_room = db.query(RoomManagement).filter(RoomManagement.id == admission.room_id).first()
    if old_room and t.to_room_id != admission.room_id:
        old_room.available_beds += 1
        old_room.is_occupied = old_room.available_beds == 0
        new_room.available_beds -= 1
        new_room.is_occupied = new_room.available_beds == 0

    admission.room_id = t.to_room_id
    if t.to_bed_id:
        admission.bed_id = t.to_bed_id
    t.status = "accepted"
    t.accepted_at = datetime.utcnow()
    # If caller didn't pre-specify, record the accepting user based on their role
    if not t.accepting_doctor_id and not t.accepting_nurse_id:
        if "doctor" in (current_user.role_names or []):
            t.accepting_doctor_id = current_user.id
        else:
            t.accepting_nurse_id = current_user.id
    db.commit()
    db.refresh(t)
    log_action(db, current_user, "accept_ward_transfer", "inpatient", "BedTransferHistory", t.id,
               f"Accepted ward transfer for admission {admission.admission_number}")
    return _transfer_to_response(t, db)


@router.patch("/transfers/{transfer_id}/cancel", response_model=TransferHistoryResponse)
async def cancel_pending_transfer(
    transfer_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "accept_ward_transfer")),
    db: Session = Depends(get_db),
):
    t = db.query(BedTransferHistory).filter(BedTransferHistory.id == transfer_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transfer not found")
    if t.status != "pending":
        raise HTTPException(status_code=409, detail="Only pending transfers can be cancelled")
    t.status = "cancelled"
    db.commit()
    db.refresh(t)
    return _transfer_to_response(t, db)


@router.get("/transfers/pending", response_model=List[TransferHistoryResponse])
async def list_pending_transfers(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """Transfers awaiting acceptance — visible on the receiving ward dashboard."""
    rows = db.query(BedTransferHistory).filter(
        BedTransferHistory.status == "pending"
    ).order_by(BedTransferHistory.transferred_at.desc()).all()
    return [_transfer_to_response(t, db) for t in rows]


# ---------- Housekeeping: bed status + turnover log ----------

VALID_BED_STATUSES = {"available", "occupied", "maintenance", "cleaning", "dirty", "out_of_service"}


class BedStatusChange(BaseModel):
    status: str = Field(..., pattern=f"^({'|'.join(VALID_BED_STATUSES)})$")
    notes: Optional[str] = None


class TurnoverLogResponse(BaseModel):
    id: int
    bed_id: int
    status_from: str
    status_to: str
    changed_at: datetime
    changed_by_id: Optional[int]
    changed_by_name: Optional[str] = None
    notes: Optional[str]

    class Config:
        from_attributes = True


def _log_bed_status_change(db: Session, bed: Bed, new_status: str, user: User, notes: Optional[str] = None):
    if bed.status == new_status:
        return
    entry = BedTurnoverLog(
        bed_id=bed.id,
        status_from=bed.status or "available",
        status_to=new_status,
        changed_by_id=user.id if user else None,
        notes=notes,
    )
    db.add(entry)
    bed.status = new_status


@router.patch("/beds/{bed_id}/status")
async def change_bed_status(
    bed_id: int,
    data: BedStatusChange,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_housekeeping")),
    db: Session = Depends(get_db),
):
    bed = db.query(Bed).filter(Bed.id == bed_id).first()
    if not bed:
        raise HTTPException(status_code=404, detail="Bed not found")
    if bed.current_admission_id and data.status == "available":
        raise HTTPException(status_code=409, detail="Bed is still linked to an active admission")
    old = bed.status
    _log_bed_status_change(db, bed, data.status, current_user, data.notes)
    db.commit()
    db.refresh(bed)
    log_action(db, current_user, "change_bed_status", "inpatient", "Bed", bed.id,
               f"Bed {bed.bed_label} status: {old} → {data.status}")
    return {"bed_id": bed.id, "status": bed.status, "previous_status": old}


@router.get("/beds/needs-cleaning")
async def beds_needing_cleaning(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_housekeeping")),
    db: Session = Depends(get_db),
):
    rows = db.query(Bed).filter(Bed.status.in_(["dirty", "cleaning"])).all()
    result = []
    for b in rows:
        room = db.query(RoomManagement).filter(RoomManagement.id == b.room_id).first()
        # Most recent status change
        last_log = db.query(BedTurnoverLog).filter(BedTurnoverLog.bed_id == b.id).order_by(BedTurnoverLog.changed_at.desc()).first()
        result.append({
            "bed_id": b.id,
            "bed_label": b.bed_label,
            "room_id": b.room_id,
            "room_number": room.room_number if room else None,
            "status": b.status,
            "since": last_log.changed_at.isoformat() if last_log else None,
        })
    return result


@router.get("/beds/turnover-stats")
async def bed_turnover_stats(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """Rough average turnover: cleaning → available transitions."""
    logs = db.query(BedTurnoverLog).filter(
        BedTurnoverLog.status_from == "cleaning",
        BedTurnoverLog.status_to == "available",
    ).order_by(BedTurnoverLog.bed_id, BedTurnoverLog.changed_at).all()

    # Pair each cleaning→available with its preceding *→cleaning for the same bed
    durations = []
    for row in logs:
        prev = db.query(BedTurnoverLog).filter(
            BedTurnoverLog.bed_id == row.bed_id,
            BedTurnoverLog.status_to == "cleaning",
            BedTurnoverLog.changed_at < row.changed_at,
        ).order_by(BedTurnoverLog.changed_at.desc()).first()
        if prev:
            delta_min = (row.changed_at - prev.changed_at).total_seconds() / 60
            durations.append(delta_min)

    avg = round(sum(durations) / len(durations), 1) if durations else 0
    return {
        "turnover_count": len(durations),
        "avg_minutes": avg,
        "beds_currently_dirty": db.query(Bed).filter(Bed.status == "dirty").count(),
        "beds_currently_cleaning": db.query(Bed).filter(Bed.status == "cleaning").count(),
    }


@router.get("/beds/{bed_id}/turnover-log", response_model=List[TurnoverLogResponse])
async def bed_turnover_log(
    bed_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    rows = db.query(BedTurnoverLog).filter(BedTurnoverLog.bed_id == bed_id).order_by(BedTurnoverLog.changed_at.desc()).all()
    result = []
    for r in rows:
        u = db.query(User).filter(User.id == r.changed_by_id).first() if r.changed_by_id else None
        result.append({
            **{c.name: getattr(r, c.name) for c in r.__table__.columns},
            "changed_by_name": f"{u.first_name} {u.last_name}" if u else None,
        })
    return result


# ---------- Bed Reservations ----------

class ReservationCreate(BaseModel):
    bed_id: Optional[int] = None
    room_id: Optional[int] = None
    room_type: Optional[str] = Field(default=None, pattern="^(general|private|icu|emergency|operation)$")
    patient_id: Optional[int] = None
    patient_name_cache: Optional[str] = Field(default=None, max_length=200)
    reserved_for_date: datetime
    reservation_reason: str = Field(default="elective", pattern="^(elective|post_op|transfer|other)$")
    notes: Optional[str] = None


class ReservationResponse(BaseModel):
    id: int
    bed_id: Optional[int]
    bed_label: Optional[str] = None
    room_id: Optional[int]
    room_number: Optional[str] = None
    room_type: Optional[str]
    patient_id: Optional[int]
    patient_name: Optional[str] = None
    reserved_for_date: datetime
    reservation_reason: str
    status: str
    notes: Optional[str]
    related_admission_id: Optional[int]
    reserved_by_id: int
    reserved_by_name: Optional[str] = None
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


def _reservation_to_response(r: BedReservation, db: Session) -> dict:
    patient = db.query(Patient).filter(Patient.id == r.patient_id).first() if r.patient_id else None
    room = db.query(RoomManagement).filter(RoomManagement.id == r.room_id).first() if r.room_id else None
    bed = db.query(Bed).filter(Bed.id == r.bed_id).first() if r.bed_id else None
    rb = db.query(User).filter(User.id == r.reserved_by_id).first()
    patient_name = None
    if patient:
        patient_name = f"{patient.first_name} {patient.last_name}"
    elif r.patient_name_cache:
        patient_name = r.patient_name_cache
    return {
        **{c.name: getattr(r, c.name) for c in r.__table__.columns},
        "bed_label": bed.bed_label if bed else None,
        "room_number": room.room_number if room else None,
        "patient_name": patient_name,
        "reserved_by_name": f"{rb.first_name} {rb.last_name}" if rb else None,
    }


@router.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    data: ReservationCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_reservations")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    if not (data.bed_id or data.room_id or data.room_type):
        raise HTTPException(status_code=400, detail="Provide bed_id, room_id, or room_type")

    r = BedReservation(
        bed_id=data.bed_id,
        room_id=data.room_id,
        room_type=data.room_type,
        patient_id=data.patient_id,
        patient_name_cache=data.patient_name_cache,
        reserved_for_date=data.reserved_for_date,
        reservation_reason=data.reservation_reason,
        notes=data.notes,
        reserved_by_id=current_user.id,
        hospital_id=hospital.id,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return _reservation_to_response(r, db)


@router.get("/reservations", response_model=List[ReservationResponse])
async def list_reservations(
    active_only: bool = True,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_reservations")),
    db: Session = Depends(get_db),
):
    q = db.query(BedReservation)
    if active_only:
        q = q.filter(BedReservation.status == "active")
    if from_date:
        q = q.filter(BedReservation.reserved_for_date >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        from datetime import timedelta
        q = q.filter(BedReservation.reserved_for_date < datetime.combine(to_date, datetime.min.time()) + timedelta(days=1))
    rows = q.order_by(BedReservation.reserved_for_date.asc()).all()
    return [_reservation_to_response(r, db) for r in rows]


@router.patch("/reservations/{reservation_id}/cancel", response_model=ReservationResponse)
async def cancel_reservation(
    reservation_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_reservations")),
    db: Session = Depends(get_db),
):
    r = db.query(BedReservation).filter(BedReservation.id == reservation_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if r.status != "active":
        raise HTTPException(status_code=409, detail=f"Reservation is in '{r.status}' state")
    r.status = "cancelled"
    db.commit()
    db.refresh(r)
    return _reservation_to_response(r, db)


class ReservationConvertRequest(BaseModel):
    admitting_doctor_id: int
    admission_type: str = Field(..., pattern="^(emergency|elective|transfer)$")
    admission_reason: Optional[str] = None
    condition_on_admission: Optional[str] = Field(default=None, pattern="^(stable|critical|serious)$")


@router.post("/reservations/{reservation_id}/convert")
async def convert_reservation_to_admission(
    reservation_id: int,
    data: ReservationConvertRequest,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_reservations")),
    db: Session = Depends(get_db),
):
    r = db.query(BedReservation).filter(BedReservation.id == reservation_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if r.status != "active":
        raise HTTPException(status_code=409, detail="Reservation is not active")
    if not r.patient_id:
        raise HTTPException(status_code=400, detail="Reservation has no linked patient")

    # Resolve the room: prefer specific bed → specific room → any room of the matching type with availability
    room = None
    bed = None
    if r.bed_id:
        bed = db.query(Bed).filter(Bed.id == r.bed_id).first()
        if bed:
            room = db.query(RoomManagement).filter(RoomManagement.id == bed.room_id).first()
    if not room and r.room_id:
        room = db.query(RoomManagement).filter(RoomManagement.id == r.room_id).first()
    if not room and r.room_type:
        room = db.query(RoomManagement).filter(
            RoomManagement.room_type == r.room_type,
            RoomManagement.is_active == True,
            RoomManagement.available_beds > 0,
        ).order_by(RoomManagement.available_beds.desc()).first()
    if not room:
        raise HTTPException(status_code=400, detail="No matching room available")
    if room.available_beds <= 0:
        raise HTTPException(status_code=400, detail="Reserved room has no available beds")

    # Reuse the create_admission machinery minus the patient-already-admitted check? Just create directly
    hospital = _get_hospital(db, current_user)
    now = datetime.now()
    admission_number = f"ADM{now.strftime('%Y%m%d%H%M%S')}"

    active = db.query(Admission).filter(
        Admission.patient_id == r.patient_id,
        Admission.status == "admitted",
    ).first()
    if active:
        raise HTTPException(status_code=400, detail="Patient already has an active admission")

    admission = Admission(
        admission_number=admission_number,
        patient_id=r.patient_id,
        admitting_doctor_id=data.admitting_doctor_id,
        room_id=room.id,
        bed_id=bed.id if bed else None,
        admission_type=data.admission_type,
        admission_reason=data.admission_reason,
        condition_on_admission=data.condition_on_admission,
        status="admitted",
    )
    db.add(admission)
    room.available_beds -= 1
    if room.available_beds == 0:
        room.is_occupied = True
    if bed:
        bed.status = "occupied"
        bed.current_admission_id = None  # will be set after flush
    db.flush()
    if bed:
        bed.current_admission_id = admission.id

    r.status = "converted"
    r.related_admission_id = admission.id
    db.commit()
    db.refresh(admission)
    log_action(db, current_user, "convert_reservation", "inpatient", "Admission", admission.id,
               f"Converted reservation #{r.id} to admission {admission_number}")
    return {
        "admission_id": admission.id,
        "admission_number": admission.admission_number,
        "reservation_id": r.id,
    }


# ---------- Nurse Assignments ----------

VALID_SHIFTS = {"morning", "afternoon", "night"}


class NurseAssignmentCreate(BaseModel):
    nurse_id: int
    shift: str = Field(..., pattern="^(morning|afternoon|night)$")
    assignment_date: Optional[date] = None
    is_primary: bool = False
    notes: Optional[str] = None


class NurseAssignmentResponse(BaseModel):
    id: int
    admission_id: int
    nurse_id: int
    nurse_name: Optional[str] = None
    shift: str
    assignment_date: datetime
    is_primary: bool
    notes: Optional[str]
    assigned_by_id: int
    assigned_by_name: Optional[str] = None
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


def _assignment_to_response(a: NurseAssignment, db: Session) -> dict:
    nurse = db.query(User).filter(User.id == a.nurse_id).first()
    assigner = db.query(User).filter(User.id == a.assigned_by_id).first()
    return {
        **{c.name: getattr(a, c.name) for c in a.__table__.columns},
        "nurse_name": f"{nurse.first_name} {nurse.last_name}" if nurse else None,
        "assigned_by_name": f"{assigner.first_name} {assigner.last_name}" if assigner else None,
    }


@router.post("/admissions/{admission_id}/assign-nurse", response_model=NurseAssignmentResponse, status_code=status.HTTP_201_CREATED)
async def assign_nurse(
    admission_id: int,
    data: NurseAssignmentCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "assign_nurses")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    nurse = db.query(User).filter(User.id == data.nurse_id).first()
    if not nurse:
        raise HTTPException(status_code=404, detail="Nurse not found")

    target_date = data.assignment_date or date.today()
    target_dt = datetime.combine(target_date, datetime.min.time())

    existing = db.query(NurseAssignment).filter(
        NurseAssignment.admission_id == admission_id,
        NurseAssignment.nurse_id == data.nurse_id,
        NurseAssignment.shift == data.shift,
        NurseAssignment.assignment_date == target_dt,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Nurse already assigned to this admission for that shift/date")

    # If is_primary, demote any other primary for same (admission, shift, date)
    if data.is_primary:
        db.query(NurseAssignment).filter(
            NurseAssignment.admission_id == admission_id,
            NurseAssignment.shift == data.shift,
            NurseAssignment.assignment_date == target_dt,
            NurseAssignment.is_primary == True,
        ).update({"is_primary": False})

    a = NurseAssignment(
        admission_id=admission_id,
        nurse_id=data.nurse_id,
        shift=data.shift,
        assignment_date=target_dt,
        is_primary=data.is_primary,
        notes=data.notes,
        assigned_by_id=current_user.id,
        hospital_id=hospital.id,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _assignment_to_response(a, db)


@router.get("/admissions/{admission_id}/nurse-assignments", response_model=List[NurseAssignmentResponse])
async def list_nurse_assignments(
    admission_id: int,
    assignment_date: Optional[date] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    q = db.query(NurseAssignment).filter(NurseAssignment.admission_id == admission_id)
    if assignment_date:
        q = q.filter(NurseAssignment.assignment_date == datetime.combine(assignment_date, datetime.min.time()))
    rows = q.order_by(NurseAssignment.assignment_date.desc(), NurseAssignment.shift).all()
    return [_assignment_to_response(a, db) for a in rows]


@router.delete("/nurse-assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_nurse_assignment(
    assignment_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "assign_nurses")),
    db: Session = Depends(get_db),
):
    a = db.query(NurseAssignment).filter(NurseAssignment.id == assignment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(a)
    db.commit()


@router.get("/nurses/my-patients")
async def my_assigned_patients(
    shift: Optional[str] = None,
    assignment_date: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Admissions currently assigned to the calling nurse for the given shift (defaults to today + any shift)."""
    target_date = assignment_date or date.today()
    target_dt = datetime.combine(target_date, datetime.min.time())

    q = db.query(NurseAssignment).filter(
        NurseAssignment.nurse_id == current_user.id,
        NurseAssignment.assignment_date == target_dt,
    )
    if shift:
        q = q.filter(NurseAssignment.shift == shift)
    rows = q.all()

    result = []
    for a in rows:
        admission = db.query(Admission).options(
            joinedload(Admission.patient),
            joinedload(Admission.room),
        ).filter(Admission.id == a.admission_id).first()
        if not admission or admission.status != "admitted":
            continue
        patient = admission.patient
        room = admission.room
        result.append({
            "admission_id": admission.id,
            "admission_number": admission.admission_number,
            "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
            "room_number": room.room_number if room else None,
            "room_type": room.room_type if room else None,
            "shift": a.shift,
            "is_primary": a.is_primary,
            "assignment_notes": a.notes,
        })
    return result


# ============================================================
# Phase 4 — Consent Management
# ============================================================

CONSENT_TYPES = {"surgical", "anaesthesia", "blood_transfusion", "high_risk_procedure", "general_treatment", "research"}


class ConsentTemplateCreate(BaseModel):
    consent_type: str = Field(..., pattern=f"^({'|'.join(CONSENT_TYPES)})$")
    template_name: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    language: str = Field(default="english", max_length=30)


class ConsentTemplateUpdate(BaseModel):
    consent_type: Optional[str] = None
    template_name: Optional[str] = None
    content: Optional[str] = None
    language: Optional[str] = None
    is_active: Optional[bool] = None


class ConsentTemplateResponse(BaseModel):
    id: int
    consent_type: str
    template_name: str
    content: str
    language: str
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/consent-templates", response_model=List[ConsentTemplateResponse])
async def list_consent_templates(
    active_only: bool = True,
    consent_type: Optional[str] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    q = db.query(ConsentTemplate)
    if active_only:
        q = q.filter(ConsentTemplate.is_active == True)
    if consent_type:
        q = q.filter(ConsentTemplate.consent_type == consent_type)
    return q.order_by(ConsentTemplate.consent_type, ConsentTemplate.template_name).all()


@router.post("/consent-templates", response_model=ConsentTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_consent_template(
    data: ConsentTemplateCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_consent_templates")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    t = ConsentTemplate(hospital_id=hospital.id, **data.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@router.put("/consent-templates/{template_id}", response_model=ConsentTemplateResponse)
async def update_consent_template(
    template_id: int,
    data: ConsentTemplateUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_consent_templates")),
    db: Session = Depends(get_db),
):
    t = db.query(ConsentTemplate).filter(ConsentTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/consent-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_consent_template(
    template_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_consent_templates")),
    db: Session = Depends(get_db),
):
    t = db.query(ConsentTemplate).filter(ConsentTemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    t.is_active = False
    db.commit()


# --- Consent records per admission ---

class ConsentCreate(BaseModel):
    consent_type: str = Field(..., pattern=f"^({'|'.join(CONSENT_TYPES)})$")
    template_id: Optional[int] = None
    procedure_name: Optional[str] = Field(default=None, max_length=200)
    doctor_id: Optional[int] = None
    risks_explained: Optional[str] = None
    language: str = Field(default="english", max_length=30)
    patient_signature: Optional[str] = None
    patient_signature_type: str = Field(default="typed", pattern="^(typed|drawn)$")
    signed_by: str = Field(default="patient", pattern="^(patient|guardian|proxy)$")
    guardian_name: Optional[str] = Field(default=None, max_length=200)
    guardian_relationship: Optional[str] = Field(default=None, max_length=100)
    witness_name: Optional[str] = Field(default=None, max_length=200)
    witness_signature: Optional[str] = None
    notes: Optional[str] = None


class ConsentWithdraw(BaseModel):
    withdrawal_reason: str = Field(..., min_length=1)


class ConsentResponse(BaseModel):
    id: int
    admission_id: int
    patient_id: int
    consent_type: str
    template_id: Optional[int]
    template_name: Optional[str] = None
    procedure_name: Optional[str]
    doctor_id: Optional[int]
    doctor_name: Optional[str] = None
    risks_explained: Optional[str]
    language: str
    patient_signature: Optional[str]
    patient_signature_type: str
    signed_by: str
    guardian_name: Optional[str]
    guardian_relationship: Optional[str]
    witness_name: Optional[str]
    signed_at: datetime
    withdrawn_at: Optional[datetime]
    withdrawal_reason: Optional[str]
    notes: Optional[str]

    class Config:
        from_attributes = True


def _consent_to_response(c: Consent, db: Session) -> dict:
    template = db.query(ConsentTemplate).filter(ConsentTemplate.id == c.template_id).first() if c.template_id else None
    doctor = db.query(User).filter(User.id == c.doctor_id).first() if c.doctor_id else None
    return {
        **{col.name: getattr(c, col.name) for col in c.__table__.columns},
        "template_name": template.template_name if template else None,
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else None,
    }


@router.post("/admissions/{admission_id}/consents", response_model=ConsentResponse, status_code=status.HTTP_201_CREATED)
async def create_consent(
    admission_id: int,
    data: ConsentCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_consent")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if data.template_id:
        t = db.query(ConsentTemplate).filter(ConsentTemplate.id == data.template_id).first()
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
    if data.signed_by in ("guardian", "proxy") and not data.guardian_name:
        raise HTTPException(status_code=400, detail="guardian_name required when signed_by is guardian or proxy")

    c = Consent(
        admission_id=admission_id,
        patient_id=admission.patient_id,
        hospital_id=hospital.id,
        created_by_id=current_user.id,
        **data.model_dump(),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    log_action(db, current_user, "create_consent", "inpatient", "Consent", c.id,
               f"Signed {data.consent_type} consent for admission {admission.admission_number}",
               {"consent_type": data.consent_type, "signed_by": data.signed_by})
    return _consent_to_response(c, db)


@router.get("/admissions/{admission_id}/consents", response_model=List[ConsentResponse])
async def list_admission_consents(
    admission_id: int,
    active_only: bool = False,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    q = db.query(Consent).filter(Consent.admission_id == admission_id)
    if active_only:
        q = q.filter(Consent.withdrawn_at.is_(None))
    rows = q.order_by(Consent.signed_at.desc()).all()
    return [_consent_to_response(c, db) for c in rows]


@router.post("/consents/{consent_id}/withdraw", response_model=ConsentResponse)
async def withdraw_consent(
    consent_id: int,
    data: ConsentWithdraw,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "withdraw_consent")),
    db: Session = Depends(get_db),
):
    c = db.query(Consent).filter(Consent.id == consent_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Consent not found")
    if c.withdrawn_at:
        raise HTTPException(status_code=409, detail="Consent already withdrawn")
    c.withdrawn_at = datetime.utcnow()
    c.withdrawal_reason = data.withdrawal_reason
    db.commit()
    db.refresh(c)
    log_action(db, current_user, "withdraw_consent", "inpatient", "Consent", c.id,
               f"Withdrew consent — reason: {data.withdrawal_reason}")
    return _consent_to_response(c, db)


@router.get("/consents/{consent_id}/pdf")
async def get_consent_pdf(
    consent_id: int,
    include_header: bool = True,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    c = db.query(Consent).filter(Consent.id == consent_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Consent not found")
    admission = db.query(Admission).filter(Admission.id == c.admission_id).first()
    patient = db.query(Patient).filter(Patient.id == c.patient_id).first()
    template = db.query(ConsentTemplate).filter(ConsentTemplate.id == c.template_id).first() if c.template_id else None
    doctor = db.query(User).filter(User.id == c.doctor_id).first() if c.doctor_id else None
    hospital = _get_hospital(db, current_user)

    consent_data = {
        "consent_type": c.consent_type,
        "template_content": template.content if template else "",
        "procedure_name": c.procedure_name,
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "",
        "risks_explained": c.risks_explained or "",
        "signed_by": c.signed_by,
        "guardian_name": c.guardian_name or "",
        "guardian_relationship": c.guardian_relationship or "",
        "patient_signature": c.patient_signature or "",
        "patient_signature_type": c.patient_signature_type,
        "witness_name": c.witness_name or "",
        "signed_at": c.signed_at.strftime("%d/%m/%Y %H:%M") if c.signed_at else "",
        "withdrawn_at": c.withdrawn_at.strftime("%d/%m/%Y %H:%M") if c.withdrawn_at else "",
        "withdrawal_reason": c.withdrawal_reason or "",
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "",
        "patient_id": patient.patient_id if patient else "",
        "admission_number": admission.admission_number if admission else "",
    }
    hospital_info = {
        "name": hospital.name,
        "address": hospital.address or "",
        "phone": hospital.phone or "",
        "email": hospital.email or "",
        "logo_url": getattr(hospital, "logo_url", "") or "",
        "hospital_subname": getattr(hospital, "hospital_subname", "") or "",
    }
    pdf_buffer = pdf_service.generate_consent_pdf(consent_data, hospital_info, include_header=include_header)
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="consent-{c.id}.pdf"'},
    )


# ============================================================
# Phase 4 — Incident Reporting
# ============================================================

INCIDENT_TYPES = {"fall", "medication_error", "pressure_ulcer", "needle_stick", "infection",
                  "equipment_failure", "documentation_error", "wrong_patient", "other"}
INCIDENT_SEVERITIES = {"low", "medium", "high", "critical"}
INCIDENT_STATUSES = {"reported", "investigating", "resolved", "closed"}


class IncidentCreate(BaseModel):
    incident_type: str = Field(..., pattern=f"^({'|'.join(INCIDENT_TYPES)})$")
    severity: str = Field(..., pattern=f"^({'|'.join(INCIDENT_SEVERITIES)})$")
    incident_date: datetime
    admission_id: Optional[int] = None
    patient_id: Optional[int] = None
    location: Optional[str] = Field(default=None, max_length=200)
    description: str = Field(..., min_length=1)
    immediate_action: Optional[str] = None
    witnessed_by: Optional[str] = Field(default=None, max_length=200)


class IncidentInvestigate(BaseModel):
    investigation_notes: Optional[str] = None
    root_cause: Optional[str] = None
    resolution: Optional[str] = None
    corrective_actions: Optional[str] = None
    preventive_measures: Optional[str] = None
    new_status: Optional[str] = Field(default=None, pattern=f"^({'|'.join(INCIDENT_STATUSES)})$")


class IncidentResponse(BaseModel):
    id: int
    admission_id: Optional[int]
    admission_number: Optional[str] = None
    patient_id: Optional[int]
    patient_name: Optional[str] = None
    incident_type: str
    severity: str
    incident_date: datetime
    location: Optional[str]
    description: str
    immediate_action: Optional[str]
    witnessed_by: Optional[str]
    status: str
    investigation_notes: Optional[str]
    root_cause: Optional[str]
    resolution: Optional[str]
    corrective_actions: Optional[str]
    preventive_measures: Optional[str]
    reported_by_id: int
    reported_by_name: Optional[str] = None
    investigated_by_id: Optional[int]
    closed_at: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


def _incident_to_response(i: Incident, db: Session) -> dict:
    reporter = db.query(User).filter(User.id == i.reported_by_id).first()
    patient = db.query(Patient).filter(Patient.id == i.patient_id).first() if i.patient_id else None
    admission = db.query(Admission).filter(Admission.id == i.admission_id).first() if i.admission_id else None
    return {
        **{c.name: getattr(i, c.name) for c in i.__table__.columns},
        "reported_by_name": f"{reporter.first_name} {reporter.last_name}" if reporter else None,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
        "admission_number": admission.admission_number if admission else None,
    }


@router.post("/incidents", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def create_incident(
    data: IncidentCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "report_incident")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    incident = Incident(
        hospital_id=hospital.id,
        reported_by_id=current_user.id,
        status="reported",
        **data.model_dump(),
    )
    db.add(incident)
    db.commit()
    db.refresh(incident)
    log_action(db, current_user, "report_incident", "inpatient", "Incident", incident.id,
               f"Reported {data.severity} {data.incident_type} incident",
               {"type": data.incident_type, "severity": data.severity})
    return _incident_to_response(incident, db)


@router.get("/incidents", response_model=List[IncidentResponse])
async def list_incidents(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    incident_type: Optional[str] = None,
    severity: Optional[str] = None,
    admission_id: Optional[int] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    q = db.query(Incident)
    if status_filter:
        q = q.filter(Incident.status == status_filter)
    if incident_type:
        q = q.filter(Incident.incident_type == incident_type)
    if severity:
        q = q.filter(Incident.severity == severity)
    if admission_id:
        q = q.filter(Incident.admission_id == admission_id)
    rows = q.order_by(Incident.incident_date.desc()).all()
    return [_incident_to_response(i, db) for i in rows]


@router.get("/incidents/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    i = db.query(Incident).filter(Incident.id == incident_id).first()
    if not i:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _incident_to_response(i, db)


@router.post("/incidents/{incident_id}/investigate", response_model=IncidentResponse)
async def investigate_incident(
    incident_id: int,
    data: IncidentInvestigate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "investigate_incident")),
    db: Session = Depends(get_db),
):
    i = db.query(Incident).filter(Incident.id == incident_id).first()
    if not i:
        raise HTTPException(status_code=404, detail="Incident not found")

    # State machine enforcement
    current_status = i.status
    if data.new_status:
        allowed = {
            "reported": {"investigating", "resolved", "closed"},
            "investigating": {"resolved", "closed"},
            "resolved": {"closed", "investigating"},
            "closed": set(),
        }
        if data.new_status not in allowed.get(current_status, set()):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot transition from '{current_status}' to '{data.new_status}'",
            )
        i.status = data.new_status
        if data.new_status == "closed":
            i.closed_at = datetime.utcnow()
            i.closed_by_id = current_user.id

    for field in ("investigation_notes", "root_cause", "resolution",
                  "corrective_actions", "preventive_measures"):
        val = getattr(data, field, None)
        if val is not None:
            setattr(i, field, val)

    if i.status in ("investigating", "resolved"):
        i.investigated_by_id = current_user.id
    db.commit()
    db.refresh(i)
    return _incident_to_response(i, db)


@router.get("/incidents/reports/monthly")
async def incident_monthly_report(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """Count by type/severity/status for last 30 days."""
    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=30)
    rows = db.query(Incident).filter(Incident.incident_date >= cutoff).all()
    by_type = {}
    by_severity = {}
    by_status = {}
    for r in rows:
        by_type[r.incident_type] = by_type.get(r.incident_type, 0) + 1
        by_severity[r.severity] = by_severity.get(r.severity, 0) + 1
        by_status[r.status] = by_status.get(r.status, 0) + 1
    return {
        "total": len(rows),
        "by_type": by_type,
        "by_severity": by_severity,
        "by_status": by_status,
    }


# ============================================================
# Phase 4 — Readmission detection list
# ============================================================

@router.get("/reports/readmissions")
async def list_readmissions(
    within_days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_readmissions")),
    db: Session = Depends(get_db),
):
    rows = db.query(Admission).options(joinedload(Admission.patient)).filter(
        Admission.is_readmission == True,
        Admission.days_since_last_discharge <= within_days,
    ).order_by(Admission.admission_date.desc()).all()
    result = []
    for a in rows:
        result.append({
            "admission_id": a.id,
            "admission_number": a.admission_number,
            "patient_name": f"{a.patient.first_name} {a.patient.last_name}" if a.patient else None,
            "admission_date": a.admission_date.isoformat() if a.admission_date else None,
            "previous_admission_id": a.previous_admission_id,
            "days_since_last_discharge": a.days_since_last_discharge,
            "admission_reason": a.admission_reason,
            "status": a.status,
        })
    return result


# ============================================================
# Phase 4 — Mortality
# ============================================================

class MortalityUpdate(BaseModel):
    cause_of_death: Optional[str] = None
    time_of_death: Optional[datetime] = None
    death_certificate_number: Optional[str] = Field(default=None, max_length=100)
    mlc_required: Optional[bool] = None
    mlc_number: Optional[str] = Field(default=None, max_length=100)
    autopsy_done: Optional[bool] = None
    autopsy_findings: Optional[str] = None
    body_handed_over_to: Optional[str] = Field(default=None, max_length=200)
    body_handover_relationship: Optional[str] = Field(default=None, max_length=100)
    body_handover_time: Optional[datetime] = None
    body_handover_id_proof: Optional[str] = Field(default=None, max_length=200)


@router.put("/admissions/{admission_id}/discharge/mortality")
async def update_mortality_details(
    admission_id: int,
    data: MortalityUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_mortality")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).options(joinedload(Admission.discharge)).filter(
        Admission.id == admission_id
    ).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if not admission.discharge:
        raise HTTPException(status_code=404, detail="Admission has no discharge record")
    if admission.discharge.discharge_type != "death":
        raise HTTPException(status_code=400, detail="Mortality details only apply to deaths")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(admission.discharge, field, value)
    db.commit()
    db.refresh(admission.discharge)
    log_action(db, current_user, "record_mortality", "inpatient", "DischargeRecord", admission.discharge.id,
               f"Recorded mortality details for admission {admission.admission_number}")
    return {
        "discharge_id": admission.discharge.id,
        "cause_of_death": admission.discharge.cause_of_death,
        "mlc_required": admission.discharge.mlc_required,
        "death_certificate_number": admission.discharge.death_certificate_number,
    }


@router.get("/reports/mortality")
async def list_mortality(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_mortality")),
    db: Session = Depends(get_db),
):
    q = db.query(DischargeRecord).filter(DischargeRecord.discharge_type == "death").join(
        Admission, Admission.id == DischargeRecord.admission_id,
    )
    if from_date:
        q = q.filter(DischargeRecord.discharge_date >= datetime.combine(from_date, datetime.min.time()))
    if to_date:
        from datetime import timedelta
        q = q.filter(DischargeRecord.discharge_date < datetime.combine(to_date, datetime.min.time()) + timedelta(days=1))

    rows = q.order_by(DischargeRecord.discharge_date.desc()).all()
    result = []
    for d in rows:
        admission = db.query(Admission).filter(Admission.id == d.admission_id).first()
        patient = db.query(Patient).filter(Patient.id == admission.patient_id).first() if admission else None
        result.append({
            "discharge_id": d.id,
            "admission_id": d.admission_id,
            "admission_number": admission.admission_number if admission else None,
            "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
            "discharge_date": d.discharge_date.isoformat() if d.discharge_date else None,
            "time_of_death": d.time_of_death.isoformat() if d.time_of_death else None,
            "cause_of_death": d.cause_of_death,
            "mlc_required": d.mlc_required,
            "autopsy_done": d.autopsy_done,
            "death_certificate_number": d.death_certificate_number,
        })
    return result


@router.get("/admissions/{admission_id}/death-certificate/pdf")
async def death_certificate_pdf(
    admission_id: int,
    include_header: bool = True,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_mortality")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).options(joinedload(Admission.discharge)).filter(
        Admission.id == admission_id
    ).first()
    if not admission or not admission.discharge:
        raise HTTPException(status_code=404, detail="Admission or discharge not found")
    if admission.discharge.discharge_type != "death":
        raise HTTPException(status_code=400, detail="Not a mortality record")

    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first()
    doctor = db.query(User).filter(User.id == admission.admitting_doctor_id).first()
    hospital = _get_hospital(db, current_user)

    d = admission.discharge
    cert_data = {
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "",
        "patient_id": patient.patient_id if patient else "",
        "age": patient.age if patient and patient.age else "",
        "gender": patient.gender if patient else "",
        "admission_number": admission.admission_number,
        "admission_date": admission.admission_date.strftime("%d/%m/%Y") if admission.admission_date else "",
        "discharge_date": d.discharge_date.strftime("%d/%m/%Y") if d.discharge_date else "",
        "time_of_death": d.time_of_death.strftime("%d/%m/%Y %H:%M") if d.time_of_death else "",
        "cause_of_death": d.cause_of_death or "",
        "death_certificate_number": d.death_certificate_number or "",
        "mlc_required": d.mlc_required,
        "mlc_number": d.mlc_number or "",
        "autopsy_done": d.autopsy_done,
        "body_handed_over_to": d.body_handed_over_to or "",
        "body_handover_relationship": d.body_handover_relationship or "",
        "body_handover_time": d.body_handover_time.strftime("%d/%m/%Y %H:%M") if d.body_handover_time else "",
        "body_handover_id_proof": d.body_handover_id_proof or "",
        "treating_doctor": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "",
    }
    hospital_info = {
        "name": hospital.name,
        "address": hospital.address or "",
        "phone": hospital.phone or "",
        "email": hospital.email or "",
        "logo_url": getattr(hospital, "logo_url", "") or "",
        "hospital_subname": getattr(hospital, "hospital_subname", "") or "",
    }
    pdf_buffer = pdf_service.generate_death_certificate_pdf(cert_data, hospital_info, include_header=include_header)
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="death-cert-{admission.admission_number}.pdf"'},
    )


# ============================================================
# ICU: Intake/Output Fluid Balance
# ============================================================

IO_INTAKE_CATEGORIES = {"oral", "iv", "ng_tube", "blood_product", "irrigation", "other"}
IO_OUTPUT_CATEGORIES = {"urine", "drain", "ng_aspirate", "vomitus", "stool", "blood_loss", "other"}


class FluidBalanceCreate(BaseModel):
    io_type: str = Field(..., pattern="^(intake|output)$")
    category: str = Field(..., min_length=1, max_length=30)
    amount_ml: float = Field(..., gt=0)
    shift: str = Field(..., pattern="^(morning|afternoon|night)$")
    recorded_at: Optional[datetime] = None
    notes: Optional[str] = None


class FluidBalanceResponse(BaseModel):
    id: int
    admission_id: int
    patient_id: int
    recorded_by_id: int
    recorded_by_name: Optional[str] = None
    recorded_at: datetime
    shift: str
    io_type: str
    category: str
    amount_ml: float
    notes: Optional[str]

    class Config:
        from_attributes = True


def _io_to_response(e: FluidBalance, db: Session) -> dict:
    rec = db.query(User).filter(User.id == e.recorded_by_id).first()
    return {
        **{c.name: getattr(e, c.name) for c in e.__table__.columns},
        "recorded_by_name": f"{rec.first_name} {rec.last_name}" if rec else None,
    }


@router.post("/admissions/{admission_id}/io", response_model=FluidBalanceResponse, status_code=status.HTTP_201_CREATED)
async def record_io(
    admission_id: int,
    data: FluidBalanceCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_io")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    valid = IO_INTAKE_CATEGORIES if data.io_type == "intake" else IO_OUTPUT_CATEGORIES
    if data.category not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid category for {data.io_type}: {data.category}")

    entry = FluidBalance(
        admission_id=admission_id,
        patient_id=admission.patient_id,
        recorded_by_id=current_user.id,
        recorded_at=data.recorded_at or datetime.utcnow(),
        shift=data.shift,
        io_type=data.io_type,
        category=data.category,
        amount_ml=data.amount_ml,
        notes=data.notes,
        hospital_id=hospital.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _io_to_response(entry, db)


@router.get("/admissions/{admission_id}/io", response_model=List[FluidBalanceResponse])
async def list_io(
    admission_id: int,
    target_date: Optional[date] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_io")),
    db: Session = Depends(get_db),
):
    from datetime import timedelta
    q = db.query(FluidBalance).filter(FluidBalance.admission_id == admission_id)
    if target_date:
        day_start = datetime.combine(target_date, datetime.min.time())
        q = q.filter(
            FluidBalance.recorded_at >= day_start,
            FluidBalance.recorded_at < day_start + timedelta(days=1),
        )
    rows = q.order_by(FluidBalance.recorded_at.desc()).all()
    return [_io_to_response(r, db) for r in rows]


@router.get("/admissions/{admission_id}/io/balance")
async def io_balance_summary(
    admission_id: int,
    target_date: Optional[date] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_io")),
    db: Session = Depends(get_db),
):
    """Return per-shift totals and running 24h balance for the given date (defaults to today in UTC)."""
    from datetime import timedelta
    # Default: use UTC today, since I/O entries are stored with utcnow()
    day = target_date or datetime.utcnow().date()
    day_start = datetime.combine(day, datetime.min.time())
    rows = db.query(FluidBalance).filter(
        FluidBalance.admission_id == admission_id,
        FluidBalance.recorded_at >= day_start,
        FluidBalance.recorded_at < day_start + timedelta(days=1),
    ).all()

    shifts = {"morning": {"intake": 0.0, "output": 0.0}, "afternoon": {"intake": 0.0, "output": 0.0}, "night": {"intake": 0.0, "output": 0.0}}
    intake_by_cat = {}
    output_by_cat = {}
    for r in rows:
        shifts[r.shift][r.io_type] += float(r.amount_ml or 0)
        bucket = intake_by_cat if r.io_type == "intake" else output_by_cat
        bucket[r.category] = bucket.get(r.category, 0.0) + float(r.amount_ml or 0)

    total_intake = sum(s["intake"] for s in shifts.values())
    total_output = sum(s["output"] for s in shifts.values())
    return {
        "date": day.isoformat(),
        "by_shift": shifts,
        "intake_by_category": intake_by_cat,
        "output_by_category": output_by_cat,
        "total_intake_ml": total_intake,
        "total_output_ml": total_output,
        "net_balance_ml": round(total_intake - total_output, 2),  # positive = net intake (fluid retention)
        "entry_count": len(rows),
    }


@router.delete("/io/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_io(
    entry_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_io")),
    db: Session = Depends(get_db),
):
    e = db.query(FluidBalance).filter(FluidBalance.id == entry_id).first()
    if not e:
        raise HTTPException(status_code=404, detail="I/O entry not found")
    db.delete(e)
    db.commit()


# ============================================================
# ICU: Critical Lab Value Alerts
# ============================================================

class ThresholdUpdate(BaseModel):
    critical_low: Optional[float] = None
    critical_high: Optional[float] = None


class CriticalAlertAcknowledge(BaseModel):
    addressed_notes: Optional[str] = None
    mark_addressed: bool = False


class CriticalAlertResponse(BaseModel):
    id: int
    lab_order_id: int
    admission_id: Optional[int]
    patient_id: int
    patient_name: Optional[str] = None
    parameter_id: Optional[int]
    parameter_name: Optional[str]
    actual_value: Optional[str]
    critical_min: Optional[float]
    critical_max: Optional[float]
    severity: str
    status: str
    acknowledged_by_id: Optional[int]
    acknowledged_by_name: Optional[str] = None
    acknowledged_at: Optional[datetime]
    addressed_notes: Optional[str]
    created_at: Optional[datetime]

    class Config:
        from_attributes = True


def _alert_to_response(a: CriticalLabAlert, db: Session) -> dict:
    patient = db.query(Patient).filter(Patient.id == a.patient_id).first()
    ack = db.query(User).filter(User.id == a.acknowledged_by_id).first() if a.acknowledged_by_id else None
    return {
        **{c.name: getattr(a, c.name) for c in a.__table__.columns},
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
        "acknowledged_by_name": f"{ack.first_name} {ack.last_name}" if ack else None,
    }


def _try_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def scan_and_create_critical_alerts(db: Session, lab_order, results_by_parameter: dict, hospital_id: int):
    """Scan a set of {parameter_id: actual_value} results against LabTestParameter
    critical thresholds and create CriticalLabAlert rows for any breaches.
    Idempotent per (lab_order_id, parameter_id) — skips if an alert already exists."""
    for param_id, actual in (results_by_parameter or {}).items():
        if actual in (None, ""):
            continue
        param = db.query(LabTestParameter).filter(LabTestParameter.id == param_id).first()
        if not param:
            continue
        if param.critical_low is None and param.critical_high is None:
            continue
        val = _try_float(actual)
        if val is None:
            continue

        breach = None
        if param.critical_low is not None and val < param.critical_low:
            breach = "low"
        elif param.critical_high is not None and val > param.critical_high:
            breach = "high"
        if not breach:
            continue

        existing = db.query(CriticalLabAlert).filter(
            CriticalLabAlert.lab_order_id == lab_order.id,
            CriticalLabAlert.parameter_id == param_id,
        ).first()
        if existing:
            continue

        db.add(CriticalLabAlert(
            lab_order_id=lab_order.id,
            admission_id=getattr(lab_order, "admission_id", None),
            patient_id=lab_order.patient_id,
            parameter_id=param_id,
            parameter_name=param.parameter_name,
            actual_value=str(actual),
            critical_min=param.critical_low,
            critical_max=param.critical_high,
            severity="critical",
            status="new",
            hospital_id=hospital_id,
        ))


@router.post("/lab-parameters/{parameter_id}/critical-thresholds")
async def set_critical_thresholds(
    parameter_id: int,
    data: ThresholdUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "set_critical_thresholds")),
    db: Session = Depends(get_db),
):
    param = db.query(LabTestParameter).filter(LabTestParameter.id == parameter_id).first()
    if not param:
        raise HTTPException(status_code=404, detail="Parameter not found")
    if data.critical_low is not None:
        param.critical_low = data.critical_low
    if data.critical_high is not None:
        param.critical_high = data.critical_high
    db.commit()
    return {"parameter_id": param.id, "critical_low": param.critical_low, "critical_high": param.critical_high}


@router.post("/lab-orders/{lab_order_id}/scan-critical")
async def scan_lab_order_for_critical(
    lab_order_id: int,
    results: dict,  # {parameter_id: value}
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "order_labs")),
    db: Session = Depends(get_db),
):
    """Public helper — lab result entry can POST the parameter→value map here
    (or we wire it into the lab module directly later). Creates any missing
    critical-value alerts and returns the count."""
    lo = db.query(PatientLabOrder).filter(PatientLabOrder.id == lab_order_id).first()
    if not lo:
        raise HTTPException(status_code=404, detail="Lab order not found")
    hospital = _get_hospital(db, current_user)
    before = db.query(CriticalLabAlert).filter(CriticalLabAlert.lab_order_id == lab_order_id).count()
    # results may come with string keys from JSON — coerce
    coerced = {int(k): v for k, v in (results or {}).items()}
    scan_and_create_critical_alerts(db, lo, coerced, hospital.id)
    db.commit()
    after = db.query(CriticalLabAlert).filter(CriticalLabAlert.lab_order_id == lab_order_id).count()
    return {"new_alerts": after - before, "total_alerts": after}


@router.get("/critical-alerts", response_model=List[CriticalAlertResponse])
async def list_critical_alerts(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    admission_id: Optional[int] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    q = db.query(CriticalLabAlert)
    if status_filter:
        q = q.filter(CriticalLabAlert.status == status_filter)
    if admission_id:
        q = q.filter(CriticalLabAlert.admission_id == admission_id)
    rows = q.order_by(CriticalLabAlert.created_at.desc()).all()
    return [_alert_to_response(a, db) for a in rows]


@router.patch("/critical-alerts/{alert_id}/acknowledge", response_model=CriticalAlertResponse)
async def acknowledge_critical_alert(
    alert_id: int,
    data: CriticalAlertAcknowledge,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "acknowledge_critical_alert")),
    db: Session = Depends(get_db),
):
    a = db.query(CriticalLabAlert).filter(CriticalLabAlert.id == alert_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Alert not found")
    if a.status in ("addressed",):
        raise HTTPException(status_code=409, detail="Alert already addressed")
    a.acknowledged_by_id = current_user.id
    a.acknowledged_at = datetime.utcnow()
    if data.addressed_notes:
        a.addressed_notes = data.addressed_notes
    a.status = "addressed" if data.mark_addressed else "acknowledged"
    db.commit()
    db.refresh(a)
    return _alert_to_response(a, db)


# ============================================================
# Nurse Shift Roster (duty schedule)
# ============================================================

ROSTER_STATUSES = {"working", "leave", "off", "on_call"}
# Nurses available to take on patient assignments are those rostered as 'working' or 'on_call'.
ASSIGNABLE_STATUSES = {"working", "on_call"}
# Default minimum staffing per shift (admin-configurable later if needed)
DEFAULT_MIN_PER_SHIFT = 2


class RosterEntryCreate(BaseModel):
    nurse_id: int
    roster_date: date
    shift: str = Field(..., pattern="^(morning|afternoon|night)$")
    status: str = Field(default="working", pattern="^(working|leave|off|on_call)$")
    ward: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None


class RosterEntryUpdate(BaseModel):
    status: Optional[str] = Field(default=None, pattern="^(working|leave|off|on_call)$")
    ward: Optional[str] = None
    notes: Optional[str] = None


class RosterBulkAssign(BaseModel):
    """Apply the same status across many nurses × dates × shifts in one shot."""
    nurse_ids: List[int] = Field(..., min_length=1)
    from_date: date
    to_date: date
    shifts: List[str] = Field(..., min_length=1)  # e.g. ["morning", "afternoon"]
    status: str = Field(default="working", pattern="^(working|leave|off|on_call)$")
    ward: Optional[str] = None
    notes: Optional[str] = None
    overwrite: bool = False  # if True, existing entries get replaced; else they're skipped


class RosterEntryResponse(BaseModel):
    id: int
    nurse_id: int
    nurse_name: Optional[str] = None
    roster_date: datetime
    shift: str
    status: str
    ward: Optional[str]
    notes: Optional[str]
    assigned_by_id: int
    assigned_by_name: Optional[str] = None
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


def _roster_to_response(r: NurseShiftRoster, db: Session) -> dict:
    nurse = db.query(User).filter(User.id == r.nurse_id).first()
    assigner = db.query(User).filter(User.id == r.assigned_by_id).first()
    return {
        **{c.name: getattr(r, c.name) for c in r.__table__.columns},
        "nurse_name": f"{nurse.first_name} {nurse.last_name}" if nurse else None,
        "assigned_by_name": f"{assigner.first_name} {assigner.last_name}" if assigner else None,
    }


@router.post("/roster", response_model=RosterEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_roster_entry(
    data: RosterEntryCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_roster")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    nurse = db.query(User).filter(User.id == data.nurse_id).first()
    if not nurse:
        raise HTTPException(status_code=404, detail="Nurse not found")

    target_dt = datetime.combine(data.roster_date, datetime.min.time())
    existing = db.query(NurseShiftRoster).filter(
        NurseShiftRoster.nurse_id == data.nurse_id,
        NurseShiftRoster.roster_date == target_dt,
        NurseShiftRoster.shift == data.shift,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"{nurse.first_name} {nurse.last_name} is already rostered for {data.shift} on {data.roster_date} as '{existing.status}'",
        )

    entry = NurseShiftRoster(
        nurse_id=data.nurse_id,
        roster_date=target_dt,
        shift=data.shift,
        status=data.status,
        ward=data.ward,
        notes=data.notes,
        assigned_by_id=current_user.id,
        hospital_id=hospital.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    log_action(db, current_user, "create_roster_entry", "inpatient", "NurseShiftRoster", entry.id,
               f"Roster: {nurse.first_name} {nurse.last_name} → {data.shift} on {data.roster_date} ({data.status})")
    return _roster_to_response(entry, db)


@router.post("/roster/bulk")
async def bulk_assign_roster(
    data: RosterBulkAssign,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_roster")),
    db: Session = Depends(get_db),
):
    """Apply a status across many nurses × dates × shifts in one call. Used for
    'all weekday morning shifts for these 5 nurses' style bulk roster planning."""
    hospital = _get_hospital(db, current_user)
    if data.from_date > data.to_date:
        raise HTTPException(status_code=400, detail="from_date must be <= to_date")
    invalid_shifts = [s for s in data.shifts if s not in {"morning", "afternoon", "night"}]
    if invalid_shifts:
        raise HTTPException(status_code=400, detail=f"Invalid shifts: {invalid_shifts}")

    # Validate nurses exist
    nurses = db.query(User).filter(User.id.in_(data.nurse_ids)).all()
    found_ids = {n.id for n in nurses}
    missing = [nid for nid in data.nurse_ids if nid not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"Nurses not found: {missing}")

    from datetime import timedelta
    created = 0
    skipped = 0
    overwritten = 0
    day = data.from_date
    while day <= data.to_date:
        target_dt = datetime.combine(day, datetime.min.time())
        for nurse_id in data.nurse_ids:
            for shift in data.shifts:
                existing = db.query(NurseShiftRoster).filter(
                    NurseShiftRoster.nurse_id == nurse_id,
                    NurseShiftRoster.roster_date == target_dt,
                    NurseShiftRoster.shift == shift,
                ).first()
                if existing:
                    if data.overwrite:
                        existing.status = data.status
                        existing.ward = data.ward
                        existing.notes = data.notes
                        existing.assigned_by_id = current_user.id
                        overwritten += 1
                    else:
                        skipped += 1
                    continue
                db.add(NurseShiftRoster(
                    nurse_id=nurse_id,
                    roster_date=target_dt,
                    shift=shift,
                    status=data.status,
                    ward=data.ward,
                    notes=data.notes,
                    assigned_by_id=current_user.id,
                    hospital_id=hospital.id,
                ))
                created += 1
        day = day + timedelta(days=1)

    db.commit()
    log_action(db, current_user, "bulk_roster_assign", "inpatient", "NurseShiftRoster", 0,
               f"Bulk roster: {len(data.nurse_ids)} nurses × {(data.to_date - data.from_date).days + 1} days × {len(data.shifts)} shifts → {created} created, {overwritten} overwritten, {skipped} skipped")
    return {"created": created, "overwritten": overwritten, "skipped": skipped}


@router.get("/roster", response_model=List[RosterEntryResponse])
async def list_roster_entries(
    from_date: date,
    to_date: date,
    nurse_id: Optional[int] = None,
    shift: Optional[str] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_roster")),
    db: Session = Depends(get_db),
):
    from datetime import timedelta
    if from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be <= to_date")
    q = db.query(NurseShiftRoster).filter(
        NurseShiftRoster.roster_date >= datetime.combine(from_date, datetime.min.time()),
        NurseShiftRoster.roster_date < datetime.combine(to_date, datetime.min.time()) + timedelta(days=1),
    )
    if nurse_id:
        q = q.filter(NurseShiftRoster.nurse_id == nurse_id)
    if shift:
        q = q.filter(NurseShiftRoster.shift == shift)
    if status_filter:
        q = q.filter(NurseShiftRoster.status == status_filter)
    rows = q.order_by(NurseShiftRoster.roster_date.asc(), NurseShiftRoster.shift, NurseShiftRoster.nurse_id).all()
    return [_roster_to_response(r, db) for r in rows]


@router.get("/roster/grid")
async def roster_grid(
    from_date: date,
    to_date: date,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_roster")),
    db: Session = Depends(get_db),
):
    """Return a calendar grid view: list of dates × shifts, plus all nurses
    in the system, plus the entry for each (nurse, date, shift) cell."""
    from datetime import timedelta
    if from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be <= to_date")
    if (to_date - from_date).days > 60:
        raise HTTPException(status_code=400, detail="Date range too large (max 60 days)")

    # Collect all nurses: anyone with role 'nurse'
    from app.models.user import UserRole, user_role_association
    nurse_role = db.query(UserRole).filter(UserRole.name == "nurse").first()
    nurse_ids = set()
    if nurse_role:
        # primary role users
        primary = db.query(User).filter(
            User.role_id == nurse_role.id, User.is_active == True
        ).all()
        nurse_ids.update(u.id for u in primary)
        # multi-role users via association table
        rows = db.execute(
            user_role_association.select().where(
                user_role_association.c.role_id == nurse_role.id
            )
        ).all()
        nurse_ids.update(r.user_id for r in rows)
    nurses = db.query(User).filter(User.id.in_(nurse_ids), User.is_active == True).all() if nurse_ids else []
    nurses_payload = [
        {"id": n.id, "name": f"{n.first_name} {n.last_name}", "username": n.username}
        for n in sorted(nurses, key=lambda x: (x.first_name or "", x.last_name or ""))
    ]

    # Date list
    dates = []
    d = from_date
    while d <= to_date:
        dates.append(d.isoformat())
        d = d + timedelta(days=1)

    # Pull all roster entries in range
    rows = db.query(NurseShiftRoster).filter(
        NurseShiftRoster.roster_date >= datetime.combine(from_date, datetime.min.time()),
        NurseShiftRoster.roster_date < datetime.combine(to_date, datetime.min.time()) + timedelta(days=1),
    ).all()

    # cells[nurse_id][date_iso][shift] = {status, ward, notes, id}
    cells: dict = {}
    for r in rows:
        nid = r.nurse_id
        diso = r.roster_date.date().isoformat() if hasattr(r.roster_date, "date") else str(r.roster_date)[:10]
        cells.setdefault(nid, {}).setdefault(diso, {})[r.shift] = {
            "id": r.id,
            "status": r.status,
            "ward": r.ward,
            "notes": r.notes,
        }

    return {
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "dates": dates,
        "shifts": ["morning", "afternoon", "night"],
        "nurses": nurses_payload,
        "cells": cells,
    }


@router.get("/roster/coverage")
async def roster_coverage(
    from_date: date,
    to_date: date,
    min_per_shift: int = Query(default=DEFAULT_MIN_PER_SHIFT, ge=0),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_roster")),
    db: Session = Depends(get_db),
):
    """For each (date, shift) pair in range, count nurses rostered as 'working'
    and flag understaffed shifts."""
    from datetime import timedelta
    if from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be <= to_date")

    rows = db.query(NurseShiftRoster).filter(
        NurseShiftRoster.roster_date >= datetime.combine(from_date, datetime.min.time()),
        NurseShiftRoster.roster_date < datetime.combine(to_date, datetime.min.time()) + timedelta(days=1),
    ).all()

    bucket: dict = {}
    for r in rows:
        diso = r.roster_date.date().isoformat() if hasattr(r.roster_date, "date") else str(r.roster_date)[:10]
        key = (diso, r.shift)
        bucket.setdefault(key, {"working": 0, "on_call": 0, "leave": 0, "off": 0})
        bucket[key][r.status] = bucket[key].get(r.status, 0) + 1

    result = []
    d = from_date
    while d <= to_date:
        for shift in ["morning", "afternoon", "night"]:
            stats = bucket.get((d.isoformat(), shift), {"working": 0, "on_call": 0, "leave": 0, "off": 0})
            result.append({
                "date": d.isoformat(),
                "shift": shift,
                **stats,
                "is_understaffed": stats["working"] < min_per_shift,
                "min_required": min_per_shift,
            })
        d = d + timedelta(days=1)
    return {
        "from_date": from_date.isoformat(),
        "to_date": to_date.isoformat(),
        "min_per_shift": min_per_shift,
        "shifts": result,
    }


@router.get("/roster/on-duty")
async def on_duty_nurses(
    target_date: date,
    shift: str = Query(..., pattern="^(morning|afternoon|night)$"),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_roster")),
    db: Session = Depends(get_db),
):
    """Nurses rostered as 'working' or 'on_call' for the given date/shift.
    Used by the Assign Nurse dropdown to filter to only available staff."""
    target_dt = datetime.combine(target_date, datetime.min.time())
    rows = db.query(NurseShiftRoster).filter(
        NurseShiftRoster.roster_date == target_dt,
        NurseShiftRoster.shift == shift,
        NurseShiftRoster.status.in_(list(ASSIGNABLE_STATUSES)),
    ).all()
    result = []
    for r in rows:
        nurse = db.query(User).filter(User.id == r.nurse_id).first()
        if nurse and nurse.is_active:
            result.append({
                "nurse_id": nurse.id,
                "nurse_name": f"{nurse.first_name} {nurse.last_name}",
                "username": nurse.username,
                "status": r.status,
                "ward": r.ward,
            })
    return result


@router.put("/roster/{entry_id}", response_model=RosterEntryResponse)
async def update_roster_entry(
    entry_id: int,
    data: RosterEntryUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_roster")),
    db: Session = Depends(get_db),
):
    entry = db.query(NurseShiftRoster).filter(NurseShiftRoster.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Roster entry not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(entry, k, v)
    db.commit()
    db.refresh(entry)
    return _roster_to_response(entry, db)


@router.delete("/roster/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_roster_entry(
    entry_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_roster")),
    db: Session = Depends(get_db),
):
    entry = db.query(NurseShiftRoster).filter(NurseShiftRoster.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Roster entry not found")
    db.delete(entry)
    db.commit()
