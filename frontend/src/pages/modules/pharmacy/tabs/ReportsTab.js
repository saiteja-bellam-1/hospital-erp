import React, { useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../../components/ui/select';
import { Download, Play, Printer } from 'lucide-react';
import { printPdfFromUrl } from '../../../../utils/printPdf';

// Each report definition can opt into:
//   dateRange:    show From / To inputs
//   singleDate:   show a single Date input (POSTed as `date` param)
//   groupOptions: list of values for the `group_by` dropdown
//   daysParam:    show a numeric Days input (sent as `days`)
//   pdfPath:      the matching backend …/pdf endpoint (printable via Printer btn)
const REPORTS = [
  { key: 'sales', label: 'Sales', path: '/api/pharmacy/reports/sales', dateRange: true,
    groupOptions: ['day', 'medicine', 'doctor', 'payment_type'],
    pdfPath: '/api/pharmacy/reports/sales/pdf' },
  { key: 'purchases', label: 'Purchases', path: '/api/pharmacy/reports/purchases', dateRange: true,
    groupOptions: ['day', 'supplier'],
    pdfPath: '/api/pharmacy/reports/purchases/pdf' },
  { key: 'stock', label: 'Stock on Hand', path: '/api/pharmacy/reports/stock-on-hand',
    pdfPath: '/api/pharmacy/reports/stock-on-hand/pdf' },
  { key: 'narcotic', label: 'Narcotic Register', path: '/api/pharmacy/reports/narcotic-register',
    dateRange: true,
    pdfPath: '/api/pharmacy/reports/narcotic-register/pdf' },
  { key: 'tax', label: 'Tax Summary', path: '/api/pharmacy/reports/tax-summary', dateRange: true,
    pdfPath: '/api/pharmacy/reports/tax-summary/pdf' },
  { key: 'daily_closeout', label: 'Daily Closeout', path: '/api/pharmacy/reports/daily-closeout',
    singleDate: true,
    pdfPath: '/api/pharmacy/reports/daily-closeout/pdf' },
  { key: 'margin', label: 'Profit / Margin', path: '/api/pharmacy/reports/margin',
    dateRange: true, groupOptions: ['day', 'medicine'],
    pdfPath: '/api/pharmacy/reports/margin/pdf' },
  { key: 'supplier_aging', label: 'Supplier Aging', path: '/api/pharmacy/reports/supplier-aging',
    pdfPath: '/api/pharmacy/reports/supplier-aging/pdf' },
  { key: 'movement', label: 'Movement (ABC)', path: '/api/pharmacy/reports/movement',
    daysParam: true,
    pdfPath: '/api/pharmacy/reports/movement/pdf' },
];

const TODAY = () => new Date().toISOString().split('T')[0];

export default function ReportsTab() {
  const [report, setReport] = useState('sales');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [singleDate, setSingleDate] = useState(TODAY());
  const [days, setDays] = useState(90);
  const [groupBy, setGroupBy] = useState('day');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const def = REPORTS.find(r => r.key === report);

  const buildParams = () => {
    const params = {};
    if (def.dateRange) {
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
    }
    if (def.singleDate && singleDate) params.date = singleDate;
    if (def.daysParam) params.days = days;
    if (def.groupOptions) params.group_by = groupBy;
    return params;
  };

  const run = async () => {
    setLoading(true);
    try {
      const r = await axios.get(def.path, { params: buildParams() });
      setRows(r.data || []);
    } catch { setRows([]); }
    finally { setLoading(false); }
  };

  // Union keys across all rows so sparse columns aren't dropped from CSV.
  const csvKeys = () => {
    const set = new Set();
    rows.forEach(r => Object.keys(r || {}).forEach(k => set.add(k)));
    return Array.from(set);
  };

  const exportCsv = () => {
    if (!rows.length) return;
    const keys = csvKeys();
    const csv = [
      keys.join(','),
      ...rows.map(r => keys.map(k => JSON.stringify(r[k] ?? '')).join(','))
    ].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `pharmacy_${report}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  const printPdf = () => {
    if (!def.pdfPath) return;
    printPdfFromUrl(def.pdfPath, { include_header: false, params: buildParams() });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Reports</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-3 items-end mb-4">
          <div>
            <Label className="text-xs">Report</Label>
            <Select value={report} onValueChange={v => {
              setReport(v); setRows([]);
              const next = REPORTS.find(r => r.key === v);
              if (next?.groupOptions && !next.groupOptions.includes(groupBy)) {
                setGroupBy(next.groupOptions[0]);
              }
            }}>
              <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
              <SelectContent>
                {REPORTS.map(r => <SelectItem key={r.key} value={r.key}>{r.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {def.dateRange && <>
            <div><Label className="text-xs">From</Label><Input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className="w-36" /></div>
            <div><Label className="text-xs">To</Label><Input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className="w-36" /></div>
          </>}
          {def.singleDate && (
            <div><Label className="text-xs">Date</Label><Input type="date" value={singleDate} onChange={e => setSingleDate(e.target.value)} className="w-36" /></div>
          )}
          {def.daysParam && (
            <div><Label className="text-xs">Days</Label><Input type="number" value={days} onChange={e => setDays(parseInt(e.target.value) || 30)} className="w-24" /></div>
          )}
          {def.groupOptions && (
            <div>
              <Label className="text-xs">Group by</Label>
              <Select value={groupBy} onValueChange={setGroupBy}>
                <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {def.groupOptions.map(g => <SelectItem key={g} value={g}>{g}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}
          <Button onClick={run} disabled={loading}><Play className="h-3 w-3 mr-1" /> Run</Button>
          <Button variant="outline" onClick={exportCsv} disabled={!rows.length}><Download className="h-3 w-3 mr-1" /> CSV</Button>
          {def.pdfPath && (
            <Button variant="outline" onClick={printPdf}><Printer className="h-3 w-3 mr-1" /> Print</Button>
          )}
        </div>

        {loading ? <p className="text-center py-6 text-sm text-gray-500">Running…</p>
          : rows.length === 0 ? <p className="text-center py-6 text-sm text-gray-500">No data. Run a report.</p>
          : (() => {
            const keys = csvKeys();
            const renderCell = (v) => {
              if (v === null || v === undefined) return '—';
              if (typeof v === 'number') return Number(v).toLocaleString();
              if (Array.isArray(v)) {
                return v.map(o => (
                  typeof o === 'object'
                    ? Object.entries(o).map(([k, vv]) => `${k}: ${vv}`).join(', ')
                    : String(o)
                )).join(' | ') || '—';
              }
              return String(v);
            };
            return (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-gray-600">
                      {keys.map(k => <th key={k} className="py-2 pr-4">{k}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r, i) => (
                      <tr key={i} className="border-b hover:bg-gray-50">
                        {keys.map(k => (
                          <td key={k} className="py-2 pr-4 text-xs">{renderCell(r[k])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })()}
      </CardContent>
    </Card>
  );
}
