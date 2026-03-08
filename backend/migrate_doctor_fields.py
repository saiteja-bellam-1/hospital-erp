#!/usr/bin/env python3

import sys
import os

# Add the backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from config.database import SessionLocal, engine

def migrate_doctor_fields():
    """Add new doctor fields to the users table"""
    
    db = SessionLocal()
    try:
        print("🔄 Starting doctor fields migration...")
        
        # Add new columns to users table
        migrations = [
            "ALTER TABLE users ADD COLUMN license_number VARCHAR(50);",
            "ALTER TABLE users ADD COLUMN consultation_fee_inr VARCHAR(20);", 
            "ALTER TABLE users ADD COLUMN inpatient_fee_inr VARCHAR(20);",
            "ALTER TABLE users ADD COLUMN emergency_fee_inr VARCHAR(20);"
        ]
        
        for migration in migrations:
            try:
                db.execute(text(migration))
                print(f"✅ Executed: {migration}")
            except Exception as e:
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"⚠️  Column already exists: {migration}")
                else:
                    print(f"❌ Error executing {migration}: {e}")
                    continue
        
        # Migrate existing consultation_fee data to consultation_fee_inr
        try:
            # First, check if we have the old consultation_fee column
            result = db.execute(text("PRAGMA table_info(users);"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'consultation_fee' in columns:
                print("🔄 Migrating existing consultation_fee data to consultation_fee_inr...")
                db.execute(text("""
                    UPDATE users 
                    SET consultation_fee_inr = consultation_fee 
                    WHERE consultation_fee IS NOT NULL AND consultation_fee != '';
                """))
                print("✅ Migrated existing consultation fee data")
                
                # Note: We're keeping the old consultation_fee column for now to avoid breaking existing code
                # In a production environment, you'd want to drop it after ensuring all code uses the new fields
                
        except Exception as e:
            print(f"⚠️  Migration of existing data failed (this is okay if consultation_fee column doesn't exist): {e}")
        
        db.commit()
        print("✅ Doctor fields migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate_doctor_fields()