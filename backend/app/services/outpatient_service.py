import uuid
from sqlalchemy.orm import Session
from app.models.outpatient import Appointment, OutpatientVisit
from app.models.patient import Patient
from app.models.user import User
from typing import Optional, List, Dict, Any
from datetime import datetime, date, time, timedelta

class OutpatientService:
    def __init__(self, db: Session):
        self.db = db
    
    # Appointment Management
    def create_appointment(self, appointment_data: Dict[str, Any]) -> Appointment:
        appointment_number = f"APT{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        appointment = Appointment(
            appointment_number=appointment_number,
            patient_id=appointment_data["patient_id"],
            doctor_id=appointment_data["doctor_id"],
            appointment_date=appointment_data["appointment_date"],
            appointment_time=appointment_data["appointment_time"],
            duration_minutes=appointment_data.get("duration_minutes", 30),
            appointment_type=appointment_data.get("appointment_type", "consultation"),
            reason=appointment_data.get("reason"),
            priority=appointment_data.get("priority", "normal"),
            notes=appointment_data.get("notes"),
            booking_source=appointment_data.get("booking_source", "manual"),
            booked_by_id=appointment_data.get("booked_by_id")
        )
        
        self.db.add(appointment)
        self.db.commit()
        self.db.refresh(appointment)
        return appointment
    
    def get_appointments(self, hospital_id: int, doctor_id: Optional[int] = None, 
                        appointment_date: Optional[date] = None, status: Optional[str] = None) -> List[Appointment]:
        # Join with patient to filter by hospital
        query = self.db.query(Appointment).join(Appointment.patient).filter(
            Patient.hospital_id == hospital_id
        )
        
        if doctor_id:
            query = query.filter(Appointment.doctor_id == doctor_id)
        
        if appointment_date:
            query = query.filter(self.db.func.date(Appointment.appointment_date) == appointment_date)
        
        if status:
            query = query.filter(Appointment.status == status)
        
        return query.order_by(Appointment.appointment_date, Appointment.appointment_time).all()
    
    def get_appointment_by_id(self, appointment_id: int) -> Optional[Appointment]:
        return self.db.query(Appointment).filter(Appointment.id == appointment_id).first()
    
    def update_appointment_status(self, appointment_id: int, status: str, notes: Optional[str] = None) -> Optional[Appointment]:
        appointment = self.get_appointment_by_id(appointment_id)
        if not appointment:
            return None
        
        appointment.status = status
        if notes:
            appointment.notes = notes
        
        current_time = datetime.now()
        
        if status == "confirmed":
            appointment.confirmed_at = current_time
        elif status == "in_progress":
            appointment.checked_in_at = current_time
            appointment.consultation_started_at = current_time
        elif status == "completed":
            appointment.consultation_ended_at = current_time
        
        self.db.commit()
        self.db.refresh(appointment)
        return appointment
    
    def reschedule_appointment(self, appointment_id: int, new_date: datetime, new_time: time) -> Optional[Appointment]:
        appointment = self.get_appointment_by_id(appointment_id)
        if not appointment:
            return None
        
        # Check if new slot is available
        if self.is_slot_available(appointment.doctor_id, new_date, new_time, appointment.duration_minutes, appointment_id):
            appointment.appointment_date = new_date
            appointment.appointment_time = new_time
            appointment.status = "scheduled"  # Reset status
            
            self.db.commit()
            self.db.refresh(appointment)
            return appointment
        else:
            raise ValueError("The requested time slot is not available")
    
    def cancel_appointment(self, appointment_id: int, cancellation_reason: str) -> Optional[Appointment]:
        appointment = self.get_appointment_by_id(appointment_id)
        if not appointment:
            return None
        
        appointment.status = "cancelled"
        appointment.notes = f"Cancelled: {cancellation_reason}"
        
        self.db.commit()
        self.db.refresh(appointment)
        return appointment
    
    def is_slot_available(self, doctor_id: int, appointment_date: datetime, appointment_time: time, 
                         duration_minutes: int, exclude_appointment_id: Optional[int] = None) -> bool:
        # Calculate appointment end time
        appointment_datetime = datetime.combine(appointment_date.date(), appointment_time)
        end_datetime = appointment_datetime + timedelta(minutes=duration_minutes)
        
        # Check for overlapping appointments
        query = self.db.query(Appointment).filter(
            Appointment.doctor_id == doctor_id,
            self.db.func.date(Appointment.appointment_date) == appointment_date.date(),
            Appointment.status.in_(["scheduled", "confirmed", "in_progress"])
        )
        
        if exclude_appointment_id:
            query = query.filter(Appointment.id != exclude_appointment_id)
        
        existing_appointments = query.all()
        
        for existing_apt in existing_appointments:
            existing_start = datetime.combine(existing_apt.appointment_date.date(), existing_apt.appointment_time)
            existing_end = existing_start + timedelta(minutes=existing_apt.duration_minutes)
            
            # Check for overlap
            if (appointment_datetime < existing_end and end_datetime > existing_start):
                return False
        
        return True
    
    def get_available_slots(self, doctor_id: int, appointment_date: date, slot_duration: int = 30) -> List[Dict[str, Any]]:
        # Define working hours (can be made configurable)
        start_time = time(9, 0)  # 9:00 AM
        end_time = time(17, 0)   # 5:00 PM
        
        slots = []
        current_time = datetime.combine(appointment_date, start_time)
        end_datetime = datetime.combine(appointment_date, end_time)
        
        while current_time < end_datetime:
            slot_time = current_time.time()
            
            if self.is_slot_available(doctor_id, datetime.combine(appointment_date, slot_time), slot_time, slot_duration):
                slots.append({
                    "time": slot_time.strftime("%H:%M"),
                    "datetime": current_time,
                    "available": True
                })
            else:
                slots.append({
                    "time": slot_time.strftime("%H:%M"),
                    "datetime": current_time,
                    "available": False
                })
            
            current_time += timedelta(minutes=slot_duration)
        
        return slots
    
    # Outpatient Visit Management
    def create_visit(self, visit_data: Dict[str, Any]) -> OutpatientVisit:
        visit_number = f"OPD{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        visit = OutpatientVisit(
            visit_number=visit_number,
            patient_id=visit_data["patient_id"],
            appointment_id=visit_data.get("appointment_id"),
            doctor_id=visit_data["doctor_id"],
            visit_type=visit_data.get("visit_type", "scheduled"),
            department=visit_data.get("department"),
            chief_complaint=visit_data.get("chief_complaint"),
            triage_level=visit_data.get("triage_level"),
            total_charges=visit_data.get("total_charges", "0.0")
        )
        
        self.db.add(visit)
        self.db.commit()
        self.db.refresh(visit)
        
        # Update appointment status if linked
        if visit.appointment_id:
            self.update_appointment_status(visit.appointment_id, "completed")
        
        return visit
    
    def update_visit_status(self, visit_id: int, status: str, discharge_summary: Optional[str] = None) -> Optional[OutpatientVisit]:
        visit = self.db.query(OutpatientVisit).filter(OutpatientVisit.id == visit_id).first()
        if not visit:
            return None
        
        visit.status = status
        if discharge_summary:
            visit.discharge_summary = discharge_summary
        
        # Calculate consultation time if completed
        if status == "completed" and visit.consultation_started_at:
            consultation_duration = datetime.now() - visit.consultation_started_at
            visit.consultation_time_minutes = int(consultation_duration.total_seconds() / 60)
        
        self.db.commit()
        self.db.refresh(visit)
        return visit
    
    def start_consultation(self, visit_id: int) -> Optional[OutpatientVisit]:
        visit = self.db.query(OutpatientVisit).filter(OutpatientVisit.id == visit_id).first()
        if not visit:
            return None
        
        visit.status = "in_consultation"
        visit.consultation_started_at = datetime.now()
        
        # Calculate waiting time
        if visit.visit_date:
            waiting_duration = datetime.now() - visit.visit_date
            visit.waiting_time_minutes = int(waiting_duration.total_seconds() / 60)
        
        self.db.commit()
        self.db.refresh(visit)
        return visit
    
    def get_visits(self, hospital_id: int, doctor_id: Optional[int] = None, 
                  visit_date: Optional[date] = None, status: Optional[str] = None) -> List[OutpatientVisit]:
        # Join with patient to filter by hospital
        query = self.db.query(OutpatientVisit).join(OutpatientVisit.patient).filter(
            Patient.hospital_id == hospital_id
        )
        
        if doctor_id:
            query = query.filter(OutpatientVisit.doctor_id == doctor_id)
        
        if visit_date:
            query = query.filter(self.db.func.date(OutpatientVisit.visit_date) == visit_date)
        
        if status:
            query = query.filter(OutpatientVisit.status == status)
        
        return query.order_by(OutpatientVisit.visit_date.desc()).all()
    
    def get_queue_status(self, doctor_id: int, visit_date: Optional[date] = None) -> Dict[str, Any]:
        if not visit_date:
            visit_date = date.today()
        
        # Get today's visits
        visits = self.db.query(OutpatientVisit).filter(
            OutpatientVisit.doctor_id == doctor_id,
            self.db.func.date(OutpatientVisit.visit_date) == visit_date
        ).order_by(OutpatientVisit.visit_date).all()
        
        # Get appointments
        appointments = self.db.query(Appointment).filter(
            Appointment.doctor_id == doctor_id,
            self.db.func.date(Appointment.appointment_date) == visit_date,
            Appointment.status.in_(["scheduled", "confirmed", "in_progress"])
        ).order_by(Appointment.appointment_time).all()
        
        waiting_visits = [v for v in visits if v.status in ["registered", "waiting"]]
        in_consultation = [v for v in visits if v.status == "in_consultation"]
        completed_visits = [v for v in visits if v.status == "completed"]
        
        return {
            "date": visit_date,
            "total_appointments": len(appointments),
            "total_visits": len(visits),
            "waiting_queue": len(waiting_visits),
            "in_consultation": len(in_consultation),
            "completed": len(completed_visits),
            "average_waiting_time": self._calculate_average_waiting_time(completed_visits),
            "queue_details": [
                {
                    "visit_number": v.visit_number,
                    "patient_name": f"{v.patient.first_name} {v.patient.last_name}",
                    "arrival_time": v.visit_date,
                    "waiting_time": v.waiting_time_minutes,
                    "priority": getattr(v, 'triage_level', 'normal')
                }
                for v in waiting_visits
            ]
        }
    
    def _calculate_average_waiting_time(self, completed_visits: List[OutpatientVisit]) -> Optional[float]:
        if not completed_visits:
            return None
        
        total_waiting_time = sum(v.waiting_time_minutes or 0 for v in completed_visits)
        return total_waiting_time / len(completed_visits)
    
    # Patient History
    def get_patient_visit_history(self, patient_id: int) -> List[OutpatientVisit]:
        return self.db.query(OutpatientVisit).filter(
            OutpatientVisit.patient_id == patient_id
        ).order_by(OutpatientVisit.visit_date.desc()).all()
    
    def get_patient_appointments(self, patient_id: int, include_past: bool = True) -> List[Appointment]:
        query = self.db.query(Appointment).filter(Appointment.patient_id == patient_id)
        
        if not include_past:
            query = query.filter(Appointment.appointment_date >= datetime.now())
        
        return query.order_by(Appointment.appointment_date.desc()).all()
    
    # Statistics and Reports
    def get_outpatient_statistics(self, hospital_id: int) -> Dict[str, Any]:
        # Total appointments
        total_appointments = self.db.query(Appointment).join(Appointment.patient).filter(
            Patient.hospital_id == hospital_id
        ).count()
        
        # Today's appointments
        today_appointments = self.db.query(Appointment).join(Appointment.patient).filter(
            Patient.hospital_id == hospital_id,
            self.db.func.date(Appointment.appointment_date) == date.today()
        ).count()
        
        # Pending appointments
        pending_appointments = self.db.query(Appointment).join(Appointment.patient).filter(
            Patient.hospital_id == hospital_id,
            Appointment.status.in_(["scheduled", "confirmed"])
        ).count()
        
        # Total visits
        total_visits = self.db.query(OutpatientVisit).join(OutpatientVisit.patient).filter(
            Patient.hospital_id == hospital_id
        ).count()
        
        # Today's visits
        today_visits = self.db.query(OutpatientVisit).join(OutpatientVisit.patient).filter(
            Patient.hospital_id == hospital_id,
            self.db.func.date(OutpatientVisit.visit_date) == date.today()
        ).count()
        
        return {
            "total_appointments": total_appointments,
            "today_appointments": today_appointments,
            "pending_appointments": pending_appointments,
            "total_visits": total_visits,
            "today_visits": today_visits
        }
    
    def get_doctor_schedule(self, doctor_id: int, schedule_date: date) -> Dict[str, Any]:
        appointments = self.get_appointments(
            hospital_id=None,  # Will be filtered by doctor_id
            doctor_id=doctor_id,
            appointment_date=schedule_date
        )
        
        visits = self.get_visits(
            hospital_id=None,  # Will be filtered by doctor_id
            doctor_id=doctor_id,
            visit_date=schedule_date
        )
        
        return {
            "date": schedule_date,
            "appointments": [
                {
                    "id": apt.id,
                    "time": apt.appointment_time.strftime("%H:%M"),
                    "patient_name": f"{apt.patient.first_name} {apt.patient.last_name}",
                    "type": apt.appointment_type,
                    "status": apt.status,
                    "duration": apt.duration_minutes
                }
                for apt in appointments
            ],
            "visits": [
                {
                    "id": visit.id,
                    "visit_number": visit.visit_number,
                    "patient_name": f"{visit.patient.first_name} {visit.patient.last_name}",
                    "type": visit.visit_type,
                    "status": visit.status,
                    "arrival_time": visit.visit_date.strftime("%H:%M") if visit.visit_date else None
                }
                for visit in visits
            ]
        }