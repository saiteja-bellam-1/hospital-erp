# TODO: Installer edge-case hardening

Goal: make first-run installation smoother by catching the soft spots identified in the flow audit. Scope is install-time UX only — runtime behaviour is unchanged.

**Status: all four implemented and smoke-tested.**

## Fixes (in priority order)

### 1. Warn when Fresh data folder already contains a DB  ✅
**Problem**: Fresh-install path doesn't reject a non-empty target folder. If `kthealth_erp.db` already exists there, the seed bootstrap opens it in place and may corrupt or silently merge state.

**Fix**:
- `installer/installer.iss` — in `NextButtonClick(DataFolderPage)` MODE_FRESH branch, after the `check-writable` call, also call `dbcheck check-db <folder>`.
- If `details.exists == true`, MsgBox `mbConfirmation`: *"This folder already contains a KT HEALTH ERP database (kthealth_erp.db, N users). A fresh install will reuse this database and may corrupt it. Continue?"* — default No.
- If folder contains other (non-DB) files, softer warning: *"This folder is not empty. Continue?"*
- Need a tiny shell-side probe — `dbcheck check-writable` already returns ok; add `dbcheck dir-info <folder>` that reports `{empty, has_db, has_other_files}`, OR just reuse `check-db` (already returns `exists` flag).

**Files**: `installer/installer.iss` (NextButtonClick), `installer/dbcheck/dbcheck.py` (only if we need a new sub-command — likely just reuse check-db).

### 2. Surface license expiry at install time  ✅
**Problem**: `dbcheck validate-license` checks signature + machine-ID but ignores expiry. Operator can install with an expired .lic and only discover at runtime that modules are disabled.

**Fix**:
- `installer/dbcheck/dbcheck.py` `validate-license` → include `days_remaining` + `status` (active / expiring_soon / expired) in the JSON report. `license_inspect.compute_license_status` already exposes this; just expose to the CLI output.
- `installer/installer.iss` `OnVerifyLicense` → when status is "expired", show RED label "EXPIRED — runtime will be restricted. Upload a renewal in-app or pick a different file." Don't block; operator may have a renewal queued. When "expiring_soon" (≤30 days), show yellow note with days remaining.
- Add a Ready-page confirmation: if a license was selected AND it's expired, MsgBox at the end *"The license you selected is expired. Proceed anyway?"* (default Yes — allow but flag).

**Files**: `installer/dbcheck/dbcheck.py`, `installer/installer.iss` (LicensePage, NextButtonClick).

### 3. Reject CSV username = admin-username at install time  ✅
**Problem**: User CSV is validated against existing DB usernames, but at install time the admin user doesn't exist yet — collision only surfaces at first-launch bootstrap, leaving the CSV file abandoned with an error in `.bootstrap_status.json`.

**Fix**:
- `installer/dbcheck/dbcheck.py` `validate-users-csv` → accept new optional flag `--reserved-username <name>` (and `--reserved-email <addr>`). Inject into the duplicate-detection set used by `parse_and_validate`.
- `installer/installer.iss` `OnValidateUsers` → pass `--reserved-username "<EdAdminUser.Text>" --reserved-email "<EdAdminEmail.Text>"`.
- Validation error becomes immediate ("username 'admin' is reserved for the super_admin you configured on the previous page") instead of post-bootstrap silent failure.

**Files**: `installer/dbcheck/dbcheck.py`, `backend/app/services/user_csv_import.py` (extend `parse_and_validate` signature to accept extra reserved sets), `installer/installer.iss` (OnValidateUsers args).

### 4. Add a watchdog timeout to dbcheck subprocess calls  ✅ (Python-side self-kill, not WinAPI)
**Problem**: Inno's `Exec(..., ewWaitUntilTerminated, ...)` has no timeout. A dbcheck run against a slow UNC share or a hung antivirus scanner hangs the wizard with no cancel button.

**Fix**:
- Replace the current `Exec` call inside `RunDbCheck` with a Pascal helper that uses `CreateProcessW` + `WaitForSingleObject(hProcess, 20000)` + `TerminateProcess` on timeout. Read stdout from a temp file as today.
- On timeout, return `{"ok": false, "error": "dbcheck timed out after 20s"}` so the caller's existing error-display path shows it.
- Different timeouts per command: machine-id 5s, check-writable/check-db 15s, validate-license 10s, validate-backup-db 30s (backups can be large), validate-users-csv 15s.

**Files**: `installer/installer.iss` (RunDbCheck + a small WinAPI helper proc).

**Flag as optional**: this is the biggest implementation by far. If you'd rather defer, leave it out and we ship #1-#3.

## Out of scope (kept as-is)
- Machine-ID mismatch already non-blocking with a clear message — intentional, useful for VMs.
- `.install_seed.pwd` ACL recovery is already handled by `_try_unlock_pwd_file`.
- Cross-platform source-mode bootstrap — documented, intentional.

## Verification plan
After implementation, manually walk through each scenario once:
- Fresh into a folder with existing `kthealth_erp.db` → confirmation prompt.
- Fresh into folder with random files → soft warning.
- Adopt an existing valid DB → still passes.
- Restore over existing DB → still blocked.
- Upload expired .lic → red label, can still proceed.
- Upload a .lic for a different machine → existing block message.
- CSV with `username=admin` matching the admin set on the previous page → validation rejects immediately.
- Point CSV at a non-existent UNC path → timeout fires within 15s (if #4 included).

No backend Pythonside changes needed apart from `user_csv_import.parse_and_validate` accepting the reserved-username set (#3).
