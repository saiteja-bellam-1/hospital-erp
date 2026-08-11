"""Shared pharmacy stock / sold-qty helpers.

Keeps purchase revoke, transfer revoke, and sale restoration consistent:
net sold = outbound sale/rx_dispense minus inbound return_in/rx_cancel.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.models.pharmacy import PharmacyInventory, PharmacyStockLedger


# Ledger types that remove sellable stock from a batch.
_OUTBOUND_TXNS = ("sale", "rx_dispense")
# Ledger types that put stock back (void/edit/cancel/sale return). Not purchase/transfer.
_INBOUND_TXNS = ("return_in", "rx_cancel", "sale_return")


def net_sold_qty_for_batch(db: Session, batch_id: Optional[int]) -> float:
    """Units still considered sold/dispensed after voids and Rx cancels.

    Used by purchase/transfer revoke to decide how much received stock is
    still "spoken for" and must not be reversed.
    """
    if not batch_id:
        return 0.0
    outbound = db.query(sa_func.coalesce(sa_func.sum(PharmacyStockLedger.qty_delta), 0)).filter(
        PharmacyStockLedger.batch_id == batch_id,
        PharmacyStockLedger.txn_type.in_(_OUTBOUND_TXNS),
    ).scalar() or 0
    inbound = db.query(sa_func.coalesce(sa_func.sum(PharmacyStockLedger.qty_delta), 0)).filter(
        PharmacyStockLedger.batch_id == batch_id,
        PharmacyStockLedger.txn_type.in_(_INBOUND_TXNS),
    ).scalar() or 0
    # Outbound deltas are negative; inbound positive.
    net = abs(float(outbound)) - abs(float(inbound))
    return max(0.0, net)


def credit_batch_stock(batch: PharmacyInventory, qty: float) -> float:
    """Add qty to a batch and reactivate when stock becomes positive.

    Returns the credited amount (0 if qty <= 0).
    """
    give = float(qty or 0)
    if give <= 0 or batch is None:
        return 0.0
    batch.quantity_in_stock = float(batch.quantity_in_stock or 0) + give
    if (batch.quantity_in_stock or 0) > 0:
        batch.is_active = True
    return give


def debit_batch_stock(batch: PharmacyInventory, qty: float) -> float:
    """Remove qty from a batch. Raises ValueError if insufficient stock.

    Returns the debited amount.
    """
    take = float(qty or 0)
    if take <= 0 or batch is None:
        return 0.0
    have = float(batch.quantity_in_stock or 0)
    if have + 1e-9 < take:
        raise ValueError(
            f"Insufficient stock on batch {batch.id}: need {take}, have {have}"
        )
    batch.quantity_in_stock = have - take
    if (batch.quantity_in_stock or 0) <= 0:
        batch.quantity_in_stock = 0.0
        batch.is_active = False
    return take


def append_stock_ledger(
    db: Session,
    *,
    medicine_id: int,
    batch_id: int,
    txn_type: str,
    qty_delta: float,
    reference_type: str,
    reference_id: int,
    performed_by: Optional[int],
    hospital_id: int,
    store_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> PharmacyStockLedger:
    row = PharmacyStockLedger(
        medicine_id=medicine_id,
        batch_id=batch_id,
        txn_type=txn_type,
        qty_delta=float(qty_delta),
        reference_type=reference_type,
        reference_id=reference_id,
        performed_by=performed_by,
        notes=notes,
        store_id=store_id,
        hospital_id=hospital_id,
    )
    db.add(row)
    return row


def sale_has_sale_ledger_rows(db: Session, sale_id: int) -> bool:
    """True when stock for this sale was deducted via txn_type='sale'.

    Cash Rx dispense creates a PharmacySale without sale ledger rows (stock
    was deducted via rx_dispense). Void must not return_in in that case.
    """
    row = (
        db.query(PharmacyStockLedger.id)
        .filter(
            PharmacyStockLedger.reference_type == "sale",
            PharmacyStockLedger.reference_id == sale_id,
            PharmacyStockLedger.txn_type == "sale",
        )
        .first()
    )
    return row is not None
