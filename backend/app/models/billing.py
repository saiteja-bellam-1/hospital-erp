from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base

class PaymentMethod(Base):
    __tablename__ = "payment_methods"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    payments = relationship("Payment", back_populates="payment_method")

class Bill(Base):
    __tablename__ = "bills"

    id = Column(Integer, primary_key=True, index=True)
    bill_number = Column(String(50), unique=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    bill_type = Column(String(20), nullable=False)  # consultation, lab, pharmacy, admission, outpatient, credit_note
    bill_subtype = Column(String(20), default="final")  # final, interim, advance_receipt
    reference_id = Column(Integer)  # ID of the source record (consultation_id, lab_order_id, etc.)
    subtotal = Column(Float, nullable=False, default=0.0)
    tax_amount = Column(Float, default=0.0)
    discount_amount = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)
    status = Column(String(20), default="pending")  # pending, paid, partial, cancelled
    bill_date = Column(DateTime(timezone=True), server_default=func.now())
    due_date = Column(DateTime)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    notes = Column(Text)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)

    # Credit notes: parent_bill_id points to the bill the credit note offsets.
    parent_bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)
    # Free-text referral source (matches the `referred_by` convention on
    # Appointment + PatientLabOrder). Populated by procedure / day-care bills
    # and surfaced in the central billing dashboard + the printed PDF.
    referred_by = Column(String(100), nullable=True)

    patient = relationship("Patient", back_populates="bills")
    items = relationship("BillItem", back_populates="bill")
    payments = relationship("Payment", back_populates="bill")
    splits = relationship("BillSplit", back_populates="bill", cascade="all, delete-orphan")

class BillItem(Base):
    __tablename__ = "bill_items"
    
    id = Column(Integer, primary_key=True, index=True)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False)
    item_type = Column(String(50), nullable=False)  # consultation, lab_test, medicine, room_charge, etc.
    item_name = Column(String(200), nullable=False)
    item_code = Column(String(50))
    quantity = Column(Integer, default=1)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    discount_percentage = Column(Float, default=0.0)
    tax_percentage = Column(Float, default=0.0)
    
    bill = relationship("Bill", back_populates="items")

class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(Integer, primary_key=True, index=True)
    payment_number = Column(String(50), unique=True, nullable=False)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=False)
    amount_paid = Column(Float, nullable=False)
    payment_method_id = Column(Integer, ForeignKey("payment_methods.id"), nullable=True)
    payment_method_name = Column(String(50), default="cash")
    payment_date = Column(DateTime(timezone=True), server_default=func.now())
    transaction_reference = Column(String(100))
    notes = Column(Text)
    received_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Reversal / refund tracking. A refund row is a Payment with negative
    # amount_paid and parent_payment_id pointing to the original. The original
    # row gets reversed_* populated when fully reversed.
    parent_payment_id = Column(Integer, ForeignKey("payments.id"), nullable=True)
    reversed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reversed_at = Column(DateTime(timezone=True), nullable=True)
    reversal_reason = Column(Text, nullable=True)

    bill = relationship("Bill", back_populates="payments")
    payment_method = relationship("PaymentMethod", back_populates="payments")