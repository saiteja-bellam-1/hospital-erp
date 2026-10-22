"""Money actually received, grouped by payment type.

The central ``payments`` table is only part of the till. OPD, lab, pharmacy
counter, canteen, and admission deposits keep the tender on their own rows.
This helper unions those sources for one date range and nets refunds, without
counting the same receipt twice when a catch-up flow also wrote a Payment.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import and_, func as sql_func, or_
from sqlalchemy.orm import Session

from app.models.billing import Bill, Payment
from app.models.canteen import CanteenSale
from app.models.inpatient import Admission, AdmissionDeposit
from app.models.lab import PatientLabOrder
from app.models.outpatient import Appointment
from app.models.patient import Patient
from app.models.pharmacy import PharmacySale

METHOD_ORDER = ("cash", "card", "upi", "cheque", "online", "insurance", "bank_transfer")

_SKIP_METHODS = frozenset({
    "scheme_approval", "credit", "credit_note", "partner", "partner_settled",
})

_ALIASES = {
    "gpay": "upi",
    "phonepe": "upi",
    "google_pay": "upi",
    "bank": "bank_transfer",
    "neft": "bank_transfer",
    "rtgs": "bank_transfer",
    "tpa": "insurance",
}

# Billing-page bill_type and reports module key → which tills to include.
_SOURCE_KEY = {
    None: "all",
    "": "all",
    "all": "all",
    "consultation": "opd",
    "appointment": "opd",
    "outpatient": "opd",
    "opd": "opd",
    "lab": "lab",
    "pharmacy": "pharmacy",
    "pharmacy_ip": "pharmacy_ip",
    "admission": "inpatient",
    "inpatient": "inpatient",
    "deposit": "inpatient",
    "physiotherapy": "physiotherapy",
    "physio": "physiotherapy",
    "day_care": "day_care",
    "procedure": "day_care",
    "canteen": "canteen",
    "catch_up": "catch_up",
    "misc": "catch_up",
    "consolidated": "consolidated",
}

_ALL_SOURCES = frozenset({
    "opd", "lab", "pharmacy", "inpatient", "physiotherapy",
    "day_care", "canteen", "catch_up", "consolidated",
})

_PAYMENT_BILL_TYPES = {
    "opd": ("consultation", "outpatient"),
    "consolidated": ("consolidated",),
    "lab": ("lab",),
    "pharmacy": ("pharmacy",),
    "inpatient": ("admission",),
    "physiotherapy": ("physiotherapy",),
    "day_care": ("day_care", "procedure"),
    "canteen": ("canteen",),
    "catch_up": ("catch_up",),
}


def sources_for(bill_type: Optional[str] = None, module: Optional[str] = None) -> frozenset:
    """Which tills a billing tab or a reports module filter should include.

    The reports module ``opd`` follows the GST map and also includes
    consolidated bills. The bills-page Outpatient tab does not.
    """
    if module is not None:
        key = _SOURCE_KEY.get(module.strip().lower(), module.strip().lower())
        if key == "all":
            return _ALL_SOURCES
        if key == "opd":
            return frozenset({"opd", "consolidated"})
        if key == "pharmacy_ip":
            return frozenset()
        if key in _ALL_SOURCES:
            return frozenset({key})
        return frozenset()
    key = _SOURCE_KEY.get((bill_type or "all").strip().lower(), (bill_type or "all").strip().lower())
    if key == "all":
        return _ALL_SOURCES
    if key == "pharmacy_ip":
        return frozenset()
    if key in _ALL_SOURCES:
        return frozenset({key})
    return frozenset()


def normalize_method(raw: Optional[str], *, default: str = "cash") -> Optional[str]:
    """Canonical tender name. None means this row is not money received."""
    text = (raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    if not text:
        text = default
    text = _ALIASES.get(text, text)
    if text in _SKIP_METHODS:
        return None
    return text


def _day(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return None


def _in_range(column, d_from: date, d_to: date):
    return and_(sql_func.date(column) >= d_from, sql_func.date(column) <= d_to)


def _receipt_day_filter(primary, fallback, d_from: date, d_to: date):
    """Prefer the receipt timestamp; fall back when the source never stored one."""
    return or_(
        and_(primary.isnot(None), _in_range(primary, d_from, d_to)),
        and_(primary.is_(None), _in_range(fallback, d_from, d_to)),
    )


def _add(by_day: dict, methods_seen: set, when, method: Optional[str], amount: float) -> None:
    if method is None:
        return
    amt = float(amount or 0)
    if abs(amt) < 0.005:
        return
    day = _day(when)
    if not day:
        return
    methods_seen.add(method)
    row = by_day.setdefault(day, {"date": day, "total": 0.0, "refunds": 0.0, "by_method": {}})
    row["total"] += amt
    if amt < 0:
        row["refunds"] += -amt
    row["by_method"][method] = row["by_method"].get(method, 0.0) + amt


def _sort_methods(seen: set) -> list:
    head = [m for m in METHOD_ORDER if m in seen]
    tail = sorted(seen.difference(head))
    return head + tail


def _linked_reference_ids(db: Session, hospital_id: int, bill_type: str) -> set:
    rows = (
        db.query(Bill.reference_id)
        .join(Payment, Payment.bill_id == Bill.id)
        .filter(
            Bill.hospital_id == hospital_id,
            Bill.bill_type == bill_type,
            Bill.reference_id.isnot(None),
        )
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def _patient_name_filter(first, last, phone, patient_search: Optional[str]):
    if not patient_search:
        return None
    q = f"%{patient_search.strip()}%"
    return or_(first.ilike(q), last.ilike(q), phone.ilike(q))


def _method_for_payment(payment: Payment, bill: Bill) -> Optional[str]:
    notes = (payment.notes or "").lower()
    if (bill.bill_type or "") == "admission":
        # Patient cash on an admission is an AdmissionDeposit. A Payment on
        # the admission bill is a TPA/insurance receipt (or its reversal).
        # Catch-up stays also write a Payment for the same deposit — skip those.
        if "bill split" not in notes and "reversal of split" not in notes:
            return None
        return "insurance"
    return normalize_method(payment.payment_method_name)


def collection_by_method(
    db: Session,
    hospital_id: int,
    d_from: date,
    d_to: date,
    *,
    sources: Optional[set] = None,
    patient_id: Optional[int] = None,
    patient_search: Optional[str] = None,
    doctor_id: Optional[int] = None,
    referred_by: Optional[str] = None,
) -> dict:
    """Net receipts by day and by tender for the selected tills."""
    active = frozenset(sources) if sources is not None else _ALL_SOURCES
    by_day: dict = {}
    methods_seen: set = set()
    # Doctor / referral filters hide counter sales on the bills list (those
    # rows have no doctor or referral). Mirror that so the strip matches.
    hide_counters = bool(doctor_id or referred_by or patient_id)

    if active:
        _add_payments(
            db, hospital_id, d_from, d_to, active, by_day, methods_seen,
            patient_id=patient_id, patient_search=patient_search,
        )

    if "opd" in active:
        _add_appointments(
            db, hospital_id, d_from, d_to, by_day, methods_seen,
            patient_id=patient_id, patient_search=patient_search,
            doctor_id=doctor_id, referred_by=referred_by,
        )
    if "lab" in active:
        _add_lab_orders(
            db, hospital_id, d_from, d_to, by_day, methods_seen,
            patient_id=patient_id, patient_search=patient_search,
            doctor_id=doctor_id, referred_by=referred_by,
        )
    if "pharmacy" in active and not hide_counters:
        _add_pharmacy_sales(
            db, hospital_id, d_from, d_to, by_day, methods_seen,
            patient_search=patient_search,
        )
    if "canteen" in active and not hide_counters:
        _add_canteen_sales(
            db, hospital_id, d_from, d_to, by_day, methods_seen,
            patient_search=patient_search,
        )
    if "inpatient" in active:
        _add_deposits(
            db, hospital_id, d_from, d_to, by_day, methods_seen,
            patient_id=patient_id, patient_search=patient_search,
        )

    methods = _sort_methods(methods_seen)
    rows = []
    grand_by_method: dict = {m: 0.0 for m in methods}
    for row in sorted(by_day.values(), key=lambda r: r["date"]):
        rounded_methods = {k: round(v, 2) for k, v in row["by_method"].items()}
        for key, value in rounded_methods.items():
            grand_by_method[key] = grand_by_method.get(key, 0.0) + value
        rows.append({
            "date": row["date"],
            "total": round(row["total"], 2),
            "refunds": round(row["refunds"], 2),
            "by_method": rounded_methods,
        })
    grand_by_method = {k: round(v, 2) for k, v in grand_by_method.items()}
    net = round(sum(r["total"] for r in rows), 2)
    refunds = round(sum(r["refunds"] for r in rows), 2)
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "methods": methods,
        "by_method": grand_by_method,
        "rows": rows,
        "totals": {
            "net_collected": net,
            "refunds": refunds,
            "gross_collected": round(net + refunds, 2),
        },
    }


def _add_payments(
    db, hospital_id, d_from, d_to, active, by_day, methods_seen, *,
    patient_id, patient_search,
) -> None:
    bill_types = []
    for source in active:
        bill_types.extend(_PAYMENT_BILL_TYPES.get(source, ()))
    if not bill_types:
        return
    q = (
        db.query(Payment, Bill)
        .join(Bill, Payment.bill_id == Bill.id)
        .join(Patient, Bill.patient_id == Patient.id)
        .filter(
            Bill.hospital_id == hospital_id,
            Bill.bill_type.in_(bill_types),
            _in_range(Payment.payment_date, d_from, d_to),
        )
    )
    if patient_id:
        q = q.filter(Bill.patient_id == patient_id)
    name_filter = _patient_name_filter(
        Patient.first_name, Patient.last_name, Patient.primary_phone, patient_search,
    )
    if name_filter is not None:
        q = q.filter(name_filter)
    for payment, bill in q.all():
        _add(
            by_day, methods_seen, payment.payment_date,
            _method_for_payment(payment, bill), payment.amount_paid,
        )


def _add_appointments(
    db, hospital_id, d_from, d_to, by_day, methods_seen, *,
    patient_id, patient_search, doctor_id, referred_by,
) -> None:
    linked = _linked_reference_ids(db, hospital_id, "consultation")
    q = (
        db.query(Appointment)
        .join(Patient, Appointment.patient_id == Patient.id)
        .filter(
            Patient.hospital_id == hospital_id,
            Appointment.payment_status == "paid",
            _receipt_day_filter(Appointment.payment_date, Appointment.created_at, d_from, d_to),
        )
    )
    if patient_id:
        q = q.filter(Appointment.patient_id == patient_id)
    if doctor_id:
        q = q.filter(Appointment.doctor_id == doctor_id)
    if referred_by:
        q = q.filter(Appointment.referred_by.ilike(f"%{referred_by}%"))
    name_filter = _patient_name_filter(
        Patient.first_name, Patient.last_name, Patient.primary_phone, patient_search,
    )
    if name_filter is not None:
        q = q.filter(name_filter)
    for apt in q.all():
        if apt.id in linked:
            continue
        when = apt.payment_date or apt.created_at
        _add(by_day, methods_seen, when, normalize_method(apt.payment_method), apt.final_amount)


def _add_lab_orders(
    db, hospital_id, d_from, d_to, by_day, methods_seen, *,
    patient_id, patient_search, doctor_id, referred_by,
) -> None:
    linked_ids = _linked_reference_ids(db, hospital_id, "lab")
    linked_groups = set()
    if linked_ids:
        groups = (
            db.query(PatientLabOrder.lab_bill_group_id)
            .filter(
                PatientLabOrder.id.in_(linked_ids),
                PatientLabOrder.lab_bill_group_id.isnot(None),
            )
            .all()
        )
        linked_groups = {row[0] for row in groups}
    q = (
        db.query(PatientLabOrder)
        .join(Patient, PatientLabOrder.patient_id == Patient.id)
        .filter(
            Patient.hospital_id == hospital_id,
            PatientLabOrder.payment_status == "paid",
            PatientLabOrder.admission_id.is_(None),
            PatientLabOrder.status != "cancelled",
            or_(PatientLabOrder.bill_to.is_(None), PatientLabOrder.bill_to == "patient"),
            _receipt_day_filter(PatientLabOrder.payment_date, PatientLabOrder.order_date, d_from, d_to),
        )
    )
    if patient_id:
        q = q.filter(PatientLabOrder.patient_id == patient_id)
    if doctor_id:
        q = q.filter(PatientLabOrder.doctor_id == doctor_id)
    if referred_by:
        q = q.filter(PatientLabOrder.referred_by.ilike(f"%{referred_by}%"))
    name_filter = _patient_name_filter(
        Patient.first_name, Patient.last_name, Patient.primary_phone, patient_search,
    )
    if name_filter is not None:
        q = q.filter(name_filter)
    for order in q.all():
        if order.id in linked_ids:
            continue
        if order.lab_bill_group_id and order.lab_bill_group_id in linked_groups:
            continue
        when = order.payment_date or order.order_date
        _add(by_day, methods_seen, when, normalize_method(order.payment_method), order.amount)


def _add_pharmacy_sales(db, hospital_id, d_from, d_to, by_day, methods_seen, *, patient_search) -> None:
    linked = _linked_reference_ids(db, hospital_id, "pharmacy")
    q = db.query(PharmacySale).filter(
        PharmacySale.hospital_id == hospital_id,
        PharmacySale.status == "completed",
        or_(
            PharmacySale.billing_mode == "cash_at_pharmacy",
            PharmacySale.billing_mode.is_(None),
        ),
        _in_range(PharmacySale.sale_date, d_from, d_to),
    )
    if patient_search:
        qtext = f"%{patient_search.strip()}%"
        q = q.filter(or_(
            PharmacySale.patient_name.ilike(qtext),
            PharmacySale.patient_phone.ilike(qtext),
        ))
    for sale in q.all():
        if sale.id in linked:
            continue
        _add(
            by_day, methods_seen, sale.sale_date,
            normalize_method(sale.payment_type), sale.grand_total,
        )


def _add_canteen_sales(db, hospital_id, d_from, d_to, by_day, methods_seen, *, patient_search) -> None:
    linked = _linked_reference_ids(db, hospital_id, "canteen")
    q = db.query(CanteenSale).filter(
        CanteenSale.hospital_id == hospital_id,
        CanteenSale.status == "completed",
        _in_range(CanteenSale.sale_date, d_from, d_to),
    )
    if patient_search:
        qtext = f"%{patient_search.strip()}%"
        q = q.filter(or_(
            CanteenSale.customer_name.ilike(qtext),
            CanteenSale.customer_phone.ilike(qtext),
        ))
    for sale in q.all():
        if sale.id in linked:
            continue
        _add(
            by_day, methods_seen, sale.sale_date,
            normalize_method(sale.payment_type), sale.grand_total,
        )


def _add_deposits(
    db, hospital_id, d_from, d_to, by_day, methods_seen, *,
    patient_id, patient_search,
) -> None:
    q = (
        db.query(AdmissionDeposit)
        .join(Admission, AdmissionDeposit.admission_id == Admission.id)
        .join(Patient, Admission.patient_id == Patient.id)
        .filter(
            AdmissionDeposit.hospital_id == hospital_id,
            _in_range(AdmissionDeposit.received_at, d_from, d_to),
        )
    )
    if patient_id:
        q = q.filter(Admission.patient_id == patient_id)
    name_filter = _patient_name_filter(
        Patient.first_name, Patient.last_name, Patient.primary_phone, patient_search,
    )
    if name_filter is not None:
        q = q.filter(name_filter)
    for deposit in q.all():
        method = normalize_method(deposit.payment_method)
        if method is None:
            continue
        amount = float(deposit.amount or 0)
        if (deposit.deposit_type or "") == "refund":
            amount = -abs(amount)
        _add(by_day, methods_seen, deposit.received_at, method, amount)
