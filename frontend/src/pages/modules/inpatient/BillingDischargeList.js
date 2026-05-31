import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Input } from '../../../components/ui/input';
import {
  Loader2, ChevronRight, Search, Wallet, FileBadge, Stethoscope, CheckCircle2,
} from 'lucide-react';

const rupee = (n) => `₹${Number(n || 0).toFixed(2)}`;

// Worklist for the unified Billing & Discharge subtab. Lists every admission
// that still has *something* outstanding:
//   • currently admitted (needs discharge + final bill + gate pass)
//   • discharged with non-zero balance (needs collection / refund)
//   • discharged with no gate pass yet (needs gate pass)
// Clicking any row opens BillingDischargePage for that admission.
const BillingDischargeList = ({ onPick }) => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState('');

  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const [actRes, disRes] = await Promise.all([
        axios.get('/api/inpatient/admissions', { params: { status: 'admitted', limit: 200 } }),
        axios.get('/api/inpatient/admissions', { params: { status: 'discharged', limit: 100 } }),
      ]);
      const active = actRes.data?.items || actRes.data || [];
      const discharged = disRes.data?.items || disRes.data || [];

      // Enrich each with balance + bill + gatepass summary so the list shows
      // why the operator should care. Capped network: simple parallel fetch.
      const enrich = async (a) => {
        const [balRes, billRes, gpRes] = await Promise.all([
          axios.get(`/api/inpatient/admissions/${a.id}/balance`).catch(() => ({ data: null })),
          axios.get(`/api/inpatient/admissions/${a.id}/bill`, { params: { unbilled_only: false } })
               .catch(() => ({ data: null })),
          axios.get(`/api/inpatient/admissions/${a.id}/gate-pass`).catch(() => ({ data: null })),
        ]);
        const computed = Number(billRes.data?.grand_total ?? billRes.data?.subtotal ?? 0);
        const billed   = Number(balRes.data?.total_billed ?? 0);
        const deposited = Number(balRes.data?.net_deposits ?? 0);
        const stayCharges = Math.max(computed, billed);
        const owes = +(stayCharges - deposited).toFixed(2);
        return { ...a, stayCharges, deposited, owes, gatePass: gpRes.data || null };
      };

      const enrichedActive = await Promise.all(active.map(enrich));
      const enrichedDischarged = await Promise.all(discharged.map(enrich));

      // Active: include all (they all need eventual discharge).
      // Discharged: include only if owes > 0.01 OR owes < -0.01 OR no gate pass.
      const dischargedFiltered = enrichedDischarged.filter(a =>
        Math.abs(a.owes) > 0.01 || !a.gatePass);

      const combined = [
        ...enrichedActive.map(a => ({ ...a, _bucket: 'active' })),
        ...dischargedFiltered.map(a => ({ ...a, _bucket: 'discharged' })),
      ];

      // Active first, then discharged-with-issues. Within each, newest first.
      combined.sort((a, b) => {
        if (a._bucket !== b._bucket) return a._bucket === 'active' ? -1 : 1;
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

  useEffect(() => { fetchRows(); }, [fetchRows]);

  const filtered = !q.trim() ? rows : rows.filter(a => {
    const needle = q.toLowerCase();
    return (a.patient_name || '').toLowerCase().includes(needle)
        || (a.admission_number || '').toLowerCase().includes(needle);
  });

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

  if (rows.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-gray-500 text-sm">
          🎉 No admissions need billing or discharge action right now.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <Input placeholder="Search by patient or admission #" value={q}
                 onChange={e => setQ(e.target.value)} className="pl-10" />
        </div>
        <Button variant="outline" size="sm" onClick={fetchRows}>Refresh</Button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b bg-gray-50">
              <th className="text-left py-2 px-3 font-medium">Patient</th>
              <th className="text-left py-2 px-3 font-medium">Status</th>
              <th className="text-right py-2 px-3 font-medium">Stay charges</th>
              <th className="text-right py-2 px-3 font-medium">Deposits</th>
              <th className="text-right py-2 px-3 font-medium">Balance</th>
              <th className="text-left py-2 px-3 font-medium">Needs</th>
              <th className="text-right py-2 px-3 font-medium w-44"></th>
            </tr>
          </thead>
          <tbody>
            {filtered.map(a => {
              const owes = a.owes > 0.01;
              const credit = a.owes < -0.01;
              const settled = !owes && !credit;
              const needs = a._bucket === 'active'
                ? <span className="text-xs"><Stethoscope className="h-3 w-3 inline mr-1" /> Discharge flow</span>
                : owes
                  ? <span className="text-xs text-red-700"><Wallet className="h-3 w-3 inline mr-1" /> Collect payment</span>
                  : credit
                    ? <span className="text-xs text-blue-700"><Wallet className="h-3 w-3 inline mr-1" /> Refund credit</span>
                    : <span className="text-xs text-purple-700"><FileBadge className="h-3 w-3 inline mr-1" /> Issue gate pass</span>;
              return (
                <tr key={a.id} className="border-b hover:bg-gray-50 cursor-pointer"
                    onClick={() => onPick(a.id)}>
                  <td className="py-2 px-3">
                    <div className="font-medium">{a.patient_name}</div>
                    <div className="text-xs text-gray-500">
                      {a.admission_number}
                      {a.room_number && (<> · Rm {a.room_number}{a.bed_label ? `/${a.bed_label}` : ''}</>)}
                    </div>
                  </td>
                  <td className="py-2 px-3">
                    {a._bucket === 'active'
                      ? <Badge className="bg-emerald-100 text-emerald-800 text-xs">Admitted</Badge>
                      : <Badge className="bg-gray-200 text-gray-800 text-xs">Discharged</Badge>}
                  </td>
                  <td className="py-2 px-3 text-right">{rupee(a.stayCharges)}</td>
                  <td className="py-2 px-3 text-right">{rupee(a.deposited)}</td>
                  <td className="py-2 px-3 text-right">
                    {owes ? <span className="text-red-600 font-medium">{rupee(a.owes)}</span>
                          : credit ? <span className="text-blue-600">credit {rupee(Math.abs(a.owes))}</span>
                          : <span className="text-green-600 inline-flex items-center gap-1">
                              <CheckCircle2 className="h-3 w-3" /> {rupee(0)}
                            </span>}
                  </td>
                  <td className="py-2 px-3">{needs}</td>
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
    </div>
  );
};

export default BillingDischargeList;
