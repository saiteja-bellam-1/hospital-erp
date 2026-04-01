from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, date, time, timedelta
import json

from config.database import get_db
from app.models.user import User
from app.models.doctor_availability import DoctorAvailability, DoctorSpecialSchedule, DoctorAvailabilityStatus
from app.models.outpatient import Appointment
from app.utils.dependencies import get_current_user, require_permission
from app.utils.auth import Modules

router = APIRouter()

# Pydantic Models
class WeeklyScheduleDay(BaseModel):
    start_time: str = Field(..., pattern=r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$')
    end_time: str = Field(..., pattern=r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$')
    enabled: bool = True

    class Config:
        extra = "ignore"

class WeeklySchedule(BaseModel):
    monday: WeeklyScheduleDay
    tuesday: WeeklyScheduleDay
    wednesday: WeeklyScheduleDay
    thursday: WeeklyScheduleDay
    friday: WeeklyScheduleDay
    saturday: WeeklyScheduleDay
    sunday: WeeklyScheduleDay

class BreakTime(BaseModel):
    start_time: str = Field(..., pattern=r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$')
    end_time: str = Field(..., pattern=r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$')
    title: str = Field(..., max_length=100)

class AvailabilitySettingsUpdate(BaseModel):
    weekly_schedule: WeeklySchedule
    default_consultation_duration: int = Field(default=10, ge=2, le=120)
    break_times: List[BreakTime] = []
    buffer_minutes: int = Field(default=0, ge=0, le=30)
    emergency_slot_percentage: int = Field(default=20, ge=0, le=50)
    max_advance_booking_days: int = Field(default=30, ge=1, le=90)

    class Config:
        extra = "ignore"

class SpecialScheduleCreate(BaseModel):
    date: date
    schedule_type: str = Field(..., pattern=r'^(holiday|leave|modified_hours|emergency_only)$')
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    title: str = Field(..., max_length=255)
    description: Optional[str] = None
    emergency_only: bool = False
    notify_patients: bool = True

class AvailabilityStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r'^(available|busy|in_consultation|on_break|unavailable)$')
    status_message: Optional[str] = Field(None, max_length=255)
    expected_return_time: Optional[datetime] = None

class AvailabilityResponse(BaseModel):
    id: int
    weekly_schedule: Dict[str, Any]
    default_consultation_duration: int
    break_times: List[Dict[str, Any]]
    buffer_minutes: int
    emergency_slot_percentage: int
    max_advance_booking_days: int
    
    class Config:
        from_attributes = True

class SpecialScheduleResponse(BaseModel):
    id: int
    date: date
    schedule_type: str
    start_time: Optional[time]
    end_time: Optional[time]
    title: str
    description: Optional[str]
    emergency_only: bool
    
    class Config:
        from_attributes = True

class AvailableSlot(BaseModel):
    start_time: str
    end_time: str
    available: bool
    appointment_id: Optional[int] = None
    appointment_reason: Optional[str] = None

class DayAvailabilityResponse(BaseModel):
    date: date
    day_of_week: str
    is_working_day: bool
    special_schedule: Optional[SpecialScheduleResponse] = None
    slots: List[AvailableSlot] = []

# Routes

@router.get("/settings", response_model=AvailabilityResponse)
async def get_availability_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get doctor's availability settings"""
    if not current_user.has_role('doctor'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can access availability settings"
        )
    
    settings = db.query(DoctorAvailability).filter(
        DoctorAvailability.doctor_id == current_user.id
    ).first()
    
    if not settings:
        # Create default settings
        default_schedule = {
            "monday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
            "tuesday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
            "wednesday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
            "thursday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
            "friday": {"start_time": "09:00", "end_time": "17:00", "enabled": True},
            "saturday": {"start_time": "09:00", "end_time": "13:00", "enabled": False},
            "sunday": {"start_time": "09:00", "end_time": "13:00", "enabled": False}
        }
        
        settings = DoctorAvailability(
            doctor_id=current_user.id,
            weekly_schedule=default_schedule
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    
    return settings

@router.put("/settings", response_model=AvailabilityResponse)
async def update_availability_settings(
    settings_data: AvailabilitySettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update doctor's availability settings"""
    if not current_user.has_role('doctor'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can update availability settings"
        )
    
    settings = db.query(DoctorAvailability).filter(
        DoctorAvailability.doctor_id == current_user.id
    ).first()
    
    if not settings:
        settings = DoctorAvailability(doctor_id=current_user.id)
        db.add(settings)
    
    # Update settings
    settings.weekly_schedule = settings_data.weekly_schedule.dict()
    settings.default_consultation_duration = settings_data.default_consultation_duration
    settings.break_times = [break_time.dict() for break_time in settings_data.break_times]
    settings.buffer_minutes = settings_data.buffer_minutes
    settings.emergency_slot_percentage = settings_data.emergency_slot_percentage
    settings.max_advance_booking_days = settings_data.max_advance_booking_days
    
    db.commit()
    db.refresh(settings)
    
    return settings

@router.post("/special-schedule", response_model=SpecialScheduleResponse)
async def create_special_schedule(
    schedule_data: SpecialScheduleCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a special schedule (holiday, leave, modified hours)"""
    if not current_user.has_role('doctor'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can create special schedules"
        )
    
    # Check if a special schedule already exists for this date
    existing = db.query(DoctorSpecialSchedule).filter(
        DoctorSpecialSchedule.doctor_id == current_user.id,
        DoctorSpecialSchedule.date == schedule_data.date
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Special schedule already exists for {schedule_data.date}"
        )
    
    # Get availability settings
    availability = db.query(DoctorAvailability).filter(
        DoctorAvailability.doctor_id == current_user.id
    ).first()
    
    if not availability:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please set up your availability settings first"
        )
    
    special_schedule = DoctorSpecialSchedule(
        availability_id=availability.id,
        doctor_id=current_user.id,
        **schedule_data.dict()
    )
    
    db.add(special_schedule)
    db.commit()
    db.refresh(special_schedule)
    
    return special_schedule

@router.get("/special-schedule", response_model=List[SpecialScheduleResponse])
async def get_special_schedules(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get doctor's special schedules"""
    if not current_user.has_role('doctor'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can access special schedules"
        )
    
    query = db.query(DoctorSpecialSchedule).filter(
        DoctorSpecialSchedule.doctor_id == current_user.id
    )
    
    if start_date:
        query = query.filter(DoctorSpecialSchedule.date >= start_date)
    if end_date:
        query = query.filter(DoctorSpecialSchedule.date <= end_date)
    
    return query.order_by(DoctorSpecialSchedule.date).all()

@router.delete("/special-schedule/{schedule_id}")
async def delete_special_schedule(
    schedule_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a special schedule"""
    if not current_user.has_role('doctor'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can delete special schedules"
        )
    
    schedule = db.query(DoctorSpecialSchedule).filter(
        DoctorSpecialSchedule.id == schedule_id,
        DoctorSpecialSchedule.doctor_id == current_user.id
    ).first()
    
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Special schedule not found"
        )
    
    db.delete(schedule)
    db.commit()
    
    return {"message": "Special schedule deleted successfully"}

@router.put("/status")
async def update_availability_status(
    status_data: AvailabilityStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update doctor's current availability status"""
    if not current_user.has_role('doctor'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can update availability status"
        )
    
    status_record = db.query(DoctorAvailabilityStatus).filter(
        DoctorAvailabilityStatus.doctor_id == current_user.id
    ).first()
    
    if not status_record:
        status_record = DoctorAvailabilityStatus(doctor_id=current_user.id)
        db.add(status_record)
    
    status_record.status = status_data.status
    status_record.status_message = status_data.status_message
    status_record.expected_return_time = status_data.expected_return_time
    
    db.commit()
    
    return {"message": "Status updated successfully"}

@router.get("/slots/{target_date}", response_model=DayAvailabilityResponse)
async def get_day_availability(
    target_date: date,
    doctor_id: Optional[int] = None,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get available slots for a specific date (for receptionists)"""
    # If doctor_id not provided, use current user (for doctors checking their own schedule)
    if not doctor_id and current_user.has_role('doctor'):
        doctor_id = current_user.id
    elif not doctor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Doctor ID is required"
        )
    
    # Get doctor info
    doctor = db.query(User).filter(User.id == doctor_id).first()
    if not doctor or doctor.role.name != 'doctor':
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found"
        )
    
    # Get availability settings
    availability = db.query(DoctorAvailability).filter(
        DoctorAvailability.doctor_id == doctor_id
    ).first()
    
    if not availability:
        return DayAvailabilityResponse(
            date=target_date,
            day_of_week=target_date.strftime('%A').lower(),
            is_working_day=False,
            slots=[]
        )
    
    day_of_week = target_date.strftime('%A').lower()
    day_schedule = availability.weekly_schedule.get(day_of_week)
    
    if not day_schedule or not day_schedule.get('enabled'):
        return DayAvailabilityResponse(
            date=target_date,
            day_of_week=day_of_week,
            is_working_day=False,
            slots=[]
        )
    
    # Check for special schedule
    special_schedule = db.query(DoctorSpecialSchedule).filter(
        DoctorSpecialSchedule.doctor_id == doctor_id,
        DoctorSpecialSchedule.date == target_date
    ).first()
    
    if special_schedule and special_schedule.schedule_type in ['holiday', 'leave']:
        return DayAvailabilityResponse(
            date=target_date,
            day_of_week=day_of_week,
            is_working_day=False,
            special_schedule=special_schedule,
            slots=[]
        )
    
    # Generate time slots
    slots = _generate_time_slots(availability, day_schedule, special_schedule, target_date, db, doctor_id)
    
    return DayAvailabilityResponse(
        date=target_date,
        day_of_week=day_of_week,
        is_working_day=True,
        special_schedule=special_schedule,
        slots=slots
    )

def _generate_time_slots(availability, day_schedule, special_schedule, target_date, db, doctor_id):
    """Helper function to generate time slots for a day"""
    from datetime import datetime, timedelta
    
    # Use special schedule times if available, otherwise use regular schedule
    if special_schedule and special_schedule.schedule_type == 'modified_hours':
        start_time = special_schedule.start_time
        end_time = special_schedule.end_time
    else:
        start_time = datetime.strptime(day_schedule['start_time'], '%H:%M').time()
        end_time = datetime.strptime(day_schedule['end_time'], '%H:%M').time()
    
    # Get existing appointments for this date
    appointments = db.query(Appointment).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == target_date
    ).all()
    
    appointment_times = {}
    for apt in appointments:
        apt_start = apt.appointment_time
        apt_end = (datetime.combine(target_date, apt_start) + timedelta(minutes=apt.duration_minutes)).time()
        appointment_times[apt_start.strftime('%H:%M')] = {
            'end_time': apt_end.strftime('%H:%M'),
            'appointment_id': apt.id,
            'reason': apt.reason
        }
    
    # Generate slots
    slots = []
    current_time = datetime.combine(target_date, start_time)
    end_datetime = datetime.combine(target_date, end_time)
    
    while current_time < end_datetime:
        slot_start = current_time.time()
        slot_end = (current_time + timedelta(minutes=availability.default_consultation_duration)).time()
        
        # Check if slot is during break time
        is_break_time = False
        for break_time in availability.break_times:
            break_start = datetime.strptime(break_time['start_time'], '%H:%M').time()
            break_end = datetime.strptime(break_time['end_time'], '%H:%M').time()
            if break_start <= slot_start < break_end:
                is_break_time = True
                break
        
        if not is_break_time:
            slot_start_str = slot_start.strftime('%H:%M')
            appointment_info = appointment_times.get(slot_start_str)
            
            slots.append(AvailableSlot(
                start_time=slot_start_str,
                end_time=slot_end.strftime('%H:%M'),
                available=appointment_info is None,
                appointment_id=appointment_info['appointment_id'] if appointment_info else None,
                appointment_reason=appointment_info['reason'] if appointment_info else None
            ))
        
        current_time += timedelta(minutes=availability.default_consultation_duration + availability.buffer_minutes)
    
    return slots