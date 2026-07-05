/** HSN / GST helpers — IGST is always CGST + SGST (combined inter-state rate). */

export function computeIgstPct(sgstPct, cgstPct) {
  const sgst = parseFloat(sgstPct) || 0;
  const cgst = parseFloat(cgstPct) || 0;
  return Math.round((sgst + cgst) * 100) / 100;
}

export function hsnTotalTaxPct(hsn) {
  if (!hsn) return 0;
  return (hsn.sgst_pct || 0) + (hsn.cgst_pct || 0);
}

export function formatHsnOption(h) {
  const igst = h.igst_pct ?? computeIgstPct(h.sgst_pct, h.cgst_pct);
  return `${h.code} (SGST ${h.sgst_pct}% + CGST ${h.cgst_pct}% · IGST ${igst}%)`;
}

export function withComputedIgst(form) {
  return { ...form, igst_pct: computeIgstPct(form.sgst_pct, form.cgst_pct) };
}

/**
 * Compute line tax from discounted gross amount.
 * @param {'exclusive'|'inclusive'} taxMode
 * @returns {{ taxable: number, tax: number, total: number }}
 */
export function computeLineTax(grossAfterDiscount, taxPct, taxMode = 'exclusive') {
  const gross = Math.max(0, parseFloat(grossAfterDiscount) || 0);
  const pct = Math.max(0, parseFloat(taxPct) || 0);
  if (pct <= 0) {
    const g = Math.round(gross * 100) / 100;
    return { taxable: g, tax: 0, total: g };
  }
  if (taxMode === 'inclusive') {
    const taxable = Math.round((gross / (1 + pct / 100)) * 100) / 100;
    const tax = Math.round((gross - taxable) * 100) / 100;
    return { taxable, tax, total: Math.round(gross * 100) / 100 };
  }
  const tax = Math.round(gross * pct / 100 * 100) / 100;
  return {
    taxable: Math.round(gross * 100) / 100,
    tax,
    total: Math.round((gross + tax) * 100) / 100,
  };
}

/** Apply a field change; SGST/CGST edits auto-refresh IGST (user can still edit IGST after). */
export function patchHsnForm(form, key, value) {
  const next = { ...form, [key]: value };
  if (key === 'sgst_pct' || key === 'cgst_pct') {
    next.igst_pct = computeIgstPct(next.sgst_pct, next.cgst_pct);
  }
  return next;
}
