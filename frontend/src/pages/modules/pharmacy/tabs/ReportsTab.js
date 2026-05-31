import React, { useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../../components/ui/select';
import { Download, Play, Printer } from 'lucide-react';
import { printPdfFromUrl } from '../../../../utils/printPdf';

const REPORTS = [
  { key: 'sales', label: 'Sales', path: '/api/pharmacy/reports/sales', dateRange: true, groupOptions: ['day', 'medicine', 'doctor', 'payment_type'] },
  { key: 'purchases', label: 'Purchases', path: '/api/pharmacy/reports/purchases', dateRange: true, groupOptions: ['day', 'supplier'] },
  { key: 'stock', label: 'Stock on Hand', path: '/api/pharmacy/reports/stock-on-hand' },
  { key: 'narcotic', label: 'Narcotic Register', path: '/api/pharmacy/reports/narcotic-register', dateRange: true },
  { key: 'tax', label: 'Tax Summary', path: '/api/pharmacy/reports/tax-summary', dateRange: true },
];

export default function ReportsTab() {
  const [report, setReport] = useState('sales');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [days, setDays] = useState(90);
  const [groupBy, setGroupBy] = useState('day');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const def = REPORTS.find(r => r.key === report);

  const run = async () => {
    setLoading(true);
    try {
      const params = {};
      if (def.dateRange) {
        if (dateFrom) params.date_from = dateFrom;
        if (dateTo) params.date_to = dateTo;
      }
      if (def.daysParam) params.days = days;
      if (def.groupOptions) params.group_by = groupBy;
      const r = await axios.get(def.path, { params });
      setRows(r.data || []);
    } catch { setRows([]); }
    finally { setLoading(false); }
  };

  const exportCsv = () => {
    if (!rows.length) return;
    const keys = Object.keys(rows[0]);
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

  return (
    <Card>
      <CardHeader>
        <CardTitle>Reports</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-3 items-end mb-4">
          <div>
            <Label className="text-xs">Report</Label>
            <Select value={report} onValueChange={v => { setReport(v); setRows([]); }}>
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
          {report === 'narcotic' && (
            <Button variant="outline" onClick={() => {
              const params = {};
              if (dateFrom) params.date_from = dateFrom;
              if (dateTo) params.date_to = dateTo;
              printPdfFromUrl('/api/pharmacy/reports/narcotic-register/pdf', { include_header: false, params });
            }}><Printer className="h-3 w-3 mr-1" /> Print Register</Button>
          )}
        </div>

        {loading ? <p className="text-center py-6 text-sm text-gray-500">Running…</p>
          : rows.length === 0 ? <p className="text-center py-6 text-sm text-gray-500">No data. Run a report.</p>
          : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-600">
                    {Object.keys(rows[0]).map(k => <th key={k} className="py-2 pr-4">{k}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i} className="border-b hover:bg-gray-50">
                      {Object.keys(rows[0]).map(k => (
                        <td key={k} className="py-2 pr-4 text-xs">{
                          typeof r[k] === 'number' ? Number(r[k]).toLocaleString() : String(r[k] ?? '—')
                        }</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </CardContent>
    </Card>
  );
}
