from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base
import uuid

class UserRole(Base):
    __tablename__ = "user_roles"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    is_system_role = Column(Boolean, default=False)  # Predefined system roles
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    users = relationship("User", back_populates="role")

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()), nullable=False)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    phone = Column(String(15))
    license_number = Column(String(50))    # Doctor's license number
    consultation_fee_inr = Column(String(20))  # Doctor's consultation fee in INR
    inpatient_fee_inr = Column(String(20))     # Doctor's inpatient fee in INR
    emergency_fee_inr = Column(String(20))     # Doctor's emergency fee in INR
    specialization = Column(String(100))  # Doctor's specialization
    qualification = Column(String(255))   # Doctor's qualifications
    experience_years = Column(Integer)     # Years of experience
    is_active = Column(Boolean, default=True)
    role_id = Column(Integer, ForeignKey("user_roles.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    role = relationship("UserRole", back_populates="users")
    hospital = relationship("Hospital", back_populates="users")
    permissions = relationship("UserPermission", back_populates="user")
    availability_settings = relationship("DoctorAvailability", back_populates="doctor", uselist=False)

class UserPermission(Base):
    __tablename__ = "user_permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    module_name = Column(String(50), nullable=False)
    can_read = Column(Boolean, default=False)
    can_write = Column(Boolean, default=False)
    can_delete = Column(Boolean, default=False)
    can_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="permissions")