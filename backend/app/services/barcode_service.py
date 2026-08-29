"""EAN-13 barcode generation, validation, and assignment for lab + pharmacy."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.lab import PatientLabOrder
from app.models.patient import Patient
from app.models.pharmacy import Medicine, PharmacyInventory

# Internal EAN-13 body prefixes (first 2 digits of the 12-digit payload).
PREFIX_LAB_SAMPLE = "20"
PREFIX_PATIENT = "21"
PREFIX_PHARMACY_ITEM = "22"
PREFIX_PHARMACY_BATCH = "23"


def compute_ean13_check_digit(digits12: str) -> int:
    """Compute EAN-13 check digit for a 12-digit string."""
    if len(digits12) != 12 or not digits12.isdigit():
        raise ValueError("EAN-13 body must be 12 digits")
    total = 0
    for i, ch in enumerate(digits12):
        n = int(ch)
        total += n * (1 if i % 2 == 0 else 3)
    return (10 - (total % 10)) % 10


def full_ean13(digits12: str) -> str:
    return f"{digits12}{compute_ean13_check_digit(digits12)}"


def validate_ean13(code: str) -> bool:
    digits = "".join(c for c in (code or "") if c.isdigit())
    if len(digits) != 13:
        return False
    body, check = digits[:12], int(digits[12])
    return compute_ean13_check_digit(body) == check


def normalize_scanned_barcode(raw: str) -> Optional[str]:
    """Normalize scanner input to a valid 13-digit EAN-13 string."""
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if len(digits) == 12:
        return full_ean13(digits)
    if len(digits) == 13 and validate_ean13(digits):
        return digits
    return None


def normalize_manufacturer_barcode(raw: str) -> Optional[str]:
    """Validate and normalize a manufacturer-supplied EAN-13."""
    code = normalize_scanned_barcode(raw)
    if not code:
        return None
    # Reject our internal prefixes when entered as manufacturer codes.
    if code.startswith((PREFIX_LAB_SAMPLE, PREFIX_PATIENT, PREFIX_PHARMACY_ITEM, PREFIX_PHARMACY_BATCH)):
        return None
    return code


def mrn_digits_payload(mrn: str) -> Optional[str]:
    """Build a 12-digit EAN body from a purely numeric MRN (rare)."""
    digits = "".join(c for c in (mrn or "") if c.isdigit())
    if len(digits) == 12 and digits.isdigit():
        return digits
    if len(digits) == 13 and validate_ean13(digits):
        return digits[:12]
    return None


def generate_lab_sample_ean13(db: Session, hospital_id: int) -> str:
    """Next lab sample EAN-13: 20 + YYMMDD + 4-digit daily sequence."""
    today = datetime.now().strftime("%y%m%d")
    prefix12 = f"{PREFIX_LAB_SAMPLE}{today}"
    last = (
        db.query(PatientLabOrder.sample_ean13)
        .filter(PatientLabOrder.sample_ean13.like(f"{prefix12}%"))
        .order_by(PatientLabOrder.sample_ean13.desc())
        .first()
    )
    seq = 1
    if last and last[0]:
        try:
            seq = int(last[0][-4:]) + 1
        except ValueError:
            seq = 1
    if seq > 9999:
        raise ValueError("Daily lab sample barcode sequence exhausted")
    body = f"{prefix12}{seq:04d}"
    return full_ean13(body)


def generate_patient_mrn_ean13(patient_id: int) -> str:
    """Internal patient scan code: 21 + zero-padded patient id."""
    if patient_id <= 0 or patient_id > 9999999999:
        raise ValueError("Invalid patient id for EAN-13")
    body = f"{PREFIX_PATIENT}{patient_id:010d}"
    return full_ean13(body)


def ensure_patient_mrn_ean13(db: Session, patient: Patient) -> str:
    if patient.mrn_ean13 and validate_ean13(patient.mrn_ean13):
        return patient.mrn_ean13
    mrn_body = mrn_digits_payload(patient.mrn or "")
    if mrn_body:
        code = full_ean13(mrn_body)
    else:
        code = generate_patient_mrn_ean13(patient.id)
    patient.mrn_ean13 = code
    db.flush()
    return code


def generate_pharmacy_item_ean13(medicine_id: int) -> str:
    body = f"{PREFIX_PHARMACY_ITEM}{medicine_id:010d}"
    return full_ean13(body)


def generate_batch_ean13(inventory_id: int) -> str:
    body = f"{PREFIX_PHARMACY_BATCH}{inventory_id:010d}"
    return full_ean13(body)


def barcode_exists_for_medicine(
    db: Session,
    hospital_id: int,
    barcode: str,
    exclude_id: Optional[int] = None,
) -> bool:
    q = db.query(Medicine.id).filter(
        Medicine.hospital_id == hospital_id,
        Medicine.barcode == barcode,
    )
    if exclude_id is not None:
        q = q.filter(Medicine.id != exclude_id)
    return q.first() is not None


def barcode_exists_for_batch(
    db: Session,
    hospital_id: int,
    batch_barcode: str,
    exclude_id: Optional[int] = None,
) -> bool:
    q = db.query(PharmacyInventory.id).filter(
        PharmacyInventory.hospital_id == hospital_id,
        PharmacyInventory.batch_barcode == batch_barcode,
    )
    if exclude_id is not None:
        q = q.filter(PharmacyInventory.id != exclude_id)
    return q.first() is not None


def resolve_medicine_barcode(
    db: Session,
    hospital_id: int,
    raw_barcode: Optional[str],
    medicine_id: int,
    *,
    auto_generate: bool = True,
) -> Tuple[str, str]:
    """
    Return (barcode, source) where source is 'manufacturer' or 'internal'.
  Raises ValueError on invalid or duplicate barcode.
    """
    if raw_barcode and str(raw_barcode).strip():
        code = normalize_manufacturer_barcode(str(raw_barcode).strip())
        if not code:
            code = normalize_scanned_barcode(str(raw_barcode).strip())
        if not code:
            raise ValueError("Barcode must be a valid EAN-13 (12 or 13 digits)")
        if barcode_exists_for_medicine(db, hospital_id, code, exclude_id=medicine_id):
            raise ValueError("Barcode already assigned to another medicine")
        return code, "manufacturer"
    if not auto_generate:
        raise ValueError("Barcode is required")
    code = generate_pharmacy_item_ean13(medicine_id)
    # Collision guard (extremely unlikely with id-based encoding).
    if barcode_exists_for_medicine(db, hospital_id, code, exclude_id=medicine_id):
        raise ValueError("Generated medicine barcode collision — contact support")
    return code, "internal"


def assign_batch_barcode(
    db: Session,
    inventory: PharmacyInventory,
    hospital_id: int,
) -> Tuple[str, str]:
    if inventory.batch_barcode and validate_ean13(inventory.batch_barcode):
        return inventory.batch_barcode, inventory.batch_barcode_source or "internal"
    code = generate_batch_ean13(inventory.id)
    if barcode_exists_for_batch(db, hospital_id, code, exclude_id=inventory.id):
        raise ValueError("Generated batch barcode collision")
    inventory.batch_barcode = code
    inventory.batch_barcode_source = "internal"
    db.flush()
    return code, "internal"


def ensure_sample_ean13_for_order(db: Session, order: PatientLabOrder, hospital_id: int) -> str:
    if order.sample_ean13 and validate_ean13(order.sample_ean13):
        return order.sample_ean13
    code = generate_lab_sample_ean13(db, hospital_id)
    order.sample_ean13 = code
    db.flush()
    return code
