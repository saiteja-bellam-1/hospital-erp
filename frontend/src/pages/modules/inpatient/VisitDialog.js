import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '../../../components/ui/dialog';
import { Button } from '../../../components/ui/button';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../../components/ui/select';
import { Stethoscope, ShieldAlert, Heart, Loader2, AlertTriangle } from 'lucide-react';

const TYPE_CARDS = [
  { value: 'doctor_visit',      label: 'Doctor (consultant)', sub: 'Visiting consultant fee',
    icon: Stethoscope, color: 'blue', forDoctors: true },
  { value: 'duty_doctor_visit', label: 'Duty doctor (round)', sub: 'Institutional flat fee',
    icon: ShieldAlert, color: 'amber', forDoctors: true },
  { value: 'nurse_visit',       label: 'Nurse visit',          sub: 'Nurse fee',
    icon: Heart, color: 'pink', forDoctors: false },
];

const colorClasses = (color, selected) => {
  const map = {
    blue:  selected ? 'border-blue-500 bg-blue-50 text-blue-800'   : 'border-gray-200 hover:border-blue-300',
    amber: selected ? 'border-amber-500 bg-amber-50 text-amber-800' : 'border-gray-200 hover:border-amber-300',
    pink:  selected ? 'border-pink-500 bg-pink-50 text-pink-800'    : 'border-gray-200 hover:border-pink-300',
  };
  return map[color] || map.blue;
};

const VisitDialog = ({
  open, onOpenChange, form, setForm,
  doctorsList = [], nursesList = [], isNurseOnly = false,
  loading = false, onSubmit,
}) => {
  const [onDuty, setOnDuty] = useState([]);     // doctors rostered now
  const [onDutyNurses, setOnDutyNurses] = useState([]);  // nurses rostered now
  const [dutyLoading, setDutyLoading] = useState(false);
  const [dutyRate, setDutyRate] = useState(null);  // hospital duty_visit_rate
  const [confirmBypass, setConfirmBypass] = useState(false);  // explicit checkbox

  // Reset bypass acknowledgement whenever the user changes type or visitor.
  useEffect(() => { setConfirmBypass(false); }, [form.visit_type, form.visitor_id]);

  // Load roster + rate config whenever the dialog opens or the type changes.
  useEffect(() => {
    if (!open) return;
    // Doctor on-duty list (used for duty-doctor card)
    if (form.visit_type === 'duty_doctor_visit') {
      setDutyLoading(true);
      axios.get('/api/inpatient/duty-doctor/on-duty')
        .then(r => setOnDuty(r.data?.on_duty || []))
        .catch(() => setOnDuty([]))
        .finally(() => setDutyLoading(false));
      axios.get('/api/inpatient/rate-config')
        .then(r => setDutyRate(r.data?.duty_visit_rate ?? null))
        .catch(() => setDutyRate(null));
    }
    // Nurse on-duty list (informational badges for nurse_visit selection)
    if (form.visit_type === 'nurse_visit') {
      const now = new Date();
      const hour = now.getHours();
      const shift = hour >= 6 && hour < 14 ? 'morning'
                  : hour >= 14 && hour < 22 ? 'afternoon' : 'night';
      const date = new Date(now);
      if (hour < 6) date.setDate(date.getDate() - 1);
      axios.get('/api/inpatient/roster/on-duty', {
        params: { target_date: date.toISOString().slice(0, 10), shift },
      })
        .then(r => setOnDutyNurses(r.data || []))
        .catch(() => setOnDutyNurses([]));
    }
  }, [open, form.visit_type]);

  const visibleCards = useMemo(
    () => TYPE_CARDS.filter(c => !isNurseOnly || !c.forDoctors || c.value === 'nurse_visit'
                               ? (isNurseOnly ? c.value === 'nurse_visit' : true)
                               : false),
    [isNurseOnly]
  );

  const isDuty = form.visit_type === 'duty_doctor_visit';
  const isDoctor = form.visit_type === 'doctor_visit';
  const isNurse = form.visit_type === 'nurse_visit';

  // Show ALL doctors/nurses for duty + nurse visits (not just on-duty). Roster
  // status is surfaced as a badge so the operator can see whether picking this
  // person is on-roster or off-roster — but they're free to choose either.
  const onDutyDoctorIds = useMemo(
    () => new Set(onDuty.map(o => o.doctor_id)), [onDuty]
  );
  const onDutyNurseIds = useMemo(
    () => new Set(onDutyNurses.map(n => n.nurse_id)), [onDutyNurses]
  );

  const visitorOptions = isNurse ? nursesList : doctorsList;
  const selectedVisitor = visitorOptions.find(u => String(u.id) === String(form.visitor_id));
  const visitorFee = selectedVisitor?.inpatient_fee_inr;

  // True when the selected duty visitor is NOT in the on-duty roster.
  const isOffRoster = isDuty && form.visitor_id
    && !onDutyDoctorIds.has(parseInt(form.visitor_id, 10));
  // For nurses, just an informational badge — no warning gate.
  const isNurseOffRoster = isNurse && form.visitor_id
    && !onDutyNurseIds.has(parseInt(form.visitor_id, 10));

  const handleCardClick = (type) => {
    setForm(p => ({ ...p, visit_type: type, visitor_id: '', bypass_roster_check: false }));
  };

  // Wrap submit so the bypass flag is added when the operator confirmed off-roster.
  const handleSubmit = (e) => {
    e.preventDefault();
    if (isDuty && isOffRoster && !confirmBypass) {
      // Sanity guard — the submit button is also disabled below; this is
      // belt-and-braces in case the keyboard submits the form first.
      return;
    }
    // Toggle the bypass flag on the form just before delegating to the
    // parent submit handler (which reads from form state).
    if (isDuty && isOffRoster) {
      setForm(p => ({ ...p, bypass_roster_check: true }));
      // Defer so the state mutation lands before the parent reads form.
      setTimeout(() => onSubmit?.(e), 0);
    } else {
      setForm(p => ({ ...p, bypass_roster_check: false }));
      onSubmit?.(e);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[92vh] overflow-y-auto">
        <DialogHeader><DialogTitle>Record Visit</DialogTitle></DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Visit type cards */}
          <div>
            <Label className="mb-2 block">Visit type *</Label>
            <div className="grid grid-cols-3 gap-2">
              {visibleCards.map(c => {
                const Icon = c.icon;
                const selected = form.visit_type === c.value;
                return (
                  <button
                    key={c.value}
                    type="button"
                    onClick={() => handleCardClick(c.value)}
                    className={
                      'border-2 rounded-lg p-3 text-left transition flex flex-col gap-1 ' +
                      colorClasses(c.color, selected)
                    }
                  >
                    <Icon className={'h-5 w-5 ' + (selected ? '' : 'text-gray-500')} />
                    <span className="text-sm font-medium">{c.label}</span>
                    <span className="text-[10px] text-gray-500">{c.sub}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Visitor selector — full list with on-duty badges. Operators are
              free to pick someone off-roster; for duty visits we then show
              a warning + require explicit confirmation. */}
          <div>
            <Label>{isDuty ? 'Duty doctor *' : 'Visitor (staff) *'}</Label>
            {isDuty && dutyLoading ? (
              <div className="flex items-center gap-2 text-xs text-gray-500 py-2">
                <Loader2 className="h-3 w-3 animate-spin" /> Loading on-duty roster…
              </div>
            ) : (
              <Select value={form.visitor_id ? String(form.visitor_id) : ''}
                      onValueChange={v => setForm(p => ({ ...p, visitor_id: v }))}>
                <SelectTrigger><SelectValue placeholder="Select" /></SelectTrigger>
                <SelectContent>
                  {visitorOptions.map(u => {
                    const dutyEntry = isDuty ? onDuty.find(o => o.doctor_id === u.id) : null;
                    const nurseEntry = isNurse ? onDutyNurses.find(n => n.nurse_id === u.id) : null;
                    const entry = dutyEntry || nurseEntry;
                    return (
                      <SelectItem key={u.id} value={String(u.id)}>
                        {u.first_name} {u.last_name}
                        {u.specialization && ` · ${u.specialization}`}
                        {entry?.ward && ` · ${entry.ward}`}
                        {entry?.status === 'working' && ' · on duty'}
                        {entry?.status === 'on_call' && ' · on-call'}
                        {(isDuty || isNurse) && !entry && ' · off-roster'}
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
            )}

            {/* Duty roster warning + bypass confirmation */}
            {isDuty && isOffRoster && (
              <div className="mt-2 flex items-start gap-2 bg-amber-50 border border-amber-300 rounded p-2 text-xs">
                <AlertTriangle className="h-4 w-4 text-amber-700 mt-0.5 flex-shrink-0" />
                <div className="flex-1">
                  <p className="font-medium text-amber-900">
                    Doctor is not on the duty roster for this shift.
                  </p>
                  <p className="text-amber-800 mt-0.5">
                    You can still record the visit — it will be logged as an
                    off-roster duty visit (audit trail kept). Update the
                    roster afterwards from Duty Roster → Doctors if needed.
                  </p>
                  <label className="mt-2 flex items-center gap-2 cursor-pointer">
                    <input type="checkbox"
                           checked={confirmBypass}
                           onChange={e => setConfirmBypass(e.target.checked)} />
                    <span className="text-amber-900">
                      I confirm — record as off-roster duty visit
                    </span>
                  </label>
                </div>
              </div>
            )}

            {/* Nurse off-roster: informational only, no gate */}
            {isNurseOffRoster && (
              <p className="text-xs text-gray-500 mt-1">
                ℹ Nurse is not on today's roster — visit will be recorded normally.
              </p>
            )}
          </div>

          {/* Charge preview */}
          {form.visitor_id && (isDoctor || isNurse) && (
            <p className="text-xs text-gray-600">
              Auto-charge: {visitorFee
                ? <b>₹{Number(visitorFee).toFixed(2)}</b>
                : 'no fee set on this user'}
              {' '}(from selected staff member's inpatient fee)
            </p>
          )}
          {isDuty && form.visitor_id && (
            <p className="text-xs text-gray-600">
              Auto-charge: {dutyRate
                ? <b>₹{Number(dutyRate).toFixed(2)}</b>
                : <b>institutional duty rate</b>}
              {' '}— flat rate from Billing Setup, independent of which doctor is on duty.
            </p>
          )}

          {/* Notes */}
          <div>
            <Label>Notes</Label>
            <Textarea value={form.notes}
                      onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                      rows={3} />
          </div>

          {/* Ward-round checklist for consultant + duty doctor */}
          {(isDoctor || isDuty) && (
            <div className="border rounded p-2 space-y-1 bg-gray-50">
              <p className="text-xs font-semibold text-gray-700">
                Round checklist (optional)
              </p>
              {[
                ['vitals_reviewed', 'Vitals reviewed'],
                ['labs_reviewed', 'Labs reviewed'],
                ['pain_assessed', 'Pain assessed'],
                ['mobility_checked', 'Mobility checked'],
                ['family_updated', 'Family updated'],
              ].map(([key, lbl]) => (
                <label key={key} className="flex items-center gap-2 text-sm cursor-pointer">
                  <input type="checkbox" checked={!!form[key]}
                         onChange={e => setForm(p => ({ ...p, [key]: e.target.checked }))} />
                  {lbl}
                </label>
              ))}
              <div>
                <Label className="text-xs">Plan for today</Label>
                <Textarea rows={2} value={form.plan_for_today}
                          placeholder="e.g., 'Continue IV antibiotics; repeat CBC tomorrow.'"
                          onChange={e => setForm(p => ({ ...p, plan_for_today: e.target.value }))} />
              </div>
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit"
                    disabled={loading || !form.visitor_id
                              || (isDuty && isOffRoster && !confirmBypass)}>
              {loading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {isDuty && isOffRoster ? 'Record off-roster visit' : 'Record visit'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default VisitDialog;
