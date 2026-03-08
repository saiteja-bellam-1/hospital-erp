"""
Migration: Add queue management, check-out, cancellation, and reschedule fields to appointments
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.database import engine
from sqlalchemy import text

def migrate():
    with engine.connect() as conn:
        # Add checked_out_at
        try:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN checked_out_at TIMESTAMP"))
            print("Added checked_out_at column")
        except Exception as e:
            print(f"checked_out_at: {e}")

        # Add token_number
        try:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN token_number INTEGER"))
            print("Added token_number column")
        except Exception as e:
            print(f"token_number: {e}")

        # Add queue_position
        try:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN queue_position INTEGER"))
            print("Added queue_position column")
        except Exception as e:
            print(f"queue_position: {e}")

        # Add cancellation_reason
        try:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN cancellation_reason TEXT"))
            print("Added cancellation_reason column")
        except Exception as e:
            print(f"cancellation_reason: {e}")

        # Add rescheduled_from_id
        try:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN rescheduled_from_id INTEGER REFERENCES appointments(id)"))
            print("Added rescheduled_from_id column")
        except Exception as e:
            print(f"rescheduled_from_id: {e}")

        conn.commit()
        print("Migration completed!")

if __name__ == "__main__":
    migrate()
