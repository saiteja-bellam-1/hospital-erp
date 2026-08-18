import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { QtyInput } from '../ui/qty-input';
import { Label } from '../ui/label';
import { Pencil, Plus, Loader2 } from 'lucide-react';

export function isPharmacyPosBill(bill) {
  if (!bill || bill.type !== 'pharmacy') return false;
  return !bill.is_catch_up && !String(bill.id || '').startsWith('CU-');
}

export function canEditBill(bill) {
  if (!bill || !bill.bill_id) return false;
  if (bill.payment_status === 'cancelled') return false;
  return true;
}

function usesBillsTable(bill) {
  if (!bill) return false;
  if (bill.is_catch_up || String(bill.id || '').startsWith('CU-')) return true;
  return ['admission', 'consolidated', 'day_care', 'physiotherapy', 'catch_up', 'canteen'].includes(bill.type);
}

function errMessage(err, fallback) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && typeof detail.message === 'string') return detail.message;
  return fallback;
}

function emptyLine() {
  return { id: null, item_name: '', item_type: 'miscellaneous', quantity: 1, unit_price: '' };
}

const EditBillDialog = ({ open, bill, onClose, onSaved, formatCurrency }) => {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [consultForm, setConsultForm] = useState({
    consultation_fee: '', registration_fee: '', discount_amount: '',
  });
  const [labItems, setLabItems] = useState([]);
  const [ledgerForm, setLedgerForm] = useState({
    items: [emptyLine()],
    discount_amount: '',
    tax_amount: '',
    amount_paid: 0,
  });

  const mode = bill?.type === 'consultation' && !usesBillsTable(bill)
    ? 'consultation'
    : bill?.type === 'lab'
      ? 'lab'
      : 'ledger';

  useEffect(() => {
    if (!open || !bill) return;
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        if (mode === 'consultation') {
          const res = await axios.get(`/api/hospital/billing/consultation/${bill.bill_id}`);
          if (cancelled) return;
          setConsultForm({
            consultation_fee: String(res.data.consultation_fee ?? 0),
            registration_fee: String(res.data.registration_fee ?? 0),
            discount_amount: String(res.data.discount_amount ?? 0),
          });
        } else if (mode === 'lab') {
          const params = bill.lab_bill_group_id
            ? { lab_bill_group_id: bill.lab_bill_group_id }
            : { order_id: bill.bill_id };
          const res = await axios.get('/api/hospital/billing/lab/edit', { params });
          if (cancelled) return;
          setLabItems((res.data.items || []).map((it) => ({
            order_id: it.order_id,
            test_name: it.test_name,
            amount: String(it.amount ?? 0),
          })));
        } else {
          const res = await axios.get(`/api/hospital/billing/bills/${bill.bill_id}`);
          if (cancelled) return;
          const items = (res.data.items || []).map((it) => ({
            id: it.id,
            item_name: it.item_name || '',
            item_type: it.item_type || 'miscellaneous',
            quantity: it.quantity ?? 1,
            unit_price: String(it.unit_price ?? 0),
          }));
          setLedgerForm({
            items: items.length ? items : [emptyLine()],
            discount_amount: String(res.data.discount_amount ?? 0),
            tax_amount: String(res.data.tax_amount ?? 0),
            amount_paid: Number(res.data.amount_paid || 0),
          });
        }
      } catch (err) {
        alert(errMessage(err, 'Could not load bill for editing'));
        onClose();
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [open, bill, mode]);

  const consultTotal = useMemo(() => {
    const fee = parseFloat(consultForm.consultation_fee) || 0;
    const reg = parseFloat(consultForm.registration_fee) || 0;
    const disc = parseFloat(consultForm.discount_amount) || 0;
    return Math.max(0, fee + reg - disc);
  }, [consultForm]);

  const labTotal = useMemo(
    () => labItems.reduce((s, it) => s + (parseFloat(it.amount) || 0), 0),
    [labItems],
  );

  const ledgerSubtotal = useMemo(
    () => ledgerForm.items.reduce(
      (s, it) => s + (Number(it.quantity) || 0) * (parseFloat(it.unit_price) || 0),
      0,
    ),
    [ledgerForm.items],
  );
  const ledgerTotal = useMemo(() => {
    const disc = parseFloat(ledgerForm.discount_amount) || 0;
    const tax = parseFloat(ledgerForm.tax_amount) || 0;
    return Math.max(0, ledgerSubtotal + tax - disc);
  }, [ledgerForm.discount_amount, ledgerForm.tax_amount, ledgerSubtotal]);

  const submit = async () => {
    if (!bill) return;
    setSaving(true);
    try {
      if (mode === 'consultation') {
        await axios.put(`/api/hospital/billing/consultation/${bill.bill_id}`, {
          consultation_fee: parseFloat(consultForm.consultation_fee) || 0,
          registration_fee: parseFloat(consultForm.registration_fee) || 0,
          discount_amount: parseFloat(consultForm.discount_amount) || 0,
        });
      } else if (mode === 'lab') {
        const params = bill.lab_bill_group_id
          ? { lab_bill_group_id: bill.lab_bill_group_id }
          : { order_id: bill.bill_id };
        await axios.put('/api/hospital/billing/lab/edit', {
          items: labItems.map((it) => ({
            order_id: it.order_id,
            amount: parseFloat(it.amount) || 0,
          })),
        }, { params });
      } else {
        const items = ledgerForm.items
          .map((it) => ({
            id: it.id || undefined,
            item_name: (it.item_name || '').trim(),
            item_type: it.item_type || 'miscellaneous',
            quantity: Number(it.quantity) || 0,
            unit_price: parseFloat(it.unit_price) || 0,
          }))
          .filter((it) => it.item_name && it.quantity > 0);
        if (!items.length) {
          alert('Add at least one line item with a name and quantity.');
          setSaving(false);
          return;
        }
        await axios.put(`/api/hospital/billing/bills/${bill.bill_id}`, {
          items,
          discount_amount: parseFloat(ledgerForm.discount_amount) || 0,
          tax_amount: parseFloat(ledgerForm.tax_amount) || 0,
        });
      }
      onSaved?.();
      onClose();
    } catch (err) {
      alert(errMessage(err, 'Could not save bill changes'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) onClose(); }}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Pencil className="h-5 w-5 text-blue-600" />
            Edit Bill
          </DialogTitle>
        </DialogHeader>
        {loading ? (
          <div className="flex justify-center py-10"><Loader2 className="h-6 w-6 animate-spin" /></div>
        ) : (
          <div className="space-y-4">
            <div className="bg-gray-50 rounded-lg p-3 text-sm space-y-1">
              <div className="flex justify-between">
                <span className="text-gray-500">Reference</span>
                <span className="font-mono">{bill?.reference}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Patient</span>
                <span>{bill?.patient_name}</span>
              </div>
            </div>

            {mode === 'consultation' && (
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <Label className="text-xs">Consultation fee (₹)</Label>
                  <Input type="number" min="0" step="0.01" value={consultForm.consultation_fee}
                    onChange={(e) => setConsultForm({ ...consultForm, consultation_fee: e.target.value })} />
                </div>
                <div>
                  <Label className="text-xs">Registration fee (₹)</Label>
                  <Input type="number" min="0" step="0.01" value={consultForm.registration_fee}
                    onChange={(e) => setConsultForm({ ...consultForm, registration_fee: e.target.value })} />
                </div>
                <div>
                  <Label className="text-xs">Discount (₹)</Label>
                  <Input type="number" min="0" step="0.01" value={consultForm.discount_amount}
                    onChange={(e) => setConsultForm({ ...consultForm, discount_amount: e.target.value })} />
                </div>
                <div className="col-span-3 text-right text-sm font-semibold">
                  Total: {formatCurrency(consultTotal)}
                </div>
              </div>
            )}

            {mode === 'lab' && (
              <div className="space-y-2">
                <Label className="text-xs">Test amounts</Label>
                {labItems.map((it, idx) => (
                  <div key={it.order_id} className="grid grid-cols-12 gap-2 items-center">
                    <div className="col-span-8 text-sm truncate" title={it.test_name}>{it.test_name}</div>
                    <Input className="col-span-4" type="number" min="0" step="0.01" value={it.amount}
                      onChange={(e) => {
                        const next = [...labItems];
                        next[idx] = { ...next[idx], amount: e.target.value };
                        setLabItems(next);
                      }} />
                  </div>
                ))}
                <div className="text-right text-sm font-semibold pt-1">
                  Total: {formatCurrency(labTotal)}
                </div>
              </div>
            )}

            {mode === 'ledger' && (
              <div className="space-y-3">
                {ledgerForm.amount_paid > 0 && (
                  <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded px-2.5 py-1.5">
                    ₹{Number(ledgerForm.amount_paid).toLocaleString('en-IN')} is already paid. The new total cannot go below that — refund first to reduce the bill.
                  </p>
                )}
                <Label className="text-xs">Line items</Label>
                {ledgerForm.items.map((it, idx) => (
                  <div key={it.id || `new-${idx}`} className="grid grid-cols-12 gap-2 items-center">
                    {it.id ? (
                      <div className="col-span-6 text-sm truncate" title={it.item_name}>{it.item_name}</div>
                    ) : (
                      <Input className="col-span-6" placeholder="Description" value={it.item_name}
                        onChange={(e) => {
                          const next = [...ledgerForm.items];
                          next[idx] = { ...next[idx], item_name: e.target.value };
                          setLedgerForm({ ...ledgerForm, items: next });
                        }} />
                    )}
                    <QtyInput className="col-span-2 w-full" min="0.01" step="1" value={it.quantity}
                      onChange={(e) => {
                        const next = [...ledgerForm.items];
                        next[idx] = { ...next[idx], quantity: e.target.value };
                        setLedgerForm({ ...ledgerForm, items: next });
                      }} />
                    <Input className="col-span-3" type="number" min="0" step="0.01" placeholder="Rate ₹" value={it.unit_price}
                      onChange={(e) => {
                        const next = [...ledgerForm.items];
                        next[idx] = { ...next[idx], unit_price: e.target.value };
                        setLedgerForm({ ...ledgerForm, items: next });
                      }} />
                    <Button variant="ghost" size="sm" className="col-span-1 text-red-600"
                      disabled={ledgerForm.items.length === 1}
                      onClick={() => {
                        const next = ledgerForm.items.filter((_, i) => i !== idx);
                        setLedgerForm({ ...ledgerForm, items: next });
                      }}>
                      ×
                    </Button>
                  </div>
                ))}
                <Button variant="outline" size="sm" onClick={() =>
                  setLedgerForm({ ...ledgerForm, items: [...ledgerForm.items, emptyLine()] })
                }>
                  <Plus className="h-3.5 w-3.5 mr-1" /> Add line
                </Button>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs">Discount (₹)</Label>
                    <Input type="number" min="0" step="0.01" value={ledgerForm.discount_amount}
                      onChange={(e) => setLedgerForm({ ...ledgerForm, discount_amount: e.target.value })} />
                  </div>
                  <div>
                    <Label className="text-xs">Tax (₹)</Label>
                    <Input type="number" min="0" step="0.01" value={ledgerForm.tax_amount}
                      onChange={(e) => setLedgerForm({ ...ledgerForm, tax_amount: e.target.value })} />
                  </div>
                </div>
                <div className="bg-gray-50 rounded-lg p-3 text-sm space-y-1">
                  <div className="flex justify-between"><span>Subtotal</span><span>{formatCurrency(ledgerSubtotal)}</span></div>
                  <div className="flex justify-between font-semibold border-t pt-1">
                    <span>Total</span><span>{formatCurrency(ledgerTotal)}</span>
                  </div>
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button variant="outline" onClick={onClose}>Cancel</Button>
              <Button disabled={saving} onClick={submit}>
                {saving ? 'Saving...' : 'Save changes'}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};

export default EditBillDialog;
