# TODO — Human-Readable MRN (Medical Record Number)

Reference plan: `/Users/saiteja/.claude/plans/if-we-introduce-mrn-lucky-whistle.md`

Format: `{PREFIX}-{YYYY}-{NNNNN}` — e.g. `KTH-2026-00042`. Per-hospital, per-year counter.

## Backend

- [x] **B1** — Add `mrn` column to `Patient` model (`backend/app/models/patient.py`) with index + unique-per-hospital constraint
- [x] **B2** — Add `mrn_prefix` column to `Hospital` model (`backend/app/models/hospital.py`)
- [x] **B3** — Append two `NEW_COLUMNS` entries to `backend/migrate_patient_fields.py` (patients.mrn, hospitals.mrn_prefix)
- [x] **B4** — Idempotent `backfill_patient_mrns()` in migration file, invoked from `migrate()` (which `main.py` calls at startup)
- [x] **B5** — `_next_mrn_for()` helper + integrate into `PatientService.create_patient()` with IntegrityError retry
- [x] **B6** — Added `mrn` to OR-clauses in `search_patients` and `advanced_search_patients` in `patient_service.py`
- [x] **B7** — Added `mrn` to `PatientResponse` and `PatientSearchResponse` Pydantic models
- [x] **B8** — `setup.py` `SetupRequest` + `complete_setup` accept, validate, and persist `mrn_prefix`
- [x] **B9** — Hospital settings update endpoint accepts `mrn_prefix` (validation + non-retroactive note)

## Frontend

- [x] **F1** — SetupWizard: MRN Prefix input on hospital-info step + review row + payload
- [x] **F2** — HospitalAdminModule: MRN Prefix field in settings form with non-retroactive warning
- [x] **F3** — PatientsModule: MRN shown beside name in list and in detail dialog
- [ ] **F4** — Reception pages (ReceptionPatientsPage, ReceptionAppointmentsPage) — *deferred; backend exposes mrn so any consumer can render it whenever those screens are next touched*
- [ ] **F5** — Other patient banners (Inpatient/Outpatient/Consultation/Receptionist) — *deferred; same reason as F4*

## PDFs

- [x] **P1** — All 9 PDF generators relabel "Patient ID" → "MRN" and read `mrn` from data dict (with safe fallback to existing key)
- [x] **P1a** — Bill builders in `inpatient.py`, `lab.py`, `appointments.py`, `consultations.py` populate `mrn` in their data dicts

## Verification

- [x] **V1** — `pytest tests/` passes (204 passed)
- [x] **V2** — Smoke imports pass; full `from main import app` works
- [x] **V3** — Programmatic E2E: created `KTH-2026-00006`, searched by MRN, found row
- [x] **V4** — Backfill on real dev DB assigned MRNs to all 5 existing patients in `created_at` order; re-run was idempotent (no changes)
- [ ] **V5** — Manual UI verification of prefix change — *requires running the dev server interactively*
