# TODO — Remove React Setup Wizard — DONE

## Tasks

- [x] 1. Moved seeding helpers from `backend/app/routes/setup.py` into
       new module `backend/app/services/db_seed.py`:
       - `SYSTEM_ROLES`, `_INPATIENT_ALL`
       - `init_database_and_seed(seed: dict, db_path)` — plain dict input
       - `store_license(content, db_path)`
       - `_seed_roles`, `_seed_module_permissions`, `_seed_role_permissions`
       - `apply_additive_migrations`, `upsert_modules_and_permissions`
- [x] 2. `bootstrap_from_seed.py` now imports from `db_seed`; no longer
       depends on `app.routes.setup`.
- [x] 3. `backend/app/routes/setup.py` deleted entirely (~1380 lines).
- [x] 4. `backend/main.py`: dropped `setup` import, dropped
       `app.include_router(setup.router, ...)`, redirected `_ensure_role_permissions`
       to import from `app.services.db_seed`.
- [x] 5. `frontend/src/pages/SetupWizard.js` deleted.
- [x] 6. `frontend/src/App.js`: removed `SetupWizard` import,
       `/api/setup/status` fetch, `setupComplete` state, and the
       wizard render branch. App now always renders Login/Dashboard.
- [x] 7. Migrated `browse-folder` and `validate-path` from setup.py to
       `backup.py` (kept usable by BackupManagement); updated
       `BackupManagement.js` to use `/api/backup/browse-folder`.
- [x] 8. Removed `/api/setup*` skip rules from `audit_middleware.py`,
       `license_middleware.py`, `maintenance.py`.
- [x] 9. Updated `backend/hospital_erp.spec` — replaced `app.routes.setup`
       hidden import with `app.services.db_seed`.
- [x] 10. Updated `backend/app/services/bootstrap_from_seed.py` docstring
        — no longer mentions React fallback.
- [x] 11. All 229 backend tests pass (1 skipped, 0 failures).
- [x] 12. Frontend parse check on App.js + BackupManagement.js passes.
- [x] 13. Backend restarted; `/api/setup/*` returns 404,
        `/api/backup/browse-folder` works, `/api/backup/health/public` works.

## Surface area after the change

**Single install path:** Inno Setup wizard collects hospital info, admin user,
license, backup paths → writes `<data-dir>/install_seed.json` +
`<data-dir>/.install_seed.pwd`. On first launch, `bootstrap_from_seed`
applies them and the React app boots straight to Login.

**Dev / source installs:** must either run the Windows installer in a VM, or
supply a hand-written `install_seed.json` + `.install_seed.pwd` under
`backend/data/` before launching the backend.

**Backend routes removed:** `/api/setup/status`, `/api/setup/complete`,
`/api/setup/inspect-data-file`, `/api/setup/staged-rebind-request`,
`/api/setup/validate-replacement-license`, `/api/setup/browse-folder` (moved),
`/api/setup/validate-path` (moved), `/api/setup/debug-permissions`.
