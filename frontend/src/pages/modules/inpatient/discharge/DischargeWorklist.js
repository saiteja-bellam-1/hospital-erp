import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Badge } from '../../../../components/ui/badge';
import { Input } from '../../../../components/ui/input';
import {
  Loader2, ChevronRight, Search, Wallet, FileBadge, FileText, CheckCircle2,
} from 'lucide-react';
import { rupee } from './constants';
import { printPdfFromUrl } from '../../../../utils/printPdf';
import DischargePrintBar from './DischargePrintBar';

const FILTERS = [
  { id: 'pending', label: 'All pending' },
  { id: 'summary', label: 'Awaiting summary' },
  { id: 'ready', label: 'Ready for discharge' },
  { id: 'bill', label: 'Need bill' },
  { id: 'checkout', label: 'Awaiting discharge' },
  { id: 'gatepass', label: 'Need gate pass' },
  { id: 'completed', label: 'Completed' },
];

const summaryIsReady = (status) => status === 'ready' || status === 'locked';

const DischargeWorklist = ({ onPick, refreshKey = 0 }) => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState('pending');

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const [actRes, disRes] = await Promise.all([
        axios.get('/api/inpatient/admissions', { params: { status: 'admitted', limit: 200 } }),
        axios.get('/api/inpatient/admissions', { params: { status: 'discharged', limit: 100 } }),
      ]);
      const active = actRes.data?.items || actRes.data || [];
      const discharged = disRes.data?.items || disRes.data || [];

      const enrich = async (a) => {
        const [balRes, billRes, gpRes, billsRes, summaryRes] = await Promise.all([
          axios.get(`/api/inpatient/admissions/${a.id}/balance`).catch(() => ({ data: null })),
          axios.get(`/api/inpatient/admissions/${a.id}/bill`, { params: { unbilled_only: false } })
            .catch(() => ({ data: null })),
          axios.get(`/api/inpatient/admissions/${a.id}/gate-pass`).catch(() => ({ data: null })),
          axios.get(`/api/inpatient/admissions/${a.id}/bills`).catch(() => ({ data: [] })),
          axios.get(`/api/inpatient/admissions/${a.id}/discharge-summary`).catch(() => ({ data: null })),
        ]);
        const computed = Number(billRes.data?.grand_total ?? billRes.data?.subtotal ?? 0);
        const billed = Number(balRes.data?.total_billed ?? 0);
        const deposited = Number(balRes.data?.net_deposits ?? 0);
        const stayCharges = Math.max(computed, billed);
        const owes = +(stayCharges - deposited).toFixed(2);
        const bills = billsRes.data?.items || billsRes.data || [];
        const finalBill = bills.find(b => b.bill_subtype === 'final' && b.status !== 'cancelled');
        const summaryStatus = summaryRes.data?.status || null;
        return {
          ...a,
          stayCharges,
          deposited,
          owes,
          gatePass: gpRes.data || null,
          finalBill: finalBill || null,
          summaryStatus,
        };
      };

      const enrichedActive = await Promise.all(active.map(enrich));
      const enrichedDischarged = await Promise.all(discharged.map(enrich));

      const combined = [
        ...enrichedActive.map(a => ({ ...a, _bucket: 'active' })),
        ...enrichedDischarged.map(a => ({ ...a, _bucket: 'discharged' })),
      ];

      combined.sort((a, b) => {
        const aPending = !a.gatePass || a._bucket === 'active';
        const bPending = !b.gatePass || b._bucket === 'active';
        if (aPending !== bPending) return aPending ? -1 : 1;
        const aReady = a._bucket === 'active' && summaryIsReady(a.summaryStatus);
        const bReady = b._bucket === 'active' && summaryIsReady(b.summaryStatus);
        if (aReady !== bReady) return aReady ? -1 : 1;
        const aT = new Date(a.admission_date || 0).getTime();
        const bT = new Date(b.admission_date || 0).getTime();
        return bT - aT;
      });
      setRows(combined);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchRows(); }, [fetchRows, refreshKey]);

  const classify = (a) => {
    if (a.gatePass && a._bucket === 'discharged' && Math.abs(a.owes) <= 0.01) return 'completed';
    if (a._bucket === 'active') {
      const summaryReady = summaryIsReady(a.summaryStatus);
      if (!summaryReady) return 'summary';
      if (a.finalBill) return 'checkout';
      return 'ready';
    }
    if (a._bucket === 'discharged' && !a.gatePass) return 'gatepass';
    if (a._bucket === 'discharged' && Math.abs(a.owes) > 0.01) return 'bill';
    return 'completed';
  };

  const activeBillBucket = (a) => (
    a._bucket === 'active' && !a.finalBill ? 'bill' : null
  );

  const statusBadge = (a) => {
    const bucket = classify(a);
    if (bucket === 'completed') {
      return <Badge className="bg-green-100 text-green-800 text-xs">Completed</Badge>;
    }
    if (a._bucket === 'discharged') {
      return <Badge className="bg-gray-200 text-gray-800 text-xs">Discharged</Badge>;
    }
    if (summaryIsReady(a.summaryStatus)) {
      return <Badge className="bg-green-100 text-green-800 text-xs">Ready for discharge</Badge>;
    }
    if (bucket === 'summary') {
      return <Badge className="bg-amber-100 text-amber-800 text-xs">Awaiting summary</Badge>;
    }
    return <Badge className="bg-emerald-100 text-emerald-800 text-xs">Admitted</Badge>;
  };

  const needsLabel = (a, bucket) => {
    if (bucket === 'bill' || activeBillBucket(a) === 'bill') {
      return <span className="text-xs"><Wallet className="h-3 w-3 inline mr-1" /> Bill / payment</span>;
    }
    if (bucket === 'summary') {
      return <span className="text-xs text-amber-700"><FileText className="h-3 w-3 inline mr-1" /> Doctor summary pending</span>;
    }
    if (bucket === 'checkout') {
      return <span className="text-xs text-blue-700"><CheckCircle2 className="h-3 w-3 inline mr-1" /> Bill settled — discharge patient</span>;
    }
    if (bucket === 'ready') {
      return <span className="text-xs text-green-700"><CheckCircle2 className="h-3 w-3 inline mr-1" /> Summary ready — open checkout</span>;
    }
    if (bucket === 'gatepass') {
      return <span className="text-xs text-purple-700"><FileBadge className="h-3 w-3 inline mr-1" /> Gate pass</span>;
    }
    return <span className="text-xs text-green-700"><CheckCircle2 className="h-3 w-3 inline mr-1" /> Done</span>;
  };

  const filtered = rows.filter(a => {
    const needle = q.trim().toLowerCase();
    if (needle) {
      const match = (a.patient_name || '').toLowerCase().includes(needle)
        || (a.admission_number || '').toLowerCase().includes(needle);
      if (!match) return false;
    }
    const bucket = classify(a);
    if (filter === 'pending') return bucket !== 'completed';
    if (filter === 'bill') {
      return activeBillBucket(a) === 'bill' || (bucket === 'bill' && a._bucket === 'discharged');
    }
    return bucket === filter;
  });

  const printDischargeSummaryPdf = (e, id) => {
    e?.stopPropagation?.();
    printPdfFromUrl(`/api/inpatient/admissions/${id}/discharge-summary/pdf`);
  };

  const printAdmissionDetailPdf = (e, id) => {
    e?.stopPropagation?.();
    printPdfFromUrl(`/api/inpatient/admissions/${id}/admission-detail/pdf`);
  };

  const printFinalBillPdf = (e, id) => {
    e?.stopPropagation?.();
    printPdfFromUrl(`/api/inpatient/admissions/${id}/bill/pdf`);
  };

  const printGatePassPdf = (e, id) => {
    e?.stopPropagation?.();
    printPdfFromUrl(`/api/inpatient/admissions/${id}/gate-pass/pdf`);
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-gray-500">
          <Loader2 className="h-5 w-5 mx-auto animate-spin" />
          <p className="text-sm mt-2">Loading admissions…</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <Input placeholder="Search patient or admission #" value={q}
                 onChange={e => setQ(e.target.value)} className="pl-10" />
        </div>
        <Button variant="outline" size="sm" onClick={fetchRows}>Refresh</Button>
      </div>

      <div className="flex flex-wrap gap-1">
        {FILTERS.map(f => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            className={
              'px-2.5 py-1 rounded-full text-xs border transition ' +
              (filter === f.id
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-600 border-gray-200 hover:border-blue-300')
            }
          >
            {f.label}
          </button>
        ))}
      </div>

      {filtered.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-500 text-sm">
            {filter === 'completed'
              ? 'No completed discharges match your search.'
              : '🎉 No admissions need discharge action right now.'}
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-x-auto border rounded-lg">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="text-left py-2 px-3 font-medium">Patient</th>
                <th className="text-left py-2 px-3 font-medium">Status</th>
                <th className="text-right py-2 px-3 font-medium">Balance</th>
                <th className="text-left py-2 px-3 font-medium">Needs</th>
                <th className="text-right py-2 px-3 font-medium min-w-[420px]">Print</th>
                <th className="text-right py-2 px-3 font-medium w-24"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(a => {
                const owes = a.owes > 0.01;
                const credit = a.owes < -0.01;
                const bucket = classify(a);
                return (
                  <tr key={a.id} className="border-b hover:bg-gray-50 cursor-pointer"
                      onClick={() => onPick(a.id)}>
                    <td className="py-2 px-3">
                      <div className="font-medium">{a.patient_name}</div>
                      <div className="text-xs text-gray-500">{a.admission_number}</div>
                    </td>
                    <td className="py-2 px-3">{statusBadge(a)}</td>
                    <td className="py-2 px-3 text-right">
                      {owes ? <span className="text-red-600 font-medium">{rupee(a.owes)}</span>
                        : credit ? <span className="text-blue-600">credit {rupee(Math.abs(a.owes))}</span>
                          : <span className="text-green-600">{rupee(0)}</span>}
                    </td>
                    <td className="py-2 px-3">{needsLabel(a, bucket)}</td>
                    <td className="py-2 px-3 text-right" onClick={e => e.stopPropagation()}>
                      <DischargePrintBar
                        onClickStopPropagation
                        canPrintFinalBill={!!a.finalBill}
                        canPrintDischargeSummary={summaryIsReady(a.summaryStatus)}
                        canPrintGatePass={!!a.gatePass}
                        onPrintFinalBill={() => printFinalBillPdf(null, a.id)}
                        onPrintDischargeSummary={() => printDischargeSummaryPdf(null, a.id)}
                        onPrintGatePass={() => printGatePassPdf(null, a.id)}
                        onPrintDetailedSummary={() => printAdmissionDetailPdf(null, a.id)}
                      />
                    </td>
                    <td className="py-2 px-3 text-right">
                      <Button size="sm" onClick={(e) => { e.stopPropagation(); onPick(a.id); }}>
                        Open <ChevronRight className="h-3.5 w-3.5 ml-1" />
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default DischargeWorklist;
