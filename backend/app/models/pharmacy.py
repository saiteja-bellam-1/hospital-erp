from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, Date, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base

class MedicineCategory(Base):
    __tablename__ = "medicine_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    medicines = relationship("Medicine", back_populates="category")

class Medicine(Base):
    __tablename__ = "medicines"
    
    id = Column(Integer, primary_key=True, index=True)
    medicine_code = Column(String(20), nullable=False)
    name = Column(String(200), nullable=False)
    generic_name = Column(String(200))
    manufacturer = Column(String(100))
    category_id = Column(Integer, ForeignKey("medicine_categories.id"), nullable=False)
    dosage_form = Column(String(50))  # tablet, capsule, syrup, injection
    strength = Column(String(50))
    unit_price = Column(Float, nullable=False)
    description = Column(Text)
    side_effects = Column(Text)
    contraindications = Column(Text)
    storage_conditions = Column(Text)
    is_active = Column(Boolean, default=True)
    requires_prescription = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    category = relationship("MedicineCategory", back_populates="medicines")
    inventory = relationship("PharmacyInventory", back_populates="medicine")
    prescription_items = relationship("PrescriptionItem", back_populates="medicine")

class PharmacyInventory(Base):
    __tablename__ = "pharmacy_inventory"
    
    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    batch_number = Column(String(50), nullable=False)
    expiry_date = Column(Date, nullable=False)
    quantity_in_stock = Column(Integer, nullable=False, default=0)
    cost_price = Column(Float, nullable=False)
    selling_price = Column(Float, nullable=False)
    supplier = Column(String(100))
    purchase_date = Column(Date)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    medicine = relationship("Medicine", back_populates="inventory")

class Prescription(Base):
    __tablename__ = "prescriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    prescription_number = Column(String(50), unique=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    consultation_id = Column(Integer, ForeignKey("consultations.id"))
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True)
    prescription_date = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String(20), default="pending")  # pending, dispensed, partial, cancelled
    notes = Column(Text)
    total_amount = Column(Float, default=0.0)
    dispensed_by_id = Column(Integer, ForeignKey("users.id"))
    dispensed_date = Column(DateTime)
    inpatient_bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)  # which admission bill consumed this Rx

    items = relationship("PrescriptionItem", back_populates="prescription")
    consultation = relationship("Consultation", back_populates="prescriptions")

class PrescriptionItem(Base):
    __tablename__ = "prescription_items"

    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    quantity_prescribed = Column(Integer, nullable=False)
    quantity_dispensed = Column(Integer, default=0)
    dosage = Column(String(100))  # 1 tablet twice daily
    duration = Column(String(50))  # 7 days
    instructions = Column(Text)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    status = Column(String(20), default="pending")  # pending, dispensed, partial

    # MAR scheduling fields (used when prescription is for an inpatient admission)
    frequency = Column(String(50))           # e.g. "BD", "TDS", "QID", "Q8H", "ONCE"
    schedule_times = Column(JSON)            # ["08:00", "16:00", "00:00"] for fixed schedules
    duration_days = Column(Integer)          # numeric form of duration for MAR generation
    route = Column(String(30))               # oral, iv, im, sc, topical, inhalation, sublingual, rectal
    is_prn = Column(Boolean, default=False)  # as-needed medication, no fixed schedule

    prescription = relationship("Prescription", back_populates="items")
    medicine = relationship("Medicine", back_populates="prescription_items")