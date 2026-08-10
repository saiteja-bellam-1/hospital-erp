from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON
from config.database import Base
from app.utils.time import system_now

class SystemModule(Base):
    """
    System-wide module configuration for the single hospital ERP
    """
    __tablename__ = "system_modules"
    
    id = Column(Integer, primary_key=True, index=True)
    module_name = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    description = Column(Text)
    is_enabled = Column(Boolean, default=False)
    is_always_enabled = Column(Boolean, default=False)  # For EHR and Admin modules
    configuration = Column(JSON)  # Module-specific configuration
    created_at = Column(DateTime(timezone=True), default=system_now)
    updated_at = Column(DateTime(timezone=True), onupdate=system_now)

class SystemSettings(Base):
    """
    General system settings and configuration
    """
    __tablename__ = "system_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String(100), unique=True, nullable=False)
    setting_value = Column(Text)
    setting_type = Column(String(20), default='string')  # string, json, boolean, integer
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), default=system_now)
    updated_at = Column(DateTime(timezone=True), onupdate=system_now)