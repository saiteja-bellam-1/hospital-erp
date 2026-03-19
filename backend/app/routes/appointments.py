from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, date, time, timedelta
import io

from config.database import get_db
from app.models.user import User
from app.models.patient import Patient
from app.models.outpatient import Appointment
from app.models.hospital import Hospital
from app.models.permissions import HospitalSettings
from app.utils.dependencies import get_current_user, require_permission
from app.utils.auth import Modules
from app.utils.pdf_service import pdf_service
from app.services.availability_service import AvailabilityService

router = APIRouter()

class DoctorForAppointment(BaseModel):
    id: int
    first_name: str
    last_name: str
    specialization: Optional[str] = None
    consultation_fee_inr: Optional[str] = None
    
    class Config:
        from_attributes = True

class AppointmentCreate(BaseModel):
    patient_id: str
    doctor_id: int
    appointment_date: date
    appointment_time: time
    duration_minutes: int = Field(default=10, ge=10, le=180)
    appointment_type: str = Field(default="consultation", pattern="^(consultation|followup|checkup)$")
    reason: Optional[str] = None
    priority: str = Field(default="normal", pattern="^(normal|urgent|emergency)$")
    notes: Optional[str] = None
    
    # Payment fields
    payment_status: str = Field(default="pending")
    payment_method: Optional[str] = Field(None, pattern="^(cash|card|upi|cheque|online|insurance)$")
    discount_amount: float = Field(default=0.0, ge=0)
    payment_notes: Optional[str] = None
    referred_by: Optional[str] = Field(None, max_length=100)

class AppointmentResponse(BaseModel):
    id: int
    appointment_number: str
    patient_id: int
    doctor_id: int
    appointment_date: date
    appointment_time: time
    duration_minutes: int
    appointment_type: str
    reason: Optional[str]
    status: str
    priority: str
    notes: Optional[str]
    patient_name: Optional[str] = None
    patient_uuid: Optional[str] = None
    doctor_name: Optional[str] = None

    # Queue / check-in fields
    token_number: Optional[int] = None
    queue_position: Optional[int] = None
    checked_in_at: Optional[datetime] = None
    checked_out_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None

    # Payment fields
    consultation_fee: float = 0.0
    registration_fee: float = 0.0
    payment_status: str = "pending"
    payment_method: Optional[str] = None
    payment_date: Optional[datetime] = None
    payment_notes: Optional[str] = None
    discount_amount: float = 0.0
    final_amount: float = 0.0
    referred_by: Optional[str] = None

    created_at: datetime

    class Config:
        from_attributes = True

class AppointmentUpdate(BaseModel):
    appointment_date: Optional[date] = None
    appointment_time: Optional[time] = None
    duration_minutes: Optional[int] = Field(None, ge=10, le=180)
    appointment_type: Optional[str] = Field(None, pattern="^(consultation|followup|checkup)$")
    reason: Optional[str] = None
    priority: Optional[str] = Field(None, pattern="^(normal|urgent|emergency)$")
    notes: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(scheduled|confirmed|in_progress|completed|cancelled|no_show)$")

    # Payment update fields
    payment_status: Optional[str] = None
    payment_method: Optional[str] = Field(None, pattern="^(cash|card|upi|cheque|online|insurance)$")
    discount_amount: Optional[float] = Field(None, ge=0)
    payment_notes: Optional[str] = None

class CancelAppointment(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)

class RescheduleAppointment(BaseModel):
    new_date: date
    new_time: time

@router.get("/doctors", response_model=List[DoctorForAppointment])
async def get_available_doctors(
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get available doctors for appointment booking"""
    doctors = db.query(User).join(User.role).filter(
        User.role.has(name='doctor'),
        User.hospital_id == current_user.hospital_id,
        User.is_active == True
    ).all()
    
    return [
        DoctorForAppointment(
            id=doctor.id,
            first_name=doctor.first_name,
            last_name=doctor.last_name,
            specialization=doctor.specialization,
            consultation_fee_inr=doctor.consultation_fee_inr
        )
        for doctor in doctors
    ]

@router.get("/patient-fee-info/{patient_uuid}")
async def get_patient_fee_info(
    patient_uuid: str,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Check if patient is new and return applicable registration fee"""
    patient = db.query(Patient).filter(Patient.patient_id == patient_uuid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    existing_appointments = db.query(Appointment).filter(
        Appointment.patient_id == patient.id
    ).count()

    is_new_patient = existing_appointments == 0
    registration_fee = 0.0

    if is_new_patient:
        fee_setting = db.query(HospitalSettings).filter(
            HospitalSettings.setting_category == "billing",
            HospitalSettings.setting_key == "registration_fee"
        ).first()
        if fee_setting:
            try:
                registration_fee = float(fee_setting.setting_value)
            except (ValueError, TypeError):
                registration_fee = 0.0

    return {
        "is_new_patient": is_new_patient,
        "registration_fee": registration_fee
    }

@router.get("/doctors/{doctor_id}/availability")
async def check_doctor_availability(
    doctor_id: int,
    appointment_date: date,
    appointment_time: time,
    duration_minutes: int = 10,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Check if doctor is available for specific date and time"""
    # Verify doctor exists and belongs to same hospital
    doctor = db.query(User).filter(User.id == doctor_id).first()
    if not doctor or doctor.role.name != 'doctor':
        raise HTTPException(status_code=404, detail="Doctor not found")
    
    if doctor.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    availability_service = AvailabilityService(db)
    is_available, reason = availability_service.is_doctor_available(
        doctor_id, appointment_date, appointment_time, duration_minutes
    )
    
    return {
        "doctor_id": doctor_id,
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}",
        "appointment_date": appointment_date,
        "appointment_time": appointment_time,
        "duration_minutes": duration_minutes,
        "is_available": is_available,
        "reason": reason
    }

@router.get("/doctors/{doctor_id}/available-slots")
async def get_doctor_available_slots(
    doctor_id: int,
    appointment_date: date,
    duration_minutes: int = 10,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get all available time slots for a doctor on specific date"""
    # Verify doctor exists and belongs to same hospital
    doctor = db.query(User).filter(User.id == doctor_id).first()
    if not doctor or doctor.role.name != 'doctor':
        raise HTTPException(status_code=404, detail="Doctor not found")
    
    if doctor.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    availability_service = AvailabilityService(db)
    available_slots = availability_service.get_available_slots(doctor_id, appointment_date, duration_minutes)
    schedule_info = availability_service.get_doctor_schedule_for_date(doctor_id, appointment_date)
    
    return {
        "doctor_id": doctor_id,
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}",
        "appointment_date": appointment_date,
        "available_slots": available_slots,
        "schedule_info": schedule_info
    }

def generate_appointment_number() -> str:
    """Generate unique appointment number"""
    import uuid
    return f"APT-{str(uuid.uuid4())[:8].upper()}"

@router.post("/", response_model=AppointmentResponse)
async def create_appointment(
    appointment_data: AppointmentCreate,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Create a new appointment"""
    # Verify patient exists
    patient = db.query(Patient).filter(Patient.patient_id == appointment_data.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    if patient.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Verify doctor exists and belongs to same hospital
    doctor = db.query(User).filter(User.id == appointment_data.doctor_id).first()
    if not doctor or doctor.role.name != 'doctor':
        raise HTTPException(status_code=404, detail="Doctor not found")
    
    if doctor.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Doctor not available")
    
    # Use availability service to check if doctor is available
    availability_service = AvailabilityService(db)
    is_available, reason = availability_service.is_doctor_available(
        doctor_id=appointment_data.doctor_id,
        appointment_date=appointment_data.appointment_date,
        appointment_time=appointment_data.appointment_time,
        duration_minutes=appointment_data.duration_minutes
    )
    
    if not is_available:
        raise HTTPException(status_code=400, detail=f"Doctor not available: {reason}")
    
    # Calculate consultation fee from doctor's rates
    consultation_fee = 0.0
    if doctor.consultation_fee_inr:
        # Extract numeric value from fee string (e.g., "₹1500" -> 1500.0)
        fee_str = doctor.consultation_fee_inr.replace('₹', '').replace(',', '').strip()
        try:
            consultation_fee = float(fee_str)
        except ValueError:
            consultation_fee = 0.0

    # Check if patient is new (no previous appointments) → add registration fee
    registration_fee = 0.0
    existing_appointments = db.query(Appointment).filter(
        Appointment.patient_id == patient.id
    ).count()
    if existing_appointments == 0:
        fee_setting = db.query(HospitalSettings).filter(
            HospitalSettings.setting_category == "billing",
            HospitalSettings.setting_key == "registration_fee"
        ).first()
        if fee_setting:
            try:
                registration_fee = float(fee_setting.setting_value)
            except (ValueError, TypeError):
                registration_fee = 0.0

    # Calculate final amount after discount
    final_amount = consultation_fee + registration_fee - appointment_data.discount_amount

    # Create appointment
    appointment = Appointment(
        appointment_number=generate_appointment_number(),
        patient_id=patient.id,
        doctor_id=appointment_data.doctor_id,
        appointment_date=appointment_data.appointment_date,
        appointment_time=appointment_data.appointment_time,
        duration_minutes=appointment_data.duration_minutes,
        appointment_type=appointment_data.appointment_type,
        reason=appointment_data.reason,
        priority=appointment_data.priority,
        notes=appointment_data.notes,
        booked_by_id=current_user.id,
        # Payment fields
        consultation_fee=consultation_fee,
        registration_fee=registration_fee,
        payment_status=appointment_data.payment_status,
        payment_method=appointment_data.payment_method,
        payment_notes=appointment_data.payment_notes,
        discount_amount=appointment_data.discount_amount,
        final_amount=final_amount,
        referred_by=appointment_data.referred_by
    )
    
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    
    return appointment

@router.get("/", response_model=List[AppointmentResponse])
async def get_appointments(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    doctor_id: Optional[int] = None,
    patient_id: Optional[str] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get appointments with optional filters"""
    query = db.query(Appointment).join(Patient).join(User, Appointment.doctor_id == User.id)
    
    # Filter by hospital
    query = query.filter(Patient.hospital_id == current_user.hospital_id)
    
    # Apply filters
    if date_from:
        # Convert date to datetime for proper comparison
        date_from_dt = datetime.combine(date_from, datetime.min.time())
        query = query.filter(Appointment.appointment_date >= date_from_dt)
    if date_to:
        # Convert date to datetime and set to end of day for proper comparison
        date_to_dt = datetime.combine(date_to, datetime.max.time())
        query = query.filter(Appointment.appointment_date <= date_to_dt)
    if doctor_id:
        query = query.filter(Appointment.doctor_id == doctor_id)
    if patient_id:
        patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
        if patient:
            query = query.filter(Appointment.patient_id == patient.id)
    if status:
        query = query.filter(Appointment.status == status)
    
    # Order by appointment date and time
    query = query.order_by(Appointment.appointment_date, Appointment.appointment_time)
    
    appointments = query.offset(skip).limit(limit).all()
    
    # Enhance with patient and doctor names
    result = []
    for apt in appointments:
        apt_dict = {
            "id": apt.id,
            "appointment_number": apt.appointment_number,
            "patient_id": apt.patient_id,
            "doctor_id": apt.doctor_id,
            "appointment_date": apt.appointment_date,
            "appointment_time": apt.appointment_time,
            "duration_minutes": apt.duration_minutes,
            "appointment_type": apt.appointment_type,
            "reason": apt.reason,
            "status": apt.status,
            "priority": apt.priority,
            "notes": apt.notes,
            "created_at": apt.created_at,
            "patient_name": f"{apt.patient.first_name} {apt.patient.last_name}",
            "patient_uuid": apt.patient.patient_id if apt.patient else None,
            "doctor_name": f"Dr. {apt.doctor.first_name} {apt.doctor.last_name}" if hasattr(apt, 'doctor') and apt.doctor else None,
            # Queue / check-in fields
            "token_number": apt.token_number,
            "queue_position": apt.queue_position,
            "checked_in_at": apt.checked_in_at,
            "checked_out_at": apt.checked_out_at,
            "cancellation_reason": apt.cancellation_reason,
            # Payment fields
            "consultation_fee": apt.consultation_fee or 0.0,
            "payment_status": apt.payment_status or "pending",
            "payment_method": apt.payment_method,
            "payment_date": apt.payment_date,
            "payment_notes": apt.payment_notes,
            "discount_amount": apt.discount_amount or 0.0,
            "final_amount": apt.final_amount or 0.0
        }
        result.append(apt_dict)
    
    return result

@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: int,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get appointment by ID"""
    appointment = db.query(Appointment).join(Patient).filter(
        Appointment.id == appointment_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # Build response with patient_uuid
    response = AppointmentResponse.model_validate(appointment)
    response.patient_uuid = appointment.patient.patient_id if appointment.patient else None
    response.patient_name = f"{appointment.patient.first_name} {appointment.patient.last_name}" if appointment.patient else None
    response.doctor_name = f"Dr. {appointment.doctor.first_name} {appointment.doctor.last_name}" if appointment.doctor else None
    return response

@router.put("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: int,
    appointment_update: AppointmentUpdate,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Update appointment"""
    appointment = db.query(Appointment).join(Patient).filter(
        Appointment.id == appointment_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Update fields
    update_data = {k: v for k, v in appointment_update.dict().items() if v is not None}
    
    for field, value in update_data.items():
        setattr(appointment, field, value)
    
    db.commit()
    db.refresh(appointment)
    
    return appointment

@router.get("/doctor/{doctor_id}", response_model=List[AppointmentResponse])
async def get_doctor_appointments(
    doctor_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[str] = None,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get appointments for a specific doctor"""
    # Verify doctor exists and has access
    doctor = db.query(User).filter(User.id == doctor_id).first()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
    
    if doctor.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    query = db.query(Appointment).join(Patient).filter(
        Appointment.doctor_id == doctor_id,
        Patient.hospital_id == current_user.hospital_id
    )
    
    # Apply date filters
    if date_from:
        # Convert date to datetime for proper comparison
        date_from_dt = datetime.combine(date_from, datetime.min.time())
        query = query.filter(Appointment.appointment_date >= date_from_dt)
    if date_to:
        # Convert date to datetime and set to end of day for proper comparison
        date_to_dt = datetime.combine(date_to, datetime.max.time())
        query = query.filter(Appointment.appointment_date <= date_to_dt)
    if status:
        query = query.filter(Appointment.status == status)
    
    appointments = query.order_by(Appointment.appointment_date, Appointment.appointment_time).all()
    
    # Enhance with patient names
    result = []
    for apt in appointments:
        apt_dict = {
            "id": apt.id,
            "appointment_number": apt.appointment_number,
            "patient_id": apt.patient_id,
            "doctor_id": apt.doctor_id,
            "appointment_date": apt.appointment_date,
            "appointment_time": apt.appointment_time,
            "duration_minutes": apt.duration_minutes,
            "appointment_type": apt.appointment_type,
            "reason": apt.reason,
            "status": apt.status,
            "priority": apt.priority,
            "notes": apt.notes,
            "created_at": apt.created_at,
            "patient_name": f"{apt.patient.first_name} {apt.patient.last_name}",
            "patient_uuid": apt.patient.patient_id if apt.patient else None,
            "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}",
            # Queue / check-in fields
            "token_number": apt.token_number,
            "queue_position": apt.queue_position,
            "checked_in_at": apt.checked_in_at,
            "checked_out_at": apt.checked_out_at,
            "cancellation_reason": apt.cancellation_reason,
        }
        result.append(apt_dict)

    return result

def _generate_token_number(db: Session, doctor_id: int, appointment_date: date) -> int:
    """Generate next token number for a doctor on a given date"""
    from sqlalchemy import func as sqlfunc
    max_token = db.query(sqlfunc.max(Appointment.token_number)).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date == datetime.combine(appointment_date, datetime.min.time()),
        Appointment.token_number.isnot(None)
    ).scalar()
    return (max_token or 0) + 1


@router.post("/{appointment_id}/check-in")
async def check_in_appointment(
    appointment_id: int,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Check in a patient for their appointment and assign a token number"""
    appointment = db.query(Appointment).join(Patient).filter(
        Appointment.id == appointment_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appointment.checked_in_at:
        raise HTTPException(status_code=400, detail="Patient already checked in")

    if appointment.status in ["cancelled", "completed", "no_show"]:
        raise HTTPException(status_code=400, detail=f"Cannot check in a {appointment.status} appointment")

    # Assign token number
    apt_date = appointment.appointment_date.date() if isinstance(appointment.appointment_date, datetime) else appointment.appointment_date
    token = _generate_token_number(db, appointment.doctor_id, apt_date)
    appointment.token_number = token
    appointment.queue_position = token
    appointment.checked_in_at = datetime.now()
    appointment.status = "confirmed"

    db.commit()
    db.refresh(appointment)

    return {
        "message": "Patient checked in successfully",
        "appointment_id": appointment.id,
        "token_number": appointment.token_number,
        "checked_in_at": appointment.checked_in_at.isoformat()
    }


@router.post("/{appointment_id}/check-out")
async def check_out_appointment(
    appointment_id: int,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Check out a patient after consultation"""
    appointment = db.query(Appointment).join(Patient).filter(
        Appointment.id == appointment_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if not appointment.checked_in_at:
        raise HTTPException(status_code=400, detail="Patient has not checked in yet")

    if appointment.checked_out_at:
        raise HTTPException(status_code=400, detail="Patient already checked out")

    appointment.checked_out_at = datetime.now()
    appointment.status = "completed"
    appointment.consultation_ended_at = datetime.now()

    db.commit()
    db.refresh(appointment)

    return {
        "message": "Patient checked out successfully",
        "appointment_id": appointment.id,
        "checked_out_at": appointment.checked_out_at.isoformat()
    }


@router.post("/{appointment_id}/cancel")
async def cancel_appointment(
    appointment_id: int,
    cancel_data: CancelAppointment,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Cancel an appointment with a reason"""
    appointment = db.query(Appointment).join(Patient).filter(
        Appointment.id == appointment_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appointment.status in ["completed", "cancelled"]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel a {appointment.status} appointment")

    appointment.status = "cancelled"
    appointment.cancellation_reason = cancel_data.reason

    db.commit()
    db.refresh(appointment)

    return {
        "message": "Appointment cancelled successfully",
        "appointment_id": appointment.id,
        "cancellation_reason": appointment.cancellation_reason
    }


@router.post("/{appointment_id}/reschedule")
async def reschedule_appointment(
    appointment_id: int,
    reschedule_data: RescheduleAppointment,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Reschedule an appointment to a new date/time"""
    appointment = db.query(Appointment).join(Patient).filter(
        Appointment.id == appointment_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appointment.status in ["completed", "cancelled", "in_progress"]:
        raise HTTPException(status_code=400, detail=f"Cannot reschedule a {appointment.status} appointment")

    # Check availability for new slot
    availability_service = AvailabilityService(db)
    is_available, reason = availability_service.is_doctor_available(
        appointment.doctor_id, reschedule_data.new_date,
        reschedule_data.new_time, appointment.duration_minutes
    )

    if not is_available:
        raise HTTPException(status_code=400, detail=f"New slot not available: {reason}")

    # Cancel old appointment
    appointment.status = "cancelled"
    appointment.cancellation_reason = "Rescheduled"

    # Create new appointment
    new_appointment = Appointment(
        appointment_number=generate_appointment_number(),
        patient_id=appointment.patient_id,
        doctor_id=appointment.doctor_id,
        appointment_date=reschedule_data.new_date,
        appointment_time=reschedule_data.new_time,
        duration_minutes=appointment.duration_minutes,
        appointment_type=appointment.appointment_type,
        reason=appointment.reason,
        priority=appointment.priority,
        notes=appointment.notes,
        booked_by_id=current_user.id,
        consultation_fee=appointment.consultation_fee,
        payment_status=appointment.payment_status,
        payment_method=appointment.payment_method,
        payment_notes=appointment.payment_notes,
        discount_amount=appointment.discount_amount,
        final_amount=appointment.final_amount,
        referred_by=appointment.referred_by,
        rescheduled_from_id=appointment.id
    )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)

    return {
        "message": "Appointment rescheduled successfully",
        "old_appointment_id": appointment.id,
        "new_appointment": {
            "id": new_appointment.id,
            "appointment_number": new_appointment.appointment_number,
            "appointment_date": new_appointment.appointment_date.isoformat() if isinstance(new_appointment.appointment_date, datetime) else str(new_appointment.appointment_date),
            "appointment_time": str(new_appointment.appointment_time),
            "token_number": new_appointment.token_number,
            "status": new_appointment.status
        }
    }


@router.get("/queue/{doctor_id}")
async def get_doctor_queue(
    doctor_id: int,
    queue_date: Optional[date] = None,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get the current queue for a doctor on a given date"""
    target_date = queue_date or date.today()
    date_start = datetime.combine(target_date, datetime.min.time())
    date_end = datetime.combine(target_date, datetime.max.time())

    appointments = db.query(Appointment).join(Patient).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date >= date_start,
        Appointment.appointment_date <= date_end,
        Appointment.token_number.isnot(None),
        Patient.hospital_id == current_user.hospital_id
    ).order_by(Appointment.token_number).all()

    queue = []
    for apt in appointments:
        queue.append({
            "appointment_id": apt.id,
            "token_number": apt.token_number,
            "patient_name": f"{apt.patient.first_name} {apt.patient.last_name}",
            "appointment_time": str(apt.appointment_time),
            "status": apt.status,
            "checked_in_at": apt.checked_in_at.isoformat() if apt.checked_in_at else None,
            "checked_out_at": apt.checked_out_at.isoformat() if apt.checked_out_at else None,
        })

    # Find current/next patient
    current_patient = None
    next_patient = None
    for item in queue:
        if item["status"] == "in_progress":
            current_patient = item
        elif item["status"] in ["confirmed"] and not item["checked_out_at"] and not next_patient:
            next_patient = item

    return {
        "doctor_id": doctor_id,
        "date": target_date.isoformat(),
        "total_in_queue": len(queue),
        "current_patient": current_patient,
        "next_patient": next_patient,
        "queue": queue
    }


@router.post("/queue/{doctor_id}/call-next")
async def call_next_patient(
    doctor_id: int,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Move to the next patient in queue for a doctor"""
    today = date.today()
    date_start = datetime.combine(today, datetime.min.time())
    date_end = datetime.combine(today, datetime.max.time())

    # Complete current in_progress appointment
    current = db.query(Appointment).join(Patient).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date >= date_start,
        Appointment.appointment_date <= date_end,
        Appointment.status == "in_progress",
        Patient.hospital_id == current_user.hospital_id
    ).first()

    if current:
        current.status = "completed"
        current.consultation_ended_at = datetime.now()
        current.checked_out_at = datetime.now()

    # Find next checked-in patient
    next_apt = db.query(Appointment).join(Patient).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.appointment_date >= date_start,
        Appointment.appointment_date <= date_end,
        Appointment.status == "confirmed",
        Appointment.checked_in_at.isnot(None),
        Appointment.checked_out_at.is_(None),
        Patient.hospital_id == current_user.hospital_id
    ).order_by(Appointment.token_number).first()

    if not next_apt:
        db.commit()
        return {"message": "No more patients in queue", "current_patient": None}

    next_apt.status = "in_progress"
    next_apt.consultation_started_at = datetime.now()

    db.commit()
    db.refresh(next_apt)

    return {
        "message": f"Now serving token #{next_apt.token_number}",
        "current_patient": {
            "appointment_id": next_apt.id,
            "token_number": next_apt.token_number,
            "patient_name": f"{next_apt.patient.first_name} {next_apt.patient.last_name}",
            "appointment_time": str(next_apt.appointment_time),
        }
    }


@router.post("/{appointment_id}/start-consultation")
async def start_consultation(
    appointment_id: int,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Start consultation for a checked-in patient"""
    appointment = db.query(Appointment).join(Patient).filter(
        Appointment.id == appointment_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appointment.status == "in_progress":
        raise HTTPException(status_code=400, detail="Consultation already in progress")

    if appointment.status in ["completed", "cancelled", "no_show"]:
        raise HTTPException(status_code=400, detail=f"Cannot start consultation for {appointment.status} appointment")

    # Auto check-in if not already checked in (doctor starting consultation implies patient is present)
    if not appointment.checked_in_at:
        appointment.checked_in_at = datetime.now()

    appointment.status = "in_progress"
    appointment.consultation_started_at = datetime.now()

    db.commit()
    db.refresh(appointment)

    return {
        "message": "Consultation started",
        "appointment_id": appointment.id,
        "consultation_started_at": appointment.consultation_started_at.isoformat()
    }


@router.post("/{appointment_id}/no-show")
async def mark_no_show(
    appointment_id: int,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Mark a patient as no-show"""
    appointment = db.query(Appointment).join(Patient).filter(
        Appointment.id == appointment_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if appointment.status in ["completed", "cancelled", "no_show"]:
        raise HTTPException(status_code=400, detail=f"Cannot mark {appointment.status} appointment as no-show")

    appointment.status = "no_show"

    db.commit()
    db.refresh(appointment)

    return {
        "message": "Appointment marked as no-show",
        "appointment_id": appointment.id
    }


class NotesUpdate(BaseModel):
    notes: str = Field(..., max_length=2000)

@router.put("/{appointment_id}/notes")
async def update_appointment_notes(
    appointment_id: int,
    notes_data: NotesUpdate,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Update notes for an appointment"""
    appointment = db.query(Appointment).join(Patient).filter(
        Appointment.id == appointment_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    appointment.notes = notes_data.notes

    db.commit()
    db.refresh(appointment)

    return {
        "message": "Notes updated",
        "appointment_id": appointment.id,
        "notes": appointment.notes
    }


@router.get("/patient/{patient_uuid}/history")
async def get_patient_appointment_history(
    patient_uuid: str,
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get appointment history for a patient"""
    patient = db.query(Patient).filter(
        Patient.patient_id == patient_uuid,
        Patient.hospital_id == current_user.hospital_id
    ).first()

    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    appointments = db.query(Appointment).filter(
        Appointment.patient_id == patient.id
    ).order_by(Appointment.appointment_date.desc(), Appointment.appointment_time.desc()
    ).offset(skip).limit(limit).all()

    result = []
    for apt in appointments:
        doctor = db.query(User).filter(User.id == apt.doctor_id).first()
        result.append({
            "id": apt.id,
            "appointment_number": apt.appointment_number,
            "appointment_date": apt.appointment_date.isoformat() if apt.appointment_date else None,
            "appointment_time": str(apt.appointment_time) if apt.appointment_time else None,
            "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "Unknown",
            "doctor_specialization": doctor.specialization if doctor else None,
            "appointment_type": apt.appointment_type,
            "status": apt.status,
            "reason": apt.reason,
            "notes": apt.notes,
            "consultation_fee": apt.consultation_fee or 0.0,
            "final_amount": apt.final_amount or 0.0,
            "payment_status": apt.payment_status or "pending",
            "token_number": apt.token_number,
            "cancellation_reason": apt.cancellation_reason,
            "checked_in_at": apt.checked_in_at.isoformat() if apt.checked_in_at else None,
            "checked_out_at": apt.checked_out_at.isoformat() if apt.checked_out_at else None,
        })

    return {
        "patient_id": patient_uuid,
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "total_appointments": len(result),
        "appointments": result
    }


@router.get("/reports/daily-summary")
async def get_daily_summary(
    report_date: Optional[date] = None,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get daily appointment and revenue summary"""
    target_date = report_date or date.today()
    date_start = datetime.combine(target_date, datetime.min.time())
    date_end = datetime.combine(target_date, datetime.max.time())

    appointments = db.query(Appointment).join(Patient).filter(
        Appointment.appointment_date >= date_start,
        Appointment.appointment_date <= date_end,
        Patient.hospital_id == current_user.hospital_id
    ).all()

    total = len(appointments)
    by_status = {}
    by_doctor = {}
    by_type = {}
    total_revenue = 0.0
    total_collected = 0.0
    payment_methods = {}

    for apt in appointments:
        # Status counts
        by_status[apt.status] = by_status.get(apt.status, 0) + 1

        # Doctor counts
        doctor_name = f"Dr. {apt.doctor.first_name} {apt.doctor.last_name}" if apt.doctor else "Unknown"
        if doctor_name not in by_doctor:
            by_doctor[doctor_name] = {"count": 0, "revenue": 0.0, "collected": 0.0}
        by_doctor[doctor_name]["count"] += 1
        by_doctor[doctor_name]["revenue"] += apt.final_amount or 0.0
        if apt.payment_status == "paid":
            by_doctor[doctor_name]["collected"] += apt.final_amount or 0.0

        # Type counts
        by_type[apt.appointment_type or "consultation"] = by_type.get(apt.appointment_type or "consultation", 0) + 1

        # Revenue
        total_revenue += apt.final_amount or 0.0
        if apt.payment_status == "paid":
            total_collected += apt.final_amount or 0.0

        # Payment methods
        if apt.payment_status == "paid" and apt.payment_method:
            method = apt.payment_method
            if method not in payment_methods:
                payment_methods[method] = {"count": 0, "amount": 0.0}
            payment_methods[method]["count"] += 1
            payment_methods[method]["amount"] += apt.final_amount or 0.0

    return {
        "date": target_date.isoformat(),
        "total_appointments": total,
        "by_status": by_status,
        "by_doctor": by_doctor,
        "by_type": by_type,
        "revenue": {
            "total_billed": total_revenue,
            "total_collected": total_collected,
            "pending": total_revenue - total_collected
        },
        "payment_methods": payment_methods
    }


@router.delete("/{appointment_id}", status_code=204)
async def delete_appointment(
    appointment_id: int,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "delete")),
    db: Session = Depends(get_db)
):
    """Delete appointment"""
    appointment = db.query(Appointment).join(Patient).filter(
        Appointment.id == appointment_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Only allow deletion of scheduled or cancelled appointments
    if appointment.status in ["in_progress", "completed"]:
        raise HTTPException(status_code=400, detail="Cannot delete appointment in progress or completed")
    
    db.delete(appointment)
    db.commit()
    
    return None

@router.get("/{appointment_id}/bill")
async def get_appointment_bill(
    appointment_id: int,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Generate bill data for appointment consultation fee"""
    appointment = db.query(Appointment).join(Patient).join(User, Appointment.doctor_id == User.id).filter(
        Appointment.id == appointment_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Generate bill number
    bill_number = f"BILL-APT-{appointment.appointment_number}"
    
    # Prepare bill items
    items = [
        {
            "item_name": f"Consultation Fee - {appointment.doctor.specialization or 'General'}",
            "item_code": "CONSULT",
            "quantity": 1,
            "unit_price": appointment.consultation_fee or 0.0,
            "total_price": appointment.consultation_fee or 0.0
        }
    ]

    # Add registration fee as separate line item if charged
    reg_fee = getattr(appointment, 'registration_fee', 0.0) or 0.0
    if reg_fee > 0:
        items.append({
            "item_name": "Patient Registration Fee",
            "item_code": "REG",
            "quantity": 1,
            "unit_price": reg_fee,
            "total_price": reg_fee
        })

    subtotal = (appointment.consultation_fee or 0.0) + reg_fee

    # Prepare bill data
    bill_data = {
        "bill_number": bill_number,
        "bill_date": appointment.created_at.isoformat(),
        "patient_name": f"{appointment.patient.first_name} {appointment.patient.last_name}",
        "doctor_name": f"Dr. {appointment.doctor.first_name} {appointment.doctor.last_name}",
        "status": "generated",
        "items": items,
        "subtotal": subtotal,
        "discount_amount": appointment.discount_amount or 0.0,
        "tax_amount": 0.0,
        "total_amount": appointment.final_amount or 0.0,
        "amount_paid": appointment.final_amount if appointment.payment_status == "paid" else 0.0,
        "balance_due": 0.0 if appointment.payment_status == "paid" else appointment.final_amount or 0.0
    }
    
    # Add payment receipt if payment was made
    if appointment.payment_status == "paid":
        bill_data["payment_receipt"] = {
            "receipt_number": f"RCP-{appointment.appointment_number}",
            "payment_date": appointment.payment_date.isoformat() if appointment.payment_date else appointment.created_at.isoformat(),
            "amount_paid": appointment.final_amount or 0.0,
            "payment_method": appointment.payment_method or "cash",
            "transaction_reference": appointment.appointment_number
        }
    
    return bill_data

@router.get("/{appointment_id}/bill/download")
async def download_appointment_bill(
    appointment_id: int,
    include_header: bool = True,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Download appointment bill as PDF"""
    # Get bill data
    appointment = db.query(Appointment).join(Patient).join(User, Appointment.doctor_id == User.id).filter(
        Appointment.id == appointment_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Get hospital info
    hospital = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
    hospital_info = {
        "name": hospital.name if hospital else "Hospital",
        "address": hospital.address if hospital else "",
        "phone": hospital.phone if hospital else "",
        "email": hospital.email if hospital else "",
        "website": hospital.website if hospital else "",
        "logo_url": hospital.logo_url if hospital else ""
    }
    
    # Generate bill number
    bill_number = f"BILL-APT-{appointment.appointment_number}"
    
    # Get booked by user name
    booked_by_name = ""
    if appointment.booked_by_id:
        booked_by = db.query(User).filter(User.id == appointment.booked_by_id).first()
        if booked_by:
            booked_by_name = f"{booked_by.first_name} {booked_by.last_name}"

    # Prepare bill data for PDF
    bill_data = {
        "bill_number": bill_number,
        "bill_date": appointment.created_at.isoformat(),
        "print_date": datetime.now().isoformat(),
        "patient_name": f"{appointment.patient.first_name} {appointment.patient.last_name}",
        "patient_phone": appointment.patient.primary_phone or "",
        "patient_id": appointment.patient.patient_id or "",
        "patient_age": "",
        "patient_gender": appointment.patient.gender or "",
        "reg_no": appointment.appointment_number,
        "doctor_name": f"Dr. {appointment.doctor.first_name} {appointment.doctor.last_name}",
        "doctor_specialization": appointment.doctor.specialization or "General",
        "appointment_type": appointment.appointment_type or "consultation",
        "payment_method": (appointment.payment_method or "cash").capitalize(),
        "payment_status": appointment.payment_status or "pending",
        "prepared_by": booked_by_name,
        "items": [
            {
                "item_name": f"Consultation Fee - {appointment.doctor.specialization or 'General'}",
                "item_code": "CONSULT",
                "quantity": 1,
                "unit_price": appointment.consultation_fee or 0.0,
                "total_price": appointment.consultation_fee or 0.0
            }
        ] + ([{
                "item_name": "Patient Registration Fee",
                "item_code": "REG",
                "quantity": 1,
                "unit_price": appointment.registration_fee,
                "total_price": appointment.registration_fee
        }] if getattr(appointment, 'registration_fee', 0) else []),
        "subtotal": (appointment.consultation_fee or 0.0) + (getattr(appointment, 'registration_fee', 0.0) or 0.0),
        "discount_amount": appointment.discount_amount or 0.0,
        "total_amount": appointment.final_amount or 0.0,
        "amount_paid": appointment.final_amount if appointment.payment_status == "paid" else 0.0,
        "balance_due": 0.0 if appointment.payment_status == "paid" else appointment.final_amount or 0.0
    }

    # Calculate patient age if date_of_birth exists
    if appointment.patient.date_of_birth:
        from dateutil.relativedelta import relativedelta
        try:
            dob = appointment.patient.date_of_birth
            if isinstance(dob, str):
                dob = datetime.fromisoformat(dob).date()
            age = relativedelta(datetime.now().date(), dob)
            bill_data["patient_age"] = f"{age.years} Years"
        except Exception:
            bill_data["patient_age"] = ""

    # Generate PDF
    pdf_buffer = pdf_service.generate_bill_pdf(bill_data, hospital_info, include_header=include_header)

    return StreamingResponse(
        io.BytesIO(pdf_buffer.read()),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=appointment_bill_{appointment.appointment_number}.pdf"}
    )