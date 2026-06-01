# TODO — Pharmacy Module Gaps & Roadmap

Audit date: 2026-06-01
Source audit: see chat session 2026-06-01 (PM review of `backend/app/routes/pharmacy.py` + `frontend/src/pages/modules/pharmacy/`).

Legend: `[ ]` not started · `[~]` in progress · `[x]` done · `(B)` backend · `(F)` frontend · `(D)` DB/migration · `(T)` tests

---

## P0 — Correctness bugs (ship first)

### 1. Rx void/cancel → Inpatient bill auto-reversal
Today an Rx tied to an admission can be voided/cancelled and the IP bill line stays. Code already flags this as deferred (`pharmacy.py:2030-2033`, `3083-3088`, "P3.6 caveat").

- [ ] (B) On `void_sale` for an Rx-linked sale, reverse the matching `InpatientBill` line via service-layer helper
- [ ] (B) On the new Rx-cancel endpoint (task 4), reverse partial dispenses too
- [ ] (B) Add `inpatient_bill_line_id` FK on `PharmacySaleItem` so reversal is O(1)
- [ ] (D) Migration to backfill the FK where deducible
- [ ] (T) Test: dispense → void → IP bill line zeroed + ledger entry written
- [ ] (T) Test: partial dispense → cancel Rx → only dispensed qty reversed

### 2. Expiry tracking restored (FEFO + alerts)
Column is NOT NULL, UI was removed, sentinel `2099-12-31` is being inserted (`pharmacy.py:985-1000`).

- [ ] (F) Re-add expiry input on purchase grid (MM/YYYY accepted, stored as last-day-of-month)
- [ ] (B) Switch dispensing/sale picker from insertion-order FIFO to FEFO (`ORDER BY expiry_date, id`)
- [ ] (B) New endpoint: `GET /api/pharmacy/inventory/expiring?days=90`
- [ ] (B) New endpoint: `POST /api/pharmacy/inventory/expire-writeoff` (auth: `adjust_stock`, writes ledger txn_type=`expiry_writeoff`)
- [ ] (F) "Expiring Soon" tile on Pharmacy dashboard + dedicated report
- [ ] (T) FEFO ordering test; expiry write-off ledger test

### 3. Supplier payments (close out P4.2 stub)
Aging report currently treats every credit purchase as 100% outstanding (`pharmacy.py:2841-2890`).

- [ ] (D) New table `PharmacySupplierPayment` (id, supplier_id, amount, mode, reference, paid_on, notes, allocations JSON)
- [ ] (D) New table `PharmacySupplierPaymentAllocation` (payment_id, purchase_id, amount) — many-to-many
- [ ] (B) `POST/GET/DELETE /api/pharmacy/supplier-payments`
- [ ] (B) Rewrite `report_supplier_aging` to subtract allocated amounts
- [ ] (F) Supplier ledger page (Payables tab) — outstanding by supplier, "Record Payment" dialog with auto-allocate FIFO
- [ ] (T) Payment partial allocation + aging recompute test

### 4. Rx cancellation endpoint
Status stuck at `pending` with no transition to `cancelled` (`pharmacy.py:2181-2285`).

- [ ] (B) `POST /api/pharmacy/prescriptions/{id}/cancel` (reason required)
- [ ] (B) Reverse any partial dispense via FIFO unwind + ledger `rx_cancel`
- [ ] (B) Block cancel if fully dispensed > void window
- [ ] (F) "Cancel Rx" button in PendingRxTab + Doctor's Rx history (with reason dialog)
- [ ] (T) cancel-pending, cancel-partial, cancel-blocked-after-window

---

## P0 — Correctness bugs (ship first)

### 5. Financial-year-scoped invoice numbering + Pharmacy Config page
Today invoice numbers increment globally forever. India-standard requirement: counter resets to `0001` at the start of each financial year, with FY tag in the number for audit/GST trails.

**Config (Hospital Admin → Pharmacy Config page — new)**
- [ ] (F) New page `frontend/src/pages/modules/HospitalAdminModule.js` → "Pharmacy Config" tab
- [ ] (D) New table `PharmacyConfig` (id, hospital_id, fy_start_month [1-12, default 4], number_format_sale, number_format_dispense, number_format_return, number_format_purchase, enabled bool, created_at, updated_at)
- [ ] (B) `GET /api/pharmacy/config` and `PUT /api/pharmacy/config` (auth: `hospital_admin` or pharmacy `manage_config` permission)
- [ ] (F) Form fields:
  - FY start month dropdown (Jan–Dec, default April)
  - Per-document prefix template inputs with token help: `{FY}`, `{FY_SHORT}`, `{FY_RANGE}`, `{NUM}`, `{NUM:4}`, `{HOSPITAL}` (e.g. `PH/{FY_SHORT}/{NUM:4}` → `PH/26/0001`)
  - Live preview of next number for each doc type
  - "Apply from next FY" vs "Apply immediately" toggle (default: from next FY rollover; immediate mode starts fresh counter today)

**Numbering engine**
- [ ] (D) New table `PharmacyInvoiceCounter` (id, hospital_id, doc_type ['sale','dispense','return','purchase'], fy_year_start [int, e.g. 2026 for FY26-27], last_number int, UNIQUE(hospital_id, doc_type, fy_year_start))
- [ ] (B) New util `app/utils/pharmacy_numbering.py` with `next_invoice_number(db, hospital_id, doc_type, dt)`:
  - Computes FY for `dt` using configured `fy_start_month`
  - Atomically increments counter (row-level lock or `UPDATE ... RETURNING`)
  - Formats via configured template
- [ ] (B) Replace existing invoice-number generation in:
  - POS sales (`pharmacy.py` create-sale around line ~1693-1713)
  - Rx dispense slip numbering
  - Sale return (task #5 below) — wire from day one
  - Internal purchase number (not supplier invoice no — that stays as-typed)
- [ ] (B) Race-safe under concurrency: use existing pattern from current numbering (advisory lock / IntegrityError retry)

**Forward-only migration**
- [ ] (D) Migration seeds `PharmacyConfig` with defaults (April start, plain `{NUM:4}` format)
- [ ] (D) Migration seeds `PharmacyInvoiceCounter` with the **current max number** per doc_type under the current FY so existing invoices stay untouched and new ones continue from there until next FY rollover

**Tests**
- [ ] (T) Counter resets at configured FY boundary (parametrize fy_start_month=1,4,7)
- [ ] (T) Format tokens render correctly (`{FY_SHORT}`, `{FY_RANGE}`, `{NUM:4}` padding)
- [ ] (T) Concurrent sale creation under same FY → no duplicate numbers
- [ ] (T) Sale dated in old FY uses old counter; sale dated in new FY uses new counter
- [ ] (T) Forward-only: existing invoices preserved, new counter starts at `max+1`

**Decisions captured (from PM)**
- FY start: **configurable month** (default April)
- Format: **custom prefix template** with tokens
- Scope: **POS sales + Rx dispenses + Sale returns/credit notes + internal purchase numbers** (NOT supplier invoice nos)
- Migration: **forward-only**

---

## P1 — Table-stakes features

### 6. Sale Return / Credit Note
Today the only reversal is full void. Real pharmacies need partial returns.

- [ ] (D) `PharmacySaleReturn` + `PharmacySaleReturnItem`
- [ ] (B) `POST /api/pharmacy/sales/{id}/return` — partial qty per item, reason, restock flag
- [ ] (B) Generate credit note PDF (reuse `pdf_service.py` pattern)
- [ ] (B) Stock ledger txn_type=`sale_return` (restock or write-off based on flag)
- [ ] (F) "Return" action on SalesTab row → dialog with line-by-line qty
- [ ] (T) Partial return + restock; partial return + write-off

### 7. Drug interaction / allergy / contraindication checks
Fields exist on Prescription model; no enforcement anywhere.

- [ ] (D) `DrugInteraction` table (salt_a_id, salt_b_id, severity, note) — seedable
- [ ] (D) `PatientAllergy` table (already may exist — verify)
- [ ] (B) `GET /api/pharmacy/prescriptions/check` — given patient_id + medicine_ids[], return warnings
- [ ] (F) Warning banner in DoctorDashboard Rx form + at dispense in PendingRxTab
- [ ] (B) Audit-log overrides (doctor/pharmacist proceeds despite warning)
- [ ] (T) Interaction match across two Rx items; allergy block; override audit

### 8. Barcode at POS and GRN
No barcode pipeline today.

- [ ] (B) `barcode` column on Medicine (already? verify) + uniqueness
- [ ] (F) USB-scanner-friendly input in SalesCounter (auto-add row on scan)
- [ ] (F) Barcode capture during purchase confirm (per-batch barcode optional)
- [ ] (B) Barcode label PDF endpoint (Avery layout, batch+expiry+price)
- [ ] (F) "Print labels" button on Inventory tab

### 9. Auto-PO suggestion from reorder thresholds
`min_qty`, `reorder_qty` exist but nothing consumes them.

- [ ] (B) `GET /api/pharmacy/purchases/suggest` — returns draft PO lines grouped by preferred supplier
- [ ] (D) Add `preferred_supplier_id` to Medicine
- [ ] (F) "Auto-suggest PO" button on PurchasesTab → opens draft purchase pre-filled
- [ ] (T) Below-reorder threshold flow

---

## P2 — Polish

- [ ] (F) Date-range + supplier + medicine filters on PurchasesTab
- [ ] (F) Date-range + cashier + payment-mode filters on SalesTab
- [ ] (F) CSV export on every report (use existing billing CSV pattern)
- [ ] (F) Bulk medicine import (CSV upload + dry-run preview + commit)
- [ ] (B/F) License expiry alerts: retail license + supplier drug licenses, dashboard tile + 30/15/7 day reminders
- [ ] (F) Generic substitution prompt at dispense — list other in-stock medicines sharing primary salt
- [ ] (F) `pharmacy_tax_on_free` admin toggle in Hospital Settings
- [ ] (B) Patient FK tightening: switch sale's `patient_ip_id` to real FK; backfill via migration
- [ ] (B) Recalculate `PrescriptionItem.unit_price` at dispense time (don't trust create-time snapshot)

---

## P3 — Future / nice-to-have (not committing yet)

- Weighted-average / FIFO / LIFO valuation toggle per hospital
- GSTR-1 / GSTR-2 export
- Cycle counting + variance approval workflow
- Cold-chain temperature logging for biologics
- Refill scheduling + SMS/WhatsApp reminders
- Customer loyalty / TPA pricing tiers consuming `rate_a`/`rate_b`
- Two-witness MAR for narcotics; prescriber on narcotic register
- Receipt-printer integration (ESC/POS) — drop reliance on PDF preview at counter

---

## Working agreement

- Each task above gets its own branch + PR; do not bundle P0 with P1.
- All new endpoints must use `require_feature_permission("pharmacy", ...)` (granular), not legacy `require_permission`.
- All money math: `Decimal`, never float — match existing pharmacy code.
- All stock changes must write a `PharmacyStockLedger` row (no exceptions).
- Tests: add to `backend/tests/test_pharmacy_smoke.py` or create `test_pharmacy_<feature>.py`. Follow shared-session-DB pattern (see `project_test_suite` memory).
- UI: keep within existing tab structure under `frontend/src/pages/modules/pharmacy/tabs/`; new pages only when a tab would exceed ~400 LOC.

---

## Decisions captured (PM, 2026-06-01)

1. **Return policy window**: 7 days; **restock by default** (write-off only if user toggles).
2. **Drug interaction source**: hospital pharmacist enters manually (no external dataset seed).
3. **Barcode standard**: EAN-13 from manufacturer (no internal Code128 generation).
4. **Supplier payment modes**: same list as patient billing (cash / card / UPI / cheque / bank transfer).
5. **Auto-PO**: one PO per supplier per run (no consolidated single draft).
6. **P0 execution order**: #1 → #2 → #3 → #4 → #5, all on one branch `pharmacy-p0`.
