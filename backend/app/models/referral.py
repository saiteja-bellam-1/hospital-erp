from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Text
from sqlalchemy.orm import relationship
from config.database import Base
from app.utils.time import system_now


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(15), nullable=True)
    village = Column(String(100), nullable=True)
    mandal = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=system_now)

    commissions = relationship("ReferralCommission", back_populates="referral", order_by="ReferralCommission.payment_date.desc()")


class ReferralCommission(Base):
    __tablename__ = "referral_commissions"

    id = Column(Integer, primary_key=True, index=True)
    referral_id = Column(Integer, ForeignKey("referrals.id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_method = Column(String(50), default="cash")
    payment_date = Column(DateTime(timezone=True), default=system_now)
    notes = Column(Text, nullable=True)
    paid_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=system_now)

    referral = relationship("Referral", back_populates="commissions")
