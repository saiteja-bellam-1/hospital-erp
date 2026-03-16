#!/usr/bin/env python3
"""
Migration script to create the new simplified prescriptions table
This replaces the complex multi-table prescription system with a simple single-table approach
"""

import sys
import os

# Add the backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from config.database import SessionLocal, engine
from app.models.prescriptions_simple import SimplePrescription, Base

def create_simple_prescriptions_table():
    """Create the new simplified prescriptions table"""
    try:
        print("🔄 Creating simplified prescriptions table...")
        
        # Create the table
        SimplePrescription.__table__.create(engine, checkfirst=True)
        
        print("✅ Simplified prescriptions table created successfully!")
        
        # Show table schema
        db = SessionLocal()
        result = db.execute(text("PRAGMA table_info(prescriptions_simple)"))
        columns = result.fetchall()
        
        print("\n📋 Table schema:")
        print("prescriptions_simple:")
        for col in columns:
            print(f"  - {col[1]} ({col[2]}) {'NOT NULL' if col[3] else 'NULL'}")
        
        db.close()
        
        print("\n🎯 New simplified prescription model features:")
        print("  ✓ Single table design (no complex relationships)")
        print("  ✓ JSON storage for medicines (no medicine inventory dependency)")
        print("  ✓ Direct patient_id UUID reference")
        print("  ✓ Simple status tracking (active/cancelled/completed)")
        print("  ✓ Built-in PDF generation support")
        print("  ✓ Multi-hospital support")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating table: {e}")
        return False

def verify_table():
    """Verify the table was created correctly"""
    try:
        db = SessionLocal()
        
        # Test a simple query
        result = db.execute(text("SELECT COUNT(*) FROM prescriptions_simple"))
        count = result.scalar()
        
        print(f"✅ Table verification successful - Current record count: {count}")
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Table verification failed: {e}")
        return False

if __name__ == "__main__":
    print("🏥 KT HEALTH ERP - Simple Prescriptions Table Migration")
    print("=" * 60)
    
    if create_simple_prescriptions_table():
        if verify_table():
            print("\n🎉 Migration completed successfully!")
            print("\nNext steps:")
            print("1. Update main.py to include the new prescriptions_simple route")
            print("2. Test the new prescription API endpoints")
            print("3. Update the frontend to use the new API")
        else:
            print("\n⚠️  Table created but verification failed")
    else:
        print("\n💥 Migration failed!")
        sys.exit(1)