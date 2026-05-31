from datetime import datetime, date, time, timedelta
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Tuple
import json

from app.models.doctor_availability import DoctorAvailability, DoctorSpecialSchedule, DoctorAvailabilityStatus
from app.models.outpatient import Appointment
from app.models.user import User

class AvailabilityService:
    """Service for checking doctor availability and managing schedules"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def has_appointment_conflict(self, doctor_id: int, appointment_date: date,
                                  appointment_time: time, duration_minutes: int = 10) -> Tuple[bool, str]:
        """Return (has_conflict, reason). Only checks existing scheduled appointments —
        ignores doctor schedule/status/breaks. Used for override-booking by reception."""
        try:
            availability = self.db.query(DoctorAvailability).filter(
                DoctorAvailability.doctor_id == doctor_id
            ).first()
            buffer_minutes = (availability.buffer_minutes or 0) if availability else 0

            appointment_datetime = datetime.combine(appointment_date, appointment_time)
            appointment_end = appointment_datetime + timedelta(minutes=duration_minutes)
            check_start = appointment_datetime - timedelta(minutes=buffer_minutes)
            check_end = appointment_end + timedelta(minutes=buffer_minutes)

            existing = self.db.query(Appointment).filter(
                Appointment.doctor_id == doctor_id,
                Appointment.appointment_date == appointment_date,
                Appointment.status.in_(["scheduled", "confirmed", "in_progress"]),
            ).all()
            for apt in existing:
                existing_start = datetime.combine(appointment_date, apt.appointment_time)
                existing_end = existing_start + timedelta(minutes=apt.duration_minutes)
                if not (check_end <= existing_start or check_start >= existing_end):
                    return True, f"Conflicts with existing appointment at {apt.appointment_time}"
            return False, ""
        except Exception as e:
            return True, f"Error checking conflict: {str(e)}"

    def is_doctor_available(self, doctor_id: int, appointment_date: date,
                           appointment_time: time, duration_minutes: int = 10) -> Tuple[bool, str]:
        """
        Check if a doctor is available for an appointment at the specified date and time
        
        Returns:
            Tuple[bool, str]: (is_available, reason)
        """
        try:
            # Check if doctor exists and is active
            doctor = self.db.query(User).filter(
                User.id == doctor_id,
                User.role.has(name='doctor'),
                User.is_active == True
            ).first()
            
            if not doctor:
                return False, "Doctor not found or inactive"
            
            # Get doctor availability settings
            availability = self.db.query(DoctorAvailability).filter(
                DoctorAvailability.doctor_id == doctor_id
            ).first()
            
            if not availability:
                return False, "Doctor availability settings not configured"
            
            # Check doctor's current status
            status = self.db.query(DoctorAvailabilityStatus).filter(
                DoctorAvailabilityStatus.doctor_id == doctor_id
            ).first()
            
            if status and status.status != 'available':
                return False, f"Doctor is currently {status.status}"
            
            # Check for special schedules (holidays, leaves, modified hours)
            special_schedule = self.db.query(DoctorSpecialSchedule).filter(
                DoctorSpecialSchedule.doctor_id == doctor_id,
                DoctorSpecialSchedule.date == appointment_date
            ).first()
            
            if special_schedule:
                if special_schedule.schedule_type == 'holiday':
                    return False, f"Doctor is on {special_schedule.schedule_type}: {special_schedule.description or 'Not available'}"
                elif special_schedule.schedule_type == 'leave':
                    return False, f"Doctor is on {special_schedule.schedule_type}: {special_schedule.description or 'Not available'}"
                elif special_schedule.schedule_type == 'modified_hours':
                    # Check if appointment time falls within modified hours
                    if (special_schedule.start_time and appointment_time < special_schedule.start_time) or \
                       (special_schedule.end_time and appointment_time >= special_schedule.end_time):
                        return False, f"Appointment time outside doctor's modified hours ({special_schedule.start_time} - {special_schedule.end_time})"
            
            # Check weekly schedule
            day_of_week = appointment_date.strftime('%A').lower()
            weekly_schedule = availability.weekly_schedule
            
            if day_of_week not in weekly_schedule or not weekly_schedule[day_of_week].get('enabled', False):
                return False, f"Doctor is not available on {appointment_date.strftime('%A')}s"
            
            day_schedule = weekly_schedule[day_of_week]
            
            # Check if appointment time is within working hours
            start_time_str = day_schedule.get('start_time')
            end_time_str = day_schedule.get('end_time')
            
            if not start_time_str or not end_time_str:
                return False, "Doctor's working hours not set for this day"
            
            try:
                start_time = datetime.strptime(start_time_str, '%H:%M').time()
                end_time = datetime.strptime(end_time_str, '%H:%M').time()
            except ValueError:
                return False, "Invalid working hours format"
            
            # Calculate appointment end time
            appointment_datetime = datetime.combine(appointment_date, appointment_time)
            appointment_end = appointment_datetime + timedelta(minutes=duration_minutes)
            appointment_end_time = appointment_end.time()
            
            # Check if appointment falls within working hours
            if appointment_time < start_time or appointment_end_time > end_time:
                return False, f"Appointment time outside working hours ({start_time_str} - {end_time_str})"
            
            # Check for break times
            break_times = availability.break_times or []
            for break_time in break_times:
                break_start = datetime.strptime(break_time['start_time'], '%H:%M').time()
                break_end = datetime.strptime(break_time['end_time'], '%H:%M').time()
                
                # Check if appointment overlaps with break time
                if not (appointment_end_time <= break_start or appointment_time >= break_end):
                    return False, f"Appointment conflicts with break time ({break_time['start_time']} - {break_time['end_time']})"
            
            # Check for existing appointments (conflicts)
            buffer_minutes = availability.buffer_minutes or 0
            
            # Calculate time range to check (including buffer)
            check_start = appointment_datetime - timedelta(minutes=buffer_minutes)
            check_end = appointment_end + timedelta(minutes=buffer_minutes)
            
            existing_appointments = self.db.query(Appointment).filter(
                Appointment.doctor_id == doctor_id,
                Appointment.appointment_date == appointment_date,
                Appointment.status.in_(["scheduled", "confirmed", "in_progress"]),
            ).all()
            
            for existing_apt in existing_appointments:
                existing_start = datetime.combine(appointment_date, existing_apt.appointment_time)
                existing_end = existing_start + timedelta(minutes=existing_apt.duration_minutes)
                
                # Check for overlap
                if not (check_end <= existing_start or check_start >= existing_end):
                    return False, f"Appointment conflicts with existing appointment at {existing_apt.appointment_time}"
            
            return True, "Doctor is available"
            
        except Exception as e:
            return False, f"Error checking availability: {str(e)}"
    
    def get_available_slots(self, doctor_id: int, appointment_date: date, 
                           duration_minutes: int = 10) -> List[Dict]:
        """
        Get all available time slots for a doctor on a specific date
        
        Returns:
            List of available slots with start_time and end_time
        """
        available_slots = []
        
        try:
            # Get doctor availability settings
            availability = self.db.query(DoctorAvailability).filter(
                DoctorAvailability.doctor_id == doctor_id
            ).first()
            
            if not availability:
                return []
            
            # Check day schedule
            day_of_week = appointment_date.strftime('%A').lower()
            weekly_schedule = availability.weekly_schedule
            
            if day_of_week not in weekly_schedule or not weekly_schedule[day_of_week].get('enabled', False):
                return []
            
            day_schedule = weekly_schedule[day_of_week]
            start_time_str = day_schedule.get('start_time')
            end_time_str = day_schedule.get('end_time')
            
            if not start_time_str or not end_time_str:
                return []
            
            start_time = datetime.strptime(start_time_str, '%H:%M').time()
            end_time = datetime.strptime(end_time_str, '%H:%M').time()
            
            # Create time slots — use doctor's configured duration as the single source of truth
            slot_duration = availability.default_consultation_duration or duration_minutes
            buffer_minutes = availability.buffer_minutes or 0

            current_time = datetime.combine(appointment_date, start_time)
            end_datetime = datetime.combine(appointment_date, end_time)

            while current_time + timedelta(minutes=slot_duration) <= end_datetime:
                slot_start = current_time.time()
                is_available, _ = self.is_doctor_available(
                    doctor_id, appointment_date, slot_start, slot_duration
                )

                if is_available:
                    slot_end = (current_time + timedelta(minutes=slot_duration)).time()
                    available_slots.append({
                        'start_time': slot_start.strftime('%H:%M'),
                        'end_time': slot_end.strftime('%H:%M'),
                        'duration': slot_duration
                    })

                current_time += timedelta(minutes=slot_duration + buffer_minutes)
            
            return available_slots
            
        except Exception as e:
            return []
    
    def get_doctor_schedule_for_date(self, doctor_id: int, appointment_date: date) -> Dict:
        """Get doctor's complete schedule for a specific date"""
        try:
            # Get availability settings
            availability = self.db.query(DoctorAvailability).filter(
                DoctorAvailability.doctor_id == doctor_id
            ).first()
            
            if not availability:
                return {"available": False, "reason": "No availability settings found"}
            
            # Get doctor status
            status = self.db.query(DoctorAvailabilityStatus).filter(
                DoctorAvailabilityStatus.doctor_id == doctor_id
            ).first()
            
            # Check special schedules
            special_schedule = self.db.query(DoctorSpecialSchedule).filter(
                DoctorSpecialSchedule.doctor_id == doctor_id,
                DoctorSpecialSchedule.date == appointment_date
            ).first()
            
            # Get existing appointments
            existing_appointments = self.db.query(Appointment).filter(
                Appointment.doctor_id == doctor_id,
                Appointment.appointment_date == appointment_date,
                Appointment.status.in_(["scheduled", "confirmed", "in_progress"])
            ).order_by(Appointment.appointment_time).all()
            
            day_of_week = appointment_date.strftime('%A').lower()
            weekly_schedule = availability.weekly_schedule
            
            schedule_info = {
                "date": appointment_date.isoformat(),
                "day_of_week": day_of_week,
                "status": status.status if status else 'available',
                "available": True,
                "working_hours": None,
                "special_schedule": None,
                "existing_appointments": [],
                "available_slots": [],
                "break_times": availability.break_times or []
            }
            
            # Add special schedule info
            if special_schedule:
                schedule_info["special_schedule"] = {
                    "type": special_schedule.schedule_type,
                    "start_time": special_schedule.start_time.strftime('%H:%M') if special_schedule.start_time else None,
                    "end_time": special_schedule.end_time.strftime('%H:%M') if special_schedule.end_time else None,
                    "notes": special_schedule.description
                }
                
                if special_schedule.schedule_type in ['holiday', 'leave']:
                    schedule_info["available"] = False
            
            # Add working hours
            if day_of_week in weekly_schedule and weekly_schedule[day_of_week].get('enabled', False):
                day_schedule = weekly_schedule[day_of_week]
                schedule_info["working_hours"] = {
                    "start_time": day_schedule.get('start_time'),
                    "end_time": day_schedule.get('end_time')
                }
            else:
                schedule_info["available"] = False
                schedule_info["working_hours"] = {"reason": "Doctor not available on this day"}
            
            # Add existing appointments
            for apt in existing_appointments:
                schedule_info["existing_appointments"].append({
                    "time": apt.appointment_time.strftime('%H:%M'),
                    "duration": apt.duration_minutes,
                    "patient_name": f"{apt.patient.first_name} {apt.patient.last_name}" if hasattr(apt, 'patient') else "Unknown",
                    "type": apt.appointment_type,
                    "status": apt.status
                })
            
            # Add available slots if working
            if schedule_info["available"] and schedule_info["working_hours"]:
                schedule_info["available_slots"] = self.get_available_slots(doctor_id, appointment_date)
            
            return schedule_info
            
        except Exception as e:
            return {"available": False, "error": str(e)}