export const PAYMENT_METHODS = [
  { value: 'cash', label: 'Cash' },
  { value: 'card', label: 'Card' },
  { value: 'upi', label: 'UPI' },
  { value: 'cheque', label: 'Cheque' },
  { value: 'online', label: 'Online transfer' },
];

export const CHECKOUT_STEPS = [
  { id: 1, key: 'bill', label: 'Bill & Settle' },
  { id: 2, key: 'clinical', label: 'Clinical' },
  { id: 3, key: 'takehome', label: 'Take-home Rx' },
  { id: 4, key: 'confirm', label: 'Confirm' },
  { id: 5, key: 'gatepass', label: 'Gate Pass' },
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
    discountValue: '0',
    taxPct: '0',
  };
};

export const EMPTY_GATE_PASS_FORM = {
  attendant_name: '',
  attendant_relationship: '',
  vehicle_no: '',
  notes: '',
  overrideReason: '',
  overrideErr: null,
};

export const rupee = (n) => `₹${Number(n || 0).toFixed(2)}`;

export const fmtInr = (n) => `₹${(Number(n) || 0).toLocaleString('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})}`;

export function computeDerived(bill, balance, admission) {
  if (!bill || !balance) return null;
  const computed = Number(bill.grand_total ?? bill.subtotal ?? 0);
  const billed = Number(balance.total_billed ?? 0);
  const deposited = Number(balance.net_deposits ?? 0);
  const stayCharges = Math.max(computed, billed);
  const owes = +(stayCharges - deposited).toFixed(2);
  const isDischarged = admission?.status === 'discharged';
  return { stayCharges, billed, deposited, owes, isDischarged };
}

/** Pick the first incomplete step based on server state. */
export function resolveStartStep({ admission, finalBill, gatePass, derived }) {
  if (!admission || !derived) return 1;
  if (gatePass) return 5;
  if (derived.isDischarged) return 5;
  if (finalBill) return 2;
  return 1;
}

export function draftStorageKey(admissionId) {
  return `discharge_checkout_draft_${admissionId}`;
}
