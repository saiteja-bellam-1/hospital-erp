# TODO — Show patient age in lab report & prescription PDFs

Problem: PDFs already have an "Age / Gender" field, but age resolves only from `patient.date_of_birth`. Patients registered with the `age` column (no DOB) render as blank.

Fix: fall back to `patient.age` when DOB is absent. No new input field; no DB change.

## Tasks
- [x] Research current behavior (PDF templates, call sites, Patient model)
- [x] `backend/app/routes/lab.py` — added `_patient_age()` helper; updated all 6 call sites
- [x] `backend/app/routes/prescriptions_simple.py` — fall back to `patient.age`
- [x] Import check passed
