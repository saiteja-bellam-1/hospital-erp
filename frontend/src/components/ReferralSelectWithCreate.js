import React from 'react';
import { Label } from './ui/label';
import { Input } from './ui/input';

/**
 * Free-text "Referred By" field.
 * Previously a referral dropdown backed by /api/referrals (removed with OPD).
 * Kept as a drop-in so PatientRegisterFormFields and edit forms keep working.
 *
 * @param {string} value
 * @param {(name: string) => void} onValueChange
 * @param {string} [label]
 * @param {string} [className]
 */
export default function ReferralSelectWithCreate({
  value = '',
  onValueChange,
  label = 'Referred By',
  className = '',
  // Accept legacy props so call sites do not break
  referrals: _referrals,
  onReferralsChange: _onReferralsChange,
}) {
  return (
    <div className={className}>
      <Label>{label}</Label>
      <Input
        className="mt-1"
        value={value || ''}
        onChange={(e) => onValueChange?.(e.target.value)}
        placeholder="Doctor / clinic / agent (optional)"
      />
    </div>
  );
}
