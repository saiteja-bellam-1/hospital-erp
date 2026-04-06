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
  CheckCircle2, AlertCircle, Loader2, CalendarDays, XCircle, Ban
} from 'lucide-react';

const BillingDashboard = () => {
  const [bills, setBills] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

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
  const [cancelBill, setCancelBill] = useState(null); // {bill_id, type, reference}
  const [cancelReason, setCancelReason] = useState('');
  const [cancelling, setCancelling] = useState(false);
  const [doctors, setDoctors] = useState([]);
  const [referrals, setReferrals] = useState([]);

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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Billing Dashboard</h1>
          <p className="text-muted-foreground text-sm">Centralised view of all bills and payments</p>
        </div>
        <Button onClick={downloadCSV} disabled={bills.length === 0} variant="outline">
          <Download className="h-4 w-4 mr-1" /> Export CSV
        </Button>
      </div>

      {/* Summary Cards */}
      {summary && (
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
            <Button size="sm" variant="outline" className="h-9" onClick={() => {
              setDateFrom(weekAgo); setDateTo(today); setPatientSearch(''); setBillType('all'); setPaymentStatus('all'); setDoctorFilter('all'); setReferralFilter('all');
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
                    <th className="pb-2 pr-3">Referred By</th>
                    <th className="pb-2 pr-3">Status</th>
                    <th className="pb-2 pr-3">Method</th>
                    <th className="pb-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {bills.map((bill) => (
                    <tr key={bill.id} className={`border-b hover:bg-gray-50 ${bill.payment_status === 'cancelled' ? 'opacity-60' : ''}`}>
                      <td className="py-2.5 pr-3 text-xs">{formatDate(bill.date)}</td>
                      <td className="py-2.5 pr-3">
                        <Badge variant="outline" className={`text-[10px] capitalize ${bill.type === 'consultation' ? 'border-blue-200 text-blue-700' : 'border-purple-200 text-purple-700'}`}>
                          {bill.type}
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
                      </td>
                      <td className="py-2.5 pr-3 text-xs text-gray-600">{bill.doctor_name || '-'}</td>
                      <td className="py-2.5 pr-3 text-xs text-gray-600">{bill.referred_by || '-'}</td>
                      <td className="py-2.5 pr-3">
                        <Badge className={`text-[10px] ${
                          bill.payment_status === 'paid' ? 'bg-green-100 text-green-700' :
                          bill.payment_status === 'cancelled' ? 'bg-red-100 text-red-700' :
                          'bg-orange-100 text-orange-700'
                        }`}>
                          {bill.payment_status}
                        </Badge>
                        {bill.cancel_reason && (
                          <p className="text-[9px] text-red-500 mt-0.5 max-w-[120px] truncate" title={`${bill.cancel_reason} — by ${bill.cancelled_by}`}>
                            {bill.cancel_reason}
                          </p>
                        )}
                      </td>
                      <td className="py-2.5 pr-3 text-xs text-gray-500 capitalize">{bill.payment_method || '-'}</td>
                      <td className="py-2.5">
                        {bill.payment_status !== 'cancelled' && bill.payment_status !== 'pending' && (
                          <Button size="sm" variant="ghost" className="h-6 text-[10px] text-red-500 hover:text-red-700 hover:bg-red-50 px-2"
                            onClick={() => { setCancelBill(bill); setCancelReason(''); }}>
                            <Ban className="w-3 h-3 mr-0.5" /> Cancel
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
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
                    await axios.post(`/api/hospital/billing/cancel/${cancelBill.type}/${cancelBill.bill_id}`, { reason: cancelReason.trim() });
                    setCancelBill(null);
                    fetchBills();
                  } catch (err) {
                    alert(err.response?.data?.detail || 'Cancel failed');
                  } finally { setCancelling(false); }
                }}>
                {cancelling ? 'Cancelling...' : 'Cancel Bill'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default BillingDashboard;
