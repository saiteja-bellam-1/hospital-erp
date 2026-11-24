import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import ActionKpiCard from '../../../components/dashboard/ActionKpiCard';
import { Banknote, Receipt, RefreshCw, Wallet, AlertCircle } from 'lucide-react';
import { BillingDateRange, formatInr } from './BillingReportControls';
import { localDateString } from '../../../utils/localDate';

const METHOD_LABELS = {
  cash: 'Cash',
  card: 'Card',
  upi: 'UPI',
  cheque: 'Cheque',
  online: 'Online',
  insurance: 'Insurance',
  bank_transfer: 'Bank transfer',
};

function methodLabel(method) {
  const key = String(method || '').trim().toLowerCase();
  if (!key) return 'Other';
  return METHOD_LABELS[key] || key.replace(/_/g, ' ');
}

function statusLabel(status) {
  const text = String(status || '').replace(/_/g, ' ').trim();
  if (!text) return '—';
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function errorMessage(err, fallback) {
  const detail = err?.response?.data?.detail;
  return typeof detail === 'string' ? detail : fallback;
}

function reportPath(kind, dateFrom, dateTo, extra = {}) {
  const params = new URLSearchParams({ kind, date_from: dateFrom, date_to: dateTo });
  Object.entries(extra).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  return `/dashboard/billing/reports?${params.toString()}`;
}

function InvoiceRows({ rows, empty, showOutstanding }) {
  if (!rows?.length) {
    return <p className="text-sm text-gray-500 py-6 text-center">{empty}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500">
            <th className="pb-2 pr-3 font-medium">Bill</th>
            <th className="pb-2 pr-3 font-medium">Patient</th>
            <th className="pb-2 pr-3 font-medium">Module</th>
            <th className="pb-2 pr-3 text-right font-medium">Billed</th>
            {showOutstanding && <th className="pb-2 pr-3 text-right font-medium">Due</th>}
            <th className="pb-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.module}-${row.number}-${row.date}`} className="border-b last:border-0">
              <td className="py-2 pr-3">
                <div className="font-mono text-xs">{row.number || '—'}</div>
                <div className="text-xs text-gray-500">{row.date || ''}</div>
              </td>
              <td className="py-2 pr-3">{row.party || '—'}</td>
              <td className="py-2 pr-3 text-xs">{row.module_label || '—'}</td>
              <td className="py-2 pr-3 text-right tabular-nums">{formatInr(row.billed)}</td>
              {showOutstanding && (
                <td className="py-2 pr-3 text-right tabular-nums text-amber-700">{formatInr(row.outstanding)}</td>
              )}
              <td className="py-2">
                <Badge variant="outline">{statusLabel(row.status)}</Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function BillingDashboardPage() {
  const navigate = useNavigate();
  const today = localDateString();
  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo, setDateTo] = useState(today);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!dateFrom || !dateTo) return;
    setLoading(true);
    setError('');
    try {
      const res = await axios.get('/api/hospital/billing/dashboard', {
        params: { date_from: dateFrom, date_to: dateTo },
      });
      setData(res.data);
    } catch (err) {
      setData(null);
      setError(errorMessage(err, 'Could not load the billing dashboard.'));
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  const totals = data?.totals || {};
  const methods = data?.methods || [];
  const byMethod = data?.by_method || {};
  const modules = data?.by_module || [];
  const trend = data?.trend || [];
  const maxMethod = Math.max(...methods.map((key) => Math.abs(Number(byMethod[key] || 0))), 1);
  const maxModule = Math.max(...modules.map((row) => Number(row.billed || 0)), 1);
  const maxTrend = Math.max(...trend.map((row) => Math.max(Number(row.billed || 0), Number(row.collected || 0))), 1);
  const topDoctor = Number(data?.top_doctors?.[0]?.total_revenue || 0) || 1;

  const openReport = (kind, extra) => navigate(reportPath(kind, dateFrom, dateTo, extra));

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Billing dashboard</h1>
          <p className="text-sm text-gray-600">
            Billed amounts follow the sales register. Net receipts follow daily collection for the same dates.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => navigate('/dashboard/billing')}>Bills</Button>
          <Button size="sm" variant="outline" onClick={() => openReport('sales')}>Reports</Button>
          <Button size="sm" variant="outline" onClick={load} disabled={loading} aria-label="Refresh">
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="pt-4">
          <BillingDateRange dateFrom={dateFrom} dateTo={dateTo} onFrom={setDateFrom} onTo={setDateTo} />
        </CardContent>
      </Card>

      {error && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 [&_.text-3xl]:text-2xl [&_.truncate]:whitespace-normal">
        <ActionKpiCard
          icon={Receipt}
          label="Billed"
          value={formatInr(totals.billed)}
          sub={`${totals.count || 0} bills`}
          tone="blue"
          onClick={() => openReport('sales')}
        />
        <ActionKpiCard
          icon={Wallet}
          label="Collected"
          value={formatInr(totals.collected)}
          sub="Applied to those bills"
          tone="green"
          onClick={() => openReport('sales')}
        />
        <ActionKpiCard
          icon={AlertCircle}
          label="Outstanding"
          value={formatInr(totals.outstanding)}
          sub="Still due on those bills"
          tone="amber"
          onClick={() => openReport('outstanding')}
        />
        <ActionKpiCard
          icon={Banknote}
          label="Net receipts"
          value={formatInr(totals.net_after_expenses ?? totals.net_receipts)}
          sub={Number(totals.expenses) > 0
            ? `After expenses ${formatInr(totals.expenses)}`
            : (Number(totals.refunds) > 0 ? `Refunds ${formatInr(totals.refunds)}` : 'Cash in by tender')}
          tone="cyan"
          onClick={() => openReport('daily-collection')}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Receipts by tender</CardTitle>
            <Button size="sm" variant="ghost" className="h-8" onClick={() => openReport('daily-collection')}>
              Daily collection
            </Button>
          </CardHeader>
          <CardContent>
            {methods.length === 0 ? (
              <p className="text-sm text-gray-500 py-6 text-center">No receipts in this period.</p>
            ) : (
              <div className="space-y-3">
                {methods.map((key) => {
                  const amount = Number(byMethod[key] || 0);
                  const width = Math.max(4, (Math.abs(amount) / maxMethod) * 100);
                  return (
                    <div key={key}>
                      <div className="flex justify-between text-sm mb-1">
                        <span>{methodLabel(key)}</span>
                        <span className="tabular-nums font-medium">{formatInr(amount)}</span>
                      </div>
                      <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                        <div
                          className={`h-full rounded-full ${amount < 0 ? 'bg-rose-400' : 'bg-cyan-500'}`}
                          style={{ width: `${width}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Billed by department</CardTitle>
            <Button size="sm" variant="ghost" className="h-8" onClick={() => openReport('sales')}>
              Sales register
            </Button>
          </CardHeader>
          <CardContent>
            {modules.length === 0 ? (
              <p className="text-sm text-gray-500 py-6 text-center">No bills in this period.</p>
            ) : (
              <div className="space-y-3">
                {modules.map((row) => (
                  <button
                    key={row.module}
                    type="button"
                    className="w-full text-left"
                    onClick={() => openReport('sales', { module: row.module })}
                  >
                    <div className="flex justify-between text-sm mb-1 gap-3">
                      <span className="font-medium">{row.module_label}</span>
                      <span className="tabular-nums">
                        {formatInr(row.billed)}
                        <span className="text-gray-500"> · {row.count}</span>
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-blue-500"
                        style={{ width: `${Math.max(4, (Number(row.billed || 0) / maxModule) * 100)}%` }}
                      />
                    </div>
                    {Number(row.outstanding) > 0.005 && (
                      <div className="text-xs text-amber-700 mt-1">Due {formatInr(row.outstanding)}</div>
                    )}
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Billed and collected by day</CardTitle>
        </CardHeader>
        <CardContent>
          {trend.length === 0 ? (
            <p className="text-sm text-gray-500 py-6 text-center">No bills in this period.</p>
          ) : (
            <>
              <div className="flex gap-4 text-xs text-gray-500 mb-3">
                <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-blue-500" /> Billed</span>
                <span className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-emerald-500" /> Collected</span>
              </div>
              <div className="flex items-end gap-2 overflow-x-auto pb-1">
                {trend.map((row) => (
                  <div key={row.date} className="flex flex-col items-center min-w-[42px] flex-1" title={`${row.date}: billed ${formatInr(row.billed)}, collected ${formatInr(row.collected)}`}>
                    <div className="h-28 w-full flex items-end justify-center gap-0.5">
                      <div
                        className="w-2.5 bg-blue-500 rounded-t"
                        style={{ height: `${Math.max(2, (Number(row.billed || 0) / maxTrend) * 100)}%` }}
                      />
                      <div
                        className="w-2.5 bg-emerald-500 rounded-t"
                        style={{ height: `${Math.max(2, (Number(row.collected || 0) / maxTrend) * 100)}%` }}
                      />
                    </div>
                    <div className="text-[10px] text-gray-500 mt-1">{String(row.date || '').slice(5)}</div>
                  </div>
                ))}
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Top doctors</CardTitle>
            <Button size="sm" variant="ghost" className="h-8" onClick={() => openReport('doctor-revenue')}>
              Doctor revenue
            </Button>
          </CardHeader>
          <CardContent>
            {(data?.top_doctors || []).length === 0 ? (
              <p className="text-sm text-gray-500 py-6 text-center">No doctor revenue in this period.</p>
            ) : (
              <div className="space-y-3">
                {data.top_doctors.map((row) => (
                  <div key={row.doctor_id ?? row.doctor_name}>
                    <div className="flex justify-between text-sm mb-1 gap-3">
                      <span>{row.doctor_name || '—'}</span>
                      <span className="tabular-nums font-medium">{formatInr(row.total_revenue)}</span>
                    </div>
                    <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-purple-500"
                        style={{ width: `${Math.max(4, (Number(row.total_revenue || 0) / topDoctor) * 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2 flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">Largest balances</CardTitle>
            <Button size="sm" variant="ghost" className="h-8" onClick={() => openReport('outstanding')}>
              Outstanding
            </Button>
          </CardHeader>
          <CardContent>
            <InvoiceRows
              rows={data?.outstanding_invoices}
              empty="Nothing outstanding in this period."
              showOutstanding
            />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Recent bills</CardTitle>
        </CardHeader>
        <CardContent>
          <InvoiceRows rows={data?.recent} empty="No bills in this period." />
        </CardContent>
      </Card>
    </div>
  );
}
