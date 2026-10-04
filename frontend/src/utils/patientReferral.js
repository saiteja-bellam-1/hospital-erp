/** Referral saved on the patient record. Empty when none has been chosen yet. */
export function patientReferralName(patient) {
  return (patient?.referred_by || '').trim();
}
