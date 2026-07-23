import { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { useToast } from '../../../../hooks/use-toast';
import { printPdfFromUrl } from '../../../../utils/printPdf';
import {
  EMPTY_CLINICAL_FORM,
  EMPTY_GATE_PASS_FORM,
  EMPTY_SETTLE_FORM,
  computeDerived,
  computeCheckoutSettlement,
  resolveStartStep,
  draftStorageKey,
  rupee,
} from './constants';

export function useDischargeCheckout(admissionId, permissions = {}) {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [admission, setAdmission] = useState(null);
  const [bill, setBill] = useState(null);
  const [balance, setBalance] = useState(null);
  const [deposits, setDeposits] = useState([]);
  const [finalBill, setFinalBill] = useState(null);
  const [gatePass, setGatePass] = useState(null);
  const [step, setStep] = useState(1);
  const [maxReachable, setMaxReachable] = useState(1);
  const [clinicalForm, setClinicalForm] = useState(EMPTY_CLINICAL_FORM);
  const [settleForm, setSettleForm] = useState(null);
  const [gatePassForm, setGatePassForm] = useState(EMPTY_GATE_PASS_FORM);
  const [blockers, setBlockers] = useState([]);
  const [depositForm, setDepositForm] = useState(null);
  const [summaryDoc, setSummaryDoc] = useState(null);

  const canAddDeposit = permissions.receive_deposits !== false;
  const canFinalize = permissions.finalize_bill !== false;
  const canDischarge = Boolean(permissions.discharge_patients);
  const canIssuePass = Boolean(permissions.issue_gate_pass);
  const canWriteSummary = Boolean(permissions.write_discharge_summary);
  const canViewSummary = Boolean(permissions.view_discharge_summary);

  const derived = useMemo(
    () => computeDerived(bill, balance, admission, finalBill),
    [bill, balance, admission, finalBill],
  );
  const settlement = useMemo(
    () => computeCheckoutSettlement(derived, settleForm, !!finalBill),
    [derived, settleForm, finalBill],
  );

  const loadDraft = useCallback((id) => {
    try {
      const raw = sessionStorage.getItem(draftStorageKey(id));
      if (!raw) return null;
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }, []);

  const saveDraft = useCallback((id, draft) => {
    try {
      sessionStorage.setItem(draftStorageKey(id), JSON.stringify(draft));
    } catch { /* ignore quota */ }
  }, []);

  const clearDraft = useCallback((id) => {
    try {
      sessionStorage.removeItem(draftStorageKey(id));
    } catch { /* ignore */ }
  }, []);

  const fetchAll = useCallback(async () => {
    if (!admissionId) return null;
    setLoading(true);
    try {
      const [admRes, billRes, balRes, depRes, billsRes, gpRes, summaryRes] = await Promise.all([
        axios.get(`/api/inpatient/admissions/${admissionId}`),
        axios.get(`/api/inpatient/admissions/${admissionId}/bill`, { params: { unbilled_only: false } }),
        axios.get(`/api/inpatient/admissions/${admissionId}/balance`),
        axios.get(`/api/inpatient/admissions/${admissionId}/deposits`),
        axios.get(`/api/inpatient/admissions/${admissionId}/bills`).catch(() => ({ data: [] })),
        axios.get(`/api/inpatient/admissions/${admissionId}/gate-pass`).catch(() => ({ data: null })),
        axios.get(`/api/inpatient/admissions/${admissionId}/discharge-summary`).catch(() => ({ data: null })),
      ]);
      const adm = admRes.data;
      const billData = billRes.data;
      const balData = balRes.data;
      const deps = depRes.data?.items || depRes.data || [];
      const bills = billsRes.data?.items || billsRes.data || [];
      const finalised = bills.find(b => b.bill_subtype === 'final' && b.status !== 'cancelled');
      const gp = gpRes.data || null;
      const summary = summaryRes.data || null;

      setAdmission(adm);
      setBill(billData);
      setBalance(balData);
      setDeposits(deps);
      setFinalBill(finalised || null);
      setGatePass(gp);
      setSummaryDoc(summary);

      const d = computeDerived(billData, balData, adm, finalised || null);
      setBlockers(prev => prev.filter(blocker => {
        if (blocker.code === 'outstanding_balance' && d?.owes <= 0.01) return false;
        if (blocker.code === 'final_bill_required' && finalised) return false;
        return true;
      }));
      if (d?.owes <= 0.01) {
        setGatePassForm(prev => prev.overrideErr
          ? { ...prev, overrideErr: null, overrideReason: '' }
          : prev);
      }
      const start = resolveStartStep({
        admission: adm,
        finalBill: finalised,
        gatePass: gp,
        derived: d,
      });

      const draft = loadDraft(admissionId);
      const summaryClinical = summary ? {
        discharge_type: summary.discharge_type || 'normal',
        condition_on_discharge: summary.condition_on_discharge || 'stable',
      } : {};
      if (draft?.clinicalForm) {
        setClinicalForm({ ...EMPTY_CLINICAL_FORM, ...summaryClinical, ...draft.clinicalForm });
      } else {
        setClinicalForm({ ...EMPTY_CLINICAL_FORM, ...summaryClinical });
      }
      if (draft?.gatePassForm) setGatePassForm({ ...EMPTY_GATE_PASS_FORM, ...draft.gatePassForm });
      if (draft?.step && !gp) {
        setStep(Math.max(start, Math.min(draft.step, 4)));
        setMaxReachable(Math.max(start, draft.maxReachable || start));
      } else {
        setStep(start);
        setMaxReachable(start);
      }

      if (d) setSettleForm(EMPTY_SETTLE_FORM(d));
      return { adm, d, start, finalised, gp };
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Could not load admission',
        description: err.response?.data?.detail || 'Network error',
      });
      return null;
    } finally {
      setLoading(false);
    }
  }, [admissionId, loadDraft, toast]);

  useEffect(() => {
    if (!admissionId) return;
    setClinicalForm(EMPTY_CLINICAL_FORM);
    setGatePassForm(EMPTY_GATE_PASS_FORM);
    setBlockers([]);
    fetchAll();
  }, [admissionId, fetchAll]);

  useEffect(() => {
    if (!admissionId || loading) return;
    saveDraft(admissionId, {
      step,
      maxReachable,
      clinicalForm,
      gatePassForm,
    });
  }, [admissionId, step, maxReachable, clinicalForm, gatePassForm, loading, saveDraft]);

  const updateClinical = (patch) => setClinicalForm(p => ({ ...p, ...patch }));

  const goToStep = (n) => {
    if (derived?.isDischarged && n === 3) return;
    if (n >= 1 && n <= 4 && n <= maxReachable) setStep(n);
  };

  const advanceStep = (n) => {
    setStep(n);
    setMaxReachable(prev => Math.max(prev, n));
  };

  const validateStep = (s) => {
    if (s === 1) {
      if (!finalBill && !canFinalize) return 'You do not have permission to finalize bills.';
      return null;
    }
    if (s === 2) {
      if (!finalBill) return 'Generate the final bill before settling.';
      return null;
    }
    if (s === 3) {
      const dischargeType = clinicalForm.discharge_type || summaryDoc?.discharge_type || 'normal';
      const isDama = dischargeType === 'against_advice';
      const isDeath = dischargeType === 'death';
      if (!isDeath && !isDama) {
        const st = summaryDoc?.status;
        if (!st || !['ready', 'locked'].includes(st)) {
          return 'Doctor must finalize the discharge summary before discharge.';
        }
      }
      if (blockers.length > 0 && !clinicalForm.override_reason.trim()) {
        return 'Override reason is required to proceed past safety gates.';
      }
      return null;
    }
    if (s === 4) {
      if (!gatePassForm.attendant_name.trim()) return 'Attendant name is required.';
      if (gatePassForm.overrideErr && !gatePassForm.overrideReason.trim()) {
        return 'Override reason is required.';
      }
      return null;
    }
    return null;
  };

  /** Step 1 — generate final bill only (discount/tax). Settlement is step 2. */
  const submitFinalizeBill = async () => {
    if (finalBill) {
      const owes = Math.abs(Number(derived?.owes || 0));
      advanceStep(owes > 0.01 ? 2 : 3);
      return true;
    }
    if (!settleForm) return false;
    setSubmitting(true);
    try {
      const billBody = {
        discount_value: parseFloat(settleForm.discountValue || '0') || 0,
        discount_type: settleForm.discountType || 'flat',
        tax_percentage: parseFloat(settleForm.taxPct || '0') || 0,
      };
      await axios.post(`/api/inpatient/admissions/${admissionId}/bill/finalize`, billBody);
      toast({ title: 'Final bill generated', description: 'Continue to collect or refund.' });
      const refreshed = await fetchAll();
      if (refreshed?.d) setSettleForm(EMPTY_SETTLE_FORM(refreshed.d));
      const owes = Math.abs(Number(refreshed?.d?.owes || 0));
      advanceStep(owes > 0.01 ? 2 : 3);
      return true;
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 409 && detail?.code === 'final_bill_exists') {
        toast({ title: 'Final bill already exists', description: 'Continue to settlement.' });
        const refreshed = await fetchAll();
        const owes = Math.abs(Number(refreshed?.d?.owes || 0));
        advanceStep(owes > 0.01 ? 2 : 3);
        return true;
      }
      const msg = typeof detail === 'string' ? detail : (detail?.message || 'Could not finalize bill');
      toast({ variant: 'destructive', title: 'Finalize failed', description: msg });
      return false;
    } finally {
      setSubmitting(false);
    }
  };

  /** Step 2 — collect outstanding or refund credit against the final bill. */
  const submitSettle = async () => {
    if (!finalBill) {
      toast({ variant: 'destructive', title: 'Final bill required', description: 'Generate the final bill first.' });
      return false;
    }
    if (!settlement || settlement.direction === 'none') {
      advanceStep(3);
      return true;
    }
    if (settlement.direction === 'collect' && !canAddDeposit) {
      toast({
        variant: 'destructive',
        title: 'No permission to collect payment',
        description: 'A user with Receive Deposits permission must settle this balance.',
      });
      return false;
    }
    const amt = settlement.amount;
    setSubmitting(true);
    try {
      const isRefund = settlement.direction === 'refund';
      await axios.post(
        isRefund
          ? `/api/inpatient/admissions/${admissionId}/refund`
          : `/api/inpatient/admissions/${admissionId}/deposits`,
        {
          amount: amt,
          ...(isRefund ? {} : { deposit_type: 'topup' }),
          payment_method: settleForm?.method || 'cash',
          reference_number: settleForm?.ref || null,
          notes: settleForm?.notes || (isRefund
            ? 'Final bill refund at discharge'
            : 'Final bill payment collected at discharge'),
        },
      );
      const refreshed = await fetchAll();
      if (Math.abs(refreshed?.d?.owes || 0) <= 0.01) {
        toast({
          title: isRefund ? 'Refund recorded' : 'Payment collected',
          description: `${rupee(amt)} ${isRefund ? 'refunded' : 'received'}. Proceed to discharge summary.`,
        });
        advanceStep(3);
        return true;
      }
      toast({
        variant: 'destructive',
        title: 'Balance still outstanding',
        description: 'The billing balance changed. Review the updated amount before continuing.',
      });
      return false;
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : (detail?.message || 'Could not settle final bill');
      toast({ variant: 'destructive', title: 'Settlement failed', description: msg });
      return false;
    } finally {
      setSubmitting(false);
    }
  };

  const buildDischargePayload = () => {
    const payload = {
      discharge_type: clinicalForm.discharge_type || summaryDoc?.discharge_type || 'normal',
      condition_on_discharge: clinicalForm.condition_on_discharge
        || summaryDoc?.condition_on_discharge || 'stable',
    };
    if (blockers.length > 0) {
      const codes = blockers.map(b => b.code);
      if (codes.includes('outstanding_balance')) payload.force_outstanding_balance = true;
      if (codes.includes('unacknowledged_critical_alerts')) payload.force_unacknowledged_alerts = true;
      if (codes.includes('missing_surgical_consent')) payload.force_missing_consents = true;
      if (codes.includes('final_bill_required')) payload.force_no_final_bill = true;
      payload.override_reason = clinicalForm.override_reason.trim();
    }
    return payload;
  };

  const submitDischarge = async () => {
    if (derived?.isDischarged) {
      advanceStep(4);
      return { wasDeath: clinicalForm.discharge_type === 'death', skipped: true };
    }
    setSubmitting(true);
    try {
      const payload = buildDischargePayload();
      await axios.post(`/api/inpatient/admissions/${admissionId}/discharge`, payload);

      const isDeath = clinicalForm.discharge_type === 'death'
        || summaryDoc?.discharge_type === 'death';

      toast({
        title: 'Patient discharged',
        description: admission?.bed_id
          ? 'Bed released (cleaning). Complete gate pass next.'
          : 'Complete gate pass next.',
      });
      await fetchAll();
      advanceStep(4);
      return { wasDeath: isDeath, admissionId };
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 409 && detail?.code === 'discharge_summary_not_ready') {
        toast({
          variant: 'destructive',
          title: 'Summary not ready',
          description: detail.message || 'Doctor must finalize the discharge summary first.',
        });
        setStep(3);
        return null;
      }
      if (err.response?.status === 409 && detail?.code === 'credit_refund_required') {
        toast({
          variant: 'destructive', title: 'Refund required',
          description: detail.message || 'Return to Collect / Refund and issue refund.',
        });
        setStep(2);
        return null;
      }
      const gateCodes = ['outstanding_balance', 'unacknowledged_critical_alerts',
        'missing_surgical_consent', 'final_bill_required'];
      if (err.response?.status === 409 && detail?.code && gateCodes.includes(detail.code)) {
        setBlockers(prev => (prev.some(b => b.code === detail.code) ? prev : [...prev, detail]));
        toast({
          variant: 'destructive', title: 'Safety gate hit',
          description: `${detail.message} Provide override reason and resubmit.`,
        });
        if (detail.code === 'outstanding_balance' || detail.code === 'final_bill_required') {
          setStep(detail.code === 'final_bill_required' ? 1 : 2);
        }
        return null;
      }
      const msg = typeof detail === 'string' ? detail : (detail?.message || 'Discharge failed');
      toast({ variant: 'destructive', title: 'Error', description: msg });
      return null;
    } finally {
      setSubmitting(false);
    }
  };

  const submitGatePass = async () => {
    if (gatePass) {
      await printBill();
      await printGatePass();
      return true;
    }
    setSubmitting(true);
    try {
      await axios.post(`/api/inpatient/admissions/${admissionId}/gate-pass`, {
        attendant_name: gatePassForm.attendant_name.trim(),
        attendant_relationship: gatePassForm.attendant_relationship.trim() || null,
        vehicle_no: gatePassForm.vehicle_no.trim() || null,
        notes: gatePassForm.notes.trim() || null,
        override_reason: gatePassForm.overrideErr ? gatePassForm.overrideReason.trim() : undefined,
      });
      toast({ title: 'Gate pass issued', description: 'Printing bill and gate pass…' });
      clearDraft(admissionId);
      await fetchAll();
      await printBill();
      await printGatePass();
      return true;
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 409 && detail?.code === 'outstanding_bill') {
        setGatePassForm(p => ({ ...p, overrideErr: detail }));
        toast({ variant: 'destructive', title: 'Outstanding balance',
          description: 'Settle payment or provide override reason.' });
        return false;
      }
      const msg = typeof detail === 'string' ? detail : (detail?.message || 'Could not issue gate pass');
      toast({ variant: 'destructive', title: 'Error', description: msg });
      return false;
    } finally {
      setSubmitting(false);
    }
  };

  const printBill = async () => {
    try {
      const res = await axios.get(
        `/api/inpatient/admissions/${admissionId}/bill/pdf`,
        { responseType: 'blob' },
      );
      printPdfFromUrl(URL.createObjectURL(res.data));
    } catch {
      toast({ variant: 'destructive', title: 'Bill print failed' });
    }
  };

  const printGatePassPdf = async () => {
    try {
      const res = await axios.get(
        `/api/inpatient/admissions/${admissionId}/gate-pass/pdf`,
        { responseType: 'blob' },
      );
      printPdfFromUrl(URL.createObjectURL(res.data));
    } catch {
      toast({ variant: 'destructive', title: 'Gate pass print failed' });
    }
  };

  const printGatePass = printGatePassPdf;

  const printDischargeSummary = async () => {
    const ok = await printPdfFromUrl(
      `/api/inpatient/admissions/${admissionId}/discharge-summary/pdf`,
    );
    if (!ok) {
      toast({
        variant: 'destructive',
        title: 'Print failed',
        description: 'Discharge summary must be finalized by the doctor before printing',
      });
    }
  };

  const printAdmissionDetail = async () => {
    const ok = await printPdfFromUrl(
      `/api/inpatient/admissions/${admissionId}/admission-detail/pdf`,
    );
    if (!ok) {
      toast({
        variant: 'destructive',
        title: 'Print failed',
        description: 'Could not generate detailed admission summary PDF',
      });
    }
  };

  const submitDeposit = async () => {
    const amt = parseFloat(depositForm?.amount);
    if (!(amt > 0)) {
      toast({ variant: 'destructive', title: 'Enter an amount greater than zero' });
      return;
    }
    setSubmitting(true);
    try {
      const res = await axios.post(`/api/inpatient/admissions/${admissionId}/deposits`, {
        amount: amt,
        deposit_type: 'topup',
        payment_method: depositForm.method,
        reference_number: depositForm.ref || null,
        notes: depositForm.notes || null,
      });
      toast({ title: 'Deposit recorded', description: `${rupee(amt)} received.` });
      try {
        const pdfRes = await axios.get(
          `/api/inpatient/deposits/${res.data.id}/receipt/pdf`,
          { responseType: 'blob' },
        );
        printPdfFromUrl(URL.createObjectURL(pdfRes.data));
      } catch { /* best-effort */ }
      setDepositForm(null);
      await fetchAll();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail : 'Could not record deposit';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally {
      setSubmitting(false);
    }
  };

  const handleNext = async () => {
    const err = validateStep(step);
    if (err) {
      toast({ variant: 'destructive', title: 'Check fields', description: err });
      return null;
    }
    if (step === 1) {
      await submitFinalizeBill();
      return null;
    }
    if (step === 2) {
      await submitSettle();
      return null;
    }
    if (step === 3) {
      if (!canDischarge && !derived?.isDischarged) {
        toast({ variant: 'destructive', title: 'No permission to discharge patients' });
        return null;
      }
      if (derived?.isDischarged) {
        advanceStep(4);
        return null;
      }
      return submitDischarge();
    }
    if (step === 4) {
      if (!canIssuePass) {
        toast({ variant: 'destructive', title: 'No permission to issue gate pass' });
        return null;
      }
      await submitGatePass();
      return null;
    }
    advanceStep(step + 1);
    return null;
  };

  const handleBack = () => {
    if (step > 1) setStep(step - 1);
  };

  return {
    loading,
    submitting,
    admission,
    bill,
    balance,
    deposits,
    finalBill,
    gatePass,
    derived,
    settlement,
    step,
    maxReachable,
    clinicalForm,
    settleForm,
    setSettleForm,
    gatePassForm,
    setGatePassForm,
    blockers,
    depositForm,
    setDepositForm,
    canAddDeposit,
    canFinalize,
    canDischarge,
    canIssuePass,
    canWriteSummary,
    canViewSummary,
    summaryDoc,
    setSummaryDoc,
    refreshSummary: async () => {
      try {
        const res = await axios.get(`/api/inpatient/admissions/${admissionId}/discharge-summary`);
        setSummaryDoc(res.data);
        if (res.data?.discharge_type) {
          setClinicalForm(p => ({
            ...p,
            discharge_type: res.data.discharge_type,
            condition_on_discharge: res.data.condition_on_discharge || p.condition_on_discharge,
          }));
        }
      } catch {
        setSummaryDoc(null);
      }
    },
    updateClinical,
    goToStep,
    handleNext,
    handleBack,
    fetchAll,
    printBill,
    printGatePass,
    printDischargeSummary,
    printAdmissionDetail,
    submitDeposit,
    validateStep,
  };
}

export default useDischargeCheckout;
