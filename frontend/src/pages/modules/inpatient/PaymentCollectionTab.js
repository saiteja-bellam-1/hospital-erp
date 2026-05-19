import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../../../components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../../components/ui/select';
import { useToast } from '../../../hooks/use-toast';
import { printPdfFromUrl } from '../../../utils/printPdf';
import BillDetailDialog from './BillDetailDialog';
import {
  Loader2, Receipt, FileDown, Wallet, ChevronRight, Banknote,
} from 'lucide-react';

const PAYMENT_METHODS = [
  { value: 'cash',    label: 'Cash' },
  { value: 'card',    label: 'Card' },
  { value: 'upi',     label: 'UPI' },
  { value: 'cheque',  label: 'Cheque' },
  { value: 'online',  label: 'Online transfer' },
];

const PaymentCollectionTab = ({
  canCollect = false,
  canOpenBill = false,
}) => {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [target, setTarget] = useState(null);
  const [billTarget, setBillTarget] = useState(null);  // admission whose bill dialog is open
  const [form, setForm] = useState({
    amount: '', payment_method: 'cash', reference_number: '',
  });
  const [submitting, setSubmitting] = useState(false);

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const admRes = await axios.get('/api/inpatient/admissions',
        { params: { status: 'discharged', limit: 100 } });
      const admissions = admRes.data?.items || admRes.data || [];
      const enriched = await Promise.all(admissions.map(async (a) => {
        const [balRes, billRes] = await Promise.all([
          axios.get(`/api/inpatient/admissions/${a.id}/balance`)
            .catch(() => ({ data: null })),
          axios.get(`/api/inpatient/admissions/${a.id}/bill`,
                    { params: { unbilled_only: false } })
            .catch(() => ({ data: null })),
        ]);
        const netDeposits = balRes.data?.net_deposits ?? 0;
        const finalisedBilled = balRes.data?.total_billed ?? 0;
        const computedCharges = billRes.data?.grand_total
                             ?? billRes.data?.subtotal
                             ?? finalisedBilled;
        const stayCharges = Math.max(computedCharges, finalisedBilled);
        return {
          ...a,
          stayCharges,
          netDeposits,
          owesAmount: stayCharges - netDeposits,
          billFinalised: finalisedBilled > 0,
        };
      }));
      // Keep only those still owing.
      const pending = enriched.filter(a => a.owesAmount > 0.01);
      pending.sort((a, b) => b.owesAmount - a.owesAmount);
      setRows(pending);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  const openCollect = (adm) => {
    setTarget(adm);
    setForm({
      amount: adm.owesAmount.toFixed(2),
      payment_method: 'cash',
      reference_number: '',
    });
  };

  const downloadBill = async (adm) => {
    try {
      const res = await axios.get(
        `/api/inpatient/admissions/${adm.id}/bill/pdf`,
        { responseType: 'blob', params: { include_header: true } },
      );
      const url = URL.createObjectURL(res.data);
      printPdfFromUrl(url);
    } catch (err) {
      let msg = 'Failed to download bill PDF';
      try {
        if (err.response?.data instanceof Blob) {
          const text = await err.response.data.text();
          const json = JSON.parse(text);
          if (typeof json.detail === 'string') msg = json.detail;
        }
      } catch { /* keep generic msg */ }
      toast({ variant: 'destructive', title: 'Error', description: msg });
    }
  };

  const submit = async () => {
    if (!form.amount || parseFloat(form.amount) <= 0) {
      toast({ variant: 'destructive', title: 'Enter an amount' });
      return;
    }
    setSubmitting(true);
    try {
      const dep = await axios.post(`/api/inpatient/admissions/${target.id}/deposits`, {
        amount: parseFloat(form.amount),
        deposit_type: 'topup',
        payment_method: form.payment_method,
        reference_number: form.reference_number || null,
      });
      toast({ title: 'Payment recorded',
              description: `Rs.${parseFloat(form.amount).toFixed(2)} collected from ${target.patient_name}.` });
      // Open the deposit receipt for printing
      try {
        const pdfRes = await axios.get(
          `/api/inpatient/deposits/${dep.data.id}/receipt/pdf?include_header=true`,
          { responseType: 'blob' },
        );
        const url = URL.createObjectURL(new Blob([pdfRes.data], { type: 'application/pdf' }));
        printPdfFromUrl(url);
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      } catch (_) { /* receipt is best-effort; collection already succeeded */ }
      setTarget(null);
      fetchRows();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail
        : 'Could not record payment';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-gray-500">
          <Loader2 className="h-5 w-5 mx-auto animate-spin" />
          <p className="text-sm mt-2">Loading bills with outstanding balance…</p>
        </CardContent>
      </Card>
    );
  }

  if (rows.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-gray-500 text-sm">
          🎉 No discharged admissions with outstanding balance.
          <div className="text-xs mt-1">Everything is settled.</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <p className="text-xs text-gray-500">
        Discharged admissions that still owe money. Collect the payment, then
        the row moves to the <b>Ready for Gate Pass</b> tab.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b bg-gray-50">
              <th className="text-left py-2 px-3 font-medium">Patient</th>
              <th className="text-left py-2 px-3 font-medium">Discharged</th>
              <th className="text-right py-2 px-3 font-medium">Stay charges</th>
              <th className="text-right py-2 px-3 font-medium">Deposits</th>
              <th className="text-right py-2 px-3 font-medium">Owes</th>
              <th className="text-left py-2 px-3 font-medium">Bill</th>
              <th className="text-right py-2 px-3 font-medium w-72">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(adm => (
              <tr key={adm.id} className="border-b hover:bg-gray-50">
                <td className="py-2 px-3">
                  <div className="font-medium">{adm.patient_name}</div>
                  <div className="text-xs text-gray-500">
                    {adm.admission_number}
                    {adm.admission_date && (
                      <> · admitted {new Date(adm.admission_date).toLocaleDateString()}</>
                    )}
                  </div>
                </td>
                <td className="py-2 px-3 text-xs">
                  {adm.discharge_date
                    ? new Date(adm.discharge_date).toLocaleString()
                    : '—'}
                </td>
                <td className="py-2 px-3 text-right">
                  ₹{adm.stayCharges.toFixed(2)}
                </td>
                <td className="py-2 px-3 text-right">
                  ₹{adm.netDeposits.toFixed(2)}
                </td>
                <td className="py-2 px-3 text-right">
                  <span className="text-red-600 font-medium">
                    ₹{adm.owesAmount.toFixed(2)}
                  </span>
                </td>
                <td className="py-2 px-3">
                  {adm.billFinalised
                    ? <Badge className="bg-blue-100 text-blue-800 text-xs">Finalized</Badge>
                    : <Badge className="bg-amber-100 text-amber-800 text-xs">Not finalized</Badge>}
                </td>
                <td className="py-2 px-3 text-right">
                  <div className="flex items-center justify-end gap-1">
                    {canOpenBill && (
                      <Button size="sm" variant="outline"
                              onClick={() => setBillTarget(adm)}
                              title="View bill, apply discount/tax, generate & download">
                        <Receipt className="h-3.5 w-3.5 mr-1" /> View / adjust
                      </Button>
                    )}
                    <Button size="sm" variant="outline"
                            onClick={() => downloadBill(adm)}
                            title="Download the current bill as PDF (preview if not yet generated)">
                      <FileDown className="h-3.5 w-3.5 mr-1" /> Download
                    </Button>
                    {canCollect && (
                      <Button size="sm"
                              onClick={() => openCollect(adm)}>
                        <Wallet className="h-3.5 w-3.5 mr-1" /> Collect
                        <ChevronRight className="h-3.5 w-3.5 ml-0.5" />
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Bill detail popup — view + adjust + generate + download */}
      <BillDetailDialog
        open={!!billTarget}
        admission={billTarget}
        onClose={() => setBillTarget(null)}
        onFinalized={() => { fetchRows(); }}
      />

      {/* Collect payment dialog */}
      <Dialog open={!!target} onOpenChange={v => !v && setTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Collect payment</DialogTitle>
          </DialogHeader>
          {target && (
            <div className="space-y-3">
              <div className="bg-gray-50 border rounded p-2 text-sm">
                <div><b>{target.patient_name}</b> · {target.admission_number}</div>
                <div className="text-xs text-gray-600">
                  Stay charges ₹{target.stayCharges.toFixed(2)} —
                  Deposits ₹{target.netDeposits.toFixed(2)} =
                  <b className="text-red-600"> Owes ₹{target.owesAmount.toFixed(2)}</b>
                </div>
              </div>
              <div>
                <Label>Amount (₹) *</Label>
                <Input type="number" min="0" step="0.01"
                       value={form.amount}
                       onChange={e => setForm(p => ({ ...p, amount: e.target.value }))} />
                <p className="text-[10px] text-gray-500 mt-1">
                  Pre-filled with the full outstanding amount.
                  Override if accepting a part-payment.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Method</Label>
                  <Select value={form.payment_method}
                          onValueChange={v => setForm(p => ({ ...p, payment_method: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {PAYMENT_METHODS.map(m => (
                        <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Reference #</Label>
                  <Input value={form.reference_number}
                         onChange={e => setForm(p => ({ ...p, reference_number: e.target.value }))}
                         placeholder="Optional (txn / cheque #)" />
                </div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setTarget(null)}>Cancel</Button>
            <Button onClick={submit} disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              <Banknote className="h-4 w-4 mr-1" /> Record payment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default PaymentCollectionTab;
