#!/usr/bin/env python3
"""
Migration: drop the Incident reporting subsystem and the Diet ordering
subsystem entirely. Safe to run multiple times — each step checks for
existence before acting.

What it does, in order:
  1. Drop the medication_administrations.incident_id column (if present).
     SQLite >= 3.35 supports ALTER TABLE DROP COLUMN; we use that. If the
     install is on an older SQLite (very unlikely on a modern KT HEALTH
     ERP deployment), the FK column is left in place — it's a nullable
     orphan and causes no runtime issue.
  2. DROP TABLE diet_meal_logs (child of diet_orders — drop first).
  3. DROP TABLE diet_orders.
  4. DROP TABLE incidents.

The order matters: child-with-FK tables drop before parents, and the FK
column on medication_administrations is removed before the incidents
table itself.
"""
from sqlalchemy import text


def migrate_drop_incidents_diet(engine):
    with engine.connect() as conn:
        # 1. medication_administrations.incident_id — drop if present.
        try:
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(medication_administrations)")).fetchall()}
            if "incident_id" in cols:
                try:
                    conn.execute(text("ALTER TABLE medication_administrations DROP COLUMN incident_id"))
                    print("  Dropped column: medication_administrations.incident_id")
                except Exception as e:
                    # Older SQLite — leave the orphan column; it does not break anything.
                    print(f"  Could not drop medication_administrations.incident_id ({e}); leaving in place")
            else:
                print("  Column medication_administrations.incident_id already absent")
        except Exception as e:
            # Table doesn't exist yet (fresh install before create_all). Nothing to do.
            print(f"  medication_administrations not present yet ({e})")

        # 2-4. Drop the three retired tables in dependency order.
        for tbl in ("diet_meal_logs", "diet_orders", "incidents"):
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))
                print(f"  Dropped table (if existed): {tbl}")
            except Exception as e:
                print(f"  DROP TABLE {tbl} failed: {e}")

        try:
            conn.commit()
        except Exception:
            # Older SQLAlchemy versions auto-commit on close; ignore.
            pass


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config.database import engine
    migrate_drop_incidents_diet(engine)
    print("Done.")
