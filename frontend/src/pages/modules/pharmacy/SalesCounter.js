import React, { useState, useCallback } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { useToast } from '../../../hooks/use-toast';
import { Search, Trash2, ShoppingCart, ArrowLeft, Receipt, Printer, Plus } from 'lucide-react';
import { errMsg } from '../PharmacyModule';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';
import PatientSearchPicker from '../../../components/PatientSearchPicker';
import QuickMedicineDialog from '../../../components/pharmacy/QuickMedicineDialog';

export default function SalesCounter() {
  const { toast } = useToast();
  const navigate = useNavigate();

  const [customer, setCustomer] = useState({
    patient_phone: '', patient_ip_id: '', patient_name: '', patient_address: '',
    doctor_number: '', doctor_name: '', payment_type: 'cash',
  });
  const [items, setItems] = useState([]);   // each: { medicine, quantity, rate, rate_tier, discount_pct, batch_id }
  const [lookupQ, setLookupQ] = useState('');
  const [lookupResults, setLookupResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [lastSale, setLastSale] = useState(null);
  const [previewSaleId, setPreviewSaleId] = useState(null);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [medicineDialogOpen, setMedicineDialogOpen] = useState(false);
  const [medicinePrefill, setMedicinePrefill] = useState({});

  const lookup = useCallback(async (q, isBarcode = false) => {
    if (!q || q.length < 2) { setLookupResults([]); return; }
    setSearching(true);
    try {
      const params = isBarcode ? { barcode: q } : { q };
      const r = await axios.get('/api/pharmacy/medicines/lookup', { params });
      setLookupResults(r.data || []);
    } catch { setLookupResults([]); }
    finally { setSearching(false); }
  }, []);

  const onLookupChange = (v) => { setLookupQ(v); lookup(v); };

  const openMedicineCreate = () => {
    setMedicinePrefill({ name: lookupQ.trim(), medicine_code: lookupQ.trim() });
    setMedicineDialogOpen(true);
  };

  const handleMedicineCreated = async (med) => {
    try {
      const r = await axios.get('/api/pharmacy/medicines/lookup', { params: { q: med.name } });
      const match = (r.data || []).find((m) => m.id === med.id) || med;
      addLine(match);
    } catch {
      addLine(med);
    }
    setLookupQ('');
    setLookupResults([]);
  };

  const handlePatientChange = (patient) => {
    setSelectedPatient(patient);
    if (!patient) {
      setCustomer({
        patient_phone: '', patient_ip_id: '', patient_name: '', patient_address: '',
        doctor_number: '', doctor_name: '', payment_type: customer.payment_type,
      });
      return;
    }
    const name = [patient.first_name, patient.last_name].filter(Boolean).join(' ').trim();
    setCustomer((s) => ({
      ...s,
      patient_phone: patient.primary_phone || '',
      patient_ip_id: patient.patient_id || '',
      patient_name: name,
      patient_address: patient.address || patient.village || '',
    }));
  };

  const addLine = (med) => {
    setItems(s => [...s, {
      medicine: med,
      quantity: 1,
      rate: med.rate_a || med.unit_price || 0,
      rate_tier: 'A',
      discount_pct: med.default_discount_pct || 0,
      batch_id: null,           // FIFO
      barcode_scanned: false,
    }]);
    setLookupQ(''); setLookupResults([]);
  };
  const updateLine = (i, patch) => setItems(s => s.map((x, idx) => idx === i ? { ...x, ...patch } : x));
  const removeLine = (i) => setItems(s => s.filter((_, idx) => idx !== i));

  const setTier = (i, tier) => {
    const ln = items[i];
    const rate = tier === 'B' ? (ln.medicine.rate_b || ln.medicine.unit_price) : (ln.medicine.rate_a || ln.medicine.unit_price);
    updateLine(i, { rate_tier: tier, rate });
  };

  const calcLine = (ln) => {
    const base = (ln.quantity || 0) * (ln.rate || 0);
    const afterDisc = base * (1 - (ln.discount_pct || 0) / 100);
    return afterDisc;  // tax computed server-side from HSN; counter displays pre-tax for now
  };
  const total = items.reduce((acc, ln) => acc + calcLine(ln), 0);

  const submitSale = async () => {
    if (items.length === 0) {
      toast({ variant: 'destructive', title: 'Add at least one item' }); return;
    }
    setSubmitting(true);
    try {
      const payload = {
        ...customer,
        items: items.map(ln => ({
          medicine_id: ln.medicine.id,
          quantity: parseFloat(ln.quantity),
          rate: parseFloat(ln.rate),
          rate_tier: ln.rate_tier,
          discount_pct: parseFloat(ln.discount_pct || 0),
          batch_id: ln.batch_id || null,
          barcode_scanned: !!ln.barcode_scanned,
        })),
      };
      const r = await axios.post('/api/pharmacy/sales', payload);
      toast({ title: `Sale ${r.data.sale_number} saved (₹${r.data.grand_total})` });
      setLastSale(r.data);
      setItems([]);
      setSelectedPatient(null);
      setCustomer({ patient_phone: '', patient_ip_id: '', patient_name: '', patient_address: '', doctor_number: '', doctor_name: '', payment_type: 'cash' });
    } catch (e) {
      toast({ variant: 'destructive', title: 'Sale failed', description: errMsg(e) });
    } finally { setSubmitting(false); }
  };

  const setC = (k, v) => setCustomer(s => ({ ...s, [k]: v }));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button size="sm" variant="outline" onClick={() => navigate('/dashboard/pharmacy')}><ArrowLeft className="h-3 w-3 mr-1" /> Back</Button>
          <h1 className="text-2xl font-bold flex items-center gap-2"><ShoppingCart className="h-6 w-6" /> Sales Counter</h1>
        </div>
        {lastSale && (
          <div className="flex items-center gap-3 text-sm text-gray-600">
            <span>Last sale: <span className="font-mono">{lastSale.sale_number}</span> • ₹{lastSale.grand_total}</span>
            <Button size="sm" variant="outline" onClick={() => setPreviewSaleId(lastSale.id)}>
              <Printer className="h-3 w-3 mr-1" /> Print Invoice
            </Button>
          </div>
        )}
      </div>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Patient & Doctor</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <PatientSearchPicker
            value={selectedPatient}
            onChange={handlePatientChange}
            label="Patient"
            compact
          />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div><Label className="text-xs">Phone</Label><Input value={customer.patient_phone} onChange={e => setC('patient_phone', e.target.value)} /></div>
            <div><Label className="text-xs">IP-ID</Label><Input value={customer.patient_ip_id} onChange={e => setC('patient_ip_id', e.target.value)} /></div>
            <div><Label className="text-xs">Patient Name</Label><Input value={customer.patient_name} onChange={e => setC('patient_name', e.target.value)} /></div>
            <div className="col-span-2"><Label className="text-xs">Address</Label><Input value={customer.patient_address} onChange={e => setC('patient_address', e.target.value)} /></div>
            <div><Label className="text-xs">Doctor #</Label><Input value={customer.doctor_number} onChange={e => setC('doctor_number', e.target.value)} /></div>
            <div><Label className="text-xs">Doctor Name</Label><Input value={customer.doctor_name} onChange={e => setC('doctor_name', e.target.value)} /></div>
            <div>
              <Label className="text-xs">Payment</Label>
              <Select value={customer.payment_type} onValueChange={v => setC('payment_type', v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="cash">Cash</SelectItem>
                  <SelectItem value="credit">Credit</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Add Items</CardTitle></CardHeader>
        <CardContent>
          <div className="flex gap-2 items-end mb-3">
            <div className="flex-1 relative">
              <Label className="text-xs">Search / Scan barcode</Label>
              <Search className="absolute left-2 top-9 h-4 w-4 text-gray-400" />
              <Input className="pl-8" placeholder="Type name / code / scan barcode…"
                value={lookupQ}
                onChange={e => onLookupChange(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && lookupResults.length === 1) addLine(lookupResults[0]); }}
              />
              {lookupResults.length > 0 && (
                <div className="absolute z-10 left-0 right-0 mt-1 border bg-white rounded shadow-lg max-h-64 overflow-y-auto">
                  {lookupResults.map(m => (
                    <div key={m.id} className="px-3 py-2 hover:bg-gray-100 cursor-pointer text-sm" onClick={() => addLine(m)}>
                      <div className="font-medium">{m.name}</div>
                      <div className="text-xs text-gray-500">{m.medicine_code} • Rate A ₹{m.rate_a || m.unit_price} / Rate B ₹{m.rate_b || '—'}</div>
                    </div>
                  ))}
                  <div className="px-3 py-2 border-t bg-gray-50">
                    <Button type="button" size="sm" variant="ghost" className="w-full text-blue-700" onClick={openMedicineCreate}>
                      <Plus className="h-4 w-4 mr-1.5" /> Add new medicine
                    </Button>
                  </div>
                </div>
              )}
              {lookupQ.length >= 2 && !searching && lookupResults.length === 0 && (
                <div className="absolute z-10 left-0 right-0 mt-1 border bg-white rounded shadow-lg p-3 text-center space-y-2">
                  <p className="text-sm text-gray-500">No medicines found for &ldquo;{lookupQ.trim()}&rdquo;</p>
                  <Button type="button" size="sm" variant="outline" onClick={openMedicineCreate}>
                    <Plus className="h-4 w-4 mr-1.5" /> Add new medicine
                  </Button>
                </div>
              )}
            </div>
          </div>

          {items.length === 0 ? (
            <p className="text-center py-4 text-sm text-gray-500">No items yet — search above or scan a barcode.</p>
          ) : (
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-gray-600">
                <th className="py-2 pr-2">Medicine</th>
                <th className="py-2 pr-2 w-20">Qty</th>
                <th className="py-2 pr-2 w-24">Rate</th>
                <th className="py-2 pr-2 w-16">Tier</th>
                <th className="py-2 pr-2 w-20">Disc %</th>
                <th className="py-2 pr-2 text-right">Subtotal</th>
                <th className="py-2 w-8"></th>
              </tr></thead>
              <tbody>
                {items.map((ln, i) => (
                  <tr key={i} className="border-b">
                    <td className="py-2 pr-2">
                      <div className="font-medium">{ln.medicine.name}</div>
                      <div className="text-xs text-gray-500">{ln.medicine.medicine_code}</div>
                    </td>
                    <td className="py-2 pr-2">
                      <Input className="h-8" type="number" min="1" step={ln.medicine.decimal_supported ? '0.5' : '1'}
                        value={ln.quantity} onChange={e => updateLine(i, { quantity: parseFloat(e.target.value) || 0 })} />
                    </td>
                    <td className="py-2 pr-2">
                      <Input className="h-8" type="number" step="0.01"
                        value={ln.rate} onChange={e => updateLine(i, { rate: parseFloat(e.target.value) || 0 })} />
                    </td>
                    <td className="py-2 pr-2">
                      <Select value={ln.rate_tier} onValueChange={v => setTier(i, v)}>
                        <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="A">A</SelectItem>
                          <SelectItem value="B">B</SelectItem>
                        </SelectContent>
                      </Select>
                    </td>
                    <td className="py-2 pr-2">
                      <Input className="h-8" type="number" min="0" max="100" step="0.5"
                        value={ln.discount_pct} onChange={e => updateLine(i, { discount_pct: parseFloat(e.target.value) || 0 })} />
                    </td>
                    <td className="py-2 pr-2 text-right">₹{calcLine(ln).toFixed(2)}</td>
                    <td className="py-2">
                      <Button size="sm" variant="ghost" onClick={() => removeLine(i)}><Trash2 className="h-3 w-3 text-red-500" /></Button>
                    </td>
                  </tr>
                ))}
                <tr className="font-medium">
                  <td colSpan={5} className="py-3 text-right pr-2">Subtotal (excl. tax):</td>
                  <td className="py-3 pr-2 text-right">₹{total.toFixed(2)}</td>
                  <td></td>
                </tr>
              </tbody>
            </table>
          )}

          <p className="text-xs text-gray-500 mt-2">Tax is computed server-side from each medicine's HSN code and reflected on the saved sale.</p>
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={() => { setItems([]); setLastSale(null); setSelectedPatient(null); setCustomer({ patient_phone: '', patient_ip_id: '', patient_name: '', patient_address: '', doctor_number: '', doctor_name: '', payment_type: 'cash' }); }}>Reset</Button>
        <Button onClick={submitSale} disabled={submitting || items.length === 0}>
          <Receipt className="h-4 w-4 mr-2" /> Save Sale
        </Button>
      </div>

      <PdfPreviewDialog
        open={!!previewSaleId}
        onClose={() => setPreviewSaleId(null)}
        title="Sale Invoice Preview"
        path={previewSaleId ? `/api/pharmacy/sales/${previewSaleId}/invoice/pdf` : null}
      />

      <QuickMedicineDialog
        open={medicineDialogOpen}
        onOpenChange={setMedicineDialogOpen}
        prefill={medicinePrefill}
        onCreated={handleMedicineCreated}
      />
    </div>
  );
}
