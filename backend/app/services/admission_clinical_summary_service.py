"""Aggregate admission-scoped clinical data for the Detailed Admission Summary PDF."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.inpatient import (
    Admission,
    AdmissionAncillaryCharge,
    AncillaryServiceCatalog,
    MedicationAdministration,
    NursingNote,
    OTSchedule,
    PatientVisit,
    VitalSigns,
)
from app.models.lab import LabReport, LabTest, LabTestParameter, PatientLabOrder
from app.models.patient import Patient
from app.models.pharmacy import Medicine, Prescription, PrescriptionItem
from app.models.prescriptions_simple import SimplePrescription
from app.models.user import User
from app.utils.patient_age import format_patient_age, patient_age_years_int


def _as_naive_local(dt: datetime) -> datetime:
    """Normalize to naive system-local wall clock for display/math."""
    if dt.tzinfo is not None:
        return dt.astimezone().replace(tzinfo=None)
    return dt


def _fmt_dt(dt: Optional[datetime]) -> str:
    if not dt:
        return ""
    return _as_naive_local(dt).strftime("%d/%m/%Y %H:%M")


def _mar_row(m: MedicationAdministration, db: Session) -> dict:
    pi = m.prescription_item
    medicine = None
    dosage = None
    if pi:
        medicine = db.query(Medicine).filter(Medicine.id == pi.medicine_id).first()
        dosage = pi.dosage
    elif m.medicine_id:
        medicine = db.query(Medicine).filter(Medicine.id == m.medicine_id).first()
    administrator = None
    if m.administered_by_id:
        administrator = db.query(User).filter(User.id == m.administered_by_id).first()
    sort_key = m.scheduled_time or m.administered_at or m.created_at
    return {
        "medicine_name": medicine.name if medicine else "—",
        "dosage": dosage or m.dose_given or "",
        "scheduled_time": _fmt_dt(m.scheduled_time),
        "administered_at": _fmt_dt(m.administered_at),
        "status": m.status or "",
        "dose_given": m.dose_given or "",
        "route": m.route or "",
        "administered_by_name": (
            f"{administrator.first_name} {administrator.last_name}" if administrator else ""
        ),
        "reason_if_not_given": m.reason_if_not_given or "",
        "notes": m.notes or "",
        "is_prn": bool(m.is_prn),
        "prn_indication": m.prn_indication or "",
        "_sort": sort_key,
    }


def _lab_results_for_order(report: LabReport, db: Session, patient: Optional[Patient]) -> list[dict]:
    results = []
    gender = patient.gender.lower() if patient and patient.gender else None
    age = patient_age_years_int(patient) if patient else None

    for rv in report.result_values or []:
        param = db.query(LabTestParameter).filter(
            LabTestParameter.id == rv.get("parameter_id")
        ).first()
        if not param:
            continue

        raw_value = rv.get("value", "")
        is_abnormal = bool(rv.get("manual_abnormal", False))
        if not is_abnormal and param.field_type in ("numeric", "less_than", "greater_than") and raw_value:
            try:
                val = float(str(raw_value).strip().lstrip("<>").strip())
                ref_min = ref_max = None
                if gender == "male" and param.reference_min_male is not None:
                    ref_min, ref_max = param.reference_min_male, param.reference_max_male
                elif gender == "female" and param.reference_min_female is not None:
                    ref_min, ref_max = param.reference_min_female, param.reference_max_female
                else:
                    ref_min, ref_max = param.reference_min_default, param.reference_max_default
                if ref_min is not None and val < ref_min:
                    is_abnormal = True
                if ref_max is not None and val > ref_max:
                    is_abnormal = True
            except (ValueError, TypeError):
                pass

        results.append({
            "parameter_name": param.parameter_name,
            "value": raw_value,
            "unit": param.unit or "",
            "is_abnormal": is_abnormal,
        })
    return results


def build_admission_clinical_summary(
    db: Session,
    admission_id: int,
    *,
    include_mar: bool = True,
) -> dict[str, Any]:
    """Build normalized payload for Detailed Admission Summary PDF."""
    admission = (
        db.query(Admission)
        .options(
            joinedload(Admission.patient),
            joinedload(Admission.admitting_doctor),
            joinedload(Admission.room),
            joinedload(Admission.bed),
            joinedload(Admission.discharge),
        )
        .filter(Admission.id == admission_id)
        .first()
    )
    if not admission:
        raise ValueError("Admission not found")

    patient = admission.patient
    doctor = admission.admitting_doctor
    room = admission.room
    discharge = admission.discharge

    discharge_date = discharge.discharge_date if discharge else None
    stay_days = None
    if admission.admission_date:
        end = _as_naive_local(discharge_date or datetime.now())
        adm_dt = _as_naive_local(admission.admission_date)
        stay_days = max(0, (end - adm_dt).days)

    admission_meta = {
        "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "N/A",
        "mrn": (patient.mrn or "") if patient else "",
        "age": patient_age_years_int(patient) or "",
        "age_display": format_patient_age(patient),
        "gender": patient.gender if patient else "",
        "village": (patient.village or "") if patient else "",
        "district": (patient.district or "") if patient else "",
        "admission_number": admission.admission_number,
        "doctor_name": f"Dr. {doctor.first_name} {doctor.last_name}" if doctor else "N/A",
        "room_number": room.room_number if room else (admission.bed_number or ""),
        "room_type": room.room_type if room else "",
        "bed_label": admission.bed.bed_label if admission.bed else "",
        "admission_date": _fmt_dt(admission.admission_date),
        "discharge_date": _fmt_dt(discharge_date),
        "status": admission.status,
        "stay_days": stay_days or 0,
        "condition_on_admission": admission.condition_on_admission or "",
    }

    visits_raw = (
        db.query(PatientVisit)
        .options(joinedload(PatientVisit.visitor))
        .filter(
            PatientVisit.admission_id == admission_id,
            PatientVisit.visit_type.in_(("doctor_visit", "duty_doctor_visit")),
        )
        .order_by(PatientVisit.visit_datetime.asc())
        .all()
    )
    visits = []
    for v in visits_raw:
        visitor = v.visitor
        visits.append({
            "visit_datetime": _fmt_dt(v.visit_datetime),
            "visitor_name": f"{visitor.first_name} {visitor.last_name}" if visitor else "",
            "visit_type": v.visit_type,
            "notes": v.notes or "",
            "plan_for_today": v.plan_for_today or "",
            "vitals_reviewed": bool(v.vitals_reviewed),
            "labs_reviewed": bool(v.labs_reviewed),
            "pain_assessed": bool(v.pain_assessed),
            "mobility_checked": bool(v.mobility_checked),
            "family_updated": bool(v.family_updated),
        })

    vitals_raw = (
        db.query(VitalSigns)
        .filter(VitalSigns.admission_id == admission_id)
        .order_by(VitalSigns.recorded_at.asc())
        .all()
    )
    vitals = []
    for v in vitals_raw:
        rec = db.query(User).filter(User.id == v.recorded_by_id).first()
        bp = ""
        if v.bp_systolic is not None or v.bp_diastolic is not None:
            bp = f"{v.bp_systolic or '—'}/{v.bp_diastolic or '—'}"
        flags = v.abnormal_flags or []
        vitals.append({
            "recorded_at": _fmt_dt(v.recorded_at),
            "recorded_by_name": f"{rec.first_name} {rec.last_name}" if rec else "",
            "shift": v.shift or "",
            "bp": bp,
            "heart_rate": v.heart_rate,
            "respiratory_rate": v.respiratory_rate,
            "temperature_c": v.temperature_c,
            "spo2": v.spo2,
            "blood_glucose": v.blood_glucose,
            "pain_score": v.pain_score,
            "gcs_score": v.gcs_score,
            "is_abnormal": bool(v.is_abnormal),
            "abnormal_flags": ", ".join(flags) if flags else "",
            "notes": v.notes or "",
        })

    mar: list[dict] = []
    if include_mar:
        mar_rows = (
            db.query(MedicationAdministration)
            .filter(MedicationAdministration.admission_id == admission_id)
            .all()
        )
        mar_sorted = sorted(
            mar_rows,
            key=lambda m: _as_naive_local(_mar_row(m, db).get("_sort") or datetime.min),
        )
        for m in mar_sorted:
            row = _mar_row(m, db)
            row.pop("_sort", None)
            mar.append(row)

    inpatient_medications: list[dict] = []
    full_prescriptions = (
        db.query(Prescription)
        .filter(Prescription.admission_id == admission_id)
        .order_by(Prescription.prescription_date.asc())
        .all()
    )
    for rx in full_prescriptions:
        prescriber = db.query(User).filter(User.id == rx.doctor_id).first()
        items = db.query(PrescriptionItem).filter(PrescriptionItem.prescription_id == rx.id).all()
        for item in items:
            medicine = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
            inpatient_medications.append({
                "prescription_date": _fmt_dt(rx.prescription_date),
                "prescriber": f"Dr. {prescriber.first_name} {prescriber.last_name}" if prescriber else "",
                "medicine_name": medicine.name if medicine else "Unknown",
                "dosage": item.dosage or "",
                "frequency": item.frequency or "",
                "route": item.route or "",
                "duration": item.duration or "",
                "duration_days": item.duration_days,
                "is_prn": bool(item.is_prn),
                "status": item.status or rx.status or "",
            })

    simple_prescriptions = (
        db.query(SimplePrescription)
        .filter(SimplePrescription.admission_id == admission_id)
        .order_by(SimplePrescription.prescription_date.asc())
        .all()
    )
    for rx in simple_prescriptions:
        prescriber = db.query(User).filter(User.id == rx.doctor_id).first()
        for med in rx.medicines or []:
            if not isinstance(med, dict):
                continue
            inpatient_medications.append({
                "prescription_date": _fmt_dt(rx.prescription_date),
                "prescriber": f"Dr. {prescriber.first_name} {prescriber.last_name}" if prescriber else "",
                "medicine_name": med.get("name") or med.get("medicine_name") or "Unknown",
                "dosage": med.get("dosage") or "",
                "frequency": med.get("frequency") or "",
                "route": med.get("route") or "",
                "duration": med.get("duration") or "",
                "duration_days": med.get("duration_days"),
                "is_prn": bool(med.get("is_prn")),
                "status": rx.status or "",
            })

    ot_rows = (
        db.query(OTSchedule)
        .filter(OTSchedule.admission_id == admission_id)
        .order_by(OTSchedule.scheduled_date.asc())
        .all()
    )
    ot_procedures = []
    for ot in ot_rows:
        surgeon = db.query(User).filter(User.id == ot.surgeon_id).first()
        ot_procedures.append({
            "kind": "ot",
            "procedure_name": ot.procedure_name,
            "scheduled_date": _fmt_dt(ot.scheduled_date),
            "status": ot.status or "",
            "surgeon_name": f"Dr. {surgeon.first_name} {surgeon.last_name}" if surgeon else "",
            "ot_room": ot.ot_room_number or "",
            "pre_op_notes": ot.pre_op_notes or "",
            "post_op_notes": ot.post_op_notes or "",
        })

    ancillary_rows = (
        db.query(AdmissionAncillaryCharge)
        .filter(AdmissionAncillaryCharge.admission_id == admission_id)
        .order_by(AdmissionAncillaryCharge.charged_at.asc())
        .all()
    )
    ancillary_procedures = []
    for c in ancillary_rows:
        svc = db.query(AncillaryServiceCatalog).filter(AncillaryServiceCatalog.id == c.service_id).first()
        perf = db.query(User).filter(User.id == c.performed_by_id).first() if c.performed_by_id else None
        ancillary_procedures.append({
            "kind": "ancillary",
            "procedure_name": svc.service_name if svc else "Service",
            "category": svc.category if svc else "",
            "charged_at": _fmt_dt(c.charged_at),
            "performed_by_name": f"{perf.first_name} {perf.last_name}" if perf else "",
            "quantity": float(c.quantity or 0),
            "notes": c.notes or "",
        })

    investigations = []
    lab_orders = (
        db.query(PatientLabOrder)
        .filter(PatientLabOrder.admission_id == admission_id)
        .order_by(PatientLabOrder.order_date.asc())
        .all()
    )
    for order in lab_orders:
        test = db.query(LabTest).filter(LabTest.id == order.test_id).first()
        report = db.query(LabReport).filter(LabReport.order_id == order.id).first()
        entry = {
            "test_name": test.name if test else "Unknown test",
            "order_number": order.order_number,
            "status": order.status or "",
            "order_date": _fmt_dt(order.order_date),
            "completion_date": _fmt_dt(order.completion_date),
            "results": [],
        }
        if report:
            entry["results"] = _lab_results_for_order(report, db, patient)
        investigations.append(entry)

    nursing_notes_raw = (
        db.query(NursingNote)
        .filter(NursingNote.admission_id == admission_id)
        .order_by(NursingNote.created_at.asc())
        .all()
    )
    nursing_notes = []
    for n in nursing_notes_raw:
        nurse = db.query(User).filter(User.id == n.nurse_id).first()
        nursing_notes.append({
            "created_at": _fmt_dt(n.created_at),
            "shift": n.shift or "",
            "note_type": n.note_type or "",
            "nurse_name": f"{nurse.first_name} {nurse.last_name}" if nurse else "",
            "content": n.content or "",
        })

    return {
        "admission_meta": admission_meta,
        "visits": visits,
        "vitals": vitals,
        "mar": mar,
        "mar_included": include_mar,
        "inpatient_medications": inpatient_medications,
        "ot_procedures": ot_procedures,
        "ancillary_procedures": ancillary_procedures,
        "investigations": investigations,
        "nursing_notes": nursing_notes,
    }
