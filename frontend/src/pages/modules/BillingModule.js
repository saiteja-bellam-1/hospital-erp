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
  Building2, Stethoscope, FlaskConical, BedDouble, Printer, FileText
} from 'lucide-react';

const BillingModule = () => {
  const [bills, setBills] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('all');

  // Filters
  const today = new Date().toISOString().split('T')[0];
  const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().split('T')[0];
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

  // Payment dialog
  const [payBill, setPayBill] = useState(null);
  const [paymentForm, setPaymentForm] = useState({
    amount_paid: '', payment_method: 'cash', transaction_reference: '', notes: ''
  });
  const [paymentLoading, setPaymentLoading] = useState(false);

  const fetchBills = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('date_from', dateFrom);
      params.set('date_to', dateTo);
      if (patientSearch) params.set('patient_search', patientSearch);
      // Map tab to bill_type filter
      if (activeTab === 'outpatient') params.set('bill_type', 'consultation');
      else if (activeTab === 'lab') params.set('bill_type', 'lab');
      else if (activeTab === 'inpatient') params.set('bill_type', 'admission');
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
  }, [dateFrom, dateTo, patientSearch, activeTab, paymentStatus, doctorFilter, referralFilter]);

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

  const handleCancelBill = async () => {
    if (!cancelBill || !cancelReason.trim()) return;
    setCancelling(true);
    try {
      await axios.post(`/api/hospital/billing/cancel/${cancelBill.type}/${cancelBill.bill_id}`, {
        reason: cancelReason.trim()
      });
      setCancelBill(null);
      setCancelReason('');
      fetchBills();
    } catch (err) {
      const detail = err.response?.data?.detail;
      alert(typeof detail === 'string' ? detail : 'Cancel failed');
    } finally {
      setCancelling(false);
    }
  };

  const openBillDetail = async (bill) => {
    // Only admission bills use the bills table with detail endpoint
    if (bill.type === 'admission') {
      setDetailBill(bill);
      setDetailLoading(true);
      try {
        const res = await axios.get(`/api/hospital/billing/bills/${bill.bill_id}`);
        setDetailData(res.data);
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

  const handlePrintAdmissionBill = async (admissionId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/inpatient/admissions/${admissionId}/bill/pdf?include_header=true`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        document.body.appendChild(iframe);
        iframe.src = url;
        iframe.onload = () => {
          iframe.contentWindow.print();
          setTimeout(() => { document.body.removeChild(iframe); URL.revokeObjectURL(url); }, 1000);
        };
      }
    } catch (err) {
      console.error('Print failed:', err);
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
        <Button onClick={downloadCSV} disabled={bills.length === 0} variant="outline">
          <Download className="h-4 w-4 mr-1" /> Export CSV
        </Button>
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
        </TabsList>

        {/* Filters - shared across all tabs */}
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
                                {/* View detail for admission bills */}
                                {bill.type === 'admission' && (
                                  <Button size="sm" variant="ghost" className="h-6 text-[10px] px-2"
                                    onClick={() => openBillDetail(bill)}>
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
                                {/* Print for admission bills */}
                                {bill.type === 'admission' && bill.admission_id && (
                                  <Button size="sm" variant="ghost" className="h-6 text-[10px] px-2"
                                    onClick={() => handlePrintAdmissionBill(bill.admission_id)}>
                                    <Printer className="w-3 h-3" />
                                  </Button>
                                )}
                                {/* Cancel for non-cancelled, non-pending bills */}
                                {bill.payment_status !== 'cancelled' && bill.payment_status !== 'pending' && bill.type !== 'admission' && (
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
                      <div key={i} className="flex items-center justify-between bg-green-50 rounded p-2.5 text-sm">
                        <div>
                          <span className="font-mono text-xs text-gray-500">{p.payment_number}</span>
                          <span className="ml-2 text-xs capitalize">{p.payment_method_name}</span>
                          {p.transaction_reference && (
                            <span className="ml-2 text-xs text-gray-400">Ref: {p.transaction_reference}</span>
                          )}
                        </div>
                        <div className="text-right">
                          <span className="font-semibold text-green-700">{formatCurrency(p.amount_paid)}</span>
                          <span className="ml-2 text-xs text-gray-400">{formatDate(p.payment_date)}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex justify-end gap-2 pt-2 border-t">
                {detailBill?.admission_id && (
                  <Button variant="outline" onClick={() => handlePrintAdmissionBill(detailBill.admission_id)}>
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
    </div>
  );
};

export default BillingModule;
