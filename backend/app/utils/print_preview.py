"""Generate sample PDFs for Print Settings live preview (draft settings, no DB write)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.hospital import Hospital
from app.models.permissions import HospitalSettings
from app.utils.pdf_service import PDFService
from app.utils.pdf_settings import VALID_REPORT_KEYS, resolve_print_options_draft

pdf_service = PDFService()

_LAB_REPORT_TYPES = {"lab_report", "lab_bill"}


def _hospital_info(db: Session, hospital_id: int | None) -> dict:
    hospital = db.query(Hospital).filter(Hospital.id == hospital_id).first() if hospital_id else None
    if not hospital:
        hospital = db.query(Hospital).first()
    if not hospital:
        return {
            "name": "Sample Hospital",
            "address": "123 Hospital Road",
            "phone": "+91 00000 00000",
            "email": "info@hospital.com",
            "logo_url": "",
            "hospital_subname": "",
        }
    return {
        "name": hospital.name or "Hospital",
        "address": hospital.address or "",
        "phone": hospital.phone or "",
        "email": hospital.email or "",
        "logo_url": getattr(hospital, "logo_url", "") or "",
        "hospital_subname": getattr(hospital, "hospital_subname", "") or "",
    }


def _lab_config(db: Session) -> dict:
    rows = db.query(HospitalSettings).filter(
        HospitalSettings.setting_category == "lab_config"
    ).all()
    return {r.setting_key: r.setting_value for r in rows}


def _sample_bill() -> dict:
    now = datetime.now().isoformat()
    return {
        "bill_number": "PREVIEW-001",
        "bill_date": now,
        "print_date": now,
        "patient_name": "Sample Patient",
        "patient_age": 35,
        "patient_gender": "M",
        "patient_phone": "9999999999",
        "mrn": "MRN-PREVIEW",
        "referred_by": "Self",
        "payment_method": "Cash",
        "items": [
            {"item_name": "Sample consultation", "item_code": "CONS", "total_price": 500},
            {"item_name": "Sample procedure", "item_code": "PROC", "total_price": 1000},
        ],
        "subtotal": 1500,
        "discount_amount": 100,
        "tax_amount": 0,
        "total_amount": 1400,
        "amount_paid": 1400,
        "balance_due": 0,
        "prepared_by": "Sample Receptionist",
    }


def _sample_inpatient_bill() -> dict:
    now = datetime.now().isoformat()
    return {
        "bill_number": "IP-PREVIEW-001",
        "bill_date": now,
        "status": "preview",
        "bill_subtype": "interim",
        "patient": {
            "name": "Sample Patient",
            "mrn": "MRN-PREVIEW",
            "patient_id": "P-PREVIEW",
            "age": 45,
            "gender": "F",
            "phone": "9999999999",
            "referred_by": "Self",
        },
        "admission": {
            "admission_number": "ADM-PREVIEW",
            "ward": "General Ward",
            "room_number": "101",
            "bed_label": "A",
            "payer": "Cash",
        },
        "items": [
            {"description": "Room charges (sample)", "code": "", "qty": 1, "rate": 1500, "amount": 1500},
        ],
        "subtotal": 1500,
        "discount": 100,
        "tax": 0,
        "total": 1400,
        "deposits": [],
        "deposits_total": 500,
        "balance_due": 900,
    }


def _sample_prescription() -> dict:
    now = datetime.now().isoformat()
    return {
        "prescription_number": "RX-PREVIEW",
        "prescription_date": now,
        "patient_name": "Sample Patient",
        "patient_age": 35,
        "patient_gender": "M",
        "patient_phone": "9999999999",
        "mrn": "MRN-PREVIEW",
        "doctor_name": "Dr. Sample Doctor",
        "doctor_specialization": "General Medicine",
        "diagnosis": "Sample diagnosis (preview only)",
        "items": [
            {
                "medicine_name": "Sample Medicine 500mg",
                "dosage": "1 tablet",
                "duration": "5 days",
                "instructions": "After food",
                "frequency_schedule": "1-0-1",
                "food_timing": "after_food",
            },
        ],
        "vitals": {},
        "consultation": {},
        "lab_tests": [],
    }


def _sample_lab_report() -> dict:
    now = datetime.now().isoformat()
    return {
        "order_number": "LAB-PREVIEW",
        "report_date": now,
        "order_date": now,
        "collection_date": now,
        "patient_name": "Sample Patient",
        "patient_age": 35,
        "patient_gender": "male",
        "patient_phone": "9999999999",
        "mrn": "MRN-PREVIEW",
        "sample_id": "S-PREVIEW",
        "test_name": "Complete Blood Count",
        "test_code": "CBC",
        "referral_name": "Self",
        "results": [
            {
                "parameter_name": "Haemoglobin",
                "value": "14.2",
                "unit": "g/dL",
                "reference_range": "12 – 16",
                "is_abnormal": False,
            },
            {
                "parameter_name": "WBC Count",
                "value": "7200",
                "unit": "/µL",
                "reference_range": "4000 – 11000",
                "is_abnormal": False,
            },
        ],
        "technician_name": "Sample Lab Tech",
    }


def _sample_discharge_summary() -> dict:
    now = datetime.now()
    return {
        "admission_number": "ADM-PREVIEW",
        "patient_name": "Sample Patient",
        "mrn": "MRN-PREVIEW",
        "patient_id": "P-PREVIEW",
        "age": "45",
        "gender": "F",
        "village": "Sample Village",
        "district": "Sample District",
        "doctor_name": "Dr. Sample Doctor",
        "admission_date": now.strftime("%d/%m/%Y"),
        "discharge_date": now.strftime("%d/%m/%Y"),
        "discharge_type": "normal",
        "condition_on_admission": "stable",
        "condition_on_discharge": "stable",
        "diagnosis": "Sample diagnosis (preview only)",
        "treatment": "Sample treatment given during stay",
        "discharge_summary": "Sample discharge summary text for preview.",
        "take_home_medications": [
            {
                "medicine_name": "Sample Medicine 500mg",
                "dosage": "1 tablet",
                "frequency": "BD",
                "duration": "5 days",
                "quantity": 10,
                "instructions": "After food",
            },
        ],
        "medications": "",
        "follow_up": "Review in 1 week",
        "follow_up_date": now.strftime("%d/%m/%Y"),
        "diet_instructions": "Normal diet",
        "activity_restrictions": "Avoid strenuous activity",
        "total_stay_days": 3,
        "total_charges": 15000.0,
    }


def _sample_admission_detail() -> dict:
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    return {
        "admission_meta": {
            "patient_name": "Sample Patient",
            "mrn": "MRN-PREVIEW",
            "age": "45",
            "gender": "F",
            "village": "Sample Village",
            "district": "Sample District",
            "admission_number": "ADM-PREVIEW",
            "doctor_name": "Dr. Sample Doctor",
            "room_number": "101",
            "bed_label": "A",
            "admission_date": now,
            "discharge_date": "",
            "status": "admitted",
            "stay_days": 2,
        },
        "visits": [
            {
                "visit_datetime": now,
                "visitor_name": "Dr. Sample Doctor",
                "visit_type": "doctor_visit",
                "notes": "Patient stable, continuing treatment.",
                "plan_for_today": "Continue IV antibiotics.",
            },
        ],
        "vitals": [
            {
                "recorded_at": now,
                "bp": "120/80",
                "heart_rate": 78,
                "respiratory_rate": 18,
                "temperature_c": 37.0,
                "spo2": 98,
                "blood_glucose": None,
                "pain_score": 2,
                "gcs_score": 15,
                "is_abnormal": False,
                "abnormal_flags": "",
            },
        ],
        "mar": [
            {
                "scheduled_time": now,
                "medicine_name": "Sample Antibiotic 500mg",
                "dosage": "1 tab",
                "status": "given",
                "administered_at": now,
                "dose_given": "1 tab",
                "route": "oral",
                "administered_by_name": "Sample Nurse",
                "reason_if_not_given": "",
                "notes": "",
            },
        ],
        "mar_included": True,
        "inpatient_medications": [
            {
                "prescription_date": now,
                "medicine_name": "Sample Antibiotic 500mg",
                "dosage": "1 tab",
                "frequency": "BD",
                "route": "oral",
                "duration": "5 days",
                "is_prn": False,
                "prescriber": "Dr. Sample Doctor",
            },
        ],
        "ot_procedures": [],
        "ancillary_procedures": [],
        "investigations": [],
        "nursing_notes": [
            {
                "created_at": now,
                "shift": "morning",
                "note_type": "progress",
                "nurse_name": "Sample Nurse",
                "content": "Patient comfortable, vitals stable.",
            },
        ],
    }


def _sample_consent() -> dict:
    now = datetime.now()
    return {
        "consent_type": "face_sheet",
        "doc_number": "CS-PREVIEW-0001",
        "template_content": (
            "FACE SHEET — ADMISSION IDENTIFICATION (preview)\n\n"
            "Patient: Sample Patient\n"
            "I consent to treatment at this hospital."
        ),
        "procedure_name": "",
        "doctor_name": "Dr. Sample Doctor",
        "risks_explained": "",
        "signed_by": "patient",
        "guardian_name": "",
        "guardian_relationship": "",
        "patient_signature": "",
        "patient_signature_type": None,
        "witness_name": "",
        "signed_at": "",
        "withdrawn_at": "",
        "withdrawal_reason": "",
        "patient_name": "Sample Patient",
        "mrn": "MRN-PREVIEW",
        "patient_id": "P-PREVIEW",
        "age": "45",
        "gender": "Female",
        "primary_phone": "9999999999",
        "village": "Sample Village",
        "district": "Sample District",
        "emergency_contact_name": "Sample Contact",
        "emergency_contact_relation": "Spouse",
        "emergency_contact_phone": "8888888888",
        "admission_number": "ADM-PREVIEW",
        "admission_date": now.strftime("%d/%m/%Y"),
        "room_name": "101",
        "room_type": "general",
    }


def _sample_gate_pass() -> dict:
    return {
        "pass_number": "GP-PREVIEW",
        "issued_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "admission_number": "ADM-PREVIEW",
        "patient_name": "Sample Patient",
        "mrn": "MRN-PREVIEW",
        "vehicle_no": "-",
        "attendant_name": "Sample Attendant",
        "attendant_relationship": "Spouse",
        "issued_by_name": "Preview User",
    }


def _sample_pharmacy_sale() -> dict:
    now = datetime.now().isoformat()
    return {
        "sale_number": "PH-PREVIEW",
        "sale_date": now,
        "payment_type": "cash",
        "status": "completed",
        "patient_name": "Sample Patient",
        "patient_phone": "9999999999",
        "items": [
            {
                "medicine_name": "Sample Tablet 500mg",
                "batch_number": "B001",
                "quantity": 10,
                "free_quantity": 0,
                "rate": 5,
                "rate_tier": "retail",
                "discount_pct": 0,
                "tax_pct": 0,
                "line_total": 50,
            },
        ],
        "subtotal": 50,
        "discount_total": 0,
        "tax_total": 0,
        "grand_total": 50,
    }


def generate_print_preview_pdf(
    db: Session,
    hospital_id: int | None,
    *,
    report_type: str,
    include_header_on_pdfs: bool,
    detailed_billing_on_pdfs: bool = True,
    include_footer_on_pdfs: bool = True,
    letterhead_gap_mm: float,
    report_header_overrides: dict[str, str] | None = None,
    report_footer_overrides: dict[str, str] | None = None,
):
    if report_type not in VALID_REPORT_KEYS:
        report_type = "opd_bill"

    opts = resolve_print_options_draft(
        include_header_on_pdfs=include_header_on_pdfs,
        letterhead_gap_mm=letterhead_gap_mm,
        report_header_overrides=report_header_overrides or {},
        report_type=report_type,
        include_footer_on_pdfs=include_footer_on_pdfs,
        report_footer_overrides=report_footer_overrides or {},
    )
    kwargs = {
        "include_header": opts.include_header,
        "letterhead_gap_pt": opts.letterhead_gap_pt,
    }
    from app.utils.pdf_settings import FOOTER_REPORT_KEYS
    if report_type in FOOTER_REPORT_KEYS:
        kwargs["include_footer"] = opts.include_footer
    bill_layout_keys = {"opd_bill", "lab_bill", "inpatient_bill"}
    if report_type in bill_layout_keys:
        kwargs["detailed_billing"] = detailed_billing_on_pdfs
    hi = _hospital_info(db, hospital_id)

    if report_type == "prescription":
        return pdf_service.generate_prescription_pdf(_sample_prescription(), hi, **kwargs)

    if report_type in _LAB_REPORT_TYPES:
        return pdf_service.generate_lab_report_pdf(
            _sample_lab_report(), hi, _lab_config(db), **kwargs
        )

    if report_type == "inpatient_bill":
        return pdf_service.generate_inpatient_bill_pdf(_sample_inpatient_bill(), hi, **kwargs)

    if report_type == "gate_pass":
        return pdf_service.generate_gate_pass_pdf(_sample_gate_pass(), hi, **kwargs)

    if report_type == "pharmacy_sale_invoice":
        return pdf_service.generate_pharmacy_sale_invoice_pdf(_sample_pharmacy_sale(), hi, **kwargs)

    if report_type == "pharmacy_purchase":
        return pdf_service.generate_pharmacy_purchase_pdf(
            {
                "purchase_number": "PO-PREVIEW",
                "purchase_date": datetime.now().isoformat(),
                "supplier_name": "Sample Supplier",
                "items": [{"medicine_name": "Sample Medicine", "batch_number": "B1",
                             "quantity": 100, "rate": 10, "line_total": 1000}],
                "subtotal": 1000,
                "tax_total": 0,
                "grand_total": 1000,
            },
            hi,
            **kwargs,
        )

    if report_type == "pharmacy_dispense":
        return pdf_service.generate_pharmacy_dispense_slip_pdf(
            {
                "dispense_number": "DSP-PREVIEW",
                "dispensed_at": datetime.now().isoformat(),
                "patient_name": "Sample Patient",
                "doctor_name": "Dr. Sample",
                "items": [{"medicine_name": "Sample Medicine", "quantity": 10, "dosage": "1-0-1"}],
            },
            hi,
            **kwargs,
        )

    if report_type == "narcotic_register":
        return pdf_service.generate_narcotic_register_pdf(
            [{"date": datetime.now().strftime("%d/%m/%Y"), "patient_name": "Sample",
              "medicine_name": "Sample Schedule-H", "quantity": 1, "balance": 10}],
            {"from": "01/01/2026", "to": datetime.now().strftime("%d/%m/%Y")},
            hi,
            **kwargs,
        )

    if report_type == "pharmacy_report":
        return pdf_service.generate_pharmacy_report_pdf(
            title="Pharmacy Report (Preview)",
            period={"from": "01/01/2026", "to": datetime.now().strftime("%d/%m/%Y")},
            columns=[
                {"key": "name", "label": "Item"},
                {"key": "qty", "label": "Qty", "align": "RIGHT"},
            ],
            rows=[{"name": "Sample Item", "qty": 10}],
            hospital_info=hi,
            **kwargs,
        )

    if report_type == "refund_receipt":
        return pdf_service.generate_refund_receipt_pdf(
            {
                "refund_number": "REF-PREVIEW",
                "refund_date": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "amount": 500,
                "payment_method": "Cash",
                "reason": "Sample preview",
                "patient_name": "Sample Patient",
                "bill_number": "BILL-PREVIEW",
            },
            hi,
            **kwargs,
        )

    if report_type == "deposit_receipt":
        return pdf_service.generate_deposit_receipt_pdf(
            {
                "deposit_number": "DEP-PREVIEW",
                "deposit_date": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "amount": 5000,
                "payment_method": "Cash",
                "patient_name": "Sample Patient",
                "admission_number": "ADM-PREVIEW",
            },
            hi,
            **kwargs,
        )

    if report_type == "discharge_summary":
        return pdf_service.generate_discharge_summary_pdf(
            _sample_discharge_summary(),
            hi,
            **kwargs,
        )

    if report_type == "admission_detail":
        return pdf_service.generate_admission_detail_pdf(
            _sample_admission_detail(),
            hi,
            **kwargs,
        )

    if report_type == "consent":
        return pdf_service.generate_consent_pdf(_sample_consent(), hi, **kwargs)

    # Default: OPD-style bill preview (covers opd_bill, lab_bill, credit_note, admin reports, etc.)
    return pdf_service.generate_bill_pdf(_sample_bill(), hi, **kwargs)
