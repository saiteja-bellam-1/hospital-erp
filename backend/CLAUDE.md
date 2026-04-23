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

### Two permission decorators

| Decorator | Use when | Example |
|---|---|---|
| `require_feature_permission(module, permission_name)` | **Preferred for new routes.** Granular — checks for one specific permission key. | `require_feature_permission(Modules.INPATIENT, "finalize_bill")` |
| `require_permission(module, action)` | Legacy — action-bucket check (`read`/`write`/`delete`/`admin`). Still used by outpatient/lab/pharmacy routes. | `require_permission(Modules.LAB, "write")` |

All 141 inpatient routes now use `require_feature_permission` with one of ~54 granular permission keys defined in `setup_hospital_roles.py`. See the "Inpatient permission vocabulary" section below or run `GET /api/admin/module-permissions?module_name=inpatient` for the live catalog.

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
- **Critical value alerts** (ICU add-on): `LabTestParameter.critical_low`/`critical_high` define thresholds. `POST /api/inpatient/lab-orders/{id}/scan-critical` with a `{parameter_id: value}` map auto-creates `CriticalLabAlert` rows, surfaced as a red banner in the inpatient admission view.

### Inpatient Module (the big one)

**Lifecycle:** Reservation (optional) → Pre-auth (optional) → Admission → stay → Discharge (with mortality flow if death) → Final bill + TPA split → Quality reports.

**Primary tables** (`backend/app/models/inpatient.py`):
- Admissions core: `Admission`, `DischargeRecord`, `RoomManagement`, `Bed`, `InpatientRateConfig`
- Clinical: `PatientVisit`, `NursingNote`, `DietOrder`, `VitalSigns`, `MedicationAdministration`, `FluidBalance`
- Consents/incidents: `ConsentTemplate`, `Consent`, `Incident`
- Billing: `AdmissionDeposit`, `AncillaryServiceCatalog`, `AdmissionAncillaryCharge`, `SurgeryPackage`, `AdmissionPackage`, `BillSplit`
- Insurance: `InsurancePreAuth`, `InsurancePreAuthExpansion`, `TPACompany`
- Operations: `BedTransferHistory`, `BedTurnoverLog`, `BedReservation`, `NurseAssignment`, `NurseShiftRoster` (duty schedule, independent of admissions)
- OT: `OTSchedule` (with `surgeon_fee`/`anaesthetist_fee`/`ot_room_charge`/`equipment_charge`/`consumables_charge`/`other_charges` for billing integration)
- Critical alerts: `CriticalLabAlert`
- `AdmissionDocument` (file uploads)

**Bill calculation:** `_compute_admission_charges(admission, unbilled_only)` in `routes/inpatient.py` is the single source of truth. It returns room + visits + OT + ancillary + pharmacy + lab totals, with support for package mode (agreed price + excess) and proper double-billing prevention via `bill_id` FKs on PatientVisit/OTSchedule/AdmissionAncillaryCharge/Prescription.inpatient_bill_id/PatientLabOrder.inpatient_bill_id.

**Readmission detection:** On every admission create, lookup the patient's most recent `DischargeRecord`; if within 30 days, mark `is_readmission=True` + `previous_admission_id` + `days_since_last_discharge`.

**Bed housekeeping:** On discharge, the structured bed is auto-flipped from `occupied` → `cleaning` (logged in `BedTurnoverLog`). Cleaning beds are excluded from room `available_beds` count. Housekeeping view lists them and toggles back to `available` when ready.

**Inter-ward transfer accept flow:** `POST /admissions/{id}/transfer-ward` creates a `pending` BedTransferHistory entry. The actual bed/room change only happens when receiving ward calls `PATCH /transfers/{id}/accept`.

**Mortality flow:** Discharge with `discharge_type="death"` creates the DischargeRecord; `PUT /admissions/{id}/discharge/mortality` then enriches it with `cause_of_death`, `time_of_death`, MLC info, autopsy, body handover. `GET /admissions/{id}/death-certificate/pdf` generates the certificate.

**Inpatient permission vocabulary** (~54 granular keys, all live under module `"inpatient"`):
- Read: `view_occupancy`, `view_vitals`, `view_mar`, `view_io`, `view_bill`, `view_documents`, `view_readmissions`, `view_mortality`
- Admission ops: `admit_patients`, `update_admission`, `discharge_patients`, `record_mortality`, `transfer_beds`, `initiate_ward_transfer`, `accept_ward_transfer`
- Rooms/beds: `manage_beds`, `manage_wards`, `set_room_rates`, `manage_housekeeping`, `manage_reservations`, `assign_nurses`, `view_roster`, `manage_roster`
- Clinical: `record_vitals`, `record_io`, `administer_medications`, `manage_nursing_notes`, `manage_diet_orders`, `manage_allergies`, `record_visits`
- Orders: `order_labs`, `prescribe_medications`
- OT: `schedule_ot`, `record_ot_charges`
- Billing: `generate_interim_bill`, `finalize_bill`, `manage_packages`, `manage_ancillary_charges`, `receive_deposits`, `issue_refunds`, `manage_bill_splits`
- Insurance: `update_claim_status`, `manage_preauth`, `manage_tpa`
- Quality: `record_consent`, `withdraw_consent`, `report_incident`, `investigate_incident`, `close_incident`, `acknowledge_critical_alert`
- Catalogs: `manage_ancillary_catalog`, `manage_surgery_packages`, `manage_consent_templates`, `set_critical_thresholds`
- Docs: `upload_documents`, `delete_documents`

**Default role→permission matrix** (seeded in `setup_hospital_roles.py`, overridable via the Role Permissions admin UI at `/dashboard` → Hospital Administration → Role Permissions):

| Permission group | nurse | doctor | inpatient_admin | billing_admin | receptionist/frontdesk |
|---|:---:|:---:|:---:|:---:|:---:|
| Clinical (vitals/MAR/I/O/nursing) | ✓ | ✓ |   |   |   |
| Admissions (admit/discharge) |   | ✓ | ✓ |   | partial (admit only) |
| Record mortality |   | ✓ |   |   |   |
| Bed/ward management + housekeeping | partial (housekeeping + accept) |   | ✓ |   |   |
| Reservations |   |   | ✓ |   | ✓ |
| Nurse assignments |   |   | ✓ |   |   |
| Bill preview | ✓ | ✓ | ✓ | ✓ | ✓ |
| Interim bill / finalize / refund / splits |   |   |   | ✓ |   |
| Receive deposits |   |   | ✓ | ✓ | ✓ |
| Pre-auth + claim status |   |   | ✓ | ✓ |   |
| TPA catalog |   |   |   | ✓ |   |
| Ancillary/packages catalogs |   |   |   | ✓ |   |
| Ancillary charges (per admission) |   |   | ✓ | ✓ |   |
| OT schedule |   | ✓ | ✓ |   |   |
| OT charges |   |   | ✓ | ✓ |   |
| Consents (record) | ✓ | ✓ |   |   |   |
| Consents (withdraw) |   | ✓ |   |   |   |
| Incidents (report) | ✓ | ✓ | ✓ |   |   |
| Incidents (investigate/close) |   |   | ✓ |   |   |
| Critical alert acknowledge | ✓ | ✓ |   |   |   |

**super_admin** and **hospital_admin** bypass all checks at the decorator level.

**Role-permission admin UI:** `HospitalAdminModule.js` → "Role Permissions" tab. Lists non-admin roles, shows the module-permission catalog grouped by category (user/admin), checkbox grid with description + bulk Select-All/Clear-All, save writes to `PUT /api/admin/roles/{role_id}/permissions`. Changes audit-logged via `log_action("update_role_permissions", ...)`.

### Inpatient PDFs

All generated by `app/utils/pdf_service.py` with the standard `include_header` toggle:
- Bill (`generate_bill_pdf`) — itemised charges with discount/tax
- Prescription (`generate_prescription_pdf`)
- Lab report (`generate_lab_report_pdf`, `generate_combined_lab_report_pdf`)
- Discharge summary (`generate_discharge_summary_pdf`)
- Deposit receipt (`generate_deposit_receipt_pdf`) — handles both inflow and refund copies
- Consent form (`generate_consent_pdf`) — template content + signatures section
- Death certificate (`generate_death_certificate_pdf`) — mortality + body-handover block

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
