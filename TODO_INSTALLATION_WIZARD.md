# Unified Installation Wizard — Plan

Goal: replace the current two-stage flow (Inno Setup file-installer → in-app React `SetupWizard` after first launch) with **one** Inno Setup wizard that collects everything an operator needs to bring up a working install. Windows-only. Mac is explicitly out of scope.

> Status: planning. No code changes yet — awaiting sign-off.

---

## Today's flow (baseline)

1. `build_exe.bat` → PyInstaller → `backend/dist/KTHEALTHERP.exe`
2. `build_installer.bat` → Inno Setup (`installer/installer.iss`) → `KTHEALTHERP_Setup_<v>.exe`
   - Pages: Welcome → Install dir → Tasks (desktop / start-menu / firewall) → Install → "Launch now"
3. First launch (`launcher.py`): picks a free port, creates `data/`, opens browser
4. Browser → React `SetupWizard.js`: hospital info → admin creation → license upload → done

The Phase 1+2 work in `TODO_INSTALLER.md` already covers: license dry-run, machine-ID display, sentinel setup-check, setup rollback, must-change-password, and self-service rebind. Reuse these — do not redo.

---

## Target flow (unified)

A single Inno Setup wizard, run on the operator's machine, with these pages in order:

| # | Page | Source | Notes |
|---|---|---|---|
| 1 | Welcome | Inno Setup default | App name + version |
| 2 | License agreement (EULA) | Inno Setup `LicenseFile=` | Plain text file in `installer/EULA.txt` |
| 3 | Install destination | Inno Setup default | `C:\Program Files\KTHEALTHERP` default |
| 4 | **Data folder** *(new)* | Custom Pascal page | Radio: "Create new data folder" (path picker, default `{app}\data`) **or** "Use existing data folder from previous install" (path picker that validates the folder contains `kthealth_erp.db`). This decides whether step 7-9 are skipped. |
| 5 | **DB integrity check** *(new)* | Custom Pascal page | Only shown if step 4 = "use existing". Runs the bundled `installer\dbcheck.exe` (small Python helper, see below) against the chosen DB; shows ✅/❌ for: file readable, schema present (sentinel `users` table), schema version recorded, no `-journal/-wal` lock files. Block "Next" on failure. |
| 6 | **License file** *(new)* | Custom Pascal page | Optional `.lic` file picker. Shows the machine ID with a Copy button. If a file is picked, runs `dbcheck.exe --validate-license <path>` for a dry-run (signature, machine-ID match, expiry, features). Block "Next" if signature OK but machine-ID mismatch. Allow skip (operator can upload later from the app). |
| 7 | **Hospital details** *(new — only on fresh install)* | Custom Pascal page | Hospital name, address, phone, email. Required: name. |
| 8 | **Admin user** *(new — only on fresh install)* | Custom Pascal page | Username (default `admin`), display name, password + confirm. `must_change_password` is **not** set here — the operator just typed the password. Min 8 chars, mixed case enforced client-side. |
| 9 | Backup destinations *(new — optional)* | Custom Pascal page | Multi-row picker: 0..N folder paths used as mirror destinations (writable check on Next). Defaults to `{app}\data\kthealth_erp_snapshots`. |
| 10 | Tasks | Inno Setup default | Desktop shortcut, Start Menu shortcut, Firewall rule. (Desktop default = checked, matches current behavior.) |
| 11 | Ready | Inno Setup default | Summary of all choices. |
| 12 | Install | Inno Setup default | Copy files, write seed file (see below). |
| 13 | Finished | Inno Setup default | "Launch now" checkbox. |

### Bridging wizard inputs to the running app

Inno Setup's Pascal scripting can't call into Python or run bcrypt. Strategy: the wizard **collects** inputs and writes them to a one-shot `data\install_seed.json` (and password to `data\.install_seed.pwd` with NTFS ACL `Administrators+SYSTEM` only — deleted after consumption). On first launch:

- `launcher.py` looks for `install_seed.json` **before** starting uvicorn.
- If present, it imports a new `app.services.bootstrap_from_seed` which:
  1. Validates the license file path (if any) using existing `license_service.inspect_license_file()`.
  2. Creates the hospital row, the `super_admin` user with bcrypt-hashed password from `.install_seed.pwd`.
  3. Writes backup destinations into `config.json`.
  4. Marks setup complete (sentinel: at least one user row exists — already implemented).
  5. Deletes both seed files. On any failure, halts and surfaces the error in `data/logs/launcher.log` and a tray dialog.
- If absent, current behavior — the app boots and the React `SetupWizard.js` handles fresh setup (kept as the **fallback** path for source installs and recovery).

The "use existing data folder" branch (step 4) skips steps 7–9 entirely; the seed file in that case only carries `{ "data_dir": "...", "license_path": "..." }` and the bootstrap just rebinds paths in `config.json`.

### `dbcheck.exe` helper

A tiny PyInstaller-built binary shipped inside the installer (`installer\bin\dbcheck.exe`). Subcommands:
- `dbcheck check-db <path-to-db>` → exit 0 / non-zero with JSON to stdout for the wizard to parse
- `dbcheck validate-license <path-to-lic>` → same; wraps `license_service.inspect_license_file`
- `dbcheck check-writable <folder>` → for backup destinations
- `dbcheck machine-id` → prints the machine ID for the License page

Built once and committed under `installer/bin/` (or built fresh by `build_installer.bat`). Keeps the Pascal code thin — it just shells out and parses JSON.

---

## Phases

### Phase A — Helper binary + seed-file bootstrap ✅
- [x] **A1.** `installer/dbcheck/dbcheck.py` (machine-id, check-db, validate-license, check-writable). Reuses `app.services.license_service` for Ed25519 verification and `app.utils.machine_id` so the wizard's machine ID matches what the running app reports.
- [x] **A2.** `installer/dbcheck/dbcheck.spec` (PyInstaller one-file) + `installer/build_dbcheck.bat`. Output: `installer/bin/dbcheck.exe`.
- [x] **A3.** `backend/app/services/bootstrap_from_seed.py`. Modes: `fresh` (full DB seed via `app.routes.setup._init_database_and_seed` + license apply via `_store_license` + backup config) and `adopt_existing` (rebind config.json to the chosen folder). Success deletes both seed files; failure preserves them and writes traceback to `data/.bootstrap_status.json`.
- [x] **A4.** `backend/launcher.py` invokes `consume_seed_if_present(exe_dir)` between version-bump check and `uvicorn.run`. Failures are logged but don't crash the launcher (React `SetupWizard` still works as fallback).
- [x] **A5.** `backend/tests/test_bootstrap_from_seed.py` — 7 tests covering no-seed, fresh, adopt, idempotent re-run, malformed seed, missing existing DB, unknown mode. All passing (full suite: 204 passing, was 197).

### Phase B — Inno Setup wizard pages ✅
- [x] **B1.** EULA dropped per user decision.
- [x] **B2.** `installer/installer.iss` rewritten with 6 custom Pascal pages: DataFolder, DbCheck, License, Hospital, Admin, Backup. Helpers: `RunDbCheck`, `JsonHasOkTrue`, `ExtractJsonError`, `JsonEscape`. Seed file written in `CurStepChanged(ssPostInstall)`; password file ACL-locked via `icacls /inheritance:r /grant SYSTEM:F /grant *S-1-5-32-544:F`. ShouldSkipPage skips license/hospital/admin in adopt mode and the DB-check page in fresh mode.
- [x] **B3.** `[Files]` ships `installer\bin\dbcheck.exe` twice — once with `Flags: dontcopy` (extracted to `{tmp}` for wizard-time use) and once installed to `{app}` (so the admin can re-run checks).
- [x] **B4.** `[Setup]` left at `AppVersion=1.1.0` default, `AppId` unchanged for in-place upgrade compatibility.
- [x] **B5.** `installer/README.md` rewritten end-to-end with the new flow.

### Phase C — In-app wizard cleanup ✅
- [x] **C1.** `frontend/src/pages/SetupWizard.js` welcome step now shows an amber "fallback" banner explaining this UI only appears when the installer wizard was skipped (source installs / recovery).
- [x] **C2.** No code change needed — the wizard is already gated by `/api/setup/status` which uses the sentinel users-table probe (`is_setup_complete()`). When bootstrap_from_seed creates the admin row, the wizard never renders.
- [x] **C3.** Bootstrap status is already exposed at `data/.bootstrap_status.json` for the existing Diagnostics endpoint to surface (no extra wiring needed; the file is written by `_write_status` in `bootstrap_from_seed.py`).

### Phase D — GitHub Actions Windows build ✅
- [x] **D1.** `.github/workflows/windows-build.yml` shipped. Triggers: push to `main`, PRs against `main`, `workflow_dispatch`, and tag pushes `v*`. Steps: checkout → derive version → patch APP_VERSION → setup Python 3.11 + Node 20 → install Inno Setup via Chocolatey → `build_exe.bat` → `installer\build_dbcheck.bat` → `build_installer.bat` → upload artifact (and create GitHub Release on tag pushes). Caching: pip + npm via setup-* `cache:`.
- [x] **Versioning rule.** Tag `v1.2.3` → version `1.2.3` (also publishes a Release). Any other trigger → `<MAJOR.MINOR>.<github.run_number>` where `<MAJOR.MINOR>` is parsed from `backend/launcher.py`'s `APP_VERSION`. The patched `APP_VERSION` flows through to the launcher's diagnostics page and the installer filename, so all three are guaranteed in sync.
- [x] **Code signing stub.** Workflow notes how to wire `SIGNING_CERT_BASE64` + `SIGNING_PASS` once a cert is available. Skipped silently until then.
- [x] **First green run:** [#6](https://github.com/saiteja-bellam-1/hospital-erp/actions/runs/25471601823) → `KTHEALTHERP_Setup_1.1.6.exe` (75 MB). Took 4 commits to land — issues fixed along the way: `wmic` removed in Server 2025, `uvloop` has no Windows wheels, CRA `CI=true` lint-as-error, Inno Setup preprocessor mistaking `#8:` Pascal char literal for a directive, `TNewEdit.Password` is `PasswordChar`.

### Phase E — Docs ✅
- [x] **E1.** `installer/README.md` rewritten with new wizard flow + smoke-test checklist.
- [x] **E2.** Root README install section — left untouched. The installer/README.md is the authoritative doc and the root README's "Installation" section already points at it. Will revisit if the root README becomes stale after a build.

---

## Files to create / change

**New**
- `installer/EULA.txt`
- `installer/dbcheck/dbcheck.py`
- `installer/dbcheck/dbcheck.spec`
- `installer/build_dbcheck.bat`
- `installer/bin/dbcheck.exe` (build output, gitignored — produced by CI)
- `backend/app/services/bootstrap_from_seed.py`
- `backend/tests/test_bootstrap_from_seed.py`
- `.github/workflows/windows-build.yml`

**Changed**
- `installer/installer.iss` — six new custom pages + `[Files]` + `LicenseFile`
- `installer/README.md` — new flow docs
- `backend/launcher.py` — call `bootstrap_from_seed` before `uvicorn.run`
- `frontend/src/pages/SetupWizard.js` — fallback banner + short-circuit when bootstrap already ran
- `build_installer.bat` — build `dbcheck.exe` before invoking ISCC
- `README.md` — update install section + add CI badge
- `.gitignore` — add `installer/bin/`

**Untouched**
- `install_and_setup.py` (source-install dev path)
- License Manager (`license-manager/`)
- `migrate_*.py`, `schema_migrations.py`

---

## Decisions (answered)

1. ~~EULA~~ — **No EULA page.** Drop step 2 from the wizard table; do not set `LicenseFile=`.
2. **Admin username** — force operator to pick. No prefilled value, validate non-empty + no whitespace.
3. **Existing data folder** — adopt-existing only. No `.zip` import path in the wizard.
4. **Code signing in CI** — stub. Workflow has the signtool step gated on a `SIGNING_CERT_BASE64` secret that is currently unset; skipped silently.
5. **Release cadence** — auto-publish a GitHub Release on `v*` tag push, attach the installer `.exe`.

> **Phase D (GitHub Actions) is deferred** until the user authenticates GitHub on this machine. Phases A → B → C → E proceed first; the workflow YAML will be added at the end.
