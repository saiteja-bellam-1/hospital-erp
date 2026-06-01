import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import { Textarea } from '../../../components/ui/textarea';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '../../../components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../../components/ui/select';
import { useToast } from '../../../hooks/use-toast';
import { printPdfFromUrl } from '../../../utils/printPdf';
import DischargeWizard from './DischargeWizard';
import BillDetailDialog from './BillDetailDialog';
import {
  ArrowLeft, Loader2, Wallet, Banknote, Printer, FileBadge, Receipt,
  Plus, Trash2, CheckCircle2, AlertTriangle, IndianRupee, BedDouble,
  FileDown, Stethoscope,
} from 'lucide-react';

const PAYMENT_METHODS = [
  { value: 'cash',   label: 'Cash' },
  { value: 'card',   label: 'Card' },
  { value: 'upi',    label: 'UPI' },
  { value: 'cheque', label: 'Cheque' },
  { value: 'online', label: 'Online transfer' },
];

const rupee = (n) => `₹${Number(n || 0).toFixed(2)}`;

// One-stop page for everything money + exit related on an admission:
//   1. View running bill (live computed)
//   2. Add deposits at any time during the stay
//   3. Discharge flow: finalize bill (auto-settles balance) → record clinical
//      discharge via DischargeWizard → issue gatepass → print bill + gatepass
//   4. Post-discharge: collect outstanding dues / issue late gatepass / reprint
//
// Room release on discharge is handled by the backend's /discharge endpoint
// (bed → cleaning, room.available_beds recomputed). We surface that in toasts.
const BillingDischargePage = ({ admissionId, onBack, permissions = {} }) => {
  const { toast } = useToast();

  const canAddDeposit  = permissions.receive_deposits !== false;
  const canFinalize    = permissions.finalize_bill    !== false;
  const canDischarge   = permissions.discharge_patients !== false;
  const canIssuePass   = permissions.issue_gate_pass  !== false;
  const canAdjustBill  = permissions.finalize_bill    !== false;
  const canRefund      = permissions.issue_refunds    !== false;

  const [loading, setLoading] = useState(true);
  const [admission, setAdmission] = useState(null);
  const [bill, setBill]           = useState(null);   // running bill (unbilled + billed view)
  const [balance, setBalance]     = useState(null);   // { net_deposits, total_billed, balance }
  const [deposits, setDeposits]   = useState([]);
  const [finalBill, setFinalBill] = useState(null);
  const [gatePass, setGatePass]   = useState(null);

  const [depositForm, setDepositForm] = useState(null);   // null | { amount, method, ref, busy }
  const [collectForm, setCollectForm] = useState(null);   // post-discharge owe-settle
  const [refundForm, setRefundForm]   = useState(null);   // post-discharge credit refund
  const [billOpen, setBillOpen] = useState(false);

  // Discharge orchestration state machine. The flow is sequential — page steps
  // through: settle prompt → DischargeWizard → gatepass dialog → prints.
  // stage: null | 'finalize' | 'clinical' | 'gatepass'
  const [orchestrator, setOrchestrator] = useState({
    stage: null,
    settleForm: null,    // { direction: 'collect'|'refund'|'none', amount, method, ref, notes, busy }
    gatePassForm: null,  // { attendant_name, attendant_relationship, vehicle_no, notes, busy, overrideErr, overrideReason }
  });

  const fetchAll = useCallback(async () => {
    if (!admissionId) return;
    setLoading(true);
    try {
      const [admRes, billRes, balRes, depRes, billsRes, gpRes] = await Promise.all([
        axios.get(`/api/inpatient/admissions/${admissionId}`),
        axios.get(`/api/inpatient/admissions/${admissionId}/bill`, { params: { unbilled_only: false } }),
        axios.get(`/api/inpatient/admissions/${admissionId}/balance`),
        axios.get(`/api/inpatient/admissions/${admissionId}/deposits`),
        axios.get(`/api/inpatient/admissions/${admissionId}/bills`).catch(() => ({ data: [] })),
        axios.get(`/api/inpatient/admissions/${admissionId}/gate-pass`).catch(() => ({ data: null })),
      ]);
      setAdmission(admRes.data);
      setBill(billRes.data);
      setBalance(balRes.data);
      setDeposits(depRes.data?.items || depRes.data || []);
      const bills = billsRes.data?.items || billsRes.data || [];
      const finalised = bills.find(b => b.bill_subtype === 'final' && b.status !== 'cancelled');
      setFinalBill(finalised || null);
      setGatePass(gpRes.data || null);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Could not load admission',
              description: err.response?.data?.detail || 'Network error' });
    } finally {
      setLoading(false);
    }
  }, [admissionId, toast]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Derived state — the source of truth for "what does the operator see"
  const derived = useMemo(() => {
    if (!bill || !balance) return null;
    const computed   = Number(bill.grand_total ?? bill.subtotal ?? 0);
    const billed     = Number(balance.total_billed ?? 0);
    const deposited  = Number(balance.net_deposits ?? 0);
    const stayCharges = Math.max(computed, billed);
    const owes = +(stayCharges - deposited).toFixed(2);  // >0: owes, <0: credit
    const isDischarged = admission?.status === 'discharged';
    return { stayCharges, billed, deposited, owes, isDischarged };
  }, [bill, balance, admission]);

  // ────────────────────────────────────────────────────────────────────
  // Deposit (during stay)
  // ────────────────────────────────────────────────────────────────────
  const openDeposit = () => setDepositForm({
    amount: '', method: 'cash', ref: '', notes: '', busy: false,
  });

  const submitDeposit = async () => {
    const amt = parseFloat(depositForm.amount);
    if (!(amt > 0)) {
      toast({ variant: 'destructive', title: 'Enter an amount greater than zero' });
      return;
    }
    setDepositForm(p => ({ ...p, busy: true }));
    try {
      const res = await axios.post(`/api/inpatient/admissions/${admissionId}/deposits`, {
        amount: amt,
        deposit_type: 'topup',
        payment_method: depositForm.method,
        reference_number: depositForm.ref || null,
        notes: depositForm.notes || null,
      });
      toast({ title: 'Deposit recorded', description: `${rupee(amt)} received.` });
      // Best-effort print receipt
      try {
        const pdfRes = await axios.get(
          `/api/inpatient/deposits/${res.data.id}/receipt/pdf`,
          { responseType: 'blob' },
        );
        printPdfFromUrl(URL.createObjectURL(pdfRes.data));
      } catch (_) { /* receipt is best-effort */ }
      setDepositForm(null);
      fetchAll();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail
        : 'Could not record deposit';
      toast({ variant: 'destructive', title: 'Error', description: msg });
      setDepositForm(p => ({ ...p, busy: false }));
    }
  };

  // ────────────────────────────────────────────────────────────────────
  // Discharge orchestrator
  //   1. Stage = finalize  → operator confirms settle direction/amount
  //                          → POST /bill/finalize-and-settle
  //                          → moves to clinical stage
  //   2. Stage = clinical  → opens DischargeWizard
  //                          → onDischarged moves to gatepass stage
  //   3. Stage = gatepass  → operator fills attendant info
  //                          → POST /gate-pass → prints bill + gatepass
  // ────────────────────────────────────────────────────────────────────
  const startDischarge = () => {
    if (!derived) return;
    const direction = derived.owes > 0.01 ? 'collect'
                    : derived.owes < -0.01 ? 'refund'
                    : 'none';
    const amount = Math.abs(derived.owes).toFixed(2);
    setOrchestrator({
      stage: 'finalize',
      settleForm: {
        direction,
        amount: direction === 'none' ? '0' : amount,
        method: 'cash',
        ref: '',
        notes: '',
        busy: false,
      },
      gatePassForm: null,
    });
  };

  const submitFinalize = async () => {
    const { settleForm } = orchestrator;
    const amt = parseFloat(settleForm.amount || '0');
    const body = {
      discount_value: 0,
      discount_type: 'flat',
      tax_percentage: 0,
      settle: {
        direction: settleForm.direction === 'none' ? 'collect' : settleForm.direction,
        amount: settleForm.direction === 'none' ? 0 : amt,
        payment_method: settleForm.method,
        reference_number: settleForm.ref || null,
        notes: settleForm.notes || null,
      },
    };
    // Backend requires amount to exactly balance the bill. Validate here for a
    // crisp error instead of a 400 from the server.
    if (settleForm.direction === 'collect' && !(amt > 0) && derived?.owes > 0.01) {
      toast({ variant: 'destructive', title: 'Collect amount required',
              description: `Patient owes ${rupee(derived.owes)} — enter that amount.` });
      return;
    }
    if (settleForm.direction === 'refund' && !(amt > 0)) {
      toast({ variant: 'destructive', title: 'Refund amount required' });
      return;
    }
    setOrchestrator(p => ({ ...p, settleForm: { ...p.settleForm, busy: true } }));
    try {
      await axios.post(`/api/inpatient/admissions/${admissionId}/bill/finalize-and-settle`, body);
      toast({ title: 'Final bill generated',
              description: `Balance settled. Now fill the clinical discharge summary.` });
      await fetchAll();
      // Move to clinical stage — opens DischargeWizard
      setOrchestrator(p => ({ ...p, stage: 'clinical', settleForm: null }));
    } catch (err) {
      const detail = err.response?.data?.detail;
      // Bill already exists? — skip ahead to clinical (operator can still proceed)
      if (err.response?.status === 409 && detail?.code === 'final_bill_exists') {
        toast({ title: 'Final bill already exists', description: 'Proceeding to clinical step.' });
        await fetchAll();
        setOrchestrator(p => ({ ...p, stage: 'clinical', settleForm: null }));
        return;
      }
      const msg = typeof detail === 'string' ? detail : (detail?.message || 'Could not finalize bill');
      toast({ variant: 'destructive', title: 'Finalize failed', description: msg });
      setOrchestrator(p => ({ ...p, settleForm: { ...p.settleForm, busy: false } }));
    }
  };

  const onDischargeWizardDone = async () => {
    // DischargeWizard already POSTed /discharge and closed itself. Backend
    // has flipped the bed to 'cleaning' and recomputed room.available_beds.
    await fetchAll();
    toast({
      title: 'Discharged',
      description: admission?.bed_id
        ? 'Bed released (status: cleaning). Now issue the gate pass.'
        : 'Now issue the gate pass.',
    });
    setOrchestrator(p => ({
      ...p, stage: 'gatepass',
      gatePassForm: {
        attendant_name: '',
        attendant_relationship: '',
        vehicle_no: '',
        notes: '',
        busy: false,
        overrideErr: null,
        overrideReason: '',
      },
    }));
  };

  const submitGatePass = async () => {
    const { gatePassForm } = orchestrator;
    if (!gatePassForm.attendant_name.trim()) {
      toast({ variant: 'destructive', title: 'Attendant name required' });
      return;
    }
    if (gatePassForm.overrideErr && !gatePassForm.overrideReason.trim()) {
      toast({ variant: 'destructive', title: 'Override reason required' });
      return;
    }
    setOrchestrator(p => ({ ...p, gatePassForm: { ...p.gatePassForm, busy: true } }));
    try {
      await axios.post(`/api/inpatient/admissions/${admissionId}/gate-pass`, {
        attendant_name: gatePassForm.attendant_name.trim(),
        attendant_relationship: gatePassForm.attendant_relationship.trim() || null,
        vehicle_no: gatePassForm.vehicle_no.trim() || null,
        notes: gatePassForm.notes.trim() || null,
        override_reason: gatePassForm.overrideErr ? gatePassForm.overrideReason.trim() : undefined,
      });
      toast({ title: 'Gate pass issued', description: 'Printing bill and gate pass…' });
      setOrchestrator({ stage: null, settleForm: null, gatePassForm: null });
      await fetchAll();
      // Print both — bill first, then gatepass
      await printBill();
      await printGatePass();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 409 && detail?.code === 'outstanding_bill') {
        setOrchestrator(p => ({
          ...p, gatePassForm: { ...p.gatePassForm, busy: false, overrideErr: detail },
        }));
        toast({ variant: 'destructive', title: 'Outstanding balance',
                description: 'Settle the listed bills or provide an override reason.' });
        return;
      }
      const msg = typeof detail === 'string' ? detail : (detail?.message || 'Could not issue gate pass');
      toast({ variant: 'destructive', title: 'Error', description: msg });
      setOrchestrator(p => ({ ...p, gatePassForm: { ...p.gatePassForm, busy: false } }));
    }
  };

  const cancelOrchestration = () => {
    setOrchestrator({ stage: null, settleForm: null, gatePassForm: null });
  };

  // ────────────────────────────────────────────────────────────────────
  // Post-discharge actions (collect late dues, issue gatepass alone, reprint)
  // ────────────────────────────────────────────────────────────────────
  const openLateCollect = () => {
    if (!derived) return;
    setCollectForm({
      amount: derived.owes > 0 ? derived.owes.toFixed(2) : '',
      method: 'cash', ref: '', notes: '', busy: false,
    });
  };

  const submitLateCollect = async () => {
    const amt = parseFloat(collectForm.amount);
    if (!(amt > 0)) {
      toast({ variant: 'destructive', title: 'Enter an amount' }); return;
    }
    setCollectForm(p => ({ ...p, busy: true }));
    try {
      const res = await axios.post(`/api/inpatient/admissions/${admissionId}/deposits`, {
        amount: amt, deposit_type: 'topup',
        payment_method: collectForm.method,
        reference_number: collectForm.ref || null,
        notes: collectForm.notes || null,
      });
      toast({ title: 'Payment recorded', description: `${rupee(amt)} collected.` });
      try {
        const pdfRes = await axios.get(
          `/api/inpatient/deposits/${res.data.id}/receipt/pdf`,
          { responseType: 'blob' },
        );
        printPdfFromUrl(URL.createObjectURL(pdfRes.data));
      } catch (_) {}
      setCollectForm(null);
      fetchAll();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail : 'Could not record payment';
      toast({ variant: 'destructive', title: 'Error', description: msg });
      setCollectForm(p => ({ ...p, busy: false }));
    }
  };

  const openIssueLateGatepass = () => {
    setOrchestrator({
      stage: 'gatepass',
      settleForm: null,
      gatePassForm: {
        attendant_name: '', attendant_relationship: '', vehicle_no: '', notes: '',
        busy: false, overrideErr: null, overrideReason: '',
      },
    });
  };

  // ────────────────────────────────────────────────────────────────────
  // PDF prints (best-effort, share the printPdfFromUrl helper)
  // ────────────────────────────────────────────────────────────────────
  const printBill = async () => {
    try {
      const res = await axios.get(
        `/api/inpatient/admissions/${admissionId}/bill/pdf`,
        { responseType: 'blob', params: {} });
      printPdfFromUrl(URL.createObjectURL(res.data));
    } catch (err) {
      toast({ variant: 'destructive', title: 'Bill print failed',
              description: 'Open the bill from the table to retry.' });
    }
  };

  const printGatePass = async () => {
    try {
      const res = await axios.get(
        `/api/inpatient/admissions/${admissionId}/gate-pass/pdf`,
        { responseType: 'blob', params: {} });
      printPdfFromUrl(URL.createObjectURL(res.data));
    } catch (err) {
      toast({ variant: 'destructive', title: 'Gate pass print failed' });
    }
  };

  const deleteDeposit = async (dep) => {
    if (!window.confirm(`Delete deposit ${dep.deposit_number} (${rupee(dep.amount)})?`)) return;
    try {
      await axios.delete(`/api/inpatient/deposits/${dep.id}`);
      toast({ title: 'Deposit deleted' });
      fetchAll();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail : 'Could not delete deposit';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    }
  };

  // ────────────────────────────────────────────────────────────────────
  // Render
  // ────────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-gray-500">
          <Loader2 className="h-6 w-6 mx-auto animate-spin" />
          <p className="text-sm mt-2">Loading admission…</p>
        </CardContent>
      </Card>
    );
  }
  if (!admission || !derived) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-gray-500">
          Admission not found.
          {onBack && <div className="mt-3"><Button variant="outline" onClick={onBack}>
            <ArrowLeft className="h-4 w-4 mr-1" /> Back
          </Button></div>}
        </CardContent>
      </Card>
    );
  }

  const owesBadge = derived.owes > 0.01
    ? <Badge className="bg-red-100 text-red-800">Owes {rupee(derived.owes)}</Badge>
    : derived.owes < -0.01
      ? <Badge className="bg-blue-100 text-blue-800">Credit {rupee(Math.abs(derived.owes))}</Badge>
      : <Badge className="bg-green-100 text-green-800">Settled</Badge>;

  const statusBadge = derived.isDischarged
    ? <Badge className="bg-gray-200 text-gray-800">Discharged</Badge>
    : <Badge className="bg-emerald-100 text-emerald-800">Admitted</Badge>;

  // What action buttons to show in the right-hand action panel
  const renderActions = () => {
    if (!derived.isDischarged) {
      // Active admission — main flow is "Discharge & Issue Gate Pass"
      const hasFinal = !!finalBill;
      return (
        <div className="space-y-2">
          {canAddDeposit && (
            <Button className="w-full" variant="outline" onClick={openDeposit}>
              <Wallet className="h-4 w-4 mr-2" /> Receive Deposit
            </Button>
          )}
          {canFinalize && canDischarge && canIssuePass && (
            <Button className="w-full" onClick={startDischarge}>
              <Stethoscope className="h-4 w-4 mr-2" />
              {hasFinal ? 'Resume Discharge' : 'Discharge & Issue Gate Pass'}
            </Button>
          )}
          {hasFinal && (
            <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
              A final bill ({finalBill.bill_number}) already exists. The discharge flow
              will skip the finalize step.
            </p>
          )}
        </div>
      );
    }
    // Discharged — late collection / late gate pass / reprints
    return (
      <div className="space-y-2">
        {derived.owes > 0.01 && canAddDeposit && (
          <Button className="w-full" onClick={openLateCollect}>
            <Banknote className="h-4 w-4 mr-2" /> Collect Outstanding {rupee(derived.owes)}
          </Button>
        )}
        {derived.owes < -0.01 && canRefund && (
          <p className="text-[11px] text-blue-700 bg-blue-50 border border-blue-200 rounded p-2">
            Patient over-deposited by {rupee(Math.abs(derived.owes))} — issue a refund
            from the deposits panel.
          </p>
        )}
        {!gatePass && canIssuePass && (
          <Button className="w-full" variant={derived.owes > 0.01 ? 'outline' : 'default'}
                  onClick={openIssueLateGatepass}>
            <FileBadge className="h-4 w-4 mr-2" /> Issue Gate Pass
          </Button>
        )}
        {gatePass && (
          <Button className="w-full" variant="outline" onClick={printGatePass}>
            <Printer className="h-4 w-4 mr-2" /> Reprint Gate Pass
          </Button>
        )}
        {finalBill && (
          <Button className="w-full" variant="outline" onClick={printBill}>
            <Printer className="h-4 w-4 mr-2" /> Reprint Final Bill
          </Button>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {onBack && (
            <Button variant="ghost" size="sm" onClick={onBack}>
              <ArrowLeft className="h-4 w-4 mr-1" /> Back
            </Button>
          )}
          <div>
            <h2 className="text-lg font-semibold">{admission.patient_name}</h2>
            <div className="text-xs text-gray-500">
              {admission.admission_number}
              {admission.room_number && (
                <> · Room {admission.room_number}{admission.bed_label ? ` / ${admission.bed_label}` : ''}</>
              )}
              {admission.admission_date && (
                <> · admitted {new Date(admission.admission_date).toLocaleDateString()}</>
              )}
              {derived.isDischarged && admission.discharge_date && (
                <> · discharged {new Date(admission.discharge_date).toLocaleDateString()}</>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {statusBadge}
          {owesBadge}
          {gatePass && <Badge className="bg-purple-100 text-purple-800">
            Gate pass · {gatePass.pass_number}
          </Badge>}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {/* Left: bill + deposits (2/3 width) */}
        <div className="col-span-2 space-y-4">
          {/* Running bill summary */}
          <Card>
            <CardHeader className="pb-2 flex flex-row items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <IndianRupee className="h-4 w-4" /> Running Bill
                {finalBill && (
                  <Badge className="ml-2 bg-blue-100 text-blue-800 text-xs">
                    Finalized · {finalBill.bill_number}
                  </Badge>
                )}
              </CardTitle>
              <div className="flex items-center gap-1">
                {canAdjustBill && (
                  <Button size="sm" variant="outline" onClick={() => setBillOpen(true)}>
                    <Receipt className="h-3.5 w-3.5 mr-1" /> View / Adjust
                  </Button>
                )}
                <Button size="sm" variant="outline" onClick={printBill}>
                  <FileDown className="h-3.5 w-3.5 mr-1" /> PDF
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
                <Stat label="Stay charges"   value={rupee(derived.stayCharges)} />
                <Stat label="Deposits"       value={rupee(derived.deposited)} />
                <Stat label={derived.owes >= 0 ? 'Outstanding' : 'Credit'}
                      value={rupee(Math.abs(derived.owes))}
                      tone={derived.owes > 0.01 ? 'red' : derived.owes < -0.01 ? 'blue' : 'green'} />
                {bill?.stay_days != null && <Stat label="Stay days" value={String(bill.stay_days)} />}
                {bill?.room_total != null && <Stat label="Room"        value={rupee(bill.room_total)} />}
                {bill?.visit_total != null && <Stat label="Doctor visits" value={rupee(bill.visit_total)} />}
                {bill?.ot_total != null && bill.ot_total > 0 && <Stat label="OT" value={rupee(bill.ot_total)} />}
                {bill?.ancillary_total != null && bill.ancillary_total > 0 && (
                  <Stat label="Ancillary" value={rupee(bill.ancillary_total)} />
                )}
                {bill?.lab_total != null && bill.lab_total > 0 && (
                  <Stat label="Lab" value={rupee(bill.lab_total)} />
                )}
                {bill?.pharmacy_total != null && bill.pharmacy_total > 0 && (
                  <Stat label="Pharmacy" value={rupee(bill.pharmacy_total)} />
                )}
              </div>
            </CardContent>
          </Card>

          {/* Deposits list */}
          <Card>
            <CardHeader className="pb-2 flex flex-row items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Wallet className="h-4 w-4" /> Deposits ({deposits.length})
              </CardTitle>
              {canAddDeposit && !derived.isDischarged && (
                <Button size="sm" onClick={openDeposit}>
                  <Plus className="h-3.5 w-3.5 mr-1" /> Add Deposit
                </Button>
              )}
            </CardHeader>
            <CardContent>
              {deposits.length === 0 ? (
                <p className="text-xs text-gray-500 py-2">No deposits yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b bg-gray-50 text-left">
                        <th className="py-1.5 px-2">Receipt #</th>
                        <th className="py-1.5 px-2">Date</th>
                        <th className="py-1.5 px-2">Type</th>
                        <th className="py-1.5 px-2">Method</th>
                        <th className="py-1.5 px-2 text-right">Amount</th>
                        <th className="py-1.5 px-2 w-12"></th>
                      </tr>
                    </thead>
                    <tbody>
                      {deposits.map(d => (
                        <tr key={d.id} className="border-b hover:bg-gray-50">
                          <td className="py-1.5 px-2 font-mono">{d.deposit_number}</td>
                          <td className="py-1.5 px-2">
                            {d.received_at ? new Date(d.received_at).toLocaleString() : '—'}
                          </td>
                          <td className="py-1.5 px-2 capitalize">{d.deposit_type}</td>
                          <td className="py-1.5 px-2 capitalize">{d.payment_method}</td>
                          <td className="py-1.5 px-2 text-right font-medium">
                            {d.deposit_type === 'refund'
                              ? <span className="text-blue-700">-{rupee(d.amount)}</span>
                              : rupee(d.amount)}
                          </td>
                          <td className="py-1.5 px-2 text-right">
                            {canAddDeposit && !derived.isDischarged && (
                              <Button size="sm" variant="ghost" className="h-7 w-7 p-0"
                                      onClick={() => deleteDeposit(d)}>
                                <Trash2 className="h-3.5 w-3.5 text-red-500" />
                              </Button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right: action panel (1/3 width) */}
        <div>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">
                {derived.isDischarged ? 'Post-Discharge Actions' : 'Discharge Flow'}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {renderActions()}
              {derived.isDischarged && (
                <div className="mt-3 text-[11px] text-gray-500 flex items-center gap-1">
                  <BedDouble className="h-3 w-3" />
                  Bed already released on discharge.
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* ──────────── Deposit dialog (during stay) ──────────── */}
      <Dialog open={!!depositForm} onOpenChange={v => !v && setDepositForm(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Receive Deposit</DialogTitle>
            <DialogDescription>Top-up deposit for {admission.patient_name}.</DialogDescription>
          </DialogHeader>
          {depositForm && (
            <div className="space-y-3">
              <div>
                <Label>Amount (₹) *</Label>
                <Input type="number" min="0" step="0.01" value={depositForm.amount}
                       onChange={e => setDepositForm(p => ({ ...p, amount: e.target.value }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Method</Label>
                  <Select value={depositForm.method}
                          onValueChange={v => setDepositForm(p => ({ ...p, method: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {PAYMENT_METHODS.map(m => (
                        <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Reference</Label>
                  <Input value={depositForm.ref}
                         onChange={e => setDepositForm(p => ({ ...p, ref: e.target.value }))}
                         placeholder="Txn / cheque #" />
                </div>
              </div>
              <div>
                <Label>Notes</Label>
                <Textarea rows={2} value={depositForm.notes}
                          onChange={e => setDepositForm(p => ({ ...p, notes: e.target.value }))} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDepositForm(null)}>Cancel</Button>
            <Button onClick={submitDeposit} disabled={depositForm?.busy}>
              {depositForm?.busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              <Banknote className="h-4 w-4 mr-1" /> Record &amp; Print Receipt
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ──────────── Orchestrator: Finalize stage ──────────── */}
      <Dialog open={orchestrator.stage === 'finalize'}
              onOpenChange={v => !v && cancelOrchestration()}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Generate Final Bill</DialogTitle>
            <DialogDescription>
              Step 1 of 3 — finalize the bill and settle the balance. Then you'll
              record the clinical discharge, then issue the gate pass.
            </DialogDescription>
          </DialogHeader>
          {orchestrator.settleForm && (
            <div className="space-y-3 text-sm">
              <div className="bg-gray-50 border rounded p-3 space-y-1">
                <div className="flex justify-between"><span>Stay charges</span><b>{rupee(derived.stayCharges)}</b></div>
                <div className="flex justify-between"><span>Deposits received</span><b>{rupee(derived.deposited)}</b></div>
                <div className="flex justify-between border-t pt-1">
                  <span className="font-semibold">
                    {orchestrator.settleForm.direction === 'collect' ? 'To collect now' :
                     orchestrator.settleForm.direction === 'refund'  ? 'To refund now'  :
                     'Balance'}
                  </span>
                  <b className={
                    orchestrator.settleForm.direction === 'collect' ? 'text-red-600' :
                    orchestrator.settleForm.direction === 'refund'  ? 'text-blue-600' :
                    'text-green-600'
                  }>{rupee(Math.abs(derived.owes))}</b>
                </div>
              </div>

              {orchestrator.settleForm.direction !== 'none' && (
                <>
                  <div>
                    <Label>{orchestrator.settleForm.direction === 'refund' ? 'Refund amount' : 'Collect amount'} (₹) *</Label>
                    <Input type="number" min="0" step="0.01"
                           value={orchestrator.settleForm.amount}
                           onChange={e => setOrchestrator(p => ({
                             ...p, settleForm: { ...p.settleForm, amount: e.target.value },
                           }))} />
                    <p className="text-[10px] text-gray-500 mt-1">
                      Must exactly balance the bill — pre-filled with the outstanding amount.
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label>Method</Label>
                      <Select value={orchestrator.settleForm.method}
                              onValueChange={v => setOrchestrator(p => ({
                                ...p, settleForm: { ...p.settleForm, method: v },
                              }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {PAYMENT_METHODS.map(m => (
                            <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label>Reference</Label>
                      <Input value={orchestrator.settleForm.ref}
                             onChange={e => setOrchestrator(p => ({
                               ...p, settleForm: { ...p.settleForm, ref: e.target.value },
                             }))} placeholder="Txn / cheque #" />
                    </div>
                  </div>
                </>
              )}
              {orchestrator.settleForm.direction === 'none' && (
                <p className="text-xs text-green-700 bg-green-50 border border-green-200 rounded p-2">
                  <CheckCircle2 className="h-3 w-3 inline mr-1" />
                  Balance already zero — final bill will be generated with no
                  additional payment.
                </p>
              )}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={cancelOrchestration}>Cancel</Button>
            <Button onClick={submitFinalize} disabled={orchestrator.settleForm?.busy}>
              {orchestrator.settleForm?.busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Generate Bill &amp; Continue
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ──────────── Orchestrator: Clinical stage (DischargeWizard) ──────────── */}
      <DischargeWizard
        open={orchestrator.stage === 'clinical'}
        admission={admission}
        onClose={cancelOrchestration}
        onDischarged={onDischargeWizardDone}
      />

      {/* ──────────── Orchestrator: Gate pass stage ──────────── */}
      <Dialog open={orchestrator.stage === 'gatepass'}
              onOpenChange={v => !v && cancelOrchestration()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Issue Gate Pass</DialogTitle>
            <DialogDescription>
              Final step — record who is taking the patient home, then print the
              bill and gate pass.
            </DialogDescription>
          </DialogHeader>
          {orchestrator.gatePassForm && (
            <div className="space-y-3">
              {orchestrator.gatePassForm.overrideErr && (
                <div className="border border-amber-300 bg-amber-50 rounded p-2 text-xs space-y-1">
                  <p className="font-semibold text-amber-900 flex items-center gap-1">
                    <AlertTriangle className="h-3 w-3" />
                    Outstanding: {rupee(orchestrator.gatePassForm.overrideErr.outstanding || 0)}
                  </p>
                  <Label className="text-xs">Override reason (required) *</Label>
                  <Input value={orchestrator.gatePassForm.overrideReason}
                         onChange={e => setOrchestrator(p => ({
                           ...p, gatePassForm: { ...p.gatePassForm, overrideReason: e.target.value },
                         }))}
                         placeholder="e.g. Insurance pending — vendor approved" />
                </div>
              )}
              <div>
                <Label>Attendant name *</Label>
                <Input value={orchestrator.gatePassForm.attendant_name}
                       onChange={e => setOrchestrator(p => ({
                         ...p, gatePassForm: { ...p.gatePassForm, attendant_name: e.target.value },
                       }))} placeholder="e.g. Lakshmi Kumar" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Relationship</Label>
                  <Input value={orchestrator.gatePassForm.attendant_relationship}
                         onChange={e => setOrchestrator(p => ({
                           ...p, gatePassForm: { ...p.gatePassForm, attendant_relationship: e.target.value },
                         }))} placeholder="Wife / Son" />
                </div>
                <div>
                  <Label>Vehicle no.</Label>
                  <Input value={orchestrator.gatePassForm.vehicle_no}
                         onChange={e => setOrchestrator(p => ({
                           ...p, gatePassForm: { ...p.gatePassForm, vehicle_no: e.target.value },
                         }))} placeholder="TS09 AB 1234" />
                </div>
              </div>
              <div>
                <Label>Notes</Label>
                <Textarea rows={2} value={orchestrator.gatePassForm.notes}
                          onChange={e => setOrchestrator(p => ({
                            ...p, gatePassForm: { ...p.gatePassForm, notes: e.target.value },
                          }))} />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={cancelOrchestration}>Cancel</Button>
            <Button onClick={submitGatePass} disabled={orchestrator.gatePassForm?.busy}>
              {orchestrator.gatePassForm?.busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              <Printer className="h-4 w-4 mr-1" /> Issue &amp; Print
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ──────────── Late-collect dialog (post-discharge) ──────────── */}
      <Dialog open={!!collectForm} onOpenChange={v => !v && setCollectForm(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Collect Outstanding Payment</DialogTitle>
          </DialogHeader>
          {collectForm && (
            <div className="space-y-3">
              <div className="bg-gray-50 border rounded p-2 text-sm">
                <div><b>{admission.patient_name}</b> · {admission.admission_number}</div>
                <div className="text-xs text-red-600">Owes {rupee(derived.owes)}</div>
              </div>
              <div>
                <Label>Amount (₹) *</Label>
                <Input type="number" min="0" step="0.01" value={collectForm.amount}
                       onChange={e => setCollectForm(p => ({ ...p, amount: e.target.value }))} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Method</Label>
                  <Select value={collectForm.method}
                          onValueChange={v => setCollectForm(p => ({ ...p, method: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {PAYMENT_METHODS.map(m => (
                        <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Reference</Label>
                  <Input value={collectForm.ref}
                         onChange={e => setCollectForm(p => ({ ...p, ref: e.target.value }))} />
                </div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setCollectForm(null)}>Cancel</Button>
            <Button onClick={submitLateCollect} disabled={collectForm?.busy}>
              {collectForm?.busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              <Banknote className="h-4 w-4 mr-1" /> Record Payment
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ──────────── Bill detail dialog (view / discount / tax / regenerate) ──────────── */}
      <BillDetailDialog
        open={billOpen}
        admission={admission}
        onClose={() => setBillOpen(false)}
        onFinalized={() => { setBillOpen(false); fetchAll(); }}
      />
    </div>
  );
};

const Stat = ({ label, value, tone }) => (
  <div>
    <div className="text-[11px] text-gray-500 uppercase tracking-wide">{label}</div>
    <div className={
      'text-sm font-semibold ' +
      (tone === 'red'   ? 'text-red-600'   :
       tone === 'blue'  ? 'text-blue-600'  :
       tone === 'green' ? 'text-green-600' : 'text-gray-900')
    }>{value}</div>
  </div>
);

export default BillingDischargePage;
