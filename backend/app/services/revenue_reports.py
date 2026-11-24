"""Period revenue for doctor, patient, and referral reports.

Admission bills include inpatient lab and pharmacy posted to the stay. Lab on
a stay stays inside admission revenue. Pharmacy posted to a stay is reported
as Pharmacy (IP) and removed from the admission figure, so the combined total
does not count it twice. Counter pharmacy stays in the pharmacy column.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import or_
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session

from app.models.billing import Bill
from app.models.inpatient import Admission
from app.models.lab import PatientLabOrder
from app.models.outpatient import Appointment
from app.models.patient import Patient
from app.models.pharmacy import PharmacySale, PharmacySaleReturn, Prescription
from app.models.user import User

OTHER_BILL_TYPES = ("day_care", "procedure", "physiotherapy", "canteen", "catch_up", "art")

MONEY_KEYS = (
    "consultation_revenue",
    "lab_revenue",
    "pharmacy_revenue",
    "pharmacy_ip_revenue",
    "admission_revenue",
    "other_revenue",
)
COUNT_KEYS = (
    "consultation_count",
    "lab_count",
    "pharmacy_count",
    "pharmacy_ip_count",
    "admission_count",
    "other_count",
)


def _money(value) -> float:
    return float(value or 0)


def _norm_person(name: Optional[str]) -> str:
    parts = (name or "").lower().replace(".", " ").split()
    return " ".join(part for part in parts if part != "dr")


def _ref_key(name: Optional[str]) -> str:
    return " ".join((name or "").strip().split()).casefold()


def _doctor_display(user: User) -> str:
    return f"Dr. {user.first_name} {user.last_name}".strip()


def _patient_display(patient: Optional[Patient], fallback: str = "") -> str:
    if patient:
        return f"{patient.first_name or ''} {patient.last_name or ''}".strip() or fallback or "Unknown"
    return fallback or "Unknown"


def _referred_name(patient: Optional[Patient], explicit: Optional[str]) -> Optional[str]:
    raw = ""
    if patient and patient.referred_by:
        raw = patient.referred_by
    elif explicit:
        raw = explicit
    cleaned = " ".join(raw.split()).strip()
    return cleaned or None


def _end_of_day(day):
    return datetime.combine(day, datetime.max.time())


def _blank_amounts() -> dict:
    row = {key: 0.0 for key in MONEY_KEYS}
    row.update({key: 0 for key in COUNT_KEYS})
    return row


def _add_amount(row: dict, stream: str, amount: float):
    row[f"{stream}_revenue"] += amount
    row[f"{stream}_count"] += 1


def _finalize_amounts(row: dict) -> dict:
    for key in MONEY_KEYS:
        row[key] = round(row[key], 2)
    row["total_revenue"] = round(sum(row[key] for key in MONEY_KEYS), 2)
    return row


def _pharmacy_on_admission(sale: PharmacySale) -> bool:
    if sale.inpatient_bill_id:
        return True
    return (sale.billing_mode or "") == "inpatient_bill"


def _return_totals(db: Session, sale_ids) -> dict:
    totals = {}
    if not sale_ids:
        return totals
    for ret in db.query(PharmacySaleReturn).filter(
        PharmacySaleReturn.sale_id.in_(sale_ids),
        PharmacySaleReturn.status == "confirmed",
    ).all():
        totals[ret.sale_id] = totals.get(ret.sale_id, 0.0) + _money(ret.grand_total)
    return totals


def _net_sale(sale: PharmacySale, returned: dict) -> float:
    return round(max(_money(sale.grand_total) - _money(returned.get(sale.id)), 0.0), 2)


def pharmacy_included_on_bills(db: Session, bill_ids) -> dict:
    """Net pharmacy already inside these admission bills, keyed by bill id.

    Used to lift Pharmacy (IP) out of the admission column. Sales posted onto
    the bill count even when the sale date is outside the report period,
    because the bill total in this period already includes them.
    """
    clean = [bill_id for bill_id in set(bill_ids) if bill_id]
    if not clean:
        return {}
    sales = db.query(PharmacySale).filter(
        PharmacySale.inpatient_bill_id.in_(clean),
        PharmacySale.status == "completed",
    ).all()
    returned = _return_totals(db, [sale.id for sale in sales])
    included = {}
    for sale in sales:
        net = _net_sale(sale, returned)
        if net <= 0 or not sale.inpatient_bill_id:
            continue
        bill_id = sale.inpatient_bill_id
        included[bill_id] = round(included.get(bill_id, 0.0) + net, 2)
    return included


def _lab_on_admission(order: PatientLabOrder) -> bool:
    return bool(order.admission_id or order.inpatient_bill_id)


def _load_users(db: Session, hospital_id: int):
    users = db.query(User).filter(User.hospital_id == hospital_id).all()
    by_id = {user.id: user for user in users}
    by_name = {}
    for user in users:
        key = _norm_person(f"{user.first_name or ''} {user.last_name or ''}")
        if key and key not in by_name:
            by_name[key] = user
    return by_id, by_name


def _patients_by_ids(db: Session, ids) -> dict:
    clean = [item for item in set(ids) if item]
    if not clean:
        return {}
    return {patient.id: patient for patient in db.query(Patient).filter(Patient.id.in_(clean)).all()}


def _patients_by_uuid(db: Session, hospital_id: int, uuids) -> dict:
    clean = [item for item in set(uuids) if item]
    if not clean:
        return {}
    rows = db.query(Patient).filter(
        Patient.hospital_id == hospital_id,
        Patient.patient_id.in_(clean),
    ).all()
    return {patient.patient_id: patient for patient in rows}


def load_period_activity(db: Session, hospital_id: int, d_from, d_to, patient_id: Optional[int] = None) -> dict:
    """Billed activity in the period, one dict per source row."""
    users_by_id, users_by_name = _load_users(db, hospital_id)
    patient_uuid = None
    if patient_id:
        chosen = db.query(Patient).filter(
            Patient.id == patient_id,
            Patient.hospital_id == hospital_id,
        ).first()
        patient_uuid = chosen.patient_id if chosen else ""

    consults = []
    apt_q = db.query(Appointment).join(Patient).filter(
        Patient.hospital_id == hospital_id,
        Appointment.appointment_date >= d_from,
        Appointment.appointment_date <= _end_of_day(d_to),
        Appointment.payment_status != "cancelled",
    )
    if patient_id:
        apt_q = apt_q.filter(Appointment.patient_id == patient_id)
    appointments = apt_q.all()
    apt_patients = _patients_by_ids(db, [row.patient_id for row in appointments])
    for appointment in appointments:
        amount = _money(appointment.consultation_fee) + _money(appointment.registration_fee)
        if amount <= 0:
            continue
        patient = apt_patients.get(appointment.patient_id)
        consults.append({
            "amount": amount,
            "doctor_id": appointment.doctor_id or None,
            "doctor_label": None,
            "patient": patient,
            "patient_name": _patient_display(patient),
            "referred_by": _referred_name(patient, appointment.referred_by),
            "on_admission": False,
        })

    labs = []
    lab_q = db.query(PatientLabOrder).join(Patient).filter(
        Patient.hospital_id == hospital_id,
        sql_func.date(PatientLabOrder.order_date) >= d_from,
        sql_func.date(PatientLabOrder.order_date) <= d_to,
        PatientLabOrder.cancelled_at.is_(None),
        PatientLabOrder.bill_cancelled_at.is_(None),
        or_(PatientLabOrder.status.is_(None), PatientLabOrder.status != "cancelled"),
    )
    if patient_id:
        lab_q = lab_q.filter(PatientLabOrder.patient_id == patient_id)
    orders = lab_q.all()
    lab_patients = _patients_by_ids(db, [row.patient_id for row in orders])
    for order in orders:
        amount = _money(order.amount)
        if amount <= 0:
            continue
        patient = lab_patients.get(order.patient_id)
        labs.append({
            "amount": amount,
            "doctor_id": order.doctor_id or None,
            "doctor_label": None,
            "patient": patient,
            "patient_name": _patient_display(patient),
            "referred_by": _referred_name(patient, order.referred_by),
            "on_admission": _lab_on_admission(order),
        })

    pharmacies = []
    sale_q = db.query(PharmacySale).filter(
        PharmacySale.hospital_id == hospital_id,
        PharmacySale.status == "completed",
        sql_func.date(PharmacySale.sale_date) >= d_from,
        sql_func.date(PharmacySale.sale_date) <= d_to,
    )
    if patient_id:
        sale_q = sale_q.filter(PharmacySale.patient_ip_id == patient_uuid)
    sales = sale_q.all()
    sale_ids = [sale.id for sale in sales]
    returned = _return_totals(db, sale_ids)
    rx_doctor = {}
    if sale_ids:
        for rx in db.query(Prescription).filter(Prescription.pharmacy_sale_id.in_(sale_ids)).all():
            if rx.pharmacy_sale_id and rx.doctor_id:
                rx_doctor[rx.pharmacy_sale_id] = rx.doctor_id
    sale_patients = _patients_by_uuid(db, hospital_id, [sale.patient_ip_id for sale in sales])
    for sale in sales:
        net = _net_sale(sale, returned)
        if net <= 0:
            continue
        doctor_id = rx_doctor.get(sale.id)
        doctor_label = None
        if not doctor_id:
            matched = users_by_name.get(_norm_person(sale.doctor_name))
            if matched:
                doctor_id = matched.id
            elif (sale.doctor_name or "").strip():
                doctor_label = sale.doctor_name.strip()
        patient = sale_patients.get(sale.patient_ip_id)
        pharmacies.append({
            "amount": net,
            "doctor_id": doctor_id or None,
            "doctor_label": doctor_label,
            "patient": patient,
            "patient_name": _patient_display(patient, sale.patient_name or "Walk-in"),
            "referred_by": _referred_name(patient, None),
            "on_admission": _pharmacy_on_admission(sale),
        })

    admissions = []
    adm_q = db.query(Bill).join(Patient).filter(
        Patient.hospital_id == hospital_id,
        Bill.bill_type == "admission",
        sql_func.date(Bill.bill_date) >= d_from,
        sql_func.date(Bill.bill_date) <= d_to,
        Bill.status != "cancelled",
        or_(Bill.bill_subtype.is_(None), Bill.bill_subtype != "advance_receipt"),
    )
    if patient_id:
        adm_q = adm_q.filter(Bill.patient_id == patient_id)
    adm_bills = adm_q.all()
    adm_ids = [bill.reference_id for bill in adm_bills if bill.reference_id]
    adm_by_id = {}
    if adm_ids:
        adm_by_id = {
            row.id: row for row in db.query(Admission).filter(Admission.id.in_(adm_ids)).all()
        }
    adm_patients = _patients_by_ids(db, [bill.patient_id for bill in adm_bills])
    pharmacy_on_bill = pharmacy_included_on_bills(db, [bill.id for bill in adm_bills])
    for bill in adm_bills:
        admission = adm_by_id.get(bill.reference_id) if bill.reference_id else None
        patient = adm_patients.get(bill.patient_id)
        gross = _money(bill.total_amount)
        pharmacy_inside = _money(pharmacy_on_bill.get(bill.id))
        admissions.append({
            "amount": round(max(gross - pharmacy_inside, 0.0), 2),
            "doctor_id": admission.admitting_doctor_id if admission and admission.admitting_doctor_id else None,
            "doctor_label": None,
            "patient": patient,
            "patient_name": _patient_display(patient),
            "referred_by": _referred_name(patient, bill.referred_by),
            "on_admission": False,
        })

    others = []
    other_q = db.query(Bill).join(Patient).filter(
        Patient.hospital_id == hospital_id,
        Bill.bill_type.in_(OTHER_BILL_TYPES),
        sql_func.date(Bill.bill_date) >= d_from,
        sql_func.date(Bill.bill_date) <= d_to,
        Bill.status != "cancelled",
        or_(Bill.bill_subtype.is_(None), Bill.bill_subtype != "advance_receipt"),
    )
    if patient_id:
        other_q = other_q.filter(Bill.patient_id == patient_id)
    other_bills = other_q.all()
    other_patients = _patients_by_ids(db, [bill.patient_id for bill in other_bills])
    for bill in other_bills:
        amount = _money(bill.total_amount)
        if amount == 0:
            continue
        patient = other_patients.get(bill.patient_id)
        others.append({
            "amount": amount,
            "doctor_id": None,
            "doctor_label": None,
            "patient": patient,
            "patient_name": _patient_display(patient),
            "referred_by": _referred_name(patient, bill.referred_by),
            "on_admission": False,
        })

    return {
        "users_by_id": users_by_id,
        "consults": consults,
        "labs": labs,
        "pharmacies": pharmacies,
        "admissions": admissions,
        "others": others,
    }


def _doctor_key(event: dict) -> tuple:
    if event.get("doctor_id"):
        return ("user", event["doctor_id"])
    label = event.get("doctor_label")
    if label:
        return ("name", _norm_person(label))
    return ("user", 0)


def _doctor_name(event: dict, users_by_id: dict) -> tuple:
    doctor_id = event.get("doctor_id") or 0
    if doctor_id:
        user = users_by_id.get(doctor_id)
        if user:
            return doctor_id, _doctor_display(user)
        return doctor_id, f"User #{doctor_id}"
    if event.get("doctor_label"):
        return 0, event["doctor_label"]
    return 0, "(Unassigned)"


def _event_streams(activity: dict, *, pharmacy_folded: bool = False):
    """Yield (stream, event).

    Lab posted onto an admission stays out of the lab column. Pharmacy posted
    onto an admission is its own ``pharmacy_ip`` stream. ``pharmacy_folded``
    yields only those inpatient sales, under the pharmacy stream, for the
    Pharmacy (IP) module filter.
    """
    for event in activity["consults"]:
        yield "consultation", event
    for event in activity["admissions"]:
        yield "admission", event
    if pharmacy_folded:
        for event in activity["pharmacies"]:
            if event.get("on_admission"):
                yield "pharmacy", event
        return
    for event in activity["labs"]:
        if not event.get("on_admission"):
            yield "lab", event
    for event in activity["pharmacies"]:
        if event.get("on_admission"):
            yield "pharmacy_ip", event
        else:
            yield "pharmacy", event
    for event in activity["others"]:
        yield "other", event


def doctor_revenue(db: Session, hospital_id: int, d_from, d_to, module: Optional[str] = None, patient_id: Optional[int] = None) -> dict:
    mod = (module or "all").strip().lower()
    if mod in ("", "all"):
        allowed = {"consultation", "admission", "lab", "pharmacy", "pharmacy_ip"}
        pharmacy_folded = False
    elif mod == "opd":
        allowed = {"consultation"}
        pharmacy_folded = False
    elif mod == "inpatient":
        allowed = {"admission", "pharmacy_ip"}
        pharmacy_folded = False
    elif mod == "lab":
        allowed = {"lab"}
        pharmacy_folded = False
    elif mod == "pharmacy":
        allowed = {"pharmacy"}
        pharmacy_folded = False
    elif mod == "pharmacy_ip":
        allowed = {"pharmacy"}
        pharmacy_folded = True
    else:
        allowed = set()
        pharmacy_folded = False

    activity = load_period_activity(db, hospital_id, d_from, d_to, patient_id=patient_id)
    buckets = {}
    for stream, event in _event_streams(activity, pharmacy_folded=pharmacy_folded):
        if stream not in allowed:
            continue
        key = _doctor_key(event)
        row = buckets.get(key)
        if row is None:
            doctor_id, doctor_name = _doctor_name(event, activity["users_by_id"])
            row = {"doctor_id": doctor_id, "doctor_name": doctor_name, **_blank_amounts()}
            buckets[key] = row
        _add_amount(row, stream, event["amount"])

    rows = [_finalize_amounts(row) for row in buckets.values()]
    rows.sort(key=lambda row: row["total_revenue"], reverse=True)
    return _payload(d_from, d_to, rows, patient_id=patient_id)


def _patient_key(event: dict) -> tuple:
    patient = event.get("patient")
    if patient is not None:
        return ("id", patient.id)
    return ("name", (event.get("patient_name") or "Walk-in").casefold())


def patient_revenue(db: Session, hospital_id: int, d_from, d_to, patient_id: Optional[int] = None) -> dict:
    activity = load_period_activity(db, hospital_id, d_from, d_to, patient_id=patient_id)
    buckets = {}
    for stream, event in _event_streams(activity, pharmacy_folded=False):
        key = _patient_key(event)
        row = buckets.get(key)
        if row is None:
            patient = event.get("patient")
            row = {
                "patient_id": patient.id if patient is not None else 0,
                "patient_name": event.get("patient_name") or "Unknown",
                "mrn": (patient.mrn or "") if patient is not None else "",
                "phone": (patient.primary_phone or "") if patient is not None else "",
                "referred_by": event.get("referred_by") or "",
                **_blank_amounts(),
            }
            buckets[key] = row
        elif not row.get("referred_by") and event.get("referred_by"):
            row["referred_by"] = event["referred_by"]
        _add_amount(row, stream, event["amount"])

    rows = [_finalize_amounts(row) for row in buckets.values()]
    rows.sort(key=lambda row: row["total_revenue"], reverse=True)
    return _payload(d_from, d_to, rows, patient_id=patient_id)


def referral_revenue(
    db: Session,
    hospital_id: int,
    d_from,
    d_to,
    referral_name: Optional[str] = None,
    referral_id: Optional[int] = None,
) -> dict:
    """Same patients as Referral Management, with Pharmacy (IP) in its own column.

    Commission is not included. Referral Management still keeps inpatient
    pharmacy inside the IP total used for commission. This report lifts that
    pharmacy into ``pharmacy_ip_revenue`` and reduces admission by the same
    amount when the sale is already on the admission bill.
    """
    from app.routes.referrals import revenue_by_referral
    rows = revenue_by_referral(db, hospital_id, d_from, d_to)
    if referral_name is not None:
        wanted = _ref_key(referral_name)
        rows = [row for row in rows if _ref_key(row.get("referral_name")) == wanted]
    rows = [_split_referral_pharmacy_ip(row) for row in rows]
    payload = _payload(d_from, d_to, rows)
    if referral_id:
        payload["referral_id"] = referral_id
    return payload


def _split_referral_pharmacy_ip(row: dict) -> dict:
    """Move pharmacy already inside the IP total into the Pharmacy (IP) column."""
    out = dict(row)
    included = _money(out.pop("pharmacy_ip_in_admission", 0))
    ip_pharmacy = _money(out.get("pharmacy_ip_revenue"))
    admission = _money(out.get("admission_revenue"))
    removed = min(included, admission)
    out["admission_revenue"] = round(admission - removed, 2)
    out["pharmacy_ip_revenue"] = round(ip_pharmacy, 2)
    out["pharmacy_ip_count"] = int(out.get("pharmacy_ip_count") or 0)
    out["total_revenue"] = round(_money(out.get("total_revenue")) - removed + ip_pharmacy, 2)
    return out


def _payload(d_from, d_to, rows, patient_id: Optional[int] = None) -> dict:
    totals = _blank_amounts()
    for row in rows:
        for key in MONEY_KEYS:
            totals[key] += row.get(key) or 0
        for key in COUNT_KEYS:
            totals[key] += row.get(key) or 0
    totals = _finalize_amounts(totals)
    totals["patient_count"] = sum(row.get("patient_count") or 0 for row in rows)
    body = {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "rows": rows,
        "totals": {
            "grand_total": totals["total_revenue"],
            "consultation_total": totals["consultation_revenue"],
            "lab_total": totals["lab_revenue"],
            "pharmacy_total": totals["pharmacy_revenue"],
            "pharmacy_ip_total": totals["pharmacy_ip_revenue"],
            "admission_total": totals["admission_revenue"],
            "other_total": totals["other_revenue"],
            "consultation_count": totals["consultation_count"],
            "lab_count": totals["lab_count"],
            "pharmacy_count": totals["pharmacy_count"],
            "pharmacy_ip_count": totals["pharmacy_ip_count"],
            "admission_count": totals["admission_count"],
            "other_count": totals["other_count"],
            "patient_count": totals["patient_count"],
        },
    }
    if patient_id:
        body["patient_id"] = patient_id
    return body
