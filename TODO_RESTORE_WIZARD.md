# TODO — Restore-aware setup wizard (DONE)

## Tasks

### Backend
- [x] 1. `backend/app/utils/schema_version.py` — `SCHEMA_VERSION=1`,
       `get_db_schema_version`, `stamp_schema_version`, `compatibility`.
- [x] 2. `is_setup_complete()` no longer falls back to "DB exists at default path".
       Wizard always runs unless `config.json` says `setup_complete=true`.
- [x] 3. `_init_database_and_seed()` stamps `schema_version` on fresh installs.
- [x] 4. `POST /api/setup/inspect-data-file` — uploads `.db` or `.zip`,
       stages in temp dir, returns integrity/tables/schema/hospital/users/
       license/uploads info + staging_token.
- [x] 5. `GET /api/setup/staged-rebind-request?token=...` — rebind request
       built from staged DB.
- [x] 6. `POST /api/setup/validate-replacement-license` — verifies signature
       + machine binding + matching license_id; stashes on staging entry.
- [x] 7. `POST /api/setup/complete` branches on `mode`. Restore path:
       copy staged DB → target, copy uploads, run additive migrations,
       upsert modules/permissions/roles (additive), stamp schema_version,
       apply replacement license if present. Skips admin/hospital creation.
- [x] 8. Staging TTL cleanup (1h, swept on every inspect call and dropped
       on successful complete).

### Frontend
- [x] 9. Branching `STEPS` based on `formData.mode` (fresh vs restore).
- [x] 10. New "Data Source" step with Fresh / Restore cards.
- [x] 11. New "Import Data" step — file upload, inspect preview card
        (integrity, schema compat, hospital, users, uploads, license/binding).
- [x] 12. License step gains a restore-mode branch with rebind download +
        replacement license upload UI when binding fails.
- [x] 13. `handleComplete()` posts `mode` and `staging_token` for restore.
- [x] 14. Review step shows different summary for restore vs fresh.

### Smoke
- [x] 15. Backend imports clean.
- [x] 16. Compatibility checker behaves correctly (None, 1, 99).
- [x] 17. SetupWizard.js parses cleanly.

## Notes
- Restore refuses to overwrite a non-empty DB at the target path — operator
  must remove or pick an empty location.
- Uploads import is additive (per-file copy); existing live uploads are not
  deleted.
- Schema version: forward-incompatible imports refused; older/legacy DBs
  allowed with a warning since additive migrations heal them on startup.
- The replacement license must match the staged DB's `license_id` (guards
  against accidentally pasting in an unrelated license).
