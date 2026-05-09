# TODO — DB restore from backup file

Two scenarios to enable restoring a hospital from a single `kthealth_erp.db`
backup file (e.g. one received over USB / OneDrive / email):

1. **At install time** (Inno Setup wizard)
2. **From inside a running app** (Backup Management page)

Existing in-app restore already works for *configured* backup folders
(manual / snapshot / mirror) — see `backend/app/routes/backup.py`
`/restore/list` + `/restore`. The gap is **arbitrary file upload**.

---

## Scenario 1 — Installer

- [x] Add `MODE_RESTORE = 2` constant + a 3rd radio on `DataFolderPage`:
      *"Restore from a backup database file"*.
- [x] Inputs in restore mode:
      - target data folder (must be empty / writable)
      - path to a `.db` file (file picker filtered to `*.db`)
- [x] Add `cmd_validate_backup_db(path)` to `installer/dbcheck/dbcheck.py`:
      verifies SQLite header, runs `PRAGMA integrity_check`, confirms
      a `users` table is present.
- [x] Wizard `NextButtonClick` for `DataFolderPage` in `MODE_RESTORE`:
      run `check-writable <data>` then `validate-backup-db <file>`,
      block on either failure.
- [x] In `MODE_RESTORE`, skip License / Hospital / Admin pages
      (settings come from the backup). Keep the Backup Destinations page.
- [x] `ShouldSkipPage` updated for the new mode.
- [x] `WriteSeedFile` writes a third JSON shape:
      ```json
      { "mode": "restore_backup",
        "data_dir": "...",
        "backup_file_path": "...",
        "backup_locations": ["...", "...", "..."] }
      ```
- [x] `bootstrap_from_seed.py` — add `_apply_restore(seed)`:
      ensure data_dir exists & has no existing DB → SQLite
      `.backup()` from the source file into `<data>/kthealth_erp.db`
      → write `config.json` with `setup_complete=true` + db_path +
      backup_locations → `reinitialize_engine()` →
      run `migrate_patient_fields.migrate()` so the restored DB picks
      up any newer columns.

## Scenario 3 — In-app upload restore

- [x] Backend: `POST /api/backup/restore-upload` (multipart)
      - accepts a `.db` file
      - writes to a temp path
      - re-uses the same validation + restore steps as `/restore`
        (header check, integrity, pre-restore safety backup, replace
        live DB, reinit engine, restart mirror/snapshot threads).
      - returns the same shape as `/restore`.
- [x] Frontend: in `BackupManagement.js`, add an "Upload Backup File"
      button next to the existing Refresh button on the Restore card.
      Confirm dialog reuses the same warning text and force-logout flow.
- [x] No new permission key — existing `_require_admin` covers it.

## Notes / decisions

- Restore in installer uses SQLite `.backup()` API rather than
  `shutil.copy2` to match what the in-app restore does and to avoid
  shipping a corrupted DB if the source happens to be open.
- Don't try to restore the `uploads/` tree from a single `.db` file —
  that's only available when the backup folder layout is intact (the
  configured-folder restore path already does this where possible).
- Pre-restore safety: in-app restore writes a `pre_restore_*.db` to
  the first configured backup location. The installer scenario starts
  from an empty target, so no pre-restore step needed there.
