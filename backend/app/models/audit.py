from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from datetime import datetime
from config.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.now, index=True)  # Local system time
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    user_name = Column(String(100))
    user_role = Column(String(50))
    action = Column(String(50), nullable=False, index=True)
    category = Column(String(30), nullable=False, index=True)
    resource_type = Column(String(50))
    resource_id = Column(String(50))
    description = Column(Text)  # Human-readable: "Created patient John Doe (M, 35 yrs)"
    ip_address = Column(String(45))
    details = Column(Text)  # JSON with structured context
