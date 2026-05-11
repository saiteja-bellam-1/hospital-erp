# TODO — Backup hardening (Phase 1 + Phase 2) — DONE

## Phase 1 — Close data-loss holes

- [x] 1.1 Snapshots include `uploads/`. Folder layout
       `kthealth_erp_snapshots/snapshot_YYYYMMDD_HHMMSS/{kthealth_erp.db,
       uploads/}`. Legacy loose-file snapshots still listed in `get_snapshot_info`.
- [x] 1.2 Verify every backup write. `app/utils/backup_verify.py` —
       sha256 + integrity check + sidecar JSON. Mirror uses quick_check,
       snapshot/manual/gdrive use full integrity_check. Gdrive aborts before
       upload if pre-upload verify fails.
- [x] 1.3 Global backup health banner. `app/services/backup_health.py` +
       `GET /api/backup/health` + `GET /api/backup/health/public`.
       `frontend/src/components/BackupHealthBanner.js` rendered next to
       LicenseBanner in Dashboard.js, polls every 90s.
- [x] 1.4 Maintenance-mode middleware. `app/middleware/maintenance.py`
       wired into `main.py`. Restore wraps swap, blocks writes via 503.
       `frontend/src/components/MaintenanceModal.js` listens for `503 +
       maintenance:true` via custom event from AuthContext interceptor.
- [x] 1.5 Post-restore verification. `_verify_restored_db()` in
       backup.py runs integrity_check + users probe; on failure, reverts
       from pre-restore safety copy and 500s with reason.

## Phase 2 — Operational safety

- [x] 2.1 On-demand test-restore. `POST /api/backup/test-restore` copies
       latest mirror + newest snapshot into tempfiles, runs full verify,
       persists result to `system_settings.backup_test_results`.
       `GET /api/backup/test-restore/last` reads it back. (Weekly thread
       deferred — easy to wire as a `start_test_restore_thread` later;
       the endpoint is the meaningful surface.)
- [x] 2.2 Disk-usage + distinct-device check. `POST /api/backup/locations/check`
       returns `valid` + warnings/errors using `shutil.disk_usage` and
       `os.stat().st_dev` (POSIX) / `GetVolumeInformationW` (Windows).
- [x] 2.3 Audit-log significant transitions. `app/services/backup_audit.py`
       — rate-limited (1/hr/category). Mirror calls `record_location_transition`
       on first failure and first recovery. Retention update + test-restore +
       failed-restore each emit one event.
- [x] 2.4 Configurable retention. `snapshot_retention_days` is now the
       canonical key (default 7); legacy `snapshot_retention_hours` still
       read for backward compatibility via `_resolve_snapshot_retention_days`.
       New endpoint `PUT /api/backup/retention-config`.
- [x] 2.5 Pre-swap machine binding check. `_validate_backup_db_file` now
       reads the candidate DB's License row and runs
       `verify_license_machine_binding` before allowing /restore or
       /restore-upload to proceed.

## Tests

- [x] T.1 `tests/test_backup_verify.py` — 6 cases: healthy, corrupt header,
       empty file, missing file, quick_check path, source_sha256 recording.
- [x] T.2 `tests/test_backup_health.py` — 6 cases: no locations, disabled,
       healthy, stale, broken, mixed broken+healthy.
- [x] T.3 `tests/test_maintenance_mode.py` — 5 cases: writes allowed when
       inactive, blocked when active, GET passes, exempt paths pass,
       state toggles.
- [x] T.4 `tests/test_backup_pipeline.py` — 6 e2e cases: manual backup,
       mirror, snapshot+uploads, retention-days resolution, corruption
       reported via verified=false, users-table sentinel.
- [x] T.5 All 23 new tests pass plus existing 206 tests still green
       (229 total / 1 skipped / 0 failures).
- [x] T.6 Backend smoke import test green.
- [x] T.7 Frontend parse check on all changed JS files green.

## Files touched

Backend (new):
  - `backend/app/utils/backup_verify.py`
  - `backend/app/services/backup_audit.py`
  - `backend/app/services/backup_health.py`
  - `backend/app/middleware/maintenance.py`
  - `backend/tests/test_backup_verify.py`
  - `backend/tests/test_backup_health.py`
  - `backend/tests/test_maintenance_mode.py`
  - `backend/tests/test_backup_pipeline.py`

Backend (edited):
  - `backend/app/utils/config.py` — verify in run_backup / run_mirror_sync
    / run_snapshot / run_gdrive_backup; folder-layout snapshots with uploads;
    `_resolve_snapshot_retention_days`; `last_verified` per-location.
  - `backend/app/routes/backup.py` — `_verify_restored_db`; expanded
    `_validate_backup_db_file` (sentinel + machine binding); restore wrapped
    in maintenance mode + post-restore verify + revert; new endpoints:
    `/health`, `/health/public`, `/locations/check`, `/retention-config`,
    `/test-restore`, `/test-restore/last`, `/maintenance`. Pre-restore
    pruning helper.
  - `backend/main.py` — wire `MaintenanceMiddleware`.

Frontend (new):
  - `frontend/src/components/BackupHealthBanner.js`
  - `frontend/src/components/MaintenanceModal.js`

Frontend (edited):
  - `frontend/src/App.js` — mount `MaintenanceModal`.
  - `frontend/src/contexts/AuthContext.js` — axios 503 → `app:maintenance` event.
  - `frontend/src/pages/Dashboard.js` — mount `BackupHealthBanner`.

## Deferred to Phase 3 (per earlier plan)
  - Encryption at rest for backups
  - Independent off-site backup (S3 / SFTP)
  - Periodic cross-location reconciliation / self-heal
  - Weekly auto-test-restore *thread* (the on-demand endpoint covers the
    same surface; a cron-style runner is a 30-line follow-up)
