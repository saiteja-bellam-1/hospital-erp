from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from config.database import Base

class SimplePrescription(Base):
    """
    Simplified prescription model storing medicines as JSON
    No dependency on pharmacy or medicine inventory
    """
    __tablename__ = "prescriptions_simple"
    
    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(String(50), unique=True, nullable=False, index=True)
    patient_id = Column(String(100), ForeignKey("patients.patient_id"), nullable=False)  # Using patient_id UUID
    doctor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    consultation_id = Column(Integer, ForeignKey("consultations.id"), nullable=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    admission_id = Column(Integer, ForeignKey("admissions.id"), nullable=True)
    pharmacy_prescription_id = Column(
        Integer,
        ForeignKey("prescriptions.id"),
        nullable=True,
        index=True,
    )

    # Store medicines as JSON array
    medicines = Column(JSON, nullable=False)  
    # Example structure: [
    #   {
    #     "name": "Paracetamol 500mg",
    #     "dosage": "1 tablet twice daily", 
    #     "duration": "5 days",
    #     "instructions": "Take with food",
    #     "quantity": "10 tablets"
    #   }
    # ]
    
    # Additional fields
    diagnosis = Column(Text)
    notes = Column(Text)
    status = Column(String(20), default="active")  # active, cancelled, completed
    
    # Timestamps
    prescription_date = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Hospital ID for multi-tenancy
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)

    def __repr__(self):
        return f"<SimplePrescription(id={self.id}, prescription_id={self.prescription_id}, patient_id={self.patient_id})>"