#!/usr/bin/env python3

import sys
import os
sys.path.insert(0, '/Users/saiteja/Documents/GitHub/hospital-ERP')
sys.path.insert(0, '/Users/saiteja/Documents/GitHub/hospital-ERP/backend')

from config.database import SessionLocal, engine
from sqlalchemy import text

def migrate_lab_consultation_link():
    """Add consultation_id and appointment_id columns to patient_lab_orders table"""
    
    db = SessionLocal()
    
    try:
        print("🔧 Starting lab-consultation link migration...")
        
        # Check if columns already exist
        result = db.execute(text("PRAGMA table_info(patient_lab_orders)"))
        columns = [row[1] for row in result.fetchall()]
        
        # Add consultation_id column if it doesn't exist
        if 'consultation_id' not in columns:
            print("📝 Adding consultation_id column...")
            db.execute(text("ALTER TABLE patient_lab_orders ADD COLUMN consultation_id INTEGER REFERENCES consultations(id)"))
            print("✅ consultation_id column added")
        else:
            print("✅ consultation_id column already exists")
        
        # Add appointment_id column if it doesn't exist
        if 'appointment_id' not in columns:
            print("📝 Adding appointment_id column...")
            db.execute(text("ALTER TABLE patient_lab_orders ADD COLUMN appointment_id INTEGER REFERENCES appointments(id)"))
            print("✅ appointment_id column added")
        else:
            print("✅ appointment_id column already exists")
        
        db.commit()
        print("🎉 Migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate_lab_consultation_link()