#!/usr/bin/env python3
"""
Pharmacy module migration.

Idempotent additive column adds for the pharmacy module. Safe to run multiple
times — skips columns that already exist. New tables are picked up by
`create_all()`; only additive ALTERs go here.

Sections B–F append rows to NEW_COLUMNS as fields are introduced.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.database import engine

# (table, column, type_with_defaults_and_fks)
# Pharmacy schema additions live here. Sections B–F append as needed.
NEW_COLUMNS = [
    # --- Section B: Catalog / master data ---
    ("medicines", "is_hidden", "BOOLEAN DEFAULT 0"),
    ("medicines", "barcode", "VARCHAR(50)"),
    ("medicines", "packaging", "VARCHAR(100)"),
    ("medicines", "decimal_supported", "BOOLEAN DEFAULT 0"),
    ("medicines", "strip_conversion_factor", "INTEGER DEFAULT 1"),
    ("medicines", "is_schedule_h", "BOOLEAN DEFAULT 0"),
    ("medicines", "is_schedule_h1", "BOOLEAN DEFAULT 0"),
    ("medicines", "is_tramadol", "BOOLEAN DEFAULT 0"),
    ("medicines", "is_controlled", "BOOLEAN DEFAULT 0"),
    ("medicines", "item_discount_pct", "FLOAT DEFAULT 0.0"),
    ("medicines", "company_id", "INTEGER REFERENCES pharmacy_companies(id)"),
    ("medicines", "rack_id", "INTEGER REFERENCES pharmacy_racks(id)"),
    ("medicines", "salt_id", "INTEGER REFERENCES pharmacy_salts(id)"),
    ("medicines", "uom_id", "INTEGER REFERENCES pharmacy_uoms(id)"),

    # --- Section C: Taxation & pricing ---
    ("medicines", "mrp", "FLOAT DEFAULT 0.0"),
    ("medicines", "purchase_rate", "FLOAT DEFAULT 0.0"),
    ("medicines", "rate_a", "FLOAT DEFAULT 0.0"),
    ("medicines", "rate_b", "FLOAT DEFAULT 0.0"),
    ("medicines", "cost_pcs", "FLOAT DEFAULT 0.0"),
    ("medicines", "default_discount_pct", "FLOAT DEFAULT 0.0"),
    ("medicines", "hsn_id", "INTEGER REFERENCES pharmacy_hsn_codes(id)"),

    # --- Section D: Inventory & batch ledger ---
    ("medicines", "min_qty", "INTEGER DEFAULT 0"),
    ("medicines", "max_qty", "INTEGER DEFAULT 0"),
    ("medicines", "reorder_qty", "INTEGER DEFAULT 0"),
    ("pharmacy_inventory", "mrp", "FLOAT DEFAULT 0.0"),
    ("pharmacy_inventory", "purchase_rate", "FLOAT DEFAULT 0.0"),
    ("pharmacy_inventory", "free_quantity", "INTEGER DEFAULT 0"),
    ("pharmacy_inventory", "discount_pct", "FLOAT DEFAULT 0.0"),
    ("pharmacy_inventory", "hsn_id", "INTEGER REFERENCES pharmacy_hsn_codes(id)"),
    ("pharmacy_inventory", "supplier_id", "INTEGER REFERENCES pharmacy_suppliers(id)"),
    ("pharmacy_inventory", "purchase_id", "INTEGER"),

    # --- Section E: Procurement ---
    # (filled in by section E)

    # --- Section F: Sales — POS ---
    # (filled in by section F)

    # --- Supplier master expansion (Marg ledger-screen parity) ---
    ("pharmacy_suppliers", "station", "VARCHAR(100)"),
    ("pharmacy_suppliers", "account_group", "VARCHAR(60) DEFAULT 'Sundry Creditors'"),
    ("pharmacy_suppliers", "balancing_method", "VARCHAR(30) DEFAULT 'bill_by_bill'"),
    ("pharmacy_suppliers", "opening_balance", "FLOAT DEFAULT 0.0"),
    ("pharmacy_suppliers", "opening_balance_dr_cr", "VARCHAR(2) DEFAULT 'Dr'"),
    ("pharmacy_suppliers", "hold_payment", "BOOLEAN DEFAULT 0"),
    ("pharmacy_suppliers", "hold_payment_pct", "FLOAT DEFAULT 0.0"),
    ("pharmacy_suppliers", "ledger_date", "DATE"),
    ("pharmacy_suppliers", "freeze_upto", "DATE"),
    ("pharmacy_suppliers", "designation", "VARCHAR(100)"),
    ("pharmacy_suppliers", "phone_office", "VARCHAR(30)"),
    ("pharmacy_suppliers", "phone_residence", "VARCHAR(30)"),
    ("pharmacy_suppliers", "mobile", "VARCHAR(30)"),
    ("pharmacy_suppliers", "fax", "VARCHAR(30)"),
    ("pharmacy_suppliers", "website", "VARCHAR(200)"),
    ("pharmacy_suppliers", "mail_to", "VARCHAR(200)"),
    ("pharmacy_suppliers", "pin_code", "VARCHAR(15)"),
    ("pharmacy_suppliers", "state", "VARCHAR(80)"),
    ("pharmacy_suppliers", "state_code", "VARCHAR(10)"),
    ("pharmacy_suppliers", "country", "VARCHAR(60) DEFAULT 'India'"),
    ("pharmacy_suppliers", "gst_heading", "VARCHAR(20) DEFAULT 'local'"),
    ("pharmacy_suppliers", "gstin_no", "VARCHAR(30)"),
    ("pharmacy_suppliers", "gstin_date", "DATE"),
    ("pharmacy_suppliers", "dl_number", "VARCHAR(50)"),
    ("pharmacy_suppliers", "dl_expiry", "DATE"),
    ("pharmacy_suppliers", "vat_number", "VARCHAR(40)"),
    ("pharmacy_suppliers", "vat_expiry", "DATE"),
    ("pharmacy_suppliers", "st_number", "VARCHAR(40)"),
    ("pharmacy_suppliers", "st_expiry", "DATE"),
    ("pharmacy_suppliers", "food_license_no", "VARCHAR(40)"),
    ("pharmacy_suppliers", "food_license_expiry", "DATE"),
    ("pharmacy_suppliers", "extra_license_no", "VARCHAR(60)"),
    ("pharmacy_suppliers", "extra_license_expiry", "DATE"),
    ("pharmacy_suppliers", "pan_number", "VARCHAR(20)"),
    ("pharmacy_suppliers", "narco_sch_h_billing", "VARCHAR(20) DEFAULT 'allow_all'"),
    ("pharmacy_suppliers", "bill_import", "VARCHAR(20) DEFAULT 'mobile'"),
    ("pharmacy_suppliers", "ledger_category", "VARCHAR(60) DEFAULT 'OTHERS'"),
    ("pharmacy_suppliers", "ledger_type", "VARCHAR(30) DEFAULT 'unregistered'"),
    ("pharmacy_suppliers", "color_tag", "VARCHAR(20) DEFAULT 'normal'"),
    ("pharmacy_suppliers", "is_hidden", "BOOLEAN DEFAULT 0"),
]


def migrate():
    from sqlalchemy import text
    if not NEW_COLUMNS:
        print("  Pharmacy: no column additions pending")
        return
    with engine.connect() as conn:
        for table, col, col_type in NEW_COLUMNS:
            # Skip silently if the parent table doesn't exist yet (create_all
            # may not have run if a section's models were removed). The next
            # startup picks the column up after the table is materialised.
            tbl_check = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=:n"
            ), {"n": table}).fetchone()
            if not tbl_check:
                print(f"  Skipping {table}.{col} — table not present yet")
                continue
            existing = {row[1] for row in conn.execute(
                text(f"PRAGMA table_info({table})")
            ).fetchall()}
            if col not in existing:
                conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"
                ))
                print(f"  Added column: {table}.{col}")
            else:
                print(f"  Already exists: {table}.{col}")


if __name__ == "__main__":
    migrate()
    print("Pharmacy migration complete")
