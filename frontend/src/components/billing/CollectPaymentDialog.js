import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { CreditCard } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { DEFAULT_PAYMENT_METHODS } from './PaymentCollectionFields';

const money = (n) => `₹${Number(n || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const errorText = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  return fallback;
};

/**
 * Collect full or partial payment against an existing invoice.
 *
 * Both URLs follow the shared service-payment contract:
 *   GET  infoUrl -> { total_amount, amount_paid, balance_due, payment_state, payments: [...] }
 *   POST postUrl <- { amount, payment_method, reference, notes }
 *
 * Endpoints: /api/hospital/billing/rows/{row_id}/payments,
 * /api/appointments/{id}/payments, /api/lab/bills/{group_id}/payments,
 * /api/pharmacy/sales/{id}/payments, /api/canteen/sales/{id}/payments.
 *
 * For a Bill-table bill use `billCollectProps(billId)`, which maps the
 * /api/hospital/billing/bills/{id} detail + /payment endpoint onto this shape.
 */
export const billCollectProps = (billId) => ({
  infoUrl: billId ? `/api/hospital/billing/bills/${billId}` : null,
  postUrl: billId ? `/api/hospital/billing/bills/${billId}/payment` : null,
  mapInfo: (d) => ({
    total_amount: d.total_amount,
    amount_paid: d.amount_paid,
    balance_due: d.balance_due,
    payments: (d.payments || []).map((p) => ({
      id: p.id, amount: p.amount_paid, payment_method: p.payment_method_name, payment_date: p.payment_date,
    })),
  }),
  mapBody: (b) => ({
    amount_paid: b.amount,
    payment_method: b.payment_method,
    transaction_reference: b.reference,
    notes: b.notes,
  }),
});

export default function CollectPaymentDialog({
  open,
  onOpenChange,
  infoUrl,
  postUrl,
  title = 'Collect Payment',
  subtitle,
  methods = DEFAULT_PAYMENT_METHODS,
  onSuccess,
  mapInfo = (d) => d,
  mapBody = (b) => b,
}) {
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ amount: '', payment_method: methods[0]?.value || 'cash', reference: '', notes: '' });

  useEffect(() => {
    if (!open || !infoUrl) return;
    let cancelled = false;
    setLoading(true);
    setError('');
    axios.get(infoUrl)
      .then((res) => {
        if (cancelled) return;
        const data = mapInfo(res.data || {});
        setInfo(data);
        setForm({
          amount: String(data?.balance_due ?? ''),
          payment_method: methods[0]?.value || 'cash',
          reference: '',
          notes: '',
        });
      })
      .catch((err) => { if (!cancelled) setError(errorText(err, 'Could not load bill balance')); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, infoUrl]);

  const balance = Number(info?.balance_due || 0);
  const amount = Number(form.amount);
  const amountError = form.amount === '' || Number.isNaN(amount) || amount <= 0
    ? 'Enter an amount'
    : amount > balance + 0.009 ? `Cannot exceed the balance (${money(balance)})` : '';

  const submit = async () => {
    if (amountError || !postUrl) return;
    setSaving(true);
    setError('');
    try {
      const res = await axios.post(postUrl, mapBody({
        amount: Math.round(amount * 100) / 100,
        payment_method: form.payment_method,
        reference: form.reference || undefined,
        notes: form.notes || undefined,
      }));
      onSuccess?.(res.data);
      onOpenChange(false);
    } catch (err) {
      setError(errorText(err, 'Payment failed'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CreditCard className="h-5 w-5 text-green-600" /> {title}
          </DialogTitle>
        </DialogHeader>
        {loading && <p className="py-4 text-center text-sm text-gray-500">Loading…</p>}
        {!loading && info && (
          <div className="space-y-4">
            <div className="rounded-lg bg-blue-50 p-3 text-sm">
              {subtitle && <p className="mb-1 font-medium">{subtitle}</p>}
              <div className="grid grid-cols-3 gap-2">
                <div><p className="text-xs text-gray-500">Total</p><p className="font-semibold">{money(info.total_amount)}</p></div>
                <div><p className="text-xs text-gray-500">Paid</p><p className="font-semibold text-green-700">{money(info.amount_paid)}</p></div>
                <div><p className="text-xs text-gray-500">Balance</p><p className="font-bold text-red-600">{money(info.balance_due)}</p></div>
              </div>
            </div>

            {Array.isArray(info.payments) && info.payments.length > 0 && (
              <div className="max-h-28 overflow-y-auto rounded border text-xs">
                {info.payments.map((p, i) => (
                  <div key={p.id ?? i} className="flex justify-between border-b px-2 py-1 last:border-0">
                    <span className="text-gray-600">
                      {p.payment_date ? new Date(p.payment_date).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' }) : '—'}
                      {' · '}{(p.payment_method || 'cash').toUpperCase()}
                    </span>
                    <span className="font-medium">{money(p.amount)}</span>
                  </div>
                ))}
              </div>
            )}

            {balance <= 0.009 ? (
              <p className="text-sm font-medium text-green-700">This bill is fully paid.</p>
            ) : (
              <>
                <div>
                  <Label>Amount</Label>
                  <Input type="number" min="0" step="0.01" inputMode="decimal" value={form.amount}
                    onChange={(e) => setForm({ ...form, amount: e.target.value })} />
                  {form.amount !== '' && amountError && <p className="mt-1 text-xs text-red-600">{amountError}</p>}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label>Method</Label>
                    <select className="h-9 w-full rounded-md border border-input bg-white px-2 text-sm"
                      value={form.payment_method}
                      onChange={(e) => setForm({ ...form, payment_method: e.target.value })}>
                      {methods.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                    </select>
                  </div>
                  <div>
                    <Label>Reference</Label>
                    <Input value={form.reference} placeholder="Optional"
                      onChange={(e) => setForm({ ...form, reference: e.target.value })} />
                  </div>
                </div>
                <div>
                  <Label>Notes</Label>
                  <Input value={form.notes} placeholder="Optional"
                    onChange={(e) => setForm({ ...form, notes: e.target.value })} />
                </div>
              </>
            )}
          </div>
        )}
        {error && <p className="text-sm text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 border-t pt-3">
          <Button variant="outline" onClick={() => onOpenChange(false)}>Close</Button>
          {info && balance > 0.009 && (
            <Button onClick={submit} disabled={saving || !!amountError}>
              {saving ? 'Saving…' : `Collect ${money(amount || 0)}`}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
