from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from config.database import Base
from app.utils.time import system_now

class SampleType(Base):
    __tablename__ = "sample_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=system_now)

    tests = relationship("LabTest", back_populates="sample_type_ref")


class LabTestCategory(Base):
    __tablename__ = "lab_test_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=system_now)

    tests = relationship("LabTest", back_populates="category")

class LabTest(Base):
    __tablename__ = "lab_tests"
    
    id = Column(Integer, primary_key=True, index=True)
    test_code = Column(String(20), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    category_id = Column(Integer, ForeignKey("lab_test_categories.id"), nullable=False)
    cost = Column(Float, nullable=False)
    sample_type = Column(String(50))  # Legacy free-text, kept for backward compat
    sample_type_id = Column(Integer, ForeignKey("sample_types.id"), nullable=True)
    method = Column(String(200))
    preparation_instructions = Column(Text)
    normal_range = Column(String(100))
    unit = Column(String(20))
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    # in_house: processed here. send_out: sample collected here, processed by a partner lab.
    default_fulfillment = Column(String(20), default="in_house")
    default_partner_id = Column(Integer, ForeignKey("lab_partners.id"), nullable=True)
    default_partner_cost = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now)
    updated_at = Column(DateTime(timezone=True), onupdate=system_now)

    category = relationship("LabTestCategory", back_populates="tests")
    sample_type_ref = relationship("SampleType", back_populates="tests")
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
    field_type = Column(String(20), default="numeric")  # numeric, tiered_numeric, less_than, greater_than, positive_negative, reactive, presence_absence, cloudy_clear, colour, manual, select
    reference_ranges = Column(JSON, nullable=True)  # [{min, max, gender, age_min, age_max, description, is_normal}]
    # Legacy columns kept for backward compatibility
    reference_min_male = Column(Float, nullable=True)
    reference_max_male = Column(Float, nullable=True)
    reference_min_female = Column(Float, nullable=True)
    reference_max_female = Column(Float, nullable=True)
    reference_min_default = Column(Float, nullable=True)
    reference_max_default = Column(Float, nullable=True)
    reference_min_child = Column(Float, nullable=True)
    reference_max_child = Column(Float, nullable=True)
    possible_values = Column(JSON, nullable=True)  # For select-type: ["Positive","Negative"]
    abnormal_values = Column(JSON, nullable=True)  # Values considered abnormal
    critical_low = Column(Float, nullable=True)    # Values below trigger a critical alert
    critical_high = Column(Float, nullable=True)   # Values above trigger a critical alert
    normal_value = Column(String(100), nullable=True)
    notes = Column(String(500), nullable=True)
    display_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=system_now)

    test = relationship("LabTest", back_populates="parameters")


class LabTestPackageCategory(Base):
    __tablename__ = "lab_test_package_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=system_now)

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
    created_at = Column(DateTime(timezone=True), default=system_now)
    updated_at = Column(DateTime(timezone=True), onupdate=system_now)

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
    created_at = Column(DateTime(timezone=True), default=system_now)
    
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
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True)  # Link to inpatient admission
    status = Column(String(20), default="ordered")  # ordered, collected, processing, completed, cancelled
    order_date = Column(DateTime(timezone=True), default=system_now)
    collection_date = Column(DateTime)
    completion_date = Column(DateTime)
    priority = Column(String(10), default="normal")  # normal, urgent, stat
    notes = Column(Text)
    amount = Column(Float, default=0.0)  # Cost from LabTest at time of order
    payment_status = Column(String(20), default="pending")  # pending, paid
    payment_method = Column(String(50), nullable=True)  # cash, card, online
    payment_date = Column(DateTime, nullable=True)
    sample_id = Column(String(50), nullable=True, index=True)
    sample_ean13 = Column(String(13), nullable=True, index=True)
    referred_by = Column(String(100), nullable=True)
    package_id = Column(Integer, ForeignKey("lab_test_packages.id"), nullable=True)
    package_booking_id = Column(String(50), nullable=True)  # Groups orders from same package booking
    bill_cancelled_reason = Column(Text, nullable=True)
    bill_cancelled_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    bill_cancelled_at = Column(DateTime, nullable=True)
    # Clinical cancellation is separate from cancelling/reversing a bill.
    cancelled_reason = Column(Text, nullable=True)
    cancelled_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    inpatient_bill_id = Column(Integer, ForeignKey("bills.id"), nullable=True)  # which admission bill consumed this lab order
    # Outpatient/reception bill grouping. Orders that were billed together
    # (e.g. all tests on one reception booking, all tests in a package, all
    # pending orders on a patient-level "pay all") share the same
    # lab_bill_group_id and lab_bill_number. This is what lets the Billing
    # dashboard render ONE row per real bill, and what lets the regenerate
    # endpoint reconstruct the original combined PDF.
    lab_bill_group_id = Column(String(64), nullable=True, index=True)
    lab_bill_number = Column(String(64), nullable=True)
    # Selling rate snapshotted at booking. amount remains the billed price.
    rate_card_id = Column(Integer, ForeignKey("lab_rate_cards.id"), nullable=True)
    # in_house | send_out | receive_in
    fulfillment = Column(String(20), default="in_house")
    partner_id = Column(Integer, ForeignKey("lab_partners.id"), nullable=True, index=True)
    partner_cost = Column(Float, nullable=True)
    # send_out: to_send, sent, result_received. receive_in: received, reported.
    partner_status = Column(String(30), nullable=True)
    partner_reference = Column(String(100), nullable=True)
    # patient: charged on the patient bill. partner: charged to the referring lab.
    bill_to = Column(String(20), default="patient")
    partner_settlement_status = Column(String(20), nullable=True)  # unsettled | settled
    partner_invoice_ref = Column(String(100), nullable=True)
    partner_settled_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now)

    patient = relationship("Patient", back_populates="lab_orders")
    test = relationship("LabTest", back_populates="orders")
    consultation = relationship("Consultation", back_populates="lab_orders")
    admission = relationship("Admission", back_populates="lab_orders")
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
    report_date = Column(DateTime(timezone=True), default=system_now)
    is_verified = Column(Boolean, default=False)
    verification_date = Column(DateTime)
    
    order = relationship("PatientLabOrder", back_populates="report")
    template = relationship("LabReportTemplate", back_populates="reports")


class LabRateCard(Base):
    """Named selling price for lab tests. Seeded as Rate A (default) and Rate B."""
    __tablename__ = "lab_rate_cards"
    __table_args__ = (
        UniqueConstraint("hospital_id", "code", name="uq_lab_rate_card_code"),
    )

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    code = Column(String(20), nullable=False)
    name = Column(String(100), nullable=False)
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=system_now)


class LabTestRate(Base):
    __tablename__ = "lab_test_rates"
    __table_args__ = (
        UniqueConstraint("test_id", "rate_card_id", name="uq_lab_test_rate"),
    )

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("lab_tests.id"), nullable=False, index=True)
    rate_card_id = Column(Integer, ForeignKey("lab_rate_cards.id"), nullable=False)
    amount = Column(Float, nullable=False, default=0.0)


class LabPartner(Base):
    """External lab we send samples to, or that sends samples to us."""
    __tablename__ = "lab_partners"
    __table_args__ = (
        UniqueConstraint("hospital_id", "name", name="uq_lab_partner_name"),
    )

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    name = Column(String(200), nullable=False)
    contact_person = Column(String(100), nullable=True)
    phone = Column(String(30), nullable=True)
    email = Column(String(100), nullable=True)
    address = Column(Text, nullable=True)
    # send_out: they process our samples. receive_in: we process theirs. both.
    partner_role = Column(String(20), default="both")
    default_rate_card_id = Column(Integer, ForeignKey("lab_rate_cards.id"), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=system_now)
    updated_at = Column(DateTime(timezone=True), onupdate=system_now)