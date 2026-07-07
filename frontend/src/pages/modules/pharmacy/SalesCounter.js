import React, { useState, useCallback, useEffect, useMemo } from 'react';
import axios from 'axios';
import { useNavigate, useParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Badge } from '../../../components/ui/badge';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../../../components/ui/dialog';
import { useToast } from '../../../hooks/use-toast';
import { Search, Trash2, Receipt, Printer, Plus, ArrowLeftRight, AlertTriangle, ChevronDown, ChevronUp, User } from 'lucide-react';
import { errMsg } from '../PharmacyModule';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';
import PatientSearchPicker from '../../../components/PatientSearchPicker';
import QuickMedicineDialog from '../../../components/pharmacy/QuickMedicineDialog';
import PharmacyBatchSelectDialog from '../../../components/pharmacy/PharmacyBatchSelectDialog';
import {
  calcLineSubtotal,
  combinedBaseQty,
  displayPharmacyNumericInput,
  formatBatchSummary,
  formatRatesHint,
  linePricingSource,
  normalizeTabQtyToStrips,
  pharmacyNoSpinInputClass,
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
import { groupSaleItemsForCart } from './saleEditUtils';

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
  const { saleId } = useParams();
  const isEditing = Boolean(saleId);
  const { activeStoreId, activeStore, storeLocked } = usePharmacyStore();
  const { hasPerm } = usePharmacyPermissions();

  const [customer, setCustomer] = useState({
    patient_phone: '', patient_ip_id: '', patient_name: '', patient_address: '',
    doctor_number: '', doctor_name: '', payment_type: 'cash',
  });
  const [billingMode, setBillingMode] = useState('cash_at_pharmacy');
  const [taxMode, setTaxMode] = useState('inclusive');
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
  const [batchPick, setBatchPick] = useState(null);
  const [billDiscountAmount, setBillDiscountAmount] = useState('');
  const [editingSale, setEditingSale] = useState(null);
  const [editReason, setEditReason] = useState('');
  const [editReasonOpen, setEditReasonOpen] = useState(false);
  const [loadingEdit, setLoadingEdit] = useState(isEditing);

  const counterStoreId = editingSale?.store_id || activeStoreId;

  useEffect(() => {
    axios.get('/api/pharmacy/hsn').then((r) => setHsnList(r.data || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (isEditing || cartRestored || !activeStoreId) return;
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
  }, [activeStoreId, cartRestored, isEditing]);

  useEffect(() => {
    if (!saleId) return;
    let cancelled = false;
    (async () => {
      setLoadingEdit(true);
      try {
        const r = await axios.get(`/api/pharmacy/sales/${saleId}`);
        const sale = r.data || {};
        if (cancelled) return;
        setEditingSale({ id: sale.id, sale_number: sale.sale_number, store_id: sale.store_id });
        setCustomer({
          patient_phone: sale.patient_phone || '',
          patient_ip_id: sale.patient_ip_id || '',
          patient_name: sale.patient_name || '',
          patient_address: sale.patient_address || '',
          doctor_number: sale.doctor_number || '',
          doctor_name: sale.doctor_name || '',
          payment_type: sale.payment_type || 'cash',
        });
        setBillingMode(sale.billing_mode || 'cash_at_pharmacy');
        setTaxMode(sale.tax_mode || 'inclusive');
        setBillDiscountAmount('');
        if (sale.patient_ip_id) {
          const parts = (sale.patient_name || '').trim().split(/\s+/);
          setSelectedPatient({
            patient_id: sale.patient_ip_id,
            first_name: parts[0] || '',
            last_name: parts.slice(1).join(' '),
            primary_phone: sale.patient_phone || '',
            address: sale.patient_address || '',
          });
          setPatientPanelOpen(true);
        } else {
          setSelectedPatient(null);
        }
        const grouped = groupSaleItemsForCart(sale.items || []);
        const storeId = sale.store_id;
        const cartLines = await Promise.all(grouped.map(async (ln) => {
          const medR = await axios.get(`/api/pharmacy/medicines/${ln.medicine_id}`);
          const medicine = medR.data;
          let batches = [];
          if (storeId) {
            try {
              const bR = await axios.get('/api/pharmacy/inventory/batches', {
                params: {
                  medicine_id: ln.medicine_id,
                  store_id: storeId,
                  active_only: false,
                  ...(ln.batch_id ? { include_batch_id: ln.batch_id } : {}),
                },
              });
              batches = bR.data || [];
            } catch { /* ignore */ }
          }
          const batch = ln.batch_id
            ? (batches.find((b) => b.id === ln.batch_id) || {
              id: ln.batch_id,
              batch_number: ln.batch_number || `Batch #${ln.batch_id}`,
            })
            : null;
          if (batch && !batches.some((b) => b.id === batch.id)) {
            batches = [batch, ...batches];
          }
          const tempLine = {
            medicine,
            batch,
            batch_id: batch?.id || null,
            rate_tier: ln.rate_tier || 'A',
          };
          const original_need_qty = combinedBaseQty(
            ln.qty_tabs,
            ln.qty_strips,
            linePricingSource(tempLine),
          );
          return {
            medicine,
            qty_tabs: ln.qty_tabs,
            qty_strips: ln.qty_strips || '',
            rate_tier: ln.rate_tier || 'A',
            discount_pct: ln.discount_pct ?? '',
            batch_id: batch?.id || null,
            batch,
            batches,
            original_batch_id: ln.original_batch_id ?? batch?.id ?? null,
            original_batch_qty: ln.original_batch_qty || 0,
            batch_number: ln.batch_number || batch?.batch_number || null,
            original_need_qty,
            barcode_scanned: ln.barcode_scanned,
          };
        }));
        if (!cancelled) {
          setItems(cartLines);
          setCartRestored(true);
        }
      } catch (e) {
        if (!cancelled) {
          toast({ variant: 'destructive', title: 'Failed to load sale', description: errMsg(e) });
          navigate('/dashboard/pharmacy/sales');
        }
      } finally {
        if (!cancelled) setLoadingEdit(false);
      }
    })();
    return () => { cancelled = true; };
  }, [saleId, navigate, toast]);

  useEffect(() => {
    if (isEditing || !cartRestored || !activeStoreId) return;
    saveCart(activeStoreId, items, customer);
  }, [items, customer, activeStoreId, cartRestored, isEditing]);

  const lookup = useCallback(async (q, isBarcode = false) => {
    if (!q || q.length < 2) { setLookupResults([]); return; }
    if (!counterStoreId) { setLookupResults([]); return; }
    setSearching(true);
    try {
      const params = isBarcode
        ? { barcode: q, store_id: counterStoreId }
        : { q, store_id: counterStoreId };
      const r = await axios.get('/api/pharmacy/medicines/lookup', { params });
      setLookupResults(r.data || []);
    } catch { setLookupResults([]); }
    finally { setSearching(false); }
  }, [counterStoreId]);

  const onLookupChange = (v) => { setLookupQ(v); lookup(v); };

  const openMedicineCreate = () => {
    setMedicinePrefill({ name: lookupQ.trim(), medicine_code: lookupQ.trim() });
    setMedicineDialogOpen(true);
  };

  const handleMedicineCreated = async (med) => {
    try {
      const r = await axios.get('/api/pharmacy/medicines/lookup', {
        params: { q: med.name, store_id: counterStoreId },
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
  };

  const loadBatchesForMedicine = async (medicineId, { forLine } = {}) => {
    if (!medicineId || !counterStoreId) return [];
    try {
      const r = await axios.get('/api/pharmacy/inventory/batches', {
        params: {
          medicine_id: medicineId,
          store_id: counterStoreId,
          active_only: !isEditing,
          ...(forLine?.batch_id ? { include_batch_id: forLine.batch_id } : {}),
        },
      });
      let batches = r.data || [];
      if (!isEditing) {
        batches = batches.filter((b) => (b.quantity_in_stock || 0) > 0);
      }
      if (forLine?.batch_id) {
        const found = batches.some((b) => b.id === forLine.batch_id);
        if (!found && forLine.batch) {
          batches = [forLine.batch, ...batches];
        }
      }
      return batches;
    } catch {
      return forLine?.batch ? [forLine.batch] : [];
    }
  };

  const addLine = async (med) => {
    const batches = await loadBatchesForMedicine(med.id);
    const lineIndex = items.length;
    setItems(s => [...s, {
      medicine: med,
      qty_tabs: 1,
      qty_strips: '',
      rate_tier: 'A',
      discount_pct: med.default_discount_pct || '',
      batch_id: null,
      batch: null,
      batches,
      barcode_scanned: false,
    }]);
    if (batches.length > 0) {
      setBatchPick({ lineIndex, medicine: med, batches, loading: false });
    }
    setLookupQ(''); setLookupResults([]);
  };

  const updateLine = (i, patch) => setItems(s => s.map((x, idx) => idx === i ? { ...x, ...patch } : x));
  const removeLine = (i) => setItems(s => s.filter((_, idx) => idx !== i));

  const openBatchPick = async (lineIndex) => {
    const ln = items[lineIndex];
    if (!ln?.medicine?.id) return;
    setBatchPick({ lineIndex, medicine: ln.medicine, batches: [], loading: true });
    const batches = await loadBatchesForMedicine(ln.medicine.id, { forLine: ln });
    updateLine(lineIndex, { batches });
    setBatchPick({ lineIndex, medicine: ln.medicine, batches, loading: false });
  };

  const closeBatchPick = () => setBatchPick(null);

  const applySaleBatch = (batch, rateTier = 'A') => {
    if (batchPick?.lineIndex == null) return;
    const i = batchPick.lineIndex;
    const ln = items[i];
    const mergedBatches = ln?.batches?.some((b) => b.id === batch.id)
      ? ln.batches
      : [batch, ...(ln?.batches || [])];
    updateLine(i, {
      batch_id: batch.id,
      batch,
      batch_number: batch.batch_number || null,
      rate_tier: rateTier,
      batches: mergedBatches,
    });
    closeBatchPick();
  };

  const applySaleAutoBatch = (rateTier = 'A') => {
    if (batchPick?.lineIndex == null) return;
    updateLine(batchPick.lineIndex, { batch_id: null, batch: null, rate_tier: rateTier });
    closeBatchPick();
  };

  const handleQtyTabsChange = (i, raw) => {
    const ln = items[i];
    if (!ln) return;
    const parsed = raw === '' ? 0 : parseFloat(raw);
    const tabs = Number.isNaN(parsed) ? 0 : parsed;
    const src = linePricingSource(ln);
    updateLine(i, normalizeTabQtyToStrips(tabs, ln.qty_strips, src));
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

  const lineTotals = items.reduce((acc, ln) => {
    const c = calcSaleLine(ln);
    return {
      sub: acc.sub + c.base,
      lineDisc: acc.lineDisc + (c.base - c.afterDisc),
      tax: acc.tax + c.tax,
      linesGrand: acc.linesGrand + c.total,
    };
  }, { sub: 0, lineDisc: 0, tax: 0, linesGrand: 0 });

  const billDiscAmt = roundMoney(Math.min(parseFloat(billDiscountAmount) || 0, lineTotals.linesGrand));
  const totals = {
    sub: lineTotals.sub,
    lineDisc: lineTotals.lineDisc,
    billDisc: billDiscAmt,
    disc: roundMoney(lineTotals.lineDisc + billDiscAmt),
    tax: lineTotals.tax,
    grand: roundMoney(Math.max(0, lineTotals.linesGrand - billDiscAmt)),
  };

  const lineNeedQty = (ln) => combinedBaseQty(ln.qty_tabs, ln.qty_strips, linePricingSource(ln));

  const stockIssues = useMemo(() => {
    if (isEditing) return [];
    return items.map((ln) => {
      const need = lineNeedQty(ln);
      let avail = 0;
      if (ln.batch_id && ln.batch) {
        avail = ln.batch.quantity_in_stock ?? 0;
      } else {
        avail = ln.medicine?.store_stock_qty ?? 0;
      }
      if (need <= 0 || avail >= need) return null;
      return { ln, need, avail, master: ln.medicine?.master_stock_qty ?? 0 };
    }).filter(Boolean);
  }, [items, isEditing]);

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

  const validateSaleForm = () => {
    if (!counterStoreId) {
      toast({ variant: 'destructive', title: 'Select a pharmacy store first' });
      return false;
    }
    if (items.length === 0) {
      toast({ variant: 'destructive', title: 'Add at least one item' });
      return false;
    }
    const invalid = items.find(ln => lineNeedQty(ln) <= 0);
    if (invalid) {
      toast({ variant: 'destructive', title: 'Enter tab or strip qty on each line' });
      return false;
    }
    if (stockIssues.length > 0) {
      toast({
        variant: 'destructive',
        title: 'Insufficient stock at this store',
        description: `${stockIssues[0].ln.medicine.name}: need ${stockIssues[0].need}, have ${stockIssues[0].avail}`,
      });
      return false;
    }
    return true;
  };

  const handleSaveClick = () => {
    if (!validateSaleForm()) return;
    if (isEditing) {
      setEditReason('');
      setEditReasonOpen(true);
      return;
    }
    submitSale();
  };

  const confirmEditSale = () => {
    if (!editReason.trim()) {
      toast({ variant: 'destructive', title: 'Enter a reason for this edit' });
      return;
    }
    setEditReasonOpen(false);
    submitSale();
  };

  const submitSale = async () => {
    if (!validateSaleForm()) return;
    if (isEditing && !editReason.trim()) {
      setEditReasonOpen(true);
      return;
    }
    setSubmitting(true);
    try {
      const payload = {
        ...customer,
        store_id: counterStoreId,
        billing_mode: billingMode,
        tax_mode: taxMode,
        bill_discount_amount: billDiscAmt,
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
      const r = isEditing
        ? await axios.put(`/api/pharmacy/sales/${editingSale.id}`, { ...payload, reason: editReason.trim() })
        : await axios.post('/api/pharmacy/sales', payload);
      const d = r.data || {};
      toast({
        title: isEditing
          ? `Sale ${d.sale_number} updated (₹${d.grand_total})`
          : d.billing_mode === 'inpatient_bill'
            ? `Sale ${d.sale_number} added to inpatient bill`
            : `Sale ${d.sale_number} saved (₹${d.grand_total})`,
        description: !isEditing && d.billing_mode === 'inpatient_bill'
          ? 'Patient pays at discharge or interim bill'
          : undefined,
      });
      setPreviewSaleId(d.id);
      if (isEditing) {
        navigate('/dashboard/pharmacy/sales');
        return;
      }
      setLastSale(d);
      setItems([]);
      clearCartStorage();
      setSelectedPatient(null);
      setBillingMode('cash_at_pharmacy');
      setTaxMode('inclusive');
      setBillDiscountAmount('');
      setCustomer({ patient_phone: '', patient_ip_id: '', patient_name: '', patient_address: '', doctor_number: '', doctor_name: '', payment_type: 'cash' });
    } catch (e) {
      toast({ variant: 'destructive', title: isEditing ? 'Update failed' : 'Sale failed', description: errMsg(e) });
    } finally { setSubmitting(false); }
  };

  const setC = (k, v) => setCustomer(s => ({ ...s, [k]: v }));

  const patientSummary = selectedPatient
    ? (customer.patient_name || 'Patient linked')
    : customer.patient_name
      ? customer.patient_name
      : 'Walk-in (optional)';

  const compactInput = 'h-8 text-sm';
  const numberInputClass = `h-8 w-full min-w-0 text-center px-1 ${pharmacyNoSpinInputClass}`;

  const resetSale = () => {
    if (isEditing) {
      navigate('/dashboard/pharmacy/sales');
      return;
    }
    setItems([]);
    setLastSale(null);
    setSelectedPatient(null);
    setBillingMode('cash_at_pharmacy');
    setTaxMode('inclusive');
    setBillDiscountAmount('');
    clearCartStorage();
    setCustomer({
      patient_phone: '',
      patient_ip_id: '',
      patient_name: '',
      patient_address: '',
      doctor_number: '',
      doctor_name: '',
      payment_type: 'cash',
    });
  };

  return (
    <div className="flex flex-col flex-1 min-h-0 gap-2">
      {loadingEdit ? (
        <p className="text-center py-12 text-sm text-gray-500">Loading sale…</p>
      ) : (
      <>
      {!counterStoreId && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 shrink-0">
          No pharmacy store is available for your account. Ask an administrator to assign you to a store under Pharmacy → Stores.
        </div>
      )}

      {stockIssues.length > 0 && !isEditing && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 space-y-2 shrink-0">
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

      <FormNavContainer mode="grid" className="grid grid-cols-1 xl:grid-cols-[minmax(280px,320px)_1fr] grid-rows-[auto_minmax(0,1fr)] xl:grid-rows-none gap-2 items-stretch flex-1 min-h-0">
      <Card className="order-2 xl:order-2 min-w-0 min-h-0 flex flex-col overflow-hidden rounded-none xl:rounded-lg border-x-0 xl:border-x">
        <CardHeader className="py-2 px-3 shrink-0 space-y-0">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <CardTitle className="text-base">
              {isEditing ? `Edit Sale ${editingSale?.sale_number || ''}` : 'Add Items'}
            </CardTitle>
            <div className="flex items-center gap-1.5 flex-wrap justify-end">
              <PharmacyStoreSelector compact posMode={storeLocked || !!activeStore} />
              {lastSale && (
                <Button size="sm" variant="outline" className="h-8" onClick={() => setPreviewSaleId(lastSale.id)}>
                  <Printer className="h-3 w-3 sm:mr-1" />
                  <span className="hidden sm:inline">Print</span>
                </Button>
              )}
              <Button size="sm" variant="outline" className="h-8" onClick={resetSale}>{isEditing ? 'Cancel' : 'Reset'}</Button>
              <Button
                size="sm"
                className="h-8"
                onClick={handleSaveClick}
                disabled={submitting || items.length === 0 || !counterStoreId || stockIssues.length > 0}
              >
                <Receipt className="h-3.5 w-3.5 sm:mr-1" />
                <span className="hidden sm:inline">{isEditing ? 'Update Sale' : 'Save Sale'}</span>
                <span className="sm:hidden">{isEditing ? 'Update' : 'Save'}</span>
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="pt-0 px-3 pb-3 flex flex-col min-h-0 flex-1 overflow-hidden">
          <div className="flex gap-2 items-end mb-2 shrink-0">
            <div className="flex-1 relative">
              <Label className="text-xs">Search / Scan barcode</Label>
              <Search className="absolute left-2 top-8 h-4 w-4 text-gray-400" />
              <Input className={`pl-8 ${compactInput}`} placeholder="Type name / code / scan barcode…"
                value={lookupQ}
                disabled={!counterStoreId}
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

          <div className="flex-1 min-h-0 overflow-y-auto overflow-x-auto">
          {items.length === 0 ? (
            <p className="text-center py-4 text-sm text-gray-500">No items yet — search above or scan a barcode.</p>
          ) : (
            <FormNavContainer mode="table">
              <table className="w-full text-sm table-fixed">
                <colgroup>
                  <col className="w-[24%]" />
                  <col className="w-[26%]" />
                  <col className="w-[72px]" />
                  <col className="w-[72px]" />
                  <col className="w-[72px]" />
                  <col className="w-[84px]" />
                  <col className="w-[36px]" />
                </colgroup>
                <thead><tr className="border-b text-left text-gray-600">
                  <th className="py-2 pr-1">Medicine</th>
                  <th className="py-2 pl-0 pr-2">Batch</th>
                  <th className="py-2 px-1 text-center">Qty Tab</th>
                  <th className="py-2 px-1 text-center">Qty Strip</th>
                  <th className="py-2 px-1 text-center">Disc %</th>
                  <th className="py-2 pl-2 text-right">Subtotal</th>
                  <th className="py-2"></th>
                </tr></thead>
                <tbody>
                  {items.map((ln, i) => {
                    const pricing = linePricingSource(ln);
                    const batches = ln.batches || [];
                    const batchLabel = ln.batch?.batch_number
                      || ln.batch_number
                      || (ln.batch_id ? `Batch #${ln.batch_id}` : null);
                    const batchSummary = !isEditing && ln.batch ? formatBatchSummary(ln.batch) : null;
                    return (
                    <tr key={i} className="border-b">
                      <td className="py-2 pr-1 align-top">
                        <div className="font-medium leading-tight">{ln.medicine.name}</div>
                        <div className="text-xs text-gray-500 mt-0.5">{ln.medicine.medicine_code}</div>
                        {!isEditing && (
                          <>
                            <div className="text-[10px] text-gray-500">{formatRatesHint(ln.medicine, ln.rate_tier, ln.batch)}</div>
                            {pricing.strip_conversion_factor > 1 && (
                              <div className="text-[10px] text-gray-400">{pricing.strip_conversion_factor} tabs/strip</div>
                            )}
                            <div className="text-[10px] text-gray-500">
                              {ln.batch_id ? 'Batch' : 'Store'} stock: {ln.batch_id && ln.batch
                                ? (ln.batch.quantity_in_stock ?? 0)
                                : (ln.medicine?.store_stock_qty ?? 0)}
                            </div>
                          </>
                        )}
                      </td>
                      <td className="py-2 pl-0 pr-2 align-top">
                        {(batches.length > 0 || ln.batch || isEditing) ? (
                          <button
                            type="button"
                            className="text-left text-xs leading-tight w-full hover:text-blue-700 focus:outline-none focus-visible:underline"
                            onClick={() => openBatchPick(i)}
                            {...navCellProps(i, 0)}
                          >
                            {isEditing ? (
                              <span className="flex flex-col items-start gap-0.5 min-w-0">
                                <span className="font-medium break-all text-gray-900">
                                  {batchLabel || 'Pick batch'}
                                </span>
                                <span className="text-[10px] text-blue-700">Rate {ln.rate_tier || 'A'}</span>
                              </span>
                            ) : batchSummary ? (
                              <span className="flex flex-col items-start gap-0.5 min-w-0">
                                <span className="font-medium break-all text-gray-900">{batchSummary.title}</span>
                                {batchSummary.meta && (
                                  <span className="text-[10px] text-gray-500 break-words">{batchSummary.meta}</span>
                                )}
                                <span className="text-[10px] text-blue-700">Rate {ln.rate_tier || 'A'}</span>
                              </span>
                            ) : (
                              <span className="flex flex-col items-start gap-0.5 text-gray-700">
                                <span>Auto (nearest expiry)</span>
                                <span className="text-[10px] text-blue-700">Rate {ln.rate_tier || 'A'}</span>
                              </span>
                            )}
                          </button>
                        ) : (
                          <span className="text-xs text-gray-400">No stock batches</span>
                        )}
                      </td>
                      <td className="py-2 px-1 align-top">
                        <Input className={numberInputClass} type="number" min="0" step={ln.medicine.decimal_supported ? '0.5' : '1'}
                          value={displayPharmacyNumericInput(ln.qty_tabs)}
                          onChange={e => handleQtyTabsChange(i, e.target.value)}
                          {...navCellProps(i, 1)} />
                      </td>
                      <td className="py-2 px-1 align-top">
                        {supportsStripSale(pricing) ? (
                          <Input className={numberInputClass} type="number" min="0" step="1"
                            value={displayPharmacyNumericInput(ln.qty_strips)}
                            onChange={e => updateLine(i, { qty_strips: e.target.value })}
                            {...navCellProps(i, 2)} />
                        ) : (
                          <span className="text-xs text-gray-400 block text-center">—</span>
                        )}
                      </td>
                      <td className="py-2 px-1 align-top">
                        <Input className={numberInputClass} type="number" min="0" max="100" step="0.01"
                          value={displayPharmacyNumericInput(ln.discount_pct)} onChange={e => updateLine(i, { discount_pct: e.target.value })}
                          {...navCellProps(i, 3)} />
                      </td>
                      <td className="py-2 pl-2 text-right align-top whitespace-nowrap">₹{calcSaleLine(ln).total.toFixed(2)}</td>
                      <td className="py-2 align-top">
                        <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => removeLine(i)}><Trash2 className="h-3 w-3 text-red-500" /></Button>
                      </td>
                    </tr>
                  );})}
                </tbody>
              </table>
            </FormNavContainer>
          )}
          </div>

          {!isEditing && (
            <p className="text-xs text-gray-500 mt-2 shrink-0">
              Sales deduct stock from the selected store only. If stock is at master, request a transfer first.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="order-1 xl:order-1 flex flex-col min-w-0 min-h-0 h-full xl:max-h-none bg-card border border-border rounded-none xl:rounded-lg overflow-hidden">
        <div className="shrink-0">
        <div className="py-2 px-3 border-b">
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
        </div>
        <div className={`px-3 pb-3 pt-0 space-y-2 ${patientPanelOpen ? 'block' : 'hidden'} xl:block`}>
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
                  <SelectItem value="inclusive">Tax Include</SelectItem>
                  <SelectItem value="exclusive">Tax Exclude</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {selectedPatient?.patient_id && (
              <div className="col-span-2">
                <Label className="text-xs">Billing</Label>
                <Select value={billingMode} onValueChange={setBillingMode}>
                  <SelectTrigger className={compactInput}><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash_at_pharmacy">Collect payment now</SelectItem>
                    <SelectItem value="inpatient_bill">Add to inpatient bill</SelectItem>
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
        </div>
        </div>

        <div className="flex-1 min-h-[200px] border-t bg-gray-50/40 flex flex-col justify-end px-4 py-4 space-y-2">
          <div className="flex justify-between text-sm text-gray-600">
            <span>Subtotal</span>
            <span>₹{totals.sub.toFixed(2)}</span>
          </div>
          {totals.lineDisc > 0 && (
            <div className="flex justify-between text-sm text-gray-600">
              <span>Line discount</span>
              <span>−₹{totals.lineDisc.toFixed(2)}</span>
            </div>
          )}
          <div className="flex items-center justify-between gap-2 text-sm text-gray-600">
            <Label className="text-sm text-gray-600 shrink-0">Bill discount (₹)</Label>
            <Input
              className={`h-9 w-28 text-right ${pharmacyNoSpinInputClass}`}
              type="number"
              min="0"
              step="0.01"
              value={displayPharmacyNumericInput(billDiscountAmount)}
              onChange={(e) => setBillDiscountAmount(e.target.value)}
            />
          </div>
          {totals.billDisc > 0 && (
            <div className="flex justify-between text-sm text-gray-600">
              <span>Bill discount applied</span>
              <span>−₹{totals.billDisc.toFixed(2)}</span>
            </div>
          )}
          <div className="flex justify-between text-sm text-gray-600">
            <span>Tax ({taxMode === 'inclusive' ? 'included' : 'added'})</span>
            <span>{taxMode === 'inclusive' ? '' : '+'}₹{totals.tax.toFixed(2)}</span>
          </div>
          <div className="pt-3 mt-1 border-t flex justify-between items-end gap-3">
            <span className="text-base font-medium text-gray-700 pb-1">Grand Total</span>
            <span className="text-4xl font-bold tracking-tight text-gray-900 leading-none">
              ₹{totals.grand.toFixed(2)}
            </span>
          </div>
        </div>
      </div>
      </FormNavContainer>
      </>
      )}

      <PdfPreviewDialog
        open={!!previewSaleId}
        onClose={() => setPreviewSaleId(null)}
        title="Sale Invoice Preview"
        path={previewSaleId ? `/api/pharmacy/sales/${previewSaleId}/invoice/pdf` : null}
      />

      <Dialog open={editReasonOpen} onOpenChange={setEditReasonOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Edit reason required</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <Label>Why are you changing sale {editingSale?.sale_number}?</Label>
            <Textarea
              rows={3}
              placeholder="e.g. wrong qty, batch correction, patient details"
              value={editReason}
              onChange={(e) => setEditReason(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) confirmEditSale();
              }}
            />
            <p className="text-xs text-gray-500">Stock is restored and re-deducted. This reason is saved in the audit log.</p>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setEditReasonOpen(false)}>Cancel</Button>
            <Button type="button" onClick={confirmEditSale} disabled={submitting || !editReason.trim()}>
              Update Sale
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <PharmacyBatchSelectDialog
        open={!!batchPick}
        onOpenChange={(open) => { if (!open) closeBatchPick(); }}
        medicine={batchPick?.medicine}
        batches={batchPick?.batches || []}
        loading={batchPick?.loading}
        includeAutoOption
        showNewBatchOption={false}
        showRateTierStep
        initialRateTier={batchPick?.lineIndex != null ? (items[batchPick.lineIndex]?.rate_tier || 'A') : 'A'}
        onSelectBatch={applySaleBatch}
        onSelectAuto={applySaleAutoBatch}
        onCancel={closeBatchPick}
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
