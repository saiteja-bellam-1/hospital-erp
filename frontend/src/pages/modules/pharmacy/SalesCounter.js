import React, { useState, useCallback, useEffect, useMemo } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Badge } from '../../../components/ui/badge';
import { useToast } from '../../../hooks/use-toast';
import { Search, Trash2, ShoppingCart, ArrowLeft, Receipt, Printer, Plus, ArrowLeftRight, AlertTriangle, ChevronDown, ChevronUp, User } from 'lucide-react';
import { errMsg } from '../PharmacyModule';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';
import PatientSearchPicker from '../../../components/PatientSearchPicker';
import QuickMedicineDialog from '../../../components/pharmacy/QuickMedicineDialog';
import {
  calcLineSubtotal,
  combinedBaseQty,
  formatBatchLabel,
  formatRatesHint,
  linePricingSource,
  stripSaleRate,
  supportsStripSale,
  tabSaleRate,
  roundMoney,
} from '../../../utils/pharmacyUnits';
import { computeLineTax, hsnTotalTaxPct } from '../../../utils/pharmacyHsnTax';
import PharmacyStoreSelector from '../../../components/pharmacy/PharmacyStoreSelector';
import { usePharmacyStore } from '../../../contexts/PharmacyStoreContext';
import { usePharmacyPermissions } from '../../../hooks/usePharmacyPermissions';
import FormNavContainer from '../../../components/FormNavContainer';
import { NAV_SKIP_ATTR, navCellProps } from '../../../utils/formNavigation';

const CART_KEY = 'pharmacy_pos_cart_v1';

function loadCart() {
  try {
    const raw = sessionStorage.getItem(CART_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveCart(storeId, items, customer) {
  try {
    sessionStorage.setItem(CART_KEY, JSON.stringify({ storeId, items, customer }));
  } catch { /* ignore quota */ }
}

function clearCartStorage() {
  sessionStorage.removeItem(CART_KEY);
}

export default function SalesCounter() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const { activeStoreId, activeStore, storeLocked } = usePharmacyStore();
  const { hasPerm } = usePharmacyPermissions();

  const [customer, setCustomer] = useState({
    patient_phone: '', patient_ip_id: '', patient_name: '', patient_address: '',
    doctor_number: '', doctor_name: '', payment_type: 'cash',
  });
  const [billingMode, setBillingMode] = useState('cash_at_pharmacy');
  const [taxMode, setTaxMode] = useState('exclusive');
  const [hsnList, setHsnList] = useState([]);
  const [items, setItems] = useState([]);
  const [lookupQ, setLookupQ] = useState('');
  const [lookupResults, setLookupResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [lastSale, setLastSale] = useState(null);
  const [previewSaleId, setPreviewSaleId] = useState(null);
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [medicineDialogOpen, setMedicineDialogOpen] = useState(false);
  const [medicinePrefill, setMedicinePrefill] = useState({});
  const [cartRestored, setCartRestored] = useState(false);
  const [patientPanelOpen, setPatientPanelOpen] = useState(false);

  useEffect(() => {
    axios.get('/api/pharmacy/hsn').then((r) => setHsnList(r.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (cartRestored || !activeStoreId) return;
    const saved = loadCart();
    let cancelled = false;
    (async () => {
      if (saved && saved.storeId === activeStoreId && Array.isArray(saved.items)) {
        const refreshed = await Promise.all((saved.items || []).map(async (ln) => {
          const batches = await loadBatchesForMedicine(ln.medicine?.id);
          const batch = ln.batch_id
            ? (batches.find((b) => b.id === ln.batch_id) || null)
            : (ln.batch || batches[0] || null);
          return {
            ...ln,
            batches,
            batch,
            batch_id: batch?.id || null,
          };
        }));
        if (!cancelled) {
          setItems(refreshed);
          if (saved.customer) setCustomer(saved.customer);
        }
      }
      if (!cancelled) setCartRestored(true);
    })();
    return () => { cancelled = true; };
  // loadBatchesForMedicine closes over activeStoreId; restore runs once per store.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeStoreId, cartRestored]);

  useEffect(() => {
    if (!cartRestored || !activeStoreId) return;
    saveCart(activeStoreId, items, customer);
  }, [items, customer, activeStoreId, cartRestored]);

  const lookup = useCallback(async (q, isBarcode = false) => {
    if (!q || q.length < 2) { setLookupResults([]); return; }
    if (!activeStoreId) { setLookupResults([]); return; }
    setSearching(true);
    try {
      const params = isBarcode
        ? { barcode: q, store_id: activeStoreId }
        : { q, store_id: activeStoreId };
      const r = await axios.get('/api/pharmacy/medicines/lookup', { params });
      setLookupResults(r.data || []);
    } catch { setLookupResults([]); }
    finally { setSearching(false); }
  }, [activeStoreId]);

  const onLookupChange = (v) => { setLookupQ(v); lookup(v); };

  const openMedicineCreate = () => {
    setMedicinePrefill({ name: lookupQ.trim(), medicine_code: lookupQ.trim() });
    setMedicineDialogOpen(true);
  };

  const handleMedicineCreated = async (med) => {
    try {
      const r = await axios.get('/api/pharmacy/medicines/lookup', {
        params: { q: med.name, store_id: activeStoreId },
      });
      const match = (r.data || []).find((m) => m.id === med.id) || med;
      addLine(match);
    } catch {
      addLine(med);
    }
    setLookupQ('');
    setLookupResults([]);
  };

  useEffect(() => {
    if (selectedPatient) setPatientPanelOpen(true);
  }, [selectedPatient]);

  const handlePatientChange = (patient) => {
    setSelectedPatient(patient);
    if (!patient) {
      setCustomer({
        patient_phone: '', patient_ip_id: '', patient_name: '', patient_address: '',
        doctor_number: '', doctor_name: '', payment_type: customer.payment_type,
      });
      setBillingMode('cash_at_pharmacy');
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
    setBillingMode('inpatient_bill');
  };

  const loadBatchesForMedicine = async (medicineId) => {
    if (!medicineId || !activeStoreId) return [];
    try {
      const r = await axios.get('/api/pharmacy/inventory/batches', {
        params: { medicine_id: medicineId, store_id: activeStoreId, active_only: true },
      });
      return (r.data || []).filter((b) => (b.quantity_in_stock || 0) > 0);
    } catch {
      return [];
    }
  };

  const addLine = async (med) => {
    const batches = await loadBatchesForMedicine(med.id);
    const defaultBatch = batches[0] || null;
    setItems(s => [...s, {
      medicine: med,
      qty_tabs: 1,
      qty_strips: '',
      rate_tier: 'A',
      discount_pct: med.default_discount_pct || '',
      batch_id: defaultBatch?.id || null,
      batch: defaultBatch,
      batches,
      barcode_scanned: false,
    }]);
    setLookupQ(''); setLookupResults([]);
  };

  const updateLine = (i, patch) => setItems(s => s.map((x, idx) => idx === i ? { ...x, ...patch } : x));
  const removeLine = (i) => setItems(s => s.filter((_, idx) => idx !== i));

  const selectBatch = (i, batchId) => {
    const ln = items[i];
    if (!ln) return;
    if (!batchId || batchId === 'auto') {
      updateLine(i, { batch_id: null, batch: null });
      return;
    }
    const id = parseInt(batchId, 10);
    const batch = (ln.batches || []).find((b) => b.id === id) || null;
    updateLine(i, { batch_id: id, batch });
  };

  const hsnForMedicine = (medicine) => {
    if (!medicine?.hsn_id) return null;
    return hsnList.find((h) => h.id === medicine.hsn_id) || null;
  };

  const saleLineGrossBeforeDisc = (ln) => {
    const tabs = parseFloat(ln.qty_tabs) || 0;
    const strips = parseFloat(ln.qty_strips) || 0;
    const src = linePricingSource(ln);
    const tabR = tabSaleRate(src, ln.rate_tier);
    const stripR = stripSaleRate(src, ln.rate_tier);
    return roundMoney(tabs * tabR + strips * stripR);
  };

  const calcSaleLine = (ln) => {
    const base = saleLineGrossBeforeDisc(ln);
    const afterDisc = calcLineSubtotal(ln);
    const hsn = hsnForMedicine(ln.medicine);
    const { taxable, tax, total } = computeLineTax(afterDisc, hsnTotalTaxPct(hsn), taxMode);
    return { base, afterDisc, taxable, tax, total };
  };

  const totals = items.reduce((acc, ln) => {
    const c = calcSaleLine(ln);
    return {
      sub: acc.sub + c.base,
      disc: acc.disc + (c.base - c.afterDisc),
      tax: acc.tax + c.tax,
      grand: acc.grand + c.total,
    };
  }, { sub: 0, disc: 0, tax: 0, grand: 0 });

  const setTier = (i, tier) => updateLine(i, { rate_tier: tier });

  const lineNeedQty = (ln) => combinedBaseQty(ln.qty_tabs, ln.qty_strips, linePricingSource(ln));
  const lineStoreStock = (ln) => {
    if (ln.batch_id && ln.batch) return ln.batch.quantity_in_stock ?? 0;
    return ln.medicine?.store_stock_qty ?? 0;
  };

  const stockIssues = useMemo(() => items.map((ln) => {
    const need = lineNeedQty(ln);
    const avail = lineStoreStock(ln);
    if (need <= 0) return null;
    if (avail >= need) return null;
    return { ln, need, avail, master: ln.medicine?.master_stock_qty ?? 0 };
  }).filter(Boolean), [items]);

  const canRequestTransfer = hasPerm('create_transfer');

  const requestTransfer = (issue) => {
    navigate('/dashboard/pharmacy/transfers/new', {
      state: {
        toStoreId: activeStoreId,
        medicineId: issue.ln.medicine.id,
        medicineName: issue.ln.medicine.name,
        qty: issue.need,
        returnPath: '/dashboard/pharmacy/sales-counter',
      },
    });
  };

  const submitSale = async () => {
    if (!activeStoreId) {
      toast({ variant: 'destructive', title: 'Select a pharmacy store first' });
      return;
    }
    if (items.length === 0) {
      toast({ variant: 'destructive', title: 'Add at least one item' }); return;
    }
    const invalid = items.find(ln => lineNeedQty(ln) <= 0);
    if (invalid) {
      toast({ variant: 'destructive', title: 'Enter tab or strip qty on each line' }); return;
    }
    if (stockIssues.length > 0) {
      toast({
        variant: 'destructive',
        title: 'Insufficient stock at this store',
        description: `${stockIssues[0].ln.medicine.name}: need ${stockIssues[0].need}, have ${stockIssues[0].avail}`,
      });
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        ...customer,
        store_id: activeStoreId,
        billing_mode: billingMode,
        tax_mode: taxMode,
        items: items.map(ln => ({
          medicine_id: ln.medicine.id,
          qty_tabs: parseFloat(ln.qty_tabs) || 0,
          qty_strips: parseFloat(ln.qty_strips) || 0,
          rate_tier: ln.rate_tier,
          discount_pct: parseFloat(ln.discount_pct || 0),
          batch_id: ln.batch_id || null,
          barcode_scanned: !!ln.barcode_scanned,
        })),
      };
      const r = await axios.post('/api/pharmacy/sales', payload);
      const d = r.data || {};
      toast({
        title: d.billing_mode === 'inpatient_bill'
          ? `Sale ${d.sale_number} added to inpatient bill`
          : `Sale ${d.sale_number} saved (₹${d.grand_total})`,
        description: d.billing_mode === 'inpatient_bill'
          ? 'Patient pays at discharge or interim bill'
          : undefined,
      });
      setLastSale(d);
      setItems([]);
      clearCartStorage();
      setSelectedPatient(null);
      setBillingMode('cash_at_pharmacy');
      setCustomer({ patient_phone: '', patient_ip_id: '', patient_name: '', patient_address: '', doctor_number: '', doctor_name: '', payment_type: 'cash' });
    } catch (e) {
      toast({ variant: 'destructive', title: 'Sale failed', description: errMsg(e) });
    } finally { setSubmitting(false); }
  };

  const setC = (k, v) => setCustomer(s => ({ ...s, [k]: v }));

  const patientSummary = selectedPatient
    ? (customer.patient_name || 'Patient linked')
    : customer.patient_name
      ? customer.patient_name
      : 'Walk-in (optional)';

  const compactInput = 'h-8 text-sm';

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={() => navigate('/dashboard/pharmacy')}><ArrowLeft className="h-3 w-3 mr-1" /> Back</Button>
          <h1 className="text-lg font-bold flex items-center gap-2"><ShoppingCart className="h-5 w-5" /> Sales Counter</h1>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <PharmacyStoreSelector compact posMode={storeLocked || !!activeStore} />
          {lastSale && (
          <div className="flex items-center gap-3 text-sm text-gray-600">
            <span>Last sale: <span className="font-mono">{lastSale.sale_number}</span> • ₹{lastSale.grand_total}</span>
            <Button size="sm" variant="outline" onClick={() => setPreviewSaleId(lastSale.id)}>
              <Printer className="h-3 w-3 mr-1" /> Print Invoice
            </Button>
          </div>
          )}
        </div>
      </div>

      {!activeStoreId && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          No pharmacy store is available for your account. Ask an administrator to assign you to a store under Pharmacy → Stores.
        </div>
      )}

      {stockIssues.length > 0 && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-red-900">
            <AlertTriangle className="h-4 w-4" /> Some lines exceed stock at {activeStore?.code || 'this store'}
          </div>
          {stockIssues.map((issue, idx) => (
            <div key={idx} className="flex flex-wrap items-center justify-between gap-2 text-sm text-red-800">
              <span>
                {issue.ln.medicine.name}: need {issue.need}, have {issue.avail}
                {issue.master > 0 ? ` (master has ${issue.master})` : ''}
              </span>
              {canRequestTransfer && issue.master > 0 && (
                <Button size="sm" variant="outline" className="h-7" onClick={() => requestTransfer(issue)}>
                  <ArrowLeftRight className="h-3 w-3 mr-1" /> Request transfer
                </Button>
              )}
            </div>
          ))}
        </div>
      )}

      <FormNavContainer mode="grid" className="grid grid-cols-1 xl:grid-cols-[minmax(0,300px)_1fr] gap-4 items-start">
      <Card className="xl:order-2 min-w-0">
        <CardHeader className="py-2 px-4">
          <CardTitle className="text-base">Add Items</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          <div className="flex gap-2 items-end mb-3">
            <div className="flex-1 relative">
              <Label className="text-xs">Search / Scan barcode</Label>
              <Search className="absolute left-2 top-8 h-4 w-4 text-gray-400" />
              <Input className={`pl-8 ${compactInput}`} placeholder="Type name / code / scan barcode…"
                value={lookupQ}
                disabled={!activeStoreId}
                onChange={e => onLookupChange(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && lookupResults.length === 1) addLine(lookupResults[0]); }}
                {...{ [NAV_SKIP_ATTR]: '' }}
              />
              {lookupResults.length > 0 && (
                <div className="absolute z-10 left-0 right-0 mt-1 border bg-white rounded shadow-lg max-h-64 overflow-y-auto">
                  {lookupResults.map(m => (
                    <div key={m.id} className="px-3 py-2 hover:bg-gray-100 cursor-pointer text-sm" onClick={() => addLine(m)}>
                      <div className="font-medium flex items-center justify-between gap-2">
                        <span>{m.name}</span>
                        <Badge variant={m.store_stock_qty > 0 ? 'secondary' : 'destructive'} className="text-[10px] shrink-0">
                          Store: {m.store_stock_qty ?? 0}
                        </Badge>
                      </div>
                      <div className="text-xs text-gray-500">
                        {m.medicine_code} · {formatRatesHint(m)}
                        {(m.master_stock_qty ?? 0) > 0 && m.store_stock_qty <= 0 && (
                          <span className="text-amber-600"> · Master: {m.master_stock_qty}</span>
                        )}
                      </div>
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
            <FormNavContainer mode="table" className="overflow-x-auto">
              <table className="w-full text-sm min-w-[900px]">
                <thead><tr className="border-b text-left text-gray-600">
                  <th className="py-2 pr-2">Medicine</th>
                  <th className="py-2 pr-2 min-w-[220px]">Batch</th>
                  <th className="py-2 pr-2 w-20">Qty Tab</th>
                  <th className="py-2 pr-2 w-20">Qty Strip</th>
                  <th className="py-2 pr-2 w-16">Tier</th>
                  <th className="py-2 pr-2 w-20">Disc %</th>
                  <th className="py-2 pr-2 text-right">Subtotal</th>
                  <th className="py-2 w-8"></th>
                </tr></thead>
                <tbody>
                  {items.map((ln, i) => {
                    const need = lineNeedQty(ln);
                    const avail = lineStoreStock(ln);
                    const over = need > avail;
                    const pricing = linePricingSource(ln);
                    const batches = ln.batches || [];
                    return (
                    <tr key={i} className={`border-b ${over ? 'bg-red-50/50' : ''}`}>
                      <td className="py-2 pr-2">
                        <div className="font-medium">{ln.medicine.name}</div>
                        <div className="text-xs text-gray-500">{ln.medicine.medicine_code}</div>
                        <div className="text-[10px] text-gray-500">{formatRatesHint(ln.medicine, ln.rate_tier, ln.batch)}</div>
                        {pricing.strip_conversion_factor > 1 && (
                          <div className="text-[10px] text-gray-400">{pricing.strip_conversion_factor} tabs/strip</div>
                        )}
                        <div className={`text-[10px] ${over ? 'text-red-600 font-medium' : 'text-gray-500'}`}>
                          {ln.batch_id ? 'Batch' : 'Store'} stock: {avail}{over ? ` (need ${need})` : ''}
                        </div>
                      </td>
                      <td className="py-2 pr-2">
                        {batches.length > 0 ? (
                          <Select
                            value={ln.batch_id ? String(ln.batch_id) : 'auto'}
                            onValueChange={(v) => selectBatch(i, v)}
                          >
                            <SelectTrigger className="h-8 text-xs" {...navCellProps(i, 0)}>
                              <SelectValue placeholder="Select batch" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="auto">Auto (nearest expiry)</SelectItem>
                              {batches.map((b) => (
                                <SelectItem key={b.id} value={String(b.id)}>
                                  {formatBatchLabel(b)}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        ) : (
                          <span className="text-xs text-gray-400">No stock batches</span>
                        )}
                      </td>
                      <td className="py-2 pr-2">
                        <Input className="h-8" type="number" min="0" step={ln.medicine.decimal_supported ? '0.5' : '1'}
                          value={ln.qty_tabs ?? 0}
                          onChange={e => updateLine(i, { qty_tabs: parseFloat(e.target.value) || 0 })}
                          {...navCellProps(i, 1)} />
                      </td>
                      <td className="py-2 pr-2">
                        {supportsStripSale(pricing) ? (
                          <Input className="h-8" type="number" min="0" step="1"
                            value={ln.qty_strips ?? ''}
                            onChange={e => updateLine(i, { qty_strips: e.target.value })}
                            {...navCellProps(i, 2)} />
                        ) : (
                          <span className="text-xs text-gray-400">—</span>
                        )}
                      </td>
                      <td className="py-2 pr-2">
                        <Select value={ln.rate_tier} onValueChange={v => setTier(i, v)}>
                          <SelectTrigger className="h-8" {...navCellProps(i, 3)}><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value="A">A</SelectItem>
                            <SelectItem value="B">B</SelectItem>
                          </SelectContent>
                        </Select>
                      </td>
                      <td className="py-2 pr-2">
                        <Input className="h-8" type="number" min="0" max="100" step="0.01"
                          value={ln.discount_pct ?? ''} onChange={e => updateLine(i, { discount_pct: e.target.value })}
                          {...navCellProps(i, 4)} />
                      </td>
                      <td className="py-2 pr-2 text-right">₹{calcSaleLine(ln).total.toFixed(2)}</td>
                      <td className="py-2">
                        <Button size="sm" variant="ghost" onClick={() => removeLine(i)}><Trash2 className="h-3 w-3 text-red-500" /></Button>
                      </td>
                    </tr>
                  );})}
                  <tr className="font-medium">
                    <td colSpan={6} className="py-2 text-right pr-2 text-sm text-gray-600">Subtotal:</td>
                    <td className="py-2 pr-2 text-right text-sm">₹{totals.sub.toFixed(2)}</td>
                    <td></td>
                  </tr>
                  <tr>
                    <td colSpan={6} className="py-1 text-right pr-2 text-sm text-gray-600">Discount:</td>
                    <td className="py-1 pr-2 text-right text-sm text-gray-600">−₹{totals.disc.toFixed(2)}</td>
                    <td></td>
                  </tr>
                  <tr>
                    <td colSpan={6} className="py-1 text-right pr-2 text-sm text-gray-600">
                      Tax ({taxMode === 'inclusive' ? 'included' : 'added'}):
                    </td>
                    <td className="py-1 pr-2 text-right text-sm text-gray-600">
                      {taxMode === 'inclusive' ? '' : '+'}₹{totals.tax.toFixed(2)}
                    </td>
                    <td></td>
                  </tr>
                  <tr className="font-bold">
                    <td colSpan={6} className="py-3 text-right pr-2">Grand Total:</td>
                    <td className="py-3 pr-2 text-right">₹{totals.grand.toFixed(2)}</td>
                    <td></td>
                  </tr>
                </tbody>
              </table>
            </FormNavContainer>
          )}

          <p className="text-xs text-gray-500 mt-2">
            Sales deduct stock from the selected store only. If stock is at master, request a transfer first.
          </p>
        </CardContent>
      </Card>

      <Card className="xl:order-1 xl:sticky xl:top-4">
        <CardHeader className="py-2 px-4">
          <button
            type="button"
            className="flex w-full items-center justify-between gap-2 text-left xl:pointer-events-none"
            onClick={() => setPatientPanelOpen((o) => !o)}
          >
            <CardTitle className="text-base flex items-center gap-2">
              <User className="h-4 w-4 text-gray-500" />
              Patient & Doctor
            </CardTitle>
            <span className="xl:hidden flex items-center gap-2 min-w-0">
              <span className="text-xs text-gray-500 truncate max-w-[140px]">{patientSummary}</span>
              {patientPanelOpen ? <ChevronUp className="h-4 w-4 shrink-0" /> : <ChevronDown className="h-4 w-4 shrink-0" />}
            </span>
          </button>
        </CardHeader>
        <CardContent className={`pt-0 space-y-2 ${patientPanelOpen ? 'block' : 'hidden'} xl:block`}>
          <PatientSearchPicker
            value={selectedPatient}
            onChange={handlePatientChange}
            label="Patient"
            compact
          />
          <div className="grid grid-cols-2 gap-2">
            <div><Label className="text-xs">Phone</Label><Input className={compactInput} value={customer.patient_phone} onChange={e => setC('patient_phone', e.target.value)} /></div>
            <div><Label className="text-xs">IP-ID</Label><Input className={compactInput} value={customer.patient_ip_id} onChange={e => setC('patient_ip_id', e.target.value)} /></div>
            <div className="col-span-2"><Label className="text-xs">Patient Name</Label><Input className={compactInput} value={customer.patient_name} onChange={e => setC('patient_name', e.target.value)} /></div>
            <div className="col-span-2"><Label className="text-xs">Address</Label><Input className={compactInput} value={customer.patient_address} onChange={e => setC('patient_address', e.target.value)} /></div>
            <div><Label className="text-xs">Doctor #</Label><Input className={compactInput} value={customer.doctor_number} onChange={e => setC('doctor_number', e.target.value)} /></div>
            <div><Label className="text-xs">Doctor Name</Label><Input className={compactInput} value={customer.doctor_name} onChange={e => setC('doctor_name', e.target.value)} /></div>
            <div>
              <Label className="text-xs">Payment</Label>
              <Select value={customer.payment_type} onValueChange={v => setC('payment_type', v)}>
                <SelectTrigger className={compactInput}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="cash">Cash</SelectItem>
                  <SelectItem value="credit">Credit</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Tax on rates</Label>
              <Select value={taxMode} onValueChange={setTaxMode}>
                <SelectTrigger className={compactInput}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="exclusive">Tax Exclude</SelectItem>
                  <SelectItem value="inclusive">Tax Include</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {selectedPatient?.patient_id && (
              <div className="col-span-2">
                <Label className="text-xs">Billing</Label>
                <Select value={billingMode} onValueChange={setBillingMode}>
                  <SelectTrigger className={compactInput}><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="inpatient_bill">Add to inpatient bill</SelectItem>
                    <SelectItem value="cash_at_pharmacy">Collect payment now</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
          {billingMode === 'inpatient_bill' && selectedPatient?.patient_id && (
            <p className="text-xs text-blue-700">
              Stock deducted now; payment on discharge bill.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2 xl:col-span-2 xl:order-3">
        <Button variant="outline" onClick={() => {
          setItems([]); setLastSale(null); setSelectedPatient(null); clearCartStorage();
          setCustomer({ patient_phone: '', patient_ip_id: '', patient_name: '', patient_address: '', doctor_number: '', doctor_name: '', payment_type: 'cash' });
        }}>Reset</Button>
        <Button onClick={submitSale} disabled={submitting || items.length === 0 || !activeStoreId || stockIssues.length > 0}>
          <Receipt className="h-4 w-4 mr-2" /> Save Sale
        </Button>
      </div>
      </FormNavContainer>

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
