"""Database seeding helpers.

These used to live inside `app.routes.setup` and were called by the React
Setup Wizard. With the Inno Setup installer as the single install path, the
wizard route has been removed; the helpers live here so the Inno Setup seed
applier (`app.services.bootstrap_from_seed`) and the existing column-
migration / restore paths can keep using them.

Public surface:
    init_database_and_seed(seed, db_path) — full first-install seed
    store_license(content, db_path)       — persist a .lic file
    apply_additive_migrations(db_path)    — idempotent column ALTERs
    upsert_modules_and_permissions(db_path) — additive heal on imported DBs

Helpers prefixed with `_` are private to this module.
"""
from __future__ import annotations

import base64
import uuid
from typing import Mapping


# ----------------------------------------------------------------------------
# Canonical role + permission catalog
# ----------------------------------------------------------------------------

SYSTEM_ROLES = [
    ("super_admin", "Super Administrator with full system access"),
    ("hospital_admin", "Hospital Administrator with full hospital access"),
    ("doctor", "Medical Doctor — patient care and medical records access"),
    ("nurse", "Nursing Staff — patient care support"),
    ("lab_admin", "Laboratory Administrator — manages lab operations, rates, templates"),
    ("lab_technician", "Laboratory Technician — performs lab tests and generates reports"),
    ("pharmacy_admin", "Pharmacy Administrator — manages inventory, drug rates, suppliers"),
    ("pharmacist", "Pharmacist — medication dispensing and pharmacy operations"),
    ("satellite_pharmacy_admin", "Satellite pharmacy in-charge — store-scoped admin at ward/satellite counters"),
    ("pharmacy_pos_operator", "Pharmacy POS operator — satellite counter sales only"),
    ("pharmacy_transfer_clerk", "Pharmacy transfer clerk — master store stock movements to satellites"),
    ("billing_admin", "Billing Administrator — manages rates, insurance, financial operations"),
    ("inpatient_admin", "Inpatient Administrator — manages beds, wards, room rates, ward operations"),
    ("canteen_admin", "Canteen Administrator — manages food catalog, prices, and kitchen orders"),
    ("canteen_sales", "Canteen Sales — IP food order queue, kitchen status, and walk-in POS"),
    ("frontdesk", "Front Desk Staff — appointments, patient registration, scheduling"),
    ("receptionist", "Receptionist with patient registration access"),
]


# Full inpatient permission set — super_admin and hospital_admin bypass checks
# at the decorator level, but we seed the grid so the admin UI shows them.
_INPATIENT_ALL = [
    "view_occupancy", "admit_patients", "update_admission", "discharge_patients", "record_mortality",
    "manage_beds", "manage_wards", "set_room_rates",
    "transfer_beds", "initiate_ward_transfer", "accept_ward_transfer",
    "manage_housekeeping", "manage_reservations", "assign_nurses",
    "record_vitals", "view_vitals", "record_io", "view_io",
    "administer_medications", "view_mar",
    "manage_nursing_notes", "manage_allergies", "record_visits",
    "order_labs", "prescribe_medications",
    "schedule_ot", "record_ot_charges",
    "view_bill", "generate_interim_bill", "finalize_bill",
    "manage_packages", "manage_ancillary_charges",
    "receive_deposits", "issue_refunds", "manage_bill_splits",
    "update_claim_status", "manage_preauth", "manage_tpa",
    "record_consent", "withdraw_consent",
    "view_readmissions", "view_mortality", "acknowledge_critical_alert",
    "manage_ancillary_catalog", "manage_surgery_packages",
    "manage_consent_templates", "manage_discharge_summary_template", "set_critical_thresholds",
    "view_procedures", "manage_procedures",
    "manage_roster", "view_roster",
    "upload_documents", "view_documents", "delete_documents",
    # B1/B2/B3/B6 — payer schemes, payer conversion, accept admission, gate pass
    "manage_payer_schemes", "convert_payer", "accept_admission", "issue_gate_pass",
    "write_discharge_summary", "view_discharge_summary",
]


# Canteen permissions — available whenever inpatient is enabled/licensed.
_CANTEEN_ALL = [
    "view_catalog", "manage_catalog",
    "view_orders", "place_order", "manage_order_status",
    "create_sale", "view_sales", "void_sale",
]
# Canteen admin: catalog + kitchen + POS (clinical staff place IP ward orders).
_CANTEEN_ADMIN_DEFAULT = [
    "view_catalog", "manage_catalog",
    "view_orders", "manage_order_status",
    "create_sale", "view_sales", "void_sale",
]
_CANTEEN_SALES_DEFAULT = [
    "view_catalog", "view_orders", "manage_order_status",
    "create_sale", "view_sales", "void_sale",
]
_CANTEEN_CLINICAL_ORDER = [
    "view_catalog", "view_orders", "place_order",
]

# Full pharmacy permission set — kept in sync with the pharmacy permission catalog
# above. Used to seed full access for super_admin / hospital_admin / pharmacy_admin.
_PHARMACY_ALL = [
    # Catalog
    "view_catalog", "manage_medicines", "manage_companies", "manage_suppliers",
    "manage_salts", "manage_racks", "manage_uoms", "manage_categories", "manage_hsn_tax",
    # Pricing
    "set_rates", "set_discounts",
    # Regulatory
    "manage_scheduled_drugs", "view_narcotic_register",
    # Inventory
    "view_inventory", "adjust_stock", "view_stock_ledger", "view_low_stock", "view_expiring",
    # Procurement
    "create_purchase", "edit_purchase", "confirm_purchase", "revoke_purchase", "view_purchases",
    # Sales — POS
    "create_sale", "edit_sale", "void_sale", "void_sale_legacy", "view_sales", "apply_discount", "select_rate_tier",
    # Sales — Rx
    "dispense_rx", "view_dispense_queue", "cancel_rx",
    # Reports
    "view_reports",
    # Multi-store
    "manage_stores", "view_all_stores",
    "create_transfer", "edit_transfer", "confirm_transfer", "revoke_transfer", "view_transfers",
]

# Pharmacist (counter operator) default permission set.
_PHARMACIST_DEFAULT = [
    "view_catalog",
    "view_inventory", "adjust_stock", "view_stock_ledger", "view_low_stock", "view_expiring",
    "view_purchases",
    "create_sale", "view_sales", "apply_discount", "select_rate_tier",
    "dispense_rx", "view_dispense_queue",
    "view_narcotic_register", "view_reports",
]

# Satellite POS counter — minimal billing permissions.
_PHARMACY_POS_OPERATOR = [
    "view_catalog",
    "create_sale", "view_sales", "apply_discount", "select_rate_tier",
    "dispense_rx", "view_dispense_queue",
]

# Satellite store in-charge — POS plus local inventory/reports.
_SATELLITE_PHARMACY_ADMIN = [
    "view_catalog",
    "create_sale", "view_sales", "apply_discount", "select_rate_tier", "edit_sale", "void_sale",
    "dispense_rx", "view_dispense_queue",
    "view_inventory", "view_low_stock", "view_expiring", "view_reports",
    "view_narcotic_register", "confirm_transfer",
]

# Master back-office — inter-store transfers.
_PHARMACY_TRANSFER_CLERK = [
    "view_catalog", "view_inventory",
    "view_transfers", "create_transfer", "edit_transfer", "confirm_transfer",
]


def _seed_roles(db, UserRole):
    for name, desc in SYSTEM_ROLES:
        existing = db.query(UserRole).filter(UserRole.name == name).first()
        if not existing:
            db.add(UserRole(name=name, description=desc, is_system_role=True))
        else:
            if not getattr(existing, "is_system_role", False):
                existing.is_system_role = True
            if not existing.description:
                existing.description = desc


def _seed_module_permissions(db, ModulePermission):
    permissions_data = [
        # Lab
        {"module_name": "lab", "permission_name": "manage_tests", "permission_description": "Create and manage lab test types", "category": "admin"},
        {"module_name": "lab", "permission_name": "set_rates", "permission_description": "Set pricing for lab tests", "category": "admin"},
        {"module_name": "lab", "permission_name": "view_reports", "permission_description": "View lab reports", "category": "user"},
        {"module_name": "lab", "permission_name": "create_reports", "permission_description": "Create lab reports", "category": "user"},
        {"module_name": "lab", "permission_name": "manage_equipment", "permission_description": "Manage lab equipment", "category": "admin"},
        {"module_name": "lab", "permission_name": "manage_templates", "permission_description": "Create and edit report templates", "category": "admin"},
        # Pharmacy — granular per-feature keys (mirror inpatient style)
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
        {"module_name": "pharmacy", "permission_name": "edit_purchase", "permission_description": "Edit purchase drafts and confirmed purchases (with reason)", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "confirm_purchase", "permission_description": "Confirm a purchase and commit batches to inventory", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "revoke_purchase", "permission_description": "Revoke a confirmed purchase (proportional reversal of un-sold qty)", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "view_purchases", "permission_description": "View purchases list and detail", "category": "user"},
        # Sales — POS
        {"module_name": "pharmacy", "permission_name": "create_sale", "permission_description": "Create POS counter sales", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "edit_sale", "permission_description": "Edit a completed POS sale (with reason)", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "void_sale", "permission_description": "Void / reverse a completed sale", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "void_sale_legacy", "permission_description": "Void sales older than the configured void window", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "view_sales", "permission_description": "View sales list and detail", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "apply_discount", "permission_description": "Apply line or sale-level discounts", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "select_rate_tier", "permission_description": "Choose between Rate-A and Rate-B on a sale line", "category": "user"},
        # Sales — Rx
        {"module_name": "pharmacy", "permission_name": "dispense_rx", "permission_description": "Dispense items against a doctor's prescription", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "view_dispense_queue", "permission_description": "View pending prescriptions awaiting dispensing", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "cancel_rx", "permission_description": "Cancel a prescription (reverses dispensed stock and issues credit-note when bill is locked)", "category": "admin"},
        # Reports
        {"module_name": "pharmacy", "permission_name": "view_reports", "permission_description": "Run pharmacy reports (sales, purchases, stock, tax, narcotic)", "category": "user"},
        # Multi-store
        {"module_name": "pharmacy", "permission_name": "manage_stores", "permission_description": "Create and manage pharmacy stores and user assignments", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "view_all_stores", "permission_description": "View consolidated data across all pharmacy stores", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "create_transfer", "permission_description": "Create inter-store stock transfer drafts", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "edit_transfer", "permission_description": "Edit inter-store stock transfer drafts", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "confirm_transfer", "permission_description": "Confirm inter-store stock transfers", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "revoke_transfer", "permission_description": "Revoke confirmed inter-store transfers", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "view_transfers", "permission_description": "View inter-store transfer list and detail", "category": "user"},
        # Billing
        {"module_name": "billing", "permission_name": "manage_rates", "permission_description": "Manage service rates and pricing", "category": "admin"},
        {"module_name": "billing", "permission_name": "process_payments", "permission_description": "Process patient payments", "category": "user"},
        {"module_name": "billing", "permission_name": "generate_invoices", "permission_description": "Generate patient invoices", "category": "user"},
        {"module_name": "billing", "permission_name": "view_financial_reports", "permission_description": "View financial reports", "category": "admin"},
        {"module_name": "billing", "permission_name": "manage_insurance", "permission_description": "Manage insurance claims", "category": "admin"},
        {"module_name": "billing", "permission_name": "handle_refunds", "permission_description": "Process refunds", "category": "admin"},
        {"module_name": "billing", "permission_name": "catch_up_bills", "permission_description": "Enter omitted / backdated bills via admin catch-up", "category": "admin"},
        # Outpatient
        {"module_name": "outpatient", "permission_name": "schedule_appointments", "permission_description": "Schedule patient appointments", "category": "user"},
        {"module_name": "outpatient", "permission_name": "manage_schedules", "permission_description": "Manage doctor schedules", "category": "admin"},
        {"module_name": "outpatient", "permission_name": "register_patients", "permission_description": "Register new patients", "category": "user"},
        {"module_name": "outpatient", "permission_name": "manage_queues", "permission_description": "Manage patient queues", "category": "user"},
        {"module_name": "outpatient", "permission_name": "view_appointments", "permission_description": "View appointment details", "category": "user"},
        {"module_name": "outpatient", "permission_name": "cancel_appointments", "permission_description": "Cancel appointments", "category": "user"},
        # Inpatient
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
        {"module_name": "inpatient", "permission_name": "manage_roster", "permission_description": "Build and edit the nurse shift roster", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "view_roster", "permission_description": "View the nurse shift roster", "category": "user"},
        {"module_name": "inpatient", "permission_name": "record_vitals", "permission_description": "Record patient vital signs during stay", "category": "user"},
        {"module_name": "inpatient", "permission_name": "view_vitals", "permission_description": "View patient vital signs", "category": "user"},
        {"module_name": "inpatient", "permission_name": "record_io", "permission_description": "Record intake/output fluid balance entries", "category": "user"},
        {"module_name": "inpatient", "permission_name": "view_io", "permission_description": "View fluid balance charts", "category": "user"},
        {"module_name": "inpatient", "permission_name": "administer_medications", "permission_description": "Administer scheduled and PRN medications, update MAR", "category": "user"},
        {"module_name": "inpatient", "permission_name": "view_mar", "permission_description": "View Medication Administration Record", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_nursing_notes", "permission_description": "Create and edit nursing notes", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_allergies", "permission_description": "Record and update patient allergies", "category": "user"},
        {"module_name": "inpatient", "permission_name": "record_visits", "permission_description": "Record ward round / nurse visits", "category": "user"},
        {"module_name": "inpatient", "permission_name": "order_labs", "permission_description": "Order lab tests for admitted patients", "category": "user"},
        {"module_name": "inpatient", "permission_name": "prescribe_medications", "permission_description": "Create prescriptions for admitted patients", "category": "user"},
        {"module_name": "inpatient", "permission_name": "schedule_ot", "permission_description": "Schedule operating theatre procedures", "category": "user"},
        {"module_name": "inpatient", "permission_name": "record_ot_charges", "permission_description": "Set surgeon / anaesthetist / consumable charges on OT", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "view_bill", "permission_description": "View admission bills and previews", "category": "user"},
        {"module_name": "inpatient", "permission_name": "generate_interim_bill", "permission_description": "Create interim bills during stay", "category": "user"},
        {"module_name": "inpatient", "permission_name": "finalize_bill", "permission_description": "Finalize the admission bill", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_packages", "permission_description": "Apply or remove surgery packages on an admission", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_ancillary_charges", "permission_description": "Add / update / delete ancillary charges on admissions", "category": "user"},
        {"module_name": "inpatient", "permission_name": "receive_deposits", "permission_description": "Record advance deposits", "category": "user"},
        {"module_name": "inpatient", "permission_name": "issue_refunds", "permission_description": "Issue refunds against deposits", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_bill_splits", "permission_description": "Split bill across cash / insurance / TPA payers", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "update_claim_status", "permission_description": "Advance the admission insurance claim state machine", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_preauth", "permission_description": "Create pre-auth requests, record decisions, request expansions", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_tpa", "permission_description": "Maintain TPA company master", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "record_consent", "permission_description": "Record signed consents", "category": "user"},
        {"module_name": "inpatient", "permission_name": "withdraw_consent", "permission_description": "Withdraw a previously signed consent", "category": "user"},
        {"module_name": "inpatient", "permission_name": "view_readmissions", "permission_description": "View 30-day readmission reports", "category": "user"},
        {"module_name": "inpatient", "permission_name": "view_mortality", "permission_description": "View mortality records and death certificates", "category": "user"},
        {"module_name": "inpatient", "permission_name": "acknowledge_critical_alert", "permission_description": "Acknowledge / address critical lab value alerts", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_ancillary_catalog", "permission_description": "Maintain the ancillary services catalog", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_surgery_packages", "permission_description": "Maintain surgery package catalog", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_consent_templates", "permission_description": "Maintain consent form templates", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_discharge_summary_template", "permission_description": "Customize the hospital-wide discharge summary layout", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "set_critical_thresholds", "permission_description": "Configure critical lab value thresholds", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "view_procedures", "permission_description": "View the procedure catalog", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_procedures", "permission_description": "Add, edit, and remove procedures with default rates", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "upload_documents", "permission_description": "Upload admission documents", "category": "user"},
        {"module_name": "inpatient", "permission_name": "view_documents", "permission_description": "Download and list admission documents", "category": "user"},
        {"module_name": "inpatient", "permission_name": "delete_documents", "permission_description": "Delete admission documents", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_payer_schemes", "permission_description": "Maintain the payer scheme catalog (Cash / govt schemes / private insurance / TPA)", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "convert_payer", "permission_description": "Change an admission's payer mode mid-stay (e.g., insurance disconnected → cash)", "category": "user"},
        {"module_name": "inpatient", "permission_name": "accept_admission", "permission_description": "Accept or reject an admission as the IP floor doctor", "category": "user"},
        {"module_name": "inpatient", "permission_name": "issue_gate_pass", "permission_description": "Issue a gate pass after discharge for security at exit", "category": "user"},
        {"module_name": "inpatient", "permission_name": "write_discharge_summary", "permission_description": "Author and finalize the clinical discharge summary", "category": "user"},
        {"module_name": "inpatient", "permission_name": "view_discharge_summary", "permission_description": "View and print the discharge summary document", "category": "user"},
        # Canteen (gated by inpatient module enablement / license)
        {"module_name": "canteen", "permission_name": "view_catalog", "permission_description": "View the canteen food catalog", "category": "user"},
        {"module_name": "canteen", "permission_name": "manage_catalog", "permission_description": "Create and edit canteen categories, items, and prices", "category": "admin"},
        {"module_name": "canteen", "permission_name": "view_orders", "permission_description": "View canteen orders for admitted patients", "category": "user"},
        {"module_name": "canteen", "permission_name": "place_order", "permission_description": "Place and cancel canteen orders for admitted patients", "category": "user"},
        {"module_name": "canteen", "permission_name": "manage_order_status", "permission_description": "Update kitchen order status (preparing / ready / delivered)", "category": "user"},
        {"module_name": "canteen", "permission_name": "create_sale", "permission_description": "Create walk-in / cash canteen POS sales", "category": "user"},
        {"module_name": "canteen", "permission_name": "view_sales", "permission_description": "View canteen POS sales history", "category": "user"},
        {"module_name": "canteen", "permission_name": "void_sale", "permission_description": "Void a completed canteen POS sale", "category": "admin"},
        # EHR
        {"module_name": "ehr", "permission_name": "view_records", "permission_description": "View patient electronic health records", "category": "user"},
        {"module_name": "ehr", "permission_name": "edit_records", "permission_description": "Edit patient records", "category": "user"},
        {"module_name": "ehr", "permission_name": "create_prescriptions", "permission_description": "Create prescriptions", "category": "user"},
        {"module_name": "ehr", "permission_name": "manage_templates", "permission_description": "Manage EHR templates", "category": "admin"},
        {"module_name": "ehr", "permission_name": "view_history", "permission_description": "View patient medical history", "category": "user"},
        {"module_name": "ehr", "permission_name": "generate_reports", "permission_description": "Generate medical reports", "category": "user"},
        # Admin
        {"module_name": "admin", "permission_name": "manage_users", "permission_description": "Create and manage users", "category": "admin"},
        {"module_name": "admin", "permission_name": "manage_roles", "permission_description": "Create and manage roles", "category": "admin"},
        {"module_name": "admin", "permission_name": "manage_modules", "permission_description": "Enable/disable modules", "category": "admin"},
        {"module_name": "admin", "permission_name": "view_system_reports", "permission_description": "View system reports", "category": "admin"},
        {"module_name": "admin", "permission_name": "manage_settings", "permission_description": "Manage system settings", "category": "admin"},
    ]
    for perm in permissions_data:
        existing = db.query(ModulePermission).filter(
            ModulePermission.module_name == perm["module_name"],
            ModulePermission.permission_name == perm["permission_name"],
        ).first()
        if not existing:
            db.add(ModulePermission(**perm))


def _seed_role_permissions(db, UserRole, RoleModulePermission):
    role_permissions_map = {
        "super_admin": {
            "admin": ["manage_users", "manage_roles", "manage_modules", "view_system_reports", "manage_settings"],
            "lab": ["manage_tests", "set_rates", "view_reports", "create_reports", "manage_equipment", "manage_templates"],
            "pharmacy": list(_PHARMACY_ALL),
            "billing": ["manage_rates", "process_payments", "generate_invoices", "view_financial_reports", "manage_insurance", "handle_refunds", "catch_up_bills"],
            "outpatient": ["schedule_appointments", "manage_schedules", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "inpatient": list(_INPATIENT_ALL),
            "canteen": list(_CANTEEN_ALL),
            "ehr": ["view_records", "edit_records", "create_prescriptions", "manage_templates", "view_history", "generate_reports"],
        },
        "hospital_admin": {
            "admin": ["manage_users", "manage_roles", "view_system_reports", "manage_settings"],
            "lab": ["view_reports", "create_reports"],
            "pharmacy": list(_PHARMACY_ALL),
            "billing": ["view_financial_reports", "manage_insurance", "process_payments", "generate_invoices", "catch_up_bills"],
            "outpatient": ["schedule_appointments", "manage_schedules", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "inpatient": list(_INPATIENT_ALL),
            "canteen": list(_CANTEEN_ALL),
            "ehr": ["view_records", "edit_records", "view_history", "generate_reports"],
        },
        "doctor": {
            "ehr": ["view_records", "edit_records", "create_prescriptions", "view_history", "generate_reports"],
            "lab": ["view_reports", "create_reports"],
            # No pharmacy permissions for doctor — pharmacy module is standalone in
            # this build. Cross-module Rx → dispense linkage is a later phase.
            "outpatient": ["view_appointments", "view_patients", "schedule_appointments", "update_appointments", "register_patients", "manage_queues", "cancel_appointments"],
            "inpatient": [
                "view_occupancy",
                "admit_patients", "update_admission", "discharge_patients", "record_mortality",
                "record_vitals", "view_vitals", "record_io", "view_io",
                "administer_medications", "view_mar",
                "manage_nursing_notes", "manage_allergies", "record_visits",
                "order_labs", "prescribe_medications",
                "schedule_ot", "view_procedures",
                "record_consent", "withdraw_consent",
                "transfer_beds", "initiate_ward_transfer", "accept_ward_transfer",
                "acknowledge_critical_alert",
                "view_bill", "view_readmissions", "view_mortality",
                "view_roster",
                "upload_documents", "view_documents",
                "accept_admission",
                "write_discharge_summary", "view_discharge_summary",
            ],
            "canteen": list(_CANTEEN_CLINICAL_ORDER),
        },
        "nurse": {
            "ehr": ["view_records", "edit_records", "view_history", "manage_allergies"],
            "outpatient": ["manage_queues", "view_appointments"],
            "lab": ["view_reports"],
            "inpatient": [
                "view_occupancy",
                "record_vitals", "view_vitals", "record_io", "view_io",
                "administer_medications", "view_mar",
                "manage_nursing_notes", "manage_allergies", "record_visits",
                "order_labs", "prescribe_medications",
                "record_consent",
                "accept_ward_transfer", "manage_housekeeping",
                "acknowledge_critical_alert",
                "view_roster",
                "view_documents",
            ],
            "canteen": list(_CANTEEN_CLINICAL_ORDER),
        },
        "inpatient_admin": {
            "ehr": ["view_records", "view_history", "manage_allergies"],
            "inpatient": [
                "view_occupancy", "admit_patients", "update_admission", "discharge_patients",
                "record_vitals", "view_vitals",
                "manage_beds", "manage_wards", "set_room_rates",
                "transfer_beds", "initiate_ward_transfer", "accept_ward_transfer",
                "manage_housekeeping", "manage_reservations", "assign_nurses",
                "view_bill", "manage_ancillary_charges", "receive_deposits", "record_ot_charges",
                "schedule_ot", "view_procedures",
                "update_claim_status", "manage_preauth",
                "view_readmissions", "view_mortality",
                "manage_consent_templates", "manage_discharge_summary_template", "set_critical_thresholds",
                "manage_roster", "view_roster",
                "upload_documents", "view_documents", "delete_documents",
                "accept_admission", "convert_payer", "manage_payer_schemes",
                "write_discharge_summary", "view_discharge_summary",
            ],
            "canteen": list(_CANTEEN_CLINICAL_ORDER),
        },
        "billing_admin": {
            "billing": ["manage_rates", "process_payments", "generate_invoices", "view_financial_reports", "manage_insurance", "handle_refunds"],
            "inpatient": [
                "view_occupancy",
                "view_bill", "generate_interim_bill", "finalize_bill",
                "manage_packages", "manage_ancillary_charges",
                "receive_deposits", "issue_refunds", "manage_bill_splits",
                "record_ot_charges",
                "update_claim_status", "manage_preauth",
                "manage_ancillary_catalog", "manage_surgery_packages", "manage_tpa",
                "view_documents",
                "manage_payer_schemes", "convert_payer", "issue_gate_pass",
                "view_discharge_summary",
            ],
        },
        "receptionist": {
            "outpatient": ["schedule_appointments", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "billing": ["process_payments", "generate_invoices", "view_financial_reports"],
            "ehr": ["view_records", "view_history"],
            "inpatient": [
                "view_occupancy", "admit_patients", "update_admission", "discharge_patients",
                "record_vitals", "view_vitals",
                "receive_deposits", "manage_reservations",
                # Bill collection — receptionist needs to view, adjust, finalize,
                # and download the bill so they can settle it with the patient
                # before issuing the gate pass.
                "view_bill", "generate_interim_bill", "finalize_bill",
                "manage_ancillary_charges", "manage_bill_splits", "issue_refunds",
                "upload_documents", "view_documents",
                "issue_gate_pass",
                "view_discharge_summary",
                "view_roster",
                "view_mortality",
                "manage_beds", "manage_wards", "set_room_rates",
                "manage_ancillary_catalog", "manage_surgery_packages", "manage_tpa",
                "manage_consent_templates",
            ],
            "canteen": list(_CANTEEN_CLINICAL_ORDER),
        },
        "frontdesk": {
            "outpatient": ["schedule_appointments", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "ehr": ["view_records", "view_history"],
            "inpatient": [
                "view_occupancy", "admit_patients", "update_admission", "discharge_patients",
                "record_vitals", "view_vitals",
                "receive_deposits", "manage_reservations",
                "view_bill", "generate_interim_bill", "finalize_bill",
                "manage_ancillary_charges", "issue_refunds",
                "view_documents",
                "issue_gate_pass",
                "view_discharge_summary",
                "view_roster",
                "view_mortality",
                "manage_beds", "manage_wards", "set_room_rates",
                "manage_ancillary_catalog", "manage_surgery_packages", "manage_tpa",
                "manage_consent_templates",
            ],
        },
        "lab_admin": {
            "lab": ["manage_tests", "set_rates", "view_reports", "create_reports", "manage_equipment", "manage_templates"],
        },
        "lab_technician": {
            "lab": ["view_reports", "create_reports"],
        },
        "pharmacy_admin": {
            "pharmacy": list(_PHARMACY_ALL),
        },
        "pharmacist": {
            "pharmacy": list(_PHARMACIST_DEFAULT),
        },
        "pharmacy_pos_operator": {
            "pharmacy": list(_PHARMACY_POS_OPERATOR),
        },
        "satellite_pharmacy_admin": {
            "pharmacy": list(_SATELLITE_PHARMACY_ADMIN),
        },
        "pharmacy_transfer_clerk": {
            "pharmacy": list(_PHARMACY_TRANSFER_CLERK),
        },
        "canteen_admin": {
            "canteen": list(_CANTEEN_ADMIN_DEFAULT),
        },
        "canteen_sales": {
            "canteen": list(_CANTEEN_SALES_DEFAULT),
        },
    }

    for role_name, module_perms in role_permissions_map.items():
        role = db.query(UserRole).filter(UserRole.name == role_name).first()
        if not role:
            continue
        for module_name, permissions in module_perms.items():
            existing = db.query(RoleModulePermission).filter(
                RoleModulePermission.role_id == role.id,
                RoleModulePermission.module_name == module_name,
            ).first()
            if existing:
                existing.permissions = permissions
            else:
                db.add(RoleModulePermission(
                    role_id=role.id,
                    module_name=module_name,
                    permissions=permissions,
                ))

    _heal_legacy_pharmacy_perms(db)


def _heal_legacy_pharmacy_perms(db):
    """Remove stale pharmacy permission keys that pre-date the granular vocabulary.

    Pharmacy permissions were originally 6 coarse action-bucket keys
    (`manage_inventory`, `set_drug_rates`, `dispense_medications`,
    `view_prescriptions`, `manage_suppliers`, `generate_reports`). Section A of
    the pharmacy module build replaced these with a 30-key granular catalog.
    This healer:
      1. Deletes ModulePermission rows for legacy keys not in `_PHARMACY_ALL`.
      2. Strips legacy keys out of any existing RoleModulePermission.permissions
         lists so old role grants don't carry forward unknown perms.

    Idempotent; safe to run on every startup.
    """
    from app.models.permissions import ModulePermission, RoleModulePermission

    valid = set(_PHARMACY_ALL)
    # 1. Drop stale catalog rows
    stale_catalog = db.query(ModulePermission).filter(
        ModulePermission.module_name == "pharmacy",
        ~ModulePermission.permission_name.in_(valid),
    ).all()
    for row in stale_catalog:
        db.delete(row)

    # 2. Strip stale entries from role grants
    grants = db.query(RoleModulePermission).filter(
        RoleModulePermission.module_name == "pharmacy",
    ).all()
    for g in grants:
        if not g.permissions:
            continue
        cleaned = [p for p in g.permissions if p in valid]
        if cleaned != list(g.permissions):
            g.permissions = cleaned


# ----------------------------------------------------------------------------
# Public seeding entry points
# ----------------------------------------------------------------------------

def apply_additive_migrations(db_path: str) -> None:
    """Run NEW_COLUMNS additive migrations against the given DB path."""
    from sqlalchemy import create_engine, text
    try:
        from migrate_patient_fields import NEW_COLUMNS
    except Exception:
        return
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    try:
        with engine.connect() as conn:
            for table, col, col_type in NEW_COLUMNS:
                try:
                    result = conn.execute(text(f"PRAGMA table_info({table})"))
                    existing = {row[1] for row in result.fetchall()}
                    if col not in existing:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                except Exception:
                    continue
            conn.commit()
    finally:
        engine.dispose()


def upsert_modules_and_permissions(db_path: str) -> None:
    """Idempotently upsert the module-permission catalog and system modules
    on an imported DB so a restored install matches what this app build
    expects. Does not touch hospital or user rows."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from config.database import Base
    from app.models.permissions import ModulePermission, RoleModulePermission  # noqa
    from app.models.user import UserRole  # noqa
    from app.models.system import SystemModule  # noqa
    from app.utils.schema_version import stamp_schema_version

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        _seed_roles(db, UserRole)
        db.flush()
        _seed_module_permissions(db, ModulePermission)
        db.flush()
        canonical = [
            ("outpatient", "Outpatient", True, False),
            ("inpatient", "Inpatient", False, False),
            ("lab", "Laboratory", False, False),
            ("pharmacy", "Pharmacy", False, False),
            ("ehr", "Electronic Health Records", True, False),
            ("billing", "Billing", True, True),
            ("admin", "Administration", True, True),
        ]
        for mod_name, display, enabled, always in canonical:
            if not db.query(SystemModule).filter(SystemModule.module_name == mod_name).first():
                db.add(SystemModule(
                    module_name=mod_name, display_name=display,
                    description=f"{display} management",
                    is_enabled=enabled, is_always_enabled=always,
                ))
        db.flush()
        stamp_schema_version(db)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        engine.dispose()


def init_database_and_seed(seed: Mapping, db_path: str) -> None:
    """Initialize DB at the given path and seed it with roles, hospital,
    admin user, system modules, schema_version. Idempotent: re-running on
    a populated DB is a no-op for already-present rows.

    Required keys in `seed`:
        hospital_name, admin_username, admin_email, admin_password
    Optional keys:
        hospital_address, hospital_phone, hospital_email, mrn_prefix,
        admin_first_name, admin_last_name
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from config.database import Base

    # Import ALL models so Base.metadata knows about them
    from app.models.user import User, UserRole, UserPermission  # noqa
    from app.models.permissions import ModulePermission, RoleModulePermission, HospitalSettings, ModuleTemplate, ModuleRates  # noqa
    from app.models.system import SystemModule, SystemSettings  # noqa
    from app.models.hospital import Hospital, HospitalModule  # noqa
    from app.models.prescriptions_simple import SimplePrescription  # noqa
    from app.models.doctor_availability import DoctorAvailability, DoctorSpecialSchedule, DoctorAvailabilityStatus  # noqa
    from app.models.license import License  # noqa
    from app.models.lab import LabTestCategory, LabTest, LabTestParameter, LabReport, PatientLabOrder  # noqa
    from app.models.lab import LabTestPackageCategory, LabTestPackage  # noqa
    from app.models.billing import PaymentMethod, Bill, BillItem, Payment  # noqa
    from app.models.ehr import Consultation  # noqa
    from app.models.outpatient import Appointment  # noqa
    from app.models.patient import Patient  # noqa
    from app.models.referral import Referral  # noqa
    from app.models.canteen import CanteenCategory, CanteenItem, CanteenOrder, CanteenOrderItem, CanteenSale, CanteenSaleItem  # noqa
    from app.models.settlement import Settlement, SettlementConfig  # noqa

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    apply_additive_migrations(db_path)

    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        _seed_roles(db, UserRole)
        db.flush()

        _seed_module_permissions(db, ModulePermission)
        db.flush()

        modules = [
            ("outpatient", "Outpatient", True, False),
            ("inpatient", "Inpatient", False, False),
            ("lab", "Laboratory", False, False),
            ("pharmacy", "Pharmacy", False, False),
            ("ehr", "Electronic Health Records", True, False),
            ("billing", "Billing", True, True),
            ("admin", "Administration", True, True),
        ]
        for mod_name, display, enabled, always in modules:
            if not db.query(SystemModule).filter(SystemModule.module_name == mod_name).first():
                db.add(SystemModule(
                    module_name=mod_name,
                    display_name=display,
                    description=f"{display} management",
                    is_enabled=enabled,
                    is_always_enabled=always,
                ))
        db.flush()

        from app.services.super_admin_service import generate_hospital_code
        hospital = db.query(Hospital).first()
        if not hospital:
            hospital = Hospital(
                hospital_id=generate_hospital_code(),
                name=seed.get("hospital_name", ""),
                address=seed.get("hospital_address", "") or "",
                phone=seed.get("hospital_phone", "") or "",
                email=seed.get("hospital_email", "") or "",
                mrn_prefix=(seed.get("mrn_prefix") or "KTH"),
                license_number="SETUP001",
                is_active=True,
            )
            db.add(hospital)
            db.flush()

        from app.utils.auth import get_password_hash
        admin_role = db.query(UserRole).filter(UserRole.name == "super_admin").first()
        admin_username = seed.get("admin_username", "")
        admin_email = seed.get("admin_email", "")
        existing_by_name = db.query(User).filter(User.username == admin_username).first() if admin_username else None
        existing_by_email = db.query(User).filter(User.email == admin_email).first() if admin_email else None
        if admin_username and admin_email and not existing_by_name and not existing_by_email:
            admin = User(
                user_id=str(uuid.uuid4()),
                username=admin_username,
                email=admin_email,
                password_hash=get_password_hash(seed["admin_password"]),
                first_name=seed.get("admin_first_name") or "System",
                last_name=seed.get("admin_last_name") or "Administrator",
                role_id=admin_role.id,
                hospital_id=hospital.id,
                is_active=True,
            )
            db.add(admin)
            db.flush()

        with db.no_autoflush:
            _seed_role_permissions(db, UserRole, RoleModulePermission)

        from app.utils.schema_version import stamp_schema_version
        stamp_schema_version(db)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        engine.dispose()


def store_license(license_content: str, db_path: str) -> dict:
    """Parse, verify, and persist a .lic file. Returns
    `{"stored": True, "license": ...}` on success or
    `{"stored": False, "error": "..."}` on failure.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.services.license_service import upload_license

    # Accept either raw .lic content or base64-encoded.
    try:
        content = base64.b64decode(license_content).decode("utf-8")
        if "\n" not in content:
            content = license_content
    except Exception:
        content = license_content

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        result = upload_license(db, content, uploaded_by=None)
        return {"stored": True, "license": result}
    except Exception as e:
        return {"stored": False, "error": str(e)}
    finally:
        db.close()
        engine.dispose()
