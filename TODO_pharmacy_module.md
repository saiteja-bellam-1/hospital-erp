# TODO — Pharmacy Module Build

Tracking the build of the Pharmacy module from `Pharmacy_Module_Requirements.md`.
Full plan: `/Users/saiteja/.claude/plans/go-through-this-pharmacy-module-requirem-hashed-falcon.md`.

**Status legend:** `[ ]` pending · `[~]` in progress · `[x]` done · `[!]` blocked.

**Confirmed design decisions:**
- Sales = both POS counter-sale AND Rx-linked dispensing.
- Catalogs = FK-referenced master tables (Company / Supplier / Salt / Rack / UoM / Category).
- Inventory = full batch tracking + FIFO + expiry + stock-movement ledger + alerts.
- **No cross-module integration in this build** (no inpatient / billing / EHR seams wired).

---

## A. Foundation ✓

- [x] A1. Create `backend/app/routes/pharmacy.py` with empty router + `/api/pharmacy/health` ping.
- [x] A1b. Register router in `backend/main.py` (uncommented include + import).
- [x] A2. Define granular permission keys in `db_seed.py` (runtime) and `setup_hospital_roles.py` (CLI). 30-key vocabulary across catalog / pricing / regulatory / inventory / procurement / sales-POS / sales-Rx / reports. `_PHARMACY_ALL` constant exported.
- [x] A2b. Per-role defaults: `super_admin` / `hospital_admin` / `pharmacy_admin` get full 30; `pharmacist` gets 15 op-only keys (`_PHARMACIST_DEFAULT`); doctor cleared (pharmacy is standalone in this build). `_heal_legacy_pharmacy_perms` strips obsolete keys from catalog + role grants on every startup.
- [x] A3. Create `backend/migrate_pharmacy.py` (idempotent, SQLite-safe column-add list); invoked from `main.py` startup chain via `run_migration` next to other migrations. Currently empty NEW_COLUMNS — sections B–F append.

## B. Catalog / Master Data (backend ✓)

- [x] B1. New master models in `app/models/pharmacy.py`: `PharmacyCompany`, `PharmacySupplier`, `PharmacySalt`, `PharmacyRack`, `PharmacyUoM`. Reuse existing `MedicineCategory`.
- [x] B2. Extend `Medicine` model — additive columns: `is_hidden`, `barcode` (indexed), `packaging`, `decimal_supported`, `company_id`, `rack_id`, `salt_id`, `uom_id`, `strip_conversion_factor`.
- [x] B3. Extend `Medicine` — regulatory flags: `is_schedule_h`, `is_schedule_h1`, `is_tramadol`, `is_controlled`, `item_discount_pct`. Keep existing `is_narcotic`.
- [x] B4. CRUD routes for each master entity + Medicine (search/filter on medicines: `search`, `category_id`, `company_id`, `schedule` ∈ {h, h1, narcotic, tramadol, controlled}, `active_only`, `include_hidden`). Includes `/medicines/lookup` for sales-counter barcode/name search. 31 routes mounted total. All audited.
- [x] B5. Frontend — replace `PharmacyModule.js` empty stub with admin tabbed UI (mirror `LabModule.js`). Tabs: Dashboard / Medicines / Categories / Companies / Suppliers / Salts / Racks / UoMs / Tax-HSN / Inventory / Purchases / Sales / Reports.
- [x] B5b. Medicines create/edit dialog — accordion grouping (Basic / Pricing-Tax / Inventory / Regulatory).

## C. Taxation & Pricing (backend ✓)

- [x] C1. New `PharmacyHSN` model (code, description, sgst_pct, cgst_pct, igst_pct). FK `Medicine.hsn_id` added.
- [x] C2. Pricing columns on `Medicine`: `mrp`, `purchase_rate`, `rate_a`, `rate_b`, `cost_pcs`, `default_discount_pct`. Legacy `unit_price` is auto-synced to `rate_a` on pricing updates.
- [x] C3. Routes: `/api/pharmacy/hsn` CRUD (4 routes) gated by `manage_hsn_tax`; `PUT /api/pharmacy/medicines/{id}/pricing` gated by `set_rates` so users can tune rates without full edit rights. Pricing changes audit-logged with diff details.
- [x] C4. Frontend Tax/HSN tab; Medicines dialog pricing block (SGST/CGST auto-pull from HSN).

## D. Inventory & Batch Control (backend ✓)

- [x] D1. Extended `PharmacyInventory` with `mrp`, `purchase_rate`, `free_quantity`, `discount_pct`, `hsn_id`, `supplier_id`, `purchase_id`. Legacy free-text `supplier` retained for backward compat.
- [x] D2. New `PharmacyStockLedger` (append-only signed `qty_delta` per movement) + `PharmacyStockAdjustment` (manual edits with reason + audit trail).
- [x] D3. Thresholds on `Medicine`: `min_qty`, `max_qty`, `reorder_qty`. Wired into create/edit dialogs via MedicineIn schema.
- [x] D4. 6 routes: `/inventory` (per-medicine summary with low-stock flag), `/inventory/batches` (filter by medicine/expiry/supplier), `/inventory/adjust` (signed adjustment + ledger), `/inventory/low-stock`, `/inventory/expiring?days=`, `/inventory/ledger?medicine_id=&txn_type=&date_from=&date_to=`. Negative-stock guarded.
- [ ] D5. Refactor `pharmacy_service.py` FIFO logic to write `PharmacyStockLedger` rows on every consumption. Add `expire_batches()` sweep. → Deferred to Section F/G when the FIFO path is actually exercised by sales/dispense.
- [x] D6. Frontend Inventory tab: stock list + batch drill-down + low-stock/expiring banners + manual adjustment dialog + ledger drawer.

## E. Procurement / Purchase (backend ✓)

- [x] E1. New `PharmacyPurchase` (header + lifecycle: draft → confirmed) + `PharmacyPurchaseItem` (batch lines with MRP/qty/free/P-Rate/discount/HSN). Auto-totals (subtotal/discount/tax/grand) computed via `_recompute_purchase_totals`. On confirm: inventory batches created/merged, ledger written, medicine master MRP+P-Rate propagated back.
- [x] E2. Routes: `POST /purchases` (draft), `PUT /purchases/{id}` (draft-only), `POST /purchases/{id}/confirm`, `GET /purchases?status=&supplier_id=&date_from=&date_to=`, `GET /purchases/{id}`. Edit-after-confirm + double-confirm both 400-guarded. PDF endpoint deferred to Section I.
- [x] E3. Frontend — new page `pages/modules/pharmacy/PurchaseEntry.js`: header row + batch-details grid + tax/total auto-calc + Save Draft / Confirm.
- [x] E3b. Purchases list tab inside `PharmacyModule.js` admin.

## F. Sales — POS Counter Sale (backend ✓)

- [x] F1. New `PharmacySale` (header — patient + doctor as free-text per req doc) + `PharmacySaleItem` (batch-linked). Void columns built in (voided_by/voided_at/void_reason).
- [x] F2. 4 routes: `POST /sales` (FIFO across batches unless `batch_id` given; one line may split into multiple SaleItem rows, one per batch consumed), `GET /sales?status=&payment_type=&date_from=&date_to=&search=`, `GET /sales/{id}`, `POST /sales/{id}/void`. Rate selection: explicit `rate` or `rate_tier` ∈ {A,B} → falls back to legacy `unit_price`. Item discount additive with medicine `item_discount_pct`. Tax auto-pulled from medicine's HSN. Over-sale + double-void guarded. Invoice PDF deferred to Section I. `/medicines/lookup` from Section B serves the counter search.
- [x] F3. Frontend — new page `pages/modules/pharmacy/SalesCounter.js`: customer + doctor + sale-info block, item grid with barcode-scan input, batch picker, Rate-A/B toggle, totals panel, Save & Print.

## G. Sales — Rx-Linked Dispensing (backend ✓)

- [x] G1. Reuses existing `Prescription` / `PrescriptionItem`. No FK linkage to inpatient bills (deferred).
- [x] G2. Routes: `GET /prescriptions/pending` (lists pending+partial Rx with remaining qty per item), `POST /prescriptions/{rx_id}/dispense` (per-item qty + optional batch_id; FIFO default; writes ledger entries with `txn_type='rx_dispense'`; auto-advances item & Rx status to `partial`/`dispensed`). Overdispense + already-dispensed guards in place. Dispense-slip PDF deferred to Section I.
- [x] G3. Frontend — `PharmacyDashboard.js` "Pending Prescriptions" tab + `DispenseRxDialog.js`.

## H. Reports & Dashboard (backend ✓)

- [x] H1. 7 endpoints (all gated by `view_reports`; narcotic-register requires the more specific perm): `GET /dashboard` (today's sales/purchases totals + low-stock + expiring-30d + pending-Rx counts), `/reports/sales?group_by=day|medicine|doctor|payment_type`, `/reports/purchases?group_by=day|supplier`, `/reports/stock-on-hand` (per-medicine totals + cost + MRP valuations), `/reports/expiry?days=`, `/reports/narcotic-register` (Sch H / H1 / Tramadol / Narcotic / Controlled), `/reports/tax-summary` (HSN-grouped SGST/CGST/IGST split).
- [x] H2. Frontend Dashboard tab (KPI cards) + Reports tab (filters + table + CSV export + print).

## I. PDFs

- [x] I1. Added 4 generators to `pdf_service.py` via shared `_pharmacy_header` helper: `generate_pharmacy_sale_invoice_pdf` (with VOIDED watermark), `generate_pharmacy_purchase_pdf` (with DRAFT watermark when not yet confirmed), `generate_pharmacy_dispense_slip_pdf`, `generate_narcotic_register_pdf`. All route through `_finalize` so the seller footer + `include_header` toggle work uniformly. 4 PDF endpoints mounted (64 total pharmacy routes). Print buttons wired in SalesTab / PurchasesTab / ReportsTab / PendingRxTab / SalesCounter via `printPdfFromUrl`.

## J. Audit & Permissions wiring ✓

- [x] J1. Every mutating route in sections B–H calls `_audit(db, user, action, resource_type, resource_id, description, details)` (wrapper over `log_action`) — covers catalog CRUD, pricing updates, stock adjustments, purchase create/edit/confirm, sale create/void, Rx dispense.
- [x] J2. Every route on `/api/pharmacy` declares `require_feature_permission(Modules.PHARMACY, "<granular_key>")`. Reads use `view_catalog` / `view_inventory` / `view_purchases` / `view_sales` / `view_reports`; writes use the specific `manage_*` / `create_*` / `confirm_*` / `set_*` / `adjust_*` / `dispense_rx` key.

## K. Frontend nav & routes

- [x] K1. Add Pharmacy nav entry in `Dashboard.js` (gated by `enabledModules.pharmacy`).
- [x] K2. Sub-routes: `/dashboard/pharmacy` (admin), `/dashboard/pharmacy/sales` (POS), `/dashboard/pharmacy/purchases/new` (purchase entry).
- [ ] K3. New `PharmacyDashboard.js` for pharmacist daily workflow (Sales / Pending Rx / My Sales Today / Low-Stock).

## L. Tests & verification

- [x] L1. `tests/test_pharmacy_smoke.py` — 7 tests covering health probe, catalog creation, purchase-confirm → inventory + ledger, FIFO sale with tax/discount math (subtotal 600 → +12% tax → 672), over-sell guard, void + restore + reverse ledger, double-void guard, stock adjustment + negative-stock guard, dashboard + all 6 report endpoints, all 4 PDF generators return valid `%PDF` magic-bytes (including `include_header=false`). **7/7 passing**, zero new failures in the broader suite.
- [x] L2. Inline backend smokes for sections B/C/D/E/F/G/H were run after each section landed; all checks passed (catalog FKs, HSN pricing pull-through, FIFO across two batches, draft→confirm propagating MRP+P-Rate back to the medicine master, void restoring stock per-batch, dispense advancing item & Rx status, dashboard KPIs aggregating today's purchase). Click-through equivalents (browser-driven QA) deferred to runtime.

---

## Notes / open follow-ups (for later)

- Cross-module integration with inpatient billing (`Prescription.inpatient_bill_id`) — deferred to a later phase.
- Cross-module integration with EHR (doctor's prescription auto-flows to pharmacy dispensing queue) — deferred.
- License gating: `"pharmacy"` already listed in module registry; ensure it's in the license `features` array before testing on a real license.
