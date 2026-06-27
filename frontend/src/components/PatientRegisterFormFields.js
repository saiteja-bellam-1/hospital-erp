import React from 'react';
import FormNavContainer from './FormNavContainer';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import {
  applyDobToForm,
  computeAgeFromDob,
  formatPatientAge,
  hasValidAge,
  parseAgeFields,
} from '../utils/patientAge';

export const EMPTY_PATIENT_FORM = {
  first_name: '',
  last_name: '',
  date_of_birth: '',
  age: '',
  age_months: '',
  gender: '',
  blood_group: '',
  marital_status: '',
  abha_id: '',
  email: '',
  primary_phone: '',
  emergency_contact_name: '',
  emergency_contact_phone: '',
  emergency_contact_relation: '',
  address_line1: '',
  address_line2: '',
  village: '',
  mandal: '',
  district: '',
};

/** Full patient registration field grid — shared by dashboard register + quick appointment step 1. */
export default function PatientRegisterFormFields({ form, onChange }) {
  const set = (key, val) => onChange({ ...form, [key]: val });

  const clearDobOnManualAge = (updates) => {
    onChange({ ...form, ...updates, date_of_birth: '' });
  };

  return (
    <FormNavContainer mode="grid" className="grid grid-cols-4 gap-x-3 gap-y-1.5">
      <div>
        <Label>First Name *</Label>
        <Input value={form.first_name} onChange={(e) => set('first_name', e.target.value)} />
      </div>
      <div>
        <Label>Last Name *</Label>
        <Input value={form.last_name} onChange={(e) => set('last_name', e.target.value)} />
      </div>
      <div>
        <Label>Date of Birth</Label>
        <Input
          type="date"
          value={form.date_of_birth}
          onChange={(e) => onChange(applyDobToForm(form, e.target.value))}
        />
      </div>
      <div>
        <Label>Age (years) *</Label>
        <Input
          type="number"
          min="0"
          max="150"
          placeholder="Years"
          value={form.age}
          onChange={(e) => clearDobOnManualAge({ age: e.target.value })}
        />
      </div>
      <div>
        <Label>Age (months)</Label>
        <Input
          type="number"
          min="0"
          max="11"
          placeholder="Months (for infants)"
          value={form.age_months}
          onChange={(e) => clearDobOnManualAge({ age_months: e.target.value })}
        />
      </div>
      <div>
        <Label>Gender</Label>
        <Select value={form.gender} onValueChange={(v) => set('gender', v)}>
          <SelectTrigger><SelectValue placeholder="Select Gender" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="Male">Male</SelectItem>
            <SelectItem value="Female">Female</SelectItem>
            <SelectItem value="Other">Other</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label>Primary Phone *</Label>
        <Input value={form.primary_phone} onChange={(e) => set('primary_phone', e.target.value)} />
      </div>
      <div>
        <Label>Blood Group</Label>
        <Select value={form.blood_group} onValueChange={(v) => set('blood_group', v)}>
          <SelectTrigger><SelectValue placeholder="Select Blood Group" /></SelectTrigger>
          <SelectContent>
            {['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'].map((bg) => (
              <SelectItem key={bg} value={bg}>{bg}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label>Marital Status</Label>
        <Select value={form.marital_status} onValueChange={(v) => set('marital_status', v)}>
          <SelectTrigger><SelectValue placeholder="Select Status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="Single">Single</SelectItem>
            <SelectItem value="Married">Married</SelectItem>
            <SelectItem value="Widowed">Widowed</SelectItem>
            <SelectItem value="Divorced">Divorced</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label>ABHA ID</Label>
        <Input value={form.abha_id} onChange={(e) => set('abha_id', e.target.value)} placeholder="14-digit ABHA number" />
      </div>
      <div>
        <Label>Email</Label>
        <Input type="email" value={form.email} onChange={(e) => set('email', e.target.value)} />
      </div>

      <div className="col-span-full border-t pt-2 mt-1">
        <Label className="text-sm font-semibold text-gray-700">Emergency Contact</Label>
      </div>
      <div>
        <Label>Contact Name</Label>
        <Input value={form.emergency_contact_name} onChange={(e) => set('emergency_contact_name', e.target.value)} />
      </div>
      <div>
        <Label>Contact Phone</Label>
        <Input value={form.emergency_contact_phone} onChange={(e) => set('emergency_contact_phone', e.target.value)} />
      </div>
      <div>
        <Label>Relation</Label>
        <Select value={form.emergency_contact_relation} onValueChange={(v) => set('emergency_contact_relation', v)}>
          <SelectTrigger><SelectValue placeholder="Select Relation" /></SelectTrigger>
          <SelectContent>
            {['Spouse', 'Parent', 'Child', 'Sibling', 'Friend', 'Other'].map((r) => (
              <SelectItem key={r} value={r}>{r}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="col-span-full border-t pt-2 mt-1">
        <Label className="text-sm font-semibold text-gray-700">Address</Label>
      </div>
      <div className="col-span-2">
        <Label>Address Line 1</Label>
        <Input value={form.address_line1} onChange={(e) => set('address_line1', e.target.value)} placeholder="House/Flat No, Street" />
      </div>
      <div className="col-span-2">
        <Label>Address Line 2</Label>
        <Input value={form.address_line2} onChange={(e) => set('address_line2', e.target.value)} placeholder="Area, Landmark" />
      </div>
      <div>
        <Label>Village / Town</Label>
        <Input value={form.village} onChange={(e) => set('village', e.target.value)} />
      </div>
      <div>
        <Label>Mandal / Taluka</Label>
        <Input value={form.mandal} onChange={(e) => set('mandal', e.target.value)} />
      </div>
      <div>
        <Label>District</Label>
        <Input value={form.district} onChange={(e) => set('district', e.target.value)} />
      </div>
    </FormNavContainer>
  );
}

export function buildPatientPayload(form) {
  const { age, age_months: ageMonths } = parseAgeFields(form);
  return Object.fromEntries(
    Object.entries({
      ...form,
      age,
      age_months: ageMonths,
      date_of_birth: form.date_of_birth || null,
    }).map(([k, v]) => [k, v === '' ? null : v])
  );
}

export function validatePatientForm(form) {
  if (!form.first_name?.trim() || !form.last_name?.trim() || !form.primary_phone?.trim()) {
    return 'First name, last name, and phone are required.';
  }
  if (!hasValidAge(form)) {
    return 'Age or date of birth is required.';
  }
  return null;
}

export { computeAgeFromDob, formatPatientAge };
