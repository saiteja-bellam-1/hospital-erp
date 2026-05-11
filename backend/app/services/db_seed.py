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
    ("billing_admin", "Billing Administrator — manages rates, insurance, financial operations"),
    ("inpatient_admin", "Inpatient Administrator — manages beds, wards, room rates, ward operations"),
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
        # Pharmacy
        {"module_name": "pharmacy", "permission_name": "manage_inventory", "permission_description": "Manage medication inventory", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "set_drug_rates", "permission_description": "Set medication pricing", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "dispense_medications", "permission_description": "Dispense medications", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "view_prescriptions", "permission_description": "View patient prescriptions", "category": "user"},
        {"module_name": "pharmacy", "permission_name": "manage_suppliers", "permission_description": "Manage drug suppliers", "category": "admin"},
        {"module_name": "pharmacy", "permission_name": "generate_reports", "permission_description": "Generate pharmacy reports", "category": "admin"},
        # Billing
        {"module_name": "billing", "permission_name": "manage_rates", "permission_description": "Manage service rates and pricing", "category": "admin"},
        {"module_name": "billing", "permission_name": "process_payments", "permission_description": "Process patient payments", "category": "user"},
        {"module_name": "billing", "permission_name": "generate_invoices", "permission_description": "Generate patient invoices", "category": "user"},
        {"module_name": "billing", "permission_name": "view_financial_reports", "permission_description": "View financial reports", "category": "admin"},
        {"module_name": "billing", "permission_name": "manage_insurance", "permission_description": "Manage insurance claims", "category": "admin"},
        {"module_name": "billing", "permission_name": "handle_refunds", "permission_description": "Process refunds", "category": "admin"},
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
        {"module_name": "inpatient", "permission_name": "manage_diet_orders", "permission_description": "Create and edit diet orders", "category": "user"},
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
        {"module_name": "inpatient", "permission_name": "report_incident", "permission_description": "File incident reports (falls, med errors, etc.)", "category": "user"},
        {"module_name": "inpatient", "permission_name": "investigate_incident", "permission_description": "Run investigations on incidents", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "close_incident", "permission_description": "Close incident investigations", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "view_readmissions", "permission_description": "View 30-day readmission reports", "category": "user"},
        {"module_name": "inpatient", "permission_name": "view_mortality", "permission_description": "View mortality records and death certificates", "category": "user"},
        {"module_name": "inpatient", "permission_name": "acknowledge_critical_alert", "permission_description": "Acknowledge / address critical lab value alerts", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_ancillary_catalog", "permission_description": "Maintain the ancillary services catalog", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_surgery_packages", "permission_description": "Maintain surgery package catalog", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "manage_consent_templates", "permission_description": "Maintain consent form templates", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "set_critical_thresholds", "permission_description": "Configure critical lab value thresholds", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "view_procedures", "permission_description": "View the procedure catalog", "category": "user"},
        {"module_name": "inpatient", "permission_name": "manage_procedures", "permission_description": "Add, edit, and remove procedures with default rates", "category": "admin"},
        {"module_name": "inpatient", "permission_name": "upload_documents", "permission_description": "Upload admission documents", "category": "user"},
        {"module_name": "inpatient", "permission_name": "view_documents", "permission_description": "Download and list admission documents", "category": "user"},
        {"module_name": "inpatient", "permission_name": "delete_documents", "permission_description": "Delete admission documents", "category": "admin"},
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
            "pharmacy": ["manage_inventory", "set_drug_rates", "dispense_medications", "view_prescriptions", "manage_suppliers", "generate_reports"],
            "billing": ["manage_rates", "process_payments", "generate_invoices", "view_financial_reports", "manage_insurance", "handle_refunds"],
            "outpatient": ["schedule_appointments", "manage_schedules", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "inpatient": list(_INPATIENT_ALL),
            "ehr": ["view_records", "edit_records", "create_prescriptions", "manage_templates", "view_history", "generate_reports"],
        },
        "hospital_admin": {
            "admin": ["manage_users", "manage_roles", "view_system_reports", "manage_settings"],
            "lab": ["view_reports", "create_reports"],
            "pharmacy": ["view_prescriptions", "generate_reports"],
            "billing": ["view_financial_reports", "manage_insurance", "process_payments", "generate_invoices"],
            "outpatient": ["schedule_appointments", "manage_schedules", "register_patients", "manage_queues", "view_appointments", "cancel_appointments"],
            "inpatient": list(_INPATIENT_ALL),
            "ehr": ["view_records", "edit_records", "view_history", "generate_reports"],
        },
        "doctor": {
            "ehr": ["view_records", "edit_records", "create_prescriptions", "view_history", "generate_reports"],
            "lab": ["view_reports", "create_reports"],
            "pharmacy": ["view_prescriptions"],
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
                "order_labs",
                "record_consent",
                "accept_ward_transfer", "manage_housekeeping",
                "report_incident", "acknowledge_critical_alert",
                "view_roster",
                "view_documents",
            ],
        },
        "inpatient_admin": {
            "ehr": ["view_records", "view_history", "manage_allergies"],
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
            ],
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
            ],
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
        "lab_admin": {
            "lab": ["manage_tests", "set_rates", "view_reports", "create_reports", "manage_equipment", "manage_templates"],
        },
        "lab_technician": {
            "lab": ["view_reports", "create_reports"],
        },
        "pharmacy_admin": {
            "pharmacy": ["manage_inventory", "set_drug_rates", "dispense_medications", "view_prescriptions", "manage_suppliers", "generate_reports"],
        },
        "pharmacist": {
            "pharmacy": ["dispense_medications", "view_prescriptions", "manage_inventory"],
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
