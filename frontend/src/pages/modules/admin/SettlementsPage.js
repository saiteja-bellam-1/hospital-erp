import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Building2,
  CalendarRange,
  Eye,
  FileText,
  FlaskConical,
  IndianRupee,
  Loader2,
  Pill,
  RefreshCw,
  UtensilsCrossed,
} from 'lucide-react';
import { Card, CardContent } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
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

const SettlementsPage = () => {
  const [filters, setFilters] = useState(defaultPeriod);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [pdfPreview, setPdfPreview] = useState(null);

  const fetchSummary = async (period = filters) => {
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
      const response = await axios.get('/api/hospital/inpatient-settlements-summary', {
        params: { from: period.from, to: period.to },
      });
      setSummary(response.data);
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Unable to load the settlement summary.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const period = defaultPeriod();
    fetchSummary(period);
    // Load the current month once when this page opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openBillPreview = (bill) => {
    if (!bill?.admission_id || !bill?.bill_id) return;
    setPdfPreview({
      title: `Bill ${bill.bill_number}`,
      path: `/api/inpatient/admissions/${bill.admission_id}/bill/pdf`,
      params: { bill_id: bill.bill_id },
      filename: `${bill.bill_number || 'inpatient-bill'}.pdf`,
    });
  };

  const totals = summary?.totals || { lab: 0, pharmacy: 0, canteen: 0, hospital: 0, total: 0 };
  const bills = summary?.bills || [];

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 bg-gradient-to-r from-slate-950 via-slate-900 to-slate-800 px-6 py-6 text-white">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-300">
                <CalendarRange className="h-4 w-4" />
                Inpatient revenue view
              </div>
              <h2 className="text-2xl font-semibold tracking-tight">Settlement summary</h2>
              <p className="mt-1 max-w-2xl text-sm text-slate-300">
                See how completed inpatient bill lines divide between laboratory, pharmacy,
                canteen, and hospital services.
              </p>
            </div>
            <Badge className="w-fit border-white/20 bg-white/10 px-3 py-1 text-white hover:bg-white/10">
              {summary?.bill_count || 0} completed bill{summary?.bill_count === 1 ? '' : 's'}
            </Badge>
          </div>
        </div>

        <div className="grid gap-4 px-6 py-5 md:grid-cols-[1fr_1fr_auto] md:items-end">
          <div className="space-y-1.5">
            <Label htmlFor="settlement-from">From date</Label>
            <Input
              id="settlement-from"
              type="date"
              value={filters.from}
              max={filters.to}
              onChange={(event) => setFilters((current) => ({ ...current, from: event.target.value }))}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="settlement-to">To date</Label>
            <Input
              id="settlement-to"
              type="date"
              value={filters.to}
              min={filters.from}
              onChange={(event) => setFilters((current) => ({ ...current, to: event.target.value }))}
            />
          </div>
          <Button onClick={() => fetchSummary()} disabled={loading} className="md:min-w-32">
            {loading ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <RefreshCw className="mr-2 h-4 w-4" />
            )}
            Refresh
          </Button>
        </div>
      </section>

      {error && (
        <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </div>
      )}

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
        ) : bills.length === 0 ? (
          <div className="flex min-h-52 flex-col items-center justify-center px-6 text-center">
            <div className="mb-3 rounded-full bg-slate-100 p-3 text-slate-500">
              <FileText className="h-6 w-6" />
            </div>
            <p className="font-medium text-slate-800">No completed inpatient bills</p>
            <p className="mt-1 text-sm text-slate-500">Try a different date range.</p>
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
                {bills.map((bill) => (
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

      <PdfPreviewDialog
        open={!!pdfPreview}
        onClose={() => setPdfPreview(null)}
        title={pdfPreview?.title || 'Bill Preview'}
        path={pdfPreview?.path || null}
        params={pdfPreview?.params || {}}
        filename={pdfPreview?.filename || 'inpatient-bill.pdf'}
      />
    </div>
  );
};

export default SettlementsPage;
