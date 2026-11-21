"""Fertility (ART) clinic and bank.

The unit of work is a treatment cycle on a couple or single-woman case.
Money still posts to the central Bill table. Donor identity lives on the
bank record; the clinic chart stores only a donor code.
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, Date, Time, JSON,
)
from sqlalchemy.orm import relationship
from config.database import Base
from app.utils.time import system_now


class ArtCentre(Base):
    """One ART clinic registration and, when held, one ART bank registration."""
    __tablename__ = "art_centres"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, unique=True, index=True)
    clinic_level = Column(Integer, nullable=False, default=1)  # 1 = IUI, 2 = IVF/ICSI
    clinic_registration_no = Column(String(80), nullable=True)
    clinic_valid_until = Column(Date, nullable=True)
    director_name = Column(String(200), nullable=True)
    bank_enabled = Column(Boolean, default=True, nullable=False)
    bank_registration_no = Column(String(80), nullable=True)
    bank_valid_until = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now)
    updated_at = Column(DateTime(timezone=True), onupdate=system_now)


class ArtService(Base):
    __tablename__ = "art_services"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    code = Column(String(40), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    category = Column(String(40), nullable=False, default="procedure")
    default_price = Column(Float, nullable=False, default=0.0)
    requires_level = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=system_now)


class ArtPackageTemplate(Base):
    __tablename__ = "art_package_templates"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    code = Column(String(40), nullable=True)
    price = Column(Float, nullable=False, default=0.0)
    included_service_codes = Column(JSON, nullable=False, default=list)
    includes_medicines = Column(Boolean, default=False, nullable=False)
    medicine_limit = Column(Float, nullable=False, default=0.0)  # 0 = no cap when included
    cancel_keep_amount = Column(Float, nullable=False, default=0.0)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=system_now)


class ArtCase(Base):
    __tablename__ = "art_cases"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    case_number = Column(String(40), nullable=False, index=True)
    case_type = Column(String(20), nullable=False)  # couple | single_woman
    woman_patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    partner_patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    status = Column(String(20), default="open", nullable=False)
    opened_at = Column(DateTime(timezone=True), default=system_now)
    opened_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now)

    woman = relationship("Patient", foreign_keys=[woman_patient_id])
    partner = relationship("Patient", foreign_keys=[partner_patient_id])
    workup = relationship("ArtWorkup", back_populates="case", uselist=False)
    cycles = relationship("ArtCycle", back_populates="case")


class ArtWorkup(Base):
    __tablename__ = "art_workups"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("art_cases.id"), nullable=False, unique=True)
    infertility_years = Column(Float, nullable=True)
    prior_pregnancies = Column(Integer, nullable=True)
    prior_cycles = Column(Integer, nullable=True)
    amh = Column(Float, nullable=True)
    antral_follicle_count = Column(Integer, nullable=True)
    tubal_status = Column(String(200), nullable=True)
    uterus_findings = Column(Text, nullable=True)
    semen_summary = Column(Text, nullable=True)
    diagnosis = Column(Text, nullable=True)
    treatment_plan = Column(Text, nullable=True)
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=system_now, onupdate=system_now)

    case = relationship("ArtCase", back_populates="workup")


class ArtCounsellorNote(Base):
    __tablename__ = "art_counsellor_notes"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("art_cases.id"), nullable=False, index=True)
    note = Column(Text, nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=system_now)


class ArtDocument(Base):
    __tablename__ = "art_documents"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("art_cases.id"), nullable=False, index=True)
    document_type = Column(String(40), nullable=False, default="report")
    document_name = Column(String(200), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=system_now)


class ArtCycle(Base):
    __tablename__ = "art_cycles"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("art_cases.id"), nullable=False, index=True)
    cycle_number = Column(String(40), nullable=False, index=True)
    cycle_type = Column(String(30), nullable=False)
    protocol = Column(String(80), nullable=True)
    protocol_change_reason = Column(Text, nullable=True)
    status = Column(String(30), default="planned", nullable=False, index=True)
    clinician_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    donor_code = Column(String(40), nullable=True)

    billing_mode = Column(String(20), nullable=False, default="itemised")
    package_template_id = Column(Integer, ForeignKey("art_package_templates.id"), nullable=True)
    agreed_price = Column(Float, nullable=False, default=0.0)
    includes_medicines = Column(Boolean, default=False, nullable=False)
    medicine_limit = Column(Float, nullable=False, default=0.0)
    medicine_consumed = Column(Float, nullable=False, default=0.0)
    cancel_keep_amount = Column(Float, nullable=False, default=0.0)
    included_service_codes = Column(JSON, nullable=False, default=list)
    estimate_snapshot = Column(JSON, nullable=True)
    advance_bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)
    billing_mode_change_reason = Column(Text, nullable=True)
    billing_mode_changed_at = Column(DateTime(timezone=True), nullable=True)

    trigger_drug = Column(String(120), nullable=True)
    trigger_at = Column(DateTime(timezone=True), nullable=True)
    cancel_reason = Column(Text, nullable=True)
    refund_bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)

    retrieval_follicles = Column(Integer, nullable=True)
    retrieval_oocytes = Column(Integer, nullable=True)
    retrieval_mii = Column(Integer, nullable=True)
    retrieval_mi = Column(Integer, nullable=True)
    retrieval_gv = Column(Integer, nullable=True)
    retrieval_at = Column(DateTime(timezone=True), nullable=True)
    fert_method = Column(String(20), nullable=True)
    fert_inseminated = Column(Integer, nullable=True)
    fert_normal = Column(Integer, nullable=True)
    fert_at = Column(DateTime(timezone=True), nullable=True)
    media_lots = Column(JSON, nullable=True)

    culture_open = Column(Boolean, default=False, nullable=False)
    culture_operator_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    linked_source_cycle_id = Column(Integer, ForeignKey("art_cycles.id"), nullable=True)

    beta_hcg_value = Column(Float, nullable=True)
    beta_hcg_positive = Column(Boolean, nullable=True)
    clinical_pregnancy = Column(Boolean, nullable=True)
    miscarriage = Column(Boolean, nullable=True)
    live_birth = Column(Boolean, nullable=True)
    outcome_notes = Column(Text, nullable=True)
    complication = Column(Text, nullable=True)
    outcome_recorded_at = Column(DateTime(timezone=True), nullable=True)

    started_at = Column(DateTime(timezone=True), default=system_now)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    case = relationship("ArtCase", back_populates="cycles")
    package = relationship("ArtPackageTemplate", foreign_keys=[package_template_id])


class ArtStimulationDay(Base):
    __tablename__ = "art_stimulation_days"

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(Integer, ForeignKey("art_cycles.id"), nullable=False, index=True)
    day_number = Column(Integer, nullable=False)
    drugs = Column(JSON, nullable=False, default=list)  # [{name, dose, route}]
    follicles_left = Column(JSON, nullable=False, default=list)
    follicles_right = Column(JSON, nullable=False, default=list)
    endometrium_mm = Column(Float, nullable=True)
    e2 = Column(Float, nullable=True)
    lh = Column(Float, nullable=True)
    progesterone = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    recorded_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    recorded_at = Column(DateTime(timezone=True), default=system_now)


class ArtAppointment(Base):
    __tablename__ = "art_appointments"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("art_cases.id"), nullable=False, index=True)
    cycle_id = Column(Integer, ForeignKey("art_cycles.id"), nullable=True, index=True)
    kind = Column(String(30), nullable=False)  # scan, iui, counsellor, opu, transfer, beta_hcg
    scheduled_date = Column(Date, nullable=False, index=True)
    scheduled_time = Column(Time, nullable=True)
    room = Column(String(80), nullable=True)
    status = Column(String(20), default="scheduled", nullable=False)
    clinician_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timeout_patient_name = Column(String(200), nullable=True)
    timeout_dob_confirmed = Column(Boolean, default=False, nullable=False)
    timeout_witness_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    timeout_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now)


class ArtConsent(Base):
    __tablename__ = "art_consents"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("art_cases.id"), nullable=False, index=True)
    cycle_id = Column(Integer, ForeignKey("art_cycles.id"), nullable=True)
    form_code = Column(String(40), nullable=False)
    signed_by_name = Column(String(200), nullable=False)
    signed_at = Column(DateTime(timezone=True), default=system_now)
    withdrawn_at = Column(DateTime(timezone=True), nullable=True)
    recorded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)


class ArtCharge(Base):
    __tablename__ = "art_charges"

    id = Column(Integer, primary_key=True, index=True)
    cycle_id = Column(Integer, ForeignKey("art_cycles.id"), nullable=False, index=True)
    service_code = Column(String(40), nullable=True)
    description = Column(String(200), nullable=False)
    kind = Column(String(20), nullable=False, default="service")  # service | medicine
    amount = Column(Float, nullable=False, default=0.0)
    covered_by_package = Column(Boolean, default=False, nullable=False)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)
    status = Column(String(20), default="open", nullable=False)  # open | voided
    created_at = Column(DateTime(timezone=True), default=system_now)


class ArtQueueEntry(Base):
    __tablename__ = "art_queue_entries"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    case_id = Column(Integer, ForeignKey("art_cases.id"), nullable=False, index=True)
    queue_date = Column(Date, nullable=False, index=True)
    token_no = Column(Integer, nullable=False)
    status = Column(String(20), default="waiting", nullable=False)
    created_at = Column(DateTime(timezone=True), default=system_now)


class ArtSpecimen(Base):
    """Oocyte, sperm, or embryo belonging to one case. Owner never changes."""
    __tablename__ = "art_specimens"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    origin_cycle_id = Column(Integer, ForeignKey("art_cycles.id"), nullable=False, index=True)
    owner_case_id = Column(Integer, ForeignKey("art_cases.id"), nullable=False, index=True)
    code = Column(String(40), nullable=False)
    sample_type = Column(String(20), nullable=False)  # embryo | oocyte | sperm
    grades = Column(JSON, nullable=False, default=list)  # [{day, grade, stage}]
    disposition = Column(String(20), default="in_culture", nullable=False)
    tank = Column(String(40), nullable=True)
    canister = Column(String(40), nullable=True)
    cane = Column(String(40), nullable=True)
    position = Column(String(40), nullable=True)
    storage_start = Column(Date, nullable=True)
    renewal_due = Column(Date, nullable=True)
    oncofertility = Column(Boolean, default=False, nullable=False)
    thaw_survived = Column(Boolean, nullable=True)
    thawed_into_cycle_id = Column(Integer, ForeignKey("art_cycles.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now)


class ArtWitnessLog(Base):
    __tablename__ = "art_witness_logs"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    cycle_id = Column(Integer, ForeignKey("art_cycles.id"), nullable=True, index=True)
    step = Column(String(40), nullable=False)
    sample_label = Column(String(80), nullable=False)
    operator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    witness_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    occurred_at = Column(DateTime(timezone=True), default=system_now)
    notes = Column(Text, nullable=True)


class ArtTankLog(Base):
    __tablename__ = "art_tank_logs"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    tank_name = Column(String(80), nullable=False)
    nitrogen_level = Column(String(40), nullable=True)
    temperature_c = Column(Float, nullable=True)
    alarm = Column(Boolean, default=False, nullable=False)
    recorded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recorded_at = Column(DateTime(timezone=True), default=system_now)


class ArtPartnerBank(Base):
    __tablename__ = "art_partner_banks"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    registration_no = Column(String(80), nullable=True)
    city = Column(String(80), nullable=True)
    phone = Column(String(30), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=system_now)


class ArtDonor(Base):
    __tablename__ = "art_donors"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    donor_code = Column(String(40), nullable=False, index=True)
    donor_type = Column(String(20), nullable=False)  # sperm | oocyte
    legal_name = Column(String(200), nullable=False)
    address = Column(Text, nullable=True)
    phone = Column(String(30), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    status = Column(String(20), default="screening", nullable=False)
    screening = Column(JSON, nullable=True)
    insurance_policy_no = Column(String(80), nullable=True)
    insurance_valid_until = Column(Date, nullable=True)
    insurance_amount = Column(Float, nullable=True)
    oocytes_retrieved = Column(Integer, nullable=True)
    over_intended_cap = Column(Boolean, default=False, nullable=False)
    cleared_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now)


class ArtBankUnit(Base):
    __tablename__ = "art_bank_units"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    donor_id = Column(Integer, ForeignKey("art_donors.id"), nullable=True, index=True)
    partner_bank_id = Column(Integer, ForeignKey("art_partner_banks.id"), nullable=True)
    external_donor_code = Column(String(40), nullable=True)
    sample_code = Column(String(40), nullable=False)
    sample_type = Column(String(20), nullable=False)
    status = Column(String(30), default="stored", nullable=False)
    tank = Column(String(40), nullable=True)
    canister = Column(String(40), nullable=True)
    cane = Column(String(40), nullable=True)
    position = Column(String(40), nullable=True)
    case_id = Column(Integer, ForeignKey("art_cases.id"), nullable=True)
    cycle_id = Column(Integer, ForeignKey("art_cycles.id"), nullable=True)
    external_clinic_name = Column(String(200), nullable=True)
    issued_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now)

    donor = relationship("ArtDonor", foreign_keys=[donor_id])


class ArtEquipment(Base):
    __tablename__ = "art_equipment"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    asset_code = Column(String(80), nullable=True)
    location = Column(String(120), nullable=True)
    installed_on = Column(Date, nullable=True)
    last_change_on = Column(Date, nullable=True)
    change_note = Column(Text, nullable=True)
    status = Column(String(20), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), default=system_now)


class ArtGrievance(Base):
    __tablename__ = "art_grievances"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    reference = Column(String(40), nullable=False)
    opened_on = Column(Date, nullable=False)
    complainant_name = Column(String(200), nullable=False)
    summary = Column(Text, nullable=False)
    status = Column(String(20), default="open", nullable=False)
    resolution = Column(Text, nullable=True)
    closed_on = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now)
