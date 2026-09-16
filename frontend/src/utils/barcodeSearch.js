/**
 * Shared helpers so patient / lab search boxes accept wedge-scanner barcodes.
 */

/** Digits only from scanner or typed input. */
export function barcodeDigits(raw) {
  return String(raw || '').replace(/\D/g, '');
}

/** Likely a full barcode scan (≥12 digits). */
export function isLikelyBarcodeQuery(raw) {
  return barcodeDigits(raw).length >= 12;
}

/**
 * True if any haystack field equals/contains the query or its digit payload.
 * Used for client-side filters after the API returns barcode fields.
 */
export function matchesBarcodeHaystacks(haystacks, query) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return true;
  const digits = barcodeDigits(query);
  const values = (haystacks || [])
    .filter((v) => v != null && String(v).trim() !== '')
    .map((v) => String(v).toLowerCase());
  if (values.some((v) => v.includes(q))) return true;
  if (digits.length >= 8) {
    return values.some((v) => {
      const vd = v.replace(/\D/g, '');
      return vd && (vd === digits || vd.includes(digits) || digits.includes(vd));
    });
  }
  return false;
}

/** Lab order / report row match including sample + patient barcodes. */
export function matchesLabOrderSearch(order, query) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return true;
  if (
    order.patient_name?.toLowerCase().includes(q) ||
    order.test_name?.toLowerCase().includes(q) ||
    order.test_code?.toLowerCase().includes(q) ||
    order.order_number?.toLowerCase().includes(q) ||
    order.doctor_name?.toLowerCase().includes(q) ||
    order.package_name?.toLowerCase().includes(q) ||
    order.sample_id?.toLowerCase().includes(q) ||
    order.patient_mrn?.toLowerCase().includes(q)
  ) {
    return true;
  }
  return matchesBarcodeHaystacks(
    [order.sample_ean13, order.patient_mrn_ean13, order.sample_id, order.patient_mrn],
    query,
  );
}
