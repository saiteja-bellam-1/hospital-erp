# Billing & PDF Priority Fixes

## Task 1 — Fix `printPdfFromUrl` API mismatch
- [ ] Update `frontend/src/utils/printPdf.js` signature to `(pdfUrl, options = {})` accepting `{ include_header, filename, headers }`
- [ ] Fetch as authenticated blob (so token is sent + works in bundled .exe), build object URL, set iframe src to blob URL
- [ ] Append `include_header` query param when passed
- [ ] Verify all ~13 call sites still work (no API change for single-arg callers)

## Task 2 — Seller footer on every PDF
- [ ] Add `_draw_footer(canvas, doc, seller_info)` helper in `backend/app/utils/pdf_service.py`
- [ ] Footer text: "Powered by KT HEALTH ERP — Sold by {vendor}" when seller present, else "Developed by KT Health Soft"
- [ ] Wire footer via `onFirstPage` / `onLaterPages` page templates in every `generate_*_pdf`
- [ ] Pass `seller_info` from callers (pull from License table; helper in pdf_service to accept hospital_info that already contains it, or add a separate arg)
- [ ] Audit all 19 generators — header style/subname drift also normalised where cheap

## Task 3 — Package double-bill + room handling
Package data model already supports it:
- `SurgeryPackage.included_services` = JSON array of categories (room, doctor_visit, nurse_visit, procedure, ot, surgery, pharmacy, lab, ancillary)
- `included_room_type`, `included_stay_days`, `excess_per_day_charge`, `base_price`
- `AdmissionPackage.agreed_price`

Display choice: **Hide included, lump sum only**.

- [ ] In `_compute_admission_charges` (inpatient.py:3086) accept `admission_package` arg. When present:
  - Drop visit/OT/ancillary/pharmacy/lab subtotals for categories in `included_services`
  - Replace room subtotal with package room logic (below)
  - Always-charge categories (those NOT in `included_services`) remain itemised
- [ ] Room logic:
  - Compute per-day actual room charges day-by-day (handle bed transfers, LOA — existing logic)
  - For included days (`day_index < included_stay_days`):
    - If `actual_room_type == included_room_type` → charge 0 (covered)
    - Else → charge `actual_rate - included_rate` (upgrade differential, clamp ≥0)
  - For excess days (`day_index >= included_stay_days`) → charge full `actual_rate` (NOT `excess_per_day_charge`; that field becomes legacy/fallback)
- [ ] Add "Surgery Package" line item at `agreed_price` to bill subtotal
- [ ] `_create_admission_bill_record` (inpatient.py:3579) — pass admission_package through; reject if package present and operator-edited items_override fights the inclusions (or trust override — document)
- [ ] Frontend Bill tab — when package applied, show breakdown: Package row, Room upgrade row (if any), Excess days row, Uncovered categories itemised
- [ ] Test in `test_billing_comprehensive.py`: packaged admission with matched room, upgraded room, excess days, uncovered pharmacy

## Task 4 — Bill cancellation: split-aware + transactional + audit
- [ ] `cancel_admission_bill` (inpatient.py:3484): block when any `BillSplit.payment_status == "received"` exists (currently only checks `Payment`)
- [ ] Wrap cancellation in try/except with `db.rollback()`; same for `_create_admission_bill_record` (inpatient.py:3579)
- [ ] After release of each source row (visits/OT/ancillary/prescriptions/lab/food), write `log_action` with bill_id + source row id
- [ ] `create_bill_split` (inpatient.py:6305): reject if `Bill.status == "cancelled"`
- [ ] `record_split_payment` (inpatient.py:6363): reject if `Bill.status == "cancelled"`; add hospital scoping
- [ ] Audit log on `delete_deposit`, `remove_admission_package`, OT cancel
- [ ] Fix `delete_deposit` tzinfo crash on naive datetimes

## Task 5 — Race-safe numbering
- [ ] Wrap `_create_admission_bill_record` Bill-insert in try/except `IntegrityError`, retry up to 5 times re-reading MAX(seq)+1
- [ ] Same for `_generate_deposit_number` (inpatient.py:5355) — wrap caller insert
- [ ] No schema change

## Bonus quick wins (batch with above)
- [ ] Clamp percentage discount and tax_percentage to ≤100% in `_create_admission_bill_record`
- [ ] `get_bill_pdf` accept `?bill_id=` query param; allow `status == "cancelled"` with CANCELLED watermark; add INTERIM watermark
- [ ] Use `generate_refund_receipt_pdf` (red/all-caps) for refund deposits instead of overloaded `generate_deposit_receipt_pdf`

## Out of scope (deferred)
- `generate_bill_split_pdf` per-payer invoice
- Refund-after-bill-cancel Payment flow
- Balance sign convention unification across backend/frontend/PDF
