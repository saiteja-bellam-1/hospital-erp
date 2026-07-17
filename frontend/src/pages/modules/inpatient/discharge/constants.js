export const PAYMENT_METHODS = [
  { value: 'cash', label: 'Cash' },
  { value: 'card', label: 'Card' },
  { value: 'upi', label: 'UPI' },
  { value: 'cheque', label: 'Cheque' },
  { value: 'online', label: 'Online transfer' },
];

export const CHECKOUT_STEPS = [
  { id: 1, key: 'bill', label: 'Bill & Settle' },
  { id: 2, key: 'summary', label: 'Discharge Summary' },
  { id: 3, key: 'gatepass', label: 'Gate Pass' },
];

export const EMPTY_CLINICAL_FORM = {
  discharge_type: 'normal',
  condition_on_discharge: 'stable',
  diagnosis_on_discharge: '',
  treatment_given: '',
  discharge_summary: '',
  take_home_medications: [],
  follow_up_instructions: '',
  follow_up_date: '',
  diet_instructions: '',
  activity_restrictions: '',
  consent_to_discharge: false,
  dama_advice_ack: false,
  dama_absolves_ack: false,
  signed_by_name: '',
  signed_by_relationship: 'self',
  guardian_relationship: '',
  decl_notes: '',
  override_reason: '',
};

export const EMPTY_SETTLE_FORM = (derived) => {
  const direction = derived?.owes > 0.01 ? 'collect'
    : derived?.owes < -0.01 ? 'refund'
      : 'none';
  return {
    direction,
    amount: direction === 'none' ? '0' : Math.abs(derived?.owes || 0).toFixed(2),
    method: 'cash',
    ref: '',
    notes: '',
    discountType: 'flat',
    discountValue: '',
    taxPct: '',
  };
};

export function computeCheckoutSettlement(derived, form, hasFinalBill = false) {
  if (!derived) return null;
  if (hasFinalBill || !form) {
    const owes = Number(derived.owes || 0);
    return {
      subtotal: Number(derived.stayCharges || 0),
      discountAmount: 0,
      taxAmount: 0,
      adjustedTotal: Number(derived.stayCharges || 0),
      owes,
      direction: owes > 0.01 ? 'collect' : owes < -0.01 ? 'refund' : 'none',
      amount: Math.abs(owes),
    };
  }

  const subtotal = Number(derived.stayCharges || 0);
  const discountValue = Math.max(0, Number(form.discountValue || 0));
  const discountAmount = form.discountType === 'percentage'
    ? Math.min(subtotal, subtotal * Math.min(discountValue, 100) / 100)
    : Math.min(subtotal, discountValue);
  const afterDiscount = Math.max(0, subtotal - discountAmount);
  const taxAmount = afterDiscount * Math.min(Math.max(Number(form.taxPct || 0), 0), 100) / 100;
  const adjustedTotal = +(afterDiscount + taxAmount).toFixed(2);
  const owes = +(adjustedTotal - Number(derived.deposited || 0)).toFixed(2);

  return {
    subtotal,
    discountAmount: +discountAmount.toFixed(2),
    taxAmount: +taxAmount.toFixed(2),
    adjustedTotal,
    owes,
    direction: owes > 0.01 ? 'collect' : owes < -0.01 ? 'refund' : 'none',
    amount: Math.abs(owes),
  };
}

export const EMPTY_GATE_PASS_FORM = {
  attendant_name: '',
  attendant_relationship: '',
  vehicle_no: '',
  notes: '',
  overrideReason: '',
  overrideErr: null,
};

export const rupee = (n) => `₹${Number(n || 0).toFixed(2)}`;

export const DISCHARGE_SUMMARY_STATUS = {
  missing: { label: 'Not started', listLabel: 'No summary', className: 'bg-gray-100 text-gray-700' },
  draft: { label: 'Draft', listLabel: 'Summary draft', className: 'bg-amber-100 text-amber-800' },
  ready: { label: 'Ready to print', listLabel: 'Summary ready', className: 'bg-green-100 text-green-800' },
  locked: { label: 'Locked', listLabel: 'Summary locked', className: 'bg-slate-100 text-slate-700' },
};

export const fmtInr = (n) => `₹${(Number(n) || 0).toLocaleString('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})}`;

export function computeDerived(bill, balance, admission, finalBill = null) {
  if (!bill || !balance) return null;
  const computed = Number(bill.grand_total ?? bill.subtotal ?? 0);
  const billed = Number(balance.total_billed ?? 0);
  const deposited = Number(balance.net_deposits ?? 0);
  // A final bill is authoritative because it includes locked discounts/tax.
  // The live charge preview remains pre-discount and must not replace it.
  const stayCharges = finalBill
    ? Number(finalBill.total_amount ?? billed)
    : Math.max(computed, billed);
  const owes = +(stayCharges - deposited).toFixed(2);
  const isDischarged = admission?.status === 'discharged';
  return { stayCharges, billed, deposited, owes, isDischarged };
}

/** Pick the first incomplete step based on server state. */
export function resolveStartStep({ admission, finalBill, gatePass, derived }) {
  if (!admission || !derived) return 1;
  if (gatePass) return 3;
  if (derived.isDischarged) return 3;
  if (finalBill) return 2;
  return 1;
}

export function draftStorageKey(admissionId) {
  return `discharge_checkout_draft_${admissionId}`;
}
