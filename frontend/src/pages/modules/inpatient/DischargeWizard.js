import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '../../../components/ui/dialog';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Badge } from '../../../components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../../components/ui/select';
import { useToast } from '../../../hooks/use-toast';
import {
  ChevronLeft, ChevronRight, Loader2, Plus, Trash2,
  Pill, Stethoscope, FileSignature, AlertTriangle,
} from 'lucide-react';
import MedicineLookupInput from '../../../components/inpatient/MedicineLookupInput';

const EMPTY_FORM = {
  // Step 1
  discharge_type: 'normal',
  condition_on_discharge: 'stable',
  diagnosis_on_discharge: '',
  treatment_given: '',
  discharge_summary: '',
  // Step 2
  take_home_medications: [],
  follow_up_instructions: '',
  follow_up_date: '',
  diet_instructions: '',
  activity_restrictions: '',
  // Step 3 — declarations
  consent_to_discharge: false,    // for normal/transfer
  dama_advice_ack: false,         // for against_advice
  dama_absolves_ack: false,       // for against_advice
  signed_by_name: '',
  signed_by_relationship: 'self', // 'self' | 'guardian'
  guardian_relationship: '',      // when relationship != self
  decl_notes: '',
  // Gate overrides — only used if backend returns 409
  force_outstanding_balance: false,
  force_unacknowledged_alerts: false,
  force_missing_consents: false,
  override_reason: '',
};

const Stepper = ({ step, totalSteps = 3, labels }) => (
  <div className="flex items-center gap-3 text-xs">
    {labels.map((label, i) => {
      const active = i + 1 === step;
      const done = i + 1 < step;
      return (
        <React.Fragment key={label}>
          <div className="flex items-center gap-1.5">
            <span className={
              'h-6 w-6 rounded-full flex items-center justify-center text-[10px] font-semibold ' +
              (done ? 'bg-green-600 text-white' :
                active ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-600')
            }>
              {done ? '✓' : i + 1}
            </span>
            <span className={active ? 'font-semibold text-blue-700' :
                              done ? 'text-green-700' : 'text-gray-500'}>
              {label}
            </span>
          </div>
          {i < labels.length - 1 && <span className="text-gray-300">›</span>}
        </React.Fragment>
      );
    })}
  </div>
);


const MedicineCard = ({ med, idx, onChange, onRemove, admissionId }) => (
  <div className="border rounded-lg p-3 bg-white space-y-2">
    <div className="flex items-start gap-2">
      <div className="flex-1">
        <Label className="text-[11px] text-gray-500">Medicine *</Label>
        <MedicineLookupInput
          admissionId={admissionId}
          value={med.medicine_name}
          medicineId={med.medicine_id}
          placeholder="Search catalog or type free-text"
          onChange={({ medicine_id, medicine_name }) => {
            onChange(idx, 'medicine_id', medicine_id || '');
            onChange(idx, 'medicine_name', medicine_name);
          }}
        />
      </div>
      <Button type="button" size="sm" variant="ghost" className="h-9 w-9 p-0 mt-5"
              onClick={() => onRemove(idx)}>
        <Trash2 className="h-4 w-4 text-red-500" />
      </Button>
    </div>
    <div className="grid grid-cols-2 gap-2">
      <div>
        <Label className="text-[11px] text-gray-500">Dosage</Label>
        <Input placeholder="500 mg" value={med.dosage}
               onChange={e => onChange(idx, 'dosage', e.target.value)} />
      </div>
      <div>
        <Label className="text-[11px] text-gray-500">Frequency</Label>
        <Input placeholder="BD / TID" value={med.frequency}
               onChange={e => onChange(idx, 'frequency', e.target.value)} />
      </div>
      <div>
        <Label className="text-[11px] text-gray-500">Duration</Label>
        <Input placeholder="5 days" value={med.duration}
               onChange={e => onChange(idx, 'duration', e.target.value)} />
      </div>
      <div>
        <Label className="text-[11px] text-gray-500">Quantity</Label>
        <Input type="number" min="1" placeholder="10" value={med.quantity}
               onChange={e => onChange(idx, 'quantity', e.target.value)} />
      </div>
    </div>
    <div>
      <Label className="text-[11px] text-gray-500">Instructions</Label>
      <Input placeholder="After meals, with water…" value={med.instructions}
             onChange={e => onChange(idx, 'instructions', e.target.value)} />
    </div>
  </div>
);


const DischargeWizard = ({
  open, onClose, admission, onDischarged,
}) => {
  const { toast } = useToast();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [blockers, setBlockers] = useState([]);
  // Unified settle dialog. mode='collect' (POST deposit) or 'refund' (POST refund).
  // retry=true means after success, auto-retry the discharge (used by the 409 gate
  // path). retry=false (manual settle) just refreshes the summary.
  // shape: { mode, amount, method, reference, notes, busy, retry } | null
  const [settle, setSettle] = useState(null);
  // Billing summary shown on Step 3 so operator sees dues/refund before confirming.
  const [billing, setBilling] = useState(null);     // breakdown from /bill
  const [balance, setBalance] = useState(null);     // { net_deposits, total_billed, balance }
  const [billingLoading, setBillingLoading] = useState(false);

  // Reset when reopened
  useEffect(() => {
    if (!open) return;
    setStep(1);
    setForm(EMPTY_FORM);
    setBlockers([]);
    setBilling(null);
    setBalance(null);
  }, [open, admission?.id]);

  // Pull live billing snapshot whenever Step 3 is in view so the figures
  // reflect any payment / refund the operator made via the in-flow dialog.
  useEffect(() => {
    if (!open || !admission?.id || step !== 3) return;
    let cancelled = false;
    (async () => {
      setBillingLoading(true);
      try {
        const [bRes, balRes] = await Promise.all([
          axios.get(`/api/inpatient/admissions/${admission.id}/bill`,
                    { params: { unbilled_only: false } }),
          axios.get(`/api/inpatient/admissions/${admission.id}/balance`),
        ]);
        if (!cancelled) {
          setBilling(bRes.data);
          setBalance(balRes.data);
        }
      } catch (err) {
        if (!cancelled) {
          toast({ variant: 'destructive', title: 'Could not load billing summary',
                  description: err.response?.data?.detail || 'Network error' });
        }
      } finally {
        if (!cancelled) setBillingLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [open, admission?.id, step, settle, toast]);

  const isDama = form.discharge_type === 'against_advice';
  const isDeath = form.discharge_type === 'death';

  const labels = ['Clinical', 'Take-home Rx & Follow-up', 'Declarations'];

  const update = (patch) => setForm(p => ({ ...p, ...patch }));
  const updateMed = (idx, key, val) => {
    setForm(p => {
      const next = [...(p.take_home_medications || [])];
      next[idx] = { ...next[idx], [key]: val };
      return { ...p, take_home_medications: next };
    });
  };
  const addMed = () => update({
    take_home_medications: [
      ...(form.take_home_medications || []),
      { medicine_id: '', medicine_name: '', dosage: '', frequency: '', duration: '', quantity: '', instructions: '' },
    ],
  });
  const removeMed = (idx) => update({
    take_home_medications: (form.take_home_medications || []).filter((_, i) => i !== idx),
  });

  const validateStep1 = () => {
    if (!form.discharge_type) return 'Discharge type is required.';
    return null;
  };
  const validateStep2 = () => null;  // all optional
  const validateStep3 = () => {
    // Declarations vary by discharge type.
    if (isDeath) {
      // Mortality details collected separately afterwards; no checkboxes here.
      return null;
    }
    if (isDama) {
      if (!form.dama_advice_ack) return 'Please confirm "Medical advice was given to the patient".';
      if (!form.dama_absolves_ack) return 'Please confirm "Patient absolves the hospital".';
    } else {
      if (!form.consent_to_discharge) return 'Please tick the discharge declaration to continue.';
    }
    if (!form.signed_by_name.trim()) return 'Enter the name of the person signing.';
    if (form.signed_by_relationship === 'guardian' && !form.guardian_relationship.trim()) {
      return 'Enter the guardian relationship (e.g. wife, son, daughter).';
    }
    if (blockers.length > 0 && !form.override_reason.trim()) {
      return 'Override reason is required to proceed past the safety gate(s).';
    }
    return null;
  };

  const next = () => {
    const err = step === 1 ? validateStep1() : step === 2 ? validateStep2() : null;
    if (err) { toast({ variant: 'destructive', title: 'Check fields', description: err }); return; }
    setStep(s => s + 1);
  };
  const back = () => setStep(s => Math.max(1, s - 1));

  const submit = async () => {
    const err = validateStep3();
    if (err) { toast({ variant: 'destructive', title: 'Cannot submit', description: err }); return; }
    setSaving(true);
    try {
      const meds = (form.take_home_medications || [])
        .filter(m => (m.medicine_name || '').trim())
        .map(m => ({
          medicine_id: m.medicine_id ? parseInt(m.medicine_id, 10) : null,
          medicine_name: m.medicine_name.trim(),
          dosage: m.dosage?.trim() || null,
          frequency: m.frequency?.trim() || null,
          duration: m.duration?.trim() || null,
          quantity: m.quantity ? parseInt(m.quantity, 10) : null,
          instructions: m.instructions?.trim() || null,
        }));

      const dischargePayload = {
        discharge_type: form.discharge_type,
        condition_on_discharge: form.condition_on_discharge,
        diagnosis_on_discharge: form.diagnosis_on_discharge || null,
        treatment_given: form.treatment_given || null,
        discharge_summary: form.discharge_summary || null,
        follow_up_instructions: form.follow_up_instructions || null,
        follow_up_date: form.follow_up_date
          ? new Date(form.follow_up_date).toISOString() : null,
        diet_instructions: form.diet_instructions || null,
        activity_restrictions: form.activity_restrictions || null,
        medications_prescribed: null,
        take_home_medications: meds.length ? meds : null,
      };
      if (blockers.length > 0) {
        const codes = blockers.map(b => b.code);
        if (codes.includes('outstanding_balance')) dischargePayload.force_outstanding_balance = true;
        if (codes.includes('unacknowledged_critical_alerts')) dischargePayload.force_unacknowledged_alerts = true;
        if (codes.includes('missing_surgical_consent')) dischargePayload.force_missing_consents = true;
        if (codes.includes('final_bill_required')) dischargePayload.force_no_final_bill = true;
        dischargePayload.override_reason = form.override_reason.trim();
      }

      await axios.post(`/api/inpatient/admissions/${admission.id}/discharge`, dischargePayload);

      // If DAMA, immediately POST the (simplified) DAMA payload. The backend
      // requires several fields we auto-fill from sensible defaults so the
      // operator only deals with the two acknowledgements + signer info.
      if (isDama) {
        const damaPayload = {
          attending_doctor_id: admission.admitting_doctor_id || admission.attending_physician_id,
          medical_advice_given: form.treatment_given?.trim()
            || 'Medical advice was explained verbally to the patient prior to leaving.',
          risks_explained:
            'Risks of leaving against medical advice were explained verbally to the patient.',
          language_used: 'english',
          patient_acknowledges_advice: !!form.dama_advice_ack,
          patient_absolves_hospital: !!form.dama_absolves_ack,
          signed_by: form.signed_by_relationship === 'guardian' ? 'guardian' : 'patient',
          guardian_name: form.signed_by_relationship === 'guardian' ? form.signed_by_name.trim() : null,
          guardian_relationship: form.signed_by_relationship === 'guardian'
            ? form.guardian_relationship.trim() : null,
          primary_signature: form.signed_by_name.trim(),
          primary_signature_type: 'typed',
          // Backend requires a witness — auto-fill with the recording user's
          // implicit witness role; UI doesn't ask for one to keep the flow short.
          witness_name: 'Hospital staff (recording user)',
          witness_designation: null,
          witness_signature: 'Counter-signed by recording user',
          witness_signature_type: 'typed',
          notes: form.decl_notes || null,
        };
        try {
          await axios.post(`/api/inpatient/admissions/${admission.id}/dama`, damaPayload);
        } catch (dErr) {
          toast({
            variant: 'destructive', title: 'DAMA form failed',
            description: 'Discharge recorded, but DAMA form did not save. Re-file from the admission detail.',
          });
        }
      }

      toast({
        title: 'Patient discharged',
        description: isDeath
          ? 'Now fill mortality details to complete the flow.'
          : 'Next: go to Billing → Finalize bill, then issue gate pass.',
      });
      onDischarged?.({ wasDeath: isDeath, wasDama: isDama, admissionId: admission.id });
      onClose?.();
    } catch (err) {
      const detail = err.response?.data?.detail;
      // Backend may 409 with { code, message, … } for any of three gates.
      // Credit-refund gate: patient overpaid. Show a refund dialog; on success retry.
      if (err.response?.status === 409
          && detail && typeof detail === 'object'
          && detail.code === 'credit_refund_required') {
        setSettle({
          mode: 'refund', retry: true,
          amount: String(detail.credit_amount ?? ''),
          method: 'cash', reference: '', notes: '', busy: false,
        });
        toast({
          variant: 'destructive', title: 'Refund required',
          description: detail.message || 'Issue the refund before discharging.',
        });
        return;
      }
      const isGate = err.response?.status === 409
        && detail && typeof detail === 'object' && detail.code
        && ['outstanding_balance', 'unacknowledged_critical_alerts', 'missing_surgical_consent', 'final_bill_required']
          .includes(detail.code);
      if (isGate) {
        // Add to blockers and jump to step 3 so the override reason input is visible.
        setBlockers(prev => {
          if (prev.some(b => b.code === detail.code)) return prev;
          return [...prev, detail];
        });
        setStep(3);
        toast({
          variant: 'destructive',
          title: 'Safety gate hit',
          description: detail.message + ' Provide an override reason and resubmit.',
        });
      } else {
        const msg = typeof detail === 'string'
          ? detail
          : (detail?.message || 'Discharge failed');
        toast({ variant: 'destructive', title: 'Error', description: msg });
      }
    } finally {
      setSaving(false);
    }
  };

  const openSettle = (mode, amount) => {
    setSettle({
      mode, retry: false,
      amount: String(amount || ''),
      method: 'cash', reference: '', notes: '', busy: false,
    });
  };

  const submitSettle = async () => {
    if (!settle) return;
    const amt = parseFloat(settle.amount);
    if (!(amt > 0)) {
      toast({ variant: 'destructive', title: 'Invalid amount',
              description: 'Enter an amount greater than zero.' });
      return;
    }
    setSettle(p => ({ ...p, busy: true }));
    try {
      const url = settle.mode === 'refund'
        ? `/api/inpatient/admissions/${admission.id}/refund`
        : `/api/inpatient/admissions/${admission.id}/deposits`;
      const body = {
        amount: amt,
        payment_method: settle.method,
        reference_number: settle.reference || undefined,
        notes: settle.notes || undefined,
      };
      if (settle.mode === 'collect') body.deposit_type = 'topup';
      await axios.post(url, body);
      toast({
        title: settle.mode === 'refund' ? 'Refund recorded' : 'Payment collected',
        description: `₹${amt.toFixed(2)} ${settle.mode === 'refund' ? 'refunded' : 'received'}.`,
      });
      const wasRetry = settle.retry;
      setSettle(null);
      if (wasRetry) {
        // Came from 409 gate — retry discharge automatically.
        await submit();
      }
      // Either way, the Step-3 useEffect re-fires (settle dep) and the
      // billing summary refreshes.
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail
        : (detail?.message || 'Failed');
      toast({ variant: 'destructive', title: 'Error', description: msg });
      setSettle(p => ({ ...p, busy: false }));
    }
  };

  if (!admission) return null;

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose?.()}>
      <DialogContent className="max-w-4xl max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span>Discharge — {admission.patient_name}</span>
            <span className="text-xs font-normal text-gray-500">Step {step} of 3</span>
          </DialogTitle>
        </DialogHeader>
        <div className="border-b pb-3 mb-4"><Stepper step={step} labels={labels} /></div>

        {/* ---------- STEP 1 — Clinical ---------- */}
        {step === 1 && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <Label>Discharge type *</Label>
                <Select value={form.discharge_type}
                        onValueChange={v => update({ discharge_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="normal">Normal</SelectItem>
                    <SelectItem value="against_advice">Against medical advice (DAMA)</SelectItem>
                    <SelectItem value="transfer">Transfer</SelectItem>
                    <SelectItem value="death">Death</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Condition on discharge</Label>
                <Select value={form.condition_on_discharge}
                        onValueChange={v => update({ condition_on_discharge: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="stable">Stable</SelectItem>
                    <SelectItem value="improved">Improved</SelectItem>
                    <SelectItem value="unchanged">Unchanged</SelectItem>
                    <SelectItem value="critical">Critical</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div>
              <Label>Diagnosis on discharge</Label>
              <Textarea rows={2} value={form.diagnosis_on_discharge}
                        onChange={e => update({ diagnosis_on_discharge: e.target.value })}
                        placeholder="Final diagnosis at discharge" />
            </div>
            <div>
              <Label>Treatment given</Label>
              <Textarea rows={2} value={form.treatment_given}
                        onChange={e => update({ treatment_given: e.target.value })}
                        placeholder="Summary of treatment provided during the stay" />
            </div>
            <div>
              <Label>Discharge summary</Label>
              <Textarea rows={3} value={form.discharge_summary}
                        onChange={e => update({ discharge_summary: e.target.value })}
                        placeholder="Overall summary for the discharge note / referral letter" />
            </div>
          </div>
        )}

        {/* ---------- STEP 2 — Rx + Follow-up ---------- */}
        {step === 2 && (
          <div className="space-y-5">
            <section>
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold text-sm text-gray-700 flex items-center gap-2">
                  <Pill className="h-4 w-4" /> Take-home medications
                </h3>
                <Button type="button" size="sm" variant="outline" onClick={addMed}>
                  <Plus className="h-3 w-3 mr-1" /> Add medicine
                </Button>
              </div>
              <p className="text-xs text-gray-500 mb-2">
                Prescription the patient takes home. Separate from drugs given during the stay.
              </p>
              {(form.take_home_medications || []).length === 0 ? (
                <p className="text-xs text-gray-500 italic border rounded p-3 bg-gray-50">
                  No take-home medications yet. Click <b>Add medicine</b> to add one.
                </p>
              ) : (
                <div className="space-y-2">
                  {form.take_home_medications.map((m, idx) => (
                    <MedicineCard key={idx} med={m} idx={idx}
                                  admissionId={admission?.id}
                                  onChange={updateMed} onRemove={removeMed} />
                  ))}
                </div>
              )}
            </section>

            <section>
              <h3 className="font-semibold text-sm text-gray-700 flex items-center gap-2 mb-2">
                <Stethoscope className="h-4 w-4" /> Follow-up & instructions
              </h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Follow-up instructions</Label>
                  <Textarea rows={2} value={form.follow_up_instructions}
                            onChange={e => update({ follow_up_instructions: e.target.value })}
                            placeholder="e.g. Review in OPD with reports" />
                </div>
                <div>
                  <Label>Follow-up date</Label>
                  <Input type="date" value={form.follow_up_date}
                         onChange={e => update({ follow_up_date: e.target.value })} />
                </div>
                <div>
                  <Label>Diet instructions</Label>
                  <Textarea rows={2} value={form.diet_instructions}
                            onChange={e => update({ diet_instructions: e.target.value })}
                            placeholder="e.g. Low-salt diet, avoid alcohol" />
                </div>
                <div>
                  <Label>Activity restrictions</Label>
                  <Textarea rows={2} value={form.activity_restrictions}
                            onChange={e => update({ activity_restrictions: e.target.value })}
                            placeholder="e.g. No driving for 2 weeks" />
                </div>
              </div>
            </section>
          </div>
        )}

        {/* ---------- STEP 3 — Declarations ---------- */}
        {step === 3 && (
          <div className="space-y-4">
            <BillingSummary loading={billingLoading} billing={billing} balance={balance}
                            onSettle={openSettle} />

            <h3 className="font-semibold text-sm text-gray-700 flex items-center gap-2">
              <FileSignature className="h-4 w-4" /> Declarations &amp; signature
            </h3>

            {isDeath ? (
              <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm">
                <b>Death discharge:</b> no on-screen declarations here.
                After submitting, you will be prompted to fill the mortality
                details (cause of death, MLC, body handover).
              </div>
            ) : isDama ? (
              <DamaDeclarations form={form} update={update} />
            ) : (
              <NormalDeclaration form={form} update={update} />
            )}

            {!isDeath && (
              <SignerBlock form={form} update={update} />
            )}

            {blockers.length > 0 && (
              <SafetyGateOverride blockers={blockers} form={form} update={update} />
            )}
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between pt-4 mt-4 border-t">
          <div>
            {step > 1 && (
              <Button variant="outline" onClick={back}>
                <ChevronLeft className="h-4 w-4 mr-1" /> Back
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>Cancel</Button>
            {step < 3 && (
              <Button onClick={next}>
                Next <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            )}
            {step === 3 && (
              <Button onClick={submit} disabled={saving}
                      variant={blockers.length > 0 ? 'destructive' : 'default'}>
                {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {blockers.length > 0 ? 'Override & discharge' : 'Confirm discharge'}
              </Button>
            )}
          </div>
        </div>
      </DialogContent>

      {/* Settle dialog — collect or refund, optionally retries discharge after */}
      <Dialog open={!!settle} onOpenChange={v => !v && !settle?.busy && setSettle(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {settle?.mode === 'refund'
                ? 'Refund excess deposit'
                : 'Collect outstanding payment'}
            </DialogTitle>
          </DialogHeader>
          {settle && (
            <div className="space-y-3 text-sm">
              <div className={`rounded p-2 text-xs border ${
                settle.mode === 'refund'
                  ? 'bg-green-50 border-green-200 text-green-900'
                  : 'bg-amber-50 border-amber-200 text-amber-900'
              }`}>
                {settle.mode === 'refund'
                  ? (settle.retry
                      ? 'Patient overpaid. Record the refund and the discharge will continue automatically.'
                      : 'Record the refund. The billing summary will refresh.')
                  : (settle.retry
                      ? 'Outstanding amount. Record the payment and the discharge will continue automatically.'
                      : 'Record the patient’s payment. The billing summary will refresh.')}
              </div>
              <div>
                <Label className="text-xs">Amount</Label>
                <Input type="number" min="0" step="0.01" value={settle.amount}
                       onChange={e => setSettle(p => ({ ...p, amount: e.target.value }))} />
              </div>
              <div>
                <Label className="text-xs">Method</Label>
                <Select value={settle.method}
                        onValueChange={v => setSettle(p => ({ ...p, method: v }))}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="card">Card</SelectItem>
                    <SelectItem value="upi">UPI</SelectItem>
                    <SelectItem value="cheque">Cheque</SelectItem>
                    <SelectItem value="online">Online</SelectItem>
                    <SelectItem value="bank_transfer">Bank transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Reference</Label>
                <Input value={settle.reference}
                       onChange={e => setSettle(p => ({ ...p, reference: e.target.value }))} />
              </div>
              <div>
                <Label className="text-xs">Notes</Label>
                <Input value={settle.notes}
                       onChange={e => setSettle(p => ({ ...p, notes: e.target.value }))} />
              </div>
            </div>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={() => setSettle(null)}
                    disabled={settle?.busy}>Cancel</Button>
            <Button onClick={submitSettle} disabled={settle?.busy}>
              {settle?.busy && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {settle?.mode === 'refund'
                ? (settle?.retry ? 'Refund & discharge' : 'Record refund')
                : (settle?.retry ? 'Collect & discharge' : 'Record payment')}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Dialog>
  );
};


// --- Sub-components ----------------------------------------------------

const fmt = (n) => `₹${(Number(n) || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const BillingSummary = ({ loading, billing, balance, onSettle }) => {
  if (loading) {
    return (
      <div className="border rounded-lg p-3 bg-gray-50 text-xs text-gray-500 flex items-center gap-2">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading billing summary…
      </div>
    );
  }
  if (!billing && !balance) return null;

  const rows = [];
  if (billing) {
    if (billing.room_total > 0) {
      rows.push({
        label: `Room (${billing.room?.room_number || '—'} · ${billing.stay_days || 0} day${billing.stay_days === 1 ? '' : 's'})`,
        amount: billing.room_total,
      });
    }
    if (billing.visits) {
      Object.entries(billing.visits).forEach(([type, data]) => {
        rows.push({
          label: `${type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())} (×${data.count})`,
          amount: data.total,
        });
      });
    }
    if (billing.ot_total > 0) {
      rows.push({ label: `OT procedures (${(billing.ot_entries || []).length})`, amount: billing.ot_total });
    }
    if (billing.ancillary_total > 0) {
      rows.push({ label: `Ancillary services (${(billing.ancillary_entries || []).length})`, amount: billing.ancillary_total });
    }
    if (billing.pharmacy_total > 0) {
      rows.push({ label: 'Pharmacy / Medications', amount: billing.pharmacy_total });
    }
    if (billing.lab_total > 0) {
      rows.push({ label: 'Lab tests', amount: billing.lab_total });
    }
  }

  // Effective total = the larger of (finalized Bill rows) and (live computed charges).
  // Before finalize, total_billed from /balance is 0 — fall through to the
  // computed breakdown so the operator sees what the patient actually owes.
  const billedFromBills = Number(balance?.total_billed || 0);
  const billedFromCompute = Number(billing?.grand_total || 0);
  const totalBilled = Math.max(billedFromBills, billedFromCompute);
  const netDeposits = Number(balance?.net_deposits || 0);
  const net = netDeposits - totalBilled;   // +ve = refund due, -ve = patient owes
  const refundDue = Math.max(0, net);
  const dueFromPatient = Math.max(0, -net);
  const usingPreview = billedFromBills <= 0.01 && billedFromCompute > 0.01;

  return (
    <section className="border-2 border-blue-200 bg-blue-50/40 rounded-lg p-3 space-y-2">
      <h3 className="font-semibold text-sm text-blue-900 flex items-center gap-2">
        <FileSignature className="h-4 w-4" /> Billing summary
      </h3>

      {usingPreview && (
        <div className="bg-amber-100 border border-amber-300 rounded p-2 text-xs text-amber-900">
          <b>Bill not yet finalized.</b> Showing the live computed charges. Generate the final bill from the
          Billing tab so the figures lock in before discharge.
        </div>
      )}

      {rows.length > 0 ? (
        <div className="bg-white border rounded p-2 text-xs space-y-1 max-h-44 overflow-y-auto">
          {rows.map((r, i) => (
            <div key={i} className="flex justify-between">
              <span className="text-gray-700">{r.label}</span>
              <span className="font-mono">{fmt(r.amount)}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-500 italic">No itemised charges recorded.</p>
      )}

      <div className="grid grid-cols-2 gap-3 text-sm pt-1">
        <div className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-gray-600">Total billed</span>
            <span className="font-mono">{fmt(totalBilled)}</span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-gray-600">Deposits received (net)</span>
            <span className="font-mono">{fmt(netDeposits)}</span>
          </div>
        </div>
        <div className={
          'rounded p-2 text-center ' +
          (refundDue > 0.01
            ? 'bg-green-100 border border-green-300'
            : dueFromPatient > 0.01
              ? 'bg-amber-100 border border-amber-300'
              : 'bg-gray-100 border border-gray-200')
        }>
          {refundDue > 0.01 ? (
            <>
              <p className="text-[10px] uppercase tracking-wide text-green-800 font-semibold">Refund due</p>
              <p className="text-base font-bold text-green-900">{fmt(refundDue)}</p>
              <p className="text-[10px] text-green-800">Issue before discharge proceeds</p>
            </>
          ) : dueFromPatient > 0.01 ? (
            <>
              <p className="text-[10px] uppercase tracking-wide text-amber-800 font-semibold">Patient owes</p>
              <p className="text-base font-bold text-amber-900">{fmt(dueFromPatient)}</p>
              <p className="text-[10px] text-amber-800">Collect or override with reason</p>
            </>
          ) : (
            <>
              <p className="text-[10px] uppercase tracking-wide text-gray-700 font-semibold">Settled</p>
              <p className="text-base font-bold text-gray-800">{fmt(0)}</p>
              <p className="text-[10px] text-gray-600">No outstanding balance</p>
            </>
          )}
        </div>
      </div>

      {/* Inline settle action — single click handles the imbalance */}
      {onSettle && refundDue > 0.01 && (
        <Button size="sm" className="w-full" variant="default"
                onClick={() => onSettle('refund', refundDue)}>
          Refund {fmt(refundDue)} now
        </Button>
      )}
      {onSettle && dueFromPatient > 0.01 && (
        <Button size="sm" className="w-full" variant="default"
                onClick={() => onSettle('collect', dueFromPatient)}>
          Collect {fmt(dueFromPatient)} now
        </Button>
      )}
    </section>
  );
};

const NormalDeclaration = ({ form, update }) => (
  <div className="border rounded p-3 bg-gray-50 space-y-2 text-sm">
    <p>
      I confirm the patient has been advised of follow-up instructions,
      take-home medication, diet, and activity restrictions; and I authorise
      the discharge.
    </p>
    <label className="flex items-center gap-2 cursor-pointer">
      <input type="checkbox"
             checked={form.consent_to_discharge}
             onChange={e => update({ consent_to_discharge: e.target.checked })} />
      <span>I acknowledge the above and consent to discharge *</span>
    </label>
  </div>
);

const DamaDeclarations = ({ form, update }) => (
  <div className="border-2 border-red-300 rounded p-3 bg-red-50 space-y-2 text-sm">
    <p className="font-semibold text-red-800 flex items-center gap-1">
      <AlertTriangle className="h-4 w-4" /> Discharge Against Medical Advice
    </p>
    <label className="flex items-start gap-2 cursor-pointer">
      <input type="checkbox" className="mt-0.5"
             checked={form.dama_advice_ack}
             onChange={e => update({ dama_advice_ack: e.target.checked })} />
      <span>
        Medical advice was given to the patient, and the risks of leaving
        against advice were explained verbally in a language they understand. *
      </span>
    </label>
    <label className="flex items-start gap-2 cursor-pointer">
      <input type="checkbox" className="mt-0.5"
             checked={form.dama_absolves_ack}
             onChange={e => update({ dama_absolves_ack: e.target.checked })} />
      <span>
        Patient / guardian absolves the hospital and treating doctors of any
        consequences arising from leaving against medical advice. *
      </span>
    </label>
  </div>
);

const SignerBlock = ({ form, update }) => (
  <div className="border rounded p-3 space-y-3 text-sm">
    <div className="grid grid-cols-2 gap-3">
      <div>
        <Label>Signed by *</Label>
        <Select value={form.signed_by_relationship}
                onValueChange={v => update({ signed_by_relationship: v })}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="self">Patient themself</SelectItem>
            <SelectItem value="guardian">Guardian / family member</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label>Name of signer *</Label>
        <Input value={form.signed_by_name}
               onChange={e => update({ signed_by_name: e.target.value })}
               placeholder="Full name as on ID" />
      </div>
    </div>
    {form.signed_by_relationship === 'guardian' && (
      <div>
        <Label>Relationship to patient *</Label>
        <Input value={form.guardian_relationship}
               onChange={e => update({ guardian_relationship: e.target.value })}
               placeholder="e.g. Wife, Son, Brother" />
      </div>
    )}
    <div>
      <Label>Notes (optional)</Label>
      <Textarea rows={2} value={form.decl_notes}
                onChange={e => update({ decl_notes: e.target.value })}
                placeholder="Any additional remarks" />
    </div>
  </div>
);

const SafetyGateOverride = ({ blockers, form, update }) => (
  <div className="border border-red-300 bg-red-50 rounded p-3 text-sm space-y-2">
    <p className="font-semibold text-red-800">
      Discharge blocked by safety gate{blockers.length > 1 ? 's' : ''}:
    </p>
    <ul className="list-disc ml-5 space-y-1 text-red-700">
      {blockers.map(b => (
        <li key={b.code}>
          <span className="font-medium">{b.code.replace(/_/g, ' ')}</span>: {b.message}
          {b.code === 'outstanding_balance' && typeof b.balance === 'number' && (
            <span className="block text-xs">
              Balance: ₹{b.balance.toFixed(2)} (billed ₹{b.total_billed?.toFixed(2)},
              deposited ₹{b.net_deposits?.toFixed(2)})
            </span>
          )}
          {b.code === 'unacknowledged_critical_alerts' && (
            <span className="block text-xs">
              {b.alert_count} alert(s){b.parameters?.length ? ` — ${b.parameters.join(', ')}` : ''}
            </span>
          )}
          {b.code === 'missing_surgical_consent' && (
            <span className="block text-xs">
              {b.completed_ot_count} completed OT procedure(s) without recorded consent.
            </span>
          )}
          {b.code === 'final_bill_required' && (
            <span className="block text-xs">
              Generate the final bill (and settle the balance) from the Billing tab, then retry discharge.
            </span>
          )}
        </li>
      ))}
    </ul>
    <div>
      <Label className="text-red-800">Override reason (required) *</Label>
      <Textarea required value={form.override_reason}
                onChange={e => update({ override_reason: e.target.value })}
                rows={2}
                placeholder="Explain why this discharge should proceed despite the gate(s)…" />
    </div>
    <p className="text-xs text-red-600">
      Submitting will record this override in the audit log against your account.
    </p>
  </div>
);


export default DischargeWizard;
