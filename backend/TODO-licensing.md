# Licensing System Implementation TODO

## Backend
- [x] 1. Install `cryptography` package (already installed)
- [x] 2. Create `app/licensing/__init__.py`
- [x] 3. Create `app/licensing/crypto.py` — Ed25519 verification + license parsing
- [x] 4. Create `app/models/license.py` — License SQLAlchemy model
- [x] 5. Create `app/services/license_service.py` — validation, caching, status checks
- [x] 6. Create `app/routes/license.py` — upload & status endpoints
- [x] 7. Create `app/middleware/license_middleware.py` — per-request license check
- [x] 8. Create `tools/generate_license.py` — vendor CLI for generating .lic files
- [x] 9. Modify `main.py` — add middleware + license router
- [x] 10. Modify `app/routes/auth.py` — license check on login
- [x] 11. Run DB migration for `licenses` table

## Frontend
- [x] 12. Create `LicenseBanner.js` — warning/expiry banner
- [x] 13. Create `LicenseManagement.js` — admin license upload/status page
- [x] 14. Modify `AuthContext.js` — store license status
- [x] 15. Modify `Dashboard.js` — show banner + add nav item

## Testing
- [x] 16. Generate test license and verify end-to-end flow
