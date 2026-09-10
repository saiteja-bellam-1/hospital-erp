/**
 * Build URL + query for the patient file-label PDF endpoint.
 * @param {number|string} patientId - integer PK or UUID patient_id
 * @param {object} [opts]
 * @param {'registration'|'appointment'|'lab'|'reprint'} [opts.source]
 * @param {number} [opts.appointmentId]
 * @param {number} [opts.orderId]
 * @param {string} [opts.paymentMethod]
 * @param {string} [opts.patType]
 * @param {string} [opts.billDate] ISO datetime
 */
export function patientFileLabelPath(patientId, opts = {}) {
  const id = patientId == null ? '' : String(patientId);
  return `/api/patients/${encodeURIComponent(id)}/file-label.pdf`;
}

export function patientFileLabelParams(opts = {}) {
  const params = {};
  if (opts.source) params.source = opts.source;
  if (opts.appointmentId != null) params.appointment_id = opts.appointmentId;
  if (opts.orderId != null) params.order_id = opts.orderId;
  if (opts.paymentMethod) params.payment_method = opts.paymentMethod;
  if (opts.patType) params.pat_type = opts.patType;
  if (opts.billDate) params.bill_date = opts.billDate;
  return params;
}
