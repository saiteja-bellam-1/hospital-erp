import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../../components/ui/dialog';
import { useToast } from '../../../../hooks/use-toast';
import { errMsg } from '../../PharmacyModule';
import { Plus, RefreshCw, Trash2 } from 'lucide-react';
import { usePharmacyPermissions } from '../../../../hooks/usePharmacyPermissions';

export default function SupplierPaymentsTab() {
  const { toast } = useToast();
  const { hasPerm } = usePharmacyPermissions();
  const [suppliers, setSuppliers] = useState([]);
  const [supplierId, setSupplierId] = useState('');
  const [payables, setPayables] = useState(null);
  const [payments, setPayments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    amount: '',
    mode: 'neft',
    paid_on: new Date().toISOString().slice(0, 10),
    reference: '',
    notes: '',
    allocations: [{ purchase_id: '', amount: '' }],
  });

  const loadSuppliers = useCallback(async () => {
    try {
      const r = await axios.get('/api/pharmacy/suppliers', { params: { active_only: true } });
      setSuppliers(r.data || []);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadSuppliers(); }, [loadSuppliers]);

  const load = useCallback(async () => {
    if (!supplierId) {
      setPayables(null);
      setPayments([]);
      return;
    }
    setLoading(true);
    try {
      const [p, pays] = await Promise.all([
        axios.get(`/api/pharmacy/suppliers/${supplierId}/payables`),
        axios.get('/api/pharmacy/supplier-payments', { params: { supplier_id: supplierId } }),
      ]);
      setPayables(p.data);
      setPayments(pays.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Failed to load', description: errMsg(e) });
    } finally {
      setLoading(false);
    }
  }, [supplierId, toast]);

  useEffect(() => { load(); }, [load]);

  const submitPayment = async () => {
    try {
      await axios.post('/api/pharmacy/supplier-payments', {
        supplier_id: Number(supplierId),
        paid_on: form.paid_on,
        amount: Number(form.amount),
        mode: form.mode,
        reference: form.reference || null,
        notes: form.notes || null,
        allocations: form.allocations
          .filter((a) => a.purchase_id && a.amount)
          .map((a) => ({ purchase_id: Number(a.purchase_id), amount: Number(a.amount) })),
      });
      toast({ title: 'Payment recorded' });
      setOpen(false);
      setForm({
        amount: '', mode: 'neft', paid_on: new Date().toISOString().slice(0, 10),
        reference: '', notes: '', allocations: [{ purchase_id: '', amount: '' }],
      });
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Payment failed', description: errMsg(e) });
    }
  };

  const voidPayment = async (id) => {
    if (!window.confirm('Void this payment?')) return;
    try {
      await axios.delete(`/api/pharmacy/supplier-payments/${id}`);
      toast({ title: 'Payment voided' });
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Void failed', description: errMsg(e) });
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap justify-between items-center gap-2">
            <span>Supplier Payments</span>
            <div className="flex gap-2 items-center">
              <select className="border rounded h-8 px-2 text-sm" value={supplierId}
                onChange={(e) => setSupplierId(e.target.value)}>
                <option value="">Select supplier…</option>
                {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-3 w-3" /></Button>
              {hasPerm('create_supplier_payment') && supplierId && (
                <Button size="sm" onClick={() => setOpen(true)}>
                  <Plus className="h-3 w-3 mr-1" /> Record Payment
                </Button>
              )}
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!supplierId ? (
            <p className="text-sm text-gray-500">Choose a supplier to view payables and payments.</p>
          ) : loading ? (
            <p className="text-sm text-gray-500">Loading…</p>
          ) : payables ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-sm">
                <div className="p-3 border rounded"><div className="text-gray-500 text-xs">Opening</div><div className="font-medium">₹{payables.opening_balance.toFixed(2)}</div></div>
                <div className="p-3 border rounded"><div className="text-gray-500 text-xs">Purchases</div><div className="font-medium">₹{payables.purchase_total.toFixed(2)}</div></div>
                <div className="p-3 border rounded"><div className="text-gray-500 text-xs">Payments</div><div className="font-medium">₹{payables.payment_total.toFixed(2)}</div></div>
                <div className="p-3 border rounded"><div className="text-gray-500 text-xs">Debit notes</div><div className="font-medium">₹{payables.debit_note_total.toFixed(2)}</div></div>
                <div className="p-3 border rounded bg-slate-50"><div className="text-gray-500 text-xs">Outstanding</div><div className="font-semibold">₹{payables.outstanding.toFixed(2)}</div></div>
              </div>

              <div>
                <h3 className="text-sm font-medium mb-2">Credit purchases</h3>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-600">
                      <th className="py-2 pr-3">Purchase #</th>
                      <th className="py-2 pr-3">Date</th>
                      <th className="py-2 pr-3">Invoice</th>
                      <th className="py-2 pr-3">Bill</th>
                      <th className="py-2 pr-3">Allocated</th>
                      <th className="py-2">Outstanding</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(payables.purchases || []).map((p) => (
                      <tr key={p.purchase_id} className="border-b">
                        <td className="py-2 pr-3 font-mono text-xs">{p.purchase_number}</td>
                        <td className="py-2 pr-3 text-xs">{p.entry_date}</td>
                        <td className="py-2 pr-3 text-xs">{p.invoice_number || '—'}</td>
                        <td className="py-2 pr-3">₹{p.grand_total.toFixed(2)}</td>
                        <td className="py-2 pr-3">₹{p.allocated.toFixed(2)}</td>
                        <td className="py-2">₹{p.outstanding.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div>
                <h3 className="text-sm font-medium mb-2">Payments</h3>
                {(payments || []).length === 0 ? (
                  <p className="text-sm text-gray-500">No payments recorded</p>
                ) : (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-gray-600">
                        <th className="py-2 pr-3">Payment #</th>
                        <th className="py-2 pr-3">Date</th>
                        <th className="py-2 pr-3">Mode</th>
                        <th className="py-2 pr-3">Amount</th>
                        <th className="py-2 pr-3">Reference</th>
                        <th className="py-2 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payments.map((p) => (
                        <tr key={p.id} className="border-b">
                          <td className="py-2 pr-3 font-mono text-xs">{p.payment_number}</td>
                          <td className="py-2 pr-3 text-xs">{p.paid_on}</td>
                          <td className="py-2 pr-3 text-xs">{p.mode}</td>
                          <td className="py-2 pr-3">₹{(p.amount || 0).toFixed(2)}</td>
                          <td className="py-2 pr-3 text-xs">{p.reference || '—'}</td>
                          <td className="py-2 text-right">
                            {hasPerm('delete_supplier_payment') && (
                              <Button size="sm" variant="ghost" onClick={() => voidPayment(p.id)}>
                                <Trash2 className="h-3 w-3 text-red-500" />
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>Record supplier payment</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div><Label>Amount</Label><Input value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} /></div>
              <div>
                <Label>Mode</Label>
                <select className="w-full border rounded h-9 px-2" value={form.mode}
                  onChange={(e) => setForm({ ...form, mode: e.target.value })}>
                  <option value="neft">NEFT</option>
                  <option value="upi">UPI</option>
                  <option value="cash">Cash</option>
                  <option value="cheque">Cheque</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div><Label>Paid on</Label><Input type="date" value={form.paid_on} onChange={(e) => setForm({ ...form, paid_on: e.target.value })} /></div>
              <div><Label>Reference</Label><Input value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} /></div>
            </div>
            <div>
              <Label>Allocations</Label>
              {form.allocations.map((a, idx) => (
                <div key={idx} className="flex gap-2 mt-1">
                  <select className="flex-1 border rounded h-8 px-2 text-xs" value={a.purchase_id}
                    onChange={(e) => {
                      const next = [...form.allocations];
                      next[idx] = { ...next[idx], purchase_id: e.target.value };
                      setForm({ ...form, allocations: next });
                    }}>
                    <option value="">Purchase…</option>
                    {(payables?.purchases || []).filter((p) => p.outstanding > 0).map((p) => (
                      <option key={p.purchase_id} value={p.purchase_id}>
                        {p.purchase_number} (₹{p.outstanding.toFixed(2)})
                      </option>
                    ))}
                  </select>
                  <Input className="w-28" value={a.amount} placeholder="Amt"
                    onChange={(e) => {
                      const next = [...form.allocations];
                      next[idx] = { ...next[idx], amount: e.target.value };
                      setForm({ ...form, allocations: next });
                    }} />
                </div>
              ))}
              <Button size="sm" variant="outline" className="mt-2"
                onClick={() => setForm({ ...form, allocations: [...form.allocations, { purchase_id: '', amount: '' }] })}>
                Add allocation
              </Button>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={submitPayment} disabled={!form.amount}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
