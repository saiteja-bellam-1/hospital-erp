import uuid
from sqlalchemy.orm import Session
from app.models.inpatient import Admission, RoomManagement, DischargeRecord
from app.models.patient import Patient
from typing import Optional, List, Dict, Any
from datetime import datetime, date

class InpatientService:
    def __init__(self, db: Session):
        self.db = db
    
    # Room Management
    def create_room(self, room_data: Dict[str, Any], hospital_id: int) -> RoomManagement:
        room = RoomManagement(
            room_number=room_data["room_number"],
            room_type=room_data["room_type"],
            floor=room_data.get("floor"),
            department=room_data.get("department"),
            bed_count=room_data.get("bed_count", 1),
            available_beds=room_data.get("available_beds", room_data.get("bed_count", 1)),
            room_charge_per_day=room_data["room_charge_per_day"],
            amenities=room_data.get("amenities"),
            hospital_id=hospital_id
        )
        
        self.db.add(room)
        self.db.commit()
        self.db.refresh(room)
        return room
    
    def get_rooms(self, hospital_id: int, room_type: Optional[str] = None, is_available: Optional[bool] = None) -> List[RoomManagement]:
        query = self.db.query(RoomManagement).filter(
            RoomManagement.hospital_id == hospital_id,
            RoomManagement.is_active == True
        )
        
        if room_type:
            query = query.filter(RoomManagement.room_type == room_type)
        
        if is_available is not None:
            if is_available:
                query = query.filter(RoomManagement.available_beds > 0)
            else:
                query = query.filter(RoomManagement.available_beds == 0)
        
        return query.order_by(RoomManagement.room_number).all()
    
    def get_room_by_id(self, room_id: int) -> Optional[RoomManagement]:
        return self.db.query(RoomManagement).filter(RoomManagement.id == room_id).first()
    
    def update_room_availability(self, room_id: int, beds_change: int) -> Optional[RoomManagement]:
        room = self.get_room_by_id(room_id)
        if not room:
            return None
        
        new_available_beds = room.available_beds + beds_change
        
        # Ensure available beds doesn't exceed total beds or go below 0
        if new_available_beds < 0:
            new_available_beds = 0
        elif new_available_beds > room.bed_count:
            new_available_beds = room.bed_count
        
        room.available_beds = new_available_beds
        room.is_occupied = new_available_beds == 0
        
        self.db.commit()
        self.db.refresh(room)
        return room
    
    def get_available_rooms(self, hospital_id: int, room_type: Optional[str] = None) -> List[RoomManagement]:
        return self.get_rooms(hospital_id, room_type, is_available=True)
    
    # Admission Management
    def create_admission(self, admission_data: Dict[str, Any]) -> Admission:
        admission_number = f"ADM{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Check room availability
        room = self.get_room_by_id(admission_data["room_id"])
        if not room or room.available_beds == 0:
            raise ValueError("Selected room is not available")
        
        admission = Admission(
            admission_number=admission_number,
            patient_id=admission_data["patient_id"],
            admitting_doctor_id=admission_data["admitting_doctor_id"],
            room_id=admission_data["room_id"],
            admission_type=admission_data["admission_type"],
            admission_reason=admission_data.get("admission_reason"),
            condition_on_admission=admission_data.get("condition_on_admission"),
            estimated_stay_days=admission_data.get("estimated_stay_days"),
            admission_notes=admission_data.get("admission_notes"),
            insurance_details=admission_data.get("insurance_details"),
            emergency_contact=admission_data.get("emergency_contact"),
            attending_physician_id=admission_data.get("attending_physician_id"),
            bed_number=admission_data.get("bed_number")
        )
        
        self.db.add(admission)
        self.db.commit()
        self.db.refresh(admission)
        
        # Update room availability
        self.update_room_availability(admission_data["room_id"], -1)
        
        return admission
    
    def get_admissions(self, hospital_id: int, status: Optional[str] = None, doctor_id: Optional[int] = None) -> List[Admission]:
        # Join with patient to filter by hospital
        query = self.db.query(Admission).join(Admission.patient).filter(
            Patient.hospital_id == hospital_id
        )
        
        if status:
            query = query.filter(Admission.status == status)
        
        if doctor_id:
            query = query.filter(
                (Admission.admitting_doctor_id == doctor_id) |
                (Admission.attending_physician_id == doctor_id)
            )
        
        return query.order_by(Admission.admission_date.desc()).all()
    
    def get_admission_by_id(self, admission_id: int) -> Optional[Admission]:
        return self.db.query(Admission).filter(Admission.id == admission_id).first()
    
    def get_admission_by_number(self, admission_number: str) -> Optional[Admission]:
        return self.db.query(Admission).filter(Admission.admission_number == admission_number).first()
    
    def update_admission(self, admission_id: int, admission_data: Dict[str, Any]) -> Optional[Admission]:
        admission = self.get_admission_by_id(admission_id)
        if not admission:
            return None
        
        for key, value in admission_data.items():
            if hasattr(admission, key) and key != "room_id":  # Handle room change separately
                setattr(admission, key, value)
        
        # Handle room change
        if "room_id" in admission_data and admission_data["room_id"] != admission.room_id:
            old_room_id = admission.room_id
            new_room_id = admission_data["room_id"]
            
            # Check new room availability
            new_room = self.get_room_by_id(new_room_id)
            if not new_room or new_room.available_beds == 0:
                raise ValueError("New room is not available")
            
            # Update room availability
            self.update_room_availability(old_room_id, 1)  # Free old room
            self.update_room_availability(new_room_id, -1)  # Occupy new room
            
            admission.room_id = new_room_id
        
        self.db.commit()
        self.db.refresh(admission)
        return admission
    
    def transfer_patient(self, admission_id: int, new_room_id: int, transfer_reason: str) -> Optional[Admission]:
        return self.update_admission(admission_id, {
            "room_id": new_room_id,
            "admission_notes": f"Transferred: {transfer_reason}"
        })
    
    # Discharge Management
    def discharge_patient(self, discharge_data: Dict[str, Any]) -> DischargeRecord:
        admission = self.get_admission_by_id(discharge_data["admission_id"])
        if not admission:
            raise ValueError("Admission not found")
        
        if admission.status != "admitted":
            raise ValueError("Patient is not currently admitted")
        
        # Calculate stay duration
        stay_duration = (datetime.now() - admission.admission_date).days + 1
        
        discharge_record = DischargeRecord(
            admission_id=discharge_data["admission_id"],
            discharge_type=discharge_data["discharge_type"],
            condition_on_discharge=discharge_data.get("condition_on_discharge"),
            discharge_summary=discharge_data.get("discharge_summary"),
            diagnosis_on_discharge=discharge_data.get("diagnosis_on_discharge"),
            treatment_given=discharge_data.get("treatment_given"),
            medications_prescribed=discharge_data.get("medications_prescribed"),
            follow_up_instructions=discharge_data.get("follow_up_instructions"),
            follow_up_date=discharge_data.get("follow_up_date"),
            diet_instructions=discharge_data.get("diet_instructions"),
            activity_restrictions=discharge_data.get("activity_restrictions"),
            discharge_approved_by_id=discharge_data["discharge_approved_by_id"],
            total_stay_days=stay_duration,
            total_charges=discharge_data.get("total_charges", 0.0)
        )
        
        self.db.add(discharge_record)
        
        # Update admission status
        admission.status = "discharged"
        
        # Free up the room
        self.update_room_availability(admission.room_id, 1)
        
        self.db.commit()
        self.db.refresh(discharge_record)
        return discharge_record
    
    def get_discharge_records(self, hospital_id: int, patient_id: Optional[int] = None) -> List[DischargeRecord]:
        # Join through admission and patient to filter by hospital
        query = self.db.query(DischargeRecord).join(DischargeRecord.admission).join(Admission.patient).filter(
            Patient.hospital_id == hospital_id
        )
        
        if patient_id:
            query = query.filter(Patient.id == patient_id)
        
        return query.order_by(DischargeRecord.discharge_date.desc()).all()
    
    # Ward Management
    def get_ward_census(self, hospital_id: int, ward_type: Optional[str] = None) -> Dict[str, Any]:
        rooms_query = self.db.query(RoomManagement).filter(
            RoomManagement.hospital_id == hospital_id,
            RoomManagement.is_active == True
        )
        
        if ward_type:
            rooms_query = rooms_query.filter(RoomManagement.room_type == ward_type)
        
        rooms = rooms_query.all()
        
        total_beds = sum(room.bed_count for room in rooms)
        occupied_beds = sum(room.bed_count - room.available_beds for room in rooms)
        available_beds = sum(room.available_beds for room in rooms)
        occupancy_rate = (occupied_beds / total_beds) * 100 if total_beds > 0 else 0
        
        # Get current admissions
        current_admissions = self.get_admissions(hospital_id, status="admitted")
        
        return {
            "total_rooms": len(rooms),
            "total_beds": total_beds,
            "occupied_beds": occupied_beds,
            "available_beds": available_beds,
            "occupancy_rate": round(occupancy_rate, 2),
            "current_patients": len(current_admissions),
            "room_details": [
                {
                    "room_number": room.room_number,
                    "room_type": room.room_type,
                    "total_beds": room.bed_count,
                    "available_beds": room.available_beds,
                    "occupied_beds": room.bed_count - room.available_beds,
                    "is_occupied": room.is_occupied,
                    "charge_per_day": room.room_charge_per_day
                }
                for room in rooms
            ]
        }
    
    def get_patient_bed_status(self, hospital_id: int) -> List[Dict[str, Any]]:
        # Get all admitted patients with their room details
        admitted_patients = self.db.query(Admission).join(Admission.patient).filter(
            Patient.hospital_id == hospital_id,
            Admission.status == "admitted"
        ).all()
        
        return [
            {
                "admission_number": admission.admission_number,
                "patient_id": admission.patient.patient_id,
                "patient_name": f"{admission.patient.first_name} {admission.patient.last_name}",
                "room_number": admission.room.room_number,
                "room_type": admission.room.room_type,
                "bed_number": admission.bed_number,
                "admission_date": admission.admission_date,
                "stay_days": (datetime.now() - admission.admission_date).days + 1,
                "admitting_doctor": f"{admission.admitting_doctor.first_name} {admission.admitting_doctor.last_name}",
                "condition": admission.condition_on_admission,
                "estimated_stay": admission.estimated_stay_days
            }
            for admission in admitted_patients
        ]
    
    # Patient Movement Tracking
    def get_patient_admission_history(self, patient_id: int) -> List[Dict[str, Any]]:
        admissions = self.db.query(Admission).filter(
            Admission.patient_id == patient_id
        ).order_by(Admission.admission_date.desc()).all()
        
        history = []
        for admission in admissions:
            admission_info = {
                "admission_number": admission.admission_number,
                "admission_date": admission.admission_date,
                "admission_type": admission.admission_type,
                "room_number": admission.room.room_number,
                "room_type": admission.room.room_type,
                "admitting_doctor": f"{admission.admitting_doctor.first_name} {admission.admitting_doctor.last_name}",
                "status": admission.status,
                "admission_reason": admission.admission_reason
            }
            
            if admission.discharge:
                admission_info.update({
                    "discharge_date": admission.discharge.discharge_date,
                    "discharge_type": admission.discharge.discharge_type,
                    "total_stay_days": admission.discharge.total_stay_days,
                    "total_charges": admission.discharge.total_charges,
                    "condition_on_discharge": admission.discharge.condition_on_discharge
                })
            
            history.append(admission_info)
        
        return history
    
    # Statistics and Reports
    def get_inpatient_statistics(self, hospital_id: int) -> Dict[str, Any]:
        # Current admissions
        current_admissions = self.get_admissions(hospital_id, status="admitted")
        
        # Total admissions (all time)
        total_admissions = self.db.query(Admission).join(Admission.patient).filter(
            Patient.hospital_id == hospital_id
        ).count()
        
        # Discharges today
        today_discharges = self.db.query(DischargeRecord).join(DischargeRecord.admission).join(Admission.patient).filter(
            Patient.hospital_id == hospital_id,
            self.db.func.date(DischargeRecord.discharge_date) == date.today()
        ).count()
        
        # Admissions today
        today_admissions = self.db.query(Admission).join(Admission.patient).filter(
            Patient.hospital_id == hospital_id,
            self.db.func.date(Admission.admission_date) == date.today()
        ).count()
        
        # Average length of stay
        completed_admissions = self.db.query(DischargeRecord).join(DischargeRecord.admission).join(Admission.patient).filter(
            Patient.hospital_id == hospital_id
        ).all()
        
        avg_stay = sum(discharge.total_stay_days for discharge in completed_admissions) / len(completed_admissions) if completed_admissions else 0
        
        # Ward census
        ward_census = self.get_ward_census(hospital_id)
        
        return {
            "current_admissions": len(current_admissions),
            "total_admissions": total_admissions,
            "today_admissions": today_admissions,
            "today_discharges": today_discharges,
            "average_length_of_stay": round(avg_stay, 1),
            "bed_occupancy_rate": ward_census["occupancy_rate"],
            "available_beds": ward_census["available_beds"],
            "total_beds": ward_census["total_beds"]
        }
    
    def get_admission_trends(self, hospital_id: int, days: int = 30) -> Dict[str, Any]:
        start_date = date.today() - timedelta(days=days)
        
        # Daily admissions
        daily_admissions = self.db.query(
            self.db.func.date(Admission.admission_date).label('admission_date'),
            self.db.func.count(Admission.id).label('admission_count')
        ).join(Admission.patient).filter(
            Patient.hospital_id == hospital_id,
            Admission.admission_date >= start_date
        ).group_by(
            self.db.func.date(Admission.admission_date)
        ).all()
        
        # Daily discharges
        daily_discharges = self.db.query(
            self.db.func.date(DischargeRecord.discharge_date).label('discharge_date'),
            self.db.func.count(DischargeRecord.id).label('discharge_count')
        ).join(DischargeRecord.admission).join(Admission.patient).filter(
            Patient.hospital_id == hospital_id,
            DischargeRecord.discharge_date >= start_date
        ).group_by(
            self.db.func.date(DischargeRecord.discharge_date)
        ).all()
        
        return {
            "period_days": days,
            "daily_admissions": [
                {
                    "date": str(record.admission_date),
                    "count": record.admission_count
                }
                for record in daily_admissions
            ],
            "daily_discharges": [
                {
                    "date": str(record.discharge_date),
                    "count": record.discharge_count
                }
                for record in daily_discharges
            ]
        }