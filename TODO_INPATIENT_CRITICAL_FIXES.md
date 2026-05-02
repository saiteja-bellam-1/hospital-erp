# Inpatient Module — Critical Fixes TODO

Started: 2026-04-30

## Task 1 — Bed-allocation row locks
Add `with_for_update()` on Room/Bed reads in:
- [ ] `create_admission` (inpatient.py:739-824)
- [ ] `accept_ward_transfer` (inpatient.py:4609-4621)
- [ ] `convert_reservation_to_admission` (inpatient.py:4924-4995)
- [ ] `update_admission` room/bed change path (inpatient.py:888-980)

SQLite caveat: `SELECT FOR UPDATE` is a no-op on SQLite but works on Postgres/MySQL.
Need to use a portable pattern; SQLite serializes writes via BEGIN IMMEDIATE.

## Task 2 — Discharge: canonical charge calc + balance gate + transactional finalize→discharge
- [ ] `discharge_patient` (inpatient.py:1189-1280) must use `_compute_admission_charges` for total
- [ ] Update `get_discharge_pdf` (inpatient.py:1297-1357) to match
- [ ] Add balance gate: block discharge if balance < 0 unless `discharge_type ∈ {death, against_advice}` or `force=true` with audit
- [ ] Wrap finalize_bill + discharge in single transaction where chained

## Task 3 — Bill uniqueness guard + cancel-bill rolls back source items
- [ ] In `_create_admission_bill_record`: 409 if active final bill already exists for admission
- [ ] On bill cancellation: reset `billed=False` and `bill_id=None` on PatientVisit, OTSchedule, AdmissionAncillaryCharge, Prescription.inpatient_bill_id, PatientLabOrder.inpatient_bill_id

## Status — all four items complete (2026-04-30)

- ✅ Task 1: bed-allocation row locks across `create_admission`, `accept_ward_transfer`, `convert_reservation_to_admission`, `update_admission` via `with_for_update()` plus portable atomic conditional UPDATEs (`_claim_bed_atomic`, `_decrement_room_available_atomic`).
- ✅ Task 2: `discharge_patient` now uses `_compute_admission_charges` for total; new `force_outstanding_balance` + `override_reason` gate; PDF endpoint recomputes canonical breakdown so it always agrees with the bill.
- ✅ Task 3: 409 on duplicate finalize (active final bill exists); new `POST /admissions/{id}/bills/{bill_id}/cancel` releases visits/OT/ancillary/Rx/lab so the admission can be re-billed; payments-present cancellation blocked.
- ✅ Task 4: `convert_reservation_to_admission` now uses `_generate_admission_number(db)` — single canonical `ADM-YYYYMMDD-NNNN` scheme.

Smoke suite: 154 passed (151 original + 3 new).

## Roadmap follow-ups completed

- ✅ Task 6: critical-alert + missing-consent gates added to discharge with three force flags (`force_outstanding_balance`, `force_unacknowledged_alerts`, `force_missing_consents`); `forced_gates` list audit-logged.
- ✅ Task 7: `migrate_inpatient_indexes.py` ensures 46 FK indexes idempotently; wired into startup after `migrate_patient_fields`.
- ✅ Task 8: hourly daemon + `inpatient_daily_charges` service auto-posts one doctor visit per admitted patient per day; `auto_posted` column on `patient_visits`; manual trigger endpoints `POST /admissions/{id}/auto-post-today` and `POST /admissions/auto-post-today/all`.

## Pending

(none)

Smoke suite after roadmap follow-ups: 155 passed.

## Frontend (Task 5) shipped

- `InpatientModule.js` discharge dialog: catches 409 with `code` ∈ {`outstanding_balance`, `unacknowledged_critical_alerts`, `missing_surgical_consent`}, accumulates blockers into a red banner showing the issue + numbers (balance / alert count + parameter names / completed OT count), and requires a single `override_reason` textarea. Submitting attaches the matching `force_*` flags. Submit button switches to destructive variant + "Override and Confirm Discharge" once any gate fires.
- Bills list: Cancel button (red) next to Split for non-cancelled bills. Opens a dedicated dialog with mandatory reason. Calls `POST /admissions/{id}/bills/{bill_id}/cancel`, reads the released-counts response, refreshes bills. `bill_has_payments` 409 is rendered with the actual paid amount. Cancelled bills render with strike-through total + "cancelled" badge and no action buttons.
