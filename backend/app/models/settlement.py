"""Business-unit revenue settlements.

The Settlements page splits finalized inpatient bill lines across the fixed
business units (lab / pharmacy / canteen / hospital). These tables let an
admin *record* a payout to a business unit for a period, applying a
configurable payout percentage (the hospital keeps the remainder as its
commission). Tables are created via ``create_all`` on startup.
"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Date, ForeignKey, Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from config.database import Base

# Fixed business units the hospital settles revenue to. "hospital" is the
# residual bucket kept in-house and is intentionally not settleable.
SETTLEMENT_UNITS = ("lab", "pharmacy", "canteen")
DEFAULT_PAYOUT_PERCENTAGE = 100.0


class SettlementConfig(Base):
    """Per-hospital payout percentage for a business unit.

    ``payout_percentage`` is the share of that unit's gross revenue paid out to
    the unit; the hospital keeps the remainder. Defaults to 100% (full
    pass-through) when no row exists.
    """
    __tablename__ = "settlement_configs"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    unit = Column(String(20), nullable=False)  # lab | pharmacy | canteen
    payout_percentage = Column(Float, nullable=False, default=DEFAULT_PAYOUT_PERCENTAGE)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("hospital_id", "unit", name="uq_settlement_config_hospital_unit"),
    )


class Settlement(Base):
    """A recorded payout to a business unit for a date range.

    Amounts snapshot the computed gross for the period and the payout
    percentage in force at recording time so historical statements stay stable
    even if bills or config change later.
    """
    __tablename__ = "settlements"

    id = Column(Integer, primary_key=True, index=True)
    settlement_number = Column(String(40), unique=True, nullable=False, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    unit = Column(String(20), nullable=False, index=True)  # lab | pharmacy | canteen

    period_from = Column(Date, nullable=False)
    period_to = Column(Date, nullable=False)

    gross_amount = Column(Float, nullable=False, default=0.0)
    payout_percentage = Column(Float, nullable=False, default=DEFAULT_PAYOUT_PERCENTAGE)
    payout_amount = Column(Float, nullable=False, default=0.0)
    hospital_share = Column(Float, nullable=False, default=0.0)
    bill_count = Column(Integer, nullable=False, default=0)

    status = Column(String(20), nullable=False, default="paid")  # paid | cancelled

    payment_method = Column(String(30), nullable=True)  # cash | bank_transfer | upi | cheque
    payment_reference = Column(String(100), nullable=True)
    payment_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancelled_reason = Column(String(255), nullable=True)
