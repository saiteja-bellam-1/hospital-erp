# IPD Billing Flow — Complete Fix Plan

## Decisions confirmed by user
1. **Finalize**: add explicit "Finalize & Settle" — after finalize, if balance ≠ 0, show collect/refund dialog.
2. **Discharge**: hard-block when patient overpaid (credit > 0). Operator must issue refund first.
3. **Gate-pass**: hard-block unless every admission bill is `paid`. Override-with-reason kept as escape hatch. Reconcile inside the endpoint so status is fresh.
4. **Generic payment endpoints** (`/billing/bills/{id}/payment`, `/billing/payments/{id}/refund`): call reconcile after for admission bills.

## Backend tasks

- [ ] **B1**: `hospital_admin.py:record_bill_payment` — after setting `bill.status`, if `bill.bill_type=="admission"`, import + call `reconcile_admission_bill_statuses(db, bill.reference_id)`.
- [ ] **B2**: `hospital_admin.py:refund_payment` — same.
- [ ] **B3**: `inpatient.py:issue_gate_pass` — call reconcile first; block if any non-cancelled admission bill is not `paid`, unless `override_balance=true` with `override_reason`.
- [ ] **B4**: `inpatient.py:discharge_patient` — after reconcile, compute `balance = _admission_balance_summary(...)['balance']`. If `balance > 0.01` (credit, patient overpaid), raise 409 with `code: "credit_refund_required"` and the amount.
- [ ] **B5**: `inpatient.py:finalize_bill` response — extend with `balance_due`, `deposit_credit`, `requires_action` ("collect" / "refund" / "none") so frontend can prompt.

## Frontend tasks

- [ ] **F1**: `BillDetailDialog.js` — after finalize, if response has `requires_action != "none"`, open Settle dialog: "Collect ₹X" (→ POST deposit) or "Refund ₹Y" (→ POST refund). Re-fetch detail on success.
- [ ] **F2**: Discharge flow — catch new 409 `credit_refund_required`; show "Refund ₹X before discharge" dialog with refund-method picker → POST refund → retry discharge.
- [ ] **F3**: Gate-pass tab — catch new 409 `outstanding_bill`; show outstanding list + "Settle" CTA or "Override with reason".

## Test scenarios after fixes
1. Deposit ₹20k → finalize ₹14.1k → expect bill auto-paid + Settle dialog shows "Refund ₹5.9k".
2. Deposit ₹5k → finalize ₹14.1k → bill partial, Settle dialog shows "Collect ₹9.1k".
3. Try discharge with credit balance → blocked, refund dialog shows.
4. Try gate-pass with unpaid bill → blocked, must settle or override.
5. Pay via generic /billing/bills/{id}/payment → bill.status correctly reflects deposit+payment pool.
