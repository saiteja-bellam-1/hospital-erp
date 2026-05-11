# Lab bills — centralised view and grouped download (DONE)

## Status

- [x] **Schema** — `lab_bill_group_id` + `lab_bill_number` added to `PatientLabOrder` (`backend/app/models/lab.py`) and registered in `migrate_patient_fields.NEW_COLUMNS` so existing installs auto-migrate on startup.
- [x] **Bill emission sites** stamp both columns:
  - `reception_book_lab_tests` — every order in a multi-test booking shares one group/number
  - `book_package` — every order in a package booking shares one group/number
  - `generate_lab_bill` (patient pay-all) — every paid pending order shares one group/number
  - `update_order_payment` (single-order pay) — orders without an existing group get assigned one
- [x] **New endpoint** `GET /api/lab/bills/{group_id}/pdf?include_header=...` rebuilds the original combined PDF (multi-test or package) with no payment side effects.
- [x] **Billing list grouping** — `/api/hospital/billing` now collapses lab orders by `lab_bill_group_id`. Pre-migration ungrouped orders keep the old per-row behavior so legacy bills are still listed and downloadable.
- [x] **Frontend BillingDashboard** — per-row PDF Download button. Routes to:
  - `lab` rows with group → `/api/lab/bills/{group_id}/pdf`
  - `lab` legacy ungrouped → `/api/lab/orders/{id}/bill`
  - `consultation` → `/api/appointments/{id}/bill/download`
  - `admission` → `/api/inpatient/admissions/{id}/bill/pdf`
- [x] **LabTechDashboard** — per-order "Bill" button + the bill preview dialog removed. Users now see all bills (combined as originally generated) on the Billing page.
- [x] **Smoke** — `pytest tests/test_inpatient_smoke.py` passes 197/197. Frontend lint clean (only pre-existing unused-import warnings remain).

## Verification on Windows / production

After upgrade, confirm:
1. Server starts (auto-migration runs and adds the two new columns).
2. Book a package or a multi-test reception lab booking → Billing dashboard shows ONE row, not N.
3. Click the PDF button → downloaded PDF matches what was issued at booking time (same items, same total, same discount).
4. Old (pre-upgrade) lab orders still appear individually with a working Download button.
