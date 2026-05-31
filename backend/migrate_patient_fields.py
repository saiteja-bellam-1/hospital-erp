#!/usr/bin/env python3
"""
Migration: Add new columns to existing tables.
Safe to run multiple times — skips columns that already exist.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.database import engine

NEW_COLUMNS = [
    ("patients", "marital_status", "VARCHAR(20)"),
    ("patients", "abha_id", "VARCHAR(30)"),
    ("patients", "email", "VARCHAR(100)"),
    ("patients", "emergency_contact_name", "VARCHAR(100)"),
    ("patients", "emergency_contact_relation", "VARCHAR(50)"),
    ("patients", "address_line1", "VARCHAR(255)"),
    ("patients", "address_line2", "VARCHAR(255)"),
    ("patients", "village", "VARCHAR(100)"),
    ("patients", "mandal", "VARCHAR(100)"),
    ("patients", "district", "VARCHAR(100)"),
    ("appointments", "registration_fee", "FLOAT DEFAULT 0.0"),
    ("consultations", "appointment_id", "INTEGER REFERENCES appointments(id)"),
    ("patients", "age", "INTEGER"),
    ("lab_test_parameters", "method", "VARCHAR(200)"),
    ("lab_test_parameters", "section", "VARCHAR(200)"),
    ("patient_lab_orders", "package_id", "INTEGER REFERENCES lab_test_packages(id)"),
    ("patient_lab_orders", "package_booking_id", "VARCHAR(50)"),
    ("patients", "referred_by", "VARCHAR(100)"),
    ("appointments", "referred_by", "VARCHAR(100)"),
    ("payments", "payment_method_name", "VARCHAR(50) DEFAULT 'cash'"),
    ("patient_lab_orders", "sample_id", "VARCHAR(50)"),
    ("lab_test_parameters", "reference_ranges", "JSON"),
    ("lab_test_parameters", "abnormal_values", "JSON"),
    ("lab_test_parameters", "normal_value", "VARCHAR(100)"),
    ("patient_lab_orders", "referred_by", "VARCHAR(100)"),
    ("lab_test_parameters", "reference_min_child", "FLOAT"),
    ("lab_test_parameters", "reference_max_child", "FLOAT"),
    ("lab_test_parameters", "notes", "VARCHAR(500)"),
    ("licenses", "seller_info", "JSON"),
    ("appointments", "bill_cancelled_reason", "TEXT"),
    ("appointments", "bill_cancelled_by", "INTEGER REFERENCES users(id)"),
    ("appointments", "bill_cancelled_at", "DATETIME"),
    ("patient_lab_orders", "bill_cancelled_reason", "TEXT"),
    ("patient_lab_orders", "bill_cancelled_by", "INTEGER REFERENCES users(id)"),
    ("patient_lab_orders", "bill_cancelled_at", "DATETIME"),
    ("licenses", "gdrive_config", "JSON"),
    ("payments", "insurance_provider", "VARCHAR(200)"),
    ("payments", "policy_number", "VARCHAR(100)"),
    ("payments", "claim_reference", "VARCHAR(100)"),
    ("payments", "parent_payment_id", "INTEGER REFERENCES payments(id)"),
    ("payments", "reversed_by_id", "INTEGER REFERENCES users(id)"),
    ("payments", "reversed_at", "DATETIME"),
    ("payments", "reversal_reason", "TEXT"),
    ("bills", "parent_bill_id", "INTEGER REFERENCES bills(id)"),
    ("bills", "referred_by", "VARCHAR(100)"),
    ("prescriptions", "admission_id", "INTEGER"),
    ("prescriptions_simple", "admission_id", "INTEGER"),
    ("admissions", "insurance_provider", "VARCHAR(200)"),
    ("admissions", "policy_number", "VARCHAR(100)"),
    ("admissions", "claim_reference", "VARCHAR(100)"),
    ("admissions", "claim_status", "VARCHAR(20) DEFAULT 'none'"),
    ("admissions", "claim_amount", "FLOAT"),
    ("admissions", "claim_submitted_at", "DATETIME"),
    ("admissions", "claim_notes", "TEXT"),
    ("patient_lab_orders", "admission_id", "INTEGER REFERENCES admissions(id)"),
    ("admissions", "bed_id", "INTEGER REFERENCES beds(id)"),
    # MAR scheduling on prescription_items (Phase 1 — Inpatient expansion)
    ("prescription_items", "frequency", "VARCHAR(50)"),
    ("prescription_items", "schedule_times", "JSON"),
    ("prescription_items", "duration_days", "INTEGER"),
    ("prescription_items", "route", "VARCHAR(30)"),
    ("prescription_items", "is_prn", "BOOLEAN DEFAULT 0"),
    # Phase 2 — Billing & financial maturity
    ("bills", "bill_subtype", "VARCHAR(20) DEFAULT 'final'"),
    ("patient_visits", "bill_id", "INTEGER REFERENCES bills(id)"),
    ("ot_schedules", "surgeon_fee", "FLOAT DEFAULT 0.0"),
    ("ot_schedules", "anaesthetist_fee", "FLOAT DEFAULT 0.0"),
    ("ot_schedules", "ot_room_charge", "FLOAT DEFAULT 0.0"),
    ("ot_schedules", "equipment_charge", "FLOAT DEFAULT 0.0"),
    ("ot_schedules", "consumables_charge", "FLOAT DEFAULT 0.0"),
    ("ot_schedules", "other_charges", "FLOAT DEFAULT 0.0"),
    ("ot_schedules", "billed", "BOOLEAN DEFAULT 0"),
    ("ot_schedules", "bill_id", "INTEGER REFERENCES bills(id)"),
    ("prescriptions", "inpatient_bill_id", "INTEGER REFERENCES bills(id)"),
    ("patient_lab_orders", "inpatient_bill_id", "INTEGER REFERENCES bills(id)"),
    # Outpatient lab bill grouping — shared across all orders on the same
    # combined bill so the Billing dashboard can render one row per bill
    # instead of one row per test.
    ("patient_lab_orders", "lab_bill_group_id", "VARCHAR(64)"),
    ("patient_lab_orders", "lab_bill_number", "VARCHAR(64)"),
    # Phase 3 — no new columns on existing tables; new tables created via create_all
    # Phase 4 — compliance & quality
    ("admissions", "is_readmission", "BOOLEAN DEFAULT 0"),
    ("admissions", "previous_admission_id", "INTEGER REFERENCES admissions(id)"),
    ("admissions", "days_since_last_discharge", "INTEGER"),
    ("discharge_records", "cause_of_death", "TEXT"),
    ("discharge_records", "time_of_death", "DATETIME"),
    ("discharge_records", "death_certificate_number", "VARCHAR(100)"),
    ("discharge_records", "mlc_required", "BOOLEAN DEFAULT 0"),
    ("discharge_records", "mlc_number", "VARCHAR(100)"),
    ("discharge_records", "autopsy_done", "BOOLEAN DEFAULT 0"),
    ("discharge_records", "autopsy_findings", "TEXT"),
    ("discharge_records", "body_handed_over_to", "VARCHAR(200)"),
    ("discharge_records", "body_handover_relationship", "VARCHAR(100)"),
    ("discharge_records", "body_handover_time", "DATETIME"),
    ("discharge_records", "body_handover_id_proof", "VARCHAR(200)"),
    # ICU add-ons: critical lab thresholds
    ("lab_test_parameters", "critical_low", "FLOAT"),
    ("lab_test_parameters", "critical_high", "FLOAT"),
    # Procedure catalog refactor (rate management)
    ("ot_schedules", "procedure_id", "INTEGER REFERENCES procedures(id)"),
    ("ot_schedules", "procedure_charge", "FLOAT DEFAULT 0.0"),
    # Sample type grouping for lab tests
    ("lab_tests", "sample_type_id", "INTEGER REFERENCES sample_types(id)"),
    # Daily auto-post tracking on patient visits (idempotency for nightly job)
    ("patient_visits", "auto_posted", "BOOLEAN DEFAULT 0"),
    # Room-rate snapshots per stay segment — eliminates the bug where a
    # mid-stay room change re-rates the entire stay at the latest rate.
    ("admissions", "initial_room_charge_per_day", "FLOAT"),
    ("bed_transfer_history", "from_room_charge_per_day", "FLOAT"),
    ("bed_transfer_history", "to_room_charge_per_day", "FLOAT"),
    # Medicine safety flags — narcotic + high-alert. Used by MAR safety wraps.
    ("medicines", "is_narcotic", "BOOLEAN DEFAULT 0"),
    ("medicines", "is_high_alert", "BOOLEAN DEFAULT 0"),
    # Doctor ward-round checklist on PatientVisit
    ("patient_visits", "vitals_reviewed", "BOOLEAN DEFAULT 0"),
    ("patient_visits", "labs_reviewed", "BOOLEAN DEFAULT 0"),
    ("patient_visits", "pain_assessed", "BOOLEAN DEFAULT 0"),
    ("patient_visits", "mobility_checked", "BOOLEAN DEFAULT 0"),
    ("patient_visits", "plan_for_today", "TEXT"),
    ("patient_visits", "family_updated", "BOOLEAN DEFAULT 0"),
    # Force-change-password flag (Installer Phase 1 — security baseline)
    ("users", "must_change_password", "BOOLEAN DEFAULT 0"),
    # B7 — Emergency / casualty workflow
    ("admissions", "triage_level", "INTEGER"),
    ("admissions", "chief_complaint", "TEXT"),
    ("admissions", "arrival_mode", "VARCHAR(20)"),
    ("admissions", "ambulance_details", "TEXT"),
    ("admissions", "is_mlc", "BOOLEAN DEFAULT 0"),
    ("admissions", "mlc_number", "VARCHAR(50)"),
    ("admissions", "mlc_type", "VARCHAR(30)"),
    ("admissions", "police_station_informed", "VARCHAR(200)"),
    ("admissions", "mlc_informed_at", "DATETIME"),
    ("patients", "registration_complete", "BOOLEAN DEFAULT 1"),
    # B7.6 — Observation cases
    ("admissions", "is_observation", "BOOLEAN DEFAULT 0"),
    # B7.7 — Deposit waiver
    ("discharge_records", "take_home_medications", "JSON"),
    ("admissions", "deposit_waived", "BOOLEAN DEFAULT 0"),
    ("admissions", "deposit_waiver_reason", "TEXT"),
    ("admissions", "deposit_waived_by_id", "INTEGER REFERENCES users(id)"),
    ("admissions", "deposit_waived_at", "DATETIME"),
    # MRN — human-readable patient identifier (PREFIX-YYYY-NNNNN)
    ("patients", "mrn", "VARCHAR(32)"),
    ("hospitals", "mrn_prefix", "VARCHAR(8)"),
    # B1 — Payer scheme on admission
    ("admissions", "payer_scheme_id", "INTEGER REFERENCES payer_schemes(id)"),
    ("admissions", "payer_type", "VARCHAR(30)"),
    ("admissions", "scheme_member_id", "VARCHAR(100)"),
    ("admissions", "scheme_approval_status", "VARCHAR(20) DEFAULT 'none'"),
    ("admissions", "scheme_approval_ref", "VARCHAR(100)"),
    ("admissions", "scheme_approval_amount", "FLOAT"),
    # B3 — Referring doctor + accept handshake. acceptance_status defaults to
    # 'accepted' so any pre-existing admissions remain editable.
    ("admissions", "referring_doctor_id", "INTEGER REFERENCES users(id)"),
    ("admissions", "referring_external_name", "VARCHAR(200)"),
    ("admissions", "acceptance_status", "VARCHAR(20) DEFAULT 'accepted'"),
    ("admissions", "accepted_by_doctor_id", "INTEGER REFERENCES users(id)"),
    ("admissions", "accepted_at", "DATETIME"),
    ("admissions", "rejection_reason", "TEXT"),
    # B4 — Duty-doctor visit rate (separate from consultant per-visit fee)
    ("inpatient_rate_configs", "duty_visit_rate", "NUMERIC(10, 2) DEFAULT 0.00"),
    # Room-level ward assignment and per-room nursing charge
    ("room_management", "ward", "VARCHAR(100)"),
    ("room_management", "nursing_charge_per_visit", "NUMERIC(10, 2) DEFAULT 0.00"),
    # Expanded room metadata: infection-control flag and gender policy
    ("room_management", "is_isolation", "BOOLEAN DEFAULT 0"),
    ("room_management", "gender_policy", "VARCHAR(10) DEFAULT 'mixed'"),
    # Sequential document number printed on face-sheet / case-sheet PDFs
    ("consents", "doc_number", "VARCHAR(50)"),
    # Granular lab-test inclusion inside a Surgery Package: when mode='selected'
    # only the LabTest IDs in included_lab_test_ids are covered, the rest bill.
    ("surgery_packages", "lab_coverage_mode", "VARCHAR(20) DEFAULT 'all'"),
    ("surgery_packages", "included_lab_test_ids", "TEXT"),
    # Outpatient token lifecycle — skip/recall/priority-boost queue management
    ("appointments", "token_status", "VARCHAR(20)"),
    ("appointments", "token_called_at", "DATETIME"),
    ("appointments", "token_skipped_at", "DATETIME"),
    ("appointments", "token_recalled_at", "DATETIME"),
    ("appointments", "priority_boost", "INTEGER DEFAULT 0"),
    # Availability override — receptionist/admin force-book outside doctor schedule
    ("appointments", "override_availability", "BOOLEAN DEFAULT 0"),
    ("appointments", "override_reason", "TEXT"),
    # Pharmacy hardening (P1.3): stop older back-dated purchases from clobbering
    # the medicine master price; only entries newer than this date win.
    ("medicines", "last_purchase_date", "DATE"),
    # Pharmacy: confirmed purchases can be revoked (proportional reversal of
    # the un-sold portion). Confirmed/draft/revoked/revoked_partial are the
    # possible statuses going forward.
    ("pharmacy_purchases", "revoked_by", "INTEGER REFERENCES users(id)"),
    ("pharmacy_purchases", "revoked_at", "DATETIME"),
    ("pharmacy_purchases", "revoke_reason", "TEXT"),
    # P2.1: snapshot HSN tax breakdown onto line items so historical reports
    # are stable even when the HSN master rates change later.
    ("pharmacy_sale_items", "sgst_pct", "FLOAT DEFAULT 0.0"),
    ("pharmacy_sale_items", "cgst_pct", "FLOAT DEFAULT 0.0"),
    ("pharmacy_sale_items", "igst_pct", "FLOAT DEFAULT 0.0"),
    ("pharmacy_purchase_items", "sgst_pct", "FLOAT DEFAULT 0.0"),
    ("pharmacy_purchase_items", "cgst_pct", "FLOAT DEFAULT 0.0"),
    ("pharmacy_purchase_items", "igst_pct", "FLOAT DEFAULT 0.0"),
]

# B6 — body release table is created via create_all on startup; no column adds.


def migrate():
    from sqlalchemy import text
    with engine.connect() as conn:
        for table, col, col_type in NEW_COLUMNS:
            # Get existing columns for this table
            result = conn.execute(text(f"PRAGMA table_info({table})"))
            existing = {row[1] for row in result.fetchall()}

            if col not in existing:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"
                ))
                print(f"  Added column: {table}.{col}")
            else:
                print(f"  Already exists: {table}.{col}")
        # Remove unique constraint on patients.primary_phone (SQLite requires table rebuild)
        try:
            result = conn.execute(text("PRAGMA index_list(patients)"))
            has_unique_phone = False
            for row in result.fetchall():
                index_name = row[1]
                idx_info = conn.execute(text(f"PRAGMA index_info({index_name})"))
                cols = [r[2] for r in idx_info.fetchall()]
                if 'primary_phone' in cols and row[2] == 1:
                    has_unique_phone = True
                    break
            if has_unique_phone:
                # SQLite: rebuild table without unique constraint
                conn.execute(text("CREATE TABLE IF NOT EXISTS patients_backup AS SELECT * FROM patients"))
                conn.execute(text("DROP TABLE patients"))
                # Get column info to recreate
                conn.execute(text("""
                    CREATE TABLE patients (
                        id INTEGER PRIMARY KEY,
                        patient_id VARCHAR(36) NOT NULL UNIQUE,
                        first_name VARCHAR(50) NOT NULL,
                        last_name VARCHAR(50) NOT NULL,
                        date_of_birth DATE,
                        age INTEGER,
                        gender VARCHAR(10),
                        blood_group VARCHAR(5),
                        marital_status VARCHAR(20),
                        abha_id VARCHAR(30),
                        email VARCHAR(100),
                        primary_phone VARCHAR(15) NOT NULL,
                        emergency_contact_phone VARCHAR(15),
                        emergency_contact_name VARCHAR(100),
                        emergency_contact_relation VARCHAR(50),
                        address_line1 VARCHAR(255),
                        address_line2 VARCHAR(255),
                        village VARCHAR(100),
                        mandal VARCHAR(100),
                        district VARCHAR(100),
                        address TEXT,
                        is_active BOOLEAN DEFAULT 1,
                        hospital_id INTEGER NOT NULL REFERENCES hospitals(id),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME
                    )
                """))
                conn.execute(text("""
                    INSERT INTO patients SELECT * FROM patients_backup
                """))
                conn.execute(text("DROP TABLE patients_backup"))
                print("  Removed unique constraint from patients.primary_phone")
        except Exception as e:
            print(f"  Note (phone constraint): {e}")

        # Remove unique constraint on patient_lab_orders.sample_id (needed for sample grouping)
        try:
            result = conn.execute(text("PRAGMA index_list(patient_lab_orders)"))
            rows = result.fetchall()
            for row in rows:
                index_name = row[1]
                is_unique = row[2]
                idx_info = conn.execute(text(f"PRAGMA index_info({index_name})"))
                cols = [r[2] for r in idx_info.fetchall()]
                if 'sample_id' in cols and is_unique == 1:
                    if index_name.startswith('sqlite_autoindex_'):
                        # Auto-index from CREATE TABLE can't be dropped — must rebuild table
                        # Read all column definitions from the existing table
                        table_info = conn.execute(text("PRAGMA table_info(patient_lab_orders)")).fetchall()
                        col_defs = []
                        for ci in table_info:
                            cid, cname, ctype, notnull, default_val, pk = ci
                            parts = [cname, ctype or 'TEXT']
                            if pk:
                                parts.append("PRIMARY KEY")
                            if notnull and not pk:
                                parts.append("NOT NULL")
                            if default_val is not None:
                                parts.append(f"DEFAULT {default_val}")
                            col_defs.append(" ".join(parts))
                        # Rebuild without unique on sample_id
                        col_names = ", ".join([ci[1] for ci in table_info])
                        col_def_str = ", ".join(col_defs)
                        conn.execute(text("ALTER TABLE patient_lab_orders RENAME TO _plo_backup"))
                        conn.execute(text(f"CREATE TABLE patient_lab_orders ({col_def_str})"))
                        conn.execute(text(f"INSERT INTO patient_lab_orders SELECT {col_names} FROM _plo_backup"))
                        conn.execute(text("DROP TABLE _plo_backup"))
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_patient_lab_orders_sample_id ON patient_lab_orders(sample_id)"))
                        print("  Rebuilt patient_lab_orders to remove unique constraint on sample_id")
                    else:
                        conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
                        print(f"  Dropped unique index {index_name} on patient_lab_orders.sample_id")
                        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_patient_lab_orders_sample_id ON patient_lab_orders(sample_id)"))
                        print("  Created non-unique index on patient_lab_orders.sample_id")
                    break
        except Exception as e:
            print(f"  Note (sample_id index): {e}")

        conn.commit()

    # MRN backfill — assign human-readable IDs to any patient where mrn IS NULL.
    # Idempotent: only touches rows that don't yet have an MRN.
    try:
        backfill_patient_mrns()
    except Exception as e:
        print(f"  Note (mrn backfill): {e}")

    print("Migration complete.")


def backfill_patient_mrns():
    """Assign MRNs to patients with mrn IS NULL.

    Format: {hospital.mrn_prefix or 'KTH'}-{YYYY}-{NNNNN}
    Sequence is per (hospital_id, year), based on registration year (created_at).
    Patients are processed in id-ascending order within each (hospital, year).
    """
    from sqlalchemy import text
    with engine.connect() as conn:
        # Verify both columns exist (older DBs without the migration won't have hospitals.mrn_prefix yet)
        try:
            conn.execute(text("SELECT mrn FROM patients LIMIT 0"))
            conn.execute(text("SELECT mrn_prefix FROM hospitals LIMIT 0"))
        except Exception:
            return  # columns missing — nothing to backfill

        hospitals = conn.execute(text("SELECT id, mrn_prefix FROM hospitals")).fetchall()
        for h_id, h_prefix in hospitals:
            prefix = (h_prefix or "KTH").strip().upper() or "KTH"

            # Find the highest existing sequence per year for this hospital, so
            # backfill picks up where any prior partial run left off.
            existing = conn.execute(text(
                """
                SELECT mrn FROM patients
                WHERE hospital_id = :hid AND mrn IS NOT NULL
                """
            ), {"hid": h_id}).fetchall()
            year_seq = {}
            for (m,) in existing:
                try:
                    parts = m.rsplit("-", 2)
                    if len(parts) >= 2:
                        y = int(parts[-2])
                        s = int(parts[-1])
                        if y not in year_seq or s > year_seq[y]:
                            year_seq[y] = s
                except Exception:
                    continue

            # Process unassigned patients in id-ascending order
            rows = conn.execute(text(
                """
                SELECT id, created_at FROM patients
                WHERE hospital_id = :hid AND (mrn IS NULL OR mrn = '')
                ORDER BY id ASC
                """
            ), {"hid": h_id}).fetchall()

            for pid, created_at in rows:
                # Derive year from created_at; fall back to current year on bad data
                year = None
                if isinstance(created_at, str):
                    try:
                        year = int(created_at[:4])
                    except Exception:
                        year = None
                elif hasattr(created_at, "year"):
                    year = created_at.year
                if not year:
                    from datetime import datetime as _dt
                    year = _dt.now().year

                next_seq = year_seq.get(year, 0) + 1
                year_seq[year] = next_seq
                mrn = f"{prefix}-{year}-{next_seq:05d}"

                conn.execute(text(
                    "UPDATE patients SET mrn = :mrn WHERE id = :pid"
                ), {"mrn": mrn, "pid": pid})

            if rows:
                print(f"  MRN backfill: assigned {len(rows)} MRN(s) for hospital_id={h_id} (prefix={prefix})")

        conn.commit()


if __name__ == "__main__":
    migrate()
