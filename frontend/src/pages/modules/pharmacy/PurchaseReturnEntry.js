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
import { Search, Trash2, Save, Check, Printer, Warehouse } from 'lucide-react';

const numberInputClass = `h-8 text-sm ${pharmacyNoSpinInputClass}`;
const compactInput = 'h-8 text-sm';

function calcPrLine(ln, taxMode = 'exclusive') {
  const qty = parseFloat(ln.quantity) || 0;
  const rate = parseFloat(ln.purchase_rate) || 0;
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

export default function PurchaseReturnEntry() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const purchaseIdParam = searchParams.get('purchaseId');
  const navigate = useNavigate();
  const { toast } = useToast();
  const { activeStoreId, storeLocked } = usePharmacyStore();
  const { hasPerm } = usePharmacyPermissions();

  const [suppliers, setSuppliers] = useState([]);
  const [header, setHeader] = useState({
    return_date: new Date().toISOString().slice(0, 10),
    supplier_id: '',
    purchase_id: purchaseIdParam || '',
    purchase_ref: purchaseIdParam || '',
    reason: '',
  });
  const [purchaseHits, setPurchaseHits] = useState([]);
  const [purchaseSearching, setPurchaseSearching] = useState(false);
  const purchaseSearchTimer = useRef(null);
  const [items, setItems] = useState([]);
  const [lookupQ, setLookupQ] = useState('');
  const [lookupResults, setLookupResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [batchPick, setBatchPick] = useState(null);
  const [doc, setDoc] = useState(null);
  const [docId, setDocId] = useState(id ? Number(id) : null);
  const [saving, setSaving] = useState(false);
  const [previewPath, setPreviewPath] = useState(null);
  const taxMode = 'exclusive';

  const editable = !doc || doc.status === 'draft';

  useEffect(() => {
    axios.get('/api/pharmacy/suppliers', { params: { active_only: true } })
      .then((r) => setSuppliers(r.data || []))
      .catch(() => {});
  }, []);

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
      return (r.data || []).filter((b) => (b.quantity_in_stock || 0) > 0 || b.id === forLine?.batch_id);
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
    const line = {
      medicine: med,
      quantity: '1',
      purchase_rate: String(nearest?.purchase_rate ?? med.purchase_rate ?? 0),
      discount_pct: '0',
      sgst_pct: '0',
      cgst_pct: '0',
      igst_pct: '0',
      purchase_item_id: null,
      batch_id: null,
      batch: nearest,
      batches,
      auto_batch: true,
      batch_number: nearest?.batch_number || null,
    };
    setItems((prev) => {
      const next = [...prev, line];
      setBatchPick({
        lineIndex: next.length - 1,
        medicine: med,
        batches,
        loading: false,
      });
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
    setBatchPick({
      lineIndex: i,
      medicine: ln.medicine,
      batches: ln.batches || [],
      loading: true,
    });
    const batches = await loadBatchesForMedicine(ln.medicine.id, ln);
    updateLine(i, { batches });
    setBatchPick({
      lineIndex: i,
      medicine: ln.medicine,
      batches,
      loading: false,
    });
  };

  const applyBatch = (batch) => {
    if (batchPick?.lineIndex == null) return;
    const i = batchPick.lineIndex;
    updateLine(i, {
      batch,
      batch_id: batch?.id || null,
      auto_batch: false,
      batch_number: batch?.batch_number || null,
      purchase_rate: String(batch?.purchase_rate ?? items[i]?.purchase_rate ?? 0),
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
      purchase_rate: String(nearest?.purchase_rate ?? items[i]?.purchase_rate ?? 0),
    });
    setBatchPick(null);
  };

  const totals = useMemo(() => items.reduce((acc, ln) => {
    const c = calcPrLine(ln, taxMode);
    return {
      sub: roundMoney(acc.sub + c.sub),
      disc: roundMoney(acc.disc + c.disc),
      tax: roundMoney(acc.tax + c.tax),
      grand: roundMoney(acc.grand + c.total),
      qty: acc.qty + (parseFloat(ln.quantity) || 0),
    };
  }, { sub: 0, disc: 0, tax: 0, grand: 0, qty: 0 }), [items]);

  const resolveBatchId = (ln) => {
    if (ln.batch_id) return Number(ln.batch_id);
    if (ln.batch?.id) return Number(ln.batch.id);
    return null;
  };

  const payload = () => ({
    return_date: header.return_date,
    supplier_id: Number(header.supplier_id),
    purchase_id: header.purchase_id ? Number(header.purchase_id) : null,
    reason: header.reason || null,
    store_id: activeStoreId || null,
    tax_mode: taxMode,
    items: items.map((ln) => ({
      purchase_item_id: ln.purchase_item_id || null,
      medicine_id: ln.medicine.id,
      batch_id: resolveBatchId(ln),
      quantity: Number(ln.quantity),
      purchase_rate: Number(ln.purchase_rate || 0),
      discount_pct: Number(ln.discount_pct || 0),
      sgst_pct: Number(ln.sgst_pct || 0),
      cgst_pct: Number(ln.cgst_pct || 0),
      igst_pct: Number(ln.igst_pct || 0),
    })).filter((it) => it.medicine_id && it.batch_id && it.quantity > 0),
  });

  const refreshDoc = useCallback(async (rid) => {
    const r = await axios.get(`/api/pharmacy/purchase-returns/${rid}`);
    const d = r.data;
    setDoc(d);
    setDocId(d.id);
    setHeader({
      return_date: d.return_date,
      supplier_id: String(d.supplier_id),
      purchase_id: d.purchase_id ? String(d.purchase_id) : '',
      purchase_ref: d.purchase_number || (d.purchase_id ? String(d.purchase_id) : ''),
      reason: d.reason || '',
    });
    const mapped = await Promise.all((d.items || []).map(async (it) => {
      let medicine = { id: it.medicine_id, name: it.medicine_name, medicine_code: '' };
      try {
        const mr = await axios.get(`/api/pharmacy/medicines/${it.medicine_id}`);
        medicine = mr.data;
      } catch { /* keep stub */ }
      const batch = {
        id: it.batch_id,
        batch_number: it.batch_number,
        purchase_rate: it.purchase_rate,
        quantity_in_stock: null,
      };
      const batches = await loadBatchesForMedicine(it.medicine_id, { batch_id: it.batch_id, batch });
      return {
        medicine,
        quantity: String(it.quantity),
        purchase_rate: String(it.purchase_rate || 0),
        discount_pct: String(it.discount_pct || 0),
        sgst_pct: String(it.sgst_pct || 0),
        cgst_pct: String(it.cgst_pct || 0),
        igst_pct: String(it.igst_pct || 0),
        purchase_item_id: it.purchase_item_id,
        batch_id: it.batch_id,
        batch: batches.find((b) => b.id === it.batch_id) || batch,
        batches,
        auto_batch: false,
        batch_number: it.batch_number,
      };
    }));
    setItems(mapped);
    return d;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeStoreId]);

  useEffect(() => {
    if (!id) return;
    refreshDoc(id).catch((e) => toast({ variant: 'destructive', title: 'Load failed', description: errMsg(e) }));
  }, [id, refreshDoc, toast]);

  const applyPurchase = async (pref) => {
    if (!pref || !editable) return;
    try {
      const p = await resolvePurchase(pref);
      setHeader((h) => ({
        ...h,
        purchase_id: String(p.id),
        purchase_ref: p.purchase_number || String(p.id),
        supplier_id: String(p.supplier_id),
      }));
      setPurchaseHits([]);
      if (p.status === 'draft') {
        toast({
          variant: 'destructive',
          title: 'Purchase still draft',
          description: 'Confirm the purchase first so stock batches exist for return.',
        });
        return;
      }
      const cartLines = await Promise.all((p.items || []).map(async (it) => {
        let medicine = { id: it.medicine_id, name: it.medicine_name };
        try {
          const mr = await axios.get(`/api/pharmacy/medicines/${it.medicine_id}`);
          medicine = mr.data;
        } catch { /* stub */ }
        const batchStub = {
          id: it.inventory_id,
          batch_number: it.batch_number,
          purchase_rate: it.purchase_rate,
          quantity_in_stock: null,
          expiry_date: it.expiry_date,
        };
        const batches = it.inventory_id
          ? await loadBatchesForMedicine(it.medicine_id, { batch_id: it.inventory_id, batch: batchStub })
          : [];
        const batch = (it.inventory_id && batches.find((b) => b.id === it.inventory_id)) || batchStub;
        return {
          medicine,
          quantity: String(it.quantity),
          purchase_rate: String(it.purchase_rate || 0),
          discount_pct: String(it.discount_pct || 0),
          sgst_pct: String(it.sgst_pct || 0),
          cgst_pct: String(it.cgst_pct || 0),
          igst_pct: String(it.igst_pct || 0),
          purchase_item_id: it.id,
          batch_id: it.inventory_id || null,
          batch: it.inventory_id ? batch : null,
          batches,
          auto_batch: !it.inventory_id,
          batch_number: it.batch_number,
        };
      }));
      const withBatch = cartLines.filter((ln) => ln.batch_id);
      setItems(withBatch.length ? withBatch : cartLines);
      if (!withBatch.length) {
        toast({
          variant: 'destructive',
          title: `Loaded ${p.purchase_number} without batches`,
          description: 'Pick a batch on each line before saving.',
        });
      } else {
        toast({ title: `Loaded purchase ${p.purchase_number}` });
      }
    } catch (e) {
      toast({
        variant: 'destructive',
        title: 'Failed to load purchase',
        description: e?.message || errMsg(e),
      });
    }
  };

  const resolvePurchase = async (raw) => {
    const q = String(raw || '').trim();
    if (!q) throw new Error('Enter a purchase ID or purchase number');
    // Backend accepts numeric id, purchase_number, or invoice_number on this path.
    try {
      const r = await axios.get(`/api/pharmacy/purchases/${encodeURIComponent(q)}`);
      return r.data;
    } catch (e) {
      if (e?.response?.status !== 404) throw e;
    }
    const r = await axios.get('/api/pharmacy/purchases', {
      params: { search: q, limit: 20 },
    });
    const rows = r.data || [];
    const needle = q.toLowerCase();
    const exact = rows.find((p) =>
      String(p.purchase_number || '').toLowerCase() === needle
      || String(p.invoice_number || '').toLowerCase() === needle
    );
    const match = exact || (rows.length === 1 ? rows[0] : null);
    if (!match) {
      throw new Error(rows.length
        ? 'Multiple purchases matched — pick one from the list or enter the full number'
        : 'No purchase found for that number');
    }
    const full = await axios.get(`/api/pharmacy/purchases/${match.id}`);
    return full.data;
  };

  const searchPurchases = useCallback((q) => {
    const term = String(q || '').trim();
    if (purchaseSearchTimer.current) clearTimeout(purchaseSearchTimer.current);
    if (term.length < 2) {
      setPurchaseHits([]);
      setPurchaseSearching(false);
      return;
    }
    setPurchaseSearching(true);
    purchaseSearchTimer.current = setTimeout(async () => {
      try {
        const r = await axios.get('/api/pharmacy/purchases', {
          params: { search: term, limit: 10 },
        });
        setPurchaseHits(r.data || []);
      } catch {
        setPurchaseHits([]);
      } finally {
        setPurchaseSearching(false);
      }
    }, 250);
  }, []);

  useEffect(() => {
    if (purchaseIdParam && !id) applyPurchase(purchaseIdParam);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [purchaseIdParam, id]);

  const persist = async () => {
    const body = payload();
    if (!body.supplier_id || !body.items.length) {
      toast({ variant: 'destructive', title: 'Supplier and lines with batches required' });
      return null;
    }
    let r;
    if (docId) r = await axios.put(`/api/pharmacy/purchase-returns/${docId}`, body);
    else {
      r = await axios.post('/api/pharmacy/purchase-returns', body);
      navigate(`/dashboard/pharmacy/purchase-returns/${r.data.id}`, { replace: true });
    }
    setDoc(r.data);
    setDocId(r.data.id);
    return r.data;
  };

  const save = async () => {
    setSaving(true);
    try {
      const saved = await persist();
      if (saved) toast({ title: 'Purchase return saved' });
      return saved;
    } catch (e) {
      toast({ variant: 'destructive', title: 'Save failed', description: errMsg(e) });
      return null;
    } finally {
      setSaving(false);
    }
  };

  const confirm = async () => {
    setSaving(true);
    try {
      let rid = docId;
      if (editable) {
        const saved = await persist();
        if (!saved) return;
        rid = saved.id;
        toast({ title: 'Purchase return saved' });
      }
      const r = await axios.post(`/api/pharmacy/purchase-returns/${rid}/confirm`);
      setDoc(r.data);
      toast({ title: 'Confirmed — continue with challan' });
      navigate(`/dashboard/pharmacy/purchase-returns?tab=challan&returnId=${rid}`);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Confirm failed', description: errMsg(e) });
    } finally {
      setSaving(false);
    }
  };

  const selectedSupplier = suppliers.find((s) => String(s.id) === String(header.supplier_id));

  return (
    <div className="flex flex-col flex-1 min-h-0 gap-2">
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_minmax(280px,320px)] gap-2 items-stretch flex-1 min-h-0">
        {/* Right rail on xl — supplier + totals */}
        <div className="order-2 xl:order-2 flex flex-col min-w-0 min-h-0 h-full xl:max-h-none bg-card border border-border rounded-none xl:rounded-lg overflow-hidden">
          <div className="py-2 px-3 border-b">
            <CardTitle className="text-base flex items-center gap-2">
              <Warehouse className="h-4 w-4 text-gray-500" />
              Supplier & Totals
            </CardTitle>
          </div>
          <div className="px-3 pb-3 pt-0 space-y-2">
            <div>
              <Label className="text-xs">Supplier</Label>
              <select
                className="w-full border rounded h-8 px-2 text-sm"
                disabled={!editable}
                value={header.supplier_id}
                onChange={(e) => setHeader({ ...header, supplier_id: e.target.value })}
              >
                <option value="">Select supplier…</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
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
            <div className="relative">
              <Label className="text-xs">Purchase (optional)</Label>
              <div className="flex gap-1">
                <Input
                  className={compactInput}
                  disabled={!editable}
                  value={header.purchase_ref}
                  onChange={(e) => {
                    const v = e.target.value;
                    setHeader({
                      ...header,
                      purchase_ref: v,
                      purchase_id: /^\d+$/.test(v.trim()) ? v.trim() : header.purchase_id,
                    });
                    searchPurchases(v);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      applyPurchase(header.purchase_ref);
                    }
                  }}
                  placeholder="PURCH-… / invoice / ID"
                />
                {editable && (
                  <Button type="button" size="sm" variant="outline" className="h-8"
                    onClick={() => applyPurchase(header.purchase_ref)}>
                    Load
                  </Button>
                )}
              </div>
              {purchaseHits.length > 0 && editable && (
                <div className="absolute z-10 left-0 right-0 mt-1 border bg-white rounded shadow-lg max-h-48 overflow-y-auto">
                  {purchaseHits.map((p) => (
                    <div
                      key={p.id}
                      className="px-3 py-2 hover:bg-gray-100 cursor-pointer text-sm"
                      onClick={() => applyPurchase(String(p.id))}
                    >
                      <div className="font-medium">{p.purchase_number}</div>
                      <div className="text-xs text-gray-500">
                        {p.supplier_name || '—'}
                        {p.invoice_number ? ` · Inv ${p.invoice_number}` : ''}
                        {' · '}₹{(p.grand_total || 0).toFixed?.(2) ?? p.grand_total}
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {purchaseSearching && (
                <p className="text-[10px] text-gray-400 mt-0.5">Searching purchases…</p>
              )}
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
            {selectedSupplier && (
              <p className="text-xs text-gray-500 truncate">{selectedSupplier.name}</p>
            )}
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
              <span>Tax</span>
              <span>+₹{totals.tax.toFixed(2)}</span>
            </div>
            <div className="pt-3 mt-1 border-t flex justify-between items-end gap-3">
              <span className="text-base font-medium text-gray-700 pb-1">Grand Total</span>
              <span className="text-4xl font-bold tracking-tight text-gray-900 leading-none">
                ₹{totals.grand.toFixed(2)}
              </span>
            </div>
          </div>
        </div>

        {/* Main cart */}
        <Card className="order-1 xl:order-1 min-w-0 min-h-0 flex flex-col overflow-hidden rounded-none xl:rounded-lg border-x-0 xl:border-x">
          <CardHeader className="py-2 px-3 shrink-0 space-y-0">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <CardTitle className="text-base">
                {doc ? doc.return_number : 'Purchase Return Items'}
              </CardTitle>
              <div className="flex items-center gap-1.5 flex-wrap justify-end">
                <PharmacyStoreSelector compact posMode={storeLocked} />
                <Button size="sm" variant="outline" className="h-8"
                  onClick={() => navigate('/dashboard/pharmacy/purchase-returns')}>
                  Back
                </Button>
                {editable && hasPerm('create_purchase_return') && (
                  <Button size="sm" className="h-8" onClick={save} disabled={saving || items.length === 0}>
                    <Save className="h-3.5 w-3.5 mr-1" /> Save
                  </Button>
                )}
                {doc?.status === 'draft' && hasPerm('confirm_purchase_return') && (
                  <Button size="sm" className="h-8" onClick={confirm} disabled={saving || items.length === 0}>
                    <Check className="h-3.5 w-3.5 mr-1" /> Confirm
                  </Button>
                )}
                {doc && (
                  <Button size="sm" variant="outline" className="h-8"
                    onClick={() => setPreviewPath(`/api/pharmacy/purchase-returns/${doc.id}/pdf`)}>
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
                  No items yet — search above to add medicines.
                </p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-600">
                      <th className="py-2 pr-2">Medicine</th>
                      <th className="py-2 pr-2">Batch</th>
                      <th className="py-2 pr-2 w-20">Qty</th>
                      <th className="py-2 pr-2 w-24">P-Rate</th>
                      <th className="py-2 pr-2 w-20">Disc%</th>
                      <th className="py-2 pl-2 text-right">Amount</th>
                      <th className="py-2 w-8" />
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((ln, i) => {
                      const batchSummary = formatBatchSummary(ln.batch || { batch_number: ln.batch_number });
                      const lineTot = calcPrLine(ln, taxMode).total;
                      return (
                        <tr key={i} className="border-b align-top">
                          <td className="py-2 pr-2">
                            <div className="font-medium leading-tight">{ln.medicine?.name}</div>
                            <div className="text-xs text-gray-500">{ln.medicine?.medicine_code}</div>
                            {ln.batch && (
                              <div className="text-[10px] text-gray-500">
                                Stock: {ln.batch.quantity_in_stock ?? '—'}
                              </div>
                            )}
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
                              value={displayPharmacyNumericInput(ln.purchase_rate)}
                              onChange={(e) => updateLine(i, { purchase_rate: e.target.value })}
                            />
                          </td>
                          <td className="py-2 pr-2">
                            <Input
                              className={numberInputClass}
                              type="number"
                              min="0"
                              max="100"
                              disabled={!editable}
                              value={displayPharmacyNumericInput(ln.discount_pct)}
                              onChange={(e) => updateLine(i, { discount_pct: e.target.value })}
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
            <p className="text-xs text-gray-500 mt-2 shrink-0">
              After confirm, create challan / CN / debit note from Purchase Returns → workflow tabs. Stock reduces on challan.
            </p>
          </CardContent>
        </Card>
      </div>


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
        open={!!previewPath}
        onClose={() => setPreviewPath(null)}
        title="Purchase Return Preview"
        path={previewPath}
      />
    </div>
  );
}
