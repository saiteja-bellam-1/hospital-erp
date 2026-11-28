"""Partial-payment support for invoices that live outside the ``bills`` table.

OP appointments, reception lab orders, pharmacy counter sales and canteen
sales each keep their own header row. Money collected against them is
recorded in ``service_payments`` (one row per collection) and the header
caches the running total in ``amount_paid``.

Legacy rows (``amount_paid IS NULL``) predate the ledger. Their collection is
derived from the old status fields, so historical reports do not change:

* appointment / lab order: ``payment_status == "paid"`` -> full amount
* pharmacy sale: completed and ``payment_type != "credit"`` -> full amount
* canteen sale: completed -> full amount

Reports should call :func:`collection_entries` instead of reading status
flags, so a partial payment is counted on the day and with the method it was
actually received.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable, List, Optional, Tuple

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.models.billing import ServicePayment


class ServicePaymentIn(BaseModel):
    """Body for every "collect payment" endpoint on non-Bill invoices."""
    amount: float = Field(..., gt=0)
    payment_method: str = Field(default="cash", max_length=50)
    reference: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=500)

APPOINTMENT = "appointment"
LAB_ORDER = "lab_order"
PHARMACY_SALE = "pharmacy_sale"
CANTEEN_SALE = "canteen_sale"

SOURCE_TYPES = (APPOINTMENT, LAB_ORDER, PHARMACY_SALE, CANTEEN_SALE)

EPS = 0.01

# Statuses on appointments / lab orders that mean "no money is owed".
_CLOSED_STATUSES = {"cancelled", "refunded", "waived", "partner_settled", "consolidated", "deleted"}


def _r(x) -> float:
    return round(float(x or 0), 2)


# ---------------------------------------------------------------------------
# Totals and status
# ---------------------------------------------------------------------------

def total_for(source_type: str, obj) -> float:
    if source_type == APPOINTMENT:
        return _r(obj.final_amount)
    if source_type == LAB_ORDER:
        return _r((obj.amount or 0) - (getattr(obj, "discount_amount", None) or 0))
    if source_type in (PHARMACY_SALE, CANTEEN_SALE):
        return _r(obj.grand_total)
    raise ValueError(f"unknown source_type {source_type!r}")


def derive_status(total: float, paid: float) -> str:
    """``paid`` | ``partial`` | ``pending`` from a total and amount collected."""
    total = _r(total)
    paid = _r(paid)
    if total <= EPS or paid >= total - EPS:
        return "paid"
    if paid > EPS:
        return "partial"
    return "pending"


def _legacy_paid(source_type: str, obj) -> float:
    total = total_for(source_type, obj)
    if source_type in (APPOINTMENT, LAB_ORDER):
        return total if (obj.payment_status or "") == "paid" else 0.0
    if source_type == PHARMACY_SALE:
        if (obj.status or "completed") != "completed":
            return 0.0
        if (obj.billing_mode or "cash_at_pharmacy") != "cash_at_pharmacy":
            return 0.0
        return 0.0 if (obj.payment_type or "cash") == "credit" else total
    if source_type == CANTEEN_SALE:
        return total if (obj.status or "completed") == "completed" else 0.0
    return 0.0


def effective_paid(source_type: str, obj) -> float:
    """Amount collected so far, honouring legacy rows.

    If some older code path flipped an appointment or lab order to ``paid``
    without writing ledger rows, it is treated as fully paid.
    """
    if obj.amount_paid is None:
        return _legacy_paid(source_type, obj)
    if source_type in (APPOINTMENT, LAB_ORDER) and (obj.payment_status or "") == "paid":
        return max(_r(obj.amount_paid), total_for(source_type, obj))
    return _r(obj.amount_paid)


def balance_due(source_type: str, obj) -> float:
    if source_type in (APPOINTMENT, LAB_ORDER) and (obj.payment_status or "") in _CLOSED_STATUSES:
        return 0.0
    if source_type in (PHARMACY_SALE, CANTEEN_SALE) and (obj.status or "completed") != "completed":
        return 0.0
    return max(0.0, _r(total_for(source_type, obj) - effective_paid(source_type, obj)))


def payment_state(source_type: str, obj) -> str:
    """Display status: paid / partial / pending / cancelled (or the closed status)."""
    if source_type in (APPOINTMENT, LAB_ORDER):
        st = obj.payment_status or "pending"
        if st in _CLOSED_STATUSES:
            return st
        return derive_status(total_for(source_type, obj), effective_paid(source_type, obj))
    if (obj.status or "completed") != "completed":
        return "cancelled"
    if source_type == PHARMACY_SALE and (obj.billing_mode or "cash_at_pharmacy") != "cash_at_pharmacy":
        return "pending"
    return derive_status(total_for(source_type, obj), effective_paid(source_type, obj))


def summary(source_type: str, obj) -> dict:
    total = total_for(source_type, obj)
    paid = effective_paid(source_type, obj)
    return {
        "total_amount": total,
        "amount_paid": _r(min(paid, total) if total > 0 else paid),
        "balance_due": balance_due(source_type, obj),
        "payment_state": payment_state(source_type, obj),
    }


# ---------------------------------------------------------------------------
# Writing payments
# ---------------------------------------------------------------------------

def _apply_status(source_type: str, obj, method: Optional[str], when: Optional[datetime]) -> None:
    total = total_for(source_type, obj)
    paid = _r(obj.amount_paid)
    status = derive_status(total, paid)
    if source_type in (APPOINTMENT, LAB_ORDER):
        if (obj.payment_status or "") not in _CLOSED_STATUSES:
            obj.payment_status = status
        if paid > EPS:
            if method:
                obj.payment_method = method
            if when is not None:
                obj.payment_date = when
    elif source_type == PHARMACY_SALE:
        # payment_type keeps its old meaning for older readers: "credit"
        # means money is still owed, "cash" means settled.
        obj.payment_type = "cash" if status == "paid" else "credit"
    elif source_type == CANTEEN_SALE:
        if method:
            obj.payment_type = method


def _hospital_id_for(obj, fallback: Optional[int]) -> Optional[int]:
    return getattr(obj, "hospital_id", None) or fallback


def resolve_initial_amount(total: float, amount_paid: Optional[float], payment_status: Optional[str] = None) -> float:
    """Amount collected at booking time.

    ``amount_paid`` wins when given. Otherwise ``payment_status`` decides:
    ``paid`` (or omitted) -> full amount, ``pending`` -> 0. ``partial`` with no
    amount is rejected.
    """
    total = _r(total)
    if amount_paid is not None:
        amt = _r(amount_paid)
        if amt < -EPS:
            raise HTTPException(status_code=400, detail="Amount paid cannot be negative")
        if amt > total + EPS:
            raise HTTPException(
                status_code=400,
                detail=f"Amount paid ({amt:.2f}) exceeds the bill total ({total:.2f})",
            )
        return max(0.0, amt)
    st = (payment_status or "paid").lower()
    if st == "partial":
        raise HTTPException(status_code=400, detail="Enter the amount received for a partial payment")
    if st in ("pending", "unpaid", "credit", "pay_later"):
        return 0.0
    return total


def set_initial_payment(
    db,
    source_type: str,
    obj,
    amount: float,
    *,
    method: Optional[str] = "cash",
    received_by_id: Optional[int] = None,
    hospital_id: Optional[int] = None,
    when: Optional[datetime] = None,
    reference: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[ServicePayment]:
    """Record what was collected when the invoice was created.

    ``obj`` must already be flushed (needs an id). Writes a ledger row only
    when ``amount > 0``; always sets ``amount_paid`` so the row is on the
    ledger regime from now on.
    """
    if obj.id is None:
        db.flush()
    amount = _r(amount)
    when = when or datetime.now()
    obj.amount_paid = amount
    row = None
    if amount > EPS:
        row = ServicePayment(
            hospital_id=_hospital_id_for(obj, hospital_id),
            source_type=source_type,
            source_id=obj.id,
            amount=amount,
            payment_method=(method or "cash"),
            payment_date=when,
            reference=reference,
            notes=notes,
            received_by_id=received_by_id,
        )
        db.add(row)
    _apply_status(source_type, obj, method, when if amount > EPS else None)
    return row


def record_payment(
    db,
    source_type: str,
    obj,
    amount: float,
    *,
    method: Optional[str] = "cash",
    received_by_id: Optional[int] = None,
    hospital_id: Optional[int] = None,
    when: Optional[datetime] = None,
    reference: Optional[str] = None,
    notes: Optional[str] = None,
) -> ServicePayment:
    """Collect money against an existing invoice. Partial amounts allowed."""
    amount = _r(amount)
    if amount <= EPS:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")
    if source_type in (APPOINTMENT, LAB_ORDER) and (obj.payment_status or "") in _CLOSED_STATUSES:
        raise HTTPException(status_code=400, detail=f"Bill is {obj.payment_status}; payment cannot be recorded")
    if source_type in (PHARMACY_SALE, CANTEEN_SALE) and (obj.status or "completed") != "completed":
        raise HTTPException(status_code=400, detail="Sale is voided; payment cannot be recorded")
    due = balance_due(source_type, obj)
    if due <= EPS:
        raise HTTPException(status_code=400, detail="Bill is already fully paid")
    if amount > due + EPS:
        raise HTTPException(
            status_code=400,
            detail=f"Payment ({amount:.2f}) exceeds the balance due ({due:.2f})",
        )
    # Bring a legacy row onto the ledger before adding to it.
    if obj.amount_paid is None:
        obj.amount_paid = effective_paid(source_type, obj)
    when = when or datetime.now()
    row = ServicePayment(
        hospital_id=_hospital_id_for(obj, hospital_id),
        source_type=source_type,
        source_id=obj.id,
        amount=amount,
        payment_method=(method or "cash"),
        payment_date=when,
        reference=reference,
        notes=notes,
        received_by_id=received_by_id,
    )
    db.add(row)
    obj.amount_paid = _r(obj.amount_paid + amount)
    _apply_status(source_type, obj, method, when)
    return row


def allocate(amount: float, objs: List, source_type: str) -> List[Tuple[object, float]]:
    """Split ``amount`` across ``objs`` (in order) up to each one's balance."""
    remaining = _r(amount)
    out = []
    for o in objs:
        if remaining <= EPS:
            break
        due = balance_due(source_type, o)
        if due <= EPS:
            continue
        take = _r(min(due, remaining))
        out.append((o, take))
        remaining = _r(remaining - take)
    return out


def record_group_payment(db, source_type: str, objs: List, amount: float, **kw) -> List[ServicePayment]:
    """Collect one amount against several invoices (e.g. a lab bill group)."""
    total_due = _r(sum(balance_due(source_type, o) for o in objs))
    amount = _r(amount)
    if amount <= EPS:
        raise HTTPException(status_code=400, detail="Payment amount must be greater than zero")
    if total_due <= EPS:
        raise HTTPException(status_code=400, detail="Bill is already fully paid")
    if amount > total_due + EPS:
        raise HTTPException(
            status_code=400,
            detail=f"Payment ({amount:.2f}) exceeds the balance due ({total_due:.2f})",
        )
    return [record_payment(db, source_type, o, take, **kw) for o, take in allocate(amount, objs, source_type)]


def set_group_initial_payment(db, source_type: str, objs: List, amount: float, **kw) -> None:
    """Initial collection across several freshly created invoices."""
    alloc = dict((id(o), take) for o, take in allocate(amount, objs, source_type))
    for o in objs:
        set_initial_payment(db, source_type, o, alloc.get(id(o), 0.0), **kw)


def audit_collection(db, user, source_type: str, source_id: int, label: str, amount: float, method: str) -> None:
    """Audit-log a collection. Never raises."""
    try:
        from app.services.audit_service import log_action
        log_action(
            db, user=user, action="collect_payment", category="billing",
            resource_type=source_type, resource_id=source_id,
            description=f"Collected {float(amount):.2f} ({method}) on {label}",
        )
    except Exception:
        pass


def spread_discount(objs: List, discount: float, attr_total="amount") -> None:
    """Allocate a bill-level discount across lab orders, proportional to price.

    Stored on each order's ``discount_amount`` so the net due survives
    reprints and partial collections. Rounding residue goes to the last one.
    """
    discount = _r(discount)
    gross = _r(sum(float(getattr(o, attr_total) or 0) for o in objs))
    if discount <= EPS or gross <= EPS:
        return
    if discount > gross + EPS:
        raise HTTPException(status_code=400, detail="Discount cannot exceed the bill amount")
    left = discount
    for i, o in enumerate(objs):
        price = float(getattr(o, attr_total) or 0)
        share = left if i == len(objs) - 1 else _r(discount * price / gross)
        share = min(share, price)
        o.discount_amount = _r((o.discount_amount or 0) + share)
        left = _r(left - share)


def payments_for(db, source_type: str, source_ids: Iterable[int]) -> List[ServicePayment]:
    ids = [i for i in source_ids if i is not None]
    if not ids:
        return []
    return (
        db.query(ServicePayment)
        .filter(ServicePayment.source_type == source_type, ServicePayment.source_id.in_(ids))
        .order_by(ServicePayment.payment_date.asc(), ServicePayment.id.asc())
        .all()
    )


def payment_rows_json(rows: List[ServicePayment]) -> List[dict]:
    return [
        {
            "id": r.id,
            "source_type": r.source_type,
            "source_id": r.source_id,
            "amount": _r(r.amount),
            "payment_method": r.payment_method,
            "payment_date": r.payment_date.isoformat() if r.payment_date else None,
            "reference": r.reference,
            "notes": r.notes,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _default_when(source_type: str, obj):
    if source_type in (APPOINTMENT, LAB_ORDER):
        fallback = obj.created_at if source_type == APPOINTMENT else obj.order_date
        return obj.payment_date or fallback
    return obj.sale_date


def _default_method(source_type: str, obj) -> str:
    if source_type in (APPOINTMENT, LAB_ORDER):
        return obj.payment_method or "cash"
    if source_type == CANTEEN_SALE:
        return obj.payment_type or "cash"
    return "cash"


def collection_entries(db, source_type: str, objs: Iterable) -> List[Tuple[object, datetime, str, float]]:
    """Every money receipt for ``objs`` as ``(obj, when, method, amount)``.

    Ledger rows contribute individually. Legacy rows contribute one synthetic
    receipt for their legacy-paid amount. A ledger row that some other code
    path marked fully ``paid`` without a matching ledger entry contributes the
    shortfall as one synthetic receipt, so nothing goes missing.
    Callers filter out cancelled / voided rows themselves.
    """
    objs = list(objs)
    ledger_ids = [o.id for o in objs if o.amount_paid is not None]
    by_src = defaultdict(list)
    for row in payments_for(db, source_type, ledger_ids):
        by_src[row.source_id].append(row)
    out = []
    for o in objs:
        if o.amount_paid is None:
            amt = _legacy_paid(source_type, o)
            if amt > EPS:
                out.append((o, _default_when(source_type, o), _default_method(source_type, o), amt))
            continue
        rows = by_src.get(o.id, [])
        got = 0.0
        for r in rows:
            out.append((o, r.payment_date, r.payment_method or "cash", _r(r.amount)))
            got += _r(r.amount)
        shortfall = _r(effective_paid(source_type, o) - got)
        if shortfall > EPS:
            out.append((o, _default_when(source_type, o), _default_method(source_type, o), shortfall))
    return out


def collected_total(db, source_type: str, objs: Iterable) -> float:
    return _r(sum(e[3] for e in collection_entries(db, source_type, objs)))
