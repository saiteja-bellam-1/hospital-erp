import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Badge } from '../../../../components/ui/badge';
import { Input } from '../../../../components/ui/input';
import { Loader2, Search } from 'lucide-react';
import { printPdfFromUrl } from '../../../../utils/printPdf';
import DischargePrintBar from './DischargePrintBar';

const DischargeHistory = () => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const PAGE_SIZE = 50;

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/inpatient/admissions', {
        params: { status: 'discharged', skip: page * PAGE_SIZE, limit: PAGE_SIZE },
      });
      setRows(res.data?.items || res.data || []);
      setTotal(res.data?.total ?? (res.data?.items || res.data || []).length);
    } catch {
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  const filtered = rows.filter(a => {
    if (!q.trim()) return true;
    const needle = q.trim().toLowerCase();
    return (a.patient_name || '').toLowerCase().includes(needle)
      || (a.admission_number || '').toLowerCase().includes(needle);
  });

  const formatDate = (d) => {
    if (!d) return '—';
    try { return new Date(d).toLocaleDateString(); } catch { return d; }
  };

  if (loading && rows.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-gray-500">
          <Loader2 className="h-5 w-5 mx-auto animate-spin" />
          <p className="text-sm mt-2">Loading discharge history…</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold">Discharge History</h2>
        <p className="text-sm text-gray-500">Past discharges — search, reprint summary, or admission detail.</p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <Input placeholder="Search patient or admission #" value={q}
                 onChange={e => setQ(e.target.value)} className="pl-10" />
        </div>
        <Button variant="outline" size="sm" onClick={fetchRows}>Refresh</Button>
      </div>

      {filtered.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-500 text-sm">
            No discharged admissions match your search.
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-x-auto border rounded-lg">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="text-left py-2 px-3 font-medium">Patient</th>
                <th className="text-left py-2 px-3 font-medium">Admitted</th>
                <th className="text-left py-2 px-3 font-medium">Discharged</th>
                <th className="text-left py-2 px-3 font-medium">Type</th>
                <th className="text-right py-2 px-3 font-medium min-w-[420px]">Print</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(a => (
                <tr key={a.id} className="border-b hover:bg-gray-50">
                  <td className="py-2 px-3">
                    <div className="font-medium">{a.patient_name}</div>
                    <div className="text-xs text-gray-500">{a.admission_number}</div>
                  </td>
                  <td className="py-2 px-3 text-gray-600">{formatDate(a.admission_date)}</td>
                  <td className="py-2 px-3 text-gray-600">{formatDate(a.discharge_date)}</td>
                  <td className="py-2 px-3">
                    <Badge variant="outline" className="text-xs capitalize">
                      {(a.discharge_type || 'normal').replace(/_/g, ' ')}
                    </Badge>
                  </td>
                  <td className="py-2 px-3 text-right">
                    <DischargePrintBar
                      canPrintFinalBill
                      canPrintDischargeSummary
                      canPrintGatePass
                      onPrintFinalBill={() => printPdfFromUrl(`/api/inpatient/admissions/${a.id}/bill/pdf`)}
                      onPrintDischargeSummary={() => printPdfFromUrl(`/api/inpatient/admissions/${a.id}/discharge-summary/pdf`)}
                      onPrintGatePass={() => printPdfFromUrl(`/api/inpatient/admissions/${a.id}/gate-pass/pdf`)}
                      onPrintDetailedSummary={() => printPdfFromUrl(`/api/inpatient/admissions/${a.id}/admission-detail/pdf`)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm text-gray-500">
          <span>Page {page + 1} · {total} total</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" disabled={page === 0}
                    onClick={() => setPage(p => p - 1)}>Previous</Button>
            <Button size="sm" variant="outline" disabled={(page + 1) * PAGE_SIZE >= total}
                    onClick={() => setPage(p => p + 1)}>Next</Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default DischargeHistory;
