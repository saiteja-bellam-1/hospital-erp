import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../../../components/ui/dialog';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../../components/ui/select';
import { useToast } from '../../../hooks/use-toast';
import { printPdfFromUrl } from '../../../utils/printPdf';
import {
  Loader2, Receipt, FileDown, AlertTriangle, CheckCircle2, Percent,
} from 'lucide-react';

const fmt = (n) => (Number(n) || 0).toFixed(2);

const BillDetailDialog = ({ open, onClose, admission, onFinalized }) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [billData, setBillData] = useState(null);          // full breakdown
  const [existingBills, setExistingBills] = useState([]);  // any finalised bills
  const [discountType, setDiscountType] = useState('flat');
  const [discountValue, setDiscountValue] = useState(0);
  const [taxPct, setTaxPct] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  // Post-finalize settle dialog
  const [settle, setSettle] = useState(null);  // { mode: 'collect'|'refund', amount, method, reference, notes, busy }

  const fetchData = useCallback(async () => {
    if (!admission?.id) return;
    setLoading(true);
    try {
      const [billRes, billsRes] = await Promise.all([
        axios.get(`/api/inpatient/admissions/${admission.id}/bill`,
                  { params: { unbilled_only: false } }),
        axios.get(`/api/inpatient/admissions/${admission.id}/bills`)
          .catch(() => ({ data: [] })),
      ]);
      setBillData(billRes.data);
      setExistingBills((billsRes.data || []).filter(b => b.status !== 'cancelled'));
    } catch (err) {
      toast({
        variant: 'destructive', title: 'Error',
        description: err.response?.data?.detail || 'Failed to load bill',
      });
    } finally {
      setLoading(false);
    }
  }, [admission?.id, toast]);

  useEffect(() => {
    if (!open) return;
    // Reset adjustments on open
    setDiscountType('flat');
    setDiscountValue(0);
    setTaxPct(0);
    fetchData();
  }, [open, fetchData]);

  const grandTotal = Number(billData?.grand_total || 0);
  const discountAmt = useMemo(() => {
    const v = Number(discountValue) || 0;
    if (v <= 0) return 0;
    return discountType === 'percentage'
      ? Math.min((grandTotal * v) / 100, grandTotal)
      : Math.min(v, grandTotal);
  }, [discountType, discountValue, grandTotal]);
  const afterDiscount = Math.max(grandTotal - discountAmt, 0);
  const taxAmt = ((Number(taxPct) || 0) / 100) * afterDiscount;
  const finalTotal = afterDiscount + taxAmt;

  const hasFinalBill = existingBills.some(b => b.bill_subtype === 'final');
  const latestFinal = existingBills.find(b => b.bill_subtype === 'final');

  // Generate (finalize) the bill with current discount/tax.
  const generateBill = async () => {
    setSubmitting(true);
    try {
      const res = await axios.post(
        `/api/inpatient/admissions/${admission.id}/bill/finalize`,
        {
          discount_type: discountType,
          discount_value: Number(discountValue) || 0,
          tax_percentage: Number(taxPct) || 0,
        },
      );
      toast({ title: 'Bill generated',
              description: 'You can now download and share it with the patient.' });
      await fetchData();
      onFinalized?.();
      // If there's a balance one way or the other, open the Settle dialog.
      const r = res.data || {};
      if (r.requires_action === 'collect' && r.amount_to_collect > 0) {
        setSettle({ mode: 'collect', amount: String(r.amount_to_collect),
                    method: 'cash', reference: '', notes: '', busy: false });
      } else if (r.requires_action === 'refund' && r.amount_to_refund > 0) {
        setSettle({ mode: 'refund', amount: String(r.amount_to_refund),
                    method: 'cash', reference: '', notes: '', busy: false });
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail
        : detail?.message || 'Could not generate bill';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally {
      setSubmitting(false);
    }
  };

  const submitSettle = async () => {
    if (!settle) return;
    const amt = parseFloat(settle.amount);
    if (!(amt > 0)) {
      toast({ variant: 'destructive', title: 'Invalid amount',
              description: 'Enter an amount greater than zero.' });
      return;
    }
    setSettle(s => ({ ...s, busy: true }));
    try {
      const url = settle.mode === 'collect'
        ? `/api/inpatient/admissions/${admission.id}/deposits`
        : `/api/inpatient/admissions/${admission.id}/refund`;
      const body = {
        amount: amt,
        payment_method: settle.method,
        reference_number: settle.reference || undefined,
        notes: settle.notes || undefined,
      };
      if (settle.mode === 'collect') body.deposit_type = 'topup';
      await axios.post(url, body);
      toast({ title: settle.mode === 'collect' ? 'Payment collected' : 'Refund issued',
              description: `₹${amt.toFixed(2)} recorded.` });
      setSettle(null);
      await fetchData();
      onFinalized?.();
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail
        : detail?.message || 'Failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
      setSettle(s => ({ ...s, busy: false }));
    }
  };

  // Fetch the bill PDF as a blob (so axios attaches auth headers), then
  // hand the blob URL to the shared iframe-print helper.
  const downloadPdf = async () => {
    try {
      const res = await axios.get(
        `/api/inpatient/admissions/${admission.id}/bill/pdf`,
        { responseType: 'blob', params: {} },
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
      } catch { /* keep generic */ }
      toast({ variant: 'destructive', title: 'Error', description: msg });
    }
  };

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose?.()}>
      <DialogContent className="max-w-2xl max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span>Bill — {admission?.patient_name}</span>
            <span className="text-xs font-normal text-gray-500">
              {admission?.admission_number}
            </span>
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="py-10 text-center text-gray-500">
            <Loader2 className="h-5 w-5 mx-auto animate-spin" />
            <p className="text-xs mt-2">Loading bill…</p>
          </div>
        ) : !billData ? (
          <div className="py-10 text-center text-gray-500 text-sm">
            No bill data available.
          </div>
        ) : (
          <div className="space-y-4">
            {/* Existing bill status */}
            {hasFinalBill ? (
              <div className="flex items-start gap-2 bg-blue-50 border border-blue-200 rounded p-2 text-xs">
                <CheckCircle2 className="h-4 w-4 text-blue-700 mt-0.5" />
                <div className="flex-1">
                  <p className="font-medium text-blue-900">
                    Final bill already generated — {latestFinal.bill_number}
                  </p>
                  <p className="text-blue-800">
                    ₹{fmt(latestFinal.total_amount)} on{' '}
                    {latestFinal.bill_date
                      ? new Date(latestFinal.bill_date).toLocaleString()
                      : '—'}.
                    To re-generate with different discount/tax, cancel this bill
                    from the admission detail first.
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded p-2 text-xs">
                <AlertTriangle className="h-4 w-4 text-amber-700 mt-0.5" />
                <span className="text-amber-900">
                  Bill not yet generated. Adjust discount / tax below and click
                  <b> Generate bill</b> to create it, then download / share with the patient.
                </span>
              </div>
            )}

            {/* Itemised breakdown */}
            <section className="border rounded-lg p-3 text-sm space-y-1.5">
              <p className="font-semibold mb-1 flex items-center gap-1.5">
                <Receipt className="h-4 w-4" /> Charges breakdown
              </p>
              {billData.room_total > 0 && (
                <div className="flex justify-between">
                  <span className="text-gray-600">
                    Room ({billData.room?.room_number} · {billData.stay_days} day{billData.stay_days === 1 ? '' : 's'})
                  </span>
                  <span>₹{fmt(billData.room_total)}</span>
                </div>
              )}
              {billData.visits && Object.entries(billData.visits).map(([type, data]) => (
                <div key={type} className="flex justify-between">
                  <span className="text-gray-600">
                    {type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                    {' '}(×{data.count})
                  </span>
                  <span>₹{fmt(data.total)}</span>
                </div>
              ))}
              {billData.ot_total > 0 && (
                <div className="flex justify-between">
                  <span className="text-gray-600">
                    OT procedures ({(billData.ot_entries || []).length})
                  </span>
                  <span>₹{fmt(billData.ot_total)}</span>
                </div>
              )}
              {billData.ancillary_total > 0 && (
                <div className="flex justify-between">
                  <span className="text-gray-600">
                    Ancillary services ({(billData.ancillary_entries || []).length})
                  </span>
                  <span>₹{fmt(billData.ancillary_total)}</span>
                </div>
              )}
              {billData.pharmacy_total > 0 && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Pharmacy / Medications</span>
                  <span>₹{fmt(billData.pharmacy_total)}</span>
                </div>
              )}
              {billData.lab_total > 0 && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Lab tests</span>
                  <span>₹{fmt(billData.lab_total)}</span>
                </div>
              )}
              {billData.package && (
                <p className="text-xs text-purple-700">
                  Package mode: ₹{fmt(billData.package.agreed_price)}
                  {' + excess '}₹{fmt(billData.package.excess_total)}
                </p>
              )}
              <div className="border-t pt-2 flex justify-between font-semibold">
                <span>Subtotal</span><span>₹{fmt(grandTotal)}</span>
              </div>
            </section>

            {/* Deposits received */}
            {(billData.deposits || []).length > 0 ? (
              <section className="border rounded-lg p-3 text-sm space-y-1.5">
                <p className="font-semibold mb-2">Deposits Received</p>
                <div className="space-y-1">
                  {billData.deposits.map((d, i) => {
                    const isRefund = d.deposit_type === 'refund' || d.amount < 0;
                    const typeLabel = (d.deposit_type || 'initial').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                    return (
                      <div key={i} className="flex justify-between items-start text-xs">
                        <div className="text-gray-600 space-y-0.5">
                          <span className="font-medium text-gray-800">{d.deposit_number || `#${i + 1}`}</span>
                          <span className="mx-1.5 text-gray-400">·</span>
                          <span>{d.date}</span>
                          <span className="mx-1.5 text-gray-400">·</span>
                          <span className={`inline-block px-1.5 py-0.5 rounded text-xs font-medium ${
                            isRefund ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'
                          }`}>{typeLabel}</span>
                          <span className="mx-1.5 text-gray-400">·</span>
                          <span className="capitalize">{d.method}</span>
                          {d.reference && <><span className="mx-1.5 text-gray-400">·</span><span>{d.reference}</span></>}
                        </div>
                        <span className={`font-medium tabular-nums ${isRefund ? 'text-red-600' : ''}`}>
                          {isRefund ? `(₹${fmt(Math.abs(d.amount))})` : `₹${fmt(d.amount)}`}
                        </span>
                      </div>
                    );
                  })}
                </div>
                <div className="border-t pt-2 space-y-1">
                  <div className="flex justify-between font-semibold">
                    <span>Net Deposits</span>
                    <span>₹{fmt(billData.deposits_total)}</span>
                  </div>
                  <div className={`flex justify-between font-semibold ${billData.balance_due < -0.01 ? 'text-green-700' : billData.balance_due > 0.01 ? 'text-amber-700' : ''}`}>
                    <span>{billData.balance_due < -0.01 ? 'Refund Due' : 'Balance Due'}</span>
                    <span>₹{fmt(Math.abs(billData.balance_due))}</span>
                  </div>
                </div>
              </section>
            ) : (
              <div className="text-xs text-gray-400 italic px-1">No deposits recorded for this admission.</div>
            )}

            {/* Discount + Tax inputs — only meaningful pre-finalization */}
            <section className="border rounded-lg p-3 space-y-3">
              <p className="font-semibold text-sm flex items-center gap-1.5">
                <Percent className="h-4 w-4" /> Adjustments
                {hasFinalBill && (
                  <Badge variant="outline" className="text-xs ml-2">
                    locked — bill already generated
                  </Badge>
                )}
              </p>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <Label className="text-xs">Discount</Label>
                  <div className="flex items-center gap-2">
                    <Select value={discountType}
                            onValueChange={setDiscountType}
                            disabled={hasFinalBill}>
                      <SelectTrigger className="w-[120px] h-9">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="flat">Flat ₹</SelectItem>
                        <SelectItem value="percentage">Percent %</SelectItem>
                      </SelectContent>
                    </Select>
                    <Input type="number" min="0" step="0.01"
                           value={discountValue || ''}
                           onChange={e => setDiscountValue(parseFloat(e.target.value) || 0)}
                           disabled={hasFinalBill}
                           placeholder="0"
                           className="h-9" />
                  </div>
                  {discountAmt > 0 && (
                    <p className="text-xs text-green-700 mt-1">
                      −₹{fmt(discountAmt)} discount
                    </p>
                  )}
                </div>
                <div>
                  <Label className="text-xs">Tax (%)</Label>
                  <Input type="number" min="0" max="100" step="0.01"
                         value={taxPct || ''}
                         onChange={e => setTaxPct(parseFloat(e.target.value) || 0)}
                         disabled={hasFinalBill}
                         placeholder="0"
                         className="h-9" />
                  {taxAmt > 0 && (
                    <p className="text-xs text-orange-700 mt-1">
                      +₹{fmt(taxAmt)} tax
                    </p>
                  )}
                </div>
              </div>

              {(discountAmt > 0 || taxAmt > 0) && (
                <div className="border-t pt-2 flex justify-between text-sm font-semibold">
                  <span>Net amount after adjustments</span>
                  <span>₹{fmt(finalTotal)}</span>
                </div>
              )}
            </section>
          </div>
        )}

        <DialogFooter className="flex items-center justify-between">
          <Button variant="outline" onClick={onClose}>Close</Button>
          <div className="flex gap-2">
            {hasFinalBill ? (
              <Button onClick={downloadPdf}>
                <FileDown className="h-4 w-4 mr-1" /> Download bill PDF
              </Button>
            ) : (
              <>
                <Button variant="outline" onClick={downloadPdf}
                        title="Preview the bill as it stands now (not yet finalized)">
                  <FileDown className="h-4 w-4 mr-1" /> Preview PDF
                </Button>
                <Button onClick={generateBill}
                        disabled={submitting || !billData || grandTotal <= 0}>
                  {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  <Receipt className="h-4 w-4 mr-1" /> Generate bill
                </Button>
              </>
            )}
          </div>
        </DialogFooter>
      </DialogContent>

      {/* Post-finalize settle dialog (collect or refund) */}
      <Dialog open={!!settle} onOpenChange={v => !v && !settle?.busy && setSettle(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {settle?.mode === 'collect' ? 'Collect outstanding amount' : 'Refund excess deposit'}
            </DialogTitle>
          </DialogHeader>
          {settle && (
            <div className="space-y-3 text-sm">
              <div className={`rounded p-2 text-xs ${
                settle.mode === 'collect'
                  ? 'bg-amber-50 border border-amber-200 text-amber-900'
                  : 'bg-green-50 border border-green-200 text-green-900'
              }`}>
                {settle.mode === 'collect'
                  ? `Bill is unpaid by ₹${fmt(settle.amount)}. Record the payment now to mark this admission's bills as paid.`
                  : `Patient has a credit of ₹${fmt(settle.amount)}. Issue the refund before discharge.`}
              </div>
              <div>
                <Label className="text-xs">Amount</Label>
                <Input type="number" min="0" step="0.01" value={settle.amount}
                       onChange={e => setSettle(s => ({ ...s, amount: e.target.value }))} />
              </div>
              <div>
                <Label className="text-xs">Payment method</Label>
                <Select value={settle.method}
                        onValueChange={v => setSettle(s => ({ ...s, method: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="card">Card</SelectItem>
                    <SelectItem value="upi">UPI</SelectItem>
                    <SelectItem value="cheque">Cheque</SelectItem>
                    <SelectItem value="online">Online</SelectItem>
                    <SelectItem value="bank_transfer">Bank transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Reference (txn id / cheque #)</Label>
                <Input value={settle.reference}
                       onChange={e => setSettle(s => ({ ...s, reference: e.target.value }))} />
              </div>
              <div>
                <Label className="text-xs">Notes</Label>
                <Input value={settle.notes}
                       onChange={e => setSettle(s => ({ ...s, notes: e.target.value }))} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setSettle(null)}
                    disabled={settle?.busy}>Skip for now</Button>
            <Button onClick={submitSettle} disabled={settle?.busy}>
              {settle?.busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {settle?.mode === 'collect' ? 'Record payment' : 'Issue refund'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Dialog>
  );
};

export default BillDetailDialog;
