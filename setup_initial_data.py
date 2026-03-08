#!/usr/bin/env python3
"""
Initial setup script for Hospital ERP
Creates initial roles, super admin user, and sample data
"""

import sys
import os

# Add the current directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, 'backend'))

from sqlalchemy.orm import Session
from backend.config.database import engine, SessionLocal, create_tables
from backend.app.models.user import UserRole, User
from backend.app.models.hospital import Hospital, HospitalModule
from backend.app.utils.auth import get_password_hash, UserRoles, Modules
import uuid
import json

def create_default_roles(db: Session):
    """Create default user roles"""
    roles = [
        (UserRoles.SUPER_ADMIN, "Super Administrator with system-wide access"),
        (UserRoles.HOSPITAL_ADMIN, "Hospital Administrator with full hospital access"),
        (UserRoles.LAB_ADMIN, "Laboratory Module Administrator"),
        (UserRoles.PHARMACY_ADMIN, "Pharmacy Module Administrator"),
        (UserRoles.BILLING_ADMIN, "Billing Module Administrator"),
        (UserRoles.OUTPATIENT_ADMIN, "Outpatient Module Administrator"),
        (UserRoles.INPATIENT_ADMIN, "Inpatient Module Administrator"),
        (UserRoles.DOCTOR, "Doctor with EHR access"),
        (UserRoles.NURSE, "Nurse with patient care access"),
        (UserRoles.LAB_TECHNICIAN, "Lab Technician"),
        (UserRoles.PHARMACIST, "Pharmacist"),
        (UserRoles.RECEPTIONIST, "Receptionist"),
    ]
    
    for role_name, description in roles:
        existing_role = db.query(UserRole).filter(UserRole.name == role_name).first()
        if not existing_role:
            role = UserRole(name=role_name, description=description)
            db.add(role)
    
    db.commit()
    print("✓ Default roles created")

def create_super_admin(db: Session):
    """Create initial super admin user"""
    super_admin_role = db.query(UserRole).filter(UserRole.name == UserRoles.SUPER_ADMIN).first()
    
    existing_admin = db.query(User).filter(User.username == "superadmin").first()
    if not existing_admin:
        admin_user = User(
            user_id=str(uuid.uuid4()),
            username="superadmin",
            email="admin@hospital-erp.local",
            password_hash=get_password_hash("admin123"),
            first_name="Super",
            last_name="Admin",
            phone="1234567890",
            role_id=super_admin_role.id,
            is_active=True
        )
        db.add(admin_user)
        db.commit()
        print("✓ Super admin created (username: superadmin, password: admin123)")
    else:
        print("✓ Super admin already exists")

def create_demo_hospital(db: Session):
    """Create a demo hospital for testing"""
    existing_hospital = db.query(Hospital).filter(Hospital.name == "Demo Hospital").first()
    
    if not existing_hospital:
        hospital = Hospital(
            hospital_id=str(uuid.uuid4()),
            name="Demo Hospital",
            address="123 Medical Center Drive, Healthcare City, HC 12345",
            phone="555-HOSPITAL",
            email="info@demohospital.local",
            license_number="DEMO-HOSPITAL-001"
        )
        db.add(hospital)
        db.commit()
        db.refresh(hospital)
        
        # Initialize modules for demo hospital
        modules = [Modules.LAB, Modules.PHARMACY, Modules.BILLING, 
                  Modules.EHR, Modules.OUTPATIENT, Modules.INPATIENT]
        
        for module_name in modules:
            hospital_module = HospitalModule(
                hospital_id=hospital.id,
                module_name=module_name,
                is_enabled=True,
                configuration=json.dumps({})
            )
            db.add(hospital_module)
        
        db.commit()
        print("✓ Demo hospital created with all modules enabled")
        
        # Create hospital admin for demo hospital
        create_demo_hospital_admin(db, hospital.id)
    else:
        print("✓ Demo hospital already exists")

def create_demo_hospital_admin(db: Session, hospital_id: int):
    """Create hospital admin for demo hospital"""
    hospital_admin_role = db.query(UserRole).filter(UserRole.name == UserRoles.HOSPITAL_ADMIN).first()
    
    existing_admin = db.query(User).filter(User.username == "hospitaladmin").first()
    if not existing_admin:
        admin_user = User(
            user_id=str(uuid.uuid4()),
            username="hospitaladmin",
            email="admin@demohospital.local",
            password_hash=get_password_hash("hospital123"),
            first_name="Hospital",
            last_name="Admin",
            phone="555-ADMIN",
            role_id=hospital_admin_role.id,
            hospital_id=hospital_id,
            is_active=True
        )
        db.add(admin_user)
        
        # Grant permissions to hospital admin (this would be done by the service)
        from backend.app.models.user import UserPermission
        modules = [Modules.LAB, Modules.PHARMACY, Modules.BILLING,
                  Modules.EHR, Modules.OUTPATIENT, Modules.INPATIENT, Modules.ADMIN]
        
        for module in modules:
            permission = UserPermission(
                user_id=admin_user.id,
                module_name=module,
                can_read=True,
                can_write=True,
                can_delete=True,
                can_admin=True
            )
            db.add(permission)
        
        db.commit()
        print("✓ Hospital admin created (username: hospitaladmin, password: hospital123)")
    else:
        print("✓ Hospital admin already exists")

def main():
    """Main setup function"""
    print("Setting up Hospital ERP Database...")
    
    # Create all tables
    create_tables()
    print("✓ Database tables created")
    
    # Create session
    db = SessionLocal()
    
    try:
        # Create default data
        create_default_roles(db)
        create_super_admin(db)
        create_demo_hospital(db)
        
        print("\n" + "="*50)
        print("Hospital ERP Setup Complete!")
        print("="*50)
        print("Default Login Credentials:")
        print("-" * 30)
        print("Super Admin:")
        print("  Username: superadmin")
        print("  Password: admin123")
        print()
        print("Hospital Admin (Demo Hospital):")
        print("  Username: hospitaladmin")
        print("  Password: hospital123")
        print()
        print("Server URLs:")
        print("  Backend API: http://localhost:8000")
        print("  Frontend: http://localhost:3000")
        print("  API Docs: http://localhost:8000/docs")
        print("="*50)
        
    except Exception as e:
        print(f"Error during setup: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    main()