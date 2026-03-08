from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Time, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base

class Appointment(Base):
    __tablename__ = "appointments"
    
    id = Column(Integer, primary_key=True, index=True)
    appointment_number = Column(String(50), unique=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    appointment_date = Column(DateTime, nullable=False)
    appointment_time = Column(Time, nullable=False)
    duration_minutes = Column(Integer, default=30)
    appointment_type = Column(String(20), default="consultation")  # consultation, followup, checkup
    reason = Column(Text)
    status = Column(String(20), default="scheduled")  # scheduled, confirmed, in_progress, completed, cancelled, no_show
    priority = Column(String(10), default="normal")  # normal, urgent, emergency
    notes = Column(Text)
    booking_source = Column(String(20), default="manual")  # manual, online, phone
    booked_by_id = Column(Integer, ForeignKey("users.id"))
    confirmed_at = Column(DateTime)
    checked_in_at = Column(DateTime)
    consultation_started_at = Column(DateTime)
    consultation_ended_at = Column(DateTime)
    checked_out_at = Column(DateTime)

    # Queue management
    token_number = Column(Integer)
    queue_position = Column(Integer)

    # Cancellation/Reschedule
    cancellation_reason = Column(Text)
    rescheduled_from_id = Column(Integer, ForeignKey("appointments.id"))

    # Payment-related fields
    consultation_fee = Column(Float, default=0.0)
    payment_status = Column(String(20), default="pending")  # pending, paid, partial, cancelled, waived
    payment_method = Column(String(50))  # cash, card, insurance, online, bank_transfer
    payment_date = Column(DateTime)
    payment_notes = Column(Text)
    discount_amount = Column(Float, default=0.0)
    final_amount = Column(Float, default=0.0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    patient = relationship("Patient", back_populates="appointments")
    doctor = relationship("User", foreign_keys=[doctor_id])
    booked_by = relationship("User", foreign_keys=[booked_by_id])
    visits = relationship("OutpatientVisit", back_populates="appointment")

class OutpatientVisit(Base):
    __tablename__ = "outpatient_visits"
    
    id = Column(Integer, primary_key=True, index=True)
    visit_number = Column(String(50), unique=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    appointment_id = Column(Integer, ForeignKey("appointments.id"))
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    visit_date = Column(DateTime(timezone=True), server_default=func.now())
    visit_type = Column(String(20), default="scheduled")  # scheduled, walk_in, emergency
    department = Column(String(50))
    chief_complaint = Column(Text)
    triage_level = Column(String(20))  # low, medium, high, critical
    waiting_time_minutes = Column(Integer)
    consultation_time_minutes = Column(Integer)
    status = Column(String(20), default="registered")  # registered, waiting, in_consultation, completed, discharged
    discharge_summary = Column(Text)
    follow_up_required = Column(Boolean, default=False)
    follow_up_date = Column(DateTime)
    total_charges = Column(String(10), default="0.0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    appointment = relationship("Appointment", back_populates="visits")