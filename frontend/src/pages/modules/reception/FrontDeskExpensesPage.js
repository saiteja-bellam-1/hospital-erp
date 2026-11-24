import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Loader2 } from 'lucide-react';
import { MoneyTable, formatInr } from '../billing/BillingReportControls';
import { localDateString } from '../../../utils/localDate';
import FrontDeskExpensesPanel from './FrontDeskExpensesPanel';

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
  return METHOD_LABELS[key] || key.replace(/_/g, ' ');
}

export default function FrontDeskExpensesPage() {
  const today = localDateString();
  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo, setDateTo] = useState(today);
  const [breakdown, setBreakdown] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadBreakdown = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await axios.get('/api/hospital/billing/reports/daily-collection', {
        params: { date_from: dateFrom, date_to: dateTo },
      });
      setBreakdown(res.data);
    } catch (err) {
      setBreakdown(null);
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Could not load the daily breakdown.');
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo]);

  useEffect(() => { loadBreakdown(); }, [loadBreakdown]);

  const totals = breakdown?.totals || {};
  const rows = (breakdown?.rows || []).map((row) => ({
    ...row,
    ...Object.fromEntries((breakdown?.methods || []).map((method) => [`m_${method}`, row.by_method?.[method] || 0])),
  }));

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Front-desk expenses</h1>
        <p className="text-sm text-gray-600">
          Record money paid out at the desk. It is deducted from the daily breakdown for these dates.
        </p>
      </div>

      <Card>
        <CardContent className="pt-4 pb-4">
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <Label className="text-xs">From</Label>
              <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-[150px] h-9" />
            </div>
            <div>
              <Label className="text-xs">To</Label>
              <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-[150px] h-9" />
            </div>
            <Button type="button" variant="outline" className="h-9" onClick={() => { setDateFrom(today); setDateTo(today); }}>
              Today
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && (
        <div className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Card>
          <CardContent className="pt-4 pb-3">
            <div className="text-xs text-gray-500">Collected</div>
            <div className="text-lg font-semibold">{formatInr(totals.net_collected)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-3">
            <div className="text-xs text-gray-500">Expenses</div>
            <div className="text-lg font-semibold">{formatInr(totals.expenses)}</div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4 pb-3">
            <div className="text-xs text-gray-500">Net</div>
            <div className="text-lg font-semibold">{formatInr(totals.net_after_expenses)}</div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Daily breakdown</CardTitle>
          <p className="text-xs font-normal text-gray-500 mt-1">
            Collected is money received after refunds. Net is collected minus front-desk expenses.
          </p>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          ) : (
            <MoneyTable
              columns={[
                { key: 'date', label: 'Date' },
                ...(breakdown?.methods || []).map((method) => ({
                  key: `m_${method}`, label: methodLabel(method), align: 'right', money: true,
                })),
                { key: 'refunds', label: 'Refunds', align: 'right', money: true },
                { key: 'total', label: 'Collected', align: 'right', money: true },
                { key: 'expenses', label: 'Expenses', align: 'right', money: true },
                { key: 'net', label: 'Net', align: 'right', money: true },
              ]}
              rows={rows}
              totals={{
                total: totals.net_collected,
                refunds: totals.refunds,
                expenses: totals.expenses,
                net: totals.net_after_expenses,
                ...Object.fromEntries((breakdown?.methods || []).map((method) => [
                  `m_${method}`,
                  (breakdown?.rows || []).reduce((sum, row) => sum + Number(row.by_method?.[method] || 0), 0),
                ])),
              }}
            />
          )}
        </CardContent>
      </Card>

      <FrontDeskExpensesPanel dateFrom={dateFrom} dateTo={dateTo} onChanged={loadBreakdown} />
    </div>
  );
}
