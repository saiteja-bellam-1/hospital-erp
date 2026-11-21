"""Fertility (ART) clinic, embryology lab, and donor bank."""
from __future__ import annotations

import csv
import io
import os
import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.art import (
    ArtAppointment, ArtBankUnit, ArtCase, ArtCharge, ArtConsent, ArtCounsellorNote,
    ArtCycle, ArtDocument, ArtDonor, ArtEquipment, ArtGrievance, ArtPackageTemplate,
    ArtPartnerBank, ArtQueueEntry, ArtService, ArtSpecimen, ArtStimulationDay,
    ArtTankLog, ArtWorkup,
)
from app.models.patient import Patient
from app.models.user import User
from app.services.art_ops import (
    CONSENT_FORMS, add_specimen, add_stimulation, assert_level2, book_appointment,
    cancel_cycle, change_billing_mode, check_in_queue, clear_donor, close_culture,
    collect_payment, complete_appointment, create_donor, dispose_specimen,
    donor_private, donor_public, get_centre, grade_specimen, issue_unit, lab_kpis,
    level2_licensed, open_culture, outcome_report, post_charge, receive_external,
    record_consent, record_donor_retrieval, record_fertilisation, record_outcome,
    record_retrieval, record_timeout, registry_export, reject_owner_change,
    renew_storage, set_trigger, start_cycle, store_bank_unit, thaw_specimen,
)
from app.services.audit_service import log_action
from app.utils.auth import Modules
from app.utils.dependencies import (
    get_current_user, require_feature_permission, require_feature_permission_any,
)
from config.database import get_db

router = APIRouter()


def _patient_name(patient: Optional[Patient]) -> Optional[str]:
    if not patient:
        return None
    return f"{patient.first_name} {patient.last_name}".strip()


def _case_or_404(db: Session, case_id: int, hospital_id: int) -> ArtCase:
    case = db.query(ArtCase).filter(ArtCase.id == case_id, ArtCase.hospital_id == hospital_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="ART case not found.")
    return case


def _cycle_or_404(db: Session, cycle_id: int, hospital_id: int) -> ArtCycle:
    cycle = db.query(ArtCycle).filter(ArtCycle.id == cycle_id, ArtCycle.hospital_id == hospital_id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="ART cycle not found.")
    return cycle


def _audit(db, user, action, resource_type, resource_id, description):
    log_action(
        db, user=user, action=action, category="art",
        resource_type=resource_type, resource_id=resource_id, description=description,
    )


class CentreUpdate(BaseModel):
    clinic_level: int = Field(..., ge=1, le=2)
    clinic_registration_no: Optional[str] = None
    clinic_valid_until: Optional[date] = None
    director_name: Optional[str] = None
    bank_enabled: bool = True
    bank_registration_no: Optional[str] = None
    bank_valid_until: Optional[date] = None


class ServiceIn(BaseModel):
    code: str
    name: str
    category: str = "procedure"
    default_price: float = 0
    requires_level: int = 1


class PackageIn(BaseModel):
    name: str
    code: Optional[str] = None
    price: float
    included_service_codes: List[str] = []
    includes_medicines: bool = False
    medicine_limit: float = 0
    cancel_keep_amount: float = 0
    description: Optional[str] = None


class CaseIn(BaseModel):
    case_type: str
    woman_patient_id: int
    partner_patient_id: Optional[int] = None


class WorkupIn(BaseModel):
    infertility_years: Optional[float] = None
    prior_pregnancies: Optional[int] = None
    prior_cycles: Optional[int] = None
    amh: Optional[float] = None
    antral_follicle_count: Optional[int] = None
    tubal_status: Optional[str] = None
    uterus_findings: Optional[str] = None
    semen_summary: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment_plan: Optional[str] = None


class NoteIn(BaseModel):
    note: str


class CycleIn(BaseModel):
    cycle_type: str
    protocol: Optional[str] = None
    clinician_id: Optional[int] = None
    billing_mode: str
    package_template_id: Optional[int] = None
    agreed_price: Optional[float] = None
    collect_advance: bool = False
    payment_method: str = "cash"


class BillingModeIn(BaseModel):
    billing_mode: str
    reason: str
    package_template_id: Optional[int] = None


class ChargeIn(BaseModel):
    service_code: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    kind: str = "service"


class CancelIn(BaseModel):
    reason: str


class StimIn(BaseModel):
    day_number: int
    drugs: list = []
    follicles_left: list = []
    follicles_right: list = []
    endometrium_mm: Optional[float] = None
    e2: Optional[float] = None
    lh: Optional[float] = None
    progesterone: Optional[float] = None
    notes: Optional[str] = None


class TriggerIn(BaseModel):
    drug: str
    trigger_at: datetime


class ConsentIn(BaseModel):
    form_code: str
    signed_by_name: str
    cycle_id: Optional[int] = None


class ApptIn(BaseModel):
    case_id: int
    cycle_id: Optional[int] = None
    kind: str
    scheduled_date: str
    scheduled_time: Optional[str] = None
    room: Optional[str] = None
    clinician_id: Optional[int] = None
    notes: Optional[str] = None


class TimeoutIn(BaseModel):
    patient_name: str
    dob_confirmed: bool
    witness_id: int


class QueueIn(BaseModel):
    case_id: int
    queue_date: Optional[date] = None


class WitnessBody(BaseModel):
    operator_id: int
    witness_id: int


class RetrievalIn(WitnessBody):
    follicles_aspirated: int = 0
    oocytes_retrieved: int = 0
    mature_mii: int = 0
    intermediate_mi: int = 0
    immature_gv: int = 0


class FertIn(WitnessBody):
    method: str
    oocytes_inseminated: int = 0
    normally_fertilised: int = 0
    media_lots: list = []


class SpecimenIn(BaseModel):
    sample_type: str


class GradeIn(BaseModel):
    day: int
    grade: str
    stage: Optional[str] = None


class DisposeIn(WitnessBody):
    disposition: str
    tank: Optional[str] = None
    canister: Optional[str] = None
    cane: Optional[str] = None
    position: Optional[str] = None
    renewal_due: Optional[str] = None
    oncofertility: bool = False


class RenewIn(BaseModel):
    renewal_due: date
    oncofertility: Optional[bool] = None


class ThawIn(WitnessBody):
    survived: bool = True
    clinician_id: Optional[int] = None
    billing_mode: str = "itemised"
    package_template_id: Optional[int] = None


class OwnerIn(BaseModel):
    case_id: int


class TankIn(BaseModel):
    tank_name: str
    nitrogen_level: Optional[str] = None
    temperature_c: Optional[float] = None
    alarm: bool = False


class PartnerIn(BaseModel):
    name: str
    registration_no: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None


class DonorIn(BaseModel):
    donor_type: str
    legal_name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[date] = None


class ScreeningIn(BaseModel):
    hiv: str
    hbsag: str
    hcv: str
    vdrl: str


class InsuranceIn(BaseModel):
    policy_no: str
    valid_until: date
    amount: float


class DonorRetrievalIn(BaseModel):
    oocytes_retrieved: int


class BankUnitIn(BaseModel):
    donor_id: int
    sample_code: str
    tank: Optional[str] = None
    canister: Optional[str] = None
    cane: Optional[str] = None
    position: Optional[str] = None


class IssueIn(WitnessBody):
    destination: str
    case_id: Optional[int] = None
    cycle_id: Optional[int] = None
    external_clinic_name: Optional[str] = None


class ReceiveIn(WitnessBody):
    partner_bank_id: int
    donor_code: str
    sample_code: str
    sample_type: str
    case_id: Optional[int] = None
    cycle_id: Optional[int] = None


class OutcomeIn(BaseModel):
    beta_hcg_value: Optional[float] = None
    beta_hcg_positive: Optional[bool] = None
    clinical_pregnancy: Optional[bool] = None
    miscarriage: Optional[bool] = None
    live_birth: Optional[bool] = None
    outcome_notes: Optional[str] = None
    complication: Optional[str] = None


class EquipmentIn(BaseModel):
    name: str
    asset_code: Optional[str] = None
    location: Optional[str] = None
    installed_on: Optional[date] = None
    last_change_on: Optional[date] = None
    change_note: Optional[str] = None
    status: str = "active"


class GrievanceIn(BaseModel):
    complainant_name: str
    summary: str
    opened_on: Optional[date] = None


class GrievanceClose(BaseModel):
    resolution: str


def _centre_dict(db, centre) -> dict:
    return {
        "id": centre.id,
        "clinic_level": centre.clinic_level,
        "clinic_registration_no": centre.clinic_registration_no,
        "clinic_valid_until": centre.clinic_valid_until.isoformat() if centre.clinic_valid_until else None,
        "director_name": centre.director_name,
        "bank_enabled": centre.bank_enabled,
        "bank_registration_no": centre.bank_registration_no,
        "bank_valid_until": centre.bank_valid_until.isoformat() if centre.bank_valid_until else None,
        "lab_enabled": int(centre.clinic_level or 1) >= 2 and level2_licensed(db),
    }


@router.get("/centre")
def read_centre(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_art")),
):
    centre = get_centre(db, user.hospital_id)
    db.commit()
    return _centre_dict(db, centre)


@router.put("/centre")
def update_centre(
    body: CentreUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_centre")),
):
    centre = get_centre(db, user.hospital_id)
    for field, value in body.model_dump().items():
        setattr(centre, field, value)
    db.commit()
    _audit(db, user, "update_art_centre", "art_centre", centre.id, f"Level {centre.clinic_level}")
    return _centre_dict(db, centre)


@router.get("/services")
def list_services(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_art")),
):
    rows = db.query(ArtService).filter(ArtService.hospital_id == user.hospital_id).all()
    return [
        {"id": r.id, "code": r.code, "name": r.name, "category": r.category,
         "default_price": r.default_price, "requires_level": r.requires_level, "is_active": r.is_active}
        for r in rows
    ]


@router.post("/services")
def create_service(
    body: ServiceIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_catalog")),
):
    row = ArtService(hospital_id=user.hospital_id, **body.model_dump())
    db.add(row)
    db.commit()
    _audit(db, user, "create_art_service", "art_service", row.id, row.code)
    return {"id": row.id, "code": row.code}


@router.get("/packages")
def list_packages(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_art")),
):
    rows = db.query(ArtPackageTemplate).filter(ArtPackageTemplate.hospital_id == user.hospital_id).all()
    return [
        {
            "id": r.id, "name": r.name, "code": r.code, "price": r.price,
            "included_service_codes": r.included_service_codes or [],
            "includes_medicines": r.includes_medicines,
            "medicine_limit": r.medicine_limit,
            "cancel_keep_amount": r.cancel_keep_amount,
            "is_active": r.is_active,
        }
        for r in rows
    ]


@router.post("/packages")
def create_package(
    body: PackageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_packages")),
):
    row = ArtPackageTemplate(hospital_id=user.hospital_id, **body.model_dump())
    db.add(row)
    db.commit()
    _audit(db, user, "create_art_package", "art_package", row.id, row.name)
    return {"id": row.id, "name": row.name}


def _case_dict(case: ArtCase) -> dict:
    return {
        "id": case.id,
        "case_number": case.case_number,
        "case_type": case.case_type,
        "status": case.status,
        "woman_patient_id": case.woman_patient_id,
        "woman_name": _patient_name(case.woman),
        "partner_patient_id": case.partner_patient_id,
        "partner_name": _patient_name(case.partner),
        "opened_at": case.opened_at.isoformat() if case.opened_at else None,
    }


@router.get("/cases")
def list_cases(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_art")),
):
    rows = db.query(ArtCase).filter(ArtCase.hospital_id == user.hospital_id).order_by(ArtCase.id.desc()).all()
    return [_case_dict(r) for r in rows]


@router.post("/cases")
def create_case(
    body: CaseIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "register_cases")),
):
    if body.case_type not in ("couple", "single_woman"):
        raise HTTPException(status_code=400, detail="Case type must be couple or single_woman.")
    woman = db.query(Patient).filter(Patient.id == body.woman_patient_id, Patient.hospital_id == user.hospital_id).first()
    if not woman:
        raise HTTPException(status_code=404, detail="Woman patient was not found in this hospital.")
    if body.case_type == "couple" and not body.partner_patient_id:
        raise HTTPException(status_code=400, detail="A couple case needs the partner's patient record.")
    if body.partner_patient_id:
        partner = db.query(Patient).filter(Patient.id == body.partner_patient_id, Patient.hospital_id == user.hospital_id).first()
        if not partner:
            raise HTTPException(status_code=404, detail="Partner patient was not found in this hospital.")
    from app.services.art_ops import _next_number
    case = ArtCase(
        hospital_id=user.hospital_id,
        case_number=_next_number(db, ArtCase, "case_number", user.hospital_id, f"ART-{user.hospital_id}-"),
        case_type=body.case_type,
        woman_patient_id=body.woman_patient_id,
        partner_patient_id=body.partner_patient_id,
        opened_by_id=user.id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    _audit(db, user, "create_art_case", "art_case", case.id, case.case_number)
    return _case_dict(case)


@router.get("/cases/{case_id}")
def read_case(
    case_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_art")),
):
    case = _case_or_404(db, case_id, user.hospital_id)
    workup = case.workup
    notes = db.query(ArtCounsellorNote).filter(ArtCounsellorNote.case_id == case.id).all()
    consents = db.query(ArtConsent).filter(ArtConsent.case_id == case.id).all()
    cycles = db.query(ArtCycle).filter(ArtCycle.case_id == case.id).order_by(ArtCycle.id).all()
    data = _case_dict(case)
    data["workup"] = None if not workup else {
        "infertility_years": workup.infertility_years,
        "prior_pregnancies": workup.prior_pregnancies,
        "prior_cycles": workup.prior_cycles,
        "amh": workup.amh,
        "antral_follicle_count": workup.antral_follicle_count,
        "tubal_status": workup.tubal_status,
        "uterus_findings": workup.uterus_findings,
        "semen_summary": workup.semen_summary,
        "diagnosis": workup.diagnosis,
        "treatment_plan": workup.treatment_plan,
    }
    data["notes"] = [{"id": n.id, "note": n.note, "created_at": n.created_at.isoformat() if n.created_at else None} for n in notes]
    data["consents"] = [
        {"id": c.id, "form_code": c.form_code, "signed_by_name": c.signed_by_name,
         "withdrawn_at": c.withdrawn_at.isoformat() if c.withdrawn_at else None}
        for c in consents
    ]
    data["cycles"] = [_cycle_dict(c) for c in cycles]
    return data


@router.put("/cases/{case_id}/workup")
def save_workup(
    case_id: int,
    body: WorkupIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "edit_workup")),
):
    case = _case_or_404(db, case_id, user.hospital_id)
    workup = case.workup or ArtWorkup(case_id=case.id)
    for field, value in body.model_dump().items():
        setattr(workup, field, value)
    workup.updated_by_id = user.id
    db.add(workup)
    db.commit()
    _audit(db, user, "save_art_workup", "art_case", case.id, case.case_number)
    return {"ok": True}


@router.post("/cases/{case_id}/notes")
def add_note(
    case_id: int,
    body: NoteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "record_counsellor_note")),
):
    case = _case_or_404(db, case_id, user.hospital_id)
    note = ArtCounsellorNote(case_id=case.id, note=body.note.strip(), author_id=user.id)
    db.add(note)
    db.commit()
    _audit(db, user, "art_counsellor_note", "art_case", case.id, case.case_number)
    return {"id": note.id}


@router.post("/cases/{case_id}/documents")
async def upload_document(
    case_id: int,
    document_type: str = Form("report"),
    document_name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "upload_documents")),
):
    from app.utils.paths import get_uploads_dir
    case = _case_or_404(db, case_id, user.hospital_id)
    folder = os.path.join(get_uploads_dir(), "art_docs")
    os.makedirs(folder, exist_ok=True)
    stored = f"{uuid.uuid4().hex}_{file.filename}"
    full = os.path.join(folder, stored)
    content = await file.read()
    with open(full, "wb") as handle:
        handle.write(content)
    row = ArtDocument(
        hospital_id=user.hospital_id,
        case_id=case.id,
        document_type=document_type,
        document_name=document_name,
        file_name=file.filename or stored,
        file_path=os.path.join("art_docs", stored),
        file_size=len(content),
        mime_type=file.content_type,
        uploaded_by_id=user.id,
    )
    db.add(row)
    db.commit()
    _audit(db, user, "upload_art_document", "art_document", row.id, document_name)
    return {"id": row.id, "document_name": row.document_name}


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_art")),
):
    from app.utils.paths import get_uploads_dir
    row = db.query(ArtDocument).filter(ArtDocument.id == document_id, ArtDocument.hospital_id == user.hospital_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Document not found.")
    full = os.path.join(get_uploads_dir(), row.file_path)
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="File is missing from storage.")
    return FileResponse(full, filename=row.file_name)


@router.get("/consent-forms")
def consent_forms(user: User = Depends(require_feature_permission(Modules.ART, "view_art"))):
    return [{"code": code, "label": label} for code, label in CONSENT_FORMS]


@router.post("/cases/{case_id}/consents")
def add_consent(
    case_id: int,
    body: ConsentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "record_consent")),
):
    case = _case_or_404(db, case_id, user.hospital_id)
    row = record_consent(db, case, body.form_code, body.signed_by_name, user, body.cycle_id)
    db.commit()
    _audit(db, user, "record_art_consent", "art_consent", row.id, body.form_code)
    return {"id": row.id, "form_code": row.form_code, "withdrawn": row.withdrawn_at is not None}


def _cycle_dict(cycle: ArtCycle) -> dict:
    return {
        "id": cycle.id,
        "case_id": cycle.case_id,
        "cycle_number": cycle.cycle_number,
        "cycle_type": cycle.cycle_type,
        "protocol": cycle.protocol,
        "status": cycle.status,
        "clinician_id": cycle.clinician_id,
        "donor_code": cycle.donor_code,
        "billing_mode": cycle.billing_mode,
        "agreed_price": cycle.agreed_price,
        "includes_medicines": cycle.includes_medicines,
        "included_service_codes": cycle.included_service_codes or [],
        "estimate_snapshot": cycle.estimate_snapshot,
        "advance_bill_id": cycle.advance_bill_id,
        "billing_mode_change_reason": cycle.billing_mode_change_reason,
        "trigger_drug": cycle.trigger_drug,
        "trigger_at": cycle.trigger_at.isoformat() if cycle.trigger_at else None,
        "cancel_reason": cycle.cancel_reason,
        "refund_bill_id": cycle.refund_bill_id,
        "culture_open": cycle.culture_open,
        "retrieval_oocytes": cycle.retrieval_oocytes,
        "fert_method": cycle.fert_method,
        "fert_normal": cycle.fert_normal,
        "linked_source_cycle_id": cycle.linked_source_cycle_id,
        "beta_hcg_positive": cycle.beta_hcg_positive,
        "clinical_pregnancy": cycle.clinical_pregnancy,
        "live_birth": cycle.live_birth,
        "complication": cycle.complication,
    }


@router.post("/cases/{case_id}/cycles")
def open_cycle(
    case_id: int,
    body: CycleIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "start_cycle")),
):
    case = _case_or_404(db, case_id, user.hospital_id)
    cycle = start_cycle(
        db, case, user,
        cycle_type=body.cycle_type, protocol=body.protocol, clinician_id=body.clinician_id,
        billing_mode=body.billing_mode, package_template_id=body.package_template_id,
        agreed_price=body.agreed_price, collect_advance=body.collect_advance,
        payment_method=body.payment_method,
    )
    db.commit()
    db.refresh(cycle)
    _audit(db, user, "start_art_cycle", "art_cycle", cycle.id, cycle.cycle_number)
    return _cycle_dict(cycle)


@router.get("/cycles/{cycle_id}")
def read_cycle(
    cycle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_art")),
):
    cycle = _cycle_or_404(db, cycle_id, user.hospital_id)
    days = db.query(ArtStimulationDay).filter(ArtStimulationDay.cycle_id == cycle.id).order_by(ArtStimulationDay.day_number).all()
    charges = db.query(ArtCharge).filter(ArtCharge.cycle_id == cycle.id).all()
    specimens = db.query(ArtSpecimen).filter(ArtSpecimen.origin_cycle_id == cycle.id).all()
    data = _cycle_dict(cycle)
    data["stimulation"] = [
        {
            "id": d.id, "day_number": d.day_number, "drugs": d.drugs or [],
            "follicles_left": d.follicles_left or [], "follicles_right": d.follicles_right or [],
            "endometrium_mm": d.endometrium_mm, "e2": d.e2, "lh": d.lh, "progesterone": d.progesterone,
            "notes": d.notes,
        }
        for d in days
    ]
    data["charges"] = [
        {"id": c.id, "description": c.description, "kind": c.kind, "amount": c.amount,
         "covered_by_package": c.covered_by_package, "bill_id": c.bill_id, "status": c.status}
        for c in charges
    ]
    data["specimens"] = [
        {"id": s.id, "code": s.code, "sample_type": s.sample_type, "disposition": s.disposition,
         "grades": s.grades or [], "tank": s.tank, "owner_case_id": s.owner_case_id,
         "oncofertility": s.oncofertility, "renewal_due": s.renewal_due.isoformat() if s.renewal_due else None}
        for s in specimens
    ]
    return data


@router.post("/cycles/{cycle_id}/billing-mode")
def update_billing_mode(
    cycle_id: int,
    body: BillingModeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "change_billing_mode")),
):
    cycle = _cycle_or_404(db, cycle_id, user.hospital_id)
    change_billing_mode(
        db, cycle, billing_mode=body.billing_mode, reason=body.reason,
        package_template_id=body.package_template_id,
    )
    db.commit()
    db.refresh(cycle)
    _audit(db, user, "change_art_billing_mode", "art_cycle", cycle.id, body.reason)
    return _cycle_dict(cycle)


@router.post("/cycles/{cycle_id}/charges")
def add_charge(
    cycle_id: int,
    body: ChargeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "start_cycle")),
):
    cycle = _cycle_or_404(db, cycle_id, user.hospital_id)
    charge = post_charge(
        db, cycle, user, service_code=body.service_code, description=body.description or "",
        amount=body.amount, kind=body.kind,
    )
    db.commit()
    return {
        "id": charge.id, "covered_by_package": charge.covered_by_package,
        "bill_id": charge.bill_id, "amount": charge.amount, "status": charge.status,
    }


@router.post("/cycles/{cycle_id}/cancel")
def cancel(
    cycle_id: int,
    body: CancelIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "issue_refunds")),
):
    cycle = _cycle_or_404(db, cycle_id, user.hospital_id)
    cancel_cycle(db, cycle, user, body.reason)
    db.commit()
    db.refresh(cycle)
    _audit(db, user, "cancel_art_cycle", "art_cycle", cycle.id, body.reason)
    return _cycle_dict(cycle)


@router.post("/cycles/{cycle_id}/stimulation")
def stimulation(
    cycle_id: int,
    body: StimIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "record_stimulation")),
):
    cycle = _cycle_or_404(db, cycle_id, user.hospital_id)
    day = add_stimulation(db, cycle, user, body.model_dump())
    db.commit()
    _audit(db, user, "art_stimulation", "art_cycle", cycle.id, f"day {day.day_number}")
    return {"id": day.id, "day_number": day.day_number}


@router.post("/cycles/{cycle_id}/trigger")
def trigger(
    cycle_id: int,
    body: TriggerIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "record_stimulation")),
):
    cycle = _cycle_or_404(db, cycle_id, user.hospital_id)
    set_trigger(db, cycle, body.drug, body.trigger_at)
    db.commit()
    _audit(db, user, "art_trigger", "art_cycle", cycle.id, body.drug)
    return {"status": cycle.status, "trigger_at": cycle.trigger_at.isoformat()}


@router.post("/cycles/{cycle_id}/outcome")
def outcome(
    cycle_id: int,
    body: OutcomeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "record_outcome")),
):
    cycle = _cycle_or_404(db, cycle_id, user.hospital_id)
    record_outcome(db, cycle, body.model_dump())
    db.commit()
    _audit(db, user, "art_outcome", "art_cycle", cycle.id, cycle.cycle_number)
    return _cycle_dict(cycle)


@router.get("/cycles/{cycle_id}/estimate.pdf")
def estimate_pdf(
    cycle_id: int,
    include_header: Optional[bool] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_art")),
):
    from app.utils.export_branding import hospital_brand_dict
    from app.utils.pdf_service import PDFService
    from app.utils.pdf_settings import pdf_gen_kwargs
    cycle = _cycle_or_404(db, cycle_id, user.hospital_id)
    snap = cycle.estimate_snapshot or {}
    rows = [
        {"item": "Billing mode", "detail": snap.get("billing_mode", cycle.billing_mode)},
        {"item": "Package", "detail": snap.get("package_name") or "—"},
        {"item": "Agreed price", "detail": f"{float(snap.get('agreed_price') or 0):.2f}"},
        {"item": "Included services", "detail": ", ".join(snap.get("included_service_codes") or []) or "—"},
        {"item": "Medicines", "detail": "Included" if snap.get("includes_medicines") else "Billed separately"},
        {"item": "Kept on cancellation", "detail": f"{float(snap.get('cancel_keep_amount') or 0):.2f}"},
    ]
    pdf = PDFService()
    buf = pdf.generate_pharmacy_report_pdf(
        title=f"ART ESTIMATE {cycle.cycle_number}",
        period=None,
        columns=[{"key": "item", "label": "Item"}, {"key": "detail", "label": "Detail"}],
        rows=rows,
        hospital_info=hospital_brand_dict(db, user.hospital_id),
        **pdf_gen_kwargs(db, user.hospital_id, "bill", query_include_header=include_header),
    )
    return Response(content=buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{cycle.cycle_number}-estimate.pdf"'})


@router.post("/appointments")
def create_appointment(
    body: ApptIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "schedule_procedures")),
):
    case = _case_or_404(db, body.case_id, user.hospital_id)
    row = book_appointment(db, case, user, body.model_dump())
    db.commit()
    _audit(db, user, "book_art_appointment", "art_appointment", row.id, row.kind)
    return {"id": row.id, "kind": row.kind, "status": row.status}


@router.post("/appointments/{appointment_id}/timeout")
def timeout(
    appointment_id: int,
    body: TimeoutIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission_any(Modules.ART, "schedule_procedures", "record_lab")),
):
    appt = db.query(ArtAppointment).filter(
        ArtAppointment.id == appointment_id, ArtAppointment.hospital_id == user.hospital_id,
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    record_timeout(db, appt, patient_name=body.patient_name, dob_confirmed=body.dob_confirmed, witness_id=body.witness_id)
    db.commit()
    _audit(db, user, "art_timeout", "art_appointment", appt.id, appt.kind)
    return {"timeout_at": appt.timeout_at.isoformat()}


@router.post("/appointments/{appointment_id}/complete")
def complete(
    appointment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission_any(Modules.ART, "schedule_procedures", "record_lab")),
):
    appt = db.query(ArtAppointment).filter(
        ArtAppointment.id == appointment_id, ArtAppointment.hospital_id == user.hospital_id,
    ).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    complete_appointment(db, appt)
    db.commit()
    _audit(db, user, "complete_art_appointment", "art_appointment", appt.id, appt.kind)
    return {"status": appt.status}


@router.post("/queue")
def queue_check_in(
    body: QueueIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "register_cases")),
):
    case = _case_or_404(db, body.case_id, user.hospital_id)
    row = check_in_queue(db, case, body.queue_date or date.today())
    db.commit()
    return {"id": row.id, "token_no": row.token_no, "queue_date": row.queue_date.isoformat()}


@router.get("/board")
def board(
    on: Optional[date] = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_art")),
):
    day = on or date.today()
    appointments = db.query(ArtAppointment).filter(
        ArtAppointment.hospital_id == user.hospital_id, ArtAppointment.scheduled_date == day,
    ).all()
    tokens = db.query(ArtQueueEntry).filter(
        ArtQueueEntry.hospital_id == user.hospital_id, ArtQueueEntry.queue_date == day,
    ).order_by(ArtQueueEntry.token_no).all()
    from app.models.billing import Bill
    pending = db.query(Bill).filter(
        Bill.hospital_id == user.hospital_id, Bill.bill_type == "art", Bill.status == "pending",
    ).count()
    soon = day.toordinal()
    renewals = []
    for specimen in db.query(ArtSpecimen).filter(ArtSpecimen.hospital_id == user.hospital_id, ArtSpecimen.disposition == "frozen").all():
        if specimen.renewal_due and 0 <= (specimen.renewal_due.toordinal() - soon) <= 30:
            renewals.append({"code": specimen.code, "renewal_due": specimen.renewal_due.isoformat()})
    return {
        "date": day.isoformat(),
        "queue": [{"token_no": t.token_no, "case_id": t.case_id, "status": t.status} for t in tokens],
        "appointments": [
            {"id": a.id, "kind": a.kind, "case_id": a.case_id, "cycle_id": a.cycle_id,
             "status": a.status, "room": a.room, "timeout_done": bool(a.timeout_at)}
            for a in appointments
        ],
        "pending_art_bills": pending,
        "cryo_renewals": renewals,
    }


@router.post("/cycles/{cycle_id}/culture/open")
def culture_open(
    cycle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "record_lab")),
):
    cycle = _cycle_or_404(db, cycle_id, user.hospital_id)
    open_culture(db, cycle, user)
    db.commit()
    return {"culture_open": True}


@router.post("/cycles/{cycle_id}/culture/close")
def culture_close(
    cycle_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "record_lab")),
):
    cycle = _cycle_or_404(db, cycle_id, user.hospital_id)
    close_culture(db, cycle)
    db.commit()
    return {"culture_open": False}


@router.post("/cycles/{cycle_id}/retrieval")
def retrieval(
    cycle_id: int,
    body: RetrievalIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "record_lab")),
):
    cycle = _cycle_or_404(db, cycle_id, user.hospital_id)
    record_retrieval(db, cycle, user, body.model_dump())
    db.commit()
    _audit(db, user, "art_retrieval", "art_cycle", cycle.id, cycle.cycle_number)
    return {"oocytes_retrieved": cycle.retrieval_oocytes, "status": cycle.status}


@router.post("/cycles/{cycle_id}/fertilisation")
def fertilisation(
    cycle_id: int,
    body: FertIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "record_lab")),
):
    cycle = _cycle_or_404(db, cycle_id, user.hospital_id)
    record_fertilisation(db, cycle, body.model_dump())
    db.commit()
    _audit(db, user, "art_fertilisation", "art_cycle", cycle.id, body.method)
    return {"fert_method": cycle.fert_method, "fert_normal": cycle.fert_normal}


@router.post("/cycles/{cycle_id}/specimens")
def create_specimen(
    cycle_id: int,
    body: SpecimenIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "record_lab")),
):
    cycle = _cycle_or_404(db, cycle_id, user.hospital_id)
    row = add_specimen(db, cycle, user, body.model_dump())
    db.commit()
    return {"id": row.id, "code": row.code, "owner_case_id": row.owner_case_id}


@router.post("/specimens/{specimen_id}/grade")
def grade(
    specimen_id: int,
    body: GradeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "record_lab")),
):
    specimen = db.query(ArtSpecimen).filter(ArtSpecimen.id == specimen_id, ArtSpecimen.hospital_id == user.hospital_id).first()
    if not specimen:
        raise HTTPException(status_code=404, detail="Specimen not found.")
    grade_specimen(db, specimen, day=body.day, grade=body.grade, stage=body.stage)
    db.commit()
    return {"grades": specimen.grades}


@router.post("/specimens/{specimen_id}/dispose")
def dispose(
    specimen_id: int,
    body: DisposeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "record_lab")),
):
    specimen = db.query(ArtSpecimen).filter(ArtSpecimen.id == specimen_id, ArtSpecimen.hospital_id == user.hospital_id).first()
    if not specimen:
        raise HTTPException(status_code=404, detail="Specimen not found.")
    dispose_specimen(db, specimen, body.model_dump())
    db.commit()
    _audit(db, user, "art_dispose", "art_specimen", specimen.id, body.disposition)
    return {"disposition": specimen.disposition, "tank": specimen.tank}


@router.post("/specimens/{specimen_id}/renew")
def renew(
    specimen_id: int,
    body: RenewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_cryo")),
):
    specimen = db.query(ArtSpecimen).filter(ArtSpecimen.id == specimen_id, ArtSpecimen.hospital_id == user.hospital_id).first()
    if not specimen:
        raise HTTPException(status_code=404, detail="Specimen not found.")
    renew_storage(db, specimen, renewal_due=body.renewal_due, oncofertility=body.oncofertility)
    db.commit()
    return {"renewal_due": specimen.renewal_due.isoformat(), "oncofertility": specimen.oncofertility}


@router.post("/specimens/{specimen_id}/thaw")
def thaw(
    specimen_id: int,
    body: ThawIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "record_lab")),
):
    specimen = db.query(ArtSpecimen).filter(ArtSpecimen.id == specimen_id, ArtSpecimen.hospital_id == user.hospital_id).first()
    if not specimen:
        raise HTTPException(status_code=404, detail="Specimen not found.")
    cycle = thaw_specimen(db, specimen, user, body.model_dump())
    db.commit()
    db.refresh(cycle)
    _audit(db, user, "art_thaw", "art_specimen", specimen.id, cycle.cycle_number)
    return {"cycle_id": cycle.id, "cycle_number": cycle.cycle_number, "cycle_type": cycle.cycle_type, "survived": specimen.thaw_survived}


@router.post("/specimens/{specimen_id}/owner")
def move_owner(
    specimen_id: int,
    body: OwnerIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_cryo")),
):
    specimen = db.query(ArtSpecimen).filter(ArtSpecimen.id == specimen_id, ArtSpecimen.hospital_id == user.hospital_id).first()
    if not specimen:
        raise HTTPException(status_code=404, detail="Specimen not found.")
    reject_owner_change()


@router.post("/cryo/tank-log")
def tank_log(
    body: TankIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_cryo")),
):
    row = ArtTankLog(hospital_id=user.hospital_id, recorded_by_id=user.id, **body.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id, "alarm": row.alarm}


@router.get("/partner-banks")
def list_partners(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_art")),
):
    rows = db.query(ArtPartnerBank).filter(ArtPartnerBank.hospital_id == user.hospital_id).all()
    return [{"id": r.id, "name": r.name, "registration_no": r.registration_no, "city": r.city} for r in rows]


@router.post("/partner-banks")
def create_partner(
    body: PartnerIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_donors")),
):
    row = ArtPartnerBank(hospital_id=user.hospital_id, **body.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id, "name": row.name}


@router.get("/donors/codes")
def donor_codes(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_art")),
):
    rows = db.query(ArtDonor).filter(ArtDonor.hospital_id == user.hospital_id).all()
    return [donor_public(r) for r in rows]


@router.get("/donors")
def list_donors(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_donor_identity")),
):
    rows = db.query(ArtDonor).filter(ArtDonor.hospital_id == user.hospital_id).all()
    return [donor_private(r) for r in rows]


@router.post("/donors")
def add_donor(
    body: DonorIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_donors")),
):
    donor = create_donor(db, user.hospital_id, body.model_dump())
    db.commit()
    db.refresh(donor)
    _audit(db, user, "create_art_donor", "art_donor", donor.id, donor.donor_code)
    return donor_private(donor)


@router.post("/donors/{donor_id}/screening")
def screen_donor(
    donor_id: int,
    body: ScreeningIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_donors")),
):
    donor = db.query(ArtDonor).filter(ArtDonor.id == donor_id, ArtDonor.hospital_id == user.hospital_id).first()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found.")
    donor.screening = body.model_dump()
    db.commit()
    return {"screening_complete": donor_public(donor)["screening_complete"]}


@router.post("/donors/{donor_id}/insurance")
def insure_donor(
    donor_id: int,
    body: InsuranceIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_donors")),
):
    donor = db.query(ArtDonor).filter(ArtDonor.id == donor_id, ArtDonor.hospital_id == user.hospital_id).first()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found.")
    donor.insurance_policy_no = body.policy_no
    donor.insurance_valid_until = body.valid_until
    donor.insurance_amount = body.amount
    db.commit()
    return {"insurance_on_file": True}


@router.post("/donors/{donor_id}/clear")
def mark_donor_clear(
    donor_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_donors")),
):
    donor = db.query(ArtDonor).filter(ArtDonor.id == donor_id, ArtDonor.hospital_id == user.hospital_id).first()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found.")
    clear_donor(db, donor)
    db.commit()
    _audit(db, user, "clear_art_donor", "art_donor", donor.id, donor.donor_code)
    return {"status": donor.status}


@router.post("/donors/{donor_id}/retrieval")
def donor_retrieval(
    donor_id: int,
    body: DonorRetrievalIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_donors")),
):
    donor = db.query(ArtDonor).filter(ArtDonor.id == donor_id, ArtDonor.hospital_id == user.hospital_id).first()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found.")
    record_donor_retrieval(db, donor, body.oocytes_retrieved)
    db.commit()
    return {"oocytes_retrieved": donor.oocytes_retrieved, "over_intended_cap": donor.over_intended_cap}


@router.post("/bank/units")
def create_unit(
    body: BankUnitIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_donors")),
):
    unit = store_bank_unit(db, user.hospital_id, body.model_dump())
    db.commit()
    return {"id": unit.id, "sample_code": unit.sample_code, "status": unit.status}


@router.post("/bank/units/{unit_id}/issue")
def issue(
    unit_id: int,
    body: IssueIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "issue_gametes")),
):
    unit = db.query(ArtBankUnit).filter(ArtBankUnit.id == unit_id, ArtBankUnit.hospital_id == user.hospital_id).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Bank unit not found.")
    issue_unit(db, unit, body.model_dump())
    db.commit()
    cycle = db.query(ArtCycle).filter(ArtCycle.id == unit.cycle_id).first() if unit.cycle_id else None
    _audit(db, user, "issue_art_unit", "art_bank_unit", unit.id, unit.status)
    return {
        "status": unit.status,
        "donor_code": cycle.donor_code if cycle else None,
        "external_clinic_name": unit.external_clinic_name,
    }


@router.post("/bank/receive")
def receive(
    body: ReceiveIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "receive_shipment")),
):
    unit = receive_external(db, user.hospital_id, body.model_dump())
    db.commit()
    _audit(db, user, "receive_art_shipment", "art_bank_unit", unit.id, unit.external_donor_code)
    return {"id": unit.id, "donor_code": unit.external_donor_code, "status": unit.status}


@router.get("/registry")
def registry(
    year: int,
    month: int,
    format: str = "json",
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_reports")),
):
    data = registry_export(db, user.hospital_id, year, month)
    if format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["section", "key", "value"])
        clinic = data["clinic"]
        writer.writerow(["clinic", "enrolments", clinic["enrolments"]])
        for key, value in clinic["procedures"].items():
            writer.writerow(["clinic", f"procedure_{key}", value])
        writer.writerow(["clinic", "outcomes", clinic["outcomes"]])
        writer.writerow([
            "clinic", "complications",
            ";".join(item["complication"] for item in clinic["complications"]),
        ])
        for key, value in data["bank"].items():
            writer.writerow(["bank", key, value])
        return Response(content=buffer.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="art-registry-{year}-{month:02d}.csv"'})
    return data


@router.get("/reports/outcomes")
def outcomes(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_reports")),
):
    return outcome_report(db, user.hospital_id)


@router.get("/reports/lab-kpis")
def kpis(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_reports")),
):
    assert_level2(db, user.hospital_id)
    return lab_kpis(db, user.hospital_id)


@router.get("/equipment")
def list_equipment(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_art")),
):
    rows = db.query(ArtEquipment).filter(ArtEquipment.hospital_id == user.hospital_id).all()
    return [
        {"id": r.id, "name": r.name, "asset_code": r.asset_code, "status": r.status,
         "installed_on": r.installed_on.isoformat() if r.installed_on else None,
         "last_change_on": r.last_change_on.isoformat() if r.last_change_on else None,
         "change_note": r.change_note}
        for r in rows
    ]


@router.post("/equipment")
def add_equipment(
    body: EquipmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_equipment")),
):
    row = ArtEquipment(hospital_id=user.hospital_id, **body.model_dump())
    db.add(row)
    db.commit()
    return {"id": row.id}


@router.patch("/equipment/{equipment_id}")
def patch_equipment(
    equipment_id: int,
    body: EquipmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_equipment")),
):
    row = db.query(ArtEquipment).filter(ArtEquipment.id == equipment_id, ArtEquipment.hospital_id == user.hospital_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Equipment not found.")
    for field, value in body.model_dump().items():
        setattr(row, field, value)
    db.commit()
    return {"id": row.id, "change_note": row.change_note}


@router.get("/grievances")
def list_grievances(
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "view_art")),
):
    rows = db.query(ArtGrievance).filter(ArtGrievance.hospital_id == user.hospital_id).all()
    return [
        {"id": r.id, "reference": r.reference, "complainant_name": r.complainant_name,
         "summary": r.summary, "status": r.status, "resolution": r.resolution}
        for r in rows
    ]


@router.post("/grievances")
def add_grievance(
    body: GrievanceIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_grievances")),
):
    from app.services.art_ops import _next_number
    row = ArtGrievance(
        hospital_id=user.hospital_id,
        reference=_next_number(db, ArtGrievance, "reference", user.hospital_id, f"GRV-{user.hospital_id}-"),
        opened_on=body.opened_on or date.today(),
        complainant_name=body.complainant_name,
        summary=body.summary,
    )
    db.add(row)
    db.commit()
    return {"id": row.id, "reference": row.reference, "status": row.status}


@router.post("/grievances/{grievance_id}/close")
def close_grievance(
    grievance_id: int,
    body: GrievanceClose,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature_permission(Modules.ART, "manage_grievances")),
):
    row = db.query(ArtGrievance).filter(ArtGrievance.id == grievance_id, ArtGrievance.hospital_id == user.hospital_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Grievance not found.")
    row.status = "closed"
    row.resolution = body.resolution
    row.closed_on = date.today()
    db.commit()
    return {"status": row.status, "resolution": row.resolution}
