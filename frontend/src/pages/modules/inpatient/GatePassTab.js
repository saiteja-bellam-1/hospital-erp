import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import { Textarea } from '../../../components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../../../components/ui/dialog';
import { useToast } from '../../../hooks/use-toast';
import { printPdfFromUrl } from '../../../utils/printPdf';
import {
  Printer, CheckCircle2, AlertTriangle, Loader2, FileBadge, Wallet,
} from 'lucide-react';

const GatePassTab = ({ canIssue = false }) => {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [target, setTarget] = useState(null);
  const [form, setForm] = useState({
    attendant_name: '', attendant_relationship: '', vehicle_no: '', notes: '',
  });
  const [submitting, setSubmitting] = useState(false);
  // 409 outstanding_bill response from backend: { message, outstanding, unpaid_bills[] }
  const [outstandingErr, setOutstandingErr] = useState(null);
  const [overrideReason, setOverrideReason] = useState('');

  // We need: discharged admissions, with their balance and existing gate pass (if any).
  // Strategy: load discharged admissions, then for each fetch /gate-pass (existing) and
  // /bill/balance to compute outstanding. Capped to last 50 to keep network reasonable.
  const fetchRows = useCallback(async () => {
    setLoading(true);
    try {
      const admRes = await axios.get('/api/inpatient/admissions',
        { params: { status: 'discharged', limit: 50 } });
      const admissions = admRes.data?.items || admRes.data || [];
      // Only those with a DischargeRecord (status='discharged' guarantees that).
      const enriched = await Promise.all(admissions.map(async (a) => {
        // /balance gives net_deposits + total_billed (sum of finalised bills),
        // /bill gives the full computed charges (room + visits + meds + …).
        // We need the computed total to show "real" stay charges — relying on
        // finalised-bill total alone shows ₹0 when no bill has been generated.
        const [balRes, billRes, gpRes] = await Promise.all([
          axios.get(`/api/inpatient/admissions/${a.id}/balance`)
            .catch(() => ({ data: null })),
          axios.get(`/api/inpatient/admissions/${a.id}/bill`,
                    { params: { unbilled_only: false } })
            .catch(() => ({ data: null })),
          axios.get(`/api/inpatient/admissions/${a.id}/gate-pass`)
            .catch(() => ({ data: null })),
        ]);
        const netDeposits = balRes.data?.net_deposits ?? 0;
        const finalisedBilled = balRes.data?.total_billed ?? 0;
        const computedCharges = billRes.data?.grand_total
                             ?? billRes.data?.subtotal
                             ?? finalisedBilled;
        // Show the larger of (computed, finalised) so post-bill amounts also
        // surface here. owesAmount > 0 means patient still owes.
        const stayCharges = Math.max(computedCharges, finalisedBilled);
        const owesAmount = stayCharges - netDeposits;
        return {
          ...a,
          stayCharges,
          netDeposits,
          owesAmount,
          finalisedBilled,
          billFinalised: finalisedBilled > 0,
          gatePass: gpRes.data || null,
        };
      }));
      // Newest discharge first — old admissions sink to the bottom.
      enriched.sort((a, b) => {
        const aT = a.discharge_date ? new Date(a.discharge_date).getTime() : 0;
        const bT = b.discharge_date ? new Date(b.discharge_date).getTime() : 0;
        return bT - aT;
      });
      setRows(enriched);
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchRows(); }, [fetchRows]);

  const openIssue = (adm) => {
    setTarget(adm);
    setForm({ attendant_name: '', attendant_relationship: '', vehicle_no: '', notes: '' });
    setOutstandingErr(null);
    setOverrideReason('');
  };

  const submit = async () => {
    if (!form.attendant_name.trim()) {
      toast({ variant: 'destructive', title: 'Attendant name required' });
      return;
    }
    if (outstandingErr && !overrideReason.trim()) {
      toast({ variant: 'destructive', title: 'Override reason required',
              description: 'Provide a reason to issue with outstanding balance.' });
      return;
    }
    setSubmitting(true);
    try {
      await axios.post(`/api/inpatient/admissions/${target.id}/gate-pass`, {
        attendant_name: form.attendant_name.trim(),
        attendant_relationship: form.attendant_relationship.trim() || null,
        vehicle_no: form.vehicle_no.trim() || null,
        notes: form.notes.trim() || null,
        override_reason: outstandingErr ? overrideReason.trim() : undefined,
      });
      toast({ title: 'Gate pass issued', description: 'Opening printable preview…' });
      const targetId = target.id;
      setTarget(null);
      setOutstandingErr(null);
      setOverrideReason('');
      await fetchRows();
      // Open the printable PDF immediately after issuance
      await fetchAndPrint(targetId);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 409
          && detail && typeof detail === 'object'
          && detail.code === 'outstanding_bill') {
        setOutstandingErr(detail);
        toast({
          variant: 'destructive', title: 'Outstanding balance',
          description: 'Settle the listed bills, or provide a reason to override.',
        });
      } else {
        const msg = typeof detail === 'string' ? detail
          : (detail?.message || 'Could not issue gate pass');
        toast({ variant: 'destructive', title: 'Error', description: msg });
      }
    } finally {
      setSubmitting(false);
    }
  };

  // Fetch the gate-pass PDF as a blob (so axios attaches auth headers), then
  // hand the blob URL to the shared iframe-print helper. The previous code
  // passed the API path directly to printPdfFromUrl, which silently failed
  // because the iframe load is anonymous (no token).
  const fetchAndPrint = async (admissionId) => {
    try {
      const res = await axios.get(
        `/api/inpatient/admissions/${admissionId}/gate-pass/pdf`,
        { responseType: 'blob', params: { include_header: true } },
      );
      const url = URL.createObjectURL(res.data);
      printPdfFromUrl(url);
    } catch (err) {
      let msg = 'Failed to load gate pass PDF';
      try {
        if (err.response?.data instanceof Blob) {
          const text = await err.response.data.text();
          const json = JSON.parse(text);
          if (typeof json.detail === 'string') msg = json.detail;
        }
      } catch { /* keep generic msg */ }
      toast({ variant: 'destructive', title: 'Error', description: msg });
    }
  };

  const reprint = async (adm) => { await fetchAndPrint(adm.id); };

  if (loading) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-gray-500">
          <Loader2 className="h-5 w-5 mx-auto animate-spin" />
          <p className="text-sm mt-2">Loading discharged admissions…</p>
        </CardContent>
      </Card>
    );
  }

  if (rows.length === 0) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-gray-500 text-sm">
          No discharged admissions in the recent window.
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <p className="text-xs text-gray-500">
        Gate passes can only be issued once the patient owes nothing
        (deposits ≥ stay charges). Reprint is always allowed.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b bg-gray-50">
              <th className="text-left py-2 px-3 font-medium">Patient</th>
              <th className="text-left py-2 px-3 font-medium">Discharged</th>
              <th className="text-right py-2 px-3 font-medium">Stay charges</th>
              <th className="text-right py-2 px-3 font-medium">Deposits</th>
              <th className="text-right py-2 px-3 font-medium">Owes</th>
              <th className="text-left py-2 px-3 font-medium">Status</th>
              <th className="text-right py-2 px-3 font-medium w-48">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(adm => {
              const owes = adm.owesAmount > 0.01;        // patient still owes
              const cleared = !owes;                      // owes <= 0 → eligible
              const hasGP = !!adm.gatePass;
              return (
                <tr key={adm.id} className="border-b hover:bg-gray-50">
                  <td className="py-2 px-3">
                    <div className="font-medium">{adm.patient_name}</div>
                    <div className="text-xs text-gray-500">
                      {adm.admission_number}
                      {adm.admission_date && (
                        <> · admitted {new Date(adm.admission_date).toLocaleDateString()}</>
                      )}
                    </div>
                  </td>
                  <td className="py-2 px-3 text-xs">
                    {adm.discharge_date
                      ? new Date(adm.discharge_date).toLocaleString()
                      : '—'}
                  </td>
                  <td className="py-2 px-3 text-right">
                    ₹{adm.stayCharges.toFixed(2)}
                    {!adm.billFinalised && adm.stayCharges > 0 && (
                      <div className="text-[10px] text-amber-600">
                        (computed — not finalized)
                      </div>
                    )}
                  </td>
                  <td className="py-2 px-3 text-right">
                    ₹{adm.netDeposits.toFixed(2)}
                  </td>
                  <td className="py-2 px-3 text-right">
                    {owes
                      ? <span className="text-red-600 font-medium">₹{adm.owesAmount.toFixed(2)}</span>
                      : adm.owesAmount < -0.01
                        ? <span className="text-blue-600" title="Patient over-deposited — refund pending">
                            credit ₹{Math.abs(adm.owesAmount).toFixed(2)}
                          </span>
                        : <span className="text-green-600">₹0.00</span>}
                  </td>
                  <td className="py-2 px-3">
                    {hasGP
                      ? <Badge className="bg-blue-100 text-blue-800 text-xs">
                          <FileBadge className="h-3 w-3 mr-1 inline" />
                          Issued · {adm.gatePass.pass_number}
                        </Badge>
                      : owes
                        ? <Badge className="bg-red-100 text-red-800 text-xs">
                            <Wallet className="h-3 w-3 mr-1 inline" />
                            Balance due
                          </Badge>
                        : <Badge className="bg-green-100 text-green-800 text-xs">
                            <CheckCircle2 className="h-3 w-3 mr-1 inline" />
                            Ready
                          </Badge>}
                  </td>
                  <td className="py-2 px-3 text-right">
                    {hasGP ? (
                      <Button size="sm" variant="outline"
                              onClick={() => reprint(adm)}>
                        <Printer className="h-3.5 w-3.5 mr-1" /> Reprint
                      </Button>
                    ) : canIssue ? (
                      <Button size="sm"
                              disabled={!cleared}
                              onClick={() => openIssue(adm)}
                              title={!cleared ? 'Patient still owes — settle balance first' : 'Issue gate pass'}>
                        <FileBadge className="h-3.5 w-3.5 mr-1" /> Issue pass
                      </Button>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <Dialog open={!!target} onOpenChange={v => !v && setTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Issue gate pass</DialogTitle>
          </DialogHeader>
          {target && (
            <div className="space-y-3">
              <div className="bg-gray-50 border rounded p-2 text-sm">
                <div><b>{target.patient_name}</b></div>
                <div className="text-xs text-gray-600">
                  {target.admission_number} · Discharged
                  {target.discharge_date
                    ? ' ' + new Date(target.discharge_date).toLocaleString()
                    : ''}
                </div>
                <div className="text-xs text-green-700 mt-1 flex items-center gap-1">
                  <CheckCircle2 className="h-3 w-3" />
                  {target.owesAmount < -0.01
                    ? <>Patient over-deposited by ₹{Math.abs(target.owesAmount).toFixed(2)} (refund pending; gate pass OK)</>
                    : <>Patient owes ₹0.00 — eligible for gate pass</>}
                </div>
              </div>
              {outstandingErr && (
                <div className="border border-amber-300 bg-amber-50 rounded p-2 text-xs space-y-1">
                  <p className="font-semibold text-amber-900">
                    Outstanding: ₹{Number(outstandingErr.outstanding || 0).toFixed(2)}
                  </p>
                  {(outstandingErr.unpaid_bills || []).length > 0 && (
                    <ul className="ml-3 list-disc text-amber-900">
                      {outstandingErr.unpaid_bills.map(b => (
                        <li key={b.bill_id}>
                          {b.bill_number} — ₹{Number(b.total || 0).toFixed(2)} ({b.status})
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="pt-1">
                    <Label className="text-xs">Override reason (required) *</Label>
                    <Input value={overrideReason}
                           onChange={e => setOverrideReason(e.target.value)}
                           placeholder="e.g. Insurance pending — vendor approved" />
                  </div>
                </div>
              )}
              <div>
                <Label>Attendant name *</Label>
                <Input value={form.attendant_name}
                       onChange={e => setForm(p => ({ ...p, attendant_name: e.target.value }))}
                       placeholder="e.g. Lakshmi Kumar" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Relationship</Label>
                  <Input value={form.attendant_relationship}
                         onChange={e => setForm(p => ({ ...p, attendant_relationship: e.target.value }))}
                         placeholder="e.g. Wife / Son" />
                </div>
                <div>
                  <Label>Vehicle no.</Label>
                  <Input value={form.vehicle_no}
                         onChange={e => setForm(p => ({ ...p, vehicle_no: e.target.value }))}
                         placeholder="TS09 AB 1234" />
                </div>
              </div>
              <div>
                <Label>Notes</Label>
                <Textarea rows={2} value={form.notes}
                          onChange={e => setForm(p => ({ ...p, notes: e.target.value }))} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setTarget(null)}>Cancel</Button>
            <Button onClick={submit} disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              <Printer className="h-4 w-4 mr-1" /> Issue &amp; print
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default GatePassTab;
