import uuid
from sqlalchemy.orm import Session
from app.models.ehr import Consultation, Diagnosis, TreatmentPlan, MedicalNote
from app.models.patient import Patient
from app.models.lab import PatientLabOrder, LabTest
from app.models.pharmacy import Prescription
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

class EHRService:
    def __init__(self, db: Session):
        self.db = db
    
    # Consultation Management
    def create_consultation(self, consultation_data: Dict[str, Any]) -> Consultation:
        consultation_number = f"CONS{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        consultation = Consultation(
            consultation_number=consultation_number,
            patient_id=consultation_data["patient_id"],
            doctor_id=consultation_data["doctor_id"],
            consultation_type=consultation_data["consultation_type"],
            chief_complaint=consultation_data.get("chief_complaint"),
            present_history=consultation_data.get("present_history"),
            examination_findings=consultation_data.get("examination_findings"),
            vital_signs=consultation_data.get("vital_signs"),
            consultation_fee=consultation_data.get("consultation_fee", 0.0),
            notes=consultation_data.get("notes")
        )
        
        self.db.add(consultation)
        self.db.commit()
        self.db.refresh(consultation)
        return consultation
    
    def update_consultation(self, consultation_id: int, consultation_data: Dict[str, Any]) -> Optional[Consultation]:
        consultation = self.db.query(Consultation).filter(Consultation.id == consultation_id).first()
        if not consultation:
            return None
        
        for key, value in consultation_data.items():
            if hasattr(consultation, key):
                setattr(consultation, key, value)
        
        self.db.commit()
        self.db.refresh(consultation)
        return consultation
    
    def complete_consultation(self, consultation_id: int, follow_up_date: Optional[datetime] = None) -> Optional[Consultation]:
        consultation = self.db.query(Consultation).filter(Consultation.id == consultation_id).first()
        if not consultation:
            return None
        
        consultation.status = "completed"
        if follow_up_date:
            consultation.follow_up_date = follow_up_date
        
        self.db.commit()
        self.db.refresh(consultation)
        return consultation
    
    def get_consultations(self, patient_id: Optional[int] = None, doctor_id: Optional[int] = None, status: Optional[str] = None) -> List[Consultation]:
        query = self.db.query(Consultation)
        
        if patient_id:
            query = query.filter(Consultation.patient_id == patient_id)
        
        if doctor_id:
            query = query.filter(Consultation.doctor_id == doctor_id)
        
        if status:
            query = query.filter(Consultation.status == status)
        
        return query.order_by(Consultation.consultation_date.desc()).all()
    
    def get_consultation_by_id(self, consultation_id: int) -> Optional[Consultation]:
        return self.db.query(Consultation).filter(Consultation.id == consultation_id).first()
    
    # Diagnosis Management
    def add_diagnosis(self, diagnosis_data: Dict[str, Any]) -> Diagnosis:
        diagnosis = Diagnosis(
            consultation_id=diagnosis_data["consultation_id"],
            diagnosis_code=diagnosis_data.get("diagnosis_code"),
            diagnosis_name=diagnosis_data["diagnosis_name"],
            diagnosis_type=diagnosis_data.get("diagnosis_type", "primary"),
            severity=diagnosis_data.get("severity"),
            status=diagnosis_data.get("status", "active"),
            notes=diagnosis_data.get("notes")
        )
        
        self.db.add(diagnosis)
        self.db.commit()
        self.db.refresh(diagnosis)
        return diagnosis
    
    def update_diagnosis(self, diagnosis_id: int, diagnosis_data: Dict[str, Any]) -> Optional[Diagnosis]:
        diagnosis = self.db.query(Diagnosis).filter(Diagnosis.id == diagnosis_id).first()
        if not diagnosis:
            return None
        
        for key, value in diagnosis_data.items():
            if hasattr(diagnosis, key):
                setattr(diagnosis, key, value)
        
        self.db.commit()
        self.db.refresh(diagnosis)
        return diagnosis
    
    def get_patient_diagnoses(self, patient_id: int, status: Optional[str] = None) -> List[Diagnosis]:
        query = self.db.query(Diagnosis).join(Diagnosis.consultation).filter(
            Consultation.patient_id == patient_id
        )
        
        if status:
            query = query.filter(Diagnosis.status == status)
        
        return query.order_by(Diagnosis.created_at.desc()).all()
    
    # Treatment Plan Management
    def create_treatment_plan(self, treatment_data: Dict[str, Any]) -> TreatmentPlan:
        treatment_plan = TreatmentPlan(
            consultation_id=treatment_data["consultation_id"],
            treatment_type=treatment_data["treatment_type"],
            description=treatment_data["description"],
            instructions=treatment_data.get("instructions"),
            start_date=treatment_data.get("start_date"),
            end_date=treatment_data.get("end_date"),
            frequency=treatment_data.get("frequency"),
            status=treatment_data.get("status", "active")
        )
        
        self.db.add(treatment_plan)
        self.db.commit()
        self.db.refresh(treatment_plan)
        return treatment_plan
    
    def update_treatment_plan(self, plan_id: int, treatment_data: Dict[str, Any]) -> Optional[TreatmentPlan]:
        treatment_plan = self.db.query(TreatmentPlan).filter(TreatmentPlan.id == plan_id).first()
        if not treatment_plan:
            return None
        
        for key, value in treatment_data.items():
            if hasattr(treatment_plan, key):
                setattr(treatment_plan, key, value)
        
        self.db.commit()
        self.db.refresh(treatment_plan)
        return treatment_plan
    
    def get_patient_treatment_plans(self, patient_id: int, status: Optional[str] = None) -> List[TreatmentPlan]:
        query = self.db.query(TreatmentPlan).join(TreatmentPlan.consultation).filter(
            Consultation.patient_id == patient_id
        )
        
        if status:
            query = query.filter(TreatmentPlan.status == status)
        
        return query.order_by(TreatmentPlan.created_at.desc()).all()
    
    # Medical Notes Management
    def add_medical_note(self, note_data: Dict[str, Any]) -> MedicalNote:
        note = MedicalNote(
            consultation_id=note_data["consultation_id"],
            note_type=note_data["note_type"],
            title=note_data.get("title"),
            content=note_data["content"],
            is_confidential=note_data.get("is_confidential", False),
            created_by_id=note_data["created_by_id"]
        )
        
        self.db.add(note)
        self.db.commit()
        self.db.refresh(note)
        return note
    
    def get_consultation_notes(self, consultation_id: int) -> List[MedicalNote]:
        return self.db.query(MedicalNote).filter(
            MedicalNote.consultation_id == consultation_id
        ).order_by(MedicalNote.created_at.desc()).all()
    
    def get_patient_notes(self, patient_id: int, note_type: Optional[str] = None) -> List[MedicalNote]:
        query = self.db.query(MedicalNote).join(MedicalNote.consultation).filter(
            Consultation.patient_id == patient_id
        )
        
        if note_type:
            query = query.filter(MedicalNote.note_type == note_type)
        
        return query.order_by(MedicalNote.created_at.desc()).all()
    
    # Prescription Integration
    def create_prescription_from_consultation(self, consultation_id: int, prescription_items: List[Dict[str, Any]]) -> Prescription:
        from app.services.pharmacy_service import PharmacyService
        
        consultation = self.get_consultation_by_id(consultation_id)
        if not consultation:
            raise ValueError("Consultation not found")
        
        pharmacy_service = PharmacyService(self.db)
        
        prescription_data = {
            "patient_id": consultation.patient_id,
            "doctor_id": consultation.doctor_id,
            "consultation_id": consultation_id,
            "notes": f"Prescribed during consultation {consultation.consultation_number}"
        }
        
        prescription = pharmacy_service.create_prescription(prescription_data)
        
        # Add prescription items
        for item_data in prescription_items:
            pharmacy_service.add_prescription_item(prescription.id, item_data)
        
        return prescription
    
    # Lab Test Orders Integration
    def order_lab_tests(self, consultation_id: int, test_orders: List[Dict[str, Any]]) -> List[PatientLabOrder]:
        from app.services.lab_service import LabService
        
        consultation = self.get_consultation_by_id(consultation_id)
        if not consultation:
            raise ValueError("Consultation not found")
        
        lab_service = LabService(self.db)
        orders = []
        
        for test_order in test_orders:
            order_data = {
                "patient_id": consultation.patient_id,
                "test_id": test_order["test_id"],
                "doctor_id": consultation.doctor_id,
                "priority": test_order.get("priority", "normal"),
                "notes": test_order.get("notes", f"Ordered during consultation {consultation.consultation_number}")
            }
            
            order = lab_service.create_lab_order(order_data)
            orders.append(order)
        
        return orders
    
    # Patient Medical History
    def get_patient_medical_summary(self, patient_id: int) -> Dict[str, Any]:
        patient = self.db.query(Patient).filter(Patient.id == patient_id).first()
        if not patient:
            return {}
        
        # Get recent consultations
        recent_consultations = self.get_consultations(patient_id=patient_id)[:5]
        
        # Get active diagnoses
        active_diagnoses = self.get_patient_diagnoses(patient_id, status="active")
        
        # Get active treatment plans
        active_treatments = self.get_patient_treatment_plans(patient_id, status="active")
        
        # Get recent lab results
        recent_lab_orders = self.db.query(PatientLabOrder).filter(
            PatientLabOrder.patient_id == patient_id,
            PatientLabOrder.status == "completed"
        ).order_by(PatientLabOrder.completion_date.desc()).limit(5).all()
        
        # Get current prescriptions
        current_prescriptions = self.db.query(Prescription).filter(
            Prescription.patient_id == patient_id,
            Prescription.status.in_(["pending", "partial"])
        ).order_by(Prescription.prescription_date.desc()).limit(5).all()
        
        return {
            "patient": {
                "patient_id": patient.patient_id,
                "name": f"{patient.first_name} {patient.last_name}",
                "age": self._calculate_age(patient.date_of_birth),
                "gender": patient.gender,
                "blood_group": patient.blood_group,
                "phone": patient.primary_phone
            },
            "recent_consultations": [
                {
                    "id": c.id,
                    "date": c.consultation_date,
                    "type": c.consultation_type,
                    "chief_complaint": c.chief_complaint,
                    "status": c.status
                }
                for c in recent_consultations
            ],
            "active_diagnoses": [
                {
                    "name": d.diagnosis_name,
                    "code": d.diagnosis_code,
                    "type": d.diagnosis_type,
                    "severity": d.severity
                }
                for d in active_diagnoses
            ],
            "active_treatments": [
                {
                    "type": t.treatment_type,
                    "description": t.description,
                    "frequency": t.frequency,
                    "start_date": t.start_date
                }
                for t in active_treatments
            ],
            "recent_lab_results": [
                {
                    "test_name": order.test.name,
                    "order_date": order.order_date,
                    "completion_date": order.completion_date,
                    "status": order.status
                }
                for order in recent_lab_orders
            ],
            "current_prescriptions": [
                {
                    "prescription_number": p.prescription_number,
                    "date": p.prescription_date,
                    "status": p.status,
                    "total_amount": p.total_amount
                }
                for p in current_prescriptions
            ]
        }
    
    def _calculate_age(self, date_of_birth):
        if not date_of_birth:
            return None
        
        today = datetime.now().date()
        age = today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
        return age
    
    # Vital Signs Helper
    def record_vital_signs(self, consultation_id: int, vital_signs_data: Dict[str, Any]) -> Optional[Consultation]:
        consultation = self.get_consultation_by_id(consultation_id)
        if not consultation:
            return None
        
        # Store vital signs as JSON
        vital_signs_json = json.dumps(vital_signs_data)
        consultation.vital_signs = vital_signs_json
        
        self.db.commit()
        self.db.refresh(consultation)
        return consultation
    
    # Statistics
    def get_doctor_statistics(self, doctor_id: int) -> Dict[str, Any]:
        total_consultations = self.db.query(Consultation).filter(
            Consultation.doctor_id == doctor_id
        ).count()
        
        today_consultations = self.db.query(Consultation).filter(
            Consultation.doctor_id == doctor_id,
            self.db.func.date(Consultation.consultation_date) == datetime.now().date()
        ).count()
        
        pending_consultations = self.db.query(Consultation).filter(
            Consultation.doctor_id == doctor_id,
            Consultation.status == "ongoing"
        ).count()
        
        # Get consultation types breakdown
        consultation_types = self.db.query(
            Consultation.consultation_type,
            self.db.func.count(Consultation.id).label('count')
        ).filter(
            Consultation.doctor_id == doctor_id
        ).group_by(Consultation.consultation_type).all()
        
        return {
            "total_consultations": total_consultations,
            "today_consultations": today_consultations,
            "pending_consultations": pending_consultations,
            "consultation_types": {
                consultation_type: count for consultation_type, count in consultation_types
            }
        }
    
    def get_hospital_ehr_statistics(self, hospital_id: int) -> Dict[str, Any]:
        # Get consultations for hospital patients
        total_consultations = self.db.query(Consultation).join(Consultation.patient).filter(
            Patient.hospital_id == hospital_id
        ).count()
        
        active_patients = self.db.query(Patient).filter(
            Patient.hospital_id == hospital_id,
            Patient.is_active == True
        ).count()
        
        # Recent activity
        recent_consultations = self.db.query(Consultation).join(Consultation.patient).filter(
            Patient.hospital_id == hospital_id,
            Consultation.consultation_date >= datetime.now().replace(hour=0, minute=0, second=0)
        ).count()
        
        return {
            "total_consultations": total_consultations,
            "active_patients": active_patients,
            "recent_consultations": recent_consultations
        }