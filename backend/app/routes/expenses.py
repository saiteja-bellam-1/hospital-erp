"""Front-desk expense entry. Amounts are deducted on the daily collection."""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.expense import FrontDeskExpense, FrontDeskExpenseCategory
from app.models.user import User
from app.services.audit_service import log_action
from app.services.front_desk_expenses import (
    PAYMENT_METHODS,
    category_label,
    get_or_create_category,
    list_categories,
    method_label,
    user_can_manage_expenses,
)
from app.utils.dependencies import get_current_user
from app.utils.time import system_now
from config.database import get_db

router = APIRouter()


class ExpenseCreate(BaseModel):
    expense_date: date
    amount: float
    category: str = ""
    category_id: Optional[int] = None
    description: str = ""
    payment_method: str = "cash"


class CategoryCreate(BaseModel):
    name: str = ""


class ExpenseVoid(BaseModel):
    reason: str = Field(..., min_length=3, max_length=300)


def _require_expense_role(current_user: User) -> None:
    if not user_can_manage_expenses(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to manage front-desk expenses")


def _user_name(user: Optional[User]) -> str:
    if not user:
        return ""
    return f"{user.first_name or ''} {user.last_name or ''}".strip()


def _serialize(row: FrontDeskExpense, names: dict) -> dict:
    return {
        "id": row.id,
        "expense_date": row.expense_date.isoformat(),
        "amount": round(float(row.amount or 0), 2),
        "category_id": row.category_id,
        "category": row.category,
        "category_label": category_label(row.category),
        "description": row.description,
        "payment_method": row.payment_method,
        "payment_method_label": method_label(row.payment_method),
        "created_by_name": names.get(row.created_by_id, ""),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "voided_at": row.voided_at.isoformat() if row.voided_at else None,
        "void_reason": row.void_reason or "",
    }


def _options(db: Session, hospital_id: int) -> dict:
    return {
        "categories": list_categories(db, hospital_id),
        "payment_methods": [{"id": key, "label": label} for key, label in PAYMENT_METHODS],
    }


def _resolve_category(db: Session, current_user: User, category_id: Optional[int], category_name: str):
    if category_id:
        row = db.query(FrontDeskExpenseCategory).filter(
            FrontDeskExpenseCategory.id == category_id,
            FrontDeskExpenseCategory.hospital_id == current_user.hospital_id,
        ).first()
        if not row:
            raise HTTPException(status_code=400, detail="Choose a category from the list")
        return row
    if not (category_name or "").strip():
        raise HTTPException(status_code=400, detail="Choose a category or type a new one")
    try:
        row, _created = get_or_create_category(
            db, current_user.hospital_id, current_user.id, category_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return row


def _parse_range(date_from: Optional[str], date_to: Optional[str]):
    today = date.today()
    try:
        d_to = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else today
        d_from = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else d_to
    except ValueError:
        raise HTTPException(status_code=400, detail="Use dates as YYYY-MM-DD")
    if d_from > d_to:
        raise HTTPException(status_code=400, detail="The from date is after the to date")
    return d_from, d_to


@router.get("/front-desk-expenses")
def list_front_desk_expenses(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_expense_role(current_user)
    d_from, d_to = _parse_range(date_from, date_to)
    rows = (
        db.query(FrontDeskExpense)
        .filter(
            FrontDeskExpense.hospital_id == current_user.hospital_id,
            FrontDeskExpense.expense_date >= d_from,
            FrontDeskExpense.expense_date <= d_to,
            FrontDeskExpense.voided_at.is_(None),
        )
        .order_by(FrontDeskExpense.expense_date.desc(), FrontDeskExpense.id.desc())
        .all()
    )
    user_ids = {row.created_by_id for row in rows}
    names = {}
    if user_ids:
        for user in db.query(User).filter(User.id.in_(user_ids)).all():
            names[user.id] = _user_name(user)
    expenses = [_serialize(row, names) for row in rows]
    return {
        "date_from": d_from.isoformat(),
        "date_to": d_to.isoformat(),
        "expenses": expenses,
        "total": round(sum(item["amount"] for item in expenses), 2),
        **_options(db, current_user.hospital_id),
    }


@router.post("/front-desk-expense-categories")
def create_front_desk_expense_category(
    body: CategoryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save a category name so it can be picked on later expenses."""
    _require_expense_role(current_user)
    try:
        row, created = get_or_create_category(
            db, current_user.hospital_id, current_user.id, body.name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if created:
        log_action(
            db, current_user, "create_expense_category", "billing",
            "FrontDeskExpenseCategory", row.id,
            f"Expense category \"{row.name}\"",
            details={"name": row.name},
        )
    return {"id": row.id, "name": row.name, "created": created}


@router.post("/front-desk-expenses")
def create_front_desk_expense(
    body: ExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_expense_role(current_user)
    method = (body.payment_method or "cash").strip().lower().replace(" ", "_").replace("-", "_")
    description = (body.description or "").strip()
    amount = round(float(body.amount or 0), 2)
    if method not in dict(PAYMENT_METHODS):
        raise HTTPException(status_code=400, detail="Choose how this expense was paid")
    if not description:
        raise HTTPException(status_code=400, detail="Enter what this expense was for")
    if len(description) > 300:
        raise HTTPException(status_code=400, detail="Description is too long")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")
    if amount > 10_000_000:
        raise HTTPException(status_code=400, detail="Amount is too large")
    if body.expense_date > date.today():
        raise HTTPException(status_code=400, detail="Expense date cannot be in the future")
    category = _resolve_category(db, current_user, body.category_id, body.category)

    row = FrontDeskExpense(
        hospital_id=current_user.hospital_id,
        expense_date=body.expense_date,
        amount=amount,
        category_id=category.id,
        category=category.name,
        description=description,
        payment_method=method,
        created_by_id=current_user.id,
        created_at=system_now(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(
        db, current_user, "create_front_desk_expense", "billing", "FrontDeskExpense", row.id,
        f"Front-desk expense ₹{amount:.2f} on {row.expense_date.isoformat()}: {description}",
        details={
            "amount": amount,
            "category": category.name,
            "category_id": category.id,
            "payment_method": method,
            "expense_date": row.expense_date.isoformat(),
        },
    )
    return _serialize(row, {current_user.id: _user_name(current_user)})


@router.post("/front-desk-expenses/{expense_id}/void")
def void_front_desk_expense(
    expense_id: int,
    body: ExpenseVoid,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_expense_role(current_user)
    row = db.query(FrontDeskExpense).filter(
        FrontDeskExpense.id == expense_id,
        FrontDeskExpense.hospital_id == current_user.hospital_id,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Expense not found")
    if row.voided_at is not None:
        raise HTTPException(status_code=400, detail="This expense is already removed")
    reason = body.reason.strip()
    if len(reason) < 3:
        raise HTTPException(status_code=400, detail="Enter a reason for removing this expense")
    row.voided_at = system_now()
    row.voided_by_id = current_user.id
    row.void_reason = reason
    db.commit()
    log_action(
        db, current_user, "void_front_desk_expense", "billing", "FrontDeskExpense", row.id,
        f"Removed front-desk expense ₹{float(row.amount or 0):.2f}: {reason}",
        details={"amount": round(float(row.amount or 0), 2), "reason": reason},
    )
    return {"id": row.id, "voided": True}
