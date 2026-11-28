import React, { useState } from 'react';
import { Button } from '../ui/button';
import CollectPaymentDialog from './CollectPaymentDialog';

/** Group part-paid lab orders by the bill they belong to. */
export const groupPartialLabBills = (orders = []) => Object.values(
  orders
    .filter((o) => o.payment_status === 'partial' && o.status !== 'cancelled' && Number(o.balance_due) > 0)
    .reduce((acc, o) => {
      const key = o.lab_bill_group_id || `order-${o.id}`;
      const g = acc[key] || {
        key,
        groupId: o.lab_bill_group_id,
        orderId: o.id,
        billNumber: o.lab_bill_number || o.order_number,
        orders: [],
        balance: 0,
      };
      g.orders.push(o);
      g.balance += Number(o.balance_due) || 0;
      acc[key] = g;
      return acc;
    }, {})
);

/**
 * "Balance due" list for lab bills that were part-paid, with a Collect
 * button that opens the shared CollectPaymentDialog against the lab bill.
 */
export default function LabBalanceDueList({ orders, onPaid, showDivider = false }) {
  const [active, setActive] = useState(null);
  const groups = groupPartialLabBills(orders);
  if (groups.length === 0) return null;

  // Grouped bills use the lab endpoint (reception / front-desk roles);
  // a stray ungrouped order falls back to the billing-row endpoint.
  const url = active
    ? (active.groupId
      ? `/api/lab/bills/${encodeURIComponent(active.groupId)}/payments`
      : `/api/hospital/billing/rows/${encodeURIComponent(`LAB-${active.orderId}`)}/payments`)
    : null;

  return (
    <>
      {showDivider && <hr className="my-2" />}
      <p className="text-sm font-medium text-gray-700">Balance Due ({groups.length})</p>
      <div className="border rounded-lg divide-y">
        {groups.map((g) => (
          <div key={g.key} className="p-3 flex items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="font-medium text-sm truncate">{g.orders.map((o) => o.test_name).filter(Boolean).join(', ')}</p>
              <p className="text-xs text-gray-500">{g.billNumber}</p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span className="text-sm font-semibold text-amber-700">₹{g.balance.toFixed(2)}</span>
              <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setActive(g)}>
                Collect
              </Button>
            </div>
          </div>
        ))}
      </div>
      <CollectPaymentDialog
        open={!!active}
        onOpenChange={(o) => { if (!o) setActive(null); }}
        infoUrl={url}
        postUrl={url}
        subtitle={active ? `Lab bill ${active.billNumber}` : ''}
        onSuccess={(data) => onPaid?.(data, active)}
      />
    </>
  );
}
