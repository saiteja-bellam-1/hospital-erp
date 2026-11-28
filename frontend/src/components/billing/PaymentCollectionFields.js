import React from 'react';
import { Input } from '../ui/input';
import { Label } from '../ui/label';

/**
 * Payment-at-billing fields shared by every invoicing dialog.
 *
 * value = { mode: 'full' | 'partial' | 'later', amount: string, method: string, reference: string }
 *
 * Use `paymentRequestFields(value, total)` to turn it into the API fields
 * (`amount_paid`, `payment_status`, `payment_method`, `payment_reference`).
 */

export const DEFAULT_PAYMENT_METHODS = [
  { value: 'cash', label: 'Cash' },
  { value: 'upi', label: 'UPI' },
  { value: 'card', label: 'Card' },
  { value: 'online', label: 'Online' },
  { value: 'cheque', label: 'Cheque' },
];

export const defaultPaymentValue = (method = 'cash') => ({
  mode: 'full',
  amount: '',
  method,
  reference: '',
});

const round2 = (n) => Math.round((Number(n) || 0) * 100) / 100;

export const amountCollectedNow = (value, total) => {
  if (!value) return round2(total);
  if (value.mode === 'later') return 0;
  if (value.mode === 'partial') return round2(value.amount);
  return round2(total);
};

/** Returns an error string, or null when the entry is valid. */
export const validatePayment = (value, total) => {
  if (!value || value.mode !== 'partial') return null;
  const amt = Number(value.amount);
  if (value.amount === '' || Number.isNaN(amt)) return 'Enter the amount received';
  if (amt < 0) return 'Amount cannot be negative';
  if (amt > round2(total) + 0.009) return `Amount cannot exceed the bill total (₹${round2(total).toFixed(2)})`;
  return null;
};

/**
 * API fields for a create call. "Paid in full" sends no amount so the server
 * charges its own computed total (the on-screen total is only an estimate).
 */
export const paymentRequestFields = (value) => {
  const v = value || defaultPaymentValue();
  const base = {
    payment_method: v.method || 'cash',
    payment_reference: v.reference || undefined,
  };
  if (v.mode === 'later') return { ...base, payment_status: 'pending', amount_paid: 0 };
  if (v.mode === 'partial') return { ...base, payment_status: 'partial', amount_paid: round2(v.amount) };
  return { ...base, payment_status: 'paid' };
};

const MODES = [
  { key: 'full', label: 'Paid in full' },
  { key: 'partial', label: 'Partial' },
  { key: 'later', label: 'Pay later' },
];

export default function PaymentCollectionFields({
  total,
  value,
  onChange,
  methods = DEFAULT_PAYMENT_METHODS,
  allowLater = true,
  showMethod = true,
  className = '',
}) {
  const v = value || defaultPaymentValue();
  const set = (patch) => onChange({ ...v, ...patch });
  const collected = amountCollectedNow(v, total);
  const balance = Math.max(0, round2(round2(total) - collected));
  const error = validatePayment(v, total);
  const modes = allowLater ? MODES : MODES.filter((m) => m.key !== 'later');
  const needsRef = ['card', 'upi', 'online', 'cheque'].includes(v.method);

  const fieldCols = 1 + (v.mode === 'partial' ? 1 : 0) + (needsRef ? 1 : 0);
  const gridCols = fieldCols === 3 ? 'sm:grid-cols-3' : fieldCols === 2 ? 'sm:grid-cols-2' : 'sm:grid-cols-2';

  return (
    <div className={`space-y-3 ${className}`}>
      <h4 className="text-sm font-medium">Payment</h4>
      <div className="grid grid-cols-3 gap-1 rounded-lg border bg-white p-1" role="radiogroup" aria-label="Payment status">
        {modes.map((m) => (
          <button
            key={m.key}
            type="button"
            role="radio"
            aria-checked={v.mode === m.key}
            onClick={() => set({ mode: m.key })}
            className={`rounded-md px-2 py-1.5 text-xs font-medium transition-colors ${
              v.mode === m.key ? 'bg-gray-900 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
            }`}
          >
            {m.label}
          </button>
        ))}
      </div>

      {(v.mode === 'partial' || (showMethod && v.mode !== 'later')) && (
        <div className={`grid grid-cols-1 gap-2 ${gridCols}`}>
          {v.mode === 'partial' && (
            <div>
              <Label className="text-xs text-gray-600">Amount received (₹)</Label>
              <Input
                type="number"
                min="0"
                step="0.01"
                inputMode="decimal"
                className="h-9 bg-white"
                value={v.amount}
                onChange={(e) => set({ amount: e.target.value })}
                placeholder={`Max ${round2(total).toFixed(2)}`}
                autoFocus
              />
            </div>
          )}
          {showMethod && v.mode !== 'later' && (
            <div>
              <Label className="text-xs text-gray-600">Method</Label>
              <select
                className="h-9 w-full rounded-md border border-input bg-white px-2 text-sm"
                value={v.method}
                onChange={(e) => set({ method: e.target.value })}
              >
                {methods.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            </div>
          )}
          {showMethod && v.mode !== 'later' && needsRef && (
            <div>
              <Label className="text-xs text-gray-600">Reference</Label>
              <Input
                className="h-9 bg-white"
                value={v.reference}
                onChange={(e) => set({ reference: e.target.value })}
                placeholder="Txn / cheque no."
              />
            </div>
          )}
        </div>
      )}

      <div className="flex items-center justify-between rounded-md bg-white px-3 py-2 text-xs border">
        <span className="text-gray-600">Collecting now <b className="text-gray-900">₹{collected.toFixed(2)}</b></span>
        <span className={balance > 0 ? 'font-semibold text-amber-700' : 'font-medium text-green-700'}>
          {balance > 0 ? `Balance ₹${balance.toFixed(2)}` : 'Fully paid'}
        </span>
      </div>
      {error && v.amount !== '' && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
