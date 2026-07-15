import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import axios from 'axios';
import {
  Receipt, Search, Download, DollarSign, TrendingUp, Clock,
  CheckCircle2, Loader2, XCircle, Ban, CreditCard, Eye,
  Building2, Stethoscope, FlaskConical, BedDouble, Printer, FileText, ChevronDown
} from 'lucide-react';
import { printPdfFromUrl } from '../../utils/printPdf';
import PdfPreviewDialog from '../../components/PdfPreviewDialog';
import PatientSearchPicker from '../../components/PatientSearchPicker';
import { localDateString, localDateStringOffset, localWeekStart, localMonthStart, localLastMonthRange } from '../../utils/localDate';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../../components/ui/dropdown-menu';

const BillingModule = () => {
  const [bills, setBills] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('all');

  // Filters
  const today = localDateString();
  const weekAgo = localDateStringOffset(-7);
  const [dateFrom, setDateFrom] = useState(weekAgo);
  const [dateTo, setDateTo] = useState(today);
  const [patientSearch, setPatientSearch] = useState('');
  const [paymentStatus, setPaymentStatus] = useState('all');
  const [doctorFilter, setDoctorFilter] = useState('all');
  const [doctors, setDoctors] = useState([]);
  const [referrals, setReferrals] = useState([]);
  const [referralFilter, setReferralFilter] = useState('all');

  // Cancel dialog
  const [cancelBill, setCancelBill] = useState(null);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelling, setCancelling] = useState(false);

  // Bill detail dialog
  const [detailBill, setDetailBill] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailData, setDetailData] = useState(null);

  // Discount / tax adjust dialog
  const [adjustMode, setAdjustMode] = useState(null); // 'discount' | 'tax' | null
  const [adjustForm, setAdjustForm] = useState({ kind: 'percent', value: '', reason: '' });
  const [adjustSaving, setAdjustSaving] = useState(false);

  // Refund dialog
  const [refundPayment, setRefundPayment] = useState(null);
  const [refundForm, setRefundForm] = useState({ amount: '', reason: '' });
  const [refundSaving, setRefundSaving] = useState(false);

  // Credit note dialog
  const [creditNoteOpen, setCreditNoteOpen] = useState(false);
  const [creditNoteForm, setCreditNoteForm] = useState({
    items: [{ item_name: '', quantity: 1, unit_price: '' }],
    reason: '',
  });
  const [creditNoteSaving, setCreditNoteSaving] = useState(false);

  // Bill splits (insurance / TPA) — admission bills only
  const [splits, setSplits] = useState([]);
  const [splitEditOpen, setSplitEditOpen] = useState(false);
  const [splitForm, setSplitForm] = useState([]);
  const [splitSaving, setSplitSaving] = useState(false);
  const [tpaList, setTpaList] = useState([]);

  // Reports
  const [reportKind, setReportKind] = useState('daily-collection'); // daily-collection | doctor-revenue | tax-summary
  const [reportFrom, setReportFrom] = useState(weekAgo);
  const [reportTo, setReportTo] = useState(today);
  const [reportData, setReportData] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);

  // Consolidate dialog
  const [consolidateOpen, setConsolidateOpen] = useState(false);
  const [consolidatePatient, setConsolidatePatient] = useState(null);
  const [consolidatePreview, setConsolidatePreview] = useState(null);
  const [consolidatePicked, setConsolidatePicked] = useState({ consultations: new Set(), labs: new Set() });
  const [consolidateSaving, setConsolidateSaving] = useState(false);

  // Payment dialog
  const [payBill, setPayBill] = useState(null);
  const [paymentForm, setPaymentForm] = useState({
    amount_paid: '', payment_method: 'cash', transaction_reference: '', notes: ''
  });
  const [paymentLoading, setPaymentLoading] = useState(false);

  // PDF preview for consultation / lab bills (and any row without a detail dialog)
  const [pdfPreview, setPdfPreview] = useState(null);
  const [exporting, setExporting] = useState(false);

  const buildBillingParams = useCallback(() => {
    const params = new URLSearchParams();
    params.set('date_from', dateFrom);
    params.set('date_to', dateTo);
    if (patientSearch) params.set('patient_search', patientSearch);
    if (activeTab === 'outpatient') params.set('bill_type', 'consultation');
    else if (activeTab === 'lab') params.set('bill_type', 'lab');
    else if (activeTab === 'inpatient') params.set('bill_type', 'admission');
    if (paymentStatus !== 'all') params.set('payment_status', paymentStatus);
    if (doctorFilter !== 'all') params.set('doctor_id', doctorFilter);
    if (referralFilter !== 'all') params.set('referred_by', referralFilter);
    return params;
  }, [dateFrom, dateTo, patientSearch, activeTab, paymentStatus, doctorFilter, referralFilter]);

  const fetchBills = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`/api/hospital/billing?${buildBillingParams().toString()}`);
      setBills(res.data.bills || []);
      setSummary(res.data.summary || null);
      if (res.data.doctors) setDoctors(res.data.doctors);
      if (res.data.referrals) setReferrals(res.data.referrals);
    } catch (err) {
      console.error('Failed to fetch bills:', err);
    } finally {
      setLoading(false);
    }
  }, [buildBillingParams]);

  useEffect(() => { fetchBills(); }, [fetchBills]);

  const formatCurrency = (val) => `₹${Number(val || 0).toLocaleString('en-IN', { minimumFractionDigits: 0 })}`;
  const formatDate = (d) => {
    if (!d) return '-';
    try { return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }); }
    catch { return d; }
  };

  const getTypeIcon = (type) => {
    switch (type) {
      case 'consultation': return <Stethoscope className="h-3 w-3" />;
      case 'lab': return <FlaskConical className="h-3 w-3" />;
      case 'admission': return <BedDouble className="h-3 w-3" />;
      default: return <Receipt className="h-3 w-3" />;
    }
  };

  const getTypeColor = (type) => {
    switch (type) {
      case 'consultation': return 'border-blue-200 text-blue-700 bg-blue-50';
      case 'lab': return 'border-purple-200 text-purple-700 bg-purple-50';
      case 'admission': return 'border-teal-200 text-teal-700 bg-teal-50';
      default: return 'border-gray-200 text-gray-700';
    }
  };

  const getStatusBadge = (status) => {
    const colors = {
      paid: 'bg-green-100 text-green-700',
      pending: 'bg-orange-100 text-orange-700',
      partial: 'bg-yellow-100 text-yellow-700',
      cancelled: 'bg-red-100 text-red-700',
    };
    return colors[status] || 'bg-gray-100 text-gray-700';
  };

  /** API path for the printable PDF of a billing row, or null when unavailable. */
  const getBillPdfPath = (bill) => {
    if (!bill) return null;
    switch (bill.type) {
      case 'consultation':
        return bill.bill_id ? `/api/appointments/${bill.bill_id}/bill/download` : null;
      case 'lab':
        if (bill.lab_bill_group_id) return `/api/lab/bills/${bill.lab_bill_group_id}/pdf`;
        return bill.bill_id ? `/api/lab/orders/${bill.bill_id}/bill` : null;
      case 'admission':
        return bill.admission_id ? `/api/inpatient/admissions/${bill.admission_id}/bill/pdf` : null;
      case 'day_care':
      case 'consolidated':
        return bill.bill_id ? `/api/hospital/billing/bills/${bill.bill_id}/pdf` : null;
      default:
        return bill.bill_id ? `/api/hospital/billing/bills/${bill.bill_id}/pdf` : null;
    }
  };

  const handlePrintBill = (bill) => {
    const path = getBillPdfPath(bill);
    if (!path) return;
    printPdfFromUrl(path, {
      onError: (msg) => alert(msg || 'Could not load the bill PDF'),
    });
  };

  const handleViewBill = (bill) => {
    if (bill.type === 'admission' || bill.type === 'consolidated' || bill.type === 'day_care') {
      openBillDetail(bill);
      return;
    }
    const path = getBillPdfPath(bill);
    if (path) {
      setPdfPreview({ title: `Bill — ${bill.reference || bill.patient_name}`, path });
    }
  };

  const handleCancelBill = async () => {
    if (!cancelBill || !cancelReason.trim()) return;
    setCancelling(true);
    try {
      if (cancelBill.type === 'admission') {
        await axios.post(
          `/api/inpatient/admissions/${cancelBill.admission_id}/bills/${cancelBill.bill_id}/cancel`,
          { reason: cancelReason.trim() }
        );
      } else {
        await axios.post(`/api/hospital/billing/cancel/${cancelBill.type}/${cancelBill.bill_id}`, {
          reason: cancelReason.trim()
        });
      }
      setCancelBill(null);
      setCancelReason('');
      fetchBills();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail && typeof detail === 'object' && detail.code === 'bill_has_payments') {
        alert(`${detail.message}\n\nAmount already paid: ₹${detail.amount_paid}\nUse the deposit refund flow first, then retry.`);
      } else {
        alert(typeof detail === 'string' ? detail : 'Cancel failed');
      }
    } finally {
      setCancelling(false);
    }
  };

  const fetchSplits = async (billId) => {
    try {
      const res = await axios.get(`/api/inpatient/bills/${billId}/split`);
      setSplits(res.data || []);
    } catch (err) {
      setSplits([]);
    }
  };

  const openBillDetail = async (bill) => {
    // Bills backed by the bills table use the detail endpoint
    if (bill.type === 'admission' || bill.type === 'consolidated' || bill.type === 'day_care') {
      setDetailBill(bill);
      setDetailLoading(true);
      setSplits([]);
      try {
        const res = await axios.get(`/api/hospital/billing/bills/${bill.bill_id}`);
        setDetailData(res.data);
        fetchSplits(bill.bill_id);
        if (!tpaList.length) {
          try {
            const tpaRes = await axios.get('/api/inpatient/tpa');
            setTpaList(tpaRes.data || []);
          } catch (_) { /* TPA optional */ }
        }
      } catch (err) {
        console.error('Failed to load bill detail:', err);
        setDetailData(null);
      } finally {
        setDetailLoading(false);
      }
    } else {
      // For consultation/lab, show inline summary
      setDetailBill(bill);
      setDetailData(null);
    }
  };

  const openSplitEditor = () => {
    if (splits.length) {
      setSplitForm(splits.map((s) => ({
        payer_type: s.payer_type, payer_name: s.payer_name,
        tpa_id: s.tpa_id || '', amount: String(s.amount), notes: s.notes || '',
      })));
    } else {
      setSplitForm([{ payer_type: 'cash', payer_name: 'Cash', tpa_id: '', amount: String(detailData.total_amount), notes: '' }]);
    }
    setSplitEditOpen(true);
  };

  const submitSplits = async () => {
    if (!detailBill) return;
    const billTotal = Number(detailData.total_amount || 0);
    const sum = splitForm.reduce((s, r) => s + (parseFloat(r.amount) || 0), 0);
    if (Math.abs(sum - billTotal) > 0.01) {
      alert(`Split sum ₹${sum.toFixed(2)} must equal bill total ₹${billTotal.toFixed(2)}`);
      return;
    }
    const payload = {
      splits: splitForm.map((r) => ({
        payer_type: r.payer_type,
        payer_name: r.payer_name.trim() || (r.payer_type === 'cash' ? 'Cash' : ''),
        tpa_id: r.payer_type === 'tpa' ? (parseInt(r.tpa_id) || null) : null,
        amount: parseFloat(r.amount),
        notes: r.notes || null,
      })),
    };
    if (payload.splits.some((s) => !s.payer_name)) {
      alert('Each split needs a payer name.');
      return;
    }
    if (payload.splits.some((s) => s.payer_type === 'tpa' && !s.tpa_id)) {
      alert('TPA splits need a TPA selected.');
      return;
    }
    setSplitSaving(true);
    try {
      await axios.post(`/api/inpatient/bills/${detailBill.bill_id}/split`, payload);
      setSplitEditOpen(false);
      fetchSplits(detailBill.bill_id);
    } catch (err) {
      const detail = err.response?.data?.detail;
      alert(typeof detail === 'string' ? detail : 'Saving splits failed');
    } finally {
      setSplitSaving(false);
    }
  };

  const markSplitReceived = async (split) => {
    const reference = window.prompt(`Payment reference for ${split.payer_name} (₹${split.amount}):`, '');
    if (reference === null) return;
    try {
      const url = `/api/inpatient/bill-splits/${split.id}/payment` +
        (reference ? `?payment_reference=${encodeURIComponent(reference)}` : '');
      await axios.patch(url);
      fetchSplits(detailBill.bill_id);
    } catch (err) {
      const detail = err.response?.data?.detail;
      alert(typeof detail === 'string' ? detail : 'Failed to record split payment');
    }
  };

  const openAdjustDialog = (mode) => {
    setAdjustMode(mode);
    setAdjustForm({ kind: mode === 'tax' ? 'percent' : 'percent', value: '', reason: '' });
  };

  const submitAdjustment = async () => {
    if (!detailBill || !adjustMode) return;
    const value = parseFloat(adjustForm.value);
    if (!(value >= 0) || !adjustForm.reason.trim() || adjustForm.reason.trim().length < 2) return;
    setAdjustSaving(true);
    try {
      const url = `/api/hospital/billing/bills/${detailBill.bill_id}/${adjustMode}`;
      const body = adjustMode === 'tax'
        ? { tax_percentage: value, reason: adjustForm.reason.trim() }
        : (adjustForm.kind === 'percent'
            ? { discount_percentage: value, reason: adjustForm.reason.trim() }
            : { discount_amount: value, reason: adjustForm.reason.trim() });
      await axios.patch(url, body);
      // Refetch detail + list
      const res = await axios.get(`/api/hospital/billing/bills/${detailBill.bill_id}`);
      setDetailData(res.data);
      setAdjustMode(null);
      fetchBills();
    } catch (err) {
      const detail = err.response?.data?.detail;
      alert(typeof detail === 'string' ? detail : 'Adjustment failed');
    } finally {
      setAdjustSaving(false);
    }
  };

  const openRefundDialog = (payment) => {
    setRefundPayment(payment);
    setRefundForm({ amount: String(payment.amount_paid), reason: '' });
  };

  const submitRefund = async () => {
    if (!refundPayment) return;
    const amt = parseFloat(refundForm.amount);
    if (!(amt > 0) || !refundForm.reason.trim() || refundForm.reason.trim().length < 2) return;
    setRefundSaving(true);
    try {
      const r = await axios.post(`/api/hospital/billing/payments/${refundPayment.id}/refund`, {
        amount: amt,
        reason: refundForm.reason.trim(),
      });
      setRefundPayment(null);
      // Refresh detail + list, then offer the PDF
      if (detailBill) {
        const res = await axios.get(`/api/hospital/billing/bills/${detailBill.bill_id}`);
        setDetailData(res.data);
      }
      fetchBills();
      if (r.data?.refund_id && window.confirm('Refund recorded. Open refund receipt?')) {
        printPdfFromUrl(`/api/hospital/billing/payments/${r.data.refund_id}/refund-receipt/pdf`);
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      alert(typeof detail === 'string' ? detail : 'Refund failed');
    } finally {
      setRefundSaving(false);
    }
  };

  const fetchReport = useCallback(async () => {
    setReportLoading(true);
    try {
      const res = await axios.get(
        `/api/hospital/billing/reports/${reportKind}?date_from=${reportFrom}&date_to=${reportTo}`
      );
      setReportData(res.data);
    } catch (err) {
      setReportData(null);
    } finally {
      setReportLoading(false);
    }
  }, [reportKind, reportFrom, reportTo]);

  useEffect(() => {
    if (activeTab === 'reports') fetchReport();
  }, [activeTab, fetchReport]);

  const exportReportCSV = () => {
    if (!reportData) return;
    let header = [];
    let lines = [];
    if (reportKind === 'daily-collection') {
      const methods = reportData.methods || [];
      header = ['Date', 'Net total', 'Refunds', ...methods];
      lines = reportData.rows.map((r) => [r.date, r.total, r.refunds, ...methods.map((m) => r.by_method?.[m] || 0)]);
    } else if (reportKind === 'doctor-revenue') {
      header = ['Doctor', 'Consultations', 'Consult revenue', 'Admissions', 'Admission revenue', 'Total'];
      lines = reportData.rows.map((r) => [r.doctor_name, r.consultation_count, r.consultation_revenue,
                                           r.admission_count, r.admission_revenue, r.total_revenue]);
    } else {
      header = ['Date', 'Bills', 'Taxable value', 'Tax amount'];
      lines = reportData.rows.map((r) => [r.date, r.bill_count, r.taxable_value, r.tax_amount]);
    }
    const csv = [header, ...lines].map((row) => row.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `billing_${reportKind}_${reportFrom}_to_${reportTo}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const openConsolidateDialog = () => {
    setConsolidatePatient(null);
    setConsolidatePreview(null);
    setConsolidatePicked({ consultations: new Set(), labs: new Set() });
    setConsolidateOpen(true);
  };

  const selectConsolidatePatient = async (p) => {
    setConsolidatePatient(p);
    try {
      const res = await axios.get(`/api/hospital/billing/consolidate/preview?patient_id=${p.id}`);
      setConsolidatePreview(res.data);
      // Pre-select everything
      setConsolidatePicked({
        consultations: new Set(res.data.consultations.map((c) => c.id)),
        labs: new Set(res.data.lab_orders.map((l) => l.id)),
      });
    } catch (err) {
      const detail = err.response?.data?.detail;
      alert(typeof detail === 'string' ? detail : 'Failed to load patient charges');
    }
  };

  const togglePicked = (kind, id) => {
    const next = new Set(consolidatePicked[kind]);
    if (next.has(id)) next.delete(id); else next.add(id);
    setConsolidatePicked({ ...consolidatePicked, [kind]: next });
  };

  const consolidateSelectedTotal = () => {
    if (!consolidatePreview) return 0;
    const c = consolidatePreview.consultations.filter((x) => consolidatePicked.consultations.has(x.id))
      .reduce((s, x) => s + x.total, 0);
    const l = consolidatePreview.lab_orders.filter((x) => consolidatePicked.labs.has(x.id))
      .reduce((s, x) => s + x.cost, 0);
    return c + l;
  };

  const submitConsolidate = async () => {
    if (!consolidatePatient) return;
    const consultation_ids = [...consolidatePicked.consultations];
    const lab_order_ids = [...consolidatePicked.labs];
    if (!consultation_ids.length && !lab_order_ids.length) {
      alert('Pick at least one item to consolidate.');
      return;
    }
    setConsolidateSaving(true);
    try {
      const r = await axios.post('/api/hospital/billing/consolidate', {
        patient_id: consolidatePatient.id, consultation_ids, lab_order_ids,
      });
      setConsolidateOpen(false);
      fetchBills();
      if (r.data?.bill_id) {
        await openBillDetail({
          type: 'consolidated',
          bill_id: r.data.bill_id,
          patient_name: `${consolidatePatient.first_name} ${consolidatePatient.last_name}`,
        });
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      alert(typeof detail === 'string' ? detail : 'Consolidate failed');
    } finally {
      setConsolidateSaving(false);
    }
  };

  const openCreditNoteDialog = () => {
    setCreditNoteForm({
      items: [{ item_name: '', quantity: 1, unit_price: '' }],
      reason: '',
    });
    setCreditNoteOpen(true);
  };

  const submitCreditNote = async () => {
    if (!detailBill) return;
    const items = creditNoteForm.items
      .map((it) => ({ item_name: it.item_name.trim(), quantity: Number(it.quantity) || 0, unit_price: parseFloat(it.unit_price) }))
      .filter((it) => it.item_name && it.quantity > 0 && it.unit_price > 0);
    if (!items.length || !creditNoteForm.reason.trim() || creditNoteForm.reason.trim().length < 2) return;
    setCreditNoteSaving(true);
    try {
      const r = await axios.post(`/api/hospital/billing/bills/${detailBill.bill_id}/credit-note`, {
        items, reason: creditNoteForm.reason.trim(),
      });
      setCreditNoteOpen(false);
      const res = await axios.get(`/api/hospital/billing/bills/${detailBill.bill_id}`);
      setDetailData(res.data);
      fetchBills();
      if (r.data?.credit_note_id && window.confirm('Credit note issued. Open PDF?')) {
        printPdfFromUrl(`/api/hospital/billing/bills/${r.data.credit_note_id}/credit-note/pdf`);
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      alert(typeof detail === 'string' ? detail : 'Credit note failed');
    } finally {
      setCreditNoteSaving(false);
    }
  };

  const openPaymentDialog = (bill) => {
    setPayBill(bill);
    setPaymentForm({
      amount_paid: String(bill.balance_due || bill.amount || ''),
      payment_method: 'cash',
      transaction_reference: '',
      notes: '',
    });
  };

  const handleRecordPayment = async () => {
    if (!payBill || !paymentForm.amount_paid) return;
    setPaymentLoading(true);
    try {
      await axios.post(`/api/hospital/billing/bills/${payBill.bill_id}/payment`, {
        amount_paid: parseFloat(paymentForm.amount_paid),
        payment_method: paymentForm.payment_method,
        transaction_reference: paymentForm.transaction_reference || undefined,
        notes: paymentForm.notes || undefined,
      });
      setPayBill(null);
      fetchBills();
    } catch (err) {
      const detail = err.response?.data?.detail;
      alert(typeof detail === 'string' ? detail : 'Payment failed');
    } finally {
      setPaymentLoading(false);
    }
  };

  const downloadCSV = () => {
    const headers = ['Date', 'Type', 'Reference', 'Patient', 'Phone', 'Items', 'Amount', 'Discount', 'Final', 'Doctor', 'Referred By', 'Status', 'Payment Method'];
    const rows = bills.map(b => [
      formatDate(b.date), b.type, b.reference, b.patient_name, b.patient_phone,
      b.items, b.subtotal, b.discount, b.amount, b.doctor_name, b.referred_by, b.payment_status, b.payment_method
    ]);
    const csv = [headers.join(','), ...rows.map(r => r.map(v => `"${v}"`).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `billing_${dateFrom}_to_${dateTo}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadExcel = async () => {
    setExporting(true);
    try {
      const res = await axios.get(`/api/hospital/billing/export.xlsx?${buildBillingParams().toString()}`, {
        responseType: 'blob',
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `billing_${dateFrom}_to_${dateTo}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Excel export failed:', err);
      alert('Could not export Excel report');
    } finally {
      setExporting(false);
    }
  };

  const applyPeriodPreset = (preset) => {
    const now = new Date();
    if (preset === 'today') {
      const t = localDateString(now);
      setDateFrom(t);
      setDateTo(t);
    } else if (preset === 'week') {
      setDateFrom(localWeekStart(now));
      setDateTo(localDateString(now));
    } else if (preset === 'month') {
      setDateFrom(localMonthStart(now));
      setDateTo(localDateString(now));
    } else if (preset === 'last_month') {
      const { from, to } = localLastMonthRange(now);
      setDateFrom(from);
      setDateTo(to);
    }
  };

  const resetFilters = () => {
    setDateFrom(weekAgo); setDateTo(today); setPatientSearch('');
    setPaymentStatus('all'); setDoctorFilter('all'); setReferralFilter('all');
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Billing Management</h1>
          <p className="text-muted-foreground text-sm">Manage outpatient, lab, and inpatient bills</p>
        </div>
        <div className="flex gap-2">
          <Button onClick={openConsolidateDialog} variant="outline">
            <FileText className="h-4 w-4 mr-1" /> Consolidate Bills
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" disabled={exporting}>
                {exporting ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Download className="h-4 w-4 mr-1" />}
                Export
                <ChevronDown className="h-3.5 w-3.5 ml-1 opacity-70" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => { downloadExcel(); }} disabled={exporting}>
                Export Excel (.xlsx)
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={downloadCSV} disabled={bills.length === 0}>
                Export CSV
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Card>
            <CardContent className="pt-5 pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-500">Total Billed</p>
                  <p className="text-xl font-bold">{formatCurrency(summary.total_billed)}</p>
                </div>
                <DollarSign className="h-8 w-8 text-blue-500" />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-5 pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-500">Collected</p>
                  <p className="text-xl font-bold text-green-600">{formatCurrency(summary.total_paid)}</p>
                </div>
                <CheckCircle2 className="h-8 w-8 text-green-500" />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-5 pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-500">Pending</p>
                  <p className="text-xl font-bold text-orange-600">{formatCurrency(summary.total_pending)}</p>
                </div>
                <Clock className="h-8 w-8 text-orange-500" />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-5 pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-500">Total Bills</p>
                  <p className="text-xl font-bold">{summary.total_bills}</p>
                  <p className="text-[10px] text-gray-400">
                    {summary.appointment_count} consult + {summary.lab_count} lab
                    {summary.admission_count > 0 && ` + ${summary.admission_count} admission`}
                  </p>
                </div>
                <Receipt className="h-8 w-8 text-purple-500" />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-5 pb-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs text-gray-500">Cancelled</p>
                  <p className="text-xl font-bold text-red-600">{summary.cancelled_count}</p>
                </div>
                <XCircle className="h-8 w-8 text-red-400" />
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Tabs + Filters */}
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="all">All Bills</TabsTrigger>
          <TabsTrigger value="outpatient">
            <Stethoscope className="h-3.5 w-3.5 mr-1" /> Outpatient
          </TabsTrigger>
          <TabsTrigger value="lab">
            <FlaskConical className="h-3.5 w-3.5 mr-1" /> Lab
          </TabsTrigger>
          <TabsTrigger value="inpatient">
            <BedDouble className="h-3.5 w-3.5 mr-1" /> Inpatient
          </TabsTrigger>
          <TabsTrigger value="reports">
            <TrendingUp className="h-3.5 w-3.5 mr-1" /> Reports
          </TabsTrigger>
        </TabsList>

        {/* Filters - shared across all tabs (hidden on Reports) */}
        {activeTab !== 'reports' && (
        <Card className="mt-4">
          <CardContent className="pt-4 pb-3">
            <div className="flex flex-wrap gap-3 items-end">
              <div>
                <Label className="text-xs">From</Label>
                <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-[150px] h-9" />
              </div>
              <div>
                <Label className="text-xs">To</Label>
                <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-[150px] h-9" />
              </div>
              <div>
                <Label className="text-xs">Quick range</Label>
                <div className="flex flex-wrap gap-1">
                  {[
                    { id: 'today', label: 'Today' },
                    { id: 'week', label: 'This week' },
                    { id: 'month', label: 'This month' },
                    { id: 'last_month', label: 'Last month' },
                  ].map((p) => (
                    <Button
                      key={p.id}
                      type="button"
                      size="sm"
                      variant="outline"
                      className="h-9 px-2.5 text-xs"
                      onClick={() => applyPeriodPreset(p.id)}
                    >
                      {p.label}
                    </Button>
                  ))}
                </div>
              </div>
              <div>
                <Label className="text-xs">Patient</Label>
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
                  <Input placeholder="Name or phone" value={patientSearch}
                    onChange={(e) => setPatientSearch(e.target.value)} className="pl-8 w-[180px] h-9" />
                </div>
              </div>
              <div>
                <Label className="text-xs">Status</Label>
                <Select value={paymentStatus} onValueChange={setPaymentStatus}>
                  <SelectTrigger className="w-[120px] h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    <SelectItem value="paid">Paid</SelectItem>
                    <SelectItem value="pending">Pending</SelectItem>
                    <SelectItem value="partial">Partial</SelectItem>
                    <SelectItem value="cancelled">Cancelled</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Doctor</Label>
                <Select value={doctorFilter} onValueChange={setDoctorFilter}>
                  <SelectTrigger className="w-[160px] h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Doctors</SelectItem>
                    {doctors.map(d => (
                      <SelectItem key={d.id} value={String(d.id)}>{d.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Referred By</Label>
                <Select value={referralFilter} onValueChange={setReferralFilter}>
                  <SelectTrigger className="w-[160px] h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Referrals</SelectItem>
                    {referrals.map(r => (
                      <SelectItem key={r.id} value={r.name}>{r.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <Button size="sm" variant="outline" className="h-9" onClick={resetFilters}>
                Reset
              </Button>
            </div>
          </CardContent>
        </Card>
        )}

        {/* Reports Tab */}
        <TabsContent value="reports" className="mt-4 space-y-4">
          <Card>
            <CardContent className="pt-4 pb-3 flex flex-wrap gap-3 items-end">
              <div>
                <Label className="text-xs">Report</Label>
                <Select value={reportKind} onValueChange={setReportKind}>
                  <SelectTrigger className="w-[220px] h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="daily-collection">Daily Collection</SelectItem>
                    <SelectItem value="doctor-revenue">Doctor-wise Revenue</SelectItem>
                    <SelectItem value="tax-summary">GST / Tax Summary</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">From</Label>
                <Input type="date" value={reportFrom} onChange={(e) => setReportFrom(e.target.value)} className="w-[150px] h-9" />
              </div>
              <div>
                <Label className="text-xs">To</Label>
                <Input type="date" value={reportTo} onChange={(e) => setReportTo(e.target.value)} className="w-[150px] h-9" />
              </div>
              <Button variant="outline" onClick={fetchReport} disabled={reportLoading}>
                {reportLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Run'}
              </Button>
              <Button variant="outline" onClick={exportReportCSV} disabled={!reportData?.rows?.length}>
                <Download className="h-4 w-4 mr-1" /> CSV
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="pt-4">
              {reportLoading ? (
                <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>
              ) : !reportData?.rows?.length ? (
                <div className="text-center py-12 text-gray-500">No data for the selected range.</div>
              ) : reportKind === 'daily-collection' ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="border-b text-left text-gray-500">
                      <th className="pb-2 pr-3">Date</th>
                      <th className="pb-2 pr-3 text-right">Net total</th>
                      <th className="pb-2 pr-3 text-right">Refunds</th>
                      {reportData.methods.map((m) => (
                        <th key={m} className="pb-2 pr-3 text-right capitalize">{m}</th>
                      ))}
                    </tr></thead>
                    <tbody>
                      {reportData.rows.map((r) => (
                        <tr key={r.date} className="border-b">
                          <td className="py-2 pr-3">{r.date}</td>
                          <td className="py-2 pr-3 text-right font-semibold">{formatCurrency(r.total)}</td>
                          <td className="py-2 pr-3 text-right text-red-600">{r.refunds > 0 ? `-${formatCurrency(r.refunds)}` : '—'}</td>
                          {reportData.methods.map((m) => (
                            <td key={m} className="py-2 pr-3 text-right">{r.by_method?.[m] ? formatCurrency(r.by_method[m]) : '—'}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                    <tfoot><tr className="border-t font-semibold">
                      <td className="py-2">Total</td>
                      <td className="py-2 text-right">{formatCurrency(reportData.totals.net_collected)}</td>
                      <td className="py-2 text-right text-red-600">-{formatCurrency(reportData.totals.refunds)}</td>
                      <td className="py-2 pr-3 text-right text-xs text-gray-500" colSpan={reportData.methods.length}>
                        Gross: {formatCurrency(reportData.totals.gross_collected)}
                      </td>
                    </tr></tfoot>
                  </table>
                </div>
              ) : reportKind === 'doctor-revenue' ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="border-b text-left text-gray-500">
                      <th className="pb-2 pr-3">Doctor</th>
                      <th className="pb-2 pr-3 text-right">Consults</th>
                      <th className="pb-2 pr-3 text-right">Consult ₹</th>
                      <th className="pb-2 pr-3 text-right">Admissions</th>
                      <th className="pb-2 pr-3 text-right">Admission ₹</th>
                      <th className="pb-2 pr-3 text-right">Total ₹</th>
                    </tr></thead>
                    <tbody>
                      {reportData.rows.map((r) => (
                        <tr key={r.doctor_id} className="border-b">
                          <td className="py-2 pr-3">{r.doctor_name}</td>
                          <td className="py-2 pr-3 text-right">{r.consultation_count}</td>
                          <td className="py-2 pr-3 text-right">{formatCurrency(r.consultation_revenue)}</td>
                          <td className="py-2 pr-3 text-right">{r.admission_count}</td>
                          <td className="py-2 pr-3 text-right">{formatCurrency(r.admission_revenue)}</td>
                          <td className="py-2 pr-3 text-right font-semibold">{formatCurrency(r.total_revenue)}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot><tr className="border-t font-semibold">
                      <td className="py-2">Total</td>
                      <td colSpan={2} className="py-2 text-right">{formatCurrency(reportData.totals.consultation_total)}</td>
                      <td colSpan={2} className="py-2 text-right">{formatCurrency(reportData.totals.admission_total)}</td>
                      <td className="py-2 text-right">{formatCurrency(reportData.totals.grand_total)}</td>
                    </tr></tfoot>
                  </table>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="border-b text-left text-gray-500">
                      <th className="pb-2 pr-3">Date</th>
                      <th className="pb-2 pr-3 text-right">Bills</th>
                      <th className="pb-2 pr-3 text-right">Taxable value</th>
                      <th className="pb-2 pr-3 text-right">Tax amount</th>
                    </tr></thead>
                    <tbody>
                      {reportData.rows.map((r) => (
                        <tr key={r.date} className="border-b">
                          <td className="py-2 pr-3">{r.date}</td>
                          <td className="py-2 pr-3 text-right">{r.bill_count}</td>
                          <td className="py-2 pr-3 text-right">{formatCurrency(r.taxable_value)}</td>
                          <td className="py-2 pr-3 text-right font-semibold">{formatCurrency(r.tax_amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot><tr className="border-t font-semibold">
                      <td className="py-2">Total</td>
                      <td className="py-2 text-right">{reportData.totals.bill_count}</td>
                      <td className="py-2 text-right">{formatCurrency(reportData.totals.taxable_value)}</td>
                      <td className="py-2 text-right">{formatCurrency(reportData.totals.tax_amount)}</td>
                    </tr></tfoot>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Bills Table - same content for all tabs, filtered by activeTab */}
        {['all', 'outpatient', 'lab', 'inpatient'].map(tab => (
          <TabsContent key={tab} value={tab} className="mt-4">
            <Card>
              <CardContent className="pt-4">
                {loading ? (
                  <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>
                ) : bills.length === 0 ? (
                  <div className="text-center py-12 text-gray-500">
                    <Receipt className="h-10 w-10 mx-auto mb-2 text-gray-300" />
                    <p>No bills found for the selected filters.</p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-gray-500">
                          <th className="pb-2 pr-3">Date</th>
                          <th className="pb-2 pr-3">Type</th>
                          <th className="pb-2 pr-3">Reference</th>
                          <th className="pb-2 pr-3">Patient</th>
                          <th className="pb-2 pr-3">Items</th>
                          <th className="pb-2 pr-3 text-right">Amount</th>
                          <th className="pb-2 pr-3">Doctor</th>
                          <th className="pb-2 pr-3">Status</th>
                          <th className="pb-2">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {bills.map((bill) => (
                          <tr key={bill.id} className={`border-b hover:bg-gray-50 ${bill.payment_status === 'cancelled' ? 'opacity-60' : ''}`}>
                            <td className="py-2.5 pr-3 text-xs">{formatDate(bill.date)}</td>
                            <td className="py-2.5 pr-3">
                              <Badge variant="outline" className={`text-[10px] capitalize gap-1 ${getTypeColor(bill.type)}`}>
                                {getTypeIcon(bill.type)} {bill.type}
                              </Badge>
                            </td>
                            <td className="py-2.5 pr-3 text-xs font-mono text-gray-500">{bill.reference}</td>
                            <td className="py-2.5 pr-3">
                              <div>
                                <p className="font-medium text-sm">{bill.patient_name}</p>
                                <p className="text-[10px] text-gray-400">{bill.patient_phone}</p>
                              </div>
                            </td>
                            <td className="py-2.5 pr-3 text-xs text-gray-600 max-w-[200px] truncate">{bill.items}</td>
                            <td className="py-2.5 pr-3 text-right">
                              <p className="font-semibold">{formatCurrency(bill.amount)}</p>
                              {bill.discount > 0 && <p className="text-[10px] text-green-600">-{formatCurrency(bill.discount)} disc.</p>}
                              {bill.type === 'admission' && bill.amount_paid > 0 && bill.payment_status !== 'paid' && (
                                <p className="text-[10px] text-blue-600">Paid: {formatCurrency(bill.amount_paid)}</p>
                              )}
                            </td>
                            <td className="py-2.5 pr-3 text-xs text-gray-600">{bill.doctor_name || '-'}</td>
                            <td className="py-2.5 pr-3">
                              <Badge className={`text-[10px] ${getStatusBadge(bill.payment_status)}`}>
                                {bill.payment_status}
                              </Badge>
                              {bill.cancel_reason && (
                                <p className="text-[9px] text-red-500 mt-0.5 max-w-[120px] truncate" title={bill.cancel_reason}>
                                  {bill.cancel_reason}
                                </p>
                              )}
                            </td>
                            <td className="py-2.5">
                              <div className="flex gap-1">
                                {(bill.type === 'admission' || bill.type === 'consolidated' || bill.type === 'day_care' || getBillPdfPath(bill)) && (
                                  <Button size="sm" variant="ghost" className="h-6 text-[10px] px-2"
                                    onClick={() => handleViewBill(bill)}>
                                    <Eye className="w-3 h-3 mr-0.5" /> View
                                  </Button>
                                )}
                                {/* Collect payment for admission bills with balance */}
                                {bill.type === 'admission' && bill.payment_status !== 'cancelled' && bill.payment_status !== 'paid' && (
                                  <Button size="sm" variant="ghost" className="h-6 text-[10px] text-green-600 hover:text-green-700 hover:bg-green-50 px-2"
                                    onClick={() => openPaymentDialog(bill)}>
                                    <CreditCard className="w-3 h-3 mr-0.5" /> Pay
                                  </Button>
                                )}
                                {getBillPdfPath(bill) && (
                                  <Button size="sm" variant="ghost" className="h-6 text-[10px] px-2"
                                    onClick={() => handlePrintBill(bill)}
                                    title="Print bill">
                                    <Printer className="w-3 h-3" />
                                  </Button>
                                )}
                                {/* Cancel: admission allowed any non-cancelled state (backend blocks if paid);
                                    consultation/lab keep prior guard */}
                                {bill.payment_status !== 'cancelled' && (
                                  bill.type === 'admission'
                                    ? bill.admission_id
                                    : bill.payment_status !== 'pending'
                                ) && (
                                  <Button size="sm" variant="ghost" className="h-6 text-[10px] text-red-500 hover:text-red-700 hover:bg-red-50 px-2"
                                    onClick={() => { setCancelBill(bill); setCancelReason(''); }}>
                                    <Ban className="w-3 h-3" />
                                  </Button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        ))}
      </Tabs>

      {/* Bill Detail Dialog (Admission) */}
      <Dialog open={!!detailBill} onOpenChange={(open) => { if (!open) { setDetailBill(null); setDetailData(null); } }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-teal-600" />
              {detailBill?.type === 'admission' ? 'Admission Bill Detail' : 'Bill Detail'}
            </DialogTitle>
          </DialogHeader>
          {detailLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin" /></div>
          ) : detailData ? (
            <div className="space-y-4">
              {/* Bill info */}
              <div className="grid grid-cols-2 gap-3 bg-gray-50 rounded-lg p-4">
                <div>
                  <p className="text-xs text-gray-500">Bill Number</p>
                  <p className="font-mono text-sm">{detailData.bill_number}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Patient</p>
                  <p className="text-sm font-medium">{detailData.patient_name}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Date</p>
                  <p className="text-sm">{formatDate(detailData.bill_date)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Status</p>
                  <Badge className={getStatusBadge(detailData.status)}>{detailData.status}</Badge>
                </div>
              </div>

              {/* Items */}
              <div>
                <Label className="text-sm font-medium text-gray-500 mb-2 block">Bill Items</Label>
                <div className="border rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left p-2.5">Item</th>
                        <th className="text-center p-2.5">Qty</th>
                        <th className="text-right p-2.5">Rate</th>
                        <th className="text-right p-2.5">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {detailData.items.map((item, i) => (
                        <tr key={i} className="border-t">
                          <td className="p-2.5">
                            <p className="font-medium">{item.item_name}</p>
                            <p className="text-[10px] text-gray-400">{item.item_type}</p>
                          </td>
                          <td className="text-center p-2.5">{item.quantity}</td>
                          <td className="text-right p-2.5">{formatCurrency(item.unit_price)}</td>
                          <td className="text-right p-2.5 font-medium">{formatCurrency(item.total_price)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Totals */}
              <div className="bg-gray-50 rounded-lg p-4 space-y-1.5">
                <div className="flex justify-between text-sm">
                  <span>Subtotal:</span>
                  <span>{formatCurrency(detailData.subtotal)}</span>
                </div>
                {detailData.discount_amount > 0 && (
                  <div className="flex justify-between text-sm text-green-600">
                    <span>Discount:</span>
                    <span>-{formatCurrency(detailData.discount_amount)}</span>
                  </div>
                )}
                {detailData.tax_amount > 0 && (
                  <div className="flex justify-between text-sm">
                    <span>Tax:</span>
                    <span>{formatCurrency(detailData.tax_amount)}</span>
                  </div>
                )}
                <div className="flex justify-between text-base font-bold border-t pt-2">
                  <span>Total:</span>
                  <span>{formatCurrency(detailData.total_amount)}</span>
                </div>
                {detailData.amount_paid > 0 && (
                  <div className="flex justify-between text-sm text-green-600">
                    <span>Paid:</span>
                    <span>{formatCurrency(detailData.amount_paid)}</span>
                  </div>
                )}
                {detailData.balance_due > 0 && (
                  <div className="flex justify-between text-sm text-red-600 font-medium">
                    <span>Balance Due:</span>
                    <span>{formatCurrency(detailData.balance_due)}</span>
                  </div>
                )}
              </div>

              {/* Payment History */}
              {detailData.payments && detailData.payments.length > 0 && (
                <div>
                  <Label className="text-sm font-medium text-gray-500 mb-2 block">Payment History</Label>
                  <div className="space-y-2">
                    {detailData.payments.map((p, i) => (
                      <div key={i} className={`flex items-center justify-between rounded p-2.5 text-sm ${p.is_refund ? 'bg-red-50' : 'bg-green-50'}`}>
                        <div className="flex-1">
                          <span className="font-mono text-xs text-gray-500">{p.payment_number}</span>
                          <span className="ml-2 text-xs capitalize">{p.payment_method_name}</span>
                          {p.is_refund && <span className="ml-2 text-[10px] font-semibold text-red-600 uppercase">Refund</span>}
                          {p.reversed_at && !p.is_refund && <span className="ml-2 text-[10px] font-semibold text-orange-600 uppercase">Reversed</span>}
                          {p.transaction_reference && (
                            <span className="ml-2 text-xs text-gray-400">Ref: {p.transaction_reference}</span>
                          )}
                        </div>
                        <div className="text-right flex items-center gap-2">
                          <div>
                            <span className={`font-semibold ${p.is_refund ? 'text-red-700' : 'text-green-700'}`}>
                              {p.is_refund ? '-' : ''}{formatCurrency(Math.abs(p.amount_paid))}
                            </span>
                            <span className="ml-2 text-xs text-gray-400">{formatDate(p.payment_date)}</span>
                          </div>
                          {!p.is_refund && !p.reversed_at && detailData.status !== 'cancelled' && (
                            <Button size="sm" variant="ghost" className="h-6 text-[10px] text-orange-600 hover:bg-orange-100 px-2"
                              onClick={() => openRefundDialog(p)}>
                              Refund
                            </Button>
                          )}
                          {p.is_refund && (
                            <Button size="sm" variant="ghost" className="h-6 text-[10px] px-2"
                              onClick={() => printPdfFromUrl(`/api/hospital/billing/payments/${p.id}/refund-receipt/pdf`)}>
                              PDF
                            </Button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Bill Splits (admission only) */}
              {detailBill?.type === 'admission' && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <Label className="text-sm font-medium text-gray-500">Bill Splits</Label>
                    {detailData.status !== 'cancelled' && (
                      <Button size="sm" variant="outline" className="h-7 text-xs" onClick={openSplitEditor}>
                        {splits.length ? 'Edit Splits' : 'Add Splits'}
                      </Button>
                    )}
                  </div>
                  {splits.length === 0 ? (
                    <p className="text-xs text-gray-400">No splits configured. Bill is treated as a single payer.</p>
                  ) : (
                    <div className="space-y-2">
                      {splits.map((s) => (
                        <div key={s.id} className="flex items-center justify-between bg-blue-50 rounded p-2.5 text-sm">
                          <div className="flex-1">
                            <span className="text-xs uppercase font-semibold text-blue-700 mr-2">{s.payer_type}</span>
                            <span>{s.payer_name}</span>
                            {s.tpa_name && <span className="ml-2 text-xs text-gray-500">({s.tpa_name})</span>}
                            {s.payment_reference && <span className="ml-2 text-[10px] text-gray-500">Ref: {s.payment_reference}</span>}
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge variant={s.payment_status === 'received' ? 'default' : 'outline'}
                              className={s.payment_status === 'received' ? 'bg-green-100 text-green-700' : 'border-orange-300 text-orange-700'}>
                              {s.payment_status}
                            </Badge>
                            <span className="font-semibold text-gray-700">{formatCurrency(s.amount)}</span>
                            {s.payment_status !== 'received' && detailData.status !== 'cancelled' && (
                              <Button size="sm" variant="ghost" className="h-6 text-[10px] text-green-700 hover:bg-green-100 px-2"
                                onClick={() => markSplitReceived(s)}>
                                Mark Received
                              </Button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Actions */}
              <div className="flex justify-end gap-2 pt-2 border-t flex-wrap">
                {detailData.status !== 'cancelled' && detailData.amount_paid === 0 && (
                  <>
                    <Button variant="outline" size="sm" onClick={() => openAdjustDialog('discount')}>
                      Apply Discount
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => openAdjustDialog('tax')}>
                      Apply Tax
                    </Button>
                  </>
                )}
                {detailData.status !== 'cancelled' && detailData.balance_due > 0 && (
                  <Button variant="outline" size="sm" className="text-red-700 border-red-300 hover:bg-red-50"
                    onClick={openCreditNoteDialog}>
                    Issue Credit Note
                  </Button>
                )}
                {getBillPdfPath(detailBill) && (
                  <Button variant="outline" onClick={() => handlePrintBill(detailBill)}>
                    <Printer className="h-4 w-4 mr-1" /> Print Bill
                  </Button>
                )}
                {detailData.balance_due > 0 && (
                  <Button onClick={() => { setDetailBill(null); setDetailData(null); openPaymentDialog({ ...detailBill, balance_due: detailData.balance_due }); }}>
                    <CreditCard className="h-4 w-4 mr-1" /> Collect Payment
                  </Button>
                )}
              </div>
            </div>
          ) : detailBill && detailBill.type !== 'admission' ? (
            /* Simple summary for consultation/lab bills */
            <div className="space-y-4">
              <div className="bg-gray-50 rounded-lg p-4 space-y-2">
                <div className="flex justify-between"><span className="text-gray-500">Reference:</span><span className="font-mono">{detailBill.reference}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Patient:</span><span>{detailBill.patient_name}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Type:</span><Badge variant="outline" className={`capitalize ${getTypeColor(detailBill.type)}`}>{detailBill.type}</Badge></div>
                <div className="flex justify-between"><span className="text-gray-500">Items:</span><span>{detailBill.items}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Doctor:</span><span>{detailBill.doctor_name || '-'}</span></div>
                <div className="flex justify-between text-lg font-bold border-t pt-2"><span>Amount:</span><span>{formatCurrency(detailBill.amount)}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Status:</span><Badge className={getStatusBadge(detailBill.payment_status)}>{detailBill.payment_status}</Badge></div>
              </div>
              {getBillPdfPath(detailBill) && (
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => setPdfPreview({
                    title: `Bill — ${detailBill.reference || detailBill.patient_name}`,
                    path: getBillPdfPath(detailBill),
                  })}>
                    <Eye className="h-4 w-4 mr-1" /> View PDF
                  </Button>
                  <Button onClick={() => handlePrintBill(detailBill)}>
                    <Printer className="h-4 w-4 mr-1" /> Print Bill
                  </Button>
                </div>
              )}
            </div>
          ) : (
            <p className="text-center py-4 text-gray-500">No detail available</p>
          )}
        </DialogContent>
      </Dialog>

      {/* Payment Dialog */}
      <Dialog open={!!payBill} onOpenChange={(open) => { if (!open) setPayBill(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CreditCard className="h-5 w-5 text-green-600" /> Collect Payment
            </DialogTitle>
          </DialogHeader>
          {payBill && (
            <div className="space-y-4">
              <div className="bg-blue-50 rounded-lg p-3">
                <p className="text-sm font-medium">{payBill.patient_name}</p>
                <p className="text-xs text-gray-500">{payBill.reference} - {payBill.items}</p>
                <p className="text-sm mt-1">
                  <span className="text-gray-500">Balance Due: </span>
                  <span className="text-lg font-bold text-red-600">{formatCurrency(payBill.balance_due || payBill.amount)}</span>
                </p>
              </div>
              <div>
                <Label>Amount</Label>
                <Input type="number" value={paymentForm.amount_paid}
                  onChange={(e) => setPaymentForm({...paymentForm, amount_paid: e.target.value})}
                  placeholder="Enter amount" />
              </div>
              <div>
                <Label>Payment Method</Label>
                <Select value={paymentForm.payment_method}
                  onValueChange={(v) => setPaymentForm({...paymentForm, payment_method: v})}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="card">Card</SelectItem>
                    <SelectItem value="upi">UPI</SelectItem>
                    <SelectItem value="online">Online</SelectItem>
                    <SelectItem value="insurance">Insurance</SelectItem>
                    <SelectItem value="cheque">Cheque</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {['card', 'upi', 'online'].includes(paymentForm.payment_method) && (
                <div>
                  <Label>Transaction Reference</Label>
                  <Input value={paymentForm.transaction_reference}
                    onChange={(e) => setPaymentForm({...paymentForm, transaction_reference: e.target.value})}
                    placeholder="Transaction ID" />
                </div>
              )}
              <div>
                <Label>Notes (Optional)</Label>
                <Textarea rows={2} value={paymentForm.notes}
                  onChange={(e) => setPaymentForm({...paymentForm, notes: e.target.value})}
                  placeholder="Payment notes..." />
              </div>
              <div className="flex justify-end gap-2 pt-2 border-t">
                <Button variant="outline" onClick={() => setPayBill(null)}>Cancel</Button>
                <Button onClick={handleRecordPayment}
                  disabled={paymentLoading || !paymentForm.amount_paid}>
                  {paymentLoading ? 'Processing...' : `Pay ${formatCurrency(paymentForm.amount_paid || 0)}`}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Cancel Bill Dialog */}
      <Dialog open={!!cancelBill} onOpenChange={(open) => { if (!open) setCancelBill(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Ban className="h-5 w-5 text-red-500" /> Cancel Bill
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {cancelBill && (
              <div className="bg-gray-50 rounded-lg p-3 space-y-1">
                <p className="text-sm font-semibold">{cancelBill.patient_name}</p>
                <p className="text-xs text-gray-500">{cancelBill.reference} - {cancelBill.items}</p>
                <p className="text-sm font-semibold text-green-600">{formatCurrency(cancelBill.amount)}</p>
              </div>
            )}
            <div>
              <Label>Reason for cancellation *</Label>
              <Textarea value={cancelReason} onChange={(e) => setCancelReason(e.target.value)}
                placeholder="e.g. Duplicate bill, Patient refund, Wrong entry..." rows={3} />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button variant="outline" onClick={() => setCancelBill(null)}>Close</Button>
              <Button variant="destructive" disabled={cancelling || !cancelReason.trim()} onClick={handleCancelBill}>
                {cancelling ? 'Cancelling...' : 'Cancel Bill'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Consolidate Bills Dialog */}
      <Dialog open={consolidateOpen} onOpenChange={(open) => { if (!open) setConsolidateOpen(false); }}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Consolidate Patient Bills</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {/* Patient search */}
            <PatientSearchPicker
              value={consolidatePatient}
              onChange={(p) => {
                if (!p) {
                  setConsolidatePatient(null);
                  setConsolidatePreview(null);
                  return;
                }
                selectConsolidatePatient(p);
              }}
              label="Patient"
              compact
            />

            {/* Preview lists */}
            {consolidatePreview && (
              <>
                <div>
                  <Label className="text-xs">Consultations ({consolidatePreview.consultations.length})</Label>
                  {consolidatePreview.consultations.length === 0 ? (
                    <p className="text-xs text-gray-400">No pending consultations.</p>
                  ) : (
                    <div className="space-y-1 max-h-40 overflow-auto">
                      {consolidatePreview.consultations.map((c) => (
                        <label key={c.id} className="flex items-center gap-2 text-sm border rounded p-2 cursor-pointer hover:bg-gray-50">
                          <input type="checkbox" checked={consolidatePicked.consultations.has(c.id)}
                            onChange={() => togglePicked('consultations', c.id)} />
                          <span className="flex-1">
                            <span className="font-mono text-xs text-gray-500">{c.appointment_number}</span>
                            <span className="ml-2 text-xs text-gray-400">{c.date ? new Date(c.date).toLocaleDateString() : ''}</span>
                            <Badge variant="outline" className="ml-2 text-[9px]">{c.payment_status}</Badge>
                          </span>
                          <span className="font-semibold">{formatCurrency(c.total)}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <Label className="text-xs">Lab Orders ({consolidatePreview.lab_orders.length})</Label>
                  {consolidatePreview.lab_orders.length === 0 ? (
                    <p className="text-xs text-gray-400">No pending lab orders.</p>
                  ) : (
                    <div className="space-y-1 max-h-40 overflow-auto">
                      {consolidatePreview.lab_orders.map((l) => (
                        <label key={l.id} className="flex items-center gap-2 text-sm border rounded p-2 cursor-pointer hover:bg-gray-50">
                          <input type="checkbox" checked={consolidatePicked.labs.has(l.id)}
                            onChange={() => togglePicked('labs', l.id)} />
                          <span className="flex-1">
                            <span className="font-mono text-xs text-gray-500">{l.order_number}</span>
                            <span className="ml-2">{l.test_name}</span>
                            <Badge variant="outline" className="ml-2 text-[9px]">{l.payment_status}</Badge>
                          </span>
                          <span className="font-semibold">{formatCurrency(l.cost)}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
                <div className="bg-gray-50 rounded p-3 text-right text-sm">
                  Total to bill: <span className="font-bold text-lg ml-2">{formatCurrency(consolidateSelectedTotal())}</span>
                </div>
              </>
            )}

            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button variant="outline" onClick={() => setConsolidateOpen(false)}>Cancel</Button>
              <Button disabled={consolidateSaving || !consolidatePreview || consolidateSelectedTotal() <= 0}
                onClick={submitConsolidate}>
                {consolidateSaving ? 'Creating...' : 'Create Consolidated Bill'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Bill Split Editor */}
      <Dialog open={splitEditOpen} onOpenChange={(open) => { if (!open) setSplitEditOpen(false); }}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>Configure Bill Splits</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            {detailData && (
              <div className="bg-gray-50 rounded p-3 text-sm flex items-center justify-between">
                <span className="text-gray-500">Bill total to allocate:</span>
                <span className="font-bold">{formatCurrency(detailData.total_amount)}</span>
              </div>
            )}
            <div className="space-y-2">
              {splitForm.map((row, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-2 items-center">
                  <Select value={row.payer_type} onValueChange={(v) => {
                    const next = [...splitForm];
                    next[idx] = { ...next[idx], payer_type: v };
                    if (v !== 'tpa') next[idx].tpa_id = '';
                    if (v === 'cash' && !next[idx].payer_name) next[idx].payer_name = 'Cash';
                    setSplitForm(next);
                  }}>
                    <SelectTrigger className="col-span-2 h-9 text-xs"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cash">Cash</SelectItem>
                      <SelectItem value="insurance">Insurance</SelectItem>
                      <SelectItem value="tpa">TPA</SelectItem>
                    </SelectContent>
                  </Select>
                  <Input className="col-span-4 h-9 text-xs" placeholder="Payer name" value={row.payer_name}
                    onChange={(e) => {
                      const next = [...splitForm];
                      next[idx] = { ...next[idx], payer_name: e.target.value };
                      setSplitForm(next);
                    }} />
                  {row.payer_type === 'tpa' ? (
                    <Select value={String(row.tpa_id || '')} onValueChange={(v) => {
                      const next = [...splitForm];
                      const tpa = tpaList.find((t) => String(t.id) === v);
                      next[idx] = { ...next[idx], tpa_id: v, payer_name: tpa ? tpa.tpa_name : next[idx].payer_name };
                      setSplitForm(next);
                    }}>
                      <SelectTrigger className="col-span-3 h-9 text-xs"><SelectValue placeholder="Select TPA" /></SelectTrigger>
                      <SelectContent>
                        {tpaList.length === 0 && <SelectItem value="_none" disabled>No TPAs configured</SelectItem>}
                        {tpaList.map((t) => (
                          <SelectItem key={t.id} value={String(t.id)}>{t.tpa_name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <div className="col-span-3" />
                  )}
                  <Input className="col-span-2 h-9 text-xs" type="number" min="0" step="0.01" placeholder="Amount"
                    value={row.amount}
                    onChange={(e) => {
                      const next = [...splitForm];
                      next[idx] = { ...next[idx], amount: e.target.value };
                      setSplitForm(next);
                    }} />
                  <Button variant="ghost" size="sm" className="col-span-1 text-red-600"
                    disabled={splitForm.length === 1}
                    onClick={() => setSplitForm(splitForm.filter((_, i) => i !== idx))}>
                    ×
                  </Button>
                </div>
              ))}
              <Button variant="outline" size="sm" onClick={() =>
                setSplitForm([...splitForm, { payer_type: 'cash', payer_name: '', tpa_id: '', amount: '', notes: '' }])
              }>
                + Add split
              </Button>
            </div>
            <div className="text-right text-sm font-semibold pt-1 border-t">
              Allocated: {formatCurrency(splitForm.reduce((s, r) => s + (parseFloat(r.amount) || 0), 0))}
              {detailData && (
                <span className="ml-3 text-xs text-gray-500">
                  / {formatCurrency(detailData.total_amount)}
                </span>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button variant="outline" onClick={() => setSplitEditOpen(false)}>Cancel</Button>
              <Button disabled={splitSaving} onClick={submitSplits}>
                {splitSaving ? 'Saving...' : 'Save Splits'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Credit Note Dialog */}
      <Dialog open={creditNoteOpen} onOpenChange={(open) => { if (!open) setCreditNoteOpen(false); }}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Issue Credit Note</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {detailData && (
              <div className="bg-gray-50 rounded-lg p-3 text-sm space-y-1">
                <div className="flex justify-between"><span className="text-gray-500">Bill:</span><span className="font-mono">{detailData.bill_number}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Total:</span><span>{formatCurrency(detailData.total_amount)}</span></div>
                <div className="flex justify-between font-semibold text-red-700"><span>Outstanding balance:</span><span>{formatCurrency(detailData.balance_due)}</span></div>
              </div>
            )}
            <div className="space-y-2">
              <Label className="text-xs">Line items *</Label>
              {creditNoteForm.items.map((it, idx) => (
                <div key={idx} className="grid grid-cols-12 gap-2">
                  <Input className="col-span-6" placeholder="Description" value={it.item_name}
                    onChange={(e) => {
                      const next = [...creditNoteForm.items];
                      next[idx] = { ...next[idx], item_name: e.target.value };
                      setCreditNoteForm({ ...creditNoteForm, items: next });
                    }} />
                  <Input className="col-span-2" type="number" min="1" placeholder="Qty" value={it.quantity}
                    onChange={(e) => {
                      const next = [...creditNoteForm.items];
                      next[idx] = { ...next[idx], quantity: e.target.value };
                      setCreditNoteForm({ ...creditNoteForm, items: next });
                    }} />
                  <Input className="col-span-3" type="number" min="0" step="0.01" placeholder="Unit ₹" value={it.unit_price}
                    onChange={(e) => {
                      const next = [...creditNoteForm.items];
                      next[idx] = { ...next[idx], unit_price: e.target.value };
                      setCreditNoteForm({ ...creditNoteForm, items: next });
                    }} />
                  <Button variant="ghost" size="sm" className="col-span-1 text-red-600"
                    disabled={creditNoteForm.items.length === 1}
                    onClick={() => {
                      const next = creditNoteForm.items.filter((_, i) => i !== idx);
                      setCreditNoteForm({ ...creditNoteForm, items: next });
                    }}>
                    ×
                  </Button>
                </div>
              ))}
              <Button variant="outline" size="sm" onClick={() =>
                setCreditNoteForm({ ...creditNoteForm, items: [...creditNoteForm.items, { item_name: '', quantity: 1, unit_price: '' }] })
              }>
                + Add line
              </Button>
              <div className="text-right text-sm font-semibold pt-1">
                Total to credit: {formatCurrency(creditNoteForm.items.reduce((s, it) => s + (Number(it.quantity) || 0) * (parseFloat(it.unit_price) || 0), 0))}
              </div>
            </div>
            <div>
              <Label className="text-xs">Reason *</Label>
              <Textarea rows={2} value={creditNoteForm.reason}
                placeholder="e.g. Service not rendered, billing error, goodwill"
                onChange={(e) => setCreditNoteForm({ ...creditNoteForm, reason: e.target.value })} />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button variant="outline" onClick={() => setCreditNoteOpen(false)}>Cancel</Button>
              <Button variant="destructive"
                disabled={creditNoteSaving || !creditNoteForm.reason.trim() || creditNoteForm.reason.trim().length < 2}
                onClick={submitCreditNote}>
                {creditNoteSaving ? 'Issuing...' : 'Issue Credit Note'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Refund Dialog */}
      <Dialog open={!!refundPayment} onOpenChange={(open) => { if (!open) setRefundPayment(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Refund Payment</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {refundPayment && (
              <div className="bg-gray-50 rounded-lg p-3 text-sm space-y-1">
                <div className="flex justify-between"><span className="text-gray-500">Payment:</span><span className="font-mono">{refundPayment.payment_number}</span></div>
                <div className="flex justify-between"><span className="text-gray-500">Method:</span><span className="capitalize">{refundPayment.payment_method_name}</span></div>
                <div className="flex justify-between font-semibold text-green-700"><span>Amount paid:</span><span>{formatCurrency(refundPayment.amount_paid)}</span></div>
              </div>
            )}
            <div>
              <Label className="text-xs">Refund amount (₹) *</Label>
              <Input type="number" min="0" step="0.01" value={refundForm.amount}
                onChange={(e) => setRefundForm({ ...refundForm, amount: e.target.value })} />
              <p className="text-[10px] text-gray-400 mt-1">Leave at full amount for a full refund, or reduce for partial.</p>
            </div>
            <div>
              <Label className="text-xs">Reason *</Label>
              <Textarea rows={2} value={refundForm.reason}
                placeholder="e.g. Patient cancelled, billing error, goodwill"
                onChange={(e) => setRefundForm({ ...refundForm, reason: e.target.value })} />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button variant="outline" onClick={() => setRefundPayment(null)}>Cancel</Button>
              <Button variant="destructive"
                disabled={refundSaving || !refundForm.amount || !refundForm.reason.trim() || refundForm.reason.trim().length < 2}
                onClick={submitRefund}>
                {refundSaving ? 'Processing...' : 'Issue Refund'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Discount / Tax Adjustment Dialog */}
      <Dialog open={!!adjustMode} onOpenChange={(open) => { if (!open) setAdjustMode(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{adjustMode === 'tax' ? 'Apply Tax' : 'Apply Discount'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {detailData && (
              <div className="bg-gray-50 rounded-lg p-3 space-y-1 text-sm">
                <div className="flex justify-between"><span>Subtotal:</span><span>{formatCurrency(detailData.subtotal)}</span></div>
                {detailData.discount_amount > 0 && (
                  <div className="flex justify-between text-green-600"><span>Current discount:</span><span>-{formatCurrency(detailData.discount_amount)}</span></div>
                )}
                {detailData.tax_amount > 0 && (
                  <div className="flex justify-between"><span>Current tax:</span><span>{formatCurrency(detailData.tax_amount)}</span></div>
                )}
                <div className="flex justify-between font-bold border-t pt-1"><span>Total:</span><span>{formatCurrency(detailData.total_amount)}</span></div>
              </div>
            )}
            {adjustMode === 'discount' && (
              <div>
                <Label className="text-xs">Discount type</Label>
                <Select value={adjustForm.kind} onValueChange={(v) => setAdjustForm({ ...adjustForm, kind: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="percent">Percentage (%)</SelectItem>
                    <SelectItem value="flat">Flat amount (₹)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            )}
            <div>
              <Label className="text-xs">
                {adjustMode === 'tax' ? 'Tax percentage (%)' : (adjustForm.kind === 'percent' ? 'Discount %' : 'Discount amount (₹)')} *
              </Label>
              <Input type="number" min="0" step="0.01" value={adjustForm.value}
                onChange={(e) => setAdjustForm({ ...adjustForm, value: e.target.value })} />
            </div>
            <div>
              <Label className="text-xs">Reason *</Label>
              <Textarea rows={2} value={adjustForm.reason}
                placeholder={adjustMode === 'tax' ? 'e.g. GST 18%' : 'e.g. Loyalty discount, goodwill'}
                onChange={(e) => setAdjustForm({ ...adjustForm, reason: e.target.value })} />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button variant="outline" onClick={() => setAdjustMode(null)}>Cancel</Button>
              <Button disabled={adjustSaving || !adjustForm.value || !adjustForm.reason.trim() || adjustForm.reason.trim().length < 2}
                onClick={submitAdjustment}>
                {adjustSaving ? 'Saving...' : 'Apply'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <PdfPreviewDialog
        open={!!pdfPreview}
        onClose={() => setPdfPreview(null)}
        title={pdfPreview?.title || 'Bill Preview'}
        path={pdfPreview?.path || null}
      />
    </div>
  );
};

export default BillingModule;
