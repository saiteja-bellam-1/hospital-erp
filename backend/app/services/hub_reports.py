"""Cross-module operational reports for the Billing → Reports hub."""
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sql_func

from app.models.patient import Patient
from app.models.user import User
from app.models.outpatient import Appointment
from app.models.lab import PatientLabOrder, LabTest
from app.models.billing import Bill
from app.models.canteen import CanteenSale, CanteenOrder
from app.models.pharmacy import PharmacySale, PharmacyInventory, Medicine
from app.models.inpatient import Admission, DischargeRecord
from app.services.gst_report_service import _money


def _dt_end(d: date) -> datetime:
    return datetime.combine(d, datetime.max.time())


def opd_activity(db: Session, hospital_id: int, d_from: date, d_to: date) -> dict:
    appts = (
        db.query(Appointment)
        .options(joinedload(Appointment.doctor))
        .join(Patient)
        .filter(
            Patient.hospital_id == hospital_id,
            Appointment.appointment_date >= d_from,
            Appointment.appointment_date <= _dt_end(d_to),
        )
        .all()
    )
    by_status = defaultdict(int)
    by_doctor = {}
    by_type = defaultdict(int)
    billed = collected = 0.0
    no_show = cancelled = completed = 0
    for a in appts:
        st = (a.status or "scheduled").lower()
        pay = (a.payment_status or "").lower()
        by_status[st] += 1
        by_type[(a.appointment_type or "consultation")] += 1
        amt = float(a.final_amount or ((a.consultation_fee or 0) + (a.registration_fee or 0)))
        billed += amt
        if pay == "paid":
            collected += amt
        if st in ("no_show", "noshow"):
            no_show += 1
        elif st == "cancelled":
            cancelled += 1
        elif st in ("completed", "consulted"):
            completed += 1
        doc = a.doctor
        name = f"Dr. {doc.first_name} {doc.last_name}" if doc else "(Unassigned)"
        row = by_doctor.setdefault(a.doctor_id or 0, {
            "doctor_id": a.doctor_id or 0,
            "doctor_name": name,
            "count": 0, "completed": 0, "no_show": 0, "cancelled": 0,
            "billed": 0.0, "collected": 0.0,
        })
        row["count"] += 1
        row["billed"] += amt
        if pay == "paid":
            row["collected"] += amt
        if st in ("no_show", "noshow"):
            row["no_show"] += 1
        elif st == "cancelled":
            row["cancelled"] += 1
        elif st in ("completed", "consulted"):
            row["completed"] += 1
    total = len(appts)
    for r in by_doctor.values():
        r["billed"] = _money(r["billed"])
        r["collected"] = _money(r["collected"])
        r["no_show_pct"] = round(r["no_show"] * 100 / r["count"], 1) if r["count"] else 0
    doctors = sorted(by_doctor.values(), key=lambda r: -r["count"])
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "totals": {
            "appointments": total,
            "completed": completed,
            "no_show": no_show,
            "cancelled": cancelled,
            "no_show_pct": round(no_show * 100 / total, 1) if total else 0,
            "billed": _money(billed),
            "collected": _money(collected),
            "outstanding": _money(max(billed - collected, 0)),
        },
        "by_status": [{"status": k, "count": v} for k, v in sorted(by_status.items())],
        "by_type": [{"type": k, "count": v} for k, v in sorted(by_type.items())],
        "rows": doctors,
    }


def lab_volume(db: Session, hospital_id: int, d_from: date, d_to: date) -> dict:
    orders = (
        db.query(PatientLabOrder)
        .options(joinedload(PatientLabOrder.test))
        .join(Patient)
        .filter(
            Patient.hospital_id == hospital_id,
            sql_func.date(PatientLabOrder.created_at) >= d_from,
            sql_func.date(PatientLabOrder.created_at) <= d_to,
            PatientLabOrder.status != "deleted",
        )
        .all()
    )
    by_status = defaultdict(int)
    by_test = {}
    billed = 0.0
    pending = completed = cancelled = 0
    tat_hours = []
    for o in orders:
        st = (o.status or "ordered").lower()
        by_status[st] += 1
        billed += float(o.amount or 0)
        if st == "completed":
            completed += 1
            if o.created_at and o.completion_date:
                delta = o.completion_date - (o.created_at.replace(tzinfo=None) if getattr(o.created_at, "tzinfo", None) else o.created_at)
                if hasattr(delta, "total_seconds"):
                    tat_hours.append(delta.total_seconds() / 3600.0)
        elif st == "cancelled":
            cancelled += 1
        else:
            pending += 1
        name = o.test.name if o.test else f"Test #{o.test_id}"
        trow = by_test.setdefault(name, {"test": name, "count": 0, "completed": 0, "pending": 0, "billed": 0.0})
        trow["count"] += 1
        trow["billed"] += float(o.amount or 0)
        if st == "completed":
            trow["completed"] += 1
        elif st != "cancelled":
            trow["pending"] += 1
    for r in by_test.values():
        r["billed"] = _money(r["billed"])
    tests = sorted(by_test.values(), key=lambda r: -r["count"])[:40]
    avg_tat = round(sum(tat_hours) / len(tat_hours), 1) if tat_hours else None
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "totals": {
            "orders": len(orders),
            "completed": completed,
            "pending": pending,
            "cancelled": cancelled,
            "billed": _money(billed),
            "avg_tat_hours": avg_tat,
        },
        "by_status": [{"status": k, "count": v} for k, v in sorted(by_status.items())],
        "rows": tests,
    }


def daycare_volume(db: Session, hospital_id: int, d_from: date, d_to: date) -> dict:
    bills = db.query(Bill).options(joinedload(Bill.patient), joinedload(Bill.payments)).join(Patient).filter(
        Patient.hospital_id == hospital_id,
        Bill.bill_type.in_(("day_care", "procedure")),
        sql_func.date(Bill.bill_date) >= d_from,
        sql_func.date(Bill.bill_date) <= d_to,
        Bill.status != "cancelled",
    ).all()
    by_status = defaultdict(lambda: {"status": "", "count": 0, "billed": 0.0})
    billed = collected = 0.0
    rows = []
    for b in bills:
        amt = float(b.total_amount or 0)
        paid = sum(float(p.amount_paid or 0) for p in (b.payments or []))
        billed += amt
        collected += paid
        st = b.status or "pending"
        bucket = by_status[st]
        bucket["status"] = st
        bucket["count"] += 1
        bucket["billed"] += amt
        p = b.patient
        rows.append({
            "date": b.bill_date.date().isoformat() if b.bill_date else "",
            "number": b.bill_number,
            "party": f"{p.first_name} {p.last_name}" if p else "",
            "billed": _money(amt),
            "status": st,
        })
    for b in by_status.values():
        b["billed"] = _money(b["billed"])
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "totals": {
            "count": len(bills),
            "billed": _money(billed),
            "collected": _money(collected),
            "outstanding": _money(max(billed - collected, 0)),
        },
        "by_status": list(by_status.values()),
        "rows": sorted(rows, key=lambda r: r["date"], reverse=True)[:200],
    }


def canteen_activity(db: Session, hospital_id: int, d_from: date, d_to: date) -> dict:
    sales = db.query(CanteenSale).filter(
        CanteenSale.hospital_id == hospital_id,
        sql_func.date(CanteenSale.sale_date) >= d_from,
        sql_func.date(CanteenSale.sale_date) <= d_to,
        CanteenSale.status == "completed",
    ).all()
    orders = db.query(CanteenOrder).filter(
        CanteenOrder.hospital_id == hospital_id,
        sql_func.date(CanteenOrder.ordered_at) >= d_from,
        sql_func.date(CanteenOrder.ordered_at) <= d_to,
        CanteenOrder.status != "cancelled",
    ).all()
    pos_total = sum(float(s.grand_total or 0) for s in sales)
    by_pay = defaultdict(lambda: {"method": "", "count": 0, "amount": 0.0})
    for s in sales:
        m = (s.payment_type or "cash").lower()
        by_pay[m]["method"] = m
        by_pay[m]["count"] += 1
        by_pay[m]["amount"] += float(s.grand_total or 0)
    for b in by_pay.values():
        b["amount"] = _money(b["amount"])
    ip_by_status = defaultdict(int)
    for o in orders:
        ip_by_status[o.status or "pending"] += 1
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "totals": {
            "pos_bills": len(sales),
            "pos_amount": _money(pos_total),
            "ip_orders": len(orders),
            "ip_billed": sum(1 for o in orders if o.billed),
        },
        "by_payment": list(by_pay.values()),
        "ip_by_status": [{"status": k, "count": v} for k, v in sorted(ip_by_status.items())],
        "rows": [
            {
                "date": s.sale_date.date().isoformat() if s.sale_date else "",
                "number": s.sale_number,
                "party": s.customer_name or "Walk-in",
                "billed": _money(s.grand_total),
                "status": s.status,
            }
            for s in sales[:200]
        ],
    }


def pharmacy_sales_ops(db: Session, hospital_id: int, d_from: date, d_to: date) -> dict:
    sales = db.query(PharmacySale).filter(
        PharmacySale.hospital_id == hospital_id,
        PharmacySale.status == "completed",
        sql_func.date(PharmacySale.sale_date) >= d_from,
        sql_func.date(PharmacySale.sale_date) <= d_to,
    ).all()
    by_day = {}
    billed = tax = disc = 0.0
    for s in sales:
        day = s.sale_date.date().isoformat() if s.sale_date else "unknown"
        row = by_day.setdefault(day, {"date": day, "count": 0, "billed": 0.0, "tax": 0.0, "discount": 0.0})
        row["count"] += 1
        row["billed"] += float(s.grand_total or 0)
        row["tax"] += float(s.tax_total or 0)
        row["discount"] += float(s.discount_total or 0)
        billed += float(s.grand_total or 0)
        tax += float(s.tax_total or 0)
        disc += float(s.discount_total or 0)
    rows = []
    for day in sorted(by_day.keys()):
        r = by_day[day]
        r["billed"] = _money(r["billed"])
        r["tax"] = _money(r["tax"])
        r["discount"] = _money(r["discount"])
        rows.append(r)
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "totals": {"count": len(sales), "billed": _money(billed), "tax": _money(tax), "discount": _money(disc)},
        "rows": rows,
    }


def pharmacy_stock_ops(db: Session, hospital_id: int) -> dict:
    inv = (
        db.query(PharmacyInventory)
        .options(joinedload(PharmacyInventory.medicine))
        .join(Medicine, Medicine.id == PharmacyInventory.medicine_id)
        .filter(Medicine.hospital_id == hospital_id, PharmacyInventory.is_active == True)  # noqa: E712
        .all()
    )
    by_med = {}
    value_mrp = value_cost = 0.0
    for batch in inv:
        qty = float(batch.quantity_in_stock or 0)
        mid = batch.medicine_id
        row = by_med.setdefault(mid, {
            "medicine_id": mid,
            "name": "",
            "total_stock": 0.0,
            "batches": 0,
            "min_qty": None,
            "nearest_expiry": None,
        })
        med = batch.medicine if hasattr(batch, "medicine") else None
        if med:
            row["name"] = med.name or ""
            row["min_qty"] = med.min_qty
        row["total_stock"] += qty
        row["batches"] += 1
        exp = batch.expiry_date
        if exp and (row["nearest_expiry"] is None or exp < row["nearest_expiry"]):
            row["nearest_expiry"] = exp
        value_mrp += qty * float(batch.mrp or 0)
        value_cost += qty * float(getattr(batch, "cost_price", None) or batch.purchase_rate or 0)
    # Fill names for any missed
    missing = [mid for mid, r in by_med.items() if not r["name"]]
    if missing:
        for m in db.query(Medicine).filter(Medicine.id.in_(missing)).all():
            by_med[m.id]["name"] = m.name
            by_med[m.id]["min_qty"] = m.min_qty
    rows = []
    low = 0
    for r in by_med.values():
        r["total_stock"] = round(r["total_stock"], 2)
        if r["nearest_expiry"]:
            r["nearest_expiry"] = r["nearest_expiry"].isoformat() if hasattr(r["nearest_expiry"], "isoformat") else str(r["nearest_expiry"])
        if r["min_qty"] is not None and r["total_stock"] <= float(r["min_qty"] or 0):
            low += 1
            r["low_stock"] = True
        else:
            r["low_stock"] = False
        rows.append(r)
    rows.sort(key=lambda r: (not r["low_stock"], r["name"] or ""))
    return {
        "totals": {
            "skus": len(rows),
            "low_stock": low,
            "stock_value_mrp": _money(value_mrp),
            "stock_value_cost": _money(value_cost),
        },
        "rows": rows[:250],
    }


def readmissions(db: Session, hospital_id: int, within_days: int = 30) -> dict:
    q = (
        db.query(Admission)
        .options(joinedload(Admission.patient))
        .join(Patient, Patient.id == Admission.patient_id)
        .filter(
            Patient.hospital_id == hospital_id,
            Admission.is_readmission == True,  # noqa: E712
            Admission.days_since_last_discharge <= within_days,
        )
        .order_by(Admission.admission_date.desc())
    )
    rows = []
    for a in q.all():
        rows.append({
            "admission_number": a.admission_number,
            "patient_name": f"{a.patient.first_name} {a.patient.last_name}" if a.patient else "",
            "admission_date": a.admission_date.isoformat() if a.admission_date else "",
            "days_since_last_discharge": a.days_since_last_discharge,
            "reason": a.admission_reason or "",
            "status": a.status,
        })
    return {"within_days": within_days, "totals": {"count": len(rows)}, "rows": rows}


def mortality(db: Session, hospital_id: int, d_from: date, d_to: date) -> dict:
    q = (
        db.query(DischargeRecord)
        .join(Admission, Admission.id == DischargeRecord.admission_id)
        .join(Patient, Patient.id == Admission.patient_id)
        .filter(
            Patient.hospital_id == hospital_id,
            DischargeRecord.discharge_type == "death",
            DischargeRecord.discharge_date >= datetime.combine(d_from, datetime.min.time()),
            DischargeRecord.discharge_date < datetime.combine(d_to, datetime.min.time()) + timedelta(days=1),
        )
        .order_by(DischargeRecord.discharge_date.desc())
    )
    rows = []
    mlc = 0
    for d in q.all():
        adm = db.query(Admission).filter(Admission.id == d.admission_id).first()
        patient = db.query(Patient).filter(Patient.id == adm.patient_id).first() if adm else None
        if d.mlc_required:
            mlc += 1
        rows.append({
            "admission_number": adm.admission_number if adm else "",
            "patient_name": f"{patient.first_name} {patient.last_name}" if patient else "",
            "discharge_date": d.discharge_date.isoformat() if d.discharge_date else "",
            "cause_of_death": d.cause_of_death or "",
            "mlc_required": bool(d.mlc_required),
            "autopsy_done": bool(d.autopsy_done),
        })
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "totals": {"count": len(rows), "mlc": mlc},
        "rows": rows,
    }


def physio_summary(db: Session, hospital_id: int, d_from: date, d_to: date) -> dict:
    from app.models.physiotherapy import PhysioAppointment
    from app.services.physio_revenue import physio_revenue_split
    appts = db.query(PhysioAppointment).filter(
        PhysioAppointment.hospital_id == hospital_id,
        PhysioAppointment.appointment_date >= d_from,
        PhysioAppointment.appointment_date <= d_to,
    ).all()
    by_status = defaultdict(int)
    by_therapist = {}
    for a in appts:
        by_status[a.status or "scheduled"] += 1
        tid = a.therapist_id
        if tid not in by_therapist:
            t = db.query(User).filter(User.id == tid).first() if tid else None
            by_therapist[tid] = {
                "therapist_id": tid,
                "therapist_name": f"{t.first_name} {t.last_name}" if t else "(Unassigned)",
                "completed": 0, "no_show": 0, "cancelled": 0, "scheduled": 0,
            }
        key = a.status if a.status in ("completed", "no_show", "cancelled") else "scheduled"
        by_therapist[tid][key] = by_therapist[tid].get(key, 0) + 1
    try:
        revenue = physio_revenue_split(db, hospital_id, d_from, d_to)
    except Exception:
        revenue = {"collections": {"total": 0}, "revenue_by_type": {}, "outstanding_dues": 0}
    rows = list(by_therapist.values())
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "totals": {
            "sessions": len(appts),
            "completed": by_status.get("completed", 0),
            "no_show": by_status.get("no_show", 0),
            "cancelled": by_status.get("cancelled", 0),
            "collections": _money((revenue.get("collections") or {}).get("total")),
            "outstanding": _money(revenue.get("outstanding_dues")),
        },
        "by_status": [{"status": k, "count": v} for k, v in sorted(by_status.items())],
        "revenue_by_type": revenue.get("revenue_by_type") or {},
        "rows": rows,
    }
