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
  if (!form?.doctor_id || !form?.appointment_date) {
    return 'Doctor and date are required.';
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
    || needsOverrideReason(form)
  );
}

/** Normalize form fields for POST /api/appointments/ — empty time becomes null. */
export function buildAppointmentCreatePayload(form, { patient_id } = {}) {
  const { payment, ...rest } = form || {};
  const payload = { ...rest };
  // `payment` comes from <PaymentCollectionFields>: full / partial / pay later.
  if (payment) {
    const mode = payment.mode || 'full';
    payload.payment_method = payment.method || payload.payment_method || 'cash';
    if (payment.reference) payload.payment_reference = payment.reference;
    if (mode === 'later') {
      payload.payment_status = 'pending';
      payload.amount_paid = 0;
    } else if (mode === 'partial') {
      payload.payment_status = 'partial';
      payload.amount_paid = Math.round((Number(payment.amount) || 0) * 100) / 100;
    } else {
      payload.payment_status = 'paid';
      delete payload.amount_paid;
    }
  }
  if (patient_id) payload.patient_id = patient_id;
  if (!payload.appointment_time) {
    payload.appointment_time = null;
  }
  return payload;
}

export function shouldShowAppointmentBill(appointment) {
  return (appointment?.consultation_fee > 0) || (appointment?.registration_fee > 0);
}
