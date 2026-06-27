import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Badge } from '../../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../../components/ui/dialog';
import { useToast } from '../../../../hooks/use-toast';
import { RefreshCw, Pill, XCircle } from 'lucide-react';
import { Textarea } from '../../../../components/ui/textarea';
import { Label } from '../../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../../components/ui/select';
import { errMsg } from '../../PharmacyModule';
import { printPdfFromUrl } from '../../../../utils/printPdf';
import { supportsStripSale } from '../../../../utils/pharmacyUnits';
import { usePharmacyStore } from '../../../../contexts/PharmacyStoreContext';

export default function PendingRxTab() {
  const { toast } = useToast();
  const { activeStoreId } = usePharmacyStore();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState(null);
  const [qtyTabs, setQtyTabs] = useState({});
  const [qtyStrips, setQtyStrips] = useState({});
  const [billingMode, setBillingMode] = useState('inpatient_bill');
  const [paymentType, setPaymentType] = useState('cash');
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelTarget, setCancelTarget] = useState(null);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelling, setCancelling] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get('/api/pharmacy/prescriptions/pending');
      setRows(r.data || []);
    } catch { /* ignore */ } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const openDispense = (rx) => {
    setTarget(rx);
    const initTabs = {};
    const initStrips = {};
    rx.items.forEach(it => {
      initTabs[it.item_id] = String(it.quantity_remaining);
      initStrips[it.item_id] = '0';
    });
    setQtyTabs(initTabs);
    setQtyStrips(initStrips);
    setBillingMode(rx.admission_id ? 'inpatient_bill' : 'cash_at_pharmacy');
    setPaymentType('cash');
    setOpen(true);
  };

  const submit = async () => {
    const items = target.items
      .map(it => ({
        item_id: it.item_id,
        qty_tabs: parseFloat(qtyTabs[it.item_id] || 0),
        qty_strips: parseFloat(qtyStrips[it.item_id] || 0),
      }))
      .filter(x => x.qty_tabs > 0 || x.qty_strips > 0);
    if (items.length === 0) {
      toast({ variant: 'destructive', title: 'Enter at least one quantity to dispense' });
      return;
    }
    try {
      const r = await axios.post(`/api/pharmacy/prescriptions/${target.id}/dispense`, {
        items,
        store_id: activeStoreId || null,
        billing_mode: billingMode,
        payment_type: paymentType,
      });
      const d = r.data || {};
      toast({
        title: `Dispensed (Rx now ${d.status})`,
        description: d.billing_mode === 'cash_at_pharmacy' && d.grand_total != null
          ? `Collected ₹${Number(d.grand_total).toFixed(2)} · Sale ${d.pharmacy_sale_number}`
          : d.billing_mode === 'inpatient_bill' && target.admission_id
            ? 'Added to inpatient bill (pay at discharge or interim bill)'
            : undefined,
      });
      const rxId = target.id;
      setOpen(false); load();
      printPdfFromUrl(`/api/pharmacy/prescriptions/${rxId}/dispense/pdf`);
      if (d.pharmacy_sale_id) {
        printPdfFromUrl(`/api/pharmacy/sales/${d.pharmacy_sale_id}/invoice/pdf`);
      }
    } catch (e) {
      toast({ variant: 'destructive', title: 'Dispense failed', description: errMsg(e) });
    }
  };

  const openCancel = (rx) => {
    setCancelTarget(rx);
    setCancelReason('');
    setCancelOpen(true);
  };

  const submitCancel = async () => {
    const reason = cancelReason.trim();
    if (reason.length < 2) {
      toast({ variant: 'destructive', title: 'Enter a cancellation reason' });
      return;
    }
    setCancelling(true);
    try {
      const r = await axios.post(
        `/api/pharmacy/prescriptions/${cancelTarget.id}/cancel`,
        { reason },
      );
      const d = r.data || {};
      const detailBits = [];
      if (d.stock_ledger_rows_written) detailBits.push(`stock restored on ${d.stock_ledger_rows_written} batch(es)`);
      if (d.bill_items_removed) detailBits.push(`${d.bill_items_removed} bill line(s) removed`);
      if (d.credit_note_number) detailBits.push(`credit note ${d.credit_note_number} issued`);
      toast({
        title: 'Prescription cancelled',
        description: detailBits.length ? detailBits.join(' · ') : undefined,
      });
      setCancelOpen(false);
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Cancel failed', description: errMsg(e) });
    } finally {
      setCancelling(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex justify-between items-center">
          <span>Pending Prescriptions ({rows.length})</span>
          <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-3 w-3" /></Button>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? <p className="text-center py-6 text-sm text-gray-500">Loading…</p>
          : rows.length === 0 ? <p className="text-center py-6 text-sm text-gray-500">No pending prescriptions</p>
          : (
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-gray-600">
                <th className="py-2 pr-4">Rx #</th><th className="py-2 pr-4">Patient</th><th className="py-2 pr-4">Date</th>
                <th className="py-2 pr-4">Items</th><th className="py-2 pr-4">Status</th>
                <th className="py-2 text-right">Actions</th>
              </tr></thead>
              <tbody>
                {rows.map(rx => (
                  <tr key={rx.id} className="border-b hover:bg-gray-50">
                    <td className="py-2 pr-4 font-mono text-xs">{rx.prescription_number}</td>
                    <td className="py-2 pr-4 text-xs">
                      {rx.patient_name || '—'}
                      {rx.admission_id ? <Badge variant="outline" className="ml-1 text-[10px]">IP</Badge> : null}
                    </td>
                    <td className="py-2 pr-4 text-xs">{new Date(rx.prescription_date).toLocaleString()}</td>
                    <td className="py-2 pr-4">{rx.items.length}</td>
                    <td className="py-2 pr-4"><Badge variant="outline" className="text-xs">{rx.status}</Badge></td>
                    <td className="py-2 text-right space-x-2">
                      <Button size="sm" onClick={() => openDispense(rx)}>
                        <Pill className="h-3 w-3 mr-1" /> Dispense
                      </Button>
                      <Button size="sm" variant="outline" className="text-red-600 border-red-200 hover:bg-red-50" onClick={() => openCancel(rx)}>
                        <XCircle className="h-3 w-3 mr-1" /> Cancel
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>Dispense — {target?.prescription_number}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            {target?.admission_id && (
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs">Billing</Label>
                  <Select value={billingMode} onValueChange={setBillingMode}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="inpatient_bill">Add to inpatient bill</SelectItem>
                      <SelectItem value="cash_at_pharmacy">Collect cash now</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {billingMode === 'cash_at_pharmacy' && (
                  <div>
                    <Label className="text-xs">Payment</Label>
                    <Select value={paymentType} onValueChange={setPaymentType}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="cash">Cash</SelectItem>
                        <SelectItem value="credit">Credit</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
            )}
            <p className="text-xs text-gray-500">FIFO batch picking is used. Leave qty 0 to skip a line.</p>
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-gray-600">
                <th className="py-2 pr-4">Medicine</th><th className="py-2 pr-4">Rate</th>
                <th className="py-2 pr-4">Prescribed</th>
                <th className="py-2 pr-4">Already</th><th className="py-2 pr-4">Remaining</th>
                <th className="py-2 pr-4">Qty Tab</th>
                <th className="py-2 pr-4">Qty Strip</th>
              </tr></thead>
              <tbody>
                {target?.items.map(it => (
                  <tr key={it.item_id} className="border-b">
                    <td className="py-2 pr-4">
                      {it.medicine_name}
                      {it.is_unmapped && (
                        <Badge variant="outline" className="ml-1 text-[10px] text-amber-700 border-amber-300">Unmapped</Badge>
                      )}
                    </td>
                    <td className="py-2 pr-4">₹{Number(it.unit_price || 0).toFixed(2)}</td>
                    <td className="py-2 pr-4">{it.quantity_prescribed}</td>
                    <td className="py-2 pr-4">{it.quantity_dispensed}</td>
                    <td className="py-2 pr-4 font-medium">{it.quantity_remaining}</td>
                    <td className="py-2 pr-4">
                      <Input className="h-7 w-20" type="number" min="0"
                        value={qtyTabs[it.item_id] ?? 0}
                        onChange={e => setQtyTabs(s => ({ ...s, [it.item_id]: e.target.value }))} />
                    </td>
                    <td className="py-2 pr-4">
                      {supportsStripSale({ strip_conversion_factor: it.strip_conversion_factor }) ? (
                        <Input className="h-7 w-20" type="number" min="0"
                          value={qtyStrips[it.item_id] ?? 0}
                          onChange={e => setQtyStrips(s => ({ ...s, [it.item_id]: e.target.value }))} />
                      ) : (
                        <span className="text-xs text-gray-400">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={submit}>Dispense</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Cancel Rx — {cancelTarget?.prescription_number}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 text-sm">
            <p className="text-gray-600">
              Any dispensed stock for this Rx will be returned to the original batch(es).
              If the prescription is already on an inpatient bill, the bill will either be
              adjusted in place (if still a draft) or offset by a credit-note (if locked / paid).
            </p>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Reason</label>
              <Textarea
                rows={3}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="e.g. Patient discharged early / Prescribed in error"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelOpen(false)} disabled={cancelling}>
              Keep Rx
            </Button>
            <Button variant="destructive" onClick={submitCancel} disabled={cancelling}>
              {cancelling ? 'Cancelling…' : 'Cancel Rx'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
