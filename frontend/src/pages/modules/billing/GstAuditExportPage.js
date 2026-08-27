import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Label } from '../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Download, FileSpreadsheet, FileText, Loader2 } from 'lucide-react';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';
import { formatInr, GstScopeChips as ModuleChips, GstinBanner, gstScopeEnabledMap } from './BillingReportControls';
import { Gst3bTables, SimpleRowsTable } from './GstReturnPreview';

const RETURNS = [
  {
    id: 'gstr1',
    label: 'GSTR-1',
    subtitle: 'Outward supplies',
    detail: 'B2B, B2CS, HSN, exempt (Table 8) and documents issued — GSTN sheet layout.',
  },
  {
    id: 'gstr2',
    label: 'GSTR-2',
    subtitle: 'Inward books (2A/2B matching)',
    detail: 'Purchase register from your books. True GSTR-2A/2B still come from the GST portal.',
  },
  {
    id: 'gstr3b',
    label: 'GSTR-3B',
    subtitle: 'Monthly summary',
    detail: 'Form GSTR-3B tables 3.1, 4, 5 and 6.1. Excel plus printable PDF.',
  },
  {
    id: 'gstr9',
    label: 'GSTR-9',
    subtitle: 'Annual return',
    detail: 'FY Apr–Mar roll-up of GSTR-1 and GSTR-3B. Interest, late fee and DRC are omitted.',
  },
];

const MONTHS = [
  { v: 1, l: 'January' }, { v: 2, l: 'February' }, { v: 3, l: 'March' },
  { v: 4, l: 'April' }, { v: 5, l: 'May' }, { v: 6, l: 'June' },
  { v: 7, l: 'July' }, { v: 8, l: 'August' }, { v: 9, l: 'September' },
  { v: 10, l: 'October' }, { v: 11, l: 'November' }, { v: 12, l: 'December' },
];

function defaultTaxPeriod() {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return { year: d.getFullYear(), month: d.getMonth() + 1 };
}

function currentFyStart() {
  const d = new Date();
  return d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1;
}

function fyOptions() {
  const cur = currentFyStart();
  return [0, 1, 2, 3, 4].map((i) => {
    const y = cur - i;
    return { v: y, l: `FY ${y}-${String(y + 1).slice(-2)} (Apr ${y} – Mar ${y + 1})` };
  });
}

function yearOptions() {
  const y = new Date().getFullYear();
  const out = [];
  for (let i = y + 1; i >= y - 6; i -= 1) out.push(i);
  return out;
}

async function downloadBlob(path, params, filename) {
  const r = await axios.get(path, { params, responseType: 'blob' });
  const url = URL.createObjectURL(r.data);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function GstAuditExportPage() {
  const initial = defaultTaxPeriod();
  const [kind, setKind] = useState('gstr1');
  const [year, setYear] = useState(initial.year);
  const [month, setMonth] = useState(initial.month);
  const [fyStart, setFyStart] = useState(currentFyStart());
  const [module, setModule] = useState('all');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
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

  const scopeEnabled = useMemo(
    () => (Object.keys(enabledModules).length ? gstScopeEnabledMap(enabledModules) : null),
    [enabledModules],
  );

  useEffect(() => {
    if (!scopeEnabled) return;
    if (module !== 'all' && scopeEnabled[module] === false) setModule('all');
  }, [scopeEnabled, module]);

  const periodParams = useMemo(() => {
    const params = {};
    if (module && module !== 'all') params.module = module;
    if (kind === 'gstr9') params.fy_start = fyStart;
    else {
      params.year = year;
      params.month = month;
    }
    return params;
  }, [kind, year, month, fyStart, module]);

  const run = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const r = await axios.get(`/api/hospital/billing/reports/gst/${kind}`, { params: periodParams });
      setData(r.data);
    } catch (e) {
      setData(null);
      setError(e?.response?.data?.detail || 'Could not load this return.');
    } finally {
      setLoading(false);
    }
  }, [kind, periodParams]);

  useEffect(() => { run(); }, [run]);

  const applyPreset = (id) => {
    const today = new Date();
    if (id === 'this_month') {
      setYear(today.getFullYear());
      setMonth(today.getMonth() + 1);
      return;
    }
    const d = new Date(today.getFullYear(), today.getMonth() - 1, 1);
    setYear(d.getFullYear());
    setMonth(d.getMonth() + 1);
  };

  const onDownload = async (pack = false) => {
    setExporting(true);
    setError('');
    try {
      if (pack) {
        await downloadBlob(
          '/api/hospital/billing/reports/gst/audit.xlsx',
          { year, month, ...(module && module !== 'all' ? { module } : {}) },
          `gst_audit_${year}_${String(month).padStart(2, '0')}.xlsx`,
        );
      } else if (kind === 'gstr9') {
        await downloadBlob(
          '/api/hospital/billing/reports/gst/gstr9.xlsx',
          { fy_start: fyStart, ...(module && module !== 'all' ? { module } : {}) },
          `GSTR9_${module || 'all'}_FY${fyStart}_${fyStart + 1}.xlsx`,
        );
      } else {
        await downloadBlob(
          `/api/hospital/billing/reports/gst/${kind}.xlsx`,
          { year, month, ...(module && module !== 'all' ? { module } : {}) },
          `${kind.toUpperCase()}_${module || 'all'}_${year}_${String(month).padStart(2, '0')}.xlsx`,
        );
      }
    } catch (e) {
      setError(e?.response?.data?.detail || 'Export failed. Confirm you can view financial reports.');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-bold text-gray-900">GST Returns</h1>
          <p className="text-sm text-gray-600 mt-0.5">
            Working papers shaped like GSTR-1, GSTR-2 books, Form GSTR-3B and GSTR-9.
            File Lab and Pharmacy on their own GSTINs; everything else files as Hospital GST.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          <Button onClick={() => onDownload(false)} disabled={exporting} size="sm">
            {exporting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <FileSpreadsheet className="h-4 w-4 mr-2" />}
            Download Excel
          </Button>
          {kind === 'gstr3b' && (
            <Button type="button" variant="outline" size="sm" onClick={() => setPdfOpen(true)}>
              <FileText className="h-4 w-4 mr-2" />
              Preview / print PDF
            </Button>
          )}
          {kind !== 'gstr9' && (
            <Button type="button" variant="outline" size="sm" onClick={() => onDownload(true)} disabled={exporting}>
              <Download className="h-4 w-4 mr-2" />
              All working papers
            </Button>
          )}
        </div>
      </div>

      <Card>
        <CardContent className="pt-4 space-y-3">
          <div className="flex flex-wrap items-end gap-x-3 gap-y-3">
            <div>
              <Label className="text-xs">Return</Label>
              <Select value={kind} onValueChange={setKind}>
                <SelectTrigger className="w-[260px] h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {RETURNS.map((r) => (
                    <SelectItem key={r.id} value={r.id}>{r.label} — {r.subtitle}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {kind === 'gstr9' ? (
              <div>
                <Label className="text-xs">Financial year (Apr–Mar)</Label>
                <Select value={String(fyStart)} onValueChange={(v) => setFyStart(Number(v))}>
                  <SelectTrigger className="w-[280px] h-9"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {fyOptions().map((o) => (
                      <SelectItem key={o.v} value={String(o.v)}>{o.l}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            ) : (
              <>
                <div>
                  <Label className="text-xs">Month</Label>
                  <Select value={String(month)} onValueChange={(v) => setMonth(Number(v))}>
                    <SelectTrigger className="w-[150px] h-9"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {MONTHS.map((m) => (
                        <SelectItem key={m.v} value={String(m.v)}>{m.l}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs">Year</Label>
                  <Select value={String(year)} onValueChange={(v) => setYear(Number(v))}>
                    <SelectTrigger className="w-[110px] h-9"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {yearOptions().map((y) => (
                        <SelectItem key={y} value={String(y)}>{y}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex gap-1">
                  <Button type="button" size="sm" variant="outline" className="h-9 text-xs" onClick={() => applyPreset('this_month')}>This month</Button>
                  <Button type="button" size="sm" variant="outline" className="h-9 text-xs" onClick={() => applyPreset('last_month')}>Last month</Button>
                </div>
              </>
            )}
            <div>
              <Label className="text-xs">GST registration</Label>
              <div className="mt-1">
                <ModuleChips value={module} onChange={setModule} enabled={scopeEnabled} />
              </div>
            </div>
          </div>
          <p className="text-xs text-gray-500">
            {RETURNS.find((r) => r.id === kind)?.detail}
            {kind === 'gstr2' ? ' Inward ITC is pharmacy GRN and files on Pharmacy GST only.' : ''}
          </p>
          <GstinBanner data={data} module={module} />
          {data?.hospital?.period_label && (
            <p className="text-xs text-gray-500">
              {data.hospital.period_label}
              {data.hospital.place_of_supply ? ` · ${data.hospital.place_of_supply}` : ''}
            </p>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
        </CardContent>
      </Card>

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>
      ) : data ? (
        <Preview kind={kind} data={data} />
      ) : null}

      {kind === 'gstr3b' && (
        <PdfPreviewDialog
          open={pdfOpen}
          onClose={() => setPdfOpen(false)}
          title="Form GSTR-3B"
          path="/api/hospital/billing/reports/gst/gstr3b.pdf"
          params={periodParams}
          filename={`GSTR3B_${module || 'all'}_${year}_${String(month).padStart(2, '0')}.pdf`}
          letterheadReportType="billing_gstr3b"
        />
      )}
    </div>
  );
}

function Preview({ kind, data }) {
  if (kind === 'gstr3b') return <Gst3bTables data={data} />;
  if (kind === 'gstr1') return <Gstr1Preview data={data} />;
  if (kind === 'gstr2') return <Gstr2Preview data={data} />;
  if (kind === 'gstr9') return <Gstr9Preview data={data} />;
  return null;
}

function Gstr1Preview({ data }) {
  const t = data.totals || {};
  const b2cs = data.b2cs || {};
  const hsn = data.hsn_b2c || {};
  const exemp = data.exemp || {};
  const docs = data.docs || {};
  const b2b = data.b2b || {};
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          ['Outward taxable', t.outward_taxable],
          ['Outward tax', t.outward_tax],
          ['Exempt / nil', t.exempt_value],
          ['B2B invoices', (b2b.summary || {}).invoices || 0],
        ].map(([label, val]) => (
          <div key={label} className="border rounded p-3">
            <div className="text-xs text-gray-500">{label}</div>
            <div className="text-lg font-semibold">{typeof val === 'number' && label !== 'B2B invoices' ? formatInr(val) : val}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      <Card>
        <CardHeader><CardTitle className="text-base">B2CS (Table 7)</CardTitle></CardHeader>
        <CardContent>
          <SimpleRowsTable
            columns={[
              { key: 'type', label: 'Type' },
              { key: 'place_of_supply', label: 'Place of supply' },
              { key: 'rate', label: 'Rate %', align: 'right' },
              { key: 'taxable_value', label: 'Taxable value', align: 'right', money: true },
              { key: 'cess', label: 'Cess', align: 'right', money: true },
            ]}
            rows={b2cs.rows || []}
            empty="No B2C supplies — walk-in pharmacy sales without a customer GSTIN appear here."
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">B2B (Table 4)</CardTitle></CardHeader>
        <CardContent>
          <SimpleRowsTable
            columns={[
              { key: 'gstin', label: 'GSTIN' },
              { key: 'invoice_number', label: 'Invoice' },
              { key: 'invoice_date', label: 'Date' },
              { key: 'rate', label: 'Rate %', align: 'right' },
              { key: 'taxable_value', label: 'Taxable', align: 'right', money: true },
              { key: 'invoice_value', label: 'Invoice value', align: 'right', money: true },
            ]}
            rows={b2b.rows || []}
            empty="No B2B invoices — add a customer GSTIN on corporate / ITC sales."
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">HSN B2C (Table 12)</CardTitle></CardHeader>
        <CardContent>
          <SimpleRowsTable
            columns={[
              { key: 'hsn', label: 'HSN' },
              { key: 'uqc', label: 'UQC' },
              { key: 'qty', label: 'Qty', align: 'right' },
              { key: 'rate', label: 'Rate %', align: 'right' },
              { key: 'taxable_value', label: 'Taxable', align: 'right', money: true },
              { key: 'cgst', label: 'CGST', align: 'right', money: true },
              { key: 'sgst', label: 'SGST', align: 'right', money: true },
            ]}
            rows={hsn.rows || []}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">Nil / exempt (Table 8)</CardTitle></CardHeader>
        <CardContent>
          <SimpleRowsTable
            columns={[
              { key: 'description', label: 'Description' },
              { key: 'nil', label: 'Nil rated', align: 'right', money: true },
              { key: 'exempt', label: 'Exempt', align: 'right', money: true },
              { key: 'non_gst', label: 'Non-GST', align: 'right', money: true },
            ]}
            rows={exemp.rows || []}
          />
        </CardContent>
      </Card>
      </div>
      <Card>
        <CardHeader><CardTitle className="text-base">Documents issued (Table 13)</CardTitle></CardHeader>
        <CardContent>
          <SimpleRowsTable
            columns={[
              { key: 'nature', label: 'Nature of document' },
              { key: 'from', label: 'Sr.No. from' },
              { key: 'to', label: 'Sr.No. to' },
              { key: 'total', label: 'Total', align: 'right' },
              { key: 'cancelled', label: 'Cancelled', align: 'right' },
            ]}
            rows={docs.rows || []}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function Gstr2Preview({ data }) {
  const itc = data.itc || {};
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          ['ITC total', itc.total],
          ['ITC CGST', itc.cgst],
          ['ITC SGST', itc.sgst],
          ['ITC IGST', itc.igst],
        ].map(([label, val]) => (
          <div key={label} className="border rounded p-3">
            <div className="text-xs text-gray-500">{label}</div>
            <div className="text-lg font-semibold">{formatInr(val)}</div>
          </div>
        ))}
      </div>
      {data.inward_note && (
        <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
          {data.inward_note}
        </p>
      )}
      <p className="text-xs text-gray-500">
        Match these invoices to a GSTR-2A/2B download from the GST portal. We do not import portal 2B in this version.
      </p>
      <Card>
        <CardHeader><CardTitle className="text-base">B2B inward</CardTitle></CardHeader>
        <CardContent>
          <SimpleRowsTable
            columns={[
              { key: 'gstin', label: 'GSTIN' },
              { key: 'supplier', label: 'Supplier' },
              { key: 'invoice_number', label: 'Invoice' },
              { key: 'invoice_date', label: 'Date' },
              { key: 'taxable', label: 'Taxable', align: 'right', money: true },
              { key: 'total_tax', label: 'Tax', align: 'right', money: true },
              { key: 'invoice_value', label: 'Invoice value', align: 'right', money: true },
            ]}
            rows={(data.b2b || {}).rows || []}
            empty="No registered inward invoices this period."
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">Unregistered inward</CardTitle></CardHeader>
        <CardContent>
          <SimpleRowsTable
            columns={[
              { key: 'supplier', label: 'Supplier' },
              { key: 'invoice_number', label: 'Invoice' },
              { key: 'taxable', label: 'Taxable', align: 'right', money: true },
              { key: 'total_tax', label: 'Tax', align: 'right', money: true },
            ]}
            rows={(data.unregistered || {}).rows || []}
            empty="No unregistered inward invoices."
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">HSN inward</CardTitle></CardHeader>
        <CardContent>
          <SimpleRowsTable
            columns={[
              { key: 'hsn', label: 'HSN' },
              { key: 'rate', label: 'Rate %', align: 'right' },
              { key: 'taxable_value', label: 'Taxable', align: 'right', money: true },
              { key: 'cgst', label: 'CGST', align: 'right', money: true },
              { key: 'sgst', label: 'SGST', align: 'right', money: true },
            ]}
            rows={(data.hsn || {}).rows || []}
          />
        </CardContent>
      </Card>
    </div>
  );
}

function Gstr9Preview({ data }) {
  const t4 = data.table_4 || {};
  const t6 = data.table_6 || {};
  const t9 = data.table_9 || {};
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle className="text-base">Table 4 — Outward supplies</CardTitle></CardHeader>
        <CardContent>
          <SimpleRowsTable
            columns={[
              { key: 'nature', label: 'Nature' },
              { key: 'taxable', label: 'Taxable', align: 'right', money: true },
              { key: 'igst', label: 'IGST', align: 'right', money: true },
              { key: 'cgst', label: 'CGST', align: 'right', money: true },
              { key: 'sgst', label: 'SGST', align: 'right', money: true },
            ]}
            rows={[
              { nature: 'B2B', ...(t4.b2b || {}) },
              { nature: 'B2C', ...(t4.b2c || {}) },
              { nature: 'Nil / exempt', ...(t4.nil_exempt || {}) },
              { nature: 'Net outward (3B 3.1(a))', ...(t4.net_outward || {}) },
            ]}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">Table 6 — ITC</CardTitle></CardHeader>
        <CardContent>
          <SimpleRowsTable
            columns={[
              { key: 'nature', label: 'Particulars' },
              { key: 'igst', label: 'IGST', align: 'right', money: true },
              { key: 'cgst', label: 'CGST', align: 'right', money: true },
              { key: 'sgst', label: 'SGST', align: 'right', money: true },
            ]}
            rows={[
              { nature: 'ITC available', ...(t6.itc_available || {}) },
              { nature: 'ITC reversed', ...(t6.itc_reversed || {}) },
              { nature: 'Net ITC', ...(t6.net_itc || {}) },
            ]}
          />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">Table 9 — Tax paid</CardTitle></CardHeader>
        <CardContent>
          <SimpleRowsTable
            columns={[
              { key: 'nature', label: 'Description' },
              { key: 'payable', label: 'Payable', align: 'right', money: true },
              { key: 'itc', label: 'Paid through ITC', align: 'right', money: true },
              { key: 'cash', label: 'Paid in cash', align: 'right', money: true },
            ]}
            rows={[
              { nature: 'Integrated Tax', ...(t9.igst || {}) },
              { nature: 'Central Tax', ...(t9.cgst || {}) },
              { nature: 'State/UT Tax', ...(t9.sgst || {}) },
            ]}
          />
        </CardContent>
      </Card>
    </div>
  );
}
