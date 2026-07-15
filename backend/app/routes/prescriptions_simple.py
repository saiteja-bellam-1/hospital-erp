from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, time
import uuid

from config.database import get_db
from app.utils.pdf_settings import pdf_gen_kwargs
from app.models.prescriptions_simple import SimplePrescription
from app.models.patient import Patient
from app.models.user import User
from app.models.ehr import Consultation
from app.models.hospital import Hospital
from app.models.outpatient import Appointment
from app.utils.dependencies import get_current_user, require_permission
from app.utils.auth import Modules
from app.utils.pdf_service import pdf_service

router = APIRouter()

# Pydantic models for API
class MedicineItem(BaseModel):
    medicine_id: Optional[int] = Field(None, description="Linked pharmacy medicine ID")
    name: str = Field(..., description="Medicine name (e.g., Paracetamol 500mg)")
    dosage: str = Field(..., description="Dosage instructions (e.g., 1 tablet twice daily)")
    duration: str = Field(..., description="Duration (e.g., 5 days)")
    instructions: Optional[str] = Field(None, description="Additional instructions")
    quantity: Optional[str] = Field(None, description="Quantity to be given")
    frequency_schedule: Optional[str] = Field("1-0-0", description="Morning-Afternoon-Night schedule (e.g., 1-0-1 for morning and night)")
    food_timing: Optional[str] = Field("after_food", description="Food timing (before_food, after_food, with_food, on_empty_stomach, anytime)")

class PrescriptionCreate(BaseModel):
    patient_id: str = Field(..., description="Patient UUID")
    consultation_id: Optional[int] = Field(None, description="Consultation ID if linked")
    appointment_id: Optional[int] = Field(None, description="Appointment ID if linked")
    admission_id: Optional[int] = Field(None, description="Inpatient admission ID if linked")
    medicines: List[MedicineItem] = Field(..., min_items=1, description="List of medicines")
    diagnosis: Optional[str] = Field(None, description="Diagnosis")
    notes: Optional[str] = Field(None, description="Additional notes")

class PrescriptionUpdate(BaseModel):
    medicines: Optional[List[MedicineItem]] = None
    diagnosis: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(active|cancelled|completed|blank)$")


class BlankPrescriptionCreate(BaseModel):
    patient_id: Optional[str] = Field(None, description="Patient UUID")
    doctor_id: Optional[int] = Field(None, description="Prescribing doctor user id")
    appointment_id: Optional[int] = Field(None, description="Linked appointment id")

class PrescriptionResponse(BaseModel):
    id: int
    prescription_id: str
    patient_id: str
    patient_name: str
    doctor_id: int
    doctor_name: str
    consultation_id: Optional[int]
    appointment_id: Optional[int] = None
    admission_id: Optional[int] = None
    medicines: List[dict]
    diagnosis: Optional[str]
    notes: Optional[str]
    status: str
    prescription_date: datetime
    created_at: datetime
    
    class Config:
        from_attributes = True

def generate_prescription_id() -> str:
    """Generate unique prescription ID when no appointment is linked."""
    timestamp = datetime.now().strftime('%Y%m%d')
    unique_id = str(uuid.uuid4()).split('-')[0].upper()
    return f"RX-{timestamp}-{unique_id}"


def _prescribed_quantity(value) -> int:
    """Coerce the OP free-text quantity field to a positive stock quantity."""
    if value is None or value == "":
        return 1
    try:
        return max(1, int(float(value)))
    except (TypeError, ValueError):
        # Older records may contain values such as "10 tablets".
        import re
        match = re.search(r"\d+(?:\.\d+)?", str(value))
        return max(1, int(float(match.group(0)))) if match else 1


def _sync_to_pharmacy_prescription(
    db: Session,
    simple: SimplePrescription,
    patient: Patient,
) -> None:
    """Mirror a filled OP prescription into pharmacy's stock-linked queue."""
    from app.models.pharmacy import (
        Medicine,
        MedicineCategory,
        Prescription,
        PrescriptionItem,
    )
    from app.utils.pharmacy_pricing import medicine_sale_rate
    from app.utils.prescription_schedule import build_dosage_instruction

    linked = None
    if simple.pharmacy_prescription_id:
        linked = db.query(Prescription).filter(
            Prescription.id == simple.pharmacy_prescription_id,
            Prescription.patient_id == patient.id,
        ).first()

    medicines = simple.medicines or []
    if simple.status in ("blank", "cancelled") or not medicines:
        if linked and linked.status == "pending" and not any(
            float(item.quantity_dispensed or 0) > 0 for item in linked.items
        ):
            linked.status = "cancelled"
        return

    can_replace = (
        linked is not None
        and linked.status == "pending"
        and not linked.pharmacy_sale_id
        and not any(float(item.quantity_dispensed or 0) > 0 for item in linked.items)
    )
    if not can_replace:
        linked = Prescription(
            prescription_number=simple.prescription_id,
            patient_id=patient.id,
            doctor_id=simple.doctor_id,
            consultation_id=simple.consultation_id,
            admission_id=None,
            notes=simple.notes,
            status="pending",
        )
        # A previously dispensed/cancelled version may already use the stable OP
        # number. Keep it for audit and mint a revision number for the new order.
        if db.query(Prescription.id).filter(
            Prescription.prescription_number == linked.prescription_number
        ).first():
            linked.prescription_number = f"{simple.prescription_id}-{uuid.uuid4().hex[:6].upper()}"
        db.add(linked)
        db.flush()
        simple.pharmacy_prescription_id = linked.id
    else:
        db.query(PrescriptionItem).filter(
            PrescriptionItem.prescription_id == linked.id
        ).delete(synchronize_session=False)
        linked.doctor_id = simple.doctor_id
        linked.consultation_id = simple.consultation_id
        linked.notes = simple.notes
        linked.status = "pending"

    general_category = None
    total_amount = 0.0
    for med_data in medicines:
        name = str(med_data.get("name") or "").strip()
        if not name:
            continue
        medicine_id = med_data.get("medicine_id")
        medicine = None
        if medicine_id:
            medicine = db.query(Medicine).filter(
                Medicine.id == medicine_id,
                Medicine.hospital_id == simple.hospital_id,
                Medicine.is_active == True,  # noqa: E712
            ).first()
        if not medicine:
            medicine = db.query(Medicine).filter(
                Medicine.hospital_id == simple.hospital_id,
                Medicine.is_active == True,  # noqa: E712
                Medicine.name.ilike(name),
            ).first()
        if not medicine:
            if general_category is None:
                general_category = db.query(MedicineCategory).filter(
                    MedicineCategory.hospital_id == simple.hospital_id,
                    MedicineCategory.name == "General",
                ).first()
                if not general_category:
                    general_category = MedicineCategory(
                        name="General",
                        description="General medicines without specific category",
                        hospital_id=simple.hospital_id,
                    )
                    db.add(general_category)
                    db.flush()
            medicine = Medicine(
                medicine_code=f"TXT-{uuid.uuid4().hex[:8].upper()}",
                name=name,
                category_id=general_category.id,
                unit_price=0.0,
                rate_a=0.0,
                hospital_id=simple.hospital_id,
                requires_prescription=True,
                is_hidden=True,
            )
            db.add(medicine)
            db.flush()

        quantity = _prescribed_quantity(med_data.get("quantity"))
        unit_price = medicine_sale_rate(medicine)
        total = unit_price * quantity
        total_amount += total
        db.add(PrescriptionItem(
            prescription_id=linked.id,
            medicine_id=medicine.id,
            quantity_prescribed=quantity,
            quantity_dispensed=0,
            dosage=build_dosage_instruction(
                med_data.get("dosage"),
                med_data.get("frequency_schedule") or "1-0-0",
                med_data.get("food_timing") or "after_food",
            ),
            duration=med_data.get("duration") or "",
            instructions=med_data.get("instructions"),
            unit_price=unit_price,
            total_price=total,
            status="pending",
        ))
    linked.total_amount = total_amount


def _prescription_id_for_appointment(appointment: Appointment) -> str:
    """One stable Rx code per appointment — reused for blank and doctor-filled Rx."""
    return f"RX-{appointment.appointment_number}"


def _find_prescription_for_appointment(
    db: Session,
    hospital_id: int,
    appointment_id: int,
) -> Optional[SimplePrescription]:
    row = (
        db.query(SimplePrescription)
        .filter(
            SimplePrescription.hospital_id == hospital_id,
            SimplePrescription.appointment_id == appointment_id,
        )
        .order_by(SimplePrescription.created_at.desc())
        .first()
    )
    if row:
        return row

    tag = _blank_appointment_notes(appointment_id)
    return (
        db.query(SimplePrescription)
        .filter(
            SimplePrescription.hospital_id == hospital_id,
            SimplePrescription.notes == tag,
        )
        .order_by(SimplePrescription.created_at.desc())
        .first()
    )


def _resolve_appointment_id(
    db: Session,
    *,
    appointment_id: Optional[int],
    consultation_id: Optional[int],
) -> Optional[int]:
    if appointment_id is not None:
        return appointment_id
    if consultation_id is None:
        return None
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    return consultation.appointment_id if consultation else None


BLANK_APT_NOTES_PREFIX = "__blank_appointment:"


def _blank_appointment_notes(appointment_id: int) -> str:
    return f"{BLANK_APT_NOTES_PREFIX}{appointment_id}__"


def _parse_blank_appointment_id(notes: Optional[str]) -> Optional[int]:
    if not notes or not notes.startswith(BLANK_APT_NOTES_PREFIX):
        return None
    try:
        return int(notes[len(BLANK_APT_NOTES_PREFIX):].rstrip("_"))
    except (TypeError, ValueError):
        return None


def _resolve_blank_prescription_context(
    db: Session,
    hospital_id: int,
    *,
    patient_id: Optional[str],
    doctor_id: Optional[int],
    appointment_id: Optional[int],
) -> tuple[Patient, User, Optional[Appointment]]:
    appointment = None
    if appointment_id is not None:
        appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found",
            )

    patient = None
    if patient_id:
        patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    elif appointment:
        patient = db.query(Patient).filter(Patient.id == appointment.patient_id).first()

    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )
    if patient.hospital_id != hospital_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    if appointment and appointment.patient_id != patient.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Appointment does not belong to the specified patient",
        )

    resolved_doctor_id = doctor_id
    if appointment and not resolved_doctor_id:
        resolved_doctor_id = appointment.doctor_id
    if not resolved_doctor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="doctor_id is required (or provide appointment_id with a doctor)",
        )

    doctor = db.query(User).filter(User.id == resolved_doctor_id).first()
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )
    if doctor.hospital_id != hospital_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    return patient, doctor, appointment


def _get_or_create_blank_prescription(
    db: Session,
    hospital_id: int,
    patient: Patient,
    doctor: User,
    *,
    appointment: Optional[Appointment] = None,
) -> SimplePrescription:
    """Reuse one prescription per appointment (blank or already filled by doctor)."""
    if appointment:
        existing = _find_prescription_for_appointment(db, hospital_id, appointment.id)
        if existing:
            if not existing.appointment_id:
                existing.appointment_id = appointment.id
                db.commit()
                db.refresh(existing)
            return existing

        prescription = SimplePrescription(
            prescription_id=_prescription_id_for_appointment(appointment),
            patient_id=patient.patient_id,
            doctor_id=doctor.id,
            appointment_id=appointment.id,
            medicines=[],
            diagnosis=None,
            notes=_blank_appointment_notes(appointment.id),
            hospital_id=hospital_id,
            status="blank",
        )
        db.add(prescription)
        db.commit()
        db.refresh(prescription)
        return prescription

    prescription = SimplePrescription(
        prescription_id=generate_prescription_id(),
        patient_id=patient.patient_id,
        doctor_id=doctor.id,
        medicines=[],
        diagnosis=None,
        notes="Blank prescription form",
        hospital_id=hospital_id,
        status="blank",
    )
    db.add(prescription)
    db.commit()
    db.refresh(prescription)
    return prescription


def _blank_prescription_pdf_response(
    prescription: SimplePrescription,
    patient: Patient,
    doctor: User,
    *,
    appointment: Optional[Appointment],
    db: Session,
    hospital_id: int,
) -> Response:
    prescription_pdf_data = _build_blank_prescription_pdf_data(
        db,
        patient,
        doctor,
        appointment=appointment,
    )
    prescription_pdf_data["prescription_number"] = prescription.prescription_id
    if prescription.prescription_date:
        prescription_pdf_data["prescription_date"] = prescription.prescription_date.isoformat()

    hospital_info = _hospital_info_for_pdf(db, hospital_id)
    pdf_buffer = pdf_service.generate_prescription_pdf(
        prescription_pdf_data,
        hospital_info,
        blank_mode=True,
        **pdf_gen_kwargs(db, hospital_id, 'prescription'),
    )

    filename = f"prescription_{prescription.prescription_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Prescription-Id": prescription.prescription_id,
        },
    )


from app.utils.patient_age import format_patient_age, patient_age_years_int


def _hospital_info_for_pdf(db: Session, hospital_id: int) -> dict:
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    return {
        "name": hospital.name if hospital else "General Hospital",
        "address": hospital.address if hospital else "Hospital Address",
        "phone": hospital.phone if hospital else "+1-000-000-0000",
        "email": hospital.email if hospital else "info@hospital.com",
        "logo_url": hospital.logo_url if hospital and hasattr(hospital, 'logo_url') else '',
    }


def _build_patient_prescription_fields(patient: Patient) -> dict:
    """Patient fields shared by filled and blank prescription PDFs."""
    return {
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "patient_age": patient_age_years_int(patient),
        "patient_age_display": format_patient_age(patient),
        "patient_gender": (patient.gender or '').capitalize(),
        "patient_phone": patient.primary_phone or '',
        "patient_blood_group": patient.blood_group or '',
        "mrn": patient.mrn or "",
        "village": patient.village or "",
        "mandal": patient.mandal or "",
        "district": patient.district or "",
        "address_line1": patient.address_line1 or "",
        "address_line2": patient.address_line2 or "",
        "patient_id_display": patient.patient_id,
    }


def _fetch_lab_tests_for_appointment(
    db: Session,
    patient: Patient,
    appointment_id: Optional[int] = None,
) -> list:
    from app.models.lab import PatientLabOrder, LabTest

    lab_query = (
        db.query(PatientLabOrder, LabTest)
        .join(LabTest, PatientLabOrder.test_id == LabTest.id)
        .filter(PatientLabOrder.patient_id == patient.id)
    )
    if appointment_id:
        lab_query = lab_query.filter(PatientLabOrder.appointment_id == appointment_id)

    lab_orders = lab_query.order_by(PatientLabOrder.order_date.desc()).limit(10).all()
    return [
        {
            "test_name": test.name,
            "test_code": test.test_code,
            "status": order.status,
            "order_date": order.order_date.strftime('%d/%m/%Y') if order.order_date else '',
        }
        for order, test in lab_orders
    ]


def _resolve_referred_by(patient: Patient, appointment: Optional[Appointment] = None) -> str:
    if appointment and appointment.referred_by:
        return appointment.referred_by.strip()
    if patient.referred_by:
        return patient.referred_by.strip()
    return ''


def _build_blank_prescription_pdf_data(
    db: Session,
    patient: Patient,
    doctor: User,
    *,
    appointment: Optional[Appointment] = None,
) -> dict:
    now = datetime.now()
    rx_dt = now

    if appointment:
        if appointment.appointment_date:
            apt_date = appointment.appointment_date
            if isinstance(apt_date, datetime):
                rx_dt = apt_date
            else:
                rx_dt = datetime.combine(apt_date, time.min)

    apt_id = appointment.id if appointment else None

    return {
        **_build_patient_prescription_fields(patient),
        "prescription_number": None,
        "appointment_number": appointment.appointment_number if appointment else None,
        "appointment_id": appointment.id if appointment else None,
        "prescription_date": rx_dt.isoformat(),
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}",
        "doctor_specialization": doctor.specialization if hasattr(doctor, 'specialization') else '',
        "doctor_registration_number": doctor.license_number if hasattr(doctor, 'license_number') else '',
        "referred_by": _resolve_referred_by(patient, appointment),
        "status": "blank",
        "notes": None,
        "diagnosis": None,
        "vitals": None,
        "consultation": None,
        "lab_tests": _fetch_lab_tests_for_appointment(db, patient, apt_id),
        "items": [],
    }


@router.post("/blank")
async def issue_blank_prescription(
    body: BlankPrescriptionCreate,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db),
):
    """Create (or reuse) a numbered blank prescription and return its PDF."""
    return _issue_blank_prescription(
        db,
        current_user,
        patient_id=body.patient_id,
        doctor_id=body.doctor_id,
        appointment_id=body.appointment_id,
    )


@router.get("/blank/download")
async def issue_blank_prescription_download(
    patient_id: Optional[str] = None,
    doctor_id: Optional[int] = None,
    appointment_id: Optional[int] = None,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db),
):
    """Legacy GET alias — prefer POST /blank."""
    return _issue_blank_prescription(
        db,
        current_user,
        patient_id=patient_id,
        doctor_id=doctor_id,
        appointment_id=appointment_id,
    )


def _issue_blank_prescription(
    db: Session,
    current_user: User,
    *,
    patient_id: Optional[str],
    doctor_id: Optional[int],
    appointment_id: Optional[int],
) -> Response:
    patient, doctor, appointment = _resolve_blank_prescription_context(
        db,
        current_user.hospital_id,
        patient_id=patient_id,
        doctor_id=doctor_id,
        appointment_id=appointment_id,
    )
    prescription = _get_or_create_blank_prescription(
        db,
        current_user.hospital_id,
        patient,
        doctor,
        appointment=appointment,
    )
    return _blank_prescription_pdf_response(
        prescription,
        patient,
        doctor,
        appointment=appointment,
        db=db,
        hospital_id=current_user.hospital_id,
    )


@router.post("/", response_model=PrescriptionResponse)
async def create_prescription(
    prescription_data: PrescriptionCreate,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Create a new prescription with JSON medicine storage"""

    # Verify patient exists
    patient = db.query(Patient).filter(Patient.patient_id == prescription_data.patient_id).first()
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Patient not found for id: {prescription_data.patient_id}"
        )
    
    # Verify patient belongs to same hospital
    if patient.hospital_id != current_user.hospital_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Verify consultation exists if provided
    consultation = None
    if prescription_data.consultation_id:
        consultation = db.query(Consultation).filter(
            Consultation.id == prescription_data.consultation_id
        ).first()
        if not consultation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Consultation not found"
            )
        if consultation.patient_id != patient.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Consultation does not belong to the specified patient"
            )

    resolved_appointment_id = _resolve_appointment_id(
        db,
        appointment_id=prescription_data.appointment_id,
        consultation_id=prescription_data.consultation_id,
    )
    linked_appointment = None
    if resolved_appointment_id is not None:
        linked_appointment = db.query(Appointment).filter(
            Appointment.id == resolved_appointment_id
        ).first()
        if not linked_appointment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Appointment not found",
            )
        if linked_appointment.patient_id != patient.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Appointment does not belong to the specified patient",
            )
    
    # Convert medicines to JSON format
    medicines_json = [
        {
            "medicine_id": medicine.medicine_id,
            "name": medicine.name,
            "dosage": medicine.dosage,
            "duration": medicine.duration,
            "instructions": medicine.instructions,
            "quantity": medicine.quantity,
            "frequency_schedule": medicine.frequency_schedule,
            "food_timing": medicine.food_timing
        }
        for medicine in prescription_data.medicines
    ]

    existing = None
    if resolved_appointment_id is not None:
        existing = _find_prescription_for_appointment(
            db, current_user.hospital_id, resolved_appointment_id
        )

    if existing:
        existing.medicines = medicines_json
        existing.diagnosis = prescription_data.diagnosis
        existing.notes = prescription_data.notes
        existing.consultation_id = prescription_data.consultation_id
        existing.appointment_id = resolved_appointment_id
        existing.doctor_id = current_user.id
        existing.status = "active"
        _sync_to_pharmacy_prescription(db, existing, patient)
        db.commit()
        db.refresh(existing)
        return build_prescription_response(existing, db)
    
    # Create prescription
    rx_code = (
        _prescription_id_for_appointment(linked_appointment)
        if linked_appointment
        else generate_prescription_id()
    )
    prescription = SimplePrescription(
        prescription_id=rx_code,
        patient_id=prescription_data.patient_id,
        doctor_id=current_user.id,
        consultation_id=prescription_data.consultation_id,
        appointment_id=resolved_appointment_id,
        admission_id=prescription_data.admission_id,
        medicines=medicines_json,
        diagnosis=prescription_data.diagnosis,
        notes=prescription_data.notes,
        hospital_id=current_user.hospital_id,
        status="active"
    )
    
    db.add(prescription)
    db.flush()
    _sync_to_pharmacy_prescription(db, prescription, patient)
    db.commit()
    db.refresh(prescription)
    
    return build_prescription_response(prescription, db)

@router.get("/", response_model=List[PrescriptionResponse])
async def get_prescriptions(
    patient_id: Optional[str] = None,
    doctor_id: Optional[int] = None,
    consultation_id: Optional[int] = None,
    appointment_id: Optional[int] = None,
    admission_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get prescriptions with optional filters"""
    query = db.query(SimplePrescription).filter(
        SimplePrescription.hospital_id == current_user.hospital_id
    )

    # Apply filters
    if patient_id:
        query = query.filter(SimplePrescription.patient_id == patient_id)

    if doctor_id:
        query = query.filter(SimplePrescription.doctor_id == doctor_id)

    if consultation_id:
        query = query.filter(SimplePrescription.consultation_id == consultation_id)

    if appointment_id:
        query = query.filter(SimplePrescription.appointment_id == appointment_id)

    if admission_id:
        query = query.filter(SimplePrescription.admission_id == admission_id)

    if status:
        query = query.filter(SimplePrescription.status == status)
    
    # For doctors, only show their own prescriptions unless they're admin
    if current_user.has_role('doctor'):
        query = query.filter(SimplePrescription.doctor_id == current_user.id)
    
    prescriptions = query.order_by(
        SimplePrescription.prescription_date.desc()
    ).offset(offset).limit(limit).all()
    
    return [build_prescription_response(prescription, db) for prescription in prescriptions]

@router.get("/{prescription_id}", response_model=PrescriptionResponse)
async def get_prescription(
    prescription_id: str,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get a specific prescription"""
    prescription = db.query(SimplePrescription).filter(
        SimplePrescription.prescription_id == prescription_id,
        SimplePrescription.hospital_id == current_user.hospital_id
    ).first()
    
    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )
    
    # Check access permissions
    if (current_user.has_role('doctor') and
        prescription.doctor_id != current_user.id and
        not any(r in current_user.role_names for r in ['super_admin', 'hospital_admin'])):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this prescription"
        )
    
    return build_prescription_response(prescription, db)

@router.put("/{prescription_id}", response_model=PrescriptionResponse)
async def update_prescription(
    prescription_id: str,
    prescription_data: PrescriptionUpdate,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Update a prescription"""
    prescription = db.query(SimplePrescription).filter(
        SimplePrescription.prescription_id == prescription_id,
        SimplePrescription.hospital_id == current_user.hospital_id
    ).first()
    
    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )
    
    # Only the prescribing doctor or admin can update
    if (prescription.doctor_id != current_user.id and
        not any(r in current_user.role_names for r in ['super_admin', 'hospital_admin'])):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the prescribing doctor can update this prescription"
        )
    
    # Update fields
    if prescription_data.medicines is not None:
        medicines_json = [
            {
                "medicine_id": medicine.medicine_id,
                "name": medicine.name,
                "dosage": medicine.dosage,
                "duration": medicine.duration,
                "instructions": medicine.instructions,
                "quantity": medicine.quantity,
                "frequency_schedule": medicine.frequency_schedule,
                "food_timing": medicine.food_timing
            }
            for medicine in prescription_data.medicines
        ]
        prescription.medicines = medicines_json
        if medicines_json and prescription.status == "blank":
            prescription.status = "active"

    if prescription_data.diagnosis is not None:
        prescription.diagnosis = prescription_data.diagnosis
        
    if prescription_data.notes is not None:
        prescription.notes = prescription_data.notes
        
    if prescription_data.status is not None:
        prescription.status = prescription_data.status

    patient = db.query(Patient).filter(
        Patient.patient_id == prescription.patient_id,
        Patient.hospital_id == current_user.hospital_id,
    ).first()
    if patient:
        _sync_to_pharmacy_prescription(db, prescription, patient)

    db.commit()
    db.refresh(prescription)
    
    return build_prescription_response(prescription, db)

@router.get("/{prescription_id}/download")
async def download_prescription_pdf(
    prescription_id: str,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Download a doctor-filled prescription PDF (vitals, findings, medicines, tests).

    For blank/empty forms use POST /blank or GET /blank/download instead.
    """
    import json as json_lib
    from app.models.ehr import Consultation
    from app.models.lab import PatientLabOrder, LabTest

    prescription = db.query(SimplePrescription).filter(
        SimplePrescription.prescription_id == prescription_id,
        SimplePrescription.hospital_id == current_user.hospital_id
    ).first()

    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )

    medicines = prescription.medicines or []
    if prescription.status == "blank" and len(medicines) == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Prescription is still blank; use /api/prescriptions-simple/blank/download",
        )

    # Get patient and doctor info
    patient = db.query(Patient).filter(Patient.patient_id == prescription.patient_id).first()
    doctor = db.query(User).filter(User.id == prescription.doctor_id).first()

    linked_appointment = None
    if prescription.appointment_id:
        linked_appointment = db.query(Appointment).filter(
            Appointment.id == prescription.appointment_id
        ).first()
    if not linked_appointment:
        apt_id = _parse_blank_appointment_id(prescription.notes)
        if apt_id:
            linked_appointment = db.query(Appointment).filter(Appointment.id == apt_id).first()

    # --- Fetch consultation findings first (needed to check its vitals too) ---
    consultation_data = None
    consultation = None
    if prescription.consultation_id:
        consultation = db.query(Consultation).filter(Consultation.id == prescription.consultation_id).first()
    if not consultation and patient:
        consultation = db.query(Consultation).filter(
            Consultation.patient_id == patient.id,
            Consultation.consultation_type != "vitals_recording"
        ).order_by(Consultation.created_at.desc()).first()

    if consultation:
        consultation_data = {
            "chief_complaint": consultation.chief_complaint,
            "present_history": consultation.present_history,
            "examination_findings": consultation.examination_findings,
            "follow_up_date": consultation.follow_up_date.strftime('%d/%m/%Y') if consultation.follow_up_date else None
        }

    # --- Fetch vitals (check multiple sources) ---
    vitals_data = None

    # Source 1: vital_signs on the linked/latest consultation itself
    if consultation and consultation.vital_signs:
        try:
            vital_signs = json_lib.loads(consultation.vital_signs)
            if vital_signs and any(vital_signs.values()):
                vitals_data = {
                    "recorded_at": consultation.created_at.strftime('%d/%m/%Y %I:%M %p') if consultation.created_at else '',
                    "vital_signs": vital_signs
                }
        except Exception:
            pass

    # Source 2: dedicated vitals_recording consultation
    if not vitals_data and patient:
        vitals_consultation = db.query(Consultation).filter(
            Consultation.patient_id == patient.id,
            Consultation.consultation_type == "vitals_recording"
        ).order_by(Consultation.created_at.desc()).first()

        if vitals_consultation and vitals_consultation.vital_signs:
            try:
                vital_signs = json_lib.loads(vitals_consultation.vital_signs)
                if vital_signs and any(vital_signs.values()):
                    vitals_data = {
                        "recorded_at": vitals_consultation.created_at.strftime('%d/%m/%Y %I:%M %p') if vitals_consultation.created_at else '',
                        "vital_signs": vital_signs
                    }
            except Exception:
                pass

    # --- Fetch lab orders linked to this consultation/appointment only ---
    lab_tests_ordered = []
    if patient:
        lab_query = db.query(PatientLabOrder, LabTest).join(
            LabTest, PatientLabOrder.test_id == LabTest.id
        ).filter(PatientLabOrder.patient_id == patient.id)

        # Filter by consultation or appointment link
        if consultation:
            lab_query = lab_query.filter(
                (PatientLabOrder.consultation_id == consultation.id) |
                (PatientLabOrder.appointment_id == consultation.appointment_id) if consultation.appointment_id else
                (PatientLabOrder.consultation_id == consultation.id)
            )

        lab_orders = lab_query.order_by(PatientLabOrder.order_date.desc()).limit(10).all()

        for order, test in lab_orders:
            lab_tests_ordered.append({
                "test_name": test.name,
                "test_code": test.test_code,
                "status": order.status,
                "order_date": order.order_date.strftime('%d/%m/%Y') if order.order_date else ''
            })

    # Patient details
    patient_age = None
    patient_age_display = ''
    patient_gender = ''
    patient_phone = ''
    patient_blood_group = ''
    if patient:
        patient_phone = patient.primary_phone or ''
        patient_gender = (patient.gender or '').capitalize()
        patient_blood_group = patient.blood_group or ''
        patient_age = patient_age_years_int(patient)
        patient_age_display = format_patient_age(patient)

    # Get appointment reason if linked
    appointment_reason = ''
    if consultation and hasattr(consultation, 'chief_complaint') and consultation.chief_complaint:
        appointment_reason = consultation.chief_complaint
    if not appointment_reason and patient:
        from app.models.outpatient import Appointment as Apt
        latest_apt = db.query(Apt).filter(
            Apt.patient_id == patient.id
        ).order_by(Apt.created_at.desc()).first()
        if latest_apt and latest_apt.reason:
            appointment_reason = latest_apt.reason

    # Format prescription data for PDF (filled layout — never blank_mode)
    display_notes = prescription.notes
    if display_notes and display_notes.startswith(BLANK_APT_NOTES_PREFIX):
        display_notes = None

    prescription_pdf_data = {
        "prescription_number": prescription.prescription_id,
        "prescription_date": prescription.prescription_date.isoformat(),
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "Unknown",
        "patient_age": patient_age,
        "patient_age_display": patient_age_display,
        "patient_gender": patient_gender,
        "patient_phone": patient_phone,
        "patient_blood_group": patient_blood_group,
        "mrn": (patient.mrn or "") if patient else "",
        "village": (patient.village or "") if patient else "",
        "mandal": (patient.mandal or "") if patient else "",
        "district": (patient.district or "") if patient else "",
        "patient_id_display": prescription.patient_id,
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "Unknown",
        "doctor_specialization": doctor.specialization if doctor and hasattr(doctor, 'specialization') else '',
        "doctor_registration_number": doctor.license_number if doctor and hasattr(doctor, 'license_number') else '',
        "appointment_reason": appointment_reason,
        "status": prescription.status,
        "notes": display_notes,
        "diagnosis": prescription.diagnosis,
        "vitals": vitals_data,
        "consultation": consultation_data,
        "lab_tests": lab_tests_ordered,
        "items": [
            {
                "medicine_name": med.get("name", ""),
                "dosage": med.get("dosage", ""),
                "duration": med.get("duration", ""),
                "instructions": med.get("instructions", "") or "As directed",
                "frequency_schedule": med.get("frequency_schedule", "1-0-0"),
                "food_timing": med.get("food_timing", "after_food")
            }
            for med in medicines
        ]
    }

    hospital = db.query(Hospital).filter(Hospital.id == current_user.hospital_id).first()
    hospital_info = {
        "name": hospital.name if hospital else "General Hospital",
        "address": hospital.address if hospital else "Hospital Address",
        "phone": hospital.phone if hospital else "+1-000-000-0000",
        "email": hospital.email if hospital else "info@hospital.com",
        "logo_url": hospital.logo_url if hospital and hasattr(hospital, 'logo_url') else ''
    }

    # Generate PDF
    pdf_buffer = pdf_service.generate_prescription_pdf(prescription_pdf_data, hospital_info, **pdf_gen_kwargs(db, current_user.hospital_id, 'prescription'))

    # Create filename
    filename = f"prescription_{prescription.prescription_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    # Return PDF as inline response (bytes — reliable in Windows bundled build)
    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )

@router.delete("/{prescription_id}")
async def cancel_prescription(
    prescription_id: str,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "delete")),
    db: Session = Depends(get_db)
):
    """Cancel a prescription (soft delete)"""
    prescription = db.query(SimplePrescription).filter(
        SimplePrescription.prescription_id == prescription_id,
        SimplePrescription.hospital_id == current_user.hospital_id
    ).first()
    
    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )
    
    # Only the prescribing doctor or admin can cancel
    if (prescription.doctor_id != current_user.id and
        not any(r in current_user.role_names for r in ['super_admin', 'hospital_admin'])):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the prescribing doctor can cancel this prescription"
        )
    
    prescription.status = "cancelled"
    patient = db.query(Patient).filter(
        Patient.patient_id == prescription.patient_id,
        Patient.hospital_id == current_user.hospital_id,
    ).first()
    if patient:
        _sync_to_pharmacy_prescription(db, prescription, patient)
    db.commit()
    
    return {"message": "Prescription cancelled successfully"}

def build_prescription_response(prescription: SimplePrescription, db: Session) -> PrescriptionResponse:
    """Build prescription response with related data"""
    patient = db.query(Patient).filter(Patient.patient_id == prescription.patient_id).first()
    doctor = db.query(User).filter(User.id == prescription.doctor_id).first()
    
    return PrescriptionResponse(
        id=prescription.id,
        prescription_id=prescription.prescription_id,
        patient_id=prescription.patient_id,
        patient_name=f"{patient.first_name} {patient.last_name}" if patient else "Unknown",
        doctor_id=prescription.doctor_id,
        doctor_name=f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "Unknown",
        consultation_id=prescription.consultation_id,
        appointment_id=prescription.appointment_id,
        admission_id=getattr(prescription, 'admission_id', None),
        medicines=prescription.medicines,
        diagnosis=prescription.diagnosis,
        notes=prescription.notes,
        status=prescription.status,
        prescription_date=prescription.prescription_date,
        created_at=prescription.created_at
    )