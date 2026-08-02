# TODO — Pharmacy Billing & Inventory Audit Fixes

Audit date: 2026-08-01  
Source: pharmacy billing/inventory audit (POS, Rx dispense, purchase/transfer revoke, IP bill linkage).  
Scope: irregular inventory values + bill-value mismatches.

Legend: `[ ]` not started · `[~]` in progress · `[x]` done · `(B)` backend · `(F)` frontend · `(D)` DB/migration · `(T)` tests

Suggested ship order: **#1 → #2 → #3 → #6 → #7 → #9**, then remaining Critical/High.

---

## P0 — Critical inventory

### 1. Sold-qty math ignores voids / Rx cancels
**Symptom:** After sell→void (or dispense→cancel), purchase/transfer revoke still treats units as sold → phantom stock or blocked full reverse.  
**Where:** `_sold_qty_for_batch` in `backend/app/routes/pharmacy.py`; duplicate inline query in `revoke_purchase`; transfer revoke in `backend/app/routes/pharmacy_stores.py`.

- [ ] (B) Centralize net-sold helper: sum outbound (`sale`, `rx_dispense`) minus inbound (`return_in`, `rx_cancel`) for the batch (clamp ≥ 0)
- [ ] (B) Replace `_sold_qty_for_batch` + purchase-revoke inline sum + transfer-revoke sold sum with the helper
- [ ] (B) Document which txn_types count as outbound vs inbound (exclude `purchase`, `transfer_*`, `adjustment`, writeoffs)
- [ ] (T) Sell → void → revoke purchase fully reverses to 0 stock
- [ ] (T) Dispense → cancel Rx → revoke transfer fully reverses
- [ ] (T) Sell without void still blocks revoke of sold portion

### 2. Cash Rx dispense + void/cancel double-restores stock
**Symptom:** Cash dispense deducts via `rx_dispense` and creates a `PharmacySale` without `sale` ledger rows; void (`return_in`) + cancel (`rx_cancel`) both credit stock.  
**Where:** `dispense_prescription` cash path; `void_sale`; `cancel_prescription` / `_reverse_dispensed_stock`.

- [ ] (B) On cash dispense, either (a) mark sale as stock-already-deducted (`stock_source=rx_dispense`) and skip stock restore on void, **or** (b) void of Rx-linked cash sale must cancel Rx / reverse only once
- [ ] (B) Prefer single reversal owner: voiding an Rx-backed cash sale cancels the Rx (or blocks void and forces cancel-Rx)
- [ ] (B) Cancel Rx when `pharmacy_sale_id` set: void or mark that sale voided **without** a second stock credit
- [ ] (B) Guard: if both paths attempted, second restore is no-op / 400
- [ ] (T) Dispense cash → void sale → stock back once; cancel Rx after void does not add again
- [ ] (T) Dispense cash → cancel Rx → sale voided/linked cleared; stock back once

### 3. Void/edit of Rx-linked POS sale does not roll back Rx qty
**Symptom:** POS with `prescription_id` advances `quantity_dispensed`; void/edit restores inventory but leaves Rx dispensed → can over-dispense.  
**Where:** `_apply_pos_prescription_sale`; `void_sale`; `edit_sale`.

- [ ] (B) On void of prescription-linked sale: reverse `quantity_dispensed` / item status / Rx status from sale quantities; clear `pharmacy_sale_id` if fully rolled back
- [ ] (B) On edit of prescription-linked sale: reverse old Rx qty, then re-apply new lines (or block edit and require void+new)
- [ ] (B) Validate remaining prescribed qty the same way create-sale does
- [ ] (T) Create Rx-linked sale → void → remaining qty restored; can re-dispense
- [ ] (T) Edit Rx-linked sale qty down → Rx counters match new qty

### 4. Restored stock on deactivated batches stays unsellable
**Symptom:** Revoke sets `is_active=False` at 0; void/edit/`rx_cancel` add qty but do not reactivate; FEFO skips inactive.  
**Where:** `_restore_sale_items_stock`; `void_sale`; `_reverse_dispensed_stock`; compare transfer revoke which sets `src.is_active = True`.

- [ ] (B) When restoring qty to a batch and new qty > 0, set `is_active=True`
- [ ] (B) Apply consistently on void, sale edit restore, rx_cancel, and any other return-in path
- [ ] (T) Revoke to inactive → void prior sale (or cancel Rx) → batch active and FEFO-sellable

### 5. Void sale ledger rows omit `store_id`
**Symptom:** Store-scoped ledger/movement reports miss voids.  
**Where:** `void_sale` ledger write vs `_restore_sale_items_stock`.

- [ ] (B) Set `store_id=sale.store_id` (fallback batch.store_id) on void `return_in` rows
- [ ] (T) Void appears in store-filtered ledger

---

## P0 — Critical bill values

### 6. POS preview discount ≠ server discount
**Symptom:** UI seeds `default_discount_pct`; server stacks `line.discount_pct + item_discount_pct` → saved grand ≠ preview.  
**Where:** `SalesCounter.js` add-line; `_process_sale_lines` in `pharmacy.py`.

- [ ] (B)+(F) Pick one policy: (A) server only uses line discount (item default is UI prefill only), **or** (B) UI preview also adds `item_discount_pct` and shows it
- [ ] (F) If (B): show effective % (line + medicine default) in cart; seed from `item_discount_pct` and/or `default_discount_pct` consistently
- [ ] (B) If (A): stop auto-adding `med.item_discount_pct` in `_process_sale_lines` (keep validation/cap if UI sends it)
- [ ] (T) Preview grand matches persisted `grand_total` for medicines with both discount fields set

### 7. Edit sale drops bill-level discount
**Symptom:** Edit load clears bill discount; amount not stored separately → re-save raises total.  
**Where:** `SalesCounter.js` edit load; `PharmacySale` model only has `discount_total`.

- [ ] (D) Add `PharmacySale.bill_discount_amount` (float, default 0) + migration
- [ ] (B) Persist bill discount on create/edit; include in `SaleOut` / PDF if needed
- [ ] (F) On edit load, restore `bill_discount_amount` into the field
- [ ] (T) Create with bill disc → edit without touching disc → grand unchanged

### 8. IP bill: Rx path untaxed, POS path taxed
**Symptom:** Admission Rx pharmacy = `unit_price × dispensed` (no GST); deferred POS uses `grand_total` (with tax).  
**Where:** `_pharmacy_rx_billable_amount`; POS filter in `_compute_admission_charges`.

- [ ] (B) Decide hospital policy: (A) IP pharmacy always ex-tax / always inc-tax, or (B) document dual paths and align Rx lines to same tax rules as POS
- [ ] (B) If unify: compute Rx IP lines via shared pricing/tax helper (HSN + tax_mode)
- [ ] (F) Bill preview labels whether pharmacy amounts include GST
- [ ] (T) Same medicine Rx vs POS deferred → comparable amounts under chosen policy

### 9. POS bill discount not reflected on IP BillItems
**Symptom:** Header uses `sale.grand_total`; BillItems use raw `line_total` → itemized sum > header; reverse can overshoot.  
**Where:** `_create_admission_bill_record_inner` POS loop; `_pharmacy_pos_sale_entries`; credit-note helpers.

- [ ] (B) When writing BillItems for a deferred POS sale, allocate bill discount across lines (or one adjustment line) so `sum(items) == grand_total`
- [ ] (B) Credit-note / unlocked reverse use amounts consistent with what was charged on the parent bill
- [ ] (T) POS with bill discount → finalize IP bill → sum(BillItems pharmacy) == sale.grand_total
- [ ] (T) Void after finalize → credit note matches charged amount

### 10. `tax_on_free` corrupts `discount_total`
**Symptom:** Free qty folded into `base_after_disc` then `disc_total += base - base_after_disc` understates/negates discount.  
**Where:** `_process_sale_lines` with `tax_on_free`.

- [ ] (B) Split accounting: paid base discount vs taxable free add-on; `discount_total` only from paid (and bill disc)
- [ ] (B) Keep tax/grand behavior for free lines; fix only discount aggregation (and PDF fields if shown)
- [ ] (T) Sale with free + tax_on_free → `discount_total` ≥ 0 and equals paid-line discounts + bill disc

---

## P1 — High inventory

### 11. No dedicated customer return document
**Symptom:** Only void/edit (`return_in`); model mentions unused `return_out`.

- [ ] (D)+(B) Optional later: sale-return doc type with partial qty, `return_out`/`return_in` ledger, credit note
- [ ] (F) Return UI from sales history (partial lines)
- [ ] (T) Partial return restores only returned qty; bill credit matches
- [ ] Note: defer if void/edit + fixes #1–#3 cover current ops; keep as product gap

### 12. Client stock checks weak / skipped on edit
**Symptom:** Create-only checks; multi-line same batch not pooled; edit skips gate; stale qty.

- [ ] (F) Pool need-qty across cart lines sharing `batch_id` / medicine for create
- [ ] (F) Wire `saleEditUtils` stock pool helpers into SalesCounter edit mode
- [ ] (F) Re-fetch batch/store qty before save (or on qty blur)
- [ ] (T) E2E or unit: two lines same batch exceeding stock blocked on client

### 13. Cash dispense sale missing `store_id`
**Symptom:** Store-filtered sales miss cash Rx sales; stock moved under dispense store.

- [ ] (B) Set `sale.store_id = dispense_store_id` on cash-at-pharmacy dispense sale
- [ ] (T) Sale appears under that store’s sales list/report

### 14. Purchase edit can orphan deactivated batches
**Symptom:** Edit reverse deactivates; re-apply only merges active → new inventory id; old row may keep residual qty.

- [ ] (B) On re-apply after confirmed edit: prefer reactivating/merging the prior `inventory_id` / same batch key including inactive rows with stock
- [ ] (B) Or: never deactivate on reverse when re-apply in same transaction will recreate same key
- [ ] (T) Confirmed purchase edit same batch key → single inventory row; no orphan qty

### 15. Legacy `PharmacyService._dispense_from_inventory` without ledger
**Symptom:** EHR path mutates qty with no ledger → ledger ≠ on-hand.  
**Where:** `backend/app/services/pharmacy_service.py`; `ehr_service.py`.

- [ ] (B) Route EHR dispense through same FEFO + ledger path as pharmacy routes, **or** remove dead stock mutation if EHR no longer dispenses stock
- [ ] (T) If still used: EHR dispense writes `rx_dispense` ledger and matches qty

### 16. Expiry write-off: active@0 + missing ledger `store_id`
**Symptom:** Reporting/consistency noise.

- [ ] (B) Set `is_active=False` when write-off zeroes qty
- [ ] (B) Set `store_id=batch.store_id` on `expiry_writeoff` ledger rows
- [ ] (T) Write-off batch inactive; ledger filterable by store

---

## P1 — High bill values

### 17. Tab vs strip price inequality (pre-rounded tab rate)
**Symptom:** `round(strip/scf) × tabs` ≠ strip price for exact strip multiples.

- [ ] (B)+(F) Prefer strip-exact math when tabs are exact multiples of scf (charge strip rate × strips), else tab rate × remainder
- [ ] (B)+(F) Align `pharmacy_pricing.py` and `pharmacyUnits.js`
- [ ] (T) 3 tabs of scf=3 at strip ₹10 → ₹10.00 both client preview and server

### 18. FEFO split can change rate vs UI
**Symptom:** Auto-batch prices per picked batch; UI may use medicine/selected batch.

- [ ] (F) When batch auto, show “rate may vary by batch” or preview FEFO allocation
- [ ] (B) Optional: price FEFO legs at first-batch / medicine rate for consistency (policy choice)
- [ ] (T) Document chosen policy; assert create response matches policy

### 19. Tax from medicine HSN; invoice HSN prefers batch
**Symptom:** Tax uses `med.hsn_id`; printed HSN prefers batch.

- [ ] (B) Resolve tax HSN with same precedence as display (batch then medicine)
- [ ] (T) Batch HSN different from medicine → tax_pct and invoice `hsn_code` match

### 20. Cash Rx auto-sale always exclusive tax
**Symptom:** Ignores inclusive POS default; always adds tax on top.

- [ ] (B) Pass hospital/sale `tax_mode` into cash dispense sale builder; use `compute_line_tax`
- [ ] (F) PendingRx cash path: expose or inherit tax mode
- [ ] (T) Inclusive mode → cash Rx sale grand matches inclusive semantics

### 21. Rx `total_amount` uses prescribed qty; IP/credit uses dispensed / fallback mismatch
**Symptom:** Credit-note fallback to `rx.total_amount` can over-credit partial fills.

- [ ] (B) Keep `rx.total_amount` as dispensed-based (or store both); credit-note fallback uses `_pharmacy_rx_billable_amount`
- [ ] (B) Align `rxi.total_price` with dispensed × unit_price when updating on dispense
- [ ] (T) Partial dispense → cancel after locked bill → CN amount = dispensed value only

### 22. Bill discount is post-tax
**Symptom:** Users expect pre-tax bill discount.

- [ ] (B)+(F) Confirm product rule (post-tax vs pre-tax); if pre-tax, redistribute before tax and update preview
- [ ] (F) Label UI “Bill discount (after tax)” or “(before tax)” so cashiers know
- [ ] (T) Fixture asserts chosen formula

### 23. Frontend rounding inconsistency in preview
**Symptom:** Display gross rounds; discount applies to unrounded base.

- [ ] (F) Use one path: round base once, then discount/tax (match `line_subtotal_before_tax` server)
- [ ] (T) Cart preview equals server for mixed tab/strip lines

---

## P2 — Medium / process

### 24. No customer partial-return billing path
- [ ] Track under #11; no separate work until product prioritizes returns

### 25. Unlocked IP reverse uses naive subtotal math
**Where:** `pharmacy_reversal.py` `_unlocked_bill_inplace_reverse*` comments.

- [ ] (B) Recompute parent bill from remaining BillItems (or shared totals helper) instead of subtracting only pharmacy line totals from header
- [ ] (T) Unlock draft bill with mixed lines → remove pharmacy → header equals sum(remaining items) ± bill-level disc/tax rules

### 26. Transfer confirm: weak client qty gate
- [ ] (F) Before confirm, re-check each line `qty ≤ batch.quantity_in_stock`
- [ ] (B) Already rejects on confirm — keep; add clear error surfacing in UI

### 27. Opening-stock import uses `adjustment` txn type
- [ ] (B) Use distinct `txn_type` e.g. `opening_stock` (and report filters)
- [ ] (D) Optional backfill notes for old rows
- [ ] (T) Import opening stock → ledger type filterable

### 28. Supplier payments / aging still open
- [ ] Track in existing `TODO_PHARMACY_GAPS.md` P0 #3 — not re-scoped here; link only

---

## Verification checklist (after P0)

- [ ] (T) Regression suite: purchase → sale → void → revoke; Rx dispense cash → void/cancel; POS edit with bill discount; IP finalize with deferred POS + bill discount
- [ ] (T) Store-scoped ledger includes void/writeoff/`store_id`
- [ ] Manual: SalesCounter preview vs saved toast for discount + tax_mode inclusive/exclusive
- [ ] Manual: Inventory on-hand equals sum of ledger for a sample medicine/batch after mixed ops

---

## File touch map (expected)

| Area | Likely files |
|------|----------------|
| Sold qty / revoke | `backend/app/routes/pharmacy.py`, `backend/app/routes/pharmacy_stores.py` |
| Rx/sale stock ownership | `backend/app/routes/pharmacy.py`, `backend/app/services/pharmacy_reversal.py` |
| Pricing / tax | `backend/app/utils/pharmacy_pricing.py`, `frontend/src/utils/pharmacyUnits.js`, `frontend/src/utils/pharmacyHsnTax.js` |
| POS UI | `frontend/src/pages/modules/pharmacy/SalesCounter.js`, `saleEditUtils.js` |
| IP bill | `backend/app/routes/inpatient.py` |
| Model/migration | `backend/app/models/pharmacy.py`, `backend/migrate_patient_fields.py` or pharmacy migrate |
| Tests | `backend/tests/test_pharmacy_*.py`, new cases as listed |

---

## Status

| ID | Severity | Status |
|----|----------|--------|
| 1–5 | P0 inventory | [x] implemented 2026-08-01 |
| 6–10 | P0 bill values | [x] implemented 2026-08-01 |
| 11–16 | P1 inventory | [x] mostly done (#11 returns deferred as product gap) |
| 17–23 | P1 bill values | [x] implemented 2026-08-01 |
| 24–28 | P2 | [~] #25–27 done; #11/#24/#28 deferred to product backlog |

### Implementation notes (2026-08-01)
- Net sold helper: `app/services/pharmacy_stock.py`
- Line discount is authoritative (no silent `item_discount_pct` stack); UI prefills `item_discount_pct \|\| default_discount_pct`
- `PharmacySale.bill_discount_amount` column + migration
- IP Rx pharmacy lines now include exclusive HSN GST (aligned with POS)
- Dedicated customer return (#11/#24) and supplier payments (#28) not built — still open product work
- Tests: `tests/test_pharmacy_audit_fixes.py` + updated edge/rx_cancel fixtures
