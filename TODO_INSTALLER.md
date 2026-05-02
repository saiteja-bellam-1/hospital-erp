# Installer Overhaul — Tracking

Audit produced 25 numbered items grouped into five phases. **All five phases
shipped.** Tests: 197 passing.

---

## Phase 1 — Security baseline ✅

- [x] **1. Remove hardcoded fallback passwords.** `install_and_setup.py` no longer seeds `superadmin/admin123` or `hospitaladmin/hospital123`. The setup wizard is the only path that creates the admin user.
- [x] **2. `must_change_password` flag.** New boolean on `users`; surfaced on login + `/me`. New `POST /api/auth/change-password`. Frontend forced-change dialog blocks UI until the user picks a new password. Admin reset-password sets the flag, so the recipient is forced to pick their own password on next login. (Also fixed a pre-existing typo where admin reset wrote to `user.hashed_password` instead of `user.password_hash`.)
- [x] **3. Skip demo data.** Demo Hospital + `hospitaladmin` removed from `install_and_setup.py`; the wizard already only created the operator's hospital.
- [x] **9. Sentinel-table check in `is_setup_complete()`** — replaced the "DB file >0 bytes" heuristic with `SELECT 1 FROM users LIMIT 1`.
- [x] **10. Setup rollback.** Failure during `_init_database_and_seed` deletes the partial DB + `-journal/-wal/-shm` sidecars so the next attempt starts clean.

## Phase 2 — License + backup install UX ✅

- [x] **4. Wizard license step.** New License step in the Setup Wizard. Shows the machine ID with copy button, accepts an optional `.lic` upload, and runs a dry-run check on it (signature valid? bound to this machine? plan? expiry? features?). Setup actually persists the license now (`_store_license` was a no-op before). If the file is for a different machine, the wizard refuses to advance until you swap it or skip the step.
- [x] **5. Self-service license rebind.** New `GET /api/license/rebind-request` (admin only) downloads a signed JSON request file containing the original `license_id`, the new machine ID, and a SHA-256 proof of the original `.lic`. New License Manager endpoint `POST /api/licenses/process-rebind` consumes that file, verifies the proof against the stored copy of the original license, and re-issues a fresh `.lic` for the new machine. The original license is marked `rebound` in the manager's DB. Frontend: "Generate Rebind Request" button on `LicenseManagement.js`. (Item 7 — restore UI — was already implemented in `BackupManagement.js`; verified during this phase, no changes needed.)
- [x] **24. Dry-run "test before applying."** New `POST /api/license/validate` (no auth) returns license metadata + machine-ID compatibility without touching the DB. Used by both the wizard and the new "verify-before-apply" flow on the License Management page (file picker now produces an inspect card with Apply/Cancel buttons instead of immediately committing).

---

## Phase 3 — Windows installer polish ✅
- [x] **12.** `build_exe.bat` rewritten: each step writes its own log under `build_logs\<timestamp>\`, hard-stops on first failure, and tails the last 50 lines of the failed step's log so the user sees the cause immediately.
- [x] **13.** New `installer/installer.iss` (Inno Setup 6) wraps `KTHEALTHERP.exe` in a real Windows installer with Start Menu + Desktop entries, an uninstaller registered in Apps & Features, and an optional Windows Firewall rule for the launcher's port range. `data\` is intentionally excluded from the install payload (created at runtime by `launcher.py`) and the uninstaller asks before wiping it. Built via `build_installer.bat`. Docs at `installer/README.md`.
- [x] **14.** `launcher.create_desktop_shortcut` no longer fails silently — every outcome (`created`, `skipped_existing`, `skipped_no_desktop`, `failed`) is written to `data/.shortcut_status.json`, and a new admin endpoint `GET /api/system/diagnostics` exposes it for an admin Diagnostics view.
- [x] **15.** Optional code-signing hook in both build scripts. Looks for `SIGNING_CERT` / `SIGNING_PASS` / `SIGNING_TIMESTAMP` env vars and runs `signtool sign` + `signtool verify` on both the `.exe` and the wrapping installer. Skipped silently if `SIGNING_CERT` is unset (so dev builds Just Work). EV certificate recommended to bypass SmartScreen — documented in `installer/README.md`.

## Phase 4 — Reliability ✅
- [x] **6.** Already shipped — `start_snapshot_backup()` writes timestamped snapshots to `kthealth_erp_snapshots/` per backup location with configurable interval + retention. Verified during this phase, no changes needed.
- [x] **8.** New `app/utils/schema_migrations.py` owns a `schema_migrations` table that records every migration run (name, status, error, timestamps, duration). `main.py` startup now wraps `migrate_patient_fields` and `migrate_inpatient_indexes` with `run_migration()` and **raises** on failure instead of silently `print()`-ing — the app refuses to boot rather than serving a half-migrated DB. History exposed via the admin Diagnostics endpoint.
- [x] **11.** `backend/requirements.lock` generated via `pip freeze` (52 transitive pins). `build_exe.bat` and `install_and_setup.py` both prefer the lockfile when present, fall back to `requirements.txt` when not (e.g. fresh checkout).
- [x] **19.** New admin-only `GET /api/system/health-check` returns a green/red checklist: DB reachable + writable, all schema migrations succeeded, license installed + not expired, frontend assets bundled (when running as .exe), backup destinations writable per location. Suitable for a post-install wizard or a tile in the admin dashboard.
- [x] **20.** New per-location mirror status (`_per_location_mirror_status` keyed by destination path). `GET /api/backup/mirror-status` now includes a `per_location` map with `last_success`, `last_error`, `last_attempt`, and a live `writable` probe per destination. Health check uses the same source.

## Phase 5 — Ops + docs ✅
- [x] **17.** Launcher now embeds an `APP_VERSION` constant and writes it to `data/version.txt` on every boot. Upgrades (version mismatch) are recorded in `data/.upgrade_history.json`. The schema-migrations tracker from Phase 4 handles the data side; the launcher just records the bump for the Diagnostics page. Documented in the new "Upgrading In Place" section of the README.
- [x] **18.** New `uninstall.py` at repo root — interactive Y/N prompts (or `--yes` for CI). Removes `backend/venv`, `frontend/node_modules`, build artifacts, and `build_logs/`. Customer data is preserved by default; `--purge-data` also wipes the DB, uploads, and `config.json`.
- [x] **21.** Launcher rotates logs to `data/logs/launcher.log` (1MB per file, 5 backups). New admin endpoint `GET /api/system/logs?lines=N` returns the tail (10–5000 lines). Already-shipped `GET /api/system/diagnostics` now also returns migration history, upgrade history, and the recorded version. The frontend can render this as a Diagnostics tab; the API is in place.
- [x] **22.** README rewritten with new sections: **Upgrading In Place** (drop-in `.exe` replacement, schema-migration runner, rollback) and **Troubleshooting** (license rebind, failed-upgrade recovery, dead backup destination, sentinel setup-check, missing default creds, forced-password-change dialog, shortcut creation). Tech stack section was already current.
- [x] **25.** Already shipped — `BackupManagement.js` (frontend) covers `db-migrate` (move the DB to a new folder) and full `backup_locations` CRUD via `PUT /api/backup/locations`. Verified during this phase, no additional UI needed.

---

## Files touched (Phases 1 + 2)

**Backend**
- `backend/app/models/user.py` — `must_change_password` column
- `backend/migrate_patient_fields.py` — column migration
- `backend/app/routes/auth.py` — `POST /change-password`, expose flag in responses
- `backend/app/routes/admin.py` — reset-password sets flag, fixes wrong field name
- `backend/app/routes/setup.py` — License storage; sentinel-check; rollback w/ sidecar cleanup
- `backend/app/routes/license.py` — `/validate` (dry-run), `/rebind-request` (download)
- `backend/app/services/license_service.py` — `inspect_license_file()` helper
- `backend/app/utils/config.py` — `is_setup_complete()` queries users table

**License Manager**
- `license-manager/backend/app.py` — `POST /api/licenses/process-rebind`

**Frontend**
- `frontend/src/contexts/AuthContext.js` — surface `must_change_password`
- `frontend/src/components/ForcePasswordChangeDialog.js` — new (blocks UI)
- `frontend/src/App.js` — render dialog when flag is true
- `frontend/src/pages/SetupWizard.js` — new License step + machine ID + dry-run
- `frontend/src/pages/modules/LicenseManagement.js` — verify-before-apply, rebind button

**Other**
- `install_and_setup.py` — stripped of user/hospital seeding
- `README.md` — dropped default-credentials section

**Phase 5 additions**
- `backend/launcher.py` — `APP_VERSION` constant, `setup_logging()` to `data/logs/launcher.log` (rotating), `check_version_bump()` writes `data/version.txt` + `.upgrade_history.json`
- `backend/app/routes/system.py` — `/api/system/logs` returns log tail; `/api/system/diagnostics` adds migration history + upgrade history + recorded_version
- `uninstall.py` (new, repo root) — source-install uninstaller with `--purge-data` + `--yes` flags
- `README.md` — new "Upgrading In Place" + "Troubleshooting" sections

**Phase 4 additions**
- `backend/app/utils/schema_migrations.py` (new) — schema_migrations table + run_migration runner
- `backend/main.py` — fail-loud migration wrapping
- `backend/requirements.lock` (new) — pinned transitive deps
- `backend/app/utils/config.py` — per-location mirror status tracking + `get_per_location_status()`
- `backend/app/routes/system.py` — `/api/system/health-check` + migration history in `/api/system/diagnostics`
- `backend/app/routes/backup.py` — `mirror-status` now includes `per_location`
- `build_exe.bat`, `install_and_setup.py` — prefer requirements.lock when present

**Phase 3 additions**
- `build_exe.bat` — per-step log files, hard-stop, log-tail on failure, optional code signing
- `build_installer.bat` (new) — Inno Setup wrapper compile + optional installer signing
- `installer/installer.iss` (new) — Inno Setup script with shortcuts, uninstaller, firewall rule, data-preserving uninstall
- `installer/README.md` (new) — Windows installer build + signing docs
- `backend/launcher.py` — record shortcut creation outcome to `data/.shortcut_status.json`
- `backend/app/routes/system.py` — `GET /api/system/diagnostics` admin endpoint surfaces the shortcut status
