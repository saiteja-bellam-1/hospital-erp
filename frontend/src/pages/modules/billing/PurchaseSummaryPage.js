import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '../../../components/ui/dropdown-menu';
import { ChevronDown, Download, FileSpreadsheet, FileText, Loader2 } from 'lucide-react';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';
import {
  BillingDateRange, MoneyTable, formatInr, defaultReportRange,
  rateAmountColumns, flattenRateRows,
} from './BillingReportControls';

export default function PurchaseSummaryPage() {
  const range = defaultReportRange();
  const [dateFrom, setDateFrom] = useState(range.from);
  const [dateTo, setDateTo] = useState(range.to);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [pdfOpen, setPdfOpen] = useState(false);

  const filterParams = useMemo(() => ({
    date_from: dateFrom,
    date_to: dateTo,
  }), [dateFrom, dateTo]);

  const run = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get('/api/hospital/billing/reports/purchase-summary', {
        params: filterParams,
      });
      setData(r.data);
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
      const res = await axios.get('/api/hospital/billing/reports/purchase-summary.xlsx', {
        params: filterParams,
        responseType: 'blob',
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `purchase_summary_${dateFrom}_to_${dateTo}.xlsx`;
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
  const invoiceRows = flattenRateRows(
    [
      ...(data?.invoices || []).map((r) => ({ ...r, kind: 'Purchase' })),
      ...(data?.returns || []).map((r) => ({ ...r, kind: 'Return' })),
    ],
    data?.tax_rate_columns,
    'amount',
  );
  const totalsFlat = flattenRateRows([t], data?.tax_rate_columns, 'amount')[0] || t;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Purchase Summary</h1>
          <p className="text-sm text-gray-600">
            Filter by date. Each rate column is billed amount at that GST %.
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
            <Button onClick={run} disabled={loading} size="sm" className="h-9">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Run'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {[
          ['Taxable', t.taxable],
          ['Tax', t.total_tax],
          ['Tax %', t.tax_pct, 'pct'],
          ['Grand total', t.grand_total],
          ['Documents', t.count, 'count'],
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
                { key: 'kind', label: 'Type' },
                { key: 'number', label: 'GRN' },
                { key: 'invoice_number', label: 'Supplier invoice' },
                { key: 'supplier', label: 'Supplier' },
                { key: 'gstin', label: 'GSTIN' },
                ...rateCols,
                { key: 'total_tax', label: 'Tax', align: 'right', money: true },
                { key: 'grand_total', label: 'Grand', align: 'right', money: true },
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
        path="/api/hospital/billing/reports/purchase-summary.pdf"
        params={filterParams}
        title="Purchase Summary PDF"
        filename={`purchase_summary_${dateFrom}_to_${dateTo}.pdf`}
        letterheadReportType="billing_purchase_summary"
      />
    </div>
  );
}
