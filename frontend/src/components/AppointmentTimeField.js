import React from 'react';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

/**
 * Doctor time picker: slot dropdown when slots exist, free time input when override is on or no slots.
 */
export default function AppointmentTimeField({
  label = 'Time *',
  timeId = 'appointment_time',
  appointmentTime,
  overrideAvailability,
  availableSlots = [],
  availabilityChecking = false,
  doctorId,
  appointmentDate,
  onTimeChange,
}) {
  const useSlotSelect = !overrideAvailability && availableSlots.length > 0;

  return (
    <div>
      <Label htmlFor={timeId}>{label}</Label>
      {useSlotSelect ? (
        <Select value={appointmentTime} onValueChange={onTimeChange}>
          <SelectTrigger id={timeId}>
            <SelectValue placeholder="Select available time" />
          </SelectTrigger>
          <SelectContent>
            {availabilityChecking ? (
              <SelectItem value="loading" disabled>Loading available times...</SelectItem>
            ) : (
              availableSlots.map((slot, index) => (
                <SelectItem key={index} value={slot.start_time}>
                  {slot.start_time} – {slot.end_time}
                  {slot.duration ? ` (${slot.duration} min)` : ''}
                </SelectItem>
              ))
            )}
          </SelectContent>
        </Select>
      ) : (
        <Input
          id={timeId}
          type="time"
          value={appointmentTime}
          onChange={(e) => onTimeChange(e.target.value)}
          required
          placeholder={overrideAvailability ? 'Enter time (any)' : 'Select doctor and date first'}
        />
      )}
      {availabilityChecking && !overrideAvailability && (
        <p className="text-sm text-blue-600 mt-1">Checking availability...</p>
      )}
      {!overrideAvailability && doctorId && appointmentDate && availableSlots.length === 0 && !availabilityChecking && (
        <p className="text-sm text-red-600 mt-1">No available slots for selected date</p>
      )}
    </div>
  );
}
