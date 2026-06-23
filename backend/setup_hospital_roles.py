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
        
        # Pharmacy Module Permissions — granular (mirrors db_seed.py)
        # Catalog
        {"module_name": "pharmacy", "permission_name": "view_catalog", "permission_description": "View medicine catalog and master tables", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "manage_medicines", "permission_description": "Create, edit, and delete medicines", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "manage_companies", "permission_description": "Maintain pharmacy company / manufacturer master", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "manage_suppliers", "permission_description": "Maintain pharmacy supplier / party master", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "manage_salts", "permission_description": "Maintain salt / composition master", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "manage_racks", "permission_description": "Maintain rack / location master", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "manage_uoms", "permission_description": "Maintain unit-of-measure master", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "manage_categories", "permission_description": "Maintain medicine category master", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "manage_hsn_tax", "permission_description": "Maintain HSN code and SGST/CGST tax master", "category": "admin"},
        # Pricing
        {"module_name": "pharmacy", "permission_name": "set_rates", "permission_description": "Set MRP, Purchase-Rate, Rate-A, Rate-B on medicines", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "set_discounts", "permission_description": "Set default discount percentages on medicines", "category": "admin"},
        # Regulatory
        {"module_name": "pharmacy", "permission_name": "manage_scheduled_drugs", "permission_description": "Flag Schedule H / H1 / Tramadol / Narcotic medicines", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "view_narcotic_register", "permission_description": "View narcotic / Schedule H register", "category": "user"},
        # Inventory
        {"module_name": "pharmacy", "permission_name": "view_inventory", "permission_description": "View current stock levels and batch list", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "adjust_stock", "permission_description": "Make manual stock adjustments", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "view_stock_ledger", "permission_description": "View stock movement ledger", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "view_low_stock", "permission_description": "View low-stock alerts", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "view_expiring", "permission_description": "View expiring batches alert", "category": "user"},
        # Procurement
        {"module_name": "pharmacy", "permission_name": "create_purchase", "permission_description": "Create purchase drafts", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "edit_purchase", "permission_description": "Edit purchase drafts", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "confirm_purchase", "permission_description": "Confirm a purchase and commit batches to inventory", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "revoke_purchase", "permission_description": "Revoke a confirmed purchase (proportional reversal of un-sold qty)", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "view_purchases", "permission_description": "View purchases list and detail", "category": "user"},
        # Sales — POS
        {"module_name": "pharmacy", "permission_name": "create_sale", "permission_description": "Create POS counter sales", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "void_sale", "permission_description": "Void / reverse a completed sale", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "void_sale_legacy", "permission_description": "Void sales older than the configured void window", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "view_sales", "permission_description": "View sales list and detail", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "apply_discount", "permission_description": "Apply line or sale-level discounts", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "select_rate_tier", "permission_description": "Choose between Rate-A and Rate-B on a sale line", "category": "user"},
        # Sales — Rx
        {"module_name": "pharmacy", "permission_name": "dispense_rx", "permission_description": "Dispense items against a doctor's prescription", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "view_dispense_queue", "permission_description": "View pending prescriptions awaiting dispensing", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "cancel_rx", "permission_description": "Cancel a prescription (reverses dispensed stock and issues a credit-note when the bill is locked)", "category": "admin"},
        # Reports
        {"module_name": "pharmacy", "permission_name": "view_reports", "permission_description": "Run pharmacy reports (sales, purchases, stock, tax, narcotic)", "category": "user"},
        
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
        
        # Inpatient Module Permissions — granular per-feature keys
        # Core admissions + rooms
        {"module_name": "inpatient", "permission_name": "view_occupancy", "permission_description": "View beds, rooms, dashboard, and admission lists", "category": "user"},
        {"module_name": "inpatient", "permission_name": "admit_patients", "permission_description": "Create admissions", "category": "user"},
        {"module_name": "inpatient", "permission_name": "update_admission", "permission_description": "Update admission details", "category": "user"},
        {"module_name": "inpatient", "permission_name": "discharge_patients", "permission_description": "Create discharge records", "category": "user"},
        {"module_name": "inpatient", "permission_name": "record_mortality", "permission_description": "Record mortality details on death discharges", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_beds", "permission_description": "Create / update / delete rooms and beds", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_wards", "permission_description": "Ward-level configuration", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "set_room_rates", "permission_description": "Set room rates and visit rate config", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "transfer_beds", "permission_description": "Change a patient's room/bed within an admission", "category": "user"},
        {"module_name": "inpatient", "permission_name": "initiate_ward_transfer", "permission_description": "Start a pending inter-ward transfer", "category": "user"},
        {"module_name": "inpatient", "permission_name": "accept_ward_transfer", "permission_description": "Accept or cancel a pending ward transfer", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_housekeeping", "permission_description": "Change bed status (cleaning/dirty/maintenance)", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_reservations", "permission_description": "Bed reservations CRUD + convert", "category": "user"},
        {"module_name": "inpatient", "permission_name": "assign_nurses", "permission_description": "Assign nurses to admissions per shift", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_roster", "permission_description": "Build and edit the nurse shift roster (duty schedule)", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "view_roster", "permission_description": "View the nurse shift roster", "category": "user"},

        # Clinical documentation
        {"module_name": "inpatient", "permission_name": "record_vitals", "permission_description": "Record patient vital signs during stay", "category": "user"},
        {"module_name": "inpatient", "permission_name": "view_vitals", "permission_description": "View patient vital signs", "category": "user"},
        {"module_name": "inpatient", "permission_name": "record_io", "permission_description": "Record intake/output fluid balance entries", "category": "user"},
        {"module_name": "inpatient", "permission_name": "view_io", "permission_description": "View fluid balance charts", "category": "user"},
        {"module_name": "inpatient", "permission_name": "administer_medications", "permission_description": "Administer scheduled and PRN medications, update MAR", "category": "user"},
        {"module_name": "inpatient", "permission_name": "view_mar", "permission_description": "View Medication Administration Record", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_nursing_notes", "permission_description": "Create and edit nursing notes", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_diet_orders", "permission_description": "Create and edit diet orders", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_allergies", "permission_description": "Record and update patient allergies", "category": "user"},
        {"module_name": "inpatient", "permission_name": "record_visits", "permission_description": "Record ward round / nurse visits", "category": "user"},

        # Orders
        {"module_name": "inpatient", "permission_name": "order_labs", "permission_description": "Order lab tests for admitted patients", "category": "user"},
        {"module_name": "inpatient", "permission_name": "prescribe_medications", "permission_description": "Create prescriptions for admitted patients", "category": "user"},

        # OT
        {"module_name": "inpatient", "permission_name": "schedule_ot", "permission_description": "Schedule operating theatre procedures", "category": "user"},
        {"module_name": "inpatient", "permission_name": "record_ot_charges", "permission_description": "Set surgeon / anaesthetist / consumable charges on OT", "category": "admin"},

        # Billing
        {"module_name": "inpatient", "permission_name": "view_bill", "permission_description": "View admission bills and previews", "category": "user"},
        {"module_name": "inpatient", "permission_name": "generate_interim_bill", "permission_description": "Create interim bills during stay", "category": "user"},
        {"module_name": "inpatient", "permission_name": "finalize_bill", "permission_description": "Finalize the admission bill", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_packages", "permission_description": "Apply or remove surgery packages on an admission", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_ancillary_charges", "permission_description": "Add / update / delete ancillary charges on admissions", "category": "user"},
        {"module_name": "inpatient", "permission_name": "receive_deposits", "permission_description": "Record advance deposits", "category": "user"},
        {"module_name": "inpatient", "permission_name": "issue_refunds", "permission_description": "Issue refunds against deposits", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_bill_splits", "permission_description": "Split bill across cash / insurance / TPA payers", "category": "admin"},

        # Insurance
        {"module_name": "inpatient", "permission_name": "update_claim_status", "permission_description": "Advance the admission insurance claim state machine", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_preauth", "permission_description": "Create pre-auth requests, record decisions, request expansions", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_tpa", "permission_description": "Maintain TPA company master", "category": "admin"},

        # Quality & compliance
        {"module_name": "inpatient", "permission_name": "record_consent", "permission_description": "Record signed consents", "category": "user"},
        {"module_name": "inpatient", "permission_name": "withdraw_consent", "permission_description": "Withdraw a previously signed consent", "category": "user"},
        {"module_name": "inpatient", "permission_name": "report_incident", "permission_description": "File incident reports (falls, med errors, etc.)", "category": "user"},
        {"module_name": "inpatient", "permission_name": "investigate_incident", "permission_description": "Run investigations on incidents", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "close_incident", "permission_description": "Close incident investigations", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "view_readmissions", "permission_description": "View 30-day readmission reports", "category": "user"},
        {"module_name": "inpatient", "permission_name": "view_mortality", "permission_description": "View mortality records and death certificates", "category": "user"},
        {"module_name": "inpatient", "permission_name": "acknowledge_critical_alert", "permission_description": "Acknowledge / address critical lab value alerts", "category": "user"},

        # Catalogs
        {"module_name": "inpatient", "permission_name": "manage_ancillary_catalog", "permission_description": "Maintain the ancillary services catalog", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_surgery_packages", "permission_description": "Maintain surgery package catalog", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_consent_templates", "permission_description": "Maintain consent form templates", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "set_critical_thresholds", "permission_description": "Configure critical lab value thresholds", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "view_procedures", "permission_description": "View the procedure catalog", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_procedures", "permission_description": "Add, edit, and remove procedures with default rates", "category": "admin"},

        # Food / Catering
        {"module_name": "inpatient", "permission_name": "view_food_orders", "permission_description": "View scheduled meals for admitted patients", "category": "user"},
        {"module_name": "inpatient", "permission_name": "order_food", "permission_description": "Order, edit, and cancel meals for admitted patients", "category": "user"},
        {"module_name": "inpatient", "permission_name": "mark_food_delivered", "permission_description": "Mark scheduled meals as delivered (kitchen staff)", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_meal_plans", "permission_description": "Set meal prices per room type", "category": "admin"},

        # Documents
        {"module_name": "inpatient", "permission_name": "upload_documents", "permission_description": "Upload admission documents", "category": "user"},
        {"module_name": "inpatient", "permission_name": "view_documents", "permission_description": "Download and list admission documents", "category": "user"},
        {"module_name": "inpatient", "permission_name": "delete_documents", "permission_description": "Delete admission documents", "category": "admin"},
        
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
            "pharmacy": ["view_catalog", "manage_medicines", "manage_companies", "manage_suppliers", "manage_salts", "manage_racks", "manage_uoms", "manage_categories", "manage_hsn_tax", "set_rates", "set_discounts", "manage_scheduled_drugs", "view_narcotic_register", "view_inventory", "adjust_stock", "view_stock_ledger", "view_low_stock", "view_expiring", "create_purchase", "edit_purchase", "confirm_purchase", "view_purchases", "create_sale", "void_sale", "view_sales", "apply_discount", "select_rate_tier", "dispense_rx", "view_dispense_queue", "cancel_rx", "view_reports"],
            "billing": ["manage_rates", "process_payments", "generate_invoices", "view_financial_reports", "manage_insurance", "handle_refunds"],
            "outpatient": ["schedule_appointments", "manage_schedules", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            # Inpatient: everything (also bypassed at decorator level, but seeded for completeness)
            "inpatient": [
                "view_occupancy", "admit_patients", "update_admission", "discharge_patients", "record_mortality",
                "manage_beds", "manage_wards", "set_room_rates",
                "transfer_beds", "initiate_ward_transfer", "accept_ward_transfer",
                "manage_housekeeping", "manage_reservations", "assign_nurses",
                "record_vitals", "view_vitals", "record_io", "view_io",
                "administer_medications", "view_mar",
                "manage_nursing_notes", "manage_diet_orders", "manage_allergies", "record_visits",
                "order_labs", "prescribe_medications",
                "schedule_ot", "record_ot_charges",
                "view_bill", "generate_interim_bill", "finalize_bill",
                "manage_packages", "manage_ancillary_charges",
                "receive_deposits", "issue_refunds", "manage_bill_splits",
                "update_claim_status", "manage_preauth", "manage_tpa",
                "record_consent", "withdraw_consent",
                "report_incident", "investigate_incident", "close_incident",
                "view_readmissions", "view_mortality", "acknowledge_critical_alert",
                "manage_ancillary_catalog", "manage_surgery_packages",
                "manage_consent_templates", "set_critical_thresholds",
                "view_procedures", "manage_procedures",
                "manage_roster", "view_roster",
                "upload_documents", "view_documents", "delete_documents",
                "view_food_orders", "order_food", "mark_food_delivered", "manage_meal_plans",
            ],
            "ehr": ["view_records", "edit_records", "create_prescriptions", "manage_templates", "view_history", "generate_reports", "manage_allergies"]
        },
        # Hospital admin bypasses all inpatient checks at the decorator level,
        # so the seeded list is symbolic. We still populate it so the role admin UI
        # can show a consistent grid.
        "hospital_admin": {
            "admin": ["manage_users", "manage_roles", "view_system_reports", "manage_settings"],
            "lab": ["view_reports", "create_reports"],
            "pharmacy": ["view_catalog", "manage_medicines", "manage_companies", "manage_suppliers", "manage_salts", "manage_racks", "manage_uoms", "manage_categories", "manage_hsn_tax", "set_rates", "set_discounts", "manage_scheduled_drugs", "view_narcotic_register", "view_inventory", "adjust_stock", "view_stock_ledger", "view_low_stock", "view_expiring", "create_purchase", "edit_purchase", "confirm_purchase", "view_purchases", "create_sale", "void_sale", "view_sales", "apply_discount", "select_rate_tier", "dispense_rx", "view_dispense_queue", "cancel_rx", "view_reports"],
            "billing": ["view_financial_reports", "manage_insurance", "process_payments", "generate_invoices"],
            "outpatient": ["schedule_appointments", "manage_schedules", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "inpatient": [
                "view_occupancy", "admit_patients", "update_admission", "discharge_patients", "record_mortality",
                "manage_beds", "manage_wards", "set_room_rates",
                "transfer_beds", "initiate_ward_transfer", "accept_ward_transfer",
                "manage_housekeeping", "manage_reservations", "assign_nurses",
                "record_vitals", "view_vitals", "record_io", "view_io",
                "administer_medications", "view_mar",
                "manage_nursing_notes", "manage_diet_orders", "manage_allergies", "record_visits",
                "order_labs", "prescribe_medications",
                "schedule_ot", "record_ot_charges",
                "view_bill", "generate_interim_bill", "finalize_bill",
                "manage_packages", "manage_ancillary_charges",
                "receive_deposits", "issue_refunds", "manage_bill_splits",
                "update_claim_status", "manage_preauth", "manage_tpa",
                "record_consent", "withdraw_consent",
                "report_incident", "investigate_incident", "close_incident",
                "view_readmissions", "view_mortality", "acknowledge_critical_alert",
                "manage_ancillary_catalog", "manage_surgery_packages",
                "manage_consent_templates", "set_critical_thresholds",
                "view_procedures", "manage_procedures",
                "manage_roster", "view_roster",
                "upload_documents", "view_documents", "delete_documents",
                "view_food_orders", "order_food", "mark_food_delivered", "manage_meal_plans",
            ],
            "ehr": ["view_records", "edit_records", "view_history", "generate_reports"]
        },
        "lab_admin": {
            "lab": ["manage_tests", "set_rates", "view_reports", "create_reports", "manage_equipment", "manage_templates"]
        },
        "pharmacy_admin": {
            "pharmacy": ["view_catalog", "manage_medicines", "manage_companies", "manage_suppliers", "manage_salts", "manage_racks", "manage_uoms", "manage_categories", "manage_hsn_tax", "set_rates", "set_discounts", "manage_scheduled_drugs", "view_narcotic_register", "view_inventory", "adjust_stock", "view_stock_ledger", "view_low_stock", "view_expiring", "create_purchase", "edit_purchase", "confirm_purchase", "view_purchases", "create_sale", "void_sale", "view_sales", "apply_discount", "select_rate_tier", "dispense_rx", "view_dispense_queue", "cancel_rx", "view_reports"],
        },
        "billing_admin": {
            "billing": ["manage_rates", "process_payments", "generate_invoices", "view_financial_reports", "manage_insurance", "handle_refunds"]
        },
        "inpatient_admin": {
            "inpatient": [
                "view_occupancy", "admit_patients", "update_admission", "discharge_patients",
                "manage_beds", "manage_wards", "set_room_rates",
                "transfer_beds", "initiate_ward_transfer", "accept_ward_transfer",
                "manage_housekeeping", "manage_reservations", "assign_nurses",
                "view_bill", "manage_ancillary_charges", "receive_deposits", "record_ot_charges",
                "schedule_ot", "view_procedures",
                "update_claim_status", "manage_preauth",
                "report_incident", "investigate_incident", "close_incident",
                "view_readmissions", "view_mortality",
                "manage_consent_templates", "set_critical_thresholds",
                "manage_roster", "view_roster",
                "upload_documents", "view_documents", "delete_documents",
                "view_food_orders", "order_food", "manage_meal_plans",
            ],
            "ehr": ["manage_allergies", "view_records", "view_history"]
        },
        "billing_admin": {
            "inpatient": [
                "view_occupancy",
                "view_bill", "generate_interim_bill", "finalize_bill",
                "manage_packages", "manage_ancillary_charges",
                "receive_deposits", "issue_refunds", "manage_bill_splits",
                "record_ot_charges",
                "update_claim_status", "manage_preauth",
                "manage_ancillary_catalog", "manage_surgery_packages", "manage_tpa",
                "view_documents",
            ],
            "billing": ["manage_rates", "process_payments", "generate_invoices", "view_financial_reports", "manage_insurance", "handle_refunds"],
        },
        "frontdesk": {
            "outpatient": ["schedule_appointments", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "ehr": ["view_records", "view_history"]
        },
        "doctor": {
            "ehr": ["view_records", "edit_records", "create_prescriptions", "view_history", "generate_reports", "manage_allergies"],
            "lab": ["view_reports", "create_reports"],
            # Doctor: no pharmacy permissions in this build. Pharmacy module
            # is standalone — Rx-to-dispense linkage is a later phase.
            "outpatient": ["view_appointments", "view_patients", "schedule_appointments", "update_appointments", "register_patients", "manage_queues", "cancel_appointments"],
            "inpatient": [
                "view_occupancy",
                "admit_patients", "update_admission", "discharge_patients", "record_mortality",
                "record_vitals", "view_vitals", "record_io", "view_io",
                "administer_medications", "view_mar",
                "manage_nursing_notes", "manage_diet_orders", "manage_allergies", "record_visits",
                "order_labs", "prescribe_medications",
                "schedule_ot", "view_procedures",
                "record_consent", "withdraw_consent",
                "transfer_beds", "initiate_ward_transfer", "accept_ward_transfer",
                "report_incident", "acknowledge_critical_alert",
                "view_bill", "view_readmissions", "view_mortality",
                "view_roster",
                "upload_documents", "view_documents",
                "view_food_orders", "order_food",
            ],
        },
        "nurse": {
            "ehr": ["view_records", "edit_records", "view_history", "manage_allergies"],
            "outpatient": ["manage_queues", "view_appointments"],
            "lab": ["view_reports"],
            "inpatient": [
                "view_occupancy",
                "record_vitals", "view_vitals", "record_io", "view_io",
                "administer_medications", "view_mar",
                "manage_nursing_notes", "manage_diet_orders", "manage_allergies", "record_visits",
                "order_labs", "prescribe_medications",
                "record_consent",
                "report_incident", "acknowledge_critical_alert",
                "view_roster",
                "view_documents",
                "view_food_orders", "order_food", "mark_food_delivered",
            ],
        },
        "lab_technician": {
            "lab": ["view_reports", "create_reports"]
        },
        "pharmacist": {
            "pharmacy": ["view_catalog", "view_inventory", "adjust_stock", "view_stock_ledger", "view_low_stock", "view_expiring", "view_purchases", "create_sale", "view_sales", "apply_discount", "select_rate_tier", "dispense_rx", "view_dispense_queue", "cancel_rx", "view_narcotic_register", "view_reports"],
        },
        "receptionist": {
            "outpatient": ["schedule_appointments", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "billing": ["process_payments", "generate_invoices", "view_financial_reports"],
            "ehr": ["view_records", "view_history"],
            "inpatient": [
                "view_occupancy", "admit_patients", "update_admission",
                "receive_deposits", "manage_reservations",
                "view_bill",
                "upload_documents", "view_documents",
                "view_food_orders", "order_food",
            ],
        },
        "frontdesk": {
            "outpatient": ["schedule_appointments", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "ehr": ["view_records", "view_history"],
            "inpatient": [
                "view_occupancy", "admit_patients", "update_admission",
                "receive_deposits", "manage_reservations",
                "view_bill", "view_documents",
            ],
        },
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