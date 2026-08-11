import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Badge } from '../../../components/ui/badge';
import { useToast } from '../../../hooks/use-toast';
import { errMsg } from '../PharmacyModule';
import { usePharmacyStore } from '../../../contexts/PharmacyStoreContext';
import { usePharmacyPermissions } from '../../../hooks/usePharmacyPermissions';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';
import PatientSearchPicker from '../../../components/PatientSearchPicker';
import PharmacyBatchSelectDialog from '../../../components/pharmacy/PharmacyBatchSelectDialog';
import PharmacyStoreSelector from '../../../components/pharmacy/PharmacyStoreSelector';
import {
  displayPharmacyNumericInput,
  formatBatchSummary,
  formatMoney,
  pharmacyNoSpinInputClass,
  roundMoney,
} from '../../../utils/pharmacyUnits';
import { computeLineTax } from '../../../utils/pharmacyHsnTax';
import { Search, Trash2, Save, Check, Printer, User } from 'lucide-react';

const numberInputClass = `h-8 text-sm ${pharmacyNoSpinInputClass}`;
const compactInput = 'h-8 text-sm';

function calcSrLine(ln, taxMode = 'inclusive') {
  const qty = parseFloat(ln.quantity) || 0;
  const rate = parseFloat(ln.rate) || 0;
  const disc = parseFloat(ln.discount_pct) || 0;
  const taxPct = (parseFloat(ln.sgst_pct) || 0) + (parseFloat(ln.cgst_pct) || 0) + (parseFloat(ln.igst_pct) || 0);
  const gross = qty * rate * (1 - disc / 100);
  const { tax, total } = computeLineTax(gross, taxPct, taxMode);
  return {
    sub: roundMoney(qty * rate),
    disc: roundMoney(qty * rate * disc / 100),
    tax,
    total,
  };
}

export default function SaleReturnEntry() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const saleIdParam = searchParams.get('saleId');
  const navigate = useNavigate();
  const { toast } = useToast();
  const { activeStoreId, storeLocked } = usePharmacyStore();
  const { hasPerm } = usePharmacyPermissions();

  const [header, setHeader] = useState({
    return_date: new Date().toISOString().slice(0, 10),
    sale_id: saleIdParam || '',
    sale_ref: saleIdParam || '',
    patient_name: '',
    patient_phone: '',
    patient_ip_id: '',
    doctor_name: '',
    reason: '',
  });
  const [selectedPatient, setSelectedPatient] = useState(null);
  const [saleHits, setSaleHits] = useState([]);
  const [saleSearching, setSaleSearching] = useState(false);
  const saleSearchTimer = useRef(null);
  const [items, setItems] = useState([]);
  const [lookupQ, setLookupQ] = useState('');
  const [lookupResults, setLookupResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [batchPick, setBatchPick] = useState(null);
  const [docId, setDocId] = useState(id ? Number(id) : null);
  const [status, setStatus] = useState('draft');
  const [saving, setSaving] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [settlement, setSettlement] = useState({
    settlement_method: 'cash',
    settlement_amount: '',
    settlement_reference: '',
  });
  const [previewId, setPreviewId] = useState(null);
  const taxMode = 'inclusive';
  const editable = status === 'draft';

  const loadBatchesForMedicine = async (medicineId, forLine) => {
    if (!medicineId || !activeStoreId) return [];
    try {
      const r = await axios.get('/api/pharmacy/inventory/batches', {
        params: {
          medicine_id: medicineId,
          store_id: activeStoreId,
          active_only: true,
          ...(forLine?.batch_id ? { include_batch_id: forLine.batch_id } : {}),
        },
      });
      return r.data || [];
    } catch {
      return forLine?.batch ? [forLine.batch] : [];
    }
  };

  const lookup = useCallback(async (q) => {
    if (!q || q.length < 2 || !activeStoreId) {
      setLookupResults([]);
      return;
    }
    setSearching(true);
    try {
      const r = await axios.get('/api/pharmacy/medicines/lookup', {
        params: { q, store_id: activeStoreId },
      });
      setLookupResults(r.data || []);
    } catch {
      setLookupResults([]);
    } finally {
      setSearching(false);
    }
  }, [activeStoreId]);

  const onLookupChange = (v) => {
    setLookupQ(v);
    lookup(v);
  };

  const addLine = async (med) => {
    if (!editable) return;
    const batches = await loadBatchesForMedicine(med.id);
    const nearest = batches[0] || null;
    const rate = nearest?.rate_a ?? med.rate_a ?? med.unit_price ?? 0;
    const line = {
      medicine: med,
      quantity: '1',
      rate: String(rate),
      discount_pct: '0',
      sgst_pct: '0',
      cgst_pct: '0',
      igst_pct: '0',
      restock: true,
      sale_item_id: null,
      batch_id: null,
      batch: nearest,
      batches,
      auto_batch: true,
      batch_number: nearest?.batch_number || null,
    };
    setItems((prev) => {
      const next = [...prev, line];
      setBatchPick({ lineIndex: next.length - 1, medicine: med, batches, loading: false });
      return next;
    });
    setLookupQ('');
    setLookupResults([]);
  };

  const updateLine = (i, patch) => {
    setItems((prev) => prev.map((ln, idx) => (idx === i ? { ...ln, ...patch } : ln)));
  };
  const removeLine = (i) => setItems((prev) => prev.filter((_, idx) => idx !== i));

  const openBatchPick = async (i) => {
    const ln = items[i];
    if (!ln?.medicine) return;
    setBatchPick({ lineIndex: i, medicine: ln.medicine, batches: ln.batches || [], loading: true });
    const batches = await loadBatchesForMedicine(ln.medicine.id, ln);
    updateLine(i, { batches });
    setBatchPick({ lineIndex: i, medicine: ln.medicine, batches, loading: false });
  };

  const applyBatch = (batch) => {
    if (batchPick?.lineIndex == null) return;
    const i = batchPick.lineIndex;
    updateLine(i, {
      batch,
      batch_id: batch?.id || null,
      auto_batch: false,
      batch_number: batch?.batch_number || null,
      rate: String(batch?.rate_a ?? items[i]?.rate ?? 0),
    });
    setBatchPick(null);
  };

  const applyAutoBatch = () => {
    if (batchPick?.lineIndex == null) return;
    const i = batchPick.lineIndex;
    const nearest = (items[i]?.batches || batchPick.batches || [])[0] || null;
    updateLine(i, {
      batch: nearest,
      batch_id: null,
      auto_batch: true,
      batch_number: nearest?.batch_number || null,
      rate: String(nearest?.rate_a ?? items[i]?.rate ?? 0),
    });
    setBatchPick(null);
  };

  const totals = useMemo(() => items.reduce((acc, ln) => {
    const c = calcSrLine(ln, taxMode);
    return {
      sub: roundMoney(acc.sub + c.sub),
      disc: roundMoney(acc.disc + c.disc),
      tax: roundMoney(acc.tax + c.tax),
      grand: roundMoney(acc.grand + c.total),
      qty: acc.qty + (parseFloat(ln.quantity) || 0),
    };
  }, { sub: 0, disc: 0, tax: 0, grand: 0, qty: 0 }), [items]);

  const resolveBatchId = (ln) => ln.batch_id || ln.batch?.id || null;

  const payload = () => ({
    return_date: header.return_date,
    sale_id: header.sale_id ? Number(header.sale_id) : null,
    patient_name: header.patient_name || null,
    patient_phone: header.patient_phone || null,
    patient_ip_id: header.patient_ip_id || null,
    doctor_name: header.doctor_name || null,
    reason: header.reason || null,
    store_id: activeStoreId || null,
    tax_mode: taxMode,
    items: items.map((ln) => ({
      sale_item_id: ln.sale_item_id || null,
      medicine_id: ln.medicine.id,
      batch_id: Number(resolveBatchId(ln)),
      quantity: Number(ln.quantity),
      rate: Number(ln.rate || 0),
      discount_pct: Number(ln.discount_pct || 0),
      sgst_pct: Number(ln.sgst_pct || 0),
      cgst_pct: Number(ln.cgst_pct || 0),
      igst_pct: Number(ln.igst_pct || 0),
      restock: !!ln.restock,
    })).filter((it) => it.medicine_id && it.batch_id && it.quantity > 0),
  });

  const handlePatientChange = (patient) => {
    setSelectedPatient(patient);
    if (!patient) {
      setHeader((h) => ({
        ...h,
        patient_name: '',
        patient_phone: '',
        patient_ip_id: '',
      }));
      return;
    }
    const name = [patient.first_name, patient.last_name].filter(Boolean).join(' ').trim();
    setHeader((h) => ({
      ...h,
      patient_name: name,
      patient_phone: patient.primary_phone || '',
      patient_ip_id: patient.patient_id || '',
    }));
  };

  const resolveSale = async (raw) => {
    const q = String(raw || '').trim();
    if (!q) throw new Error('Enter a sale ID or sale number');
    try {
      const r = await axios.get(`/api/pharmacy/sales/${encodeURIComponent(q)}`);
      return r.data;
    } catch (e) {
      if (e?.response?.status !== 404) throw e;
    }
    const r = await axios.get('/api/pharmacy/sales', {
      params: { search: q, limit: 20 },
    });
    const rows = r.data || [];
    const needle = q.toLowerCase();
    const exact = rows.find((s) => String(s.sale_number || '').toLowerCase() === needle);
    const match = exact || (rows.length === 1 ? rows[0] : null);
    if (!match) {
      throw new Error(rows.length
        ? 'Multiple sales matched — pick one from the list or enter the full sale number'
        : 'No sale found for that number');
    }
    const full = await axios.get(`/api/pharmacy/sales/${match.id}`);
    return full.data;
  };

  const searchSales = useCallback((q) => {
    const term = String(q || '').trim();
    if (saleSearchTimer.current) clearTimeout(saleSearchTimer.current);
    if (term.length < 2) {
      setSaleHits([]);
      setSaleSearching(false);
      return;
    }
    setSaleSearching(true);
    saleSearchTimer.current = setTimeout(async () => {
      try {
        const r = await axios.get('/api/pharmacy/sales', {
          params: { search: term, limit: 10 },
        });
        setSaleHits(r.data || []);
      } catch {
        setSaleHits([]);
      } finally {
        setSaleSearching(false);
      }
    }, 250);
  }, []);

  const applySale = useCallback(async (saleRef) => {
    if (!saleRef || !editable) return;
    try {
      const s = await resolveSale(saleRef);
      setHeader((h) => ({
        ...h,
        sale_id: String(s.id),
        sale_ref: s.sale_number || String(s.id),
        patient_name: s.patient_name || '',
        patient_phone: s.patient_phone || '',
        patient_ip_id: s.patient_ip_id || '',
        doctor_name: s.doctor_name || '',
      }));
      setSaleHits([]);
      if (s.patient_ip_id || s.patient_name) {
        const parts = (s.patient_name || '').trim().split(/\s+/);
        setSelectedPatient({
          patient_id: s.patient_ip_id || '',
          first_name: parts[0] || s.patient_name || '',
          last_name: parts.slice(1).join(' '),
          primary_phone: s.patient_phone || '',
        });
      }
      const cartLines = await Promise.all((s.items || []).map(async (it) => {
        let medicine = { id: it.medicine_id, name: it.medicine_name };
        try {
          const mr = await axios.get(`/api/pharmacy/medicines/${it.medicine_id}`);
          medicine = mr.data;
        } catch { /* stub */ }
        const batchStub = {
          id: it.batch_id,
          batch_number: it.batch_number,
          rate_a: it.rate,
          quantity_in_stock: null,
        };
        const batches = await loadBatchesForMedicine(it.medicine_id, {
          batch_id: it.batch_id,
          batch: batchStub,
        });
        const batch = batches.find((b) => b.id === it.batch_id) || batchStub;
        return {
          medicine,
          quantity: String(it.quantity),
          rate: String(it.rate || 0),
          discount_pct: String(it.discount_pct || 0),
          sgst_pct: String(it.sgst_pct || 0),
          cgst_pct: String(it.cgst_pct || 0),
          igst_pct: String(it.igst_pct || 0),
          restock: true,
          sale_item_id: it.id,
          batch_id: it.batch_id,
          batch,
          batches,
          auto_batch: false,
          batch_number: it.batch_number,
        };
      }));
      setItems(cartLines);
      toast({ title: `Loaded sale ${s.sale_number}` });
    } catch (e) {
      toast({
        variant: 'destructive',
        title: 'Failed to load sale',
        description: e?.message || errMsg(e),
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editable, toast, activeStoreId]);

  useEffect(() => {
    if (saleIdParam && !id) applySale(saleIdParam);
  }, [saleIdParam, id, applySale]);

  useEffect(() => {
    if (!id) return;
    (async () => {
      try {
        const r = await axios.get(`/api/pharmacy/sale-returns/${id}`);
        const d = r.data;
        setDocId(d.id);
        setStatus(d.status);
        setHeader({
          return_date: d.return_date,
          sale_id: d.sale_id ? String(d.sale_id) : '',
          sale_ref: d.sale_number || (d.sale_id ? String(d.sale_id) : ''),
          patient_name: d.patient_name || '',
          patient_phone: d.patient_phone || '',
          patient_ip_id: d.patient_ip_id || '',
          doctor_name: d.doctor_name || '',
          reason: d.reason || '',
        });
        if (d.patient_ip_id || d.patient_name) {
          const parts = (d.patient_name || '').trim().split(/\s+/);
          setSelectedPatient({
            patient_id: d.patient_ip_id || '',
            first_name: parts[0] || d.patient_name || '',
            last_name: parts.slice(1).join(' '),
            primary_phone: d.patient_phone || '',
          });
        } else {
          setSelectedPatient(null);
        }
        const mapped = await Promise.all((d.items || []).map(async (it) => {
          let medicine = { id: it.medicine_id, name: it.medicine_name };
          try {
            const mr = await axios.get(`/api/pharmacy/medicines/${it.medicine_id}`);
            medicine = mr.data;
          } catch { /* stub */ }
          const batchStub = {
            id: it.batch_id,
            batch_number: it.batch_number,
            rate_a: it.rate,
          };
          const batches = await loadBatchesForMedicine(it.medicine_id, {
            batch_id: it.batch_id,
            batch: batchStub,
          });
          return {
            medicine,
            quantity: String(it.quantity),
            rate: String(it.rate || 0),
            discount_pct: String(it.discount_pct || 0),
            sgst_pct: String(it.sgst_pct || 0),
            cgst_pct: String(it.cgst_pct || 0),
            igst_pct: String(it.igst_pct || 0),
            restock: it.restock !== false,
            sale_item_id: it.sale_item_id,
            batch_id: it.batch_id,
            batch: batches.find((b) => b.id === it.batch_id) || batchStub,
            batches,
            auto_batch: false,
            batch_number: it.batch_number,
          };
        }));
        setItems(mapped);
        setSettlement({
          settlement_method: d.settlement_method || 'cash',
          settlement_amount: d.settlement_amount != null ? String(d.settlement_amount) : '',
          settlement_reference: d.settlement_reference || '',
        });
      } catch (e) {
        toast({ variant: 'destructive', title: 'Failed to load return', description: errMsg(e) });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, toast]);

  const save = async () => {
    const body = payload();
    if (!body.items.length) {
      toast({ variant: 'destructive', title: 'Add at least one line with a batch' });
      return;
    }
    setSaving(true);
    try {
      let r;
      if (docId) {
        r = await axios.put(`/api/pharmacy/sale-returns/${docId}`, body);
        toast({ title: 'Return updated' });
      } else {
        r = await axios.post('/api/pharmacy/sale-returns', body);
        toast({ title: 'Return drafted' });
        setDocId(r.data.id);
        navigate(`/dashboard/pharmacy/sale-returns/${r.data.id}`, { replace: true });
      }
      setStatus(r.data.status);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Save failed', description: errMsg(e) });
    } finally {
      setSaving(false);
    }
  };

  const confirm = async () => {
    if (!docId) {
      toast({ variant: 'destructive', title: 'Save the draft first' });
      return;
    }
    setSaving(true);
    try {
      const r = await axios.post(`/api/pharmacy/sale-returns/${docId}/confirm`, {
        settlement_method: settlement.settlement_method,
        settlement_amount: settlement.settlement_amount === '' ? null : Number(settlement.settlement_amount),
        settlement_reference: settlement.settlement_reference || null,
      });
      setStatus(r.data.status);
      setConfirmOpen(false);
      toast({ title: 'Sales return confirmed' });
    } catch (e) {
      toast({ variant: 'destructive', title: 'Confirm failed', description: errMsg(e) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col flex-1 min-h-0 gap-2">
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_minmax(280px,320px)] gap-2 items-stretch flex-1 min-h-0">
        <div className="order-2 xl:order-2 flex flex-col min-w-0 min-h-0 h-full xl:max-h-none bg-card border border-border rounded-none xl:rounded-lg overflow-hidden">
          <div className="py-2 px-3 border-b">
            <CardTitle className="text-base flex items-center gap-2">
              <User className="h-4 w-4 text-gray-500" />
              Patient & Totals
            </CardTitle>
          </div>
          <div className="px-3 pb-3 pt-0 space-y-2">
            <div className="relative">
              <Label className="text-xs">Sale (optional)</Label>
              <div className="flex gap-1">
                <Input
                  className={compactInput}
                  disabled={!editable}
                  value={header.sale_ref}
                  onChange={(e) => {
                    const v = e.target.value;
                    setHeader({ ...header, sale_ref: v, sale_id: /^\d+$/.test(v.trim()) ? v.trim() : header.sale_id });
                    searchSales(v);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      applySale(header.sale_ref);
                    }
                  }}
                  placeholder="Sale # or ID…"
                />
                {editable && (
                  <Button type="button" size="sm" variant="outline" className="h-8"
                    onClick={() => applySale(header.sale_ref)}>
                    Load
                  </Button>
                )}
              </div>
              {saleHits.length > 0 && editable && (
                <div className="absolute z-10 left-0 right-0 mt-1 border bg-white rounded shadow-lg max-h-48 overflow-y-auto">
                  {saleHits.map((s) => (
                    <div
                      key={s.id}
                      className="px-3 py-2 hover:bg-gray-100 cursor-pointer text-sm"
                      onClick={() => applySale(String(s.id))}
                    >
                      <div className="font-medium">{s.sale_number}</div>
                      <div className="text-xs text-gray-500">
                        {s.patient_name || '—'} · ₹{(s.grand_total || 0).toFixed?.(2) ?? s.grand_total}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {saleSearching && (
                <p className="text-[10px] text-gray-400 mt-0.5">Searching sales…</p>
              )}
            </div>
            <div>
              <Label className="text-xs">Return date</Label>
              <Input
                type="date"
                className={compactInput}
                disabled={!editable}
                value={header.return_date}
                onChange={(e) => setHeader({ ...header, return_date: e.target.value })}
              />
            </div>
            <PatientSearchPicker
              value={selectedPatient}
              onChange={handlePatientChange}
              label="Patient"
              compact
            />
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Phone</Label>
                <Input
                  className={compactInput}
                  disabled={!editable}
                  value={header.patient_phone}
                  onChange={(e) => setHeader({ ...header, patient_phone: e.target.value })}
                />
              </div>
              <div>
                <Label className="text-xs">Doctor</Label>
                <Input
                  className={compactInput}
                  disabled={!editable}
                  value={header.doctor_name}
                  onChange={(e) => setHeader({ ...header, doctor_name: e.target.value })}
                />
              </div>
            </div>
            <div>
              <Label className="text-xs">Patient name</Label>
              <Input
                className={compactInput}
                disabled={!editable}
                value={header.patient_name}
                onChange={(e) => setHeader({ ...header, patient_name: e.target.value })}
              />
            </div>
            <div>
              <Label className="text-xs">Reason</Label>
              <Textarea
                className="text-sm min-h-[64px]"
                disabled={!editable}
                value={header.reason}
                onChange={(e) => setHeader({ ...header, reason: e.target.value })}
              />
            </div>
            <Badge variant="outline" className="text-xs">{status}</Badge>
          </div>

          <div className="flex-1 min-h-[200px] border-t bg-gray-50/40 flex flex-col justify-end px-4 py-4 space-y-2">
            <div className="flex justify-between text-sm text-gray-600">
              <span>Items</span>
              <span>{items.length}</span>
            </div>
            <div className="flex justify-between text-sm text-gray-600">
              <span>Total qty</span>
              <span>{totals.qty}</span>
            </div>
            <div className="flex justify-between text-sm text-gray-600">
              <span>Subtotal</span>
              <span>₹{totals.sub.toFixed(2)}</span>
            </div>
            {totals.disc > 0 && (
              <div className="flex justify-between text-sm text-gray-600">
                <span>Discount</span>
                <span>−₹{totals.disc.toFixed(2)}</span>
              </div>
            )}
            <div className="flex justify-between text-sm text-gray-600">
              <span>Tax (included)</span>
              <span>₹{totals.tax.toFixed(2)}</span>
            </div>
            <div className="pt-3 mt-1 border-t flex justify-between items-end gap-3">
              <span className="text-base font-medium text-gray-700 pb-1">Grand Total</span>
              <span className="text-4xl font-bold tracking-tight text-gray-900 leading-none">
                ₹{totals.grand.toFixed(2)}
              </span>
            </div>
          </div>
        </div>

        <Card className="order-1 xl:order-1 min-w-0 min-h-0 flex flex-col overflow-hidden rounded-none xl:rounded-lg border-x-0 xl:border-x">
          <CardHeader className="py-2 px-3 shrink-0 space-y-0">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <CardTitle className="text-base">
                {docId ? `Sales Return #${docId}` : 'Sales Return Items'}
              </CardTitle>
              <div className="flex items-center gap-1.5 flex-wrap justify-end">
                <PharmacyStoreSelector compact posMode={storeLocked} />
                <Button size="sm" variant="outline" className="h-8"
                  onClick={() => navigate('/dashboard/pharmacy/sale-returns')}>
                  Back
                </Button>
                {editable && (
                  <Button size="sm" className="h-8" onClick={save} disabled={saving || items.length === 0}>
                    <Save className="h-3.5 w-3.5 mr-1" /> Save
                  </Button>
                )}
                {editable && docId && hasPerm('confirm_sale_return') && (
                  <Button size="sm" className="h-8" onClick={() => {
                    setSettlement((s) => ({
                      ...s,
                      settlement_amount: s.settlement_amount || String(totals.grand),
                    }));
                    setConfirmOpen(true);
                  }} disabled={saving}>
                    <Check className="h-3.5 w-3.5 mr-1" /> Confirm
                  </Button>
                )}
                {status === 'confirmed' && docId && (
                  <Button size="sm" variant="outline" className="h-8" onClick={() => setPreviewId(docId)}>
                    <Printer className="h-3 w-3" />
                  </Button>
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent className="pt-0 px-3 pb-3 flex flex-col min-h-0 flex-1 overflow-hidden">
            {editable && (
              <div className="relative mb-2 shrink-0">
                <Label className="text-xs">Search medicine</Label>
                <Search className="absolute left-2 top-8 h-4 w-4 text-gray-400" />
                <Input
                  className={`pl-8 ${compactInput}`}
                  placeholder="Type name / code…"
                  value={lookupQ}
                  disabled={!activeStoreId}
                  onChange={(e) => onLookupChange(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && lookupResults.length === 1) addLine(lookupResults[0]);
                  }}
                />
                {lookupResults.length > 0 && (
                  <div className="absolute z-10 left-0 right-0 mt-1 border bg-white rounded shadow-lg max-h-64 overflow-y-auto">
                    {lookupResults.map((m) => (
                      <div
                        key={m.id}
                        className="px-3 py-2 hover:bg-gray-100 cursor-pointer text-sm"
                        onClick={() => addLine(m)}
                      >
                        <div className="font-medium flex items-center justify-between gap-2">
                          <span>{m.name}</span>
                          <Badge variant={m.store_stock_qty > 0 ? 'secondary' : 'destructive'} className="text-[10px]">
                            Store: {m.store_stock_qty ?? 0}
                          </Badge>
                        </div>
                        <div className="text-xs text-gray-500">{m.medicine_code}</div>
                      </div>
                    ))}
                  </div>
                )}
                {lookupQ.length >= 2 && !searching && lookupResults.length === 0 && (
                  <div className="absolute z-10 left-0 right-0 mt-1 border bg-white rounded shadow-lg p-3 text-center">
                    <p className="text-sm text-gray-500">No medicines found</p>
                  </div>
                )}
              </div>
            )}

            <div className="flex-1 min-h-0 overflow-y-auto overflow-x-auto">
              {items.length === 0 ? (
                <p className="text-center py-8 text-sm text-gray-500">
                  No items yet — search above or load a sale.
                </p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-600">
                      <th className="py-2 pr-2">Medicine</th>
                      <th className="py-2 pr-2">Batch</th>
                      <th className="py-2 pr-2 w-20">Qty</th>
                      <th className="py-2 pr-2 w-24">Rate</th>
                      <th className="py-2 pr-2 w-16">Restock</th>
                      <th className="py-2 pl-2 text-right">Amount</th>
                      <th className="py-2 w-8" />
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((ln, i) => {
                      const batchSummary = formatBatchSummary(ln.batch || { batch_number: ln.batch_number });
                      const lineTot = calcSrLine(ln, taxMode).total;
                      return (
                        <tr key={i} className="border-b align-top">
                          <td className="py-2 pr-2">
                            <div className="font-medium leading-tight">{ln.medicine?.name}</div>
                            <div className="text-xs text-gray-500">{ln.medicine?.medicine_code}</div>
                          </td>
                          <td className="py-2 pr-2">
                            <button
                              type="button"
                              disabled={!editable}
                              className="text-left text-xs hover:text-blue-700 disabled:opacity-70"
                              onClick={() => openBatchPick(i)}
                            >
                              {batchSummary?.title || ln.batch_number || 'Pick batch'}
                              {batchSummary?.meta && (
                                <div className="text-[10px] text-gray-500">{batchSummary.meta}</div>
                              )}
                            </button>
                          </td>
                          <td className="py-2 pr-2">
                            <Input
                              className={numberInputClass}
                              type="number"
                              min="0"
                              disabled={!editable}
                              value={displayPharmacyNumericInput(ln.quantity)}
                              onChange={(e) => updateLine(i, { quantity: e.target.value })}
                            />
                          </td>
                          <td className="py-2 pr-2">
                            <Input
                              className={numberInputClass}
                              type="number"
                              min="0"
                              step="0.01"
                              disabled={!editable}
                              value={displayPharmacyNumericInput(ln.rate)}
                              onChange={(e) => updateLine(i, { rate: e.target.value })}
                            />
                          </td>
                          <td className="py-2 pr-2">
                            <input
                              type="checkbox"
                              disabled={!editable}
                              checked={!!ln.restock}
                              onChange={(e) => updateLine(i, { restock: e.target.checked })}
                            />
                          </td>
                          <td className="py-2 pl-2 text-right whitespace-nowrap">
                            ₹{formatMoney(lineTot)}
                          </td>
                          <td className="py-2">
                            {editable && (
                              <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => removeLine(i)}>
                                <Trash2 className="h-3 w-3 text-red-500" />
                              </Button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {confirmOpen && (
        <Card>
          <CardHeader className="py-3 px-4"><CardTitle className="text-base">Confirm & settle</CardTitle></CardHeader>
          <CardContent className="pt-0 px-4 pb-4 grid grid-cols-1 md:grid-cols-3 gap-3">
            <div>
              <Label>Method</Label>
              <select
                className="w-full border rounded h-9 px-2"
                value={settlement.settlement_method}
                onChange={(e) => setSettlement({ ...settlement, settlement_method: e.target.value })}
              >
                <option value="cash">Cash</option>
                <option value="upi">UPI</option>
                <option value="card">Card</option>
                <option value="adjust">Adjust</option>
                <option value="none">None</option>
              </select>
            </div>
            <div>
              <Label>Amount</Label>
              <Input
                value={settlement.settlement_amount}
                onChange={(e) => setSettlement({ ...settlement, settlement_amount: e.target.value })}
                placeholder={String(totals.grand)}
              />
            </div>
            <div>
              <Label>Reference</Label>
              <Input
                value={settlement.settlement_reference}
                onChange={(e) => setSettlement({ ...settlement, settlement_reference: e.target.value })}
              />
            </div>
            <div className="md:col-span-3 flex gap-2">
              <Button variant="outline" onClick={() => setConfirmOpen(false)}>Cancel</Button>
              <Button onClick={confirm} disabled={saving}>Confirm return</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <PharmacyBatchSelectDialog
        open={!!batchPick}
        onOpenChange={(open) => { if (!open) setBatchPick(null); }}
        medicine={batchPick?.medicine}
        manufacturer={batchPick?.medicine?.company_name || batchPick?.medicine?.manufacturer || ''}
        batches={batchPick?.batches || []}
        loading={batchPick?.loading}
        includeAutoOption
        showRateTierStep={false}
        onSelectBatch={applyBatch}
        onSelectAuto={applyAutoBatch}
        onCancel={() => setBatchPick(null)}
      />

      <PdfPreviewDialog
        open={!!previewId}
        onClose={() => setPreviewId(null)}
        title="Credit Note Preview"
        path={previewId ? `/api/pharmacy/sale-returns/${previewId}/credit-note/pdf` : null}
      />
    </div>
  );
}
