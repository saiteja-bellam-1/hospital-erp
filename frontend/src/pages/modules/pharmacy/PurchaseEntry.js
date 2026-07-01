import React, { useEffect, useState, useRef, useCallback } from 'react';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { useToast } from '../../../hooks/use-toast';
import { ArrowLeft, Plus, Trash2, Save, CheckCircle2, ScanLine, Pill } from 'lucide-react';
import { errMsg } from '../PharmacyModule';
import PharmacyMasterSelectWithCreate from '../../../components/pharmacy/PharmacyMasterSelectWithCreate';
import PharmacyMedicinePicker from '../../../components/pharmacy/PharmacyMedicinePicker';
import QuickMedicineDialog from '../../../components/pharmacy/QuickMedicineDialog';
import { usePharmacyStore } from '../../../contexts/PharmacyStoreContext';
import FormNavContainer from '../../../components/FormNavContainer';
import { NAV_SKIP_ATTR, navCellProps } from '../../../utils/formNavigation';
import { roundMoney } from '../../../utils/pharmacyUnits';

const TODAY = new Date().toISOString().split('T')[0];

const expiryToDisplay = (iso) => {
  if (!iso) return '';
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime()) || d.getFullYear() >= 2099) return '';
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;
};

export default function PurchaseEntry() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const { id: routeId } = useParams();
  const { stores } = usePharmacyStore();
  const masterStore = stores.find((s) => s.store_type === 'master');

  const [header, setHeader] = useState({
    entry_date: TODAY, supplier_id: null, invoice_number: '', bill_date: TODAY,
    payment_type: 'cash', purchase_type: 'local', notes: '',
  });
  const [items, setItems] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [medicineCache, setMedicineCache] = useState({});
  const [hsnList, setHsnList] = useState([]);
  const [draftId, setDraftId] = useState(null);
  const [purchaseStatus, setPurchaseStatus] = useState(null);
  const [purchaseNumber, setPurchaseNumber] = useState('');
  const [editReason, setEditReason] = useState('');
  const [loadingPurchase, setLoadingPurchase] = useState(Boolean(routeId));
  const [submitting, setSubmitting] = useState(false);
  const [scanInput, setScanInput] = useState('');
  const [medicineDialogOpen, setMedicineDialogOpen] = useState(false);
  const [medicinePrefill, setMedicinePrefill] = useState({});
  const [medicineDialogLineIndex, setMedicineDialogLineIndex] = useState(null);
  const scanRef = useRef(null);

  const isConfirmed = purchaseStatus === 'confirmed';

  const cacheMedicine = useCallback((med) => {
    if (!med?.id) return;
    setMedicineCache((prev) => ({ ...prev, [med.id]: med }));
  }, []);

  const loadMedicinesByIds = useCallback(async (ids) => {
    const unique = [...new Set(ids.filter(Boolean))];
    await Promise.all(unique.map(async (id) => {
      try {
        const r = await axios.get(`/api/pharmacy/medicines/${id}`);
        cacheMedicine(r.data);
      } catch { /* ignore */ }
    }));
  }, [cacheMedicine]);

  useEffect(() => {
    Promise.all([
      axios.get('/api/pharmacy/suppliers').then(r => setSuppliers(r.data || [])),
      axios.get('/api/pharmacy/hsn').then(r => setHsnList(r.data || [])),
    ]).catch(() => {});
  }, []);

  useEffect(() => {
    if (!routeId) return;
    setLoadingPurchase(true);
    axios.get(`/api/pharmacy/purchases/${routeId}`)
      .then(async (r) => {
        const p = r.data;
        if (!['draft', 'confirmed'].includes(p.status)) {
          toast({
            variant: 'destructive',
            title: 'Cannot edit',
            description: `This purchase is ${p.status} and can no longer be edited.`,
          });
          navigate('/dashboard/pharmacy/purchases');
          return;
        }
        setDraftId(p.id);
        setPurchaseStatus(p.status);
        setPurchaseNumber(p.purchase_number || '');
        setHeader({
          entry_date: p.entry_date || TODAY,
          supplier_id: p.supplier_id,
          invoice_number: p.invoice_number || '',
          bill_date: p.bill_date || TODAY,
          payment_type: p.payment_type || 'cash',
          purchase_type: p.purchase_type || 'local',
          notes: p.notes || '',
        });
        const loaded = (p.items || []).map((it) => ({
          medicine_id: it.medicine_id,
          batch_number: it.batch_number || '',
          expiry_mm_yyyy: expiryToDisplay(it.expiry_date),
          mrp: it.mrp || 0,
          quantity: it.quantity ?? 1,
          free_quantity: it.free_quantity || 0,
          purchase_rate: it.purchase_rate || 0,
          discount_pct: it.discount_pct || 0,
        }));
        setItems(loaded);
        await loadMedicinesByIds(loaded.map((it) => it.medicine_id));
      })
      .catch((e) => {
        toast({ variant: 'destructive', title: 'Load failed', description: errMsg(e) });
        navigate('/dashboard/pharmacy/purchases');
      })
      .finally(() => setLoadingPurchase(false));
  }, [routeId, navigate, toast, loadMedicinesByIds]);

  const lineFromMed = (m) => ({
    medicine_id: m.id,
    batch_number: '',
    expiry_mm_yyyy: '',
    mrp: m.mrp || 0,
    quantity: 1,
    free_quantity: 0,
    purchase_rate: m.purchase_rate || 0,
    discount_pct: 0,
  });

  const addLine = () => setItems(s => [...s, {
    medicine_id: null, batch_number: '', expiry_mm_yyyy: '', mrp: 0,
    quantity: 1, free_quantity: 0, purchase_rate: 0, discount_pct: 0,
  }]);

  const expiryToISO = (raw) => {
    if (!raw) return null;
    const s = String(raw).trim();
    const m = s.match(/^(\d{1,2})\s*[/\-.]\s*(\d{2}|\d{4})$/);
    if (!m) return undefined;
    const mo = parseInt(m[1], 10);
    let yr = parseInt(m[2], 10);
    if (yr < 100) yr += 2000;
    if (mo < 1 || mo > 12) return undefined;
    const d = new Date(yr, mo, 0);
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  };

  const handleScan = async (e) => {
    if (e.key !== 'Enter' || !scanInput.trim()) return;
    e.preventDefault();
    const code = scanInput.trim();
    try {
      let res = await axios.get('/api/pharmacy/medicines/lookup', { params: { barcode: code } });
      let matches = res.data || [];
      if (matches.length === 0) {
        res = await axios.get('/api/pharmacy/medicines/lookup', { params: { q: code } });
        matches = res.data || [];
      }
      if (matches.length === 0) {
        openMedicineCreate(null, { name: code, medicine_code: code, barcode: code });
      } else if (matches.length > 1) {
        toast({ variant: 'destructive', title: 'Ambiguous scan', description: `${matches.length} matches — type a more specific code` });
      } else {
        cacheMedicine(matches[0]);
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

  const selectMedicine = (lineIndex, med) => {
    cacheMedicine(med);
    update(lineIndex, {
      medicine_id: med.id,
      purchase_rate: med.purchase_rate || 0,
      mrp: med.mrp || 0,
    });
  };

  const hsnForMedicine = (medicineId) => {
    const med = medicineCache[medicineId];
    if (!med?.hsn_id) return null;
    return hsnList.find((h) => h.id === med.hsn_id) || null;
  };

  const calcLine = (ln, hsn) => {
    const base = roundMoney((ln.quantity || 0) * (ln.purchase_rate || 0));
    const afterDisc = roundMoney(base * (1 - (ln.discount_pct || 0) / 100));
    const taxPct = hsn ? ((hsn.sgst_pct || 0) + (hsn.cgst_pct || 0) + (hsn.igst_pct || 0)) : 0;
    const tax = roundMoney(afterDisc * taxPct / 100);
    return { base, afterDisc, tax, total: roundMoney(afterDisc + tax) };
  };
  const totals = items.reduce((acc, ln) => {
    const c = calcLine(ln, hsnForMedicine(ln.medicine_id));
    return { sub: acc.sub + c.base, disc: acc.disc + (c.base - c.afterDisc), tax: acc.tax + c.tax, grand: acc.grand + c.total };
  }, { sub: 0, disc: 0, tax: 0, grand: 0 });

  const buildPayload = () => {
    const errors = [];
    if (!header.supplier_id) errors.push('Pick a supplier.');
    if (items.length === 0) errors.push('Add at least one item.');
    items.forEach((it, idx) => {
      const n = idx + 1;
      if (!it.medicine_id) errors.push(`Line ${n}: pick or create a medicine.`);
      if (!it.batch_number || !String(it.batch_number).trim()) errors.push(`Line ${n}: batch number is required.`);
      const exp = expiryToISO(it.expiry_mm_yyyy);
      if (exp === undefined) errors.push(`Line ${n}: expiry must be MM/YYYY (e.g. 12/2027).`);
      const q = parseFloat(it.quantity);
      if (!q || q <= 0) errors.push(`Line ${n}: quantity must be > 0.`);
      const pr = parseFloat(it.purchase_rate);
      if (pr === undefined || pr < 0 || Number.isNaN(pr)) errors.push(`Line ${n}: purchase rate must be ≥ 0.`);
    });
    if (isConfirmed && editReason.trim().length < 2) {
      errors.push('Enter a reason for editing this confirmed purchase.');
    }
    return {
      errors,
      payload: {
        entry_date: header.entry_date,
        supplier_id: header.supplier_id,
        store_id: masterStore?.id || null,
        invoice_number: header.invoice_number || null,
        bill_date: header.bill_date || null,
        payment_type: header.payment_type,
        purchase_type: header.purchase_type || null,
        notes: header.notes || null,
        ...(isConfirmed ? { reason: editReason.trim() } : {}),
        items: items.map(it => ({
          medicine_id: it.medicine_id,
          batch_number: String(it.batch_number || '').trim(),
          expiry_date: expiryToISO(it.expiry_mm_yyyy) || null,
          mrp: roundMoney(it.mrp),
          quantity: parseFloat(it.quantity) || 0,
          free_quantity: parseFloat(it.free_quantity) || 0,
          purchase_rate: roundMoney(it.purchase_rate),
          discount_pct: roundMoney(it.discount_pct),
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
      setPurchaseStatus(r.data.status);
      setPurchaseNumber(r.data.purchase_number || '');
      toast({ title: `Draft saved: ${r.data.purchase_number}` });
    } catch (e) {
      toast({ variant: 'destructive', title: 'Save failed', description: errMsg(e) });
    } finally { setSubmitting(false); }
  };

  const saveConfirmedEdit = async () => {
    const { errors, payload } = buildPayload();
    if (errors.length) { showValidationErrors(errors); return; }
    setSubmitting(true);
    try {
      const r = await axios.put(`/api/pharmacy/purchases/${draftId}`, payload);
      toast({ title: `Updated ${r.data.purchase_number}`, description: 'Inventory adjusted for the changes.' });
      navigate('/dashboard/pharmacy/purchases');
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
        await axios.put(`/api/pharmacy/purchases/${id}`, payload);
      }
      const r2 = await axios.post(`/api/pharmacy/purchases/${id}/confirm`);
      toast({ title: `Confirmed ${r2.data.purchase_number}` });
      navigate('/dashboard/pharmacy/purchases');
    } catch (e) {
      toast({ variant: 'destructive', title: 'Confirm failed', description: errMsg(e) });
    } finally { setSubmitting(false); }
  };

  const setH = (k, v) => setHeader(s => ({ ...s, [k]: v }));

  const openMedicineCreate = (lineIndex = null, prefill = {}) => {
    setMedicineDialogLineIndex(lineIndex);
    setMedicinePrefill(prefill);
    setMedicineDialogOpen(true);
  };

  const handleMedicineCreated = (med) => {
    cacheMedicine(med);
    if (medicineDialogLineIndex != null) {
      selectMedicine(medicineDialogLineIndex, med);
    } else {
      setItems((s) => [...s, lineFromMed(med)]);
    }
    setMedicineDialogLineIndex(null);
    toast({ title: 'Medicine added to catalog', description: med.name });
  };

  const pageTitle = isConfirmed
    ? `Edit Purchase ${purchaseNumber}`
    : draftId
      ? `Edit Draft ${purchaseNumber || `#${draftId}`}`
      : 'New Purchase';

  if (loadingPurchase) {
    return <p className="text-center py-12 text-sm text-gray-500">Loading purchase…</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <Button size="sm" variant="outline" onClick={() => navigate('/dashboard/pharmacy/purchases')}><ArrowLeft className="h-3 w-3 mr-1" /> Back</Button>
        <h1 className="text-2xl font-bold flex-1">{pageTitle}</h1>
        <Button size="sm" variant="outline" onClick={() => navigate('/dashboard/pharmacy/medicines')}>
          <Pill className="h-3 w-3 mr-1" /> Medicines catalog
        </Button>
        <Button size="sm" variant="outline" onClick={() => openMedicineCreate()}>
          <Plus className="h-3 w-3 mr-1" /> New medicine
        </Button>
      </div>

      <FormNavContainer mode="grid" className="space-y-4">

      {isConfirmed && (
        <Card className="border-amber-200 bg-amber-50/50">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Edit reason *</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-xs text-gray-600 mb-2">
              Confirmed purchases are corrected in place — stock is adjusted and this reason is logged.
              Quantities cannot be reduced below what has already been sold or dispensed.
            </p>
            <Textarea
              rows={2}
              placeholder="e.g. wrong invoice rate, batch number typo, supplier invoice correction"
              value={editReason}
              onChange={(e) => setEditReason(e.target.value)}
            />
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Header</CardTitle></CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div><Label className="text-xs">Entry Date</Label><Input type="date" value={header.entry_date} onChange={e => setH('entry_date', e.target.value)} /></div>
          <div>
            <Label className="text-xs">Supplier *</Label>
            <PharmacyMasterSelectWithCreate
              path="suppliers"
              value={header.supplier_id}
              onChange={(v) => setH('supplier_id', v)}
              options={suppliers}
              onOptionsChange={setSuppliers}
              placeholder="Pick supplier"
            />
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
                placeholder="Scan barcode or type code + Enter"
                value={scanInput}
                onChange={e => setScanInput(e.target.value)}
                onKeyDown={handleScan}
                {...{ [NAV_SKIP_ATTR]: '' }}
              />
            </div>
            <Button size="sm" variant="outline" onClick={addLine}><Plus className="h-3 w-3 mr-1" /> Add line</Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-gray-600 mb-3">
            Search the catalog to pick an existing medicine, or use <span className="font-medium">+ New medicine</span> when
            the product is not listed yet. You can also open the full{' '}
            <button type="button" className="text-blue-700 underline font-medium" onClick={() => navigate('/dashboard/pharmacy/medicines')}>
              Medicines
            </button>{' '}
            catalog to manage items.
          </p>
          {items.length === 0 ? (
            <p className="text-center py-4 text-sm text-gray-500">
              No items — scan a catalog barcode, search on a line, or click <span className="font-medium">Add line</span>.
            </p>
          ) : (
            <FormNavContainer mode="table" className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b text-left text-gray-600">
                  <th className="py-2 pr-2">Medicine</th>
                  <th className="py-2 pr-2 w-32">Batch #</th>
                  <th className="py-2 pr-2 w-24">Expiry</th>
                  <th className="py-2 pr-2 w-24">MRP</th>
                  <th className="py-2 pr-2 w-20">Qty</th>
                  <th className="py-2 pr-2 w-20">Free</th>
                  <th className="py-2 pr-2 w-24">P-Rate</th>
                  <th className="py-2 pr-2 w-20">Disc %</th>
                  <th className="py-2 pr-2 text-right w-24">Line Total</th>
                  <th className="py-2 w-8"></th>
                </tr></thead>
                <tbody>
                  {items.map((ln, i) => {
                    const c = calcLine(ln, hsnForMedicine(ln.medicine_id));
                    const lineInvalid = !ln.medicine_id || !String(ln.batch_number || '').trim() || !(parseFloat(ln.quantity) > 0);
                    return (
                      <tr key={i} className={`border-b ${lineInvalid ? 'bg-red-50/50' : ''}`}>
                        <td className="py-2 pr-2 min-w-[220px]">
                          <PharmacyMedicinePicker
                            value={ln.medicine_id}
                            medicine={medicineCache[ln.medicine_id]}
                            onSelect={(m) => selectMedicine(i, m)}
                            onCreateNew={(q) => openMedicineCreate(i, {
                              name: q || '',
                              medicine_code: q || '',
                              barcode: q || undefined,
                            })}
                            navProps={navCellProps(i, 0)}
                          />
                        </td>
                        <td className="py-2 pr-2">
                          <Input
                            className={`h-8 ${!String(ln.batch_number || '').trim() ? 'border-red-300' : ''}`}
                            placeholder="Batch *"
                            value={ln.batch_number}
                            onChange={e => update(i, { batch_number: e.target.value })}
                            {...navCellProps(i, 1)}
                          />
                        </td>
                        <td className="py-2 pr-2">
                          {(() => {
                            const expInvalid = expiryToISO(ln.expiry_mm_yyyy) === undefined;
                            return (
                              <Input
                                className={`h-8 ${expInvalid ? 'border-red-300' : ''}`}
                                placeholder="MM/YYYY"
                                value={ln.expiry_mm_yyyy || ''}
                                onChange={e => update(i, { expiry_mm_yyyy: e.target.value })}
                                {...navCellProps(i, 2)}
                              />
                            );
                          })()}
                        </td>
                        <td className="py-2 pr-2"><Input className="h-8" type="number" step="0.01" min="0" value={ln.mrp} onChange={e => update(i, { mrp: roundMoney(e.target.value) })} {...navCellProps(i, 3)} /></td>
                        <td className="py-2 pr-2"><Input className="h-8" type="number" min="0" step="0.5" value={ln.quantity} onChange={e => update(i, { quantity: parseFloat(e.target.value) || 0 })} {...navCellProps(i, 4)} /></td>
                        <td className="py-2 pr-2"><Input className="h-8" type="number" min="0" step="0.5" value={ln.free_quantity} onChange={e => update(i, { free_quantity: parseFloat(e.target.value) || 0 })} {...navCellProps(i, 5)} /></td>
                        <td className="py-2 pr-2"><Input className="h-8" type="number" step="0.01" min="0" value={ln.purchase_rate} onChange={e => update(i, { purchase_rate: roundMoney(e.target.value) })} {...navCellProps(i, 6)} /></td>
                        <td className="py-2 pr-2"><Input className="h-8" type="number" min="0" max="100" step="0.01" value={ln.discount_pct} onChange={e => update(i, { discount_pct: roundMoney(e.target.value) })} {...navCellProps(i, 7)} /></td>
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
            </FormNavContainer>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2">
        {isConfirmed ? (
          <Button onClick={saveConfirmedEdit} disabled={submitting || items.length === 0}>
            <Save className="h-4 w-4 mr-2" /> Save Changes
          </Button>
        ) : (
          <>
            <Button variant="outline" onClick={saveDraft} disabled={submitting}><Save className="h-4 w-4 mr-2" /> Save Draft</Button>
            <Button onClick={confirm} disabled={submitting || items.length === 0}>
              <CheckCircle2 className="h-4 w-4 mr-2" /> Confirm & Commit
            </Button>
          </>
        )}
      </div>
      </FormNavContainer>

      <QuickMedicineDialog
        open={medicineDialogOpen}
        onOpenChange={setMedicineDialogOpen}
        prefill={medicinePrefill}
        onCreated={handleMedicineCreated}
      />
    </div>
  );
}
