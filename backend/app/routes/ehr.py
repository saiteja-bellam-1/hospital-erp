from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from datetime import date
import json

from config.database import get_db
from app.models.patient import Patient, PatientMedicalHistory
from app.models.ehr import Consultation, Diagnosis, TreatmentPlan, MedicalNote
from app.models.prescriptions_simple import SimplePrescription
from app.models.lab import PatientLabOrder, LabTest, LabReport, LabTestParameter
from app.models.user import User
from app.utils.dependencies import get_current_user

router = APIRouter()


def _require_ehr_access(current_user: User):
    """Only doctor, hospital_admin, super_admin can access EHR"""
    allowed = ['doctor', 'hospital_admin', 'super_admin']
    if not any(r in current_user.role_names for r in allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to EHR records"
        )


@router.get("/patients/search")
async def search_patients_ehr(
    q: str = Query("", description="Search by name, phone, or patient ID"),
    limit: int = 200,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Search patients for EHR lookup. Returns all patients when q is empty."""
    _require_ehr_access(current_user)

    query = db.query(Patient).filter(
        Patient.hospital_id == current_user.hospital_id,
        Patient.is_active == True
    )

    if q.strip():
        search = f"%{q}%"
        query = query.filter(
            (Patient.first_name.ilike(search)) |
            (Patient.last_name.ilike(search)) |
            (Patient.primary_phone.ilike(search)) |
            (Patient.patient_id.ilike(search))
        )

    patients = query.order_by(Patient.first_name).limit(limit).all()

    return [
        {
            "id": p.id,
            "patient_id": p.patient_id,
            "first_name": p.first_name,
            "last_name": p.last_name,
            "full_name": f"{p.first_name} {p.last_name}",
            "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None,
            "age": _calc_age(p.date_of_birth) if p.date_of_birth else None,
            "gender": p.gender,
            "blood_group": p.blood_group,
            "primary_phone": p.primary_phone,
            "address": p.address,
        }
        for p in patients
    ]


@router.get("/patient/{patient_id}/history")
async def get_patient_full_history(
    patient_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get complete patient history: consultations, prescriptions, lab orders, notes"""
    _require_ehr_access(current_user)

    # Find patient by UUID
    patient = db.query(Patient).filter(
        Patient.patient_id == patient_id,
        Patient.hospital_id == current_user.hospital_id
    ).first()

    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # --- Patient info ---
    patient_info = {
        "id": patient.id,
        "patient_id": patient.patient_id,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "full_name": f"{patient.first_name} {patient.last_name}",
        "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        "age": _calc_age(patient.date_of_birth) if patient.date_of_birth else None,
        "gender": patient.gender,
        "blood_group": patient.blood_group,
        "primary_phone": patient.primary_phone,
        "emergency_contact_phone": patient.emergency_contact_phone,
        "address": patient.address,
    }

    # --- Medical history ---
    med_history = db.query(PatientMedicalHistory).filter(
        PatientMedicalHistory.patient_id == patient.id
    ).order_by(PatientMedicalHistory.created_at.desc()).all()

    medical_history = [
        {
            "id": mh.id,
            "condition": mh.condition,
            "diagnosed_date": mh.diagnosed_date.isoformat() if mh.diagnosed_date else None,
            "status": mh.status,
            "notes": mh.notes,
        }
        for mh in med_history
    ]

    # --- Consultations (exclude vitals_recording type) ---
    consultations_db = db.query(Consultation).filter(
        Consultation.patient_id == patient.id,
        Consultation.consultation_type != "vitals_recording"
    ).order_by(Consultation.consultation_date.desc()).all()

    consultations = []
    for c in consultations_db:
        doctor = db.query(User).filter(User.id == c.doctor_id).first()

        # Parse vital_signs JSON
        vitals = None
        if c.vital_signs:
            try:
                vitals = json.loads(c.vital_signs)
            except Exception:
                vitals = None

        # Diagnoses
        diagnoses = []
        if hasattr(c, 'diagnoses') and c.diagnoses:
            for d in c.diagnoses:
                diagnoses.append({
                    "diagnosis_name": d.diagnosis_name,
                    "diagnosis_code": d.diagnosis_code,
                    "diagnosis_type": d.diagnosis_type,
                    "severity": d.severity,
                    "status": d.status,
                    "notes": d.notes,
                })

        # Treatment plans
        treatments = []
        if hasattr(c, 'treatment_plans') and c.treatment_plans:
            for t in c.treatment_plans:
                treatments.append({
                    "treatment_type": t.treatment_type,
                    "description": t.description,
                    "instructions": t.instructions,
                    "status": t.status,
                })

        # Medical notes
        notes = []
        if hasattr(c, 'medical_notes') and c.medical_notes:
            for n in c.medical_notes:
                notes.append({
                    "note_type": n.note_type,
                    "title": n.title,
                    "content": n.content,
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                })

        consultations.append({
            "id": c.id,
            "consultation_number": c.consultation_number,
            "consultation_date": c.consultation_date.isoformat() if c.consultation_date else None,
            "consultation_type": c.consultation_type,
            "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "Unknown",
            "doctor_specialization": doctor.specialization if doctor and hasattr(doctor, 'specialization') else None,
            "chief_complaint": c.chief_complaint,
            "present_history": c.present_history,
            "examination_findings": c.examination_findings,
            "vital_signs": vitals,
            "status": c.status,
            "consultation_fee": c.consultation_fee,
            "follow_up_date": c.follow_up_date.isoformat() if c.follow_up_date else None,
            "notes": c.notes,
            "diagnoses": diagnoses,
            "treatment_plans": treatments,
            "medical_notes": notes,
        })

    # --- Prescriptions ---
    prescriptions_db = db.query(SimplePrescription).filter(
        SimplePrescription.patient_id == patient.patient_id,
        SimplePrescription.hospital_id == current_user.hospital_id
    ).order_by(SimplePrescription.prescription_date.desc()).all()

    prescriptions = []
    for rx in prescriptions_db:
        doctor = db.query(User).filter(User.id == rx.doctor_id).first()
        prescriptions.append({
            "id": rx.id,
            "prescription_id": rx.prescription_id,
            "prescription_date": rx.prescription_date.isoformat() if rx.prescription_date else None,
            "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "Unknown",
            "diagnosis": rx.diagnosis,
            "medicines": rx.medicines,
            "notes": rx.notes,
            "status": rx.status,
        })

    # --- Lab orders ---
    lab_orders_db = db.query(PatientLabOrder, LabTest).join(
        LabTest, PatientLabOrder.test_id == LabTest.id
    ).filter(
        PatientLabOrder.patient_id == patient.id
    ).order_by(PatientLabOrder.order_date.desc()).all()

    lab_orders = []
    for order, test in lab_orders_db:
        doctor = db.query(User).filter(User.id == order.doctor_id).first() if order.doctor_id else None

        # Get report if completed
        report_data = None
        if order.status == 'completed':
            report = db.query(LabReport).filter(LabReport.order_id == order.id).first()
            if report:
                # Parse results with parameter names
                results = []
                if report.result_values:
                    try:
                        raw_results = json.loads(report.result_values) if isinstance(report.result_values, str) else report.result_values
                        for rv in raw_results:
                            param = db.query(LabTestParameter).filter(
                                LabTestParameter.id == rv.get('parameter_id')
                            ).first()
                            results.append({
                                "parameter_name": param.parameter_name if param else f"Param {rv.get('parameter_id')}",
                                "value": rv.get('value', ''),
                                "unit": param.unit if param else '',
                                "reference_range": f"{param.reference_min_default or ''} - {param.reference_max_default or ''}" if param else '',
                                "is_abnormal": rv.get('is_abnormal', False),
                            })
                    except Exception:
                        pass

                report_data = {
                    "id": report.id,
                    "report_date": report.report_date.isoformat() if report.report_date else None,
                    "interpretation": report.interpretation,
                    "is_verified": report.is_verified,
                    "results": results,
                }

        lab_orders.append({
            "id": order.id,
            "order_number": order.order_number,
            "order_date": order.order_date.isoformat() if order.order_date else None,
            "test_name": test.name,
            "test_code": test.test_code,
            "status": order.status,
            "priority": order.priority,
            "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else None,
            "notes": order.notes,
            "completion_date": order.completion_date.isoformat() if order.completion_date else None,
            "report": report_data,
        })

    # --- Build unified timeline ---
    timeline = []

    for c in consultations:
        timeline.append({
            "type": "consultation",
            "date": c["consultation_date"],
            "data": c,
        })

    for rx in prescriptions:
        timeline.append({
            "type": "prescription",
            "date": rx["prescription_date"],
            "data": rx,
        })

    for lo in lab_orders:
        timeline.append({
            "type": "lab_order",
            "date": lo["order_date"],
            "data": lo,
        })

    # Sort timeline by date descending
    timeline.sort(key=lambda x: x["date"] or "", reverse=True)

    return {
        "patient": patient_info,
        "medical_history": medical_history,
        "consultations": consultations,
        "prescriptions": prescriptions,
        "lab_orders": lab_orders,
        "timeline": timeline,
    }


def _calc_age(dob: date) -> int:
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
