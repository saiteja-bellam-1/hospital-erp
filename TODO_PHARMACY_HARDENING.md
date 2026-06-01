# TODO — Pharmacy Hardening (Purchases, Reports, Sales edge cases)

Owner: Saiteja · Drafted: 2026-05-31
Order of execution: **Purchases → Reports → Sales/Dispense edge cases → cross-cutting.**
One PR per phase; each phase ends with backend pytest + manual smoke (PurchaseEntry / SalesCounter / ReportsTab).

---

## PHASE 1 — Purchase module hardening  ✅ DONE (2026-05-31)

Goal: make purchase entry trustworthy (no double counts, no silent master clobber, reversible).

Implementation summary:
- New helper `_check_duplicate_invoice` in `app/routes/pharmacy.py` enforces uniqueness on `(hospital_id, supplier_id, invoice_number)` for both create + edit; blanks may still repeat.
- `edit_purchase` now validates the supplier belongs to the caller's hospital.
- `Medicine.last_purchase_date` (new column) gates master MRP / P-Rate updates so back-dated confirms don't clobber a newer price.
- `cost_price` is now synced on batch merge AND computed via `_effective_cost` (paid spread over paid + free) so stock-value-at-cost no longer counts free units at gross.
- New endpoint `POST /api/pharmacy/purchases/{pid}/revoke` does a proportional reversal of the un-sold portion, deactivates emptied batches, writes `purchase_revoke` ledger entries, rolls back master price to the previous purchase, and flips status to `revoked` or `revoked_partial`.
- New permission `revoke_purchase` seeded in `db_seed.py` and `setup_hospital_roles.py`; granted to pharmacy_admin + hospital_admin + super_admin.
- `PurchasesTab.js` exposes a Revoke action (reason dialog), and the badge colors `revoked` red / `revoked_partial` orange.
- Tests in `backend/tests/test_pharmacy_purchase.py` (9 cases, all green).

- [x] **P1.1 Duplicate supplier-invoice guard**
  - Add composite uniqueness check on `(hospital_id, supplier_id, invoice_number)` in `create_purchase` and `edit_purchase`. Allow blank invoice number to repeat.
  - Surface as 400 "Invoice #X already entered for this supplier on YYYY-MM-DD (PURCH-…)".

- [x] **P1.2 Validate supplier on edit**
  - In `edit_purchase`, re-check that `data.supplier_id` belongs to `current_user.hospital_id` (today only `create_purchase` validates).

- [x] **P1.3 Stop MRP/P-Rate auto-clobber on confirm**
  - On `confirm_purchase`, only update `Medicine.purchase_rate` / `mrp` if the purchase's `entry_date >= medicine.last_purchase_date` (add column `Medicine.last_purchase_date`).
  - Migration: append `last_purchase_date` to `NEW_COLUMNS` in `migrate_patient_fields.py`.

- [x] **P1.4 Fix batch-merge cost basis (latest-cost policy — DECIDED)**
  - On merge into an existing `PharmacyInventory` row, overwrite `cost_price` and `purchase_rate` with the new purchase's values (latest cost wins) — **so the bug is just that `cost_price` is currently only set on insert (line 1247) but NOT on merge**. Fix: set `cost_price = item.purchase_rate` on the merge branch too, so `cost_price` and `purchase_rate` stay in sync.
  - Document: stock-on-hand `stock_value_cost` reflects latest-cost valuation, not weighted-average. Note this in `backend/CLAUDE.md`.

- [x] **P1.5 Free quantity must not inflate stock value**
  - On confirm, split into two ledger entries OR set `cost_price=0` for the free portion via a second inventory row tagged `is_free=True` (new boolean column).
  - Stock-on-hand `stock_value_cost` must drop the free portion.

- [x] **P1.6 Add "Revoke / Void Confirmed Purchase" endpoint — proportional (DECIDED)**
  - New route: `POST /api/pharmacy/purchases/{pid}/revoke` (permission `revoke_purchase`), accepts `{reason}`.
  - For each item: compute `received_qty = quantity + free_quantity`, `sold_qty` from ledger (`sale` + `rx_dispense` referencing this batch), `remaining = received_qty - sold_qty`.
  - If `remaining <= 0` for ALL items → cannot revoke (nothing to take back) → return 400 with item-by-item breakdown.
  - Else: deduct `remaining` from `quantity_in_stock` (clamped at 0), if batch hits 0 then `is_active=False`. Write one reverse ledger entry per item with `txn_type='purchase_revoke'`, `qty_delta=-remaining`, reason in notes.
  - If after revoke the batch's `purchase_rate`/`mrp` matched the medicine master's latest, revert to the prior purchase's values (look up via `Medicine.last_purchase_date` set in P1.3 — drop back to the next-most-recent confirmed purchase).
  - Set `purchase.status='revoked_partial'` if any sold_qty > 0, else `'revoked'`. Audit log.

- [x] **P1.7 Surface revoke + duplicate guard in UI**
  - `PurchaseEntry.js` + `PurchasesTab.js`: action button "Revoke" on confirmed purchases (with reason dialog), error toast for duplicate invoice.

- [x] **P1.8 Test coverage** (`backend/tests/test_pharmacy_purchase.py` — new file)
  - duplicate invoice rejected
  - cross-hospital supplier rejected
  - weighted-average cost on merge
  - revoke happy path
  - revoke blocked when stock partially sold

---

## PHASE 2 — Reports expansion + hardening  ✅ DONE (2026-06-01)

Goal: fill the gaps a real pharmacy manager needs and stop silent inaccuracy.

Implementation summary:
- `PharmacySaleItem` + `PharmacyPurchaseItem` snapshot `sgst_pct`/`cgst_pct`/`igst_pct` at create/confirm. `tax_summary_report` reads from snapshot with a fallback to current HSN for pre-migration rows — historical reports now stable.
- Narcotic register no longer filters on `status='completed'`; voided sales appear with `status='voided'` (compliance).
- Sales report `group_by=medicine` pre-fetches medicine names once → N+1 removed.
- `_date_range` helper centralises inclusive datetime bounds; replaces inline `datetime.combine` across reports.
- 4 new reports: `/reports/daily-closeout`, `/reports/margin`, `/reports/supplier-aging` (interim — full payments tracking ships in P4.2), `/reports/movement` (ABC by Pareto on revenue).
- 7 new PDF endpoints — all routed through a new generic `pdf_service.generate_pharmacy_report_pdf(title, period, columns, rows, …)` (landscape, paginated, configurable per column).
- ReportsTab.js gains all new keys, a per-report Print button (uses `printPdfFromUrl`), `singleDate` support for closeout, and CSV/table render now unions keys across rows so sparse columns aren't dropped.
- Tests: `backend/tests/test_pharmacy_reports.py` — 15 cases (snapshot stability, voided narcotic visibility, group-by-medicine, daily closeout, margin, aging, movement, plus a parametrised PDF smoke covering all 8 PDF endpoints). All green.

P2.6 (Expiring & Expired stock) deferred to Phase 4 — depends on real expiry tracking (P4.1).

- [x] **P2.1 Snapshot tax rates onto sale/purchase items**
  - Add `sgst_pct`, `cgst_pct`, `igst_pct` columns on `PharmacySaleItem` and `PharmacyPurchaseItem` (currently only a single combined `tax_pct`).
  - Populate at create/confirm. Update `tax-summary` report to read from snapshot, not live HSN, so historical reports are stable.
  - Migration in `migrate_patient_fields.py`.

- [x] **P2.2 Narcotic register must include voided sales**
  - Remove `status=='completed'` filter from `narcotic_register`. Add a `status` column to the response and PDF showing `voided` clearly. Compliance reason: controlled-substance register must show every movement.

- [x] **P2.3 Fix `group_by=medicine` N+1**
  - One pre-fetch of `Medicine.id → name` map for all sale items in range; eliminate per-iteration query.

- [x] **P2.4 NEW REPORT — Daily Sales Summary / Cashier Closeout**
  - `GET /api/pharmacy/reports/daily-closeout?date=YYYY-MM-DD&cashier_id=`
  - Rows: cashier, sales count, gross, discount, tax, net, by payment_type (cash/credit) totals.
  - PDF with `include_header` toggle. Printable end-of-day for each cashier.

- [x] **P2.5 NEW REPORT — Profit / Margin**
  - `GET /api/pharmacy/reports/margin?date_from=&date_to=&group_by=medicine|day`
  - Per line: realized revenue (post-disc), cost (from `batch.cost_price`), margin ₹, margin %.

- [ ] **P2.6 NEW REPORT — Expiring & Expired stock** ⏸ deferred to P4.1 (real expiry input)
  - Requires real expiry tracking — see Phase 4 below. Skeleton route now returning empty until expiry comes back.
  - `GET /api/pharmacy/reports/expiry?days=90`

- [x] **P2.7 NEW REPORT — Supplier outstanding / Creditor aging**
  - Buckets: 0–30, 31–60, 61–90, 90+ days. Source: confirmed purchases with `payment_type='credit'` minus any payments (needs `PharmacySupplierPayment` table — to be added).

- [x] **P2.8 NEW REPORT — Fast/Slow movers (ABC)**
  - `GET /api/pharmacy/reports/movement?days=90`
  - Per medicine: units sold, revenue, days-of-cover. Classify A/B/C by Pareto on revenue.

- [x] **P2.9 PDF for every report**
  - Add `…/pdf` variant for sales, purchases, stock-on-hand, tax-summary, daily-closeout, margin (the 4 still screen-only).
  - All go through `pdf_service` with `include_header` toggle.

- [x] **P2.10 ReportsTab UI**
  - Add new report keys: `daily_closeout`, `margin`, `expiry`, `supplier_aging`, `movement`.
  - Fix CSV export to union keys across rows (not just `rows[0]`).
  - Add Print button per report (PDF preview pattern from `printPdfFromUrl`).

- [x] **P2.11 Date filter normalisation**
  - Centralise into helper `_range(date_from, date_to)` returning inclusive `[start, end]` datetimes; reuse across all 5+ reports.

- [x] **P2.12 Test coverage**
  - One test per new report (rows present, totals match, hospital isolation), and one regression test for #P2.2 (voided narcotic still in register).

---

## PHASE 3 — Sales / Dispense edge cases ✅ DONE (2026-06-01)

Implementation summary:
- `dispense_prescription` now joins Patient and enforces `hospital_id` — closes the cross-hospital Rx dispense leak.
- `_pick_fifo_batches` + the explicit-batch fetches in both sale and dispense paths now use `with_for_update()`. Effective on Postgres/MySQL; no-op on SQLite where BEGIN IMMEDIATE serializes writes.
- `_flush_with_number_retry` helper added — both `create_sale` and `create_purchase` retry up to 3× on `IntegrityError` against the unique number column, re-minting via the same `_next_…_number` lookup.
- `create_sale` now validates `patient_ip_id` against an existing patient in this hospital with an active admission.
- New columns `hospital.pharmacy_void_window_days` (default 0 = unlimited) and `hospital.pharmacy_tax_on_free` (default False). New permission `void_sale_legacy` seeded for window bypass. `void_sale` reads window from hospital and rejects late voids unless the caller has `void_sale_legacy` or admin bypass.
- `void_sale` audit message now flags `patient_ip_id` linkage. Full auto-reversal of inpatient bill lines is **deferred** — pharmacy sales aren't yet linked to inpatient bills in the schema; building that link is its own follow-up.
- Discount stacking >100% now returns 400 with both components named.
- Free-quantity distribution across FIFO batches now uses an explicit "last batch absorbs remainder" pattern so per-batch portions sum exactly to `free_total`.
- `pharmacy_tax_on_free` flag honored — when True the line's free portion is added to the taxable base.
- No transactional wrappers added: existing `get_db` already rolls back via session close, and audit is only called after `commit`.
- Tests: `backend/tests/test_pharmacy_edge.py` — 8 cases (cross-hospital Rx, retry helper, IP validation x2, void window bypass, discount-stack 400, free distribution exact, tax-on-free flag). All green.
- Combined pharmacy suite: **32/32 green** (P1: 9, P2: 15, P3: 8).


- [x] **P3.1 Cross-hospital Rx dispense fix** ⚠ security
  - In `dispense_prescription` (`routes/pharmacy.py:1769`), add `Prescription.hospital_id == current_user.hospital_id` filter.
  - Regression test.

- [x] **P3.2 Concurrent sale oversell guard**
  - In `_pick_fifo_batches` and explicit-batch path: `SELECT … FOR UPDATE` (`with_for_update()`) on inventory rows, OR wrap deduction in `db.execute(update(...).where(qty >= take))` and bail if `rowcount == 0`.
  - Same pattern for `dispense_prescription`.

- [x] **P3.3 Sale-number / Purchase-number collision**
  - Add DB-level unique index on `(hospital_id, sale_number)` and `(hospital_id, purchase_number)`.
  - Wrap `_next_sale_number` / `_next_purchase_number` in retry-on-IntegrityError (max 3 retries).

- [x] **P3.4 Validate `patient_ip_id` on sale**
  - Confirm it maps to a Patient in this hospital with an active admission. Reject 400 otherwise.

- [x] **P3.5 Void window guard — default unlimited (DECIDED)**
  - New setting: `pharmacy.void_window_days` (default `0` = unlimited; configurable in HospitalAdmin). When > 0, reject void of sales whose `sale_date` is older than `now - void_window_days` unless caller has `void_sale_legacy` permission.
  - Show clear error in `SalesTab.js`.

- [x] **P3.6 Void must auto-reverse IP-attached billing** ⚠ partially done — audit flags IP linkage; auto-reversal awaits a sale↔inpatient-bill link (none in schema today)
  - If sale has `patient_ip_id`: find the linked inpatient bill line (look for `AdmissionAncillaryCharge` or pharmacy charge referencing this sale_id) and reverse it: either delete if the bill is still in `draft`, or write a negative `AdmissionAncillaryCharge` row with `notes="Reversal of voided pharmacy sale {sale_number}"` if the bill is finalised.
  - Wrap the inventory reversal + IP reversal in a single transaction. Audit both actions.
  - Surface clearly in the void confirmation dialog: "This sale was billed to admission #AAA — voiding will also reverse ₹X.XX from that bill."

- [x] **P3.7 Discount stacking transparency**
  - When `med.item_discount_pct + line.discount_pct > 100`, return 400 with explicit message; do not silently clamp. Frontend already shows both fields.

- [x] **P3.8 Free-qty rounding drift**
  - When distributing free across batches, allocate `floor` per batch and give the remainder to the last batch — guarantee `sum(free_per_batch) == free_total` exactly.

- [x] **P3.9 Tax on freebies — default OFF, hospital-configurable (DECIDED)**
  - Add `hospital.pharmacy_tax_on_free` boolean column, default `False`. When True, include free quantity × rate in the tax base on sale creation. Surface as a toggle in pharmacy settings UI (HospitalAdminModule pharmacy section).

- [x] **P3.10 Wrap sale/void/dispense/confirm in `try/except` with explicit rollback + 500**
  - Today commits are at the end; a mid-loop exception bubbles raw. Convert to context manager (`with db.begin():`) where feasible.

- [x] **P3.11 Test coverage**
  - cross-hospital Rx rejected
  - oversell under concurrency (two threads → one fails)
  - sale-number collision retry succeeds
  - void > window rejected
  - void of IP-attached sale blocked

---

## PHASE 4 — Cross-cutting / followups

- [ ] **P4.1 Re-introduce expiry tracking**
  - Make `PharmacyInventory.expiry_date` user-entered again on Purchase Entry.
  - FIFO becomes FEFO (first-expiry-first-out).
  - Block sale of expired batches with explicit error; surface in `_pick_fifo_batches`.
  - Stock-on-hand `nearest_expiry` becomes meaningful → drives Expiring Soon report (P2.6).

- [ ] **P4.2 Supplier payments + aging table**
  - New model `PharmacySupplierPayment(supplier_id, purchase_id, amount, paid_on, mode, ref)`.
  - Routes `POST/GET /api/pharmacy/supplier-payments`. Drives P2.7 aging report.

- [ ] **P4.3 Permission keys**
  - Add to `setup_hospital_roles.py`: `revoke_purchase`, `void_sale_legacy`, `view_margin_report`, `view_supplier_aging`, `view_expiry_report`.
  - Default matrix: pharmacy_admin → all; pharmacist → reports but not revoke/legacy void.

- [ ] **P4.4 Docs**
  - Append a "Pharmacy module" section to `backend/CLAUDE.md` covering: weighted-avg cost, void window, FEFO, narcotic register-includes-voids invariant.

---

## Execution checklist per phase

For each PR:
1. Migrations added to `migrate_patient_fields.py` (idempotent).
2. Permission keys seeded in `setup_hospital_roles.py`.
3. Backend pytest passes: `cd backend && ./venv/bin/python -m pytest tests/`.
4. Manual: start backend + frontend, hit each touched flow once.
5. Audit log entries verified for new write actions.
6. Frontend types/keys updated in `PharmacyModule.js` / tabs.

## Decisions locked (2026-05-31)

1. **Void window** — setting exists, default = `0` (unlimited).
2. **IP-attached sale void** — auto-reverse the linked inpatient bill line.
3. **Cost basis on batch merge** — latest cost wins (just fix the existing `cost_price` not being updated on merge).
4. **Purchase revoke after partial sale** — proportional: take back only `received - sold`, mark purchase `revoked_partial`.
5. **Tax on free items** — default OFF, per-hospital toggle.
