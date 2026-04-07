from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from sqlalchemy.sql import func
from config.database import Base


class License(Base):
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True, index=True)
    license_id = Column(String(50), unique=True, nullable=False)
    hospital_id = Column(String(10), nullable=False)  # 6-char alphanumeric code
    hospital_name = Column(String(200))
    plan = Column(String(50), default="standard")
    max_users = Column(Integer, default=50)
    features = Column(JSON)
    issued_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    status = Column(String(20), default="active")  # active, expiring_soon, grace_period, expired
    seller_info = Column(JSON, nullable=True)  # 3rd party vendor details: {name, address, phone}
    gdrive_config = Column(JSON, nullable=True)  # {enabled, service_account, folder_id}
    raw_license_data = Column(Text, nullable=False)  # The full .lic file content
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    uploaded_by = Column(Integer, nullable=True)
