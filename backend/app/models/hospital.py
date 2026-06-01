from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base

class Hospital(Base):
    __tablename__ = "hospitals"
    
    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(String(36), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    address = Column(Text)
    city = Column(String(50))
    state = Column(String(50))
    postal_code = Column(String(20))
    country = Column(String(50))
    phone = Column(String(15))
    fax = Column(String(15))
    email = Column(String(100))
    website = Column(String(100))
    license_number = Column(String(50))
    registration_number = Column(String(50))
    tax_id = Column(String(50))
    logo_url = Column(String(255))
    description = Column(Text)
    established_date = Column(DateTime)
    mrn_prefix = Column(String(8), nullable=True)
    is_active = Column(Boolean, default=True)
    # Pharmacy module per-hospital settings (Phase 3).
    # void_window_days = 0 means voids are never time-limited; > 0 caps the
    # age of a sale that can be voided without the `void_sale_legacy` perm.
    pharmacy_void_window_days = Column(Integer, default=0)
    # When True, free quantity included on a sale line contributes to the
    # taxable base. Default off — most pharmacies do not tax freebies.
    pharmacy_tax_on_free = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    users = relationship("User", back_populates="hospital")
    modules = relationship("HospitalModule", back_populates="hospital")

class HospitalModule(Base):
    __tablename__ = "hospital_modules"
    
    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    module_name = Column(String(50), nullable=False)
    is_enabled = Column(Boolean, default=False)
    configuration = Column(Text)  # JSON configuration for module
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    hospital = relationship("Hospital", back_populates="modules")