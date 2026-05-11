# TODO — Runtime machine-ID binding enforcement (DONE)

Problem: license machine_id was only checked at upload time. If a user copied
the DB to a new machine, the stored license kept working because nothing
re-verified the binding at runtime.

## Tasks

- [x] 1. `verify_license_machine_binding(license_record)` helper in
       `backend/app/services/license_service.py` — re-parses
       `raw_license_data` and compares the signed `machine_id` to
       `get_machine_id()`.
- [x] 2. `STATUS_MACHINE_MISMATCH = "machine_mismatch"` constant; exposed in
       `get_license_status()` (with `machine_match`, `license_machine_id`,
       `current_machine_id`).
- [x] 3. `is_license_valid_for_login()` blocks non-admin roles when binding is
       broken; admins can still log in to fix it.
- [x] 4. `LicenseMiddleware` cache also re-verifies binding; surfaces
       `X-License-Status: machine_mismatch`.
- [x] 5. Frontend `LicenseBanner` shows `machine_mismatch` with the backend's
       rebind message (existing rebind UI in `LicenseManagement.js` is the
       recovery path).
- [x] 6. Smoke import check passed.

## Notes

- Legitimate hardware change (NIC swap, hostname change) is treated the same
  as a migration — the operator must use the existing rebind flow at
  `/dashboard/license` to request a fresh `.lic`.
- Old licenses without a `machine_id` field are still treated as bound
  (skip check), preserving backward compatibility with legacy installs.
- Cache TTL is 5 minutes; on license re-upload `invalidate_license_cache()` is
  already called.
