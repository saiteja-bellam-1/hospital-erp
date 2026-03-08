#!/usr/bin/env python3
"""
Database migration script to add hospital admin features:
- Enhanced hospital information fields
- Doctor consultation fees and profile fields
"""

import sys
import os
import sqlite3

# Add the backend directory to Python path
sys.path.insert(0, '/Users/saiteja/Documents/GitHub/hospital-ERP/backend')

def migrate_hospital_admin():
    """Add new columns for hospital admin features"""
    db_path = '/Users/saiteja/Documents/GitHub/hospital-ERP/backend/hospital_erp.db'
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔄 Starting hospital admin migration...")
        
        # Add new columns to hospitals table
        hospital_columns = [
            ("city", "VARCHAR(50)"),
            ("state", "VARCHAR(50)"),
            ("postal_code", "VARCHAR(20)"),
            ("country", "VARCHAR(50)"),
            ("fax", "VARCHAR(15)"),
            ("website", "VARCHAR(100)"),
            ("registration_number", "VARCHAR(50)"),
            ("tax_id", "VARCHAR(50)"),
            ("logo_url", "VARCHAR(255)"),
            ("description", "TEXT"),
            ("established_date", "TIMESTAMP")
        ]
        
        for column_name, column_type in hospital_columns:
            try:
                cursor.execute(f"ALTER TABLE hospitals ADD COLUMN {column_name} {column_type}")
                print(f"✓ Added {column_name} column to hospitals table")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    print(f"✓ {column_name} column already exists in hospitals table")
                else:
                    print(f"❌ Error adding {column_name} column to hospitals: {e}")
        
        # Add new columns to users table for doctor profiles
        user_columns = [
            ("consultation_fee", "VARCHAR(20)"),
            ("specialization", "VARCHAR(100)"),
            ("qualification", "VARCHAR(255)"),
            ("experience_years", "INTEGER")
        ]
        
        for column_name, column_type in user_columns:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                print(f"✓ Added {column_name} column to users table")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    print(f"✓ {column_name} column already exists in users table")
                else:
                    print(f"❌ Error adding {column_name} column to users: {e}")
        
        # Create a default hospital if none exists
        cursor.execute("SELECT COUNT(*) FROM hospitals")
        hospital_count = cursor.fetchone()[0]
        
        if hospital_count == 0:
            print("🏥 Creating default hospital record...")
            cursor.execute("""
                INSERT INTO hospitals (
                    hospital_id, name, address, city, state, country, 
                    phone, email, license_number, is_active
                ) VALUES (
                    'HOSP-001', 'General Hospital', '123 Main Street',
                    'New York', 'NY', 'USA', '+1-555-0123', 
                    'admin@generalhospital.com', 'LIC-2024-001', 1
                )
            """)
            print("✓ Default hospital created")
        
        conn.commit()
        conn.close()
        
        print("✅ Hospital admin migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Migration error: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()

if __name__ == "__main__":
    migrate_hospital_admin()