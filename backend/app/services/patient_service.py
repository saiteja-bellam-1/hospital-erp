import uuid
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from app.models.patient import Patient, PatientContact, PatientMedicalHistory
from app.models.outpatient import Appointment
from typing import Optional, List, Dict, Any, Tuple
from datetime import date, datetime, timedelta

class PatientService:
    def __init__(self, db: Session):
        self.db = db
    
    def create_patient(self, patient_data: Dict[str, Any]) -> Patient:
        allowed = {
            "first_name", "last_name", "date_of_birth", "age", "gender",
            "blood_group", "marital_status", "abha_id", "email",
            "primary_phone", "emergency_contact_phone", "emergency_contact_name",
            "emergency_contact_relation", "address_line1", "address_line2",
            "village", "mandal", "district", "address", "referred_by",
            "hospital_id",
        }
        kwargs = {k: v for k, v in patient_data.items() if k in allowed}
        kwargs["patient_id"] = str(uuid.uuid4())

        patient = Patient(**kwargs)
        self.db.add(patient)
        self.db.commit()
        self.db.refresh(patient)
        return patient
    
    def get_patient_by_phone(self, phone: str) -> Optional[Patient]:
        return self.db.query(Patient).filter(
            Patient.primary_phone == phone,
            Patient.is_active == True
        ).first()
    
    def get_patient_by_id(self, patient_id: str) -> Optional[Patient]:
        return self.db.query(Patient).filter(
            Patient.patient_id == patient_id,
            Patient.is_active == True
        ).first()
    
    def get_or_create_patient(self, phone: str, patient_data: Dict[str, Any]) -> Patient:
        patient = self.get_patient_by_phone(phone)
        if patient:
            return patient
        
        patient_data["primary_phone"] = phone
        return self.create_patient(patient_data)
    
    def add_contact(self, patient_id: int, contact_data: Dict[str, Any]) -> PatientContact:
        contact = PatientContact(
            patient_id=patient_id,
            contact_type=contact_data["contact_type"],
            name=contact_data.get("name"),
            phone=contact_data["phone"],
            email=contact_data.get("email"),
            relationship=contact_data.get("relationship")
        )
        
        self.db.add(contact)
        self.db.commit()
        self.db.refresh(contact)
        return contact
    
    def add_medical_history(self, patient_id: int, history_data: Dict[str, Any]) -> PatientMedicalHistory:
        history = PatientMedicalHistory(
            patient_id=patient_id,
            condition=history_data["condition"],
            diagnosed_date=history_data.get("diagnosed_date"),
            status=history_data.get("status", "active"),
            notes=history_data.get("notes")
        )
        
        self.db.add(history)
        self.db.commit()
        self.db.refresh(history)
        return history
    
    def update_patient(self, patient_id: str, update_data: Dict[str, Any]) -> Optional[Patient]:
        patient = self.get_patient_by_id(patient_id)
        if not patient:
            return None
        
        for key, value in update_data.items():
            if hasattr(patient, key):
                setattr(patient, key, value)
        
        self.db.commit()
        self.db.refresh(patient)
        return patient
    
    def search_patients(self, search_term: str, hospital_id: int) -> List[Patient]:
        return self.db.query(Patient).filter(
            Patient.hospital_id == hospital_id,
            Patient.is_active == True,
            (Patient.first_name.ilike(f"%{search_term}%") |
             Patient.last_name.ilike(f"%{search_term}%") |
             Patient.primary_phone.ilike(f"%{search_term}%") |
             Patient.patient_id.ilike(f"%{search_term}%"))
        ).all()
    
    def calculate_age(self, date_of_birth: date) -> int:
        """Calculate age from date of birth"""
        if not date_of_birth:
            return None
        today = date.today()
        return today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
    
    def advanced_search_patients(self, filters: Dict[str, Any], hospital_id: int, page: int = 1, per_page: int = 20) -> Tuple[List[Dict], Dict]:
        """Enhanced patient search with filters, metadata, and appointment info"""
        
        # Base query with appointment aggregation
        query = self.db.query(
            Patient,
            func.count(Appointment.id).label('total_appointments'),
            func.max(Appointment.appointment_date).label('last_appointment_date')
        ).outerjoin(
            Appointment, Patient.id == Appointment.patient_id
        ).filter(
            Patient.hospital_id == hospital_id,
            Patient.is_active == True
        ).group_by(Patient.id)
        
        # Apply search term filter
        search_term = filters.get('search_term')
        if search_term:
            query = query.filter(
                (Patient.first_name.ilike(f"%{search_term}%") |
                 Patient.last_name.ilike(f"%{search_term}%") |
                 Patient.primary_phone.ilike(f"%{search_term}%") |
                 Patient.patient_id.ilike(f"%{search_term}%"))
            )
        
        # Apply age filters
        if filters.get('min_age') or filters.get('max_age'):
            today = date.today()
            if filters.get('min_age'):
                max_birth_date = date(today.year - filters['min_age'], today.month, today.day)
                query = query.filter(Patient.date_of_birth <= max_birth_date)
            if filters.get('max_age'):
                min_birth_date = date(today.year - filters['max_age'] - 1, today.month, today.day)
                query = query.filter(Patient.date_of_birth >= min_birth_date)
        
        # Apply gender filter
        if filters.get('gender'):
            query = query.filter(Patient.gender.ilike(filters['gender']))
        
        # Apply blood group filter
        if filters.get('blood_group'):
            query = query.filter(Patient.blood_group == filters['blood_group'])
        
        # Apply recent appointments filter
        if filters.get('has_recent_appointments'):
            thirty_days_ago = datetime.now() - timedelta(days=30)
            if filters['has_recent_appointments']:
                query = query.having(func.max(Appointment.appointment_date) >= thirty_days_ago)
            else:
                query = query.having(func.max(Appointment.appointment_date) < thirty_days_ago)
        
        # Get total count before pagination
        total_count = query.count()
        
        # Apply sorting
        sort_by = filters.get('sort_by', 'name')
        sort_order = filters.get('sort_order', 'asc')
        
        if sort_by == 'name':
            order_field = Patient.first_name
        elif sort_by == 'age':
            order_field = Patient.date_of_birth
        elif sort_by == 'last_visit':
            order_field = func.max(Appointment.appointment_date)
        elif sort_by == 'created_at':
            order_field = Patient.created_at
        else:
            order_field = Patient.first_name
        
        if sort_order == 'desc':
            query = query.order_by(order_field.desc())
        else:
            query = query.order_by(order_field.asc())
        
        # Apply pagination
        offset = (page - 1) * per_page
        results = query.offset(offset).limit(per_page).all()
        
        # Transform results
        patient_data = []
        for patient, total_appointments, last_appointment_date in results:
            # Calculate age
            age = self.calculate_age(patient.date_of_birth) if patient.date_of_birth else patient.age
            
            # Determine recent visit status
            recent_visit_status = None
            if last_appointment_date:
                # Convert both to dates for comparison
                if isinstance(last_appointment_date, datetime):
                    last_visit_date = last_appointment_date.date()
                else:
                    last_visit_date = last_appointment_date
                
                days_since_last = (datetime.now().date() - last_visit_date).days
                if days_since_last <= 7:
                    recent_visit_status = "recent"
                elif days_since_last <= 30:
                    recent_visit_status = "moderate"
                else:
                    recent_visit_status = "old"
            
            patient_data.append({
                'id': patient.id,
                'patient_id': patient.patient_id,
                'first_name': patient.first_name,
                'last_name': patient.last_name,
                'date_of_birth': patient.date_of_birth,
                'age': age,
                'gender': patient.gender,
                'blood_group': patient.blood_group,
                'primary_phone': patient.primary_phone,
                'emergency_contact_phone': patient.emergency_contact_phone,
                'address': patient.address,
                'is_active': patient.is_active,
                'created_at': patient.created_at,
                'last_appointment_date': last_appointment_date,
                'total_appointments': total_appointments or 0,
                'recent_visit_status': recent_visit_status
            })
        
        # Create metadata
        total_pages = (total_count + per_page - 1) // per_page
        metadata = {
            'total_count': total_count,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages
        }
        
        return patient_data, metadata