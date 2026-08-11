"""Sales return / purchase return challan stock movements."""

from __future__ import annotations

from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.pharmacy import (
    PharmacyInventory,
    PharmacyPurchaseReturn,
    PharmacyPurchaseReturnItem,
    PharmacyReturnChallan,
    PharmacyReturnChallanItem,
    PharmacySaleReturn,
    PharmacySaleReturnItem,
)
from app.services.pharmacy_stock import (
    append_stock_ledger,
    credit_batch_stock,
    debit_batch_stock,
)


def apply_sale_return_stock(
    db: Session,
    sale_return: PharmacySaleReturn,
    items: Iterable[PharmacySaleReturnItem],
    *,
    user_id: Optional[int],
) -> None:
    """Credit batches for restock=True lines; txn_type=sale_return."""
    for it in items:
        if not it.restock:
            continue
        batch = db.query(PharmacyInventory).filter(PharmacyInventory.id == it.batch_id).first()
        if not batch:
            raise HTTPException(status_code=400, detail=f"Batch {it.batch_id} not found")
        credit_batch_stock(batch, float(it.quantity or 0))
        append_stock_ledger(
            db,
            medicine_id=it.medicine_id,
            batch_id=batch.id,
            txn_type="sale_return",
            qty_delta=float(it.quantity or 0),
            reference_type="sale_return",
            reference_id=sale_return.id,
            performed_by=user_id,
            hospital_id=sale_return.hospital_id,
            store_id=sale_return.store_id or batch.store_id,
            notes=f"Sales return {sale_return.return_number}",
        )


def challaned_qty_for_item(db: Session, purchase_return_item_id: int) -> float:
    total = (
        db.query(func.coalesce(func.sum(PharmacyReturnChallanItem.quantity), 0.0))
        .filter(PharmacyReturnChallanItem.purchase_return_item_id == purchase_return_item_id)
        .scalar()
    )
    return float(total or 0)


def remaining_challan_qty(db: Session, pr_item: PharmacyPurchaseReturnItem) -> float:
    return max(0.0, float(pr_item.quantity or 0) - challaned_qty_for_item(db, pr_item.id))


def apply_return_challan_stock(
    db: Session,
    pr: PharmacyPurchaseReturn,
    challan: PharmacyReturnChallan,
    lines: Iterable[tuple[PharmacyPurchaseReturnItem, float]],
    *,
    user_id: Optional[int],
) -> list[PharmacyReturnChallanItem]:
    """Debit batches for explicit challan lines; txn_type=return_out.

    `lines` is an iterable of (purchase_return_item, quantity_to_ship).
    """
    challan_items: list[PharmacyReturnChallanItem] = []
    for it, qty in lines:
        qty = float(qty or 0)
        if qty <= 0:
            continue
        remaining = remaining_challan_qty(db, it)
        if qty > remaining + 1e-9:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot ship {qty} of item {it.id}; only {remaining} remaining "
                    f"(return qty {it.quantity})"
                ),
            )
        batch = db.query(PharmacyInventory).filter(PharmacyInventory.id == it.batch_id).with_for_update().first()
        if not batch:
            raise HTTPException(status_code=400, detail=f"Batch {it.batch_id} not found")
        try:
            debit_batch_stock(batch, qty)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        append_stock_ledger(
            db,
            medicine_id=it.medicine_id,
            batch_id=batch.id,
            txn_type="return_out",
            qty_delta=-qty,
            reference_type="return_challan",
            reference_id=challan.id,
            performed_by=user_id,
            hospital_id=pr.hospital_id,
            store_id=challan.store_id or pr.store_id or batch.store_id,
            notes=f"Return challan {challan.challan_number} for {pr.return_number}",
        )
        ci = PharmacyReturnChallanItem(
            challan_id=challan.id,
            purchase_return_item_id=it.id,
            medicine_id=it.medicine_id,
            batch_id=batch.id,
            quantity=qty,
        )
        db.add(ci)
        challan_items.append(ci)
    if not challan_items:
        raise HTTPException(status_code=400, detail="Challan has no quantities to ship")
    return challan_items
