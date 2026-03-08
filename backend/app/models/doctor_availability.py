from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Time, Date, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base

class DoctorAvailability(Base):
    """Model for managing doctor availability schedules"""
    __tablename__ = "doctor_availability"
    
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Weekly Schedule (JSON format: {"monday": {"start": "09:00", "end": "17:00", "enabled": true}, ...})
    weekly_schedule = Column(JSON, nullable=False, default={
        "monday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
        "tuesday": {"start_time": "09:00", "end_time": "17:00", "enabled": True}, 
        "wednesday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
        "thursday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
        "friday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
        "saturday": {"start_time": "09:00", "end_time": "13:00", "enabled": False},
        "sunday": {"start_time": "09:00", "end_time": "13:00", "enabled": False}
    })
    
    # Default consultation duration in minutes
    default_consultation_duration = Column(Integer, default=10)
    
    # Break times (JSON format: [{"start": "13:00", "end": "14:00", "title": "Lunch Break"}])
    break_times = Column(JSON, default=[])
    
    # Buffer time between appointments in minutes
    buffer_minutes = Column(Integer, default=0)
    
    # Emergency/walk-in slot percentage (0-100)
    emergency_slot_percentage = Column(Integer, default=20)
    
    # Maximum advance booking days
    max_advance_booking_days = Column(Integer, default=30)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    doctor = relationship("User", back_populates="availability_settings")
    special_schedules = relationship("DoctorSpecialSchedule", back_populates="availability")


class DoctorSpecialSchedule(Base):
    """Model for handling special dates like holidays, leaves, or modified hours"""
    __tablename__ = "doctor_special_schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    availability_id = Column(Integer, ForeignKey("doctor_availability.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Date for the special schedule
    date = Column(Date, nullable=False)
    
    # Type of special schedule
    schedule_type = Column(String(50), nullable=False)  # 'holiday', 'leave', 'modified_hours', 'emergency_only'
    
    # Custom working hours for modified_hours type
    start_time = Column(Time)
    end_time = Column(Time)
    
    # Reason/title for the special schedule
    title = Column(String(255), nullable=False)
    description = Column(Text)
    
    # Whether this is available for emergency appointments only
    emergency_only = Column(Boolean, default=False)
    
    # Whether to notify patients about changes
    notify_patients = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    availability = relationship("DoctorAvailability", back_populates="special_schedules")
    doctor = relationship("User")


class DoctorAvailabilityStatus(Base):
    """Model for real-time availability status updates"""
    __tablename__ = "doctor_availability_status"
    
    id = Column(Integer, primary_key=True, index=True)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Current status
    status = Column(String(50), default="available")  # 'available', 'busy', 'in_consultation', 'on_break', 'unavailable'
    
    # Status message visible to receptionists
    status_message = Column(String(255))
    
    # Expected return time for temporary unavailability
    expected_return_time = Column(DateTime)
    
    # Last updated timestamp
    last_updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    doctor = relationship("User")