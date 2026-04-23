from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base
import uuid

class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()), nullable=False)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    date_of_birth = Column(Date)
    age = Column(Integer)
    gender = Column(String(10))
    blood_group = Column(String(5))
    marital_status = Column(String(20))
    abha_id = Column(String(30))
    email = Column(String(100))
    primary_phone = Column(String(15), nullable=False)
    emergency_contact_phone = Column(String(15))
    emergency_contact_name = Column(String(100))
    emergency_contact_relation = Column(String(50))
    address_line1 = Column(String(255))
    address_line2 = Column(String(255))
    village = Column(String(100))
    mandal = Column(String(100))
    district = Column(String(100))
    address = Column(Text)  # kept for backward compat / display
    referred_by = Column(String(100))
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    contacts = relationship("PatientContact", back_populates="patient")
    medical_history = relationship("PatientMedicalHistory", back_populates="patient")
    lab_orders = relationship("PatientLabOrder", back_populates="patient")
    consultations = relationship("Consultation", back_populates="patient")
    appointments = relationship("Appointment", back_populates="patient")
    admissions = relationship("Admission", back_populates="patient")
    bills = relationship("Bill", back_populates="patient")
    allergies = relationship("PatientAllergy", back_populates="patient", cascade="all, delete-orphan")

class PatientContact(Base):
    __tablename__ = "patient_contacts"
    
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    contact_type = Column(String(20), nullable=False)  # primary, emergency, family
    name = Column(String(100))
    phone = Column(String(15), nullable=False)
    email = Column(String(100))
    relation_type = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    patient = relationship("Patient", back_populates="contacts")

class PatientMedicalHistory(Base):
    __tablename__ = "patient_medical_history"
    
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    condition = Column(String(200), nullable=False)
    diagnosed_date = Column(Date)
    status = Column(String(20))  # active, resolved, chronic
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    patient = relationship("Patient", back_populates="medical_history")


class PatientAllergy(Base):
    __tablename__ = "patient_allergies"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    allergy_type = Column(String(20), nullable=False)  # drug, food, environmental, other
    allergen = Column(String(200), nullable=False)
    severity = Column(String(20), nullable=False)  # mild, moderate, severe, anaphylaxis
    reaction = Column(Text)
    notes = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)
    recorded_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    patient = relationship("Patient", back_populates="allergies")
    recorded_by = relationship("User", foreign_keys=[recorded_by_id])