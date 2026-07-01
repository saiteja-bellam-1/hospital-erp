/** Tablet/strip pricing for pharmacy POS — MRP & rates are per strip; tab = strip / tablets_per_strip. */

/** Round currency to 2 decimal places. */
export function roundMoney(value) {
  const n = parseFloat(value);
  if (!Number.isFinite(n)) return 0;
  return Math.round(n * 100) / 100;
}

/** Format a currency amount for display (2dp). */
export function formatMoney(value) {
  return roundMoney(value).toFixed(2);
}

export function unitsPerStrip(medicine) {
  return Math.max(1, parseInt(medicine?.strip_conversion_factor, 10) || 1);
}

export function supportsStripSale(medicine) {
  return unitsPerStrip(medicine) > 1;
}

/** Strip/sheet sale rate (Rate A/B, then MRP). */
export function stripSaleRate(medicine, tier = 'A') {
  let raw = tier === 'B'
    ? (medicine.rate_b || 0)
    : (medicine.rate_a || medicine.unit_price || 0);
  if (!raw || raw <= 0) raw = medicine.mrp || 0;
  if (!raw || raw <= 0) raw = medicine.unit_price || 0;
  return roundMoney(raw);
}

/** Per-tab price = strip rate ÷ tablets per strip. */
export function tabSaleRate(medicine, tier = 'A', stripRate = null) {
  const sr = stripRate != null && stripRate > 0 ? stripRate : stripSaleRate(medicine, tier);
  if (!sr) return 0;
  return roundMoney(sr / unitsPerStrip(medicine));
}

export function combinedBaseQty(qtyTabs, qtyStrips, medicine) {
  return (parseFloat(qtyTabs) || 0) + (parseFloat(qtyStrips) || 0) * unitsPerStrip(medicine);
}

export function calcLineSubtotal(line) {
  const tabs = parseFloat(line.qty_tabs) || 0;
  const strips = parseFloat(line.qty_strips) || 0;
  const tabR = tabSaleRate(line.medicine, line.rate_tier);
  const stripR = stripSaleRate(line.medicine, line.rate_tier);
  const base = tabs * tabR + strips * stripR;
  return roundMoney(base * (1 - (parseFloat(line.discount_pct) || 0) / 100));
}

export function perTabFromMrp(medicine) {
  const mrp = parseFloat(medicine?.mrp) || 0;
  if (!mrp) return 0;
  return mrp / unitsPerStrip(medicine);
}

/** Cost per smallest unit (tab) — same as per-tab sale price from MRP. */
export function costPcsFromMrp(medicine) {
  const v = perTabFromMrp(medicine);
  return v > 0 ? roundMoney(v) : 0;
}

export function formatRatesHint(medicine, tier = 'A') {
  const stripR = stripSaleRate(medicine, tier);
  const tabR = tabSaleRate(medicine, tier, stripR);
  if (!stripR) return 'Set MRP or Rate A';
  if (supportsStripSale(medicine)) {
    return `Tab ₹${tabR.toFixed(2)} · Strip ₹${stripR.toFixed(2)}`;
  }
  return `₹${tabR.toFixed(2)} each`;
}
