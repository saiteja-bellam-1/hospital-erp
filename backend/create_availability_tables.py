#!/usr/bin/env python3
"""
Create doctor availability tables
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.database import engine
from app.models.doctor_availability import DoctorAvailability, DoctorSpecialSchedule, DoctorAvailabilityStatus

def create_availability_tables():
    """Create doctor availability tables"""
    try:
        # Create the tables
        DoctorAvailability.__table__.create(bind=engine, checkfirst=True)
        DoctorSpecialSchedule.__table__.create(bind=engine, checkfirst=True)
        DoctorAvailabilityStatus.__table__.create(bind=engine, checkfirst=True)
        
        print("✅ Doctor availability tables created successfully!")
        
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        return False
    
    return True

if __name__ == "__main__":
    create_availability_tables()