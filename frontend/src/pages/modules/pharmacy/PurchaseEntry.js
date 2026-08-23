import React, { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import axios from 'axios';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../components/ui/dialog';
import { useToast } from '../../../hooks/use-toast';
import { ArrowLeft, Plus, Trash2, Save, CheckCircle2, ScanLine, Pill, ChevronDown, ChevronUp, FileText, Pencil } from 'lucide-react';
import { computeLineTax, formatHsnOption, hsnTotalTaxPct } from '../../../utils/pharmacyHsnTax';
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
  hsn_id: null,
});

const TODAY = localDateString();

const expiryToDisplay = (iso) => {
  if (!iso) return '';
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime()) || d.getFullYear() >= 2099) return '';
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;
};

/** Auto-insert MM/YYYY (or MM/YY) slash while typing digits. */
const formatExpiryInput = (raw) => {
  const digits = String(raw || '').replace(/\D/g, '').slice(0, 6);
  if (digits.length <= 2) return digits;
  return `${digits.slice(0, 2)}/${digits.slice(2)}`;
};

/** True when expiry month/year is strictly after the current calendar month. */
const isExpiryAfterCurrentMonth = (raw) => {
  if (!raw) return false;
  const s = String(raw).trim();
  let m = s.match(/^(\d{1,2})\s*[/\-.]\s*(\d{2}|\d{4})$/);
  if (!m) {
    const digits = s.replace(/\D/g, '');
    if (digits.length === 4 || digits.length === 6) {
      m = ['', digits.slice(0, 2), digits.slice(2)];
    } else {
      return false;
    }
  }
  const mo = parseInt(m[1], 10);
  let yr = parseInt(m[2], 10);
  if (yr < 100) yr += 2000;
  if (mo < 1 || mo > 12) return false;
  const now = new Date();
  const curYm = now.getFullYear() * 12 + (now.getMonth() + 1);
  const expYm = yr * 12 + mo;
  return expYm > curYm;
};

export default function PurchaseEntry() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const location = useLocation();
  const { id: routeId } = useParams();
  const { stores } = usePharmacyStore();
  const masterStore = stores.find((s) => s.store_type === 'master');

  const [header, setHeader] = useState({
    entry_date: TODAY, supplier_id: null, invoice_number: '', bill_date: TODAY,
    payment_type: 'cash', purchase_type: 'local', tax_mode: 'exclusive', notes: '',
    bill_discount_pct: '', bill_discount_amount: '',
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

  const importAppliedRef = useRef(false);
  useEffect(() => {
    if (importAppliedRef.current || routeId) return;
    const draft = location.state?.importDraft;
    if (!draft?.items?.length) return;
    importAppliedRef.current = true;
    const h = draft.header || {};
    setHeader({
      entry_date: h.entry_date || TODAY,
      supplier_id: h.supplier_id || null,
      invoice_number: h.invoice_number || '',
      bill_date: h.bill_date || TODAY,
      payment_type: h.payment_type === 'cash' ? 'cash' : 'credit',
      purchase_type: h.purchase_type || 'local',
      tax_mode: h.tax_mode === 'inclusive' ? 'inclusive' : 'exclusive',
      notes: h.notes || '',
      bill_discount_pct: h.bill_discount_pct || '',
      bill_discount_amount: h.bill_discount_amount || '',
    });
    const loaded = (draft.items || []).map((it) => ({
      medicine_id: it.medicine_id || null,
      batch_number: it.batch_number || '',
      expiry_mm_yyyy: expiryToDisplay(it.expiry_date),
      mrp: it.mrp ?? '',
      quantity: it.quantity ?? 1,
      free_quantity: it.free_quantity || '',
      purchase_rate: it.purchase_rate ?? '',
      rate_a: it.rate_a ?? '',
      rate_b: it.rate_b ?? '',
      strip_conversion_factor: it.strip_conversion_factor || 1,
      discount_pct: it.discount_pct || '',
      hsn_id: it.hsn_id ?? null,
    }));
    setItems(loaded);
    setHeaderPanelOpen(true);
    loadMedicinesByIds(loaded.map((l) => l.medicine_id).filter(Boolean));
    (draft.warnings || []).forEach((w) => {
      toast({ title: 'Import notice', description: w });
    });
    toast({
      title: `Loaded ${loaded.length} line(s) from import`,
      description: 'Review the purchase, then Save draft or Submit.',
    });
    navigate(location.pathname, { replace: true, state: {} });
  }, [location.state, location.pathname, routeId, loadMedicinesByIds, navigate, toast]);

  useEffect(() => {
    Promise.all([
      axios.get('/api/pharmacy/suppliers').then(r => setSuppliers(r.data || [])),
      axios.get('/api/pharmacy/hsn').then(r => setHsnList(r.data || [])),
      axios.get('/api/pharmacy/companies', { params: { active_only: false } }).then(r => setCompanies(r.data || [])).catch(() => {}),
    ]).catch(() => {});
  }, []);

  useEffect(() => {
    if (routeId) return; // edit mode loads tax_mode from the purchase
    if (location.state?.importDraft) return;
    axios.get('/api/pharmacy/pos-settings')
      .then((r) => {
        const mode = r.data?.default_tax_mode_purchase === 'inclusive' ? 'inclusive' : 'exclusive';
        setHeader((h) => ({ ...h, tax_mode: mode }));
      })
      .catch(() => {});
  }, [routeId]);

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
          bill_discount_pct: Number(p.bill_discount_pct) > 0 ? p.bill_discount_pct : '',
          bill_discount_amount: Number(p.bill_discount_amount) > 0 ? p.bill_discount_amount : '',
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
          hsn_id: it.hsn_id ?? null,
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

  const lineFromMed = (m) => {
    const mrp = m.mrp || '';
    return {
      ...emptyLine(),
      medicine_id: m.id,
      mrp,
      purchase_rate: m.purchase_rate || '',
      rate_a: mrp,
      rate_b: mrp,
      strip_conversion_factor: m.strip_conversion_factor || 1,
      hsn_id: m.hsn_id ?? null,
    };
  };

  const expiryToISO = (raw) => {
    if (!raw) return null;
    const s = String(raw).trim();
    let m = s.match(/^(\d{1,2})\s*[/\-.]\s*(\d{2}|\d{4})$/);
    if (!m) {
      // Accept bare digits: MMYY or MMYYYY (e.g. 1227 → 12/27)
      const digits = s.replace(/\D/g, '');
      if (digits.length === 4 || digits.length === 6) {
        m = ['', digits.slice(0, 2), digits.slice(2)];
      } else {
        return undefined;
      }
    }
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

  const remove = (i) => {
    const next = items.filter((_, idx) => idx !== i);
    setItems(next);
    if (!isConfirmed) enqueueDraftSave({ nextItems: next, quiet: true });
  };

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
    } else if (!isExpiryAfterCurrentMonth(form.expiry_mm_yyyy)) {
      errors.push('Expiry must be after the current month.');
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
    const med = medicineCache[src.medicine_id];
    setLineDialog({ mode: 'edit', index: i });
    setLineForm({
      ...src,
      hsn_id: src.hsn_id ?? med?.hsn_id ?? null,
    });
  };

  const openBatchDialog = (i) => {
    const src = items[i];
    if (!src?.medicine_id) return;
    const med = medicineCache[src.medicine_id];
    setLineDialog({ mode: 'batch', index: i });
    const mrp = src.mrp ?? med?.mrp ?? '';
    setLineForm({
      medicine_id: src.medicine_id,
      batch_number: '',
      expiry_mm_yyyy: '',
      mrp,
      quantity: 1,
      free_quantity: '',
      purchase_rate: src.purchase_rate ?? med?.purchase_rate ?? '',
      rate_a: mrp,
      rate_b: mrp,
      strip_conversion_factor: src.strip_conversion_factor || med?.strip_conversion_factor || 1,
      discount_pct: '',
      hsn_id: src.hsn_id ?? med?.hsn_id ?? null,
    });
  };

  const closeLineDialog = () => {
    setLineDialog(null);
    setLineForm(null);
    setLineBatches([]);
  };

  const setLineField = (k, v) => setLineForm((s) => {
    if (!s) return s;
    if (k === 'mrp') {
      return { ...s, mrp: v, rate_a: v, rate_b: v };
    }
    return { ...s, [k]: v };
  });

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
    const mrp = batch.mrp ?? '';
    setLineForm((s) => ({
      ...(s || emptyLine()),
      batch_number: batch.batch_number || '',
      expiry_mm_yyyy: expiryToDisplay(batch.expiry_date),
      mrp,
      purchase_rate: batch.purchase_rate ?? '',
      rate_a: mrp,
      rate_b: mrp,
      strip_conversion_factor: batch.strip_conversion_factor || 1,
      hsn_id: batch.hsn_id ?? s?.hsn_id ?? null,
    }));
  };

  const applyMedicineToForm = (med) => {
    cacheMedicine(med);
    const mrp = med.mrp || 0;
    setLineForm((s) => ({
      ...(s || emptyLine()),
      medicine_id: med.id,
      batch_number: '',
      expiry_mm_yyyy: '',
      purchase_rate: med.purchase_rate || 0,
      mrp,
      rate_a: mrp,
      rate_b: mrp,
      strip_conversion_factor: med.strip_conversion_factor || 1,
      hsn_id: med.hsn_id ?? null,
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
    let nextItems;
    if (lineDialog.mode === 'edit') {
      nextItems = items.map((x, idx) => (idx === lineDialog.index ? row : x));
      toast({ title: 'Line updated', description: medName });
    } else if (lineDialog.mode === 'batch') {
      const insertAt = (lineDialog.index ?? 0) + 1;
      nextItems = [...items];
      nextItems.splice(insertAt, 0, row);
      toast({ title: `Batch ${row.batch_number} added`, description: medName });
    } else {
      nextItems = [...items, row];
      toast({ title: 'Line added', description: medName });
    }
    setItems(nextItems);
    closeLineDialog();
    if (!isConfirmed) enqueueDraftSave({ nextItems, quiet: true });
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

  const hsnForLine = (ln) => {
    const hsnId = ln?.hsn_id ?? medicineCache[ln?.medicine_id]?.hsn_id;
    if (!hsnId) return null;
    return hsnList.find((h) => h.id === hsnId) || null;
  };

  const calcLine = (ln, hsn) => {
    const base = roundMoney((ln.quantity || 0) * (ln.purchase_rate || 0));
    const afterDisc = roundMoney(base * (1 - (ln.discount_pct || 0) / 100));
    const taxPct = hsnTotalTaxPct(hsn);
    const { tax, total } = computeLineTax(afterDisc, taxPct, header.tax_mode);
    return { base, afterDisc, tax, total };
  };
  const lineTotals = items.reduce((acc, ln) => {
    const c = calcLine(ln, hsnForLine(ln));
    return {
      sub: acc.sub + c.base,
      lineDisc: acc.lineDisc + (c.base - c.afterDisc),
      tax: acc.tax + c.tax,
      linesGrand: acc.linesGrand + c.total,
    };
  }, { sub: 0, lineDisc: 0, tax: 0, linesGrand: 0 });
  const billDiscPct = parseFloat(header.bill_discount_pct) || 0;
  const billDiscEntered = parseFloat(header.bill_discount_amount) || 0;
  const billDiscAmt = roundMoney(billDiscPct > 0
    ? Math.min(lineTotals.linesGrand * billDiscPct / 100, lineTotals.linesGrand)
    : Math.min(billDiscEntered, lineTotals.linesGrand));
  const totals = {
    sub: lineTotals.sub,
    lineDisc: lineTotals.lineDisc,
    billDisc: billDiscAmt,
    disc: roundMoney(lineTotals.lineDisc + billDiscAmt),
    tax: lineTotals.tax,
    grand: roundMoney(Math.max(0, lineTotals.linesGrand - billDiscAmt)),
  };

  const buildPayload = ({ lines = items, headerState = header, allowEmpty = false } = {}) => {
    const errors = [];
    if (!headerState.supplier_id) errors.push('Pick a supplier.');
    if (!allowEmpty && lines.length === 0) errors.push('Add at least one item.');
    lines.forEach((it, idx) => {
      const n = idx + 1;
      if (!it.medicine_id) errors.push(`Line ${n}: pick or create a medicine.`);
      if (!it.batch_number || !String(it.batch_number).trim()) errors.push(`Line ${n}: batch number is required.`);
      if (!it.expiry_mm_yyyy || !String(it.expiry_mm_yyyy).trim()) {
        errors.push(`Line ${n}: expiry is required (MM/YYYY).`);
      } else {
        const exp = expiryToISO(it.expiry_mm_yyyy);
        if (exp === undefined || exp === null) {
          errors.push(`Line ${n}: expiry must be MM/YYYY (e.g. 12/2027).`);
        } else if (!isExpiryAfterCurrentMonth(it.expiry_mm_yyyy)) {
          errors.push(`Line ${n}: expiry must be after the current month.`);
        }
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
        entry_date: headerState.entry_date,
        supplier_id: headerState.supplier_id,
        store_id: masterStore?.id || null,
        invoice_number: headerState.invoice_number || null,
        bill_date: headerState.bill_date || null,
        payment_type: headerState.payment_type,
        purchase_type: headerState.purchase_type || null,
        tax_mode: headerState.tax_mode || 'exclusive',
        notes: headerState.notes || null,
        bill_discount_pct: roundMoney(headerState.bill_discount_pct),
        bill_discount_amount: roundMoney(
          (parseFloat(headerState.bill_discount_pct) || 0) > 0 ? 0 : headerState.bill_discount_amount,
        ),
        ...(isConfirmed ? { reason: editReason.trim() } : {}),
        items: lines.map(it => ({
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

  const draftIdRef = useRef(draftId);
  useEffect(() => { draftIdRef.current = draftId; }, [draftId]);
  const pendingSaveRef = useRef(null);
  const savingRef = useRef(false);

  /** Persist draft to the server. Quiet mode is used for auto-save after line changes. */
  const persistDraft = async ({
    nextItems,
    headerOverride,
    quiet = false,
  } = {}) => {
    if (isConfirmed) return false;
    const lines = nextItems ?? items;
    const headerState = headerOverride ?? header;
    if (!headerState.supplier_id) {
      if (quiet) {
        toast({
          title: 'Select a supplier to auto-save',
          description: 'Lines stay on this page until a supplier is chosen.',
        });
      }
      return false;
    }
    const id = draftIdRef.current;
    if (lines.length === 0 && !id) return false;

    const { errors, payload } = buildPayload({
      lines,
      headerState,
      allowEmpty: Boolean(id),
    });
    if (errors.length) {
      if (!quiet) showValidationErrors(errors);
      else {
        toast({
          variant: 'destructive',
          title: 'Could not auto-save draft',
          description: errors[0],
        });
      }
      return false;
    }

    try {
      const r = id
        ? await axios.put(`/api/pharmacy/purchases/${id}`, payload)
        : await axios.post('/api/pharmacy/purchases', payload);
      draftIdRef.current = r.data.id;
      setDraftId(r.data.id);
      setPurchaseStatus(r.data.status);
      setPurchaseNumber(r.data.purchase_number || '');
      // Wait until coalesced queue is idle before leaving /new, so a follow-up
      // line save can PUT instead of racing a remounted load.
      if (!routeId && r.data.id && !pendingSaveRef.current) {
        navigate(`/dashboard/pharmacy/purchases/${r.data.id}/edit`, { replace: true });
      }
      if (quiet) {
        toast({ title: 'Draft auto-saved', description: r.data.purchase_number });
      } else {
        toast({ title: `Draft saved: ${r.data.purchase_number}` });
      }
      return true;
    } catch (e) {
      toast({
        variant: 'destructive',
        title: quiet ? 'Auto-save failed' : 'Save failed',
        description: errMsg(e),
      });
      return false;
    }
  };

  const pumpDraftSaves = async () => {
    if (savingRef.current) return;
    savingRef.current = true;
    try {
      while (pendingSaveRef.current) {
        const opts = pendingSaveRef.current;
        pendingSaveRef.current = null;
        await persistDraft(opts);
      }
    } finally {
      savingRef.current = false;
      // If a create finished while another save was pending, URL may still be /new.
      if (!routeId && draftIdRef.current && !pendingSaveRef.current) {
        navigate(`/dashboard/pharmacy/purchases/${draftIdRef.current}/edit`, { replace: true });
      }
    }
  };

  const enqueueDraftSave = (opts) => {
    pendingSaveRef.current = opts;
    return pumpDraftSaves();
  };

  const saveDraft = async () => {
    const { errors } = buildPayload();
    if (errors.length) { showValidationErrors(errors); return; }
    setSubmitting(true);
    try {
      await persistDraft({ quiet: false });
      if (!routeId && draftIdRef.current) {
        navigate(`/dashboard/pharmacy/purchases/${draftIdRef.current}/edit`, { replace: true });
      }
    } finally {
      setSubmitting(false);
    }
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

  const persistBillDiscount = () => {
    if (!isConfirmed && header.supplier_id) {
      enqueueDraftSave({ quiet: true });
    }
  };

  const setBillDiscount = (k, v) => {
    setHeader((s) => {
      if (k === 'bill_discount_pct') {
        return { ...s, bill_discount_pct: v, bill_discount_amount: v === '' || v == null ? s.bill_discount_amount : '' };
      }
      if (k === 'bill_discount_amount') {
        return { ...s, bill_discount_amount: v, bill_discount_pct: '' };
      }
      return { ...s, [k]: v };
    });
  };

  const setH = (k, v) => {
    setHeader((s) => {
      const next = { ...s, [k]: v };
      if (
        k === 'supplier_id'
        && v
        && !isConfirmed
        && items.length > 0
      ) {
        enqueueDraftSave({
          nextItems: items,
          headerOverride: next,
          quiet: true,
        });
      }
      return next;
    });
  };

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
  const dialogInput = 'h-10 text-base';
  const dialogNumInput = `${dialogInput} ${pharmacyNoSpinInputClass}`;
  const dialogLabel = 'text-sm font-medium';

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
            {totals.lineDisc > 0 && (
              <div className="flex justify-between gap-3 text-gray-600">
                <span>Line discount</span>
                <span className="tabular-nums">−₹{totals.lineDisc.toFixed(2)}</span>
              </div>
            )}
            <div className="flex items-center justify-between gap-2 text-gray-600">
              <Label className="text-xs text-gray-600 shrink-0">Global disc %</Label>
              <Input
                className={`h-8 w-20 text-right ${pharmacyNoSpinInputClass}`}
                type="number"
                min="0"
                max="100"
                step="0.01"
                value={displayPharmacyNumericInput(header.bill_discount_pct)}
                onChange={(e) => setBillDiscount(
                  'bill_discount_pct',
                  e.target.value === '' ? '' : roundMoney(e.target.value),
                )}
                onBlur={persistBillDiscount}
              />
            </div>
            <div className="flex items-center justify-between gap-2 text-gray-600">
              <Label className="text-xs text-gray-600 shrink-0">Global disc ₹</Label>
              <Input
                className={`h-8 w-24 text-right ${pharmacyNoSpinInputClass}`}
                type="number"
                min="0"
                step="0.01"
                value={displayPharmacyNumericInput(
                  billDiscPct > 0 ? billDiscAmt : header.bill_discount_amount,
                )}
                onChange={(e) => setBillDiscount(
                  'bill_discount_amount',
                  e.target.value === '' ? '' : roundMoney(e.target.value),
                )}
                onBlur={persistBillDiscount}
              />
            </div>
            {totals.billDisc > 0 && (
              <div className="flex justify-between gap-3 text-gray-600">
                <span>Bill discount</span>
                <span className="tabular-nums">−₹{totals.billDisc.toFixed(2)}</span>
              </div>
            )}
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
                    <th className="px-2 py-1.5">Strips</th>
                    <th className="px-2 py-1.5 text-right">P-Rate</th>
                    <th className="px-2 py-1.5 text-right">Total</th>
                    <th className="px-2 py-1.5" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((ln, i) => {
                    const med = medicineCache[ln.medicine_id];
                    const c = calcLine(ln, hsnForLine(ln));
                    const lineInvalid = !ln.medicine_id
                      || !String(ln.batch_number || '').trim()
                      || !ln.expiry_mm_yyyy
                      || expiryToISO(ln.expiry_mm_yyyy) == null
                      || !isExpiryAfterCurrentMonth(ln.expiry_mm_yyyy)
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
                          {(ln.strip_conversion_factor || 1) > 1 ? (
                            <div className="text-[10px] text-gray-400">
                              = {((ln.quantity || 0) + (parseFloat(ln.free_quantity) || 0)) * (ln.strip_conversion_factor || 1)} tabs
                            </div>
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
        <DialogContent className="max-w-6xl w-[96vw] h-[92vh] max-h-[95vh] flex flex-col overflow-hidden gap-0 p-0 text-base" formNav="grid">
          <div className="shrink-0 border-b px-6 pt-5 pb-4">
            <DialogHeader className="space-y-0">
              <DialogTitle className="text-xl">
                {lineDialog?.mode === 'edit'
                  ? 'Edit line'
                  : lineDialog?.mode === 'batch'
                    ? 'Add another batch'
                    : 'Add line'}
              </DialogTitle>
            </DialogHeader>
          </div>
          {lineForm && (() => {
            const selectedMed = medicineCache[lineForm.medicine_id];
            const mfr = manufacturerOf(selectedMed);
            const company = selectedMed?.company_id != null ? companyById[selectedMed.company_id] : null;
            const medicineLocked = lineDialog?.mode === 'batch';
            return (
              <div className="flex-1 min-h-0 overflow-y-auto px-6 py-5 flex flex-col gap-5">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                  <div className="space-y-4 min-w-0">
                    {medicineLocked ? (
                      <div className="rounded-md border bg-gray-50 px-3 py-2.5 text-base space-y-1">
                        <div className="font-medium text-gray-900">{selectedMed?.name || 'Medicine'}</div>
                        <div className="text-sm text-gray-600">
                          {[selectedMed?.medicine_code, mfr].filter(Boolean).join(' · ')}
                        </div>
                      </div>
                    ) : (
                      <div>
                        <Label className={dialogLabel}>Medicine *</Label>
                        <PharmacyMedicinePicker
                          value={lineForm.medicine_id}
                          medicine={selectedMed}
                          companyById={companyById}
                          wideMenu
                          className="[&_input]:h-10 [&_input]:text-base [&_button]:h-10 [&_.font-medium]:text-base"
                          onSelect={applyMedicineToForm}
                          onCreateNew={(q) => openMedicineCreate({
                            name: q || '',
                            medicine_code: q || '',
                            barcode: q || undefined,
                          })}
                        />
                      </div>
                    )}

                    {lineForm.medicine_id && lineBatches.length > 0 && (
                      <div>
                        <Label className={dialogLabel}>Stock batch (optional)</Label>
                        <Select value={purchaseBatchSelectValue()} onValueChange={onPurchaseBatchSelect}>
                          <SelectTrigger className={dialogInput}>
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
                        <p className="text-sm text-gray-400 mt-1">
                          Pick an existing batch to prefill, or type a new batch number below.
                        </p>
                      </div>
                    )}

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label className={dialogLabel}>Batch # *</Label>
                        <Input
                          className={`${dialogInput} ${!String(lineForm.batch_number || '').trim() ? 'border-red-300' : ''}`}
                          placeholder="Batch number"
                          value={lineForm.batch_number}
                          onChange={(e) => setLineField('batch_number', e.target.value)}
                          autoFocus={!!lineForm.medicine_id}
                        />
                      </div>
                      <div>
                        <Label className={dialogLabel}>Expiry *</Label>
                        <Input
                          className={`${dialogInput} ${(!lineForm.expiry_mm_yyyy || expiryToISO(lineForm.expiry_mm_yyyy) == null || !isExpiryAfterCurrentMonth(lineForm.expiry_mm_yyyy)) ? 'border-red-300' : ''}`}
                          placeholder="MM/YYYY"
                          inputMode="numeric"
                          maxLength={7}
                          value={lineForm.expiry_mm_yyyy || ''}
                          onChange={(e) => setLineField('expiry_mm_yyyy', formatExpiryInput(e.target.value))}
                        />
                      </div>
                      <div>
                        <Label className={dialogLabel}>Qty (strips) *</Label>
                        <Input
                          className={dialogNumInput}
                          type="number"
                          min="0"
                          step="0.5"
                          value={displayPharmacyNumericInput(lineForm.quantity)}
                          onChange={(e) => setLineField('quantity', parseFloat(e.target.value) || 0)}
                        />
                      </div>
                      <div>
                        <Label className={dialogLabel}>Free (strips)</Label>
                        <Input
                          className={dialogNumInput}
                          type="number"
                          min="0"
                          step="0.5"
                          value={displayPharmacyNumericInput(lineForm.free_quantity)}
                          onChange={(e) => setLineField('free_quantity', e.target.value)}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="space-y-4 min-w-0">
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                      <div>
                        <Label className={dialogLabel}>P-Rate / strip *</Label>
                        <Input
                          className={dialogNumInput}
                          type="number"
                          step="0.01"
                          min="0"
                          value={displayPharmacyNumericInput(lineForm.purchase_rate)}
                          onChange={(e) => setLineField('purchase_rate', e.target.value === '' ? '' : roundMoney(e.target.value))}
                        />
                      </div>
                      <div>
                        <Label className={dialogLabel}>Tabs / strip</Label>
                        <Input
                          className={dialogNumInput}
                          type="number"
                          min="1"
                          step="1"
                          value={lineForm.strip_conversion_factor ?? 1}
                          onChange={(e) => setLineField('strip_conversion_factor', Math.max(1, parseInt(e.target.value, 10) || 1))}
                        />
                        <p className="text-xs text-gray-500 mt-0.5">
                          Stock +{((parseFloat(lineForm.quantity) || 0) + (parseFloat(lineForm.free_quantity) || 0)) * Math.max(1, parseInt(lineForm.strip_conversion_factor, 10) || 1)} tabs
                        </p>
                      </div>
                      <div>
                        <Label className={dialogLabel}>Disc %</Label>
                        <Input
                          className={dialogNumInput}
                          type="number"
                          min="0"
                          max="100"
                          step="0.01"
                          value={displayPharmacyNumericInput(lineForm.discount_pct)}
                          onChange={(e) => setLineField('discount_pct', e.target.value === '' ? '' : roundMoney(e.target.value))}
                        />
                      </div>
                      <div>
                        <Label className={dialogLabel}>MRP</Label>
                        <Input
                          className={dialogNumInput}
                          type="number"
                          step="0.01"
                          min="0"
                          value={displayPharmacyNumericInput(lineForm.mrp)}
                          onChange={(e) => setLineField('mrp', e.target.value === '' ? '' : roundMoney(e.target.value))}
                        />
                      </div>
                      <div>
                        <Label className={dialogLabel}>Rate A</Label>
                        <Input
                          className={dialogNumInput}
                          type="number"
                          step="0.01"
                          min="0"
                          value={displayPharmacyNumericInput(lineForm.rate_a)}
                          onChange={(e) => setLineField('rate_a', e.target.value === '' ? '' : roundMoney(e.target.value))}
                        />
                      </div>
                      <div>
                        <Label className={dialogLabel}>Rate B</Label>
                        <Input
                          className={dialogNumInput}
                          type="number"
                          step="0.01"
                          min="0"
                          value={displayPharmacyNumericInput(lineForm.rate_b)}
                          onChange={(e) => setLineField('rate_b', e.target.value === '' ? '' : roundMoney(e.target.value))}
                        />
                      </div>
                      <div className="sm:col-span-2">
                        <Label className={dialogLabel}>HSN / Tax</Label>
                        <PharmacyMasterSelectWithCreate
                          path="hsn"
                          value={lineForm.hsn_id}
                          onChange={(v) => setLineField('hsn_id', v)}
                          options={hsnList}
                          onOptionsChange={setHsnList}
                          placeholder="(none)"
                          allowEmpty
                          labelKey="code"
                          format={formatHsnOption}
                          className="[&_button]:h-10 [&_button]:text-base"
                        />
                      </div>
                      <div className="flex flex-col justify-end">
                        <Label className={dialogLabel}>Line total</Label>
                        <div className="h-10 flex items-center text-base font-semibold tabular-nums">
                          ₹{calcLine(lineForm, hsnForLine(lineForm)).total.toFixed(2)}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {selectedMed && (
                  <div className="mt-auto rounded-md border border-blue-100 bg-blue-50/60 px-4 py-3">
                    <div className="font-medium text-blue-900 text-base mb-3">Catalog</div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-x-4 gap-y-3 text-sm">
                      {[
                        { label: 'Name', value: selectedMed.name || '—' },
                        { label: 'Code', value: selectedMed.medicine_code || '—' },
                        { label: 'Manufacturer', value: mfr || '—' },
                        ...(company?.contact ? [{ label: 'Contact', value: company.contact }] : []),
                        { label: 'Generic', value: selectedMed.generic_name || '—' },
                        { label: 'Strength', value: selectedMed.strength || '—' },
                        { label: 'Pack', value: selectedMed.packaging || '—' },
                        { label: 'MRP', value: `₹${Number(selectedMed.mrp || 0).toFixed(2)}` },
                        { label: 'P-Rate', value: `₹${Number(selectedMed.purchase_rate || 0).toFixed(2)}` },
                        { label: 'Rate A', value: `₹${Number(selectedMed.rate_a || selectedMed.unit_price || 0).toFixed(2)}` },
                        { label: 'Rate B', value: `₹${Number(selectedMed.rate_b || 0).toFixed(2)}` },
                      ].map((row) => (
                        <div key={row.label} className="min-w-0">
                          <div className="text-xs text-blue-700/80 mb-0.5">{row.label}</div>
                          <div className="text-blue-950 font-medium truncate" title={String(row.value)}>{row.value}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })()}
          <div className="shrink-0 border-t px-6 py-4 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
            <Button type="button" variant="outline" className="h-10 text-base" onClick={closeLineDialog}>Cancel</Button>
            <Button type="button" className="h-10 text-base" onClick={submitLineDialog}>
              {lineDialog?.mode === 'edit' ? (
                <><Save className="h-4 w-4 mr-1.5" /> Save line</>
              ) : lineDialog?.mode === 'batch' ? (
                <><Plus className="h-4 w-4 mr-1.5" /> Add batch</>
              ) : (
                <><Plus className="h-4 w-4 mr-1.5" /> Add line</>
              )}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
