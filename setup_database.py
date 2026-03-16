#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, r"/Users/saiteja/Documents/GitHub/hospital-ERP")
sys.path.insert(0, r"/Users/saiteja/Documents/GitHub/hospital-ERP/backend")

from sqlalchemy.orm import Session
from backend.config.database import SessionLocal, create_tables
from backend.app.models.user import UserRole, User
from backend.app.models.hospital import Hospital, HospitalModule
from backend.app.utils.auth import get_password_hash, UserRoles, Modules
import uuid
import json

def create_default_roles(db: Session):
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
    super_admin_role = db.query(UserRole).filter(UserRole.name == UserRoles.SUPER_ADMIN).first()
    existing_admin = db.query(User).filter(User.username == "superadmin").first()
    if not existing_admin:
        admin_user = User(
            user_id=str(uuid.uuid4()),
            username="superadmin",
            email="admin@kthealth-erp.local",
            password_hash=get_password_hash("admin123"),
            first_name="Super",
            last_name="Admin",
            phone="1234567890",
            role_id=super_admin_role.id,
            is_active=True
        )
        db.add(admin_user)
        db.commit()
        print("✓ Super admin created")
    else:
        print("✓ Super admin already exists")

def create_demo_hospital(db: Session):
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
        print("✓ Demo hospital created")
        
        # Create hospital admin
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
                hospital_id=hospital.id,
                is_active=True
            )
            db.add(admin_user)
            db.commit()
            print("✓ Hospital admin created")

def main():
    try:
        create_tables()
        print("✓ Database tables created")
        
        db = SessionLocal()
        create_default_roles(db)
        create_super_admin(db)
        create_demo_hospital(db)
        db.close()
        
        print("\n✅ Database setup complete!")
        return True
    except Exception as e:
        print(f"❌ Database setup failed: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
