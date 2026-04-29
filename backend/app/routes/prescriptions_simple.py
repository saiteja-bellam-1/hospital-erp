from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import uuid

from config.database import get_db
from app.models.prescriptions_simple import SimplePrescription
from app.models.patient import Patient
from app.models.user import User
from app.models.ehr import Consultation
from app.models.hospital import Hospital
from app.utils.dependencies import get_current_user, require_permission
from app.utils.auth import Modules
from app.utils.pdf_service import pdf_service

router = APIRouter()

# Pydantic models for API
class MedicineItem(BaseModel):
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
    admission_id: Optional[int] = Field(None, description="Inpatient admission ID if linked")
    medicines: List[MedicineItem] = Field(..., min_items=1, description="List of medicines")
    diagnosis: Optional[str] = Field(None, description="Diagnosis")
    notes: Optional[str] = Field(None, description="Additional notes")

class PrescriptionUpdate(BaseModel):
    medicines: Optional[List[MedicineItem]] = None
    diagnosis: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(active|cancelled|completed)$")

class PrescriptionResponse(BaseModel):
    id: int
    prescription_id: str
    patient_id: str
    patient_name: str
    doctor_id: int
    doctor_name: str
    consultation_id: Optional[int]
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
    """Generate unique prescription ID"""
    timestamp = datetime.now().strftime('%Y%m%d')
    unique_id = str(uuid.uuid4()).split('-')[0].upper()
    return f"RX-{timestamp}-{unique_id}"

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
    
    # Convert medicines to JSON format
    medicines_json = [
        {
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
    
    # Create prescription
    prescription = SimplePrescription(
        prescription_id=generate_prescription_id(),
        patient_id=prescription_data.patient_id,
        doctor_id=current_user.id,
        consultation_id=prescription_data.consultation_id,
        admission_id=prescription_data.admission_id,
        medicines=medicines_json,
        diagnosis=prescription_data.diagnosis,
        notes=prescription_data.notes,
        hospital_id=current_user.hospital_id,
        status="active"
    )
    
    db.add(prescription)
    db.commit()
    db.refresh(prescription)
    
    return build_prescription_response(prescription, db)

@router.get("/", response_model=List[PrescriptionResponse])
async def get_prescriptions(
    patient_id: Optional[str] = None,
    doctor_id: Optional[int] = None,
    consultation_id: Optional[int] = None,
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
        
    if prescription_data.diagnosis is not None:
        prescription.diagnosis = prescription_data.diagnosis
        
    if prescription_data.notes is not None:
        prescription.notes = prescription_data.notes
        
    if prescription_data.status is not None:
        prescription.status = prescription_data.status
    
    db.commit()
    db.refresh(prescription)
    
    return build_prescription_response(prescription, db)

@router.get("/{prescription_id}/download")
async def download_prescription_pdf(
    prescription_id: str,
    include_header: bool = True,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Download prescription as PDF with vitals, findings, medicines, tests, follow-up"""
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

    # Get patient and doctor info
    patient = db.query(Patient).filter(Patient.patient_id == prescription.patient_id).first()
    doctor = db.query(User).filter(User.id == prescription.doctor_id).first()

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
    patient_gender = ''
    patient_phone = ''
    patient_blood_group = ''
    if patient:
        patient_phone = patient.primary_phone or ''
        patient_gender = (patient.gender or '').capitalize()
        patient_blood_group = patient.blood_group or ''
        if patient.date_of_birth:
            from datetime import date
            today = date.today()
            patient_age = today.year - patient.date_of_birth.year - (
                (today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day)
            )
        elif patient.age is not None:
            patient_age = patient.age

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

    # Format prescription data for PDF
    prescription_pdf_data = {
        "prescription_number": prescription.prescription_id,
        "prescription_date": prescription.prescription_date.isoformat(),
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "Unknown",
        "patient_age": patient_age,
        "patient_gender": patient_gender,
        "patient_phone": patient_phone,
        "patient_blood_group": patient_blood_group,
        "patient_id_display": prescription.patient_id,
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "Unknown",
        "doctor_specialization": doctor.specialization if doctor and hasattr(doctor, 'specialization') else '',
        "doctor_registration_number": doctor.license_number if doctor and hasattr(doctor, 'license_number') else '',
        "appointment_reason": appointment_reason,
        "status": prescription.status,
        "notes": prescription.notes,
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
            for med in prescription.medicines
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
    pdf_buffer = pdf_service.generate_prescription_pdf(prescription_pdf_data, hospital_info, include_header)

    # Create filename
    filename = f"prescription_{prescription.prescription_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    # Return PDF as streaming response
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
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
        medicines=prescription.medicines,
        diagnosis=prescription.diagnosis,
        notes=prescription.notes,
        status=prescription.status,
        prescription_date=prescription.prescription_date,
        created_at=prescription.created_at
    )