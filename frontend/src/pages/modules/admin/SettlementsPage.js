import React, { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Ban,
  Building2,
  Eye,
  FileText,
  FlaskConical,
  IndianRupee,
  Loader2,
  Percent,
  Pill,
  RefreshCw,
  Save,
  Search,
  Send,
  UtensilsCrossed,
} from 'lucide-react';
import { Card, CardContent } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../../components/ui/dialog';
import { useToast } from '../../../hooks/use-toast';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';

const toDateInput = (value) => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const defaultPeriod = () => {
  const today = new Date();
  return {
    from: toDateInput(new Date(today.getFullYear(), today.getMonth(), 1)),
    to: toDateInput(today),
  };
};

const formatCurrency = (value) =>
  new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(Number(value) || 0);

const formatBillDate = (value) => {
  if (!value) return '—';
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(new Date(value));
};

const summaryCards = [
  {
    key: 'lab',
    label: 'Laboratory',
    description: 'Diagnostic tests',
    icon: FlaskConical,
    accent: 'border-cyan-200 bg-cyan-50/70 text-cyan-800',
    iconClass: 'bg-cyan-100 text-cyan-700',
  },
  {
    key: 'pharmacy',
    label: 'Pharmacy',
    description: 'Medicines dispensed',
    icon: Pill,
    accent: 'border-emerald-200 bg-emerald-50/70 text-emerald-800',
    iconClass: 'bg-emerald-100 text-emerald-700',
  },
  {
    key: 'canteen',
    label: 'Canteen',
    description: 'Food and meals',
    icon: UtensilsCrossed,
    accent: 'border-orange-200 bg-orange-50/70 text-orange-900',
    iconClass: 'bg-orange-100 text-orange-800',
  },
  {
    key: 'hospital',
    label: 'Hospital',
    description: 'All other IP services',
    icon: Building2,
    accent: 'border-amber-200 bg-amber-50/70 text-amber-900',
    iconClass: 'bg-amber-100 text-amber-800',
  },
  {
    key: 'total',
    label: 'Combined total',
    description: 'Completed IP bill lines',
    icon: IndianRupee,
    accent: 'border-slate-300 bg-slate-900 text-white',
    iconClass: 'bg-white/10 text-white',
  },
];

const UNIT_META = {
  lab: {
    label: 'Laboratory',
    icon: FlaskConical,
    accent: 'border-cyan-200 bg-cyan-50/70 text-cyan-900',
    iconClass: 'bg-cyan-100 text-cyan-700',
  },
  pharmacy: {
    label: 'Pharmacy',
    icon: Pill,
    accent: 'border-emerald-200 bg-emerald-50/70 text-emerald-900',
    iconClass: 'bg-emerald-100 text-emerald-700',
  },
  canteen: {
    label: 'Canteen',
    icon: UtensilsCrossed,
    accent: 'border-orange-200 bg-orange-50/70 text-orange-900',
    iconClass: 'bg-orange-100 text-orange-800',
  },
};

const SETTLEABLE_UNITS = ['lab', 'pharmacy', 'canteen'];

const PAYMENT_METHODS = [
  { value: 'cash', label: 'Cash' },
  { value: 'bank_transfer', label: 'Bank Transfer' },
  { value: 'upi', label: 'UPI' },
  { value: 'cheque', label: 'Cheque' },
];

const statusBadgeClass = (status) =>
  status === 'cancelled'
    ? 'border-red-200 bg-red-50 text-red-700'
    : 'border-emerald-200 bg-emerald-50 text-emerald-700';

const SettlementsPage = () => {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState('summary');
  const [filters, setFilters] = useState(defaultPeriod);
  const [searchTerm, setSearchTerm] = useState('');
  const [summary, setSummary] = useState(null);
  const [settlements, setSettlements] = useState([]);
  const [rates, setRates] = useState({ lab: 100, pharmacy: 100, canteen: 100 });
  const [loading, setLoading] = useState(true);
  const [savingRates, setSavingRates] = useState(false);
  const [error, setError] = useState('');
  const [pdfPreview, setPdfPreview] = useState(null);

  const [recordUnit, setRecordUnit] = useState(null);
  const [recordForm, setRecordForm] = useState({
    payment_method: 'bank_transfer',
    payment_reference: '',
    payment_date: toDateInput(new Date()),
    notes: '',
  });
  const [submitting, setSubmitting] = useState(false);

  const fetchAll = async (period = filters) => {
    if (!period.from || !period.to) {
      setError('Choose both a from date and a to date.');
      return;
    }
    if (period.from > period.to) {
      setError('From date must be on or before the to date.');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const [summaryRes, settlementsRes] = await Promise.all([
        axios.get('/api/hospital/inpatient-settlements-summary', {
          params: { from: period.from, to: period.to },
        }),
        axios.get('/api/hospital/settlements'),
      ]);
      setSummary(summaryRes.data);
      setSettlements(settlementsRes.data?.settlements || []);
      if (summaryRes.data?.config) {
        setRates((current) => ({ ...current, ...summaryRes.data.config }));
      }
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Unable to load the settlement data.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll(defaultPeriod());
    // Load the current month once when this page opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveRates = async () => {
    const payload = {};
    for (const unit of SETTLEABLE_UNITS) {
      const value = Number(rates[unit]);
      if (Number.isNaN(value) || value < 0 || value > 100) {
        toast({ variant: 'destructive', title: 'Invalid rate', description: `${UNIT_META[unit].label} payout % must be between 0 and 100.` });
        return;
      }
      payload[unit] = value;
    }
    setSavingRates(true);
    try {
      await axios.put('/api/hospital/settlement-config', payload);
      toast({ title: 'Payout rates saved' });
      await fetchAll();
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      toast({ variant: 'destructive', title: 'Error', description: typeof detail === 'string' ? detail : 'Could not save payout rates.' });
    } finally {
      setSavingRates(false);
    }
  };

  const openBillPreview = (bill) => {
    if (!bill?.admission_id || !bill?.bill_id) return;
    setPdfPreview({
      title: `Bill ${bill.bill_number}`,
      path: `/api/inpatient/admissions/${bill.admission_id}/bill/pdf`,
      params: { bill_id: bill.bill_id },
      filename: `${bill.bill_number || 'inpatient-bill'}.pdf`,
    });
  };

  const openStatementPreview = (settlement) => {
    setPdfPreview({
      title: `Settlement ${settlement.settlement_number}`,
      path: `/api/hospital/settlements/${settlement.id}/pdf`,
      params: {},
      filename: `${settlement.settlement_number}.pdf`,
    });
  };

  const openRecordDialog = (unit) => {
    setRecordUnit(unit);
    setRecordForm({
      payment_method: 'bank_transfer',
      payment_reference: '',
      payment_date: toDateInput(new Date()),
      notes: '',
    });
  };

  const submitRecord = async () => {
    if (!recordUnit || !summary?.period) return;
    setSubmitting(true);
    try {
      const response = await axios.post('/api/hospital/settlements', {
        unit: recordUnit.unit,
        from: summary.period.from,
        to: summary.period.to,
        payment_method: recordForm.payment_method || null,
        payment_reference: recordForm.payment_reference || null,
        payment_date: recordForm.payment_date || null,
        notes: recordForm.notes || null,
      });
      toast({
        title: 'Settlement recorded',
        description: `${response.data.settlement_number} — ${formatCurrency(response.data.payout_amount)} to ${response.data.unit_label}`,
      });
      setRecordUnit(null);
      await fetchAll();
      openStatementPreview(response.data);
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      toast({ variant: 'destructive', title: 'Could not record settlement', description: typeof detail === 'string' ? detail : 'Please try again.' });
    } finally {
      setSubmitting(false);
    }
  };

  const cancelSettlement = async (settlement) => {
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Cancel settlement ${settlement.settlement_number}? This frees its period to be settled again.`)) {
      return;
    }
    try {
      await axios.post(`/api/hospital/settlements/${settlement.id}/cancel`, { reason: null });
      toast({ title: 'Settlement cancelled' });
      await fetchAll();
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      toast({ variant: 'destructive', title: 'Error', description: typeof detail === 'string' ? detail : 'Could not cancel settlement.' });
    }
  };

  const totals = summary?.totals || { lab: 0, pharmacy: 0, canteen: 0, hospital: 0, total: 0 };
  const bills = summary?.bills || [];

  const filteredBills = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    if (!query) return bills;
    return bills.filter((bill) =>
      [bill.bill_number, bill.patient_name, bill.patient_id, bill.admission_number]
        .some((field) => String(field || '').toLowerCase().includes(query)),
    );
  }, [bills, searchTerm]);

  const filteredSettlements = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    if (!query) return settlements;
    return settlements.filter((settlement) =>
      [settlement.settlement_number, settlement.unit_label, settlement.status]
        .some((field) => String(field || '').toLowerCase().includes(query)),
    );
  }, [settlements, searchTerm]);

  const units = useMemo(() => {
    if (summary?.units) return summary.units;
    return SETTLEABLE_UNITS.map((unit) => ({
      unit,
      unit_label: UNIT_META[unit].label,
      gross_amount: totals[unit] || 0,
      payout_percentage: rates[unit] || 0,
      payout_amount: 0,
      hospital_share: 0,
    }));
  }, [summary, totals, rates]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Settlements</h1>
          <p className="text-sm text-slate-500">
            Split inpatient revenue across business units and record payouts.
          </p>
        </div>
        <Button variant="outline" onClick={() => fetchAll()} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <Label htmlFor="settlement-from">From</Label>
              <Input
                id="settlement-from"
                type="date"
                value={filters.from}
                max={filters.to}
                onChange={(event) => setFilters((current) => ({ ...current, from: event.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="settlement-to">To</Label>
              <Input
                id="settlement-to"
                type="date"
                value={filters.to}
                min={filters.from}
                onChange={(event) => setFilters((current) => ({ ...current, to: event.target.value }))}
              />
            </div>
            <div className="flex-1 min-w-[220px]">
              <Label htmlFor="settlement-search">Search</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <Input
                  id="settlement-search"
                  className="pl-9"
                  placeholder="Bill, patient, settlement #..."
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-3 sm:w-auto sm:inline-grid">
          <TabsTrigger value="summary">Revenue Summary</TabsTrigger>
          <TabsTrigger value="payouts">Payouts</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        {/* ---------------- Revenue Summary tab ---------------- */}
        <TabsContent value="summary" className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {summaryCards.map(({ key, label, description, icon: Icon, accent, iconClass }) => (
              <Card key={key} className={`overflow-hidden shadow-none ${accent}`}>
                <CardContent className="p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider opacity-75">{label}</p>
                      <p className="mt-2 text-2xl font-bold tabular-nums">
                        {loading && !summary ? '—' : formatCurrency(totals[key])}
                      </p>
                      <p className="mt-1 text-xs opacity-70">{description}</p>
                    </div>
                    <div className={`rounded-lg p-2.5 ${iconClass}`}>
                      <Icon className="h-5 w-5" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <Card className="overflow-hidden">
            <div className="flex flex-col gap-2 border-b bg-slate-50/80 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="font-semibold text-slate-900">Completed inpatient bills</h3>
                <p className="text-sm text-slate-500">Category amounts are based on saved bill line totals.</p>
              </div>
              {summary?.period && (
                <span className="text-xs font-medium text-slate-500">
                  {formatBillDate(`${summary.period.from}T00:00:00`)} – {formatBillDate(`${summary.period.to}T00:00:00`)}
                </span>
              )}
            </div>

            {loading && !summary ? (
              <div className="flex min-h-52 items-center justify-center text-sm text-slate-500">
                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                Loading settlement figures…
              </div>
            ) : filteredBills.length === 0 ? (
              <div className="flex min-h-52 flex-col items-center justify-center px-6 text-center">
                <div className="mb-3 rounded-full bg-slate-100 p-3 text-slate-500">
                  <FileText className="h-6 w-6" />
                </div>
                <p className="font-medium text-slate-800">No completed inpatient bills</p>
                <p className="mt-1 text-sm text-slate-500">
                  {searchTerm ? 'No bills match your search.' : 'Try a different date range.'}
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[1000px] text-sm">
                  <thead>
                    <tr className="border-b bg-white text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="px-6 py-3 font-semibold">Bill</th>
                      <th className="px-4 py-3 font-semibold">Patient</th>
                      <th className="px-4 py-3 font-semibold">Admission</th>
                      <th className="px-4 py-3 text-right font-semibold">Lab</th>
                      <th className="px-4 py-3 text-right font-semibold">Pharmacy</th>
                      <th className="px-4 py-3 text-right font-semibold">Canteen</th>
                      <th className="px-4 py-3 text-right font-semibold">Hospital</th>
                      <th className="px-4 py-3 text-right font-semibold">Total</th>
                      <th className="px-6 py-3 text-right font-semibold">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredBills.map((bill) => (
                      <tr key={bill.bill_id} className="transition-colors hover:bg-slate-50">
                        <td className="px-6 py-4">
                          <p className="font-medium text-slate-900">{bill.bill_number}</p>
                          <p className="mt-0.5 text-xs text-slate-500">{formatBillDate(bill.bill_date)}</p>
                        </td>
                        <td className="px-4 py-4">
                          <p className="font-medium text-slate-800">{bill.patient_name || 'Unknown'}</p>
                          <p className="mt-0.5 text-xs text-slate-500">{bill.patient_id || '—'}</p>
                        </td>
                        <td className="px-4 py-4 text-slate-600">
                          {bill.admission_number || (bill.admission_id ? `#${bill.admission_id}` : '—')}
                        </td>
                        <td className="px-4 py-4 text-right tabular-nums text-cyan-800">
                          {formatCurrency(bill.lab)}
                        </td>
                        <td className="px-4 py-4 text-right tabular-nums text-emerald-800">
                          {formatCurrency(bill.pharmacy)}
                        </td>
                        <td className="px-4 py-4 text-right tabular-nums text-orange-900">
                          {formatCurrency(bill.canteen)}
                        </td>
                        <td className="px-4 py-4 text-right tabular-nums text-amber-900">
                          {formatCurrency(bill.hospital)}
                        </td>
                        <td className="px-4 py-4 text-right font-semibold tabular-nums text-slate-900">
                          {formatCurrency(bill.total)}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={!bill.admission_id || !bill.bill_id}
                            onClick={() => openBillPreview(bill)}
                          >
                            <Eye className="mr-1.5 h-3.5 w-3.5" />
                            View
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </TabsContent>

        {/* ---------------- Payouts tab ---------------- */}
        <TabsContent value="payouts" className="space-y-6">
          {/* Unit payout cards */}
          <div className="grid gap-4 lg:grid-cols-3">
            {units.map((unitRow) => {
              const meta = UNIT_META[unitRow.unit] || UNIT_META.lab;
              const Icon = meta.icon;
              return (
                <Card key={unitRow.unit} className={`overflow-hidden shadow-none ${meta.accent}`}>
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wider opacity-75">{unitRow.unit_label}</p>
                        <p className="mt-2 text-2xl font-bold tabular-nums">
                          {loading && !summary ? '—' : formatCurrency(unitRow.payout_amount)}
                        </p>
                        <p className="mt-1 text-xs opacity-70">
                          Gross {formatCurrency(unitRow.gross_amount)} · {Number(unitRow.payout_percentage)}% payout
                        </p>
                      </div>
                      <div className={`rounded-lg p-2.5 ${meta.iconClass}`}>
                        <Icon className="h-5 w-5" />
                      </div>
                    </div>
                    <Button
                      size="sm"
                      className="mt-4 w-full bg-slate-900 text-white hover:bg-slate-800"
                      disabled={loading || !summary || (unitRow.gross_amount || 0) <= 0}
                      onClick={() => openRecordDialog(unitRow)}
                    >
                      <Send className="mr-1.5 h-3.5 w-3.5" />
                      Record payout
                    </Button>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* Recorded settlements */}
          <Card className="overflow-hidden">
            <div className="flex flex-col gap-2 border-b bg-slate-50/80 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="font-semibold text-slate-900">Recorded settlements</h3>
                <p className="text-sm text-slate-500">Payouts already sent to business units.</p>
              </div>
            </div>
            {filteredSettlements.length === 0 ? (
              <div className="flex min-h-32 flex-col items-center justify-center px-6 py-8 text-center">
                <p className="text-sm text-slate-500">
                  {settlements.length === 0
                    ? 'No settlements recorded yet.'
                    : 'No settlements match your search.'}
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px] text-sm">
                  <thead>
                    <tr className="border-b bg-white text-left text-xs uppercase tracking-wide text-slate-500">
                      <th className="px-6 py-3 font-semibold">Settlement</th>
                      <th className="px-4 py-3 font-semibold">Unit</th>
                      <th className="px-4 py-3 font-semibold">Period</th>
                      <th className="px-4 py-3 text-right font-semibold">Gross</th>
                      <th className="px-4 py-3 text-right font-semibold">Payout</th>
                      <th className="px-4 py-3 font-semibold">Status</th>
                      <th className="px-6 py-3 text-right font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredSettlements.map((settlement) => (
                      <tr key={settlement.id} className="transition-colors hover:bg-slate-50">
                        <td className="px-6 py-4">
                          <p className="font-medium text-slate-900">{settlement.settlement_number}</p>
                          <p className="mt-0.5 text-xs text-slate-500">{formatBillDate(settlement.created_at)}</p>
                        </td>
                        <td className="px-4 py-4 text-slate-700">{settlement.unit_label}</td>
                        <td className="px-4 py-4 text-slate-600">
                          {formatBillDate(`${settlement.period_from}T00:00:00`)} – {formatBillDate(`${settlement.period_to}T00:00:00`)}
                        </td>
                        <td className="px-4 py-4 text-right tabular-nums text-slate-600">
                          {formatCurrency(settlement.gross_amount)}
                        </td>
                        <td className="px-4 py-4 text-right font-semibold tabular-nums text-slate-900">
                          {formatCurrency(settlement.payout_amount)}
                          <span className="ml-1 text-xs font-normal text-slate-400">({Number(settlement.payout_percentage)}%)</span>
                        </td>
                        <td className="px-4 py-4">
                          <Badge variant="outline" className={statusBadgeClass(settlement.status)}>
                            {settlement.status === 'cancelled' ? 'Cancelled' : 'Paid'}
                          </Badge>
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center justify-end gap-2">
                            <Button type="button" size="sm" variant="outline" onClick={() => openStatementPreview(settlement)}>
                              <FileText className="mr-1.5 h-3.5 w-3.5" />
                              Statement
                            </Button>
                            {settlement.status !== 'cancelled' && (
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                className="border-red-200 text-red-700 hover:bg-red-50"
                                onClick={() => cancelSettlement(settlement)}
                              >
                                <Ban className="mr-1.5 h-3.5 w-3.5" />
                                Cancel
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
          </Card>
        </TabsContent>

        {/* ---------------- Settings tab ---------------- */}
        <TabsContent value="settings" className="space-y-6">
          <Card className="overflow-hidden">
            <div className="flex flex-col gap-1 border-b bg-slate-50/80 px-6 py-4">
              <div className="flex items-center gap-2">
                <Percent className="h-4 w-4 text-slate-500" />
                <h3 className="font-semibold text-slate-900">Payout rates</h3>
              </div>
              <p className="text-sm text-slate-500">
                Share of each unit&apos;s revenue paid out to that unit. The hospital keeps the remainder as commission.
              </p>
            </div>
            <CardContent className="grid gap-4 p-6 sm:grid-cols-3 lg:grid-cols-[repeat(3,minmax(0,1fr))_auto] lg:items-end">
              {SETTLEABLE_UNITS.map((unit) => (
                <div key={unit} className="space-y-1.5">
                  <Label htmlFor={`rate-${unit}`}>{UNIT_META[unit].label} payout %</Label>
                  <div className="relative">
                    <Input
                      id={`rate-${unit}`}
                      type="number"
                      min={0}
                      max={100}
                      step="0.01"
                      value={rates[unit] ?? ''}
                      onChange={(event) => setRates((current) => ({ ...current, [unit]: event.target.value }))}
                      className="pr-8"
                    />
                    <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm text-slate-400">%</span>
                  </div>
                </div>
              ))}
              <Button variant="outline" onClick={saveRates} disabled={savingRates} className="lg:min-w-32">
                {savingRates ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                Save rates
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Record payout dialog */}
      <Dialog open={!!recordUnit} onOpenChange={(open) => !open && setRecordUnit(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Record {recordUnit?.unit_label} payout</DialogTitle>
            <DialogDescription>
              {summary?.period && (
                <>Period {formatBillDate(`${summary.period.from}T00:00:00`)} – {formatBillDate(`${summary.period.to}T00:00:00`)}</>
              )}
            </DialogDescription>
          </DialogHeader>

          {recordUnit && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-center">
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500">Gross</p>
                  <p className="mt-1 font-semibold tabular-nums text-slate-900">{formatCurrency(recordUnit.gross_amount)}</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500">Payout %</p>
                  <p className="mt-1 font-semibold tabular-nums text-slate-900">{Number(recordUnit.payout_percentage)}%</p>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500">Payable</p>
                  <p className="mt-1 font-semibold tabular-nums text-emerald-700">{formatCurrency(recordUnit.payout_amount)}</p>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="record-method">Payment method</Label>
                <select
                  id="record-method"
                  value={recordForm.payment_method}
                  onChange={(event) => setRecordForm((current) => ({ ...current, payment_method: event.target.value }))}
                  className="flex h-10 w-full items-center rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                >
                  {PAYMENT_METHODS.map((method) => (
                    <option key={method.value} value={method.value}>{method.label}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="record-ref">Reference</Label>
                  <Input
                    id="record-ref"
                    value={recordForm.payment_reference}
                    onChange={(event) => setRecordForm((current) => ({ ...current, payment_reference: event.target.value }))}
                    placeholder="Txn / cheque #"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="record-date">Payment date</Label>
                  <Input
                    id="record-date"
                    type="date"
                    value={recordForm.payment_date}
                    onChange={(event) => setRecordForm((current) => ({ ...current, payment_date: event.target.value }))}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="record-notes">Notes</Label>
                <textarea
                  id="record-notes"
                  rows={2}
                  value={recordForm.notes}
                  onChange={(event) => setRecordForm((current) => ({ ...current, notes: event.target.value }))}
                  className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                  placeholder="Optional"
                />
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setRecordUnit(null)} disabled={submitting}>Cancel</Button>
            <Button onClick={submitRecord} disabled={submitting}>
              {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
              Record &amp; generate statement
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <PdfPreviewDialog
        open={!!pdfPreview}
        onClose={() => setPdfPreview(null)}
        title={pdfPreview?.title || 'Preview'}
        path={pdfPreview?.path || null}
        params={pdfPreview?.params || {}}
        filename={pdfPreview?.filename || 'document.pdf'}
      />
    </div>
  );
};

export default SettlementsPage;
