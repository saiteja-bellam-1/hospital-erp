import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Badge } from '../../../components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../../components/ui/select';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../../../components/ui/dialog';
import { useToast } from '../../../hooks/use-toast';
import TakeHomeMedicinesSection from '../../../components/prescription/TakeHomeMedicinesSection';
import { serializeTakeHomeMed } from '../../../utils/prescriptionSchedule';
import { printPdfFromUrl } from '../../../utils/printPdf';
import DischargeSummaryPdfPreviewDialog from './discharge/DischargeSummaryPdfPreviewDialog';
import { summaryIsReadyForPrint } from './discharge/dischargeSummaryUtils';
import {
  Loader2, FileText, CheckCircle2, ChevronLeft, ChevronRight, Printer, Eye, Pencil,
} from 'lucide-react';

const SUMMARY_STEPS = [
  { id: 1, label: 'Doctors & Type' },
  { id: 2, label: 'Complaints & History' },
  { id: 3, label: 'Course & Surgery' },
  { id: 4, label: 'Advice & Review' },
];

const TOTAL_STEPS = SUMMARY_STEPS.length;

const EMPTY_FORM = {
  chief_complaint: '',
  provisional_diagnosis: '',
  primary_diagnosis: '',
  past_history: '',
  family_history: '',
  present_medical_history: '',
  physical_examination_notes: '',
  include_admission_vitals: true,
  emergency_instructions: '',
  findings_at_admission: '',
  investigations_summary: '',
  course_in_hospital: '',
  procedure_notes: '',
  discharge_advice: '',
  follow_up: '',
  discharge_type: 'normal',
  condition_on_discharge: 'stable',
  take_home_medications: [],
  follow_up_date: '',
  diet_instructions: '',
  activity_restrictions: '',
  primary_doctor_id: '',
  secondary_doctor_id: '',
  payer_label: '',
  department_name: '',
  allergies_summary: '',
  surgery_date: '',
};

const STATUS_BADGE = {
  draft: { label: 'Draft', className: 'bg-amber-100 text-amber-800' },
  ready: { label: 'Ready to print', className: 'bg-green-100 text-green-800' },
  locked: { label: 'Locked', className: 'bg-slate-100 text-slate-700' },
};

const Section = ({ title, children }) => (
  <div className="space-y-2">
    <h4 className="text-sm font-semibold text-gray-800 border-b pb-1">{title}</h4>
    {children}
  </div>
);

const SummaryStepper = ({ step, onStepClick, locked }) => (
  <div className="flex flex-wrap items-center gap-2 text-xs border-b pb-3">
    {SUMMARY_STEPS.map((s, i) => {
      const done = s.id < step;
      const active = s.id === step;
      const clickable = onStepClick && (locked || s.id <= step);
      return (
        <React.Fragment key={s.id}>
          <button
            type="button"
            disabled={!clickable}
            onClick={() => clickable && onStepClick(s.id)}
            className={
              'flex items-center gap-1.5 rounded-full px-2 py-1 transition ' +
              (active ? 'bg-blue-600 text-white' :
                done ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600') +
              (clickable && !active ? ' hover:ring-1 hover:ring-blue-300 cursor-pointer' : '')
            }
          >
            <span className={
              'h-5 w-5 rounded-full flex items-center justify-center text-[10px] font-semibold ' +
              (active ? 'bg-white/20' : done ? 'bg-green-600 text-white' : 'bg-gray-300 text-gray-700')
            }>
              {done && !active ? '✓' : s.id}
            </span>
            <span className={active ? 'font-semibold' : ''}>{s.label}</span>
          </button>
          {i < SUMMARY_STEPS.length - 1 && (
            <span className="text-gray-300 hidden sm:inline">›</span>
          )}
        </React.Fragment>
      );
    })}
  </div>
);

const DischargeSummaryEditor = ({
  open,
  onClose,
  admissionId,
  admissionLabel = '',
  doctorsList = [],
  readOnly = false,
  onSaved,
}) => {
  const { toast } = useToast();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [status, setStatus] = useState(null);
  const [step, setStep] = useState(1);
  const [showPdfPreview, setShowPdfPreview] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [editingSubmitted, setEditingSubmitted] = useState(false);

  const update = (patch) => setForm(p => ({ ...p, ...patch }));

  const load = useCallback(async () => {
    if (!admissionId || !open) return;
    setLoading(true);
    try {
      const res = await axios.get(`/api/inpatient/admissions/${admissionId}/discharge-summary`);
      const data = res.data;
      setStatus(data.status);
      setForm({
        ...EMPTY_FORM,
        ...data,
        include_admission_vitals: data.include_admission_vitals !== false,
        follow_up_date: data.follow_up_date
          ? String(data.follow_up_date).slice(0, 10) : '',
        primary_doctor_id: data.primary_doctor_id ? String(data.primary_doctor_id) : '',
        secondary_doctor_id: data.secondary_doctor_id ? String(data.secondary_doctor_id) : '',
        take_home_medications: data.take_home_medications || [],
        payer_label: data.payer_label || '',
        department_name: data.department_name || '',
        allergies_summary: data.allergies_summary || '',
        surgery_date: data.surgery_date || '',
        chief_complaint: data.chief_complaint || '',
      });
    } catch (err) {
      if (err.response?.status === 404) {
        setStatus(null);
        setForm(EMPTY_FORM);
      } else {
        toast({
          variant: 'destructive',
          title: 'Could not load summary',
          description: typeof err.response?.data?.detail === 'string'
            ? err.response.data.detail : 'Network error',
        });
      }
    } finally {
      setLoading(false);
    }
  }, [admissionId, open, toast]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (open) setStep(1);
    if (!open) {
      setShowPdfPreview(false);
      setEditingSubmitted(false);
    }
  }, [open, admissionId]);

  const buildPayload = () => ({
    chief_complaint: form.chief_complaint || null,
    provisional_diagnosis: form.provisional_diagnosis || null,
    primary_diagnosis: form.primary_diagnosis || null,
    past_history: form.past_history || null,
    family_history: form.family_history || null,
    present_medical_history: form.present_medical_history || null,
    physical_examination_notes: form.physical_examination_notes || null,
    include_admission_vitals: form.include_admission_vitals !== false,
    emergency_instructions: form.emergency_instructions || null,
    findings_at_admission: form.findings_at_admission || null,
    investigations_summary: form.investigations_summary || null,
    course_in_hospital: form.course_in_hospital || null,
    procedure_notes: form.procedure_notes || null,
    discharge_advice: form.discharge_advice || null,
    follow_up: form.follow_up || null,
    discharge_type: form.discharge_type,
    condition_on_discharge: form.condition_on_discharge,
    take_home_medications: (form.take_home_medications || [])
      .filter(m => (m.medicine_name || '').trim())
      .map(serializeTakeHomeMed),
    follow_up_date: form.follow_up_date
      ? new Date(form.follow_up_date).toISOString() : null,
    diet_instructions: form.diet_instructions || null,
    activity_restrictions: form.activity_restrictions || null,
    primary_doctor_id: form.primary_doctor_id
      ? parseInt(form.primary_doctor_id, 10) : null,
    secondary_doctor_id: form.secondary_doctor_id
      ? parseInt(form.secondary_doctor_id, 10) : null,
  });

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await axios.put(
        `/api/inpatient/admissions/${admissionId}/discharge-summary`,
        buildPayload(),
      );
      setStatus(res.data.status);
      toast({ title: 'Draft saved' });
      onSaved?.(res.data);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail : 'Save failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally {
      setSaving(false);
    }
  };

  const handleFinalize = async () => {
    if (!form.primary_diagnosis?.trim()) {
      toast({ variant: 'destructive', title: 'Primary diagnosis required', description: 'Go to step 2 and enter the primary diagnosis.' });
      setStep(2);
      return;
    }
    setSaving(true);
    try {
      await axios.put(
        `/api/inpatient/admissions/${admissionId}/discharge-summary`,
        buildPayload(),
      );
      setShowPdfPreview(true);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail : 'Save failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally {
      setSaving(false);
    }
  };

  const handlePreviewDraft = async () => {
    setSaving(true);
    try {
      await axios.put(
        `/api/inpatient/admissions/${admissionId}/discharge-summary`,
        buildPayload(),
      );
      setShowPdfPreview(true);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail : 'Save failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally {
      setSaving(false);
    }
  };

  const confirmFinalize = async () => {
    setFinalizing(true);
    try {
      const res = await axios.post(
        `/api/inpatient/admissions/${admissionId}/discharge-summary/finalize`,
      );
      setStatus(res.data.status);
      setShowPdfPreview(false);
      toast({
        title: 'Summary finalized',
        description: 'Reception can now print this discharge summary.',
      });
      onSaved?.(res.data);
      onClose?.();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail : 'Finalize failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally {
      setFinalizing(false);
    }
  };

  const handleImportOt = async () => {
    try {
      const res = await axios.get(
        `/api/inpatient/admissions/${admissionId}/discharge-summary/ot-import`,
      );
      const text = (res.data?.text || '').trim();
      if (!text) {
        toast({
          variant: 'destructive',
          title: 'No OT record found',
          description: 'Schedule and complete an OT procedure for this admission first.',
        });
        return;
      }
      const patch = {
        procedure_notes: form.procedure_notes?.trim()
          ? `${form.procedure_notes.trim()}\n\n${text}` : text,
      };
      if (res.data?.surgery_date) {
        patch.surgery_date = res.data.surgery_date;
      }
      update(patch);
      toast({ title: 'Imported from OT schedule' });
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Import failed',
        description: typeof err.response?.data?.detail === 'string'
          ? err.response.data.detail : 'Could not load OT details',
      });
    }
  };

  const goNext = () => {
    if (step < TOTAL_STEPS) setStep(step + 1);
  };

  const goBack = () => {
    if (step > 1) setStep(step - 1);
  };

  const isSubmittedReady = status === 'ready' && !readOnly;
  const locked = status === 'locked' || readOnly || (isSubmittedReady && !editingSubmitted);
  const canPrint = summaryIsReadyForPrint(status);

  const handleReopenForEdit = async () => {
    setSaving(true);
    try {
      const res = await axios.post(
        `/api/inpatient/admissions/${admissionId}/discharge-summary/reopen`,
      );
      setStatus(res.data.status);
      setEditingSubmitted(true);
      toast({
        title: 'Reopened for editing',
        description: 'Summary is back in draft until you mark it ready for print again.',
      });
      onSaved?.(res.data);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail : 'Could not reopen summary';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally {
      setSaving(false);
    }
  };

  const handlePrint = async () => {
    const ok = await printPdfFromUrl(`/api/inpatient/admissions/${admissionId}/discharge-summary/pdf`);
    if (!ok) {
      toast({
        variant: 'destructive',
        title: 'Print failed',
        description: 'Mark the summary ready for print before printing.',
      });
    }
  };
  const badge = STATUS_BADGE[status] || STATUS_BADGE.draft;
  const isLastStep = step === TOTAL_STEPS;

  const renderStep = () => {
    if (step === 1) {
      return (
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <Label>Discharge type</Label>
              <Select value={form.discharge_type} disabled={locked}
                      onValueChange={v => update({ discharge_type: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="normal">Normal</SelectItem>
                  <SelectItem value="against_advice">Against medical advice</SelectItem>
                  <SelectItem value="transfer">Transfer</SelectItem>
                  <SelectItem value="death">Death</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Condition on discharge</Label>
              <Select value={form.condition_on_discharge} disabled={locked}
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
            <div>
              <Label>Primary doctor</Label>
              <Select value={form.primary_doctor_id} disabled={locked}
                      onValueChange={v => update({ primary_doctor_id: v })}>
                <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>
                  {doctorsList.map(d => (
                    <SelectItem key={d.id} value={String(d.id)}>
                      Dr. {d.first_name} {d.last_name}
                      {d.specialization ? ` · ${d.specialization}` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Secondary doctor</Label>
              <Select value={form.secondary_doctor_id} disabled={locked}
                      onValueChange={v => update({ secondary_doctor_id: v })}>
                <SelectTrigger><SelectValue placeholder="Optional" /></SelectTrigger>
                <SelectContent>
                  {doctorsList.map(d => (
                    <SelectItem key={d.id} value={String(d.id)}>
                      Dr. {d.first_name} {d.last_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          {(form.payer_label || form.department_name) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm bg-slate-50 border rounded p-3">
              {form.department_name && (
                <div>
                  <span className="text-gray-500">Department: </span>
                  <span className="font-medium">{form.department_name}</span>
                </div>
              )}
              {form.payer_label && (
                <div>
                  <span className="text-gray-500">Payer / scheme: </span>
                  <span className="font-medium">{form.payer_label}</span>
                </div>
              )}
              {form.surgery_date && (
                <div>
                  <span className="text-gray-500">Surgery date: </span>
                  <span className="font-medium">{form.surgery_date}</span>
                </div>
              )}
            </div>
          )}
          <p className="text-xs text-gray-500">
            Discharge type and consulting doctors appear on the printed summary.
          </p>
        </div>
      );
    }

    if (step === 2) {
      return (
        <div className="space-y-4">
          <Section title="Chief Complaints">
            <Textarea rows={2} disabled={locked} value={form.chief_complaint}
                      onChange={e => update({ chief_complaint: e.target.value })}
                      placeholder="Pre-filled from admission when available" />
          </Section>
          {form.allergies_summary && (
            <div className="text-sm bg-amber-50 border border-amber-100 rounded p-2">
              <span className="font-medium text-amber-900">Allergies (from patient record): </span>
              {form.allergies_summary}
            </div>
          )}
          <Section title="Provisional Diagnosis">
            <Textarea rows={2} disabled={locked} value={form.provisional_diagnosis}
                      onChange={e => update({ provisional_diagnosis: e.target.value })} />
          </Section>
          <Section title="Primary Diagnosis *">
            <Textarea rows={2} disabled={locked} value={form.primary_diagnosis}
                      onChange={e => update({ primary_diagnosis: e.target.value })}
                      placeholder="Required before marking ready for print" />
          </Section>
          <Section title="Past History">
            <Textarea rows={2} disabled={locked} value={form.past_history}
                      onChange={e => update({ past_history: e.target.value })} />
          </Section>
          <Section title="Family History">
            <Textarea rows={2} disabled={locked} value={form.family_history}
                      onChange={e => update({ family_history: e.target.value })} />
          </Section>
          <Section title="History of Present Illness">
            <Textarea rows={2} disabled={locked} value={form.present_medical_history}
                      onChange={e => update({ present_medical_history: e.target.value })} />
          </Section>
          <Section title="Physical Examination (additional notes)">
            <Textarea rows={2} disabled={locked} value={form.physical_examination_notes}
                      onChange={e => update({ physical_examination_notes: e.target.value })}
                      placeholder="Systemic examination notes; admission vitals are auto-included on print when enabled" />
            <label className="flex items-center gap-2 text-xs text-gray-600 mt-1">
              <input
                type="checkbox"
                disabled={locked}
                checked={form.include_admission_vitals !== false}
                onChange={e => update({ include_admission_vitals: e.target.checked })}
              />
              Include first recorded admission vitals on printed summary
            </label>
          </Section>
          <Section title="Key Findings at Admission">
            <Textarea rows={2} disabled={locked} value={form.findings_at_admission}
                      onChange={e => update({ findings_at_admission: e.target.value })} />
          </Section>
        </div>
      );
    }

    if (step === 3) {
      return (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <h4 className="text-sm font-semibold text-gray-800">Surgery / OT Findings</h4>
            {!locked && (
              <Button type="button" size="sm" variant="outline" onClick={handleImportOt}>
                Import from OT
              </Button>
            )}
          </div>
          <Section title="Summary of Key Investigation">
            <Textarea rows={3} disabled={locked} value={form.investigations_summary}
                      onChange={e => update({ investigations_summary: e.target.value })} />
          </Section>
          <Section title="Course in Hospital">
            <Textarea rows={4} disabled={locked} value={form.course_in_hospital}
                      onChange={e => update({ course_in_hospital: e.target.value })} />
          </Section>
          <Section title="Surgery / Procedure Notes">
            <Textarea rows={3} disabled={locked} value={form.procedure_notes}
                      onChange={e => update({ procedure_notes: e.target.value })}
                      placeholder="Procedure name, OT findings, anaesthesia details" />
          </Section>
        </div>
      );
    }

    return (
      <div className="space-y-4">
        <Section title="Discharge Advice">
          <Textarea rows={3} disabled={locked} value={form.discharge_advice}
                    onChange={e => update({ discharge_advice: e.target.value })} />
        </Section>
        <Section title="Follow Up">
          <Textarea rows={2} disabled={locked} value={form.follow_up}
                    onChange={e => update({ follow_up: e.target.value })}
                    placeholder="OPD review instructions, department, named consultants" />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-2">
            <div>
              <Label>Follow-up date</Label>
              <Input type="date" disabled={locked} value={form.follow_up_date}
                     onChange={e => update({ follow_up_date: e.target.value })} />
            </div>
            <div>
              <Label>Diet instructions</Label>
              <Input disabled={locked} value={form.diet_instructions}
                     onChange={e => update({ diet_instructions: e.target.value })} />
            </div>
          </div>
          <div className="mt-2">
            <Label>Activity restrictions</Label>
            <Input disabled={locked} value={form.activity_restrictions}
                   onChange={e => update({ activity_restrictions: e.target.value })} />
          </div>
          <div className="mt-2">
            <Label>Emergency instructions</Label>
            <Textarea rows={2} disabled={locked} value={form.emergency_instructions}
                      onChange={e => update({ emergency_instructions: e.target.value })}
                      placeholder="e.g. fever, bleeding, wound discharge — contact casualty immediately" />
          </div>
        </Section>
        <Section title="Take-home medications">
          <TakeHomeMedicinesSection
            medications={form.take_home_medications || []}
            onMedicationsChange={locked ? undefined : (meds) => update({ take_home_medications: meds })}
            admissionId={admissionId}
            description="Prescription for the patient to take home."
          />
        </Section>
        {!locked && (
          <p className="text-xs text-gray-500 bg-gray-50 border rounded p-2">
            Review all steps, then use <b>Mark ready for print</b> so reception can print and discharge the patient.
          </p>
        )}
      </div>
    );
  };

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose?.()}>
      <DialogContent className="max-w-3xl max-h-[92vh] flex flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 flex-wrap">
            <FileText className="h-5 w-5" />
            Discharge Summary
            {admissionLabel && (
              <span className="text-sm font-normal text-gray-500">— {admissionLabel}</span>
            )}
            {status && <Badge className={badge.className}>{badge.label}</Badge>}
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="py-12 text-center text-gray-500">
            <Loader2 className="h-6 w-6 mx-auto animate-spin" />
          </div>
        ) : (
          <>
            <SummaryStepper
              step={step}
              onStepClick={setStep}
              locked={locked}
            />
            <div className="flex-1 overflow-y-auto min-h-0 py-1 pr-1">
              {isSubmittedReady && !editingSubmitted && (
                <div className="mb-3 text-xs text-green-800 bg-green-50 border border-green-200 rounded p-2">
                  This summary is marked <b>ready for print</b>. Click <b>Edit submitted summary</b> to make changes.
                </div>
              )}
              {renderStep()}
            </div>
          </>
        )}

        <DialogFooter className="gap-2 flex-wrap sm:justify-between border-t pt-3 mt-1">
          <div className="flex gap-2 flex-wrap">
            <Button variant="outline" onClick={onClose}>Close</Button>
            {step > 1 && !loading && (
              <Button variant="outline" onClick={goBack} disabled={saving}>
                <ChevronLeft className="h-4 w-4 mr-1" /> Back
              </Button>
            )}
            {canPrint && !loading && (
              <Button variant="outline" onClick={handlePrint}>
                <Printer className="h-4 w-4 mr-1" /> Print discharge summary
              </Button>
            )}
            {!locked && !loading && isLastStep && !canPrint && (
              <Button variant="outline" onClick={handlePreviewDraft} disabled={saving || finalizing}>
                <Eye className="h-4 w-4 mr-1" /> Preview PDF
              </Button>
            )}
          </div>
          <div className="flex gap-2 flex-wrap">
            {isSubmittedReady && !editingSubmitted && !loading && (
              <>
                <Button variant="outline" onClick={handleReopenForEdit} disabled={saving}>
                  <Pencil className="h-4 w-4 mr-1" /> Edit submitted summary
                </Button>
              </>
            )}
            {!locked && !loading && (
              <>
                <Button variant="secondary" onClick={handleSave} disabled={saving}>
                  {saving && <Loader2 className="h-4 w-4 mr-1 animate-spin" />}
                  Save draft
                </Button>
                {!isLastStep ? (
                  <Button onClick={goNext} disabled={saving}>
                    Next <ChevronRight className="h-4 w-4 ml-1" />
                  </Button>
                ) : (
                  <Button onClick={handleFinalize} disabled={saving || finalizing}>
                    {saving ? <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                      : <CheckCircle2 className="h-4 w-4 mr-1" />}
                    Mark ready for print
                  </Button>
                )}
              </>
            )}
          </div>
        </DialogFooter>
      </DialogContent>

      <DischargeSummaryPdfPreviewDialog
        open={showPdfPreview}
        onClose={() => setShowPdfPreview(false)}
        admissionId={admissionId}
        admissionLabel={admissionLabel}
        onConfirm={confirmFinalize}
        confirming={finalizing}
      />
    </Dialog>
  );
};

export default DischargeSummaryEditor;
