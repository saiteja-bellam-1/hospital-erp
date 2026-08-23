import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Label } from '../../../components/ui/label';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '../../../components/ui/dropdown-menu';
import { ChevronDown, Download, FileSpreadsheet, FileText, Loader2 } from 'lucide-react';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';
import {
  BillingDateRange, GstScopeChips, MoneyTable, GstinBanner, defaultReportRange,
} from './BillingReportControls';
import { Gst3bTables } from './GstReturnPreview';

const KINDS = [
  { id: 'outward', label: 'Outward HSN', slug: 'outward-hsn' },
  { id: 'inward', label: 'Inward HSN', slug: 'inward-hsn' },
  { id: 'b2b', label: 'B2B / B2C', slug: 'b2b-b2c' },
  { id: 'exempt', label: 'Exempt (SAC 9993)', slug: 'exempt' },
  { id: 'gstr3b', label: 'GSTR-3B summary', slug: 'gstr3b' },
];

export default function GstReportsPage() {
  const range = defaultReportRange();
  const [dateFrom, setDateFrom] = useState(range.from);
  const [dateTo, setDateTo] = useState(range.to);
  const [kind, setKind] = useState('outward');
  const [module, setModule] = useState('all');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [pdfOpen, setPdfOpen] = useState(false);

  const filterParams = useMemo(() => {
    const params = { date_from: dateFrom, date_to: dateTo };
    if (module && module !== 'all') params.module = module;
    return params;
  }, [dateFrom, dateTo, module]);

  const kindMeta = KINDS.find((k) => k.id === kind) || KINDS[0];
  const exportBase = `/api/hospital/billing/reports/gst/${kindMeta.slug}`;
  const fileStem = `gst_${kindMeta.slug.replace(/-/g, '_')}_${module || 'all'}_${dateFrom}_to_${dateTo}`;
  const letterheadReportType = kind === 'gstr3b' ? 'billing_gstr3b' : 'billing_gst_reports';

  const run = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(exportBase, { params: filterParams });
      setData(r.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [exportBase, filterParams]);

  useEffect(() => { run(); }, [run]);

  const downloadExcel = async () => {
    setExporting(true);
    try {
      const res = await axios.get(`${exportBase}.xlsx`, {
        params: filterParams,
        responseType: 'blob',
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${fileStem}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
      alert('Could not export Excel');
    } finally {
      setExporting(false);
    }
  };

  const hsnCols = [
    { key: 'hsn_code', label: 'HSN' },
    { key: 'sgst_pct', label: 'SGST %', align: 'right' },
    { key: 'cgst_pct', label: 'CGST %', align: 'right' },
    { key: 'igst_pct', label: 'IGST %', align: 'right' },
    { key: 'taxable_value', label: 'Taxable', align: 'right', money: true },
    { key: 'sgst_amount', label: 'SGST', align: 'right', money: true },
    { key: 'cgst_amount', label: 'CGST', align: 'right', money: true },
    { key: 'igst_amount', label: 'IGST', align: 'right', money: true },
    { key: 'total_tax', label: 'Total tax', align: 'right', money: true },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">GST Reports</h1>
          <p className="text-sm text-gray-600">
            Pharmacy taxable outward / inward (HSN) plus exempt healthcare services (SAC 9993).
            Group by GST registration: Lab and Pharmacy stay independent; everything else is Hospital GST.
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
        <CardContent className="pt-4 space-y-3">
          <div className="flex flex-wrap items-end gap-x-3 gap-y-3">
            <BillingDateRange
              dateFrom={dateFrom}
              dateTo={dateTo}
              onFrom={setDateFrom}
              onTo={setDateTo}
              className="contents"
            />
            <div>
              <Label className="text-xs">Report</Label>
              <Select value={kind} onValueChange={setKind}>
                <SelectTrigger className="w-[200px] h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {KINDS.map((k) => <SelectItem key={k.id} value={k.id}>{k.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">GST registration</Label>
              <div className="mt-1">
                <GstScopeChips value={module} onChange={setModule} />
              </div>
            </div>
          </div>
          <GstinBanner data={data} module={module} />
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>
      ) : kind === 'gstr3b' && data ? (
        <Gst3bTables data={data} />
      ) : kind === 'b2b' && data ? (
        <>
          <Card>
            <CardHeader><CardTitle className="text-base">B2B invoices (customer GSTIN present)</CardTitle></CardHeader>
            <CardContent>
              <MoneyTable
                columns={[
                  { key: 'date', label: 'Date' },
                  { key: 'number', label: 'Invoice' },
                  { key: 'party', label: 'Customer' },
                  { key: 'gstin', label: 'GSTIN' },
                  { key: 'hsn_code', label: 'HSN' },
                  { key: 'taxable_value', label: 'Taxable', align: 'right', money: true },
                  { key: 'total_tax', label: 'Tax', align: 'right', money: true },
                ]}
                rows={data.b2b || []}
              />
              {!(data.b2b || []).length && (
                <p className="text-sm text-gray-500 mt-2">No B2B sales — add a patient GSTIN for corporate / ITC invoices.</p>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">B2C rate-wise</CardTitle></CardHeader>
            <CardContent>
              <MoneyTable
                columns={[
                  { key: 'rate', label: 'Rate %' },
                  { key: 'invoice_count', label: 'Invoices', align: 'right' },
                  { key: 'taxable_value', label: 'Taxable', align: 'right', money: true },
                  { key: 'sgst_amount', label: 'SGST', align: 'right', money: true },
                  { key: 'cgst_amount', label: 'CGST', align: 'right', money: true },
                  { key: 'igst_amount', label: 'IGST', align: 'right', money: true },
                ]}
                rows={data.b2c || []}
              />
            </CardContent>
          </Card>
        </>
      ) : kind === 'exempt' && data ? (
        <>
          <Card>
            <CardHeader><CardTitle className="text-base">Exempt by module (SAC {data.sac})</CardTitle></CardHeader>
            <CardContent>
              <MoneyTable
                columns={[
                  { key: 'module_label', label: 'Module' },
                  { key: 'count', label: 'Bills', align: 'right' },
                  { key: 'taxable_value', label: 'Exempt value', align: 'right', money: true },
                ]}
                rows={data.by_module || []}
                totals={data.totals}
              />
            </CardContent>
          </Card>
        </>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{kind === 'inward' ? 'Inward' : 'Outward'} HSN</CardTitle>
          </CardHeader>
          <CardContent>
            <MoneyTable columns={hsnCols} rows={data?.rows || []} totals={data?.totals} />
          </CardContent>
        </Card>
      )}

      <PdfPreviewDialog
        open={pdfOpen}
        onClose={() => setPdfOpen(false)}
        path={`${exportBase}.pdf`}
        params={filterParams}
        title={`${kindMeta.label} PDF`}
        filename={`${fileStem}.pdf`}
        letterheadReportType={letterheadReportType}
      />
    </div>
  );
}
