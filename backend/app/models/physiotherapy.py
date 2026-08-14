"""Physiotherapy clinic models — standalone ops + billing (v1).

Does not depend on outpatient/inpatient. Money flows through central Bill/Payment.
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, Date, Time, JSON,
)
from sqlalchemy.orm import relationship
from config.database import Base
from app.utils.time import system_now


class PhysioService(Base):
    """Clinic service / modality catalog (Assessment, IFT, Ultrasound, …)."""
    __tablename__ = "physio_services"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    code = Column(String(50), nullable=True)
    default_price = Column(Float, nullable=False, default=0.0)
    duration_minutes = Column(Integer, nullable=False, default=30)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now)
    updated_at = Column(DateTime(timezone=True), onupdate=system_now)


class PhysioPackageTemplate(Base):
    """Sellable prepaid package definition (e.g. 10× IFT)."""
    __tablename__ = "physio_package_templates"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    # NULL service_id = redeemable against any active modality
    service_id = Column(Integer, ForeignKey("physio_services.id"), nullable=True)
    session_count = Column(Integer, nullable=False, default=10)
    price = Column(Float, nullable=False, default=0.0)
    validity_days = Column(Integer, nullable=False, default=90)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now)
    updated_at = Column(DateTime(timezone=True), onupdate=system_now)

    service = relationship("PhysioService", foreign_keys=[service_id])


class PhysioPatientPackage(Base):
    """A package sold to a patient — tracks remaining sessions."""
    __tablename__ = "physio_patient_packages"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    template_id = Column(Integer, ForeignKey("physio_package_templates.id"), nullable=True)
    service_id = Column(Integer, ForeignKey("physio_services.id"), nullable=True)
    name = Column(String(200), nullable=False)
    sessions_total = Column(Integer, nullable=False)
    sessions_remaining = Column(Integer, nullable=False)
    price_paid = Column(Float, nullable=False, default=0.0)
    purchased_at = Column(DateTime(timezone=True), default=system_now)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default="active")  # active, exhausted, expired, refunded
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)
    sold_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now)
    updated_at = Column(DateTime(timezone=True), onupdate=system_now)

    patient = relationship("Patient", foreign_keys=[patient_id])
    template = relationship("PhysioPackageTemplate", foreign_keys=[template_id])
    service = relationship("PhysioService", foreign_keys=[service_id])


class PhysioPackageLedger(Base):
    """Audit trail for package session consumption / adjustments."""
    __tablename__ = "physio_package_ledger"

    id = Column(Integer, primary_key=True, index=True)
    package_id = Column(Integer, ForeignKey("physio_patient_packages.id"), nullable=False, index=True)
    appointment_id = Column(Integer, ForeignKey("physio_appointments.id"), nullable=True)
    delta = Column(Integer, nullable=False)  # typically -1 on attendance
    reason = Column(String(100), nullable=True)
    override_reason = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now)


class PhysioTherapistAvailability(Base):
    """Weekly schedule for a physiotherapist user."""
    __tablename__ = "physio_therapist_availability"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    weekly_schedule = Column(JSON, nullable=False, default={
        "monday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
        "tuesday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
        "wednesday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
        "thursday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
        "friday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
        "saturday": {"start_time": "09:00", "end_time": "13:00", "enabled": True},
        "sunday": {"start_time": "09:00", "end_time": "13:00", "enabled": False},
    })
    default_session_duration = Column(Integer, default=30)
    buffer_minutes = Column(Integer, default=0)
    max_advance_booking_days = Column(Integer, default=30)
    created_at = Column(DateTime(timezone=True), default=system_now)
    updated_at = Column(DateTime(timezone=True), onupdate=system_now)

    therapist = relationship("User", foreign_keys=[therapist_id])
    special_schedules = relationship(
        "PhysioTherapistSpecialSchedule",
        back_populates="availability",
        cascade="all, delete-orphan",
    )


class PhysioTherapistSpecialSchedule(Base):
    """Leave / holiday / modified hours for a therapist on a specific date."""
    __tablename__ = "physio_therapist_special_schedules"

    id = Column(Integer, primary_key=True, index=True)
    availability_id = Column(Integer, ForeignKey("physio_therapist_availability.id"), nullable=False)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    schedule_type = Column(String(50), nullable=False)  # holiday, leave, modified_hours
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now)

    availability = relationship("PhysioTherapistAvailability", back_populates="special_schedules")


class PhysioAppointment(Base):
    """Physio session booking / attendance record."""
    __tablename__ = "physio_appointments"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    appointment_number = Column(String(50), unique=True, nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    therapist_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    service_id = Column(Integer, ForeignKey("physio_services.id"), nullable=True)
    package_id = Column(Integer, ForeignKey("physio_patient_packages.id"), nullable=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)

    appointment_date = Column(Date, nullable=False, index=True)
    appointment_time = Column(Time, nullable=True)
    duration_minutes = Column(Integer, default=30)
    session_type = Column(String(20), default="treatment")  # assessment, treatment, review
    status = Column(String(20), default="scheduled", index=True)
    # scheduled → checked_in → in_progress → completed | no_show | cancelled
    is_walk_in = Column(Boolean, default=False)
    referral_source = Column(String(100), nullable=True)
    chief_complaint = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    session_note = Column(Text, nullable=True)
    next_appointment_suggested = Column(Date, nullable=True)

    booked_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    checked_in_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=system_now)
    updated_at = Column(DateTime(timezone=True), onupdate=system_now)

    patient = relationship("Patient", foreign_keys=[patient_id])
    therapist = relationship("User", foreign_keys=[therapist_id])
    service = relationship("PhysioService", foreign_keys=[service_id])
    package = relationship("PhysioPatientPackage", foreign_keys=[package_id])
