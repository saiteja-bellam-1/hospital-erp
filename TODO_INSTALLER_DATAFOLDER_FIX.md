# Installer data-folder step — fix plan

Symptoms (now fixed):
- "Cannot write to this folder" even when folder is valid
- "Database check failed" even when kthealth_erp.db exists

## Status

- [x] **Gap 1** — Stop using `cmd /C` wrapping for `dbcheck.exe`; trim trailing backslashes
  - `installer/dbcheck/dbcheck.py`: added `--out FILE` global flag, `_emit` writes JSON there when set
  - `installer/installer.iss`: `RunDbCheck` now calls `Exec(DbCheckExePath, ...)` directly with `--out` for the result file (no shell, no double-quote nesting)
  - Added `StripTrailingSlash` and `QuoteArg` helpers; every caller (check-writable, check-db, validate-license, validate-backup-db) now strips trailing `\`/`/` from user-supplied paths before passing them to dbcheck

- [x] **Gap 2** — Relax `check-db` so legitimate existing DBs are recognised
  - Accepts legacy `hospital_erp.db` if `kthealth_erp.db` is missing (warning, not failure)
  - 0 users → warning, not failure (allows reuse of an interrupted setup)
  - WAL/SHM sidecars → warning, not failure (stale -wal after unclean shutdown is benign)
  - Hard failures kept: file empty, file not SQLite, `users` table absent
  - Smoke-tested: legacy filename, 0 users + WAL sidecar, trailing-slash folder

- [x] **Gap 3** — Better default for new data folder
  - `EdNewDataDir` and `EdRestoreDataDir` now default to `{commonappdata}\KTHEALTHERP\data` (= `C:\ProgramData\KTHEALTHERP\data`) instead of `Program Files`

- [x] **Gap 4** — Pre-fill existing-folder field
  - `EdExistingDataDir.Text` now defaults to the same path so a typical reinstall just clicks Next

- [x] **Gap 5** — Surface raw failure when JSON probe finds nothing
  - New `DescribeFailure(Output)` helper: returns the JSON `error` field if present, otherwise truncated raw output, otherwise points at `{tmp}\dbcheck_out.txt`
  - All `MsgBox` failure paths now use it
  - `RunDbIntegrityCheck` populates the memo with raw output even on Exec-level failures

## Build steps to apply on Windows

```cmd
cd installer
build_dbcheck.bat   :: rebuild dbcheck.exe with the --out flag
:: then re-run your installer build (build_installer.bat or equivalent)
```

## Follow-ups (not in this fix, surface if needed)

- `app/services/bootstrap_from_seed.py` may need to handle the legacy `hospital_erp.db` filename when an operator picks a legacy folder via "Use existing data folder". Currently the rest of the app assumes `kthealth_erp.db`.
