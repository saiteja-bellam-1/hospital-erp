export const APPOINTMENT_OVERRIDE_DEFAULTS = {
  override_availability: false,
  override_reason: '',
};

export function needsOverrideReason(form) {
  return !!form?.override_availability && !(form?.override_reason || '').trim();
}

export function validateAppointmentBooking(form, { selectedPatient = true } = {}) {
  if (!selectedPatient) {
    return 'Select a patient first.';
  }
  if (!form?.doctor_id || !form?.appointment_date || !form?.appointment_time) {
    return 'Doctor, date, and time are required.';
  }
  if (needsOverrideReason(form)) {
    return 'Please provide a reason for overriding doctor availability.';
  }
  return null;
}

export function isAppointmentSubmitDisabled(form, { loading = false, selectedPatient = true } = {}) {
  return (
    loading
    || !selectedPatient
    || !form?.doctor_id
    || !form?.appointment_date
    || !form?.appointment_time
    || needsOverrideReason(form)
  );
}
