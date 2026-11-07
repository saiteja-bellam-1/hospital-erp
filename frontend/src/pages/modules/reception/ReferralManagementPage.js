import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import { Textarea } from '../../../components/ui/textarea';
import { printPdfFromUrl } from '../../../utils/printPdf';
import { useToast } from '../../../hooks/use-toast';
import { useAuth } from '../../../contexts/AuthContext';
import { normalizeUserRoles } from '../../../hooks/useNavigationSections';
import axios from 'axios';
import {
  Users, Plus, Search, Edit2, Trash2, Phone, MapPin, Eye, Loader2,
  DollarSign, ArrowLeft, Stethoscope, TestTube, Bed, Pill, Printer
} from 'lucide-react';

const EMPTY_FORM = {
  name: '', phone: '', village: '', mandal: '', district: '',
  op_commission_pct: '0', lab_commission_pct: '0', ip_commission_pct: '0', pharmacy_commission_pct: '0',
};

function errorMessage(err, fallback) {
  const detail = err.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return detail[0].msg;
  return fallback;
}

function parseRate(value) {
  if (value === '' || value === null || value === undefined) return 0;
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0 || n > 100) return null;
  return Math.round(n * 100) / 100;
}

function billPrintTarget(row) {
  if (!row) return null;
  if (row.type === 'consultation') return { url: `/api/appointments/${row.id}/bill/download` };
  if (row.type === 'lab') {
    if (row.lab_bill_group_id) return { url: `/api/lab/bills/${row.lab_bill_group_id}/pdf` };
    return { url: `/api/lab/orders/${row.id}/bill` };
  }
  if (row.type === 'inpatient' && row.admission_id) {
    return { url: `/api/inpatient/admissions/${row.admission_id}/bill/pdf`, params: { bill_id: row.id } };
  }
  if (row.type === 'pharmacy') return { url: `/api/pharmacy/sales/${row.id}/invoice/pdf` };
  return null;
}

function rateCell(row) {
  const pct = row.commission_pct != null ? `${row.commission_pct}%` : '';
  if (row.type === 'lab') {
    return { title: row.category_name || 'Uncategorised', pct };
  }
  return { title: row.detail || '—', pct };
}

function BillSection({ rows, emptyLabel, detailHeading, formatCurrency, formatDate, onPrint, printingKey }) {
  if (rows.length === 0) {
    return <p className="text-sm text-gray-400 text-center py-8">{emptyLabel}</p>;
  }
  return (
    <div className="border rounded-lg overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b bg-muted/50 text-left text-xs text-gray-500">
            <th className="px-3 py-2 font-medium">Patient</th>
            <th className="px-3 py-2 font-medium">{detailHeading}</th>
            <th className="px-3 py-2 font-medium text-right">Amount earned</th>
            <th className="px-3 py-2 font-medium text-right">Bill value</th>
            <th className="px-3 py-2 font-medium text-right">Print</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((b) => {
            const rowKey = `${b.type}-${b.id}`;
            const canPrint = Boolean(billPrintTarget(b));
            const rate = rateCell(b);
            const sendOut = b.fulfillment === 'send_out' && b.commission_base != null && b.commission_base !== b.amount;
            const paid = b.status === 'paid' || b.status === 'completed';
            return (
              <tr key={rowKey} className="border-b last:border-b-0">
                <td className="px-3 py-2.5 align-top">
                  <p className="font-medium">{b.patient_name}</p>
                  <p className="text-xs text-gray-400">
                    {[b.type === 'lab' ? b.detail : null, b.reference, formatDate(b.date)].filter(Boolean).join(' · ')}
                  </p>
                </td>
                <td className="px-3 py-2.5 align-top">
                  <p>{rate.title}</p>
                  {rate.pct && <p className="text-xs text-gray-500">{rate.pct}</p>}
                </td>
                <td className="px-3 py-2.5 align-top text-right font-medium text-blue-700 whitespace-nowrap">
                  {formatCurrency(b.commission)}
                </td>
                <td className="px-3 py-2.5 align-top text-right whitespace-nowrap">
                  <p className="font-semibold">{formatCurrency(b.amount)}</p>
                  {sendOut && <p className="text-[10px] text-gray-500">base {formatCurrency(b.commission_base)}</p>}
                  <Badge className={`mt-1 text-[10px] ${paid ? 'bg-green-100 text-green-700' : 'bg-orange-100 text-orange-700'}`}>{b.status}</Badge>
                </td>
                <td className="px-3 py-2.5 align-top text-right">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    disabled={!canPrint || printingKey === rowKey}
                    onClick={() => onPrint(b)}
                  >
                    {printingKey === rowKey ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Printer className="h-3 w-3 mr-1" />}
                    Print
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const ReferralManagementPage = () => {
  const { toast } = useToast();
  const { user } = useAuth();
  const canEditReferral = normalizeUserRoles(user).some((role) => role === 'billing_admin' || role === 'hospital_admin' || role === 'super_admin');
  const token = localStorage.getItem('token');
  const headers = { Authorization: `Bearer ${token}` };

  const [referrals, setReferrals] = useState([]);
  const [dashboard, setDashboard] = useState({
    referral_count: 0, active_count: 0,
    revenue_generated: 0, commission_earned: 0, commission_paid: 0, commission_due: 0,
  });
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');

  // Form dialog
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [categoryRates, setCategoryRates] = useState({});
  const [labCategories, setLabCategories] = useState([]);
  const [categoriesLoaded, setCategoriesLoaded] = useState(false);
  const [categoriesFailed, setCategoriesFailed] = useState(false);
  const [saving, setSaving] = useState(false);

  // Detail view
  const [selectedReferral, setSelectedReferral] = useState(null);
  const [details, setDetails] = useState(null);
  const [viewTab, setViewTab] = useState('op');
  const [printingKey, setPrintingKey] = useState(null);
  const [, setDetailsLoading] = useState(false);

  // Commission form
  const [showCommForm, setShowCommForm] = useState(false);
  const [commForm, setCommForm] = useState({ amount: '', payment_method: 'cash', notes: '' });
  const [commSaving, setCommSaving] = useState(false);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    fetchReferrals();
    axios.get('/api/referrals/lab-categories', { headers })
      .then((res) => setLabCategories(Array.isArray(res.data) ? res.data : []))
      .catch(() => { setLabCategories([]); setCategoriesFailed(true); })
      .finally(() => setCategoriesLoaded(true));
  }, []);

  const fetchReferrals = async () => {
    try {
      const [listRes, dashRes] = await Promise.all([
        axios.get('/api/referrals/all', { headers }),
        axios.get('/api/referrals/dashboard', { headers }),
      ]);
      setReferrals(listRes.data);
      setDashboard(dashRes.data);
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to load referrals' });
    } finally {
      setLoading(false);
    }
  };

  const openForm = (ref = null) => {
    if (ref) {
      setEditing(ref);
      setForm({
        name: ref.name,
        phone: ref.phone || '',
        village: ref.village || '',
        mandal: ref.mandal || '',
        district: ref.district || '',
        op_commission_pct: String(ref.op_commission_pct ?? 0),
        lab_commission_pct: String(ref.lab_commission_pct ?? 0),
        ip_commission_pct: String(ref.ip_commission_pct ?? 0),
        pharmacy_commission_pct: String(ref.pharmacy_commission_pct ?? 0),
      });
      const rates = {};
      (ref.category_rates || []).forEach((rate) => {
        rates[rate.category_id] = String(rate.commission_pct ?? 0);
      });
      setCategoryRates(rates);
    } else {
      setEditing(null);
      setForm(EMPTY_FORM);
      setCategoryRates({});
    }
    setShowForm(true);
  };

  const referralPayload = () => {
    const op = parseRate(form.op_commission_pct);
    const lab = parseRate(form.lab_commission_pct);
    const ip = parseRate(form.ip_commission_pct);
    const pharmacy = parseRate(form.pharmacy_commission_pct);
    if ([op, lab, ip, pharmacy].some((n) => n === null)) return null;
    const payload = {
      name: form.name.trim(),
      phone: form.phone || null,
      village: form.village || null,
      mandal: form.mandal || null,
      district: form.district || null,
      op_commission_pct: op,
      lab_commission_pct: lab,
      ip_commission_pct: ip,
      pharmacy_commission_pct: pharmacy,
    };
    if (categoriesLoaded && !categoriesFailed) {
      const category_rates = [];
      for (const category of labCategories) {
        const raw = categoryRates[category.id];
        if (raw === '' || raw === undefined || raw === null) continue;
        const pct = parseRate(raw);
        if (pct === null) return null;
        category_rates.push({ category_id: category.id, commission_pct: pct });
      }
      payload.category_rates = category_rates;
    }
    return payload;
  };

  const saveReferral = async () => {
    if (!form.name.trim()) return;
    const payload = referralPayload();
    if (!payload) {
      toast({ variant: 'destructive', title: 'Invalid rate', description: 'Commission percents must be between 0 and 100.' });
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await axios.put(`/api/referrals/${editing.id}`, payload, { headers });
        toast({ title: 'Updated' });
      } else {
        await axios.post('/api/referrals', payload, { headers });
        toast({ title: 'Added' });
      }
      setShowForm(false);
      fetchReferrals();
      if (selectedReferral && editing?.id === selectedReferral.id) fetchDetails(editing.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: errorMessage(err, 'Failed to save') });
    } finally { setSaving(false); }
  };

  const deleteReferral = async (id) => {
    if (!window.confirm('Deactivate this referral?')) return;
    try {
      await axios.delete(`/api/referrals/${id}`, { headers });
      toast({ title: 'Deactivated' });
      fetchReferrals();
      if (selectedReferral?.id === id) { setSelectedReferral(null); setDetails(null); }
    } catch {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to deactivate' });
    }
  };

  const reactivate = async (ref) => {
    try {
      await axios.put(`/api/referrals/${ref.id}`, { is_active: true }, { headers });
      toast({ title: 'Reactivated' });
      fetchReferrals();
    } catch {
      toast({ variant: 'destructive', title: 'Error' });
    }
  };

  const fetchDetails = async (id) => {
    setDetailsLoading(true);
    try {
      const res = await axios.get(`/api/referrals/${id}/details`, { headers });
      setDetails(res.data);
    } catch {
      setSelectedReferral(null);
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to load details' });
    } finally { setDetailsLoading(false); }
  };

  const openDetails = (ref) => {
    setSelectedReferral(ref);
    setDetails(null);
    setViewTab('op');
    fetchDetails(ref.id);
  };

  const printBill = async (row) => {
    const target = billPrintTarget(row);
    if (!target) {
      toast({ variant: 'destructive', title: 'No bill to print', description: 'This row has no printable bill.' });
      return;
    }
    const rowKey = `${row.type}-${row.id}`;
    setPrintingKey(rowKey);
    try {
      await printPdfFromUrl(target.url, {
        params: target.params,
        onError: (msg) => toast({ variant: 'destructive', title: 'Print failed', description: msg || 'Could not load the bill PDF' }),
      });
    } finally {
      setPrintingKey(null);
    }
  };

  const openPayDialog = () => {
    const due = Math.max(0, Number(details?.summary?.commission_balance) || 0);
    setCommForm({
      amount: due > 0 ? String(due) : '',
      payment_method: 'cash',
      notes: '',
    });
    setShowCommForm(true);
  };

  const addCommission = async () => {
    if (!commForm.amount || parseFloat(commForm.amount) <= 0) return;
    setCommSaving(true);
    try {
      await axios.post(`/api/referrals/${selectedReferral.id}/commissions`, {
        amount: parseFloat(commForm.amount),
        payment_method: commForm.payment_method,
        notes: commForm.notes || null,
      }, { headers });
      toast({ title: 'Commission recorded' });
      setShowCommForm(false);
      setCommForm({ amount: '', payment_method: 'cash', notes: '' });
      fetchDetails(selectedReferral.id);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: errorMessage(err, 'Failed') });
    } finally { setCommSaving(false); }
  };

  const deleteCommission = async (commId) => {
    if (!window.confirm('Delete this commission record?')) return;
    try {
      await axios.delete(`/api/referrals/${selectedReferral.id}/commissions/${commId}`, { headers });
      toast({ title: 'Deleted' });
      fetchDetails(selectedReferral.id);
    } catch {
      toast({ variant: 'destructive', title: 'Error' });
    }
  };

  const formatCurrency = (v) => `₹${Number(v || 0).toLocaleString('en-IN')}`;
  const formatDate = (d) => {
    if (!d) return '-';
    try { return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }); }
    catch { return d; }
  };

  const filtered = referrals.filter(r => {
    if (!search) return true;
    const q = search.toLowerCase();
    return r.name.toLowerCase().includes(q) || (r.village || '').toLowerCase().includes(q) ||
      (r.mandal || '').toLowerCase().includes(q) || (r.phone || '').includes(q);
  });

  if (loading || (selectedReferral && !details)) {
    return <div className="flex items-center justify-center p-12"><Loader2 className="w-6 h-6 animate-spin" /></div>;
  }

  // ===== DETAIL VIEW =====
  if (selectedReferral && details) {
    const s = details.summary;
    const labCategoriesSummary = s.lab_by_category || [];
    const labRatesDiffer = labCategoriesSummary.some((row) => Number(row.percent) !== Number(s.lab_commission_pct));
    const labRateLabel = labRatesDiffer ? 'by category' : `${s.lab_commission_pct}%`;
    const serviceCards = [
      { key: 'op', label: 'OP', count: s.total_consultations, revenue: s.op_revenue, rateLabel: `${s.op_commission_pct}%`, commission: s.op_commission },
      { key: 'lab', label: 'Lab', count: s.total_lab_orders, revenue: s.lab_revenue, rateLabel: labRateLabel, commission: s.lab_commission, base: s.lab_commission_base },
      { key: 'ip', label: 'IP', count: s.total_ip_bills, revenue: s.ip_revenue, rateLabel: `${s.ip_commission_pct}%`, commission: s.ip_commission },
      { key: 'pharmacy', label: 'Pharmacy', count: s.total_pharmacy_sales, revenue: s.pharmacy_revenue, rateLabel: `${s.pharmacy_commission_pct}%`, commission: s.pharmacy_commission },
    ];
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => { setSelectedReferral(null); setDetails(null); fetchReferrals(); }}>
            <ArrowLeft className="h-4 w-4 mr-1" /> Back
          </Button>
          <div>
            <h1 className="text-2xl font-bold">{details.referral.name}</h1>
            <p className="text-sm text-gray-500">
              {[details.referral.village, details.referral.mandal, details.referral.district].filter(Boolean).join(', ')}
              {details.referral.phone && <span> | {details.referral.phone}</span>}
            </p>
          </div>
        </div>

        <p className="text-sm text-gray-500">
          Bills are included for patients registered with this referral. Lab tests and pharmacy sales already on an inpatient bill are counted under IP only.
        </p>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {serviceCards.map((card) => (
            <Card
              key={card.key}
              className={`cursor-pointer ${viewTab === card.key ? 'ring-2 ring-primary' : ''}`}
              onClick={() => setViewTab(card.key)}
            ><CardContent className="pt-4 pb-3">
              <p className="text-xs text-gray-500">{card.label} · {card.count}</p>
              <p className="text-lg font-bold">{formatCurrency(card.revenue)}</p>
              <p className="text-xs text-gray-500">
                {card.rateLabel}
                {card.base != null && card.base !== card.revenue ? ` · base ${formatCurrency(card.base)}` : ''}
                {' → '}{formatCurrency(card.commission)}
              </p>
            </CardContent></Card>
          ))}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <Card><CardContent className="pt-4 pb-3 text-center">
            <p className="text-xs text-gray-500">Commission earned</p>
            <p className="text-xl font-bold text-blue-600">{formatCurrency(s.total_commission_earned)}</p>
          </CardContent></Card>
          <Card><CardContent className="pt-4 pb-3 text-center">
            <p className="text-xs text-gray-500">Paid out</p>
            <p className="text-xl font-bold text-green-600">{formatCurrency(s.total_commission_paid)}</p>
          </CardContent></Card>
          <Card><CardContent className="pt-4 pb-3 text-center">
            <p className="text-xs text-gray-500">Balance due</p>
            <p className={`text-xl font-bold ${s.commission_balance < 0 ? 'text-red-600' : 'text-orange-600'}`}>{formatCurrency(s.commission_balance)}</p>
          </CardContent></Card>
        </div>

        <Tabs value={viewTab} onValueChange={setViewTab}>
          <TabsList className="flex h-auto w-full flex-wrap justify-start gap-1">
            <TabsTrigger value="op"><Stethoscope className="h-3.5 w-3.5 mr-1" /> OP ({s.total_consultations})</TabsTrigger>
            <TabsTrigger value="lab"><TestTube className="h-3.5 w-3.5 mr-1" /> Lab ({s.total_lab_orders})</TabsTrigger>
            <TabsTrigger value="ip"><Bed className="h-3.5 w-3.5 mr-1" /> IP ({s.total_ip_bills})</TabsTrigger>
            <TabsTrigger value="pharmacy"><Pill className="h-3.5 w-3.5 mr-1" /> Pharmacy ({s.total_pharmacy_sales})</TabsTrigger>
            <TabsTrigger value="payouts"><DollarSign className="h-3.5 w-3.5 mr-1" /> Payouts ({details.commissions.length})</TabsTrigger>
          </TabsList>

          <TabsContent value="op">
            <BillSection rows={details.consultations || []} emptyLabel="No outpatient bills" detailHeading="Service"
              formatCurrency={formatCurrency} formatDate={formatDate} onPrint={printBill} printingKey={printingKey} />
          </TabsContent>

          <TabsContent value="lab" className="space-y-4">
            {labCategoriesSummary.length > 0 && (
              <div className="border rounded-lg overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50 text-left text-xs text-gray-500">
                      <th className="px-3 py-2 font-medium">Category</th>
                      <th className="px-3 py-2 font-medium text-right">Rate</th>
                      <th className="px-3 py-2 font-medium text-right">Orders</th>
                      <th className="px-3 py-2 font-medium text-right">Bill value</th>
                      <th className="px-3 py-2 font-medium text-right">Amount earned</th>
                    </tr>
                  </thead>
                  <tbody>
                    {labCategoriesSummary.map((row) => (
                      <tr key={row.category_id ?? row.category_name} className="border-b last:border-b-0">
                        <td className="px-3 py-2 font-medium">{row.category_name}</td>
                        <td className="px-3 py-2 text-right">{row.percent}%</td>
                        <td className="px-3 py-2 text-right">{row.order_count}</td>
                        <td className="px-3 py-2 text-right">
                          {formatCurrency(row.billed)}
                          {row.base !== row.billed && <p className="text-[10px] text-gray-500">base {formatCurrency(row.base)}</p>}
                        </td>
                        <td className="px-3 py-2 text-right font-medium text-blue-700">{formatCurrency(row.commission)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <BillSection rows={details.lab_orders || []} emptyLabel="No lab bills" detailHeading="Lab category"
              formatCurrency={formatCurrency} formatDate={formatDate} onPrint={printBill} printingKey={printingKey} />
          </TabsContent>

          <TabsContent value="ip">
            <BillSection rows={details.inpatient_bills || []} emptyLabel="No inpatient bills" detailHeading="Bill"
              formatCurrency={formatCurrency} formatDate={formatDate} onPrint={printBill} printingKey={printingKey} />
          </TabsContent>

          <TabsContent value="pharmacy">
            <BillSection rows={details.pharmacy_sales || []} emptyLabel="No pharmacy sales" detailHeading="Sale"
              formatCurrency={formatCurrency} formatDate={formatDate} onPrint={printBill} printingKey={printingKey} />
          </TabsContent>

          <TabsContent value="payouts">
            <div className="flex justify-end mb-3">
              <Button size="sm" onClick={openPayDialog}>
                <Plus className="h-3 w-3 mr-1" /> Pay commission
              </Button>
            </div>
            {details.commissions.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-8">No commission payments recorded</p>
            ) : (
              <div className="border rounded-lg divide-y">
                {details.commissions.map(c => (
                  <div key={c.id} className="p-3 flex items-center justify-between text-sm">
                    <div>
                      <p className="font-medium text-green-700">{formatCurrency(c.amount)}</p>
                      <p className="text-xs text-gray-400">
                        {formatDate(c.payment_date)} | {c.payment_method} | by {c.paid_by}
                        {c.notes && <span> | {c.notes}</span>}
                      </p>
                    </div>
                    <Button size="sm" variant="ghost" className="h-7 text-xs text-red-400" onClick={() => deleteCommission(c.id)}>
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>

        {/* Commission Payment Dialog */}
        <Dialog open={showCommForm} onOpenChange={setShowCommForm}>
          <DialogContent className="max-w-sm">
            <DialogHeader><DialogTitle>Pay Commission — {selectedReferral.name}</DialogTitle></DialogHeader>
            <div className="space-y-3">
              <p className="text-sm text-gray-500">
                Balance due {formatCurrency(details.summary.commission_balance)}. The amount is filled with that balance and can be changed for a partial payout.
              </p>
              <div>
                <Label>Amount *</Label>
                <Input type="number" step="0.01" value={commForm.amount}
                  onChange={(e) => setCommForm({ ...commForm, amount: e.target.value })} placeholder="Enter amount" />
              </div>
              <div>
                <Label>Payment Method</Label>
                <Select value={commForm.payment_method} onValueChange={(v) => setCommForm({ ...commForm, payment_method: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="card">Card</SelectItem>
                    <SelectItem value="upi">UPI</SelectItem>
                    <SelectItem value="online">Online</SelectItem>
                    <SelectItem value="cheque">Cheque</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Notes</Label>
                <Textarea value={commForm.notes} onChange={(e) => setCommForm({ ...commForm, notes: e.target.value })}
                  placeholder="Optional notes" rows={2} />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowCommForm(false)}>Cancel</Button>
                <Button onClick={addCommission} disabled={!commForm.amount || commSaving}>
                  {commSaving && <Loader2 className="h-4 w-4 mr-1 animate-spin" />} Record Payment
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    );
  }

  // ===== LIST VIEW =====
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Referral Management</h1>
          <p className="text-muted-foreground text-sm">Manage referrals, set commission rates, and record payouts</p>
        </div>
        <Button onClick={() => openForm()}>
          <Plus className="h-4 w-4 mr-1" /> Add Referral
        </Button>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Card><CardContent className="pt-4 pb-3">
          <p className="text-xs text-gray-500 flex items-center gap-1"><Users className="h-3.5 w-3.5" /> Referrals</p>
          <p className="text-2xl font-bold">{dashboard.referral_count ?? 0}</p>
          <p className="text-xs text-gray-400">{dashboard.active_count ?? 0} active</p>
        </CardContent></Card>
        <Card><CardContent className="pt-4 pb-3">
          <p className="text-xs text-gray-500">Revenue generated</p>
          <p className="text-2xl font-bold">{formatCurrency(dashboard.revenue_generated)}</p>
        </CardContent></Card>
        <Card><CardContent className="pt-4 pb-3">
          <p className="text-xs text-gray-500">Commission earned</p>
          <p className="text-2xl font-bold text-blue-600">{formatCurrency(dashboard.commission_earned)}</p>
        </CardContent></Card>
        <Card><CardContent className="pt-4 pb-3">
          <p className="text-xs text-gray-500">Commission paid</p>
          <p className="text-2xl font-bold text-green-600">{formatCurrency(dashboard.commission_paid)}</p>
        </CardContent></Card>
        <Card><CardContent className="pt-4 pb-3">
          <p className="text-xs text-gray-500">Commission due</p>
          <p className={`text-2xl font-bold ${(dashboard.commission_due || 0) < 0 ? 'text-red-600' : 'text-orange-600'}`}>{formatCurrency(dashboard.commission_due)}</p>
        </CardContent></Card>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <Input placeholder="Search by name, village, mandal..." value={search}
          onChange={(e) => setSearch(e.target.value)} className="pl-10" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map(ref => (
          <Card key={ref.id} className={`cursor-pointer hover:shadow-md transition-shadow ${!ref.is_active ? 'opacity-50' : ''}`}
            onClick={() => ref.is_active && openDetails(ref)}>
            <CardContent className="pt-5 pb-4">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <h3 className="font-semibold text-base">{ref.name}</h3>
                  {ref.phone && (
                    <p className="text-sm text-gray-500 flex items-center gap-1 mt-0.5">
                      <Phone className="h-3 w-3" /> {ref.phone}
                    </p>
                  )}
                </div>
                {!ref.is_active && <Badge variant="secondary">Inactive</Badge>}
              </div>
              {(ref.village || ref.mandal || ref.district) && (
                <p className="text-xs text-gray-500 flex items-center gap-1 mb-1">
                  <MapPin className="h-3 w-3 flex-shrink-0" />
                  {[ref.village, ref.mandal, ref.district].filter(Boolean).join(', ')}
                </p>
              )}
              <p className="text-xs text-gray-500 mb-3">
                OP {ref.op_commission_pct ?? 0}% · Lab {ref.lab_commission_pct ?? 0}%
                {(ref.category_rates || []).length > 0 ? ` · ${ref.category_rates.length} lab categor${ref.category_rates.length === 1 ? 'y' : 'ies'}` : ''}
                {' · '}IP {ref.ip_commission_pct ?? 0}% · Pharmacy {ref.pharmacy_commission_pct ?? 0}%
              </p>
              <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
                <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => openDetails(ref)}>
                  <Eye className="h-3 w-3 mr-1" /> View
                </Button>
                {canEditReferral && (
                  <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => openForm(ref)}>
                    <Edit2 className="h-3 w-3 mr-1" /> Edit
                  </Button>
                )}
                {ref.is_active ? (
                  <Button size="sm" variant="ghost" className="h-7 text-xs text-red-500" onClick={() => deleteReferral(ref.id)}>
                    <Trash2 className="h-3 w-3 mr-1" /> Deactivate
                  </Button>
                ) : (
                  <Button size="sm" variant="ghost" className="h-7 text-xs text-green-600" onClick={() => reactivate(ref)}>
                    Reactivate
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
        {filtered.length === 0 && (
          <div className="col-span-full text-center py-12 text-gray-500">
            <Users className="h-10 w-10 mx-auto mb-2 text-gray-300" />
            <p>No referrals found. Click "Add Referral" to create one.</p>
          </div>
        )}
      </div>

      {/* Add/Edit Dialog */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Referral' : 'Add Referral'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Name *</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Person name" />
            </div>
            <div>
              <Label>Phone</Label>
              <Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="Phone number" />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div><Label>Village</Label><Input value={form.village} onChange={(e) => setForm({ ...form, village: e.target.value })} placeholder="Village" /></div>
              <div><Label>Mandal</Label><Input value={form.mandal} onChange={(e) => setForm({ ...form, mandal: e.target.value })} placeholder="Mandal" /></div>
              <div><Label>District</Label><Input value={form.district} onChange={(e) => setForm({ ...form, district: e.target.value })} placeholder="District" /></div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                ['op_commission_pct', 'OP %'],
                ['lab_commission_pct', 'Lab %'],
                ['ip_commission_pct', 'IP %'],
                ['pharmacy_commission_pct', 'Pharmacy %'],
              ].map(([key, label]) => (
                <div key={key}>
                  <Label>{key === 'lab_commission_pct' ? 'Lab % default' : label}</Label>
                  <Input type="number" min="0" max="100" step="0.01" value={form[key]}
                    onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
                </div>
              ))}
            </div>
            {labCategories.length > 0 && (
              <div className="space-y-2">
                <Label>Lab category %</Label>
                <p className="text-xs text-gray-500">Leave a category blank to use the Lab % default. Send-out orders use this percent of the invoice minus the partner cost.</p>
                <div className="border rounded-lg divide-y max-h-48 overflow-y-auto">
                  {labCategories.map((category) => (
                    <div key={category.id} className="p-2 flex items-center justify-between gap-3">
                      <span className="text-sm truncate">{category.name}</span>
                      <Input
                        type="number"
                        min="0"
                        max="100"
                        step="0.01"
                        className="w-24 h-8"
                        placeholder={form.lab_commission_pct || '0'}
                        value={categoryRates[category.id] ?? ''}
                        onChange={(e) => setCategoryRates((prev) => ({ ...prev, [category.id]: e.target.value }))}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}
            <p className="text-xs text-gray-500">Percent of each bill for patients registered with this referral. Patients keep the name saved at registration, so renaming this referral changes which patients match.</p>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowForm(false)}>Cancel</Button>
              <Button onClick={saveReferral} disabled={!form.name.trim() || saving}>
                {saving && <Loader2 className="h-4 w-4 mr-1 animate-spin" />} {editing ? 'Update' : 'Add'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ReferralManagementPage;
