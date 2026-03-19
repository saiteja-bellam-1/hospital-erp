from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, date

from config.database import get_db
from app.models.pharmacy import Prescription, PrescriptionItem, Medicine, MedicineCategory
from app.models.ehr import Consultation
from app.models.patient import Patient
from app.models.user import User
from app.utils.dependencies import get_current_user

router = APIRouter()

class PrescriptionItemCreate(BaseModel):
    medicine_id: Optional[int] = None  # Optional for backward compatibility
    medicine_name: Optional[str] = None  # New field for text-based medicine names
    quantity_prescribed: int = Field(..., gt=0)
    dosage: str  # e.g., "1 tablet twice daily"
    duration: str  # e.g., "7 days"
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
    prescription_date: datetime
    status: str
    notes: Optional[str]
    total_amount: float
    dispensed_by_id: Optional[int]
    dispensed_date: Optional[datetime]
    items: List[PrescriptionItemResponse]
    
    class Config:
        from_attributes = True

def require_doctor_access(current_user: User = Depends(get_current_user)):
    """Dependency to ensure only doctors can create prescriptions"""
    if not any(r in current_user.role_names for r in ['doctor', 'super_admin']):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Doctor access required"
        )
    return current_user

def require_pharmacy_access(current_user: User = Depends(get_current_user)):
    """Dependency for pharmacy staff to dispense medications"""
    if not any(r in current_user.role_names for r in ['pharmacist', 'pharmacy_admin', 'super_admin', 'hospital_admin']):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Pharmacy access required"
        )
    return current_user

def generate_prescription_number(db: Session) -> str:
    """Generate unique prescription number"""
    import uuid
    import time
    timestamp = int(time.time())
    unique_id = str(uuid.uuid4()).split('-')[0].upper()
    return f"RX{timestamp}{unique_id}"

@router.post("/", response_model=PrescriptionResponse)
async def create_prescription(
    prescription_data: PrescriptionCreate,
    current_user: User = Depends(require_doctor_access),
    db: Session = Depends(get_db)
):
    """Create a new prescription"""
    # Verify patient exists
    patient = db.query(Patient).filter(Patient.id == prescription_data.patient_id).first()
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found"
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
    
    # Create prescription
    prescription = Prescription(
        prescription_number=generate_prescription_number(db),
        patient_id=prescription_data.patient_id,
        doctor_id=current_user.id,
        consultation_id=prescription_data.consultation_id,
        notes=prescription_data.notes,
        status="pending"
    )
    
    db.add(prescription)
    db.flush()  # Get the prescription ID
    
    total_amount = 0.0
    prescription_items = []
    
    # Create prescription items
    for item_data in prescription_data.items:
        medicine_id = None
        unit_price = 0.0
        medicine_name = ""
        medicine_strength = ""
        dosage_form = ""
        
        # Handle both medicine_id (existing) and medicine_name (new) approaches
        if item_data.medicine_id:
            # Traditional approach - look up medicine in inventory
            medicine = db.query(Medicine).filter(Medicine.id == item_data.medicine_id).first()
            if not medicine:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Medicine with ID {item_data.medicine_id} not found"
                )
            medicine_id = medicine.id
            unit_price = medicine.unit_price
            medicine_name = medicine.name
            medicine_strength = medicine.strength
            dosage_form = medicine.dosage_form
        elif item_data.medicine_name:
            # Text-based approach - create or find a generic medicine record
            # Look for existing medicine with this name, or create a new one
            existing_medicine = db.query(Medicine).filter(
                Medicine.name == item_data.medicine_name,
                Medicine.hospital_id == current_user.hospital_id
            ).first()
            
            if existing_medicine:
                medicine_id = existing_medicine.id
                unit_price = existing_medicine.unit_price
                medicine_name = existing_medicine.name
                medicine_strength = existing_medicine.strength
                dosage_form = existing_medicine.dosage_form
            else:
                # Create a new medicine record for this text-based entry
                # First, get or create a "General" category
                general_category = db.query(MedicineCategory).filter(
                    MedicineCategory.name == "General",
                    MedicineCategory.hospital_id == current_user.hospital_id
                ).first()
                
                if not general_category:
                    general_category = MedicineCategory(
                        name="General",
                        description="General medicines without specific category",
                        hospital_id=current_user.hospital_id
                    )
                    db.add(general_category)
                    db.flush()
                
                # Create the medicine record
                import uuid
                new_medicine = Medicine(
                    medicine_code=f"TXT-{uuid.uuid4().hex[:8].upper()}",
                    name=item_data.medicine_name,
                    category_id=general_category.id,
                    unit_price=0.0,  # No pricing for text-based entries
                    hospital_id=current_user.hospital_id,
                    requires_prescription=True
                )
                db.add(new_medicine)
                db.flush()
                
                medicine_id = new_medicine.id
                unit_price = 0.0
                medicine_name = new_medicine.name
                medicine_strength = ""
                dosage_form = ""
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either medicine_id or medicine_name must be provided"
            )
        
        # Calculate total price
        item_total = unit_price * item_data.quantity_prescribed
        total_amount += item_total
        
        prescription_item = PrescriptionItem(
            prescription_id=prescription.id,
            medicine_id=medicine_id,  # Will always have a value now (either existing or newly created)
            quantity_prescribed=item_data.quantity_prescribed,
            dosage=item_data.dosage,
            duration=item_data.duration,
            instructions=item_data.instructions,
            unit_price=unit_price,
            total_price=item_total,
            status="pending"
        )
        
        db.add(prescription_item)
        prescription_items.append(prescription_item)
    
    # Update total amount
    prescription.total_amount = total_amount
    
    db.commit()
    db.refresh(prescription)
    
    # Build response
    return build_prescription_response(prescription, db)

@router.get("/", response_model=List[PrescriptionResponse])
async def get_prescriptions(
    patient_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get prescriptions with optional filters"""
    query = db.query(Prescription)
    
    # Filter by patient if requested
    if patient_id:
        query = query.filter(Prescription.patient_id == patient_id)
    
    # Filter by status if requested
    if status:
        query = query.filter(Prescription.status == status)
    
    # For doctors, only show their own prescriptions
    if current_user.has_role('doctor'):
        query = query.filter(Prescription.doctor_id == current_user.id)
    
    prescriptions = query.offset(offset).limit(limit).all()
    
    return [build_prescription_response(prescription, db) for prescription in prescriptions]

@router.get("/{prescription_id}", response_model=PrescriptionResponse)
async def get_prescription(
    prescription_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific prescription"""
    prescription = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )
    
    # Check access permissions
    if (current_user.has_role('doctor') and prescription.doctor_id != current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this prescription"
        )
    
    return build_prescription_response(prescription, db)

@router.put("/{prescription_id}", response_model=PrescriptionResponse)
async def update_prescription(
    prescription_id: int,
    prescription_data: PrescriptionUpdate,
    current_user: User = Depends(require_doctor_access),
    db: Session = Depends(get_db)
):
    """Update a prescription (doctors only)"""
    prescription = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )
    
    # Only the prescribing doctor can update
    if prescription.doctor_id != current_user.id and not current_user.has_role('super_admin'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the prescribing doctor can update this prescription"
        )
    
    # Update fields
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
    db: Session = Depends(get_db)
):
    """Dispense a prescription (pharmacy staff only)"""
    prescription = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not prescription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Prescription not found"
        )
    
    if prescription.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prescription is not pending"
        )
    
    # Mark as dispensed
    prescription.status = "dispensed"
    prescription.dispensed_by_id = current_user.id
    prescription.dispensed_date = datetime.now()
    
    # Update all items as dispensed
    for item in prescription.items:
        item.quantity_dispensed = item.quantity_prescribed
        item.status = "dispensed"
    
    db.commit()
    
    return {"message": "Prescription dispensed successfully"}

def build_prescription_response(prescription: Prescription, db: Session) -> dict:
    """Build prescription response with all related data"""
    patient = db.query(Patient).filter(Patient.id == prescription.patient_id).first()
    doctor = db.query(User).filter(User.id == prescription.doctor_id).first()
    
    items = []
    for item in prescription.items:
        medicine = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
        items.append(PrescriptionItemResponse(
            id=item.id,
            medicine_id=item.medicine_id,
            medicine_name=medicine.name,
            medicine_strength=medicine.strength or "",
            dosage_form=medicine.dosage_form or "",
            quantity_prescribed=item.quantity_prescribed,
            quantity_dispensed=item.quantity_dispensed,
            dosage=item.dosage,
            duration=item.duration,
            instructions=item.instructions,
            unit_price=item.unit_price,
            total_price=item.total_price,
            status=item.status
        ))
    
    return PrescriptionResponse(
        id=prescription.id,
        prescription_number=prescription.prescription_number,
        patient_id=prescription.patient_id,
        patient_name=f"{patient.first_name} {patient.last_name}",
        doctor_id=prescription.doctor_id,
        doctor_name=f"Dr. {doctor.first_name} {doctor.last_name}",
        consultation_id=prescription.consultation_id,
        prescription_date=prescription.prescription_date,
        status=prescription.status,
        notes=prescription.notes,
        total_amount=prescription.total_amount,
        dispensed_by_id=prescription.dispensed_by_id,
        dispensed_date=prescription.dispensed_date,
        items=items
    )