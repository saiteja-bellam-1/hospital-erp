from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, ForeignKey, Text, Float, Numeric, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base

class RoomType(Base):
    """User-manageable room type catalog per hospital.
    Auto-seeded from the built-in list on first access if the table is empty."""
    __tablename__ = "room_types"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    key = Column(String(50), nullable=False)    # slug: "icu", "general", "my_custom_ward"
    label = Column(String(100), nullable=False)  # display name
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)  # True for built-in seed entries
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("hospital_id", "key", name="uq_room_type_key_per_hospital"),
    )


class RoomManagement(Base):
    __tablename__ = "room_management"

    id = Column(Integer, primary_key=True, index=True)
    room_number = Column(String(20), nullable=False)
    # Expanded room types — see ROOM_TYPES in routes/inpatient.py for full list
    room_type = Column(String(30), nullable=False)
    floor = Column(String(10))
    department = Column(String(50))
    ward = Column(String(100))
    bed_count = Column(Integer, default=1)
    available_beds = Column(Integer, default=1)
    room_charge_per_day = Column(Float, nullable=False)
    nursing_charge_per_visit = Column(Numeric(10, 2), default=0.00)
    # Structured amenities — JSON list of strings, e.g. ["ac","tv","oxygen_point"]
    amenities = Column(Text)
    # Clinical flags
    is_isolation = Column(Boolean, default=False)   # negative-pressure / infection-control room
    gender_policy = Column(String(10), default="mixed")  # mixed | male | female
    is_active = Column(Boolean, default=True)
    is_occupied = Column(Boolean, default=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    admissions = relationship("Admission", back_populates="room")
    beds = relationship("Bed", back_populates="room")
    maintenance_requests = relationship("RoomMaintenance", back_populates="room", foreign_keys="RoomMaintenance.room_id")


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
    status = Column(String(20), default="admitted")  # draft, admitted, discharged, transferred, cancelled
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
    # Person accompanying / admitting the patient (printed on face sheet).
    admitting_person_name = Column(String(200), nullable=True)
    admitting_person_relationship = Column(String(100), nullable=True)
    admitting_person_address = Column(Text, nullable=True)
    admitting_person_phone = Column(String(20), nullable=True)
    admitting_person_id_proof = Column(String(200), nullable=True)
    attending_physician_id = Column(Integer, ForeignKey("users.id"))
    bed_number = Column(String(10))  # legacy free-text field
    bed_id = Column(Integer, ForeignKey("beds.id"), nullable=True)  # structured bed reference
    # Snapshot of the room rate at admission time. Used to bill the stay
    # segment before the first room transfer at the rate in effect when the
    # patient was admitted, even if the room rate (or room) changed later.
    initial_room_charge_per_day = Column(Float, nullable=True)
    # Phase 4 — readmission tracking (populated on admission create)
    is_readmission = Column(Boolean, default=False)
    previous_admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True)
    days_since_last_discharge = Column(Integer, nullable=True)
    # B7 — Emergency / casualty fields (only meaningful when admission_type='emergency')
    triage_level = Column(Integer, nullable=True)  # 1 (resuscitation) … 5 (non-urgent), per ESI/CTAS
    chief_complaint = Column(Text, nullable=True)
    arrival_mode = Column(String(20), nullable=True)  # walk_in, ambulance, referred, police
    ambulance_details = Column(Text, nullable=True)  # vehicle no., paramedic name, vitals on arrival
    is_mlc = Column(Boolean, default=False)
    mlc_number = Column(String(50), nullable=True)
    mlc_type = Column(String(30), nullable=True)  # rta, assault, poisoning, burn, sexual_assault, attempted_suicide, other
    police_station_informed = Column(String(200), nullable=True)
    mlc_informed_at = Column(DateTime(timezone=True), nullable=True)
    # B7.6 — Observation case (≤24h, room rent skipped, lighter discharge gate)
    is_observation = Column(Boolean, default=False, nullable=False)
    # B7.7 — Deposit waiver (e.g. emergency cases per Supreme Court / CEA Act)
    deposit_waived = Column(Boolean, default=False, nullable=False)
    deposit_waiver_reason = Column(Text, nullable=True)
    deposit_waived_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    deposit_waived_at = Column(DateTime(timezone=True), nullable=True)
    # B1 — Payer scheme (Cash / Aarogyasri / Teachers / Govt Employee / Private Insurance / TPA).
    # payer_type is denormalised from PayerScheme.scheme_type so bill splits + reports
    # can filter without a join. Both nullable for back-compat with rows created before
    # this column existed.
    payer_scheme_id = Column(Integer, ForeignKey("payer_schemes.id"), nullable=True)
    payer_type = Column(String(30), nullable=True)
    scheme_member_id = Column(String(100), nullable=True)
    scheme_approval_status = Column(String(20), default="none", nullable=False)
    # none, pending, approved, rejected, disconnected
    scheme_approval_ref = Column(String(100), nullable=True)
    scheme_approval_amount = Column(Float, nullable=True)
    # B3 — Referring doctor (may be internal user or external free-text name)
    # and IP doctor acceptance handshake. Existing admissions get acceptance_status
    # 'accepted' by default so back-compat is preserved.
    referring_doctor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    referring_external_name = Column(String(200), nullable=True)
    acceptance_status = Column(String(20), default="accepted", nullable=False)
    # pending, accepted, rejected
    accepted_by_doctor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    patient = relationship("Patient", back_populates="admissions")
    admitting_doctor = relationship("User", foreign_keys=[admitting_doctor_id])
    referring_doctor = relationship("User", foreign_keys=[referring_doctor_id])
    accepted_by_doctor = relationship("User", foreign_keys=[accepted_by_doctor_id])
    payer_scheme = relationship("PayerScheme", foreign_keys=[payer_scheme_id])
    bed = relationship("Bed", foreign_keys=[bed_id])
    room = relationship("RoomManagement", back_populates="admissions")
    discharge = relationship("DischargeRecord", back_populates="admission", uselist=False)
    visits = relationship("PatientVisit", back_populates="admission")
    ot_schedules = relationship("OTSchedule", back_populates="admission")
    lab_orders = relationship("PatientLabOrder", back_populates="admission")
    documents = relationship("AdmissionDocument", back_populates="admission")
    nursing_notes = relationship("NursingNote", back_populates="admission")
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
    # Structured take-home prescription set on discharge. Distinct from inpatient
    # ward prescriptions (which are administered during the stay). Each item is
    # {medicine_id?, medicine_name, dosage, frequency, duration, quantity, instructions}.
    take_home_medications = Column(JSON, nullable=True)
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


class DAMARecord(Base):
    """Discharge Against Medical Advice — structured liability record.

    Indian context: references Section 88/92 IPC ('absolves staff of
    consequences when patient leaves against medical advice'). Mandatory for
    any DAMA discharge; the unsigned form has no legal weight."""
    __tablename__ = "dama_records"

    id = Column(Integer, primary_key=True, index=True)
    discharge_id = Column(Integer, ForeignKey("discharge_records.id"), nullable=False, unique=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)

    # Clinical context
    attending_doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    medical_advice_given = Column(Text, nullable=False)
    risks_explained = Column(Text, nullable=False)
    language_used = Column(String(30), default="english")

    # Acknowledgements (both must be True at submit-time; persisted for audit)
    patient_acknowledges_advice = Column(Boolean, default=False, nullable=False)
    patient_absolves_hospital = Column(Boolean, default=False, nullable=False)

    # Signatures
    signed_by = Column(String(20), default="patient")  # patient, guardian
    guardian_name = Column(String(200), nullable=True)
    guardian_relationship = Column(String(100), nullable=True)
    primary_signature = Column(Text, nullable=False)  # typed name or base64 image
    primary_signature_type = Column(String(10), default="typed")  # typed, drawn

    witness_name = Column(String(200), nullable=False)
    witness_designation = Column(String(100), nullable=True)  # 'Nurse', 'Doctor', 'Senior Resident', etc.
    witness_signature = Column(Text, nullable=False)
    witness_signature_type = Column(String(10), default="typed")

    notes = Column(Text, nullable=True)

    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    discharge = relationship("DischargeRecord", foreign_keys=[discharge_id])
    admission = relationship("Admission", foreign_keys=[admission_id])


class InpatientRateConfig(Base):
    __tablename__ = "inpatient_rate_configs"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    doctor_visit_rate = Column(Numeric(10, 2), default=0.00)
    # B4 — duty-doctor (covering doctor on the floor) round fee. Separate from
    # the consultant's per-visit fee. Falls back to doctor_visit_rate if zero.
    duty_visit_rate = Column(Numeric(10, 2), default=0.00)
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
    auto_posted = Column(Boolean, default=False)       # True if created by the nightly daily-charges job
    # Optional structured ward-round checklist. Free-text `notes` remains the
    # primary clinical narrative; these checkboxes drive the "rounded today"
    # dashboard signals and discharge-summary auto-fill.
    vitals_reviewed = Column(Boolean, default=False)
    labs_reviewed = Column(Boolean, default=False)
    pain_assessed = Column(Boolean, default=False)
    mobility_checked = Column(Boolean, default=False)
    plan_for_today = Column(Text, nullable=True)
    family_updated = Column(Boolean, default=False)
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


class CodeBlueEvent(Base):
    """Code Blue / Rapid Response Team activation log. One row per activation,
    reportable for monthly safety stats (NABH chapter on emergency response)."""
    __tablename__ = "code_blue_events"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True)  # may be a visitor / outpatient
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    event_type = Column(String(20), default="code_blue")  # code_blue, rrt
    event_datetime = Column(DateTime(timezone=True), nullable=False)
    location = Column(String(200), nullable=False)        # e.g. 'ICU bed 3', 'Reception waiting area'
    activated_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    response_time_seconds = Column(Integer, nullable=True)  # from activation to first responder arrival
    team_members = Column(Text, nullable=True)              # comma-separated names / ids
    interventions = Column(Text, nullable=True)             # CPR, defibrillation, intubation, drugs given
    outcome = Column(String(30), nullable=False)            # rosc, transferred_icu, expired, false_alarm
    debrief_notes = Column(Text, nullable=True)

    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    admission = relationship("Admission", foreign_keys=[admission_id])
    patient = relationship("Patient", foreign_keys=[patient_id])
    activated_by = relationship("User", foreign_keys=[activated_by_id])


class ShiftHandover(Base):
    """Structured nurse-to-nurse shift handover. One row per admission per
    shift end; the incoming nurse acknowledges before her shift starts."""
    __tablename__ = "shift_handovers"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    handover_date = Column(DateTime(timezone=True), nullable=False)
    from_shift = Column(String(20), nullable=False)  # morning, afternoon, night
    from_nurse_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_nurse_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    # Structured handover content
    patient_status_summary = Column(Text, nullable=True)
    pending_tasks = Column(Text, nullable=True)        # bullet list as text
    alerts_to_watch = Column(Text, nullable=True)      # vital alarms, isolation, fall risk
    family_communication = Column(Text, nullable=True) # what was said to relatives
    on_call_contacts = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    admission = relationship("Admission", foreign_keys=[admission_id])
    from_nurse = relationship("User", foreign_keys=[from_nurse_id])
    to_nurse = relationship("User", foreign_keys=[to_nurse_id])


class LeaveOfAbsence(Base):
    """Patient temporarily off-ward (pass-out / LOA). Bed remains held; room
    rent is skipped for any day fully covered by an active LOA window. No
    room rent skip is given for partial days — a patient who returns the same
    afternoon still pays for that day's room."""
    __tablename__ = "leave_of_absences"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    start_datetime = Column(DateTime(timezone=True), nullable=False)
    expected_return_datetime = Column(DateTime(timezone=True), nullable=False)
    actual_return_datetime = Column(DateTime(timezone=True), nullable=True)
    reason = Column(Text, nullable=False)
    approved_by_doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String(20), default="active")  # active, returned, no_show, cancelled
    notes = Column(Text, nullable=True)
    bed_held = Column(Boolean, default=True)

    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    admission = relationship("Admission", foreign_keys=[admission_id])
    approved_by_doctor = relationship("User", foreign_keys=[approved_by_doctor_id])


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
    # Per-category granular inclusion. When "lab" is in included_services and
    # lab_coverage_mode == "selected", only the LabTest IDs listed in
    # included_lab_test_ids are covered; the rest bill normally. Mode "all" (the
    # default) preserves the original behaviour of covering every lab order.
    lab_coverage_mode = Column(String(20), default="all")  # "all" | "selected"
    included_lab_test_ids = Column(JSON, nullable=True)    # list[int] of LabTest.id
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
    doc_number = Column(String(50), unique=True, nullable=True, index=True)
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


class ConsentDocReservation(Base):
    """A pre-allocated consent doc number reserved during the admit-patient
    wizard so staff can write/print the number on a physical form before
    the admission (and therefore the Consent row) exists. Consumed when the
    matching Consent record is actually created.
    """
    __tablename__ = "consent_doc_reservations"

    id = Column(Integer, primary_key=True, index=True)
    doc_number = Column(String(50), unique=True, nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    consent_type = Column(String(40), nullable=False)
    template_id = Column(Integer, ForeignKey("consent_templates.id"), nullable=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    reserved_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reserved_at = Column(DateTime(timezone=True), server_default=func.now())
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    consumed_consent_id = Column(Integer, ForeignKey("consents.id"), nullable=True)


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

    # Snapshot of room rates at transfer time. Used to bill the stay segments
    # before/after this transfer at the rate that was actually in effect.
    from_room_charge_per_day = Column(Float, nullable=True)
    to_room_charge_per_day = Column(Float, nullable=True)

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


class RoomMaintenance(Base):
    """Tracks maintenance issues reported against a room or specific bed."""
    __tablename__ = "room_maintenance"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("room_management.id"), nullable=False)
    bed_id = Column(Integer, ForeignKey("beds.id"), nullable=True)   # None = whole room
    # Issue classification
    issue_type = Column(String(30), nullable=False)  # electrical, plumbing, hvac, equipment, structural, cleaning, other
    priority = Column(String(10), default="routine")  # routine | urgent | emergency
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    # Workflow
    status = Column(String(20), default="open")   # open | in_progress | completed | deferred
    assigned_to = Column(String(200), nullable=True)   # free-text staff name / team
    scheduled_date = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)
    # Audit
    reported_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    room = relationship("RoomManagement", back_populates="maintenance_requests", foreign_keys=[room_id])
    bed = relationship("Bed", foreign_keys=[bed_id])
    reported_by = relationship("User", foreign_keys=[reported_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])


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


# ============================================================
# B6 — Body release / mortuary / post-mortem coordination
# ============================================================
class BodyReleaseRecord(Base):
    """Tracks the body from death → mortuary → (optional autopsy) → release.
    One row per discharge (death). Distinct from DischargeRecord so the
    mortuary workflow can evolve without bloating discharge."""
    __tablename__ = "body_release_records"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False, unique=True)
    discharge_id = Column(Integer, ForeignKey("discharge_records.id"), nullable=False)

    # Mortuary tracking
    mortuary_slot = Column(String(20), nullable=True)
    body_in_mortuary_at = Column(DateTime(timezone=True), nullable=True)
    body_out_mortuary_at = Column(DateTime(timezone=True), nullable=True)

    # Embalming (required for long-distance transport / delayed handover)
    embalming_done = Column(Boolean, default=False, nullable=False)
    embalming_at = Column(DateTime(timezone=True), nullable=True)
    embalmed_by = Column(String(200), nullable=True)

    # Post-mortem (typically required for MLC)
    post_mortem_required = Column(Boolean, default=False, nullable=False)
    pm_hospital = Column(String(200), nullable=True)
    pm_doctor = Column(String(200), nullable=True)
    pm_referred_at = Column(DateTime(timezone=True), nullable=True)
    pm_completed_at = Column(DateTime(timezone=True), nullable=True)
    pm_report_received = Column(Boolean, default=False, nullable=False)
    pm_report_number = Column(String(100), nullable=True)

    # Police clearance (mandatory for MLC body release)
    police_noc_required = Column(Boolean, default=False, nullable=False)
    police_noc_received = Column(Boolean, default=False, nullable=False)
    police_noc_number = Column(String(100), nullable=True)
    police_noc_received_at = Column(DateTime(timezone=True), nullable=True)

    # Release details
    body_released = Column(Boolean, default=False, nullable=False)
    body_released_at = Column(DateTime(timezone=True), nullable=True)
    released_to_name = Column(String(200), nullable=True)
    released_to_relationship = Column(String(50), nullable=True)
    released_to_phone = Column(String(20), nullable=True)
    released_to_id_proof_type = Column(String(30), nullable=True)  # aadhar, voter, license, passport, other
    released_to_id_proof_number = Column(String(50), nullable=True)
    released_to_address = Column(Text, nullable=True)
    witness_name = Column(String(200), nullable=True)
    witness_phone = Column(String(20), nullable=True)
    witness_id_proof = Column(String(100), nullable=True)
    transport_details = Column(Text, nullable=True)  # vehicle no., ambulance, hearse
    notes = Column(Text, nullable=True)
    released_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    admission = relationship("Admission", foreign_keys=[admission_id])
    discharge = relationship("DischargeRecord", foreign_keys=[discharge_id])
    released_by = relationship("User", foreign_keys=[released_by_id])

# ======================================================================
# B1 — Payer scheme master + B2 — payer change history
# ======================================================================

class PayerScheme(Base):
    """Catalog of payer schemes the hospital accepts: Cash, private insurance,
    TPAs, and government schemes (Aarogyasri, Teachers' Health Scheme, Govt
    Employee Health Scheme, etc.). The hospital admin can edit this list."""
    __tablename__ = "payer_schemes"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    code = Column(String(40), nullable=False)
    name = Column(String(200), nullable=False)
    scheme_type = Column(String(20), nullable=False)
    # cash, private_insurance, tpa, govt_scheme
    active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("hospital_id", "code", name="uq_payer_scheme_code_per_hospital"),
    )


class AdmissionPayerChange(Base):
    """Audit log of payer-mode conversions during an admission. Each row
    captures one transition (e.g., Aarogyasri rejected → Cash)."""
    __tablename__ = "admission_payer_changes"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    from_scheme_id = Column(Integer, ForeignKey("payer_schemes.id"), nullable=True)
    to_scheme_id = Column(Integer, ForeignKey("payer_schemes.id"), nullable=False)
    from_payer_type = Column(String(30), nullable=True)
    to_payer_type = Column(String(30), nullable=False)
    reason = Column(Text, nullable=False)
    changed_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)

    admission = relationship("Admission", foreign_keys=[admission_id])
    from_scheme = relationship("PayerScheme", foreign_keys=[from_scheme_id])
    to_scheme = relationship("PayerScheme", foreign_keys=[to_scheme_id])
    changed_by = relationship("User", foreign_keys=[changed_by_id])


# ======================================================================
# B6 — Gate pass (printable security artifact on discharge)
# ======================================================================

class GatePass(Base):
    """Printable gate pass issued after discharge. Guard at the exit checks
    this. Normally only issued when outstanding balance is zero; supports
    an override with documented reason for edge cases (insurance pending,
    etc.)."""
    __tablename__ = "gate_passes"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False)
    pass_number = Column(String(50), nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    generated_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    vehicle_no = Column(String(40), nullable=True)
    attendant_name = Column(String(200), nullable=True)
    attendant_relationship = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    # Set when balance > 0 at issue time
    override_balance = Column(Boolean, default=False, nullable=False)
    override_reason = Column(Text, nullable=True)
    outstanding_at_issue = Column(Float, default=0.0)
    qr_token = Column(String(64), nullable=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)

    admission = relationship("Admission", foreign_keys=[admission_id])
    generated_by = relationship("User", foreign_keys=[generated_by_id])

    __table_args__ = (
        UniqueConstraint("admission_id", name="uq_gate_pass_per_admission"),
    )


# ======================================================================
# B4 — Doctor duty roster (identifies duty doctors per shift)
# ======================================================================

class DoctorDutyRoster(Base):
    """Per-shift duty roster for doctors. Mirrors NurseShiftRoster.
    Used to identify the duty doctor on the floor at any moment — visits
    flagged as `duty_doctor_visit` are only accepted from a doctor whose
    roster entry covers the visit time."""
    __tablename__ = "doctor_duty_roster"

    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    roster_date = Column(DateTime(timezone=True), nullable=False)  # date-only; time part unused
    shift = Column(String(20), nullable=False)  # morning, afternoon, night
    status = Column(String(20), default="working", nullable=False)
    # working — scheduled on duty
    # on_call — available if called, can record duty visits
    # leave — approved leave, blocks duty visits
    # off — rest day, blocks duty visits
    ward = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    assigned_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    doctor = relationship("User", foreign_keys=[doctor_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])

    __table_args__ = (
        UniqueConstraint("doctor_id", "roster_date", "shift", name="uq_doctor_shift_per_date"),
    )


class RoomTypeRateConfig(Base):
    """Per-hospital, per-room-type nursing charge configuration.
    Sits between per-room nursing_charge_per_visit and the global
    InpatientRateConfig.nurse_visit_rate in the charge resolution chain."""
    __tablename__ = "room_type_rate_configs"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    room_type = Column(String(30), nullable=False)
    nursing_charge_per_visit = Column(Numeric(10, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("hospital_id", "room_type", name="uq_room_type_rate_per_hospital"),
    )


class DoctorRoomTypeRate(Base):
    """Per-doctor, per-room-type visit rate override.
    When a doctor visits a patient, the charge resolution is:
      explicit amount → this table → doctor.inpatient_fee_inr → global rate → 0"""
    __tablename__ = "doctor_room_type_rates"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    room_type = Column(String(30), nullable=False)
    visit_rate = Column(Numeric(10, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    doctor = relationship("User", foreign_keys=[doctor_id])

    __table_args__ = (
        UniqueConstraint("hospital_id", "doctor_id", "room_type", name="uq_doctor_room_type_rate"),
    )


class MealPlan(Base):
    """Per-room-type meal pricing. One row per (hospital, room_type, meal_type)."""
    __tablename__ = "meal_plans"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    room_type = Column(String(30), nullable=False)
    meal_type = Column(String(20), nullable=False)  # breakfast/lunch/dinner/snacks
    price = Column(Numeric(10, 2), nullable=False, default=0)
    description = Column(String(200), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("hospital_id", "room_type", "meal_type", name="uq_meal_plan_room_meal"),
    )


class FoodOrder(Base):
    """A scheduled meal for an admitted patient. Billable at order time;
    cancellation before billing simply drops the line. After the bill stamps
    bill_id, cancellation is blocked (must refund through the deposit flow)."""
    __tablename__ = "food_orders"

    id = Column(Integer, primary_key=True, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    meal_date = Column(Date, nullable=False, index=True)
    meal_type = Column(String(20), nullable=False)  # breakfast/lunch/dinner/snacks
    status = Column(String(20), default="ordered", nullable=False)  # ordered/delivered/cancelled
    price = Column(Numeric(10, 2), nullable=False)  # snapshot at order time
    diet_preference = Column(String(50), nullable=True)  # veg/non-veg/diabetic/soft/liquid/custom
    notes = Column(Text, nullable=True)
    ordered_at = Column(DateTime(timezone=True), server_default=func.now())
    ordered_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    delivered_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancelled_reason = Column(String(200), nullable=True)
    billed = Column(Boolean, default=False, nullable=False)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)

    admission = relationship("Admission", foreign_keys=[admission_id])

    __table_args__ = (
        UniqueConstraint("admission_id", "meal_date", "meal_type", name="uq_food_order_per_meal"),
    )
