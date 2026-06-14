/** Best-effort prefill for quick-register from a search box query. */
export function guessPatientFieldsFromQuery(query) {
  const trimmed = (query || '').trim();
  if (!trimmed) return {};

  const digits = trimmed.replace(/\D/g, '');
  const compact = trimmed.replace(/\s/g, '');
  if (digits.length >= 6 && digits.length / Math.max(compact.length, 1) >= 0.6) {
    const phone = digits.length >= 10 ? digits.slice(-10) : digits;
    return { primary_phone: phone };
  }

  const parts = trimmed.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return { first_name: parts[0] };
  return { first_name: parts[0], last_name: parts.slice(1).join(' ') };
}
