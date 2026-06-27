"""Tests for Detailed Admission Summary aggregation and PDF."""

import uuid
import pytest
from datetime import datetime, timezone

from app.models.inpatient import (
    Admission,
    NursingNote,
    PatientVisit,
    RoomManagement,
    VitalSigns,
)
from app.services.admission_clinical_summary_service import build_admission_clinical_summary


def _create_room_and_admission(db_session, seed_data):
    suffix = uuid.uuid4().hex[:8].upper()
    room = RoomManagement(
        room_number=f"DET-{suffix}",
        room_type="general",
        floor="1",
        department="General",
        bed_count=2,
        available_beds=2,
        room_charge_per_day=500.0,
        hospital_id=seed_data["hospital_id"],
        is_occupied=False,
    )
    db_session.add(room)
    db_session.flush()

    admission = Admission(
        admission_number=f"ADM-DET-{suffix}",
        patient_id=seed_data["patient_id"],
        admitting_doctor_id=seed_data["doctor_user_id"],
        room_id=room.id,
        admission_type="elective",
        admission_reason="Detail summary test",
        condition_on_admission="stable",
        status="admitted",
        admission_date=datetime.now(timezone.utc),
    )
    db_session.add(admission)
    db_session.flush()
    return admission


class TestAdmissionClinicalSummaryService:
    def test_build_summary_includes_clinical_sections(self, db_session, seed_data):
        admission = _create_room_and_admission(db_session, seed_data)

        visit = PatientVisit(
            admission_id=admission.id,
            patient_id=seed_data["patient_id"],
            visitor_id=seed_data["doctor_user_id"],
            visit_type="doctor_visit",
            visit_datetime=datetime.now(timezone.utc),
            notes="Rounding note",
            plan_for_today="Continue care",
            created_by_id=seed_data["doctor_user_id"],
            hospital_id=seed_data["hospital_id"],
        )
        db_session.add(visit)

        vitals = VitalSigns(
            admission_id=admission.id,
            patient_id=seed_data["patient_id"],
            recorded_by_id=seed_data["doctor_user_id"],
            recorded_at=datetime.now(timezone.utc),
            bp_systolic=120,
            bp_diastolic=80,
            heart_rate=72,
            is_abnormal=False,
            hospital_id=seed_data["hospital_id"],
        )
        db_session.add(vitals)

        note = NursingNote(
            admission_id=admission.id,
            patient_id=seed_data["patient_id"],
            nurse_id=seed_data["admin_user_id"],
            shift="morning",
            note_type="progress",
            content="Patient resting comfortably.",
            hospital_id=seed_data["hospital_id"],
        )
        db_session.add(note)
        db_session.commit()

        payload = build_admission_clinical_summary(db_session, admission.id, include_mar=True)

        assert payload["admission_meta"]["admission_number"].startswith("ADM-DET-")
        assert len(payload["visits"]) == 1
        assert payload["visits"][0]["notes"] == "Rounding note"
        assert len(payload["vitals"]) == 1
        assert payload["vitals"][0]["heart_rate"] == 72
        assert len(payload["nursing_notes"]) == 1
        assert "resting" in payload["nursing_notes"][0]["content"]

    def test_mar_omitted_when_flag_false(self, db_session, seed_data):
        admission = _create_room_and_admission(db_session, seed_data)
        db_session.commit()

        payload = build_admission_clinical_summary(db_session, admission.id, include_mar=False)
        assert payload["mar_included"] is False
        assert payload["mar"] == []


class TestAdmissionDetailPdfApi:
    def test_pdf_on_active_admission(self, client, auth_headers, db_session, seed_data):
        admission = _create_room_and_admission(db_session, seed_data)
        db_session.commit()

        resp = client.get(
            f"/api/inpatient/admissions/{admission.id}/admission-detail/pdf",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content[:4] == b"%PDF"

    def test_pdf_after_discharge(self, client, auth_headers, db_session, seed_data):
        admission = _create_room_and_admission(db_session, seed_data)
        admission.status = "discharged"
        db_session.commit()

        resp = client.get(
            f"/api/inpatient/admissions/{admission.id}/admission-detail/pdf",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.content[:4] == b"%PDF"

    def test_list_admission_ot(self, client, auth_headers, db_session, seed_data):
        admission = _create_room_and_admission(db_session, seed_data)
        db_session.commit()

        resp = client.get(
            f"/api/inpatient/admissions/{admission.id}/ot",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_admission_detail_print_preview(self, db_session):
        from app.utils.print_preview import generate_print_preview_pdf

        buf = generate_print_preview_pdf(
            db_session,
            None,
            report_type="admission_detail",
            include_header_on_pdfs=True,
            letterhead_gap_mm=35.0,
        )
        data = buf.getvalue()
        assert data[:4] == b"%PDF"
