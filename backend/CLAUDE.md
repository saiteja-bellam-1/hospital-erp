# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Product

**KT HEALTH ERP** — Hospital management system for local network deployment. Sold as a Windows .exe bundle or run from source. Supports direct sales and 3rd party vendor (seller) distribution via the license system.

## Development Commands

### Backend (FastAPI)
```bash
cd backend
source venv/bin/activate              # macOS/Linux
./venv/bin/python main.py             # Start server on port 8000
./venv/bin/python migrate_patient_fields.py  # Run column migrations
./venv/bin/python -c "from app.routes.lab import router; print('OK')"  # Verify imports
```

### Frontend (React)
```bash
cd frontend
npm start                             # Dev server on port 3000 (proxies to :8000)
npx react-scripts build               # Production build
```

### License Manager (separate app)
```bash
cd license-manager/backend
python app.py                         # Runs on port 9000
```

### Windows .exe Build
```bash
cd backend
build_exe.bat                         # npm build → pip install → pyinstaller
```

## Architecture

### Backend (`backend/`)
- **Framework**: FastAPI + SQLAlchemy + SQLite (`kthealth_erp.db`)
- **Entry point**: `main.py` — registers all routers, runs migrations on startup, starts mirror backup
- **Database**: Lazy-initialized engine via `_EngineProxy` in `config/database.py` to support setup wizard changing DB path at runtime
- **Auth**: JWT (HS256, 24h expiry), bcrypt passwords, multi-role users via `user_role_association` many-to-many table
- **Permission chain**: super_admin/hospital_admin bypass → module enabled check → license features check → role-module permission check

### Key Backend Patterns
- **Routes**: `backend/app/routes/` — each file is a router with prefix (e.g., `/api/lab`, `/api/appointments`)
- **Models**: `backend/app/models/` — SQLAlchemy models, tables auto-created via `create_all()`
- **Migrations**: `migrate_patient_fields.py` has a `NEW_COLUMNS` list — add new columns here, they're idempotent (checks "already exists")
- **PDF generation**: `app/utils/pdf_service.py` using ReportLab — bills, prescriptions, lab reports all support `include_header` toggle
- **Permission decorator**: `require_permission(Modules.LAB, "read")` — use on route dependencies
- **Audit logging**: Hybrid — `AuditMiddleware` (automatic) + explicit `log_action()` calls in routes

### Frontend (`frontend/`)
- **Framework**: React 18 + Tailwind CSS + shadcn/ui (Radix UI primitives)
- **Routing**: `App.js` → `Dashboard.js` (main layout with sidebar nav, role-based route rendering)
- **Auth**: `AuthContext.js` — stores token + user + licenseStatus in localStorage, global axios 401 interceptor
- **Module gating**: `enabledModules` object from `/api/system/enabled-modules` controls nav visibility and route access
- **Pages**: `frontend/src/pages/modules/` — one file per dashboard/module, reception pages in `reception/` subdirectory

### Print/PDF Pattern (uniform across app)
All PDF printing follows: fetch PDF → blob URL → preview dialog with embedded iframe → "Include header" checkbox (re-fetches PDF) → Print via hidden `iframe.contentWindow.print()` → cleanup with `revokeObjectURL`. Shared utility at `frontend/src/utils/printPdf.js`.

### License System
- **Crypto**: Ed25519 signing — license data is base64-encoded JSON + signature in `.lic` file
- **License Manager** (`license-manager/`): Separate app for generating/managing licenses with customer tracking, seller/vendor management, payment tracking
- **Hospital side**: Upload `.lic` → `license_service.py` verifies signature + machine ID → stores in DB → modules auto-enabled/disabled based on `features` array
- **Seller info**: Embedded in signed license payload, auto-populates footer and support contact page
- **Module gating**: A module is enabled only if BOTH admin toggle is on AND license includes it in features

### Multi-Role System
- Users have primary `role_id` (FK) + many-to-many `roles` via `user_role_association` table
- `current_user.role_names` returns all role names (used in permission checks)
- `hasRole()` / `hasAnyRole()` helpers in frontend Dashboard.js

### Lab Module
- **4 order creation points**: `create_orders` (doctor), `reception_book_lab_tests` (reception), `book_package` (packages), `create_consultation_lab_orders` (consultation) — all enforce duplicate checking via `_check_duplicate_orders()`
- **Abnormal detection**: Auto-detected for numeric/select fields via reference ranges, additive manual checkbox for all field types
- **Parameters**: Support 10 field types (numeric, less_than, greater_than, positive_negative, reactive, presence_absence, cloudy_clear, manual, text, select) with gender/age-specific reference ranges stored as JSON
- **Bill regeneration**: `POST /api/lab/orders/regenerate-bill` — re-generates bill PDF with header toggle without payment side effects

### Setup Wizard
- First launch (no `config.json`): frontend shows `SetupWizard` instead of login
- `backend/app/routes/setup.py`: `/api/setup/status` and `/api/setup/complete`
- After wizard: user logs in and uploads `.lic` file via Dashboard > License
- Backward compat: if DB file already exists, `is_setup_complete()` returns True

### Backup System
- SQLite backup API for safe copies (not `shutil.copy2`)
- Mirror backup: background thread syncs every 60 seconds to configured locations
- Config stored in `config.json`

### Windows Packaging
- PyInstaller bundles FastAPI + React build + SQLite into `KTHEALTHERP.exe`
- `backend/app/utils/paths.py`: `get_db_path()`, `get_uploads_dir()`, `get_frontend_dir()` detect `sys.frozen` for bundled mode
- Data persists in `data/` folder next to .exe
- Server binds `0.0.0.0` with CORS `*` for LAN access

## Important Conventions

- Product name: **KTHEALTHERP** (brand), **KT HEALTH ERP** (display)
- Patient identified by UUID `patient_id` in some APIs, integer `id` in others — check the endpoint
- All bill/report PDFs support header toggle via `include_header` parameter
- `referred_by` is a free-text field on patients, appointments, and lab orders
- Frontend uses relative API URLs (no hardcoded localhost) — works on any origin via proxy/LAN
- Consultation duration is configurable per doctor (2-120 min) via AvailabilityModule
- Module enable/disable respects license — unlicensed modules can't be enabled by admin
