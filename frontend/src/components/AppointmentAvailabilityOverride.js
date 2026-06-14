import React from 'react';
import { Input } from './ui/input';
import { Label } from './ui/label';

/**
 * Shared availability-override block for appointment booking forms.
 * Backend enforces role check; double-booking the same slot is still blocked.
 */
export default function AppointmentAvailabilityOverride({
  overrideAvailability,
  overrideReason,
  onChange,
  className = '',
  reasonId = 'override_reason',
}) {
  const setOverride = (checked) => {
    onChange({
      override_availability: checked,
      override_reason: checked ? overrideReason : '',
    });
  };

  return (
    <div className={`border border-amber-200 bg-amber-50 rounded-md p-3 space-y-2 ${className}`}>
      <label className="flex items-start gap-2 cursor-pointer">
        <input
          type="checkbox"
          className="mt-1"
          checked={!!overrideAvailability}
          onChange={(e) => setOverride(e.target.checked)}
        />
        <div className="text-sm">
          <div className="font-medium text-amber-900">Override doctor availability</div>
          <div className="text-amber-700 text-xs">
            Allows booking outside the doctor&apos;s schedule (leave, off-hours, breaks). Double-booking the same slot is still blocked. The override is audit-logged.
          </div>
        </div>
      </label>
      {overrideAvailability && (
        <div>
          <Label htmlFor={reasonId} className="text-amber-900">Reason for override *</Label>
          <Input
            id={reasonId}
            value={overrideReason || ''}
            onChange={(e) => onChange({ override_reason: e.target.value })}
            placeholder="e.g. emergency walk-in, doctor agreed by phone"
            maxLength={500}
          />
        </div>
      )}
    </div>
  );
}
