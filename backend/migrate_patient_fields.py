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
        conn.commit()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
