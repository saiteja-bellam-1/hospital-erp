"""Front-desk expenses and how they reduce the daily collection."""
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

EXPENSE_ROLES = (
    "super_admin",
    "hospital_admin",
    "billing_admin",
    "receptionist",
    "frontdesk",
)

PAYMENT_METHODS = (
    ("cash", "Cash"),
    ("upi", "UPI"),
    ("card", "Card"),
    ("cheque", "Cheque"),
    ("online", "Online"),
    ("bank_transfer", "Bank transfer"),
)

_METHOD_LABELS = dict(PAYMENT_METHODS)


def user_can_manage_expenses(user) -> bool:
    names = getattr(user, "role_names", None) or []
    return any(role in names for role in EXPENSE_ROLES)


def category_label(stored: str) -> str:
    """Show the saved name. Older lowercase keys are title-cased."""
    text = (stored or "").strip()
    if text and text == text.lower():
        return text.replace("_", " ").title()
    return text


def split_category_name(raw: str) -> tuple:
    """Return (display name, case-folded key) or raise ValueError."""
    name = " ".join((raw or "").split())
    if len(name) < 2:
        raise ValueError("Enter a category name")
    if len(name) > 80:
        raise ValueError("Category name is too long")
    return name, name.casefold()


def list_categories(db: Session, hospital_id: int) -> list:
    from app.models.expense import FrontDeskExpenseCategory
    rows = (
        db.query(FrontDeskExpenseCategory)
        .filter(FrontDeskExpenseCategory.hospital_id == hospital_id)
        .order_by(FrontDeskExpenseCategory.name.asc())
        .all()
    )
    return [{"id": row.id, "name": row.name} for row in rows]


def get_or_create_category(db: Session, hospital_id: int, user_id: int, raw_name: str):
    """Save a new category, or return the hospital's existing one with the same name."""
    from sqlalchemy.exc import IntegrityError
    from app.models.expense import FrontDeskExpenseCategory
    from app.utils.time import system_now

    name, name_key = split_category_name(raw_name)
    existing = (
        db.query(FrontDeskExpenseCategory)
        .filter(
            FrontDeskExpenseCategory.hospital_id == hospital_id,
            FrontDeskExpenseCategory.name_key == name_key,
        )
        .first()
    )
    if existing:
        return existing, False
    row = FrontDeskExpenseCategory(
        hospital_id=hospital_id,
        name=name,
        name_key=name_key,
        created_by_id=user_id,
        created_at=system_now(),
    )
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except IntegrityError:
        db.rollback()
        row = (
            db.query(FrontDeskExpenseCategory)
            .filter(
                FrontDeskExpenseCategory.hospital_id == hospital_id,
                FrontDeskExpenseCategory.name_key == name_key,
            )
            .first()
        )
        if row is None:
            raise
        return row, False
    return row, True


def method_label(key: str) -> str:
    return _METHOD_LABELS.get(key, (key or "").replace("_", " ").title())


def expenses_apply(module: Optional[str], patient_id: Optional[int]) -> bool:
    """Hospital expenses belong on the unfiltered daily total only."""
    if patient_id:
        return False
    key = (module or "all").strip().lower()
    return key in ("", "all")


def sum_expenses(db: Session, hospital_id: int, d_from: date, d_to: date) -> float:
    return round(sum(expenses_by_day(db, hospital_id, d_from, d_to).values()), 2)


def expenses_by_day(db: Session, hospital_id: int, d_from: date, d_to: date) -> dict:
    from app.models.expense import FrontDeskExpense

    rows = (
        db.query(FrontDeskExpense)
        .filter(
            FrontDeskExpense.hospital_id == hospital_id,
            FrontDeskExpense.expense_date >= d_from,
            FrontDeskExpense.expense_date <= d_to,
            FrontDeskExpense.voided_at.is_(None),
        )
        .all()
    )
    by_day: dict = {}
    for row in rows:
        day = row.expense_date.isoformat()
        by_day[day] = by_day.get(day, 0.0) + float(row.amount or 0)
    return {day: round(amount, 2) for day, amount in by_day.items()}


def attach_front_desk_expenses(
    db: Session,
    hospital_id: int,
    payload: dict,
    *,
    module: Optional[str] = None,
    patient_id: Optional[int] = None,
) -> dict:
    """Add an expenses column and a net that is collections minus those expenses.

    Filtered tills and patient views stay as money received. A day that only
    has an expense still appears, so the deduction is not dropped.
    """
    apply = expenses_apply(module, patient_id)
    totals = dict(payload.get("totals") or {})
    rows = [dict(row) for row in (payload.get("rows") or [])]
    by_day = {}
    if apply:
        d_from = date.fromisoformat(payload["date_from"])
        d_to = date.fromisoformat(payload["date_to"])
        by_day = expenses_by_day(db, hospital_id, d_from, d_to)

    seen = {row["date"] for row in rows}
    for day, amount in by_day.items():
        if day not in seen and amount:
            rows.append({
                "date": day,
                "total": 0.0,
                "refunds": 0.0,
                "by_method": {},
            })
    rows.sort(key=lambda row: row["date"])

    expense_sum = 0.0
    for row in rows:
        spent = round(float(by_day.get(row["date"], 0.0) if apply else 0.0), 2)
        expense_sum += spent
        row["expenses"] = spent
        row["net"] = round(float(row.get("total") or 0) - spent, 2)

    collected = round(float(totals.get("net_collected") or 0), 2)
    expense_sum = round(expense_sum, 2)
    totals["expenses"] = expense_sum
    totals["net_after_expenses"] = round(collected - expense_sum, 2)
    payload = dict(payload)
    payload["rows"] = rows
    payload["totals"] = totals
    payload["expenses_applied"] = apply
    return payload
