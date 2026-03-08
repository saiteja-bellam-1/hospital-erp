#!/usr/bin/env python3
"""
Setup script to initialize system modules and data for the Hospital ERP
"""

import sys
import os

# Add the backend directory to Python path
sys.path.insert(0, '/Users/saiteja/Documents/GitHub/hospital-ERP/backend')

from config.database import SessionLocal, create_tables
from app.models.system import SystemModule, SystemSettings
from app.models.user import UserRole, User
from app.models.hospital import Hospital
from app.utils.auth import get_password_hash
import uuid

def setup_system_modules():
    """Initialize system modules"""
    db = SessionLocal()
    
    modules = [
        {
            "module_name": "outpatient",
            "display_name": "Outpatient",
            "description": "Outpatient management and appointments",
            "is_enabled": False,
            "is_always_enabled": False
        },
        {
            "module_name": "inpatient", 
            "display_name": "Inpatient",
            "description": "Inpatient management and ward administration",
            "is_enabled": False,
            "is_always_enabled": False
        },
        {
            "module_name": "lab",
            "display_name": "Laboratory",
            "description": "Laboratory tests and reports management",
            "is_enabled": False,
            "is_always_enabled": False
        },
        {
            "module_name": "pharmacy",
            "display_name": "Pharmacy",
            "description": "Pharmacy and medication management",
            "is_enabled": False,
            "is_always_enabled": False
        },
        {
            "module_name": "ehr",
            "display_name": "Electronic Health Records",
            "description": "Electronic health records and patient data",
            "is_enabled": True,
            "is_always_enabled": True
        },
        {
            "module_name": "admin",
            "display_name": "Administration",
            "description": "System administration and user management",
            "is_enabled": True,
            "is_always_enabled": True
        }
    ]
    
    try:
        for module_data in modules:
            # Check if module already exists
            existing = db.query(SystemModule).filter(
                SystemModule.module_name == module_data["module_name"]
            ).first()
            
            if not existing:
                module = SystemModule(**module_data)
                db.add(module)
                print(f"✓ Created module: {module_data['display_name']}")
            else:
                print(f"✓ Module already exists: {module_data['display_name']}")
        
        db.commit()
        print("✅ System modules setup completed")
        
    except Exception as e:
        print(f"❌ Error setting up modules: {e}")
        db.rollback()
    finally:
        db.close()

def setup_default_roles():
    """Initialize default user roles"""
    db = SessionLocal()
    
    roles = [
        {
            "name": "super_admin",
            "description": "Super Administrator with full system access"
        },
        {
            "name": "hospital_admin", 
            "description": "Hospital Administrator with full hospital access"
        },
        {
            "name": "doctor",
            "description": "Doctor with patient care access"
        },
        {
            "name": "nurse",
            "description": "Nurse with patient care support access"
        },
        {
            "name": "lab_technician",
            "description": "Laboratory technician with lab module access"
        },
        {
            "name": "pharmacist",
            "description": "Pharmacist with pharmacy module access"
        },
        {
            "name": "receptionist",
            "description": "Receptionist with patient registration access"
        }
    ]
    
    try:
        for role_data in roles:
            # Check if role already exists
            existing = db.query(UserRole).filter(
                UserRole.name == role_data["name"]
            ).first()
            
            if not existing:
                role = UserRole(**role_data)
                db.add(role)
                print(f"✓ Created role: {role_data['name']}")
            else:
                print(f"✓ Role already exists: {role_data['name']}")
        
        db.commit()
        print("✅ Default roles setup completed")
        
    except Exception as e:
        print(f"❌ Error setting up roles: {e}")
        db.rollback()
    finally:
        db.close()

def setup_default_hospital():
    """Create default hospital entry"""
    db = SessionLocal()
    
    try:
        # Check if hospital already exists
        existing = db.query(Hospital).first()
        
        if not existing:
            from app.services.super_admin_service import generate_hospital_code
            hospital = Hospital(
                hospital_id=generate_hospital_code(),
                name="Default Hospital",
                address="Default Address",
                phone="1234567890",
                email="hospital@example.com",
                license_number="DEFAULT001",
                is_active=True
            )
            db.add(hospital)
            db.commit()
            print("✓ Created default hospital")
        else:
            print("✓ Hospital already exists")
            
        print("✅ Default hospital setup completed")
        
    except Exception as e:
        print(f"❌ Error setting up hospital: {e}")
        db.rollback()
    finally:
        db.close()

def main():
    """Main setup function"""
    print("🏥 Hospital ERP System Setup")
    print("=" * 40)
    
    # Create all tables
    print("Creating database tables...")
    create_tables()
    print("✅ Database tables created")
    
    # Setup system data
    setup_system_modules()
    setup_default_roles()
    setup_default_hospital()
    
    print("\n🎉 System setup completed successfully!")
    print("\nYou can now:")
    print("1. Start the backend server")
    print("2. Login with existing super admin credentials")
    print("3. Use the admin panel to manage modules and users")

if __name__ == "__main__":
    main()