"""Fertility (ART) rules: billing modes, consent gates, Level 2 licence, bank identity."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
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


def _next_number(db: Session, model, number_attr: str, hospital_id: int, prefix: str) -> str:
    column = getattr(model, number_attr)
    last = (
        db.query(model)
        .filter(model.hospital_id == hospital_id, column.like(f"{prefix}%"))
        .order_by(model.id.desc())
        .first()
    )
    seq = 1
    if last:
        tail = getattr(last, number_attr).rsplit("-", 1)[-1]
        if tail.isdigit():
            seq = int(tail) + 1
    return f"{prefix}{seq:05d}"


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


def _bill_number(db: Session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"ART-{today}-"
    last = db.query(Bill).filter(Bill.bill_number.like(f"{prefix}%")).order_by(Bill.id.desc()).first()
    seq = (int(last.bill_number.split("-")[-1]) + 1) if last else 1
    return f"{prefix}{seq:04d}"


def _payment_number(db: Session) -> str:
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"PAY-{today}-"
    last = db.query(Payment).filter(Payment.payment_number.like(f"{prefix}%")).order_by(Payment.id.desc()).first()
    seq = (int(last.payment_number.split("-")[-1]) + 1) if last else 1
    return f"{prefix}{seq:04d}"


def _add_bill(
    db: Session, *, patient: Patient, hospital_id: int, user: User, cycle: ArtCycle,
    item_name: str, item_code: str, amount: float, item_type: str, notes: str,
    status: str = "pending", parent_bill_id=None, bill_type: str = "art",
) -> Bill:
    bill = Bill(
        bill_number=_bill_number(db),
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
    db.flush()
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
        payment_number=_payment_number(db),
        bill_id=bill.id,
        amount_paid=round(float(amount), 2),
        payment_method_name=method or "cash",
        payment_date=datetime.now(),
        received_by_id=user.id,
        notes=f"ART collection ({bill.bill_number})",
    )
    db.add(payment)
    db.flush()
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
        cycle_number=_next_number(db, ArtCycle, "cycle_number", case.hospital_id, prefix),
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
    db.flush()

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


def change_billing_mode(
    db: Session, cycle: ArtCycle, *, billing_mode: str, reason: str, package_template_id: Optional[int],
) -> ArtCycle:
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required to change the billing mode.")
    if cycle.status == "cancelled":
        raise HTTPException(status_code=400, detail="This cycle is cancelled.")
    if billing_mode not in ("package", "itemised"):
        raise HTTPException(status_code=400, detail="Billing mode must be package or itemised.")
    if cycle.estimate_snapshot is None:
        cycle.estimate_snapshot = {"billing_mode": cycle.billing_mode, "agreed_price": cycle.agreed_price}
    original = dict(cycle.estimate_snapshot)
    if billing_mode == "package":
        template = db.query(ArtPackageTemplate).filter(
            ArtPackageTemplate.id == package_template_id,
            ArtPackageTemplate.hospital_id == cycle.hospital_id,
        ).first()
        if not template:
            raise HTTPException(status_code=404, detail="Package template not found.")
        cycle.package_template_id = template.id
        cycle.included_service_codes = list(template.included_service_codes or [])
        cycle.includes_medicines = bool(template.includes_medicines)
        cycle.medicine_limit = float(template.medicine_limit or 0)
        cycle.cancel_keep_amount = float(template.cancel_keep_amount or 0)
        if not cycle.agreed_price:
            cycle.agreed_price = float(template.price or 0)
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


def cancel_cycle(db: Session, cycle: ArtCycle, user: User, reason: str) -> ArtCycle:
    reason = (reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A cancellation reason is required.")
    if cycle.status == "cancelled":
        raise HTTPException(status_code=400, detail="This cycle is already cancelled.")
    case = db.query(ArtCase).filter(ArtCase.id == cycle.case_id).one()
    woman = db.query(Patient).filter(Patient.id == case.woman_patient_id).one()
    if cycle.billing_mode == "package":
        paid = _paid_total(db, cycle.advance_bill_id)
        refund = round(max(0.0, paid - float(cycle.cancel_keep_amount or 0)), 2)
        if refund > 0 and cycle.advance_bill_id:
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
            cycle.refund_bill_id = credit.id
    else:
        charges = db.query(ArtCharge).filter(ArtCharge.cycle_id == cycle.id, ArtCharge.status == "open").all()
        for charge in charges:
            if not charge.bill_id:
                charge.status = "voided"
                continue
            bill = db.query(Bill).filter(Bill.id == charge.bill_id).first()
            if bill and bill.status == "pending":
                bill.status = "cancelled"
                bill.notes = ((bill.notes or "") + f" | voided: {reason}").strip()
                charge.status = "voided"
    cycle.status = "cancelled"
    cycle.cancel_reason = reason
    db.flush()
    return cycle


def add_stimulation(db: Session, cycle: ArtCycle, user: User, payload: dict) -> ArtStimulationDay:
    if cycle.status == "cancelled":
        raise HTTPException(status_code=400, detail="This cycle is cancelled.")
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
    if cycle.status == "planned":
        cycle.status = "stimulation"
    db.flush()
    return day


def set_trigger(db: Session, cycle: ArtCycle, drug: str, trigger_at: datetime) -> ArtCycle:
    if cycle.status == "cancelled":
        raise HTTPException(status_code=400, detail="This cycle is cancelled.")
    cycle.trigger_drug = drug
    cycle.trigger_at = trigger_at
    cycle.status = "triggered"
    db.flush()
    return cycle


def book_appointment(db: Session, case: ArtCase, user: User, payload: dict) -> ArtAppointment:
    kind = payload["kind"]
    if kind in LEVEL2_APPOINTMENT_KINDS:
        assert_level2(db, case.hospital_id)
    cycle_id = payload.get("cycle_id")
    if kind == "iui":
        if not cycle_id:
            raise HTTPException(status_code=400, detail="IUI is booked on a cycle.")
        cycle = db.query(ArtCycle).filter(ArtCycle.id == cycle_id, ArtCycle.case_id == case.id).first()
        if not cycle:
            raise HTTPException(status_code=404, detail="Cycle not found on this case.")
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


def record_timeout(db: Session, appt: ArtAppointment, *, patient_name: str, dob_confirmed: bool, witness_id: int) -> ArtAppointment:
    if not dob_confirmed or not (patient_name or "").strip():
        raise HTTPException(status_code=400, detail="Time-out needs the patient's stated name and a confirmed date of birth.")
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
    if appt.kind == "iui" and appt.cycle_id:
        cycle = db.query(ArtCycle).filter(ArtCycle.id == appt.cycle_id).one()
        form = PROCEDURE_CONSENT.get(cycle.cycle_type)
        if form:
            require_consent(db, appt.case_id, form)
        cycle.status = "luteal"
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


def witness(
    db: Session, *, hospital_id: int, cycle_id: Optional[int], step: str, sample_label: str,
    operator_id: int, witness_id: int, notes: Optional[str] = None,
) -> ArtWitnessLog:
    if operator_id == witness_id:
        raise HTTPException(status_code=400, detail="The operator and the witness must be two different people.")
    for uid in (operator_id, witness_id):
        if not db.query(User).filter(User.id == uid).first():
            raise HTTPException(status_code=404, detail="Operator or witness user was not found.")
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
    other = (
        db.query(ArtCycle)
        .filter(
            ArtCycle.culture_open == True,  # noqa: E712
            ArtCycle.culture_operator_id == user.id,
            ArtCycle.id != cycle.id,
        )
        .first()
    )
    if other:
        raise HTTPException(
            status_code=409,
            detail=f"Culture for {other.cycle_number} is still open on this bench. Close it before opening another patient's culture.",
        )
    cycle.culture_open = True
    cycle.culture_operator_id = user.id
    if cycle.status in ("planned", "stimulation", "triggered", "retrieval", "fertilisation"):
        cycle.status = "culture"
    db.flush()
    return cycle


def close_culture(db: Session, cycle: ArtCycle) -> ArtCycle:
    cycle.culture_open = False
    db.flush()
    return cycle


def record_retrieval(db: Session, cycle: ArtCycle, user: User, payload: dict) -> ArtCycle:
    assert_level2(db, cycle.hospital_id)
    require_consent(db, cycle.case_id, "oocyte_retrieval")
    witness(
        db, hospital_id=cycle.hospital_id, cycle_id=cycle.id, step="retrieval",
        sample_label=cycle.cycle_number,
        operator_id=int(payload["operator_id"]), witness_id=int(payload["witness_id"]),
    )
    cycle.retrieval_follicles = payload.get("follicles_aspirated")
    cycle.retrieval_oocytes = payload.get("oocytes_retrieved")
    cycle.retrieval_mii = payload.get("mature_mii")
    cycle.retrieval_mi = payload.get("intermediate_mi")
    cycle.retrieval_gv = payload.get("immature_gv")
    cycle.retrieval_at = datetime.now()
    cycle.status = "retrieval"
    db.flush()
    return cycle


def record_fertilisation(db: Session, cycle: ArtCycle, payload: dict) -> ArtCycle:
    assert_level2(db, cycle.hospital_id)
    method = payload["method"]
    if method not in ("ivf", "icsi"):
        raise HTTPException(status_code=400, detail="Fertilisation method must be ivf or icsi.")
    witness(
        db, hospital_id=cycle.hospital_id, cycle_id=cycle.id, step="fertilisation",
        sample_label=cycle.cycle_number,
        operator_id=int(payload["operator_id"]), witness_id=int(payload["witness_id"]),
    )
    cycle.fert_method = method
    cycle.fert_inseminated = int(payload.get("oocytes_inseminated") or 0)
    cycle.fert_normal = int(payload.get("normally_fertilised") or 0)
    cycle.fert_at = datetime.now()
    cycle.media_lots = payload.get("media_lots") or []
    cycle.status = "fertilisation"
    db.flush()
    return cycle


def add_specimen(db: Session, cycle: ArtCycle, user: User, payload: dict) -> ArtSpecimen:
    assert_level2(db, cycle.hospital_id)
    if not cycle.culture_open:
        raise HTTPException(status_code=400, detail="Open this cycle's culture before adding embryos or gametes to the worksheet.")
    sample_type = payload["sample_type"]
    if sample_type not in ("embryo", "oocyte", "sperm"):
        raise HTTPException(status_code=400, detail="Sample type must be embryo, oocyte, or sperm.")
    prefix = f"SP-{cycle.hospital_id}-"
    row = ArtSpecimen(
        hospital_id=cycle.hospital_id,
        origin_cycle_id=cycle.id,
        owner_case_id=cycle.case_id,
        code=_next_number(db, ArtSpecimen, "code", cycle.hospital_id, prefix),
        sample_type=sample_type,
        grades=[],
        disposition="in_culture",
    )
    db.add(row)
    db.flush()
    return row


def grade_specimen(db: Session, specimen: ArtSpecimen, *, day: int, grade: str, stage: Optional[str]) -> ArtSpecimen:
    cycle = db.query(ArtCycle).filter(ArtCycle.id == specimen.origin_cycle_id).one()
    if not cycle.culture_open:
        raise HTTPException(status_code=400, detail="Culture for this cycle is closed.")
    grades = list(specimen.grades or [])
    grades.append({"day": int(day), "grade": grade, "stage": stage})
    specimen.grades = grades
    db.flush()
    return specimen


def _location_complete(payload: dict) -> bool:
    return all((payload.get(k) or "").strip() for k in ("tank", "canister", "cane", "position"))


def dispose_specimen(db: Session, specimen: ArtSpecimen, payload: dict) -> ArtSpecimen:
    action = payload["disposition"]
    if specimen.disposition in ("discarded", "transferred"):
        raise HTTPException(status_code=400, detail="This specimen already has a final disposition.")
    witness(
        db, hospital_id=specimen.hospital_id, cycle_id=specimen.origin_cycle_id, step=action,
        sample_label=specimen.code,
        operator_id=int(payload["operator_id"]), witness_id=int(payload["witness_id"]),
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
        cycle = db.query(ArtCycle).filter(ArtCycle.id == specimen.origin_cycle_id).one()
        cycle.status = "transfer"
    else:
        raise HTTPException(status_code=400, detail="Disposition must be freeze, discard, or transfer.")
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
    assert_level2(db, specimen.hospital_id)
    if specimen.disposition != "frozen":
        raise HTTPException(status_code=400, detail="Only frozen material can be thawed.")
    witness(
        db, hospital_id=specimen.hospital_id, cycle_id=specimen.origin_cycle_id, step="thaw",
        sample_label=specimen.code,
        operator_id=int(payload["operator_id"]), witness_id=int(payload["witness_id"]),
    )
    case = db.query(ArtCase).filter(ArtCase.id == specimen.owner_case_id).one()
    cycle_type = "fet" if specimen.sample_type == "embryo" else "ivf"
    cycle = start_cycle(
        db, case, user,
        cycle_type=cycle_type, protocol=None, clinician_id=payload.get("clinician_id"),
        billing_mode=payload.get("billing_mode") or "itemised",
        package_template_id=payload.get("package_template_id"),
        agreed_price=None, collect_advance=False, payment_method="cash",
    )
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
        donor_code=_next_number(db, ArtDonor, "donor_code", hospital_id, prefix),
        donor_type=payload["donor_type"],
        legal_name=payload["legal_name"].strip(),
        address=payload.get("address"),
        phone=payload.get("phone"),
        date_of_birth=_as_date(payload.get("date_of_birth")),
        status="screening",
    )
    if donor.donor_type not in ("sperm", "oocyte"):
        raise HTTPException(status_code=400, detail="Donor type must be sperm or oocyte.")
    db.add(donor)
    db.flush()
    return donor


def clear_donor(db: Session, donor: ArtDonor) -> ArtDonor:
    if not _screening_ok(donor.screening or {}):
        raise HTTPException(status_code=400, detail="Donor screening is incomplete. HIV, HBsAg, HCV, and VDRL must be non-reactive.")
    if donor.donor_type == "oocyte":
        if not donor.insurance_policy_no or not donor.insurance_valid_until:
            raise HTTPException(status_code=400, detail="Oocyte donor insurance for 12 months is required before the donor is cleared.")
        if donor.insurance_valid_until < date.today() + timedelta(days=365):
            raise HTTPException(status_code=400, detail="Oocyte donor insurance must cover at least 12 months from today.")
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


def store_bank_unit(db: Session, hospital_id: int, payload: dict) -> ArtBankUnit:
    donor = db.query(ArtDonor).filter(ArtDonor.id == payload["donor_id"], ArtDonor.hospital_id == hospital_id).first()
    if not donor or donor.status != "cleared":
        raise HTTPException(status_code=400, detail="Only a cleared in-house donor can be stored in the bank.")
    unit = ArtBankUnit(
        hospital_id=hospital_id,
        donor_id=donor.id,
        sample_code=payload["sample_code"],
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


def issue_unit(db: Session, unit: ArtBankUnit, payload: dict) -> ArtBankUnit:
    if unit.status != "stored":
        raise HTTPException(status_code=400, detail="This straw is not available to issue.")
    destination = payload["destination"]
    witness(
        db, hospital_id=unit.hospital_id, cycle_id=payload.get("cycle_id"), step="bank_issue",
        sample_label=unit.sample_code,
        operator_id=int(payload["operator_id"]), witness_id=int(payload["witness_id"]),
    )
    if destination == "internal":
        case_id = payload.get("case_id")
        cycle_id = payload.get("cycle_id")
        if unit.case_id and unit.case_id != case_id:
            raise HTTPException(status_code=400, detail="This sample is already assigned to another case.")
        cycle = db.query(ArtCycle).filter(ArtCycle.id == cycle_id, ArtCycle.case_id == case_id).first()
        if not cycle:
            raise HTTPException(status_code=404, detail="Cycle not found for this case.")
        donor = db.query(ArtDonor).filter(ArtDonor.id == unit.donor_id).first()
        cycle.donor_code = donor.donor_code if donor else unit.external_donor_code
        unit.case_id = case_id
        unit.cycle_id = cycle.id
        unit.status = "issued_internal"
    elif destination == "external":
        clinic = (payload.get("external_clinic_name") or "").strip()
        if not clinic:
            raise HTTPException(status_code=400, detail="Name the registered clinic that is receiving this sample.")
        unit.external_clinic_name = clinic
        unit.status = "issued_external"
    else:
        raise HTTPException(status_code=400, detail="Destination must be internal or external.")
    unit.issued_at = datetime.now()
    db.flush()
    return unit


def receive_external(db: Session, hospital_id: int, payload: dict) -> ArtBankUnit:
    witness(
        db, hospital_id=hospital_id, cycle_id=payload.get("cycle_id"), step="bank_receipt",
        sample_label=payload["sample_code"],
        operator_id=int(payload["operator_id"]), witness_id=int(payload["witness_id"]),
    )
    case_id = payload.get("case_id")
    cycle_id = payload.get("cycle_id")
    if cycle_id:
        cycle = db.query(ArtCycle).filter(ArtCycle.id == cycle_id, ArtCycle.hospital_id == hospital_id).first()
        if not cycle:
            raise HTTPException(status_code=404, detail="Cycle not found.")
        if case_id and cycle.case_id != case_id:
            raise HTTPException(status_code=400, detail="Cycle does not belong to that case.")
        cycle.donor_code = payload["donor_code"]
        case_id = cycle.case_id
    unit = ArtBankUnit(
        hospital_id=hospital_id,
        partner_bank_id=payload["partner_bank_id"],
        external_donor_code=payload["donor_code"],
        sample_code=payload["sample_code"],
        sample_type=payload["sample_type"],
        status="received_external",
        case_id=case_id,
        cycle_id=cycle_id,
        issued_at=datetime.now(),
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


def record_outcome(db: Session, cycle: ArtCycle, payload: dict) -> ArtCycle:
    if cycle.status == "cancelled":
        raise HTTPException(status_code=400, detail="A cancelled cycle has no clinical outcome.")
    cycle.beta_hcg_value = payload.get("beta_hcg_value")
    cycle.beta_hcg_positive = payload.get("beta_hcg_positive")
    cycle.clinical_pregnancy = payload.get("clinical_pregnancy")
    cycle.miscarriage = payload.get("miscarriage")
    cycle.live_birth = payload.get("live_birth")
    cycle.outcome_notes = payload.get("outcome_notes")
    cycle.complication = payload.get("complication")
    cycle.outcome_recorded_at = datetime.now()
    cycle.status = "outcome"
    db.flush()
    return cycle


def outcome_report(db: Session, hospital_id: int) -> dict:
    cycles = (
        db.query(ArtCycle)
        .filter(ArtCycle.hospital_id == hospital_id, ArtCycle.outcome_recorded_at.isnot(None))
        .all()
    )
    groups = {"by_age": {}, "by_protocol": {}, "by_clinician": {}, "by_cycle_type": {}}

    def bump(bucket, key, cycle):
        row = bucket.setdefault(key, {"cycles": 0, "clinical_pregnancies": 0, "live_births": 0})
        row["cycles"] += 1
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
            user = db.query(User).filter(User.id == cycle.clinician_id).first()
            if user:
                clinician = f"{user.first_name} {user.last_name}".strip()
        bump(groups["by_clinician"], clinician, cycle)
        bump(groups["by_cycle_type"], cycle.cycle_type, cycle)
    for bucket in groups.values():
        for row in bucket.values():
            denom = row["cycles"] or 1
            row["clinical_pregnancy_rate"] = round(row["clinical_pregnancies"] / denom, 4)
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
        ArtAppointment.hospital_id == hospital_id, ArtAppointment.status == "done",
    ).all()
    procedures = {"iui": 0, "opu": 0, "transfer": 0}
    for appt in appointments:
        if appt.scheduled_date and appt.scheduled_date.year == year and appt.scheduled_date.month == month:
            if appt.kind in procedures:
                procedures[appt.kind] += 1
    cycles = db.query(ArtCycle).filter(ArtCycle.hospital_id == hospital_id).all()
    outcomes = [c for c in cycles if in_month(c.outcome_recorded_at)]
    complications = [
        {"cycle_number": c.cycle_number, "complication": c.complication}
        for c in outcomes if (c.complication or "").strip()
    ]
    donors = db.query(ArtDonor).filter(ArtDonor.hospital_id == hospital_id).all()
    screened = [d for d in donors if d.screening and in_month(d.created_at)]
    cleared = [d for d in donors if in_month(d.cleared_at)]
    units = db.query(ArtBankUnit).filter(ArtBankUnit.hospital_id == hospital_id).all()
    issued = [u for u in units if u.status in ("issued_internal", "issued_external") and in_month(u.issued_at)]
    received = [u for u in units if u.status == "received_external" and in_month(u.issued_at)]
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
