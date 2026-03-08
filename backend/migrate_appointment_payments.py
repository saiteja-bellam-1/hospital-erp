#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from config.database import SessionLocal, engine
from sqlalchemy import text

def migrate_appointment_payment_fields():
    """Add payment fields to appointments table"""
    
    try:
        with engine.connect() as conn:
            # Check if columns already exist
            result = conn.execute(text("PRAGMA table_info(appointments)"))
            columns = [row[1] for row in result.fetchall()]
            
            # Add missing columns
            columns_to_add = [
                ("consultation_fee", "FLOAT DEFAULT 0.0"),
                ("payment_status", "VARCHAR(20) DEFAULT 'pending'"),
                ("payment_method", "VARCHAR(50)"),
                ("payment_date", "DATETIME"),
                ("payment_notes", "TEXT"),
                ("discount_amount", "FLOAT DEFAULT 0.0"),
                ("final_amount", "FLOAT DEFAULT 0.0")
            ]
            
            for col_name, col_def in columns_to_add:
                if col_name not in columns:
                    try:
                        conn.execute(text(f"ALTER TABLE appointments ADD COLUMN {col_name} {col_def}"))
                        conn.commit()
                        print(f"✅ Added column: {col_name}")
                    except Exception as e:
                        print(f"❌ Error adding column {col_name}: {e}")
                else:
                    print(f"⚠️  Column {col_name} already exists")
            
            print("\n✅ Appointment payment fields migration completed successfully!")
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("🏥 Migrating Appointment Payment Fields")
    print("=" * 40)
    
    success = migrate_appointment_payment_fields()
    
    if success:
        print("\n🎉 Migration completed successfully!")
        sys.exit(0)
    else:
        print("\n💥 Migration failed!")
        sys.exit(1)