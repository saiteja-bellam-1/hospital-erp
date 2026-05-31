import React, { useEffect, useState, useRef } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { useToast } from '../../../hooks/use-toast';
import { ArrowLeft, Plus, Trash2, Save, CheckCircle2, ScanLine } from 'lucide-react';
import { errMsg } from '../PharmacyModule';

const TODAY = new Date().toISOString().split('T')[0];

export default function PurchaseEntry() {
  const { toast } = useToast();
  const navigate = useNavigate();

  const [header, setHeader] = useState({
    entry_date: TODAY, supplier_id: null, invoice_number: '', bill_date: TODAY,
    payment_type: 'cash', purchase_type: 'local', notes: '',
  });
  const [items, setItems] = useState([]);   // { medicine_id, batch_number, mrp, quantity, free_quantity, purchase_rate, discount_pct, hsn_id }
  const [suppliers, setSuppliers] = useState([]);
  const [medicines, setMedicines] = useState([]);
  const [hsnList, setHsnList] = useState([]);
  const [draftId, setDraftId] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [scanInput, setScanInput] = useState('');
  const scanRef = useRef(null);

  useEffect(() => {
    Promise.all([
      axios.get('/api/pharmacy/suppliers').then(r => setSuppliers(r.data || [])),
      axios.get('/api/pharmacy/medicines', { params: { active_only: true, include_hidden: false, limit: 500 } }).then(r => setMedicines(r.data || [])),
      axios.get('/api/pharmacy/hsn').then(r => setHsnList(r.data || [])),
    ]).catch(() => {});
  }, []);

  const lineFromMed = (m) => ({
    medicine_id: m.id,
    batch_number: '',
    mrp: m.mrp || 0,
    quantity: 1,
    free_quantity: 0,
    purchase_rate: m.purchase_rate || 0,
    discount_pct: 0,
    hsn_id: m.hsn_id || null,
  });

  const addLine = () => setItems(s => [...s, {
    medicine_id: null, batch_number: '', mrp: 0,
    quantity: 1, free_quantity: 0, purchase_rate: 0, discount_pct: 0, hsn_id: null,
  }]);

  const handleScan = async (e) => {
    if (e.key !== 'Enter' || !scanInput.trim()) return;
    e.preventDefault();
    const code = scanInput.trim();
    try {
      // Try barcode-exact first, then fall back to free-text (medicine code / name)
      let res = await axios.get('/api/pharmacy/medicines/lookup', { params: { barcode: code } });
      let matches = res.data || [];
      if (matches.length === 0) {
        res = await axios.get('/api/pharmacy/medicines/lookup', { params: { q: code } });
        matches = res.data || [];
      }
      if (matches.length === 0) {
        toast({ variant: 'destructive', title: 'No medicine found', description: `Nothing matches "${code}"` });
      } else if (matches.length > 1) {
        toast({ variant: 'destructive', title: 'Ambiguous scan', description: `${matches.length} matches — type a more specific code` });
      } else {
        setItems(s => [...s, lineFromMed(matches[0])]);
        toast({ title: `Added ${matches[0].name}` });
      }
    } catch (err) {
      toast({ variant: 'destructive', title: 'Lookup failed', description: errMsg(err) });
    }
    setScanInput('');
    scanRef.current?.focus();
  };
  const update = (i, patch) => setItems(s => s.map((x, idx) => idx === i ? { ...x, ...patch } : x));
  const remove = (i) => setItems(s => s.filter((_, idx) => idx !== i));

  const calcLine = (ln, hsn) => {
    const base = (ln.quantity || 0) * (ln.purchase_rate || 0);
    const afterDisc = base * (1 - (ln.discount_pct || 0) / 100);
    const taxPct = hsn ? ((hsn.sgst_pct || 0) + (hsn.cgst_pct || 0) + (hsn.igst_pct || 0)) : 0;
    const tax = afterDisc * taxPct / 100;
    return { base, afterDisc, tax, total: afterDisc + tax };
  };
  const totals = items.reduce((acc, ln) => {
    const hsn = hsnList.find(h => h.id === ln.hsn_id);
    const c = calcLine(ln, hsn);
    return { sub: acc.sub + c.base, disc: acc.disc + (c.base - c.afterDisc), tax: acc.tax + c.tax, grand: acc.grand + c.total };
  }, { sub: 0, disc: 0, tax: 0, grand: 0 });

  /** Validate UI rows. Returns { errors: string[], payload } — when errors is
   *  empty, payload is safe to POST. */
  const buildPayload = () => {
    const errors = [];
    if (!header.supplier_id) errors.push('Pick a supplier.');
    if (items.length === 0) errors.push('Add at least one item.');
    items.forEach((it, idx) => {
      const n = idx + 1;
      if (!it.medicine_id) errors.push(`Line ${n}: pick a medicine.`);
      if (!it.batch_number || !String(it.batch_number).trim()) errors.push(`Line ${n}: batch number is required.`);
      const q = parseFloat(it.quantity);
      if (!q || q <= 0) errors.push(`Line ${n}: quantity must be > 0.`);
      const pr = parseFloat(it.purchase_rate);
      if (pr === undefined || pr < 0 || Number.isNaN(pr)) errors.push(`Line ${n}: purchase rate must be ≥ 0.`);
    });
    return {
      errors,
      payload: {
        entry_date: header.entry_date,
        supplier_id: header.supplier_id,
        invoice_number: header.invoice_number || null,
        bill_date: header.bill_date || null,
        payment_type: header.payment_type,
        purchase_type: header.purchase_type || null,
        notes: header.notes || null,
        items: items.map(it => ({
          medicine_id: it.medicine_id,
          batch_number: String(it.batch_number || '').trim(),
          mrp: parseFloat(it.mrp) || 0,
          quantity: parseFloat(it.quantity) || 0,
          free_quantity: parseFloat(it.free_quantity) || 0,
          purchase_rate: parseFloat(it.purchase_rate) || 0,
          discount_pct: parseFloat(it.discount_pct) || 0,
          hsn_id: it.hsn_id || null,
        })),
      },
    };
  };

  const showValidationErrors = (errors) => {
    toast({
      variant: 'destructive',
      title: errors.length === 1 ? 'Fix this before saving' : `Fix ${errors.length} issues before saving`,
      description: errors.slice(0, 4).join(' • ') + (errors.length > 4 ? ` • +${errors.length - 4} more…` : ''),
    });
  };

  const saveDraft = async () => {
    const { errors, payload } = buildPayload();
    if (errors.length) { showValidationErrors(errors); return; }
    setSubmitting(true);
    try {
      const r = draftId
        ? await axios.put(`/api/pharmacy/purchases/${draftId}`, payload)
        : await axios.post('/api/pharmacy/purchases', payload);
      setDraftId(r.data.id);
      toast({ title: `Draft saved: ${r.data.purchase_number}` });
    } catch (e) {
      toast({ variant: 'destructive', title: 'Save failed', description: errMsg(e) });
    } finally { setSubmitting(false); }
  };

  const confirm = async () => {
    const { errors, payload } = buildPayload();
    if (errors.length) { showValidationErrors(errors); return; }
    setSubmitting(true);
    try {
      let id = draftId;
      if (!id) {
        const r = await axios.post('/api/pharmacy/purchases', payload);
        id = r.data.id;
        setDraftId(id);
      } else {
        // Push latest edits to the draft first
        await axios.put(`/api/pharmacy/purchases/${id}`, payload);
      }
      const r2 = await axios.post(`/api/pharmacy/purchases/${id}/confirm`);
      toast({ title: `Confirmed ${r2.data.purchase_number}` });
      navigate('/dashboard/pharmacy');
    } catch (e) {
      toast({ variant: 'destructive', title: 'Confirm failed', description: errMsg(e) });
    } finally { setSubmitting(false); }
  };

  const setH = (k, v) => setHeader(s => ({ ...s, [k]: v }));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button size="sm" variant="outline" onClick={() => navigate('/dashboard/pharmacy')}><ArrowLeft className="h-3 w-3 mr-1" /> Back</Button>
        <h1 className="text-2xl font-bold">New Purchase {draftId && <span className="text-sm text-gray-500">(draft #{draftId})</span>}</h1>
      </div>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Header</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><Label className="text-xs">Entry Date</Label><Input type="date" value={header.entry_date} onChange={e => setH('entry_date', e.target.value)} /></div>
          <div>
            <Label className="text-xs">Supplier *</Label>
            <Select value={header.supplier_id ? String(header.supplier_id) : ''} onValueChange={v => setH('supplier_id', Number(v))}>
              <SelectTrigger><SelectValue placeholder="Pick supplier" /></SelectTrigger>
              <SelectContent>
                {suppliers.map(s => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div><Label className="text-xs">Invoice #</Label><Input value={header.invoice_number} onChange={e => setH('invoice_number', e.target.value)} /></div>
          <div><Label className="text-xs">Bill Date</Label><Input type="date" value={header.bill_date} onChange={e => setH('bill_date', e.target.value)} /></div>
          <div>
            <Label className="text-xs">Payment Type</Label>
            <Select value={header.payment_type} onValueChange={v => setH('payment_type', v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="cash">Cash</SelectItem>
                <SelectItem value="credit">Credit</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div><Label className="text-xs">Purchase Type</Label><Input value={header.purchase_type} onChange={e => setH('purchase_type', e.target.value)} placeholder="local / interstate" /></div>
          <div className="col-span-2"><Label className="text-xs">Notes</Label><Textarea rows={1} value={header.notes} onChange={e => setH('notes', e.target.value)} /></div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex flex-wrap gap-2 justify-between items-center">
            <span>Batch Details</span>
            <div className="flex items-center gap-2 flex-1 max-w-md ml-4">
              <ScanLine className="h-4 w-4 text-gray-500" />
              <Input
                ref={scanRef}
                className="h-8"
                placeholder="Scan barcode or type code / name + Enter"
                value={scanInput}
                onChange={e => setScanInput(e.target.value)}
                onKeyDown={handleScan}
              />
            </div>
            <Button size="sm" variant="outline" onClick={addLine}><Plus className="h-3 w-3 mr-1" /> Add line</Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {items.length === 0 ? (
            <p className="text-center py-4 text-sm text-gray-500">No items — scan a barcode above or click <span className="font-medium">Add line</span>.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b text-left text-gray-600">
                  <th className="py-2 pr-2">Medicine</th>
                  <th className="py-2 pr-2 w-32">Batch #</th>
                  <th className="py-2 pr-2 w-24">MRP</th>
                  <th className="py-2 pr-2 w-20">Qty</th>
                  <th className="py-2 pr-2 w-20">Free</th>
                  <th className="py-2 pr-2 w-24">P-Rate</th>
                  <th className="py-2 pr-2 w-20">Disc %</th>
                  <th className="py-2 pr-2 w-32">HSN</th>
                  <th className="py-2 pr-2 text-right w-24">Line Total</th>
                  <th className="py-2 w-8"></th>
                </tr></thead>
                <tbody>
                  {items.map((ln, i) => {
                    const hsn = hsnList.find(h => h.id === ln.hsn_id);
                    const c = calcLine(ln, hsn);
                    const lineInvalid = !ln.medicine_id || !String(ln.batch_number || '').trim() || !(parseFloat(ln.quantity) > 0);
                    return (
                      <tr key={i} className={`border-b ${lineInvalid ? 'bg-red-50/50' : ''}`}>
                        <td className="py-2 pr-2 min-w-[200px]">
                          <Select value={ln.medicine_id ? String(ln.medicine_id) : ''}
                            onValueChange={v => {
                              const m = medicines.find(x => x.id === Number(v));
                              update(i, { medicine_id: Number(v),
                                          purchase_rate: m?.purchase_rate || 0,
                                          mrp: m?.mrp || 0,
                                          hsn_id: m?.hsn_id || null });
                            }}>
                            <SelectTrigger className="h-8"><SelectValue placeholder="Pick" /></SelectTrigger>
                            <SelectContent>
                              {medicines.map(m => <SelectItem key={m.id} value={String(m.id)}>{m.name}</SelectItem>)}
                            </SelectContent>
                          </Select>
                        </td>
                        <td className="py-2 pr-2">
                          <Input
                            className={`h-8 ${!String(ln.batch_number || '').trim() ? 'border-red-300' : ''}`}
                            placeholder="Batch *"
                            value={ln.batch_number}
                            onChange={e => update(i, { batch_number: e.target.value })}
                          />
                        </td>
                        <td className="py-2 pr-2"><Input className="h-8" type="number" step="0.01" value={ln.mrp} onChange={e => update(i, { mrp: parseFloat(e.target.value) || 0 })} /></td>
                        <td className="py-2 pr-2"><Input className="h-8" type="number" min="0" step="0.5" value={ln.quantity} onChange={e => update(i, { quantity: parseFloat(e.target.value) || 0 })} /></td>
                        <td className="py-2 pr-2"><Input className="h-8" type="number" min="0" step="0.5" value={ln.free_quantity} onChange={e => update(i, { free_quantity: parseFloat(e.target.value) || 0 })} /></td>
                        <td className="py-2 pr-2"><Input className="h-8" type="number" step="0.01" value={ln.purchase_rate} onChange={e => update(i, { purchase_rate: parseFloat(e.target.value) || 0 })} /></td>
                        <td className="py-2 pr-2"><Input className="h-8" type="number" min="0" max="100" step="0.5" value={ln.discount_pct} onChange={e => update(i, { discount_pct: parseFloat(e.target.value) || 0 })} /></td>
                        <td className="py-2 pr-2">
                          <Select value={ln.hsn_id ? String(ln.hsn_id) : '__none'}
                            onValueChange={v => update(i, { hsn_id: v === '__none' ? null : Number(v) })}>
                            <SelectTrigger className="h-8"><SelectValue placeholder="—" /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="__none">(none)</SelectItem>
                              {hsnList.map(h => <SelectItem key={h.id} value={String(h.id)}>{h.code}</SelectItem>)}
                            </SelectContent>
                          </Select>
                        </td>
                        <td className="py-2 pr-2 text-right">₹{c.total.toFixed(2)}</td>
                        <td className="py-2"><Button size="sm" variant="ghost" onClick={() => remove(i)}><Trash2 className="h-3 w-3 text-red-500" /></Button></td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr><td colSpan={8} className="py-2 text-right font-medium">Subtotal:</td><td className="text-right">₹{totals.sub.toFixed(2)}</td><td></td></tr>
                  <tr><td colSpan={8} className="py-1 text-right text-sm text-gray-600">Discount:</td><td className="text-right text-sm text-gray-600">−₹{totals.disc.toFixed(2)}</td><td></td></tr>
                  <tr><td colSpan={8} className="py-1 text-right text-sm text-gray-600">Tax:</td><td className="text-right text-sm text-gray-600">+₹{totals.tax.toFixed(2)}</td><td></td></tr>
                  <tr className="font-bold"><td colSpan={8} className="py-2 text-right">Grand Total:</td><td className="text-right">₹{totals.grand.toFixed(2)}</td><td></td></tr>
                </tfoot>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={saveDraft} disabled={submitting}><Save className="h-4 w-4 mr-2" /> Save Draft</Button>
        <Button onClick={confirm} disabled={submitting || items.length === 0}>
          <CheckCircle2 className="h-4 w-4 mr-2" /> Confirm & Commit
        </Button>
      </div>
    </div>
  );
}
