/** tel: href for a license support phone number. */
export function phoneTel(phone) {
  const compact = String(phone || '').replace(/[^\d+]/g, '');
  return compact ? `tel:${compact}` : '';
}
