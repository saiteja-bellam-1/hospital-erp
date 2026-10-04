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

/**
 * Split a GST rate into equal SGST and CGST. IGST is the full rate.
 * Odd rates (5%) become 2.5 + 2.5; any half-paisa remainder stays on CGST.
 */
export function splitGstPct(gstPct) {
  if (gstPct === '' || gstPct == null) {
    return { gst_pct: '', sgst_pct: '', cgst_pct: '', igst_pct: '' };
  }
  const gst = Math.round((parseFloat(gstPct) || 0) * 100) / 100;
  const sgst = Math.round((gst / 2) * 100) / 100;
  const cgst = Math.round((gst - sgst) * 100) / 100;
  return { gst_pct: gst, sgst_pct: sgst, cgst_pct: cgst, igst_pct: gst };
}

/** Apply a field change. GST % fills SGST, CGST, and IGST. */
export function patchHsnForm(form, key, value) {
  if (key === 'gst_pct') {
    return { ...form, ...splitGstPct(value) };
  }
  const next = { ...form, [key]: value };
  if (key === 'sgst_pct' || key === 'cgst_pct') {
    const combined = computeIgstPct(next.sgst_pct, next.cgst_pct);
    next.igst_pct = combined;
    next.gst_pct = combined;
  }
  return next;
}
