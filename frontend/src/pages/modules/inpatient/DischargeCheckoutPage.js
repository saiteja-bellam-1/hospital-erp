import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import { Textarea } from '../../../components/ui/textarea';
import FormNavContainer from '../../../components/FormNavContainer';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from '../../../components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../../components/ui/select';
import {
  ArrowLeft, Loader2, Wallet, Banknote, FileBadge, CheckCircle2,
  AlertTriangle, IndianRupee, Plus, ChevronLeft, ChevronRight,
} from 'lucide-react';
import DischargeWorklist from './discharge/DischargeWorklist';
import DischargeStepper from './discharge/DischargeStepper';
import DischargeSummaryReview from './discharge/DischargeSummaryReview';
import DischargeSummaryEditor from './DischargeSummaryEditor';
import DischargePrintBar from './discharge/DischargePrintBar';
import useDischargeCheckout from './discharge/useDischargeCheckout';
import { PAYMENT_METHODS, rupee } from './discharge/constants';
import { SafetyGateOverride } from './discharge/ClinicalFormSections';

const Stat = ({ label, value, tone }) => (
  <div>
    <div className="text-[11px] text-gray-500 uppercase tracking-wide">{label}</div>
    <div className={
      'text-sm font-semibold ' +
      (tone === 'red' ? 'text-red-600' : tone === 'blue' ? 'text-blue-600'
        : tone === 'green' ? 'text-green-600' : 'text-gray-900')
    }>{value}</div>
  </div>
);

const CheckoutFlow = ({ admissionId, onBack, permissions, onDeathDischarge, doctorsList = [] }) => {
  const [summaryEditorOpen, setSummaryEditorOpen] = useState(false);
  const checkout = useDischargeCheckout(admissionId, permissions);
  const {
    loading, submitting, admission, bill, derived, settlement, deposits, finalBill, gatePass,
    step, maxReachable, clinicalForm, settleForm, setSettleForm, gatePassForm, setGatePassForm,
    blockers, depositForm, setDepositForm,
    canAddDeposit, canFinalize, canDischarge, canIssuePass, canWriteSummary, canViewSummary,
    summaryDoc, refreshSummary,
    updateClinical,
    goToStep, handleNext, handleBack, printBill, printGatePass, printDischargeSummary, printAdmissionDetail, submitDeposit,
  } = checkout;

  if (loading) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-gray-500">
          <Loader2 className="h-6 w-6 mx-auto animate-spin" />
          <p className="text-sm mt-2">Loading checkout…</p>
        </CardContent>
      </Card>
    );
  }

  if (!admission || !derived) {
    return (
      <Card>
        <CardContent className="py-12 text-center text-gray-500">
          Admission not found.
          {onBack && (
            <div className="mt-3">
              <Button variant="outline" onClick={onBack}>
                <ArrowLeft className="h-4 w-4 mr-1" /> Back
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    );
  }

  const isDeath = (clinicalForm.discharge_type || summaryDoc?.discharge_type) === 'death';
  const isComplete = !!gatePass;
  const readOnlyBill = !!finalBill && step > 1;
  const summaryReady = summaryDoc?.status === 'ready' || summaryDoc?.status === 'locked';
  const checkoutOwes = settlement?.owes ?? derived.owes;

  const printBar = (
    <DischargePrintBar
      canPrintFinalBill={!!finalBill}
      canPrintDischargeSummary={summaryReady}
      canPrintGatePass={!!gatePass}
      onPrintFinalBill={printBill}
      onPrintDischargeSummary={printDischargeSummary}
      onPrintGatePass={printGatePass}
      onPrintDetailedSummary={printAdmissionDetail}
    />
  );

  const onPrimaryAction = async () => {
    if (isComplete) {
      onBack?.();
      return;
    }
    const result = await handleNext();
    if (result?.wasDeath) onDeathDischarge?.(result);
  };

  const primaryLabel = () => {
    if (isComplete) return 'Back to worklist';
    if (step === 1) {
      return finalBill ? 'Continue to Settlement' : 'Generate Final Bill';
    }
    if (step === 2) {
      if (settlement?.direction === 'collect') {
        return `Collect ${rupee(settlement.amount)} & Continue`;
      }
      if (settlement?.direction === 'refund') {
        return `Refund ${rupee(settlement.amount)} & Continue`;
      }
      return 'Continue to Summary';
    }
    if (step === 3) {
      if (derived.isDischarged) return 'Continue to Gate Pass';
      return blockers.length > 0 ? 'Override & Discharge' : 'Discharge & Continue';
    }
    if (step === 4) return gatePass ? 'Reprint Documents' : 'Issue Gate Pass & Print';
    return 'Next';
  };

  const showBack = step > 1 && !isComplete;

  return (
    <FormNavContainer mode="grid" className="space-y-4 pb-20">
      {/* Sticky header */}
      <div className="sticky top-0 z-10 bg-white border-b pb-3 -mx-1 px-1">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2">
            {onBack && (
              <Button variant="ghost" size="sm" className="mt-0.5" onClick={onBack}>
                <ArrowLeft className="h-4 w-4 mr-1" /> List
              </Button>
            )}
            <div>
              <h2 className="text-lg font-semibold">{admission.patient_name}</h2>
              <div className="text-xs text-gray-500">
                {admission.admission_number}
                {admission.room_number && (
                  <> · Rm {admission.room_number}{admission.bed_label ? `/${admission.bed_label}` : ''}</>
                )}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 justify-end">
            <Badge className={derived.isDischarged ? 'bg-gray-200 text-gray-800' : 'bg-emerald-100 text-emerald-800'}>
              {derived.isDischarged ? 'Discharged' : 'Admitted'}
            </Badge>
            {checkoutOwes > 0.01
              ? <Badge className="bg-red-100 text-red-800">Owes {rupee(checkoutOwes)}</Badge>
              : checkoutOwes < -0.01
                ? <Badge className="bg-blue-100 text-blue-800">Credit {rupee(Math.abs(checkoutOwes))}</Badge>
                : <Badge className="bg-green-100 text-green-800">Settled</Badge>}
            {finalBill && <Badge className="bg-blue-100 text-blue-800 text-xs">{finalBill.bill_number}</Badge>}
            {gatePass && <Badge className="bg-purple-100 text-purple-800">{gatePass.pass_number}</Badge>}
          </div>
        </div>
        <div className="mt-2 pt-2 border-t">
          {printBar}
        </div>
        <div className="mt-3">
          <DischargeStepper
            step={step}
            maxReachable={maxReachable}
            onStepClick={goToStep}
            isDischarged={derived.isDischarged}
            hasGatePass={!!gatePass}
          />
        </div>
      </div>

      {/* Step 1 — Finalize bill (discount / tax) */}
      {step === 1 && (
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-2 flex flex-row items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <IndianRupee className="h-4 w-4" /> Finalize Bill
              </CardTitle>
              <div className="flex gap-1">
                {canAddDeposit && !derived.isDischarged && (
                  <Button size="sm" variant="outline" onClick={() => setDepositForm({
                    amount: '', method: 'cash', ref: '', notes: '',
                  })}>
                    <Plus className="h-3.5 w-3.5 mr-1" /> Add Deposit
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {finalBill && (
                <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded p-2">
                  Final bill <b>{finalBill.bill_number}</b> already exists — continue to settlement.
                </div>
              )}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
                <Stat label="Stay charges" value={rupee(derived.stayCharges)} />
                <Stat label="Deposits" value={rupee(derived.deposited)} />
                <Stat label="Balance preview" value={rupee(Math.abs(checkoutOwes))}
                      tone={checkoutOwes > 0.01 ? 'red' : checkoutOwes < -0.01 ? 'blue' : 'green'} />
                {bill?.stay_days != null && <Stat label="Stay days" value={String(bill.stay_days)} />}
                {bill?.room_total != null && <Stat label="Room" value={rupee(bill.room_total)} />}
                {bill?.visit_total != null && <Stat label="Visits" value={rupee(bill.visit_total)} />}
                {finalBill && Number(finalBill.discount_amount || 0) > 0 && (
                  <Stat label="Discount applied" value={`-${rupee(finalBill.discount_amount)}`} tone="green" />
                )}
                {finalBill && <Stat label="Final bill total" value={rupee(finalBill.total_amount)} tone="blue" />}
              </div>

              {!readOnlyBill && settleForm && canFinalize && !finalBill && (
                <>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <Label className="text-xs">Discount type</Label>
                      <Select value={settleForm.discountType}
                              onValueChange={v => setSettleForm(p => ({ ...p, discountType: v }))}>
                        <SelectTrigger><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="flat">Flat (₹)</SelectItem>
                          <SelectItem value="percentage">Percentage (%)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="text-xs">Discount</Label>
                      <Input type="number" min="0" value={settleForm.discountValue}
                             onChange={e => setSettleForm(p => ({ ...p, discountValue: e.target.value }))} />
                    </div>
                    <div>
                      <Label className="text-xs">Tax %</Label>
                      <Input type="number" min="0" value={settleForm.taxPct}
                             onChange={e => setSettleForm(p => ({ ...p, taxPct: e.target.value }))} />
                    </div>
                  </div>
                  <div className="bg-gray-50 border rounded p-3 space-y-2 text-sm">
                    {(settlement?.discountAmount > 0 || settlement?.taxAmount > 0) && (
                      <div className="text-xs space-y-1">
                        {settlement.discountAmount > 0 && (
                          <div className="flex justify-between text-green-700">
                            <span>Discount</span><span>-{rupee(settlement.discountAmount)}</span>
                          </div>
                        )}
                        {settlement.taxAmount > 0 && (
                          <div className="flex justify-between text-orange-700">
                            <span>Tax</span><span>+{rupee(settlement.taxAmount)}</span>
                          </div>
                        )}
                      </div>
                    )}
                    <div className="flex justify-between font-medium">
                      <span>Adjusted final total</span><span>{rupee(settlement?.adjustedTotal || derived.stayCharges)}</span>
                    </div>
                    <p className="text-xs text-gray-500 pt-1 border-t">
                      Payment collection / refund happens in the next step.
                    </p>
                  </div>
                </>
              )}

              {deposits.length > 0 && (
                <div className="border rounded overflow-hidden">
                  <div className="bg-gray-50 px-3 py-1.5 text-xs font-medium">Deposits ({deposits.length})</div>
                  <div className="max-h-32 overflow-y-auto text-xs">
                    {deposits.map(d => (
                      <div key={d.id} className="flex justify-between px-3 py-1 border-t">
                        <span>{d.deposit_number} · {d.payment_method}</span>
                        <span className={d.deposit_type === 'refund' ? 'text-blue-700' : ''}>
                          {d.deposit_type === 'refund' ? '-' : ''}{rupee(d.amount)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Step 2 — Collect / Refund */}
      {step === 2 && (
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-2 flex flex-row items-center justify-between">
              <CardTitle className="text-base flex items-center gap-2">
                <Wallet className="h-4 w-4" /> Collect / Refund
              </CardTitle>
              {canAddDeposit && !derived.isDischarged && (
                <Button size="sm" variant="outline" onClick={() => setDepositForm({
                  amount: '', method: 'cash', ref: '', notes: '',
                })}>
                  <Plus className="h-3.5 w-3.5 mr-1" /> Add Deposit
                </Button>
              )}
            </CardHeader>
            <CardContent className="space-y-4">
              {!finalBill ? (
                <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded p-2">
                  Generate the final bill in the previous step before settling.
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
                    <Stat label="Final bill" value={rupee(finalBill.total_amount)} tone="blue" />
                    <Stat label="Deposits" value={rupee(derived.deposited)} />
                    <Stat label="Balance" value={rupee(Math.abs(checkoutOwes))}
                          tone={checkoutOwes > 0.01 ? 'red' : checkoutOwes < -0.01 ? 'blue' : 'green'} />
                  </div>
                  <div className="bg-gray-50 border rounded p-3 space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span>To {settlement?.direction === 'refund' ? 'refund' : settlement?.direction === 'collect' ? 'collect' : 'settle'}</span>
                      <b className={
                        settlement?.direction === 'collect' ? 'text-red-600'
                          : settlement?.direction === 'refund' ? 'text-blue-600' : 'text-green-600'
                      }>{rupee(settlement?.amount || 0)}</b>
                    </div>
                    {settlement?.direction !== 'none' && settleForm && (
                      <div className="grid grid-cols-2 gap-3 pt-2">
                        <div>
                          <Label className="text-xs">Amount (₹)</Label>
                          <Input type="number" min="0" step="0.01"
                                 value={(settlement?.amount || 0).toFixed(2)} readOnly />
                        </div>
                        <div>
                          <Label className="text-xs">Method</Label>
                          <Select value={settleForm.method}
                                  onValueChange={v => setSettleForm(p => ({ ...p, method: v }))}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              {PAYMENT_METHODS.map(m => (
                                <SelectItem key={m.value} value={m.value}>{m.label}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="col-span-2">
                          <Label className="text-xs">Reference</Label>
                          <Input value={settleForm.ref}
                                 onChange={e => setSettleForm(p => ({ ...p, ref: e.target.value }))}
                                 placeholder="Txn / cheque #" />
                        </div>
                      </div>
                    )}
                    {settlement?.direction === 'none' && (
                      <p className="text-xs text-green-700 flex items-center gap-1">
                        <CheckCircle2 className="h-3 w-3" /> Balance zero — continue to discharge summary.
                      </p>
                    )}
                  </div>
                </>
              )}
              {deposits.length > 0 && (
                <div className="border rounded overflow-hidden">
                  <div className="bg-gray-50 px-3 py-1.5 text-xs font-medium">Deposits ({deposits.length})</div>
                  <div className="max-h-32 overflow-y-auto text-xs">
                    {deposits.map(d => (
                      <div key={d.id} className="flex justify-between px-3 py-1 border-t">
                        <span>{d.deposit_number} · {d.payment_method}</span>
                        <span className={d.deposit_type === 'refund' ? 'text-blue-700' : ''}>
                          {d.deposit_type === 'refund' ? '-' : ''}{rupee(d.amount)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Step 3 — Discharge summary */}
      {step === 3 && (
        <div className="space-y-4">
          <DischargeSummaryReview
            summary={summaryDoc}
            canWrite={canWriteSummary && !derived.isDischarged}
            onEdit={() => setSummaryEditorOpen(true)}
            admissionId={admissionId}
          />
          {blockers.length > 0 && !derived.isDischarged && (
            <SafetyGateOverride blockers={blockers} form={clinicalForm} update={updateClinical} />
          )}
        </div>
      )}

      {/* Step 4 — Gate pass */}
      {step === 4 && (
        <div className="space-y-4">
          {isComplete ? (
            <Card>
              <CardContent className="py-8 text-center space-y-3">
                <CheckCircle2 className="h-12 w-12 text-green-600 mx-auto" />
                <h3 className="text-lg font-semibold">Discharge complete</h3>
                <p className="text-sm text-gray-500">
                  Gate pass {gatePass.pass_number} issued. Patient may exit.
                </p>
                <div className="flex justify-center pt-2">
                  {printBar}
                </div>
                {onBack && (
                  <div className="pt-2">
                    <Button onClick={onBack}>Back to worklist</Button>
                  </div>
                )}
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base flex items-center gap-2">
                  <FileBadge className="h-4 w-4" /> Gate Pass
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {derived.isDischarged && (
                  <p className="text-xs text-gray-600 bg-gray-50 border rounded p-2">
                    Patient discharged. Record exit details and print documents.
                  </p>
                )}
                {gatePassForm.overrideErr && (
                  <div className="border border-amber-300 bg-amber-50 rounded p-2 text-xs space-y-1">
                    <p className="font-semibold text-amber-900 flex items-center gap-1">
                      <AlertTriangle className="h-3 w-3" />
                      Outstanding: {rupee(gatePassForm.overrideErr.outstanding || 0)}
                    </p>
                    <Label className="text-xs">Override reason *</Label>
                    <Input value={gatePassForm.overrideReason}
                           onChange={e => setGatePassForm(p => ({ ...p, overrideReason: e.target.value }))}
                           placeholder="e.g. Insurance pending" />
                  </div>
                )}
                <div>
                  <Label>Attendant name *</Label>
                  <Input value={gatePassForm.attendant_name}
                         onChange={e => setGatePassForm(p => ({ ...p, attendant_name: e.target.value }))} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label>Relationship</Label>
                    <Input value={gatePassForm.attendant_relationship}
                           onChange={e => setGatePassForm(p => ({ ...p, attendant_relationship: e.target.value }))} />
                  </div>
                  <div>
                    <Label>Vehicle no.</Label>
                    <Input value={gatePassForm.vehicle_no}
                           onChange={e => setGatePassForm(p => ({ ...p, vehicle_no: e.target.value }))} />
                  </div>
                </div>
                <div>
                  <Label>Notes</Label>
                  <Textarea rows={2} value={gatePassForm.notes}
                            onChange={e => setGatePassForm(p => ({ ...p, notes: e.target.value }))} />
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {step === 4 && derived.isDischarged && !isComplete && (
        <Card>
          <CardContent className="py-3 text-xs text-gray-500">
            Discharged on {admission.discharge_date
              ? new Date(admission.discharge_date).toLocaleString() : 'discharge'}.
          </CardContent>
        </Card>
      )}

      {/* Sticky footer */}
      <div className="fixed bottom-0 left-0 right-0 md:left-auto md:right-auto md:relative md:mt-4
                      bg-white border-t md:border rounded-t-lg md:rounded-lg p-3 flex items-center justify-between gap-2 z-20">
        <div className="flex items-center gap-2">
          {!isComplete && showBack && (
            <Button variant="outline" onClick={handleBack} disabled={submitting}>
              <ChevronLeft className="h-4 w-4 mr-1" /> Back
            </Button>
          )}
          {isComplete && onBack && (
            <Button variant="outline" onClick={onBack}>
              <ArrowLeft className="h-4 w-4 mr-1" /> Worklist
            </Button>
          )}
        </div>
        <Button onClick={onPrimaryAction} disabled={submitting && !isComplete}
                variant={!isComplete && step === 3 && blockers.length > 0 ? 'destructive' : 'default'}>
          {submitting && !isComplete && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
          {primaryLabel()}
          {!isComplete && step < 4 && step !== 3 && <ChevronRight className="h-4 w-4 ml-1" />}
        </Button>
      </div>

      {/* Deposit dialog — only auxiliary modal kept */}
      <Dialog open={!!depositForm} onOpenChange={v => !v && setDepositForm(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Receive Deposit</DialogTitle>
            <DialogDescription>Top-up before or during settlement.</DialogDescription>
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
                         onChange={e => setDepositForm(p => ({ ...p, ref: e.target.value }))} />
                </div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDepositForm(null)}>Cancel</Button>
            <Button onClick={submitDeposit} disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              <Banknote className="h-4 w-4 mr-1" /> Record
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <DischargeSummaryEditor
        open={summaryEditorOpen}
        onClose={() => setSummaryEditorOpen(false)}
        admissionId={admissionId}
        admissionLabel={admission.patient_name}
        doctorsList={doctorsList}
        onSaved={() => refreshSummary()}
      />
    </FormNavContainer>
  );
};

/** Single-page discharge checkout: worklist + inline 4-step flow. */
const DischargeCheckoutPage = ({
  admissionId,
  onSelectAdmission,
  onBack,
  permissions = {},
  onDeathDischarge,
  doctorsList = [],
  worklistRefreshKey = 0,
}) => {
  if (!admissionId) {
    return (
      <div className="space-y-3">
        <div>
          <h2 className="text-lg font-semibold">Discharge &amp; Exit</h2>
          <p className="text-sm text-gray-500">
            One flow — finalize bill, settle, discharge summary, and gate pass.
          </p>
        </div>
        <DischargeWorklist onPick={onSelectAdmission} refreshKey={worklistRefreshKey} />
      </div>
    );
  }
  return (
    <CheckoutFlow
      admissionId={admissionId}
      onBack={onBack}
      permissions={permissions}
      onDeathDischarge={onDeathDischarge}
      doctorsList={doctorsList}
    />
  );
};

export default DischargeCheckoutPage;
