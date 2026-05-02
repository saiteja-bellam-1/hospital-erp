# TODO: Auto-seed full role set + permission matrix on startup

## Goal
Fresh installs and existing installs should always have all hospital roles
(`inpatient_admin`, `billing_admin`, `pharmacy_admin`, `frontdesk`, etc.) with
their default granular permission matrix, without manually running
`setup_hospital_roles.py`.

## Bugs found in current code
1. `backend/app/routes/setup.py` `role_names` (line 333) seeds only 8 roles —
   missing `inpatient_admin`, `billing_admin`, `pharmacy_admin`, `frontdesk`.
2. `backend/app/routes/setup.py` `_seed_role_permissions` only has a "lean"
   inpatient grant (`manage_beds`, `admit_patients` etc.), not the ~54 granular
   keys defined in `setup_hospital_roles.py`.
3. `setup_hospital_roles.py` `role_permissions_map` has duplicate keys
   `billing_admin` (line 326 & 346) and `frontdesk` (359 & 416) — the second
   silently overwrites the first; the inpatient grants on `billing_admin` and
   `frontdesk` get lost.
4. Module permission catalog (`ModulePermission` table, used by the Role
   Permissions admin UI) is never seeded by the wizard or on startup — only by
   the manual `setup_hospital_roles.py` script.

## Tasks
- [x] Research current seeding paths and identify gaps
- [x] Add missing roles (`inpatient_admin`, `billing_admin`, `pharmacy_admin`, `frontdesk`) to `role_names` in `setup.py`
- [x] Replace `_seed_role_permissions` map with the comprehensive matrix (and fix the duplicate-key bug)
- [x] Add `_seed_module_permissions` helper in `setup.py` that seeds `ModulePermission` rows
- [x] Wire `_seed_module_permissions` and the role-existence check into `_ensure_role_permissions` in `main.py` so existing DBs heal on next startup
- [x] Verify by running backend startup on the existing `kthealth_erp.db`

## Result
All 12 system roles now seeded automatically (super_admin, hospital_admin, doctor,
nurse, lab_admin, lab_technician, pharmacy_admin, pharmacist, billing_admin,
inpatient_admin, frontdesk, receptionist). The `_ensure_role_permissions()` startup
hook now also calls `_seed_roles` and `_seed_module_permissions`, so existing DBs
(like `kthealth_erp.db`) heal on next backend start. Verified: `inpatient_admin`
got 33 inpatient + 3 EHR permissions seeded.
