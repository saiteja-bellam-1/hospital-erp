/** Price of a lab test on a selected rate card. Falls back to Rate A (`cost`). */
export function testPrice(test, rateCardId) {
  const rates = test?.rates || [];
  if (rateCardId != null && rateCardId !== '') {
    const hit = rates.find((r) => String(r.rate_card_id) === String(rateCardId));
    if (hit) return Number(hit.amount) || 0;
  }
  const fallback = rates.find((r) => r.is_default) || rates.find((r) => r.code === 'A');
  if (fallback) return Number(fallback.amount) || 0;
  return Number(test?.cost) || 0;
}

export function defaultRateCardId(cards) {
  if (!cards?.length) return '';
  const preferred = cards.find((c) => c.is_default) || cards[0];
  return String(preferred.id);
}
