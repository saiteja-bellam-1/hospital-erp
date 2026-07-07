/** Sum tablets originally sold from each batch on this bill (for edit stock credit). */
export function originalQtyCreditByBatch(items) {
  const map = {};
  for (const ln of items || []) {
    const bid = ln.original_batch_id;
    const qty = parseFloat(ln.original_batch_qty) || 0;
    if (bid && qty > 0) {
      map[bid] = (map[bid] || 0) + qty;
    }
  }
  return map;
}

/** Shelf qty + credit from this sale when editing the same batch. */
export function batchEditPoolAvail(ln, items, isEditing) {
  if (!ln?.batch_id || !ln.batch) return 0;
  const shelf = parseFloat(ln.batch.quantity_in_stock) || 0;
  if (!isEditing) return shelf;
  const credit = originalQtyCreditByBatch(items)[ln.batch_id] || 0;
  return shelf + credit;
}

/** Per-line available stock — shares batch pool across lines on the same batch. */
export function lineEditStoreStock(ln, items, isEditing, lineNeedQty) {
  if (!ln.batch_id || !ln.batch) {
    return parseFloat(ln.medicine?.store_stock_qty) || 0;
  }
  const pool = batchEditPoolAvail(ln, items, isEditing);
  if (!isEditing) return pool;
  const otherNeed = (items || [])
    .filter((other) => other !== ln && other.batch_id === ln.batch_id)
    .reduce((sum, other) => sum + lineNeedQty(other), 0);
  return Math.max(0, pool - otherNeed);
}

/** Stock error only when increasing qty beyond what is available. */
export function lineHasStockIssue(ln, items, isEditing, lineNeedQty) {
  const need = lineNeedQty(ln);
  if (need <= 0) return false;
  const originalNeed = parseFloat(ln.original_need_qty) || 0;
  if (isEditing && need <= originalNeed) return false;
  const avail = lineEditStoreStock(ln, items, isEditing, lineNeedQty);
  return need > avail;
}

/** Batch object for table display — shows edit-available qty, not raw shelf-only. */
export function batchForDisplay(ln, items, isEditing) {
  if (!ln?.batch) return null;
  if (!isEditing || !ln.batch_id) return ln.batch;
  return {
    ...ln.batch,
    quantity_in_stock: batchEditPoolAvail(ln, items, isEditing),
  };
}

/** Group API sale item rows (per-batch) back into POS cart lines. */
export function groupSaleItemsForCart(apiItems) {
  if (!apiItems?.length) return [];
  const lines = [];
  let idx = 0;
  while (idx < apiItems.length) {
    const head = apiItems[idx];
    const tabs = head.sale_qty_tabs ?? 0;
    const strips = head.sale_qty_strips ?? 0;
    let end = idx + 1;
    while (
      end < apiItems.length
      && apiItems[end].sale_qty_tabs == null
      && apiItems[end].sale_qty_strips == null
    ) {
      end += 1;
    }
    const run = apiItems.slice(idx, end);
    const batchId = run.length === 1 ? run[0].batch_id : null;
    const original_batch_qty = run.reduce(
      (sum, it) => sum + (parseFloat(it.quantity) || 0) + (parseFloat(it.free_quantity) || 0),
      0,
    );
    lines.push({
      medicine_id: head.medicine_id,
      qty_tabs: tabs,
      qty_strips: strips,
      rate_tier: head.rate_tier || 'A',
      discount_pct: head.discount_pct ?? '',
      batch_id: batchId,
      batch_number: head.batch_number || null,
      original_batch_id: batchId,
      original_batch_qty,
      barcode_scanned: !!head.barcode_scanned,
    });
    idx = end;
  }
  return lines;
}
