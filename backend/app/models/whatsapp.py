"""Outbound WhatsApp message log. PDFs are not stored here."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from config.database import Base
from app.utils.time import system_now


class WhatsAppMessage(Base):
    __tablename__ = "whatsapp_messages"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=True, index=True)
    kind = Column(String(50), nullable=False)
    template_family = Column(String(40), nullable=False)
    resource_type = Column(String(50), nullable=False)
    resource_id = Column(String(200), nullable=False)
    phone = Column(String(20), nullable=False)
    filename = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="submitted")
    provider_request_id = Column(String(120), nullable=True)
    error = Column(Text, nullable=True)
    sent_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=system_now, index=True)
