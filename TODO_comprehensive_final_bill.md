# Comprehensive Final Bill Implementation

## Goal
Final bill should be a comprehensive statement showing ALL admission charges
(prior interim bill items + new unbilled items), not just new unbilled ones.

## Tasks

- [x] 1. Backend: Fix billing dashboard `total_charges` — use final bill total when one exists (no double-counting)
- [x] 2. Frontend: `openReviewBillDialog` — fetch ALL items (billed + unbilled), mark prior items with `is_prior`
- [x] 3. Frontend: Review dialog UI — show "Previously Billed" vs "New Charges" sections
- [x] 4. Unit tests: `backend/tests/test_billing_comprehensive.py` covering full billing flow (28 pass, 2 skipped)
- [x] 5. Backend: Fix `_admission_balance_summary` double-counting (use final bill total when one exists)

## Key Insight
- Backend `finalize_bill` uses `unbilled_only=True` breakdown for STAMPING (correct)
- `items_override` from frontend will contain ALL items (prior + new) → comprehensive total
- `_create_admission_bill_record` with `items_override` already stamps only breakdown records ✅
- Only needed: dashboard fix + frontend comprehensive items build
