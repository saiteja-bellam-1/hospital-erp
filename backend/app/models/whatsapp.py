from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from config.database import Base
from app.utils.time import system_now


class WhatsAppMessageLog(Base):
    """One row per staff-triggered WhatsApp send (used for usage counts per topic)."""
    __tablename__ = "whatsapp_message_log"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=system_now, index=True)  # naive local time
    kind = Column(String(40), nullable=False, index=True)           # template key / topic
    status = Column(String(10), nullable=False, index=True)         # sent | failed
    attachments = Column(Integer, default=0)                        # files attached to the send
    delivered = Column(Integer, default=0)                          # WhatsApp messages actually delivered
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    patient_ref = Column(String(50))                                # patient uuid/id as passed by UI
    phone_last4 = Column(String(4))                                 # never store the full number
    sent_via = Column(String(20))                                   # primary | secondary (which linked number)
    error = Column(Text)
