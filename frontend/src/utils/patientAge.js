/** Shared patient age helpers — mirrors backend/app/utils/patient_age.py */

export function computeAgeFromDob(dobStr) {
  if (!dobStr) return { years: '', months: '' };
  const today = new Date();
  const birth = new Date(`${dobStr}T00:00:00`);
  let totalMonths = (today.getFullYear() - birth.getFullYear()) * 12
    + (today.getMonth() - birth.getMonth());
  if (today.getDate() < birth.getDate()) totalMonths -= 1;
  if (totalMonths < 0) totalMonths = 0;
  return {
    years: String(Math.floor(totalMonths / 12)),
    months: String(totalMonths % 12),
  };
}

export function formatAgeParts({ years, months, totalMonths } = {}) {
  if (totalMonths == null) {
    const y = Number(years) || 0;
    const m = Number(months) || 0;
    if (years == null && months == null) return '';
    totalMonths = y * 12 + m;
  }
  if (totalMonths <= 0) return '';
  if (totalMonths < 24) {
    return `${totalMonths} Month${totalMonths === 1 ? '' : 's'}`;
  }
  const y = Math.floor(totalMonths / 12);
  const m = totalMonths % 12;
  if (m === 0) return `${y} Year${y === 1 ? '' : 's'}`;
  return `${y} Year${y === 1 ? '' : 's'} ${m} Month${m === 1 ? '' : 's'}`;
}

export function formatPatientAge(patient) {
  if (!patient) return '';
  if (patient.date_of_birth) {
    const { years, months } = computeAgeFromDob(patient.date_of_birth);
    return formatAgeParts({ years, months });
  }
  if (patient.age != null || patient.age_months != null) {
    return formatAgeParts({
      years: patient.age ?? 0,
      months: patient.age_months ?? 0,
    });
  }
  return '';
}

export function hasValidAge(form) {
  if (form.date_of_birth) return true;
  const years = form.age === '' || form.age == null ? null : parseInt(form.age, 10);
  const months = form.age_months === '' || form.age_months == null
    ? null
    : parseInt(form.age_months, 10);
  if (years != null && !Number.isNaN(years) && years > 0) return true;
  if (months != null && !Number.isNaN(months) && months > 0) return true;
  return false;
}

export function applyDobToForm(form, dob) {
  const updates = { date_of_birth: dob };
  if (dob) {
    const { years, months } = computeAgeFromDob(dob);
    updates.age = years;
    updates.age_months = months;
  }
  return { ...form, ...updates };
}

export function parseAgeFields(form) {
  const age = form.age === '' || form.age == null ? null : parseInt(form.age, 10);
  const ageMonths = form.age_months === '' || form.age_months == null
    ? null
    : parseInt(form.age_months, 10);
  return { age, age_months: ageMonths };
}
