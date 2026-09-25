import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { QtyInput } from '../../../../components/ui/qty-input';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '../../../../components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../../../components/ui/select';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import { useToast } from '../../../../hooks/use-toast';

const titleCase = (s) => String(s || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

/** Turn the live charge breakdown into the editable lines the operator reviews. */
export async function loadReviewBillItems(admissionId) {
  const safeFetch = (path, params) => axios.get(path, params ? { params } : undefined)
    .then(r => r.data)
    .catch(() => null);
  const [billAll, billUnbilled, rxList, labList] = await Promise.all([
    safeFetch(`/api/inpatient/admissions/${admissionId}/bill`),
    safeFetch(`/api/inpatient/admissions/${admissionId}/bill`, { unbilled_only: true }),
    safeFetch(`/api/inpatient/admissions/${admissionId}/prescriptions`),
    safeFetch(`/api/inpatient/admissions/${admissionId}/lab-orders`),
  ]);
  const b = billAll || {};
  const bu = billUnbilled || {};
  const items = [];

  if (b.package && (b.package.agreed_price || 0) > 0) {
    items.push({
      source: 'package', source_id: b.package.package_id || null,
      item_type: 'package',
      item_name: `Surgery Package: ${b.package.package_name || ''}${b.package.package_code ? ' [' + b.package.package_code + ']' : ''}`,
      quantity: 1,
      unit_price: parseFloat(b.package.agreed_price || 0),
      total_price: parseFloat(b.package.agreed_price || 0),
      is_prior: !!b.package.fee_already_billed,
    });
  }

  const fullRoomTotal = b.room_total || 0;
  const unbilledRoomTotal = bu.room_total || 0;
  const billedRoomTotal = Math.max(0, Math.round((fullRoomTotal - unbilledRoomTotal) * 100) / 100);
  const packageRoomLines = (b.package?.room_lines || []).filter(line => (line.total || 0) > 0);
  const roomCoveredByPackage = !!(b.package && (
    (b.package.included_services || []).includes('room')
    || (b.package.included_stay_days || 0) > 0
    || packageRoomLines.length
  ));
  const staySegments = roomCoveredByPackage
    ? []
    : (b.room?.rate_segments || []).filter(seg => (seg.days || 0) > 0 && (seg.total || 0) > 0);
  const roomLines = packageRoomLines.length
    ? packageRoomLines.map(line => ({
      name: line.label,
      days: parseFloat(line.days || 1),
      rate: parseFloat(line.rate || 0),
      total: parseFloat(line.total || 0),
    }))
    : staySegments.map(seg => {
      const days = parseFloat(seg.days || 0);
      const dayLabel = Number.isInteger(days) ? days : days;
      return {
        name: `Room ${seg.room_number || b.room?.room_number || ''} (${seg.room_type || b.room?.room_type || ''}) — ${dayLabel} day${dayLabel === 1 ? '' : 's'}`,
        days,
        rate: parseFloat(seg.rate || 0),
        total: parseFloat(seg.total || 0),
      };
    });
  if (roomLines.length) {
    let billedLeft = billedRoomTotal;
    roomLines.forEach(line => {
      const push = (amount, dayCount, prior) => {
        if (!(amount > 0)) return;
        const shownDays = Math.max(0.01, dayCount || 1);
        items.push({
          source: 'room', source_id: null,
          item_type: 'room_charge',
          item_name: line.name,
          quantity: Math.max(1, Math.round(shownDays)),
          unit_price: line.rate,
          total_price: amount,
          is_prior: prior,
        });
      };
      if (billedLeft <= 0.009) {
        push(line.total, line.days, false);
      } else if (line.total <= billedLeft + 0.009) {
        push(line.total, line.days, true);
        billedLeft = Math.round((billedLeft - line.total) * 100) / 100;
      } else {
        const priorDays = line.rate ? +(billedLeft / line.rate).toFixed(2) : line.days;
        const rest = Math.round((line.total - billedLeft) * 100) / 100;
        const restDays = line.rate ? +(rest / line.rate).toFixed(2) : 0;
        push(billedLeft, priorDays, true);
        push(rest, restDays, false);
        billedLeft = 0;
      }
    });
  } else if ((fullRoomTotal > 0 || unbilledRoomTotal > 0) && b.room) {
    const roomRate = b.room.charge_per_day || 0;
    const pushRoom = (total, prior) => {
      if (!(total > 0)) return;
      const days = roomRate ? +(total / roomRate).toFixed(2) : 1;
      items.push({
        source: 'room', source_id: null,
        item_type: 'room_charge',
        item_name: `Room ${b.room.room_number || ''} (${b.room.room_type || ''}) — ${days} day${days === 1 ? '' : 's'}`,
        quantity: Math.max(1, Math.round(days)),
        unit_price: roomRate,
        total_price: total,
        is_prior: prior,
      });
    };
    pushRoom(billedRoomTotal, true);
    pushRoom(unbilledRoomTotal, false);
  }

  Object.entries(b.visits || {}).forEach(([vtype, group]) => {
    (group.items || []).forEach(v => {
      items.push({
        source: 'visit', source_id: v.id,
        item_type: vtype,
        item_name: `${titleCase(vtype)}${v.visitor ? ' - ' + v.visitor : ''}`,
        quantity: 1,
        unit_price: parseFloat(v.amount || 0),
        total_price: parseFloat(v.amount || 0),
        is_prior: !!v.billed,
      });
    });
  });

  (b.ot_entries || []).forEach(o => {
    items.push({
      source: 'ot', source_id: o.id,
      item_type: 'ot_procedure',
      item_name: `OT: ${o.procedure || ''}`,
      quantity: 1,
      unit_price: parseFloat(o.total || 0),
      total_price: parseFloat(o.total || 0),
      is_prior: !!o.billed,
    });
  });

  (b.ancillary_entries || []).forEach(a => {
    items.push({
      source: 'ancillary', source_id: a.id,
      item_type: 'ancillary',
      item_name: `${a.service_name || 'Service'}${a.category ? ' (' + a.category + ')' : ''}`,
      quantity: parseFloat(a.quantity || 1),
      unit_price: parseFloat(a.unit_price || 0),
      total_price: parseFloat(a.total_amount || 0),
      is_prior: !!a.billed,
    });
  });

  (rxList || []).forEach(rx => {
    if (rx.type !== 'pharmacy') return;
    if (rx.status === 'pending') return;
    if (rx.pharmacy_sale_id) return;
    (rx.medicines || []).forEach(m => {
      const qty = parseFloat(m.quantity_dispensed || 0);
      if (qty <= 0) return;
      const total = parseFloat(m.unit_price || 0) * qty;
      if (total <= 0) return;
      items.push({
        source: 'pharmacy_rx', source_id: rx.id,
        item_type: 'pharmacy',
        item_name: `Rx: ${m.name || 'Medicine'}${m.dosage ? ' (' + m.dosage + ')' : ''}`,
        quantity: Math.max(1, Math.round(qty)),
        unit_price: parseFloat(m.unit_price || 0),
        total_price: total,
        is_prior: !!rx.inpatient_bill_id,
      });
    });
  });

  (b.pharmacy_pos_entries || []).forEach(sale => {
    (sale.items || []).forEach(item => {
      const total = parseFloat(item.total_price || 0);
      if (total <= 0) return;
      items.push({
        source: 'pharmacy_pos', source_id: sale.id,
        item_type: 'pharmacy',
        item_name: `POS: ${item.name || 'Medicine'} (${sale.sale_number || ''})`,
        quantity: Math.max(1, Math.round(parseFloat(item.quantity || 1))),
        unit_price: parseFloat(item.unit_price || 0),
        total_price: total,
        is_prior: !!sale.billed,
      });
    });
  });

  (labList || []).forEach(l => {
    if (l.status === 'cancelled') return;
    items.push({
      source: 'lab_order', source_id: l.id,
      item_type: 'lab_test',
      item_name: `Lab: ${l.test_name || 'Test'}${l.order_number ? ' (' + l.order_number + ')' : ''}`,
      quantity: 1,
      unit_price: parseFloat(l.amount || 0),
      total_price: parseFloat(l.amount || 0),
      is_prior: !!l.inpatient_bill_id,
    });
  });

  (b.food_entries || []).forEach(f => {
    const price = parseFloat(f.price || 0);
    if (price <= 0) return;
    const canteen = f.source === 'canteen';
    items.push({
      source: canteen ? 'canteen' : 'food',
      source_id: f.order_id || f.id,
      item_type: 'food',
      item_name: canteen
        ? `Canteen: ${f.item_name || 'Item'}${f.meal_date ? ' — ' + f.meal_date : ''}`
        : `Meal: ${titleCase(f.meal_type || 'meal')}${f.meal_date ? ' on ' + f.meal_date : ''}`,
      quantity: Math.max(1, parseInt(f.quantity || 1, 10)),
      unit_price: parseFloat(f.unit_price != null ? f.unit_price : price),
      total_price: price,
      is_prior: !!f.billed,
    });
  });

  return items;
}

export function buildFinalizePayload(items, discount, taxPct) {
  const payload = {
    items_override: items.map(it => ({
      source: it.source || 'custom',
      source_id: it.source_id || null,
      item_type: it.item_type || 'custom',
      item_name: (it.item_name || '').trim() || 'Custom charge',
      quantity: Math.max(0.01, parseFloat(it.quantity) || 1),
      unit_price: parseFloat(it.unit_price) || 0,
      total_price: parseFloat(it.total_price) || 0,
    })),
  };
  const discountValue = parseFloat(discount?.value) || 0;
  if (discountValue > 0) {
    payload.discount_type = discount.type || 'flat';
    payload.discount_value = discountValue;
  }
  const tax = parseFloat(taxPct) || 0;
  if (tax > 0) payload.tax_percentage = tax;
  return payload;
}

const ReviewFinalBillDialog = ({
  open,
  onOpenChange,
  admissionId,
  patientName,
  netDeposits = 0,
  payerShare = 0,
  priorBilled = 0,
  initialDiscount,
  initialTaxPct,
  submitting = false,
  onConfirm,
  confirmLabel = 'Confirm charges',
  embedded = false,
}) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState([]);
  const [discount, setDiscount] = useState({ type: 'flat', value: '' });
  const [taxPct, setTaxPct] = useState('');

  useEffect(() => {
    if (!open || !admissionId) return undefined;
    let cancelled = false;
    setDiscount({
      type: initialDiscount?.type || 'flat',
      value: initialDiscount?.value || '',
    });
    setTaxPct(initialTaxPct || '');
    setLoading(true);
    loadReviewBillItems(admissionId)
      .then(rows => { if (!cancelled) setItems(rows); })
      .catch(() => {
        if (!cancelled) {
          toast({ variant: 'destructive', title: 'Could not load bill lines' });
          setItems([]);
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [open, admissionId, initialDiscount?.type, initialDiscount?.value, initialTaxPct, toast]);

  const totals = useMemo(() => {
    const subtotal = items.reduce((s, it) => s + (parseFloat(it.total_price) || 0), 0);
    const raw = parseFloat(discount.value) || 0;
    const discountAmount = raw <= 0
      ? 0
      : discount.type === 'percentage'
        ? Math.round(subtotal * Math.min(raw, 100)) / 100
        : Math.min(raw, subtotal);
    const after = Math.max(0, subtotal - discountAmount);
    const taxRate = parseFloat(taxPct) || 0;
    const taxAmount = taxRate > 0 ? Math.round(after * Math.min(taxRate, 100)) / 100 : 0;
    return {
      subtotal,
      discountAmount,
      taxAmount,
      grand: +(after + taxAmount).toFixed(2),
    };
  }, [items, discount, taxPct]);

  const deposits = parseFloat(netDeposits) || 0;
  const approval = Math.min(Math.max(parseFloat(payerShare) || 0, 0), totals.grand);
  const patientTotal = +(totals.grand - approval).toFixed(2);
  const postBalance = +(deposits - patientTotal).toFixed(2);
  const owes = postBalance < -0.01;
  const refund = postBalance > 0.01;
  const settleAmount = Math.abs(postBalance);
  const bannerCls = owes
    ? 'border-red-300 bg-red-50 text-red-900'
    : refund ? 'border-green-300 bg-green-50 text-green-900'
      : 'border-gray-200 bg-gray-50 text-gray-700';
  const banner = owes
    ? `Still to collect ₹${settleAmount.toFixed(2)} before the final bill`
    : refund
      ? `Refund ₹${settleAmount.toFixed(2)} before the final bill`
      : 'Balance is zero — ready for the final bill';

  const updateItem = (idx, patch) => {
    setItems(arr => {
      const next = [...arr];
      next[idx] = { ...next[idx], ...patch };
      return next;
    });
  };

  const renderEditable = (it, idx) => (
      <tr key={`line-${idx}`} className="border-b last:border-b-0">
        <td className="px-2 py-1">
          <Input
            className="h-7 text-xs"
            value={it.item_name}
            onChange={e => updateItem(idx, { item_name: e.target.value })}
          />
          <span className="text-[10px] text-gray-400">
            {it.source && it.source !== 'custom' ? `${it.source}${it.source_id ? ` #${it.source_id}` : ''}` : 'custom'}
            {it.is_prior ? ' · already on an earlier bill' : ''}
          </span>
        </td>
        <td className="px-2 py-1">
          <QtyInput size="sm" min="0.01" step="0.01" className="w-full text-right"
            value={it.quantity}
            onChange={e => {
              const raw = e.target.value;
              const q = parseFloat(raw);
              const up = parseFloat(it.unit_price) || 0;
              updateItem(idx, {
                quantity: raw,
                ...(Number.isFinite(q) && q > 0 ? { total_price: +(q * up).toFixed(2) } : {}),
              });
            }} />
        </td>
        <td className="px-2 py-1">
          <Input type="number" min="0" step="0.01" className="h-7 text-xs text-right"
            value={it.unit_price}
            onChange={e => {
              const raw = e.target.value;
              const up = parseFloat(raw) || 0;
              const q = parseFloat(it.quantity) || 1;
              updateItem(idx, { unit_price: raw, total_price: +(q * up).toFixed(2) });
            }} />
        </td>
        <td className="px-2 py-1">
          <Input type="number" min="0" step="0.01" className="h-7 text-xs text-right"
            value={it.total_price}
            onChange={e => updateItem(idx, { total_price: e.target.value })} />
        </td>
        <td className="px-1 py-1 text-center">
          <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0"
            onClick={() => setItems(arr => arr.filter((_, i) => i !== idx))}>
            <Trash2 className="h-3.5 w-3.5 text-red-500" />
          </Button>
        </td>
      </tr>
  );

  const body = (
    <>
        {loading ? (
          <div className="py-10 text-center text-gray-500">
            <Loader2 className="h-5 w-5 mx-auto animate-spin" />
            <p className="text-sm mt-2">Loading charges…</p>
          </div>
        ) : (
          <div className="space-y-3">
            <div className={`border rounded-lg p-3 text-sm ${bannerCls}`}>
              <div className="font-semibold">{banner}</div>
              <div className="text-xs mt-1 opacity-80">
                Charges ₹{totals.grand.toFixed(2)}
                {approval > 0 ? ` · Approval −₹${approval.toFixed(2)} · Patient ₹${patientTotal.toFixed(2)}` : ''}
                {' '}· Deposits ₹{deposits.toFixed(2)}
                {priorBilled > 0 && (
                  <span> · Prior interim ₹{priorBilled.toFixed(2)} (shown below)</span>
                )}
              </div>
            </div>
            <p className="text-xs text-gray-500">
              Every charge is editable. Change the name, quantity, or price, remove a line, or add a new one, then confirm. Collection happens after this.
            </p>
            <div className="border rounded">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 border-b">
                  <tr>
                    <th className="text-left px-2 py-1.5">Item</th>
                    <th className="text-right px-2 py-1.5 w-24">Qty</th>
                    <th className="text-right px-2 py-1.5 w-28">Unit ₹</th>
                    <th className="text-right px-2 py-1.5 w-28">Total ₹</th>
                    <th className="w-8"></th>
                  </tr>
                </thead>
                <tbody>
                  {items.length === 0 ? (
                    <tr><td colSpan={5} className="text-center text-gray-500 py-4 italic text-xs">
                      No charges found for this admission.<br />
                      Add a custom line below if needed.
                    </td></tr>
                  ) : items.map(renderEditable)}
                </tbody>
              </table>
            </div>
            <Button type="button" size="sm" variant="outline" onClick={() => setItems(arr => [...arr, {
              source: 'custom', source_id: null, item_type: 'custom', item_name: '',
              quantity: 1, unit_price: '', total_price: '', is_prior: false,
            }])}>
              <Plus className="h-3.5 w-3.5 mr-1" /> Add Custom Line
            </Button>
            <div className="border rounded p-3 bg-gray-50 space-y-2">
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <Label className="text-xs">Discount Type</Label>
                  <Select value={discount.type} onValueChange={v => setDiscount(p => ({ ...p, type: v }))}>
                    <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="flat">Flat ₹</SelectItem>
                      <SelectItem value="percentage">Percentage %</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Discount Value</Label>
                  <Input type="number" min="0" step="0.01" className="h-8 text-xs"
                    value={discount.value ?? ''}
                    onChange={e => setDiscount(p => ({ ...p, value: e.target.value }))} />
                </div>
                <div>
                  <Label className="text-xs">Tax %</Label>
                  <Input type="number" min="0" max="100" step="0.01" className="h-8 text-xs"
                    value={taxPct ?? ''}
                    onChange={e => setTaxPct(e.target.value)} />
                </div>
              </div>
            </div>
            <div className="border-t pt-2 text-sm space-y-0.5">
              <div className="flex justify-between"><span>Subtotal</span><span>₹{totals.subtotal.toFixed(2)}</span></div>
              {totals.discountAmount > 0 && (
                <div className="flex justify-between text-gray-600">
                  <span>Discount{discount.type === 'percentage' ? ` (${discount.value}%)` : ''}</span>
                  <span>– ₹{totals.discountAmount.toFixed(2)}</span>
                </div>
              )}
              {totals.taxAmount > 0 && (
                <div className="flex justify-between text-gray-600">
                  <span>Tax ({taxPct}%)</span>
                  <span>+ ₹{totals.taxAmount.toFixed(2)}</span>
                </div>
              )}
              {approval > 0 && (
                <div className="flex justify-between text-gray-600">
                  <span>Insurance / TPA approval</span>
                  <span>– ₹{approval.toFixed(2)}</span>
                </div>
              )}
              <div className="flex justify-between font-semibold text-base pt-1 border-t mt-1">
                <span>{approval > 0 ? 'Patient total' : 'Grand Total'}</span>
                <span>₹{(approval > 0 ? patientTotal : totals.grand).toFixed(2)}</span>
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              {!embedded && (
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
                Cancel
              </Button>
              )}
              <Button
                type="button"
                disabled={submitting || items.some(it => !(it.item_name || '').trim())}
                onClick={() => onConfirm(buildFinalizePayload(items, discount, taxPct), totals.grand)}
              >
                {submitting ? 'Working…' : confirmLabel}
              </Button>
            </div>
          </div>
        )}
    </>
  );

  if (embedded) return body;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Review charges — {patientName || ''}</DialogTitle>
        </DialogHeader>
        {body}
      </DialogContent>
    </Dialog>
  );
};

export default ReviewFinalBillDialog;
