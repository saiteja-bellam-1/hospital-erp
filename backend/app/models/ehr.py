from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base

class Consultation(Base):
    __tablename__ = "consultations"
    
    id = Column(Integer, primary_key=True, index=True)
    consultation_number = Column(String(50), unique=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    consultation_date = Column(DateTime(timezone=True), server_default=func.now())
    consultation_type = Column(String(20), nullable=False)  # outpatient, inpatient, emergency, followup
    chief_complaint = Column(Text)
    present_history = Column(Text)
    examination_findings = Column(Text)
    vital_signs = Column(Text)  # JSON format for structured data
    status = Column(String(20), default="ongoing")  # ongoing, completed, cancelled
    consultation_fee = Column(Float, default=0.0)
    follow_up_date = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    patient = relationship("Patient", back_populates="consultations")
    diagnoses = relationship("Diagnosis", back_populates="consultation")
    treatment_plans = relationship("TreatmentPlan", back_populates="consultation")
    medical_notes = relationship("MedicalNote", back_populates="consultation")
    prescriptions = relationship("Prescription", back_populates="consultation")
    lab_orders = relationship("PatientLabOrder", back_populates="consultation")
    bills = relationship("Bill", primaryjoin="and_(Consultation.id == foreign(Bill.reference_id), Bill.bill_type == 'consultation')", viewonly=True)

class Diagnosis(Base):
    __tablename__ = "diagnoses"
    
    id = Column(Integer, primary_key=True, index=True)
    consultation_id = Column(Integer, ForeignKey("consultations.id"), nullable=False)
    diagnosis_code = Column(String(20))  # ICD-10 code
    diagnosis_name = Column(String(200), nullable=False)
    diagnosis_type = Column(String(20), default="primary")  # primary, secondary, differential
    severity = Column(String(20))  # mild, moderate, severe
    status = Column(String(20), default="active")  # active, resolved, chronic
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    consultation = relationship("Consultation", back_populates="diagnoses")

class TreatmentPlan(Base):
    __tablename__ = "treatment_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    consultation_id = Column(Integer, ForeignKey("consultations.id"), nullable=False)
    treatment_type = Column(String(50), nullable=False)  # medication, procedure, therapy, lifestyle
    description = Column(Text, nullable=False)
    instructions = Column(Text)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    frequency = Column(String(100))
    status = Column(String(20), default="active")  # active, completed, discontinued
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    consultation = relationship("Consultation", back_populates="treatment_plans")

class MedicalNote(Base):
    __tablename__ = "medical_notes"
    
    id = Column(Integer, primary_key=True, index=True)
    consultation_id = Column(Integer, ForeignKey("consultations.id"), nullable=False)
    note_type = Column(String(50), nullable=False)  # progress, discharge, referral, general
    title = Column(String(200))
    content = Column(Text, nullable=False)
    is_confidential = Column(Boolean, default=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    consultation = relationship("Consultation", back_populates="medical_notes")