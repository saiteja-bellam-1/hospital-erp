from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, Numeric, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base

class RoomManagement(Base):
    __tablename__ = "room_management"
    
    id = Column(Integer, primary_key=True, index=True)
    room_number = Column(String(20), nullable=False)
    room_type = Column(String(30), nullable=False)  # general, private, icu, emergency, operation
    floor = Column(String(10))
    department = Column(String(50))
    bed_count = Column(Integer, default=1)
    available_beds = Column(Integer, default=1)
    room_charge_per_day = Column(Float, nullable=False)
    amenities = Column(Text)  # JSON or comma-separated list
    is_active = Column(Boolean, default=True)
    is_occupied = Column(Boolean, default=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    admissions = relationship("Admission", back_populates="room")
    beds = relationship("Bed", back_populates="room")


class Bed(Base):
    __tablename__ = "beds"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("room_management.id"), nullable=False)
    bed_label = Column(String(20), nullable=False)  # e.g. "A", "B", "1", "2"
    status = Column(String(20), default="available")  # available, occupied, maintenance
    current_admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    room = relationship("RoomManagement", back_populates="beds")
    admission = relationship("Admission", foreign_keys=[current_admission_id])


class Admission(Base):
    __tablename__ = "admissions"
    
    id = Column(Integer, primary_key=True, index=True)
    admission_number = Column(String(50), unique=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    admitting_doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("room_management.id"), nullable=False)
    admission_date = Column(DateTime(timezone=True), server_default=func.now())
    admission_type = Column(String(20), nullable=False)  # emergency, elective, transfer
    admission_reason = Column(Text)
    condition_on_admission = Column(String(20))  # stable, critical, serious
    estimated_stay_days = Column(Integer)
    status = Column(String(20), default="admitted")  # admitted, discharged, transferred
    admission_notes = Column(Text)
    insurance_details = Column(Text)
    insurance_provider = Column(String(200), nullable=True)
    policy_number = Column(String(100), nullable=True)
    claim_reference = Column(String(100), nullable=True)
    claim_status = Column(String(20), default="none")  # none, draft, submitted, approved, rejected
    claim_amount = Column(Float, nullable=True)
    claim_submitted_at = Column(DateTime(timezone=True), nullable=True)
    claim_notes = Column(Text, nullable=True)
    emergency_contact = Column(String(100))
    attending_physician_id = Column(Integer, ForeignKey("users.id"))
    bed_number = Column(String(10))  # legacy free-text field
    bed_id = Column(Integer, ForeignKey("beds.id"), nullable=True)  # structured bed reference
    # Phase 4 — readmission tracking (populated on admission create)
    is_readmission = Column(Boolean, default=False)
    previous_admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True)
    days_since_last_discharge = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    patient = relationship("Patient", back_populates="admissions")
    admitting_doctor = relationship("User", foreign_keys=[admitting_doctor_id])
    bed = relationship("Bed", foreign_keys=[bed_id])
    room = relationship("RoomManagement", back_populates="admissions")
    discharge = relationship("DischargeRecord", back_populates="admission", uselist=False)
    visits = relationship("PatientVisit", back_populates="admission")
    ot_schedules = relationship("OTSchedule", back_populates="admission")
    lab_orders = relationship("PatientLabOrder", back_populates="admission")
    documents = relationship("AdmissionDocument", back_populates="admission")
    nursing_notes = relationship("NursingNote", back_populates="admission")
    diet_orders = relationship("DietOrder", back_populates="admission")
    vital_signs = relationship("VitalSigns", back_populates="admission")
    medication_administrations = relationship("MedicationAdministration", back_populates="admission")
    deposits = relationship("AdmissionDeposit", back_populates="admission", cascade="all, delete-orphan")
    ancillary_charges = relationship("AdmissionAncillaryCharge", back_populates="admission", cascade="all, delete-orphan")
    package_assignment = relationship("AdmissionPackage", back_populates="admission", uselist=False, cascade="all, delete-orphan")
    preauth_requests = relationship("InsurancePreAuth", back_populates="admission")

class DischargeRecord(Base):
    __tablename__ = "discharge_records"
    
    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    discharge_date = Column(DateTime(timezone=True), server_default=func.now())
    discharge_type = Column(String(20), nullable=False)  # normal, against_advice, transfer, death
    condition_on_discharge = Column(String(20))  # stable, improved, unchanged, critical
    discharge_summary = Column(Text)
    diagnosis_on_discharge = Column(Text)
    treatment_given = Column(Text)
    medications_prescribed = Column(Text)
    follow_up_instructions = Column(Text)
    follow_up_date = Column(DateTime)
    diet_instructions = Column(Text)
    activity_restrictions = Column(Text)
    discharge_approved_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total_stay_days = Column(Integer)
    total_charges = Column(Float, default=0.0)
    # Phase 4 — mortality details (only populated when discharge_type='death')
    cause_of_death = Column(Text, nullable=True)
    time_of_death = Column(DateTime(timezone=True), nullable=True)
    death_certificate_number = Column(String(100), nullable=True)
    mlc_required = Column(Boolean, default=False)
    mlc_number = Column(String(100), nullable=True)
    autopsy_done = Column(Boolean, default=False)
    autopsy_findings = Column(Text, nullable=True)
    body_handed_over_to = Column(String(200), nullable=True)
    body_handover_relationship = Column(String(100), nullable=True)
    body_handover_time = Column(DateTime(timezone=True), nullable=True)
    body_handover_id_proof = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    admission = relationship("Admission", back_populates="discharge")


class InpatientRateConfig(Base):
    __tablename__ = "inpatient_rate_configs"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    doctor_visit_rate = Column(Numeric(10, 2), default=0.00)
    nurse_visit_rate = Column(Numeric(10, 2), default=0.00)
    procedure_rate = Column(Numeric(10, 2), default=0.00)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PatientVisit(Base):
    __tablename__ = "patient_visits"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    visitor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    visit_type = Column(String(20), nullable=False)  # doctor_visit, nurse_visit, procedure
    visit_datetime = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text, nullable=True)
    charge_amount = Column(Numeric(10, 2), default=0.00)
    billed = Column(Boolean, default=False)            # legacy: kept for backwards compat with existing rows
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)  # which bill (interim or final) consumed this visit
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    admission = relationship("Admission", back_populates="visits")
    visitor = relationship("User", foreign_keys=[visitor_id])


class OTSchedule(Base):
    __tablename__ = "ot_schedules"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    surgeon_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    anaesthetist_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    ot_room_number = Column(String(20), nullable=False)
    procedure_name = Column(String(200), nullable=False)
    procedure_id = Column(Integer, ForeignKey("procedures.id"), nullable=True)
    scheduled_date = Column(DateTime(timezone=True), nullable=False)
    estimated_duration_minutes = Column(Integer)
    status = Column(String(20), default="scheduled")  # scheduled, in_progress, completed, cancelled, postponed
    pre_op_notes = Column(Text, nullable=True)
    post_op_notes = Column(Text, nullable=True)

    # Charges (set after the procedure; flow into the admission bill)
    surgeon_fee = Column(Float, default=0.0)
    anaesthetist_fee = Column(Float, default=0.0)
    ot_room_charge = Column(Float, default=0.0)
    equipment_charge = Column(Float, default=0.0)
    consumables_charge = Column(Float, default=0.0)
    procedure_charge = Column(Float, default=0.0)
    other_charges = Column(Float, default=0.0)
    billed = Column(Boolean, default=False)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    admission = relationship("Admission", back_populates="ot_schedules")
    patient = relationship("Patient", foreign_keys=[patient_id])
    surgeon = relationship("User", foreign_keys=[surgeon_id])

    @property
    def total_charges(self) -> float:
        return float(
            (self.surgeon_fee or 0) + (self.anaesthetist_fee or 0) +
            (self.ot_room_charge or 0) + (self.equipment_charge or 0) +
            (self.consumables_charge or 0) + (self.procedure_charge or 0) +
            (self.other_charges or 0)
        )


class AdmissionDocument(Base):
    __tablename__ = "admission_documents"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    document_type = Column(String(50), nullable=False)  # consent_form, referral_letter, insurance_doc, lab_report, other
    document_name = Column(String(200), nullable=False)
    file_name = Column(String(255), nullable=False)  # stored filename on disk
    file_path = Column(String(500), nullable=False)  # relative path under uploads/
    file_size = Column(Integer)  # bytes
    mime_type = Column(String(100))
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    admission = relationship("Admission", back_populates="documents")
    uploaded_by = relationship("User", foreign_keys=[uploaded_by_id])


class NursingNote(Base):
    __tablename__ = "nursing_notes"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    nurse_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shift = Column(String(20), nullable=False)  # morning, afternoon, night
    note_type = Column(String(30), nullable=False)  # observation, medication, vitals, procedure, handover, general
    content = Column(Text, nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    admission = relationship("Admission", back_populates="nursing_notes")
    nurse = relationship("User", foreign_keys=[nurse_id])


class DietOrder(Base):
    __tablename__ = "diet_orders"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    diet_type = Column(String(30), nullable=False)  # regular, diabetic, liquid, soft, npo, low_salt, renal, cardiac
    meal_instructions = Column(Text, nullable=True)  # specific meal-time instructions
    allergies = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    ordered_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    admission = relationship("Admission", back_populates="diet_orders")
    ordered_by = relationship("User", foreign_keys=[ordered_by_id])


class VitalSigns(Base):
    __tablename__ = "vital_signs"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    recorded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    shift = Column(String(20), nullable=True)  # morning, afternoon, night

    bp_systolic = Column(Integer, nullable=True)        # mmHg
    bp_diastolic = Column(Integer, nullable=True)       # mmHg
    heart_rate = Column(Integer, nullable=True)         # bpm
    respiratory_rate = Column(Integer, nullable=True)   # breaths/min
    temperature_c = Column(Float, nullable=True)        # Celsius
    spo2 = Column(Integer, nullable=True)               # %
    blood_glucose = Column(Float, nullable=True)        # mg/dL
    pain_score = Column(Integer, nullable=True)         # 0-10
    gcs_score = Column(Integer, nullable=True)          # 3-15
    weight_kg = Column(Float, nullable=True)
    height_cm = Column(Float, nullable=True)

    position = Column(String(30), nullable=True)        # sitting, lying, standing
    notes = Column(Text, nullable=True)
    is_abnormal = Column(Boolean, default=False, nullable=False)
    abnormal_flags = Column(JSON, nullable=True)        # list of flagged field names

    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    admission = relationship("Admission", back_populates="vital_signs")
    recorded_by = relationship("User", foreign_keys=[recorded_by_id])


class MedicationAdministration(Base):
    __tablename__ = "medication_administrations"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    prescription_item_id = Column(Integer, ForeignKey("prescription_items.id"), nullable=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=True)  # for PRN snapshot

    scheduled_time = Column(DateTime(timezone=True), nullable=True)  # null for PRN
    administered_at = Column(DateTime(timezone=True), nullable=True)
    administered_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    witness_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    status = Column(String(20), default="scheduled", nullable=False)
    # scheduled, given, missed, refused, held, prn

    dose_given = Column(String(100), nullable=True)   # free-text actual dose
    route = Column(String(30), nullable=True)         # oral, iv, im, sc, topical, inhalation, sublingual, rectal
    site = Column(String(100), nullable=True)         # for injections
    reason_if_not_given = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    is_prn = Column(Boolean, default=False, nullable=False)
    prn_indication = Column(Text, nullable=True)      # why PRN dose was given

    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    admission = relationship("Admission", back_populates="medication_administrations")
    prescription_item = relationship("PrescriptionItem", foreign_keys=[prescription_item_id])
    medicine = relationship("Medicine", foreign_keys=[medicine_id])
    administered_by = relationship("User", foreign_keys=[administered_by_id])
    witness = relationship("User", foreign_keys=[witness_id])


# ======================================================================
# Phase 2 — Billing & financial maturity
# ======================================================================

class AdmissionDeposit(Base):
    __tablename__ = "admission_deposits"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    deposit_number = Column(String(50), unique=True, nullable=False)
    amount = Column(Float, nullable=False)  # negative for refunds
    deposit_type = Column(String(20), default="initial", nullable=False)  # initial, topup, refund
    payment_method = Column(String(30), default="cash", nullable=False)   # cash, card, upi, cheque, online
    reference_number = Column(String(100), nullable=True)  # transaction ref / cheque #
    received_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text, nullable=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    admission = relationship("Admission", back_populates="deposits")
    received_by = relationship("User", foreign_keys=[received_by_id])


class AncillaryServiceCatalog(Base):
    __tablename__ = "ancillary_service_catalog"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    service_name = Column(String(200), nullable=False)
    service_code = Column(String(50), nullable=True)
    category = Column(String(30), nullable=False)  # imaging, physiotherapy, dialysis, oxygen, equipment, consumable, other
    default_charge = Column(Float, nullable=False, default=0.0)
    charge_unit = Column(String(20), default="per_session")  # per_session, per_hour, per_day, per_unit
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Procedure(Base):
    __tablename__ = "procedures"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    name = Column(String(200), nullable=False)
    default_rate = Column(Float, nullable=False, default=0.0)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (UniqueConstraint("hospital_id", "name", name="uq_procedure_hospital_name"),)


class AdmissionAncillaryCharge(Base):
    __tablename__ = "admission_ancillary_charges"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("ancillary_service_catalog.id"), nullable=False)
    quantity = Column(Float, default=1.0)
    unit_price = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    charged_at = Column(DateTime(timezone=True), server_default=func.now())
    performed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    billed = Column(Boolean, default=False)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    admission = relationship("Admission", back_populates="ancillary_charges")
    service = relationship("AncillaryServiceCatalog", foreign_keys=[service_id])


class SurgeryPackage(Base):
    __tablename__ = "surgery_packages"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    package_name = Column(String(200), nullable=False)
    package_code = Column(String(50), nullable=True)
    base_price = Column(Float, nullable=False)
    included_room_type = Column(String(30), nullable=True)
    included_stay_days = Column(Integer, default=0)
    included_services = Column(JSON, nullable=True)  # ["pharmacy", "lab", "doctor_visit", ...]
    excess_per_day_charge = Column(Float, default=0.0)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class AdmissionPackage(Base):
    __tablename__ = "admission_packages"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), unique=True, nullable=False)
    package_id = Column(Integer, ForeignKey("surgery_packages.id"), nullable=False)
    agreed_price = Column(Float, nullable=False)
    applied_at = Column(DateTime(timezone=True), server_default=func.now())
    applied_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    notes = Column(Text, nullable=True)

    admission = relationship("Admission", back_populates="package_assignment")
    package = relationship("SurgeryPackage", foreign_keys=[package_id])


class InsurancePreAuth(Base):
    __tablename__ = "insurance_preauths"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    insurance_provider = Column(String(200), nullable=False)
    policy_number = Column(String(100), nullable=True)
    tpa_id = Column(Integer, ForeignKey("tpa_companies.id"), nullable=True)
    requested_amount = Column(Float, nullable=False)
    approved_amount = Column(Float, default=0.0)
    status = Column(String(30), default="requested")
    # requested, approved, rejected, expansion_requested, expanded, expired
    request_date = Column(DateTime(timezone=True), server_default=func.now())
    approval_date = Column(DateTime(timezone=True), nullable=True)
    validity_days = Column(Integer, nullable=True)
    approval_document_path = Column(String(500), nullable=True)
    approval_reference = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    admission = relationship("Admission", back_populates="preauth_requests")
    patient = relationship("Patient", foreign_keys=[patient_id])
    tpa = relationship("TPACompany", foreign_keys=[tpa_id])
    expansions = relationship("InsurancePreAuthExpansion", back_populates="preauth", cascade="all, delete-orphan")


class InsurancePreAuthExpansion(Base):
    __tablename__ = "insurance_preauth_expansions"

    id = Column(Integer, primary_key=True, index=True)
    preauth_id = Column(Integer, ForeignKey("insurance_preauths.id"), nullable=False)
    requested_amount = Column(Float, nullable=False)
    approved_amount = Column(Float, default=0.0)
    status = Column(String(30), default="requested")  # requested, approved, rejected
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    decided_at = Column(DateTime(timezone=True), nullable=True)
    document_path = Column(String(500), nullable=True)
    reason = Column(Text, nullable=True)
    requested_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    preauth = relationship("InsurancePreAuth", back_populates="expansions")


class TPACompany(Base):
    __tablename__ = "tpa_companies"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    tpa_name = Column(String(200), nullable=False)
    tpa_code = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    phone = Column(String(15), nullable=True)
    email = Column(String(100), nullable=True)
    default_discount_percent = Column(Float, default=0.0)
    contract_details = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ======================================================================
# ICU add-ons: Intake/Output fluid balance + Critical lab value alerts
# ======================================================================

class FluidBalance(Base):
    __tablename__ = "fluid_balance_entries"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    recorded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    shift = Column(String(20), nullable=False)  # morning, afternoon, night
    io_type = Column(String(10), nullable=False)  # intake, output
    category = Column(String(30), nullable=False)
    # intake: oral, iv, ng_tube, blood_product, irrigation, other
    # output: urine, drain, ng_aspirate, vomitus, stool, blood_loss, other
    amount_ml = Column(Float, nullable=False)  # stored positive for both intake and output; sign inferred from io_type
    notes = Column(Text, nullable=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    admission = relationship("Admission", foreign_keys=[admission_id])
    recorded_by = relationship("User", foreign_keys=[recorded_by_id])


class CriticalLabAlert(Base):
    __tablename__ = "critical_lab_alerts"

    id = Column(Integer, primary_key=True, index=True)
    lab_order_id = Column(Integer, ForeignKey("patient_lab_orders.id"), nullable=False)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    parameter_id = Column(Integer, ForeignKey("lab_test_parameters.id"), nullable=True)
    parameter_name = Column(String(200), nullable=True)
    actual_value = Column(String(100), nullable=True)
    critical_min = Column(Float, nullable=True)
    critical_max = Column(Float, nullable=True)
    severity = Column(String(20), default="critical")  # high, critical
    status = Column(String(20), default="new", nullable=False)
    # new, acknowledged, addressed

    acknowledged_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    addressed_notes = Column(Text, nullable=True)

    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ======================================================================
# Phase 4 — Compliance & quality
# ======================================================================

class ConsentTemplate(Base):
    __tablename__ = "consent_templates"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    consent_type = Column(String(40), nullable=False)
    # surgical, anaesthesia, blood_transfusion, high_risk_procedure, general_treatment, research
    template_name = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    language = Column(String(30), default="english")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Consent(Base):
    __tablename__ = "consents"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    consent_type = Column(String(40), nullable=False)
    template_id = Column(Integer, ForeignKey("consent_templates.id"), nullable=True)
    procedure_name = Column(String(200), nullable=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    risks_explained = Column(Text, nullable=True)
    language = Column(String(30), default="english")

    # Signatures — stored as text or base64 drawn signature
    patient_signature = Column(Text, nullable=True)   # typed name OR base64 image
    patient_signature_type = Column(String(10), default="typed")  # typed, drawn
    signed_by = Column(String(20), default="patient")  # patient, guardian, proxy
    guardian_name = Column(String(200), nullable=True)
    guardian_relationship = Column(String(100), nullable=True)
    witness_name = Column(String(200), nullable=True)
    witness_signature = Column(Text, nullable=True)

    signed_at = Column(DateTime(timezone=True), server_default=func.now())
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    withdrawal_reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    admission = relationship("Admission", foreign_keys=[admission_id])
    patient = relationship("Patient", foreign_keys=[patient_id])
    doctor = relationship("User", foreign_keys=[doctor_id])
    template = relationship("ConsentTemplate", foreign_keys=[template_id])


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    incident_type = Column(String(40), nullable=False)
    # fall, medication_error, pressure_ulcer, needle_stick, infection,
    # equipment_failure, documentation_error, wrong_patient, other
    severity = Column(String(20), nullable=False)  # low, medium, high, critical
    incident_date = Column(DateTime(timezone=True), nullable=False)
    location = Column(String(200), nullable=True)
    description = Column(Text, nullable=False)
    immediate_action = Column(Text, nullable=True)
    witnessed_by = Column(String(200), nullable=True)  # free-text — can be multiple names

    status = Column(String(20), default="reported", nullable=False)
    # reported, investigating, resolved, closed
    investigation_notes = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    resolution = Column(Text, nullable=True)
    corrective_actions = Column(Text, nullable=True)
    preventive_measures = Column(Text, nullable=True)

    reported_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    investigated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    closed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ======================================================================
# Phase 3 — Operational workflow
# ======================================================================

class BedTransferHistory(Base):
    __tablename__ = "bed_transfer_history"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    from_room_id = Column(Integer, ForeignKey("room_management.id"), nullable=True)
    from_bed_id = Column(Integer, ForeignKey("beds.id"), nullable=True)
    to_room_id = Column(Integer, ForeignKey("room_management.id"), nullable=False)
    to_bed_id = Column(Integer, ForeignKey("beds.id"), nullable=True)
    transfer_type = Column(String(20), default="room_change", nullable=False)
    # bed_change, room_change, ward_change
    reason = Column(Text, nullable=False)
    transfer_note = Column(Text, nullable=True)  # clinical handover note for ward_change
    transferred_at = Column(DateTime(timezone=True), server_default=func.now())
    transferred_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Inter-ward transfer accept flow
    status = Column(String(20), default="completed", nullable=False)
    # completed (simple bed/room change), pending, accepted, cancelled
    accepting_doctor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    accepting_nurse_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)

    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    admission = relationship("Admission", foreign_keys=[admission_id])
    from_room = relationship("RoomManagement", foreign_keys=[from_room_id])
    to_room = relationship("RoomManagement", foreign_keys=[to_room_id])
    from_bed = relationship("Bed", foreign_keys=[from_bed_id])
    to_bed = relationship("Bed", foreign_keys=[to_bed_id])
    transferred_by = relationship("User", foreign_keys=[transferred_by_id])


class BedTurnoverLog(Base):
    __tablename__ = "bed_turnover_log"

    id = Column(Integer, primary_key=True, index=True)
    bed_id = Column(Integer, ForeignKey("beds.id"), nullable=False)
    status_from = Column(String(20), nullable=False)
    status_to = Column(String(20), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    changed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)

    bed = relationship("Bed", foreign_keys=[bed_id])
    changed_by = relationship("User", foreign_keys=[changed_by_id])


class BedReservation(Base):
    __tablename__ = "bed_reservations"

    id = Column(Integer, primary_key=True, index=True)
    bed_id = Column(Integer, ForeignKey("beds.id"), nullable=True)  # null = any bed in room/type
    room_id = Column(Integer, ForeignKey("room_management.id"), nullable=True)
    room_type = Column(String(30), nullable=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    patient_name_cache = Column(String(200), nullable=True)  # for anonymous/external holds
    reserved_for_date = Column(DateTime(timezone=True), nullable=False)
    reservation_reason = Column(String(30), default="elective")
    # elective, post_op, transfer, other
    status = Column(String(20), default="active", nullable=False)
    # active, converted, cancelled, expired
    notes = Column(Text, nullable=True)
    related_admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True)
    reserved_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    bed = relationship("Bed", foreign_keys=[bed_id])
    room = relationship("RoomManagement", foreign_keys=[room_id])
    patient = relationship("Patient", foreign_keys=[patient_id])
    reserved_by = relationship("User", foreign_keys=[reserved_by_id])


class NurseAssignment(Base):
    __tablename__ = "nurse_assignments"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    nurse_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shift = Column(String(20), nullable=False)  # morning, afternoon, night
    assignment_date = Column(DateTime(timezone=True), nullable=False)  # just the date; time part unused
    is_primary = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    assigned_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    admission = relationship("Admission", foreign_keys=[admission_id])
    nurse = relationship("User", foreign_keys=[nurse_id])


class NurseShiftRoster(Base):
    """Duty roster — defines which nurses are scheduled to work which shifts on
    which dates, independent of patient assignments. Drives the Assign Nurse
    dropdown filter and the coverage report."""
    __tablename__ = "nurse_shift_roster"

    id = Column(Integer, primary_key=True, index=True)
    nurse_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    roster_date = Column(DateTime(timezone=True), nullable=False)  # date only, time part unused
    shift = Column(String(20), nullable=False)  # morning, afternoon, night
    status = Column(String(20), default="working", nullable=False)
    # working — scheduled to work this shift
    # leave — approved leave (sick / planned), counts against coverage but blocks assignment
    # off — scheduled rest day, blocks assignment
    # on_call — available if needed, can be assigned but doesn't count toward minimum coverage
    ward = Column(String(100), nullable=True)  # optional ward/department assignment
    notes = Column(Text, nullable=True)
    assigned_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    nurse = relationship("User", foreign_keys=[nurse_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])

    __table_args__ = (
        UniqueConstraint("nurse_id", "roster_date", "shift", name="uq_nurse_shift_per_date"),
    )


class BillSplit(Base):
    __tablename__ = "bill_splits"

    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False)
    payer_type = Column(String(20), nullable=False)  # cash, insurance, tpa
    payer_name = Column(String(200), nullable=False)
    tpa_id = Column(Integer, ForeignKey("tpa_companies.id"), nullable=True)
    amount = Column(Float, nullable=False)
    payment_status = Column(String(20), default="pending")  # pending, received
    payment_date = Column(DateTime(timezone=True), nullable=True)
    payment_reference = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    bill = relationship("Bill", back_populates="splits")
    tpa = relationship("TPACompany", foreign_keys=[tpa_id])