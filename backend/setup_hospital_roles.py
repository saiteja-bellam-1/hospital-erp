#!/usr/bin/env python3
"""
Setup script to initialize hospital roles, permissions, and module-specific configurations
"""

import sys
import os

# Add the backend directory to Python path
sys.path.insert(0, '/Users/saiteja/Documents/GitHub/hospital-ERP/backend')

from config.database import SessionLocal, create_tables
from app.models.user import UserRole
from app.models.permissions import ModulePermission, RoleModulePermission, HospitalSettings
from app.models.system import SystemModule

def setup_module_permissions():
    """Create detailed permissions for each module"""
    db = SessionLocal()
    
    permissions_data = [
        # Lab Module Permissions
        {"module_name": "lab", "permission_name": "manage_tests", "permission_description": "Create and manage lab test types", "category": "admin"},
        {"module_name": "lab", "permission_name": "set_rates", "permission_description": "Set pricing for lab tests", "category": "admin"},
        {"module_name": "lab", "permission_name": "view_reports", "permission_description": "View lab reports", "category": "user"},
        {"module_name": "lab", "permission_name": "create_reports", "permission_description": "Create lab reports", "category": "user"},
        {"module_name": "lab", "permission_name": "manage_equipment", "permission_description": "Manage lab equipment", "category": "admin"},
        {"module_name": "lab", "permission_name": "manage_templates", "permission_description": "Create and edit report templates", "category": "admin"},
        
        # Pharmacy Module Permissions  
        {"module_name": "pharmacy", "permission_name": "manage_inventory", "permission_description": "Manage medication inventory", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "set_drug_rates", "permission_description": "Set medication pricing", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "dispense_medications", "permission_description": "Dispense medications", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "view_prescriptions", "permission_description": "View patient prescriptions", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "manage_suppliers", "permission_description": "Manage drug suppliers", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "generate_reports", "permission_description": "Generate pharmacy reports", "category": "admin"},
        
        # Billing Module Permissions
        {"module_name": "billing", "permission_name": "manage_rates", "permission_description": "Manage service rates and pricing", "category": "admin"},
        {"module_name": "billing", "permission_name": "process_payments", "permission_description": "Process patient payments", "category": "user"},
        {"module_name": "billing", "permission_name": "generate_invoices", "permission_description": "Generate patient invoices", "category": "user"},
        {"module_name": "billing", "permission_name": "view_financial_reports", "permission_description": "View financial reports", "category": "admin"},
        {"module_name": "billing", "permission_name": "manage_insurance", "permission_description": "Manage insurance claims", "category": "admin"},
        {"module_name": "billing", "permission_name": "handle_refunds", "permission_description": "Process refunds", "category": "admin"},
        
        # Outpatient Module Permissions
        {"module_name": "outpatient", "permission_name": "schedule_appointments", "permission_description": "Schedule patient appointments", "category": "user"},
        {"module_name": "outpatient", "permission_name": "manage_schedules", "permission_description": "Manage doctor schedules", "category": "admin"},
        {"module_name": "outpatient", "permission_name": "register_patients", "permission_description": "Register new patients", "category": "user"},
        {"module_name": "outpatient", "permission_name": "manage_queues", "permission_description": "Manage patient queues", "category": "user"},
        {"module_name": "outpatient", "permission_name": "view_appointments", "permission_description": "View appointment details", "category": "user"},
        {"module_name": "outpatient", "permission_name": "cancel_appointments", "permission_description": "Cancel appointments", "category": "user"},
        
        # Inpatient Module Permissions
        {"module_name": "inpatient", "permission_name": "manage_beds", "permission_description": "Manage hospital bed allocation", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "admit_patients", "permission_description": "Admit patients", "category": "user"},
        {"module_name": "inpatient", "permission_name": "discharge_patients", "permission_description": "Discharge patients", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_wards", "permission_description": "Manage ward configurations", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "set_room_rates", "permission_description": "Set room pricing", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "view_occupancy", "permission_description": "View bed occupancy reports", "category": "user"},
        
        # EHR Module Permissions (always enabled)
        {"module_name": "ehr", "permission_name": "view_records", "permission_description": "View patient electronic health records", "category": "user"},
        {"module_name": "ehr", "permission_name": "edit_records", "permission_description": "Edit patient records", "category": "user"},
        {"module_name": "ehr", "permission_name": "create_prescriptions", "permission_description": "Create prescriptions", "category": "user"},
        {"module_name": "ehr", "permission_name": "manage_templates", "permission_description": "Manage EHR templates", "category": "admin"},
        {"module_name": "ehr", "permission_name": "view_history", "permission_description": "View patient medical history", "category": "user"},
        {"module_name": "ehr", "permission_name": "generate_reports", "permission_description": "Generate medical reports", "category": "user"},
        
        # Admin Module Permissions
        {"module_name": "admin", "permission_name": "manage_users", "permission_description": "Create and manage users", "category": "admin"},
        {"module_name": "admin", "permission_name": "manage_roles", "permission_description": "Create and manage roles", "category": "admin"},
        {"module_name": "admin", "permission_name": "manage_modules", "permission_description": "Enable/disable modules", "category": "admin"},
        {"module_name": "admin", "permission_name": "view_system_reports", "permission_description": "View system reports", "category": "admin"},
        {"module_name": "admin", "permission_name": "manage_settings", "permission_description": "Manage system settings", "category": "admin"},
    ]
    
    try:
        for perm_data in permissions_data:
            existing = db.query(ModulePermission).filter(
                ModulePermission.module_name == perm_data["module_name"],
                ModulePermission.permission_name == perm_data["permission_name"]
            ).first()
            
            if not existing:
                permission = ModulePermission(**perm_data)
                db.add(permission)
                
        db.commit()
        print("✅ Module permissions setup completed")
        
    except Exception as e:
        print(f"❌ Error setting up permissions: {e}")
        db.rollback()
    finally:
        db.close()

def setup_hospital_roles():
    """Create predefined hospital roles with specific responsibilities"""
    db = SessionLocal()
    
    roles_data = [
        {
            "name": "hospital_admin",
            "description": "Hospital Administrator with overall management access",
            "is_system_role": True
        },
        {
            "name": "lab_admin", 
            "description": "Laboratory Administrator - manages lab operations, rates, and templates",
            "is_system_role": True
        },
        {
            "name": "pharmacy_admin",
            "description": "Pharmacy Administrator - manages inventory, rates, and drug supplies",
            "is_system_role": True
        },
        {
            "name": "billing_admin",
            "description": "Billing Administrator - manages rates, insurance, and financial operations",
            "is_system_role": True
        },
        {
            "name": "inpatient_admin",
            "description": "Inpatient Administrator - manages beds, wards, and room rates",
            "is_system_role": True
        },
        {
            "name": "frontdesk",
            "description": "Front Desk Staff - manages appointments, patient registration, and scheduling",
            "is_system_role": True
        },
        {
            "name": "doctor",
            "description": "Medical Doctor - patient care and medical records access",
            "is_system_role": True
        },
        {
            "name": "nurse", 
            "description": "Nursing Staff - patient care support",
            "is_system_role": True
        },
        {
            "name": "lab_technician",
            "description": "Laboratory Technician - performs lab tests and generates reports",
            "is_system_role": True
        },
        {
            "name": "pharmacist",
            "description": "Pharmacist - medication dispensing and pharmacy operations",
            "is_system_role": True
        }
    ]
    
    try:
        for role_data in roles_data:
            existing = db.query(UserRole).filter(UserRole.name == role_data["name"]).first()
            
            if not existing:
                role = UserRole(**role_data)
                db.add(role)
                print(f"✓ Created role: {role_data['name']}")
            else:
                # Update existing role to be system role if not already
                if not existing.is_system_role:
                    existing.is_system_role = True
                    print(f"✓ Updated role: {role_data['name']}")
                else:
                    print(f"✓ Role already exists: {role_data['name']}")
                    
        db.commit()
        print("✅ Hospital roles setup completed")
        
    except Exception as e:
        print(f"❌ Error setting up roles: {e}")
        db.rollback()
    finally:
        db.close()

def setup_role_permissions():
    """Assign specific permissions to each role"""
    db = SessionLocal()
    
    role_permissions_map = {
        "super_admin": {
            "admin": ["manage_users", "manage_roles", "manage_modules", "view_system_reports", "manage_settings"],
            "lab": ["manage_tests", "set_rates", "view_reports", "create_reports", "manage_equipment", "manage_templates"],
            "pharmacy": ["manage_inventory", "set_drug_rates", "dispense_medications", "view_prescriptions", "manage_suppliers", "generate_reports"],
            "billing": ["manage_rates", "process_payments", "generate_invoices", "view_financial_reports", "manage_insurance", "handle_refunds"],
            "outpatient": ["schedule_appointments", "manage_schedules", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "inpatient": ["manage_beds", "admit_patients", "discharge_patients", "manage_wards", "set_room_rates", "view_occupancy"],
            "ehr": ["view_records", "edit_records", "create_prescriptions", "manage_templates", "view_history", "generate_reports"]
        },
        "hospital_admin": {
            "admin": ["manage_users", "manage_roles", "view_system_reports", "manage_settings"],
            "lab": ["view_reports", "create_reports"],
            "pharmacy": ["view_prescriptions", "generate_reports"],
            "billing": ["view_financial_reports", "manage_insurance", "process_payments", "generate_invoices"],
            "outpatient": ["schedule_appointments", "manage_schedules", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "inpatient": ["view_occupancy"],
            "ehr": ["view_records", "edit_records", "view_history", "generate_reports"]
        },
        "lab_admin": {
            "lab": ["manage_tests", "set_rates", "view_reports", "create_reports", "manage_equipment", "manage_templates"]
        },
        "pharmacy_admin": {
            "pharmacy": ["manage_inventory", "set_drug_rates", "dispense_medications", "view_prescriptions", "manage_suppliers", "generate_reports"]
        },
        "billing_admin": {
            "billing": ["manage_rates", "process_payments", "generate_invoices", "view_financial_reports", "manage_insurance", "handle_refunds"]
        },
        "inpatient_admin": {
            "inpatient": ["manage_beds", "admit_patients", "discharge_patients", "manage_wards", "set_room_rates", "view_occupancy"]
        },
        "frontdesk": {
            "outpatient": ["schedule_appointments", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "ehr": ["view_records", "view_history"]
        },
        "doctor": {
            "ehr": ["view_records", "edit_records", "create_prescriptions", "view_history", "generate_reports"],
            "lab": ["view_reports", "create_reports"],
            "pharmacy": ["view_prescriptions"],
            "outpatient": ["view_appointments"],
            "inpatient": ["admit_patients", "discharge_patients", "view_occupancy"]
        },
        "nurse": {
            "ehr": ["view_records", "edit_records", "view_history"],
            "inpatient": ["view_occupancy"],
            "outpatient": ["manage_queues", "view_appointments"]
        },
        "lab_technician": {
            "lab": ["view_reports", "create_reports"]
        },
        "pharmacist": {
            "pharmacy": ["dispense_medications", "view_prescriptions", "manage_inventory"]
        },
        "receptionist": {
            "outpatient": ["schedule_appointments", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "billing": ["process_payments", "generate_invoices", "view_financial_reports"],
            "ehr": ["view_records", "view_history"]
        }
    }
    
    try:
        for role_name, module_permissions in role_permissions_map.items():
            role = db.query(UserRole).filter(UserRole.name == role_name).first()
            if not role:
                print(f"⚠️ Role {role_name} not found, skipping permissions")
                continue
                
            for module_name, permissions in module_permissions.items():
                existing = db.query(RoleModulePermission).filter(
                    RoleModulePermission.role_id == role.id,
                    RoleModulePermission.module_name == module_name
                ).first()
                
                if existing:
                    existing.permissions = permissions
                else:
                    role_perm = RoleModulePermission(
                        role_id=role.id,
                        module_name=module_name,
                        permissions=permissions
                    )
                    db.add(role_perm)
                    
        db.commit()
        print("✅ Role permissions mapping completed")
        
    except Exception as e:
        print(f"❌ Error setting up role permissions: {e}")
        db.rollback()
    finally:
        db.close()

def main():
    """Main setup function"""
    print("🏥 Hospital Roles & Permissions Setup")
    print("=" * 50)
    
    # Create all tables
    print("Creating database tables...")
    create_tables()
    print("✅ Database tables created")
    
    # Setup components
    setup_module_permissions()
    setup_hospital_roles() 
    setup_role_permissions()
    
    print("\n🎉 Hospital roles and permissions setup completed successfully!")
    print("\nPredefined Roles Created:")
    print("- hospital_admin: Overall hospital management")
    print("- lab_admin: Lab operations, rates, templates")
    print("- pharmacy_admin: Inventory, drug rates, suppliers")
    print("- billing_admin: Financial operations, rates, insurance")
    print("- inpatient_admin: Bed management, ward operations")
    print("- frontdesk: Appointment scheduling, patient registration")
    print("- doctor: Medical care, prescriptions, records")
    print("- nurse: Patient care support")
    print("- lab_technician: Lab test operations")
    print("- pharmacist: Medication dispensing")

if __name__ == "__main__":
    main()