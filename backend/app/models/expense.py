"""Cash paid out by the front desk, deducted from the daily collection."""
from sqlalchemy import Column, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from config.database import Base
from app.utils.time import system_now


class FrontDeskExpenseCategory(Base):
    """Names the hospital has saved for front-desk expenses."""
    __tablename__ = "front_desk_expense_categories"
    __table_args__ = (
        UniqueConstraint("hospital_id", "name_key", name="uq_front_desk_expense_category"),
    )

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    name = Column(String(80), nullable=False)
    name_key = Column(String(80), nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=system_now, nullable=False)


class FrontDeskExpense(Base):
    __tablename__ = "front_desk_expenses"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    expense_date = Column(Date, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    category_id = Column(Integer, ForeignKey("front_desk_expense_categories.id"), nullable=True)
    category = Column(String(80), nullable=False)
    description = Column(String(300), nullable=False)
    payment_method = Column(String(30), nullable=False, default="cash")
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=system_now, nullable=False)
    voided_at = Column(DateTime, nullable=True)
    voided_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    void_reason = Column(String(300), nullable=True)
