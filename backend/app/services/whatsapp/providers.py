"""Built-in document kinds. Other modules register more the same way."""

from app.services.whatsapp.registry import DocumentKind, PreparedDocument, register_document_kind


def _prepared(template_family: str, built: dict) -> PreparedDocument:
    return PreparedDocument(
        pdf_bytes=built["pdf_bytes"],
        filename=built.get("filename") or "document.pdf",
        phone=built.get("phone") or "",
        patient_name=built.get("patient_name") or "",
        reference=built.get("reference") or "",
        document_date=built.get("document_date") or "",
        resource_type=built.get("resource_type") or "Document",
        resource_id=str(built.get("resource_id") or ""),
        template_family=template_family,
    )


def _load_hospital_bill(db, user, resource_id, include_header=None):
    from app.routes.hospital_admin import build_central_bill_document
    return _prepared("invoice", build_central_bill_document(db, user, int(resource_id)))


def _phone_hospital_bill(db, user, resource_id) -> str:
    from app.models.billing import Bill
    from app.models.patient import Patient
    bill = db.query(Bill).filter(Bill.id == int(resource_id)).first()
    if not bill or (bill.hospital_id and user.hospital_id and bill.hospital_id != user.hospital_id):
        return ""
    patient = db.query(Patient).filter(Patient.id == bill.patient_id).first() if bill.patient_id else None
    return (patient.primary_phone or "") if patient else ""


def _load_pharmacy_sale(db, user, resource_id, include_header=None):
    from app.routes.pharmacy import build_sale_invoice_document
    return _prepared("invoice", build_sale_invoice_document(db, user, int(resource_id)))


def _phone_pharmacy_sale(db, user, resource_id) -> str:
    from app.models.pharmacy import PharmacySale
    sale = db.query(PharmacySale).filter(
        PharmacySale.id == int(resource_id),
        PharmacySale.hospital_id == user.hospital_id,
    ).first()
    return (sale.patient_phone or "") if sale else ""


def _load_lab_report(db, user, resource_id, include_header=None):
    from app.routes.lab import build_lab_report_document
    return _prepared("lab_report", build_lab_report_document(db, user, int(resource_id), include_header))


def _phone_lab_report(db, user, resource_id) -> str:
    from app.models.lab import LabReport, PatientLabOrder
    from app.models.patient import Patient
    row = (
        db.query(Patient.primary_phone)
        .join(PatientLabOrder, PatientLabOrder.patient_id == Patient.id)
        .join(LabReport, LabReport.order_id == PatientLabOrder.id)
        .filter(LabReport.id == int(resource_id), Patient.hospital_id == user.hospital_id)
        .first()
    )
    return (row[0] or "") if row else ""


def _load_lab_bill(db, user, resource_id, include_header=None):
    from app.routes.lab import build_grouped_lab_bill_document
    return _prepared("invoice", build_grouped_lab_bill_document(db, user, resource_id))


def _phone_lab_bill(db, user, resource_id) -> str:
    from app.models.lab import PatientLabOrder
    from app.models.patient import Patient
    row = (
        db.query(Patient.primary_phone)
        .join(PatientLabOrder, PatientLabOrder.patient_id == Patient.id)
        .filter(
            PatientLabOrder.lab_bill_group_id == resource_id,
            Patient.hospital_id == user.hospital_id,
        )
        .first()
    )
    return (row[0] or "") if row else ""


def _load_appointment_bill(db, user, resource_id, include_header=None):
    from app.routes.appointments import build_appointment_bill_document
    return _prepared("invoice", build_appointment_bill_document(db, user, int(resource_id)))


def _phone_appointment_bill(db, user, resource_id) -> str:
    from app.models.outpatient import Appointment
    from app.models.patient import Patient
    row = (
        db.query(Patient.primary_phone)
        .join(Appointment, Appointment.patient_id == Patient.id)
        .filter(Appointment.id == int(resource_id), Patient.hospital_id == user.hospital_id)
        .first()
    )
    return (row[0] or "") if row else ""


def _load_inpatient_bill(db, user, resource_id, include_header=None):
    from app.routes.inpatient import build_inpatient_bill_document
    admission_id, bill_id = _split_admission_resource(resource_id)
    return _prepared("invoice", build_inpatient_bill_document(db, user, admission_id, bill_id=bill_id))


def _phone_inpatient(db, user, resource_id) -> str:
    from app.models.inpatient import Admission
    from app.models.patient import Patient
    admission_id, _bill_id = _split_admission_resource(resource_id)
    row = (
        db.query(Patient.primary_phone)
        .join(Admission, Admission.patient_id == Patient.id)
        .filter(Admission.id == admission_id, Patient.hospital_id == user.hospital_id)
        .first()
    )
    return (row[0] or "") if row else ""


def _split_admission_resource(resource_id: str):
    text = str(resource_id)
    if ":" in text:
        admission_s, bill_s = text.split(":", 1)
        return int(admission_s), int(bill_s)
    return int(text), None


def _load_deposit_receipt(db, user, resource_id, include_header=None):
    from app.routes.inpatient import build_deposit_receipt_document
    return _prepared("invoice", build_deposit_receipt_document(db, user, int(resource_id)))


def _phone_deposit(db, user, resource_id) -> str:
    from app.models.inpatient import Admission, AdmissionDeposit
    from app.models.patient import Patient
    row = (
        db.query(Patient.primary_phone)
        .join(Admission, Admission.patient_id == Patient.id)
        .join(AdmissionDeposit, AdmissionDeposit.admission_id == Admission.id)
        .filter(AdmissionDeposit.id == int(resource_id), Patient.hospital_id == user.hospital_id)
        .first()
    )
    return (row[0] or "") if row else ""


def _load_canteen_receipt(db, user, resource_id, include_header=None):
    from app.routes.canteen import build_canteen_receipt_document
    return _prepared("invoice", build_canteen_receipt_document(db, user, int(resource_id)))


def _phone_canteen(db, user, resource_id) -> str:
    from app.models.canteen import CanteenSale
    sale = db.query(CanteenSale).filter(
        CanteenSale.id == int(resource_id),
        CanteenSale.hospital_id == user.hospital_id,
    ).first()
    return (sale.customer_phone or "") if sale else ""


def _phone_lab_report_combined(db, user, resource_id) -> str:
    first = str(resource_id).split(",")[0].strip()
    if not first:
        return ""
    return _phone_lab_report(db, user, first)


def _load_lab_report_combined(db, user, resource_id, include_header=None):
    from app.routes.lab import build_combined_lab_report_document
    return _prepared("lab_report", build_combined_lab_report_document(db, user, resource_id, include_header))


def _load_lab_report_package(db, user, resource_id, include_header=None):
    from app.routes.lab import build_package_lab_report_document
    return _prepared("lab_report", build_package_lab_report_document(db, user, resource_id, include_header))


def _phone_lab_package(db, user, resource_id) -> str:
    from app.models.lab import PatientLabOrder
    from app.models.patient import Patient
    row = (
        db.query(Patient.primary_phone)
        .join(PatientLabOrder, PatientLabOrder.patient_id == Patient.id)
        .filter(
            PatientLabOrder.package_booking_id == resource_id,
            Patient.hospital_id == user.hospital_id,
        )
        .first()
    )
    return (row[0] or "") if row else ""


def _load_lab_order_bill(db, user, resource_id, include_header=None):
    from app.routes.lab import build_lab_order_bill_document
    return _prepared("invoice", build_lab_order_bill_document(db, user, int(resource_id)))


def _phone_lab_order(db, user, resource_id) -> str:
    from app.models.lab import PatientLabOrder
    from app.models.patient import Patient
    row = (
        db.query(Patient.primary_phone)
        .join(PatientLabOrder, PatientLabOrder.patient_id == Patient.id)
        .filter(PatientLabOrder.id == int(resource_id), Patient.hospital_id == user.hospital_id)
        .first()
    )
    return (row[0] or "") if row else ""


def _load_prescription(db, user, resource_id, include_header=None):
    from app.routes.prescriptions_simple import build_prescription_document
    return _prepared("prescription", build_prescription_document(db, user, resource_id))


def _phone_prescription(db, user, resource_id) -> str:
    from app.models.patient import Patient
    from app.models.prescriptions_simple import SimplePrescription
    prescription = db.query(SimplePrescription).filter(
        SimplePrescription.prescription_id == resource_id,
        SimplePrescription.hospital_id == user.hospital_id,
    ).first()
    if not prescription:
        return ""
    patient = db.query(Patient).filter(Patient.patient_id == prescription.patient_id).first()
    return (patient.primary_phone or "") if patient else ""


def _load_discharge_summary(db, user, resource_id, include_header=None):
    from app.routes.inpatient import build_discharge_summary_document
    return _prepared(
        "discharge",
        build_discharge_summary_document(db, user, int(resource_id), include_header),
    )


def register_builtin_documents() -> None:
    register_document_kind(DocumentKind(
        key="hospital_bill",
        template_family="invoice",
        load=_load_hospital_bill,
        suggest_phone=_phone_hospital_bill,
    ))
    register_document_kind(DocumentKind(
        key="pharmacy_sale",
        template_family="invoice",
        load=_load_pharmacy_sale,
        suggest_phone=_phone_pharmacy_sale,
    ))
    register_document_kind(DocumentKind(
        key="lab_report",
        template_family="lab_report",
        load=_load_lab_report,
        suggest_phone=_phone_lab_report,
    ))
    register_document_kind(DocumentKind(
        key="lab_bill",
        template_family="invoice",
        load=_load_lab_bill,
        suggest_phone=_phone_lab_bill,
    ))
    register_document_kind(DocumentKind(
        key="lab_order_bill",
        template_family="invoice",
        load=_load_lab_order_bill,
        suggest_phone=_phone_lab_order,
    ))
    register_document_kind(DocumentKind(
        key="appointment_bill",
        template_family="invoice",
        load=_load_appointment_bill,
        suggest_phone=_phone_appointment_bill,
    ))
    register_document_kind(DocumentKind(
        key="inpatient_bill",
        template_family="invoice",
        load=_load_inpatient_bill,
        suggest_phone=_phone_inpatient,
    ))
    register_document_kind(DocumentKind(
        key="deposit_receipt",
        template_family="invoice",
        load=_load_deposit_receipt,
        suggest_phone=_phone_deposit,
    ))
    register_document_kind(DocumentKind(
        key="canteen_receipt",
        template_family="invoice",
        load=_load_canteen_receipt,
        suggest_phone=_phone_canteen,
    ))
    register_document_kind(DocumentKind(
        key="lab_report_combined",
        template_family="lab_report",
        load=_load_lab_report_combined,
        suggest_phone=_phone_lab_report_combined,
    ))
    register_document_kind(DocumentKind(
        key="lab_report_package",
        template_family="lab_report",
        load=_load_lab_report_package,
        suggest_phone=_phone_lab_package,
    ))
    register_document_kind(DocumentKind(
        key="prescription",
        template_family="prescription",
        load=_load_prescription,
        suggest_phone=_phone_prescription,
    ))
    register_document_kind(DocumentKind(
        key="discharge_summary",
        template_family="discharge",
        load=_load_discharge_summary,
        suggest_phone=_phone_inpatient,
    ))


register_builtin_documents()
