"""Shared physiotherapy revenue helpers (package vs à-la-carte).

Used by physio reports/dashboard and central Billing Management summary.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, Iterable, Optional, Set

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.billing import Bill
from app.models.physiotherapy import PhysioPatientPackage


def empty_revenue_by_type() -> Dict[str, dict]:
    return {
        "package": {"billed": 0.0, "collected": 0.0, "bill_count": 0},
        "a_la_carte": {"billed": 0.0, "collected": 0.0, "bill_count": 0},
    }


def package_bill_id_set(db: Session, hospital_id: int) -> Set[int]:
    return {
        bid for (bid,) in db.query(PhysioPatientPackage.bill_id).filter(
            PhysioPatientPackage.hospital_id == hospital_id,
            PhysioPatientPackage.bill_id.isnot(None),
        ).all()
    }


def is_package_bill(bill: Bill, package_bill_ids: Optional[Set[int]] = None) -> bool:
    if package_bill_ids is not None and bill.id in package_bill_ids:
        return True
    for item in (bill.items or []):
        code = (item.item_code or "").upper()
        name = item.item_name or ""
        if code.startswith("PKG-") or name.startswith("Package:"):
            return True
    return False


def _round_revenue_buckets(revenue_by_type: Dict[str, dict]) -> Dict[str, dict]:
    for key in revenue_by_type:
        revenue_by_type[key]["billed"] = round(float(revenue_by_type[key]["billed"]), 2)
        revenue_by_type[key]["collected"] = round(float(revenue_by_type[key]["collected"]), 2)
        revenue_by_type[key]["bill_count"] = int(revenue_by_type[key]["bill_count"])
    return revenue_by_type


def classify_physio_bills(
    bills: Iterable[Bill],
    *,
    package_bill_ids: Optional[Set[int]] = None,
) -> dict:
    """Split physio bills into package vs à-la-carte and sum collections by method."""
    collections = {"cash": 0.0, "upi": 0.0, "card": 0.0, "other": 0.0, "total": 0.0}
    revenue_by_type = empty_revenue_by_type()
    outstanding = 0.0

    for b in bills:
        paid = sum(float(p.amount_paid or 0) for p in (b.payments or []))
        billed = float(b.total_amount or 0)
        outstanding += max(billed - paid, 0)
        bucket = "package" if is_package_bill(b, package_bill_ids) else "a_la_carte"
        revenue_by_type[bucket]["billed"] += billed
        revenue_by_type[bucket]["collected"] += paid
        revenue_by_type[bucket]["bill_count"] += 1
        for p in (b.payments or []):
            method = (p.payment_method_name or "other").lower()
            amt = float(p.amount_paid or 0)
            collections["total"] += amt
            if "upi" in method or "gpay" in method or "phonepe" in method:
                collections["upi"] += amt
            elif "card" in method:
                collections["card"] += amt
            elif "cash" in method:
                collections["cash"] += amt
            else:
                collections["other"] += amt

    return {
        "collections": {k: round(float(v), 2) for k, v in collections.items()},
        "revenue_by_type": _round_revenue_buckets(revenue_by_type),
        "outstanding_dues": round(outstanding, 2),
    }


def physio_revenue_split(
    db: Session,
    hospital_id: int,
    d_from: date,
    d_to: date,
) -> dict:
    """Query physio bills in range and return collections + revenue_by_type + outstanding."""
    bills = db.query(Bill).options(
        joinedload(Bill.items),
        joinedload(Bill.payments),
    ).filter(
        Bill.hospital_id == hospital_id,
        Bill.bill_type == "physiotherapy",
        Bill.status != "cancelled",
        func.date(Bill.bill_date) >= d_from,
        func.date(Bill.bill_date) <= d_to,
    ).all()
    pkg_ids = package_bill_id_set(db, hospital_id)
    return classify_physio_bills(bills, package_bill_ids=pkg_ids)


def classify_billing_hub_physio_rows(
    physio_rows: Iterable[dict],
    *,
    package_bill_ids: Set[int],
) -> Dict[str, dict]:
    """Classify billing-hub physio list rows (dicts with bill_id / amount / amount_paid).

    Hub rows may not carry item lines; rely primarily on package bill_id linkage,
    with a fallback on items text starting with "Package:".
    """
    revenue_by_type = empty_revenue_by_type()
    for row in physio_rows:
        if (row.get("payment_status") or "") == "cancelled":
            continue
        bill_id = row.get("bill_id")
        items_text = row.get("items") or ""
        is_pkg = (
            (bill_id is not None and bill_id in package_bill_ids)
            or str(items_text).startswith("Package:")
        )
        bucket = "package" if is_pkg else "a_la_carte"
        billed = float(row.get("amount") or 0)
        collected = float(row.get("amount_paid") or 0)
        revenue_by_type[bucket]["billed"] += billed
        revenue_by_type[bucket]["collected"] += collected
        revenue_by_type[bucket]["bill_count"] += 1
    return _round_revenue_buckets(revenue_by_type)
