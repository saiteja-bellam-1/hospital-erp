import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Label } from '../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '../../../components/ui/dropdown-menu';
import { ChevronDown, Download, FileSpreadsheet, FileText, Loader2 } from 'lucide-react';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';
import {
  BILLING_MODULES, BillingDateRange, MoneyTable, formatInr, defaultReportRange,
  rateAmountColumns, flattenRateRows, filterBillingModules,
} from './BillingReportControls';

export default function SalesSummaryPage() {
  const range = defaultReportRange();
  const [dateFrom, setDateFrom] = useState(range.from);
  const [dateTo, setDateTo] = useState(range.to);
  const [module, setModule] = useState('all');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [pdfOpen, setPdfOpen] = useState(false);
  const [enabledModules, setEnabledModules] = useState({});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await axios.get('/api/system/enabled-modules');
        const map = {};
        (res.data || []).forEach((m) => { map[m.module_name] = !!m.is_enabled; });
        if (!cancelled) setEnabledModules(map);
      } catch {
        if (!cancelled) setEnabledModules({});
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const moduleOptions = useMemo(
    () => (Object.keys(enabledModules).length
      ? filterBillingModules(enabledModules)
      : BILLING_MODULES),
    [enabledModules],
  );

  useEffect(() => {
    if (!moduleOptions.some((m) => m.id === module)) setModule('all');
  }, [moduleOptions, module]);

  const filterParams = useMemo(() => {
    const params = { date_from: dateFrom, date_to: dateTo };
    if (module && module !== 'all') params.module = module;
    return params;
  }, [dateFrom, dateTo, module]);

  const run = useCallback(async () => {
    setLoading(true);
    try {
      const sales = await axios.get('/api/hospital/billing/reports/sales-summary', { params: filterParams });
      setData(sales.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [filterParams]);

  useEffect(() => { run(); }, [run]);

  const downloadExcel = async () => {
    setExporting(true);
    try {
      const res = await axios.get('/api/hospital/billing/reports/sales-summary.xlsx', {
        params: filterParams,
        responseType: 'blob',
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `sales_summary_${dateFrom}_to_${dateTo}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
      alert('Could not export Excel');
    } finally {
      setExporting(false);
    }
  };

  const t = data?.totals || {};
  const rateCols = rateAmountColumns(data?.tax_rate_columns, 'amount');
  const invoiceRows = flattenRateRows(data?.invoices, data?.tax_rate_columns, 'amount');
  const totalsFlat = flattenRateRows([t], data?.tax_rate_columns, 'amount')[0] || t;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Sales Summary</h1>
          <p className="text-sm text-gray-600">
            Filter by date and module. Each rate column is billed amount at that GST %.
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" disabled={exporting || loading}>
              {exporting ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Download className="h-4 w-4 mr-1" />}
              Export
              <ChevronDown className="h-3.5 w-3.5 ml-1 opacity-70" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={() => setPdfOpen(true)}>
              <FileText className="h-4 w-4 mr-2" /> Export PDF
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => { downloadExcel(); }} disabled={exporting}>
              <FileSpreadsheet className="h-4 w-4 mr-2" /> Export Excel (.xlsx)
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[220px] flex-1">
              <BillingDateRange dateFrom={dateFrom} dateTo={dateTo} onFrom={setDateFrom} onTo={setDateTo} />
            </div>
            <div>
              <Label className="text-xs">Module</Label>
              <Select value={module} onValueChange={setModule}>
                <SelectTrigger className="w-[160px] h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {moduleOptions.map((m) => (
                    <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button onClick={run} disabled={loading} size="sm" className="h-9">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Run'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          ['Billed', t.billed],
          ['Taxable', t.taxable],
          ['Tax', t.tax],
          ['Tax %', t.tax_pct, 'pct'],
          ['Bills', t.count, 'count'],
        ].map(([label, val, kind]) => (
          <Card key={label}>
            <CardContent className="pt-4 pb-3">
              <div className="text-xs text-gray-500">{label}</div>
              <div className="text-lg font-semibold">
                {kind === 'count' ? (val || 0) : kind === 'pct' ? `${Number(val || 0).toFixed(2)}%` : formatInr(val)}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Invoices by tax rate</CardTitle>
          <p className="text-xs font-normal text-gray-500 mt-1">
            Each rate column is the billed amount (taxable + tax) for lines at that GST rate. Exempt = 0% GST.
          </p>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
          ) : (
            <MoneyTable
              columns={[
                { key: 'date', label: 'Date' },
                { key: 'number', label: 'Number' },
                { key: 'module_label', label: 'Module' },
                { key: 'party', label: 'Party' },
                ...rateCols,
                { key: 'tax', label: 'Tax', align: 'right', money: true },
                { key: 'billed', label: 'Grand', align: 'right', money: true },
                { key: 'status', label: 'Status' },
              ]}
              rows={invoiceRows}
              totals={totalsFlat}
            />
          )}
        </CardContent>
      </Card>

      <PdfPreviewDialog
        open={pdfOpen}
        onClose={() => setPdfOpen(false)}
        path="/api/hospital/billing/reports/sales-summary.pdf"
        params={filterParams}
        title="Sales Summary PDF"
        filename={`sales_summary_${dateFrom}_to_${dateTo}.pdf`}
        letterheadReportType="billing_sales_summary"
      />
    </div>
  );
}
