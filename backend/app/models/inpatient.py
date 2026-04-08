from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, Numeric
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
    billed = Column(Boolean, default=False)
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
    scheduled_date = Column(DateTime(timezone=True), nullable=False)
    estimated_duration_minutes = Column(Integer)
    status = Column(String(20), default="scheduled")  # scheduled, in_progress, completed, cancelled, postponed
    pre_op_notes = Column(Text, nullable=True)
    post_op_notes = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    admission = relationship("Admission", back_populates="ot_schedules")
    patient = relationship("Patient", foreign_keys=[patient_id])
    surgeon = relationship("User", foreign_keys=[surgeon_id])


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