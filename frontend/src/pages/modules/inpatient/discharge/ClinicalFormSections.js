import React from 'react';
import FormNavContainer from '../../../../components/FormNavContainer';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Textarea } from '../../../../components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../../../components/ui/select';
import { AlertTriangle, FileSignature, Loader2, Stethoscope } from 'lucide-react';
import TakeHomeMedicinesSection from '../../../../components/prescription/TakeHomeMedicinesSection';
import { fmtInr } from './constants';

export const BillingRecap = ({ bill, balance, loading }) => {
  if (loading) {
    return (
      <div className="border rounded-lg p-3 bg-gray-50 text-xs text-gray-500 flex items-center gap-2">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading billing summary…
      </div>
    );
  }
  if (!bill && !balance) return null;

  const billedFromBills = Number(balance?.total_billed || 0);
  const billedFromCompute = Number(bill?.grand_total || 0);
  const totalBilled = Math.max(billedFromBills, billedFromCompute);
  const netDeposits = Number(balance?.net_deposits || 0);
  const net = netDeposits - totalBilled;
  const refundDue = Math.max(0, net);
  const dueFromPatient = Math.max(0, -net);

  return (
    <section className="border border-blue-200 bg-blue-50/40 rounded-lg p-3 space-y-2">
      <h3 className="font-semibold text-sm text-blue-900 flex items-center gap-2">
        <FileSignature className="h-4 w-4" /> Billing recap
      </h3>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="bg-white border rounded p-2">
          <div className="text-gray-500">Total billed</div>
          <div className="font-semibold">{fmtInr(totalBilled)}</div>
        </div>
        <div className="bg-white border rounded p-2">
          <div className="text-gray-500">Deposits</div>
          <div className="font-semibold">{fmtInr(netDeposits)}</div>
        </div>
        <div className={`border rounded p-2 ${
          refundDue > 0.01 ? 'bg-green-50 border-green-200'
            : dueFromPatient > 0.01 ? 'bg-amber-50 border-amber-200'
              : 'bg-gray-50'
        }`}>
          <div className="text-gray-500">Balance</div>
          <div className="font-semibold">
            {refundDue > 0.01 ? `Credit ${fmtInr(refundDue)}`
              : dueFromPatient > 0.01 ? `Owes ${fmtInr(dueFromPatient)}`
                : fmtInr(0)}
          </div>
        </div>
      </div>
    </section>
  );
};

export const NormalDeclaration = ({ form, update }) => (
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

export const DamaDeclarations = ({ form, update }) => (
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

export const SignerBlock = ({ form, update }) => (
  <FormNavContainer mode="grid" className="border rounded p-3 space-y-3 text-sm">
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
  </FormNavContainer>
);

export const SafetyGateOverride = ({ blockers, form, update }) => (
  <div className="border border-red-300 bg-red-50 rounded p-3 text-sm space-y-2">
    <p className="font-semibold text-red-800">
      Discharge blocked by safety gate{blockers.length > 1 ? 's' : ''}:
    </p>
    <ul className="list-disc ml-5 space-y-1 text-red-700">
      {blockers.map(b => (
        <li key={b.code}>
          <span className="font-medium">{b.code.replace(/_/g, ' ')}</span>: {b.message}
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
  </div>
);

export const ClinicalFields = ({ form, update }) => (
  <FormNavContainer mode="grid" className="space-y-4">
    <div className="grid grid-cols-2 gap-4">
      <div>
        <Label>Discharge type *</Label>
        <Select value={form.discharge_type} onValueChange={v => update({ discharge_type: v })}>
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
  </FormNavContainer>
);

export const TakeHomeFields = ({ form, update, admissionId }) => (
  <div className="space-y-5">
    <TakeHomeMedicinesSection
      medications={form.take_home_medications || []}
      onMedicationsChange={(meds) => update({ take_home_medications: meds })}
      admissionId={admissionId}
      description="Prescription the patient takes home. Separate from drugs given during the stay."
    />
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
                    onChange={e => update({ diet_instructions: e.target.value })} />
        </div>
        <div>
          <Label>Activity restrictions</Label>
          <Textarea rows={2} value={form.activity_restrictions}
                    onChange={e => update({ activity_restrictions: e.target.value })} />
        </div>
      </div>
    </section>
  </div>
);
