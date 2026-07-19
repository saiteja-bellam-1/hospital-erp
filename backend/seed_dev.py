"""Dev-only seeder: creates a fresh hospital DB + super_admin.

Run once from the backend/ dir with the venv python:
    .\venv\Scripts\python seed_dev.py

Idempotent — re-running on an already-seeded DB is a no-op for existing rows.
Credentials/hospital are intentionally simple for LOCAL dev only.
"""
import os

from app.services.db_seed import init_database_and_seed
from app.utils.paths import get_db_path

SEED = {
    "hospital_name": "Test Hospital",
    "admin_username": "admin",
    "admin_email": "admin@test.local",
    "admin_password": "admin123",
}


def main():
    db_path = get_db_path()
    print(f"Seeding DB at: {db_path}")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    init_database_and_seed(SEED, db_path)
    print("Seed complete. Login: admin / admin123")


if __name__ == "__main__":
    main()
