"""Canteen module — à-la-carte catalog and IP-linked food orders.

Availability is gated by the inpatient module (no separate license feature).
Legacy MealPlan / FoodOrder tables remain for historical bills.
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Text,
    Numeric, Date, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base


class CanteenCategory(Base):
    """Optional grouping for catalog items (Breakfast, Lunch, Beverages, …)."""
    __tablename__ = "canteen_categories"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    items = relationship("CanteenItem", back_populates="category")

    __table_args__ = (
        UniqueConstraint("hospital_id", "name", name="uq_canteen_category_hospital_name"),
    )


class CanteenItem(Base):
    """À-la-carte menu item with current selling price."""
    __tablename__ = "canteen_items"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("canteen_categories.id"), nullable=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Numeric(10, 2), nullable=False, default=0)
    is_veg = Column(Boolean, default=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    category = relationship("CanteenCategory", back_populates="items")

    __table_args__ = (
        UniqueConstraint("hospital_id", "name", name="uq_canteen_item_hospital_name"),
    )


class CanteenOrder(Base):
    """Food order for an admitted patient. Line items carry price snapshots."""
    __tablename__ = "canteen_orders"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=False, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False, index=True)
    # pending → preparing → ready → delivered | cancelled
    status = Column(String(20), default="pending", nullable=False, index=True)
    notes = Column(Text, nullable=True)
    serve_date = Column(Date, nullable=True, index=True)
    ordered_at = Column(DateTime(timezone=True), server_default=func.now())
    ordered_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status_updated_at = Column(DateTime(timezone=True), nullable=True)
    status_updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancelled_reason = Column(String(200), nullable=True)
    billed = Column(Boolean, default=False, nullable=False)
    bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)

    admission = relationship("Admission", foreign_keys=[admission_id])
    items = relationship(
        "CanteenOrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )


class CanteenOrderItem(Base):
    """One catalog line on a canteen order. Prices are snapshotted at order time."""
    __tablename__ = "canteen_order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("canteen_orders.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("canteen_items.id"), nullable=True)
    item_name = Column(String(200), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    line_total = Column(Numeric(10, 2), nullable=False)

    order = relationship("CanteenOrder", back_populates="items")
    catalog_item = relationship("CanteenItem", foreign_keys=[item_id])


class CanteenSale(Base):
    """Walk-in / cash POS sale (standalone — not linked to IP admission billing)."""
    __tablename__ = "canteen_sales"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False, index=True)
    sale_number = Column(String(40), unique=True, nullable=False, index=True)
    sale_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(String(20), default="completed", nullable=False)  # completed | voided
    payment_type = Column(String(20), default="cash", nullable=False)  # cash | upi | card
    customer_name = Column(String(150), nullable=True)
    customer_phone = Column(String(30), nullable=True)
    subtotal = Column(Numeric(10, 2), nullable=False, default=0)
    discount_amount = Column(Numeric(10, 2), nullable=False, default=0)
    grand_total = Column(Numeric(10, 2), nullable=False, default=0)
    notes = Column(Text, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    voided_at = Column(DateTime(timezone=True), nullable=True)
    voided_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    void_reason = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    items = relationship(
        "CanteenSaleItem",
        back_populates="sale",
        cascade="all, delete-orphan",
    )


class CanteenSaleItem(Base):
    """Line on a canteen POS sale with price snapshot."""
    __tablename__ = "canteen_sale_items"

    id = Column(Integer, primary_key=True, index=True)
    sale_id = Column(Integer, ForeignKey("canteen_sales.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("canteen_items.id"), nullable=True)
    item_name = Column(String(200), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    line_total = Column(Numeric(10, 2), nullable=False)

    sale = relationship("CanteenSale", back_populates="items")
    catalog_item = relationship("CanteenItem", foreign_keys=[item_id])
