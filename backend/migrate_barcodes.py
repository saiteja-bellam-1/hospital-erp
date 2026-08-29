#!/usr/bin/env python3
"""Barcode unique indexes and duplicate barcode cleanup. Idempotent."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from config.database import engine


def _dedupe_medicine_barcodes(conn) -> int:
    """Clear duplicate medicine barcodes (keep lowest id per hospital+barcode)."""
    rows = conn.execute(text(
        """
        SELECT hospital_id, barcode, GROUP_CONCAT(id) AS ids, COUNT(*) AS cnt
        FROM medicines
        WHERE barcode IS NOT NULL AND TRIM(barcode) != ''
        GROUP BY hospital_id, barcode
        HAVING cnt > 1
        """
    )).fetchall()
    cleared = 0
    for hospital_id, barcode, ids_csv, _ in rows:
        id_list = [int(x) for x in str(ids_csv).split(",")]
        keep = min(id_list)
        for mid in id_list:
            if mid == keep:
                continue
            conn.execute(text(
                "UPDATE medicines SET barcode = NULL, barcode_source = NULL WHERE id = :id"
            ), {"id": mid})
            cleared += 1
        print(f"  Deduped medicine barcode {barcode} hospital={hospital_id} (kept id={keep})")
    return cleared


def migrate():
    with engine.connect() as conn:
        conn.execute(text(
            "UPDATE medicines SET barcode = NULL, barcode_source = NULL "
            "WHERE barcode IS NOT NULL AND TRIM(barcode) = ''"
        ))
        conn.execute(text(
            "UPDATE pharmacy_inventory SET batch_barcode = NULL, batch_barcode_source = NULL "
            "WHERE batch_barcode IS NOT NULL AND TRIM(batch_barcode) = ''"
        ))
        cleared = _dedupe_medicine_barcodes(conn)
        if cleared:
            print(f"  Cleared {cleared} duplicate medicine barcode(s)")

        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_patients_hospital_mrn_ean13 "
            "ON patients(hospital_id, mrn_ean13) WHERE mrn_ean13 IS NOT NULL"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_medicines_hospital_barcode "
            "ON medicines(hospital_id, barcode) WHERE barcode IS NOT NULL"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_pharmacy_inventory_hospital_batch_barcode "
            "ON pharmacy_inventory(hospital_id, batch_barcode) WHERE batch_barcode IS NOT NULL"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_patient_lab_orders_sample_ean13 "
            "ON patient_lab_orders(sample_ean13)"
        ))
        print("  Barcode indexes ensured")
        conn.commit()


if __name__ == "__main__":
    migrate()
    print("Barcode migration complete")
