from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
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
    emergency_contact = Column(String(100))
    attending_physician_id = Column(Integer, ForeignKey("users.id"))
    bed_number = Column(String(10))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    patient = relationship("Patient", back_populates="admissions")
    room = relationship("RoomManagement", back_populates="admissions")
    discharge = relationship("DischargeRecord", back_populates="admission", uselist=False)

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