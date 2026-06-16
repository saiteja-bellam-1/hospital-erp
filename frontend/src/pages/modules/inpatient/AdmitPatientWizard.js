import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle
} from '../../../components/ui/dialog';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Badge } from '../../../components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '../../../components/ui/select';
import { useToast } from '../../../hooks/use-toast';
import PatientSearchPicker from '../../../components/PatientSearchPicker';
import { printPdfFromUrl } from '../../../utils/printPdf';
import {
  Search, ChevronLeft, ChevronRight, Loader2,
  Banknote, Shield, FileCheck2, Landmark,
  CheckCircle2, AlertTriangle, FileText, X, Printer
} from 'lucide-react';

const DRAFT_KEY = 'kt_admit_wizard_draft_v1';

const SCHEME_ICONS = {
  cash:              Banknote,
  private_insurance: Shield,
  tpa:               FileCheck2,
  govt_scheme:       Landmark,
};

const EMPTY_DRAFT = {
  // Step 1
  patient_id: '',
  patient_label: '',
  room_id: '',
  bed_id: '',
  admission_type: 'elective',
  triage_level: '',
  estimated_stay_days: '',
  admission_reason: '',
  // Step 2 — doctors
  referring_doctor_id: '',
  referring_doctor_kind: 'internal',     // 'internal' | 'external'
  referring_external_name: '',
  admitting_doctor_id: '',
  attending_physician_id: '',
  require_acceptance: false,
  // Step 2 — payer
  payer_scheme_id: '',
  scheme_member_id: '',
  scheme_approval_status: 'none',
  scheme_approval_ref: '',
  scheme_approval_amount: '',
  // Step 2 — deposit
  deposit_amount: '',
  deposit_method: 'cash',
  deposit_reference: '',
  deposit_waived: false,
  deposit_waiver_reason: '',
  // Step 3
  face_sheet_signed: false,
  case_sheet_signed: false,
  face_sheet_doc_number: '',
  case_sheet_doc_number: '',
};

const Stepper = ({ step }) => {
  const labels = ['Identity & Bed', 'Doctors · Payer · Deposit', 'Declarations'];
  return (
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
                 active ? 'bg-blue-600 text-white' :
                 'bg-gray-200 text-gray-600')
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
};


const PayerCard = ({ scheme, selected, onSelect }) => {
  const Icon = SCHEME_ICONS[scheme.scheme_type] || Banknote;
  return (
    <button
      type="button"
      onClick={() => onSelect(scheme)}
      className={
        'border-2 rounded-lg p-3 text-left transition flex flex-col items-start gap-1 min-h-[72px] ' +
        (selected
          ? 'border-blue-500 bg-blue-50'
          : 'border-gray-200 hover:border-gray-400 bg-white')
      }
    >
      <Icon className={'h-5 w-5 ' + (selected ? 'text-blue-600' : 'text-gray-500')} />
      <span className={'text-sm font-medium ' + (selected ? 'text-blue-700' : 'text-gray-800')}>
        {scheme.name}
      </span>
      <span className="text-[10px] uppercase tracking-wide text-gray-400">
        {scheme.scheme_type.replace('_', ' ')}
      </span>
    </button>
  );
};


const AdmitPatientWizard = ({ open, onClose, onCreated, doctorsList = [] }) => {
  const { toast } = useToast();
  const [step, setStep] = useState(1);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [saving, setSaving] = useState(false);

  // lookups
  const [rooms, setRooms] = useState([]);
  const [bedsInRoom, setBedsInRoom] = useState([]);
  const [schemes, setSchemes] = useState([]);
  const [templates, setTemplates] = useState([]);  // consent templates (face/case sheet)
  const [selectedPatient, setSelectedPatient] = useState(null);

  const patientFromDraftLabel = (saved) => {
    if (!saved?.patient_id) return null;
    const namePart = (saved.patient_label || '').split(' · ')[0] || '';
    const parts = namePart.trim().split(/\s+/).filter(Boolean);
    return {
      id: saved.patient_id,
      first_name: parts[0] || 'Patient',
      last_name: parts.slice(1).join(' '),
      patient_id: saved.patient_id,
      primary_phone: '',
    };
  };

  // restore draft on open
  useEffect(() => {
    if (!open) return;
    setStep(1);
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (raw) {
        const saved = JSON.parse(raw);
        setDraft({ ...EMPTY_DRAFT, ...saved });
        setSelectedPatient(patientFromDraftLabel(saved));
      } else {
        setDraft(EMPTY_DRAFT);
        setSelectedPatient(null);
      }
    } catch {
      setDraft(EMPTY_DRAFT);
      setSelectedPatient(null);
    }
  }, [open]);

  // persist draft as user edits
  useEffect(() => {
    if (!open) return;
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(draft)); } catch {}
  }, [draft, open]);

  // load rooms + schemes + consent templates once when dialog opens
  useEffect(() => {
    if (!open) return;
    axios.get('/api/inpatient/rooms', { params: { available_only: true } })
      .then(r => setRooms(r.data || [])).catch(() => setRooms([]));
    axios.get('/api/inpatient/payer-schemes', { params: { active_only: true } })
      .then(r => setSchemes(r.data || [])).catch(() => setSchemes([]));
    axios.get('/api/inpatient/consent-templates')
      .then(r => setTemplates(r.data || []))
      .catch(() => setTemplates([]));
  }, [open]);

  // load beds when room changes
  useEffect(() => {
    if (!draft.room_id) { setBedsInRoom([]); return; }
    axios.get(`/api/inpatient/rooms/${draft.room_id}/beds`)
      .then(r => setBedsInRoom((r.data || []).filter(b => b.status === 'available')))
      .catch(() => setBedsInRoom([]));
  }, [draft.room_id]);

  const selectedScheme = useMemo(
    () => schemes.find(s => s.id === parseInt(draft.payer_scheme_id, 10)) || null,
    [schemes, draft.payer_scheme_id]
  );
  const selectedRoom = useMemo(
    () => rooms.find(r => r.id === parseInt(draft.room_id, 10)) || null,
    [rooms, draft.room_id]
  );

  const faceTpl = useMemo(() => templates.find(t => t.consent_type === 'face_sheet'), [templates]);
  const caseTpl = useMemo(() => templates.find(t => t.consent_type === 'case_sheet_declaration'), [templates]);

  // Pre-reserve doc numbers as soon as the user reaches Step 3 with a
  // patient selected, so the wizard can print/show them. Idempotent on
  // the backend — repeated calls return the same unconsumed reservation.
  useEffect(() => {
    if (step !== 3 || !draft.patient_id) return;
    const reserve = async (tpl, draftKey) => {
      if (!tpl || draft[draftKey]) return;
      try {
        const res = await axios.post('/api/inpatient/consents/reserve-doc-number', {
          patient_id: String(draft.patient_id),
          template_id: tpl.id,
          consent_type: tpl.consent_type,
        });
        const num = res.data?.doc_number;
        if (num) update({ [draftKey]: num });
      } catch (_) { /* non-fatal — staff can still admit; number assigned at sign-time */ }
    };
    reserve(faceTpl, 'face_sheet_doc_number');
    reserve(caseTpl, 'case_sheet_doc_number');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, draft.patient_id, faceTpl, caseTpl]);

  const update = (patch) => setDraft(p => ({ ...p, ...patch }));

  const validateStep1 = () => {
    if (!draft.patient_id) return 'Select a patient.';
    if (!draft.room_id) return 'Select a ward / room.';
    if (!draft.admission_type) return 'Choose admission type.';
    if (draft.admission_type === 'emergency' && !draft.triage_level) {
      return 'Triage level is required for emergency admissions.';
    }
    return null;
  };
  const validateStep2 = () => {
    if (!draft.admitting_doctor_id) return 'Pick the admitting / joining doctor.';
    if (draft.referring_doctor_kind === 'internal' && !draft.referring_doctor_id
        && draft.referring_external_name === '') {
      // referring is optional altogether — only validate if they tried to fill
    }
    if (draft.referring_doctor_kind === 'external' && !draft.referring_external_name.trim()) {
      return 'Enter the external referring doctor name.';
    }
    if (!draft.payer_scheme_id) return 'Choose a payer scheme.';
    if (selectedScheme && selectedScheme.scheme_type !== 'cash' && !draft.scheme_member_id.trim()) {
      return 'Member / policy ID is required for non-cash schemes.';
    }
    if (draft.deposit_waived && !draft.deposit_waiver_reason.trim()) {
      return 'Waiver reason is required when deposit is waived.';
    }
    if (!draft.deposit_waived && (!draft.deposit_amount || parseFloat(draft.deposit_amount) <= 0)) {
      return 'Enter an advance deposit (or check Waive deposit).';
    }
    return null;
  };
  const validateStep3 = () => {
    if (!draft.face_sheet_signed) return 'Face sheet must be marked signed.';
    if (!draft.case_sheet_signed) return 'Case sheet must be marked signed.';
    return null;
  };

  const goNext = () => {
    const err = step === 1 ? validateStep1() : step === 2 ? validateStep2() : null;
    if (err) { toast({ variant: 'destructive', title: 'Check fields', description: err }); return; }
    setStep(s => s + 1);
  };
  const goBack = () => setStep(s => Math.max(1, s - 1));

  const closeAndClear = () => {
    try { localStorage.removeItem(DRAFT_KEY); } catch {}
    onClose?.();
  };

  const handleSaveDraft = () => {
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(draft)); } catch {}
    toast({ title: 'Draft saved', description: 'You can resume this admission later.' });
    onClose?.();
  };

  const submit = async () => {
    const err = validateStep3();
    if (err) { toast({ variant: 'destructive', title: 'Cannot admit', description: err }); return; }
    setSaving(true);
    try {
      const payload = {
        patient_id: parseInt(draft.patient_id, 10),
        admitting_doctor_id: parseInt(draft.admitting_doctor_id, 10),
        attending_physician_id: draft.attending_physician_id
          ? parseInt(draft.attending_physician_id, 10) : null,
        room_id: parseInt(draft.room_id, 10),
        bed_id: draft.bed_id ? parseInt(draft.bed_id, 10) : null,
        admission_type: draft.admission_type,
        admission_reason: draft.admission_reason || null,
        estimated_stay_days: draft.estimated_stay_days
          ? parseInt(draft.estimated_stay_days, 10) : null,
        triage_level: draft.admission_type === 'emergency' && draft.triage_level
          ? parseInt(draft.triage_level, 10) : null,
        // Referring
        referring_doctor_id: draft.referring_doctor_kind === 'internal' && draft.referring_doctor_id
          ? parseInt(draft.referring_doctor_id, 10) : null,
        referring_external_name: draft.referring_doctor_kind === 'external'
          ? (draft.referring_external_name.trim() || null) : null,
        // Payer
        payer_scheme_id: parseInt(draft.payer_scheme_id, 10),
        scheme_member_id: draft.scheme_member_id || null,
        scheme_approval_status: draft.scheme_approval_status || 'none',
        scheme_approval_ref: draft.scheme_approval_ref || null,
        scheme_approval_amount: draft.scheme_approval_amount
          ? parseFloat(draft.scheme_approval_amount) : null,
        // Acceptance
        require_acceptance: !!draft.require_acceptance,
        // Waiver
        deposit_waived: !!draft.deposit_waived,
        deposit_waiver_reason: draft.deposit_waived ? draft.deposit_waiver_reason : null,
      };
      const admRes = await axios.post('/api/inpatient/admissions', payload);
      const newAdm = admRes.data;

      // Deposit (only if not waived and amount > 0)
      if (!draft.deposit_waived && draft.deposit_amount && parseFloat(draft.deposit_amount) > 0) {
        try {
          const dep = await axios.post(`/api/inpatient/admissions/${newAdm.id}/deposits`, {
            amount: parseFloat(draft.deposit_amount),
            deposit_type: 'initial',
            payment_method: draft.deposit_method,
            reference_number: draft.deposit_reference || null,
          });
          // Auto-print the deposit receipt so the receptionist can hand it over
          try {
            const pdfRes = await axios.get(
              `/api/inpatient/deposits/${dep.data.id}/receipt/pdf`,
              { responseType: 'blob' },
            );
            const url = URL.createObjectURL(new Blob([pdfRes.data], { type: 'application/pdf' }));
            printPdfFromUrl(url);
            setTimeout(() => URL.revokeObjectURL(url), 60_000);
          } catch (_) { /* receipt is best-effort; admission already saved */ }
        } catch (dErr) {
          toast({ variant: 'destructive', title: 'Deposit not recorded',
            description: 'Admission created but deposit failed. Add it from the admission detail.' });
        }
      }

      // Record the two consent acknowledgements (face + case sheet)
      const recordConsent = async (template, reservedDocNumber) => {
        if (!template) return null;
        try {
          const res = await axios.post(`/api/inpatient/admissions/${newAdm.id}/consents`, {
            consent_type: template.consent_type,
            template_id: template.id,
            language: template.language || 'english',
            patient_signature: draft.patient_label || 'Signed at admission',
            patient_signature_type: 'typed',
            signed_by: 'patient',
            doc_number: reservedDocNumber || undefined,
          });
          return res.data?.doc_number || null;
        } catch { return null; }
      };
      const faceDocNum = await recordConsent(faceTpl, draft.face_sheet_doc_number);
      const caseDocNum = await recordConsent(caseTpl, draft.case_sheet_doc_number);
      if (faceDocNum) update({ face_sheet_doc_number: faceDocNum });
      if (caseDocNum) update({ case_sheet_doc_number: caseDocNum });

      try { localStorage.removeItem(DRAFT_KEY); } catch {}
      toast({ title: 'Patient admitted',
        description: payload.require_acceptance
          ? 'Awaiting IP doctor acceptance.'
          : 'Admission accepted.' });
      onCreated?.(newAdm);
      onClose?.();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail
        : 'Failed to create admission';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={v => !v && onClose?.()}>
      <DialogContent className="max-w-5xl max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span>Admit Patient</span>
            <span className="text-xs font-normal text-gray-500">Step {step} of 3</span>
          </DialogTitle>
        </DialogHeader>

        <div className="border-b pb-3 mb-4">
          <Stepper step={step} />
        </div>

        {/* ---------- STEP 1 ---------- */}
        {step === 1 && (
          <div className="space-y-4">
            <section>
              <PatientSearchPicker
                value={selectedPatient}
                onChange={(p) => {
                  setSelectedPatient(p);
                  if (p) {
                    update({
                      patient_id: p.id,
                      patient_label: `${p.first_name} ${p.last_name} · ${p.gender || '—'} · MRN ${p.mrn || p.patient_id}`,
                    });
                  } else {
                    update({ patient_id: '', patient_label: '' });
                  }
                }}
                label="Patient"
                required
              />
            </section>

            <section className="grid grid-cols-2 gap-3">
              <div>
                <Label>Ward / Room *</Label>
                <Select value={draft.room_id ? String(draft.room_id) : ''}
                        onValueChange={v => update({ room_id: v, bed_id: '' })}>
                  <SelectTrigger><SelectValue placeholder="Select room" /></SelectTrigger>
                  <SelectContent>
                    {rooms.map(r => (
                      <SelectItem key={r.id} value={String(r.id)}>
                        {r.room_number} · {r.room_type} · ₹{r.room_charge_per_day}/day · {r.available_beds} bed(s) free
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Bed</Label>
                <Select value={draft.bed_id ? String(draft.bed_id) : ''}
                        onValueChange={v => update({ bed_id: v })}
                        disabled={!draft.room_id || bedsInRoom.length === 0}>
                  <SelectTrigger>
                    <SelectValue placeholder={bedsInRoom.length ? 'Pick a bed' : 'No structured beds'} />
                  </SelectTrigger>
                  <SelectContent>
                    {bedsInRoom.map(b => (
                      <SelectItem key={b.id} value={String(b.id)}>Bed {b.bed_label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </section>

            <section className="grid grid-cols-2 gap-3">
              <div>
                <Label>Admission type *</Label>
                <Select value={draft.admission_type}
                        onValueChange={v => update({ admission_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="elective">Elective</SelectItem>
                    <SelectItem value="emergency">Emergency</SelectItem>
                    <SelectItem value="transfer">Transfer</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label>Estimated stay (days)</Label>
                <Input type="number" min="1"
                       value={draft.estimated_stay_days}
                       onChange={e => update({ estimated_stay_days: e.target.value })}
                       placeholder="e.g. 3" />
              </div>
            </section>

            {draft.admission_type === 'emergency' && (
              <section>
                <Label>Triage level *</Label>
                <Select value={draft.triage_level}
                        onValueChange={v => update({ triage_level: v })}>
                  <SelectTrigger><SelectValue placeholder="ESI 1–5" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">1 — Resuscitation</SelectItem>
                    <SelectItem value="2">2 — Emergent</SelectItem>
                    <SelectItem value="3">3 — Urgent</SelectItem>
                    <SelectItem value="4">4 — Less urgent</SelectItem>
                    <SelectItem value="5">5 — Non-urgent</SelectItem>
                  </SelectContent>
                </Select>
              </section>
            )}

            <section>
              <Label>Admission reason / chief complaint</Label>
              <Textarea rows={2}
                        value={draft.admission_reason}
                        onChange={e => update({ admission_reason: e.target.value })}
                        placeholder="e.g. Chest pain, requires cardiac evaluation" />
            </section>
          </div>
        )}

        {/* ---------- STEP 2 ---------- */}
        {step === 2 && (
          <div className="space-y-5">
            {/* Doctors */}
            <section className="space-y-3">
              <h3 className="font-semibold text-sm text-gray-700 border-b pb-1">Doctors</h3>

              <div>
                <Label>Referring doctor (optional)</Label>
                <div className="flex gap-3 mb-2">
                  <label className="flex items-center gap-1 text-sm">
                    <input type="radio" name="ref_kind"
                           checked={draft.referring_doctor_kind === 'internal'}
                           onChange={() => update({ referring_doctor_kind: 'internal',
                                                    referring_external_name: '' })} />
                    Internal
                  </label>
                  <label className="flex items-center gap-1 text-sm">
                    <input type="radio" name="ref_kind"
                           checked={draft.referring_doctor_kind === 'external'}
                           onChange={() => update({ referring_doctor_kind: 'external',
                                                    referring_doctor_id: '' })} />
                    External
                  </label>
                </div>
                {draft.referring_doctor_kind === 'internal' ? (
                  <Select value={draft.referring_doctor_id ? String(draft.referring_doctor_id) : ''}
                          onValueChange={v => update({ referring_doctor_id: v })}>
                    <SelectTrigger><SelectValue placeholder="Pick referring doctor (optional)" /></SelectTrigger>
                    <SelectContent>
                      {doctorsList.map(d => (
                        <SelectItem key={d.id} value={String(d.id)}>
                          Dr. {d.first_name} {d.last_name}
                          {d.specialization ? ` · ${d.specialization}` : ''}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <Input value={draft.referring_external_name}
                         onChange={e => update({ referring_external_name: e.target.value })}
                         placeholder="External doctor name & clinic" />
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Admitting / joining doctor *</Label>
                  <Select value={draft.admitting_doctor_id ? String(draft.admitting_doctor_id) : ''}
                          onValueChange={v => update({ admitting_doctor_id: v })}>
                    <SelectTrigger><SelectValue placeholder="Select doctor" /></SelectTrigger>
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
                  <Label>Attending physician (under whom)</Label>
                  <Select value={draft.attending_physician_id ? String(draft.attending_physician_id) : ''}
                          onValueChange={v => update({ attending_physician_id: v })}>
                    <SelectTrigger><SelectValue placeholder="Same as admitting if blank" /></SelectTrigger>
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
              </div>

              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox"
                       className="mt-0.5"
                       checked={draft.require_acceptance}
                       onChange={e => update({ require_acceptance: e.target.checked })} />
                <span>
                  Require IP-doctor acceptance before clinical actions
                  <span className="block text-xs text-gray-500">
                    Recommended. Uncheck only if the admitting doctor will also handle the patient on the floor.
                  </span>
                </span>
              </label>
            </section>

            {/* Payer */}
            <section className="space-y-3">
              <h3 className="font-semibold text-sm text-gray-700 border-b pb-1">Payer</h3>
              {schemes.length === 0 ? (
                <div className="text-sm text-gray-500 border rounded p-3">
                  No active payer schemes. Ask an admin to add them in
                  Hospital Administration → Payer Schemes.
                </div>
              ) : (
                <div className="grid grid-cols-3 gap-2">
                  {schemes.map(s => (
                    <PayerCard
                      key={s.id}
                      scheme={s}
                      selected={parseInt(draft.payer_scheme_id, 10) === s.id}
                      onSelect={(sc) => update({ payer_scheme_id: String(sc.id) })}
                    />
                  ))}
                </div>
              )}

              {selectedScheme && selectedScheme.scheme_type !== 'cash' && (
                <div className="grid grid-cols-2 gap-3 pt-1">
                  <div>
                    <Label>Member / Policy ID *</Label>
                    <Input value={draft.scheme_member_id}
                           onChange={e => update({ scheme_member_id: e.target.value })}
                           placeholder="e.g. AGS-1029-3811" />
                  </div>
                  <div>
                    <Label>Approval status</Label>
                    <Select value={draft.scheme_approval_status}
                            onValueChange={v => update({ scheme_approval_status: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="none">Not submitted</SelectItem>
                        <SelectItem value="pending">Pending</SelectItem>
                        <SelectItem value="approved">Approved</SelectItem>
                        <SelectItem value="rejected">Rejected</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Approval ref</Label>
                    <Input value={draft.scheme_approval_ref}
                           onChange={e => update({ scheme_approval_ref: e.target.value })}
                           placeholder="Approval letter no." />
                  </div>
                  <div>
                    <Label>Approved amount (₹)</Label>
                    <Input type="number" min="0" step="0.01"
                           value={draft.scheme_approval_amount}
                           onChange={e => update({ scheme_approval_amount: e.target.value })} />
                  </div>
                </div>
              )}
            </section>

            {/* Deposit */}
            <section className="space-y-3">
              <h3 className="font-semibold text-sm text-gray-700 border-b pb-1">Advance deposit</h3>
              {draft.deposit_waived ? (
                <Textarea rows={2}
                          value={draft.deposit_waiver_reason}
                          onChange={e => update({ deposit_waiver_reason: e.target.value })}
                          placeholder="Waiver reason (required) — e.g. life-threatening emergency, Supreme Court / CEA Act compliance" />
              ) : (
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <Label>Amount ₹ *</Label>
                    <Input type="number" min="0" step="0.01"
                           value={draft.deposit_amount}
                           onChange={e => update({ deposit_amount: e.target.value })} />
                  </div>
                  <div>
                    <Label>Method</Label>
                    <Select value={draft.deposit_method}
                            onValueChange={v => update({ deposit_method: v })}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="cash">Cash</SelectItem>
                        <SelectItem value="card">Card</SelectItem>
                        <SelectItem value="upi">UPI</SelectItem>
                        <SelectItem value="cheque">Cheque</SelectItem>
                        <SelectItem value="online">Online transfer</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Reference no.</Label>
                    <Input value={draft.deposit_reference}
                           onChange={e => update({ deposit_reference: e.target.value })}
                           placeholder="Optional" />
                  </div>
                </div>
              )}
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox"
                       checked={draft.deposit_waived}
                       onChange={e => update({ deposit_waived: e.target.checked })} />
                Waive deposit (e.g. emergency / charity case)
              </label>
            </section>
          </div>
        )}

        {/* ---------- STEP 3 ---------- */}
        {step === 3 && (
          <div className="space-y-4">
            <p className="text-sm text-gray-700">
              Both declarations must be signed before the admission is created.
              The templates below come from
              Hospital Administration → Consent Templates and can be edited there.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <DeclarationCard
                title="Face Sheet"
                subtitle="Patient identification + responsible person details"
                template={faceTpl}
                signed={draft.face_sheet_signed}
                onToggle={v => update({ face_sheet_signed: v })}
                docNumber={draft.face_sheet_doc_number}
                patientId={draft.patient_id}
                roomId={draft.room_id}
                doctorId={draft.admitting_doctor_id}
                referringDoctorId={draft.referring_doctor_kind === 'internal' ? draft.referring_doctor_id : ''}
                admissionReason={draft.admission_reason}
              />
              <DeclarationCard
                title="Case Sheet"
                subtitle="General consent / liability declaration"
                template={caseTpl}
                signed={draft.case_sheet_signed}
                onToggle={v => update({ case_sheet_signed: v })}
                docNumber={draft.case_sheet_doc_number}
                patientId={draft.patient_id}
                roomId={draft.room_id}
                doctorId={draft.admitting_doctor_id}
                referringDoctorId={draft.referring_doctor_kind === 'internal' ? draft.referring_doctor_id : ''}
                admissionReason={draft.admission_reason}
              />
            </div>
            {(!faceTpl || !caseTpl) && (
              <div className="flex items-start gap-2 bg-amber-50 border border-amber-200 rounded p-3 text-sm">
                <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5" />
                <span>
                  Default templates not yet seeded. Restart the backend to auto-seed
                  the face-sheet and case-sheet, or add them manually in Hospital Administration → Consent Templates.
                </span>
              </div>
            )}
          </div>
        )}

        {/* Footer actions */}
        <div className="flex items-center justify-between pt-4 mt-4 border-t">
          <div>
            {step > 1 && (
              <Button variant="outline" onClick={goBack}>
                <ChevronLeft className="h-4 w-4 mr-1" /> Back
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={handleSaveDraft}>Save draft</Button>
            <Button variant="ghost" onClick={closeAndClear}>Cancel</Button>
            {step < 3 && (
              <Button onClick={goNext}>
                Next <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            )}
            {step === 3 && (
              <Button onClick={submit} disabled={saving}>
                {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Admit patient
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};


const DeclarationCard = ({
  title, subtitle, template, signed, onToggle, docNumber,
  patientId, roomId, doctorId, referringDoctorId, admissionReason,
}) => {
  const { toast } = useToast();
  const [previewOpen, setPreviewOpen] = useState(false);
  const [printing, setPrinting] = useState(false);

  const canPrefill = Boolean(template && patientId);

  const handlePrint = async () => {
    if (!canPrefill || printing) return;
    if (!template?.id) {
      toast({ variant: 'destructive', title: 'Print failed', description: 'Consent template is not configured.' });
      return;
    }
    setPrinting(true);
    try {
      const params = {
        patient_id: String(patientId),
        template_id: template.id,
      };
      if (roomId) params.room_id = parseInt(roomId, 10);
      if (doctorId) params.admitting_doctor_id = parseInt(doctorId, 10);
      if (referringDoctorId) params.referring_doctor_id = parseInt(referringDoctorId, 10);
      if (admissionReason) params.admission_reason = admissionReason;
      if (docNumber) params.doc_number = docNumber;
      let errMsg = null;
      const ok = await printPdfFromUrl('/api/inpatient/consents/preview-pdf', {
        params,
        onError: (msg) => { errMsg = msg; },
      });
      if (!ok) {
        toast({
          variant: 'destructive',
          title: 'Print failed',
          description: errMsg || 'Could not load or print the consent form.',
        });
      }
    } finally {
      setPrinting(false);
    }
  };

  return (
    <div className={
      'border-2 rounded-lg p-3 ' +
      (signed ? 'border-green-500 bg-green-50' : 'border-gray-200')
    }>
      <div className="flex items-start gap-2">
        <FileText className={'h-5 w-5 ' + (signed ? 'text-green-600' : 'text-gray-500')} />
        <div className="flex-1">
          <div className="font-medium text-sm">{title}</div>
          <div className="text-xs text-gray-600">{subtitle}</div>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => setPreviewOpen(true)}
                disabled={!template}>
          Preview
        </Button>
        <Button size="sm" variant="outline" onClick={handlePrint}
                disabled={!canPrefill || printing}
                title={!patientId ? 'Select a patient first' : 'Print prefilled form for patient signature'}>
          {printing
            ? <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> Printing…</>
            : <><Printer className="h-4 w-4 mr-1" /> Print</>}
        </Button>
        <Button size="sm"
                variant={signed ? 'outline' : 'default'}
                onClick={() => onToggle(!signed)}>
          {signed
            ? <><CheckCircle2 className="h-4 w-4 mr-1" /> Signed — undo</>
            : 'Mark signed'}
        </Button>
      </div>
      {signed && (
        <Badge className="bg-green-100 text-green-800 text-xs mt-2">
          ✓ Signature recorded
        </Badge>
      )}
      {docNumber ? (
        <div className="mt-2 rounded bg-blue-50 border border-blue-200 px-2 py-1 text-xs text-blue-800">
          <span className="font-semibold">Doc No: {docNumber}</span>
          <span className="ml-1 text-blue-600">— write this on your physical form if you're not printing ours</span>
        </div>
      ) : (
        <div className="mt-2 text-xs text-gray-400 italic">
          {patientId ? 'Allocating doc number…' : 'Doc number appears once patient is selected.'}
        </div>
      )}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{template?.template_name || title}</DialogTitle>
          </DialogHeader>
          <pre className="whitespace-pre-wrap text-xs font-mono bg-gray-50 p-3 rounded border">
            {template?.content || '—'}
          </pre>
        </DialogContent>
      </Dialog>
    </div>
  );
};


export default AdmitPatientWizard;
