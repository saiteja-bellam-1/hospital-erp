import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../../../components/ui/dialog';
import { useToast } from '../../../hooks/use-toast';
import { ArrowLeft, Plus, Trash2, Save, CheckCircle2, ScanLine, Pill, ChevronDown, ChevronUp, FileText, Pencil } from 'lucide-react';
import { computeLineTax, hsnTotalTaxPct } from '../../../utils/pharmacyHsnTax';
import PharmacyMasterSelectWithCreate from '../../../components/pharmacy/PharmacyMasterSelectWithCreate';
import PharmacyMedicinePicker from '../../../components/pharmacy/PharmacyMedicinePicker';
import QuickMedicineDialog from '../../../components/pharmacy/QuickMedicineDialog';
import { usePharmacyStore } from '../../../contexts/PharmacyStoreContext';
import FormNavContainer from '../../../components/FormNavContainer';
import { NAV_SKIP_ATTR } from '../../../utils/formNavigation';
import { displayPharmacyNumericInput, formatBatchLabel, pharmacyNoSpinInputClass, roundMoney } from '../../../utils/pharmacyUnits';
import { errMsg } from '../PharmacyModule';
import { localDateString } from '../../../utils/localDate';

const emptyLine = () => ({
  medicine_id: null,
  batch_number: '',
  expiry_mm_yyyy: '',
  mrp: '',
  quantity: 1,
  free_quantity: '',
  purchase_rate: '',
  rate_a: '',
  rate_b: '',
  strip_conversion_factor: 1,
  discount_pct: '',
});

const TODAY = localDateString();

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
    payment_type: 'cash', purchase_type: 'local', tax_mode: 'exclusive', notes: '',
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
  const [headerPanelOpen, setHeaderPanelOpen] = useState(false);
  const [companies, setCompanies] = useState([]);
  /** @type {[{ mode: 'add'|'edit'|'batch', index?: number }, object] | [null, null]} */
  const [lineDialog, setLineDialog] = useState(null);
  const [lineForm, setLineForm] = useState(null);
  const [lineBatches, setLineBatches] = useState([]);
  const scanRef = useRef(null);

  const isConfirmed = purchaseStatus === 'confirmed';

  const companyById = useMemo(() => {
    const map = {};
    companies.forEach((c) => { map[c.id] = c; });
    return map;
  }, [companies]);

  const manufacturerOf = useCallback((med) => {
    if (!med) return '';
    if (med.company_name) return med.company_name;
    if (med.company_id != null && companyById[med.company_id]?.name) return companyById[med.company_id].name;
    return med.manufacturer || '';
  }, [companyById]);

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
      axios.get('/api/pharmacy/companies', { params: { active_only: false } }).then(r => setCompanies(r.data || [])).catch(() => {}),
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
          tax_mode: p.tax_mode || 'exclusive',
          notes: p.notes || '',
        });
        const loaded = (p.items || []).map((it) => ({
          medicine_id: it.medicine_id,
          batch_number: it.batch_number || '',
          expiry_mm_yyyy: expiryToDisplay(it.expiry_date),
          mrp: it.mrp || '',
          quantity: it.quantity ?? 1,
          free_quantity: it.free_quantity || '',
          purchase_rate: it.purchase_rate || '',
          rate_a: it.rate_a || '',
          rate_b: it.rate_b || '',
          strip_conversion_factor: it.strip_conversion_factor || 1,
          discount_pct: it.discount_pct || '',
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
    ...emptyLine(),
    medicine_id: m.id,
    mrp: m.mrp || '',
    purchase_rate: m.purchase_rate || '',
    rate_a: m.rate_a || m.unit_price || '',
    rate_b: m.rate_b || '',
    strip_conversion_factor: m.strip_conversion_factor || 1,
  });

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

  const remove = (i) => setItems(s => s.filter((_, idx) => idx !== i));

  const normalizeLine = (form) => ({
    ...form,
    medicine_id: form.medicine_id,
    batch_number: String(form.batch_number || '').trim(),
    mrp: form.mrp === '' ? '' : roundMoney(form.mrp),
    purchase_rate: form.purchase_rate === '' ? '' : roundMoney(form.purchase_rate),
    rate_a: form.rate_a === '' ? '' : roundMoney(form.rate_a),
    rate_b: form.rate_b === '' ? '' : roundMoney(form.rate_b),
    discount_pct: form.discount_pct === '' ? '' : roundMoney(form.discount_pct),
    strip_conversion_factor: Math.max(1, parseInt(form.strip_conversion_factor, 10) || 1),
  });

  const validateLineForm = (form) => {
    const errors = [];
    if (!form.medicine_id) errors.push('Pick a medicine.');
    if (!String(form.batch_number || '').trim()) errors.push('Batch number is required.');
    const exp = expiryToISO(form.expiry_mm_yyyy);
    if (!form.expiry_mm_yyyy || !String(form.expiry_mm_yyyy).trim()) {
      errors.push('Expiry is required (MM/YYYY).');
    } else if (exp === undefined || exp === null) {
      errors.push('Expiry must be MM/YYYY (e.g. 12/2027).');
    }
    if (!(parseFloat(form.quantity) > 0)) errors.push('Quantity must be > 0.');
    const pr = parseFloat(form.purchase_rate);
    if (pr === undefined || pr < 0 || Number.isNaN(pr)) errors.push('Purchase rate must be ≥ 0.');
    return errors;
  };

  const openAddLineDialog = (prefill = null) => {
    setLineDialog({ mode: 'add' });
    setLineForm(prefill || emptyLine());
  };

  const openEditLineDialog = (i) => {
    const src = items[i];
    if (!src) return;
    setLineDialog({ mode: 'edit', index: i });
    setLineForm({ ...src });
  };

  const openBatchDialog = (i) => {
    const src = items[i];
    if (!src?.medicine_id) return;
    const med = medicineCache[src.medicine_id];
    setLineDialog({ mode: 'batch', index: i });
    setLineForm({
      medicine_id: src.medicine_id,
      batch_number: '',
      expiry_mm_yyyy: '',
      mrp: src.mrp ?? med?.mrp ?? '',
      quantity: 1,
      free_quantity: '',
      purchase_rate: src.purchase_rate ?? med?.purchase_rate ?? '',
      rate_a: src.rate_a ?? med?.rate_a ?? '',
      rate_b: src.rate_b ?? med?.rate_b ?? '',
      strip_conversion_factor: src.strip_conversion_factor || med?.strip_conversion_factor || 1,
      discount_pct: '',
    });
  };

  const closeLineDialog = () => {
    setLineDialog(null);
    setLineForm(null);
    setLineBatches([]);
  };

  const setLineField = (k, v) => setLineForm((s) => (s ? { ...s, [k]: v } : s));

  const loadBatchesForMedicine = useCallback(async (medicineId) => {
    if (!medicineId || !masterStore?.id) return [];
    try {
      const r = await axios.get('/api/pharmacy/inventory/batches', {
        params: { medicine_id: medicineId, store_id: masterStore.id, active_only: true },
      });
      return r.data || [];
    } catch {
      return [];
    }
  }, [masterStore?.id]);

  useEffect(() => {
    if (!lineDialog || !lineForm?.medicine_id) {
      setLineBatches([]);
      return undefined;
    }
    let cancelled = false;
    loadBatchesForMedicine(lineForm.medicine_id).then((rows) => {
      if (!cancelled) setLineBatches(rows);
    });
    return () => { cancelled = true; };
  }, [lineDialog, lineForm?.medicine_id, loadBatchesForMedicine]);

  const purchaseBatchSelectValue = () => {
    if (!lineForm?.batch_number) return '__new__';
    const match = lineBatches.find((b) => b.batch_number === String(lineForm.batch_number).trim());
    return match ? String(match.id) : '__new__';
  };

  const onPurchaseBatchSelect = (v) => {
    if (v === '__new__') {
      setLineField('batch_number', '');
      return;
    }
    const batch = lineBatches.find((b) => String(b.id) === v);
    if (!batch) return;
    setLineForm((s) => ({
      ...(s || emptyLine()),
      batch_number: batch.batch_number || '',
      expiry_mm_yyyy: expiryToDisplay(batch.expiry_date),
      mrp: batch.mrp ?? '',
      purchase_rate: batch.purchase_rate ?? '',
      rate_a: batch.rate_a ?? '',
      rate_b: batch.rate_b ?? '',
      strip_conversion_factor: batch.strip_conversion_factor || 1,
    }));
  };

  const applyMedicineToForm = (med) => {
    cacheMedicine(med);
    setLineForm((s) => ({
      ...(s || emptyLine()),
      medicine_id: med.id,
      batch_number: '',
      expiry_mm_yyyy: '',
      purchase_rate: med.purchase_rate || 0,
      mrp: med.mrp || 0,
      rate_a: med.rate_a || med.unit_price || 0,
      rate_b: med.rate_b || 0,
      strip_conversion_factor: med.strip_conversion_factor || 1,
    }));
  };

  const submitLineDialog = () => {
    if (!lineForm || !lineDialog) return;
    const errors = validateLineForm(lineForm);
    if (errors.length) {
      toast({
        variant: 'destructive',
        title: errors.length === 1 ? 'Fix this before saving' : `Fix ${errors.length} issues`,
        description: errors.join(' • '),
      });
      return;
    }
    const row = normalizeLine(lineForm);
    const medName = medicineCache[row.medicine_id]?.name || 'medicine';
    if (lineDialog.mode === 'edit') {
      setItems((s) => s.map((x, idx) => (idx === lineDialog.index ? row : x)));
      toast({ title: 'Line updated', description: medName });
    } else if (lineDialog.mode === 'batch') {
      const insertAt = (lineDialog.index ?? 0) + 1;
      setItems((s) => {
        const next = [...s];
        next.splice(insertAt, 0, row);
        return next;
      });
      toast({ title: `Batch ${row.batch_number} added`, description: medName });
    } else {
      setItems((s) => [...s, row]);
      toast({ title: 'Line added', description: medName });
    }
    closeLineDialog();
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
        openMedicineCreate({ name: code, medicine_code: code, barcode: code });
      } else if (matches.length > 1) {
        toast({ variant: 'destructive', title: 'Ambiguous scan', description: `${matches.length} matches — type a more specific code` });
      } else {
        cacheMedicine(matches[0]);
        openAddLineDialog(lineFromMed(matches[0]));
      }
    } catch (err) {
      toast({ variant: 'destructive', title: 'Lookup failed', description: errMsg(err) });
    }
    setScanInput('');
    scanRef.current?.focus();
  };

  const hsnForMedicine = (medicineId) => {
    const med = medicineCache[medicineId];
    if (!med?.hsn_id) return null;
    return hsnList.find((h) => h.id === med.hsn_id) || null;
  };

  const calcLine = (ln, hsn) => {
    const base = roundMoney((ln.quantity || 0) * (ln.purchase_rate || 0));
    const afterDisc = roundMoney(base * (1 - (ln.discount_pct || 0) / 100));
    const taxPct = hsnTotalTaxPct(hsn);
    const { tax, total } = computeLineTax(afterDisc, taxPct, header.tax_mode);
    return { base, afterDisc, tax, total };
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
      if (!it.expiry_mm_yyyy || !String(it.expiry_mm_yyyy).trim()) {
        errors.push(`Line ${n}: expiry is required (MM/YYYY).`);
      } else {
        const exp = expiryToISO(it.expiry_mm_yyyy);
        if (exp === undefined || exp === null) errors.push(`Line ${n}: expiry must be MM/YYYY (e.g. 12/2027).`);
      }
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
        tax_mode: header.tax_mode || 'exclusive',
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
          rate_a: roundMoney(it.rate_a),
          rate_b: roundMoney(it.rate_b),
          strip_conversion_factor: Math.max(1, parseInt(it.strip_conversion_factor, 10) || 1),
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

  const openMedicineCreate = (prefill = {}) => {
    setMedicinePrefill(prefill);
    setMedicineDialogOpen(true);
  };

  const handleMedicineCreated = (med) => {
    cacheMedicine(med);
    if (lineDialog && lineForm) {
      applyMedicineToForm(med);
    } else {
      openAddLineDialog(lineFromMed(med));
    }
    toast({ title: 'Medicine added to catalog', description: med.name });
  };

  const pageTitle = isConfirmed
    ? `Edit Purchase ${purchaseNumber}`
    : draftId
      ? `Edit Draft ${purchaseNumber || `#${draftId}`}`
      : 'New Purchase';

  const supplierName = suppliers.find((s) => s.id === header.supplier_id)?.name || '';
  const headerSummary = [
    supplierName || 'No supplier',
    header.payment_type,
    header.tax_mode === 'inclusive' ? 'tax incl.' : 'tax excl.',
  ].join(' · ');

  const compactInput = 'h-8 text-sm';
  const numInput = `${compactInput} ${pharmacyNoSpinInputClass}`;

  if (loadingPurchase) {
    return <p className="text-center py-12 text-sm text-gray-500">Loading purchase…</p>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <Button size="sm" variant="outline" onClick={() => navigate('/dashboard/pharmacy/purchases')}><ArrowLeft className="h-3 w-3 mr-1" /> Back</Button>
        <h1 className="text-lg font-bold flex-1">{pageTitle}</h1>
        <Button size="sm" variant="outline" onClick={() => navigate('/dashboard/pharmacy/medicines')}>
          <Pill className="h-3 w-3 mr-1" /> Medicines catalog
        </Button>
        <Button size="sm" variant="outline" onClick={() => openMedicineCreate()}>
          <Plus className="h-3 w-3 mr-1" /> New medicine
        </Button>
      </div>

      <FormNavContainer mode="grid" className="grid grid-cols-1 xl:grid-cols-[minmax(340px,420px)_minmax(0,1fr)] gap-2 items-start">

      {isConfirmed && (
        <Card className="border-amber-200 bg-amber-50/50 xl:col-span-2">
          <CardHeader className="py-2 px-4 pb-2">
            <CardTitle className="text-base">Edit reason *</CardTitle>
          </CardHeader>
          <CardContent className="pt-0">
            <p className="text-xs text-gray-600 mb-2">
              Stock is adjusted in place — this reason is logged.
            </p>
            <Textarea
              rows={2}
              className="text-sm"
              placeholder="e.g. wrong invoice rate, batch number typo"
              value={editReason}
              onChange={(e) => setEditReason(e.target.value)}
            />
          </CardContent>
        </Card>
      )}

      <div className="xl:order-1 xl:sticky xl:top-4 space-y-2">
        <Card>
          <CardHeader className="py-2 px-4">
            <button
              type="button"
              className="flex w-full items-center justify-between gap-2 text-left xl:pointer-events-none"
              onClick={() => setHeaderPanelOpen((o) => !o)}
            >
              <CardTitle className="text-base flex items-center gap-2">
                <FileText className="h-4 w-4 text-gray-500" />
                Purchase Header
              </CardTitle>
              <span className="xl:hidden flex items-center gap-2 min-w-0">
                <span className="text-xs text-gray-500 truncate max-w-[160px]">{headerSummary}</span>
                {headerPanelOpen ? <ChevronUp className="h-4 w-4 shrink-0" /> : <ChevronDown className="h-4 w-4 shrink-0" />}
              </span>
            </button>
          </CardHeader>
          <CardContent className={`pt-0 grid grid-cols-2 gap-2 ${headerPanelOpen ? '' : 'hidden xl:grid'}`}>
            <div><Label className="text-xs">Entry Date</Label><Input className={compactInput} type="date" value={header.entry_date} onChange={e => setH('entry_date', e.target.value)} /></div>
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
            <div><Label className="text-xs">Invoice #</Label><Input className={compactInput} value={header.invoice_number} onChange={e => setH('invoice_number', e.target.value)} /></div>
            <div><Label className="text-xs">Bill Date</Label><Input className={compactInput} type="date" value={header.bill_date} onChange={e => setH('bill_date', e.target.value)} /></div>
            <div>
              <Label className="text-xs">Payment Type</Label>
              <Select value={header.payment_type} onValueChange={v => setH('payment_type', v)}>
                <SelectTrigger className={compactInput}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="cash">Cash</SelectItem>
                  <SelectItem value="credit">Credit</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Tax on rates</Label>
              <Select value={header.tax_mode} onValueChange={v => setH('tax_mode', v)}>
                <SelectTrigger className={compactInput}><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="exclusive">Tax Exclude</SelectItem>
                  <SelectItem value="inclusive">Tax Include</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div><Label className="text-xs">Purchase Type</Label><Input className={compactInput} value={header.purchase_type} onChange={e => setH('purchase_type', e.target.value)} placeholder="local / interstate" /></div>
            <div className="col-span-2"><Label className="text-xs">Notes</Label><Textarea rows={1} className="text-sm min-h-[2rem]" value={header.notes} onChange={e => setH('notes', e.target.value)} /></div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="py-2 px-4">
            <CardTitle className="text-base">Totals</CardTitle>
          </CardHeader>
          <CardContent className="pt-0 text-sm space-y-1.5">
            <div className="flex justify-between gap-3">
              <span className="text-gray-600">Subtotal</span>
              <span className="tabular-nums">₹{totals.sub.toFixed(2)}</span>
            </div>
            <div className="flex justify-between gap-3 text-gray-600">
              <span>Discount</span>
              <span className="tabular-nums">−₹{totals.disc.toFixed(2)}</span>
            </div>
            <div className="flex justify-between gap-3 text-gray-600">
              <span>Tax ({header.tax_mode === 'inclusive' ? 'incl.' : 'added'})</span>
              <span className="tabular-nums">
                {header.tax_mode === 'inclusive' ? '' : '+'}₹{totals.tax.toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between gap-3 font-bold border-t pt-1.5 text-base">
              <span>Grand Total</span>
              <span className="tabular-nums">₹{totals.grand.toFixed(2)}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card className="xl:order-2 min-w-0">
        <CardHeader className="py-2 px-4">
          <CardTitle className="text-base flex flex-wrap gap-2 justify-between items-center">
            <span>Batch Details</span>
            <div className="flex items-center gap-2 flex-1 max-w-md ml-0 xl:ml-4">
              <ScanLine className="h-4 w-4 text-gray-500 shrink-0" />
              <Input
                ref={scanRef}
                className={compactInput}
                placeholder="Scan barcode or type code + Enter"
                value={scanInput}
                onChange={e => setScanInput(e.target.value)}
                onKeyDown={handleScan}
                {...{ [NAV_SKIP_ATTR]: '' }}
              />
            </div>
            <Button size="sm" variant="outline" onClick={() => openAddLineDialog()}>
              <Plus className="h-3 w-3 mr-1" /> Add line
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
          {items.length === 0 ? (
            <p className="text-center py-4 text-sm text-gray-500">
              No items — scan a barcode or click <span className="font-medium">Add line</span>.
            </p>
          ) : (
            <>
            <div className="rounded-md border overflow-x-auto">
              <table className="w-full text-sm table-fixed min-w-[720px]">
                <colgroup>
                  <col className="w-10" />
                  <col />
                  <col className="w-[5.5rem]" />
                  <col className="w-[5rem]" />
                  <col className="w-[4rem]" />
                  <col className="w-[5rem]" />
                  <col className="w-[5.5rem]" />
                  <col className="w-[11.5rem]" />
                </colgroup>
                <thead>
                  <tr className="border-b bg-gray-50 text-left text-[11px] font-medium text-gray-500">
                    <th className="px-2 py-1.5">#</th>
                    <th className="px-2 py-1.5">Medicine</th>
                    <th className="px-2 py-1.5">Batch</th>
                    <th className="px-2 py-1.5">Expiry</th>
                    <th className="px-2 py-1.5">Qty</th>
                    <th className="px-2 py-1.5 text-right">P-Rate</th>
                    <th className="px-2 py-1.5 text-right">Total</th>
                    <th className="px-2 py-1.5" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((ln, i) => {
                    const med = medicineCache[ln.medicine_id];
                    const c = calcLine(ln, hsnForMedicine(ln.medicine_id));
                    const lineInvalid = !ln.medicine_id
                      || !String(ln.batch_number || '').trim()
                      || !ln.expiry_mm_yyyy
                      || expiryToISO(ln.expiry_mm_yyyy) == null
                      || !(parseFloat(ln.quantity) > 0);
                    const mfr = manufacturerOf(med);
                    const pRate = ln.purchase_rate === '' || ln.purchase_rate == null
                      ? '—'
                      : `₹${Number(ln.purchase_rate).toFixed(2)}`;
                    return (
                      <tr
                        key={i}
                        className={`border-b last:border-0 ${lineInvalid ? 'bg-red-50/50' : 'hover:bg-gray-50/80'}`}
                      >
                        <td className="px-2 py-2 align-middle text-xs text-gray-400 font-medium">{i + 1}</td>
                        <td className="px-2 py-2 align-middle min-w-0">
                          <button
                            type="button"
                            className="text-left w-full min-w-0"
                            onClick={() => openEditLineDialog(i)}
                          >
                            <div className="font-medium truncate">
                              {med?.name || (ln.medicine_id ? `Medicine #${ln.medicine_id}` : 'No medicine')}
                            </div>
                            <div className="text-[11px] text-gray-500 truncate">
                              {[med?.medicine_code, mfr].filter(Boolean).join(' · ') || '—'}
                            </div>
                          </button>
                        </td>
                        <td className="px-2 py-2 align-middle truncate">
                          {ln.batch_number || <span className="text-red-500">—</span>}
                        </td>
                        <td className="px-2 py-2 align-middle tabular-nums text-gray-700">
                          {ln.expiry_mm_yyyy || <span className="text-red-500">—</span>}
                        </td>
                        <td className="px-2 py-2 align-middle tabular-nums">
                          {ln.quantity}
                          {ln.free_quantity ? (
                            <span className="text-gray-400 text-xs"> +{ln.free_quantity}f</span>
                          ) : null}
                        </td>
                        <td className="px-2 py-2 align-middle text-right tabular-nums">{pRate}</td>
                        <td className="px-2 py-2 align-middle text-right font-semibold tabular-nums">
                          ₹{c.total.toFixed(2)}
                        </td>
                        <td className="px-2 py-2 align-middle">
                          <div className="flex items-center justify-end gap-0.5">
                            <Button type="button" size="sm" variant="ghost" className="h-7 px-1.5" onClick={() => openEditLineDialog(i)}>
                              <Pencil className="h-3.5 w-3.5 mr-1" /> Edit
                            </Button>
                            {ln.medicine_id && (
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                className="h-7 px-1.5 text-blue-700 border-blue-200"
                                onClick={() => openBatchDialog(i)}
                              >
                                <Plus className="h-3.5 w-3.5 mr-1" /> Batch
                              </Button>
                            )}
                            <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => remove(i)} title="Remove">
                              <Trash2 className="h-3.5 w-3.5 text-red-500" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Click a row or <span className="font-medium">Edit</span> to change details. Use <span className="font-medium">Batch</span> for another batch of the same medicine.
            </p>
            </>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-end gap-2 xl:col-span-2 xl:order-3">
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

      <Dialog open={!!lineDialog && !!lineForm} onOpenChange={(open) => { if (!open) closeLineDialog(); }}>
        <DialogContent className="max-w-3xl w-[95vw] sm:w-full" formNav="grid">
          <DialogHeader>
            <DialogTitle>
              {lineDialog?.mode === 'edit'
                ? 'Edit line'
                : lineDialog?.mode === 'batch'
                  ? 'Add another batch'
                  : 'Add line'}
            </DialogTitle>
          </DialogHeader>
          {lineForm && (() => {
            const selectedMed = medicineCache[lineForm.medicine_id];
            const mfr = manufacturerOf(selectedMed);
            const company = selectedMed?.company_id != null ? companyById[selectedMed.company_id] : null;
            const medicineLocked = lineDialog?.mode === 'batch';
            return (
              <div className="space-y-3">
                {medicineLocked ? (
                  <div className="rounded-md border bg-gray-50 px-3 py-2 text-sm space-y-1">
                    <div className="font-medium text-gray-900">{selectedMed?.name || 'Medicine'}</div>
                    <div className="text-xs text-gray-600">
                      {[selectedMed?.medicine_code, mfr].filter(Boolean).join(' · ')}
                    </div>
                  </div>
                ) : (
                  <div>
                    <Label className="text-xs">Medicine *</Label>
                    <PharmacyMedicinePicker
                      value={lineForm.medicine_id}
                      medicine={selectedMed}
                      companyById={companyById}
                      wideMenu
                      onSelect={applyMedicineToForm}
                      onCreateNew={(q) => openMedicineCreate({
                        name: q || '',
                        medicine_code: q || '',
                        barcode: q || undefined,
                      })}
                    />
                  </div>
                )}

                {selectedMed && (
                  <div className="rounded-md border border-blue-100 bg-blue-50/60 px-3 py-2 text-xs space-y-1">
                    <div className="font-medium text-blue-900">Manufacturer / catalog check</div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-blue-900/90">
                      <span className="text-blue-700/80">Manufacturer</span>
                      <span className="font-medium">{mfr || '—'}</span>
                      {company?.contact && (
                        <>
                          <span className="text-blue-700/80">Contact</span>
                          <span>{company.contact}</span>
                        </>
                      )}
                      <span className="text-blue-700/80">Code</span>
                      <span>{selectedMed.medicine_code || '—'}</span>
                      <span className="text-blue-700/80">Generic</span>
                      <span>{selectedMed.generic_name || '—'}</span>
                      <span className="text-blue-700/80">Strength</span>
                      <span>{selectedMed.strength || '—'}</span>
                      <span className="text-blue-700/80">Packaging</span>
                      <span>{selectedMed.packaging || '—'}</span>
                      <span className="text-blue-700/80">Catalog MRP</span>
                      <span>₹{Number(selectedMed.mrp || 0).toFixed(2)}</span>
                      <span className="text-blue-700/80">Catalog P-Rate</span>
                      <span>₹{Number(selectedMed.purchase_rate || 0).toFixed(2)}</span>
                      <span className="text-blue-700/80">Catalog Rate A</span>
                      <span>₹{Number(selectedMed.rate_a || selectedMed.unit_price || 0).toFixed(2)}</span>
                      <span className="text-blue-700/80">Catalog Rate B</span>
                      <span>₹{Number(selectedMed.rate_b || 0).toFixed(2)}</span>
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-3">
                  {lineForm.medicine_id && lineBatches.length > 0 && (
                    <div className="col-span-2">
                      <Label className="text-xs">Stock batch (optional)</Label>
                      <Select value={purchaseBatchSelectValue()} onValueChange={onPurchaseBatchSelect}>
                        <SelectTrigger className={compactInput}>
                          <SelectValue placeholder="New batch — type below" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__new__">New batch — type below</SelectItem>
                          {lineBatches.map((b) => (
                            <SelectItem key={b.id} value={String(b.id)}>
                              {formatBatchLabel(b)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <p className="text-[11px] text-gray-400 mt-1">
                        Pick an existing batch to prefill, or type a new batch number below.
                      </p>
                    </div>
                  )}
                  <div className="col-span-2 sm:col-span-1">
                    <Label className="text-xs">Batch # *</Label>
                    <Input
                      className={`${compactInput} ${!String(lineForm.batch_number || '').trim() ? 'border-red-300' : ''}`}
                      placeholder="Batch number"
                      value={lineForm.batch_number}
                      onChange={(e) => setLineField('batch_number', e.target.value)}
                      autoFocus={!!lineForm.medicine_id}
                    />
                  </div>
                  <div>
                    <Label className="text-xs">Expiry *</Label>
                    <Input
                      className={`${compactInput} ${(!lineForm.expiry_mm_yyyy || expiryToISO(lineForm.expiry_mm_yyyy) == null) ? 'border-red-300' : ''}`}
                      placeholder="MM/YYYY"
                      value={lineForm.expiry_mm_yyyy || ''}
                      onChange={(e) => setLineField('expiry_mm_yyyy', e.target.value)}
                    />
                  </div>
                  <div>
                    <Label className="text-xs">Qty *</Label>
                    <Input
                      className={numInput}
                      type="number"
                      min="0"
                      step="0.5"
                      value={displayPharmacyNumericInput(lineForm.quantity)}
                      onChange={(e) => setLineField('quantity', parseFloat(e.target.value) || 0)}
                    />
                  </div>
                  <div>
                    <Label className="text-xs">Free</Label>
                    <Input
                      className={numInput}
                      type="number"
                      min="0"
                      step="0.5"
                      value={displayPharmacyNumericInput(lineForm.free_quantity)}
                      onChange={(e) => setLineField('free_quantity', e.target.value)}
                    />
                  </div>
                  <div>
                    <Label className="text-xs">MRP</Label>
                    <Input
                      className={numInput}
                      type="number"
                      step="0.01"
                      min="0"
                      value={displayPharmacyNumericInput(lineForm.mrp)}
                      onChange={(e) => setLineField('mrp', e.target.value === '' ? '' : roundMoney(e.target.value))}
                    />
                  </div>
                  <div>
                    <Label className="text-xs">P-Rate</Label>
                    <Input
                      className={numInput}
                      type="number"
                      step="0.01"
                      min="0"
                      value={displayPharmacyNumericInput(lineForm.purchase_rate)}
                      onChange={(e) => setLineField('purchase_rate', e.target.value === '' ? '' : roundMoney(e.target.value))}
                    />
                  </div>
                  <div>
                    <Label className="text-xs">Rate A</Label>
                    <Input
                      className={numInput}
                      type="number"
                      step="0.01"
                      min="0"
                      value={displayPharmacyNumericInput(lineForm.rate_a)}
                      onChange={(e) => setLineField('rate_a', e.target.value === '' ? '' : roundMoney(e.target.value))}
                    />
                  </div>
                  <div>
                    <Label className="text-xs">Rate B</Label>
                    <Input
                      className={numInput}
                      type="number"
                      step="0.01"
                      min="0"
                      value={displayPharmacyNumericInput(lineForm.rate_b)}
                      onChange={(e) => setLineField('rate_b', e.target.value === '' ? '' : roundMoney(e.target.value))}
                    />
                  </div>
                  <div>
                    <Label className="text-xs">Qty/Strip</Label>
                    <Input
                      className={numInput}
                      type="number"
                      min="1"
                      step="1"
                      value={lineForm.strip_conversion_factor ?? 1}
                      onChange={(e) => setLineField('strip_conversion_factor', Math.max(1, parseInt(e.target.value, 10) || 1))}
                    />
                  </div>
                  <div>
                    <Label className="text-xs">Disc %</Label>
                    <Input
                      className={numInput}
                      type="number"
                      min="0"
                      max="100"
                      step="0.01"
                      value={displayPharmacyNumericInput(lineForm.discount_pct)}
                      onChange={(e) => setLineField('discount_pct', e.target.value === '' ? '' : roundMoney(e.target.value))}
                    />
                  </div>
                  <div className="flex flex-col justify-end">
                    <Label className="text-xs">Line total</Label>
                    <div className="h-8 flex items-center text-sm font-semibold tabular-nums">
                      ₹{calcLine(lineForm, hsnForMedicine(lineForm.medicine_id)).total.toFixed(2)}
                    </div>
                  </div>
                </div>
              </div>
            );
          })()}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={closeLineDialog}>Cancel</Button>
            <Button type="button" onClick={submitLineDialog}>
              {lineDialog?.mode === 'edit' ? (
                <><Save className="h-4 w-4 mr-1.5" /> Save line</>
              ) : lineDialog?.mode === 'batch' ? (
                <><Plus className="h-4 w-4 mr-1.5" /> Add batch</>
              ) : (
                <><Plus className="h-4 w-4 mr-1.5" /> Add line</>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
