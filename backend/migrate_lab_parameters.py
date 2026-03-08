"""
Migration: Create lab_test_parameters table using SQLAlchemy metadata
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.database import engine, Base
from app.models.lab import LabTestParameter

def run_migration():
    from sqlalchemy import inspect
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    if "lab_test_parameters" in existing_tables:
        print("Table lab_test_parameters already exists, skipping.")
        return

    LabTestParameter.__table__.create(engine)
    print("Created lab_test_parameters table successfully.")

if __name__ == "__main__":
    run_migration()
