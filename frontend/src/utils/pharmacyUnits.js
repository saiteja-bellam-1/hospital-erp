/** Tablet/strip pricing for pharmacy POS — MRP & rates are per strip; tab = strip / tablets_per_strip.

 * When a sale/purchase line has a selected batch, batch MRP / Rate A / P-Rate /
 * qty-per-strip override the medicine master (zero/missing batch fields fall back).
 */

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

/** Effective pricing source: batch fields win when set, else medicine master. */
export function pricingSource(medicine, batch = null) {
  const med = medicine || {};
  const b = batch || {};
  const batchRateA = parseFloat(b.rate_a) || 0;
  const batchMrp = parseFloat(b.mrp) || 0;
  const batchPr = parseFloat(b.purchase_rate) || 0;
  const batchScf = parseInt(b.strip_conversion_factor, 10) || 0;
  return {
    rate_a: batchRateA > 0 ? batchRateA : (parseFloat(med.rate_a) || 0),
    rate_b: parseFloat(med.rate_b) || 0,
    mrp: batchMrp > 0 ? batchMrp : (parseFloat(med.mrp) || 0),
    purchase_rate: batchPr > 0 ? batchPr : (parseFloat(med.purchase_rate) || 0),
    unit_price: parseFloat(med.unit_price) || 0,
    strip_conversion_factor: batchScf > 0
      ? batchScf
      : Math.max(1, parseInt(med.strip_conversion_factor, 10) || 1),
  };
}

/** Resolve pricing for a cart line (uses line.batch when present). */
export function linePricingSource(line) {
  return pricingSource(line?.medicine, line?.batch || null);
}

export function unitsPerStrip(source) {
  return Math.max(1, parseInt(source?.strip_conversion_factor, 10) || 1);
}

export function supportsStripSale(source) {
  return unitsPerStrip(source) > 1;
}

/** Strip/sheet sale rate (Rate A/B, then MRP). */
export function stripSaleRate(source, tier = 'A') {
  const src = source || {};
  let raw = tier === 'B'
    ? (src.rate_b || 0)
    : (src.rate_a || src.unit_price || 0);
  if (!raw || raw <= 0) raw = src.mrp || 0;
  if (!raw || raw <= 0) raw = src.unit_price || 0;
  return roundMoney(raw);
}

/** Per-tab price = strip rate ÷ tablets per strip. */
export function tabSaleRate(source, tier = 'A', stripRate = null) {
  const src = source || {};
  const sr = stripRate != null && stripRate > 0 ? stripRate : stripSaleRate(src, tier);
  if (!sr) return 0;
  return roundMoney(sr / unitsPerStrip(src));
}

export function combinedBaseQty(qtyTabs, qtyStrips, source) {
  return (parseFloat(qtyTabs) || 0) + (parseFloat(qtyStrips) || 0) * unitsPerStrip(source);
}

export function calcLineSubtotal(line) {
  const tabs = parseFloat(line.qty_tabs) || 0;
  const strips = parseFloat(line.qty_strips) || 0;
  const src = linePricingSource(line);
  const tabR = tabSaleRate(src, line.rate_tier);
  const stripR = stripSaleRate(src, line.rate_tier);
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

export function formatRatesHint(source, tier = 'A', batch = null) {
  const effectiveBatch = batch || source?.batch || null;
  const src = effectiveBatch
    ? pricingSource(source?.medicine || source, effectiveBatch)
    : (source || {});
  const stripR = stripSaleRate(src, tier);
  const tabR = tabSaleRate(src, tier, stripR);
  if (!stripR) return 'Set MRP or Rate A';
  if (supportsStripSale(src)) {
    return `Tab ₹${tabR.toFixed(2)} · Strip ₹${stripR.toFixed(2)}`;
  }
  return `₹${tabR.toFixed(2)} each`;
}

export function formatBatchLabel(batch) {
  if (!batch) return '';
  const parts = [batch.batch_number || '—'];
  if (batch.expiry_date) {
    const d = new Date(`${batch.expiry_date}T12:00:00`);
    if (!Number.isNaN(d.getTime())) {
      parts.push(`exp ${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`);
    }
  }
  parts.push(`qty ${batch.quantity_in_stock ?? 0}`);
  const rateA = parseFloat(batch.rate_a) || parseFloat(batch.mrp) || 0;
  if (rateA > 0) parts.push(`A ₹${formatMoney(rateA)}`);
  const scf = parseInt(batch.strip_conversion_factor, 10) || 0;
  if (scf > 1) parts.push(`${scf}/strip`);
  return parts.join(' · ');
}
