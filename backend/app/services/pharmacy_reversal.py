"""Pharmacy reversal helpers.

Owns the logic for cancelling a Prescription and, when needed, emitting a
credit-note bill to offset an inpatient bill that has already been finalized
(and possibly paid).

See `TODO_PHARMACY_GAPS.md` P0 #1 for the design notes and the hybrid policy
this implements:

  * Rx not yet billed (`inpatient_bill_id IS NULL`):
      → just mark Rx cancelled and reverse the dispensed stock. The next call
        to `_compute_admission_charges` skips it because the status filter
        already excludes `cancelled`.

  * Rx billed but parent bill is "unlocked"
      (status in ('pending',) AND bill_subtype != 'final' AND no payments):
      → unset `inpatient_bill_id`, delete the matching BillItem(s) from the
        parent bill, recompute parent totals. No credit-note needed because
        the bill hasn't been issued/paid.

  * Rx billed AND parent bill is "locked"
      (any of: final subtype, payments recorded, status paid/partial/cancelled):
      → create a credit-note Bill (`bill_type='credit_note'`,
        `parent_bill_id=original.id`) with negative BillItem(s) keyed by the
        same `source_ref_*`. Original bill is left untouched.

Stock is always reversed via `PharmacyStockLedger txn_type='rx_cancel'`. The
deduction loop walks the per-item dispense ledger entries and re-credits
exactly those batches that were debited.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.billing import Bill, BillItem, Payment
from app.models.pharmacy import (
    Medicine,
    PharmacyInventory,
    PharmacySale,
    PharmacyStockLedger,
    Prescription,
    PrescriptionItem,
)
from app.models.patient import Patient
from app.services.audit_service import log_action


# Statuses that mean the Rx can still be cancelled (idempotent cancel is not
# allowed — caller gets a 400 if Rx is already cancelled).
_CANCELLABLE_STATUSES = {"pending", "partial", "dispensed"}


def _is_bill_locked(db: Session, bill: Bill) -> bool:
    """Bill is "locked" if any of: final subtype, non-pending status, or any
    payment row has been recorded against it.

    Locked → reversal must be via credit-note. Unlocked → bill is still a
    draft and we can mutate items / totals in place.
    """
    if (bill.bill_subtype or "").lower() == "final":
        return True
    if (bill.status or "pending") != "pending":
        return True
    has_payment = db.query(Payment).filter(Payment.bill_id == bill.id).first()
    return has_payment is not None


def _next_credit_note_number(db: Session) -> str:
    """Mirrors the BILL-ADM-YYYYMMDD-#### scheme used by _persist_bill, but
    with a CN-ADM-... prefix so the two namespaces never collide."""
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"CN-ADM-{today}-"
    last = (
        db.query(Bill)
        .filter(Bill.bill_number.like(f"{prefix}%"))
        .order_by(Bill.id.desc())
        .first()
    )
    seq = (int(last.bill_number.split("-")[-1]) + 1) if last else 1
    return f"{prefix}{seq:04d}"


def _reverse_dispensed_stock(
    db: Session, rx: Prescription, user_id: int, hospital_id: int, reason: str
) -> int:
    """For each `rx_dispense` ledger row tied to this Rx, write an opposing
    `rx_cancel` row and credit the qty back to the original batch.

    Returns the number of ledger rows written.
    """
    dispense_rows = (
        db.query(PharmacyStockLedger)
        .filter(
            PharmacyStockLedger.txn_type == "rx_dispense",
            PharmacyStockLedger.reference_type == "prescription",
            PharmacyStockLedger.reference_id == rx.id,
        )
        .all()
    )
    written = 0
    for row in dispense_rows:
        # qty_delta on a rx_dispense is negative; the cancel re-credits that
        # exact amount (positive) back to the same batch.
        give_back = -float(row.qty_delta or 0)
        if give_back <= 0:
            continue
        batch = (
            db.query(PharmacyInventory)
            .filter(PharmacyInventory.id == row.batch_id)
            .with_for_update()
            .first()
        )
        if not batch:
            continue
        batch.quantity_in_stock = (batch.quantity_in_stock or 0) + give_back
        db.add(PharmacyStockLedger(
            medicine_id=row.medicine_id,
            batch_id=batch.id,
            txn_type="rx_cancel",
            qty_delta=give_back,
            reference_type="prescription",
            reference_id=rx.id,
            performed_by=user_id,
            hospital_id=hospital_id,
            notes=f"Cancel Rx {rx.prescription_number}: {reason}",
        ))
        written += 1
    # Roll back the per-item counters.
    items = (
        db.query(PrescriptionItem)
        .filter(PrescriptionItem.prescription_id == rx.id)
        .all()
    )
    for it in items:
        it.quantity_dispensed = 0
        it.status = "pending"
    return written


def _unlocked_bill_inplace_reverse(db: Session, rx: Prescription, bill: Bill) -> int:
    """Delete the pharmacy BillItem rows on the unlocked parent bill that
    point back at this Rx, and decrement the bill totals accordingly.

    Returns the number of bill items removed.
    """
    item_ids = [it.id for it in rx.items]
    if not item_ids:
        return 0
    bill_items = (
        db.query(BillItem)
        .filter(
            BillItem.bill_id == bill.id,
            BillItem.source_ref_type == "prescription_item",
            BillItem.source_ref_id.in_(item_ids),
        )
        .all()
    )
    removed_total = 0.0
    for bi in bill_items:
        removed_total += float(bi.total_price or 0)
        db.delete(bi)
    if removed_total > 0:
        # Subtotal/total math on un-finalized bills is naive (no tax/discount
        # baked in yet for pharmacy lines as of the current pricing flow), so
        # subtract from both subtotal and total_amount directly.
        bill.subtotal = max(0.0, float(bill.subtotal or 0) - removed_total)
        bill.total_amount = max(0.0, float(bill.total_amount or 0) - removed_total)
    rx.inpatient_bill_id = None
    return len(bill_items)


def _emit_credit_note(
    db: Session,
    rx: Prescription,
    parent_bill: Bill,
    user_id: int,
    reason: str,
) -> Bill:
    """Issue a `credit_note` Bill against `parent_bill` with one negative
    BillItem per pharmacy line tracable to this Rx."""
    item_ids = [it.id for it in rx.items]
    parent_lines = (
        db.query(BillItem)
        .filter(
            BillItem.bill_id == parent_bill.id,
            BillItem.source_ref_type == "prescription_item",
            BillItem.source_ref_id.in_(item_ids),
        )
        .all()
    )
    if not parent_lines:
        # No source_ref linkage (likely a bill emitted before the migration
        # landed). Fall back to summing the Rx total; cashier-visible label
        # makes the offset explicit.
        total = float(rx.total_amount or 0)
        if total <= 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cannot emit credit-note: parent bill has no source_ref "
                    "linkage and Rx has no total_amount to offset against."
                ),
            )
        cn = Bill(
            bill_number=_next_credit_note_number(db),
            patient_id=parent_bill.patient_id,
            bill_type="credit_note",
            bill_subtype="final",
            reference_id=parent_bill.reference_id,
            subtotal=-total,
            tax_amount=0.0,
            discount_amount=0.0,
            total_amount=-total,
            status="pending",
            created_by_id=user_id,
            hospital_id=parent_bill.hospital_id,
            parent_bill_id=parent_bill.id,
            notes=f"Credit note for cancelled Rx {rx.prescription_number}: {reason}",
        )
        db.add(cn)
        db.flush()
        db.add(BillItem(
            bill_id=cn.id,
            item_type="pharmacy",
            item_name=f"Reversal: Rx {rx.prescription_number}",
            quantity=1,
            unit_price=-total,
            total_price=-total,
            source_ref_type="prescription",
            source_ref_id=rx.id,
        ))
        return cn

    subtotal = sum(float(li.total_price or 0) for li in parent_lines)
    cn = Bill(
        bill_number=_next_credit_note_number(db),
        patient_id=parent_bill.patient_id,
        bill_type="credit_note",
        bill_subtype="final",
        reference_id=parent_bill.reference_id,
        subtotal=-subtotal,
        tax_amount=0.0,
        discount_amount=0.0,
        total_amount=-subtotal,
        status="pending",
        created_by_id=user_id,
        hospital_id=parent_bill.hospital_id,
        parent_bill_id=parent_bill.id,
        notes=f"Credit note for cancelled Rx {rx.prescription_number}: {reason}",
    )
    db.add(cn)
    db.flush()
    for li in parent_lines:
        db.add(BillItem(
            bill_id=cn.id,
            item_type="pharmacy",
            item_name=f"Reversal: {li.item_name}",
            quantity=li.quantity,
            unit_price=-float(li.unit_price or 0),
            total_price=-float(li.total_price or 0),
            source_ref_type="prescription_item",
            source_ref_id=li.source_ref_id,
        ))
    return cn


def _unlocked_bill_inplace_reverse_pos_sale(db: Session, sale: PharmacySale, bill: Bill) -> int:
    """Remove POS sale line items from an unlocked parent admission bill."""
    sale_item_ids = [it.id for it in (sale.items or [])]
    if not sale_item_ids:
        sale.inpatient_bill_id = None
        return 0
    bill_items = (
        db.query(BillItem)
        .filter(
            BillItem.bill_id == bill.id,
            BillItem.source_ref_type == "pharmacy_sale_item",
            BillItem.source_ref_id.in_(sale_item_ids),
        )
        .all()
    )
    removed_total = 0.0
    for bi in bill_items:
        removed_total += float(bi.total_price or 0)
        db.delete(bi)
    if removed_total > 0:
        bill.subtotal = max(0.0, float(bill.subtotal or 0) - removed_total)
        bill.total_amount = max(0.0, float(bill.total_amount or 0) - removed_total)
    sale.inpatient_bill_id = None
    return len(bill_items)


def _emit_credit_note_pos_sale(
    db: Session,
    sale: PharmacySale,
    parent_bill: Bill,
    user_id: int,
    reason: str,
) -> Bill:
    sale_item_ids = [it.id for it in (sale.items or [])]
    parent_lines = (
        db.query(BillItem)
        .filter(
            BillItem.bill_id == parent_bill.id,
            BillItem.source_ref_type == "pharmacy_sale_item",
            BillItem.source_ref_id.in_(sale_item_ids),
        )
        .all()
    )
    if not parent_lines:
        total = float(sale.grand_total or 0)
        if total <= 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cannot emit credit-note: parent bill has no source_ref "
                    "linkage and sale has no grand_total to offset against."
                ),
            )
        cn = Bill(
            bill_number=_next_credit_note_number(db),
            patient_id=parent_bill.patient_id,
            bill_type="credit_note",
            bill_subtype="final",
            reference_id=parent_bill.reference_id,
            subtotal=-total,
            tax_amount=0.0,
            discount_amount=0.0,
            total_amount=-total,
            status="pending",
            created_by_id=user_id,
            hospital_id=parent_bill.hospital_id,
            parent_bill_id=parent_bill.id,
            notes=f"Credit note for voided POS sale {sale.sale_number}: {reason}",
        )
        db.add(cn)
        db.flush()
        db.add(BillItem(
            bill_id=cn.id,
            item_type="pharmacy",
            item_name=f"Reversal: POS {sale.sale_number}",
            quantity=1,
            unit_price=-total,
            total_price=-total,
            source_ref_type="pharmacy_sale",
            source_ref_id=sale.id,
        ))
        return cn

    subtotal = sum(float(li.total_price or 0) for li in parent_lines)
    cn = Bill(
        bill_number=_next_credit_note_number(db),
        patient_id=parent_bill.patient_id,
        bill_type="credit_note",
        bill_subtype="final",
        reference_id=parent_bill.reference_id,
        subtotal=-subtotal,
        tax_amount=0.0,
        discount_amount=0.0,
        total_amount=-subtotal,
        status="pending",
        created_by_id=user_id,
        hospital_id=parent_bill.hospital_id,
        parent_bill_id=parent_bill.id,
        notes=f"Credit note for voided POS sale {sale.sale_number}: {reason}",
    )
    db.add(cn)
    db.flush()
    for li in parent_lines:
        db.add(BillItem(
            bill_id=cn.id,
            item_type="pharmacy",
            item_name=f"Reversal: {li.item_name}",
            quantity=li.quantity,
            unit_price=-float(li.unit_price or 0),
            total_price=-float(li.total_price or 0),
            source_ref_type="pharmacy_sale_item",
            source_ref_id=li.source_ref_id,
        ))
    return cn


def reverse_inpatient_pos_sale_bill(
    db: Session,
    sale: PharmacySale,
    user_id: int,
    reason: str,
) -> dict:
    """Reverse bill impact when voiding a POS sale charged to an admission bill."""
    credit_note_id: Optional[int] = None
    credit_note_number: Optional[str] = None
    bill_items_removed = 0
    parent_bill_id_before = sale.inpatient_bill_id

    if parent_bill_id_before:
        parent = db.query(Bill).filter(Bill.id == parent_bill_id_before).first()
        if parent is None:
            sale.inpatient_bill_id = None
        elif _is_bill_locked(db, parent):
            cn = _emit_credit_note_pos_sale(db, sale, parent, user_id=user_id, reason=reason)
            db.flush()
            credit_note_id = cn.id
            credit_note_number = cn.bill_number
            sale.inpatient_bill_id = None
        else:
            bill_items_removed = _unlocked_bill_inplace_reverse_pos_sale(db, sale, parent)

    return {
        "parent_bill_id": parent_bill_id_before,
        "bill_items_removed": bill_items_removed,
        "credit_note_id": credit_note_id,
        "credit_note_number": credit_note_number,
    }


def cancel_prescription(
    db: Session,
    rx_id: int,
    user,
    reason: str,
) -> dict:
    """Cancel a Prescription end-to-end. Caller is responsible for permission
    checking and DB commit.

    Returns a dict summarizing what happened, suitable to send back as the
    route response and to feed into the audit description.
    """
    rx = (
        db.query(Prescription)
        .join(Patient, Patient.id == Prescription.patient_id)
        .filter(
            Prescription.id == rx_id,
            Patient.hospital_id == user.hospital_id,
        )
        .first()
    )
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    if rx.status == "cancelled":
        raise HTTPException(status_code=400, detail="Prescription is already cancelled")
    if rx.status not in _CANCELLABLE_STATUSES:
        raise HTTPException(
            status_code=400, detail=f"Cannot cancel prescription in status '{rx.status}'"
        )

    # Step 1 — stock reversal (always).
    stock_rows_written = _reverse_dispensed_stock(
        db, rx, user_id=user.id, hospital_id=user.hospital_id, reason=reason
    )

    # Step 2 — bill handling.
    credit_note_id: Optional[int] = None
    credit_note_number: Optional[str] = None
    bill_items_removed = 0
    parent_bill_id_before = rx.inpatient_bill_id

    if parent_bill_id_before:
        parent = db.query(Bill).filter(Bill.id == parent_bill_id_before).first()
        if parent is None:
            # Defensive: orphan link. Treat as un-billed.
            rx.inpatient_bill_id = None
        elif _is_bill_locked(db, parent):
            cn = _emit_credit_note(db, rx, parent, user_id=user.id, reason=reason)
            db.flush()
            credit_note_id = cn.id
            credit_note_number = cn.bill_number
        else:
            bill_items_removed = _unlocked_bill_inplace_reverse(db, rx, parent)

    # Step 3 — stamp the Rx itself.
    rx.status = "cancelled"
    rx.cancelled_at = datetime.now()
    rx.cancelled_by_id = user.id
    rx.cancel_reason = reason

    db.flush()

    summary = {
        "prescription_id": rx.id,
        "prescription_number": rx.prescription_number,
        "status": rx.status,
        "stock_ledger_rows_written": stock_rows_written,
        "parent_bill_id": parent_bill_id_before,
        "bill_items_removed": bill_items_removed,
        "credit_note_id": credit_note_id,
        "credit_note_number": credit_note_number,
        "reason": reason,
    }

    log_action(
        db=db,
        user=user,
        action="cancel_rx",
        category="pharmacy",
        resource_type="prescription",
        resource_id=rx.id,
        description=(
            f"Cancelled Rx {rx.prescription_number} "
            f"(stock_rows={stock_rows_written}, bill_items_removed={bill_items_removed}, "
            f"credit_note={credit_note_number or '-'}): {reason}"
        ),
        details=summary,
    )

    return summary
