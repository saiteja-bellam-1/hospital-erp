import React, { useEffect, useState } from 'react';
import axios from 'axios';

const expiryToDisplay = (iso) => {
  if (!iso) return '—';
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime()) || d.getFullYear() >= 2099) return '—';
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;
};

const formatQty = (qty, freeQty) => {
  const q = Number(qty) || 0;
  const f = Number(freeQty) || 0;
  if (f > 0) return `${q} +${f}f`;
  return String(q);
};

const formatStock = (tabs, scf) => {
  const n = Number(tabs) || 0;
  const factor = Math.max(1, parseInt(scf, 10) || 1);
  if (n <= 0) return '0';
  if (factor > 1) return `${n} tabs`;
  return String(n);
};

function SkeletonRows() {
  return (
    <>
      {[0, 1, 2].map((i) => (
        <tr key={i} className="border-b">
          {[0, 1, 2, 3, 4].map((j) => (
            <td key={j} className="py-2 pr-3">
              <div className="h-4 bg-gray-200/80 rounded animate-pulse" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

export default function PurchaseHistoryPanel({
  medicineId,
  currentBatchNumber,
  onSelectRow,
}) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!medicineId) {
      setRows([]);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    axios
      .get(`/api/pharmacy/medicines/${medicineId}/purchase-history`, { params: { limit: 20 } })
      .then((r) => {
        if (!cancelled) setRows(r.data || []);
      })
      .catch(() => {
        if (!cancelled) setRows([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [medicineId]);

  if (!medicineId) return null;

  const normalizedCurrentBatch = String(currentBatchNumber || '').trim().toLowerCase();

  return (
    <div className="rounded-md border bg-gray-50/80 px-4 py-3 shrink-0">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="font-medium text-gray-900 text-sm">
          Previous purchases
          {!loading && rows.length > 0 ? (
            <span className="text-gray-500 font-normal ml-1">({rows.length})</span>
          ) : null}
        </div>
        <span className="text-xs text-gray-400">Newest first</span>
      </div>

      <div className="max-h-[168px] overflow-y-auto overflow-x-auto rounded border bg-white">
        <table className="w-full text-sm min-w-[520px]">
          <thead className="sticky top-0 bg-gray-50 border-b text-left text-gray-600 text-xs">
            <tr>
              <th className="py-2 pl-3 pr-3 font-medium">Supplier</th>
              <th className="py-2 pr-3 font-medium">Batch</th>
              <th className="py-2 pr-3 font-medium">Expiry</th>
              <th className="py-2 pr-3 font-medium">Qty</th>
              <th className="py-2 pr-3 font-medium">Stock</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <SkeletonRows />
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-6 text-center text-sm text-gray-500">
                  No previous purchases for this medicine.
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const isSelected = normalizedCurrentBatch
                  && String(row.batch_number || '').trim().toLowerCase() === normalizedCurrentBatch;
                const zeroStock = (Number(row.quantity_in_stock) || 0) <= 0;
                return (
                  <tr
                    key={row.purchase_item_id}
                    role="button"
                    tabIndex={0}
                    className={[
                      'border-b cursor-pointer transition-colors',
                      isSelected ? 'bg-blue-100/70 border-l-2 border-l-blue-500' : 'hover:bg-blue-50/60',
                      zeroStock && !isSelected ? 'text-gray-400' : '',
                    ].filter(Boolean).join(' ')}
                    onClick={() => onSelectRow?.(row)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onSelectRow?.(row);
                      }
                    }}
                  >
                    <td className="py-2 pl-3 pr-3 text-xs max-w-[140px] truncate" title={row.supplier_name}>
                      {row.supplier_name || '—'}
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs">{row.batch_number || '—'}</td>
                    <td className="py-2 pr-3 tabular-nums text-xs">{expiryToDisplay(row.expiry_date)}</td>
                    <td className="py-2 pr-3 tabular-nums text-xs">{formatQty(row.quantity, row.free_quantity)}</td>
                    <td className="py-2 pr-3 tabular-nums text-xs">
                      {formatStock(row.quantity_in_stock, row.strip_conversion_factor)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {!loading && rows.length > 0 ? (
        <p className="text-xs text-gray-400 mt-2">Click a row to prefill batch details.</p>
      ) : null}
    </div>
  );
}
