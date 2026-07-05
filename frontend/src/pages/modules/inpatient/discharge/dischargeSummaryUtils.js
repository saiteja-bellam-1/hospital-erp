import axios from 'axios';

/** Attach discharge-summary status to each admission (404 → missing). */
export async function enrichAdmissionsWithSummaryStatus(admissions = []) {
  if (!admissions.length) return [];
  return Promise.all(admissions.map(async (adm) => {
    try {
      const res = await axios.get(`/api/inpatient/admissions/${adm.id}/discharge-summary`);
      return { ...adm, summaryStatus: res.data.status };
    } catch (err) {
      if (err.response?.status === 404) {
        return { ...adm, summaryStatus: 'missing' };
      }
      return { ...adm, summaryStatus: null };
    }
  }));
}

/** Reception checkout — bill finalize, discharge event, gate pass. Not the doctor summary editor. */
export function canAccessDischargeCheckout({ isAdminLike, hasCheckoutDeskRole, hasPerm }) {
  if (isAdminLike || hasCheckoutDeskRole) return true;
  return !!(hasPerm('finalize_bill') || hasPerm('issue_gate_pass'));
}
