# TODO — CSV user import (installer wizard + in-app)

## Decisions (locked in 2026-05-29)
1. **Passwords**: plaintext in CSV; force `must_change_password=True` on first login.
2. **Installer CSV scope**: "normal" users only — exclude `doctor` and `nurse` roles. Allowed roles for installer-time CSV:
   - hospital_admin, lab_admin, lab_technician, pharmacy_admin, pharmacist,
     billing_admin, inpatient_admin, frontdesk, receptionist
   - Reject `super_admin` (already created from AdminPage) and `doctor`/`nurse` (handled via dedicated in-app importers).
3. **Duplicates** (username OR email already exists, or duplicated within file): **block** the whole import with a row-level error report. No partial apply.

## In-app importers (separate, post-install)
- Hospital Administration → "Import Doctors (CSV)" — extra columns: `specialization`, `qualifications`, `default_consultation_duration`, `consultation_fee`, etc. Creates User + DoctorProfile.
- Hospital Administration → "Import Nurses (CSV)" — extra columns: `shift_preference`, `ward_assignment` (optional).
- Both reuse the core CSV parser/validator from the installer path.

## CSV schema (installer "general users")
```
username,email,first_name,last_name,role,password,phone,additional_roles
```
- `additional_roles` is `;`-separated, optional.
- Required: username, email, first_name, last_name, role, password.
- Password ≥ 8 chars.
- Within-file uniqueness on `username` and `email`.

## Wizard placement
`Welcome → SelectDir → DataFolder → DbCheck → License → Hospital → Admin → Backup → UsersPage(NEW) → Ready → ...`
Skip `UsersPage` unless `MODE_FRESH`.

## Task list
- [ ] **T1** — Add `app/services/user_csv_import.py`: pure parser + validator + applier.
  - `parse_and_validate(path, allowed_roles, existing_usernames=None, existing_emails=None) -> (rows, errors)`
  - `apply_users(db, rows, hospital_id) -> {created, errors}` (atomic — rollback on any DB-level error since duplicates are blocking).
- [ ] **T2** — Hook into `bootstrap_from_seed._apply_fresh`:
  - Read `users_csv_path` from seed, run `parse_and_validate` with `allowed_roles = INSTALLER_ROLES` (excludes doctor/nurse/super_admin), then `apply_users`.
  - Add `users_import: {created, errors}` block to `.bootstrap_status.json`.
  - Delete `install_users.csv` on success; keep on any error so operator can fix and retry.
- [ ] **T3** — `dbcheck.exe`: add `validate-users-csv <path>` command (pure-Python, no sqlalchemy). Emits `{ok, count, errors[]}` JSON line. Hard-coded allowed-role list mirrors backend constant.
- [ ] **T4** — `installer.iss`:
  - Add `UsersPage` after `BackupPage`, only for `MODE_FRESH`.
  - Fields: file picker, Validate button (calls dbcheck), Skip button, status memo.
  - Block `NextButtonClick` unless empty (skipped) or validation passed.
  - Copy chosen CSV to `{app}\data\install_users.csv` in `WriteSeedFile`.
  - Add `"users_csv_path"` to the fresh-seed JSON.
  - Ship a `users_sample.csv` template via `[Files]` + a "Download sample" button.
- [ ] **T5** — Pytest: `backend/tests/test_user_csv_import.py`
  - Happy path (3 valid users, mix of additional_roles).
  - Duplicate username within file → blocks all.
  - Duplicate email vs existing DB user → blocks all.
  - Disallowed role (doctor/nurse/super_admin) → blocks all.
  - Short password → blocks all.
  - Verify `must_change_password=True` and password verifies with `verify_password`.
- [x] **T6** — In-app importers — DONE.
  - `POST /api/admin/users/bulk-import-doctors` + `/bulk-import-nurses` + `/bulk-import-sample/{role}` in `app/routes/admin.py`.
  - `parse_and_validate_doctors` / `parse_and_validate_nurses` + `apply_doctors` / `apply_nurses` in `user_csv_import.py`.
  - Doctor importer also seeds a `DoctorAvailability` row with the chosen `default_consultation_duration` so the slot generator works out-of-the-box.
  - Frontend: `frontend/src/pages/modules/admin/BulkUserImport.js`, mounted as a "Bulk Import" tab in HospitalAdminModule.
  - Tests: `tests/test_bulk_import_endpoints.py` (6), additions to `tests/test_user_csv_import.py` (10 doctor/nurse cases).

## Notes / risks
- `must_change_password` column — confirm it already exists on the User model from the installer-overhaul work (it should, per memory `installer_overhaul.md`). If missing, add to `migrate_patient_fields.NEW_COLUMNS`.
- dbcheck spec excludes sqlalchemy — keep `user_csv_import.py` import-clean of `sqlalchemy` at module level so dbcheck can import the validator half. (Apply half stays in a separate module that does import sqlalchemy.)
- Order in `_apply_fresh`: run CSV import AFTER `store_license` so a license failure doesn't waste user creation, and so all roles + hospital_id are in place.
