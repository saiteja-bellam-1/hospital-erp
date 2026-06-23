from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from config.database import get_db
from app.models.pharmacy import Prescription, PrescriptionItem, Medicine, MedicineCategory
from app.models.ehr import Consultation
from app.models.inpatient import Admission
from app.models.patient import Patient
from app.models.user import User
from app.utils.auth import Modules, UserRoles
from app.utils.dependencies import get_current_user, user_has_feature_permission
from app.utils.pharmacy_pricing import medicine_sale_rate, is_free_text_medicine
from app.utils.prescription_schedule import (
    build_dosage_instruction,
    parse_duration_days,
    schedule_to_mar,
)

router = APIRouter()


class PrescriptionItemCreate(BaseModel):
    medicine_id: Optional[int] = None
    medicine_name: Optional[str] = None
    quantity_prescribed: int = Field(..., gt=0)
    dosage: str
    duration: str
    frequency_schedule: Optional[str] = Field("1-0-0", description="Morning-Afternoon-Night e.g. 1-0-1")
    food_timing: Optional[str] = Field("after_food", description="before_food, after_food, with_food, on_empty_stomach, anytime")
    instructions: Optional[str] = None


class PrescriptionItemResponse(BaseModel):
    id: int
    medicine_id: int
    medicine_name: str
    medicine_strength: str
    dosage_form: str
    quantity_prescribed: int
    quantity_dispensed: int
    dosage: str
    duration: str
    instructions: Optional[str]
    unit_price: float
    total_price: float
    status: str

    class Config:
        from_attributes = True


class PrescriptionCreate(BaseModel):
    patient_id: int
    consultation_id: Optional[int] = None
    admission_id: Optional[int] = None
    notes: Optional[str] = None
    items: List[PrescriptionItemCreate]


class PrescriptionUpdate(BaseModel):
    notes: Optional[str] = None
    status: Optional[str] = None


class PrescriptionResponse(BaseModel):
    id: int
    prescription_number: str
    patient_id: int
    patient_name: str
    doctor_id: int
    doctor_name: str
    consultation_id: Optional[int]
    admission_id: Optional[int] = None
    prescription_date: datetime
    status: str
    notes: Optional[str]
    total_amount: float
    dispensed_by_id: Optional[int]
    dispensed_date: Optional[datetime]
    items: List[PrescriptionItemResponse]

    class Config:
        from_attributes = True


def _assert_can_create_prescription(
    current_user: User,
    db: Session,
    admission_id: Optional[int],
) -> None:
    """Doctors/admins for OP; doctors/nurses with inpatient:prescribe_medications for IP."""
    user_roles = set(current_user.role_names)
    if user_roles & {UserRoles.SUPER_ADMIN, UserRoles.HOSPITAL_ADMIN}:
        return
    if admission_id is not None:
        if user_has_feature_permission(db, current_user, Modules.INPATIENT, "prescribe_medications"):
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission required: inpatient.prescribe_medications",
        )
    if UserRoles.DOCTOR in user_roles:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Doctor access required for outpatient prescriptions",
    )


def _get_or_create_general_category(db: Session, hospital_id: int) -> MedicineCategory:
    general_category = db.query(MedicineCategory).filter(
        MedicineCategory.name == "General",
        MedicineCategory.hospital_id == hospital_id,
    ).first()
    if not general_category:
        general_category = MedicineCategory(
            name="General",
            description="General medicines without specific category",
            hospital_id=hospital_id,
        )
        db.add(general_category)
        db.flush()
    return general_category


def _resolve_medicine_for_item(
    db: Session,
    current_user: User,
    item_data: PrescriptionItemCreate,
) -> tuple[int, float, str, str, str]:
    if item_data.medicine_id:
        medicine = db.query(Medicine).filter(
            Medicine.id == item_data.medicine_id,
            Medicine.hospital_id == current_user.hospital_id,
            Medicine.is_active == True,  # noqa: E712
        ).first()
        if not medicine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Medicine with ID {item_data.medicine_id} not found",
            )
        unit_price = medicine_sale_rate(medicine)
        return (
            medicine.id,
            unit_price,
            medicine.name,
            medicine.strength or "",
            medicine.dosage_form or "",
        )

    if item_data.medicine_name:
        name = item_data.medicine_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Medicine name cannot be empty")
        existing = db.query(Medicine).filter(
            Medicine.name == name,
            Medicine.hospital_id == current_user.hospital_id,
        ).first()
        if existing:
            unit_price = medicine_sale_rate(existing)
            return (
                existing.id,
                unit_price,
                existing.name,
                existing.strength or "",
                existing.dosage_form or "",
            )

        import uuid
        general_category = _get_or_create_general_category(db, current_user.hospital_id)
        new_medicine = Medicine(
            medicine_code=f"TXT-{uuid.uuid4().hex[:8].upper()}",
            name=name,
            category_id=general_category.id,
            unit_price=0.0,
            rate_a=0.0,
            hospital_id=current_user.hospital_id,
            requires_prescription=True,
            is_hidden=True,
        )
        db.add(new_medicine)
        db.flush()
        return (new_medicine.id, 0.0, new_medicine.name, "", "")

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Either medicine_id or medicine_name must be provided",
    )


def require_pharmacy_access(current_user: User = Depends(get_current_user)):
    if not any(r in current_user.role_names for r in ['pharmacist', 'pharmacy_admin', 'super_admin', 'hospital_admin']):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pharmacy access required",
        )
    return current_user


def generate_prescription_number(db: Session) -> str:
    import uuid
    import time
    timestamp = int(time.time())
    unique_id = str(uuid.uuid4()).split('-')[0].upper()
    return f"RX{timestamp}{unique_id}"


@router.post("/", response_model=PrescriptionResponse)
async def create_prescription(
    prescription_data: PrescriptionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a prescription (outpatient doctor or inpatient prescriber)."""
    _assert_can_create_prescription(current_user, db, prescription_data.admission_id)

    patient = db.query(Patient).filter(
        Patient.id == prescription_data.patient_id,
        Patient.hospital_id == current_user.hospital_id,
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    if prescription_data.admission_id:
        admission = db.query(Admission).filter(
            Admission.id == prescription_data.admission_id,
            Admission.patient_id == patient.id,
        ).first()
        if not admission:
            raise HTTPException(status_code=404, detail="Admission not found for this patient")
        if admission.status != "admitted":
            raise HTTPException(status_code=400, detail="Admission is not active")

    if prescription_data.consultation_id:
        consultation = db.query(Consultation).filter(
            Consultation.id == prescription_data.consultation_id,
        ).first()
        if not consultation:
            raise HTTPException(status_code=404, detail="Consultation not found")

    prescription = Prescription(
        prescription_number=generate_prescription_number(db),
        patient_id=prescription_data.patient_id,
        doctor_id=current_user.id,
        consultation_id=prescription_data.consultation_id,
        admission_id=prescription_data.admission_id,
        notes=prescription_data.notes,
        status="pending",
    )
    db.add(prescription)
    db.flush()

    total_amount = 0.0
    for item_data in prescription_data.items:
        medicine_id, unit_price, _, _, _ = _resolve_medicine_for_item(db, current_user, item_data)
        item_total = unit_price * item_data.quantity_prescribed
        total_amount += item_total
        freq_code, schedule_times = schedule_to_mar(item_data.frequency_schedule)
        dosage_line = build_dosage_instruction(
            item_data.dosage,
            item_data.frequency_schedule,
            item_data.food_timing,
        )
        db.add(PrescriptionItem(
            prescription_id=prescription.id,
            medicine_id=medicine_id,
            quantity_prescribed=item_data.quantity_prescribed,
            dosage=dosage_line,
            duration=item_data.duration,
            instructions=item_data.instructions,
            unit_price=unit_price,
            total_price=item_total,
            status="pending",
            frequency=freq_code,
            schedule_times=schedule_times,
            duration_days=parse_duration_days(item_data.duration),
        ))

    prescription.total_amount = total_amount
    db.commit()
    db.refresh(prescription)
    return build_prescription_response(prescription, db)


@router.get("/", response_model=List[PrescriptionResponse])
async def get_prescriptions(
    patient_id: Optional[int] = None,
    admission_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Prescription)
    if patient_id:
        query = query.filter(Prescription.patient_id == patient_id)
    if admission_id:
        query = query.filter(Prescription.admission_id == admission_id)
    if status:
        query = query.filter(Prescription.status == status)
    if current_user.has_role('doctor') and not admission_id:
        query = query.filter(Prescription.doctor_id == current_user.id)
    prescriptions = query.offset(offset).limit(limit).all()
    return [build_prescription_response(p, db) for p in prescriptions]


@router.get("/{prescription_id}", response_model=PrescriptionResponse)
async def get_prescription(
    prescription_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prescription = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    if current_user.has_role('doctor') and prescription.doctor_id != current_user.id:
        if not prescription.admission_id:
            raise HTTPException(status_code=403, detail="Access denied to this prescription")
    return build_prescription_response(prescription, db)


@router.put("/{prescription_id}", response_model=PrescriptionResponse)
async def update_prescription(
    prescription_id: int,
    prescription_data: PrescriptionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prescription = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    if prescription.admission_id:
        _assert_can_create_prescription(current_user, db, prescription.admission_id)
    elif not current_user.has_role('doctor') and not current_user.has_role('super_admin'):
        raise HTTPException(status_code=403, detail="Doctor access required")
    if prescription.doctor_id != current_user.id and not current_user.has_role('super_admin'):
        raise HTTPException(status_code=403, detail="Only the prescribing clinician can update this prescription")
    if prescription_data.notes is not None:
        prescription.notes = prescription_data.notes
    if prescription_data.status is not None:
        prescription.status = prescription_data.status
    db.commit()
    db.refresh(prescription)
    return build_prescription_response(prescription, db)


@router.post("/{prescription_id}/dispense")
async def dispense_prescription(
    prescription_id: int,
    current_user: User = Depends(require_pharmacy_access),
    db: Session = Depends(get_db),
):
    """Legacy simple dispense — prefer /api/pharmacy/prescriptions/{id}/dispense."""
    prescription = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    if prescription.status != "pending":
        raise HTTPException(status_code=400, detail="Prescription is not pending")
    prescription.status = "dispensed"
    prescription.dispensed_by_id = current_user.id
    prescription.dispensed_date = datetime.now()
    for item in prescription.items:
        item.quantity_dispensed = item.quantity_prescribed
        item.status = "dispensed"
    db.commit()
    return {"message": "Prescription dispensed successfully"}


def build_prescription_response(prescription: Prescription, db: Session) -> dict:
    patient = db.query(Patient).filter(Patient.id == prescription.patient_id).first()
    doctor = db.query(User).filter(User.id == prescription.doctor_id).first()
    items = []
    for item in prescription.items:
        medicine = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
        items.append(PrescriptionItemResponse(
            id=item.id,
            medicine_id=item.medicine_id,
            medicine_name=medicine.name if medicine else "Unknown",
            medicine_strength=medicine.strength or "" if medicine else "",
            dosage_form=medicine.dosage_form or "" if medicine else "",
            quantity_prescribed=item.quantity_prescribed,
            quantity_dispensed=item.quantity_dispensed,
            dosage=item.dosage,
            duration=item.duration,
            instructions=item.instructions,
            unit_price=item.unit_price,
            total_price=item.total_price,
            status=item.status,
        ))
    return PrescriptionResponse(
        id=prescription.id,
        prescription_number=prescription.prescription_number,
        patient_id=prescription.patient_id,
        patient_name=f"{patient.first_name} {patient.last_name}" if patient else "Unknown",
        doctor_id=prescription.doctor_id,
        doctor_name=f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "Unknown",
        consultation_id=prescription.consultation_id,
        admission_id=prescription.admission_id,
        prescription_date=prescription.prescription_date,
        status=prescription.status,
        notes=prescription.notes,
        total_amount=prescription.total_amount,
        dispensed_by_id=prescription.dispensed_by_id,
        dispensed_date=prescription.dispensed_date,
        items=items,
    )
