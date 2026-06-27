#!/usr/bin/env python3
"""
Multi-store pharmacy migration.

1. Adds store_id columns to pharmacy transactional tables.
2. Adds pharmacy_multi_store_enabled on hospitals.
3. Creates a default master store per hospital and backfills store_id.

Idempotent — safe to run multiple times.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.database import engine

NEW_COLUMNS = [
    ("hospitals", "pharmacy_multi_store_enabled", "BOOLEAN DEFAULT 0"),
    ("hospitals", "pharmacy_require_store_assignment", "BOOLEAN DEFAULT 0"),
    ("pharmacy_inventory", "store_id", "INTEGER REFERENCES pharmacy_stores(id)"),
    ("pharmacy_stock_ledger", "store_id", "INTEGER REFERENCES pharmacy_stores(id)"),
    ("pharmacy_purchases", "store_id", "INTEGER REFERENCES pharmacy_stores(id)"),
    ("pharmacy_sales", "store_id", "INTEGER REFERENCES pharmacy_stores(id)"),
    ("pharmacy_stock_adjustments", "store_id", "INTEGER REFERENCES pharmacy_stores(id)"),
    ("prescriptions", "dispense_store_id", "INTEGER REFERENCES pharmacy_stores(id)"),
]

BACKFILL_TABLES = [
    "pharmacy_inventory",
    "pharmacy_stock_ledger",
    "pharmacy_purchases",
    "pharmacy_sales",
    "pharmacy_stock_adjustments",
]


def _table_exists(conn, name: str) -> bool:
    from sqlalchemy import text
    row = conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:n"
    ), {"n": name}).fetchone()
    return row is not None


def _add_columns(conn):
    from sqlalchemy import text
    for table, col, col_type in NEW_COLUMNS:
        if not _table_exists(conn, table):
            print(f"  Skipping {table}.{col} — table not present yet")
            continue
        existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}
        if col not in existing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
            print(f"  Added column: {table}.{col}")
        else:
            print(f"  Already exists: {table}.{col}")


def _ensure_default_stores(conn):
    from sqlalchemy import text

    if not _table_exists(conn, "pharmacy_stores"):
        print("  Skipping store backfill — pharmacy_stores table not present yet")
        return

    hospital_ids = set()
    for tbl in BACKFILL_TABLES + ["medicines"]:
        if not _table_exists(conn, tbl):
            continue
        if not _table_exists(conn, "hospitals"):
            break
        rows = conn.execute(text(f"SELECT DISTINCT hospital_id FROM {tbl} WHERE hospital_id IS NOT NULL")).fetchall()
        hospital_ids.update(r[0] for r in rows if r[0] is not None)

    if not hospital_ids and _table_exists(conn, "hospitals"):
        rows = conn.execute(text("SELECT id FROM hospitals")).fetchall()
        hospital_ids.update(r[0] for r in rows)

    for hid in sorted(hospital_ids):
        existing = conn.execute(text(
            "SELECT id FROM pharmacy_stores WHERE hospital_id = :hid AND is_default = 1 LIMIT 1"
        ), {"hid": hid}).fetchone()
        if existing:
            default_id = existing[0]
        else:
            conn.execute(text("""
                INSERT INTO pharmacy_stores
                    (code, name, store_type, can_receive_supplier_purchase, is_active, is_default, hospital_id)
                VALUES
                    ('MAIN', 'Main Pharmacy', 'master', 1, 1, 1, :hid)
            """), {"hid": hid})
            default_id = conn.execute(text("SELECT last_insert_rowid()")).scalar()
            print(f"  Created default master store (id={default_id}) for hospital {hid}")

        for tbl in BACKFILL_TABLES:
            if not _table_exists(conn, tbl):
                continue
            cols = {row[1] for row in conn.execute(text(f"PRAGMA table_info({tbl})")).fetchall()}
            if "store_id" not in cols:
                continue
            result = conn.execute(text(f"""
                UPDATE {tbl} SET store_id = :sid WHERE hospital_id = :hid AND store_id IS NULL
            """), {"sid": default_id, "hid": hid})
            if result.rowcount:
                print(f"  Backfilled {tbl}.store_id for hospital {hid}: {result.rowcount} rows")


def migrate():
    with engine.connect() as conn:
        _add_columns(conn)
        _ensure_default_stores(conn)
        conn.commit()


if __name__ == "__main__":
    migrate()
    print("Pharmacy stores migration complete")
