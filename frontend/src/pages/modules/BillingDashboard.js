import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import { Textarea } from '../../components/ui/textarea';
import {
  Receipt, Search, Download, Filter, DollarSign, TrendingUp, Clock,
  CheckCircle2, AlertCircle, Loader2, CalendarDays, XCircle, Ban, Eye, FileText, CreditCard
} from 'lucide-react';

const BillingDashboard = () => {
  const [bills, setBills] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  // Active Bills vs Bill History (cancelled) toggle
  const [viewMode, setViewMode] = useState('active'); // 'active' | 'history'

  // Filters — default to last 7 days
  const today = new Date().toISOString().split('T')[0];
  const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().split('T')[0];
  const [dateFrom, setDateFrom] = useState(weekAgo);
  const [dateTo, setDateTo] = useState(today);
  const [patientSearch, setPatientSearch] = useState('');
  const [billType, setBillType] = useState('all');
  const [paymentStatus, setPaymentStatus] = useState('all');
  const [doctorFilter, setDoctorFilter] = useState('all');
  const [referralFilter, setReferralFilter] = useState('all');
  const [cancelBill, setCancelBill] = useState(null);
  const [cancelReason, setCancelReason] = useState('');
  const [cancelling, setCancelling] = useState(false);

  // Collect payment dialog
  const [collectBill, setCollectBill] = useState(null); // the bill row being settled
  const [collectForm, setCollectForm] = useState({ amount: '', method: 'cash', reference: '', notes: '' });
  const [collectLoading, setCollectLoading] = useState(false);
  const [doctors, setDoctors] = useState([]);
  const [referrals, setReferrals] = useState([]);
  // Bill preview dialog: bill row currently being viewed, blob URL of the
  // most recently fetched PDF, and whether the header is included.
  const [previewBill, setPreviewBill] = useState(null);
  const [previewPdfUrl, setPreviewPdfUrl] = useState(null);
  const [previewIncludeHeader, setPreviewIncludeHeader] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);

  const fetchBills = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('date_from', dateFrom);
      params.set('date_to', dateTo);
      if (patientSearch) params.set('patient_search', patientSearch);
      if (billType !== 'all') params.set('bill_type', billType);
      if (paymentStatus !== 'all') params.set('payment_status', paymentStatus);
      if (doctorFilter !== 'all') params.set('doctor_id', doctorFilter);
      if (referralFilter !== 'all') params.set('referred_by', referralFilter);

      const res = await axios.get(`/api/hospital/billing?${params.toString()}`);
      setBills(res.data.bills || []);
      setSummary(res.data.summary || null);
      if (res.data.doctors) setDoctors(res.data.doctors);
      if (res.data.referrals) setReferrals(res.data.referrals);
    } catch (err) {
      console.error('Failed to fetch bills:', err);
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, patientSearch, billType, paymentStatus, doctorFilter, referralFilter]);

  useEffect(() => { fetchBills(); }, [fetchBills]);

  const formatCurrency = (val) => `₹${Number(val || 0).toLocaleString('en-IN', { minimumFractionDigits: 0 })}`;
  const formatDate = (d) => {
    if (!d) return '-';
    try { return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }); }
    catch { return d; }
  };

  // Build the right endpoint URL per bill type. Lab bills with a group id
  // hit the combined-bill endpoint; ungrouped legacy lab orders fall back
  // to the per-order endpoint so they're still viewable.
  const buildBillPdfUrl = (bill, includeHeader) => {
    const h = includeHeader ? 'true' : 'false';
    if (bill.type === 'lab') {
      return bill.lab_bill_group_id
        ? `/api/lab/bills/${bill.lab_bill_group_id}/pdf?include_header=${h}`
        : `/api/lab/orders/${bill.bill_id}/bill?include_header=${h}`;
    }
    if (bill.type === 'consultation') {
      return `/api/appointments/${bill.bill_id}/bill/download?include_header=${h}`;
    }
    if (bill.type === 'admission') {
      // bill.bill_id is the Bill table PK; the PDF endpoint takes admission_id.
      const aid = bill.admission_id || bill.bill_id;
      return `/api/inpatient/admissions/${aid}/bill/pdf?include_header=${h}`;
    }
    // Day-care / procedure / consolidated bills — generic Bill PDF endpoint.
    return `/api/hospital/billing/bills/${bill.bill_id}/pdf?include_header=${h}`;
  };

  const fetchBillBlobUrl = async (bill, includeHeader) => {
    const url = buildBillPdfUrl(bill, includeHeader);
    if (!url) return null;
    const res = await axios.get(url, { responseType: 'blob' });
    return URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
  };

  const extractBlobError = async (err) => {
    // axios with responseType:'blob' wraps the error body as a Blob.
    // Read it as text and try to parse for the FastAPI detail.
    try {
      if (err.response?.data instanceof Blob) {
        const text = await err.response.data.text();
        try {
          const j = JSON.parse(text);
          return typeof j.detail === 'string' ? j.detail
            : (j.detail?.message || text || `HTTP ${err.response.status}`);
        } catch {
          return text || `HTTP ${err.response.status}`;
        }
      }
    } catch { /* ignore */ }
    return err.response?.data?.detail || `HTTP ${err.response?.status || 'error'}`;
  };

  const openBillPreview = async (bill) => {
    setPreviewBill(bill);
    setPreviewIncludeHeader(true);
    setPreviewPdfUrl(null);
    setPreviewLoading(true);
    try {
      const blobUrl = await fetchBillBlobUrl(bill, true);
      setPreviewPdfUrl(blobUrl);
    } catch (err) {
      const msg = await extractBlobError(err);
      alert(`Could not load bill PDF: ${msg}`);
      setPreviewBill(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const togglePreviewHeader = async (newVal) => {
    if (!previewBill) return;
    setPreviewIncludeHeader(newVal);
    setPreviewLoading(true);
    try {
      if (previewPdfUrl) URL.revokeObjectURL(previewPdfUrl);
      const blobUrl = await fetchBillBlobUrl(previewBill, newVal);
      setPreviewPdfUrl(blobUrl);
    } catch (err) {
      const msg = await extractBlobError(err);
      alert(`Could not reload bill PDF: ${msg}`);
    } finally {
      setPreviewLoading(false);
    }
  };

  const downloadFromPreview = () => {
    if (!previewBill || !previewPdfUrl) return;
    const a = document.createElement('a');
    a.href = previewPdfUrl;
    a.download = `bill_${previewBill.reference || previewBill.id}.pdf`;
    a.click();
  };

  const closeBillPreview = () => {
    if (previewPdfUrl) URL.revokeObjectURL(previewPdfUrl);
    setPreviewPdfUrl(null);
    setPreviewBill(null);
    setPreviewIncludeHeader(true);
  };

  const openCollect = (bill) => {
    // For admissions balance_due is the outstanding amount; for others use full amount.
    const due = bill.type === 'admission'
      ? (bill.balance_due > 0 ? bill.balance_due : bill.amount)
      : bill.amount;
    setCollectBill(bill);
    setCollectForm({ amount: due.toFixed(2), method: 'cash', reference: '', notes: '' });
  };

  const handleCollect = async () => {
    if (!collectBill || !collectForm.amount) return;
    const amt = parseFloat(collectForm.amount);
    if (!amt || amt <= 0) return;
    setCollectLoading(true);
    try {
      if (collectBill.type === 'admission') {
        // Admission payments go through the deposit ledger so the inpatient
        // balance view stays consistent. Uses deposit_type "topup" so it
        // appears as a top-up in the deposits list.
        await axios.post(`/api/inpatient/admissions/${collectBill.admission_id}/deposits`, {
          amount: amt,
          payment_method: collectForm.method,
          deposit_type: 'topup',
          reference_number: collectForm.reference || undefined,
          notes: collectForm.notes || undefined,
        });
      } else {
        // Consultation / lab / day-care / consolidated bills use the generic
        // payment endpoint — keeps parity with BillingModule's "Collect" flow.
        await axios.post(`/api/hospital/billing/bills/${collectBill.bill_id}/payment`, {
          amount_paid: amt,
          payment_method: collectForm.method,
          transaction_reference: collectForm.reference || undefined,
          notes: collectForm.notes || undefined,
        });
      }
      setCollectBill(null);
      fetchBills();
    } catch (err) {
      const detail = err.response?.data?.detail;
      alert(typeof detail === 'string' ? detail : (detail?.message || 'Payment failed'));
    } finally {
      setCollectLoading(false);
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

  // Split bills by cancelled status for the two views
  const activeBills = bills.filter(b => b.payment_status !== 'cancelled');
  const cancelledBills = bills.filter(b => b.payment_status === 'cancelled');
  const displayedBills = viewMode === 'active' ? activeBills : cancelledBills;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Bills History</h1>
          <p className="text-muted-foreground text-sm">Centralised view of all bills and payments</p>
        </div>
        <Button onClick={downloadCSV} disabled={displayedBills.length === 0} variant="outline">
          <Download className="h-4 w-4 mr-1" /> Export CSV
        </Button>
      </div>

      {/* Active Bills / Bill History tabs */}
      <div className="flex gap-1 border-b">
        <button
          onClick={() => { setViewMode('active'); setPaymentStatus('all'); }}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            viewMode === 'active'
              ? 'border-blue-600 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Active Bills
          {activeBills.length > 0 && (
            <span className="ml-2 text-[10px] bg-blue-100 text-blue-700 rounded-full px-1.5 py-0.5">
              {activeBills.length}
            </span>
          )}
        </button>
        <button
          onClick={() => { setViewMode('history'); setPaymentStatus('all'); }}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            viewMode === 'history'
              ? 'border-gray-600 text-gray-700'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Cancelled / History
          {cancelledBills.length > 0 && (
            <span className="ml-2 text-[10px] bg-gray-100 text-gray-600 rounded-full px-1.5 py-0.5">
              {cancelledBills.length}
            </span>
          )}
        </button>
      </div>

      {/* Summary Cards — only shown for the active bills view */}
      {summary && viewMode === 'active' && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
                  <p className="text-[10px] text-gray-400">{summary.appointment_count} consult + {summary.lab_count} lab</p>
                </div>
                <Receipt className="h-8 w-8 text-purple-500" />
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <Card>
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
              <Label className="text-xs">Patient</Label>
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
                <Input placeholder="Name or phone" value={patientSearch}
                  onChange={(e) => setPatientSearch(e.target.value)} className="pl-8 w-[180px] h-9" />
              </div>
            </div>
            <div>
              <Label className="text-xs">Type</Label>
              <Select value={billType} onValueChange={setBillType}>
                <SelectTrigger className="w-[130px] h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="consultation">Consultation</SelectItem>
                  <SelectItem value="lab">Lab Orders</SelectItem>
                  <SelectItem value="admission">Admission</SelectItem>
                  <SelectItem value="deposit">Deposits / Refunds</SelectItem>
                </SelectContent>
              </Select>
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
                  {viewMode === 'history' && <SelectItem value="cancelled">Cancelled</SelectItem>}
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
            <Button size="sm" variant="outline" className="h-9" onClick={() => {
              setDateFrom(weekAgo); setDateTo(today); setPatientSearch('');
              setBillType('all'); setPaymentStatus('all'); setDoctorFilter('all'); setReferralFilter('all');
            }}>
              Reset
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Bills Table */}
      <Card>
        <CardContent className="pt-4">
          {loading ? (
            <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>
          ) : displayedBills.length === 0 ? (
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
                    <th className="pb-2 pr-3">Referred By</th>
                    <th className="pb-2 pr-3">Status</th>
                    <th className="pb-2 pr-3">Method</th>
                    <th className="pb-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedBills.map((bill) => {
                    const typeBadge = (() => {
                      if (bill.type === 'consultation') return 'border-blue-200 text-blue-700';
                      if (bill.type === 'lab') return 'border-purple-200 text-purple-700';
                      if (bill.type === 'admission') return 'border-green-200 text-green-700';
                      return 'border-gray-200 text-gray-700';
                    })();
                    const typeLabel = (() => {
                      if (bill.type === 'admission') {
                        return bill.bill_subtype === 'final' ? 'Admission' : 'Admission (interim)';
                      }
                      return bill.type === 'consultation' ? 'Consultation' : bill.type === 'lab' ? 'Lab' : bill.type;
                    })();
                    const statusBadge = `text-[10px] ${
                      bill.payment_status === 'paid' ? 'bg-green-100 text-green-700' :
                      bill.payment_status === 'cancelled' ? 'bg-red-100 text-red-700' :
                      bill.payment_status === 'partial' ? 'bg-yellow-100 text-yellow-700' :
                      'bg-orange-100 text-orange-700'
                    }`;
                    return (
                      <React.Fragment key={bill.id}>
                        {/* Main bill row */}
                        <tr className={`border-b hover:bg-gray-50 ${bill.payment_status === 'cancelled' ? 'opacity-60' : ''}`}>
                          <td className="py-2.5 pr-3 text-xs">{formatDate(bill.date)}</td>
                          <td className="py-2.5 pr-3">
                            <Badge variant="outline" className={`text-[10px] ${typeBadge}`}>{typeLabel}</Badge>
                          </td>
                          <td className="py-2.5 pr-3 text-xs font-mono text-gray-500">{bill.reference}</td>
                          <td className="py-2.5 pr-3">
                            <p className="font-medium text-sm">{bill.patient_name}</p>
                            <p className="text-[10px] text-gray-400">{bill.patient_phone}</p>
                          </td>
                          <td className="py-2.5 pr-3 text-xs text-gray-600 max-w-[200px] truncate">{bill.items}</td>
                          <td className="py-2.5 pr-3 text-right">
                            <p className="font-semibold">{formatCurrency(bill.amount)}</p>
                            {bill.type === 'admission' && bill.balance_due > 0.01 && (
                              <p className="text-[10px] text-orange-600">bal. {formatCurrency(bill.balance_due)}</p>
                            )}
                            {bill.discount > 0 && <p className="text-[10px] text-green-600">-{formatCurrency(bill.discount)} disc.</p>}
                          </td>
                          <td className="py-2.5 pr-3 text-xs text-gray-600">{bill.doctor_name || '-'}</td>
                          <td className="py-2.5 pr-3 text-xs text-gray-600">{bill.referred_by || '-'}</td>
                          <td className="py-2.5 pr-3">
                            <Badge className={statusBadge}>{bill.payment_status}</Badge>
                            {bill.cancel_reason && (
                              <p className="text-[9px] text-red-500 mt-0.5 max-w-[120px] truncate" title={`${bill.cancel_reason} — by ${bill.cancelled_by}`}>
                                {bill.cancel_reason}
                              </p>
                            )}
                          </td>
                          <td className="py-2.5 pr-3 text-xs text-gray-500 capitalize">{bill.payment_method || '-'}</td>
                          <td className="py-2.5">
                            <div className="flex items-center gap-1">
                              {bill.payment_status !== 'cancelled' && bill.bill_id && (
                                <Button size="sm" variant="ghost" className="h-6 text-[10px] px-2"
                                  onClick={() => openBillPreview(bill)} title="View bill PDF">
                                  <Eye className="w-3 h-3 mr-0.5" /> View
                                </Button>
                              )}
                              {['pending', 'partial'].includes(bill.payment_status) && (
                                <Button size="sm" variant="ghost"
                                  className="h-6 text-[10px] px-2 text-green-700 hover:text-green-800 hover:bg-green-50"
                                  onClick={() => openCollect(bill)}>
                                  <CreditCard className="w-3 h-3 mr-0.5" /> Collect
                                </Button>
                              )}
                              {bill.payment_status !== 'cancelled' && bill.type !== 'admission' && (
                                <Button size="sm" variant="ghost" className="h-6 text-[10px] text-red-500 hover:text-red-700 hover:bg-red-50 px-2"
                                  onClick={() => { setCancelBill(bill); setCancelReason(''); }}>
                                  <Ban className="w-3 h-3 mr-0.5" /> Cancel
                                </Button>
                              )}
                            </div>
                          </td>
                        </tr>

                        {/* Inline deposit / refund child rows */}
                        {bill.type === 'admission' && (bill.deposits || []).map((dep, i) => {
                          const isRefund = dep.deposit_type === 'refund';
                          const depLabel = dep.deposit_type === 'initial' ? 'Deposit'
                            : dep.deposit_type === 'topup' ? 'Top-up'
                            : 'Refund';
                          return (
                            <tr key={`dep-${bill.id}-${i}`} className="border-b bg-gray-50/60">
                              <td className="py-1.5 pr-3 pl-6 text-[10px] text-gray-400">{formatDate(dep.date)}</td>
                              <td className="py-1.5 pr-3">
                                <Badge className={`text-[10px] ${isRefund ? 'bg-red-100 text-red-700' : 'bg-teal-100 text-teal-700'}`}>
                                  {depLabel}
                                </Badge>
                              </td>
                              <td className="py-1.5 pr-3 text-[10px] font-mono text-gray-400">{dep.deposit_number}</td>
                              <td className="py-1.5 pr-3 text-[10px] text-gray-400" colSpan={2}>
                                {dep.method.charAt(0).toUpperCase() + dep.method.slice(1)}
                                {dep.reference ? ` · ${dep.reference}` : ''}
                              </td>
                              <td className="py-1.5 pr-3 text-right">
                                <span className={`text-xs font-medium ${isRefund ? 'text-red-600' : 'text-teal-700'}`}>
                                  {isRefund ? '−' : '+'}{formatCurrency(dep.amount)}
                                </span>
                              </td>
                              <td colSpan={5} />
                            </tr>
                          );
                        })}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

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
                <p className="text-xs text-gray-500">{cancelBill.reference} — {cancelBill.items}</p>
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
              <Button variant="destructive" disabled={cancelling || !cancelReason.trim()}
                onClick={async () => {
                  setCancelling(true);
                  try {
                    if (cancelBill.type === 'admission') {
                      await axios.post(
                        `/api/inpatient/admissions/${cancelBill.admission_id}/bills/${cancelBill.bill_id}/cancel`,
                        { reason: cancelReason.trim() }
                      );
                    } else {
                      await axios.post(`/api/hospital/billing/cancel/${cancelBill.type}/${cancelBill.bill_id}`, { reason: cancelReason.trim() });
                    }
                    setCancelBill(null);
                    fetchBills();
                  } catch (err) {
                    const detail = err.response?.data?.detail;
                    if (detail && typeof detail === 'object' && detail.code === 'bill_has_payments') {
                      alert(`${detail.message}\n\nAmount already paid: ₹${detail.amount_paid}\nUse the deposit refund flow first, then retry.`);
                    } else {
                      alert(typeof detail === 'string' ? detail : 'Cancel failed');
                    }
                  } finally { setCancelling(false); }
                }}>
                {cancelling ? 'Cancelling...' : 'Cancel Bill'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Collect Payment Dialog */}
      <Dialog open={!!collectBill} onOpenChange={(open) => { if (!open) setCollectBill(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CreditCard className="h-5 w-5 text-green-600" /> Collect Payment
            </DialogTitle>
          </DialogHeader>
          {collectBill && (
            <div className="space-y-4">
              {/* Bill summary */}
              <div className="bg-gray-50 rounded-lg p-3 space-y-1">
                <p className="text-sm font-semibold">{collectBill.patient_name}</p>
                <p className="text-xs text-gray-500 font-mono">{collectBill.reference}</p>
                <div className="flex items-center justify-between pt-1">
                  <span className="text-xs text-gray-500">
                    {collectBill.type === 'admission' ? 'Balance due' : 'Amount due'}
                  </span>
                  <span className="text-base font-bold text-orange-600">
                    {formatCurrency(
                      collectBill.type === 'admission'
                        ? (collectBill.balance_due > 0 ? collectBill.balance_due : collectBill.amount)
                        : collectBill.amount
                    )}
                  </span>
                </div>
                {collectBill.type === 'admission' && collectBill.amount !== collectBill.balance_due && (
                  <p className="text-[10px] text-gray-400">
                    Total charges: {formatCurrency(collectBill.amount)} · Deposits received: {formatCurrency(collectBill.net_deposits || 0)}
                  </p>
                )}
              </div>

              {/* Amount */}
              <div>
                <Label className="text-sm">Amount collecting (₹) *</Label>
                <Input
                  type="number" min="0.01" step="0.01"
                  className="mt-1"
                  value={collectForm.amount}
                  onChange={e => setCollectForm(p => ({ ...p, amount: e.target.value }))}
                />
              </div>

              {/* Payment method */}
              <div>
                <Label className="text-sm">Payment method *</Label>
                <Select value={collectForm.method} onValueChange={v => setCollectForm(p => ({ ...p, method: v }))}>
                  <SelectTrigger className="mt-1"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="card">Card</SelectItem>
                    <SelectItem value="upi">UPI</SelectItem>
                    <SelectItem value="cheque">Cheque</SelectItem>
                    <SelectItem value="online">Online Transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Reference */}
              <div>
                <Label className="text-sm">Reference / Transaction ID</Label>
                <Input
                  className="mt-1" placeholder="Optional"
                  value={collectForm.reference}
                  onChange={e => setCollectForm(p => ({ ...p, reference: e.target.value }))}
                />
              </div>

              {/* Notes */}
              <div>
                <Label className="text-sm">Notes</Label>
                <Textarea
                  className="mt-1" rows={2} placeholder="Optional"
                  value={collectForm.notes}
                  onChange={e => setCollectForm(p => ({ ...p, notes: e.target.value }))}
                />
              </div>

              <div className="flex justify-end gap-2 pt-2 border-t">
                <Button variant="outline" onClick={() => setCollectBill(null)}>Cancel</Button>
                <Button
                  disabled={collectLoading || !collectForm.amount || parseFloat(collectForm.amount) <= 0}
                  onClick={handleCollect}
                  className="bg-green-600 hover:bg-green-700 text-white"
                >
                  {collectLoading
                    ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Recording…</>
                    : <><CreditCard className="h-4 w-4 mr-2" /> Record Payment</>
                  }
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Bill Preview Dialog — same iframe + header-toggle pattern used
          everywhere else in the app for printable artifacts. */}
      <Dialog open={!!previewBill} onOpenChange={(open) => { if (!open) closeBillPreview(); }}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              {previewBill ? `${
                previewBill.type === 'lab' ? 'Lab'
                  : previewBill.type === 'consultation' ? 'Consultation'
                  : previewBill.type === 'admission' ? 'Admission'
                  : previewBill.type === 'day_care' ? 'Day Care'
                  : (previewBill.type || 'Bill').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
              } Bill` : 'Bill'}
              {previewBill?.reference && (
                <span className="text-xs font-mono text-gray-500 font-normal">— {previewBill.reference}</span>
              )}
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col space-y-4">
            <div className="flex-1 min-h-[500px] border rounded-lg overflow-hidden bg-gray-50 relative">
              {previewLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-white/70 z-10">
                  <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
                </div>
              )}
              {previewPdfUrl && (
                <iframe src={previewPdfUrl} className="w-full h-[60vh] border-0" title="Bill Preview" />
              )}
            </div>
            <div className="flex items-center gap-3">
              <div className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  id="bill-include-header"
                  checked={previewIncludeHeader}
                  onChange={(e) => togglePreviewHeader(e.target.checked)}
                  disabled={previewLoading}
                  className="w-4 h-4"
                />
                <Label htmlFor="bill-include-header" className="text-sm cursor-pointer">Include header</Label>
              </div>
              <div className="flex-1" />
              <Button variant="outline" onClick={closeBillPreview}>Close</Button>
              <Button onClick={downloadFromPreview} disabled={!previewPdfUrl || previewLoading}>
                <Download className="h-4 w-4 mr-2" /> Download
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default BillingDashboard;
