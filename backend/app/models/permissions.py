from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config.database import Base

class ModulePermission(Base):
    """
    Defines what permissions are available for each module
    """
    __tablename__ = "module_permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    module_name = Column(String(50), nullable=False)
    permission_name = Column(String(100), nullable=False)
    permission_description = Column(Text)
    category = Column(String(50))  # admin, user, view_only
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Make combination of module and permission unique
    __table_args__ = (
        {'sqlite_autoincrement': True},
    )

class RoleModulePermission(Base):
    """
    Maps which permissions each role has for each module
    """
    __tablename__ = "role_module_permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    role_id = Column(Integer, ForeignKey("user_roles.id"), nullable=False)
    module_name = Column(String(50), nullable=False)
    permissions = Column(JSON)  # List of permission names this role has for this module
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    role = relationship("UserRole")

class HospitalSettings(Base):
    """
    Hospital-wide settings and configurations
    """
    __tablename__ = "hospital_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    setting_category = Column(String(50), nullable=False)  # billing, lab, pharmacy, etc.
    setting_key = Column(String(100), nullable=False)
    setting_value = Column(Text)
    setting_type = Column(String(20), default='string')  # string, json, number, boolean
    description = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    creator = relationship("User")

class ModuleTemplate(Base):
    """
    Templates for different modules (forms, reports, etc.)
    """
    __tablename__ = "module_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    module_name = Column(String(50), nullable=False)
    template_name = Column(String(100), nullable=False)
    template_type = Column(String(50), nullable=False)  # form, report, prescription, etc.
    template_data = Column(JSON)  # Template structure/content
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    creator = relationship("User")

class ModuleRates(Base):
    """
    Pricing/rates configuration for different modules
    """
    __tablename__ = "module_rates"
    
    id = Column(Integer, primary_key=True, index=True)
    module_name = Column(String(50), nullable=False)
    service_name = Column(String(100), nullable=False)
    service_code = Column(String(50))
    base_rate = Column(String(20))  # Stored as string to handle different currencies/formats
    discounted_rate = Column(String(20))
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    creator = relationship("User")