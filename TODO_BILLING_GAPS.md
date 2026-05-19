# Billing Module — Gap Closure Plan

Scope: close the gaps surfaced in the billing audit (pharmacy excluded).
Workflow per item: **(1) verify backend exists & test → (2) build/extend backend → (3) build frontend → (4) smoke**.

Legend: `[B]` backend, `[F]` frontend, `[T]` test, `[D]` done.

---

## Phase 1 — Admission cancellation in unified Billing UI ✅
Backend: `POST /api/inpatient/admissions/{id}/bills/{bill_id}/cancel`, blocks if payments recorded, releases source items.

- [x] [T] Inpatient suite 188 passed (covers `test_cancel_bill_releases_source_items_and_allows_refinalize`)
- [x] [F] `BillingModule.js`: cancel button now shown for admission bills (when not cancelled); handler branches by type
- [x] [F] `BillingDashboard.js`: same wiring
- [x] [F] `bill_has_payments` 409 surfaced with friendly message + amount paid

## Phase 2 — Refund / payment reversal ✅

- [x] [B] Added `Payment.parent_payment_id`, `reversed_by_id`, `reversed_at`, `reversal_reason` (model + migration NEW_COLUMNS)
- [x] [B] `POST /api/hospital/billing/payments/{payment_id}/refund` — creates negative Payment row, recomputes bill status (pending/partial/paid), audit-logs; supports partial via `amount` field, full by omission
- [x] [B] Blocks refunding a refund row, overshoot rejected, already-fully-refunded rejected
- [x] [B] `generate_refund_receipt_pdf` added in `pdf_service.py`; route `GET /api/hospital/billing/payments/{id}/refund-receipt/pdf` with header toggle
- [x] [B] Bill detail endpoint now flags `is_refund`, `reversed_at`, `parent_payment_id` per payment row
- [x] [T] `tests/test_billing_refunds.py` — 8 tests (full refund → pending, partial → partial, overshoot reject, double-refund reject, refund-of-refund reject, split-then-final, PDF, detail flagging)
- [x] [F] Refund button per non-refund payment in detail dialog; refund rows shown in red with PDF link; original payments marked "Reversed" when fully refunded

## Phase 3 — Insurance / TPA split bills UI ✅

- [x] [T] Existing backend `test_split_interim_bill` / `test_split_mismatched_total_rejected` pass in the full inpatient suite
- [x] [F] Admission bill detail dialog now loads + renders Bill Splits section (loads `/api/inpatient/bills/{id}/split` and `/api/inpatient/tpa`)
- [x] [F] Editor: multi-row, payer_type (cash/insurance/tpa) + payer_name + TPA dropdown + amount, with live "Allocated vs Total" footer and pre-save sum validation
- [x] [F] Per-split "Mark Received" action prompts for reference and `PATCH`es `/bill-splits/{id}/payment`
- [x] [F] Status badge (received/pending) on each split row

## Phase 4 — Consolidated bill ✅
Wrote fresh focused endpoints (existing `BillingService.create_consolidated_bill` was too broad — pulled ALL completed items ever). Marking source rows `payment_status='consolidated'` prevents double-billing without schema changes.

- [x] [B] `GET /api/hospital/billing/consolidate/preview?patient_id=X` — pending appointments + lab orders with totals
- [x] [B] `POST /api/hospital/billing/consolidate` — creates Bill (`bill_type='consolidated'`, `CB-YYYYMMDD-NNNN`) from selected consultation+lab order IDs; flips source `payment_status='consolidated'`; audit-logged
- [x] [B] Billing list (`GET /billing`) now includes consolidated bills
- [x] [T] `tests/test_billing_consolidate.py` — 5 tests (preview, create+sources marked, empty rejected, list inclusion, already-consolidated skip)
- [x] [F] "Consolidate Bills" button in Billing header; dialog with patient search → preview list with checkboxes per consultation/lab → live total → create → opens bill detail dialog

## Phase 5 — Discount & Tax at point-of-bill ✅

- [x] [B] `PATCH /api/hospital/billing/bills/{id}/discount` and `.../tax` — admin-only, audit-logged with reason, blocks cancelled / paid / partially-paid bills
- [x] [T] `tests/test_billing_adjustments.py` — 7 tests cover %-discount, flat discount, tax-after-discount (₹1062), exceed-subtotal rejection, missing fields, cancelled-bill block, payments-recorded block
- [x] [F] Discount / Tax buttons in admission bill detail dialog; dialog supports % or flat amount, reason min-length validation; refetches detail + list after save
- [x] [F] Existing detail dialog already renders discount_amount / tax_amount lines

## Phase 6 — Credit Notes / Adjustments ✅
Modelled as Bill row with `bill_type='credit_note'`, negative total, `parent_bill_id` pointing to original. Auto-creates an offsetting Payment on the parent (method `credit_note`) so balance/status recompute through existing plumbing.

- [x] [B] Migration: `bills.parent_bill_id` added; model accepts `credit_note` bill_type
- [x] [B] `POST /api/hospital/billing/bills/{id}/credit-note` — items[] + reason; creates negative-total Bill + offsetting Payment, recomputes parent status; rejects overshoot, CN-on-CN, cancelled-bill
- [x] [B] PDF: `generate_credit_note_pdf` with red "CREDIT NOTE" header, line items, parent bill ref
- [x] [B] `GET /billing/bills/{id}/credit-note/pdf` with header toggle
- [x] [T] `tests/test_billing_credit_notes.py` — 7 tests (₹1000→₹200 CN→balance 800/partial; full CN→paid; overshoot reject; cumulative; CN-on-CN reject; cancelled-bill reject; PDF)
- [x] [F] "Issue Credit Note" button in bill detail (when balance_due > 0); dialog has multi-line item picker with auto-total, reason; confirms then opens PDF

## Phase 7 — Reports ✅

- [x] [B] `GET /api/hospital/billing/reports/daily-collection?date_from=&date_to=` — grouped by date + payment method; nets refunds; reports gross + net + refunds totals
- [x] [B] `GET /api/hospital/billing/reports/doctor-revenue?date_from=&date_to=` — per-doctor consultation + admission revenue; excludes cancelled
- [x] [B] `GET /api/hospital/billing/reports/tax-summary?date_from=&date_to=` — per-day taxable_value + tax_amount; excludes cancelled bills + credit notes
- [x] [B] All three are admin-only (403 for non-admins)
- [x] [T] `tests/test_billing_reports.py` — 5 tests (daily by method, refund netting, doctor consultations, tax exclusions, admin gate)
- [x] [F] New "Reports" tab in BillingModule with report dropdown, date range, Run + CSV export, three table views with totals row
- [ ] [F] PDF export deferred — CSV covers the immediate need; can wire `printPdf.js` later if requested

---

## Cross-cutting
- All new write endpoints: `log_action(...)` for audit
- All new PDFs: `include_header` toggle parity
- Add to `backend/CLAUDE.md` and update memory file after Phase 7 lands
- New permission keys (`refund_payment`, `apply_discount`, `apply_tax`, `issue_credit_note`, `view_billing_reports`) — wire into role defaults matrix

## Suggested execution order
1 → 5 → 2 → 6 → 3 → 4 → 7 (smallest UI-only first, then refund chain which credit notes depend on, then bigger features, reports last).
