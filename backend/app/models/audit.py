from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from config.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_name = Column(String(100))
    user_role = Column(String(50))
    action = Column(String(50), nullable=False, index=True)  # create_patient, book_appointment, etc.
    category = Column(String(30), nullable=False, index=True)  # patient, appointment, lab, admin, etc.
    resource_type = Column(String(50))  # Patient, Appointment, LabOrder, etc.
    resource_id = Column(String(50))  # ID of affected record
    description = Column(Text)  # Human-readable description
    ip_address = Column(String(45))
    details = Column(Text)  # JSON string for extra context (before/after values)
