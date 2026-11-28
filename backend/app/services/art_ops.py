"""Fertility (ART) rules: billing modes, consent gates, Level 2 licence, bank identity."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
import uuid
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.art import (
    ArtAppointment, ArtBankUnit, ArtCase, ArtCentre, ArtCharge, ArtConsent,
    ArtCycle, ArtDonor, ArtPackageTemplate, ArtQueueEntry, ArtService, ArtSpecimen,
    ArtStimulationDay, ArtWitnessLog,
)
from app.models.billing import Bill, BillItem, Payment
from app.models.patient import Patient
from app.models.user import User

LEVEL2_CYCLE_TYPES = {"ivf", "icsi", "freeze_all", "fet", "oocyte_freeze"}
CYCLE_TYPES = {
    "oi", "iui_husband", "iui_donor", "ivf", "icsi", "freeze_all", "fet", "oocyte_freeze", "sperm_freeze",
}
IUI_CYCLES = {"iui_husband", "iui_donor"}
EGG_CYCLES = {"ivf", "icsi", "freeze_all", "oocyte_freeze"}
FERT_CYCLES = {"ivf", "icsi", "freeze_all"}
TRANSFER_CYCLES = {"ivf", "icsi", "fet"}
NO_PREGNANCY_CYCLES = {"freeze_all", "oocyte_freeze", "sperm_freeze"}
APPOINTMENT_KINDS = {"scan", "iui", "counsellor", "opu", "transfer", "beta_hcg"}
APPOINTMENT_CYCLES = {"iui": IUI_CYCLES, "opu": EGG_CYCLES, "transfer": TRANSFER_CYCLES}
STATUS_RANK = {
    "planned": 0, "stimulation": 1, "triggered": 2, "retrieval": 3, "fertilisation": 4,
    "culture": 5, "transfer": 6, "luteal": 7, "outcome": 8,
}


def require_open(cycle: ArtCycle) -> None:
    if cycle.status == "cancelled":
        raise HTTPException(status_code=400, detail="This cycle is cancelled.")
    if cycle.status == "outcome":
        raise HTTPException(status_code=400, detail="The outcome is recorded. This cycle is closed.")


def advance(cycle: ArtCycle, status: str) -> None:
    """Move the cycle forward. A later step never moves it back."""
    if STATUS_RANK.get(status, 0) > STATUS_RANK.get(cycle.status, 0):
        cycle.status = status


def _count(value) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Counts must be whole numbers.")
    if number < 0:
        raise HTTPException(status_code=400, detail="Counts cannot be negative.")
    return number
LEVEL2_APPOINTMENT_KINDS = {"opu", "transfer"}
TIMEOUT_KINDS = {"iui", "opu", "transfer"}
SCREENING_KEYS = ("hiv", "hbsag", "hcv", "vdrl")
CLEAR_VALUE = "non_reactive"

CONSENT_FORMS = (
    ("couple_treatment", "Couple or woman consent before treatment"),
    ("iui_husband", "IUI with husband's semen"),
    ("iui_donor", "IUI with donor semen"),
    ("embryo_freeze", "Freezing of embryos"),
    ("gamete_freeze", "Freezing of gametes"),
    ("parental_assent", "Parental assent for gamete freezing"),
    ("oocyte_retrieval", "Oocyte retrieval"),
    ("donor_sperm", "Donor of sperm"),
    ("donor_oocyte", "Donor of oocytes"),
    ("death_incapacity", "Cryostorage if a party dies or becomes incapacitated"),
    ("withdrawal", "Withdrawal of consent"),
    ("discard", "Discard of gametes or embryos"),
)

PROCEDURE_CONSENT = {
    "iui_husband": "iui_husband",
    "iui_donor": "iui_donor",
    "opu": "oocyte_retrieval",
    "transfer": "couple_treatment",
    "discard_embryo": "discard",
    "discard_gamete": "discard",
    "freeze_embryo": "embryo_freeze",
    "freeze_gamete": "gamete_freeze",
}

# The donor's own consent is printed from the bank file, where the legal name is kept.
DONOR_CONSENT_CODES = {"donor_sperm": "sperm", "donor_oocyte": "oocyte"}

CONSENT_BODY = {
    "couple_treatment": [
        "We have been told, in language we understand, what this treatment involves, the chance of a pregnancy, and the main risks. Those risks include no pregnancy, a multiple pregnancy, infection, bleeding, and ovarian hyperstimulation.",
        "We agree to treatment at this registered clinic. The sex of an embryo will not be selected.",
        "We may withdraw this consent before the procedure. Once an embryo has been created, withdrawal follows the written instructions already given for storage or discard.",
    ],
    "iui_husband": [
        "I agree to intrauterine insemination using sperm from the husband or partner named on this form, after the sample is prepared.",
        "This does not guarantee a pregnancy. The sample is used only for the people named here.",
    ],
    "iui_donor": [
        "We agree to intrauterine insemination with donor sperm. The donor is identified on this chart only by a donor code. We will not be told the donor's name, and the donor will not be told ours.",
        "The donor has no parental rights over a child born from this treatment. The sample is used only after the required infection screen is clear.",
    ],
    "embryo_freeze": [
        "We agree that embryos from this treatment may be frozen and stored at this clinic.",
        "Storage is reviewed every year. Unused embryos cannot be given to another couple. If storage is not renewed, or if we sign a discard form, the clinic follows that instruction.",
        "What should happen if one of us dies or cannot decide is written on the separate storage form. That form is part of this consent.",
    ],
    "gamete_freeze": [
        "I agree that my eggs or sperm may be frozen and stored at this clinic.",
        "They will not be used to create an embryo, and will not be given to anyone else, unless I sign a later consent that says so.",
        "Storage is reviewed every year. Samples kept because of cancer treatment may be stored for the longer period allowed for that purpose.",
    ],
    "parental_assent": [
        "I am the parent or lawful guardian of the person named on this form. I agree that their eggs or sperm may be frozen before treatment that may affect their fertility.",
        "The samples stay in that person's name. They are not used, and not given to anyone else, unless that person signs their own consent when they are able to decide.",
    ],
    "oocyte_retrieval": [
        "I agree to egg collection under anaesthesia or sedation, as explained to me.",
        "I understand the risks, including bleeding, infection, injury to nearby organs, and a reaction to the medicines.",
        "The number of eggs collected is written on the procedure record. Eggs are not used except as this consent, and any later consent, allow.",
    ],
    "donor_sperm": [
        "I am donating sperm to this registered bank. I have completed the infection screen required before a donation can be cleared.",
        "I give up any claim to be treated as a parent of a child born from this donation. My name stays in the bank file. The recipient's chart shows only my donor code.",
        "I may withdraw this consent before a sample is issued.",
    ],
    "donor_oocyte": [
        "I am donating eggs to this registered bank. I have been told about the stimulation medicines and about egg collection, including the risks.",
        "Insurance for this donation covers at least 12 months from the collection. I have been told the intended number of eggs is not more than 7. The number actually collected is still recorded.",
        "I give up any claim to be treated as a parent of a child born from these eggs. My name stays in the bank file. The recipient's chart shows only my donor code.",
        "I may withdraw this consent before the eggs are collected.",
    ],
    "death_incapacity": [
        "If one of the people named here dies, or cannot decide, the stored eggs, sperm, or embryos are handled as marked below.",
        "This instruction does not allow the samples to be given to a different couple.",
    ],
    "withdrawal": [
        "We withdraw the consents previously signed for this case.",
        "Withdrawal applies to treatment that has not yet been carried out. Embryos already created are handled under the storage and discard instructions already signed.",
    ],
    "discard": [
        "We instruct this clinic to discard the eggs, sperm, or embryos identified on this form.",
        "Once discarded they cannot be restored. They will not be used for treatment and will not be given to anyone else.",
    ],
}

DEATH_CHOICES = [
    "Continue storage until the renewal date",
    "Discard the stored samples",
    "Use them only as both people have already agreed in writing",
]


def _age_years(born, stored_age) -> str:
    if born:
        today = date.today()
        years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        return str(years)
    if stored_age is not None:
        return str(stored_age)
    return ""


def _patient_address(patient: Patient) -> str:
    parts = [
        patient.address_line1, patient.address_line2, patient.village,
        patient.mandal, patient.district,
    ]
    joined = ", ".join(part.strip() for part in parts if part and str(part).strip())
    if joined:
        return joined
    return (patient.address or "").strip()


def _person_fields(patient: Patient, role: str) -> list[tuple[str, str]]:
    rows = [(role, f"{patient.first_name} {patient.last_name}".strip())]
    age = _age_years(patient.date_of_birth, patient.age)
    if age:
        rows.append(("Age", age))
    if patient.mrn:
        rows.append(("MRN", patient.mrn))
    if patient.primary_phone:
        rows.append(("Phone", patient.primary_phone))
    address = _patient_address(patient)
    if address:
        rows.append(("Address", address))
    return rows


def _clinic_fields(centre: ArtCentre, reference_label: str, reference: str) -> list[tuple[str, str]]:
    level = "IVF, ICSI, and the embryology lab" if centre.clinic_level >= 2 else "Investigations and IUI"
    rows = [
        ("Clinic registration", centre.clinic_registration_no or "Not recorded"),
        ("Clinic is registered for", level),
        ("Clinic director", centre.director_name or "Not recorded"),
        (reference_label, reference),
    ]
    if centre.bank_registration_no:
        rows.append(("Bank registration", centre.bank_registration_no))
    return rows


def case_consent_document(case: ArtCase, centre: ArtCentre, form_code: str) -> dict:
    """Unsigned consent for a couple or woman. Donor identity is not included."""
    if form_code in DONOR_CONSENT_CODES:
        raise HTTPException(
            status_code=400,
            detail="Download the donor's own consent from the donor bank. The donor's name is not kept on the patient chart.",
        )
    titles = dict(CONSENT_FORMS)
    if form_code not in titles:
        raise HTTPException(status_code=400, detail="Unknown consent form.")
    fields = _clinic_fields(centre, "Case number", case.case_number)
    fields.extend(_person_fields(case.woman, "Woman"))
    signers = [{"role": "Woman", "name": f"{case.woman.first_name} {case.woman.last_name}".strip()}]
    if case.case_type == "couple" and case.partner:
        fields.extend(_person_fields(case.partner, "Husband or partner"))
        signers.append({
            "role": "Husband or partner",
            "name": f"{case.partner.first_name} {case.partner.last_name}".strip(),
        })
    if form_code == "parental_assent":
        signers = [{"role": "Parent or guardian", "name": ""}]
    signers.extend([
        {"role": "Witness", "name": ""},
        {"role": "Doctor or counsellor", "name": ""},
    ])
    return {
        "title": titles[form_code],
        "reference": case.case_number,
        "fields": fields,
        "paragraphs": CONSENT_BODY[form_code],
        "choices": DEATH_CHOICES if form_code == "death_incapacity" else [],
        "signers": signers,
    }


def donor_consent_document(donor: ArtDonor, centre: ArtCentre) -> dict:
    form_code = "donor_oocyte" if donor.donor_type == "oocyte" else "donor_sperm"
    titles = dict(CONSENT_FORMS)
    fields = _clinic_fields(centre, "Donor code", donor.donor_code)
    fields.append(("Donor's name", donor.legal_name))
    age = _age_years(donor.date_of_birth, None)
    if age:
        fields.append(("Age", age))
    if donor.phone:
        fields.append(("Phone", donor.phone))
    if donor.address:
        fields.append(("Address", donor.address))
    return {
        "title": titles[form_code],
        "reference": donor.donor_code,
        "fields": fields,
        "paragraphs": CONSENT_BODY[form_code],
        "choices": [],
        "signers": [
            {"role": "Donor", "name": donor.legal_name},
            {"role": "Witness", "name": ""},
            {"role": "Bank officer", "name": ""},
        ],
    }


def level2_licensed(db: Session) -> bool:
    """Level 2 lab is open when no licence filter exists, or the grant lists art_lab."""
    from app.services.license_service import licensed_feature_names
    names = licensed_feature_names(db)
    if names is None:
        return True
    return "art_lab" in names


def get_centre(db: Session, hospital_id: int) -> ArtCentre:
    centre = db.query(ArtCentre).filter(ArtCentre.hospital_id == hospital_id).first()
    if not centre:
        centre = ArtCentre(hospital_id=hospital_id, clinic_level=1, bank_enabled=True)
        db.add(centre)
        db.flush()
    return centre


def assert_level2(db: Session, hospital_id: int) -> ArtCentre:
    centre = get_centre(db, hospital_id)
    if int(centre.clinic_level or 1) < 2:
        raise HTTPException(
            status_code=403,
            detail="This centre is registered as Level 1. IVF, ICSI, and embryo work need Level 2.",
        )
    if not level2_licensed(db):
        raise HTTPException(
            status_code=403,
            detail="The licence does not include the Level 2 ART lab (art_lab).",
        )
    return centre


def _as_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _next_number(db: Session, model, number_attr: str, hospital_id: int, prefix: str, exclude_id=None) -> str:
    column = getattr(model, number_attr)
    query = db.query(model).filter(model.hospital_id == hospital_id, column.like(f"{prefix}%"))
    if exclude_id is not None:
        query = query.filter(model.id != exclude_id)
    seq = 0
    for (value,) in query.with_entities(column).all():
        tail = (value or "").rsplit("-", 1)[-1]
        if tail.isdigit():
            seq = max(seq, int(tail))
    return f"{prefix}{seq + 1:05d}"


def placeholder() -> str:
    return f"TMP-{uuid.uuid4().hex}"


def assign_number(db: Session, row, number_attr: str, prefix: str) -> str:
    """Number a row after its INSERT has flushed.

    SQLite lets one writer hold the database at a time, so once our INSERT is in,
    no other request can commit until we do. Reading the highest number now cannot
    race with another request taking the same one.
    """
    db.flush()
    value = _next_number(db, type(row), number_attr, row.hospital_id, prefix, exclude_id=row.id)
    setattr(row, number_attr, value)
    db.flush()
    return value


def active_consent(db: Session, case_id: int, form_code: str) -> Optional[ArtConsent]:
    rows = (
        db.query(ArtConsent)
        .filter(ArtConsent.case_id == case_id, ArtConsent.form_code == form_code)
        .order_by(ArtConsent.id.desc())
        .all()
    )
    for row in rows:
        if row.withdrawn_at is None:
            return row
    return None


def require_consent(db: Session, case_id: int, form_code: str) -> ArtConsent:
    row = active_consent(db, case_id, form_code)
    if not row:
        raise HTTPException(
            status_code=400,
            detail=f"Procedure blocked. Active consent '{form_code}' is missing or was withdrawn.",
        )
    return row


def record_consent(db: Session, case: ArtCase, form_code: str, signed_by_name: str, user: User, cycle_id=None) -> ArtConsent:
    known = {code for code, _ in CONSENT_FORMS}
    if form_code not in known:
        raise HTTPException(status_code=400, detail="Unknown consent form.")
    row = ArtConsent(
        case_id=case.id,
        cycle_id=cycle_id,
        form_code=form_code,
        signed_by_name=signed_by_name.strip(),
        recorded_by_id=user.id,
    )
    db.add(row)
    db.flush()
    if form_code == "withdrawal":
        others = (
            db.query(ArtConsent)
            .filter(ArtConsent.case_id == case.id, ArtConsent.id != row.id, ArtConsent.withdrawn_at.is_(None))
            .all()
        )
        now = datetime.now()
        for other in others:
            other.withdrawn_at = now
    return row


def _daily_number(db: Session, model, attr: str, prefix: str, exclude_id: int) -> str:
    column = getattr(model, attr)
    seq = 0
    rows = db.query(column).filter(column.like(f"{prefix}%"), model.id != exclude_id).all()
    for (value,) in rows:
        tail = (value or "").rsplit("-", 1)[-1]
        if tail.isdigit():
            seq = max(seq, int(tail))
    return f"{prefix}{seq + 1:04d}"


def _number_bill(db: Session, bill: Bill) -> None:
    db.flush()
    bill.bill_number = _daily_number(db, Bill, "bill_number", f"ART-{datetime.now():%Y%m%d}-", bill.id)
    db.flush()


def _number_payment(db: Session, payment: Payment, kind: str = "PAY") -> None:
    db.flush()
    payment.payment_number = _daily_number(db, Payment, "payment_number", f"{kind}-{datetime.now():%Y%m%d}-", payment.id)
    db.flush()


def _add_bill(
    db: Session, *, patient: Patient, hospital_id: int, user: User, cycle: ArtCycle,
    item_name: str, item_code: str, amount: float, item_type: str, notes: str,
    status: str = "pending", parent_bill_id=None, bill_type: str = "art",
) -> Bill:
    bill = Bill(
        bill_number=placeholder(),
        patient_id=patient.id,
        bill_type=bill_type,
        bill_subtype="final",
        reference_id=cycle.id,
        parent_bill_id=parent_bill_id,
        subtotal=round(float(amount), 2),
        tax_amount=0.0,
        discount_amount=0.0,
        total_amount=round(float(amount), 2),
        status=status,
        bill_date=datetime.now(),
        created_by_id=user.id,
        hospital_id=hospital_id,
        notes=notes,
    )
    db.add(bill)
    _number_bill(db, bill)
    db.add(BillItem(
        bill_id=bill.id,
        item_type=item_type,
        item_name=item_name,
        item_code=item_code,
        quantity=1,
        unit_price=round(float(amount), 2),
        total_price=round(float(amount), 2),
    ))
    db.flush()
    return bill


def _paid_total(db: Session, bill_id: Optional[int]) -> float:
    if not bill_id:
        return 0.0
    rows = db.query(Payment).filter(Payment.bill_id == bill_id).all()
    return round(sum(float(p.amount_paid or 0) for p in rows), 2)


def collect_payment(db: Session, bill: Bill, amount: float, method: str, user: User) -> Payment:
    payment = Payment(
        payment_number=placeholder(),
        bill_id=bill.id,
        amount_paid=round(float(amount), 2),
        payment_method_name=method or "cash",
        payment_date=datetime.now(),
        received_by_id=user.id,
        notes=f"ART collection ({bill.bill_number})",
    )
    db.add(payment)
    _number_payment(db, payment)
    paid = _paid_total(db, bill.id)
    if paid >= float(bill.total_amount or 0) - 0.001:
        bill.status = "paid"
    elif paid > 0:
        bill.status = "partial"
    return payment


def start_cycle(
    db: Session, case: ArtCase, user: User, *,
    cycle_type: str, protocol: Optional[str], clinician_id: Optional[int],
    billing_mode: str, package_template_id: Optional[int], agreed_price: Optional[float],
    collect_advance: bool, payment_method: str,
) -> ArtCycle:
    if cycle_type not in CYCLE_TYPES:
        raise HTTPException(status_code=400, detail="Unknown treatment type.")
    if case.status != "open":
        raise HTTPException(status_code=400, detail="This case is closed. Reopen it before starting a cycle.")
    if case.case_type == "single_woman" and cycle_type == "iui_husband":
        raise HTTPException(status_code=400, detail="Husband IUI needs a couple case.")
    if cycle_type in LEVEL2_CYCLE_TYPES:
        assert_level2(db, case.hospital_id)
    if billing_mode not in ("package", "itemised"):
        raise HTTPException(status_code=400, detail="Billing mode must be package or itemised.")

    template = None
    price = 0.0
    included: list = []
    includes_medicines = False
    medicine_limit = 0.0
    cancel_keep = 0.0
    if billing_mode == "package":
        if not package_template_id:
            raise HTTPException(status_code=400, detail="A package template is required for package billing.")
        template = db.query(ArtPackageTemplate).filter(
            ArtPackageTemplate.id == package_template_id,
            ArtPackageTemplate.hospital_id == case.hospital_id,
            ArtPackageTemplate.is_active == True,  # noqa: E712
        ).first()
        if not template:
            raise HTTPException(status_code=404, detail="Package template not found.")
        price = float(agreed_price if agreed_price is not None else template.price or 0)
        included = list(template.included_service_codes or [])
        includes_medicines = bool(template.includes_medicines)
        medicine_limit = float(template.medicine_limit or 0)
        cancel_keep = float(template.cancel_keep_amount or 0)

    prefix = f"CYC-{case.hospital_id}-"
    cycle = ArtCycle(
        hospital_id=case.hospital_id,
        case_id=case.id,
        cycle_number=placeholder(),
        cycle_type=cycle_type,
        protocol=protocol,
        status="planned",
        clinician_id=clinician_id,
        billing_mode=billing_mode,
        package_template_id=template.id if template else None,
        agreed_price=price,
        includes_medicines=includes_medicines,
        medicine_limit=medicine_limit,
        cancel_keep_amount=cancel_keep,
        included_service_codes=included,
        created_by_id=user.id,
    )
    cycle.estimate_snapshot = {
        "billing_mode": billing_mode,
        "package_template_id": template.id if template else None,
        "package_name": template.name if template else None,
        "agreed_price": price,
        "included_service_codes": included,
        "includes_medicines": includes_medicines,
        "medicine_limit": medicine_limit,
        "cancel_keep_amount": cancel_keep,
        "cycle_type": cycle_type,
    }
    db.add(cycle)
    assign_number(db, cycle, "cycle_number", prefix)

    if billing_mode == "package" and price > 0:
        woman = db.query(Patient).filter(Patient.id == case.woman_patient_id).one()
        bill = _add_bill(
            db, patient=woman, hospital_id=case.hospital_id, user=user, cycle=cycle,
            item_name=f"ART package {template.name}",
            item_code=template.code or "ART-PKG",
            amount=price,
            item_type="art",
            notes=f"Advance for {cycle.cycle_number}",
        )
        cycle.advance_bill_id = bill.id
        if collect_advance:
            collect_payment(db, bill, price, payment_method or "cash", user)
    return cycle


def _void_pending_bill(db: Session, bill_id: Optional[int], note: str) -> bool:
    """Cancel an unpaid bill. Returns False when money has already been taken on it."""
    if not bill_id:
        return True
    bill = db.query(Bill).filter(Bill.id == bill_id).first()
    if not bill or bill.status == "cancelled":
        return True
    if _paid_total(db, bill.id) > 0.001:
        return False
    bill.status = "cancelled"
    bill.notes = ((bill.notes or "") + f" | voided: {note}").strip(" |")
    return True


def _charge_bill(db: Session, cycle: ArtCycle, user: User, charge: ArtCharge, amount: float) -> Bill:
    case = db.query(ArtCase).filter(ArtCase.id == cycle.case_id).one()
    woman = db.query(Patient).filter(Patient.id == case.woman_patient_id).one()
    return _add_bill(
        db, patient=woman, hospital_id=cycle.hospital_id, user=user, cycle=cycle,
        item_name=charge.description, item_code=charge.service_code or charge.kind, amount=amount,
        item_type="medicine" if charge.kind == "medicine" else "art",
        notes=f"Charge on {cycle.cycle_number}",
    )


def change_billing_mode(
    db: Session, cycle: ArtCycle, *, billing_mode: str, reason: str, package_template_id: Optional[int],
    user: Optional[User] = None, agreed_price: Optional[float] = None,
) -> ArtCycle:
    """Switch package and itemised billing, moving the money with it.

    Package to itemised: allowed only while the advance is unpaid. The advance is
    voided and every charge the package covered gets its own bill.
    Itemised to package: an advance bill is raised at the agreed price. Unpaid
    bills for charges the package now covers are voided; paid ones stay paid.
    """
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required to change the billing mode.")
    if cycle.status in ("cancelled", "outcome"):
        raise HTTPException(status_code=400, detail="This cycle is closed.")
    if billing_mode not in ("package", "itemised"):
        raise HTTPException(status_code=400, detail="Billing mode must be package or itemised.")
    if billing_mode == cycle.billing_mode:
        raise HTTPException(status_code=400, detail=f"This cycle is already billed as {billing_mode}.")
    if cycle.estimate_snapshot is None:
        cycle.estimate_snapshot = {"billing_mode": cycle.billing_mode, "agreed_price": cycle.agreed_price}
    original = dict(cycle.estimate_snapshot)
    charges = db.query(ArtCharge).filter(ArtCharge.cycle_id == cycle.id, ArtCharge.status == "open").all()

    if billing_mode == "itemised":
        if not _void_pending_bill(db, cycle.advance_bill_id, f"switched to itemised: {reason}"):
            raise HTTPException(
                status_code=400,
                detail="The package advance has been paid. Keep package billing, or cancel the cycle to refund it.",
            )
        cycle.advance_bill_id = None
        for charge in charges:
            if charge.covered_by_package:
                if user is None:
                    raise HTTPException(status_code=400, detail="A user is required to raise bills.")
                already = 0.0
                if charge.bill_id:
                    bill = db.query(Bill).filter(Bill.id == charge.bill_id).first()
                    already = float(bill.total_amount or 0) if bill and bill.status != "cancelled" else 0.0
                owed = round(float(charge.amount or 0) - already, 2)
                if owed > 0:
                    charge.bill_id = _charge_bill(db, cycle, user, charge, owed).id
                charge.covered_by_package = False
        cycle.package_template_id = None
        cycle.included_service_codes = []
        cycle.includes_medicines = False
        cycle.medicine_limit = 0.0
        cycle.medicine_consumed = 0.0
        cycle.cancel_keep_amount = 0.0
    else:
        template = db.query(ArtPackageTemplate).filter(
            ArtPackageTemplate.id == package_template_id,
            ArtPackageTemplate.hospital_id == cycle.hospital_id,
            ArtPackageTemplate.is_active == True,  # noqa: E712
        ).first()
        if not template:
            raise HTTPException(status_code=404, detail="Package template not found.")
        cycle.package_template_id = template.id
        cycle.included_service_codes = list(template.included_service_codes or [])
        cycle.includes_medicines = bool(template.includes_medicines)
        cycle.medicine_limit = float(template.medicine_limit or 0)
        cycle.medicine_consumed = 0.0
        cycle.cancel_keep_amount = float(template.cancel_keep_amount or 0)
        cycle.agreed_price = float(agreed_price if agreed_price is not None else template.price or 0)
        codes = set(cycle.included_service_codes)
        for charge in charges:
            covered = (
                (charge.kind == "medicine" and cycle.includes_medicines)
                or (charge.kind != "medicine" and charge.service_code in codes)
            )
            if covered and _void_pending_bill(db, charge.bill_id, f"now in package: {reason}"):
                charge.covered_by_package = True
                charge.bill_id = None
                if charge.kind == "medicine":
                    cycle.medicine_consumed = float(cycle.medicine_consumed or 0) + float(charge.amount or 0)
        if cycle.agreed_price > 0:
            if user is None:
                raise HTTPException(status_code=400, detail="A user is required to raise bills.")
            case = db.query(ArtCase).filter(ArtCase.id == cycle.case_id).one()
            woman = db.query(Patient).filter(Patient.id == case.woman_patient_id).one()
            bill = _add_bill(
                db, patient=woman, hospital_id=cycle.hospital_id, user=user, cycle=cycle,
                item_name=f"ART package {template.name}", item_code=template.code or "ART-PKG",
                amount=cycle.agreed_price, item_type="art",
                notes=f"Advance for {cycle.cycle_number}",
            )
            cycle.advance_bill_id = bill.id
    cycle.billing_mode = billing_mode
    cycle.billing_mode_change_reason = reason
    cycle.billing_mode_changed_at = datetime.now()
    cycle.estimate_snapshot = original
    db.flush()
    return cycle


def post_charge(
    db: Session, cycle: ArtCycle, user: User, *,
    service_code: Optional[str], description: str, amount: Optional[float], kind: str,
) -> ArtCharge:
    if cycle.status == "cancelled":
        raise HTTPException(status_code=400, detail="This cycle is cancelled.")
    kind = kind or "service"
    catalog = None
    if service_code:
        catalog = db.query(ArtService).filter(
            ArtService.hospital_id == cycle.hospital_id,
            ArtService.code == service_code,
            ArtService.is_active == True,  # noqa: E712
        ).first()
        if catalog and int(catalog.requires_level or 1) >= 2:
            assert_level2(db, cycle.hospital_id)
    price = float(catalog.default_price if catalog and amount is None else (amount or 0))
    label = description or (catalog.name if catalog else service_code or kind)
    covered = False
    bill_amount = price
    if cycle.billing_mode == "package":
        codes = set(cycle.included_service_codes or [])
        if kind == "medicine" and cycle.includes_medicines:
            limit = float(cycle.medicine_limit or 0)
            consumed = float(cycle.medicine_consumed or 0)
            if limit <= 0 or consumed + price <= limit + 0.001:
                covered = True
                bill_amount = 0.0
                cycle.medicine_consumed = consumed + price
            else:
                room = max(0.0, limit - consumed)
                cycle.medicine_consumed = consumed + room
                bill_amount = round(price - room, 2)
                covered = bill_amount <= 0
        elif kind != "medicine" and service_code and service_code in codes:
            covered = True
            bill_amount = 0.0

    bill_id = None
    if not covered and bill_amount > 0:
        case = db.query(ArtCase).filter(ArtCase.id == cycle.case_id).one()
        woman = db.query(Patient).filter(Patient.id == case.woman_patient_id).one()
        item_type = "medicine" if kind == "medicine" else "art"
        bill = _add_bill(
            db, patient=woman, hospital_id=cycle.hospital_id, user=user, cycle=cycle,
            item_name=label, item_code=service_code or kind, amount=bill_amount,
            item_type=item_type, notes=f"Charge on {cycle.cycle_number}",
        )
        bill_id = bill.id
    charge = ArtCharge(
        cycle_id=cycle.id,
        service_code=service_code,
        description=label,
        kind=kind,
        amount=price,
        covered_by_package=covered,
        bill_id=bill_id,
        status="open",
    )
    db.add(charge)
    db.flush()
    return charge


def cancel_cycle(db: Session, cycle: ArtCycle, user: User, reason: str, refund_method: str = "cash") -> ArtCycle:
    """Cancel a cycle and settle its money.

    Package: the unpaid part of the advance is waived; anything paid above the
    kept amount goes back as a credit note with a matching refund payment.
    Every unpaid charge bill is voided. Bills already paid stay paid.
    """
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A cancellation reason is required.")
    if cycle.status == "cancelled":
        raise HTTPException(status_code=400, detail="This cycle is already cancelled.")
    if cycle.status == "outcome":
        raise HTTPException(status_code=400, detail="An outcome is already recorded. This cycle cannot be cancelled.")
    case = db.query(ArtCase).filter(ArtCase.id == cycle.case_id).one()
    woman = db.query(Patient).filter(Patient.id == case.woman_patient_id).one()
    if cycle.billing_mode == "package" and cycle.advance_bill_id:
        advance = db.query(Bill).filter(Bill.id == cycle.advance_bill_id).first()
        paid = _paid_total(db, cycle.advance_bill_id)
        if advance and paid <= 0.001:
            advance.status = "cancelled"
            advance.notes = ((advance.notes or "") + f" | cancelled: {reason}").strip(" |")
        elif advance:
            unpaid = round(float(advance.total_amount or 0) - paid, 2)
            if unpaid > 0.001:
                advance.discount_amount = round(float(advance.discount_amount or 0) + unpaid, 2)
                advance.total_amount = paid
                advance.notes = ((advance.notes or "") + f" | balance {unpaid:.2f} waived on cancellation").strip(" |")
            advance.status = "paid"
            refund = round(max(0.0, paid - float(cycle.cancel_keep_amount or 0)), 2)
            if refund > 0:
                credit = _add_bill(
                    db, patient=woman, hospital_id=cycle.hospital_id, user=user, cycle=cycle,
                    item_name=f"Refund {cycle.cycle_number}",
                    item_code="ART-REFUND",
                    amount=-refund,
                    item_type="art",
                    notes=reason,
                    status="paid",
                    parent_bill_id=cycle.advance_bill_id,
                    bill_type="credit_note",
                )
                source = (
                    db.query(Payment)
                    .filter(Payment.bill_id == cycle.advance_bill_id, Payment.amount_paid > 0)
                    .order_by(Payment.id.desc())
                    .first()
                )
                refund_row = Payment(
                    payment_number=placeholder(),
                    bill_id=credit.id,
                    amount_paid=-refund,
                    payment_method_name=refund_method or (source.payment_method_name if source else "cash"),
                    payment_date=datetime.now(),
                    received_by_id=user.id,
                    parent_payment_id=source.id if source else None,
                    notes=f"Refund on cancelling {cycle.cycle_number}: {reason}",
                )
                db.add(refund_row)
                _number_payment(db, refund_row, "RFD")
                cycle.refund_bill_id = credit.id
    charges = db.query(ArtCharge).filter(ArtCharge.cycle_id == cycle.id, ArtCharge.status == "open").all()
    for charge in charges:
        if _void_pending_bill(db, charge.bill_id, reason):
            charge.status = "voided"
    cycle.status = "cancelled"
    cycle.cancel_reason = reason
    db.flush()
    return cycle


def add_stimulation(db: Session, cycle: ArtCycle, user: User, payload: dict) -> ArtStimulationDay:
    require_open(cycle)
    if STATUS_RANK.get(cycle.status, 0) > STATUS_RANK["triggered"]:
        raise HTTPException(status_code=400, detail="Monitoring days are recorded before egg collection, IUI, or transfer.")
    day_number = int(payload["day_number"])
    if day_number < 1:
        raise HTTPException(status_code=400, detail="The cycle day starts at 1.")
    if db.query(ArtStimulationDay).filter(
        ArtStimulationDay.cycle_id == cycle.id, ArtStimulationDay.day_number == day_number,
    ).first():
        raise HTTPException(status_code=400, detail=f"Day {day_number} is already recorded on this cycle.")
    day = ArtStimulationDay(
        cycle_id=cycle.id,
        day_number=int(payload["day_number"]),
        drugs=payload.get("drugs") or [],
        follicles_left=payload.get("follicles_left") or [],
        follicles_right=payload.get("follicles_right") or [],
        endometrium_mm=payload.get("endometrium_mm"),
        e2=payload.get("e2"),
        lh=payload.get("lh"),
        progesterone=payload.get("progesterone"),
        notes=payload.get("notes"),
        recorded_by_id=user.id,
    )
    db.add(day)
    advance(cycle, "stimulation")
    db.flush()
    return day


def set_trigger(db: Session, cycle: ArtCycle, drug: str, trigger_at: datetime) -> ArtCycle:
    require_open(cycle)
    if cycle.cycle_type == "sperm_freeze":
        raise HTTPException(status_code=400, detail="A sperm freezing cycle has no trigger.")
    if STATUS_RANK.get(cycle.status, 0) > STATUS_RANK["triggered"]:
        raise HTTPException(status_code=400, detail="This cycle is already past the trigger.")
    if not (drug or "").strip():
        raise HTTPException(status_code=400, detail="Name the trigger medicine.")
    cycle.trigger_drug = drug.strip()
    cycle.trigger_at = trigger_at
    advance(cycle, "triggered")
    db.flush()
    return cycle


def book_appointment(db: Session, case: ArtCase, user: User, payload: dict) -> ArtAppointment:
    kind = payload["kind"]
    if kind not in APPOINTMENT_KINDS:
        raise HTTPException(status_code=400, detail="Unknown appointment type.")
    if kind in LEVEL2_APPOINTMENT_KINDS:
        assert_level2(db, case.hospital_id)
    cycle_id = payload.get("cycle_id")
    cycle = None
    if cycle_id:
        cycle = db.query(ArtCycle).filter(ArtCycle.id == cycle_id, ArtCycle.case_id == case.id).first()
        if not cycle:
            raise HTTPException(status_code=404, detail="Cycle not found on this case.")
        require_open(cycle)
    if kind in APPOINTMENT_CYCLES:
        if not cycle:
            raise HTTPException(status_code=400, detail=f"{kind.upper()} is booked on a cycle.")
        if cycle.cycle_type not in APPOINTMENT_CYCLES[kind]:
            raise HTTPException(status_code=400, detail=f"This cycle type cannot have a {kind.upper()} booking.")
    if kind == "iui":
        form = PROCEDURE_CONSENT.get(cycle.cycle_type)
        if form:
            require_consent(db, case.id, form)
    raw_time = payload.get("scheduled_time")
    parsed = None
    if raw_time:
        parts = str(raw_time).split(":")
        parsed = time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    row = ArtAppointment(
        hospital_id=case.hospital_id,
        case_id=case.id,
        cycle_id=cycle_id,
        kind=kind,
        scheduled_date=date.fromisoformat(payload["scheduled_date"]),
        scheduled_time=parsed,
        room=payload.get("room"),
        clinician_id=payload.get("clinician_id"),
        notes=payload.get("notes"),
        created_by_id=user.id,
    )
    db.add(row)
    db.flush()
    return row


def _name_matches(stated: str, patient: Optional[Patient]) -> bool:
    if not patient:
        return False
    words = {w for w in stated.lower().split() if w}
    first = (patient.first_name or "").strip().lower()
    return bool(first) and first in words


def record_timeout(
    db: Session, appt: ArtAppointment, *, patient_name: str, dob_confirmed: bool, witness_id: int,
    actor: Optional[User] = None,
) -> ArtAppointment:
    if not dob_confirmed or not (patient_name or "").strip():
        raise HTTPException(status_code=400, detail="Time-out needs the patient's stated name and a confirmed date of birth.")
    if appt.status in ("done", "cancelled"):
        raise HTTPException(status_code=400, detail="This appointment is already closed.")
    _staff_user(db, appt.hospital_id, witness_id, "witness")
    if actor is not None and int(witness_id) == actor.id:
        raise HTTPException(status_code=400, detail="The time-out witness must be someone other than you.")
    case = db.query(ArtCase).filter(ArtCase.id == appt.case_id).first()
    if case and not _name_matches(patient_name, case.woman):
        raise HTTPException(
            status_code=400,
            detail="The stated name does not match the woman on this case. Stop and check the patient.",
        )
    appt.timeout_patient_name = patient_name.strip()
    appt.timeout_dob_confirmed = True
    appt.timeout_witness_id = witness_id
    appt.timeout_at = datetime.now()
    db.flush()
    return appt


def complete_appointment(db: Session, appt: ArtAppointment) -> ArtAppointment:
    if appt.kind in TIMEOUT_KINDS:
        if not appt.timeout_at or not appt.timeout_dob_confirmed:
            raise HTTPException(status_code=400, detail="Complete the time-out before this procedure.")
    if appt.status in ("done", "cancelled"):
        raise HTTPException(status_code=400, detail="This appointment is already closed.")
    cycle = db.query(ArtCycle).filter(ArtCycle.id == appt.cycle_id).first() if appt.cycle_id else None
    if cycle and appt.kind in APPOINTMENT_CYCLES:
        require_open(cycle)
    if appt.kind == "iui" and cycle:
        form = PROCEDURE_CONSENT.get(cycle.cycle_type)
        if form:
            require_consent(db, appt.case_id, form)
        advance(cycle, "luteal")
    if appt.kind == "transfer" and cycle:
        moved = db.query(ArtSpecimen).filter(
            ArtSpecimen.disposition == "transferred",
            ((ArtSpecimen.thawed_into_cycle_id == cycle.id)
             | ((ArtSpecimen.origin_cycle_id == cycle.id) & ArtSpecimen.thawed_into_cycle_id.is_(None))),
        ).count()
        if not moved:
            raise HTTPException(status_code=400, detail="Mark the transferred embryo on the lab worksheet first.")
        advance(cycle, "luteal")
    if appt.kind in LEVEL2_APPOINTMENT_KINDS:
        assert_level2(db, appt.hospital_id)
        form = PROCEDURE_CONSENT.get(appt.kind)
        if form:
            require_consent(db, appt.case_id, form)
    appt.status = "done"
    db.flush()
    return appt


def check_in_queue(db: Session, case: ArtCase, queue_date: date) -> ArtQueueEntry:
    last = (
        db.query(ArtQueueEntry)
        .filter(ArtQueueEntry.hospital_id == case.hospital_id, ArtQueueEntry.queue_date == queue_date)
        .order_by(ArtQueueEntry.token_no.desc())
        .first()
    )
    token = (last.token_no + 1) if last else 1
    row = ArtQueueEntry(
        hospital_id=case.hospital_id,
        case_id=case.id,
        queue_date=queue_date,
        token_no=token,
    )
    db.add(row)
    db.flush()
    return row


LAB_WITNESS_PERMS = ("witness_lab", "record_lab")
BANK_WITNESS_PERMS = ("witness_lab", "issue_gametes", "receive_shipment", "manage_donors")
BANK_STEPS = {"bank_issue", "bank_receipt"}


def _staff_user(db: Session, hospital_id: int, user_id, label: str) -> User:
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Choose the {label}.")
    person = db.query(User).filter(User.id == uid).first()
    if not person or person.hospital_id != hospital_id:
        raise HTTPException(status_code=404, detail=f"The {label} was not found in this hospital.")
    if not person.is_active:
        raise HTTPException(status_code=400, detail=f"The {label} account is inactive.")
    return person


def _can_witness(db: Session, person: User, perms) -> bool:
    from app.utils.auth import Modules
    from app.utils.dependencies import user_has_feature_permission
    return any(user_has_feature_permission(db, person, Modules.ART, name) for name in perms)


def resolve_operator(payload: dict, actor: Optional[User]) -> int:
    """The operator is the person signed in. A different operator id is refused."""
    given = payload.get("operator_id")
    if actor is None:
        return int(given)
    if given not in (None, "") and int(given) != actor.id:
        raise HTTPException(
            status_code=400,
            detail="The operator is the person signed in. Sign in as the operator to record this step.",
        )
    return actor.id


def witness(
    db: Session, *, hospital_id: int, cycle_id: Optional[int], step: str, sample_label: str,
    operator_id: int, witness_id: int, notes: Optional[str] = None,
) -> ArtWitnessLog:
    if operator_id is None or witness_id is None:
        raise HTTPException(status_code=400, detail="Both the operator and the witness are required.")
    if int(operator_id) == int(witness_id):
        raise HTTPException(status_code=400, detail="The operator and the witness must be two different people.")
    _staff_user(db, hospital_id, operator_id, "operator")
    witness_user = _staff_user(db, hospital_id, witness_id, "witness")
    perms = BANK_WITNESS_PERMS if step in BANK_STEPS else LAB_WITNESS_PERMS
    if not _can_witness(db, witness_user, perms):
        raise HTTPException(
            status_code=403,
            detail="The witness does not hold the ART witness permission.",
        )
    row = ArtWitnessLog(
        hospital_id=hospital_id,
        cycle_id=cycle_id,
        step=step,
        sample_label=sample_label,
        operator_id=operator_id,
        witness_id=witness_id,
        notes=notes,
    )
    db.add(row)
    db.flush()
    return row


def open_culture(db: Session, cycle: ArtCycle, user: User) -> ArtCycle:
    assert_level2(db, cycle.hospital_id)
    require_open(cycle)
    other = (
        db.query(ArtCycle)
        .filter(
            ArtCycle.hospital_id == cycle.hospital_id,
            ArtCycle.culture_open == True,  # noqa: E712
            ArtCycle.culture_operator_id == user.id,
            ArtCycle.id != cycle.id,
        )
        .first()
    )
    if cycle.culture_open and cycle.culture_operator_id and cycle.culture_operator_id != user.id:
        holder = db.query(User).filter(User.id == cycle.culture_operator_id).first()
        name = f"{holder.first_name} {holder.last_name}".strip() if holder else "another embryologist"
        raise HTTPException(status_code=409, detail=f"This culture is open on {name}'s bench. They must close it first.")
    if other:
        raise HTTPException(
            status_code=409,
            detail=f"Culture for {other.cycle_number} is still open on this bench. Close it before opening another patient's culture.",
        )
    cycle.culture_open = True
    cycle.culture_operator_id = user.id
    advance(cycle, "culture")
    db.flush()
    return cycle


def close_culture(db: Session, cycle: ArtCycle, user: Optional[User] = None) -> ArtCycle:
    if user is not None and cycle.culture_open and cycle.culture_operator_id not in (None, user.id):
        from app.utils.auth import UserRoles
        if not ({UserRoles.SUPER_ADMIN, UserRoles.HOSPITAL_ADMIN} & set(user.role_names)):
            raise HTTPException(status_code=403, detail="Only the embryologist who opened this culture, or an administrator, can close it.")
    cycle.culture_open = False
    db.flush()
    return cycle


def record_retrieval(db: Session, cycle: ArtCycle, user: User, payload: dict) -> ArtCycle:
    assert_level2(db, cycle.hospital_id)
    require_open(cycle)
    if cycle.cycle_type not in EGG_CYCLES:
        raise HTTPException(status_code=400, detail="Egg collection is recorded on an IVF, ICSI, freeze-all, or egg freezing cycle.")
    if not cycle.trigger_at:
        raise HTTPException(status_code=400, detail="Record the trigger injection before egg collection.")
    if cycle.retrieval_at:
        raise HTTPException(status_code=400, detail="Egg collection is already recorded on this cycle.")
    follicles = _count(payload.get("follicles_aspirated"))
    oocytes = _count(payload.get("oocytes_retrieved"))
    mii, mi, gv = (_count(payload.get(k)) for k in ("mature_mii", "intermediate_mi", "immature_gv"))
    if follicles and oocytes > follicles:
        raise HTTPException(status_code=400, detail="More eggs than follicles aspirated. Check the counts.")
    if mii + mi + gv > oocytes:
        raise HTTPException(status_code=400, detail="MII, MI, and GV together cannot be more than the eggs collected.")
    require_consent(db, cycle.case_id, "oocyte_retrieval")
    witness(
        db, hospital_id=cycle.hospital_id, cycle_id=cycle.id, step="retrieval",
        sample_label=cycle.cycle_number,
        operator_id=resolve_operator(payload, user), witness_id=payload.get("witness_id"),
    )
    cycle.retrieval_follicles = follicles
    cycle.retrieval_oocytes = oocytes
    cycle.retrieval_mii = mii
    cycle.retrieval_mi = mi
    cycle.retrieval_gv = gv
    cycle.retrieval_at = datetime.now()
    advance(cycle, "retrieval")
    db.flush()
    return cycle


def record_fertilisation(db: Session, cycle: ArtCycle, payload: dict, actor: Optional[User] = None) -> ArtCycle:
    assert_level2(db, cycle.hospital_id)
    require_open(cycle)
    method = payload["method"]
    if method not in ("ivf", "icsi"):
        raise HTTPException(status_code=400, detail="Fertilisation method must be ivf or icsi.")
    if cycle.cycle_type not in FERT_CYCLES:
        raise HTTPException(status_code=400, detail="Fertilisation is recorded on an IVF, ICSI, or freeze-all cycle.")
    if not cycle.retrieval_at:
        raise HTTPException(status_code=400, detail="Record the egg collection before fertilisation.")
    if cycle.fert_at:
        raise HTTPException(status_code=400, detail="Fertilisation is already recorded on this cycle.")
    inseminated = _count(payload.get("oocytes_inseminated"))
    normal = _count(payload.get("normally_fertilised"))
    if inseminated > int(cycle.retrieval_oocytes or 0):
        raise HTTPException(status_code=400, detail="More eggs inseminated than were collected.")
    if method == "icsi" and inseminated > int(cycle.retrieval_mii or 0):
        raise HTTPException(status_code=400, detail="ICSI uses mature (MII) eggs only. Check the count.")
    if normal > inseminated:
        raise HTTPException(status_code=400, detail="More eggs fertilised than were inseminated.")
    witness(
        db, hospital_id=cycle.hospital_id, cycle_id=cycle.id, step="fertilisation",
        sample_label=cycle.cycle_number,
        operator_id=resolve_operator(payload, actor), witness_id=payload.get("witness_id"),
    )
    cycle.fert_method = method
    cycle.fert_inseminated = inseminated
    cycle.fert_normal = normal
    cycle.fert_at = datetime.now()
    cycle.media_lots = payload.get("media_lots") or []
    advance(cycle, "fertilisation")
    db.flush()
    return cycle


def add_specimen(db: Session, cycle: ArtCycle, user: User, payload: dict) -> ArtSpecimen:
    assert_level2(db, cycle.hospital_id)
    if not cycle.culture_open:
        raise HTTPException(status_code=400, detail="Open this cycle's culture before adding embryos or gametes to the worksheet.")
    require_open(cycle)
    sample_type = payload["sample_type"]
    if sample_type not in ("embryo", "oocyte", "sperm"):
        raise HTTPException(status_code=400, detail="Sample type must be embryo, oocyte, or sperm.")
    existing = db.query(ArtSpecimen).filter(
        ArtSpecimen.origin_cycle_id == cycle.id, ArtSpecimen.sample_type == sample_type,
    ).count()
    if sample_type == "embryo":
        if cycle.cycle_type == "fet":
            raise HTTPException(status_code=400, detail="A frozen embryo transfer uses thawed embryos. Thaw them into this cycle.")
        if not cycle.fert_at:
            raise HTTPException(status_code=400, detail="Record fertilisation before adding embryos.")
        if existing >= int(cycle.fert_normal or 0):
            raise HTTPException(status_code=400, detail="There are already as many embryos as normally fertilised eggs.")
    elif sample_type == "oocyte":
        if not cycle.retrieval_at:
            raise HTTPException(status_code=400, detail="Record the egg collection before adding eggs.")
        if existing >= int(cycle.retrieval_oocytes or 0):
            raise HTTPException(status_code=400, detail="There are already as many eggs as were collected.")
    prefix = f"SP-{cycle.hospital_id}-"
    row = ArtSpecimen(
        hospital_id=cycle.hospital_id,
        origin_cycle_id=cycle.id,
        owner_case_id=cycle.case_id,
        code=placeholder(),
        sample_type=sample_type,
        grades=[],
        disposition="in_culture",
    )
    db.add(row)
    assign_number(db, row, "code", prefix)
    return row


def working_cycle_id(specimen: ArtSpecimen) -> int:
    """The cycle a specimen is being worked in now: the FET cycle after a thaw, else its origin."""
    return specimen.thawed_into_cycle_id or specimen.origin_cycle_id


def grade_specimen(db: Session, specimen: ArtSpecimen, *, day: int, grade: str, stage: Optional[str]) -> ArtSpecimen:
    if specimen.disposition not in ("in_culture", "thawed"):
        raise HTTPException(status_code=400, detail="Only material in the incubator can be graded.")
    cycle = db.query(ArtCycle).filter(ArtCycle.id == working_cycle_id(specimen)).one()
    if not cycle.culture_open:
        raise HTTPException(status_code=400, detail="Culture for this cycle is closed.")
    grades = list(specimen.grades or [])
    grades.append({"day": int(day), "grade": grade, "stage": stage})
    specimen.grades = grades
    db.flush()
    return specimen


def _location_complete(payload: dict) -> bool:
    return all((payload.get(k) or "").strip() for k in ("tank", "canister", "cane", "position"))


def dispose_specimen(db: Session, specimen: ArtSpecimen, payload: dict, actor: Optional[User] = None) -> ArtSpecimen:
    action = payload["disposition"]
    if action not in ("freeze", "discard", "transfer"):
        raise HTTPException(status_code=400, detail="Disposition must be freeze, discard, or transfer.")
    if specimen.disposition in ("discarded", "transferred"):
        raise HTTPException(status_code=400, detail="This specimen already has a final disposition.")
    if action == "freeze" and specimen.disposition != "in_culture":
        raise HTTPException(status_code=400, detail="Only material in the incubator can be frozen.")
    if action == "transfer":
        if specimen.sample_type != "embryo":
            raise HTTPException(status_code=400, detail="Only an embryo can be transferred.")
        if specimen.disposition == "frozen":
            raise HTTPException(status_code=400, detail="Thaw this embryo before the transfer.")
        if specimen.disposition == "thawed" and specimen.thaw_survived is False:
            raise HTTPException(status_code=400, detail="This embryo did not survive thawing.")
    target_cycle_id = working_cycle_id(specimen)
    if action == "transfer":
        target = db.query(ArtCycle).filter(ArtCycle.id == target_cycle_id).one()
        require_open(target)
        if target.cycle_type not in TRANSFER_CYCLES:
            raise HTTPException(status_code=400, detail="This cycle does not include a transfer. Freeze the embryo instead.")
    witness(
        db, hospital_id=specimen.hospital_id, cycle_id=target_cycle_id, step=action,
        sample_label=specimen.code,
        operator_id=resolve_operator(payload, actor), witness_id=payload.get("witness_id"),
    )
    if action == "freeze":
        form = "embryo_freeze" if specimen.sample_type == "embryo" else "gamete_freeze"
        require_consent(db, specimen.owner_case_id, form)
        if not _location_complete(payload):
            raise HTTPException(status_code=400, detail="Freeze needs tank, canister, cane, and position.")
        specimen.disposition = "frozen"
        specimen.tank = payload["tank"]
        specimen.canister = payload["canister"]
        specimen.cane = payload["cane"]
        specimen.position = payload["position"]
        specimen.storage_start = date.today()
        if payload.get("renewal_due"):
            specimen.renewal_due = date.fromisoformat(payload["renewal_due"])
        specimen.oncofertility = bool(payload.get("oncofertility"))
    elif action == "discard":
        require_consent(db, specimen.owner_case_id, "discard")
        specimen.disposition = "discarded"
    elif action == "transfer":
        require_consent(db, specimen.owner_case_id, "couple_treatment")
        specimen.disposition = "transferred"
        cycle = db.query(ArtCycle).filter(ArtCycle.id == target_cycle_id).one()
        advance(cycle, "transfer")
    db.flush()
    return specimen


def renew_storage(db: Session, specimen: ArtSpecimen, *, renewal_due: date, oncofertility: Optional[bool]) -> ArtSpecimen:
    if specimen.disposition != "frozen":
        raise HTTPException(status_code=400, detail="Only frozen material has a storage renewal.")
    if oncofertility is not None:
        specimen.oncofertility = bool(oncofertility)
    if specimen.storage_start:
        limit = specimen.storage_start + timedelta(days=3650)
        if renewal_due > limit and not specimen.oncofertility:
            raise HTTPException(
                status_code=400,
                detail="Storage past 10 years needs the oncofertility flag and National Board permission.",
            )
    specimen.renewal_due = renewal_due
    db.flush()
    return specimen


def thaw_specimen(db: Session, specimen: ArtSpecimen, user: User, payload: dict) -> ArtCycle:
    """Thaw into an existing open cycle on the same case, or start one new cycle for it."""
    assert_level2(db, specimen.hospital_id)
    if specimen.disposition != "frozen":
        raise HTTPException(status_code=400, detail="Only frozen material can be thawed.")
    case = db.query(ArtCase).filter(ArtCase.id == specimen.owner_case_id).one()
    cycle_type = "fet" if specimen.sample_type == "embryo" else "ivf"
    into_id = payload.get("into_cycle_id")
    if into_id:
        cycle = db.query(ArtCycle).filter(
            ArtCycle.id == int(into_id), ArtCycle.hospital_id == specimen.hospital_id,
        ).first()
        if not cycle or cycle.case_id != case.id:
            reject_owner_change()
        if cycle.status in ("cancelled", "outcome"):
            raise HTTPException(status_code=400, detail="That cycle is closed. Thaw into an open cycle.")
        if cycle.cycle_type != cycle_type and not (cycle_type == "ivf" and cycle.cycle_type == "icsi"):
            raise HTTPException(
                status_code=400,
                detail="Thawed embryos go into a frozen embryo transfer cycle. Thawed eggs go into an IVF or ICSI cycle.",
            )
    else:
        cycle = None
    witness(
        db, hospital_id=specimen.hospital_id,
        cycle_id=cycle.id if cycle else specimen.origin_cycle_id, step="thaw",
        sample_label=specimen.code,
        operator_id=resolve_operator(payload, user), witness_id=payload.get("witness_id"),
    )
    if cycle is None:
        cycle = start_cycle(
            db, case, user,
            cycle_type=cycle_type, protocol=None, clinician_id=payload.get("clinician_id"),
            billing_mode=payload.get("billing_mode") or "itemised",
            package_template_id=payload.get("package_template_id"),
            agreed_price=None, collect_advance=False, payment_method="cash",
        )
    if not cycle.linked_source_cycle_id:
        cycle.linked_source_cycle_id = specimen.origin_cycle_id
    specimen.disposition = "thawed"
    specimen.thaw_survived = bool(payload.get("survived", True))
    specimen.thawed_into_cycle_id = cycle.id
    db.flush()
    return cycle


def reject_owner_change() -> None:
    raise HTTPException(
        status_code=400,
        detail="Stored gametes and embryos stay with the same couple or woman. They cannot be moved to another case.",
    )


def donor_public(donor: ArtDonor) -> dict:
    screening = donor.screening or {}
    return {
        "id": donor.id,
        "donor_code": donor.donor_code,
        "donor_type": donor.donor_type,
        "status": donor.status,
        "screening_complete": _screening_ok(screening),
        "insurance_on_file": bool(donor.insurance_policy_no and donor.insurance_valid_until),
        "over_intended_cap": bool(donor.over_intended_cap),
        "oocytes_retrieved": donor.oocytes_retrieved,
    }


def donor_private(donor: ArtDonor) -> dict:
    data = donor_public(donor)
    data.update({
        "legal_name": donor.legal_name,
        "address": donor.address,
        "phone": donor.phone,
        "date_of_birth": donor.date_of_birth.isoformat() if donor.date_of_birth else None,
        "screening": donor.screening or {},
        "insurance_policy_no": donor.insurance_policy_no,
        "insurance_valid_until": donor.insurance_valid_until.isoformat() if donor.insurance_valid_until else None,
        "insurance_amount": donor.insurance_amount,
    })
    return data


def _screening_ok(screening: dict) -> bool:
    return all((screening or {}).get(key) == CLEAR_VALUE for key in SCREENING_KEYS)


def create_donor(db: Session, hospital_id: int, payload: dict) -> ArtDonor:
    prefix = f"DON-{hospital_id}-"
    donor = ArtDonor(
        hospital_id=hospital_id,
        donor_code=placeholder(),
        donor_type=payload["donor_type"],
        legal_name=payload["legal_name"].strip(),
        address=payload.get("address"),
        phone=payload.get("phone"),
        date_of_birth=_as_date(payload.get("date_of_birth")),
        status="screening",
    )
    if donor.donor_type not in ("sperm", "oocyte"):
        raise HTTPException(status_code=400, detail="Donor type must be sperm or oocyte.")
    if not donor.legal_name:
        raise HTTPException(status_code=400, detail="The donor's legal name is required.")
    db.add(donor)
    assign_number(db, donor, "donor_code", prefix)
    return donor


SCREENING_VALUES = {"non_reactive", "reactive", "pending"}


def donor_clear_problem(donor: ArtDonor) -> Optional[str]:
    if not _screening_ok(donor.screening or {}):
        return "Donor screening is incomplete. HIV, HBsAg, HCV, and VDRL must be non-reactive."
    if donor.donor_type == "oocyte":
        if not donor.insurance_policy_no or not donor.insurance_valid_until:
            return "Oocyte donor insurance for 12 months is required before the donor is cleared."
        if donor.insurance_valid_until < date.today() + timedelta(days=365):
            return "Oocyte donor insurance must cover at least 12 months from today."
    return None


def recheck_donor(donor: ArtDonor) -> bool:
    """After screening or insurance changes, a cleared donor who no longer qualifies goes back to screening."""
    if donor.status == "cleared" and donor_clear_problem(donor):
        donor.status = "screening"
        donor.cleared_at = None
        return True
    return False


def set_screening(db: Session, donor: ArtDonor, values: dict) -> ArtDonor:
    for key in SCREENING_KEYS:
        value = (values.get(key) or "").strip().lower()
        if value not in SCREENING_VALUES:
            raise HTTPException(status_code=400, detail=f"{key.upper()} must be non_reactive, reactive, or pending.")
        values[key] = value
    donor.screening = {key: values[key] for key in SCREENING_KEYS}
    recheck_donor(donor)
    db.flush()
    return donor


def set_insurance(db: Session, donor: ArtDonor, policy_no: str, valid_until: date, amount: float) -> ArtDonor:
    if not (policy_no or "").strip():
        raise HTTPException(status_code=400, detail="Enter the insurance policy number.")
    donor.insurance_policy_no = policy_no.strip()
    donor.insurance_valid_until = valid_until
    donor.insurance_amount = amount
    recheck_donor(donor)
    db.flush()
    return donor


def clear_donor(db: Session, donor: ArtDonor) -> ArtDonor:
    problem = donor_clear_problem(donor)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    donor.status = "cleared"
    donor.cleared_at = datetime.now()
    db.flush()
    return donor


def record_donor_retrieval(db: Session, donor: ArtDonor, count: int) -> ArtDonor:
    if donor.donor_type != "oocyte":
        raise HTTPException(status_code=400, detail="Oocyte retrieval counts apply to oocyte donors.")
    donor.oocytes_retrieved = int(count)
    donor.over_intended_cap = int(count) > 7
    db.flush()
    return donor


UNIT_CYCLES = {"sperm": {"iui_donor", "ivf", "icsi"}, "oocyte": {"ivf", "icsi"}}


def _unique_sample_code(db: Session, hospital_id: int, code: str) -> str:
    code = (code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="Enter the straw or sample code.")
    if db.query(ArtBankUnit).filter(ArtBankUnit.hospital_id == hospital_id, ArtBankUnit.sample_code == code).first():
        raise HTTPException(status_code=400, detail=f"Sample code {code} is already in the bank.")
    return code


def _cycle_for_unit(db: Session, hospital_id: int, sample_type: str, case_id, cycle_id) -> ArtCycle:
    cycle = db.query(ArtCycle).filter(ArtCycle.id == cycle_id, ArtCycle.hospital_id == hospital_id).first()
    if not cycle or (case_id and cycle.case_id != case_id):
        raise HTTPException(status_code=404, detail="Cycle not found for this case.")
    require_open(cycle)
    allowed = UNIT_CYCLES.get(sample_type, set())
    if cycle.cycle_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail="Donor sperm goes to a donor IUI, IVF, or ICSI cycle. Donor eggs go to an IVF or ICSI cycle.",
        )
    return cycle


def store_bank_unit(db: Session, hospital_id: int, payload: dict) -> ArtBankUnit:
    donor = db.query(ArtDonor).filter(ArtDonor.id == payload["donor_id"], ArtDonor.hospital_id == hospital_id).first()
    if not donor or donor.status != "cleared":
        raise HTTPException(status_code=400, detail="Only a cleared in-house donor can be stored in the bank.")
    unit = ArtBankUnit(
        hospital_id=hospital_id,
        donor_id=donor.id,
        sample_code=_unique_sample_code(db, hospital_id, payload["sample_code"]),
        sample_type=donor.donor_type,
        status="stored",
        tank=payload.get("tank"),
        canister=payload.get("canister"),
        cane=payload.get("cane"),
        position=payload.get("position"),
    )
    db.add(unit)
    db.flush()
    return unit


def issue_unit(db: Session, unit: ArtBankUnit, payload: dict, actor: Optional[User] = None) -> ArtBankUnit:
    if unit.status != "stored":
        raise HTTPException(status_code=400, detail="This straw is not available to issue.")
    destination = payload["destination"]
    if destination not in ("internal", "external"):
        raise HTTPException(status_code=400, detail="Destination must be internal or external.")
    donor = db.query(ArtDonor).filter(ArtDonor.id == unit.donor_id).first() if unit.donor_id else None
    cycle = None
    if destination == "internal":
        case_id = payload.get("case_id")
        if not case_id or not payload.get("cycle_id"):
            raise HTTPException(status_code=400, detail="Choose the case and cycle that receive this sample.")
        if unit.case_id and unit.case_id != case_id:
            raise HTTPException(status_code=400, detail="This sample is already assigned to another case.")
        cycle = _cycle_for_unit(db, unit.hospital_id, unit.sample_type, case_id, payload.get("cycle_id"))
        if donor:
            other = db.query(ArtBankUnit).filter(
                ArtBankUnit.donor_id == donor.id,
                ArtBankUnit.case_id.isnot(None),
                ArtBankUnit.case_id != case_id,
            ).first()
            if other:
                raise HTTPException(
                    status_code=400,
                    detail="This donor's samples already went to another couple or woman. One donor supplies one recipient.",
                )
            if donor.status != "cleared":
                raise HTTPException(status_code=400, detail="This donor is no longer cleared. Recheck screening and insurance.")
    else:
        if not (payload.get("external_clinic_name") or "").strip():
            raise HTTPException(status_code=400, detail="Name the registered clinic that is receiving this sample.")
    witness(
        db, hospital_id=unit.hospital_id, cycle_id=cycle.id if cycle else None, step="bank_issue",
        sample_label=unit.sample_code,
        operator_id=resolve_operator(payload, actor), witness_id=payload.get("witness_id"),
    )
    if cycle is not None:
        cycle.donor_code = donor.donor_code if donor else unit.external_donor_code
        unit.case_id = cycle.case_id
        unit.cycle_id = cycle.id
        unit.status = "issued_internal"
    else:
        unit.external_clinic_name = payload["external_clinic_name"].strip()
        unit.status = "issued_external"
    unit.issued_at = datetime.now()
    db.flush()
    return unit


def receive_external(db: Session, hospital_id: int, payload: dict, actor: Optional[User] = None) -> ArtBankUnit:
    """Receive a sample from an outside bank. With a cycle it goes straight to that cycle;
    without one it is stored here and issued later like any other straw."""
    from app.models.art import ArtPartnerBank
    partner = db.query(ArtPartnerBank).filter(
        ArtPartnerBank.id == payload.get("partner_bank_id"), ArtPartnerBank.hospital_id == hospital_id,
    ).first()
    if not partner or not partner.is_active:
        raise HTTPException(status_code=404, detail="Partner bank not found.")
    sample_type = payload.get("sample_type")
    if sample_type not in UNIT_CYCLES:
        raise HTTPException(status_code=400, detail="An outside bank supplies sperm or eggs.")
    donor_code = (payload.get("donor_code") or "").strip()
    if not donor_code:
        raise HTTPException(status_code=400, detail="Enter the donor code from the outside bank.")
    code = _unique_sample_code(db, hospital_id, payload.get("sample_code"))
    case_id = payload.get("case_id")
    cycle = None
    if payload.get("cycle_id"):
        cycle = _cycle_for_unit(db, hospital_id, sample_type, case_id, payload["cycle_id"])
    witness(
        db, hospital_id=hospital_id, cycle_id=cycle.id if cycle else None, step="bank_receipt",
        sample_label=code,
        operator_id=resolve_operator(payload, actor), witness_id=payload.get("witness_id"),
    )
    if cycle is not None:
        cycle.donor_code = donor_code
    unit = ArtBankUnit(
        hospital_id=hospital_id,
        partner_bank_id=partner.id,
        external_donor_code=donor_code,
        sample_code=code,
        sample_type=sample_type,
        status="received_external" if cycle else "stored",
        case_id=cycle.case_id if cycle else None,
        cycle_id=cycle.id if cycle else None,
        tank=payload.get("tank"),
        canister=payload.get("canister"),
        cane=payload.get("cane"),
        position=payload.get("position"),
        issued_at=datetime.now() if cycle else None,
    )
    db.add(unit)
    db.flush()
    return unit


def age_band(dob: Optional[date], on: date) -> str:
    if not dob:
        return "unknown"
    years = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
    if years < 35:
        return "<35"
    if years <= 37:
        return "35-37"
    if years <= 40:
        return "38-40"
    return "41+"


OUTCOME_FIELDS = (
    "beta_hcg_value", "beta_hcg_positive", "clinical_pregnancy", "miscarriage",
    "live_birth", "outcome_notes", "complication",
)
PREGNANCY_FIELDS = ("beta_hcg_value", "beta_hcg_positive", "clinical_pregnancy", "miscarriage", "live_birth")


def record_outcome(db: Session, cycle: ArtCycle, payload: dict) -> ArtCycle:
    """Record or update the outcome. Results arrive in stages, so later calls fill in more."""
    if cycle.status == "cancelled":
        raise HTTPException(status_code=400, detail="A cancelled cycle has no clinical outcome.")
    merged = {key: getattr(cycle, key) for key in OUTCOME_FIELDS}
    merged.update({key: payload[key] for key in OUTCOME_FIELDS if key in payload})
    if cycle.cycle_type in NO_PREGNANCY_CYCLES:
        if any(merged[key] is not None for key in PREGNANCY_FIELDS):
            raise HTTPException(status_code=400, detail="A freezing cycle has no pregnancy result. Record notes or complications only.")
    elif cycle.status != "outcome":
        if cycle.cycle_type in IUI_CYCLES and STATUS_RANK.get(cycle.status, 0) < STATUS_RANK["luteal"]:
            raise HTTPException(status_code=400, detail="Complete the IUI before recording the pregnancy result.")
        if cycle.cycle_type in TRANSFER_CYCLES and STATUS_RANK.get(cycle.status, 0) < STATUS_RANK["transfer"]:
            raise HTTPException(status_code=400, detail="Record the embryo transfer before the pregnancy result.")
        if cycle.cycle_type == "oi" and cycle.status == "planned":
            raise HTTPException(status_code=400, detail="Record the monitoring before the pregnancy result.")
    if merged["clinical_pregnancy"] and merged["beta_hcg_positive"] is False:
        raise HTTPException(status_code=400, detail="A clinical pregnancy needs a positive pregnancy test.")
    if merged["live_birth"] and not merged["clinical_pregnancy"]:
        raise HTTPException(status_code=400, detail="A live birth needs a clinical pregnancy first.")
    if merged["live_birth"] and merged["miscarriage"]:
        raise HTTPException(status_code=400, detail="A pregnancy cannot end in both a miscarriage and a live birth.")
    for key, value in merged.items():
        setattr(cycle, key, value)
    cycle.outcome_recorded_at = datetime.now()
    cycle.status = "outcome"
    cycle.culture_open = False
    db.flush()
    return cycle


def treated(cycle: ArtCycle) -> bool:
    """The cycle reached the step that can make a pregnancy: insemination, transfer, or timed OI."""
    rank = STATUS_RANK.get(cycle.status, -1)
    if cycle.cycle_type in TRANSFER_CYCLES:
        return rank >= STATUS_RANK["transfer"]
    if cycle.cycle_type in IUI_CYCLES:
        return rank >= STATUS_RANK["luteal"]
    if cycle.cycle_type == "oi":
        return rank >= STATUS_RANK["stimulation"]
    return False


def outcome_report(db: Session, hospital_id: int) -> dict:
    """Rates use cycles that reached transfer, IUI, or timed OI as the denominator.

    Cycles started (including cancelled ones) are shown beside it so drop-out is visible.
    Freezing-only cycles are left out because they cannot give a pregnancy.
    """
    cycles = (
        db.query(ArtCycle)
        .filter(ArtCycle.hospital_id == hospital_id, ArtCycle.cycle_type.notin_(NO_PREGNANCY_CYCLES))
        .all()
    )
    groups = {"by_age": {}, "by_protocol": {}, "by_clinician": {}, "by_cycle_type": {}}
    names: dict = {}

    def bump(bucket, key, cycle):
        row = bucket.setdefault(key, {
            "cycles": 0, "cycles_started": 0, "treated": 0, "cancelled": 0,
            "clinical_pregnancies": 0, "live_births": 0,
        })
        row["cycles_started"] += 1
        if cycle.status == "cancelled":
            row["cancelled"] += 1
        if treated(cycle):
            row["treated"] += 1
            row["cycles"] = row["treated"]
            if cycle.clinical_pregnancy:
                row["clinical_pregnancies"] += 1
            if cycle.live_birth:
                row["live_births"] += 1

    for cycle in cycles:
        case = db.query(ArtCase).filter(ArtCase.id == cycle.case_id).one()
        woman = db.query(Patient).filter(Patient.id == case.woman_patient_id).one()
        on = cycle.started_at.date() if cycle.started_at else date.today()
        bump(groups["by_age"], age_band(woman.date_of_birth, on), cycle)
        bump(groups["by_protocol"], cycle.protocol or "unspecified", cycle)
        clinician = "unassigned"
        if cycle.clinician_id:
            if cycle.clinician_id not in names:
                user = db.query(User).filter(User.id == cycle.clinician_id).first()
                names[cycle.clinician_id] = f"{user.first_name} {user.last_name}".strip() if user else "unassigned"
            clinician = names[cycle.clinician_id]
        bump(groups["by_clinician"], clinician, cycle)
        bump(groups["by_cycle_type"], cycle.cycle_type, cycle)
    for bucket in groups.values():
        for row in bucket.values():
            row["clinical_pregnancy_rate"] = (
                round(row["clinical_pregnancies"] / row["treated"], 4) if row["treated"] else None
            )
            row["live_birth_rate"] = round(row["live_births"] / row["treated"], 4) if row["treated"] else None
    return groups


def lab_kpis(db: Session, hospital_id: int) -> dict:
    cycles = db.query(ArtCycle).filter(ArtCycle.hospital_id == hospital_id).all()
    inseminated = sum(int(c.fert_inseminated or 0) for c in cycles)
    fertilised = sum(int(c.fert_normal or 0) for c in cycles)
    embryos = db.query(ArtSpecimen).filter(
        ArtSpecimen.hospital_id == hospital_id, ArtSpecimen.sample_type == "embryo",
    ).all()
    blast = 0
    for embryo in embryos:
        if any(int(g.get("day") or 0) >= 5 for g in (embryo.grades or [])):
            blast += 1
    thawed = [e for e in embryos if e.disposition == "thawed"]
    survived = [e for e in thawed if e.thaw_survived]
    return {
        "oocytes_inseminated": inseminated,
        "normally_fertilised": fertilised,
        "fertilisation_rate": round(fertilised / inseminated, 4) if inseminated else None,
        "embryos": len(embryos),
        "blastocysts": blast,
        "blastocyst_rate": round(blast / len(embryos), 4) if embryos else None,
        "thawed": len(thawed),
        "thaw_survived": len(survived),
        "thaw_survival_rate": round(len(survived) / len(thawed), 4) if thawed else None,
    }


def registry_export(db: Session, hospital_id: int, year: int, month: int) -> dict:
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)

    def in_month(value) -> bool:
        return bool(value and start <= value.replace(tzinfo=None) < end)

    cases = db.query(ArtCase).filter(ArtCase.hospital_id == hospital_id).all()
    enrolments = [c for c in cases if in_month(c.opened_at)]
    appointments = db.query(ArtAppointment).filter(
        ArtAppointment.hospital_id == hospital_id, ArtAppointment.status == "done", ArtAppointment.kind == "iui",
    ).all()
    cycles = db.query(ArtCycle).filter(ArtCycle.hospital_id == hospital_id).all()
    transfers = db.query(ArtWitnessLog).filter(
        ArtWitnessLog.hospital_id == hospital_id, ArtWitnessLog.step == "transfer",
    ).all()
    transfer_logs = [w for w in transfers if in_month(w.occurred_at)]
    procedures = {
        "iui": sum(
            1 for a in appointments
            if a.scheduled_date and a.scheduled_date.year == year and a.scheduled_date.month == month
        ),
        # Egg collections and transfers come from the lab record, booked or not.
        "opu": sum(1 for c in cycles if in_month(c.retrieval_at)),
        "transfer": len({w.cycle_id for w in transfer_logs}),
        "embryos_transferred": len(transfer_logs),
    }
    outcomes = [c for c in cycles if in_month(c.outcome_recorded_at)]
    complications = [
        {"cycle_number": c.cycle_number, "complication": c.complication}
        for c in outcomes if (c.complication or "").strip()
    ]
    donors = db.query(ArtDonor).filter(ArtDonor.hospital_id == hospital_id).all()
    screened = [d for d in donors if d.screening and in_month(d.created_at)]
    cleared = [d for d in donors if in_month(d.cleared_at)]
    units = db.query(ArtBankUnit).filter(ArtBankUnit.hospital_id == hospital_id).all()
    issued = [
        u for u in units
        if u.status in ("issued_internal", "issued_external", "received_external") and in_month(u.issued_at)
    ]
    received = [u for u in units if u.partner_bank_id and in_month(u.created_at)]
    return {
        "period": f"{year:04d}-{month:02d}",
        "clinic": {
            "enrolments": len(enrolments),
            "procedures": procedures,
            "outcomes": len(outcomes),
            "complications": complications,
        },
        "bank": {
            "donors_screened": len(screened),
            "donors_cleared": len(cleared),
            "samples_issued": len(issued),
            "samples_received": len(received),
        },
    }
