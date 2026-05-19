# IPD Lab Order — Tech Visibility + Payment Cascade

## Problem
1. Lab tech queue filters `payment_status == 'paid'` (lab.py:1336-1338) → IPD lab orders (always `pending` until bill settle) are invisible to technicians.
2. IPD lab orders' `payment_status` is never flipped to `paid` even after the admission bill is fully settled. Same gap exists for `Prescription`.

## Tasks
- [ ] **T1**: Allow lab techs to see IPD orders regardless of payment status. Change filter at `lab.py:1336-1338` to `(payment_status=='paid') OR (admission_id IS NOT NULL)`.
- [ ] **T2**: Cascade payment status on IPD bill settle. In `record_split_payment` (`inpatient.py:5657`), after flipping the split to `received`, check if all splits for the bill are now `received`. If yes, flip `PatientLabOrder.payment_status` and `Prescription.payment_status` to `'paid'` for rows where `inpatient_bill_id == bill.id`.
- [ ] **T3**: Edge case — bills with no splits at all. If a bill is settled without using the BillSplit mechanism, the cascade won't fire. Investigate whether there's a single-payer settle path; if so, hook in there too.
- [ ] **T4**: Manual verification — list endpoints and reports filtering by `payment_status=='paid'` (lab.py:1337, 1757, 1869) will now correctly include IPD orders post-settle.
