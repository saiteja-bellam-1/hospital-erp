#!/usr/bin/env python3
"""Idempotent migration: add FK indexes on inpatient hot paths.

Inpatient list endpoints scan by admission_id / bill_id / room_id / bed_id
without indexes, so any sizeable archive turns linear scans into hot paths.
SQLite's CREATE INDEX IF NOT EXISTS is portable enough for the targeted DBs.

Safe to run repeatedly. Called from main.py's startup_event.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.database import engine
from sqlalchemy import text

# (index_name, table, columns) — names prefixed `ix_inpatient_` for traceability.
INDEXES = [
    ("ix_inpatient_visits_admission", "patient_visits", "admission_id"),
    ("ix_inpatient_visits_bill", "patient_visits", "bill_id"),

    ("ix_inpatient_ot_admission", "ot_schedules", "admission_id"),
    ("ix_inpatient_ot_bill", "ot_schedules", "bill_id"),
    ("ix_inpatient_ot_status", "ot_schedules", "status"),

    ("ix_inpatient_anc_admission", "admission_ancillary_charges", "admission_id"),
    ("ix_inpatient_anc_bill", "admission_ancillary_charges", "bill_id"),

    ("ix_inpatient_deposits_admission", "admission_deposits", "admission_id"),

    ("ix_inpatient_discharge_admission", "discharge_records", "admission_id"),

    ("ix_inpatient_nursing_admission", "nursing_notes", "admission_id"),
    ("ix_inpatient_diet_admission", "diet_orders", "admission_id"),
    ("ix_inpatient_vitals_admission", "vital_signs", "admission_id"),
    ("ix_inpatient_mar_admission", "medication_administrations", "admission_id"),
    ("ix_inpatient_io_admission", "fluid_balance_entries", "admission_id"),

    ("ix_inpatient_consent_admission", "consents", "admission_id"),
    ("ix_inpatient_incident_admission", "incidents", "admission_id"),
    ("ix_inpatient_incident_status", "incidents", "status"),

    ("ix_inpatient_transfer_admission", "bed_transfer_history", "admission_id"),
    ("ix_inpatient_transfer_status", "bed_transfer_history", "status"),

    ("ix_inpatient_turnover_bed", "bed_turnover_log", "bed_id"),
    ("ix_inpatient_reservation_patient", "bed_reservations", "patient_id"),
    ("ix_inpatient_reservation_status", "bed_reservations", "status"),

    ("ix_inpatient_nurse_assign_admission", "nurse_assignments", "admission_id"),
    ("ix_inpatient_nurse_assign_nurse", "nurse_assignments", "nurse_id"),

    ("ix_inpatient_alert_admission", "critical_lab_alerts", "admission_id"),
    ("ix_inpatient_alert_status", "critical_lab_alerts", "status"),
    ("ix_inpatient_alert_lab_order", "critical_lab_alerts", "lab_order_id"),

    ("ix_inpatient_doc_admission", "admission_documents", "admission_id"),
    ("ix_inpatient_pkg_admission", "admission_packages", "admission_id"),
    ("ix_inpatient_preauth_admission", "insurance_preauths", "admission_id"),
    ("ix_inpatient_preauth_exp_preauth", "insurance_preauth_expansions", "preauth_id"),

    ("ix_inpatient_split_bill", "bill_splits", "bill_id"),

    ("ix_inpatient_admissions_patient", "admissions", "patient_id"),
    ("ix_inpatient_admissions_doctor", "admissions", "admitting_doctor_id"),
    ("ix_inpatient_admissions_room", "admissions", "room_id"),
    ("ix_inpatient_admissions_bed", "admissions", "bed_id"),
    ("ix_inpatient_admissions_status", "admissions", "status"),

    ("ix_inpatient_beds_room", "beds", "room_id"),
    ("ix_inpatient_beds_admission", "beds", "current_admission_id"),
    ("ix_inpatient_beds_status", "beds", "status"),

    # Bills are looked up by (bill_type, reference_id) constantly for admission balance.
    ("ix_bills_type_reference", "bills", "bill_type, reference_id"),
    ("ix_bills_reference", "bills", "reference_id"),

    # Inpatient-bill linkage on Rx/lab.
    ("ix_prescriptions_inpatient_bill", "prescriptions", "inpatient_bill_id"),
    ("ix_prescriptions_admission", "prescriptions", "admission_id"),
    ("ix_lab_orders_inpatient_bill", "patient_lab_orders", "inpatient_bill_id"),
    ("ix_lab_orders_admission", "patient_lab_orders", "admission_id"),
]


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:t"
    ), {"t": table_name}).fetchone()
    return row is not None


def _column_exists(conn, table_name: str, columns_csv: str) -> bool:
    cols = [c.strip() for c in columns_csv.split(",")]
    info = conn.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
    existing = {r[1] for r in info}
    return all(c in existing for c in cols)


def migrate_indexes():
    created = 0
    skipped = 0
    with engine.connect() as conn:
        for name, table, cols in INDEXES:
            if not _table_exists(conn, table):
                skipped += 1
                continue
            if not _column_exists(conn, table, cols):
                skipped += 1
                continue
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})"))
            created += 1
        try:
            conn.commit()
        except Exception:
            pass
    print(f"Inpatient index migration: ensured {created} indexes ({skipped} skipped — table/column missing)")


if __name__ == "__main__":
    migrate_indexes()
