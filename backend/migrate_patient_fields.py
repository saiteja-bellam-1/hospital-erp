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
]

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

        conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
