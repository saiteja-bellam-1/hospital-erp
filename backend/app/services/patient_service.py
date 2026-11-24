import uuid
from sqlalchemy.orm import Session
from sqlalchemy import func, case, or_
from sqlalchemy.exc import IntegrityError
from app.models.patient import Patient, PatientContact, PatientMedicalHistory
from app.models.hospital import Hospital
from app.models.outpatient import Appointment
from typing import Optional, List, Dict, Any, Tuple
from datetime import date, datetime, timedelta
from app.utils.patient_age import compute_age_parts_from_dob
from app.services.barcode_service import barcode_lookup_codes


def _admission_search_predicates(term: str):
    """Match an inpatient stay by admission number or numeric admission id.

    Short digit strings match Admission.id only. A contains-match on
    ADM-YYYYMMDD-NNNN would treat "1" as every admission whose date contains 1.
    """
    from sqlalchemy import select
    from app.models.inpatient import Admission

    compact = (term or "").strip()
    if not compact:
        return None
    predicates = []
    upper = compact.upper()
    digits_only = compact.isdigit()
    has_digit = any(ch.isdigit() for ch in compact)
    # "ADM-" alone would match every stay. Require a digit so typeahead
    # starts narrowing at ADM-2… / 20261124-0001 / 0007.
    number_fragment = (
        (upper.startswith("ADM") or "-" in compact) and len(compact) >= 4 and has_digit
    )
    if number_fragment or (digits_only and len(compact) >= 4):
        predicates.append(Admission.admission_number.ilike(f"%{compact}%"))
    if digits_only:
        try:
            admission_pk = int(compact)
        except ValueError:
            admission_pk = None
        if admission_pk and admission_pk > 0:
            predicates.append(Admission.id == admission_pk)
    if not predicates:
        return None
    return select(Admission.patient_id).where(or_(*predicates))


def admission_term_matches(admission_id, admission_number, term: str) -> bool:
    """Same rules as _admission_search_predicates, for picking a row to display."""
    compact = (term or "").strip()
    if not compact:
        return False
    upper = compact.upper()
    number = (admission_number or "").upper()
    digits_only = compact.isdigit()
    has_digit = any(ch.isdigit() for ch in compact)
    if (
        ((upper.startswith("ADM") or "-" in compact) and len(compact) >= 4 and has_digit)
        or (digits_only and len(compact) >= 4)
    ):
        if upper in number:
            return True
    if digits_only:
        try:
            if int(compact) > 0 and int(compact) == admission_id:
                return True
        except ValueError:
            return False
    return False


def _pick_admission(admissions, term: str):
    """Prefer the stay the search hit. Otherwise the current admission."""
    if not admissions:
        return None
    hits = [
        adm for adm in admissions
        if admission_term_matches(adm.id, adm.admission_number, term)
    ]
    if hits:
        hits.sort(key=lambda adm: (adm.status == "admitted", adm.id or 0), reverse=True)
        return hits[0]
    active = [adm for adm in admissions if adm.status == "admitted"]
    if not active:
        return None
    active.sort(key=lambda adm: adm.id or 0, reverse=True)
    return active[0]


def patient_search_match_clause(search_term: str, include_admissions: bool = False):
    """OR clause: name / phone / id / MRN text / patient MRN barcode.

    include_admissions also matches inpatient admission number (ADM-…) and
    the numeric admission id. Used by the pharmacy sales counter.
    """
    term = (search_term or "").strip()
    if not term:
        return True
    like = f"%{term}%"
    clauses = [
        Patient.first_name.ilike(like),
        Patient.last_name.ilike(like),
        Patient.primary_phone.ilike(like),
        Patient.patient_id.ilike(like),
        Patient.mrn.ilike(like),
        Patient.mrn_ean13.ilike(like),
        Patient.aadhaar_number.ilike(like),
    ]
    aadhaar_digits = "".join(ch for ch in term if ch.isdigit())
    if len(aadhaar_digits) == 12:
        clauses.append(Patient.aadhaar_number == aadhaar_digits)
    for code in barcode_lookup_codes(term):
        clauses.append(Patient.mrn_ean13 == code)
    if include_admissions:
        admission_ids = _admission_search_predicates(term)
        if admission_ids is not None:
            clauses.append(Patient.id.in_(admission_ids))
    return or_(*clauses)

def _next_mrn_for(db: Session, hospital_id: int) -> str:
    """Compute the next MRN for a hospital.

    Format: {prefix}-{YYYY}-{NNNNN} where prefix comes from Hospital.mrn_prefix
    (defaulting to 'KTH'). Counter resets each calendar year, scoped per hospital.
    """
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first()
    prefix = (getattr(hospital, "mrn_prefix", None) or "KTH").strip().upper() or "KTH"
    year = datetime.now().year
    pattern = f"{prefix}-{year}-%"

    last = (
        db.query(Patient.mrn)
        .filter(Patient.hospital_id == hospital_id, Patient.mrn.like(pattern))
        .order_by(Patient.mrn.desc())
        .first()
    )
    next_seq = 1
    if last and last[0]:
        try:
            next_seq = int(last[0].rsplit("-", 1)[-1]) + 1
        except Exception:
            next_seq = 1
    return f"{prefix}-{year}-{next_seq:05d}"


class PatientService:
    def __init__(self, db: Session):
        self.db = db

    def create_patient(self, patient_data: Dict[str, Any]) -> Patient:
        allowed = {
            "first_name", "last_name", "date_of_birth", "age", "age_months", "gender",
            "blood_group", "marital_status", "abha_id", "aadhaar_number", "email",
            "primary_phone", "emergency_contact_phone", "emergency_contact_name",
            "emergency_contact_relation", "address_line1", "address_line2",
            "village", "mandal", "district", "address", "referred_by",
            "gstin",
            "hospital_id",
        }
        kwargs = {k: v for k, v in patient_data.items() if k in allowed}
        kwargs["patient_id"] = str(uuid.uuid4())

        # Generate MRN with one retry on the unique-constraint to handle the
        # race when two patients are created simultaneously (SQLite has no
        # SELECT ... FOR UPDATE so we rely on the constraint as the source of truth).
        for attempt in range(3):
            kwargs["mrn"] = _next_mrn_for(self.db, kwargs["hospital_id"])
            patient = Patient(**kwargs)
            self.db.add(patient)
            try:
                self.db.commit()
                self.db.refresh(patient)
                return patient
            except IntegrityError:
                self.db.rollback()
                if attempt == 2:
                    raise
        # Unreachable
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
        query = self.db.query(Patient).filter(
            Patient.hospital_id == hospital_id,
            Patient.is_active == True,
        )
        if (search_term or "").strip():
            query = query.filter(patient_search_match_clause(search_term))
        return query.all()

    def _attach_admission_matches(self, patient_data: List[Dict], search_term: str) -> None:
        """Stamp the stay the counter should show: the matched admission, else the active one."""
        from app.models.inpatient import Admission

        ids = [p["id"] for p in patient_data if p.get("id")]
        if not ids:
            return
        rows = (
            self.db.query(Admission)
            .filter(Admission.patient_id.in_(ids))
            .all()
        )
        grouped: Dict[int, List] = {}
        for row in rows:
            grouped.setdefault(row.patient_id, []).append(row)
        for patient in patient_data:
            chosen = _pick_admission(grouped.get(patient["id"]) or [], search_term)
            if not chosen:
                continue
            patient["admission_id"] = chosen.id
            patient["admission_number"] = chosen.admission_number
            patient["admission_status"] = chosen.status
    
    def calculate_age(self, date_of_birth: date) -> int:
        """Calculate whole years from date of birth."""
        if not date_of_birth:
            return None
        years, _, _ = compute_age_parts_from_dob(date_of_birth)
        return years
    
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
        include_admissions = bool(filters.get("include_admissions"))
        if search_term:
            query = query.filter(
                patient_search_match_clause(search_term, include_admissions=include_admissions)
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
                'mrn': patient.mrn,
                'first_name': patient.first_name,
                'last_name': patient.last_name,
                'date_of_birth': patient.date_of_birth,
                'age': age,
                'gender': patient.gender,
                'blood_group': patient.blood_group,
                'aadhaar_number': getattr(patient, "aadhaar_number", None),
                'primary_phone': patient.primary_phone,
                'emergency_contact_phone': patient.emergency_contact_phone,
                'address': patient.address,
                'referred_by': patient.referred_by,
                'is_active': patient.is_active,
                'created_at': patient.created_at,
                'last_appointment_date': last_appointment_date,
                'total_appointments': total_appointments or 0,
                'recent_visit_status': recent_visit_status
            })

        if include_admissions:
            self._attach_admission_matches(patient_data, search_term or "")
        
        # Create metadata
        total_pages = (total_count + per_page - 1) // per_page
        metadata = {
            'total_count': total_count,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages
        }
        
        return patient_data, metadata