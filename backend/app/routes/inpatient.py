from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sqlfunc, and_, cast, Date, update as sa_update
from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime, date, timezone


def _now_utc() -> datetime:
    """Timezone-aware UTC 'now'. Use everywhere instead of the deprecated
    _now_utc() (which returned a naive datetime)."""
    return datetime.now(timezone.utc)


def _inline_pdf_response(pdf_buffer, filename: str) -> Response:
    """Return PDF bytes inline — more reliable than StreamingResponse(BytesIO)
    in the Windows bundled build."""
    data = pdf_buffer.getvalue() if hasattr(pdf_buffer, "getvalue") else pdf_buffer
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


import io
import os
import uuid

from config.database import get_db
from app.utils.pdf_settings import bill_pdf_gen_kwargs, pdf_gen_kwargs
from app.models.user import User
from app.models.patient import Patient
from app.models.hospital import Hospital
from app.models.billing import Bill, BillItem
from app.models.inpatient import (
    RoomManagement, Admission, DischargeRecord, DAMARecord,
    PatientVisit, InpatientRateConfig, OTSchedule, Bed, AdmissionDocument, NursingNote,
    VitalSigns, MedicationAdministration,
    AdmissionDeposit, AncillaryServiceCatalog, AdmissionAncillaryCharge, Procedure,
    SurgeryPackage, AdmissionPackage, InsurancePreAuth, InsurancePreAuthExpansion,
    TPACompany, BillSplit, LeaveOfAbsence, ShiftHandover, CodeBlueEvent, BodyReleaseRecord,
    PayerScheme, AdmissionPayerChange, GatePass, DoctorDutyRoster, RoomMaintenance,
    RoomTypeRateConfig, DoctorRoomTypeRate, RoomType,
    MealPlan, FoodOrder,
)
from app.models.pharmacy import Prescription, PrescriptionItem, Medicine, PharmacySale, PharmacySaleItem
from app.models.prescriptions_simple import SimplePrescription
from app.models.lab import PatientLabOrder, LabTest, LabReport
from app.utils.dependencies import (
    get_current_user,
    require_permission,
    require_feature_permission,
    require_feature_permission_any,
    user_has_feature_permission,
)
from app.utils.auth import Modules
from app.utils.pdf_service import pdf_service
from app.services.audit_service import log_action
from app.services.admission_clinical_summary_service import build_admission_clinical_summary

router = APIRouter()

# ============================================================
# Age helper — prefer DOB-derived age, fall back to stored age
# ============================================================
from app.utils.patient_age import format_patient_age, patient_age_years_int


def _patient_age(patient):
    return patient_age_years_int(patient)


def _patient_age_display(patient):
    return format_patient_age(patient)

# ============================================================
# Pydantic Models
# ============================================================

# --- Room ---
ROOM_TYPES = {
    "general":      "General Ward",
    "semi_private": "Semi-Private",
    "private":      "Private",
    "suite":        "Suite / Deluxe",
    "icu":          "ICU",
    "hdu":          "HDU / Step-Down",
    "nicu":         "NICU",
    "picu":         "PICU",
    "isolation":    "Isolation",
    "labour":       "Labour & Delivery",
    "recovery":     "Post-Op Recovery",
    "daycare":      "Day Care",
    "emergency":    "Emergency / Casualty",
    "operation":    "Operation Theatre",
}
ROOM_TYPE_PATTERN = "^(" + "|".join(ROOM_TYPES.keys()) + ")$"

AMENITY_OPTIONS = [
    "ac", "tv", "wifi", "attached_bath", "refrigerator", "locker",
    "oxygen_point", "suction_point", "call_bell", "visitor_chair",
    "cardiac_monitor", "pulse_oximeter", "ventilator_support",
    "infusion_pump", "dialysis_point",
]

class RoomCreate(BaseModel):
    room_number: str = Field(..., max_length=20)
    room_type: str = Field(..., pattern=ROOM_TYPE_PATTERN)
    floor: Optional[str] = None
    department: Optional[str] = None
    ward: Optional[str] = None
    bed_count: int = Field(default=1, ge=1)
    room_charge_per_day: float = Field(..., ge=0)
    nursing_charge_per_visit: Optional[float] = Field(default=0.0, ge=0)
    amenities: Optional[List[str]] = None   # list of AMENITY_OPTIONS keys
    is_isolation: bool = False
    gender_policy: str = Field(default="mixed", pattern="^(mixed|male|female)$")

class RoomUpdate(BaseModel):
    room_number: Optional[str] = None
    room_type: Optional[str] = Field(default=None, pattern=ROOM_TYPE_PATTERN)
    floor: Optional[str] = None
    department: Optional[str] = None
    ward: Optional[str] = None
    bed_count: Optional[int] = Field(default=None, ge=1)
    room_charge_per_day: Optional[float] = Field(default=None, ge=0)
    nursing_charge_per_visit: Optional[float] = Field(default=None, ge=0)
    amenities: Optional[List[str]] = None
    is_isolation: Optional[bool] = None
    gender_policy: Optional[str] = Field(default=None, pattern="^(mixed|male|female)$")

class RoomResponse(BaseModel):
    id: int
    room_number: str
    room_type: str
    floor: Optional[str]
    department: Optional[str]
    ward: Optional[str]
    bed_count: int
    available_beds: int
    room_charge_per_day: float
    nursing_charge_per_visit: Optional[float] = 0.0
    amenities: Optional[Any] = None   # list or legacy string
    is_isolation: bool = False
    gender_policy: str = "mixed"
    is_active: bool
    is_occupied: bool
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    class Config:
        from_attributes = True

# --- Maintenance ---
class MaintenanceCreate(BaseModel):
    room_id: int
    bed_id: Optional[int] = None
    issue_type: str = Field(..., pattern="^(electrical|plumbing|hvac|equipment|structural|cleaning|other)$")
    priority: str = Field(default="routine", pattern="^(routine|urgent|emergency)$")
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    assigned_to: Optional[str] = None
    scheduled_date: Optional[datetime] = None

class MaintenanceUpdate(BaseModel):
    status: Optional[str] = Field(default=None, pattern="^(open|in_progress|completed|deferred)$")
    assigned_to: Optional[str] = None
    scheduled_date: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    priority: Optional[str] = Field(default=None, pattern="^(routine|urgent|emergency)$")

class MaintenanceResponse(BaseModel):
    id: int
    room_id: int
    bed_id: Optional[int]
    issue_type: str
    priority: str
    title: str
    description: Optional[str]
    status: str
    assigned_to: Optional[str]
    scheduled_date: Optional[datetime]
    resolved_at: Optional[datetime]
    resolution_notes: Optional[str]
    reported_by_id: int
    reported_by_name: Optional[str] = None
    room_number: Optional[str] = None
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    class Config:
        from_attributes = True

# --- Room-Type Rate Config (nursing charge layer 1) ---
class RoomTypeRateUpsert(BaseModel):
    nursing_charge_per_visit: Optional[float] = Field(default=None, ge=0)

class RoomTypeRateResponse(BaseModel):
    id: Optional[int] = None
    room_type: str
    nursing_charge_per_visit: Optional[float] = None
    class Config:
        from_attributes = True

# --- Doctor Room-Type Rate Override ---
class DoctorRoomRateUpsert(BaseModel):
    doctor_id: int
    room_type: str
    visit_rate: float = Field(..., ge=0)

class DoctorRoomRateResponse(BaseModel):
    id: int
    doctor_id: int
    room_type: str
    visit_rate: float
    class Config:
        from_attributes = True

# --- Rate Config ---
class RateConfigUpdate(BaseModel):
    doctor_visit_rate: Optional[float] = Field(default=None, ge=0)
    duty_visit_rate: Optional[float] = Field(default=None, ge=0)
    nurse_visit_rate: Optional[float] = Field(default=None, ge=0)
    procedure_rate: Optional[float] = Field(default=None, ge=0)

class RateConfigResponse(BaseModel):
    id: int
    doctor_visit_rate: float
    duty_visit_rate: Optional[float] = 0
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
    admitting_person_name: Optional[str] = Field(default=None, max_length=200)
    admitting_person_relationship: Optional[str] = Field(default=None, max_length=100)
    admitting_person_address: Optional[str] = None
    admitting_person_phone: Optional[str] = Field(default=None, max_length=20)
    admitting_person_id_proof: Optional[str] = Field(default=None, max_length=200)
    attending_physician_id: Optional[int] = None
    bed_number: Optional[str] = None
    bed_id: Optional[int] = None
    # B7 — Emergency / casualty fields
    triage_level: Optional[int] = Field(default=None, ge=1, le=5)
    chief_complaint: Optional[str] = None
    arrival_mode: Optional[str] = Field(default=None, pattern="^(walk_in|ambulance|referred|police)$")
    ambulance_details: Optional[str] = None
    is_mlc: Optional[bool] = False
    mlc_number: Optional[str] = None
    mlc_type: Optional[str] = Field(default=None, pattern="^(rta|assault|poisoning|burn|sexual_assault|attempted_suicide|other)$")
    police_station_informed: Optional[str] = None
    mlc_informed_at: Optional[datetime] = None
    # B7.6 — Observation cases
    is_observation: Optional[bool] = False
    # B7.7 — Deposit waiver (e.g. cannot-pay emergencies; soft-warns at discharge)
    deposit_waived: Optional[bool] = False
    deposit_waiver_reason: Optional[str] = None
    # B1 — Payer scheme + member details (Cash / Aarogyasri / Teachers / etc.)
    payer_scheme_id: Optional[int] = None
    scheme_member_id: Optional[str] = Field(default=None, max_length=100)
    scheme_approval_status: Optional[str] = Field(
        default=None, pattern="^(none|pending|approved|rejected|disconnected)$")
    scheme_approval_ref: Optional[str] = Field(default=None, max_length=100)
    scheme_approval_amount: Optional[float] = Field(default=None, ge=0)
    # B3 — Referring doctor (internal or external)
    referring_doctor_id: Optional[int] = None
    referring_external_name: Optional[str] = Field(default=None, max_length=200)
    # If true, this admission starts in `pending` state and requires an IP
    # doctor to explicitly accept before clinical actions are allowed.
    require_acceptance: Optional[bool] = False
    # Wizard: persist as draft (no bed claim) for resume later.
    save_as_draft: Optional[bool] = False

class AdmissionDraftUpdate(BaseModel):
    """Partial update for in-progress admission drafts."""
    patient_id: Optional[int] = None
    admitting_doctor_id: Optional[int] = None
    room_id: Optional[int] = None
    admission_type: Optional[str] = Field(default=None, pattern="^(emergency|elective|transfer)$")
    admission_reason: Optional[str] = None
    condition_on_admission: Optional[str] = Field(default=None, pattern="^(stable|critical|serious)$")
    estimated_stay_days: Optional[int] = Field(default=None, ge=1)
    admission_notes: Optional[str] = None
    admitting_person_name: Optional[str] = Field(default=None, max_length=200)
    admitting_person_relationship: Optional[str] = Field(default=None, max_length=100)
    admitting_person_address: Optional[str] = None
    admitting_person_phone: Optional[str] = Field(default=None, max_length=20)
    admitting_person_id_proof: Optional[str] = Field(default=None, max_length=200)
    attending_physician_id: Optional[int] = None
    bed_id: Optional[int] = None
    triage_level: Optional[int] = Field(default=None, ge=1, le=5)
    deposit_waived: Optional[bool] = None
    deposit_waiver_reason: Optional[str] = None
    payer_scheme_id: Optional[int] = None
    scheme_member_id: Optional[str] = Field(default=None, max_length=100)
    scheme_approval_status: Optional[str] = Field(
        default=None, pattern="^(none|pending|approved|rejected|disconnected)$")
    scheme_approval_ref: Optional[str] = Field(default=None, max_length=100)
    scheme_approval_amount: Optional[float] = Field(default=None, ge=0)
    referring_doctor_id: Optional[int] = None
    referring_external_name: Optional[str] = Field(default=None, max_length=200)
    require_acceptance: Optional[bool] = None


class AdmissionActivateRequest(BaseModel):
    """Step 3 of admit wizard — claim bed and optionally record deposit."""
    deposit_amount: Optional[float] = Field(default=None, ge=0)
    deposit_method: Optional[str] = Field(default="cash", max_length=30)
    deposit_reference: Optional[str] = None
    deposit_waived: Optional[bool] = False


class AdmissionCancelRequest(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)

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
    admitting_person_name: Optional[str] = Field(default=None, max_length=200)
    admitting_person_relationship: Optional[str] = Field(default=None, max_length=100)
    admitting_person_address: Optional[str] = None
    admitting_person_phone: Optional[str] = Field(default=None, max_length=20)
    admitting_person_id_proof: Optional[str] = Field(default=None, max_length=200)
    attending_physician_id: Optional[int] = None
    bed_number: Optional[str] = None
    # Required when the update changes room/bed — used to populate BedTransferHistory
    transfer_reason: Optional[str] = None
    # B7 — Emergency / casualty fields (allow update so MLC can be added later)
    triage_level: Optional[int] = Field(default=None, ge=1, le=5)
    chief_complaint: Optional[str] = None
    arrival_mode: Optional[str] = Field(default=None, pattern="^(walk_in|ambulance|referred|police)$")
    ambulance_details: Optional[str] = None
    is_mlc: Optional[bool] = None
    mlc_number: Optional[str] = None
    mlc_type: Optional[str] = Field(default=None, pattern="^(rta|assault|poisoning|burn|sexual_assault|attempted_suicide|other)$")
    police_station_informed: Optional[str] = None
    mlc_informed_at: Optional[datetime] = None
    is_observation: Optional[bool] = None
    deposit_waived: Optional[bool] = None
    deposit_waiver_reason: Optional[str] = None
    # B1 — payer details (use PATCH /payer to also write history; plain update
    # here is a simple field edit without an audit row)
    scheme_member_id: Optional[str] = Field(default=None, max_length=100)
    scheme_approval_status: Optional[str] = Field(
        default=None, pattern="^(none|pending|approved|rejected|disconnected)$")
    scheme_approval_ref: Optional[str] = Field(default=None, max_length=100)
    scheme_approval_amount: Optional[float] = Field(default=None, ge=0)
    # B3 — referring doctor edits
    referring_doctor_id: Optional[int] = None
    referring_external_name: Optional[str] = Field(default=None, max_length=200)

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
    admitting_person_name: Optional[str] = None
    admitting_person_relationship: Optional[str] = None
    admitting_person_address: Optional[str] = None
    admitting_person_phone: Optional[str] = None
    admitting_person_id_proof: Optional[str] = None
    attending_physician_id: Optional[int]
    bed_number: Optional[str]
    bed_id: Optional[int] = None
    # Phase 4 — readmission metadata
    is_readmission: Optional[bool] = False
    previous_admission_id: Optional[int] = None
    days_since_last_discharge: Optional[int] = None
    # B7 — Emergency / casualty fields
    triage_level: Optional[int] = None
    chief_complaint: Optional[str] = None
    arrival_mode: Optional[str] = None
    ambulance_details: Optional[str] = None
    is_mlc: Optional[bool] = False
    mlc_number: Optional[str] = None
    mlc_type: Optional[str] = None
    police_station_informed: Optional[str] = None
    mlc_informed_at: Optional[datetime] = None
    is_observation: Optional[bool] = False
    deposit_waived: Optional[bool] = False
    deposit_waiver_reason: Optional[str] = None
    deposit_waived_at: Optional[datetime] = None
    # B1 — Payer scheme
    payer_scheme_id: Optional[int] = None
    payer_type: Optional[str] = None
    payer_scheme_name: Optional[str] = None
    scheme_member_id: Optional[str] = None
    scheme_approval_status: Optional[str] = "none"
    scheme_approval_ref: Optional[str] = None
    scheme_approval_amount: Optional[float] = None
    # B3 — Referring doctor + acceptance handshake
    referring_doctor_id: Optional[int] = None
    referring_doctor_name: Optional[str] = None
    referring_external_name: Optional[str] = None
    acceptance_status: Optional[str] = "accepted"
    accepted_by_doctor_id: Optional[int] = None
    accepted_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    cancelled_at: Optional[datetime] = None
    cancelled_by_id: Optional[int] = None
    cancellation_reason: Optional[str] = None
    registration_complete: Optional[bool] = True  # from joined patient
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
    visit_type: str = Field(..., pattern="^(doctor_visit|duty_doctor_visit|nurse_visit|procedure)$")
    visitor_id: int
    notes: Optional[str] = None
    charge_amount: Optional[float] = None  # auto-populated from rate config if not provided
    # Optional structured ward-round checklist (only meaningful for doctor_visit)
    vitals_reviewed: bool = False
    labs_reviewed: bool = False
    pain_assessed: bool = False
    mobility_checked: bool = False
    plan_for_today: Optional[str] = None
    family_updated: bool = False
    # B4 — duty-doctor visits default to a strict roster check; setting this
    # true records the visit anyway and logs the bypass via audit. Used by the
    # UI when the operator explicitly confirms an off-roster visit.
    bypass_roster_check: bool = False

class VisitUpdate(BaseModel):
    notes: Optional[str] = None
    charge_amount: Optional[float] = Field(default=None, ge=0)
    vitals_reviewed: Optional[bool] = None
    labs_reviewed: Optional[bool] = None
    pain_assessed: Optional[bool] = None
    mobility_checked: Optional[bool] = None
    plan_for_today: Optional[str] = None
    family_updated: Optional[bool] = None

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
    vitals_reviewed: Optional[bool] = False
    labs_reviewed: Optional[bool] = False
    pain_assessed: Optional[bool] = False
    mobility_checked: Optional[bool] = False
    plan_for_today: Optional[str] = None
    family_updated: Optional[bool] = False
    class Config:
        from_attributes = True

# --- Discharge ---
class TakeHomeMedItem(BaseModel):
    medicine_id: Optional[int] = None
    medicine_name: str = Field(..., min_length=1, max_length=200)
    dosage: Optional[str] = Field(default=None, max_length=100)
    frequency: Optional[str] = Field(default=None, max_length=100)
    frequency_schedule: Optional[str] = Field(default=None, max_length=20)
    food_timing: Optional[str] = Field(default=None, max_length=30)
    duration: Optional[str] = Field(default=None, max_length=100)
    quantity: Optional[int] = Field(default=None, ge=1)
    instructions: Optional[str] = None


class DischargeCreate(BaseModel):
    discharge_type: str = Field(..., pattern="^(normal|against_advice|transfer|death)$")
    condition_on_discharge: Optional[str] = Field(default=None, pattern="^(stable|improved|unchanged|critical)$")
    discharge_summary: Optional[str] = None
    diagnosis_on_discharge: Optional[str] = None
    treatment_given: Optional[str] = None
    medications_prescribed: Optional[str] = None
    take_home_medications: Optional[List[TakeHomeMedItem]] = None
    follow_up_instructions: Optional[str] = None
    follow_up_date: Optional[datetime] = None
    diet_instructions: Optional[str] = None
    activity_restrictions: Optional[str] = None
    # Safety/quality gates. Each can be individually overridden but every
    # override requires `override_reason` and is audit-logged.
    #   - force_outstanding_balance: bypass the negative-balance check.
    #   - force_unacknowledged_alerts: bypass the unacknowledged critical
    #     lab alert check (patient-safety regression risk; use carefully).
    #   - force_missing_consents: bypass the "OT performed without a
    #     non-withdrawn surgical/anaesthesia consent" check.
    # death and against_advice exits skip all of these gates by design.
    force_outstanding_balance: bool = False
    force_unacknowledged_alerts: bool = False
    force_missing_consents: bool = False
    force_no_final_bill: bool = False
    override_reason: Optional[str] = None

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
    take_home_medications: Optional[List[dict]] = None
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
class BillItemOverride(BaseModel):
    """An editable bill line. `source` ties the line to one of the auto-computed
    items so the source record's `bill_id` (or `billed` flag) is set correctly
    when the bill is committed. `source=None` is a custom add-on line that has
    no source record."""
    source: Optional[str] = Field(default=None, pattern=r"^(room|visit|ot|ancillary|pharmacy_rx|pharmacy_pos|lab_order|package|custom)$")
    source_id: Optional[int] = None
    item_type: str = Field(..., max_length=40)
    item_name: str = Field(..., min_length=1, max_length=300)
    quantity: int = Field(default=1, ge=1)
    unit_price: float = Field(default=0.0, ge=0)
    total_price: float = Field(default=0.0, ge=0)


class FinalizeBillRequest(BaseModel):
    discount_type: Optional[str] = Field(default=None, pattern="^(flat|percentage)$")
    discount_value: Optional[float] = Field(default=0, ge=0)
    tax_percentage: Optional[float] = Field(default=0, ge=0, le=100)
    # When provided, the final bill is built from these explicit lines instead
    # of the auto-computed breakdown. Server still stamps source records'
    # `bill_id` so they can't be re-billed; sources NOT included in the
    # override (or included with total_price=0) are also stamped — they're
    # explicitly waived on this bill rather than carried forward.
    items_override: Optional[List[BillItemOverride]] = None

class SettleInstruction(BaseModel):
    direction: str = Field(..., pattern="^(collect|refund)$")
    amount: float = Field(..., gt=0)
    payment_method: str = Field(default="cash", max_length=30)
    reference_number: Optional[str] = Field(default=None, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=500)


class FinalizeAndSettleRequest(FinalizeBillRequest):
    settle: SettleInstruction


def _compute_draft_final_bill_total(
    breakdown: dict,
    discount_value: float,
    discount_type: str,
    tax_percentage: float,
    items_override: Optional[List[BillItemOverride]] = None,
) -> float:
    """Mirror of the subtotal→discount→tax→total math in
    _create_admission_bill_record_inner so callers can preview the total
    without persisting a Bill row. Used by the balance precheck."""
    if items_override is not None:
        subtotal = round(sum(float(i.total_price or 0) for i in items_override), 2)
    else:
        subtotal = float(breakdown.get("subtotal") or 0)
    discount_amount = 0.0
    if discount_value and discount_value > 0:
        if discount_type == "percentage":
            pct = min(max(float(discount_value), 0.0), 100.0)
            discount_amount = round(subtotal * pct / 100, 2)
        else:
            discount_amount = min(discount_value, subtotal)
    discount_amount = min(max(discount_amount, 0.0), subtotal)
    after_discount = max(subtotal - discount_amount, 0.0)
    tax_amount = 0.0
    if tax_percentage and tax_percentage > 0:
        tax_pct = min(max(float(tax_percentage), 0.0), 100.0)
        tax_amount = round(after_discount * tax_pct / 100, 2)
    return round(after_discount + tax_amount, 2)


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
    referring = getattr(adm, "referring_doctor", None)
    scheme = getattr(adm, "payer_scheme", None)
    return {
        **{c.name: getattr(adm, c.name) for c in adm.__table__.columns},
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
        "doctor_name": f"{doctor.first_name} {doctor.last_name}" if doctor else None,
        "room_number": room.room_number if room else None,
        "room_type": room.room_type if room else None,
        "bed_label": adm.bed.bed_label if adm.bed else None,
        "discharge_date": discharge_date,
        "stay_days": stay_days,
        "registration_complete": bool(getattr(patient, "registration_complete", True)) if patient else True,
        "payer_scheme_name": scheme.name if scheme else None,
        "referring_doctor_name": (f"{referring.first_name} {referring.last_name}"
                                  if referring else None),
    }


# ============================================================
# Staff lookups (for admission / OT dropdowns)
# ============================================================

def _list_staff_by_role(db: Session, hospital_id: int, role_name: str):
    users = db.query(User).join(User.role).filter(
        User.role.has(name=role_name),
        User.hospital_id == hospital_id,
        User.is_active == True,
    ).all()
    return [
        {
            "id": u.id,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "specialization": u.specialization,
            "inpatient_fee_inr": getattr(u, "inpatient_fee_inr", None),
            "consultation_fee_inr": getattr(u, "consultation_fee_inr", None),
        }
        for u in users
    ]


@router.get("/doctors")
async def list_inpatient_doctors(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """Lightweight list of doctors in the current hospital for inpatient dropdowns
    (admit, OT scheduling, etc). Gated by the same read permission as the ward
    overview so any inpatient role can populate the picker."""
    return _list_staff_by_role(db, current_user.hospital_id, 'doctor')


@router.get("/nurses")
async def list_inpatient_nurses(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """Lightweight list of nurses for the Assign Nurse / shift roster pickers."""
    return _list_staff_by_role(db, current_user.hospital_id, 'nurse')


# ============================================================
# Room metadata helpers
@router.get("/room-types")
async def get_room_types(current_user: User = Depends(get_current_user)):
    return [{"value": k, "label": v} for k, v in ROOM_TYPES.items()]

@router.get("/amenity-options")
async def get_amenity_options(current_user: User = Depends(get_current_user)):
    labels = {
        "ac": "Air Conditioning", "tv": "Television", "wifi": "Wi-Fi",
        "attached_bath": "Attached Bathroom", "refrigerator": "Refrigerator",
        "locker": "Locker", "oxygen_point": "Oxygen Point",
        "suction_point": "Suction Point", "call_bell": "Call Bell",
        "visitor_chair": "Visitor Chair", "cardiac_monitor": "Cardiac Monitor",
        "pulse_oximeter": "Pulse Oximeter", "ventilator_support": "Ventilator Support",
        "infusion_pump": "Infusion Pump", "dialysis_point": "Dialysis Point",
    }
    return [{"value": k, "label": labels.get(k, k)} for k in AMENITY_OPTIONS]

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

    import json as _json
    data = room.model_dump()
    if data.get("amenities") is not None:
        data["amenities"] = _json.dumps(data["amenities"])
    db_room = RoomManagement(
        **data,
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

    import json as _json
    update_data = room.model_dump(exclude_unset=True)

    if "amenities" in update_data and update_data["amenities"] is not None:
        update_data["amenities"] = _json.dumps(update_data["amenities"])

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
# Maintenance
# ============================================================

@router.post("/maintenance", response_model=MaintenanceResponse, status_code=status.HTTP_201_CREATED)
async def report_maintenance(
    data: MaintenanceCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_housekeeping")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    room = db.query(RoomManagement).filter(RoomManagement.id == data.room_id, RoomManagement.hospital_id == hospital.id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    mr = RoomMaintenance(
        **data.model_dump(),
        reported_by_id=current_user.id,
        hospital_id=hospital.id,
    )
    db.add(mr)
    db.commit()
    db.refresh(mr)
    log_action(db, current_user, "report_maintenance", "inpatient", "RoomMaintenance", mr.id,
               f"Reported {mr.priority} maintenance issue for room {room.room_number}: {mr.title}")
    result = {c.name: getattr(mr, c.name) for c in mr.__table__.columns}
    result["reported_by_name"] = f"{current_user.first_name} {current_user.last_name}"
    result["room_number"] = room.room_number
    return result


@router.get("/maintenance", response_model=List[MaintenanceResponse])
async def list_maintenance(
    status_filter: Optional[str] = None,
    priority: Optional[str] = None,
    room_id: Optional[int] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_housekeeping")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    q = db.query(RoomMaintenance).filter(RoomMaintenance.hospital_id == hospital.id)
    if status_filter:
        q = q.filter(RoomMaintenance.status == status_filter)
    if priority:
        q = q.filter(RoomMaintenance.priority == priority)
    if room_id:
        q = q.filter(RoomMaintenance.room_id == room_id)
    items = q.order_by(
        RoomMaintenance.priority.desc(),
        RoomMaintenance.created_at.desc()
    ).all()
    results = []
    for mr in items:
        row = {c.name: getattr(mr, c.name) for c in mr.__table__.columns}
        row["reported_by_name"] = f"{mr.reported_by.first_name} {mr.reported_by.last_name}" if mr.reported_by else None
        row["room_number"] = mr.room.room_number if mr.room else None
        results.append(row)
    return results


@router.patch("/maintenance/{issue_id}", response_model=MaintenanceResponse)
async def update_maintenance(
    issue_id: int,
    data: MaintenanceUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_housekeeping")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    mr = db.query(RoomMaintenance).filter(
        RoomMaintenance.id == issue_id,
        RoomMaintenance.hospital_id == hospital.id,
    ).first()
    if not mr:
        raise HTTPException(status_code=404, detail="Maintenance issue not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(mr, key, value)
    if data.status == "completed" and not mr.resolved_at:
        mr.resolved_at = datetime.now()
    mr.updated_by_id = current_user.id
    db.commit()
    db.refresh(mr)
    result = {c.name: getattr(mr, c.name) for c in mr.__table__.columns}
    result["reported_by_name"] = f"{mr.reported_by.first_name} {mr.reported_by.last_name}" if mr.reported_by else None
    result["room_number"] = mr.room.room_number if mr.room else None
    return result


# ============================================================
# Room-Type Rate Config (nursing charge layer 1)
# ============================================================

@router.get("/room-type-rates")
async def get_room_type_rates(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "set_room_rates")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    existing = {
        r.room_type: r
        for r in db.query(RoomTypeRateConfig).filter(
            RoomTypeRateConfig.hospital_id == hospital.id
        ).all()
    }
    
    result = []
    for room_type, label in ROOM_TYPES.items():
        row = existing.get(room_type)
        result.append({
            "room_type": room_type,
            "room_type_label": label,
            "nursing_charge_per_visit": float(row.nursing_charge_per_visit) if row and row.nursing_charge_per_visit is not None else None,
            "id": row.id if row else None,
        })
    return result


@router.put("/room-type-rates/{room_type}")
async def upsert_room_type_rate(
    room_type: str,
    data: RoomTypeRateUpsert,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "set_room_rates")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    
    if room_type not in ROOM_TYPES:
        raise HTTPException(status_code=400, detail="Invalid room type")
    row = db.query(RoomTypeRateConfig).filter(
        RoomTypeRateConfig.hospital_id == hospital.id,
        RoomTypeRateConfig.room_type == room_type,
    ).first()
    if row:
        row.nursing_charge_per_visit = data.nursing_charge_per_visit
    else:
        row = RoomTypeRateConfig(
            hospital_id=hospital.id,
            room_type=room_type,
            nursing_charge_per_visit=data.nursing_charge_per_visit,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "room_type": row.room_type,
        "room_type_label": ROOM_TYPES.get(row.room_type, row.room_type),
        "nursing_charge_per_visit": float(row.nursing_charge_per_visit) if row.nursing_charge_per_visit is not None else None,
        "id": row.id,
    }


# ============================================================
# Doctor Room-Type Rate Overrides
# ============================================================

@router.get("/doctor-room-rates")
async def get_doctor_room_rates(
    doctor_id: Optional[int] = Query(default=None),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_visits")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    
    q = db.query(DoctorRoomTypeRate).filter(
        DoctorRoomTypeRate.hospital_id == hospital.id
    )
    if doctor_id:
        q = q.filter(DoctorRoomTypeRate.doctor_id == doctor_id)
    rows = q.all()
    return [
        {
            "id": r.id,
            "doctor_id": r.doctor_id,
            "room_type": r.room_type,
            "room_type_label": ROOM_TYPES.get(r.room_type, r.room_type),
            "visit_rate": float(r.visit_rate),
        }
        for r in rows
    ]


@router.post("/doctor-room-rates", status_code=status.HTTP_201_CREATED)
async def upsert_doctor_room_rate(
    data: DoctorRoomRateUpsert,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "set_room_rates")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    
    if data.room_type not in ROOM_TYPES:
        raise HTTPException(status_code=400, detail="Invalid room type")
    doctor = db.query(User).filter(User.id == data.doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    row = db.query(DoctorRoomTypeRate).filter(
        DoctorRoomTypeRate.hospital_id == hospital.id,
        DoctorRoomTypeRate.doctor_id == data.doctor_id,
        DoctorRoomTypeRate.room_type == data.room_type,
    ).first()
    if row:
        row.visit_rate = data.visit_rate
    else:
        row = DoctorRoomTypeRate(
            hospital_id=hospital.id,
            doctor_id=data.doctor_id,
            room_type=data.room_type,
            visit_rate=data.visit_rate,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "doctor_id": row.doctor_id,
        "room_type": row.room_type,
        "room_type_label": ROOM_TYPES.get(row.room_type, row.room_type),
        "visit_rate": float(row.visit_rate),
    }


@router.delete("/doctor-room-rates/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_doctor_room_rate(
    rate_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "set_room_rates")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    row = db.query(DoctorRoomTypeRate).filter(
        DoctorRoomTypeRate.id == rate_id,
        DoctorRoomTypeRate.hospital_id == hospital.id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Rate not found")
    db.delete(row)
    db.commit()


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

# ---- Race-safe bed allocation primitives ----------------------------------
# Two concurrent admissions can both read available_beds=1 and both decrement,
# producing negative counts or shared beds. We use atomic conditional UPDATEs
# (portable across SQLite/Postgres/MySQL) plus with_for_update() row hints
# (honored by Postgres/MySQL, no-op on SQLite). Callers must rollback and 409
# when a claim helper returns False.

def _claim_bed_atomic(db: Session, bed_id: int, room_id: int) -> bool:
    """Atomically transition a bed from 'available' to 'occupied'.
    Returns True if this caller won the claim, False if the bed was already
    taken by another transaction (caller must rollback)."""
    result = db.execute(
        sa_update(Bed)
        .where(Bed.id == bed_id, Bed.room_id == room_id, Bed.status == "available")
        .values(status="occupied")
    )
    return result.rowcount > 0


def _decrement_room_available_atomic(db: Session, room_id: int) -> bool:
    """Atomically decrement RoomManagement.available_beds if > 0.
    Returns True on success. Used only in legacy (unstructured) bed mode."""
    result = db.execute(
        sa_update(RoomManagement)
        .where(RoomManagement.id == room_id, RoomManagement.available_beds > 0)
        .values(available_beds=RoomManagement.available_beds - 1)
    )
    return result.rowcount > 0


def _assign_bed_to_admission(db: Session, admission: Admission, room: RoomManagement, bed_id: Optional[int]):
    """Claim a structured bed (if bed_id) and sync room availability."""
    bed_obj = None
    if bed_id:
        bed_obj = db.query(Bed).filter(
            Bed.id == bed_id, Bed.room_id == room.id
        ).with_for_update().first()
        if not bed_obj:
            raise HTTPException(status_code=404, detail="Bed not found in selected room")
        if bed_obj.status != "available":
            raise HTTPException(status_code=400, detail=f"Bed '{bed_obj.bed_label}' is not available")
        if not _claim_bed_atomic(db, bed_obj.id, room.id):
            raise HTTPException(status_code=409, detail="Bed was just taken; please pick another")
        bed_obj.current_admission_id = admission.id
        admission.bed_id = bed_obj.id
        admission.bed_number = bed_obj.bed_label

    room_beds = db.query(Bed).filter(Bed.room_id == room.id).count()
    if room_beds > 0:
        room.available_beds = db.query(Bed).filter(
            Bed.room_id == room.id, Bed.status == "available"
        ).count()
        room.bed_count = room_beds
    else:
        if not _decrement_room_available_atomic(db, room.id):
            raise HTTPException(status_code=409, detail="No beds available; another admission took the last bed")
        db.refresh(room)
    if room.available_beds == 0:
        room.is_occupied = True


def _release_admission_bed(db: Session, admission: Admission):
    """Release bed held by a draft/cancelled admission back to available."""
    if not admission.room_id:
        return
    room = db.query(RoomManagement).filter(RoomManagement.id == admission.room_id).first()
    if admission.bed_id:
        bed_obj = db.query(Bed).filter(Bed.id == admission.bed_id).with_for_update().first()
        if bed_obj and bed_obj.current_admission_id == admission.id:
            bed_obj.status = "available"
            bed_obj.current_admission_id = None
    if room:
        room_beds = db.query(Bed).filter(Bed.room_id == room.id).count()
        if room_beds > 0:
            room.available_beds = db.query(Bed).filter(
                Bed.room_id == room.id, Bed.status == "available"
            ).count()
            room.bed_count = room_beds
        else:
            room.available_beds += 1
        room.is_occupied = room.available_beds == 0


def _strip_admission_api_fields(payload: dict) -> dict:
    """Remove request-only keys that are not Admission ORM columns."""
    return {k: v for k, v in payload.items() if k not in ("save_as_draft", "require_acceptance")}


def _build_admission_from_payload(db: Session, payload: dict, require_acceptance: bool) -> Admission:
    clean = _strip_admission_api_fields(payload)
    scheme_id = clean.get("payer_scheme_id")
    if scheme_id:
        scheme = db.query(PayerScheme).filter(PayerScheme.id == scheme_id).first()
        if not scheme:
            raise HTTPException(status_code=400, detail="Unknown payer_scheme_id")
        clean["payer_type"] = scheme.scheme_type
    acceptance_status = "pending" if require_acceptance else "accepted"
    admission = Admission(**clean, acceptance_status=acceptance_status)
    if acceptance_status == "accepted":
        admission.accepted_by_doctor_id = (
            clean.get("attending_physician_id") or clean.get("admitting_doctor_id")
        )
        admission.accepted_at = datetime.now()
    return admission


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


def _generate_consent_doc_number(db: Session) -> str:
    """Next CS-YYYYMMDD-NNNN number considering BOTH issued consents and
    pre-allocated wizard reservations so the two streams never collide.
    """
    from app.models.inpatient import ConsentDocReservation
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"CS-{today}-"
    max_seq = 0
    for cls, col in ((Consent, Consent.doc_number),
                     (ConsentDocReservation, ConsentDocReservation.doc_number)):
        row = db.query(cls).filter(col.like(f"{prefix}%")).order_by(cls.id.desc()).first()
        if row and row.doc_number:
            try:
                max_seq = max(max_seq, int(row.doc_number.split("-")[-1]))
            except ValueError:
                pass
    return f"{prefix}{(max_seq + 1):04d}"


def _substitute_template_tokens(content: str, ctx: dict) -> str:
    """Replace {{token}} placeholders inside a consent template body with
    values from ctx. Unknown tokens are blanked so the printed form does
    not leak literal {{patient_name}} text.
    """
    if not content:
        return content
    import re
    def repl(m):
        key = m.group(1).strip().lower()
        val = ctx.get(key)
        return str(val) if val not in (None, "") else "________________"
    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", repl, content)


def _admitting_person_token_ctx(admission: Optional[Admission]) -> dict:
    """Tokens for the responsible person / attendant on the admission face sheet."""
    if not admission:
        empty = ""
        return {
            "admitting_person_name": empty,
            "attendant_name": empty,
            "responsible_person_name": empty,
            "admitting_person_relationship": empty,
            "attendant_relationship": empty,
            "responsible_person_relationship": empty,
            "admitting_person_address": empty,
            "attendant_address": empty,
            "admitting_person_phone": empty,
            "attendant_phone": empty,
            "admitting_person_id_proof": empty,
            "attendant_id_proof": empty,
        }
    name = (admission.admitting_person_name or "").strip()
    rel = (admission.admitting_person_relationship or "").strip()
    addr = (admission.admitting_person_address or "").strip()
    phone = (admission.admitting_person_phone or "").strip()
    id_proof = (admission.admitting_person_id_proof or "").strip()
    return {
        "admitting_person_name": name,
        "attendant_name": name,
        "responsible_person_name": name,
        "admitting_person_relationship": rel,
        "attendant_relationship": rel,
        "responsible_person_relationship": rel,
        "admitting_person_address": addr,
        "attendant_address": addr,
        "admitting_person_phone": phone,
        "attendant_phone": phone,
        "admitting_person_id_proof": id_proof,
        "attendant_id_proof": id_proof,
    }


@router.post("/admissions", response_model=AdmissionResponse, status_code=status.HTTP_201_CREATED)
async def create_admission(
    data: AdmissionCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "admit_patients")),
    db: Session = Depends(get_db),
):
    patient = db.query(Patient).filter(Patient.id == data.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    active = db.query(Admission).filter(
        Admission.patient_id == data.patient_id,
        Admission.status == "admitted",
    ).first()
    if active:
        raise HTTPException(status_code=400, detail="Patient already has an active admission")

    payload = data.model_dump()
    save_as_draft = payload.pop("save_as_draft", False)

    if save_as_draft:
        existing_draft = db.query(Admission).filter(
            Admission.patient_id == data.patient_id,
            Admission.status == "draft",
        ).first()
        if existing_draft:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "draft_exists",
                    "message": "A draft admission already exists for this patient. Resume or cancel it first.",
                    "admission_id": existing_draft.id,
                    "admission_number": existing_draft.admission_number,
                },
            )
        doctor = db.query(User).filter(User.id == data.admitting_doctor_id).first()
        if not doctor:
            raise HTTPException(status_code=404, detail="Doctor not found")
        room = db.query(RoomManagement).filter(
            RoomManagement.id == data.room_id,
            RoomManagement.is_active == True,
        ).first()
        if not room:
            raise HTTPException(status_code=404, detail="Room not found")
        require_acceptance = payload.pop("require_acceptance", False)
        if payload.get("is_mlc") and not payload.get("mlc_informed_at"):
            payload["mlc_informed_at"] = datetime.now()
        admission_number = _generate_admission_number(db)
        admission = _build_admission_from_payload(db, payload, require_acceptance)
        admission.admission_number = admission_number
        admission.status = "draft"
        admission.initial_room_charge_per_day = float(room.room_charge_per_day) if room else 0.0
        if payload.get("deposit_waived"):
            admission.deposit_waived_by_id = current_user.id
            admission.deposit_waived_at = datetime.now()
        db.add(admission)
        db.commit()
        db.refresh(admission)
        log_action(db, current_user, "save_admission_draft", "inpatient", "Admission", admission.id,
                   f"Saved admission draft {admission_number} for {patient.first_name} {patient.last_name}")
        admission = db.query(Admission).options(
            joinedload(Admission.patient),
            joinedload(Admission.admitting_doctor),
            joinedload(Admission.room),
            joinedload(Admission.discharge),
            joinedload(Admission.bed),
            joinedload(Admission.payer_scheme),
            joinedload(Admission.referring_doctor),
        ).filter(Admission.id == admission.id).first()
        return _admission_to_response(admission)

    # --- Full admit (legacy dialog + immediate admit) ---
    doctor = db.query(User).filter(User.id == data.admitting_doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    room = db.query(RoomManagement).filter(
        RoomManagement.id == data.room_id,
        RoomManagement.is_active == True,
    ).with_for_update().first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    if room.available_beds <= 0:
        raise HTTPException(status_code=400, detail="No beds available in this room")

    admission_number = _generate_admission_number(db)

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

    if payload.get("is_mlc") and not payload.get("mlc_informed_at"):
        payload["mlc_informed_at"] = datetime.now()
    require_acceptance = payload.pop("require_acceptance", False)
    scheme_id = payload.get("payer_scheme_id")
    if scheme_id:
        scheme = db.query(PayerScheme).filter(PayerScheme.id == scheme_id).first()
        if not scheme:
            raise HTTPException(status_code=400, detail="Unknown payer_scheme_id")
        payload["payer_type"] = scheme.scheme_type
    acceptance_status = "pending" if require_acceptance else "accepted"
    admission = Admission(
        **_strip_admission_api_fields(payload),
        admission_number=admission_number,
        is_readmission=is_readmission,
        previous_admission_id=previous_admission_id,
        days_since_last_discharge=days_since,
        acceptance_status=acceptance_status,
        initial_room_charge_per_day=float(room.room_charge_per_day) if room else 0.0,
    )
    if acceptance_status == "accepted":
        admission.accepted_by_doctor_id = (
            payload.get("attending_physician_id") or payload.get("admitting_doctor_id")
        )
        admission.accepted_at = datetime.now()
    if payload.get("deposit_waived"):
        admission.deposit_waived_by_id = current_user.id
        admission.deposit_waived_at = datetime.now()

    db.add(admission)
    db.flush()
    _assign_bed_to_admission(db, admission, room, data.bed_id)

    db.commit()
    db.refresh(admission)

    log_action(db, current_user, "create_admission", "inpatient", "Admission", admission.id,
               f"Admitted patient {patient.first_name} {patient.last_name} ({admission_number})",
               details={"patient_id": data.patient_id, "room": room.room_number})

    admission = db.query(Admission).options(
        joinedload(Admission.patient),
        joinedload(Admission.admitting_doctor),
        joinedload(Admission.room),
        joinedload(Admission.discharge),
        joinedload(Admission.bed),
        joinedload(Admission.payer_scheme),
        joinedload(Admission.referring_doctor),
    ).filter(Admission.id == admission.id).first()
    return _admission_to_response(admission)


def _load_admission_response(db: Session, admission_id: int):
    admission = db.query(Admission).options(
        joinedload(Admission.patient),
        joinedload(Admission.admitting_doctor),
        joinedload(Admission.room),
        joinedload(Admission.discharge),
        joinedload(Admission.bed),
        joinedload(Admission.payer_scheme),
        joinedload(Admission.referring_doctor),
    ).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    return _admission_to_response(admission)


@router.put("/admissions/{admission_id}/draft", response_model=AdmissionResponse)
async def update_admission_draft(
    admission_id: int,
    data: AdmissionDraftUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "admit_patients")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft admissions can be updated this way")

    update_data = data.model_dump(exclude_unset=True)
    if "patient_id" in update_data and update_data["patient_id"] != admission.patient_id:
        active = db.query(Admission).filter(
            Admission.patient_id == update_data["patient_id"],
            Admission.status == "admitted",
        ).first()
        if active:
            raise HTTPException(status_code=400, detail="Patient already has an active admission")

    require_acceptance = update_data.pop("require_acceptance", None)
    if require_acceptance is not None:
        admission.acceptance_status = "pending" if require_acceptance else "accepted"
        if admission.acceptance_status == "accepted":
            admission.accepted_by_doctor_id = (
                update_data.get("attending_physician_id") or update_data.get("admitting_doctor_id")
                or admission.attending_physician_id or admission.admitting_doctor_id
            )
            admission.accepted_at = datetime.now()
        else:
            admission.accepted_by_doctor_id = None
            admission.accepted_at = None

    scheme_id = update_data.get("payer_scheme_id")
    if scheme_id:
        scheme = db.query(PayerScheme).filter(PayerScheme.id == scheme_id).first()
        if not scheme:
            raise HTTPException(status_code=400, detail="Unknown payer_scheme_id")
        admission.payer_type = scheme.scheme_type

    for k, v in update_data.items():
        setattr(admission, k, v)

    if update_data.get("deposit_waived"):
        admission.deposit_waived_by_id = current_user.id
        admission.deposit_waived_at = datetime.now()

    db.commit()
    log_action(db, current_user, "update_admission_draft", "inpatient", "Admission", admission.id,
               f"Updated admission draft {admission.admission_number}")
    return _load_admission_response(db, admission.id)


@router.post("/admissions/{admission_id}/activate", response_model=AdmissionResponse)
async def activate_admission_draft(
    admission_id: int,
    data: AdmissionActivateRequest,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "admit_patients")),
    db: Session = Depends(get_db),
):
    """Wizard step 3 — claim bed, record deposit, keep status as draft until declarations."""
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft admissions can be activated")

    room = db.query(RoomManagement).filter(
        RoomManagement.id == admission.room_id,
        RoomManagement.is_active == True,
    ).with_for_update().first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    already_held = admission.bed_id and db.query(Bed).filter(
        Bed.id == admission.bed_id,
        Bed.current_admission_id == admission.id,
    ).first()
    if not already_held:
        if room.available_beds <= 0:
            raise HTTPException(status_code=400, detail="No beds available in this room")
        _assign_bed_to_admission(db, admission, room, admission.bed_id)

    waived = data.deposit_waived if data.deposit_waived is not None else admission.deposit_waived
    if not waived and data.deposit_amount and float(data.deposit_amount) > 0:
        has_initial = db.query(AdmissionDeposit).filter(
            AdmissionDeposit.admission_id == admission.id,
            AdmissionDeposit.deposit_type == "initial",
        ).first()
        if not has_initial:
            hospital = _get_hospital(db, current_user)
            admission_id = admission.id
            received_by_id = current_user.id

            def _dep_kwargs():
                return dict(
                    admission_id=admission_id,
                    deposit_number=_generate_deposit_number(db),
                    amount=float(data.deposit_amount),
                    deposit_type="initial",
                    payment_method=data.deposit_method or "cash",
                    reference_number=data.deposit_reference or _generate_txn_id(db),
                    received_by_id=received_by_id,
                    hospital_id=hospital.id,
                )

            _insert_deposit_safely(db, _dep_kwargs)

    db.commit()
    log_action(db, current_user, "activate_admission_draft", "inpatient", "Admission", admission.id,
               f"Activated draft {admission.admission_number} — bed assigned, pending declarations")
    return _load_admission_response(db, admission.id)


@router.post("/admissions/{admission_id}/complete-admission", response_model=AdmissionResponse)
async def complete_admission_draft(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "admit_patients")),
    db: Session = Depends(get_db),
):
    """Wizard step 4 — after face/case sheets signed, promote draft to admitted."""
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft admissions can be completed")

    admission.status = "admitted"
    db.commit()
    log_action(db, current_user, "complete_admission", "inpatient", "Admission", admission.id,
               f"Completed admission {admission.admission_number}")
    return _load_admission_response(db, admission.id)


@router.post("/admissions/{admission_id}/cancel", response_model=AdmissionResponse)
async def cancel_admission(
    admission_id: int,
    data: AdmissionCancelRequest,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "admit_patients")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"Only draft admissions can be cancelled (current status: {admission.status})",
        )

    _release_admission_bed(db, admission)
    admission.status = "cancelled"
    admission.cancelled_at = datetime.now()
    admission.cancelled_by_id = current_user.id
    admission.cancellation_reason = (data.reason or "").strip() or None
    db.commit()
    log_action(db, current_user, "cancel_admission", "inpatient", "Admission", admission.id,
               f"Cancelled admission {admission.admission_number}",
               details={"reason": admission.cancellation_reason})
    return _load_admission_response(db, admission.id)


# ---------------------------------------------------------------
# B7 — Quick / Emergency admit
# Creates a stub Patient (registration_complete=False) plus the
# Admission in a single call. Use when a casualty case arrives
# without time for full reception KYC. Reception completes the
# patient record afterwards via the normal patient edit flow.
# ---------------------------------------------------------------
class QuickAdmitRequest(BaseModel):
    # Minimal patient identity (full record completed later by reception)
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: Optional[str] = Field(default="UNKNOWN", max_length=50)
    age: Optional[int] = Field(default=None, ge=0, le=150)
    gender: Optional[str] = Field(default=None, pattern="^(male|female|other)$")
    primary_phone: Optional[str] = Field(default="0000000000", max_length=15)
    # Admission essentials
    admitting_doctor_id: int
    room_id: int
    bed_id: Optional[int] = None
    admission_reason: Optional[str] = None
    condition_on_admission: Optional[str] = Field(default="critical", pattern="^(stable|critical|serious)$")
    # Emergency-specific
    triage_level: int = Field(..., ge=1, le=5)
    chief_complaint: Optional[str] = None
    arrival_mode: Optional[str] = Field(default="walk_in", pattern="^(walk_in|ambulance|referred|police)$")
    ambulance_details: Optional[str] = None
    is_mlc: bool = False
    mlc_type: Optional[str] = Field(default=None, pattern="^(rta|assault|poisoning|burn|sexual_assault|attempted_suicide|other)$")
    mlc_number: Optional[str] = None
    police_station_informed: Optional[str] = None
    emergency_contact: Optional[str] = None
    # B7.6 / B7.7
    is_observation: bool = False
    deposit_waived: bool = False
    deposit_waiver_reason: Optional[str] = None


@router.post("/admissions/quick-admit", response_model=AdmissionResponse, status_code=status.HTTP_201_CREATED)
async def quick_admit(
    data: QuickAdmitRequest,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "admit_patients")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)

    # Create stub patient — reception completes name, DOB, address, ID proof later.
    from app.services.patient_service import _next_mrn_for
    hospital_id_val = hospital.id if hospital else 1
    patient = Patient(
        first_name=data.first_name.strip(),
        last_name=(data.last_name or "UNKNOWN").strip() or "UNKNOWN",
        age=data.age,
        gender=data.gender,
        primary_phone=(data.primary_phone or "0000000000").strip(),
        hospital_id=hospital_id_val,
        mrn=_next_mrn_for(db, hospital_id_val),
        registration_complete=False,
    )
    db.add(patient)
    db.flush()

    # Reuse the normal admission create path so all bed-claim / readmission
    # / rate-snapshot logic stays in one place.
    admit_payload = AdmissionCreate(
        patient_id=patient.id,
        admitting_doctor_id=data.admitting_doctor_id,
        room_id=data.room_id,
        admission_type="emergency",
        admission_reason=data.admission_reason,
        condition_on_admission=data.condition_on_admission,
        bed_id=data.bed_id,
        emergency_contact=data.emergency_contact,
        triage_level=data.triage_level,
        chief_complaint=data.chief_complaint,
        arrival_mode=data.arrival_mode,
        ambulance_details=data.ambulance_details,
        is_mlc=data.is_mlc,
        mlc_type=data.mlc_type,
        mlc_number=data.mlc_number,
        police_station_informed=data.police_station_informed,
        is_observation=data.is_observation,
        deposit_waived=data.deposit_waived,
        deposit_waiver_reason=data.deposit_waiver_reason,
    )
    return await create_admission(admit_payload, current_user=current_user, db=db)


@router.get("/admissions/triage-queue")
async def list_triage_queue(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """B7.8 — Active emergency admissions sorted by triage level (1 = most urgent)
    then by arrival time. Includes door-to-now elapsed minutes."""
    rows = db.query(Admission).options(
        joinedload(Admission.patient),
        joinedload(Admission.admitting_doctor),
        joinedload(Admission.room),
    ).filter(
        Admission.admission_type == "emergency",
        Admission.status == "admitted",
    ).order_by(
        # NULLs last so untriaged go to bottom
        Admission.triage_level.is_(None),
        Admission.triage_level.asc(),
        Admission.admission_date.asc(),
    ).all()

    out = []
    now = datetime.now()
    for a in rows:
        elapsed_min = None
        if a.admission_date:
            ref = a.admission_date.replace(tzinfo=None) if a.admission_date.tzinfo else a.admission_date
            elapsed_min = int((now - ref).total_seconds() / 60)
        d = _admission_to_response(a)
        d["elapsed_minutes"] = elapsed_min
        out.append(d)
    return {"items": out, "total": len(out)}


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
        joinedload(Admission.payer_scheme),
        joinedload(Admission.referring_doctor),
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
        joinedload(Admission.payer_scheme),
        joinedload(Admission.referring_doctor),
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

    # Handle room transfer (race-safe)
    if room_changed:
        if not transfer_reason:
            raise HTTPException(status_code=400, detail="transfer_reason is required when changing room")
        new_room = db.query(RoomManagement).filter(
            RoomManagement.id == update_data["room_id"],
            RoomManagement.is_active == True,
        ).with_for_update().first()
        if not new_room:
            raise HTTPException(status_code=404, detail="New room not found")
        if new_room.available_beds <= 0:
            raise HTTPException(status_code=400, detail="No beds available in new room")

        old_room = db.query(RoomManagement).filter(
            RoomManagement.id == admission.room_id
        ).with_for_update().first()

        # Release old structured bed if present
        if admission.bed_id:
            old_bed = db.query(Bed).filter(Bed.id == admission.bed_id).with_for_update().first()
            if old_bed and old_bed.current_admission_id == admission.id:
                old_bed.status = "cleaning"
                old_bed.current_admission_id = None

        # Sync old room (structured recompute or legacy +1)
        if old_room:
            old_structured = db.query(Bed).filter(Bed.room_id == old_room.id).count()
            if old_structured > 0:
                old_room.available_beds = db.query(Bed).filter(
                    Bed.room_id == old_room.id, Bed.status == "available"
                ).count()
            else:
                old_room.available_beds += 1
            old_room.is_occupied = old_room.available_beds == 0

        # Claim target bed if specified
        if update_data.get("bed_id"):
            target_bed = db.query(Bed).filter(
                Bed.id == update_data["bed_id"], Bed.room_id == new_room.id
            ).with_for_update().first()
            if not target_bed:
                raise HTTPException(status_code=404, detail="Target bed not found in new room")
            if target_bed.status != "available":
                raise HTTPException(status_code=400, detail=f"Bed '{target_bed.bed_label}' is not available")
            if not _claim_bed_atomic(db, target_bed.id, new_room.id):
                db.rollback()
                raise HTTPException(status_code=409, detail="Target bed was just taken; pick another")
            target_bed.current_admission_id = admission.id

        # Sync new room (structured recompute or atomic decrement)
        new_structured = db.query(Bed).filter(Bed.room_id == new_room.id).count()
        if new_structured > 0:
            new_room.available_beds = db.query(Bed).filter(
                Bed.room_id == new_room.id, Bed.status == "available"
            ).count()
        else:
            if not _decrement_room_available_atomic(db, new_room.id):
                db.rollback()
                raise HTTPException(status_code=409, detail="New room ran out of beds")
            db.refresh(new_room)
        new_room.is_occupied = new_room.available_beds == 0

    if bed_changed and not room_changed:
        if not transfer_reason:
            raise HTTPException(status_code=400, detail="transfer_reason is required when changing bed")
        # Bed-only change inside the same room — release old, claim new atomically.
        if admission.bed_id:
            old_bed = db.query(Bed).filter(Bed.id == admission.bed_id).with_for_update().first()
            if old_bed and old_bed.current_admission_id == admission.id:
                old_bed.status = "cleaning"
                old_bed.current_admission_id = None
        if update_data.get("bed_id"):
            target_bed = db.query(Bed).filter(
                Bed.id == update_data["bed_id"], Bed.room_id == admission.room_id
            ).with_for_update().first()
            if not target_bed:
                raise HTTPException(status_code=404, detail="Target bed not found in current room")
            if target_bed.status != "available":
                raise HTTPException(status_code=400, detail=f"Bed '{target_bed.bed_label}' is not available")
            if not _claim_bed_atomic(db, target_bed.id, admission.room_id):
                db.rollback()
                raise HTTPException(status_code=409, detail="Target bed was just taken; pick another")
            target_bed.current_admission_id = admission.id
        # Recompute room availability from beds
        same_room = db.query(RoomManagement).filter(
            RoomManagement.id == admission.room_id
        ).with_for_update().first()
        if same_room:
            same_room.available_beds = db.query(Bed).filter(
                Bed.room_id == same_room.id, Bed.status == "available"
            ).count()
            same_room.is_occupied = same_room.available_beds == 0

    # B7 — auto-stamp MLC informed time when toggling on without explicit timestamp
    if update_data.get("is_mlc") and not update_data.get("mlc_informed_at") and not admission.mlc_informed_at:
        update_data["mlc_informed_at"] = datetime.now()

    # B7.7 — stamp deposit-waiver audit when toggled on
    if update_data.get("deposit_waived") and not admission.deposit_waived:
        admission.deposit_waived_by_id = current_user.id
        admission.deposit_waived_at = datetime.now()
        log_action(db, current_user, "deposit_waived", "inpatient", "admission", str(admission.id),
                   f"Deposit waived for admission {admission.admission_number}",
                   {"reason": update_data.get("deposit_waiver_reason")})

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

        # Snapshot rates so the bill calc segments by what was charged at the time.
        from_rate = float(old_room.room_charge_per_day) if old_room else None
        to_rate = float(new_room.room_charge_per_day) if new_room else None
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
            from_room_charge_per_day=from_rate,
            to_room_charge_per_day=to_rate,
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
# Daily census report
# ============================================================

def _build_census_payload(db: Session) -> dict:
    """Compute per-ward and per-room-type occupancy snapshot."""
    rooms = db.query(RoomManagement).filter(RoomManagement.is_active == True).all()
    by_dept = {}
    by_type = {}
    total_beds = 0
    occupied_beds = 0
    cleaning_beds = 0
    free_beds = 0
    on_leave = 0

    # Count active LOAs to subtract from "occupied"
    active_loa_admissions = {l.admission_id for l in db.query(LeaveOfAbsence).filter(
        LeaveOfAbsence.status == "active").all()}

    for r in rooms:
        # Prefer structured Bed counts when available
        beds_in_room = db.query(Bed).filter(Bed.room_id == r.id).all()
        if beds_in_room:
            r_total = len(beds_in_room)
            r_occ = sum(1 for b in beds_in_room if b.status == "occupied")
            r_clean = sum(1 for b in beds_in_room if b.status == "cleaning")
            r_free = sum(1 for b in beds_in_room if b.status == "available")
        else:
            r_total = r.bed_count or 0
            r_free = r.available_beds or 0
            r_occ = max(r_total - r_free, 0)
            r_clean = 0

        # Count on-leave subset of occupied beds in this room
        adms_in_room = db.query(Admission).filter(
            Admission.room_id == r.id,
            Admission.status == "admitted",
        ).all()
        r_on_leave = sum(1 for a in adms_in_room if a.id in active_loa_admissions)

        total_beds += r_total
        occupied_beds += r_occ
        cleaning_beds += r_clean
        free_beds += r_free
        on_leave += r_on_leave

        dept = r.department or "—"
        if dept not in by_dept:
            by_dept[dept] = {"department": dept, "rooms": 0, "total_beds": 0,
                             "occupied": 0, "cleaning": 0, "free": 0, "on_leave": 0}
        by_dept[dept]["rooms"] += 1
        by_dept[dept]["total_beds"] += r_total
        by_dept[dept]["occupied"] += r_occ
        by_dept[dept]["cleaning"] += r_clean
        by_dept[dept]["free"] += r_free
        by_dept[dept]["on_leave"] += r_on_leave

        rtype = r.room_type or "—"
        if rtype not in by_type:
            by_type[rtype] = {"room_type": rtype, "total_beds": 0,
                              "occupied": 0, "cleaning": 0, "free": 0}
        by_type[rtype]["total_beds"] += r_total
        by_type[rtype]["occupied"] += r_occ
        by_type[rtype]["cleaning"] += r_clean
        by_type[rtype]["free"] += r_free

    return {
        "as_of": _now_utc().isoformat(),
        "totals": {
            "total_beds": total_beds,
            "occupied": occupied_beds,
            "cleaning": cleaning_beds,
            "free": free_beds,
            "on_leave": on_leave,
            "occupancy_pct": round(occupied_beds * 100 / total_beds, 1) if total_beds else 0.0,
        },
        "by_department": sorted(by_dept.values(), key=lambda x: x["department"]),
        "by_room_type": sorted(by_type.values(), key=lambda x: x["room_type"]),
    }


@router.get("/reports/census")
async def get_census(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """JSON snapshot of current occupancy across the hospital."""
    return _build_census_payload(db)


@router.get("/reports/census/pdf")
async def get_census_pdf(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """Printable per-ward + per-type census snapshot."""
    payload = _build_census_payload(db)
    hospital = _get_hospital(db, current_user)
    hospital_info = {
        "name": hospital.name,
        "address": hospital.address or "",
        "phone": hospital.phone or "",
        "email": hospital.email or "",
        "logo_url": getattr(hospital, "logo_url", "") or "",
        "hospital_subname": getattr(hospital, "hospital_subname", "") or "",
    }
    pdf_buffer = pdf_service.generate_census_pdf(payload, hospital_info, **pdf_gen_kwargs(db, current_user.hospital_id, 'census'))
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=census_{date.today().isoformat()}.pdf"},
    )


# ============================================================
# Leave of Absence (pass-out)
# ============================================================

class LOACreate(BaseModel):
    start_datetime: datetime
    expected_return_datetime: datetime
    reason: str = Field(..., min_length=1)
    approved_by_doctor_id: int
    notes: Optional[str] = None
    bed_held: bool = True


class LOAReturn(BaseModel):
    actual_return_datetime: Optional[datetime] = None
    notes: Optional[str] = None


def _loa_to_response(loa: LeaveOfAbsence, db: Session) -> dict:
    doc = db.query(User).filter(User.id == loa.approved_by_doctor_id).first()
    return {
        **{c.name: getattr(loa, c.name) for c in loa.__table__.columns},
        "approved_by_name": f"Dr. {doc.first_name} {doc.last_name}" if doc else None,
    }


@router.post("/admissions/{admission_id}/loa", status_code=status.HTTP_201_CREATED)
async def create_loa(
    admission_id: int,
    data: LOACreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "update_admission")),
    db: Session = Depends(get_db),
):
    """Start a Leave-of-Absence window. Patient is not discharged; the bed is
    optionally held. Days fully covered by the LOA are excluded from room rent."""
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status != "admitted":
        raise HTTPException(status_code=400, detail="Patient is not currently admitted")
    if data.expected_return_datetime <= data.start_datetime:
        raise HTTPException(status_code=400, detail="expected_return_datetime must be after start_datetime")

    overlap = db.query(LeaveOfAbsence).filter(
        LeaveOfAbsence.admission_id == admission_id,
        LeaveOfAbsence.status == "active",
    ).first()
    if overlap:
        raise HTTPException(status_code=409, detail="Patient already has an active LOA")

    hospital = _get_hospital(db, current_user)
    rec = LeaveOfAbsence(
        admission_id=admission_id,
        start_datetime=data.start_datetime,
        expected_return_datetime=data.expected_return_datetime,
        reason=data.reason,
        approved_by_doctor_id=data.approved_by_doctor_id,
        notes=data.notes,
        bed_held=data.bed_held,
        status="active",
        hospital_id=hospital.id,
        created_by_id=current_user.id,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    log_action(db, current_user, "create_loa", "inpatient", "LeaveOfAbsence", rec.id,
               f"Started LOA for admission {admission.admission_number}",
               details={"admission_id": admission_id, "expected_return": data.expected_return_datetime.isoformat()})
    return _loa_to_response(rec, db)


@router.get("/admissions/{admission_id}/loa")
async def list_loas(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """All LOA records for an admission, newest first."""
    rows = db.query(LeaveOfAbsence).filter(
        LeaveOfAbsence.admission_id == admission_id
    ).order_by(LeaveOfAbsence.start_datetime.desc()).all()
    return [_loa_to_response(r, db) for r in rows]


@router.patch("/loa/{loa_id}/return")
async def mark_loa_returned(
    loa_id: int,
    data: LOAReturn,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "update_admission")),
    db: Session = Depends(get_db),
):
    """Patient has returned to the ward. Closes the LOA window."""
    rec = db.query(LeaveOfAbsence).filter(LeaveOfAbsence.id == loa_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="LOA not found")
    if rec.status != "active":
        raise HTTPException(status_code=409, detail=f"LOA is in '{rec.status}' state")
    rec.actual_return_datetime = data.actual_return_datetime or _now_utc()
    rec.status = "returned"
    if data.notes:
        rec.notes = (rec.notes + "\n" if rec.notes else "") + data.notes
    db.commit()
    db.refresh(rec)
    log_action(db, current_user, "mark_loa_returned", "inpatient", "LeaveOfAbsence", rec.id,
               f"LOA #{rec.id} returned",
               details={"admission_id": rec.admission_id})
    return _loa_to_response(rec, db)


@router.patch("/loa/{loa_id}/cancel")
async def cancel_loa(
    loa_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "update_admission")),
    db: Session = Depends(get_db),
):
    """Cancel an active LOA without recording a return — used when the LOA was
    entered in error or the patient never actually left the ward."""
    rec = db.query(LeaveOfAbsence).filter(LeaveOfAbsence.id == loa_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="LOA not found")
    if rec.status != "active":
        raise HTTPException(status_code=409, detail=f"LOA is in '{rec.status}' state")
    rec.status = "cancelled"
    db.commit()
    db.refresh(rec)
    return _loa_to_response(rec, db)


@router.patch("/loa/{loa_id}/no-show")
async def mark_loa_no_show(
    loa_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "update_admission")),
    db: Session = Depends(get_db),
):
    """Mark an LOA as no-show. Use when the patient never returned beyond a
    grace window. The associated admission can then be discharged separately."""
    rec = db.query(LeaveOfAbsence).filter(LeaveOfAbsence.id == loa_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="LOA not found")
    if rec.status != "active":
        raise HTTPException(status_code=409, detail=f"LOA is in '{rec.status}' state")
    rec.status = "no_show"
    db.commit()
    db.refresh(rec)
    log_action(db, current_user, "mark_loa_no_show", "inpatient", "LeaveOfAbsence", rec.id,
               f"LOA #{rec.id} marked as no-show",
               details={"admission_id": rec.admission_id})
    return _loa_to_response(rec, db)


@router.get("/loa/active")
async def list_active_loas(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """All currently active LOAs across the hospital — used by ward dashboards."""
    rows = db.query(LeaveOfAbsence).filter(
        LeaveOfAbsence.status == "active"
    ).order_by(LeaveOfAbsence.expected_return_datetime).all()
    out = []
    for r in rows:
        adm = db.query(Admission).filter(Admission.id == r.admission_id).first()
        patient = db.query(Patient).filter(Patient.id == adm.patient_id).first() if adm else None
        d = _loa_to_response(r, db)
        d["admission_number"] = adm.admission_number if adm else None
        d["patient_name"] = f"{patient.first_name} {patient.last_name}" if patient else None
        out.append(d)
    return out


# ============================================================
# Shift Handover (nurse-to-nurse)
# ============================================================

VALID_SHIFTS_HANDOVER = {"morning", "afternoon", "night"}


class ShiftHandoverCreate(BaseModel):
    handover_date: Optional[datetime] = None
    from_shift: str = Field(..., min_length=1)
    to_nurse_id: Optional[int] = None
    patient_status_summary: Optional[str] = None
    pending_tasks: Optional[str] = None
    alerts_to_watch: Optional[str] = None
    family_communication: Optional[str] = None
    on_call_contacts: Optional[str] = None
    notes: Optional[str] = None


def _handover_to_response(h: ShiftHandover, db: Session) -> dict:
    fn = db.query(User).filter(User.id == h.from_nurse_id).first()
    tn = db.query(User).filter(User.id == h.to_nurse_id).first() if h.to_nurse_id else None
    return {
        **{c.name: getattr(h, c.name) for c in h.__table__.columns},
        "from_nurse_name": f"{fn.first_name} {fn.last_name}" if fn else None,
        "to_nurse_name": f"{tn.first_name} {tn.last_name}" if tn else None,
    }


@router.post("/admissions/{admission_id}/handover", status_code=status.HTTP_201_CREATED)
async def create_shift_handover(
    admission_id: int,
    data: ShiftHandoverCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_nursing_notes")),
    db: Session = Depends(get_db),
):
    """File the outgoing nurse's handover note for the current shift."""
    if data.from_shift not in VALID_SHIFTS_HANDOVER:
        raise HTTPException(status_code=400, detail=f"from_shift must be one of {sorted(VALID_SHIFTS_HANDOVER)}")
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    hospital = _get_hospital(db, current_user)
    rec = ShiftHandover(
        admission_id=admission_id,
        handover_date=data.handover_date or _now_utc(),
        from_shift=data.from_shift,
        from_nurse_id=current_user.id,
        to_nurse_id=data.to_nurse_id,
        patient_status_summary=data.patient_status_summary,
        pending_tasks=data.pending_tasks,
        alerts_to_watch=data.alerts_to_watch,
        family_communication=data.family_communication,
        on_call_contacts=data.on_call_contacts,
        notes=data.notes,
        hospital_id=hospital.id,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    log_action(db, current_user, "create_shift_handover", "inpatient", "ShiftHandover", rec.id,
               f"Handover filed for admission {admission.admission_number}",
               details={"admission_id": admission_id, "from_shift": data.from_shift})
    return _handover_to_response(rec, db)


@router.patch("/handover/{handover_id}/acknowledge")
async def acknowledge_handover(
    handover_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_nursing_notes")),
    db: Session = Depends(get_db),
):
    """Incoming nurse confirms they read the handover. Sets to_nurse_id +
    acknowledged_at if they weren't pre-assigned."""
    rec = db.query(ShiftHandover).filter(ShiftHandover.id == handover_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Handover not found")
    if rec.acknowledged_at:
        raise HTTPException(status_code=409, detail="Handover already acknowledged")
    if not rec.to_nurse_id:
        rec.to_nurse_id = current_user.id
    rec.acknowledged_at = _now_utc()
    db.commit()
    db.refresh(rec)
    log_action(db, current_user, "acknowledge_handover", "inpatient", "ShiftHandover", rec.id,
               f"Acknowledged handover for admission #{rec.admission_id}")
    return _handover_to_response(rec, db)


@router.get("/admissions/{admission_id}/handovers")
async def list_handovers(
    admission_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    rows = db.query(ShiftHandover).filter(
        ShiftHandover.admission_id == admission_id
    ).order_by(ShiftHandover.handover_date.desc()).limit(limit).all()
    return [_handover_to_response(r, db) for r in rows]


@router.get("/handover/{handover_id}/pdf")
async def get_handover_pdf(
    handover_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    rec = db.query(ShiftHandover).filter(ShiftHandover.id == handover_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Handover not found")
    admission = db.query(Admission).filter(Admission.id == rec.admission_id).first()
    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first() if admission else None
    fn = db.query(User).filter(User.id == rec.from_nurse_id).first()
    tn = db.query(User).filter(User.id == rec.to_nurse_id).first() if rec.to_nurse_id else None
    room = db.query(RoomManagement).filter(RoomManagement.id == admission.room_id).first() if admission else None
    hospital = _get_hospital(db, current_user)
    hospital_info = {
        "name": hospital.name, "address": hospital.address or "", "phone": hospital.phone or "",
        "email": hospital.email or "",
        "logo_url": getattr(hospital, "logo_url", "") or "",
        "hospital_subname": getattr(hospital, "hospital_subname", "") or "",
    }
    payload = {
        "admission_number": admission.admission_number if admission else "",
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "",
        "mrn": (patient.mrn or "") if patient else "",
        "patient_id": patient.patient_id if patient else "",
        "room": room.room_number if room else "",
        "bed": (admission.bed.bed_label if admission and admission.bed else admission.bed_number) if admission else "",
        "from_shift": rec.from_shift,
        "handover_date": rec.handover_date.strftime("%d/%m/%Y %H:%M") if rec.handover_date else "",
        "from_nurse": f"{fn.first_name} {fn.last_name}" if fn else "",
        "to_nurse": f"{tn.first_name} {tn.last_name}" if tn else "",
        "acknowledged_at": rec.acknowledged_at.strftime("%d/%m/%Y %H:%M") if rec.acknowledged_at else "",
        "patient_status_summary": rec.patient_status_summary or "",
        "pending_tasks": rec.pending_tasks or "",
        "alerts_to_watch": rec.alerts_to_watch or "",
        "family_communication": rec.family_communication or "",
        "on_call_contacts": rec.on_call_contacts or "",
        "notes": rec.notes or "",
    }
    pdf_buffer = pdf_service.generate_handover_pdf(payload, hospital_info, **pdf_gen_kwargs(db, current_user.hospital_id, 'handover'))
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=handover_{rec.id}.pdf"},
    )


# ============================================================
# Code Blue / Rapid Response Team event log
# ============================================================

VALID_CODE_BLUE_OUTCOMES = {"rosc", "transferred_icu", "expired", "false_alarm"}


class CodeBlueCreate(BaseModel):
    admission_id: Optional[int] = None
    patient_id: Optional[int] = None
    event_type: str = Field(default="code_blue", pattern="^(code_blue|rrt)$")
    event_datetime: datetime
    location: str = Field(..., min_length=1, max_length=200)
    response_time_seconds: Optional[int] = Field(default=None, ge=0, le=3600)
    team_members: Optional[str] = None
    interventions: Optional[str] = None
    outcome: str = Field(..., min_length=1)
    debrief_notes: Optional[str] = None


def _code_blue_to_response(c: CodeBlueEvent, db: Session) -> dict:
    activator = db.query(User).filter(User.id == c.activated_by_id).first()
    patient = db.query(Patient).filter(Patient.id == c.patient_id).first() if c.patient_id else None
    return {
        **{col.name: getattr(c, col.name) for col in c.__table__.columns},
        "activated_by_name": f"{activator.first_name} {activator.last_name}" if activator else None,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
    }


@router.post("/code-blue", status_code=status.HTTP_201_CREATED)
async def create_code_blue(
    data: CodeBlueCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "report_incident")),
    db: Session = Depends(get_db),
):
    """Log a Code Blue / Rapid Response Team activation. Records who activated,
    response time (if measured), team, interventions, and outcome."""
    if data.outcome not in VALID_CODE_BLUE_OUTCOMES:
        raise HTTPException(status_code=400, detail=f"outcome must be one of {sorted(VALID_CODE_BLUE_OUTCOMES)}")
    hospital = _get_hospital(db, current_user)
    rec = CodeBlueEvent(
        admission_id=data.admission_id,
        patient_id=data.patient_id,
        event_type=data.event_type,
        event_datetime=data.event_datetime,
        location=data.location,
        activated_by_id=current_user.id,
        response_time_seconds=data.response_time_seconds,
        team_members=data.team_members,
        interventions=data.interventions,
        outcome=data.outcome,
        debrief_notes=data.debrief_notes,
        hospital_id=hospital.id,
        created_by_id=current_user.id,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    log_action(db, current_user, "log_code_blue", "inpatient", "CodeBlueEvent", rec.id,
               f"{data.event_type.upper()} at {data.location} — outcome: {data.outcome}",
               details={"admission_id": data.admission_id, "outcome": data.outcome,
                        "response_time_seconds": data.response_time_seconds})
    return _code_blue_to_response(rec, db)


@router.get("/code-blue")
async def list_code_blue(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """Recent code-blue / RRT events. Default window: last 30 days."""
    from datetime import timedelta as _td
    cutoff = _now_utc() - _td(days=days)
    rows = db.query(CodeBlueEvent).filter(
        CodeBlueEvent.event_datetime >= cutoff
    ).order_by(CodeBlueEvent.event_datetime.desc()).all()
    return [_code_blue_to_response(r, db) for r in rows]


@router.get("/reports/code-blue")
async def code_blue_monthly_stats(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """Aggregated code-blue stats for NABH safety reporting: counts by type
    and outcome, mean response time. Window: last `days` days."""
    from datetime import timedelta as _td
    cutoff = _now_utc() - _td(days=days)
    rows = db.query(CodeBlueEvent).filter(CodeBlueEvent.event_datetime >= cutoff).all()
    by_type = {}
    by_outcome = {}
    response_times = []
    for r in rows:
        by_type[r.event_type] = by_type.get(r.event_type, 0) + 1
        by_outcome[r.outcome] = by_outcome.get(r.outcome, 0) + 1
        if r.response_time_seconds is not None:
            response_times.append(r.response_time_seconds)
    return {
        "window_days": days,
        "total_events": len(rows),
        "by_type": by_type,
        "by_outcome": by_outcome,
        "mean_response_time_seconds": round(sum(response_times) / len(response_times), 1) if response_times else None,
        "median_response_time_seconds": (sorted(response_times)[len(response_times) // 2]
                                         if response_times else None),
    }


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
        admission.claim_submitted_at = _now_utc()

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
    admission = db.query(Admission).options(
        joinedload(Admission.room)
    ).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status != "admitted":
        raise HTTPException(status_code=400, detail="Cannot add visits to a non-active admission")
    _require_accepted(admission)

    hospital = _get_hospital(db, current_user)

    visitor = db.query(User).filter(User.id == data.visitor_id).first()

    # B4 — Duty-doctor visit guard. By default the visiting user must be on
    # the duty roster (status working/on_call) covering this moment. The
    # operator can override by setting bypass_roster_check=True; the bypass
    # is recorded in the audit log so it remains traceable.
    roster_bypassed = False
    if data.visit_type == "duty_doctor_visit":
        if not visitor:
            raise HTTPException(status_code=400, detail="visitor_id is required for duty_doctor_visit")
        if data.bypass_roster_check:
            roster_bypassed = True
        else:
            _require_duty_doctor(db, hospital.id, visitor.id, datetime.now())

    # Auto-populate charge_amount from the visit type.
    # Resolution chains (most-specific → least-specific):
    #   nurse_visit:       per-room → room-type RoomTypeRateConfig → global nurse_visit_rate → 0
    #   doctor_visit:      DoctorRoomTypeRate (doctor+room_type) → doctor.inpatient_fee_inr → global → 0
    #   duty_doctor_visit: hospital-wide InpatientRateConfig.duty_visit_rate → 0
    #   procedure:         0 (OT charges flow through ot_schedules)
    charge = data.charge_amount
    if charge is None:
        if data.visit_type == "nurse_visit":
            # 1. Per-room specific override
            room_nursing = None
            if admission.room and admission.room.nursing_charge_per_visit:
                try:
                    room_nursing = float(admission.room.nursing_charge_per_visit)
                except (ValueError, TypeError):
                    room_nursing = None
            if room_nursing and room_nursing > 0:
                charge = room_nursing
            else:
                # 2. Room-type level (layer 1)
                room_type = admission.room.room_type if admission.room else None
                rt_rate = None
                if room_type:
                    rtrc = db.query(RoomTypeRateConfig).filter(
                        RoomTypeRateConfig.hospital_id == hospital.id,
                        RoomTypeRateConfig.room_type == room_type,
                    ).first()
                    if rtrc and rtrc.nursing_charge_per_visit is not None:
                        try:
                            rt_rate = float(rtrc.nursing_charge_per_visit)
                        except (ValueError, TypeError):
                            rt_rate = None
                if rt_rate is not None and rt_rate > 0:
                    charge = rt_rate
                else:
                    # 3. Global fallback
                    rc = db.query(InpatientRateConfig).filter(
                        InpatientRateConfig.hospital_id == hospital.id
                    ).first()
                    try:
                        charge = float(rc.nurse_visit_rate) if rc and rc.nurse_visit_rate else 0
                    except (ValueError, TypeError):
                        charge = 0
        elif data.visit_type == "duty_doctor_visit":
            rc = db.query(InpatientRateConfig).filter(
                InpatientRateConfig.hospital_id == hospital.id
            ).first()
            try:
                charge = float(rc.duty_visit_rate) if rc and rc.duty_visit_rate else 0
            except (ValueError, TypeError):
                charge = 0
        elif visitor and data.visit_type == "doctor_visit":
            # 1. Per-doctor, per-room-type override
            room_type = admission.room.room_type if admission.room else None
            drtr = None
            if room_type:
                drtr = db.query(DoctorRoomTypeRate).filter(
                    DoctorRoomTypeRate.hospital_id == hospital.id,
                    DoctorRoomTypeRate.doctor_id == visitor.id,
                    DoctorRoomTypeRate.room_type == room_type,
                ).first()
            if drtr:
                try:
                    charge = float(drtr.visit_rate)
                except (ValueError, TypeError):
                    charge = 0
            else:
                # 2. Doctor base inpatient fee (layer 1)
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
        vitals_reviewed=bool(data.vitals_reviewed),
        labs_reviewed=bool(data.labs_reviewed),
        pain_assessed=bool(data.pain_assessed),
        mobility_checked=bool(data.mobility_checked),
        plan_for_today=data.plan_for_today,
        family_updated=bool(data.family_updated),
        created_by_id=current_user.id,
        hospital_id=hospital.id,
    )
    db.add(visit)
    db.commit()
    db.refresh(visit)

    if roster_bypassed:
        log_action(db, current_user, "duty_visit_roster_bypass", "inpatient",
                   "PatientVisit", visit.id,
                   f"Recorded off-roster duty visit for "
                   f"{visitor.first_name} {visitor.last_name}",
                   details={"admission_id": admission_id, "visitor_id": visitor.id})

    result = {c.name: getattr(visit, c.name) for c in visit.__table__.columns}
    result["visitor_name"] = f"{visitor.first_name} {visitor.last_name}" if visitor else None
    result["roster_bypassed"] = roster_bypassed
    return result


@router.post("/admissions/{admission_id}/auto-post-today")
async def auto_post_today(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_visits")),
    db: Session = Depends(get_db),
):
    """Manually trigger today's auto-post for one admission. Idempotent — if a
    doctor_visit already exists today for this admission, this is a no-op."""
    from app.services.inpatient_daily_charges import auto_post_daily_visits_for_admission
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status != "admitted":
        raise HTTPException(status_code=400, detail="Admission is not currently admitted")
    visit_id = auto_post_daily_visits_for_admission(db, admission, actor_user_id=current_user.id)
    db.commit()
    if visit_id is None:
        return {"posted": False, "reason": "Already covered for today"}
    return {"posted": True, "visit_id": visit_id}


@router.post("/admissions/auto-post-today/all")
async def auto_post_today_all(
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_visits")),
    db: Session = Depends(get_db),
):
    """Manually trigger today's auto-post for every active admission.
    Useful when the hourly daemon hasn't run yet or needs to be re-fired."""
    from app.services.inpatient_daily_charges import auto_post_daily_visits_all
    summary = auto_post_daily_visits_all(db)
    log_action(db, current_user, "auto_post_daily_visits", "inpatient", "Admission", 0,
               f"Auto-posted daily visits: {summary}", details=summary)
    return summary


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

    # An active LOA means the patient is off the ward. Discharge would be
    # incoherent — close the LOA first or mark it no-show, then discharge.
    active_loa = db.query(LeaveOfAbsence).filter(
        LeaveOfAbsence.admission_id == admission_id,
        LeaveOfAbsence.status == "active",
    ).first()
    if active_loa:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "active_loa",
                "message": "Patient is currently on Leave of Absence. Mark the LOA as returned, no-show, or cancelled before discharging.",
                "loa_id": active_loa.id,
            },
        )

    # Canonical charge breakdown — same source of truth as the final bill so
    # the discharge summary cannot disagree with what the patient is billed.
    charges = _compute_admission_charges(db, admission, unbilled_only=False)
    stay_days = charges["stay_days"]
    total_charges = float(charges.get("subtotal", 0.0))

    # Outstanding-balance gate. Death and AMA exits always proceed (the
    # remaining balance becomes a debt to settle post-exit). For normal/transfer
    # exits with a negative balance (patient still owes), require an explicit
    # override + reason that we audit-log.
    balance = _admission_balance_summary(db, admission)
    is_protected_exit = data.discharge_type in ("death", "against_advice")
    forced_gates = []

    # Credit-balance gate: patient overpaid (deposits > total billed). Refund
    # must be issued before discharge proceeds. Death/AMA bypass because the
    # refund destination may be ambiguous (estate, AMA dispute).
    if not is_protected_exit and balance["balance"] > 0.01:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "credit_refund_required",
                "message": f"Patient has a credit balance of ₹{balance['balance']:.2f}. Issue a refund before discharging.",
                "credit_amount": round(balance["balance"], 2),
                "net_deposits": balance["net_deposits"],
                "total_billed": balance["total_billed"],
            },
        )

    if not is_protected_exit and balance["balance"] < 0:
        # B7.7 — Deposit-waiver soft-pass. When the admission was admitted
        # under a documented deposit waiver (cannot-pay emergency, charity
        # case), the outstanding balance is allowed through but recorded
        # in forced_gates for audit. No additional override flag needed.
        if admission.deposit_waived:
            forced_gates.append("outstanding_balance_waived")
        elif not data.force_outstanding_balance:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "outstanding_balance",
                    "message": "Patient has an outstanding balance. Settle bill or set force_outstanding_balance=true with override_reason.",
                    "balance": balance["balance"],
                    "total_billed": balance["total_billed"],
                    "net_deposits": balance["net_deposits"],
                },
            )
        else:
            forced_gates.append("outstanding_balance")

    # Patient-safety gate: any critical lab alert in the 'new' state (i.e. no
    # clinician has even acknowledged it) blocks the discharge. Acknowledged or
    # addressed alerts pass — those represent a recorded clinical decision.
    if not is_protected_exit:
        new_alerts = db.query(CriticalLabAlert).filter(
            CriticalLabAlert.admission_id == admission_id,
            CriticalLabAlert.status == "new",
        ).all()
        if new_alerts:
            if not data.force_unacknowledged_alerts:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "unacknowledged_critical_alerts",
                        "message": "There are unacknowledged critical lab alerts for this admission. Acknowledge them or override with force_unacknowledged_alerts=true.",
                        "alert_count": len(new_alerts),
                        "alert_ids": [a.id for a in new_alerts],
                        "parameters": [a.parameter_name for a in new_alerts if a.parameter_name],
                    },
                )
            forced_gates.append("unacknowledged_critical_alerts")

    # Consent gate: if any OT was completed for this admission, require at
    # least one non-withdrawn surgical or anaesthesia consent on the
    # admission. Catches the "surgery performed without recorded consent" case.
    if not is_protected_exit:
        completed_ot_count = db.query(OTSchedule).filter(
            OTSchedule.admission_id == admission_id,
            OTSchedule.status == "completed",
        ).count()
        if completed_ot_count > 0:
            valid_consent = db.query(Consent).filter(
                Consent.admission_id == admission_id,
                Consent.consent_type.in_(["surgical", "anaesthesia"]),
                Consent.withdrawn_at.is_(None),
            ).first()
            if not valid_consent:
                if not data.force_missing_consents:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "missing_surgical_consent",
                            "message": "Completed OT procedures exist but no non-withdrawn surgical/anaesthesia consent was recorded. Record the consent or override with force_missing_consents=true.",
                            "completed_ot_count": completed_ot_count,
                        },
                    )
                forced_gates.append("missing_surgical_consent")

    # Final-bill gate: a non-cancelled final bill must exist before discharge
    # (so the patient leaves with a printed bill in hand and a settled
    # balance). Death/AMA exits bypass — those flows still let the operator
    # close out the admission without a polished bill.
    if not is_protected_exit:
        final_bill = db.query(Bill).filter(
            Bill.bill_type == "admission",
            Bill.reference_id == admission_id,
            Bill.bill_subtype == "final",
            Bill.status != "cancelled",
        ).first()
        if not final_bill:
            if not data.force_no_final_bill:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "final_bill_required",
                        "message": "Generate the final bill (and settle the balance) before discharging. Override with force_no_final_bill=true and an override_reason if absolutely needed.",
                    },
                )
            forced_gates.append("no_final_bill")

    # An override_reason is required when forcing discharge gates — except for
    # "outstanding_balance_waived", which is a soft-pass recorded for audit
    # only. The deposit waiver carries its own deposit_waiver_reason, so it is
    # already justified and must not demand a second reason here.
    gates_needing_reason = [g for g in forced_gates if g != "outstanding_balance_waived"]
    if gates_needing_reason and not (data.override_reason and data.override_reason.strip()):
        raise HTTPException(
            status_code=400,
            detail=f"override_reason is required when forcing discharge gates: {', '.join(gates_needing_reason)}",
        )

    room = db.query(RoomManagement).filter(RoomManagement.id == admission.room_id).first()

    discharge = DischargeRecord(
        admission_id=admission_id,
        discharge_type=data.discharge_type,
        condition_on_discharge=data.condition_on_discharge,
        discharge_summary=data.discharge_summary,
        diagnosis_on_discharge=data.diagnosis_on_discharge,
        treatment_given=data.treatment_given,
        medications_prescribed=data.medications_prescribed,
        take_home_medications=([m.dict() for m in data.take_home_medications] if data.take_home_medications else None),
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

    # Reconcile any existing admission bills against deposits so their status
    # reflects the final state at discharge time (deposits already received
    # may now fully cover the bill).
    reconcile_admission_bill_statuses(db, admission_id)
    db.commit()

    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first()
    audit_details = {
        "admission_id": admission_id,
        "stay_days": stay_days,
        "total_charges": total_charges,
        "balance_at_discharge": balance["balance"],
        "discharge_type": data.discharge_type,
    }
    if forced_gates:
        audit_details["forced_gates"] = forced_gates
        audit_details["override_reason"] = data.override_reason
    log_action(db, current_user, "discharge_patient", "inpatient", "Discharge", discharge.id,
               f"Discharged patient {patient.first_name} {patient.last_name} ({admission.admission_number})",
               details=audit_details)

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

    # Recompute the canonical breakdown so the summary always agrees with the
    # final bill, even if one was finalised after the discharge record was saved.
    charges_now = _compute_admission_charges(db, admission, unbilled_only=False)

    discharge_data = {
        "admission_number": admission.admission_number,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "N/A",
        "mrn": (patient.mrn or "") if patient else "",
        "patient_id": patient.patient_id if patient else "N/A",
        "age": _patient_age(patient) or "",
        "age_display": _patient_age_display(patient),
        "gender": patient.gender if patient else "",
        "village": (patient.village or "") if patient else "",
        "district": (patient.district or "") if patient else "",
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "N/A",
        "admission_date": admission.admission_date.strftime("%d/%m/%Y") if admission.admission_date else "",
        "discharge_date": discharge.discharge_date.strftime("%d/%m/%Y") if discharge.discharge_date else "",
        "discharge_type": discharge.discharge_type,
        "condition_on_admission": admission.condition_on_admission or "",
        "condition_on_discharge": discharge.condition_on_discharge or "",
        "diagnosis": discharge.diagnosis_on_discharge or "",
        "treatment": discharge.treatment_given or "",
        "discharge_summary": discharge.discharge_summary or "",
        # Structured take-home prescription (preferred). Falls back to free-text
        # medications_prescribed when no structured list was provided so older
        # discharges still render.
        "take_home_medications": discharge.take_home_medications or [],
        "medications": discharge.medications_prescribed or "",
        "follow_up": discharge.follow_up_instructions or "",
        "follow_up_date": discharge.follow_up_date.strftime("%d/%m/%Y") if discharge.follow_up_date else "",
        "diet_instructions": discharge.diet_instructions or "",
        "activity_restrictions": discharge.activity_restrictions or "",
        "total_stay_days": charges_now.get("stay_days") or discharge.total_stay_days or 0,
        "total_charges": float(charges_now.get("subtotal") or discharge.total_charges or 0),
    }

    pdf_buffer = pdf_service.generate_discharge_summary_pdf(discharge_data, hospital_info, **pdf_gen_kwargs(db, current_user.hospital_id, 'discharge_summary'))

    return _inline_pdf_response(pdf_buffer, f"discharge_{admission.admission_number}.pdf")


@router.get("/admissions/{admission_id}/admission-detail/pdf")
async def get_admission_detail_pdf(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """Detailed Admission Summary — full clinical dossier for active or discharged stays."""
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    include_mar = user_has_feature_permission(db, current_user, Modules.INPATIENT, "view_mar")
    try:
        payload = build_admission_clinical_summary(db, admission_id, include_mar=include_mar)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    hospital = _get_hospital(db, current_user)
    hospital_info = {
        "name": hospital.name,
        "address": hospital.address or "",
        "phone": hospital.phone or "",
        "email": hospital.email or "",
        "logo_url": hospital.logo_url if hasattr(hospital, "logo_url") else "",
        "hospital_subname": hospital.hospital_subname if hasattr(hospital, "hospital_subname") else "",
    }

    pdf_buffer = pdf_service.generate_admission_detail_pdf(
        payload,
        hospital_info,
        **pdf_gen_kwargs(db, current_user.hospital_id, "admission_detail"),
    )
    return _inline_pdf_response(
        pdf_buffer,
        f"admission_detail_{admission.admission_number}.pdf",
    )


@router.get("/admissions/{admission_id}/ot")
async def list_admission_ot_schedules(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """OT schedules linked to a specific admission."""
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    rows = (
        db.query(OTSchedule)
        .filter(OTSchedule.admission_id == admission_id)
        .order_by(OTSchedule.scheduled_date.desc())
        .all()
    )
    results = []
    for ot in rows:
        surgeon = db.query(User).filter(User.id == ot.surgeon_id).first()
        anaesthetist = (
            db.query(User).filter(User.id == ot.anaesthetist_id).first()
            if ot.anaesthetist_id else None
        )
        results.append({
            **{c.name: getattr(ot, c.name) for c in ot.__table__.columns},
            "surgeon_name": f"Dr. {surgeon.first_name} {surgeon.last_name}" if surgeon else None,
            "anaesthetist_name": (
                f"Dr. {anaesthetist.first_name} {anaesthetist.last_name}" if anaesthetist else None
            ),
        })
    return results


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
            "inpatient_bill_id": rx.inpatient_bill_id,
            "pharmacy_sale_id": rx.pharmacy_sale_id,
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

# ---- Package billing helpers ------------------------------------------------

# Categories that the package's `included_services` JSON can list. Used to
# detect "included" service buckets when netting them out of the bill.
_PKG_CAT_ROOM = "room"
_PKG_CAT_DOCTOR_VISIT = "doctor_visit"
_PKG_CAT_NURSE_VISIT = "nurse_visit"
_PKG_CAT_OT = "ot"
_PKG_CAT_SURGERY = "surgery"
_PKG_CAT_PHARMACY = "pharmacy"
_PKG_CAT_LAB = "lab"
_PKG_CAT_ANCILLARY = "ancillary"


def _pharmacy_rx_billable_amount(db: Session, rx: Prescription) -> float:
    """Bill only what was actually dispensed (partial fills bill partial qty)."""
    items = db.query(PrescriptionItem).filter(
        PrescriptionItem.prescription_id == rx.id,
    ).all()
    return round(
        sum(float(i.unit_price or 0) * float(i.quantity_dispensed or 0) for i in items),
        2,
    )


def _pharmacy_pos_sale_entries(db: Session, sales: list) -> list:
    """Serialize deferred POS sales for bill preview / review UI."""
    out = []
    for sale in sales:
        line_items = []
        for item in (sale.items or []):
            med = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
            line_items.append({
                "id": item.id,
                "medicine_id": item.medicine_id,
                "name": med.name if med else "Medicine",
                "quantity": float(item.quantity or 0),
                "unit_price": float(item.rate or 0),
                "total_price": float(item.line_total or 0),
            })
        out.append({
            "id": sale.id,
            "sale_number": sale.sale_number,
            "date": sale.sale_date.isoformat() if sale.sale_date else None,
            "grand_total": float(sale.grand_total or 0),
            "billed": sale.inpatient_bill_id is not None,
            "items": line_items,
        })
    return out


def _pkg_covers(boundary, when) -> bool:
    """True if `when` falls within the package coverage window.

    - boundary == None  → entire stay is covered (no window set).
    - when     == None  → treated as covered (no usable date to decide otherwise).
    - Otherwise covered iff when <= boundary.

    Tz-safe: normalises both sides so a tz-aware/naive mismatch (very common
    when comparing DB datetimes against datetimes parsed from isoformat
    strings) doesn't raise TypeError.
    """
    if boundary is None or when is None:
        return True
    b_aware = boundary.tzinfo is not None
    w_aware = when.tzinfo is not None
    if b_aware and not w_aware:
        when = when.replace(tzinfo=boundary.tzinfo)
    elif w_aware and not b_aware:
        boundary = boundary.replace(tzinfo=when.tzinfo)
    return when <= boundary


def _pkg_visit_included(visit_type: str, included: set) -> bool:
    """Whether a given PatientVisit.visit_type is covered by a package's
    included_services set."""
    if not included:
        return False
    if visit_type == "doctor_visit" and (_PKG_CAT_DOCTOR_VISIT in included or "visits" in included):
        return True
    if visit_type == "nurse_visit" and (_PKG_CAT_NURSE_VISIT in included or "visits" in included):
        return True
    if "visits" in included:
        return True
    return False


def _pkg_ot_included(included: set) -> bool:
    return bool(included) and (_PKG_CAT_OT in included or _PKG_CAT_SURGERY in included)


def _pkg_lab_covered(pkg, lab_test_id: Optional[int]) -> bool:
    """True when this lab test is covered by the package.

    Resolution:
      * "lab" not in the package's included_services → not covered.
      * lab_coverage_mode == "all" → covered.
      * lab_coverage_mode == "selected" → covered only when test_id is in the
        whitelist (``included_lab_test_ids``). Missing test_id → not covered.
    """
    if pkg is None:
        return False
    included = set(pkg.included_services or [])
    if _PKG_CAT_LAB not in included:
        return False
    mode = (pkg.lab_coverage_mode or "all").lower()
    if mode == "all":
        return True
    whitelist = pkg.included_lab_test_ids or []
    return lab_test_id is not None and lab_test_id in whitelist


def _get_package_assignment(db: Session, admission_id: int):
    """Return (assignment, pkg) for the admission's active package, or (None, None)."""
    ap = db.query(AdmissionPackage).filter(AdmissionPackage.admission_id == admission_id).first()
    if not ap:
        return None, None
    pkg = db.query(SurgeryPackage).filter(SurgeryPackage.id == ap.package_id).first()
    return ap, pkg


def _included_room_rate(db: Session, hospital_id, included_room_type: Optional[str]) -> float:
    """Resolve the package's included room rate by looking at rooms of the
    matching room_type in the hospital. Falls back to 0 if no room of that
    type exists (or no type specified). ``hospital_id`` is optional — when
    None, the rate is resolved across all hospitals (single-tenant deployments)."""
    if not included_room_type:
        return 0.0
    q = db.query(sqlfunc.min(RoomManagement.room_charge_per_day)).filter(
        RoomManagement.room_type == included_room_type,
    )
    if hospital_id is not None:
        q = q.filter(RoomManagement.hospital_id == hospital_id)
    rate = q.scalar()
    return float(rate or 0)


def _apply_package_room(rate_segments, billable_stay_days, included_stay_days, included_room_rate, has_reference_rate=True):
    """Apply package room logic to the rate_segments timeline.

    Returns (package_room_total, line_items) where line_items is a list of
    {label, days, rate, total} dicts suitable for emitting BillItem rows.

    Rules:
      * For days <= included_stay_days, charge max(seg_rate - included_room_rate, 0)
        per day (upgrade differential, clamped at 0 when patient is in same or
        cheaper room than the package). When ``has_reference_rate`` is False
        (no included_room_type configured, or no room of that type exists),
        the actual room is treated as fully covered — no upgrade charge.
      * For days > included_stay_days, charge the actual segment rate per day
        (NOT excess_per_day_charge — caller passes that in only as a fallback
        when no rate_segments exist).
    """
    pkg_total = 0.0
    lines = []
    days_consumed = 0
    inc_cap = max(int(included_stay_days or 0), 0)

    for seg in rate_segments:
        seg_days = int(seg.get("days") or 0)
        seg_rate = float(seg.get("rate") or 0)
        if seg_days <= 0:
            continue

        # Split into included (within cap) and excess (beyond cap) portions
        remaining_inc = max(inc_cap - days_consumed, 0)
        inc_days = min(seg_days, remaining_inc)
        exc_days = seg_days - inc_days

        if inc_days > 0 and has_reference_rate:
            upgrade_rate = max(seg_rate - included_room_rate, 0.0)
            if upgrade_rate > 0:
                total = round(upgrade_rate * inc_days, 2)
                pkg_total += total
                lines.append({
                    "label": f"Room upgrade ({inc_days} days @ Rs. {upgrade_rate:.2f})",
                    "days": inc_days,
                    "rate": upgrade_rate,
                    "total": total,
                })
        if exc_days > 0:
            total = round(seg_rate * exc_days, 2)
            pkg_total += total
            lines.append({
                "label": f"Room excess stay ({exc_days} days @ Rs. {seg_rate:.2f})",
                "days": exc_days,
                "rate": seg_rate,
                "total": total,
            })
        days_consumed += seg_days

    return round(pkg_total, 2), lines


def _compute_admission_charges(db: Session, admission: Admission, unbilled_only: bool = False, apply_package: bool = True) -> dict:
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
    # `room_charge_per_day` is reported as the *current* room rate for display.
    # The actual bill total is computed by summing rate-snapshotted segments.
    room_charge_per_day = float(room.room_charge_per_day) if room else 0.0

    # ---- Rate-snapshotted room rent computation ----------------------------
    # Walk the stay timeline as a series of segments, each at the rate that
    # was actually in effect during that segment. Days per segment use whole
    # `.days` (matches the original integer-day billing convention so the
    # stay-day arithmetic stays consistent across the codebase). The last
    # segment absorbs any rounding so total segment days == stay_days.
    full_room_total = 0.0
    rate_segments = []
    # B7.6 — Observation cases skip room rent entirely (bed used briefly,
    # typically ≤24h). Doctor visits, drugs, labs etc. still bill normally.
    is_observation = bool(getattr(admission, "is_observation", False))
    if admission.admission_date and not is_observation:
        transfers = db.query(BedTransferHistory).filter(
            BedTransferHistory.admission_id == admission.id,
            BedTransferHistory.status.in_(["completed", "accepted"]),
        ).all()

        def _eff_time(t):
            return t.accepted_at or t.transferred_at or t.created_at

        transfers.sort(key=lambda t: _eff_time(t) or admission.admission_date)

        # Segment boundaries: admission_date → t1 → t2 → ... → end_date
        boundaries = [admission.admission_date]
        for t in transfers:
            eff = _eff_time(t)
            if eff and eff > boundaries[-1] and eff <= end_date:
                boundaries.append(eff)
        boundaries.append(end_date)

        # Rates per segment: segment i uses the rate in effect at boundary i.
        # First segment uses initial; subsequent uses to_room_charge_per_day
        # of the transfer at boundary i.
        rates = [(admission.initial_room_charge_per_day
                  if admission.initial_room_charge_per_day is not None
                  else room_charge_per_day)]
        for t in transfers:
            eff = _eff_time(t)
            if eff and eff > admission.admission_date and eff <= end_date:
                rates.append(t.to_room_charge_per_day
                             if t.to_room_charge_per_day is not None
                             else room_charge_per_day)

        # Sum days per segment using `.days`; last segment absorbs remainder.
        total_days_assigned = 0
        n_segs = len(boundaries) - 1
        for i in range(n_segs):
            seg_from, seg_to = boundaries[i], boundaries[i + 1]
            if i < n_segs - 1:
                seg_days = max((seg_to - seg_from).days, 0)
                total_days_assigned += seg_days
            else:
                # Last segment: ensure all stay_days are accounted for.
                seg_days = max(stay_days - total_days_assigned, 0)
                total_days_assigned += seg_days
            seg_rate = rates[i]
            seg_total = seg_rate * seg_days
            full_room_total += seg_total
            if seg_days > 0:
                rate_segments.append({
                    "from": seg_from.isoformat(), "to": seg_to.isoformat(),
                    "days": seg_days, "rate": seg_rate, "total": round(seg_total, 2),
                })
    elif not is_observation:
        full_room_total = room_charge_per_day * stay_days

    # Subtract whole days fully covered by an LOA (returned or active).
    # 'active' LOAs use expected_return_datetime as the end; 'returned' use
    # actual_return_datetime; 'cancelled' / 'no_show' don't reduce billing.
    # LOA day skip uses the *current* segment rate at LOA start time. This
    # is a reasonable approximation; full segment-aware LOA skipping would
    # add complexity for negligible billing impact.
    loa_days_skipped = 0
    loa_credit = 0.0
    if admission.admission_date:
        loas = db.query(LeaveOfAbsence).filter(
            LeaveOfAbsence.admission_id == admission.id,
            LeaveOfAbsence.status.in_(["active", "returned"]),
        ).all()
        for loa in loas:
            loa_end = loa.actual_return_datetime if loa.status == "returned" else loa.expected_return_datetime
            if not loa_end or not loa.start_datetime:
                continue
            from datetime import timedelta as _td
            cur = loa.start_datetime.date() + _td(days=1)
            while cur < loa_end.date():
                loa_days_skipped += 1
                # Find rate in effect on this date
                day_dt = datetime.combine(cur, datetime.min.time(), tzinfo=loa.start_datetime.tzinfo)
                applicable_rate = (admission.initial_room_charge_per_day
                                   if admission.initial_room_charge_per_day is not None
                                   else room_charge_per_day)
                for seg in rate_segments:
                    seg_from = datetime.fromisoformat(seg["from"])
                    seg_to = datetime.fromisoformat(seg["to"])
                    if seg_from <= day_dt < seg_to:
                        applicable_rate = seg["rate"]
                        break
                loa_credit += applicable_rate
                cur += _td(days=1)
    full_room_total = max(full_room_total - loa_credit, 0.0)
    billable_stay_days = max(stay_days - loa_days_skipped, 1)

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

    # Pharmacy — exclude Rx already paid at the pharmacy counter
    rx_q = db.query(Prescription).filter(
        Prescription.admission_id == admission.id,
        Prescription.status.in_(["dispensed", "partial"]),
        Prescription.pharmacy_sale_id.is_(None),
    )
    if unbilled_only:
        rx_q = rx_q.filter(Prescription.inpatient_bill_id.is_(None))
    pharmacy_rxs = rx_q.all()
    pharmacy_rx_total = sum(_pharmacy_rx_billable_amount(db, rx) for rx in pharmacy_rxs)

    # POS counter sales deferred to the admission bill (not paid at counter).
    pos_q = db.query(PharmacySale).options(joinedload(PharmacySale.items)).filter(
        PharmacySale.admission_id == admission.id,
        PharmacySale.billing_mode == "inpatient_bill",
        PharmacySale.status == "completed",
    )
    if unbilled_only:
        pos_q = pos_q.filter(PharmacySale.inpatient_bill_id.is_(None))
    pharmacy_pos_sales = pos_q.order_by(PharmacySale.sale_date.asc()).all()
    pharmacy_pos_total = sum(float(s.grand_total or 0) for s in pharmacy_pos_sales)
    pharmacy_total = round(pharmacy_rx_total + pharmacy_pos_total, 2)
    pharmacy_pos_entries = _pharmacy_pos_sale_entries(db, pharmacy_pos_sales)

    # Lab — build a per-order breakdown so the bill display can mark each
    # individual lab test as covered or billed when the package uses granular
    # inclusion (lab_coverage_mode == "selected"). `included_in_package` is
    # filled in by the package overlay block below.
    lab_q = db.query(PatientLabOrder).filter(
        PatientLabOrder.admission_id == admission.id,
        PatientLabOrder.status != "cancelled",
    )
    if unbilled_only:
        lab_q = lab_q.filter(PatientLabOrder.inpatient_bill_id.is_(None))
    lab_orders = lab_q.all()
    lab_total = sum(float(o.amount or 0) for o in lab_orders)
    lab_entries = []
    for o in lab_orders:
        test = db.query(LabTest).filter(LabTest.id == o.test_id).first() if o.test_id else None
        lab_entries.append({
            "id": o.id,
            "test_id": o.test_id,
            "test_name": test.name if test else "Lab Test",
            "order_number": o.order_number,
            "amount": float(o.amount or 0),
            "billed": o.inpatient_bill_id is not None,
            "included_in_package": False,
        })

    # Food orders — non-cancelled. When unbilled_only, exclude already-billed.
    food_q = db.query(FoodOrder).filter(
        FoodOrder.admission_id == admission.id,
        FoodOrder.status != "cancelled",
    )
    if unbilled_only:
        food_q = food_q.filter(FoodOrder.billed == False)
    food_orders = food_q.order_by(FoodOrder.meal_date.asc(), FoodOrder.meal_type.asc()).all()
    food_total = sum(float(f.price or 0) for f in food_orders)
    food_entries = [
        {
            "id": f.id,
            "meal_date": f.meal_date.isoformat() if f.meal_date else None,
            "meal_type": f.meal_type,
            "status": f.status,
            "price": float(f.price or 0),
            "diet_preference": f.diet_preference or "",
            "billed": bool(f.billed),
        }
        for f in food_orders
    ]

    # ---- Package overlay --------------------------------------------------
    # When an admission has an active package, the agreed_price covers all
    # included_services performed within the coverage window
    # (admission_date → admission_date + included_stay_days). Anything outside
    # that window — or any category NOT in included_services — bills at the
    # full standard rate as "excess".
    #
    # `included_stay_days == 0` (or None) means "no window cap" — every item
    # in an included category is covered for the entire stay.
    pkg_block = None
    pkg_room_lines = []
    pkg = None  # SurgeryPackage row, exposed below for downstream coverage checks
    pkg_boundary = None
    pkg_fee_already_billed = False
    pkg_room_excess_already_billed = 0.0
    if apply_package:
        pkg_assignment, pkg = _get_package_assignment(db, admission.id)
        if pkg_assignment and pkg:
            from datetime import timedelta as _td_v
            included = set(pkg.included_services or [])
            # Coverage window. included_stay_days=0/null → no boundary
            # (whole stay covered for included categories).
            if (pkg.included_stay_days or 0) > 0 and admission.admission_date:
                pkg_boundary = admission.admission_date + _td_v(days=pkg.included_stay_days)

            # Has the package fee already been billed on a prior non-cancelled
            # bill for this admission? Used in unbilled_only mode so finalize
            # after interim doesn't re-bill the agreed_price.
            prior_pkg_item = db.query(BillItem).join(Bill, Bill.id == BillItem.bill_id).filter(
                Bill.bill_type == "admission",
                Bill.reference_id == admission.id,
                Bill.status != "cancelled",
                BillItem.item_type == "package",
            ).first()
            pkg_fee_already_billed = prior_pkg_item is not None

            # Resolve package's reference room rate (for upgrade differential).
            included_room_rate = _included_room_rate(
                db,
                getattr(room, 'hospital_id', None) or getattr(admission, 'hospital_id', None),
                pkg.included_room_type,
            ) if _PKG_CAT_ROOM in included else 0.0
            has_reference_rate = bool(pkg.included_room_type) and included_room_rate > 0

            # ---- Room: replace total with package logic when room is included
            pkg_room_total = room_total
            if _PKG_CAT_ROOM in included:
                if rate_segments:
                    pkg_room_total, pkg_room_lines = _apply_package_room(
                        rate_segments,
                        billable_stay_days,
                        pkg.included_stay_days or 0,
                        included_room_rate,
                        has_reference_rate=has_reference_rate,
                    )
                else:
                    excess_days = max(billable_stay_days - (pkg.included_stay_days or 0), 0)
                    pkg_room_total = round(excess_days * float(pkg.excess_per_day_charge or 0), 2)
                    if pkg_room_total > 0:
                        pkg_room_lines.append({
                            "label": f"Room excess stay ({excess_days} days)",
                            "days": excess_days,
                            "rate": float(pkg.excess_per_day_charge or 0),
                            "total": pkg_room_total,
                        })
                # Subtract room excess already billed on prior bills so a
                # finalize after interim doesn't double-bill it.
                if unbilled_only:
                    pkg_room_excess_already_billed = float(billed_room_total or 0)
                    pkg_room_total = round(max(pkg_room_total - pkg_room_excess_already_billed, 0.0), 2)

            # ---- Visits — split per-item by boundary.
            pkg_visit_total = 0.0
            for vtype, vdata in list(visit_summary.items()):
                if _pkg_visit_included(vtype, included):
                    covered_orig_total = 0.0
                    billed_total = 0.0
                    covered_count = 0
                    billed_count = 0
                    for it in vdata.get("items", []):
                        visit_dt = None
                        if it.get("date"):
                            try:
                                visit_dt = datetime.fromisoformat(it["date"])
                            except Exception:
                                visit_dt = None
                        if _pkg_covers(pkg_boundary, visit_dt):
                            it["original_amount"] = it.get("amount", 0)
                            it["amount"] = 0.0
                            it["included_in_package"] = True
                            covered_orig_total += float(it.get("original_amount") or 0)
                            covered_count += 1
                        else:
                            it["included_in_package"] = False
                            billed_total += float(it.get("amount") or 0)
                            billed_count += 1
                    vdata["covered_count"] = covered_count
                    vdata["billed_count"] = billed_count
                    vdata["covered_total_original"] = round(covered_orig_total, 2)
                    vdata["billed_total"] = round(billed_total, 2)
                    vdata["original_total"] = round(covered_orig_total + billed_total, 2)
                    vdata["total"] = round(billed_total, 2)
                    vdata["included_in_package"] = covered_count > 0
                    pkg_visit_total += billed_total
                else:
                    vdata["included_in_package"] = False
                    pkg_visit_total += float(vdata.get("total") or 0)

            # ---- OT — per-entry boundary check (covered/excess split).
            ot_type_in_pkg = _pkg_ot_included(included)
            pkg_ot_total = 0.0
            for raw, entry in zip(ot_entries, ot_breakdown):
                covers = ot_type_in_pkg and _pkg_covers(pkg_boundary, getattr(raw, "scheduled_date", None))
                if covers:
                    entry["included_in_package"] = True
                    entry["original_total"] = entry.get("total", 0)
                    entry["total"] = 0.0
                else:
                    entry["included_in_package"] = False
                    pkg_ot_total += float(entry.get("total") or 0)
            pkg_ot_total = round(pkg_ot_total, 2)

            # ---- Ancillary — per-entry boundary check.
            anc_type_in_pkg = _PKG_CAT_ANCILLARY in included
            pkg_ancillary_total = 0.0
            for raw, entry in zip(anc_entries, ancillary_breakdown):
                covers = anc_type_in_pkg and _pkg_covers(pkg_boundary, getattr(raw, "charged_at", None))
                if covers:
                    entry["included_in_package"] = True
                    entry["original_total"] = entry.get("total_amount", 0)
                    entry["total_amount"] = 0.0
                else:
                    entry["included_in_package"] = False
                    pkg_ancillary_total += float(entry.get("total_amount") or 0)
            pkg_ancillary_total = round(pkg_ancillary_total, 2)

            # ---- Pharmacy — per-Rx boundary check (still surfaced as lump
            # totals; covered/billed split exposed so the PDF can show two
            # rows).
            rx_type_in_pkg = _PKG_CAT_PHARMACY in included
            pkg_pharmacy_total = 0.0
            pkg_pharmacy_covered_total = 0.0
            for rx in pharmacy_rxs:
                rx_dt = getattr(rx, "dispensed_date", None) or getattr(rx, "prescription_date", None)
                amt = _pharmacy_rx_billable_amount(db, rx)
                covers = rx_type_in_pkg and _pkg_covers(pkg_boundary, rx_dt)
                if covers:
                    pkg_pharmacy_covered_total += amt
                else:
                    pkg_pharmacy_total += amt
            for sale in pharmacy_pos_sales:
                sale_dt = getattr(sale, "sale_date", None)
                amt = float(sale.grand_total or 0)
                covers = rx_type_in_pkg and _pkg_covers(pkg_boundary, sale_dt)
                if covers:
                    pkg_pharmacy_covered_total += amt
                else:
                    pkg_pharmacy_total += amt
            pkg_pharmacy_total = round(pkg_pharmacy_total, 2)
            pkg_pharmacy_covered_total = round(pkg_pharmacy_covered_total, 2)

            # ---- Lab — per-order: covered iff package covers the test AND
            # the order was placed within the coverage window.
            pkg_lab_total = 0.0
            for raw, entry in zip(lab_orders, lab_entries):
                test_covered = _pkg_lab_covered(pkg, entry.get("test_id"))
                date_covered = _pkg_covers(pkg_boundary, getattr(raw, "order_date", None))
                covered = test_covered and date_covered
                entry["included_in_package"] = covered
                if not covered:
                    pkg_lab_total += float(entry.get("amount") or 0)
            pkg_lab_total = round(pkg_lab_total, 2)

            # Override display totals
            room_total = pkg_room_total
            visit_total = pkg_visit_total
            ot_total = pkg_ot_total
            ancillary_total = pkg_ancillary_total
            pharmacy_total = pkg_pharmacy_total
            lab_total = pkg_lab_total

            pkg_block = {
                "package_id": pkg.id,
                "package_name": pkg.package_name,
                "package_code": pkg.package_code,
                "agreed_price": float(pkg_assignment.agreed_price or 0),
                "included_services": list(included),
                "included_room_type": pkg.included_room_type,
                "included_stay_days": pkg.included_stay_days or 0,
                "included_room_rate": included_room_rate,
                "excess_per_day_charge": float(pkg.excess_per_day_charge or 0),
                "room_lines": pkg_room_lines,
                "lab_coverage_mode": (pkg.lab_coverage_mode or "all"),
                "included_lab_test_ids": list(pkg.included_lab_test_ids or []),
                "boundary_at": pkg_boundary.isoformat() if pkg_boundary else None,
                "fee_already_billed": pkg_fee_already_billed,
                "pharmacy_covered_total": pkg_pharmacy_covered_total,
                "_assignment_id": pkg_assignment.id,
            }

    # Bill subtotal = excess + agreed_price (when applicable). Agreed_price
    # is part of the inpatient bill — not collected separately. On finalize
    # after an interim that already billed the package fee, we skip it.
    subtotal = round(
        room_total + visit_total + ot_total + ancillary_total
        + pharmacy_total + lab_total + food_total,
        2,
    )
    include_agreed_price = bool(pkg_block) and not (unbilled_only and pkg_fee_already_billed)
    if include_agreed_price:
        subtotal = round(subtotal + pkg_block["agreed_price"], 2)

    return {
        "stay_days": stay_days,
        "billable_stay_days": billable_stay_days,
        "loa_days_skipped": loa_days_skipped,
        "room": {
            "room_number": room.room_number if room else "N/A",
            "room_type": room.room_type if room else "N/A",
            "charge_per_day": room_charge_per_day,
            "total": room_total,
            "full_total": full_room_total,
            "billed_so_far": billed_room_total,
            "loa_days_skipped": loa_days_skipped,
            "loa_credit": round(loa_credit, 2),
            "rate_segments": rate_segments,
        },
        "visits": visit_summary,
        "visit_total": visit_total,
        "ot_entries": ot_breakdown,
        "ot_total": ot_total,
        "ancillary_entries": ancillary_breakdown,
        "ancillary_total": ancillary_total,
        "pharmacy_total": pharmacy_total,
        "pharmacy_pos_entries": pharmacy_pos_entries,
        "lab_total": lab_total,
        "lab_entries": lab_entries,
        "food_entries": food_entries,
        "food_total": food_total,
        "room_total": room_total,
        "package": pkg_block,
        "subtotal": subtotal,
        # Source records (used by bill creation to tag with bill_id)
        "_visits": visits,
        "_ot": ot_entries,
        "_ancillary": anc_entries,
        "_pharmacy_rxs": pharmacy_rxs,
        "_pharmacy_pos_sales": pharmacy_pos_sales,
        "_lab_orders": lab_orders,
        "_food_orders": food_orders,
        "_room_unbilled_total": room_total if unbilled_only else 0.0,
        "_room_charge_per_day": room_charge_per_day,
        "_room": room,
        "_package": pkg_block,
        # Raw SurgeryPackage row, exposed so the bill writer can re-evaluate
        # per-test coverage when emitting BillItems.
        "_package_obj": pkg if pkg_block is not None else None,
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

    # Package totals are now baked into the breakdown by _compute_admission_charges
    # — preserve the previous response shape with excess_total / grand_total fields
    # for the frontend that consumes them.
    package_block = breakdown.get("package")
    if package_block:
        stay_days = breakdown["stay_days"]
        inc_days = package_block.get("included_stay_days") or 0
        days_remaining = max(inc_days - stay_days, 0)
        excess_days = max(stay_days - inc_days, 0)
        # Excess = bill subtotal minus the package fee (when the fee is
        # part of this bill — it isn't on a finalize-after-interim).
        agreed = float(package_block.get("agreed_price") or 0)
        fee_in_this_bill = not bool(package_block.get("fee_already_billed"))
        excess_total = round(breakdown["subtotal"] - (agreed if fee_in_this_bill else 0), 2)
        # Precise time-since-admission so the operator sees hours/minutes too,
        # not just whole days (the integer day count rounds up to 1 from minute
        # one of admission, which can mislead).
        admitted_at = admission.admission_date
        hours_since = None
        elapsed_label = None
        if admitted_at:
            now = datetime.now(admitted_at.tzinfo) if admitted_at.tzinfo else datetime.now()
            delta_secs = max((now - admitted_at).total_seconds(), 0)
            hours_since = round(delta_secs / 3600, 2)
            d = int(delta_secs // 86400)
            h = int((delta_secs % 86400) // 3600)
            m = int((delta_secs % 3600) // 60)
            if d > 0:
                elapsed_label = f"{d}d {h}h {m}m"
            elif h > 0:
                elapsed_label = f"{h}h {m}m"
            else:
                elapsed_label = f"{m}m"
        package_block = {
            **package_block,
            "days_elapsed": stay_days,
            "hours_since_admission": hours_since,
            "elapsed_label": elapsed_label,
            "admitted_at": admitted_at.isoformat() if admitted_at else None,
            "days_remaining_in_package": days_remaining,
            "excess_days": excess_days,
            "excess_room": breakdown["room_total"],
            "excess_total": excess_total,
            "grand_total": breakdown["subtotal"],
        }

    grand_total = breakdown["subtotal"]

    # Strip private keys before responding
    response_breakdown = {k: v for k, v in breakdown.items() if not k.startswith("_") and k != "package"}

    # Deposits received for this admission
    deposit_rows = db.query(AdmissionDeposit).filter(
        AdmissionDeposit.admission_id == admission_id
    ).order_by(AdmissionDeposit.received_at).all()
    deposits_list = [
        {
            "deposit_number": d.deposit_number or "",
            "date": d.received_at.strftime("%d/%m/%Y %H:%M") if d.received_at else "",
            "deposit_type": d.deposit_type or "initial",
            "method": d.payment_method or "cash",
            "reference": d.reference_number or "",
            "amount": float(d.amount or 0) if d.deposit_type != "refund" else -abs(float(d.amount or 0)),
        }
        for d in deposit_rows
    ]
    net_deposits = sum(float(d.amount or 0) if d.deposit_type != "refund" else -abs(float(d.amount or 0))
                       for d in deposit_rows)

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
        "deposits": deposits_list,
        "deposits_total": round(net_deposits, 2),
        "balance_due": round(grand_total - net_deposits, 2),
    }


@router.get("/admissions/{admission_id}/bills")
async def list_admission_bills(
    admission_id: int,
    include_cancelled: bool = False,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_bill")),
    db: Session = Depends(get_db),
):
    """Bill records (interim + final) for an admission, oldest-first.

    Cancelled bills are hidden by default — they're considered "removed" from
    the admission's billing view. Pass ``include_cancelled=true`` to surface
    them for audit. The billing dashboard's dedicated cancelled-history tab
    uses that flag.
    """
    q = db.query(Bill).filter(
        Bill.bill_type == "admission",
        Bill.reference_id == admission_id,
    )
    if not include_cancelled:
        q = q.filter(Bill.status != "cancelled")
    bills = q.order_by(Bill.bill_date.asc()).all()
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


class CancelAdmissionBillRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)


@router.post("/admissions/{admission_id}/bills/{bill_id}/cancel")
async def cancel_admission_bill(
    admission_id: int,
    bill_id: int,
    data: CancelAdmissionBillRequest,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "finalize_bill")),
    db: Session = Depends(get_db),
):
    """Cancel an admission bill (interim or final) and release every source
    item that was attached to it. After cancel, those items become eligible
    to be re-billed on the next interim/final bill. Cancellation is rejected
    if any payment has been recorded against the bill (refund first)."""
    bill = db.query(Bill).filter(
        Bill.id == bill_id,
        Bill.bill_type == "admission",
        Bill.reference_id == admission_id,
    ).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found for this admission")
    if bill.status == "cancelled":
        raise HTTPException(status_code=400, detail="Bill is already cancelled")

    # Block if any payment has been recorded — operator must refund through
    # the deposit/refund flow first to avoid silently breaking accounting.
    paid = sum(float(p.amount_paid or 0) for p in (bill.payments or []))
    if paid > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "bill_has_payments",
                "message": "Cannot cancel a bill with recorded payments. Refund through the deposit flow first.",
                "amount_paid": round(paid, 2),
            },
        )

    # Also block when any bill_split has been collected — those flow through
    # the BillSplit table, not the Payment table, so the paid-check above
    # misses TPA / insurance receipts.
    received_splits = db.query(BillSplit).filter(
        BillSplit.bill_id == bill.id,
        BillSplit.payment_status == "received",
    ).all()
    if received_splits:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "bill_splits_received",
                "message": "Cannot cancel — one or more payer splits have already been marked as received. Reverse those splits first.",
                "received_splits": [
                    {"id": s.id, "payer_type": s.payer_type, "payer_name": s.payer_name, "amount": float(s.amount or 0)}
                    for s in received_splits
                ],
            },
        )

    try:
        # Release every source row tagged with this bill_id so it can be billed again.
        visits_q = db.query(PatientVisit).filter(PatientVisit.bill_id == bill.id)
        visits_released = visits_q.count()
        visits_q.update({PatientVisit.billed: False, PatientVisit.bill_id: None}, synchronize_session=False)

        ot_q = db.query(OTSchedule).filter(OTSchedule.bill_id == bill.id)
        ot_released = ot_q.count()
        ot_q.update({OTSchedule.billed: False, OTSchedule.bill_id: None}, synchronize_session=False)

        anc_q = db.query(AdmissionAncillaryCharge).filter(AdmissionAncillaryCharge.bill_id == bill.id)
        anc_released = anc_q.count()
        anc_q.update({AdmissionAncillaryCharge.billed: False, AdmissionAncillaryCharge.bill_id: None}, synchronize_session=False)

        rx_q = db.query(Prescription).filter(Prescription.inpatient_bill_id == bill.id)
        rx_released = rx_q.count()
        rx_q.update({Prescription.inpatient_bill_id: None}, synchronize_session=False)

        pos_q = db.query(PharmacySale).filter(PharmacySale.inpatient_bill_id == bill.id)
        pos_released = pos_q.count()
        pos_q.update({PharmacySale.inpatient_bill_id: None}, synchronize_session=False)

        lab_q = db.query(PatientLabOrder).filter(PatientLabOrder.inpatient_bill_id == bill.id)
        lab_released = lab_q.count()
        lab_q.update({PatientLabOrder.inpatient_bill_id: None}, synchronize_session=False)

        food_q = db.query(FoodOrder).filter(FoodOrder.bill_id == bill.id)
        food_released = food_q.count()
        food_q.update({FoodOrder.billed: False, FoodOrder.bill_id: None}, synchronize_session=False)

        bill.status = "cancelled"
        cancel_note = f"[CANCELLED by user {current_user.id} on {datetime.now().isoformat()}]: {data.reason}"
        bill.notes = (bill.notes + "\n" if bill.notes else "") + cancel_note

        db.commit()
    except Exception:
        db.rollback()
        raise

    log_action(db, current_user, "cancel_admission_bill", "inpatient", "Bill", bill.id,
               f"Cancelled admission bill {bill.bill_number}: {data.reason}",
               details={
                   "admission_id": admission_id,
                   "bill_subtype": bill.bill_subtype,
                   "released": {
                       "visits": visits_released,
                       "ot": ot_released,
                       "ancillary": anc_released,
                       "prescriptions": rx_released,
                       "pharmacy_pos_sales": pos_released,
                       "lab_orders": lab_released,
                       "food_orders": food_released,
                   },
               })

    return {
        "message": f"Bill {bill.bill_number} cancelled",
        "bill_id": bill.id,
        "released": {
            "visits": visits_released,
            "ot": ot_released,
            "ancillary": anc_released,
            "prescriptions": rx_released,
            "pharmacy_pos_sales": pos_released,
            "lab_orders": lab_released,
            "food_orders": food_released,
        },
    }


def _create_admission_bill_record(
    db: Session, admission: Admission, hospital, current_user: User,
    breakdown: dict, discount_value: float, discount_type: str, tax_percentage: float,
    bill_subtype: str,
    items_override: Optional[List[BillItemOverride]] = None,
) -> Bill:
    """Transactional wrapper around _create_admission_bill_record_inner that
    rolls back on any failure so partial Bill+BillItems writes never leak.

    Also retries on ``IntegrityError`` so concurrent finalize calls that race on
    the ``BILL-ADM-{date}-{seq}`` MAX(seq)+1 read don't 500 — the loser simply
    re-reads and increments."""
    from sqlalchemy.exc import IntegrityError
    last_exc = None
    for _attempt in range(5):
        try:
            return _create_admission_bill_record_inner(
                db, admission, hospital, current_user, breakdown,
                discount_value, discount_type, tax_percentage, bill_subtype,
                items_override=items_override,
            )
        except IntegrityError as e:
            db.rollback()
            last_exc = e
            continue
        except Exception:
            db.rollback()
            raise
    # Exhausted retries — re-raise the last collision
    if last_exc is not None:
        raise last_exc


def _create_admission_bill_record_inner(
    db: Session, admission: Admission, hospital, current_user: User,
    breakdown: dict, discount_value: float, discount_type: str, tax_percentage: float,
    bill_subtype: str,
    items_override: Optional[List[BillItemOverride]] = None,
) -> Bill:
    """Persist a Bill + BillItems and tag source records with bill_id.
    `breakdown` is the dict returned by _compute_admission_charges(... unbilled_only=True).
    When `items_override` is provided, the bill lines come from there (operator
    has reviewed/edited them). Source records still get their bill_id stamped
    from `breakdown` so they're not re-billed on a subsequent interim/final."""
    if items_override is not None:
        subtotal = round(sum(float(i.total_price or 0) for i in items_override), 2)
    else:
        subtotal = breakdown["subtotal"]
    discount_amount = 0.0
    if discount_value and discount_value > 0:
        if discount_type == "percentage":
            # Clamp percentage to [0, 100] so we never go below zero.
            pct = min(max(float(discount_value), 0.0), 100.0)
            discount_amount = round(subtotal * pct / 100, 2)
        else:
            discount_amount = min(discount_value, subtotal)
    # Never let discount exceed subtotal (guards against operator-supplied
    # percentage > 100 or flat > subtotal slipping through).
    discount_amount = min(max(discount_amount, 0.0), subtotal)
    after_discount = max(subtotal - discount_amount, 0.0)
    tax_amount = 0.0
    if tax_percentage and tax_percentage > 0:
        tax_pct = min(max(float(tax_percentage), 0.0), 100.0)
        tax_amount = round(after_discount * tax_pct / 100, 2)
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

    # Override path: persist exactly what the operator submitted, then stamp
    # all source records from the breakdown so they don't reappear on a future
    # bill. Even items the operator removed/zeroed are stamped — the bill is
    # the operator's final say on what's billable for this admission slice.
    if items_override is not None:
        for it in items_override:
            db.add(BillItem(
                bill_id=bill.id,
                item_type=it.item_type,
                item_name=it.item_name,
                quantity=int(it.quantity or 1),
                unit_price=float(it.unit_price or 0),
                total_price=float(it.total_price or 0),
            ))
        for v in breakdown["_visits"]:
            v.billed = True
            v.bill_id = bill.id
        for ot in breakdown["_ot"]:
            ot.billed = True
            ot.bill_id = bill.id
        for c in breakdown["_ancillary"]:
            c.billed = True
            c.bill_id = bill.id
        for rx in breakdown["_pharmacy_rxs"]:
            rx.inpatient_bill_id = bill.id
        for sale in breakdown.get("_pharmacy_pos_sales", []):
            sale.inpatient_bill_id = bill.id
        for lo in breakdown["_lab_orders"]:
            lo.inpatient_bill_id = bill.id
        for f in breakdown.get("_food_orders", []):
            f.billed = True
            f.bill_id = bill.id
        db.commit()
        db.refresh(bill)
        return bill

    pkg = breakdown.get("_package")
    included = set(pkg["included_services"]) if pkg else set()
    # Resolve package coverage boundary (admission_date + included_stay_days)
    # so we know which items to bill as excess-stay.
    pkg_boundary_dt = None
    if pkg and pkg.get("boundary_at"):
        try:
            pkg_boundary_dt = datetime.fromisoformat(pkg["boundary_at"])
        except Exception:
            pkg_boundary_dt = None

    # Package fee — emit a single BillItem at agreed_price UNLESS a prior
    # non-cancelled bill on this admission already booked it (dedup so a
    # finalize after an interim doesn't double-bill).
    if pkg and not pkg.get("fee_already_billed"):
        db.add(BillItem(
            bill_id=bill.id,
            item_type="package",
            item_name=f"Surgery Package: {pkg['package_name']}" + (
                f" [{pkg['package_code']}]" if pkg.get('package_code') else ""
            ),
            quantity=1,
            unit_price=float(pkg["agreed_price"]),
            total_price=float(pkg["agreed_price"]),
        ))

    room = breakdown["_room"]
    if pkg and _PKG_CAT_ROOM in included:
        # Package covers room — emit per-segment upgrade/excess lines only.
        for line in pkg.get("room_lines", []):
            if (line.get("total") or 0) <= 0:
                continue
            db.add(BillItem(
                bill_id=bill.id,
                item_type="room_charge",
                item_name=line["label"],
                quantity=int(line.get("days") or 1),
                unit_price=float(line.get("rate") or 0),
                total_price=float(line.get("total") or 0),
            ))
    elif breakdown["room_total"] > 0 and room:
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
        type_in_pkg = _pkg_visit_included(v.visit_type, included)
        # Excess-stay visits (after pkg_boundary) bill even if type is included.
        is_excess_visit = bool(
            type_in_pkg and pkg_boundary_dt and v.visit_datetime and v.visit_datetime > pkg_boundary_dt
        )
        if (not type_in_pkg) or is_excess_visit:
            visit_label = f"{v.visit_type.replace('_', ' ').title()} - {visitor.first_name} {visitor.last_name}" if visitor else v.visit_type
            if is_excess_visit:
                visit_label += " (excess stay)"
            db.add(BillItem(
                bill_id=bill.id,
                item_type=v.visit_type,
                item_name=visit_label,
                quantity=1,
                unit_price=float(v.charge_amount or 0),
                total_price=float(v.charge_amount or 0),
            ))
        v.billed = True
        v.bill_id = bill.id

    # OT — covered iff package includes ot/surgery AND scheduled inside the
    # boundary; excess-stay procedures bill at the full rate.
    ot_type_in_pkg = _pkg_ot_included(included)
    for ot in breakdown["_ot"]:
        covers = ot_type_in_pkg and _pkg_covers(pkg_boundary_dt, getattr(ot, "scheduled_date", None))
        if not covers:
            label = f"OT: {ot.procedure_name}"
            if ot_type_in_pkg and not covers:
                label += " (excess stay)"
            db.add(BillItem(
                bill_id=bill.id,
                item_type="ot_procedure",
                item_name=label,
                quantity=1,
                unit_price=ot.total_charges,
                total_price=ot.total_charges,
            ))
        ot.billed = True
        ot.bill_id = bill.id

    # Ancillary — covered iff included AND charged inside the boundary.
    anc_type_in_pkg = _PKG_CAT_ANCILLARY in included
    for c in breakdown["_ancillary"]:
        covers = anc_type_in_pkg and _pkg_covers(pkg_boundary_dt, getattr(c, "charged_at", None))
        if not covers:
            svc = db.query(AncillaryServiceCatalog).filter(AncillaryServiceCatalog.id == c.service_id).first()
            label = f"{svc.service_name if svc else 'Service'} ({svc.category if svc else ''})"
            if anc_type_in_pkg and not covers:
                label += " (excess stay)"
            db.add(BillItem(
                bill_id=bill.id,
                item_type="ancillary",
                item_name=label,
                quantity=int(c.quantity) if float(c.quantity).is_integer() else 1,
                unit_price=float(c.unit_price or 0),
                total_price=float(c.total_amount or 0),
            ))
        c.billed = True
        c.bill_id = bill.id

    # Pharmacy — covered iff included AND dispensed/prescribed inside the
    # boundary. Each prescription decides independently.
    rx_type_in_pkg = _PKG_CAT_PHARMACY in included
    for rx in breakdown["_pharmacy_rxs"]:
        rx_dt = getattr(rx, "dispensed_date", None) or getattr(rx, "prescription_date", None)
        covers = rx_type_in_pkg and _pkg_covers(pkg_boundary_dt, rx_dt)
        if not covers:
            rx_items = db.query(PrescriptionItem).filter(PrescriptionItem.prescription_id == rx.id).all()
            for item in rx_items:
                qty = float(item.quantity_dispensed or 0)
                if qty <= 0:
                    continue
                line_total = round(float(item.unit_price or 0) * qty, 2)
                medicine = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
                label = f"Rx: {medicine.name if medicine else 'Medicine'} ({item.dosage or ''})"
                if rx_type_in_pkg and not covers:
                    label += " (excess stay)"
                db.add(BillItem(
                    bill_id=bill.id,
                    item_type="pharmacy",
                    item_name=label,
                    quantity=int(qty) if qty.is_integer() else qty,
                    unit_price=item.unit_price,
                    total_price=line_total,
                    source_ref_type="prescription_item",
                    source_ref_id=item.id,
                ))
        rx.inpatient_bill_id = bill.id

    for sale in breakdown.get("_pharmacy_pos_sales", []):
        sale_dt = getattr(sale, "sale_date", None)
        covers = rx_type_in_pkg and _pkg_covers(pkg_boundary_dt, sale_dt)
        if not covers:
            for item in (sale.items or []):
                med = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
                label = f"POS: {med.name if med else 'Medicine'} ({sale.sale_number})"
                if rx_type_in_pkg and not covers:
                    label += " (excess stay)"
                db.add(BillItem(
                    bill_id=bill.id,
                    item_type="pharmacy",
                    item_name=label,
                    quantity=float(item.quantity or 0),
                    unit_price=float(item.rate or 0),
                    total_price=float(item.line_total or 0),
                    source_ref_type="pharmacy_sale_item",
                    source_ref_id=item.id,
                ))
        sale.inpatient_bill_id = bill.id

    # Lab — covered iff per-test whitelist matches AND order is inside the
    # boundary. Either failing → bill at full rate.
    pkg_obj = breakdown.get("_package_obj")  # SurgeryPackage row when packaged
    for lo in breakdown["_lab_orders"]:
        test_covered = _pkg_lab_covered(pkg_obj, lo.test_id) if pkg_obj else False
        date_covered = _pkg_covers(pkg_boundary_dt, getattr(lo, "order_date", None))
        covered = test_covered and date_covered
        if not covered:
            test = db.query(LabTest).filter(LabTest.id == lo.test_id).first()
            label = f"Lab: {test.name if test else 'Test'} ({lo.order_number})"
            # Tag excess-stay specifically (test was in coverage but order was outside window)
            if pkg_obj and test_covered and not date_covered:
                label += " (excess stay)"
            db.add(BillItem(
                bill_id=bill.id,
                item_type="lab_test",
                item_name=label,
                quantity=1,
                unit_price=float(lo.amount or 0),
                total_price=float(lo.amount or 0),
            ))
        lo.inpatient_bill_id = bill.id

    for f in breakdown.get("_food_orders", []):
        db.add(BillItem(
            bill_id=bill.id,
            item_type="food",
            item_name=f"Meal: {f.meal_type.title()} on {f.meal_date.isoformat() if f.meal_date else ''}",
            quantity=1,
            unit_price=float(f.price or 0),
            total_price=float(f.price or 0),
        ))
        f.billed = True
        f.bill_id = bill.id

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

    # Uniqueness guard: an admission must not have two active final bills.
    # This blocks both concurrent finalize calls (lost update) and accidental
    # double-clicks. Cancelled bills are explicitly excluded so a corrected
    # final bill can be issued after a cancellation.
    existing_final = db.query(Bill).filter(
        Bill.bill_type == "admission",
        Bill.reference_id == admission_id,
        Bill.bill_subtype == "final",
        Bill.status != "cancelled",
    ).first()
    if existing_final:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "final_bill_exists",
                "message": "A final bill already exists for this admission. Cancel it first to issue a new one.",
                "bill_id": existing_final.id,
                "bill_number": existing_final.bill_number,
            },
        )

    breakdown = _compute_admission_charges(db, admission, unbilled_only=True)
    items_override = data.items_override if data else None
    # Allow finalize with NO new computed charges if the operator submitted an
    # explicit override (e.g. waiving everything but adding a single custom
    # line). Without an override, refuse so we don't create empty final bills.
    if breakdown["subtotal"] <= 0 and items_override is None:
        raise HTTPException(
            status_code=400,
            detail="No outstanding charges to finalize. All charges may already be on prior bills — the review dialog will let you confirm and close the admission.",
        )

    # Balance precheck — refuse to finalize unless deposits already cover the
    # would-be bill (within ₹0.01). The UI is expected to either collect the
    # owed amount / issue the refund first, or call /bill/finalize-and-settle
    # to do both atomically.
    draft_total = _compute_draft_final_bill_total(
        breakdown,
        discount_value=(data.discount_value if data else 0) or 0,
        discount_type=(data.discount_type if data else "flat") or "flat",
        tax_percentage=(data.tax_percentage if data else 0) or 0,
        items_override=items_override,
    )
    prior_summary = _admission_balance_summary(db, admission)
    # net_deposits = total_collected - total_refunded. With the draft total as
    # what *this* finalize would book, the post-finalize balance is:
    #   net_deposits - (billed_on_bills_before + draft_total)
    # We approximate already-billed-and-this-final as prior_billed + draft.
    prior_billed_on_bills = float(prior_summary.get("billed_on_bills") or 0)
    post_finalize_balance = round(
        float(prior_summary.get("net_deposits") or 0)
        - (prior_billed_on_bills + draft_total),
        2,
    )
    if abs(post_finalize_balance) >= 0.01:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "unsettled_balance",
                "message": (
                    "Settle the balance before finalising the bill. "
                    "Either collect/refund the difference first or use "
                    "/bill/finalize-and-settle to do both in one step."
                ),
                "draft_total": draft_total,
                "net_deposits": float(prior_summary.get("net_deposits") or 0),
                "balance": post_finalize_balance,
                "amount_to_collect": round(max(0.0, -post_finalize_balance), 2),
                "amount_to_refund": round(max(0.0, post_finalize_balance), 2),
            },
        )

    bill = _create_admission_bill_record(
        db, admission, hospital, current_user, breakdown,
        discount_value=(data.discount_value if data else 0) or 0,
        discount_type=(data.discount_type if data else "flat") or "flat",
        tax_percentage=(data.tax_percentage if data else 0) or 0,
        bill_subtype="final",
        items_override=items_override,
    )

    reconcile_admission_bill_statuses(db, admission_id)
    db.commit()
    db.refresh(bill)

    log_action(db, current_user, "finalize_admission_bill", "inpatient", "Bill", bill.id,
               f"Finalized admission bill {bill.bill_number} for {patient.first_name} {patient.last_name}",
               details={"admission_id": admission_id, "total": float(bill.total_amount)})

    # Compute the per-admission settle hint so the UI can prompt the operator
    # to collect or refund in one step.
    summary = _admission_balance_summary(db, admission)
    credit_balance = summary["balance"]  # +ve = patient credit, -ve = patient owes
    if credit_balance > 0.01:
        requires_action = "refund"
    elif credit_balance < -0.01:
        requires_action = "collect"
    else:
        requires_action = "none"

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
        "requires_action": requires_action,
        "credit_balance": round(credit_balance, 2),
        "amount_to_collect": round(max(0.0, -credit_balance), 2),
        "amount_to_refund": round(max(0.0, credit_balance), 2),
        "net_deposits": summary["net_deposits"],
        "total_billed": summary["total_billed"],
    }


@router.post("/admissions/{admission_id}/bill/finalize-and-settle")
async def finalize_and_settle_bill(
    admission_id: int,
    data: FinalizeAndSettleRequest,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "finalize_bill")),
    db: Session = Depends(get_db),
):
    """Atomic: insert a settle deposit/refund AND create the final bill so the
    admission lands at balance = 0 in a single transaction. Either both rows
    persist or neither does.

    Used by the Review Final Bill dialog when the operator clicks the inline
    Collect/Refund button.
    """
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first()
    hospital = _get_hospital(db, current_user)

    # Uniqueness guard — same as plain finalize.
    existing_final = db.query(Bill).filter(
        Bill.bill_type == "admission",
        Bill.reference_id == admission_id,
        Bill.bill_subtype == "final",
        Bill.status != "cancelled",
    ).first()
    if existing_final:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "final_bill_exists",
                "message": "A final bill already exists for this admission. Cancel it first to issue a new one.",
                "bill_id": existing_final.id,
                "bill_number": existing_final.bill_number,
            },
        )

    breakdown = _compute_admission_charges(db, admission, unbilled_only=True)
    items_override = data.items_override
    if breakdown["subtotal"] <= 0 and items_override is None:
        raise HTTPException(
            status_code=400,
            detail="No outstanding charges to finalize.",
        )

    # Verify the operator-supplied settle amount actually balances the bill.
    draft_total = _compute_draft_final_bill_total(
        breakdown,
        discount_value=data.discount_value or 0,
        discount_type=data.discount_type or "flat",
        tax_percentage=data.tax_percentage or 0,
        items_override=items_override,
    )
    prior_summary = _admission_balance_summary(db, admission)
    prior_billed_on_bills = float(prior_summary.get("billed_on_bills") or 0)
    net_deposits_before = float(prior_summary.get("net_deposits") or 0)

    settle = data.settle
    if settle.direction == "collect":
        net_deposits_after = round(net_deposits_before + float(settle.amount), 2)
    else:
        # Refund — guard against refunding more than the credit on hand even
        # after the bill is booked.
        post_bill_credit = round(net_deposits_before - (prior_billed_on_bills + draft_total), 2)
        if float(settle.amount) > post_bill_credit + 0.01:
            raise HTTPException(
                status_code=409,
                detail=f"Refund of Rs.{settle.amount:,.2f} exceeds the credit that will remain after this bill (Rs.{post_bill_credit:,.2f}).",
            )
        net_deposits_after = round(net_deposits_before - float(settle.amount), 2)
    post_finalize_balance = round(net_deposits_after - (prior_billed_on_bills + draft_total), 2)
    if abs(post_finalize_balance) >= 0.01:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "settle_amount_mismatch",
                "message": (
                    f"Settle amount Rs.{settle.amount:,.2f} doesn't balance the bill. "
                    f"Post-settle balance would be Rs.{post_finalize_balance:,.2f}."
                ),
                "draft_total": draft_total,
                "expected_collect": round(max(0.0, draft_total + prior_billed_on_bills - net_deposits_before), 2),
                "expected_refund": round(max(0.0, net_deposits_before - prior_billed_on_bills - draft_total), 2),
            },
        )

    # Insert the deposit/refund FIRST, then the bill. Both share this request's
    # transaction; if the bill creation fails we rollback the deposit too.
    def _settle_kwargs():
        return dict(
            admission_id=admission_id,
            deposit_number=_generate_deposit_number(db),
            amount=float(settle.amount),
            deposit_type=("refund" if settle.direction == "refund" else "topup"),
            payment_method=settle.payment_method,
            reference_number=settle.reference_number or _generate_txn_id(db),
            notes=settle.notes or ("Bill settle — refund" if settle.direction == "refund" else "Bill settle — collect"),
            received_by_id=current_user.id,
            hospital_id=hospital.id,
        )
    deposit = _insert_deposit_safely(db, _settle_kwargs)

    bill = _create_admission_bill_record(
        db, admission, hospital, current_user, breakdown,
        discount_value=data.discount_value or 0,
        discount_type=data.discount_type or "flat",
        tax_percentage=data.tax_percentage or 0,
        bill_subtype="final",
        items_override=items_override,
    )
    reconcile_admission_bill_statuses(db, admission_id)
    db.commit()
    db.refresh(bill)
    db.refresh(deposit)

    log_action(db, current_user, "finalize_and_settle_admission_bill", "inpatient", "Bill", bill.id,
               f"Finalized + settled admission bill {bill.bill_number} (settle Rs.{settle.amount:,.2f} {settle.direction}) for {patient.first_name} {patient.last_name}",
               details={
                   "admission_id": admission_id,
                   "total": float(bill.total_amount),
                   "settle_direction": settle.direction,
                   "settle_amount": float(settle.amount),
                   "deposit_id": deposit.id,
               })

    return {
        "bill_id": bill.id,
        "bill_number": bill.bill_number,
        "bill_subtype": bill.bill_subtype,
        "subtotal": float(bill.subtotal),
        "discount_amount": float(bill.discount_amount or 0),
        "tax_amount": float(bill.tax_amount or 0),
        "total_amount": float(bill.total_amount),
        "status": bill.status,
        "message": "Bill finalized and settled",
        "deposit_id": deposit.id,
        "deposit_number": deposit.deposit_number,
        "settle_direction": settle.direction,
        "settle_amount": float(settle.amount),
        "credit_balance": 0.0,
        "requires_action": "none",
        "amount_to_collect": 0.0,
        "amount_to_refund": 0.0,
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

    reconcile_admission_bill_statuses(db, admission_id)
    db.commit()
    db.refresh(bill)

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
    bill_id: Optional[int] = Query(default=None, description="Specific bill row to render (any status). Defaults to the latest non-cancelled bill."),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_bill")),
    db: Session = Depends(get_db),
):
    """Inpatient bill PDF — uses the live computed breakdown so it always
    shows itemised charges (room, visits, OT, ancillary, pharmacy, lab) even
    when the saved Bill snapshot stored category totals only. Falls back to
    a "preview" header when no Bill record exists yet.

    ``bill_id`` lets the operator print a specific historical bill — including
    cancelled ones — for audit. Cancelled bills are rendered with a CANCELLED
    watermark; interim bills render with an INTERIM watermark.
    """
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    if bill_id is not None:
        bill = db.query(Bill).filter(
            Bill.id == bill_id,
            Bill.bill_type == "admission",
            Bill.reference_id == admission.id,
        ).first()
        if not bill:
            raise HTTPException(status_code=404, detail="Bill not found for this admission")
    else:
        # Optional Bill record (may not exist — we still render a preview)
        bill = db.query(Bill).filter(
            Bill.bill_type == "admission",
            Bill.reference_id == admission.id,
            Bill.status != "cancelled",
        ).order_by(Bill.id.desc()).first()

    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first()
    hospital = _get_hospital(db, current_user)
    room = db.query(RoomManagement).filter(RoomManagement.id == admission.room_id).first()
    bed = db.query(Bed).filter(Bed.id == admission.bed_id).first() if admission.bed_id else None

    # Build itemised display rows from the computed breakdown.
    breakdown = _compute_admission_charges(db, admission, unbilled_only=False)
    pkg_block = breakdown.get("package")
    pkg_included = set(pkg_block.get("included_services") or []) if pkg_block else set()

    INCLUDED_TAG = "  [INCLUDED]"

    # Bucketed item collection so the printed bill always orders as:
    #   1. Package fee
    #   2. Included (covered-by-package) non-lab rows
    #   3. Excluded / excess / non-package non-lab rows
    #   4. Lab tests (included first, then excluded)
    bucket_included = []
    bucket_excluded = []
    bucket_lab_included = []
    bucket_lab_excluded = []
    bucket_package = []

    # ---- Room -------------------------------------------------------------
    room_info = breakdown.get("room") or {}
    room_segs = room_info.get("rate_segments") or []
    if pkg_block and _PKG_CAT_ROOM in pkg_included:
        # Show the COVERED portion of the room stay only: capped at
        # included_stay_days (or the actual stay, whichever is smaller).
        # Anything beyond that appears in pkg_block.room_lines as excess.
        stay_days_total = int(breakdown.get('billable_stay_days') or breakdown.get('stay_days') or 0)
        included_days_cap = int(pkg_block.get('included_stay_days') or 0)
        # included_stay_days=0 means "covers entire stay", so use full stay then.
        covered_days = stay_days_total if included_days_cap <= 0 else min(stay_days_total, included_days_cap)

        if room_segs and covered_days > 0:
            remaining = covered_days
            for seg in room_segs:
                if remaining <= 0:
                    break
                seg_days = min(int(seg['days']), remaining)
                if seg_days <= 0:
                    continue
                bucket_included.append({
                    "description": f"Room rent — {room_info.get('room_number')} ({room_info.get('room_type')}){INCLUDED_TAG}",
                    "qty": f"{seg_days} day(s)",
                    "rate": seg['rate'],
                    "amount": 0,
                })
                remaining -= seg_days
        elif covered_days > 0:
            bucket_included.append({
                "description": f"Room rent — {room_info.get('room_number')} ({room_info.get('room_type')}){INCLUDED_TAG}",
                "qty": f"{covered_days} day(s)",
                "rate": room_info.get('charge_per_day') or 0,
                "amount": 0,
            })
        for line in pkg_block.get("room_lines") or []:
            if (line.get('total') or 0) <= 0:
                continue
            bucket_excluded.append({
                "description": line.get('label') or "Room excess",
                "qty": f"{line.get('days') or 1} day(s)",
                "rate": line.get('rate') or 0,
                "amount": line.get('total') or 0,
            })
    elif room_segs:
        for seg in room_segs:
            bucket_excluded.append({
                "description": f"Room rent — {room_info.get('room_number')} ({room_info.get('room_type')})",
                "qty": f"{seg['days']} day(s)",
                "rate": seg['rate'],
                "amount": seg['total'],
            })
    elif breakdown.get("room_total", 0) > 0:
        bucket_excluded.append({
            "description": f"Room rent — {room_info.get('room_number')} ({room_info.get('room_type')})",
            "qty": f"{breakdown.get('stay_days', 0)} day(s)",
            "rate": room_info.get('charge_per_day') or 0,
            "amount": breakdown['room_total'],
        })

    # ---- Visits — emit a covered row and/or an excess-stay row per type.
    for vtype, vinfo in (breakdown.get("visits") or {}).items():
        if not vinfo or not vinfo.get('count'):
            continue
        type_label = vtype.replace('_', ' ').title()
        type_in_pkg = bool(vinfo.get("included_in_package")) or bool(vinfo.get("covered_count"))
        covered_count = int(vinfo.get("covered_count") or 0)
        billed_count = int(vinfo.get("billed_count") or 0)
        if pkg_block and type_in_pkg and (covered_count or billed_count):
            if covered_count:
                covered_orig = float(vinfo.get("covered_total_original") or 0)
                bucket_included.append({
                    "description": f"{type_label}{INCLUDED_TAG}",
                    "qty": f"× {covered_count}",
                    "rate": (covered_orig / covered_count) if covered_count else 0,
                    "amount": 0,
                })
            if billed_count:
                billed_total = float(vinfo.get("billed_total") or vinfo.get("total") or 0)
                bucket_excluded.append({
                    "description": f"{type_label} (excess stay)",
                    "qty": f"× {billed_count}",
                    "rate": (billed_total / billed_count) if billed_count else 0,
                    "amount": billed_total,
                })
        else:
            count = int(vinfo.get('count') or 0)
            total = float(vinfo.get('total') or 0)
            bucket_excluded.append({
                "description": type_label,
                "qty": f"× {count}",
                "rate": (total / count) if count else 0,
                "amount": total,
            })

    # ---- OT — one row per procedure with covered/excess tag.
    for ot in (breakdown.get("ot_entries") or []):
        covered = bool(ot.get("included_in_package"))
        ref_total = float(ot.get("original_total") if covered else ot.get("total") or 0)
        proc_name = ot.get('procedure', ot.get('procedure_name', 'Procedure'))
        suffix = INCLUDED_TAG if covered else (
            " (excess stay)" if pkg_block and _pkg_ot_included(pkg_included) else ""
        )
        row = {
            "description": f"OT — {proc_name}{suffix}",
            "qty": "1",
            "rate": ref_total,
            "amount": 0 if covered else float(ot.get('total') or 0),
        }
        (bucket_included if covered else bucket_excluded).append(row)

    # ---- Ancillary — itemised with covered/excess tag.
    for anc in (breakdown.get("ancillary_entries") or []):
        covered = bool(anc.get("included_in_package"))
        ref_total = float(anc.get("original_total") if covered else (anc.get("total_amount") or anc.get('total') or 0))
        suffix = INCLUDED_TAG if covered else (
            " (excess stay)" if pkg_block and _PKG_CAT_ANCILLARY in pkg_included else ""
        )
        row = {
            "description": f"Ancillary — {anc.get('service_name', 'Service')}{suffix}",
            "qty": str(anc.get('quantity', 1)),
            "rate": anc.get('unit_price', 0),
            "amount": 0 if covered else float(anc.get('total_amount') or anc.get('total') or 0),
        }
        (bucket_included if covered else bucket_excluded).append(row)

    # ---- Pharmacy — lump sums split into covered + billed.
    pharmacy_covered_total = float((pkg_block or {}).get("pharmacy_covered_total") or 0)
    if pharmacy_covered_total > 0:
        bucket_included.append({
            "description": "Pharmacy / Medications" + INCLUDED_TAG,
            "qty": "—",
            "rate": "",
            "amount": 0,
        })
    if breakdown.get("pharmacy_total", 0) > 0:
        excess_suffix = " (excess stay)" if pkg_block and _PKG_CAT_PHARMACY in pkg_included else ""
        bucket_excluded.append({
            "description": f"Pharmacy / Medications{excess_suffix}",
            "qty": "—",
            "rate": "",
            "amount": breakdown['pharmacy_total'],
        })

    # ---- Lab — one row per test. Included labs go in their own sub-bucket
    # ahead of excluded labs; the whole lab section is rendered AFTER all
    # non-lab rows so the bill ends with the lab listing.
    for lab in (breakdown.get("lab_entries") or []):
        covered = bool(lab.get("included_in_package"))
        amount = float(lab.get('amount') or 0)
        suffix = INCLUDED_TAG if covered else ""
        if not covered and pkg_block and _PKG_CAT_LAB in pkg_included:
            suffix = " (excess stay)" if not lab.get("test_excluded") else ""
        row = {
            "description": f"Lab — {lab.get('test_name', 'Test')} ({lab.get('order_number', '')}){suffix}",
            "qty": "1",
            "rate": amount,
            "amount": 0 if covered else amount,
        }
        (bucket_lab_included if covered else bucket_lab_excluded).append(row)

    # Catering — group meals by type for a compact view (excluded section).
    food_entries = breakdown.get("food_entries") or []
    if food_entries:
        food_by_type: dict = {}
        for f in food_entries:
            mt = f.get("meal_type", "meal")
            food_by_type.setdefault(mt, {"count": 0, "total": 0.0})
            food_by_type[mt]["count"] += 1
            food_by_type[mt]["total"] += float(f.get("price") or 0)
        for mt, info in food_by_type.items():
            rate = info["total"] / info["count"] if info["count"] else 0
            bucket_excluded.append({
                "description": f"Catering — {mt.title()}",
                "qty": f"× {info['count']}",
                "rate": rate,
                "amount": info["total"],
            })

    # ---- Package fee line (always at the very top when present).
    if pkg_block and float(pkg_block.get("agreed_price") or 0) > 0 \
            and not pkg_block.get("fee_already_billed"):
        pkg_label = f"Surgery Package: {pkg_block.get('package_name', '')}"
        if pkg_block.get("package_code"):
            pkg_label += f" [{pkg_block['package_code']}]"
        bucket_package.append({
            "description": pkg_label,
            "qty": "1",
            "rate": float(pkg_block["agreed_price"]),
            "amount": float(pkg_block["agreed_price"]),
        })

    # Final assembled order: package → included → excluded → lab (included → excluded)
    items = (
        bucket_package
        + bucket_included
        + bucket_excluded
        + bucket_lab_included
        + bucket_lab_excluded
    )

    # Totals — prefer the saved Bill snapshot when present; otherwise show the
    # live computed breakdown so a "preview" is still meaningful.
    if bill:
        subtotal = float(bill.subtotal or 0)
        discount = float(bill.discount_amount or 0)
        tax = float(bill.tax_amount or 0)
        total = float(bill.total_amount or 0)
        bill_number = bill.bill_number
        bill_date = bill.bill_date.strftime("%d/%m/%Y") if bill.bill_date else datetime.now().strftime("%d/%m/%Y")
        bill_subtype = bill.bill_subtype or 'final'
        status = bill.status or 'active'
    else:
        subtotal = float(breakdown.get('subtotal', 0))
        discount = 0.0
        tax = 0.0
        total = subtotal
        bill_number = f"PREVIEW-{admission.admission_number}"
        bill_date = datetime.now().strftime("%d/%m/%Y")
        bill_subtype = 'preview'
        status = 'not_finalized'

    # Deposit summary + balance (uses existing helper)
    bal = _admission_balance_summary(db, admission)
    deposits_total = float(bal.get('net_deposits', 0))
    # balance = net_deposits - total_billed; we want owes = total - deposits
    balance_due = total - deposits_total

    # Itemised deposit receipts — list each payment so the patient sees the
    # trail of payments collected before the final balance.
    deposit_rows = db.query(AdmissionDeposit).filter(
        AdmissionDeposit.admission_id == admission_id
    ).order_by(AdmissionDeposit.received_at).all()
    deposits_list = [
        {
            "deposit_number": d.deposit_number or "",
            "date": d.received_at.strftime("%d/%m/%Y %H:%M") if d.received_at else "",
            "deposit_type": d.deposit_type or "initial",
            "method": d.payment_method or "cash",
            "reference": d.reference_number or "",
            "amount": float(d.amount or 0) if d.deposit_type != "refund" else -abs(float(d.amount or 0)),
        }
        for d in deposit_rows
    ]

    # Doctor names (admitting / attending / referring)
    def _name(user_id):
        if not user_id:
            return None
        u = db.query(User).filter(User.id == user_id).first()
        if not u:
            return None
        return f"Dr. {u.first_name} {u.last_name}"

    admitting_doctor = _name(admission.admitting_doctor_id)
    attending_doctor = _name(admission.attending_physician_id)
    referring_doctor = _name(admission.referring_doctor_id) or admission.referring_external_name

    # Payer (if PayerScheme is wired in)
    payer_name = None
    payer_status = None
    if getattr(admission, 'payer_scheme_id', None):
        sch = db.query(PayerScheme).filter(PayerScheme.id == admission.payer_scheme_id).first()
        if sch:
            payer_name = sch.name
            payer_status = admission.scheme_approval_status

    # Discharge date if present
    discharge = db.query(DischargeRecord).filter(DischargeRecord.admission_id == admission_id).first()

    hospital_info = {
        "name": hospital.name,
        "address": hospital.address or "",
        "phone": hospital.phone or "",
        "email": hospital.email or "",
        "logo_url": hospital.logo_url if hasattr(hospital, "logo_url") else "",
        "hospital_subname": hospital.hospital_subname if hasattr(hospital, "hospital_subname") else "",
    }

    bill_data = {
        "bill_number": bill_number,
        "bill_date": bill_date,
        "bill_subtype": bill_subtype,
        "status": status,
        "patient": {
            "name": f"{patient.first_name} {patient.last_name}" if patient else "N/A",
            "mrn": patient.mrn if patient else "",
            "patient_id": patient.patient_id if patient else "",
            "age": _patient_age(patient),
            "age_display": _patient_age_display(patient),
            "gender": patient.gender if patient else "",
            "phone": patient.primary_phone if patient else "",
            "address": ", ".join(filter(None, [
                getattr(patient, "address_line1", None),
                getattr(patient, "address_line2", None),
                getattr(patient, "village", None),
                getattr(patient, "mandal", None),
                getattr(patient, "district", None),
            ])) if patient else "",
            "village": (getattr(patient, "village", None) or "") if patient else "",
            "district": (getattr(patient, "district", None) or "") if patient else "",
            "referred_by": getattr(patient, "referred_by", None),
        },
        "admission": {
            "admission_number": admission.admission_number,
            "ward": room.department if room else None,
            "room_number": room.room_number if room else None,
            "bed_label": (bed.bed_label if bed else admission.bed_number),
            "admitted_at": admission.admission_date.strftime("%d/%m/%Y %H:%M")
                if admission.admission_date else None,
            "discharged_at": (discharge.discharge_date.strftime("%d/%m/%Y %H:%M")
                if discharge and discharge.discharge_date else None),
            "length_of_stay": breakdown.get("stay_days", 0),
            "admitting_doctor": admitting_doctor,
            "attending_doctor": attending_doctor,
            "referring_doctor": referring_doctor,
            "payer": payer_name,
            "payer_status": payer_status,
            "scheme_member_id": getattr(admission, "scheme_member_id", None),
        },
        "items": items,
        "subtotal": subtotal,
        "discount": discount,
        "tax": tax,
        "total": total,
        "deposits": deposits_list,
        "deposits_total": deposits_total,
        "balance_due": balance_due,
        "prepared_by_name": f"{current_user.first_name} {current_user.last_name}",
    }

    pdf_buffer = pdf_service.generate_inpatient_bill_pdf(
        bill_data, hospital_info, **bill_pdf_gen_kwargs(db, current_user.hospital_id, 'inpatient_bill'))

    return StreamingResponse(
        io.BytesIO(pdf_buffer.getvalue()) if hasattr(pdf_buffer, "getvalue") else pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=bill_{bill_number}.pdf"}
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
            "inpatient_bill_id": order.inpatient_bill_id,
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


@router.get("/admissions/{admission_id}/medicines-lookup")
async def lookup_medicines_for_admission(
    admission_id: int,
    q: Optional[str] = Query(None, min_length=1),
    limit: int = Query(20, ge=1, le=50),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "prescribe_medications")),
    db: Session = Depends(get_db),
):
    """Search the pharmacy catalog from inpatient prescribing context.

    Does not require pharmacy-module permissions — mirrors lab-tests-available.
    Returns name + sale rate only (no stock levels).
    """
    from sqlalchemy import or_
    from app.utils.pharmacy_pricing import medicine_sale_rate

    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")

    query = db.query(Medicine).filter(
        Medicine.hospital_id == current_user.hospital_id,
        Medicine.is_active == True,  # noqa: E712
        Medicine.is_hidden == False,  # noqa: E712
    )
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(or_(
            Medicine.name.ilike(like),
            Medicine.generic_name.ilike(like),
            Medicine.medicine_code.ilike(like),
        ))
    else:
        return []

    medicines = query.order_by(Medicine.name).limit(limit).all()
    return [
        {
            "id": m.id,
            "name": m.name,
            "generic_name": m.generic_name,
            "strength": m.strength,
            "dosage_form": m.dosage_form,
            "medicine_code": m.medicine_code,
            "unit_price": medicine_sale_rate(m),
        }
        for m in medicines
    ]


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
    _require_accepted(admission)

    payload = data.dict(exclude_unset=True)
    is_abnormal, flags = _evaluate_vitals(payload)

    vitals = VitalSigns(
        admission_id=admission_id,
        patient_id=admission.patient_id,
        recorded_by_id=current_user.id,
        recorded_at=payload.pop("recorded_at", None) or _now_utc(),
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
    # Safety overrides (require accompanying override_reason). Each maps to a
    # distinct 409 the backend can return so the UI can target the right gate.
    force_allergy_override: bool = False
    force_duplicate_dose: bool = False
    override_reason: Optional[str] = None
    # Minimum window in minutes between two doses of the same medicine for the
    # same admission. 30 by default — caller can override per-PRN entry.
    duplicate_dose_window_minutes: int = Field(default=30, ge=1, le=720)


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
    _require_accepted(admission)

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


def _run_mar_safety_checks(db: Session, m: "MedicationAdministration", data: MARAdministerRequest,
                           current_user: User) -> list:
    """Run the four MAR safety wraps for a 'given' (or PRN) administration.
    Returns the list of forced gates so the route can audit-log them. Raises
    400/409 with structured detail for any unforced violation.

    Wraps:
      1. Allergy x-check — block if patient has an active drug allergy
         matching the medicine name or generic name (substring, case-insensitive).
         Override: force_allergy_override + override_reason.
      2. Narcotic / high-alert 2nd-witness — block if Medicine.is_narcotic or
         is_high_alert and no witness_id provided. Witness must be a different
         user from the administering nurse. No override — must provide witness.
      3. Duplicate-dose window — block if the same medicine was given to the
         same admission within `duplicate_dose_window_minutes` (default 30 min).
         Override: force_duplicate_dose + override_reason.
    Wraps run only when data.status == 'given' (skipped for missed/refused/held).
    """
    if data.status != "given":
        return []

    from app.models.pharmacy import Medicine as _Medicine
    from app.models.patient import PatientAllergy as _PatientAllergy

    forced_gates = []
    medicine = db.query(_Medicine).filter(_Medicine.id == m.medicine_id).first() if m.medicine_id else None

    # 1. Allergy x-check
    if medicine:
        names = [n.lower() for n in [medicine.name, medicine.generic_name] if n]
        active_drug_allergies = db.query(_PatientAllergy).filter(
            _PatientAllergy.patient_id == m.patient_id,
            _PatientAllergy.allergy_type == "drug",
            _PatientAllergy.is_active == True,
        ).all()
        matches = [a for a in active_drug_allergies
                   if any(a.allergen and a.allergen.lower() in n or n in a.allergen.lower()
                          for n in names)]
        if matches:
            if not data.force_allergy_override:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "allergy_match",
                        "message": "Patient has a recorded allergy matching this medication.",
                        "medicine": medicine.name,
                        "allergens": [a.allergen for a in matches],
                        "max_severity": max((a.severity for a in matches),
                                            key=lambda s: ["mild", "moderate", "severe", "anaphylaxis"].index(s)
                                                          if s in ["mild", "moderate", "severe", "anaphylaxis"] else 0),
                    },
                )
            forced_gates.append("allergy_match")

    # 2. Narcotic / high-alert 2nd-witness
    if medicine and (medicine.is_narcotic or medicine.is_high_alert):
        if not data.witness_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "witness_required",
                    "message": "Narcotic or high-alert medication requires a second-witness signature. Pass witness_id (must be a different user).",
                    "is_narcotic": bool(medicine.is_narcotic),
                    "is_high_alert": bool(medicine.is_high_alert),
                },
            )
        if data.witness_id == current_user.id:
            raise HTTPException(status_code=400,
                detail="Witness must be a different user from the administering nurse.")

    # 3. Duplicate-dose window
    if m.medicine_id:
        from datetime import timedelta as _td
        when = data.administered_at or _now_utc()
        window_start = when - _td(minutes=data.duplicate_dose_window_minutes)
        recent = db.query(MedicationAdministration).filter(
            MedicationAdministration.id != m.id,
            MedicationAdministration.admission_id == m.admission_id,
            MedicationAdministration.medicine_id == m.medicine_id,
            MedicationAdministration.status == "given",
            MedicationAdministration.administered_at >= window_start,
            MedicationAdministration.administered_at <= when,
        ).first()
        if recent:
            if not data.force_duplicate_dose:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "duplicate_dose",
                        "message": f"Same medication was administered within the last {data.duplicate_dose_window_minutes} minutes.",
                        "previous_administration_id": recent.id,
                        "previous_administered_at": recent.administered_at.isoformat() if recent.administered_at else None,
                        "window_minutes": data.duplicate_dose_window_minutes,
                    },
                )
            forced_gates.append("duplicate_dose")

    if forced_gates and not (data.override_reason and data.override_reason.strip()):
        raise HTTPException(status_code=400,
            detail=f"override_reason required when forcing safety gates: {', '.join(forced_gates)}")

    return forced_gates


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

    forced_gates = _run_mar_safety_checks(db, m, data, current_user)

    m.status = data.status
    m.administered_by_id = current_user.id
    m.administered_at = data.administered_at or _now_utc()
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

    audit_details = {"status": data.status, "is_prn": m.is_prn}
    if forced_gates:
        audit_details["forced_safety_gates"] = forced_gates
        audit_details["override_reason"] = data.override_reason
    log_action(
        db, current_user, "administer_medication", "inpatient", "MedicationAdministration", m.id,
        f"Marked dose as '{data.status}' for admission #{m.admission_id}",
        audit_details,
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
    _require_accepted(admission)

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
        administered_at=data.administered_at or _now_utc(),
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


def _insert_deposit_safely(db: Session, build_kwargs) -> AdmissionDeposit:
    """Insert an AdmissionDeposit, retrying on UNIQUE collisions of the
    auto-generated deposit_number / reference_number. `build_kwargs` is a
    callable that returns a fresh dict of column values — re-invoked on each
    retry so the seq numbers are re-rolled."""
    from sqlalchemy.exc import IntegrityError
    last_exc = None
    for _ in range(5):
        kwargs = build_kwargs()
        deposit = AdmissionDeposit(**kwargs)
        db.add(deposit)
        try:
            db.flush()
            return deposit
        except IntegrityError as e:
            db.rollback()
            last_exc = e
            continue
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Failed to allocate deposit number after retries")


def _generate_txn_id(db: Session) -> str:
    """Auto-generate a transaction ID when the user doesn't supply one."""
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"TXN-{today}-"
    last = db.query(AdmissionDeposit).filter(
        AdmissionDeposit.reference_number.like(f"{prefix}%")
    ).order_by(AdmissionDeposit.id.desc()).first()
    if last and last.reference_number:
        try:
            seq = int(last.reference_number.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
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
    # When a comprehensive final bill exists it already includes prior interim charges
    # — use only the final bill total to avoid double-counting with interim bills.
    final_bill = next((b for b in bills if b.bill_subtype == "final"), None)
    if final_bill:
        billed_from_bills = float(final_bill.total_amount or 0)
    else:
        billed_from_bills = sum(float(b.total_amount or 0) for b in bills)
    total_paid = 0.0
    for b in bills:
        for p in (b.payments or []):
            total_paid += float(p.amount_paid or 0)

    # Fold in any charges that aren't on a saved Bill row yet so the balance
    # reflects what the patient actually owes for services rendered. Without
    # this, an admission that never had its bill finalized shows total_billed=0
    # and the discharge gate misclassifies deposits as refundable credit.
    try:
        unbilled = _compute_admission_charges(db, admission, unbilled_only=True)
        unbilled_subtotal = float(unbilled.get("subtotal", 0) or 0)
    except Exception:
        unbilled_subtotal = 0.0
    total_billed = billed_from_bills + unbilled_subtotal

    return {
        "admission_id": admission.id,
        "admission_number": admission.admission_number,
        "total_collected": round(total_collected, 2),
        "total_refunded": round(total_refunded, 2),
        "net_deposits": round(net_deposits, 2),
        "total_billed": round(total_billed, 2),
        "billed_on_bills": round(billed_from_bills, 2),
        "unbilled_charges": round(unbilled_subtotal, 2),
        "total_paid": round(total_paid, 2),
        "balance": round(net_deposits - total_billed, 2),  # +ve = credit, -ve = patient owes
        "deposit_count": len(deposits),
        "bill_count": len(bills),
    }


def _admission_net_deposits(db: Session, admission_id: int) -> float:
    rows = db.query(AdmissionDeposit).filter(
        AdmissionDeposit.admission_id == admission_id
    ).all()
    return sum(
        float(d.amount) if d.deposit_type != "refund" else -abs(float(d.amount))
        for d in rows
    )


def allocate_deposits_to_bill(db: Session, bill: Bill) -> float:
    """Return the portion of the admission's net deposit pool that applies to
    *this* bill. Deposits are allocated oldest-bill-first, capped at each
    bill's outstanding (total - Payment rows on that bill). Bills are walked
    in id order. Returns 0 for non-admission or cancelled bills."""
    if (bill.bill_type or "") != "admission" or not bill.reference_id:
        return 0.0
    if (bill.status or "") == "cancelled":
        return 0.0
    remaining = _admission_net_deposits(db, bill.reference_id)
    if remaining <= 0:
        return 0.0
    siblings = db.query(Bill).filter(
        Bill.bill_type == "admission",
        Bill.reference_id == bill.reference_id,
        Bill.status != "cancelled",
    ).order_by(Bill.id.asc()).all()
    for b in siblings:
        payments_on_b = sum(float(p.amount_paid or 0) for p in (b.payments or []))
        outstanding = max(0.0, float(b.total_amount or 0) - payments_on_b)
        alloc = min(outstanding, remaining)
        if b.id == bill.id:
            return round(alloc, 2)
        remaining -= alloc
        if remaining <= 0:
            return 0.0
    return 0.0


def reconcile_admission_bill_statuses(db: Session, admission_id: int) -> None:
    """Recompute Bill.status for every non-cancelled admission bill, folding
    in both Payment rows and allocated AdmissionDeposit pool. Cascades
    PatientLabOrder.payment_status. Caller is responsible for committing."""
    bills = db.query(Bill).filter(
        Bill.bill_type == "admission",
        Bill.reference_id == admission_id,
        Bill.status != "cancelled",
    ).order_by(Bill.id.asc()).all()
    remaining = _admission_net_deposits(db, admission_id)
    if remaining < 0:
        remaining = 0.0
    for b in bills:
        payments_on_b = sum(float(p.amount_paid or 0) for p in (b.payments or []))
        total = float(b.total_amount or 0)
        outstanding = max(0.0, total - payments_on_b)
        alloc = min(outstanding, remaining)
        remaining -= alloc
        effective_paid = payments_on_b + alloc
        if effective_paid >= total - 0.01:
            b.status = "paid"
        elif effective_paid > 0.01:
            b.status = "partial"
        else:
            b.status = "pending"
        # Cascade lab order payment_status
        target = "paid" if b.status == "paid" else "pending"
        db.query(PatientLabOrder).filter(
            PatientLabOrder.inpatient_bill_id == b.id
        ).update({PatientLabOrder.payment_status: target}, synchronize_session=False)


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

    def _kwargs():
        return dict(
            admission_id=admission_id,
            deposit_number=_generate_deposit_number(db),
            amount=data.amount,
            deposit_type=data.deposit_type,
            payment_method=data.payment_method,
            reference_number=data.reference_number or _generate_txn_id(db),
            notes=data.notes,
            received_by_id=current_user.id,
            hospital_id=hospital.id,
        )
    deposit = _insert_deposit_safely(db, _kwargs)
    reconcile_admission_bill_statuses(db, admission_id)
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

    def _kwargs():
        return dict(
            admission_id=admission_id,
            deposit_number=_generate_deposit_number(db),
            amount=data.amount,  # stored positive; deposit_type marks it as refund
            deposit_type="refund",
            payment_method=data.payment_method,
            reference_number=data.reference_number or _generate_txn_id(db),
            notes=data.notes,
            received_by_id=current_user.id,
            hospital_id=hospital.id,
        )
    deposit = _insert_deposit_safely(db, _kwargs)
    reconcile_admission_bill_statuses(db, admission_id)
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
    # Guard against naive vs aware datetime arithmetic — SQLite-stored values
    # can come back naive even though we wrote them aware.
    received_at = d.received_at
    now = datetime.now(received_at.tzinfo) if received_at and received_at.tzinfo else datetime.now()
    if received_at and received_at.tzinfo is None and now.tzinfo is not None:
        now = now.replace(tzinfo=None)
    age_hours = ((now - received_at).total_seconds() / 3600) if received_at else 0
    if age_hours > 24:
        raise HTTPException(status_code=409, detail="Deposit older than 24h cannot be deleted; issue a refund instead")
    adm_id = d.admission_id
    snapshot = {
        "deposit_number": d.deposit_number,
        "amount": float(d.amount or 0),
        "deposit_type": d.deposit_type,
        "payment_method": d.payment_method,
        "reference_number": d.reference_number,
        "received_at": received_at.isoformat() if received_at else None,
    }
    db.delete(d)
    db.flush()
    reconcile_admission_bill_statuses(db, adm_id)
    db.commit()
    log_action(db, current_user, "delete_deposit", "inpatient", "AdmissionDeposit", deposit_id,
               f"Deleted deposit {snapshot.get('deposit_number')} (Rs.{snapshot['amount']:,.2f}) for admission {adm_id}",
               details={"admission_id": adm_id, **snapshot})


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


# ============================================================
# B1 — Payer scheme master CRUD
# ============================================================

PAYER_SCHEME_TYPES = {"cash", "private_insurance", "tpa", "govt_scheme"}


class PayerSchemeCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=200)
    scheme_type: str = Field(..., pattern=f"^({'|'.join(PAYER_SCHEME_TYPES)})$")
    active: bool = True
    notes: Optional[str] = None


class PayerSchemeUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=40)
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    scheme_type: Optional[str] = Field(default=None, pattern=f"^({'|'.join(PAYER_SCHEME_TYPES)})$")
    active: Optional[bool] = None
    notes: Optional[str] = None


class PayerSchemeResponse(BaseModel):
    id: int
    code: str
    name: str
    scheme_type: str
    active: bool
    notes: Optional[str]

    class Config:
        from_attributes = True


@router.get("/payer-schemes", response_model=List[PayerSchemeResponse])
async def list_payer_schemes(
    active_only: bool = True,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    q = db.query(PayerScheme).filter(PayerScheme.hospital_id == hospital.id)
    if active_only:
        q = q.filter(PayerScheme.active == True)
    return q.order_by(PayerScheme.scheme_type, PayerScheme.name).all()


@router.post("/payer-schemes", response_model=PayerSchemeResponse,
             status_code=status.HTTP_201_CREATED)
async def create_payer_scheme(
    data: PayerSchemeCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_payer_schemes")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    existing = db.query(PayerScheme).filter(
        PayerScheme.hospital_id == hospital.id,
        PayerScheme.code == data.code,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Payer scheme code '{data.code}' already exists")
    scheme = PayerScheme(hospital_id=hospital.id, **data.model_dump())
    db.add(scheme)
    db.commit()
    db.refresh(scheme)
    log_action(db, current_user, "create_payer_scheme", "inpatient",
               "PayerScheme", scheme.id, f"Created payer scheme {scheme.code} ({scheme.scheme_type})")
    return scheme


@router.put("/payer-schemes/{scheme_id}", response_model=PayerSchemeResponse)
async def update_payer_scheme(
    scheme_id: int,
    data: PayerSchemeUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_payer_schemes")),
    db: Session = Depends(get_db),
):
    scheme = db.query(PayerScheme).filter(PayerScheme.id == scheme_id).first()
    if not scheme:
        raise HTTPException(status_code=404, detail="Payer scheme not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(scheme, k, v)
    db.commit()
    db.refresh(scheme)
    log_action(db, current_user, "update_payer_scheme", "inpatient",
               "PayerScheme", scheme.id, f"Updated payer scheme {scheme.code}")
    return scheme


@router.delete("/payer-schemes/{scheme_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payer_scheme(
    scheme_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_payer_schemes")),
    db: Session = Depends(get_db),
):
    scheme = db.query(PayerScheme).filter(PayerScheme.id == scheme_id).first()
    if not scheme:
        raise HTTPException(status_code=404, detail="Payer scheme not found")
    # Soft-delete: keep referencing admissions intact, just deactivate the master entry.
    scheme.active = False
    db.commit()
    log_action(db, current_user, "delete_payer_scheme", "inpatient",
               "PayerScheme", scheme.id, f"Deactivated payer scheme {scheme.code}")


# ============================================================
# B2 — Convert payer mid-stay
# ============================================================

class PayerChangeRequest(BaseModel):
    payer_scheme_id: int
    reason: str = Field(..., min_length=1)
    scheme_member_id: Optional[str] = Field(default=None, max_length=100)
    scheme_approval_status: Optional[str] = Field(
        default=None, pattern="^(none|pending|approved|rejected|disconnected)$")
    scheme_approval_ref: Optional[str] = Field(default=None, max_length=100)
    scheme_approval_amount: Optional[float] = Field(default=None, ge=0)


@router.patch("/admissions/{admission_id}/payer")
async def convert_admission_payer(
    admission_id: int,
    data: PayerChangeRequest,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "convert_payer")),
    db: Session = Depends(get_db),
):
    """Switch an admission from one payer scheme to another mid-stay (e.g.,
    Aarogyasri rejected → Cash). Already-finalised bill splits remain
    immutable; subsequent charges go to the new payer."""
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    new_scheme = db.query(PayerScheme).filter(PayerScheme.id == data.payer_scheme_id).first()
    if not new_scheme:
        raise HTTPException(status_code=404, detail="Payer scheme not found")
    if not new_scheme.active:
        raise HTTPException(status_code=400, detail="Payer scheme is inactive")

    hospital = _get_hospital(db, current_user)
    history = AdmissionPayerChange(
        admission_id=admission.id,
        from_scheme_id=admission.payer_scheme_id,
        to_scheme_id=new_scheme.id,
        from_payer_type=admission.payer_type,
        to_payer_type=new_scheme.scheme_type,
        reason=data.reason,
        changed_by_id=current_user.id,
        hospital_id=hospital.id,
    )
    db.add(history)

    admission.payer_scheme_id = new_scheme.id
    admission.payer_type = new_scheme.scheme_type
    if data.scheme_member_id is not None:
        admission.scheme_member_id = data.scheme_member_id
    if data.scheme_approval_status is not None:
        admission.scheme_approval_status = data.scheme_approval_status
    if data.scheme_approval_ref is not None:
        admission.scheme_approval_ref = data.scheme_approval_ref
    if data.scheme_approval_amount is not None:
        admission.scheme_approval_amount = data.scheme_approval_amount

    db.commit()
    db.refresh(admission)
    log_action(db, current_user, "convert_payer", "inpatient",
               "Admission", admission.id,
               f"Payer converted: {history.from_payer_type or 'none'} → {history.to_payer_type}",
               details={"from_scheme_id": history.from_scheme_id,
                        "to_scheme_id": history.to_scheme_id,
                        "reason": data.reason})
    return {
        "admission_id": admission.id,
        "payer_scheme_id": admission.payer_scheme_id,
        "payer_type": admission.payer_type,
        "scheme_member_id": admission.scheme_member_id,
        "scheme_approval_status": admission.scheme_approval_status,
        "scheme_approval_ref": admission.scheme_approval_ref,
        "scheme_approval_amount": admission.scheme_approval_amount,
        "history_id": history.id,
    }


@router.get("/admissions/{admission_id}/payer-history")
async def list_payer_changes(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_bill")),
    db: Session = Depends(get_db),
):
    rows = db.query(AdmissionPayerChange).filter(
        AdmissionPayerChange.admission_id == admission_id
    ).order_by(AdmissionPayerChange.changed_at.desc()).all()
    out = []
    for r in rows:
        out.append({
            "id": r.id,
            "from_scheme_id": r.from_scheme_id,
            "from_scheme_name": r.from_scheme.name if r.from_scheme else None,
            "to_scheme_id": r.to_scheme_id,
            "to_scheme_name": r.to_scheme.name if r.to_scheme else None,
            "from_payer_type": r.from_payer_type,
            "to_payer_type": r.to_payer_type,
            "reason": r.reason,
            "changed_by_id": r.changed_by_id,
            "changed_by_name": (f"{r.changed_by.first_name} {r.changed_by.last_name}"
                                if r.changed_by else None),
            "changed_at": r.changed_at.isoformat() if r.changed_at else None,
        })
    return out


# ============================================================
# B3 — Accept / reject admission (IP doctor handshake)
# ============================================================

class AcceptanceDecision(BaseModel):
    accepting_doctor_id: Optional[int] = None  # defaults to current_user if omitted


class RejectionDecision(BaseModel):
    reason: str = Field(..., min_length=1)


def _can_act_on_acceptance(db: Session, user: User, admission: Admission) -> bool:
    """The IP-doctor acceptance gate. Allows:
       1. super / hospital / inpatient admins (role bypass)
       2. any user with the 'doctor' role — clinicians on the floor act as
          the IP doctor for incoming admissions; this is independent of
          whether their role row has been re-seeded with `accept_admission`
       3. the doctor assigned to this admission (admitting or attending)
       4. anyone with the `accept_admission` granular permission key
    """
    roles = set(user.role_names or [])
    if {"super_admin", "hospital_admin", "inpatient_admin"} & roles:
        return True
    if "doctor" in roles:
        return True
    if admission.admitting_doctor_id and admission.admitting_doctor_id == user.id:
        return True
    if admission.attending_physician_id and admission.attending_physician_id == user.id:
        return True
    # Granular permission lookup (mirrors require_feature_permission)
    from app.models.permissions import RoleModulePermission
    role_ids = [r.id for r in (user.roles or [])]
    if user.role_id and user.role_id not in role_ids:
        role_ids.append(user.role_id)
    for rid in role_ids:
        rp = db.query(RoleModulePermission).filter(
            RoleModulePermission.role_id == rid,
            RoleModulePermission.module_name == Modules.INPATIENT,
        ).first()
        if rp and rp.permissions and "accept_admission" in rp.permissions:
            return True
    return False


@router.post("/admissions/{admission_id}/accept")
async def accept_admission(
    admission_id: int,
    data: AcceptanceDecision,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if not _can_act_on_acceptance(db, current_user, admission):
        raise HTTPException(status_code=403,
            detail="Only the admitting/attending doctor or an admin can accept this admission")
    if admission.acceptance_status == "accepted":
        return {"admission_id": admission.id, "acceptance_status": "accepted",
                "accepted_at": admission.accepted_at.isoformat() if admission.accepted_at else None}
    if admission.acceptance_status == "rejected":
        raise HTTPException(status_code=400, detail="Admission was rejected — re-admit the patient instead")
    admission.acceptance_status = "accepted"
    admission.accepted_by_doctor_id = data.accepting_doctor_id or current_user.id
    admission.accepted_at = datetime.utcnow()
    db.commit()
    db.refresh(admission)
    log_action(db, current_user, "accept_admission", "inpatient",
               "Admission", admission.id, "Admission accepted by IP doctor")
    return {"admission_id": admission.id, "acceptance_status": admission.acceptance_status,
            "accepted_by_doctor_id": admission.accepted_by_doctor_id,
            "accepted_at": admission.accepted_at.isoformat() if admission.accepted_at else None}


@router.post("/admissions/{admission_id}/reject")
async def reject_admission(
    admission_id: int,
    data: RejectionDecision,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if not _can_act_on_acceptance(db, current_user, admission):
        raise HTTPException(status_code=403,
            detail="Only the admitting/attending doctor or an admin can reject this admission")
    if admission.acceptance_status == "accepted":
        raise HTTPException(status_code=400,
            detail="Admission already accepted — use discharge flow instead")
    admission.acceptance_status = "rejected"
    admission.rejection_reason = data.reason
    admission.status = "rejected"
    db.commit()
    db.refresh(admission)
    log_action(db, current_user, "reject_admission", "inpatient",
               "Admission", admission.id, f"Admission rejected: {data.reason[:80]}")
    return {"admission_id": admission.id, "acceptance_status": admission.acceptance_status,
            "rejection_reason": admission.rejection_reason}


def _require_accepted(admission: Admission) -> None:
    """Raise 409 if clinical action is attempted before IP doctor accepts."""
    if admission.acceptance_status == "pending":
        raise HTTPException(status_code=409,
            detail="Admission is pending IP doctor acceptance — clinical actions are locked")
    if admission.acceptance_status == "rejected":
        raise HTTPException(status_code=409,
            detail="Admission was rejected — re-admit the patient first")


# ============================================================
# B6 — Gate pass
# ============================================================

class GatePassCreate(BaseModel):
    vehicle_no: Optional[str] = Field(default=None, max_length=40)
    attendant_name: Optional[str] = Field(default=None, max_length=200)
    attendant_relationship: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = None
    override_reason: Optional[str] = None  # required if balance > 0


@router.post("/admissions/{admission_id}/gate-pass", status_code=status.HTTP_201_CREATED)
async def create_gate_pass(
    admission_id: int,
    data: GatePassCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "issue_gate_pass")),
    db: Session = Depends(get_db),
):
    """Issue a printable gate pass for security at the exit. Requires that
    the patient is discharged and the bill balance is zero — or that an
    override reason is provided (e.g., 'insurance pending')."""
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    discharge = db.query(DischargeRecord).filter(
        DischargeRecord.admission_id == admission.id
    ).first()
    if not discharge:
        raise HTTPException(status_code=400,
            detail="Cannot issue gate pass — admission has no discharge record")
    existing = db.query(GatePass).filter(GatePass.admission_id == admission.id).first()
    if existing:
        raise HTTPException(status_code=400,
            detail=f"Gate pass already issued for this admission (#{existing.pass_number})")

    # Reconcile bill statuses against the current deposit pool first, so any
    # late-recorded deposit/refund is reflected before the gate.
    reconcile_admission_bill_statuses(db, admission.id)
    db.flush()

    # Outstanding bills = any non-cancelled admission bill not in 'paid' state.
    unpaid_bills = db.query(Bill).filter(
        Bill.bill_type == "admission",
        Bill.reference_id == admission.id,
        Bill.status.notin_(["paid", "cancelled"]),
    ).all()
    balance = _admission_balance_summary(db, admission)
    # outstanding = how much patient still owes (negative balance flipped); 0 if credit/zero
    outstanding = round(max(0.0, -balance["balance"]), 2)

    override = False
    if unpaid_bills or outstanding > 0.01:
        if not data.override_reason or not data.override_reason.strip():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "outstanding_bill",
                    "message": f"{len(unpaid_bills)} unpaid bill(s); outstanding ₹{outstanding:.2f}. Settle first or provide override_reason.",
                    "outstanding": outstanding,
                    "unpaid_bills": [
                        {"bill_id": b.id, "bill_number": b.bill_number, "status": b.status,
                         "total": float(b.total_amount or 0)}
                        for b in unpaid_bills
                    ],
                },
            )
        override = True

    hospital = _get_hospital(db, current_user)
    import uuid as _uuid
    pass_number = f"GP-{admission.admission_number}-{_uuid.uuid4().hex[:6].upper()}"
    gp = GatePass(
        admission_id=admission.id,
        pass_number=pass_number,
        generated_by_id=current_user.id,
        vehicle_no=data.vehicle_no,
        attendant_name=data.attendant_name,
        attendant_relationship=data.attendant_relationship,
        notes=data.notes,
        override_balance=override,
        override_reason=data.override_reason if override else None,
        outstanding_at_issue=outstanding,
        qr_token=_uuid.uuid4().hex,
        hospital_id=hospital.id,
    )
    db.add(gp)
    db.commit()
    db.refresh(gp)
    log_action(db, current_user, "issue_gate_pass", "inpatient",
               "GatePass", gp.id, f"Issued gate pass {gp.pass_number}"
               + (f" with override (₹{outstanding:.2f} outstanding)" if override else ""))
    return {
        "id": gp.id,
        "pass_number": gp.pass_number,
        "admission_id": gp.admission_id,
        "generated_at": gp.generated_at.isoformat() if gp.generated_at else None,
        "vehicle_no": gp.vehicle_no,
        "attendant_name": gp.attendant_name,
        "outstanding_at_issue": gp.outstanding_at_issue,
        "override_balance": gp.override_balance,
        "override_reason": gp.override_reason,
        "qr_token": gp.qr_token,
    }


@router.get("/admissions/{admission_id}/gate-pass")
async def get_gate_pass(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    gp = db.query(GatePass).filter(GatePass.admission_id == admission_id).first()
    if not gp:
        return None
    return {
        "id": gp.id,
        "pass_number": gp.pass_number,
        "admission_id": gp.admission_id,
        "generated_at": gp.generated_at.isoformat() if gp.generated_at else None,
        "vehicle_no": gp.vehicle_no,
        "attendant_name": gp.attendant_name,
        "attendant_relationship": gp.attendant_relationship,
        "notes": gp.notes,
        "outstanding_at_issue": gp.outstanding_at_issue,
        "override_balance": gp.override_balance,
        "override_reason": gp.override_reason,
        "qr_token": gp.qr_token,
    }


@router.get("/admissions/{admission_id}/gate-pass/pdf")
async def gate_pass_pdf(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    gp = db.query(GatePass).filter(GatePass.admission_id == admission_id).first()
    if not gp:
        raise HTTPException(status_code=404, detail="Gate pass not yet issued")
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first() if admission else None
    hospital = _get_hospital(db, current_user)
    hospital_info = {
        "name": hospital.name,
        "address": hospital.address or "",
        "phone": hospital.phone or "",
        "email": hospital.email or "",
        "logo_url": getattr(hospital, "logo_url", "") or "",
        "hospital_subname": getattr(hospital, "hospital_subname", "") or "",
    }
    payload = {
        "pass_number": gp.pass_number,
        "issued_at": gp.generated_at.strftime("%d/%m/%Y %H:%M") if gp.generated_at else "",
        "admission_number": admission.admission_number if admission else "",
        "patient_name": (f"{patient.first_name} {patient.last_name}" if patient else "-"),
        "mrn": (patient.mrn or "") if patient else "",
        "patient_id": patient.patient_id if patient else "-",
        "vehicle_no": gp.vehicle_no or "-",
        "attendant_name": gp.attendant_name or "-",
        "attendant_relationship": gp.attendant_relationship or "-",
        "outstanding_at_issue": gp.outstanding_at_issue or 0.0,
        "override_balance": gp.override_balance,
        "override_reason": gp.override_reason or "",
        "qr_token": gp.qr_token or "",
        "notes": gp.notes or "",
        "issued_by_name": f"{current_user.first_name} {current_user.last_name}".strip() or current_user.username,
    }
    pdf_buffer = pdf_service.generate_gate_pass_pdf(payload, hospital_info=hospital_info,
                                                    **pdf_gen_kwargs(db, current_user.hospital_id, 'gate_pass'))
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="gate-pass-{gp.pass_number}.pdf"'},
    )


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
    if bill.status == "cancelled":
        raise HTTPException(status_code=409, detail="Cannot split a cancelled bill")
    # Hospital scoping — prevent cross-tenant split mutation
    if getattr(bill, "hospital_id", None) and bill.hospital_id != _get_hospital(db, current_user).id:
        raise HTTPException(status_code=403, detail="Bill belongs to a different hospital")

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
    parent = db.query(Bill).filter(Bill.id == s.bill_id).first()
    if parent and parent.status == "cancelled":
        raise HTTPException(status_code=409, detail="Cannot record payment on a cancelled bill")
    if parent and getattr(parent, "hospital_id", None) and parent.hospital_id != _get_hospital(db, current_user).id:
        raise HTTPException(status_code=403, detail="Bill belongs to a different hospital")
    s.payment_status = "received"
    s.payment_date = _now_utc()
    if payment_reference:
        s.payment_reference = payment_reference
    if notes:
        s.notes = (s.notes or "") + ("\n" if s.notes else "") + notes
    db.flush()

    # If all splits on the parent bill are now received, mark the bill paid
    # and cascade payment_status onto consumed lab orders.
    bill = db.query(Bill).filter(Bill.id == s.bill_id).first()
    if bill and bill.status != "cancelled":
        all_splits = db.query(BillSplit).filter(BillSplit.bill_id == bill.id).all()
        if all_splits and all(sp.payment_status == "received" for sp in all_splits):
            bill.status = "paid"
            if (bill.bill_type or "") == "admission":
                db.query(PatientLabOrder).filter(
                    PatientLabOrder.inpatient_bill_id == bill.id
                ).update({PatientLabOrder.payment_status: "paid"}, synchronize_session=False)

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
    p.approval_date = _now_utc() if data.status == "approved" else p.approval_date
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
    exp.decided_at = _now_utc()

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


PKG_COVERAGE_MODES = {"all", "selected"}


class PackageCreate(BaseModel):
    package_name: str = Field(..., min_length=1, max_length=200)
    package_code: Optional[str] = Field(default=None, max_length=50)
    base_price: float = Field(..., ge=0)
    included_room_type: Optional[str] = Field(default=None, max_length=30)
    included_stay_days: int = Field(default=0, ge=0)
    included_services: Optional[List[str]] = None
    # Granular lab inclusion. Only meaningful when "lab" is in included_services.
    lab_coverage_mode: Optional[str] = Field(default="all", description="'all' or 'selected'")
    included_lab_test_ids: Optional[List[int]] = None
    excess_per_day_charge: float = Field(default=0.0, ge=0)
    description: Optional[str] = None


class PackageUpdate(BaseModel):
    package_name: Optional[str] = None
    package_code: Optional[str] = None
    base_price: Optional[float] = Field(default=None, ge=0)
    included_room_type: Optional[str] = None
    included_stay_days: Optional[int] = Field(default=None, ge=0)
    included_services: Optional[List[str]] = None
    lab_coverage_mode: Optional[str] = None
    included_lab_test_ids: Optional[List[int]] = None
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
    lab_coverage_mode: Optional[str] = "all"
    included_lab_test_ids: Optional[List[int]] = None
    excess_per_day_charge: float
    description: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


def _validate_lab_coverage(
    db: Session,
    hospital_id: int,
    included_services: Optional[List[str]],
    lab_coverage_mode: Optional[str],
    included_lab_test_ids: Optional[List[int]],
) -> tuple:
    """Normalize + validate the granular lab fields. Returns (mode, ids) ready
    to persist. Raises HTTPException on validation failure."""
    services = set(included_services or [])
    mode = (lab_coverage_mode or "all").lower()
    if mode not in PKG_COVERAGE_MODES:
        raise HTTPException(status_code=400, detail=f"lab_coverage_mode must be one of {sorted(PKG_COVERAGE_MODES)}")

    # If lab isn't in included_services, the granular fields are irrelevant.
    # Force back to a sane default so the DB doesn't carry confusing stale data.
    if "lab" not in services:
        return "all", None

    ids = list(included_lab_test_ids or [])
    if mode == "selected" and ids:
        # Validate every ID exists and belongs to this hospital.
        from app.models.lab import LabTest
        rows = db.query(LabTest.id).filter(
            LabTest.id.in_(ids),
            LabTest.hospital_id == hospital_id,
        ).all()
        found = {r[0] for r in rows}
        missing = [i for i in ids if i not in found]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Lab test IDs not found in this hospital: {missing}",
            )
    return mode, (ids or None)


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
    lab_mode, lab_ids = _validate_lab_coverage(
        db, hospital.id, data.included_services,
        data.lab_coverage_mode, data.included_lab_test_ids,
    )
    payload = data.model_dump()
    payload["lab_coverage_mode"] = lab_mode
    payload["included_lab_test_ids"] = lab_ids
    pkg = SurgeryPackage(hospital_id=hospital.id, **payload)
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
    # Re-normalize lab coverage when any related field is being touched OR when
    # included_services is changing (which can drop/add 'lab' silently).
    touches_lab_fields = any(k in update for k in ("included_services", "lab_coverage_mode", "included_lab_test_ids"))
    if touches_lab_fields:
        effective_services = update.get("included_services", pkg.included_services)
        effective_mode = update.get("lab_coverage_mode", pkg.lab_coverage_mode)
        effective_ids = update.get("included_lab_test_ids", pkg.included_lab_test_ids)
        lab_mode, lab_ids = _validate_lab_coverage(
            db, pkg.hospital_id, effective_services, effective_mode, effective_ids,
        )
        update["lab_coverage_mode"] = lab_mode
        update["included_lab_test_ids"] = lab_ids
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
    # Block when a non-cancelled admission bill already reflects this package —
    # the bill line items would no longer match what was finalised.
    existing_bill = db.query(Bill).filter(
        Bill.bill_type == "admission",
        Bill.reference_id == admission_id,
        Bill.status != "cancelled",
    ).first()
    if existing_bill:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "package_locked_by_bill",
                "message": "Cannot remove the package — a bill has already been generated with it. Cancel the bill first.",
                "bill_id": existing_bill.id,
                "bill_number": existing_bill.bill_number,
            },
        )
    pkg = db.query(SurgeryPackage).filter(SurgeryPackage.id == ap.package_id).first()
    snapshot = {
        "package_id": ap.package_id,
        "package_name": pkg.package_name if pkg else None,
        "agreed_price": float(ap.agreed_price or 0),
    }
    db.delete(ap)
    db.commit()
    log_action(db, current_user, "remove_admission_package", "inpatient", "AdmissionPackage", ap.id,
               f"Removed package '{snapshot.get('package_name')}' from admission {admission_id}",
               details={"admission_id": admission_id, **snapshot})


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
        charged_at=data.charged_at or _now_utc(),
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
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_bill")),
    db: Session = Depends(get_db),
):
    d = db.query(AdmissionDeposit).filter(AdmissionDeposit.id == deposit_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Deposit not found")
    admission = db.query(Admission).filter(Admission.id == d.admission_id).first()
    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first() if admission else None
    hospital = _get_hospital(db, current_user)

    received_by = db.query(User).filter(User.id == d.received_by_id).first() if d.received_by_id else None
    received_by_name = (
        f"{received_by.first_name} {received_by.last_name}".strip() or received_by.username
    ) if received_by else "-"
    deposit_data = {
        "deposit_number": d.deposit_number,
        "amount": float(d.amount),
        "deposit_type": d.deposit_type,
        "payment_method": d.payment_method,
        "reference_number": d.reference_number,
        "notes": d.notes,
        "received_at": d.received_at.strftime("%d/%m/%Y %H:%M") if d.received_at else "",
        "received_by_name": received_by_name,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "—",
        "mrn": (patient.mrn or "") if patient else "",
        "patient_id": patient.patient_id if patient else "—",
        "patient_phone": patient.primary_phone if patient else "",
        "village": (patient.village or "") if patient else "",
        "district": (patient.district or "") if patient else "",
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
    if (d.deposit_type or "").lower() == "refund":
        # Route to the dedicated refund template (red, all-caps amount, refund-specific layout).
        pdf_buffer = pdf_service.generate_refund_receipt_pdf(deposit_data, hospital_info, **pdf_gen_kwargs(db, current_user.hospital_id, 'refund_receipt'))
    else:
        pdf_buffer = pdf_service.generate_deposit_receipt_pdf(deposit_data, hospital_info, **pdf_gen_kwargs(db, current_user.hospital_id, 'deposit_receipt'))
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
    ConsentTemplate, Consent,
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

    from_room_for_rate = db.query(RoomManagement).filter(RoomManagement.id == admission.room_id).first()
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
        # Rate snapshots — locked at initiate-time so the patient is billed
        # by the rate that was in effect when the transfer was approved.
        from_room_charge_per_day=float(from_room_for_rate.room_charge_per_day) if from_room_for_rate else None,
        to_room_charge_per_day=float(new_room.room_charge_per_day) if new_room else None,
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

    # Lock target room and (if specified) target bed before claiming.
    new_room = db.query(RoomManagement).filter(
        RoomManagement.id == t.to_room_id
    ).with_for_update().first()
    if not new_room or new_room.available_beds <= 0:
        raise HTTPException(status_code=400, detail="No beds available in target room")

    target_bed = None
    if t.to_bed_id:
        target_bed = db.query(Bed).filter(
            Bed.id == t.to_bed_id, Bed.room_id == t.to_room_id
        ).with_for_update().first()
        if not target_bed:
            raise HTTPException(status_code=404, detail="Target bed not found")
        if target_bed.status != "available":
            raise HTTPException(status_code=400, detail=f"Target bed '{target_bed.bed_label}' is not available")
        if not _claim_bed_atomic(db, target_bed.id, t.to_room_id):
            db.rollback()
            raise HTTPException(status_code=409, detail="Target bed was just taken; cancel and re-initiate transfer")

    # Move bed accounting (only when actually changing rooms)
    old_room = db.query(RoomManagement).filter(
        RoomManagement.id == admission.room_id
    ).with_for_update().first()
    if old_room and t.to_room_id != admission.room_id:
        # Release old bed if structured
        if admission.bed_id:
            old_bed = db.query(Bed).filter(Bed.id == admission.bed_id).with_for_update().first()
            if old_bed and old_bed.current_admission_id == admission.id:
                old_bed.status = "cleaning"
                old_bed.current_admission_id = None
        # Recompute counts from Bed table where structured beds exist; else legacy +/- 1
        old_structured = db.query(Bed).filter(Bed.room_id == old_room.id).count()
        if old_structured > 0:
            old_room.available_beds = db.query(Bed).filter(
                Bed.room_id == old_room.id, Bed.status == "available"
            ).count()
        else:
            old_room.available_beds += 1
        old_room.is_occupied = old_room.available_beds == 0

        new_structured = db.query(Bed).filter(Bed.room_id == new_room.id).count()
        if new_structured > 0:
            new_room.available_beds = db.query(Bed).filter(
                Bed.room_id == new_room.id, Bed.status == "available"
            ).count()
        else:
            if not _decrement_room_available_atomic(db, new_room.id):
                db.rollback()
                raise HTTPException(status_code=409, detail="Target room ran out of beds during accept")
            db.refresh(new_room)
        new_room.is_occupied = new_room.available_beds == 0

    admission.room_id = t.to_room_id
    if t.to_bed_id:
        admission.bed_id = t.to_bed_id
        if target_bed:
            target_bed.current_admission_id = admission.id
    t.status = "accepted"
    t.accepted_at = _now_utc()
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

    # Resolve the room: prefer specific bed → specific room → any room of the
    # matching type with availability. Lock rows we intend to claim.
    room = None
    bed = None
    if r.bed_id:
        bed = db.query(Bed).filter(Bed.id == r.bed_id).with_for_update().first()
        if bed:
            room = db.query(RoomManagement).filter(
                RoomManagement.id == bed.room_id
            ).with_for_update().first()
    if not room and r.room_id:
        room = db.query(RoomManagement).filter(
            RoomManagement.id == r.room_id
        ).with_for_update().first()
    if not room and r.room_type:
        room = db.query(RoomManagement).filter(
            RoomManagement.room_type == r.room_type,
            RoomManagement.is_active == True,
            RoomManagement.available_beds > 0,
        ).order_by(RoomManagement.available_beds.desc()).with_for_update().first()
    if not room:
        raise HTTPException(status_code=400, detail="No matching room available")
    if room.available_beds <= 0:
        raise HTTPException(status_code=400, detail="Reserved room has no available beds")

    active = db.query(Admission).filter(
        Admission.patient_id == r.patient_id,
        Admission.status == "admitted",
    ).first()
    if active:
        raise HTTPException(status_code=400, detail="Patient already has an active admission")

    # Atomic bed claim — race-safe.
    if bed:
        if bed.status != "available":
            raise HTTPException(status_code=400, detail=f"Bed '{bed.bed_label}' is not available")
        if not _claim_bed_atomic(db, bed.id, room.id):
            db.rollback()
            raise HTTPException(status_code=409, detail="Reserved bed was just taken; pick another")

    hospital = _get_hospital(db, current_user)
    admission_number = _generate_admission_number(db)  # unified generator

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
        initial_room_charge_per_day=float(room.room_charge_per_day) if room else 0.0,
    )
    db.add(admission)

    # Sync room counts (structured) or atomic decrement (legacy).
    room_beds = db.query(Bed).filter(Bed.room_id == room.id).count()
    if room_beds > 0:
        room.available_beds = db.query(Bed).filter(
            Bed.room_id == room.id, Bed.status == "available"
        ).count()
    else:
        if not _decrement_room_available_atomic(db, room.id):
            db.rollback()
            raise HTTPException(status_code=409, detail="Room ran out of beds during conversion")
        db.refresh(room)
    if room.available_beds == 0:
        room.is_occupied = True

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

CONSENT_TYPES = {"surgical", "anaesthesia", "blood_transfusion", "high_risk_procedure", "general_treatment", "research", "face_sheet", "case_sheet_declaration"}
# Face/case sheets are part of the admit wizard — staff with admit_patients may print/record them.
ADMISSION_WIZARD_CONSENT_TYPES = frozenset({"face_sheet", "case_sheet_declaration"})


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
    # When the wizard pre-reserves a doc number via /consents/reserve-doc-number,
    # it sends it back here so the issued consent uses the same number that was
    # printed/written on the physical form.
    doc_number: Optional[str] = None


class ConsentWithdraw(BaseModel):
    withdrawal_reason: str = Field(..., min_length=1)


class ConsentResponse(BaseModel):
    id: int
    doc_number: Optional[str] = None
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.consent_type in ADMISSION_WIZARD_CONSENT_TYPES:
        allowed = (
            user_has_feature_permission(db, current_user, Modules.INPATIENT, "admit_patients")
            or user_has_feature_permission(db, current_user, Modules.INPATIENT, "record_consent")
        )
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail="Permission 'admit_patients' or 'record_consent' required on inpatient",
            )
    elif not user_has_feature_permission(db, current_user, Modules.INPATIENT, "record_consent"):
        raise HTTPException(
            status_code=403,
            detail="Permission 'record_consent' required on inpatient",
        )

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

    from app.models.inpatient import ConsentDocReservation
    payload = data.model_dump()
    requested_doc = payload.pop("doc_number", None)
    reservation = None
    if requested_doc:
        reservation = db.query(ConsentDocReservation).filter(
            ConsentDocReservation.doc_number == requested_doc,
            ConsentDocReservation.consumed_at.is_(None),
        ).first()
        # If the supplied number isn't a live reservation we silently fall
        # back to a fresh sequence to avoid collisions with already-issued
        # consents.
        doc_number = requested_doc if reservation else _generate_consent_doc_number(db)
    else:
        doc_number = _generate_consent_doc_number(db)

    c = Consent(
        admission_id=admission_id,
        patient_id=admission.patient_id,
        hospital_id=hospital.id,
        created_by_id=current_user.id,
        doc_number=doc_number,
        **payload,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    if reservation:
        reservation.consumed_at = datetime.now()
        reservation.consumed_consent_id = c.id
        db.commit()
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
    c.withdrawn_at = _now_utc()
    c.withdrawal_reason = data.withdrawal_reason
    db.commit()
    db.refresh(c)
    log_action(db, current_user, "withdraw_consent", "inpatient", "Consent", c.id,
               f"Withdrew consent — reason: {data.withdrawal_reason}")
    return _consent_to_response(c, db)


class ConsentReserveRequest(BaseModel):
    patient_id: str  # int Patient.id or UUID Patient.patient_id
    template_id: int
    consent_type: str = Field(..., pattern=f"^({'|'.join(CONSENT_TYPES)})$")


@router.post("/consents/reserve-doc-number")
async def reserve_consent_doc_number(
    data: ConsentReserveRequest,
    current_user: User = Depends(require_feature_permission_any(
        Modules.INPATIENT, "admit_patients", "record_consent"
    )),
    db: Session = Depends(get_db),
):
    """Allocate (and persist) a CS-YYYYMMDD-NNNN doc number before the
    consent record exists. Idempotent per patient + consent_type today —
    repeated calls return the same unconsumed reservation so refreshing
    the wizard doesn't burn numbers.
    """
    from app.models.inpatient import ConsentDocReservation
    patient = None
    if data.patient_id.isdigit():
        patient = db.query(Patient).filter(Patient.id == int(data.patient_id)).first()
    if not patient:
        patient = db.query(Patient).filter(Patient.patient_id == data.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    template = db.query(ConsentTemplate).filter(ConsentTemplate.id == data.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Consent template not found")

    today_prefix = f"CS-{datetime.now().strftime('%Y%m%d')}-"
    existing = db.query(ConsentDocReservation).filter(
        ConsentDocReservation.patient_id == patient.id,
        ConsentDocReservation.consent_type == data.consent_type,
        ConsentDocReservation.consumed_at.is_(None),
        ConsentDocReservation.doc_number.like(f"{today_prefix}%"),
    ).order_by(ConsentDocReservation.id.desc()).first()
    if existing:
        return {"doc_number": existing.doc_number, "reservation_id": existing.id}

    hospital = _get_hospital(db, current_user)
    res = ConsentDocReservation(
        doc_number=_generate_consent_doc_number(db),
        patient_id=patient.id,
        consent_type=data.consent_type,
        template_id=template.id,
        hospital_id=hospital.id,
        reserved_by_id=current_user.id,
    )
    db.add(res)
    db.commit()
    db.refresh(res)
    return {"doc_number": res.doc_number, "reservation_id": res.id}


@router.get("/consents/preview-pdf")
async def preview_consent_pdf(
    patient_id: str,
    template_id: int,
    room_id: Optional[int] = None,
    admitting_doctor_id: Optional[int] = None,
    referring_doctor_id: Optional[int] = None,
    admission_reason: Optional[str] = None,
    doc_number: Optional[str] = None,
    admission_id: Optional[int] = None,
    current_user: User = Depends(require_feature_permission_any(
        Modules.INPATIENT, "admit_patients", "record_consent"
    )),
    db: Session = Depends(get_db),
):
    """Generate a prefilled (unsigned) consent PDF for the admit wizard.

    When ``admission_id`` is supplied (post-admit declarations step), the
    printed form includes the real admission number, bed, and admission date.
    Without it, demographics are prefilled but admission number stays blank.
    No DB writes.
    """
    # patient_id may be either the integer Patient.id (what the admit wizard
    # holds) or the UUID Patient.patient_id — accept both.
    patient = None
    if patient_id.isdigit():
        patient = db.query(Patient).filter(Patient.id == int(patient_id)).first()
    if not patient:
        patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    template = db.query(ConsentTemplate).filter(ConsentTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Consent template not found")

    admission = None
    if admission_id is not None:
        admission = db.query(Admission).filter(Admission.id == admission_id).first()
        if not admission:
            raise HTTPException(status_code=404, detail="Admission not found")
        if admission.patient_id != patient.id:
            raise HTTPException(status_code=400, detail="Admission does not belong to this patient")

    effective_room_id = room_id or (admission.room_id if admission else None)
    effective_doctor_id = admitting_doctor_id or (admission.admitting_doctor_id if admission else None)
    effective_referring_id = referring_doctor_id or (admission.referring_doctor_id if admission else None)
    effective_reason = admission_reason or (admission.admission_reason if admission else None)

    room = db.query(RoomManagement).filter(RoomManagement.id == effective_room_id).first() if effective_room_id else None
    doctor = db.query(User).filter(User.id == effective_doctor_id).first() if effective_doctor_id else None
    referring_doctor = db.query(User).filter(User.id == effective_referring_id).first() if effective_referring_id else None
    if admission and admission.referring_external_name and not referring_doctor:
        referring_name_override = admission.referring_external_name
    else:
        referring_name_override = None
    hospital = _get_hospital(db, current_user)

    def _age_str(p):
        if p.age:
            return str(p.age)
        if p.date_of_birth:
            from datetime import date
            today = date.today()
            dob = p.date_of_birth
            return str(today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day)))
        return ""

    patient_name = f"{patient.first_name} {patient.last_name}".strip()
    doctor_name = f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else ""
    referring_name = (
        f"Dr. {referring_doctor.first_name} {referring_doctor.last_name}"
        if referring_doctor else (referring_name_override or "")
    )
    room_label = room.room_number if room else ""
    bed_label = ""
    if admission:
        bed_label = admission.bed_number or ""
        if not bed_label and admission.bed_id:
            bed_obj = db.query(Bed).filter(Bed.id == admission.bed_id).first()
            bed_label = bed_obj.bed_label if bed_obj else ""
    admission_number = admission.admission_number if admission else ""
    admission_date_str = (
        admission.admission_date.strftime("%d/%m/%Y")
        if admission and admission.admission_date
        else datetime.now().strftime("%d/%m/%Y")
    )
    token_ctx = {
        "patient_name": patient_name,
        "name": patient_name,
        "age": _age_str(patient),
        "gender": (patient.gender or "").title(),
        "sex": (patient.gender or "").title(),
        "mrn": getattr(patient, "mrn", None) or patient.patient_id,
        "patient_id": patient.patient_id,
        "primary_phone": getattr(patient, "primary_phone", None) or "",
        "phone": getattr(patient, "primary_phone", None) or "",
        "admission_number": admission_number,
        "admission_date": admission_date_str,
        "ward": getattr(room, "ward", "") if room else "",
        "room": room_label,
        "room_name": room_label,
        "room_number": room_label,
        "bed": bed_label,
        "admitting_doctor": doctor_name,
        "doctor": doctor_name,
        "doctor_name": doctor_name,
        "referring_doctor": referring_name,
        "admission_reason": effective_reason or "",
        "diagnosis": effective_reason or "",
        "emergency_contact_name": getattr(patient, "emergency_contact_name", None) or "",
        "emergency_contact_relation": getattr(patient, "emergency_contact_relation", None) or "",
        "emergency_contact_phone": getattr(patient, "emergency_contact_phone", None) or "",
        **_admitting_person_token_ctx(admission),
    }
    rendered_content = _substitute_template_tokens(template.content or "", token_ctx)

    consent_data = {
        "consent_type": template.consent_type,
        "doc_number": doc_number or _generate_consent_doc_number(db),
        "template_content": rendered_content,
        "procedure_name": "",
        "doctor_name": doctor_name,
        "risks_explained": "",
        "signed_by": "patient",
        "guardian_name": "",
        "guardian_relationship": "",
        "patient_signature": "",
        "patient_signature_type": None,
        "witness_name": "",
        "signed_at": "",
        "withdrawn_at": "",
        "withdrawal_reason": "",
        "patient_name": patient_name,
        "mrn": token_ctx["mrn"],
        "patient_id": patient.patient_id,
        "age": token_ctx["age"],
        "gender": token_ctx["gender"],
        "primary_phone": token_ctx["primary_phone"],
        "village": (patient.village or "") if patient else "",
        "district": (patient.district or "") if patient else "",
        "emergency_contact_name": token_ctx["emergency_contact_name"],
        "emergency_contact_relation": token_ctx["emergency_contact_relation"],
        "emergency_contact_phone": token_ctx["emergency_contact_phone"],
        "admission_number": admission_number,
        "admission_date": admission_date_str,
        "room_name": room_label,
        "room_type": room.room_type if room else "",
    }
    hospital_info = {
        "name": hospital.name,
        "address": hospital.address or "",
        "phone": hospital.phone or "",
        "email": hospital.email or "",
        "logo_url": getattr(hospital, "logo_url", "") or "",
        "hospital_subname": getattr(hospital, "hospital_subname", "") or "",
    }
    pdf_buffer = pdf_service.generate_consent_pdf(consent_data, hospital_info, **pdf_gen_kwargs(db, current_user.hospital_id, 'consent'))
    return _inline_pdf_response(pdf_buffer, f"consent-{template.consent_type}-preview.pdf")


@router.get("/consents/{consent_id}/pdf")
async def get_consent_pdf(
    consent_id: int,
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

    room = db.query(RoomManagement).filter(RoomManagement.id == admission.room_id).first() if admission and admission.room_id else None

    def _age_str(p):
        if p.age:
            return str(p.age)
        if p.date_of_birth:
            from datetime import date
            today = date.today()
            dob = p.date_of_birth
            return str(today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day)))
        return ""

    patient_name_full = f"{patient.first_name} {patient.last_name}".strip() if patient else ""
    doctor_name_full = f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else ""
    referring_doctor = (
        db.query(User).filter(User.id == admission.referring_doctor_id).first()
        if admission and admission.referring_doctor_id else None
    )
    referring_name_full = (
        f"Dr. {referring_doctor.first_name} {referring_doctor.last_name}"
        if referring_doctor
        else (admission.referring_external_name if admission and admission.referring_external_name else "")
    )
    token_ctx = {
        "patient_name": patient_name_full,
        "name": patient_name_full,
        "age": _age_str(patient) if patient else "",
        "gender": (patient.gender or "").title() if patient else "",
        "sex": (patient.gender or "").title() if patient else "",
        "mrn": (getattr(patient, "mrn", None) or (patient.patient_id if patient else "")),
        "patient_id": patient.patient_id if patient else "",
        "primary_phone": (getattr(patient, "primary_phone", None) or "") if patient else "",
        "phone": (getattr(patient, "primary_phone", None) or "") if patient else "",
        "admission_number": admission.admission_number if admission else "",
        "admission_date": admission.admission_date.strftime("%d/%m/%Y") if admission and admission.admission_date else "",
        "ward": getattr(room, "ward", "") if room else "",
        "room": room.room_number if room else "",
        "room_name": room.room_number if room else "",
        "room_number": room.room_number if room else "",
        "bed": "",
        "admitting_doctor": doctor_name_full,
        "doctor": doctor_name_full,
        "doctor_name": doctor_name_full,
        "referring_doctor": referring_name_full,
        "admission_reason": (admission.admission_reason or "") if admission else "",
        "diagnosis": (admission.admission_reason or "") if admission else "",
        "emergency_contact_name": (getattr(patient, "emergency_contact_name", None) or "") if patient else "",
        "emergency_contact_relation": (getattr(patient, "emergency_contact_relation", None) or "") if patient else "",
        "emergency_contact_phone": (getattr(patient, "emergency_contact_phone", None) or "") if patient else "",
        **_admitting_person_token_ctx(admission),
    }
    rendered_content = _substitute_template_tokens(template.content if template else "", token_ctx)
    consent_data = {
        "consent_type": c.consent_type,
        "doc_number": c.doc_number or "",
        "template_content": rendered_content,
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
        "mrn": getattr(patient, "mrn", None) or (patient.patient_id if patient else ""),
        "patient_id": patient.patient_id if patient else "",
        "village": (getattr(patient, "village", None) or "") if patient else "",
        "district": (getattr(patient, "district", None) or "") if patient else "",
        "age": _age_str(patient) if patient else "",
        "gender": (patient.gender or "").title() if patient else "",
        "primary_phone": getattr(patient, "primary_phone", None) or "",
        "emergency_contact_name": getattr(patient, "emergency_contact_name", None) or "",
        "emergency_contact_relation": getattr(patient, "emergency_contact_relation", None) or "",
        "emergency_contact_phone": getattr(patient, "emergency_contact_phone", None) or "",
        "admission_number": admission.admission_number if admission else "",
        "admission_date": admission.admission_date.strftime("%d/%m/%Y") if admission and admission.admission_date else "",
        "room_name": room.room_number if room else "",
        "room_type": room.room_type if room else "",
    }
    hospital_info = {
        "name": hospital.name,
        "address": hospital.address or "",
        "phone": hospital.phone or "",
        "email": hospital.email or "",
        "logo_url": getattr(hospital, "logo_url", "") or "",
        "hospital_subname": getattr(hospital, "hospital_subname", "") or "",
    }
    pdf_buffer = pdf_service.generate_consent_pdf(consent_data, hospital_info, **pdf_gen_kwargs(db, current_user.hospital_id, 'consent'))
    return _inline_pdf_response(pdf_buffer, f"consent-{c.id}.pdf")


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


# ============================================================
# DAMA — Discharge Against Medical Advice
# ============================================================

class DAMACreate(BaseModel):
    attending_doctor_id: int
    medical_advice_given: str = Field(..., min_length=1)
    risks_explained: str = Field(..., min_length=1)
    language_used: str = Field(default="english", max_length=30)
    patient_acknowledges_advice: bool
    patient_absolves_hospital: bool
    signed_by: str = Field(default="patient", pattern="^(patient|guardian)$")
    guardian_name: Optional[str] = Field(default=None, max_length=200)
    guardian_relationship: Optional[str] = Field(default=None, max_length=100)
    primary_signature: str = Field(..., min_length=1)
    primary_signature_type: str = Field(default="typed", pattern="^(typed|drawn)$")
    witness_name: str = Field(..., min_length=1, max_length=200)
    witness_designation: Optional[str] = Field(default=None, max_length=100)
    witness_signature: str = Field(..., min_length=1)
    witness_signature_type: str = Field(default="typed", pattern="^(typed|drawn)$")
    notes: Optional[str] = None


def _dama_to_response(d: DAMARecord, db: Session) -> dict:
    doctor = db.query(User).filter(User.id == d.attending_doctor_id).first()
    return {
        **{c.name: getattr(d, c.name) for c in d.__table__.columns},
        "attending_doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else None,
    }


@router.post("/admissions/{admission_id}/dama", status_code=status.HTTP_201_CREATED)
async def record_dama(
    admission_id: int,
    data: DAMACreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "discharge_patients")),
    db: Session = Depends(get_db),
):
    """Record the Discharge Against Medical Advice form for an admission that
    has already been discharged with discharge_type='against_advice'.
    Both acknowledgements (advice + absolves) must be True or 400."""
    if not (data.patient_acknowledges_advice and data.patient_absolves_hospital):
        raise HTTPException(
            status_code=400,
            detail="Both acknowledgements (advice given + absolves hospital) must be checked to file a DAMA form",
        )
    if data.signed_by == "guardian" and not (data.guardian_name and data.guardian_name.strip()):
        raise HTTPException(status_code=400, detail="guardian_name is required when signed_by='guardian'")

    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    discharge = db.query(DischargeRecord).filter(DischargeRecord.admission_id == admission_id).first()
    if not discharge:
        raise HTTPException(status_code=400, detail="Patient is not yet discharged — create discharge first")
    if discharge.discharge_type != "against_advice":
        raise HTTPException(
            status_code=400,
            detail=f"DAMA form is only valid for against_advice discharges (current: {discharge.discharge_type})",
        )
    existing = db.query(DAMARecord).filter(DAMARecord.discharge_id == discharge.id).first()
    if existing:
        raise HTTPException(status_code=409, detail="DAMA form already recorded for this discharge")

    hospital = _get_hospital(db, current_user)
    rec = DAMARecord(
        discharge_id=discharge.id,
        admission_id=admission_id,
        patient_id=admission.patient_id,
        attending_doctor_id=data.attending_doctor_id,
        medical_advice_given=data.medical_advice_given,
        risks_explained=data.risks_explained,
        language_used=data.language_used,
        patient_acknowledges_advice=True,
        patient_absolves_hospital=True,
        signed_by=data.signed_by,
        guardian_name=data.guardian_name,
        guardian_relationship=data.guardian_relationship,
        primary_signature=data.primary_signature,
        primary_signature_type=data.primary_signature_type,
        witness_name=data.witness_name,
        witness_designation=data.witness_designation,
        witness_signature=data.witness_signature,
        witness_signature_type=data.witness_signature_type,
        notes=data.notes,
        hospital_id=hospital.id,
        created_by_id=current_user.id,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    log_action(db, current_user, "record_dama", "inpatient", "DAMARecord", rec.id,
               f"Recorded DAMA form for admission {admission.admission_number}",
               details={"admission_id": admission_id, "signed_by": data.signed_by})
    return _dama_to_response(rec, db)


@router.get("/admissions/{admission_id}/dama")
async def get_dama(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    rec = db.query(DAMARecord).filter(DAMARecord.admission_id == admission_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="DAMA record not found")
    return _dama_to_response(rec, db)


@router.get("/admissions/{admission_id}/dama/pdf")
async def get_dama_pdf(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    rec = db.query(DAMARecord).filter(DAMARecord.admission_id == admission_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="DAMA record not found")
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    patient = db.query(Patient).filter(Patient.id == rec.patient_id).first()
    doctor = db.query(User).filter(User.id == rec.attending_doctor_id).first()
    discharge = db.query(DischargeRecord).filter(DischargeRecord.id == rec.discharge_id).first()
    hospital = _get_hospital(db, current_user)

    hospital_info = {
        "name": hospital.name,
        "address": hospital.address or "",
        "phone": hospital.phone or "",
        "email": hospital.email or "",
        "logo_url": getattr(hospital, "logo_url", "") or "",
        "hospital_subname": getattr(hospital, "hospital_subname", "") or "",
    }
    dama_data = {
        "admission_number": admission.admission_number if admission else "",
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "",
        "patient_id": patient.patient_id if patient else "",
        "age": _patient_age(patient) or "",
        "age_display": _patient_age_display(patient),
        "gender": patient.gender if patient else "",
        "village": (patient.village or "") if patient else "",
        "district": (patient.district or "") if patient else "",
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "",
        "admission_date": admission.admission_date.strftime("%d/%m/%Y") if admission and admission.admission_date else "",
        "discharge_date": discharge.discharge_date.strftime("%d/%m/%Y %H:%M") if discharge and discharge.discharge_date else "",
        "medical_advice_given": rec.medical_advice_given,
        "risks_explained": rec.risks_explained,
        "language_used": rec.language_used,
        "signed_by": rec.signed_by,
        "guardian_name": rec.guardian_name or "",
        "guardian_relationship": rec.guardian_relationship or "",
        "primary_signature": rec.primary_signature,
        "primary_signature_type": rec.primary_signature_type,
        "witness_name": rec.witness_name,
        "witness_designation": rec.witness_designation or "",
        "witness_signature": rec.witness_signature,
        "witness_signature_type": rec.witness_signature_type,
        "notes": rec.notes or "",
        "signed_at": rec.created_at.strftime("%d/%m/%Y %H:%M") if rec.created_at else "",
    }
    pdf_buffer = pdf_service.generate_dama_pdf(dama_data, hospital_info, **pdf_gen_kwargs(db, current_user.hospital_id, 'dama'))
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=DAMA_{admission.admission_number if admission else admission_id}.pdf"},
    )


@router.get("/admissions/{admission_id}/mlc/pdf")
async def get_mlc_register_pdf(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """B7.5 — MLC register entry / police intimation PDF."""
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if not admission.is_mlc:
        raise HTTPException(status_code=400, detail="This admission is not flagged as MLC")
    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first()
    doctor = db.query(User).filter(User.id == admission.admitting_doctor_id).first()
    hospital = _get_hospital(db, current_user)

    hospital_info = {
        "name": hospital.name, "address": hospital.address or "",
        "phone": hospital.phone or "", "email": hospital.email or "",
        "logo_url": getattr(hospital, "logo_url", "") or "",
        "hospital_subname": getattr(hospital, "hospital_subname", "") or "",
    }
    addr = ""
    if patient:
        parts = [p for p in [patient.address_line1, patient.village, patient.mandal, patient.district] if p]
        addr = ", ".join(parts) or (patient.address or "")
    mlc_data = {
        "mlc_number": admission.mlc_number,
        "mlc_type": admission.mlc_type,
        "police_station_informed": admission.police_station_informed,
        "mlc_informed_at": admission.mlc_informed_at.strftime("%d/%m/%Y %H:%M") if admission.mlc_informed_at else "",
        "admission_number": admission.admission_number,
        "admission_date": admission.admission_date.strftime("%d/%m/%Y %H:%M") if admission.admission_date else "",
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "",
        "age": _patient_age(patient) or "",
        "age_display": _patient_age_display(patient),
        "gender": patient.gender if patient else "",
        "phone": patient.primary_phone if patient else "",
        "address": addr,
        "brought_by": admission.emergency_contact or "",
        "arrival_mode": admission.arrival_mode or "",
        "ambulance_details": admission.ambulance_details or "",
        "chief_complaint": admission.chief_complaint or admission.admission_reason or "",
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "",
    }
    pdf_buffer = pdf_service.generate_mlc_register_pdf(mlc_data, hospital_info, **pdf_gen_kwargs(db, current_user.hospital_id, 'mlc_register'))
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=MLC_{admission.admission_number}.pdf"},
    )


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


# ============================================================
# E2 — Monthly outcomes (mortality + readmission + LOS + occupancy)
# ============================================================

def _age_band(age):
    """Bucket an age (years) into NABH-friendly bands. Returns 'unknown' if None."""
    if age is None:
        return "unknown"
    try:
        a = int(age)
    except (ValueError, TypeError):
        return "unknown"
    if a < 1:
        return "<1"
    if a <= 14:
        return "1-14"
    if a <= 30:
        return "15-30"
    if a <= 45:
        return "31-45"
    if a <= 60:
        return "46-60"
    if a <= 75:
        return "61-75"
    return ">75"


def _month_window(month_str: Optional[str]):
    """Resolve a 'YYYY-MM' string (or None → previous completed month) to a
    naive [start, end_exclusive) datetime tuple."""
    today = date.today()
    if month_str:
        try:
            year, mo = map(int, month_str.split("-"))
        except Exception:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")
        if not (1 <= mo <= 12) or year < 1900:
            raise HTTPException(status_code=400, detail="invalid month")
    else:
        # Previous completed month
        first_of_this = today.replace(day=1)
        from datetime import timedelta as _td
        last_of_prev = first_of_this - _td(days=1)
        year, mo = last_of_prev.year, last_of_prev.month

    start = datetime.combine(date(year, mo, 1), datetime.min.time())
    if mo == 12:
        end_exclusive = datetime.combine(date(year + 1, 1, 1), datetime.min.time())
    else:
        end_exclusive = datetime.combine(date(year, mo + 1, 1), datetime.min.time())
    return start, end_exclusive, year, mo


def _build_monthly_outcomes(db: Session, month_str: Optional[str]) -> dict:
    start, end_exclusive, year, mo = _month_window(month_str)

    # ---- Mortality ----
    deaths = db.query(DischargeRecord).join(
        Admission, Admission.id == DischargeRecord.admission_id,
    ).filter(
        DischargeRecord.discharge_type == "death",
        DischargeRecord.discharge_date >= start,
        DischargeRecord.discharge_date < end_exclusive,
    ).all()

    death_total = len(deaths)
    death_by_dept = {}
    death_by_diagnosis = {}
    death_by_age_band = {}
    death_by_gender = {}
    mlc_count = 0
    autopsy_count = 0
    for d in deaths:
        adm = db.query(Admission).filter(Admission.id == d.admission_id).first()
        patient = db.query(Patient).filter(Patient.id == adm.patient_id).first() if adm else None
        room = db.query(RoomManagement).filter(RoomManagement.id == adm.room_id).first() if adm else None
        dept = (room.department if room else None) or "—"
        death_by_dept[dept] = death_by_dept.get(dept, 0) + 1
        diag = (d.diagnosis_on_discharge or d.cause_of_death or "Unknown").strip()[:80]
        death_by_diagnosis[diag] = death_by_diagnosis.get(diag, 0) + 1
        band = _age_band(_patient_age(patient))
        death_by_age_band[band] = death_by_age_band.get(band, 0) + 1
        g = (patient.gender if patient else None) or "unknown"
        death_by_gender[g] = death_by_gender.get(g, 0) + 1
        if d.mlc_required:
            mlc_count += 1
        if d.autopsy_done:
            autopsy_count += 1

    # ---- All discharges in the window — denominator for mortality rate + LOS stats ----
    discharges = db.query(DischargeRecord).join(
        Admission, Admission.id == DischargeRecord.admission_id,
    ).filter(
        DischargeRecord.discharge_date >= start,
        DischargeRecord.discharge_date < end_exclusive,
    ).all()
    discharge_total = len(discharges)

    los_per_dept = {}      # dept → list of stay_days
    overall_los = []
    for d in discharges:
        if d.total_stay_days is None:
            continue
        overall_los.append(d.total_stay_days)
        adm = db.query(Admission).filter(Admission.id == d.admission_id).first()
        room = db.query(RoomManagement).filter(RoomManagement.id == adm.room_id).first() if adm else None
        dept = (room.department if room else None) or "—"
        los_per_dept.setdefault(dept, []).append(d.total_stay_days)

    def _stats(xs):
        if not xs:
            return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
        s = sorted(xs)
        n = len(s)
        return {
            "count": n,
            "mean": round(sum(s) / n, 1),
            "median": s[n // 2] if n % 2 else round((s[n // 2 - 1] + s[n // 2]) / 2, 1),
            "min": s[0],
            "max": s[-1],
        }

    los_overall = _stats(overall_los)
    los_by_dept = {dept: _stats(xs) for dept, xs in los_per_dept.items()}

    # ---- Readmissions: admissions in this window flagged as readmission ----
    readmissions = db.query(Admission).filter(
        Admission.is_readmission == True,
        Admission.admission_date >= start,
        Admission.admission_date < end_exclusive,
    ).all()
    readmission_total = len(readmissions)
    readmission_buckets = {"<=7": 0, "8-15": 0, "16-30": 0, ">30": 0}
    readmission_by_dept = {}
    readmission_by_diagnosis = {}
    for a in readmissions:
        days = a.days_since_last_discharge
        if days is None:
            continue
        if days <= 7:
            readmission_buckets["<=7"] += 1
        elif days <= 15:
            readmission_buckets["8-15"] += 1
        elif days <= 30:
            readmission_buckets["16-30"] += 1
        else:
            readmission_buckets[">30"] += 1
        room = db.query(RoomManagement).filter(RoomManagement.id == a.room_id).first()
        dept = (room.department if room else None) or "—"
        readmission_by_dept[dept] = readmission_by_dept.get(dept, 0) + 1
        # Diagnosis at the prior discharge if available
        if a.previous_admission_id:
            prev_disch = db.query(DischargeRecord).filter(
                DischargeRecord.admission_id == a.previous_admission_id
            ).first()
            if prev_disch and prev_disch.diagnosis_on_discharge:
                diag = prev_disch.diagnosis_on_discharge.strip()[:80]
                readmission_by_diagnosis[diag] = readmission_by_diagnosis.get(diag, 0) + 1

    # Total admissions in the month — denominator for readmission rate
    admissions_in_month = db.query(Admission).filter(
        Admission.admission_date >= start,
        Admission.admission_date < end_exclusive,
    ).count()

    # ---- Occupancy: average daily occupied beds across the month ----
    # For each day in window, count admissions whose admission_date <= day < discharge_date
    # (or still admitted). Cap at total beds for sanity.
    from datetime import timedelta as _td
    total_beds = sum(r.bed_count or 0 for r in db.query(RoomManagement).filter(
        RoomManagement.is_active == True
    ).all())
    occupancy_samples = []
    cur = start
    while cur < end_exclusive:
        next_day = cur + _td(days=1)
        occupied = db.query(Admission).filter(
            Admission.admission_date < next_day,
        ).count() - db.query(Admission).join(
            DischargeRecord, DischargeRecord.admission_id == Admission.id,
        ).filter(
            DischargeRecord.discharge_date < cur,
        ).count()
        occupancy_samples.append(min(max(occupied, 0), total_beds) if total_beds else max(occupied, 0))
        cur = next_day
    avg_occupancy = (sum(occupancy_samples) / len(occupancy_samples)) if occupancy_samples else 0
    occupancy_pct = (avg_occupancy * 100 / total_beds) if total_beds else 0

    return {
        "month": f"{year:04d}-{mo:02d}",
        "window": {"start": start.isoformat(), "end_exclusive": end_exclusive.isoformat()},
        "totals": {
            "admissions": admissions_in_month,
            "discharges": discharge_total,
            "deaths": death_total,
            "readmissions": readmission_total,
            "mortality_rate_pct": round(death_total * 100 / discharge_total, 2) if discharge_total else 0,
            "readmission_rate_pct": round(readmission_total * 100 / admissions_in_month, 2) if admissions_in_month else 0,
            "average_daily_occupancy": round(avg_occupancy, 1),
            "average_occupancy_pct": round(occupancy_pct, 1),
        },
        "mortality": {
            "by_department": death_by_dept,
            "by_diagnosis_top10": dict(sorted(death_by_diagnosis.items(), key=lambda x: -x[1])[:10]),
            "by_age_band": death_by_age_band,
            "by_gender": death_by_gender,
            "mlc_count": mlc_count,
            "autopsy_count": autopsy_count,
        },
        "readmissions": {
            "by_window_days": readmission_buckets,
            "by_department": readmission_by_dept,
            "by_diagnosis_top10": dict(sorted(readmission_by_diagnosis.items(), key=lambda x: -x[1])[:10]),
        },
        "length_of_stay": {
            "overall": los_overall,
            "by_department": los_by_dept,
        },
    }


@router.get("/reports/monthly-outcomes")
async def get_monthly_outcomes(
    month: Optional[str] = Query(default=None, description="YYYY-MM; defaults to last completed month"),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_mortality")),
    db: Session = Depends(get_db),
):
    """Aggregated mortality + readmission + LOS + occupancy for a calendar month.
    Defaults to the last completed month so the report is reproducible."""
    return _build_monthly_outcomes(db, month)


@router.get("/reports/monthly-outcomes/pdf")
async def get_monthly_outcomes_pdf(
    month: Optional[str] = Query(default=None),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_mortality")),
    db: Session = Depends(get_db),
):
    payload = _build_monthly_outcomes(db, month)
    hospital = _get_hospital(db, current_user)
    hospital_info = {
        "name": hospital.name, "address": hospital.address or "",
        "phone": hospital.phone or "", "email": hospital.email or "",
        "logo_url": getattr(hospital, "logo_url", "") or "",
        "hospital_subname": getattr(hospital, "hospital_subname", "") or "",
    }
    pdf_buffer = pdf_service.generate_monthly_outcomes_pdf(payload, hospital_info, **pdf_gen_kwargs(db, current_user.hospital_id, 'monthly_outcomes'))
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=outcomes_{payload['month']}.pdf"},
    )


# ============================================================
# E3 — Doctor productivity report
# ============================================================

def _build_doctor_productivity(db: Session, date_from: date, date_to: date,
                               doctor_id: Optional[int]) -> dict:
    """Per-doctor breakdown over [date_from, date_to] inclusive.
    If doctor_id is given, returns one row; else returns rows for every doctor
    that has any activity in the window."""
    from datetime import timedelta as _td
    start = datetime.combine(date_from, datetime.min.time())
    end_exclusive = datetime.combine(date_to, datetime.min.time()) + _td(days=1)

    # Collect candidate doctor ids: any user touching admissions/visits/OT in the window.
    if doctor_id:
        doctor_ids = {doctor_id}
    else:
        doctor_ids = set()
        for row in db.query(Admission.admitting_doctor_id).filter(
            Admission.admission_date >= start,
            Admission.admission_date < end_exclusive,
        ).all():
            if row[0]:
                doctor_ids.add(row[0])
        for row in db.query(PatientVisit.visitor_id).filter(
            PatientVisit.visit_datetime >= start,
            PatientVisit.visit_datetime < end_exclusive,
            PatientVisit.visit_type == "doctor_visit",
        ).all():
            if row[0]:
                doctor_ids.add(row[0])
        for row in db.query(OTSchedule.surgeon_id).filter(
            OTSchedule.scheduled_date >= start,
            OTSchedule.scheduled_date < end_exclusive,
        ).all():
            if row[0]:
                doctor_ids.add(row[0])
        for row in db.query(OTSchedule.anaesthetist_id).filter(
            OTSchedule.scheduled_date >= start,
            OTSchedule.scheduled_date < end_exclusive,
        ).all():
            if row[0]:
                doctor_ids.add(row[0])

    rows = []
    for did in sorted(doctor_ids):
        doc = db.query(User).filter(User.id == did).first()
        if not doc:
            continue

        # Admissions where this doctor was admitting in the window
        admissions_q = db.query(Admission).filter(
            Admission.admitting_doctor_id == did,
            Admission.admission_date >= start,
            Admission.admission_date < end_exclusive,
        )
        admissions_count = admissions_q.count()

        # Discharges in the window where this doctor was the admitting doctor
        # (regardless of when admitted)
        discharges_in_window = db.query(DischargeRecord).join(
            Admission, Admission.id == DischargeRecord.admission_id,
        ).filter(
            Admission.admitting_doctor_id == did,
            DischargeRecord.discharge_date >= start,
            DischargeRecord.discharge_date < end_exclusive,
        ).all()
        discharges_count = len(discharges_in_window)

        # Mortality + readmissions among those discharges
        mortality_count = sum(1 for d in discharges_in_window if d.discharge_type == "death")
        # Readmission count: admissions in the window where prior admission's
        # admitting_doctor was this doctor.
        readmissions = db.query(Admission).filter(
            Admission.is_readmission == True,
            Admission.admission_date >= start,
            Admission.admission_date < end_exclusive,
            Admission.previous_admission_id.isnot(None),
        ).all()
        readmission_count = 0
        for r in readmissions:
            prev = db.query(Admission).filter(Admission.id == r.previous_admission_id).first()
            if prev and prev.admitting_doctor_id == did:
                readmission_count += 1

        # OT cases — surgeon vs anaesthetist split
        surgeon_ot_count = db.query(OTSchedule).filter(
            OTSchedule.surgeon_id == did,
            OTSchedule.scheduled_date >= start,
            OTSchedule.scheduled_date < end_exclusive,
        ).count()
        anaesthetist_ot_count = db.query(OTSchedule).filter(
            OTSchedule.anaesthetist_id == did,
            OTSchedule.scheduled_date >= start,
            OTSchedule.scheduled_date < end_exclusive,
        ).count()

        # Visits in the window
        visits = db.query(PatientVisit).filter(
            PatientVisit.visitor_id == did,
            PatientVisit.visit_datetime >= start,
            PatientVisit.visit_datetime < end_exclusive,
        ).all()
        visits_count = len(visits)
        visits_billed_total = sum(float(v.charge_amount or 0) for v in visits)

        # OT fees attributable to this doctor
        ot_surgeon_fees = sum(
            float(o.surgeon_fee or 0)
            for o in db.query(OTSchedule).filter(
                OTSchedule.surgeon_id == did,
                OTSchedule.scheduled_date >= start,
                OTSchedule.scheduled_date < end_exclusive,
                OTSchedule.status == "completed",
            ).all()
        )
        ot_anaesthetist_fees = sum(
            float(o.anaesthetist_fee or 0)
            for o in db.query(OTSchedule).filter(
                OTSchedule.anaesthetist_id == did,
                OTSchedule.scheduled_date >= start,
                OTSchedule.scheduled_date < end_exclusive,
                OTSchedule.status == "completed",
            ).all()
        )

        # Average LOS for this doctor's discharged-in-window patients
        los_values = [d.total_stay_days for d in discharges_in_window if d.total_stay_days is not None]
        avg_los = round(sum(los_values) / len(los_values), 1) if los_values else None

        rows.append({
            "doctor_id": did,
            "doctor_name": f"Dr. {doc.first_name} {doc.last_name}",
            "admissions": admissions_count,
            "discharges": discharges_count,
            "deaths": mortality_count,
            "readmissions_30d": readmission_count,
            "ot_as_surgeon": surgeon_ot_count,
            "ot_as_anaesthetist": anaesthetist_ot_count,
            "visits": visits_count,
            "average_los_days": avg_los,
            "visit_fees_billed": round(visits_billed_total, 2),
            "ot_surgeon_fees": round(ot_surgeon_fees, 2),
            "ot_anaesthetist_fees": round(ot_anaesthetist_fees, 2),
            "total_billed_attributable": round(visits_billed_total + ot_surgeon_fees + ot_anaesthetist_fees, 2),
        })

    rows.sort(key=lambda x: -x["total_billed_attributable"])

    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "doctor_count": len(rows),
        "rows": rows,
    }


def _validate_date_range(date_from: date, date_to: date):
    if date_to < date_from:
        raise HTTPException(status_code=400, detail="date_to must be on or after date_from")
    from datetime import timedelta as _td
    if (date_to - date_from) > _td(days=366):
        raise HTTPException(status_code=400, detail="Date range cannot exceed 366 days")


@router.get("/reports/doctor-productivity")
async def get_doctor_productivity(
    date_from: date = Query(...),
    date_to: date = Query(...),
    doctor_id: Optional[int] = Query(default=None),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """Per-doctor breakdown of admissions, discharges, OT cases, visits,
    LOS, mortality, readmissions, and total fees attributable.

    Note on attribution: total_billed_attributable = sum of this doctor's
    PatientVisit.charge_amount + their OTSchedule.surgeon_fee (for OTs they
    led) + their OTSchedule.anaesthetist_fee. Outpatient consultation fees
    are NOT included (separate module). Doctors who only consulted on a
    case via PatientVisit get credit for those visit charges only."""
    _validate_date_range(date_from, date_to)
    return _build_doctor_productivity(db, date_from, date_to, doctor_id)


@router.get("/reports/doctor-productivity/csv")
async def get_doctor_productivity_csv(
    date_from: date = Query(...),
    date_to: date = Query(...),
    doctor_id: Optional[int] = Query(default=None),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """CSV export of doctor productivity for revenue-share spreadsheet imports."""
    import csv as _csv
    _validate_date_range(date_from, date_to)
    payload = _build_doctor_productivity(db, date_from, date_to, doctor_id)

    out = io.StringIO()
    cols = ["doctor_id", "doctor_name", "admissions", "discharges", "deaths",
            "readmissions_30d", "ot_as_surgeon", "ot_as_anaesthetist",
            "visits", "average_los_days", "visit_fees_billed",
            "ot_surgeon_fees", "ot_anaesthetist_fees", "total_billed_attributable"]
    w = _csv.DictWriter(out, fieldnames=cols)
    w.writeheader()
    for r in payload["rows"]:
        w.writerow(r)

    body = out.getvalue().encode("utf-8")
    return StreamingResponse(
        io.BytesIO(body),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=doctor_productivity_{date_from}_{date_to}.csv"},
    )


@router.get("/reports/doctor-productivity/pdf")
async def get_doctor_productivity_pdf(
    date_from: date = Query(...),
    date_to: date = Query(...),
    doctor_id: Optional[int] = Query(default=None),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    _validate_date_range(date_from, date_to)
    payload = _build_doctor_productivity(db, date_from, date_to, doctor_id)
    hospital = _get_hospital(db, current_user)
    hospital_info = {
        "name": hospital.name, "address": hospital.address or "",
        "phone": hospital.phone or "", "email": hospital.email or "",
        "logo_url": getattr(hospital, "logo_url", "") or "",
        "hospital_subname": getattr(hospital, "hospital_subname", "") or "",
    }
    pdf_buffer = pdf_service.generate_doctor_productivity_pdf(payload, hospital_info, **pdf_gen_kwargs(db, current_user.hospital_id, 'doctor_productivity'))
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=doctor_productivity_{date_from}_{date_to}.pdf"},
    )


@router.get("/admissions/{admission_id}/death-certificate/pdf")
async def death_certificate_pdf(
    admission_id: int,
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
        "mrn": (patient.mrn or "") if patient else "",
        "patient_id": patient.patient_id if patient else "",
        "age": _patient_age(patient) or "",
        "age_display": _patient_age_display(patient),
        "gender": patient.gender if patient else "",
        "village": (patient.village or "") if patient else "",
        "district": (patient.district or "") if patient else "",
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
    pdf_buffer = pdf_service.generate_death_certificate_pdf(cert_data, hospital_info, **pdf_gen_kwargs(db, current_user.hospital_id, 'death_certificate'))
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
    _require_accepted(admission)

    valid = IO_INTAKE_CATEGORIES if data.io_type == "intake" else IO_OUTPUT_CATEGORIES
    if data.category not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid category for {data.io_type}: {data.category}")

    entry = FluidBalance(
        admission_id=admission_id,
        patient_id=admission.patient_id,
        recorded_by_id=current_user.id,
        recorded_at=data.recorded_at or _now_utc(),
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
    day = target_date or _now_utc().date()
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
    a.acknowledged_at = _now_utc()
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


# ============================================================
# B4 — Doctor duty roster (identifies on-floor duty doctor)
# ============================================================

# Shift time windows (24h clock). Used to map a visit timestamp to a shift.
SHIFT_TIME_WINDOWS = {
    "morning":   (6, 14),    # 06:00 – 13:59
    "afternoon": (14, 22),   # 14:00 – 21:59
    "night":     (22, 6),    # 22:00 – 05:59 (wraps midnight)
}


def _shift_for_datetime(dt: datetime) -> str:
    """Return the shift name (morning/afternoon/night) for a given timestamp."""
    hour = dt.hour
    if 6 <= hour < 14:
        return "morning"
    if 14 <= hour < 22:
        return "afternoon"
    return "night"


def _roster_date_for_datetime(dt: datetime) -> datetime:
    """Night-shift hours 00:00–05:59 still belong to the previous calendar
    day's night roster. Map a timestamp to its owning roster_date."""
    if dt.hour < 6:
        from datetime import timedelta as _td
        d = (dt - _td(days=1)).date()
    else:
        d = dt.date()
    return datetime.combine(d, datetime.min.time())


class DoctorRosterEntryCreate(BaseModel):
    doctor_id: int
    roster_date: date
    shift: str = Field(..., pattern="^(morning|afternoon|night)$")
    status: str = Field(default="working", pattern="^(working|leave|off|on_call)$")
    ward: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None


class DoctorRosterEntryUpdate(BaseModel):
    shift: Optional[str] = Field(default=None, pattern="^(morning|afternoon|night)$")
    status: Optional[str] = Field(default=None, pattern="^(working|leave|off|on_call)$")
    ward: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None


class DoctorRosterResponse(BaseModel):
    id: int
    doctor_id: int
    doctor_name: Optional[str] = None
    roster_date: datetime
    shift: str
    status: str
    ward: Optional[str]
    notes: Optional[str]

    class Config:
        from_attributes = True


def _doctor_roster_to_response(r: DoctorDutyRoster, db: Session) -> dict:
    doctor = db.query(User).filter(User.id == r.doctor_id).first()
    return {
        "id": r.id,
        "doctor_id": r.doctor_id,
        "doctor_name": f"{doctor.first_name} {doctor.last_name}" if doctor else None,
        "roster_date": r.roster_date,
        "shift": r.shift,
        "status": r.status,
        "ward": r.ward,
        "notes": r.notes,
    }


@router.post("/doctor-roster", response_model=DoctorRosterResponse,
             status_code=status.HTTP_201_CREATED)
async def create_doctor_roster_entry(
    data: DoctorRosterEntryCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_roster")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    target_dt = datetime.combine(data.roster_date, datetime.min.time())
    existing = db.query(DoctorDutyRoster).filter(
        DoctorDutyRoster.doctor_id == data.doctor_id,
        DoctorDutyRoster.roster_date == target_dt,
        DoctorDutyRoster.shift == data.shift,
    ).first()
    if existing:
        raise HTTPException(status_code=400,
            detail=f"Doctor already rostered for {data.roster_date} {data.shift}")
    entry = DoctorDutyRoster(
        doctor_id=data.doctor_id,
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
    return _doctor_roster_to_response(entry, db)


@router.get("/doctor-roster", response_model=List[DoctorRosterResponse])
async def list_doctor_roster(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    doctor_id: Optional[int] = None,
    shift: Optional[str] = Query(default=None, pattern="^(morning|afternoon|night)$"),
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_roster")),
    db: Session = Depends(get_db),
):
    q = db.query(DoctorDutyRoster).filter(
        DoctorDutyRoster.hospital_id == current_user.hospital_id
    )
    if start_date:
        q = q.filter(DoctorDutyRoster.roster_date >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        q = q.filter(DoctorDutyRoster.roster_date <= datetime.combine(end_date, datetime.min.time()))
    if doctor_id:
        q = q.filter(DoctorDutyRoster.doctor_id == doctor_id)
    if shift:
        q = q.filter(DoctorDutyRoster.shift == shift)
    rows = q.order_by(DoctorDutyRoster.roster_date.desc(), DoctorDutyRoster.shift).all()
    return [_doctor_roster_to_response(r, db) for r in rows]


@router.put("/doctor-roster/{entry_id}", response_model=DoctorRosterResponse)
async def update_doctor_roster_entry(
    entry_id: int,
    data: DoctorRosterEntryUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_roster")),
    db: Session = Depends(get_db),
):
    entry = db.query(DoctorDutyRoster).filter(DoctorDutyRoster.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Roster entry not found")
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(entry, k, v)
    db.commit()
    db.refresh(entry)
    return _doctor_roster_to_response(entry, db)


@router.delete("/doctor-roster/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_doctor_roster_entry(
    entry_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_roster")),
    db: Session = Depends(get_db),
):
    entry = db.query(DoctorDutyRoster).filter(DoctorDutyRoster.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Roster entry not found")
    db.delete(entry)
    db.commit()


@router.get("/duty-doctor/on-duty")
async def duty_doctors_on_duty(
    at: Optional[datetime] = Query(default=None,
        description="Timestamp to check; defaults to now"),
    ward: Optional[str] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_occupancy")),
    db: Session = Depends(get_db),
):
    """Doctors rostered as 'working' or 'on_call' at the given moment.
    The frontend uses this to pre-select the visitor for a duty-doctor visit."""
    at = at or datetime.now()
    roster_date = _roster_date_for_datetime(at)
    shift = _shift_for_datetime(at)
    q = db.query(DoctorDutyRoster).filter(
        DoctorDutyRoster.hospital_id == current_user.hospital_id,
        DoctorDutyRoster.roster_date == roster_date,
        DoctorDutyRoster.shift == shift,
        DoctorDutyRoster.status.in_(list(ASSIGNABLE_STATUSES)),
    )
    if ward:
        q = q.filter(DoctorDutyRoster.ward == ward)
    rows = q.all()
    result = []
    for r in rows:
        doc = db.query(User).filter(User.id == r.doctor_id).first()
        if doc and doc.is_active:
            result.append({
                "doctor_id": doc.id,
                "doctor_name": f"{doc.first_name} {doc.last_name}",
                "username": doc.username,
                "status": r.status,
                "ward": r.ward,
                "specialization": doc.specialization,
            })
    return {
        "at": at.isoformat(),
        "shift": shift,
        "roster_date": roster_date.date().isoformat(),
        "on_duty": result,
    }


def _require_duty_doctor(db: Session, hospital_id: int, doctor_id: int,
                        at: datetime) -> None:
    """Raise 409 if `doctor_id` is not rostered (working or on_call) at the
    given timestamp. Used to guard duty-doctor visits from being recorded by
    a doctor who isn't actually on duty."""
    roster_date = _roster_date_for_datetime(at)
    shift = _shift_for_datetime(at)
    entry = db.query(DoctorDutyRoster).filter(
        DoctorDutyRoster.hospital_id == hospital_id,
        DoctorDutyRoster.doctor_id == doctor_id,
        DoctorDutyRoster.roster_date == roster_date,
        DoctorDutyRoster.shift == shift,
        DoctorDutyRoster.status.in_(list(ASSIGNABLE_STATUSES)),
    ).first()
    if not entry:
        raise HTTPException(
            status_code=409,
            detail=f"Doctor is not on duty for {shift} shift on {roster_date.date()} — "
                   f"record this as a regular doctor_visit, or add a roster entry first."
        )


# ============================================================
# B6 — Body release / mortuary / post-mortem coordination
# ============================================================

class BodyReleaseUpsert(BaseModel):
    mortuary_slot: Optional[str] = Field(default=None, max_length=20)
    body_in_mortuary_at: Optional[datetime] = None
    body_out_mortuary_at: Optional[datetime] = None
    embalming_done: Optional[bool] = None
    embalming_at: Optional[datetime] = None
    embalmed_by: Optional[str] = Field(default=None, max_length=200)
    post_mortem_required: Optional[bool] = None
    pm_hospital: Optional[str] = Field(default=None, max_length=200)
    pm_doctor: Optional[str] = Field(default=None, max_length=200)
    pm_referred_at: Optional[datetime] = None
    pm_completed_at: Optional[datetime] = None
    pm_report_received: Optional[bool] = None
    pm_report_number: Optional[str] = Field(default=None, max_length=100)
    police_noc_required: Optional[bool] = None
    police_noc_received: Optional[bool] = None
    police_noc_number: Optional[str] = Field(default=None, max_length=100)
    police_noc_received_at: Optional[datetime] = None
    notes: Optional[str] = None


class BodyReleaseAction(BaseModel):
    """Final-release payload — requires release-to identity + witness."""
    released_to_name: str = Field(..., min_length=1, max_length=200)
    released_to_relationship: str = Field(..., min_length=1, max_length=50)
    released_to_phone: Optional[str] = Field(default=None, max_length=20)
    released_to_id_proof_type: str = Field(..., pattern="^(aadhar|voter|license|passport|other)$")
    released_to_id_proof_number: str = Field(..., min_length=1, max_length=50)
    released_to_address: Optional[str] = None
    witness_name: str = Field(..., min_length=1, max_length=200)
    witness_phone: Optional[str] = Field(default=None, max_length=20)
    witness_id_proof: Optional[str] = Field(default=None, max_length=100)
    transport_details: Optional[str] = None
    notes: Optional[str] = None
    # Override flags for missing prerequisites (audit-logged)
    force_missing_noc: bool = False
    force_missing_pm: bool = False
    override_reason: Optional[str] = None


def _body_release_to_response(rec: BodyReleaseRecord) -> dict:
    return {c.name: getattr(rec, c.name) for c in rec.__table__.columns}


def _get_or_create_body_release(db: Session, admission: Admission) -> BodyReleaseRecord:
    rec = db.query(BodyReleaseRecord).filter(BodyReleaseRecord.admission_id == admission.id).first()
    if rec:
        return rec
    if not admission.discharge or admission.discharge.discharge_type != "death":
        raise HTTPException(status_code=400, detail="Not a mortality discharge — body release does not apply")
    # Pre-fill defaults from admission/discharge: MLC ⇒ NOC required and PM typically required.
    pm_required = bool(admission.is_mlc)
    rec = BodyReleaseRecord(
        admission_id=admission.id,
        discharge_id=admission.discharge.id,
        body_in_mortuary_at=admission.discharge.discharge_date or datetime.now(),
        post_mortem_required=pm_required,
        police_noc_required=bool(admission.is_mlc),
    )
    db.add(rec)
    db.flush()
    return rec


@router.get("/admissions/{admission_id}/body-release")
async def get_body_release(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_mortality")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).options(joinedload(Admission.discharge)).filter(
        Admission.id == admission_id
    ).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    rec = _get_or_create_body_release(db, admission)
    db.commit()
    return _body_release_to_response(rec)


@router.put("/admissions/{admission_id}/body-release")
async def update_body_release(
    admission_id: int,
    data: BodyReleaseUpsert,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_mortality")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).options(joinedload(Admission.discharge)).filter(
        Admission.id == admission_id
    ).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    rec = _get_or_create_body_release(db, admission)
    if rec.body_released:
        raise HTTPException(status_code=400, detail="Body already released — record is locked")

    payload = data.model_dump(exclude_unset=True)
    # Auto-stamp timestamps when boolean is toggled true without explicit time
    if payload.get("embalming_done") and not payload.get("embalming_at") and not rec.embalming_at:
        payload["embalming_at"] = datetime.now()
    if payload.get("police_noc_received") and not payload.get("police_noc_received_at") and not rec.police_noc_received_at:
        payload["police_noc_received_at"] = datetime.now()
    if payload.get("pm_report_received") and not payload.get("pm_completed_at") and not rec.pm_completed_at:
        payload["pm_completed_at"] = datetime.now()

    for k, v in payload.items():
        setattr(rec, k, v)
    db.commit()
    log_action(db, current_user, "update_body_release", "inpatient", "BodyReleaseRecord", str(rec.id),
               f"Updated body release for admission {admission.admission_number}", payload)
    return _body_release_to_response(rec)


@router.post("/admissions/{admission_id}/body-release/release")
async def release_body(
    admission_id: int,
    data: BodyReleaseAction,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "record_mortality")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).options(joinedload(Admission.discharge)).filter(
        Admission.id == admission_id
    ).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    rec = _get_or_create_body_release(db, admission)
    if rec.body_released:
        raise HTTPException(status_code=400, detail="Body already released")

    forced = []
    # Gate 1: Police NOC required + not received → block unless forced.
    if rec.police_noc_required and not rec.police_noc_received:
        if not data.force_missing_noc:
            raise HTTPException(status_code=409, detail={
                "code": "missing_police_noc",
                "message": "Police NOC is required for MLC body release. Receive NOC or set force_missing_noc=true with override_reason.",
            })
        forced.append("missing_police_noc")
    # Gate 2: Post-mortem required + not completed → block unless forced.
    if rec.post_mortem_required and not rec.pm_completed_at:
        if not data.force_missing_pm:
            raise HTTPException(status_code=409, detail={
                "code": "missing_pm",
                "message": "Post-mortem is required for this case. Complete PM or set force_missing_pm=true with override_reason.",
            })
        forced.append("missing_pm")
    if forced and not (data.override_reason and data.override_reason.strip()):
        raise HTTPException(status_code=400, detail="override_reason is required when forcing release without prerequisites")

    rec.released_to_name = data.released_to_name.strip()
    rec.released_to_relationship = data.released_to_relationship.strip()
    rec.released_to_phone = data.released_to_phone
    rec.released_to_id_proof_type = data.released_to_id_proof_type
    rec.released_to_id_proof_number = data.released_to_id_proof_number.strip()
    rec.released_to_address = data.released_to_address
    rec.witness_name = data.witness_name.strip()
    rec.witness_phone = data.witness_phone
    rec.witness_id_proof = data.witness_id_proof
    rec.transport_details = data.transport_details
    if data.notes:
        rec.notes = (rec.notes + "\n" if rec.notes else "") + data.notes
    rec.body_released = True
    rec.body_released_at = datetime.now()
    rec.body_out_mortuary_at = rec.body_out_mortuary_at or rec.body_released_at
    rec.released_by_id = current_user.id
    db.commit()
    log_action(db, current_user, "release_body", "inpatient", "BodyReleaseRecord", str(rec.id),
               f"Body released for admission {admission.admission_number}",
               {"forced_gates": forced, "override_reason": data.override_reason,
                "released_to": rec.released_to_name, "relationship": rec.released_to_relationship})
    return _body_release_to_response(rec)


@router.get("/admissions/{admission_id}/body-release/pdf")
async def get_body_release_pdf(
    admission_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_mortality")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).options(joinedload(Admission.discharge)).filter(
        Admission.id == admission_id
    ).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    rec = db.query(BodyReleaseRecord).filter(BodyReleaseRecord.admission_id == admission_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="No body release record")
    patient = db.query(Patient).filter(Patient.id == admission.patient_id).first()
    doctor = db.query(User).filter(User.id == admission.admitting_doctor_id).first()
    hospital = _get_hospital(db, current_user)
    hospital_info = {
        "name": hospital.name, "address": hospital.address or "",
        "phone": hospital.phone or "", "email": hospital.email or "",
        "logo_url": getattr(hospital, "logo_url", "") or "",
        "hospital_subname": getattr(hospital, "hospital_subname", "") or "",
    }
    discharge = admission.discharge
    rel_data = {
        "admission_number": admission.admission_number,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "",
        "mrn": (patient.mrn or "") if patient else "",
        "patient_id": patient.patient_id if patient else "",
        "age": _patient_age(patient) or "",
        "age_display": _patient_age_display(patient),
        "gender": patient.gender if patient else "",
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "",
        "death_date": discharge.discharge_date.strftime("%d/%m/%Y %H:%M") if discharge and discharge.discharge_date else "",
        "is_mlc": admission.is_mlc,
        "mlc_number": admission.mlc_number or "",
        "mortuary_slot": rec.mortuary_slot or "",
        "body_in_at": rec.body_in_mortuary_at.strftime("%d/%m/%Y %H:%M") if rec.body_in_mortuary_at else "",
        "body_out_at": rec.body_out_mortuary_at.strftime("%d/%m/%Y %H:%M") if rec.body_out_mortuary_at else "",
        "embalming_done": rec.embalming_done,
        "embalmed_by": rec.embalmed_by or "",
        "embalming_at": rec.embalming_at.strftime("%d/%m/%Y %H:%M") if rec.embalming_at else "",
        "post_mortem_required": rec.post_mortem_required,
        "pm_hospital": rec.pm_hospital or "",
        "pm_doctor": rec.pm_doctor or "",
        "pm_completed_at": rec.pm_completed_at.strftime("%d/%m/%Y %H:%M") if rec.pm_completed_at else "",
        "pm_report_number": rec.pm_report_number or "",
        "police_noc_received": rec.police_noc_received,
        "police_noc_number": rec.police_noc_number or "",
        "police_noc_received_at": rec.police_noc_received_at.strftime("%d/%m/%Y %H:%M") if rec.police_noc_received_at else "",
        "body_released_at": rec.body_released_at.strftime("%d/%m/%Y %H:%M") if rec.body_released_at else "",
        "released_to_name": rec.released_to_name or "",
        "released_to_relationship": rec.released_to_relationship or "",
        "released_to_phone": rec.released_to_phone or "",
        "released_to_id_proof_type": rec.released_to_id_proof_type or "",
        "released_to_id_proof_number": rec.released_to_id_proof_number or "",
        "released_to_address": rec.released_to_address or "",
        "witness_name": rec.witness_name or "",
        "witness_phone": rec.witness_phone or "",
        "witness_id_proof": rec.witness_id_proof or "",
        "transport_details": rec.transport_details or "",
        "notes": rec.notes or "",
    }
    pdf_buffer = pdf_service.generate_body_release_pdf(rel_data, hospital_info, **pdf_gen_kwargs(db, current_user.hospital_id, 'body_release'))
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=BodyRelease_{admission.admission_number}.pdf"},
    )


# ============================================================
# FOOD ORDERING — meal plans + per-admission food orders
# ============================================================

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snacks")
DIET_OPTIONS = ("veg", "non-veg", "diabetic", "soft", "liquid", "custom")


class MealPlanItem(BaseModel):
    room_type: str = Field(..., min_length=1, max_length=30)
    meal_type: str = Field(..., pattern=r"^(breakfast|lunch|dinner|snacks)$")
    price: float = Field(..., ge=0)
    description: Optional[str] = Field(default=None, max_length=200)
    is_active: bool = True


class MealPlanBulkUpdate(BaseModel):
    plans: List[MealPlanItem]


@router.get("/meal-plans")
async def list_meal_plans(
    room_type: Optional[str] = None,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_food_orders")),
    db: Session = Depends(get_db),
):
    """List meal plans, optionally filtered by room_type. Returns rows for
    every (room_type, meal_type) combination — missing ones come back with
    price=0 and is_active=False so the UI can render the full grid."""
    hospital = _get_hospital(db, current_user)
    q = db.query(MealPlan).filter(MealPlan.hospital_id == hospital.id)
    if room_type:
        q = q.filter(MealPlan.room_type == room_type)
    existing = {(p.room_type, p.meal_type): p for p in q.all()}

    # Determine the set of room_types to render. Prefer the RoomType catalog;
    # fall back to room types currently in use by rooms or existing plans;
    # finally to the built-in default list so the grid is never empty.
    rt_rows = db.query(RoomType).filter(RoomType.hospital_id == hospital.id).all()
    room_types = [r.type_key for r in rt_rows] if rt_rows else []
    if not room_types:
        room_types = list({r[0] for r in db.query(RoomManagement.room_type).filter(
            RoomManagement.hospital_id == hospital.id
        ).distinct().all() if r[0]})
    if not room_types:
        room_types = list({k for k in existing.keys()} and {p.room_type for p in existing.values()})
    if not room_types:
        room_types = [
            "general", "semi_private", "private", "suite", "icu", "hdu",
            "nicu", "picu", "isolation", "labour", "recovery", "daycare",
            "emergency", "operation",
        ]
    if room_type and room_type not in room_types:
        room_types = [room_type]

    out = []
    for rt in room_types:
        for mt in MEAL_TYPES:
            p = existing.get((rt, mt))
            out.append({
                "id": p.id if p else None,
                "room_type": rt,
                "meal_type": mt,
                "price": float(p.price) if p else 0.0,
                "description": (p.description if p else "") or "",
                "is_active": bool(p.is_active) if p else False,
            })
    return out


@router.put("/meal-plans")
async def upsert_meal_plans(
    data: MealPlanBulkUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_meal_plans")),
    db: Session = Depends(get_db),
):
    """Bulk upsert. Each (room_type, meal_type) row is created or updated."""
    hospital = _get_hospital(db, current_user)
    upserted = 0
    for item in data.plans:
        row = db.query(MealPlan).filter(
            MealPlan.hospital_id == hospital.id,
            MealPlan.room_type == item.room_type,
            MealPlan.meal_type == item.meal_type,
        ).first()
        if row:
            row.price = item.price
            row.description = item.description
            row.is_active = item.is_active
        else:
            row = MealPlan(
                hospital_id=hospital.id,
                room_type=item.room_type,
                meal_type=item.meal_type,
                price=item.price,
                description=item.description,
                is_active=item.is_active,
            )
            db.add(row)
        upserted += 1
    db.commit()
    log_action(db, current_user, "upsert_meal_plans", "inpatient", "MealPlan", None,
               f"Updated {upserted} meal plan row(s)")
    return {"upserted": upserted}


@router.delete("/meal-plans/{plan_id}")
async def delete_meal_plan(
    plan_id: int,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "manage_meal_plans")),
    db: Session = Depends(get_db),
):
    hospital = _get_hospital(db, current_user)
    row = db.query(MealPlan).filter(
        MealPlan.id == plan_id, MealPlan.hospital_id == hospital.id
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    db.delete(row)
    db.commit()
    return {"deleted": True}


class FoodOrderItem(BaseModel):
    meal_date: date
    meal_type: str = Field(..., pattern=r"^(breakfast|lunch|dinner|snacks)$")
    diet_preference: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=500)


class FoodOrderBulkCreate(BaseModel):
    items: List[FoodOrderItem] = Field(..., min_length=1)


class FoodOrderUpdate(BaseModel):
    status: Optional[str] = Field(default=None, pattern=r"^(ordered|delivered)$")
    diet_preference: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=500)


class FoodOrderCancel(BaseModel):
    reason: str = Field(..., min_length=1, max_length=200)


def _food_order_to_response(o: FoodOrder) -> dict:
    return {
        "id": o.id,
        "admission_id": o.admission_id,
        "meal_date": o.meal_date.isoformat() if o.meal_date else None,
        "meal_type": o.meal_type,
        "status": o.status,
        "price": float(o.price or 0),
        "diet_preference": o.diet_preference or "",
        "notes": o.notes or "",
        "ordered_at": o.ordered_at.isoformat() if o.ordered_at else None,
        "delivered_at": o.delivered_at.isoformat() if o.delivered_at else None,
        "cancelled_at": o.cancelled_at.isoformat() if o.cancelled_at else None,
        "cancelled_reason": o.cancelled_reason or "",
        "billed": bool(o.billed),
    }


@router.get("/admissions/{admission_id}/food-orders")
async def list_food_orders(
    admission_id: int,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    include_cancelled: bool = True,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "view_food_orders")),
    db: Session = Depends(get_db),
):
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    q = db.query(FoodOrder).filter(FoodOrder.admission_id == admission_id)
    if from_date:
        q = q.filter(FoodOrder.meal_date >= from_date)
    if to_date:
        q = q.filter(FoodOrder.meal_date <= to_date)
    if not include_cancelled:
        q = q.filter(FoodOrder.status != "cancelled")
    orders = q.order_by(FoodOrder.meal_date.asc(), FoodOrder.meal_type.asc()).all()
    return [_food_order_to_response(o) for o in orders]


@router.post("/admissions/{admission_id}/food-orders", status_code=201)
async def create_food_orders(
    admission_id: int,
    data: FoodOrderBulkCreate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "order_food")),
    db: Session = Depends(get_db),
):
    """Create one or more food orders. Each line is priced from the active
    MealPlan row for the admission's current room_type + meal_type. Duplicate
    (admission, date, meal_type) rows are silently skipped — already-ordered
    cells are a UX no-op."""
    admission = db.query(Admission).filter(Admission.id == admission_id).first()
    if not admission:
        raise HTTPException(status_code=404, detail="Admission not found")
    if admission.status not in ("admitted", "active"):
        raise HTTPException(status_code=400, detail="Cannot order food for a non-active admission")
    hospital = _get_hospital(db, current_user)
    room = db.query(RoomManagement).filter(RoomManagement.id == admission.room_id).first()
    if not room:
        raise HTTPException(status_code=400, detail="Admission has no room assigned")

    # Cache meal-plan lookups for this room_type
    plan_rows = db.query(MealPlan).filter(
        MealPlan.hospital_id == hospital.id,
        MealPlan.room_type == room.room_type,
        MealPlan.is_active == True,
    ).all()
    plan_by_type = {p.meal_type: p for p in plan_rows}

    created = []
    skipped = []
    for it in data.items:
        plan = plan_by_type.get(it.meal_type)
        if not plan:
            raise HTTPException(
                status_code=400,
                detail=f"No active meal plan for room type '{room.room_type}' / {it.meal_type}. Set price in Hospital Admin → Meal Plans.",
            )
        existing = db.query(FoodOrder).filter(
            FoodOrder.admission_id == admission_id,
            FoodOrder.meal_date == it.meal_date,
            FoodOrder.meal_type == it.meal_type,
        ).first()
        if existing:
            # If it was cancelled, re-activate at current price; otherwise skip.
            if existing.status == "cancelled":
                existing.status = "ordered"
                existing.price = plan.price
                existing.diet_preference = it.diet_preference
                existing.notes = it.notes
                existing.cancelled_at = None
                existing.cancelled_by_id = None
                existing.cancelled_reason = None
                existing.ordered_at = datetime.now(timezone.utc)
                existing.ordered_by_id = current_user.id
                created.append(existing)
            else:
                skipped.append({"meal_date": it.meal_date.isoformat(), "meal_type": it.meal_type})
            continue
        order = FoodOrder(
            admission_id=admission_id,
            hospital_id=hospital.id,
            meal_date=it.meal_date,
            meal_type=it.meal_type,
            status="ordered",
            price=plan.price,
            diet_preference=it.diet_preference,
            notes=it.notes,
            ordered_by_id=current_user.id,
        )
        db.add(order)
        created.append(order)
    db.commit()
    for o in created:
        db.refresh(o)
    log_action(db, current_user, "create_food_orders", "inpatient", "FoodOrder", None,
               f"Created {len(created)} food order(s) for admission {admission_id}",
               details={"created": len(created), "skipped": len(skipped)})
    return {
        "created": [_food_order_to_response(o) for o in created],
        "skipped": skipped,
    }


@router.patch("/food-orders/{order_id}")
async def update_food_order(
    order_id: int,
    data: FoodOrderUpdate,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "order_food")),
    db: Session = Depends(get_db),
):
    """Update diet/notes or mark delivered. Marking delivered requires the
    mark_food_delivered permission — checked inline since this endpoint
    accepts both status transitions and diet edits under one permission."""
    order = db.query(FoodOrder).filter(FoodOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Food order not found")
    if order.status == "cancelled":
        raise HTTPException(status_code=400, detail="Cannot edit a cancelled order")
    if data.status == "delivered":
        # Enforce delivery-specific permission inline. super_admin/hospital_admin bypass.
        allowed = any(r in current_user.role_names for r in ("super_admin", "hospital_admin"))
        if not allowed:
            from app.models.permissions import RoleModulePermission
            role_ids = [r.id for r in (current_user.roles or [])]
            if current_user.role_id and current_user.role_id not in role_ids:
                role_ids.append(current_user.role_id)
            for rid in role_ids:
                rp = db.query(RoleModulePermission).filter(
                    RoleModulePermission.role_id == rid,
                    RoleModulePermission.module_name == Modules.INPATIENT,
                ).first()
                if rp and rp.permissions and "mark_food_delivered" in rp.permissions:
                    allowed = True
                    break
        if not allowed:
            raise HTTPException(status_code=403, detail="Missing mark_food_delivered permission")
        if order.status == "delivered":
            raise HTTPException(status_code=400, detail="Already marked delivered")
        order.status = "delivered"
        order.delivered_at = datetime.now(timezone.utc)
        order.delivered_by_id = current_user.id
    if data.diet_preference is not None:
        order.diet_preference = data.diet_preference
    if data.notes is not None:
        order.notes = data.notes
    db.commit()
    db.refresh(order)
    return _food_order_to_response(order)


@router.post("/food-orders/{order_id}/cancel")
async def cancel_food_order(
    order_id: int,
    data: FoodOrderCancel,
    current_user: User = Depends(require_feature_permission(Modules.INPATIENT, "order_food")),
    db: Session = Depends(get_db),
):
    """Cancel a food order. Blocked if already billed — operator must refund
    through the deposit flow instead."""
    order = db.query(FoodOrder).filter(FoodOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Food order not found")
    if order.status == "cancelled":
        raise HTTPException(status_code=400, detail="Already cancelled")
    if order.billed or order.bill_id:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "food_order_billed",
                "message": "This meal is already on a finalized bill. Cancel the bill or issue a refund.",
                "bill_id": order.bill_id,
            },
        )
    order.status = "cancelled"
    order.cancelled_at = datetime.now(timezone.utc)
    order.cancelled_by_id = current_user.id
    order.cancelled_reason = data.reason
    db.commit()
    log_action(db, current_user, "cancel_food_order", "inpatient", "FoodOrder", order.id,
               f"Cancelled meal {order.meal_type} on {order.meal_date}: {data.reason}")
    return {"cancelled": True}
