from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import uuid
import re

from config.database import get_db
from app.models.user import User
from app.models.ehr import Consultation
from app.models.lab import PatientLabOrder, LabTest, LabTestCategory
from app.models.patient import Patient
from app.models.prescriptions_simple import SimplePrescription
from app.models.billing import Bill, BillItem, PaymentMethod, Payment
from app.utils.dependencies import get_current_user, require_permission
from app.utils.auth import Modules
from app.utils.pdf_service import pdf_service

router = APIRouter()

# --- Consultation CRUD ---

class ConsultationCreate(BaseModel):
    patient_id: int
    appointment_id: Optional[int] = None
    consultation_type: str = Field(default="outpatient", pattern="^(outpatient|inpatient|emergency|followup)$")
    chief_complaint: Optional[str] = None
    present_history: Optional[str] = None
    examination_findings: Optional[str] = None
    vital_signs: Optional[str] = None
    consultation_fee: float = 0.0
    notes: Optional[str] = None

class ConsultationUpdate(BaseModel):
    chief_complaint: Optional[str] = None
    present_history: Optional[str] = None
    examination_findings: Optional[str] = None
    vital_signs: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(ongoing|completed|cancelled)$")
    follow_up_date: Optional[str] = None

class ConsultationResponse(BaseModel):
    id: int
    consultation_number: str
    patient_id: int
    patient_name: Optional[str] = None
    doctor_id: int
    doctor_name: Optional[str] = None
    consultation_date: datetime
    consultation_type: str
    chief_complaint: Optional[str] = None
    present_history: Optional[str] = None
    examination_findings: Optional[str] = None
    vital_signs: Optional[str] = None
    status: str
    consultation_fee: float
    follow_up_date: Optional[datetime] = None
    notes: Optional[str] = None
    appointment_id: Optional[int] = None

    class Config:
        from_attributes = True

def _build_consultation_response(consultation: Consultation, db: Session) -> dict:
    patient = db.query(Patient).filter(Patient.id == consultation.patient_id).first()
    doctor = db.query(User).filter(User.id == consultation.doctor_id).first()
    return {
        "id": consultation.id,
        "consultation_number": consultation.consultation_number,
        "patient_id": consultation.patient_id,
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
        "doctor_id": consultation.doctor_id,
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else None,
        "consultation_date": consultation.consultation_date,
        "consultation_type": consultation.consultation_type,
        "chief_complaint": consultation.chief_complaint,
        "present_history": consultation.present_history,
        "examination_findings": consultation.examination_findings,
        "vital_signs": consultation.vital_signs,
        "status": consultation.status,
        "consultation_fee": consultation.consultation_fee or 0.0,
        "follow_up_date": consultation.follow_up_date,
        "notes": consultation.notes,
        "appointment_id": getattr(consultation, 'appointment_id', None),
    }

@router.post("/", response_model=ConsultationResponse)
async def create_consultation(
    data: ConsultationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new consultation record"""
    if current_user.role.name not in ['doctor', 'super_admin']:
        raise HTTPException(status_code=403, detail="Only doctors can create consultations")

    patient = db.query(Patient).filter(Patient.id == data.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    consultation_number = f"CONS{datetime.now().strftime('%Y%m%d%H%M%S')}{str(uuid.uuid4())[:4].upper()}"

    consultation = Consultation(
        consultation_number=consultation_number,
        patient_id=data.patient_id,
        doctor_id=current_user.id,
        appointment_id=data.appointment_id,
        consultation_type=data.consultation_type,
        chief_complaint=data.chief_complaint,
        present_history=data.present_history,
        examination_findings=data.examination_findings,
        vital_signs=data.vital_signs,
        consultation_fee=data.consultation_fee,
        notes=data.notes,
        status="ongoing"
    )
    db.add(consultation)
    db.commit()
    db.refresh(consultation)

    return _build_consultation_response(consultation, db)

@router.get("/doctor/me", response_model=List[ConsultationResponse])
async def get_my_consultations(
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get consultations for current doctor"""
    if current_user.role.name not in ['doctor', 'super_admin']:
        raise HTTPException(status_code=403, detail="Only doctors can access this")

    query = db.query(Consultation).filter(Consultation.doctor_id == current_user.id)
    if status:
        query = query.filter(Consultation.status == status)
    if date_from:
        query = query.filter(Consultation.consultation_date >= date_from)
    if date_to:
        query = query.filter(Consultation.consultation_date <= date_to + " 23:59:59")

    consultations = query.order_by(Consultation.consultation_date.desc()).limit(50).all()
    return [_build_consultation_response(c, db) for c in consultations]

@router.get("/patient/{patient_id}/history")
async def get_patient_consultation_history(
    patient_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all consultations for a patient (excluding vitals_recording)"""
    consultations = db.query(Consultation).filter(
        Consultation.patient_id == patient_id,
        Consultation.consultation_type != "vitals_recording"
    ).order_by(Consultation.consultation_date.desc()).limit(50).all()

    result = []
    for c in consultations:
        doctor = db.query(User).filter(User.id == c.doctor_id).first()
        # Get prescriptions linked to this consultation
        rx_list = db.query(SimplePrescription).filter(
            SimplePrescription.consultation_id == c.id
        ).all()
        prescriptions = []
        for rx in rx_list:
            prescriptions.append({
                "prescription_id": rx.prescription_id,
                "medicines": rx.medicines or [],
                "diagnosis": rx.diagnosis,
                "notes": rx.notes,
                "prescription_date": rx.prescription_date
            })

        # Parse vital signs
        vital_signs = None
        if c.vital_signs:
            try:
                import json
                vital_signs = json.loads(c.vital_signs)
            except Exception:
                vital_signs = None

        result.append({
            "id": c.id,
            "consultation_number": c.consultation_number,
            "consultation_date": c.consultation_date,
            "consultation_type": c.consultation_type,
            "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "Unknown",
            "doctor_specialization": doctor.specialization if doctor else None,
            "chief_complaint": c.chief_complaint,
            "present_history": c.present_history,
            "examination_findings": c.examination_findings,
            "vital_signs": vital_signs,
            "status": c.status,
            "notes": c.notes,
            "follow_up_date": c.follow_up_date,
            "prescriptions": prescriptions,
            "appointment_id": getattr(c, 'appointment_id', None),
        })

    return result

@router.get("/by-appointment/{appointment_id}", response_model=ConsultationResponse)
async def get_consultation_by_appointment(
    appointment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get consultation for a specific appointment"""
    consultation = db.query(Consultation).filter(
        Consultation.appointment_id == appointment_id,
        Consultation.consultation_type != "vitals_recording"
    ).order_by(Consultation.created_at.desc()).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="No consultation found for this appointment")
    return _build_consultation_response(consultation, db)

@router.get("/by-id/{consultation_id}", response_model=ConsultationResponse)
async def get_consultation(
    consultation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a specific consultation"""
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    return _build_consultation_response(consultation, db)

@router.put("/by-id/{consultation_id}", response_model=ConsultationResponse)
async def update_consultation(
    consultation_id: int,
    data: ConsultationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update consultation details"""
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    if consultation.doctor_id != current_user.id and current_user.role.name != 'super_admin':
        raise HTTPException(status_code=403, detail="Not authorized")

    if data.chief_complaint is not None:
        consultation.chief_complaint = data.chief_complaint
    if data.present_history is not None:
        consultation.present_history = data.present_history
    if data.examination_findings is not None:
        consultation.examination_findings = data.examination_findings
    if data.vital_signs is not None:
        consultation.vital_signs = data.vital_signs
    if data.notes is not None:
        consultation.notes = data.notes
    if data.status is not None:
        consultation.status = data.status
    if data.follow_up_date is not None:
        consultation.follow_up_date = datetime.fromisoformat(data.follow_up_date) if data.follow_up_date else None

    db.commit()
    db.refresh(consultation)
    return _build_consultation_response(consultation, db)

# --- Lab Orders (existing) ---

class LabOrderCreate(BaseModel):
    test_ids: List[int] = Field(..., description="List of lab test IDs to order")
    priority: str = Field(default="normal", pattern="^(normal|urgent|stat)$")
    notes: Optional[str] = None

class LabOrderResponse(BaseModel):
    id: int
    order_number: str
    test_id: int
    test_name: str
    test_code: str
    test_cost: float
    priority: str
    status: str
    notes: Optional[str]
    order_date: datetime
    
    class Config:
        from_attributes = True

class ConsultationLabOrdersResponse(BaseModel):
    consultation_id: int
    total_orders: int
    total_cost: float
    lab_orders: List[LabOrderResponse]

class TestRecommendation(BaseModel):
    test_id: int
    test_name: str
    test_code: str
    cost: float
    recommendation_reason: str
    confidence_score: float
    category_name: str

class TestRecommendationsResponse(BaseModel):
    consultation_id: int
    chief_complaint: str
    recommendations: List[TestRecommendation]
    total_recommended_cost: float

class BillItemResponse(BaseModel):
    item_type: str
    item_name: str
    item_code: Optional[str]
    quantity: int
    unit_price: float
    total_price: float
    discount_percentage: float

class ConsultationBillResponse(BaseModel):
    bill_id: int
    bill_number: str
    consultation_id: int
    patient_name: str
    doctor_name: str
    consultation_fee: float
    lab_orders_cost: float
    subtotal: float
    tax_amount: float
    discount_amount: float
    total_amount: float
    amount_paid: float
    balance_due: float
    status: str
    bill_date: datetime
    items: List[BillItemResponse]

class PaymentCreate(BaseModel):
    amount_paid: float = Field(..., gt=0, description="Amount to be paid")
    payment_method: str = Field(..., pattern="^(cash|card|upi|cheque|online|insurance)$")
    transaction_reference: Optional[str] = None
    notes: Optional[str] = None

class PaymentResponse(BaseModel):
    payment_id: int
    payment_number: str
    bill_id: int
    amount_paid: float
    payment_method: str
    payment_date: datetime
    transaction_reference: Optional[str]
    notes: Optional[str]
    receipt_number: str

class BillPrintResponse(BaseModel):
    bill: ConsultationBillResponse
    hospital_info: dict
    payment_receipt: Optional[PaymentResponse]

def generate_lab_order_number() -> str:
    """Generate unique lab order number"""
    return f"LAB-{str(uuid.uuid4())[:8].upper()}"

def generate_bill_number() -> str:
    """Generate unique bill number"""
    return f"BILL-{str(uuid.uuid4())[:8].upper()}"

def generate_payment_number() -> str:
    """Generate unique payment number"""
    return f"PAY-{str(uuid.uuid4())[:8].upper()}"

def get_bill_payment_status(bill: Bill, db: Session) -> tuple:
    """Calculate payment status and amounts for a bill"""
    total_payments = db.query(Payment).filter(Payment.bill_id == bill.id).all()
    amount_paid = sum(payment.amount_paid for payment in total_payments)
    balance_due = bill.total_amount - amount_paid
    
    # Update bill status based on payment
    if amount_paid >= bill.total_amount:
        status = "paid"
    elif amount_paid > 0:
        status = "partial"
    else:
        status = "pending"
    
    return amount_paid, balance_due, status

def create_consultation_bill(consultation_id: int, db: Session, current_user: User) -> Bill:
    """Create or update a bill for a consultation with lab orders"""
    
    # Get consultation details
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    
    # Check if bill already exists
    existing_bill = db.query(Bill).filter(
        Bill.bill_type == "consultation",
        Bill.reference_id == consultation_id
    ).first()
    
    if existing_bill:
        # Update existing bill
        bill = existing_bill
        # Clear existing items to recalculate
        db.query(BillItem).filter(BillItem.bill_id == bill.id).delete()
    else:
        # Create new bill
        bill = Bill(
            bill_number=generate_bill_number(),
            patient_id=consultation.patient_id,
            bill_type="consultation",
            reference_id=consultation_id,
            created_by_id=current_user.id,
            hospital_id=current_user.hospital_id,
            status="pending",
            subtotal=0.0,
            tax_amount=0.0,
            discount_amount=0.0,
            total_amount=0.0
        )
        db.add(bill)
        db.flush()  # Get bill ID
    
    # Add consultation fee item
    consultation_fee = consultation.consultation_fee or 0.0
    if consultation_fee > 0:
        consultation_item = BillItem(
            bill_id=bill.id,
            item_type="consultation",
            item_name="Doctor Consultation",
            item_code="CONSULT",
            quantity=1,
            unit_price=consultation_fee,
            total_price=consultation_fee
        )
        db.add(consultation_item)
    
    # Add lab order items
    lab_orders = db.query(PatientLabOrder, LabTest).join(
        LabTest, PatientLabOrder.test_id == LabTest.id
    ).filter(PatientLabOrder.consultation_id == consultation_id).all()
    
    for lab_order, lab_test in lab_orders:
        lab_item = BillItem(
            bill_id=bill.id,
            item_type="lab_test",
            item_name=lab_test.name,
            item_code=lab_test.test_code,
            quantity=1,
            unit_price=lab_test.cost,
            total_price=lab_test.cost
        )
        db.add(lab_item)
    
    # Calculate totals after all items are added
    db.flush()  # Ensure all items are saved
    bill_items = db.query(BillItem).filter(BillItem.bill_id == bill.id).all()
    subtotal = sum(item.total_price for item in bill_items)
    
    # For basic functionality, no tax or discount
    tax_amount = 0.0
    discount_amount = 0.0
    total_amount = subtotal - discount_amount + tax_amount
    
    bill.subtotal = subtotal
    bill.tax_amount = tax_amount
    bill.discount_amount = discount_amount
    bill.total_amount = total_amount
    
    db.commit()
    return bill

def get_test_recommendations(chief_complaint: str, present_history: str, patient_age: int = None) -> Dict[str, List[Dict]]:
    """
    Intelligent test recommendation engine based on symptoms and clinical presentation
    """
    
    # Normalize text for pattern matching
    complaint_text = (chief_complaint or "").lower()
    history_text = (present_history or "").lower()
    combined_text = f"{complaint_text} {history_text}"
    
    recommendations = {
        "high_priority": [],  # 90%+ confidence
        "medium_priority": [], # 70-89% confidence  
        "low_priority": []     # 50-69% confidence
    }
    
    # Define symptom-test mappings with confidence scores
    test_patterns = [
        # Fever and Infection patterns
        {
            "keywords": ["fever", "temperature", "chills", "infection", "sepsis"],
            "tests": [
                {"code": "CBC001", "reason": "Fever workup - check for infection/inflammation", "confidence": 0.95},
                {"code": "ESR001", "reason": "Inflammatory marker for fever evaluation", "confidence": 0.85}
            ]
        },
        
        # Diabetes and Metabolic patterns
        {
            "keywords": ["diabetes", "sugar", "glucose", "thirst", "urination", "weight loss", "fatigue"],
            "tests": [
                {"code": "FBS001", "reason": "Diabetes screening/monitoring", "confidence": 0.95},
                {"code": "RBS001", "reason": "Random glucose for immediate assessment", "confidence": 0.90},
                {"code": "HBA1C", "reason": "Long-term glucose control assessment", "confidence": 0.85}
            ]
        },
        
        # Cardiovascular patterns
        {
            "keywords": ["chest pain", "heart", "cardiac", "cholesterol", "hypertension", "bp", "blood pressure"],
            "tests": [
                {"code": "LIPID001", "reason": "Cardiovascular risk assessment", "confidence": 0.85},
                {"code": "CBC001", "reason": "General health screening for cardiac workup", "confidence": 0.70}
            ]
        },
        
        # General screening patterns
        {
            "keywords": ["checkup", "screening", "routine", "general", "health"],
            "tests": [
                {"code": "CBC001", "reason": "Routine health screening", "confidence": 0.80},
                {"code": "FBS001", "reason": "Diabetes screening", "confidence": 0.75},
                {"code": "LIPID001", "reason": "Cardiovascular screening", "confidence": 0.70}
            ]
        },
        
        # Fatigue and weakness patterns
        {
            "keywords": ["tired", "fatigue", "weakness", "energy", "exhausted"],
            "tests": [
                {"code": "CBC001", "reason": "Anemia and blood disorder screening", "confidence": 0.85},
                {"code": "FBS001", "reason": "Rule out diabetes as cause of fatigue", "confidence": 0.75}
            ]
        }
    ]
    
    # Score each test based on keyword matches
    test_scores = {}
    
    for pattern in test_patterns:
        # Check if any keywords match
        keyword_matches = sum(1 for keyword in pattern["keywords"] if keyword in combined_text)
        
        if keyword_matches > 0:
            # Calculate match strength (more keywords = higher relevance)
            match_strength = min(keyword_matches / len(pattern["keywords"]), 1.0)
            
            for test_info in pattern["tests"]:
                test_code = test_info["code"]
                base_confidence = test_info["confidence"]
                adjusted_confidence = base_confidence * match_strength
                
                if test_code not in test_scores:
                    test_scores[test_code] = {
                        "confidence": adjusted_confidence,
                        "reason": test_info["reason"],
                        "match_count": 1
                    }
                else:
                    # If test appears in multiple patterns, boost confidence
                    existing = test_scores[test_code]
                    existing["confidence"] = min((existing["confidence"] + adjusted_confidence) / 2 * 1.2, 1.0)
                    existing["match_count"] += 1
                    if existing["match_count"] > 1:
                        existing["reason"] += f" (Multiple indications)"
    
    return test_scores

@router.post("/{consultation_id}/lab-orders", response_model=List[LabOrderResponse])
async def create_consultation_lab_orders(
    consultation_id: int,
    lab_order_data: LabOrderCreate,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Create lab orders for a consultation"""
    
    # Verify consultation exists and user has access
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    
    # Verify patient belongs to same hospital
    patient = db.query(Patient).filter(Patient.id == consultation.patient_id).first()
    if not patient or patient.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    created_orders = []
    
    for test_id in lab_order_data.test_ids:
        # Verify test exists and is active
        lab_test = db.query(LabTest).filter(
            LabTest.id == test_id,
            LabTest.is_active == True,
            LabTest.hospital_id == current_user.hospital_id
        ).first()
        
        if not lab_test:
            raise HTTPException(status_code=404, detail=f"Lab test {test_id} not found")
        
        # Create lab order
        lab_order = PatientLabOrder(
            order_number=generate_lab_order_number(),
            patient_id=consultation.patient_id,
            test_id=test_id,
            doctor_id=consultation.doctor_id,
            consultation_id=consultation_id,
            priority=lab_order_data.priority,
            notes=lab_order_data.notes,
            status="ordered",
            amount=lab_test.cost or 0.0,
            payment_status="pending"
        )
        
        db.add(lab_order)
        db.flush()  # Get the ID without committing
        
        # Create response object
        order_response = LabOrderResponse(
            id=lab_order.id,
            order_number=lab_order.order_number,
            test_id=lab_test.id,
            test_name=lab_test.name,
            test_code=lab_test.test_code,
            test_cost=lab_test.cost,
            priority=lab_order.priority,
            status=lab_order.status,
            notes=lab_order.notes,
            order_date=lab_order.order_date
        )
        
        created_orders.append(order_response)
    
    db.commit()
    return created_orders

@router.get("/{consultation_id}/lab-orders", response_model=ConsultationLabOrdersResponse)
async def get_consultation_lab_orders(
    consultation_id: int,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get all lab orders for a consultation"""
    
    # Verify consultation exists and user has access
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    
    # Verify patient belongs to same hospital
    patient = db.query(Patient).filter(Patient.id == consultation.patient_id).first()
    if not patient or patient.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get lab orders with test details
    lab_orders_query = db.query(PatientLabOrder, LabTest).join(
        LabTest, PatientLabOrder.test_id == LabTest.id
    ).filter(PatientLabOrder.consultation_id == consultation_id)
    
    lab_orders_data = lab_orders_query.all()
    
    lab_orders = []
    total_cost = 0.0
    
    for lab_order, lab_test in lab_orders_data:
        order_response = LabOrderResponse(
            id=lab_order.id,
            order_number=lab_order.order_number,
            test_id=lab_test.id,
            test_name=lab_test.name,
            test_code=lab_test.test_code,
            test_cost=lab_test.cost,
            priority=lab_order.priority,
            status=lab_order.status,
            notes=lab_order.notes,
            order_date=lab_order.order_date
        )
        lab_orders.append(order_response)
        total_cost += lab_test.cost
    
    return ConsultationLabOrdersResponse(
        consultation_id=consultation_id,
        total_orders=len(lab_orders),
        total_cost=total_cost,
        lab_orders=lab_orders
    )

class LabOrderStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(ordered|collected|processing|completed|cancelled)$")

@router.put("/{consultation_id}/lab-orders/{order_id}/status")
async def update_lab_order_status(
    consultation_id: int,
    order_id: int,
    status_update: LabOrderStatusUpdate,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Update lab order status"""
    
    # Verify consultation and lab order exist
    lab_order = db.query(PatientLabOrder).filter(
        PatientLabOrder.id == order_id,
        PatientLabOrder.consultation_id == consultation_id
    ).first()
    
    if not lab_order:
        raise HTTPException(status_code=404, detail="Lab order not found")
    
    # Verify patient belongs to same hospital
    patient = db.query(Patient).filter(Patient.id == lab_order.patient_id).first()
    if not patient or patient.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update status and timestamps
    lab_order.status = status_update.status
    
    if status_update.status == "collected":
        lab_order.collection_date = datetime.now()
    elif status_update.status == "completed":
        lab_order.completion_date = datetime.now()
    
    db.commit()
    
    return {"message": "Lab order status updated successfully", "status": status_update.status}

@router.delete("/{consultation_id}/lab-orders/{order_id}")
async def cancel_lab_order(
    consultation_id: int,
    order_id: int,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "delete")),
    db: Session = Depends(get_db)
):
    """Cancel a lab order (only if not yet collected)"""
    
    # Verify consultation and lab order exist
    lab_order = db.query(PatientLabOrder).filter(
        PatientLabOrder.id == order_id,
        PatientLabOrder.consultation_id == consultation_id
    ).first()
    
    if not lab_order:
        raise HTTPException(status_code=404, detail="Lab order not found")
    
    # Verify patient belongs to same hospital
    patient = db.query(Patient).filter(Patient.id == lab_order.patient_id).first()
    if not patient or patient.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Only allow cancellation if not yet collected
    if lab_order.status in ["collected", "processing", "completed"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot cancel lab order with status '{lab_order.status}'"
        )
    
    lab_order.status = "cancelled"
    db.commit()
    
    return {"message": "Lab order cancelled successfully"}

@router.get("/{consultation_id}/available-tests", response_model=List[dict])
async def get_available_lab_tests(
    consultation_id: int,
    category_id: Optional[int] = None,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get available lab tests for a consultation"""
    
    # Verify consultation exists and user has access
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    
    # Get available tests for the hospital
    query = db.query(LabTest).filter(
        LabTest.hospital_id == current_user.hospital_id,
        LabTest.is_active == True
    )
    
    if category_id:
        query = query.filter(LabTest.category_id == category_id)
    
    lab_tests = query.order_by(LabTest.name).all()
    
    return [
        {
            "id": test.id,
            "name": test.name,
            "test_code": test.test_code,
            "cost": test.cost,
            "sample_type": test.sample_type,
            "preparation_instructions": test.preparation_instructions,
            "category_id": test.category_id
        }
        for test in lab_tests
    ]

@router.get("/{consultation_id}/test-recommendations", response_model=TestRecommendationsResponse)
async def get_consultation_test_recommendations(
    consultation_id: int,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get intelligent test recommendations for a consultation based on symptoms"""
    
    # Verify consultation exists and user has access
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    
    # Verify patient belongs to same hospital
    patient = db.query(Patient).filter(Patient.id == consultation.patient_id).first()
    if not patient or patient.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get test recommendations based on symptoms
    test_scores = get_test_recommendations(
        consultation.chief_complaint or "",
        consultation.present_history or "",
        patient_age=None  # Could calculate from DOB if needed
    )
    
    # Get available lab tests for the hospital
    available_tests = db.query(LabTest).filter(
        LabTest.hospital_id == current_user.hospital_id,
        LabTest.is_active == True
    ).all()
    
    # Create mapping of test codes to test objects
    test_code_map = {test.test_code: test for test in available_tests}
    
    recommendations = []
    total_cost = 0.0
    
    # Build recommendations list
    for test_code, score_info in test_scores.items():
        if test_code in test_code_map:
            test = test_code_map[test_code]
            
            # Get category name
            category = db.query(LabTestCategory).filter(LabTestCategory.id == test.category_id).first()
            category_name = category.name if category else "Other"
            
            recommendation = TestRecommendation(
                test_id=test.id,
                test_name=test.name,
                test_code=test.test_code,
                cost=test.cost,
                recommendation_reason=score_info["reason"],
                confidence_score=round(score_info["confidence"] * 100, 1),
                category_name=category_name
            )
            
            recommendations.append(recommendation)
            total_cost += test.cost
    
    # Sort by confidence score (highest first)
    recommendations.sort(key=lambda x: x.confidence_score, reverse=True)
    
    return TestRecommendationsResponse(
        consultation_id=consultation_id,
        chief_complaint=consultation.chief_complaint or "",
        recommendations=recommendations,
        total_recommended_cost=total_cost
    )

@router.post("/{consultation_id}/generate-bill", response_model=ConsultationBillResponse)
async def generate_consultation_bill(
    consultation_id: int,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Generate or update bill for consultation with lab orders"""
    
    # Verify consultation exists and user has access
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    
    # Verify patient belongs to same hospital
    patient = db.query(Patient).filter(Patient.id == consultation.patient_id).first()
    if not patient or patient.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Generate bill
    bill = create_consultation_bill(consultation_id, db, current_user)
    
    # Get bill items
    bill_items = db.query(BillItem).filter(BillItem.bill_id == bill.id).all()
    
    # Get doctor info
    doctor = db.query(User).filter(User.id == consultation.doctor_id).first()
    
    # Calculate lab orders cost
    lab_orders_cost = sum(item.total_price for item in bill_items if item.item_type == "lab_test")
    
    # Get payment information
    amount_paid, balance_due, payment_status = get_bill_payment_status(bill, db)
    bill.status = payment_status
    
    items_response = [
        BillItemResponse(
            item_type=item.item_type,
            item_name=item.item_name,
            item_code=item.item_code,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total_price=item.total_price,
            discount_percentage=item.discount_percentage
        )
        for item in bill_items
    ]
    
    return ConsultationBillResponse(
        bill_id=bill.id,
        bill_number=bill.bill_number,
        consultation_id=consultation_id,
        patient_name=f"{patient.first_name} {patient.last_name}",
        doctor_name=f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "Unknown",
        consultation_fee=consultation.consultation_fee or 0.0,
        lab_orders_cost=lab_orders_cost,
        subtotal=bill.subtotal,
        tax_amount=bill.tax_amount,
        discount_amount=bill.discount_amount,
        total_amount=bill.total_amount,
        amount_paid=amount_paid,
        balance_due=balance_due,
        status=payment_status,
        bill_date=bill.bill_date,
        items=items_response
    )

@router.get("/{consultation_id}/bill", response_model=ConsultationBillResponse)
async def get_consultation_bill(
    consultation_id: int,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get existing bill for consultation"""
    
    # Verify consultation exists and user has access
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    
    # Verify patient belongs to same hospital
    patient = db.query(Patient).filter(Patient.id == consultation.patient_id).first()
    if not patient or patient.hospital_id != current_user.hospital_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get existing bill
    bill = db.query(Bill).filter(
        Bill.bill_type == "consultation",
        Bill.reference_id == consultation_id
    ).first()
    
    if not bill:
        raise HTTPException(status_code=404, detail="No bill found for this consultation")
    
    # Get bill items
    bill_items = db.query(BillItem).filter(BillItem.bill_id == bill.id).all()
    
    # Get doctor info
    doctor = db.query(User).filter(User.id == consultation.doctor_id).first()
    
    # Calculate lab orders cost
    lab_orders_cost = sum(item.total_price for item in bill_items if item.item_type == "lab_test")
    
    # Get payment information
    amount_paid, balance_due, payment_status = get_bill_payment_status(bill, db)
    bill.status = payment_status
    
    items_response = [
        BillItemResponse(
            item_type=item.item_type,
            item_name=item.item_name,
            item_code=item.item_code,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total_price=item.total_price,
            discount_percentage=item.discount_percentage
        )
        for item in bill_items
    ]
    
    return ConsultationBillResponse(
        bill_id=bill.id,
        bill_number=bill.bill_number,
        consultation_id=consultation_id,
        patient_name=f"{patient.first_name} {patient.last_name}",
        doctor_name=f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "Unknown",
        consultation_fee=consultation.consultation_fee or 0.0,
        lab_orders_cost=lab_orders_cost,
        subtotal=bill.subtotal,
        tax_amount=bill.tax_amount,
        discount_amount=bill.discount_amount,
        total_amount=bill.total_amount,
        amount_paid=amount_paid,
        balance_due=balance_due,
        status=payment_status,
        bill_date=bill.bill_date,
        items=items_response
    )

@router.post("/{consultation_id}/bill/payment", response_model=PaymentResponse)
async def process_bill_payment(
    consultation_id: int,
    payment_data: PaymentCreate,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "write")),
    db: Session = Depends(get_db)
):
    """Process payment for consultation bill"""
    
    # Get bill for consultation
    bill = db.query(Bill).filter(
        Bill.bill_type == "consultation",
        Bill.reference_id == consultation_id
    ).first()
    
    if not bill:
        raise HTTPException(status_code=404, detail="No bill found for this consultation")
    
    # Check payment amount validity
    amount_paid, balance_due, _ = get_bill_payment_status(bill, db)
    if payment_data.amount_paid > balance_due:
        raise HTTPException(
            status_code=400, 
            detail=f"Payment amount (₹{payment_data.amount_paid}) exceeds balance due (₹{balance_due})"
        )
    
    # Create payment record
    payment = Payment(
        payment_number=generate_payment_number(),
        bill_id=bill.id,
        amount_paid=payment_data.amount_paid,
        payment_method_id=1,
        payment_method_name=payment_data.payment_method,
        transaction_reference=payment_data.transaction_reference,
        notes=payment_data.notes,
        received_by_id=current_user.id
    )
    
    db.add(payment)
    db.commit()
    db.refresh(payment)
    
    return PaymentResponse(
        payment_id=payment.id,
        payment_number=payment.payment_number,
        bill_id=bill.id,
        amount_paid=payment.amount_paid,
        payment_method=payment_data.payment_method,
        payment_date=payment.payment_date,
        transaction_reference=payment.transaction_reference,
        notes=payment.notes,
        receipt_number=f"RCP-{payment.payment_number}"
    )

@router.get("/{consultation_id}/bill/print", response_model=BillPrintResponse)
async def get_bill_for_printing(
    consultation_id: int,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Get bill details formatted for printing"""
    
    # Get consultation and bill
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    
    bill = db.query(Bill).filter(
        Bill.bill_type == "consultation",
        Bill.reference_id == consultation_id
    ).first()
    
    if not bill:
        raise HTTPException(status_code=404, detail="No bill found for this consultation")
    
    # Get patient and doctor info
    patient = db.query(Patient).filter(Patient.id == consultation.patient_id).first()
    doctor = db.query(User).filter(User.id == consultation.doctor_id).first()
    
    # Get bill items and payment info
    bill_items = db.query(BillItem).filter(BillItem.bill_id == bill.id).all()
    amount_paid, balance_due, payment_status = get_bill_payment_status(bill, db)
    
    # Get latest payment if any
    latest_payment = db.query(Payment).filter(Payment.bill_id == bill.id).order_by(Payment.payment_date.desc()).first()
    
    lab_orders_cost = sum(item.total_price for item in bill_items if item.item_type == "lab_test")
    
    items_response = [
        BillItemResponse(
            item_type=item.item_type,
            item_name=item.item_name,
            item_code=item.item_code,
            quantity=item.quantity,
            unit_price=item.unit_price,
            total_price=item.total_price,
            discount_percentage=item.discount_percentage
        )
        for item in bill_items
    ]
    
    bill_response = ConsultationBillResponse(
        bill_id=bill.id,
        bill_number=bill.bill_number,
        consultation_id=consultation_id,
        patient_name=f"{patient.first_name} {patient.last_name}",
        doctor_name=f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "Unknown",
        consultation_fee=consultation.consultation_fee or 0.0,
        lab_orders_cost=lab_orders_cost,
        subtotal=bill.subtotal,
        tax_amount=bill.tax_amount,
        discount_amount=bill.discount_amount,
        total_amount=bill.total_amount,
        amount_paid=amount_paid,
        balance_due=balance_due,
        status=payment_status,
        bill_date=bill.bill_date,
        items=items_response
    )
    
    hospital_info = {
        "name": "General Hospital",
        "address": "123 Medical Center Drive, New York, NY 10001",
        "phone": "+1-212-555-0123",
        "email": "info@generalhospital.com",
        "website": "https://www.generalhospital.com"
    }
    
    payment_receipt = None
    if latest_payment:
        payment_receipt = PaymentResponse(
            payment_id=latest_payment.id,
            payment_number=latest_payment.payment_number,
            bill_id=latest_payment.bill_id,
            amount_paid=latest_payment.amount_paid,
            payment_method=latest_payment.payment_method_name or "cash",
            payment_date=latest_payment.payment_date,
            transaction_reference=latest_payment.transaction_reference,
            notes=latest_payment.notes,
            receipt_number=f"RCP-{latest_payment.payment_number}"
        )
    
    return BillPrintResponse(
        bill=bill_response,
        hospital_info=hospital_info,
        payment_receipt=payment_receipt
    )

@router.get("/{consultation_id}/bill/download")
async def download_bill_pdf(
    consultation_id: int,
    include_header: bool = True,
    current_user: User = Depends(require_permission(Modules.OUTPATIENT, "read")),
    db: Session = Depends(get_db)
):
    """Download bill as PDF"""
    
    # Get consultation and bill
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")
    
    bill = db.query(Bill).filter(
        Bill.bill_type == "consultation",
        Bill.reference_id == consultation_id
    ).first()
    
    if not bill:
        raise HTTPException(status_code=404, detail="No bill found for this consultation")
    
    # Get patient and doctor info
    patient = db.query(Patient).filter(Patient.id == consultation.patient_id).first()
    doctor = db.query(User).filter(User.id == consultation.doctor_id).first()
    
    # Get bill items and payment info
    bill_items = db.query(BillItem).filter(BillItem.bill_id == bill.id).all()
    amount_paid, balance_due, payment_status = get_bill_payment_status(bill, db)
    
    # Get latest payment if any
    latest_payment = db.query(Payment).filter(Payment.bill_id == bill.id).order_by(Payment.payment_date.desc()).first()
    
    lab_orders_cost = sum(item.total_price for item in bill_items if item.item_type == "lab_test")
    
    # Format bill data for PDF
    bill_data = {
        "bill_number": bill.bill_number,
        "bill_date": bill.bill_date.isoformat(),
        "patient_name": f"{patient.first_name} {patient.last_name}",
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "Unknown",
        "status": payment_status,
        "subtotal": bill.subtotal,
        "tax_amount": bill.tax_amount,
        "discount_amount": bill.discount_amount,
        "total_amount": bill.total_amount,
        "amount_paid": amount_paid,
        "balance_due": balance_due,
        "payment_method": (latest_payment.payment_method_name or "cash").capitalize() if latest_payment else "Cash",
        "items": [
            {
                "item_name": item.item_name,
                "item_code": item.item_code or "",
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price
            }
            for item in bill_items
        ]
    }
    
    # Add payment receipt if available
    if latest_payment:
        bill_data["payment_receipt"] = {
            "receipt_number": f"RCP-{latest_payment.payment_number}",
            "payment_date": latest_payment.payment_date.isoformat(),
            "amount_paid": latest_payment.amount_paid,
            "payment_method": (latest_payment.payment_method_name or "cash").capitalize(),
            "transaction_reference": latest_payment.transaction_reference
        }
    
    hospital_info = {
        "name": "General Hospital",
        "address": "123 Medical Center Drive, New York, NY 10001",
        "phone": "+1-212-555-0123",
        "email": "info@generalhospital.com",
        "website": "https://www.generalhospital.com"
    }
    
    # Generate PDF
    pdf_buffer = pdf_service.generate_bill_pdf(bill_data, hospital_info, include_header=include_header)

    # Create filename
    filename = f"bill_{bill.bill_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    
    # Return PDF as streaming response
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )