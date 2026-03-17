from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base

class LabTestCategory(Base):
    __tablename__ = "lab_test_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    tests = relationship("LabTest", back_populates="category")

class LabTest(Base):
    __tablename__ = "lab_tests"
    
    id = Column(Integer, primary_key=True, index=True)
    test_code = Column(String(20), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    category_id = Column(Integer, ForeignKey("lab_test_categories.id"), nullable=False)
    cost = Column(Float, nullable=False)
    sample_type = Column(String(50))
    method = Column(String(200))
    preparation_instructions = Column(Text)
    normal_range = Column(String(100))
    unit = Column(String(20))
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    category = relationship("LabTestCategory", back_populates="tests")
    orders = relationship("PatientLabOrder", back_populates="test")
    parameters = relationship("LabTestParameter", back_populates="test", order_by="LabTestParameter.display_order")

class LabTestParameter(Base):
    __tablename__ = "lab_test_parameters"

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("lab_tests.id"), nullable=False)
    parameter_name = Column(String(200), nullable=False)
    unit = Column(String(50))
    method = Column(String(200), nullable=True)
    section = Column(String(200), nullable=True)  # For grouping parameters within a test
    field_type = Column(String(20), default="numeric")  # numeric, text, select
    reference_min_male = Column(Float, nullable=True)
    reference_max_male = Column(Float, nullable=True)
    reference_min_female = Column(Float, nullable=True)
    reference_max_female = Column(Float, nullable=True)
    reference_min_default = Column(Float, nullable=True)
    reference_max_default = Column(Float, nullable=True)
    reference_min_child = Column(Float, nullable=True)
    reference_max_child = Column(Float, nullable=True)
    possible_values = Column(JSON, nullable=True)  # For select-type: ["Positive","Negative"]
    abnormal_values = Column(JSON, nullable=True)  # Values considered abnormal: ["Positive","Reactive","++","+++"]
    normal_value = Column(String(100), nullable=True)  # Normal/expected value for reference display: "Negative"
    notes = Column(String(500), nullable=True)
    display_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    test = relationship("LabTest", back_populates="parameters")


class LabTestPackageCategory(Base):
    __tablename__ = "lab_test_package_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    packages = relationship("LabTestPackage", back_populates="category")


class LabTestPackage(Base):
    __tablename__ = "lab_test_packages"

    id = Column(Integer, primary_key=True, index=True)
    package_code = Column(String(20), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    category_id = Column(Integer, ForeignKey("lab_test_package_categories.id"), nullable=False)
    package_price = Column(Float, nullable=False)
    actual_price = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    category = relationship("LabTestPackageCategory", back_populates="packages")
    items = relationship("LabTestPackageItem", back_populates="package", cascade="all, delete-orphan")
    orders = relationship("PatientLabOrder", back_populates="package")


class LabTestPackageItem(Base):
    __tablename__ = "lab_test_package_items"

    id = Column(Integer, primary_key=True, index=True)
    package_id = Column(Integer, ForeignKey("lab_test_packages.id"), nullable=False)
    test_id = Column(Integer, ForeignKey("lab_tests.id"), nullable=False)

    package = relationship("LabTestPackage", back_populates="items")
    test = relationship("LabTest")


class LabReportTemplate(Base):
    __tablename__ = "lab_report_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    test_id = Column(Integer, ForeignKey("lab_tests.id"), nullable=False)
    template_fields = Column(JSON)  # Dynamic template fields
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    reports = relationship("LabReport", back_populates="template")

class PatientLabOrder(Base):
    __tablename__ = "patient_lab_orders"
    
    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String(50), unique=True, nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    test_id = Column(Integer, ForeignKey("lab_tests.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("users.id"))
    consultation_id = Column(Integer, ForeignKey("consultations.id"), nullable=True)  # Link to consultation
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)  # Link to appointment
    status = Column(String(20), default="ordered")  # ordered, collected, processing, completed, cancelled
    order_date = Column(DateTime(timezone=True), server_default=func.now())
    collection_date = Column(DateTime)
    completion_date = Column(DateTime)
    priority = Column(String(10), default="normal")  # normal, urgent, stat
    notes = Column(Text)
    amount = Column(Float, default=0.0)  # Cost from LabTest at time of order
    payment_status = Column(String(20), default="pending")  # pending, paid
    payment_method = Column(String(50), nullable=True)  # cash, card, online
    payment_date = Column(DateTime, nullable=True)
    sample_id = Column(String(50), nullable=True, unique=True)
    referred_by = Column(String(100), nullable=True)
    package_id = Column(Integer, ForeignKey("lab_test_packages.id"), nullable=True)
    package_booking_id = Column(String(50), nullable=True)  # Groups orders from same package booking
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    patient = relationship("Patient", back_populates="lab_orders")
    test = relationship("LabTest", back_populates="orders")
    consultation = relationship("Consultation", back_populates="lab_orders")
    report = relationship("LabReport", back_populates="order", uselist=False)
    package = relationship("LabTestPackage", back_populates="orders")

class LabReport(Base):
    __tablename__ = "lab_reports"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("patient_lab_orders.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("lab_report_templates.id"))
    result_values = Column(JSON)  # Test results
    interpretation = Column(Text)
    technician_id = Column(Integer, ForeignKey("users.id"))
    verified_by_id = Column(Integer, ForeignKey("users.id"))
    report_date = Column(DateTime(timezone=True), server_default=func.now())
    is_verified = Column(Boolean, default=False)
    verification_date = Column(DateTime)
    
    order = relationship("PatientLabOrder", back_populates="report")
    template = relationship("LabReportTemplate", back_populates="reports")