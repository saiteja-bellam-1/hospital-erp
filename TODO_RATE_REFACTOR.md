# Rate Management Refactor — Plan & TODO

**Status:** Planning complete, awaiting approval before execution.
**Created:** 2026-04-19

## Goal

Move per-role hospital-wide visit rates to **per-user rates** (set on the user record) and introduce a **Procedure catalog** with default rates that auto-fill OT schedule charges.

## Decisions (confirmed with user)

| # | Question | Decision |
|---|----------|----------|
| 1 | Doctor visit rate vs. existing `inpatient_fee_inr` | **Same field — reuse `inpatient_fee_inr`**, do not add a new column |
| 2 | Fallback when rate not set | **None — required at user creation** for doctor/nurse roles |
| 3 | Procedure catalog UI location | **New tab in InpatientModule** |
| 4 | Procedure → OT charge behavior | **Auto-fill, user can override** |
| 5 | Existing admission/visit rows | **Leave as-is** (charges already recorded on rows) |

## Scope summary

**Doctor & Nurse:** reuse the **same existing `User.inpatient_fee_inr` column** for both roles. The form shows the "Inpatient Fee" input whenever the user being created/edited has a doctor *or* nurse role. Required when either role applies. No new user column.

**Procedure:** new `Procedure` model with `name` + `default_rate`. Catalog managed from a new "Procedures" tab in InpatientModule. Selecting a procedure when creating an OT schedule auto-fills `OTSchedule.other_charges` (or a new `procedure_charge` column — see decision below) with the catalog rate; the user can edit before saving.

**Hospital-wide `InpatientRateConfig`:** deprecated. The "Billing Setup" tab in InpatientModule loses its rate fields (or the whole tab goes away). Existing rows in the table are left untouched but no longer read.

## Sub-decisions (resolved 2026-04-19)

- **A. Procedure → OT charge mapping:** ✅ Add a new `OTSchedule.procedure_charge Numeric(10,2)` column. Auto-fill from catalog `default_rate`. Keeps `other_charges` free for unrelated extras.
- **B. Surgeon/anaesthetist fee auto-fill:** ✅ When surgeon picked, default `OTSchedule.surgeon_fee` from that user's `inpatient_fee_inr`. Same for anaesthetist. Both editable.
- **C. Procedure dropdown UX:** ✅ Catalog dropdown with **free-text fallback** — when user types a name not in the catalog, allow saving the OT schedule with that free-text `procedure_name` and no auto-fill.
- **D. Permissions matrix:** ✅ `manage_procedures` granted to `hospital_admin` only. `view_procedures` granted to `hospital_admin`, `inpatient_admin`, and `doctor`.
- **E. Validation timing:** enforce on backend at `POST /api/admin/users` when role is doctor/nurse. Frontend mirrors with `required` attr conditional on role.

---

## TODO — Execution checklist

### Phase 1 — Backend: schema + migration ✅ DONE
- [x] **No new User column** — reuse existing `User.inpatient_fee_inr` for both doctor and nurse rates (Option A confirmed)
- [x] Added new `Procedure` model in `backend/app/models/inpatient.py` after `AncillaryServiceCatalog`: `id, hospital_id, name, default_rate, description, is_active, created_at, updated_at`. Unique `(hospital_id, name)`.
- [x] Added `OTSchedule.procedure_charge Float` and `OTSchedule.procedure_id FK -> procedures.id` (nullable for free-text fallback)
- [x] Updated `OTSchedule.total_charges` property to include `procedure_charge`
- [x] Added `procedure_id` and `procedure_charge` to `migrate_patient_fields.py` `NEW_COLUMNS` list
- [x] Added `Procedure` to inpatient model imports in `main.py`
- [x] Verified imports: model loads cleanly, columns present

### Phase 2 — Backend: routes ✅ DONE
- [x] Validation helpers in `admin.py`: `_role_requires_visit_fee`, `_parse_positive_fee`, `_ensure_visit_fee_for_role`. Wired into both `create_user` and `update_user`. Returns 400 if doctor/nurse role and `inpatient_fee_inr` missing or ≤ 0.
- [x] CRUD routes added in `inpatient.py` (kept inline for consistency with AncillaryServiceCatalog pattern instead of a new file): `GET/POST/PUT/DELETE /api/inpatient/procedures`. Soft-delete via `is_active=False`. Unique-name check per hospital.
- [x] Gated with `require_feature_permission("inpatient", "view_procedures" / "manage_procedures")`
- [x] Updated `create_visit` (line 1063 area) to read the visiting user's `inpatient_fee_inr` for `doctor_visit` / `nurse_visit` types (same column for both). Procedure visits no longer auto-fill (those flow through OT).
- [x] Updated `create_ot_schedule` to accept optional `procedure_id`; if set, auto-fills `procedure_charge` from catalog. Surgeon/anaesthetist fees auto-fill from their `inpatient_fee_inr`. Free-text `procedure_name` still accepted when `procedure_id` is null (sub-decision C).
- [x] `OTChargesUpdate` schema accepts `procedure_charge`; `_compute_admission_charges` exposes it in the OT bill breakdown; `OTSchedule.total_charges` includes it.
- [x] Marked `GET/PUT /api/inpatient/rate-config` as deprecated in a comment. Endpoints still functional for backwards compat.

### Phase 3 — Backend: permissions ✅ DONE
- [x] Added `view_procedures` and `manage_procedures` entries to `permissions_data` in `setup_hospital_roles.py` (catalog seed)
- [x] Updated role-permission matrix: super_admin + hospital_admin get both; inpatient_admin + doctor get `view_procedures`; nurse/receptionist get neither
- [x] Verified end-to-end: `setup_module_permissions()` seeds the catalog, `setup_role_permissions()` seeds the role grants. Both are idempotent.
- [ ] **Deployment note for upgrades:** existing installs need to run `python setup_hospital_roles.py` once to pick up the new permission catalog entries (same as for prior 54 inpatient permissions). Hospital admins bypass all checks so the UI works for them out-of-box; doctor/inpatient_admin role users need the seed run.

### Phase 4 — Frontend: user form ✅ DONE
- [x] Added `isNurseRole()` and `requiresInpatientFee()` helpers in `AdminModule.js`
- [x] Doctor block: marked Inpatient Fee input as `required` with red asterisk
- [x] Added a separate "Visit Fee" section that renders only when nurse role is selected without doctor role (so the field appears once, in the natural place for either role)
- [x] Form uses the same `inpatient_fee_inr` field for both — no schema change, single source of truth
- [x] Existing toast error path surfaces backend's 400 message (`error.response?.data?.detail`) for invalid/missing values
- [x] Same conditional logic applies in edit mode (form is shared)

### Phase 5 — Frontend: Procedures tab ✅ DONE
- [x] Added "Procedures" entry to Dashboard.js sidebar nav (visible to hospital_admin, super_admin, inpatient_admin, doctor)
- [x] Added `procedures` route key to InpatientModule's `TAB_TO_PATH` map
- [x] Added Procedures table page with name / default_rate / description / status / actions columns
- [x] Added create/edit dialog with name, default_rate, description fields
- [x] Wired CRUD via plain axios (matches existing module pattern; React Query not used elsewhere here)
- [x] Backend gates the routes (`view_procedures`/`manage_procedures`); add/edit/remove buttons hidden via the page itself surfacing the catalog only when reachable

### Phase 6 — Frontend: OT schedule integration ✅ DONE
- [x] OT dialog now shows a procedure dropdown (catalog) **plus** a free-text input below — picking from catalog populates the name + sets `procedure_id`; typing in the input clears `procedure_id` and treats as free-text (sub-decision C)
- [x] Added an Anaesthetist dropdown (was missing from the dialog) with an "Optional" placeholder
- [x] Backend auto-fills `procedure_charge` from catalog and `surgeon_fee` / `anaesthetist_fee` from users' `inpatient_fee_inr`
- [x] Helper text indicates auto-fill behaviour ("Surgeon fee auto-fills from their inpatient fee", "Procedure charge will auto-fill from catalog")
- [x] OT Charges edit dialog gained a `procedure_charge` input so users can override after-the-fact

### Phase 7 — Frontend: remove/clean up old rate UI ✅ DONE
- [x] Removed the "Rate Configuration" card (it was actually on the Rooms tab, not Billing Setup)
- [x] Removed `rateForm` and `rateConfig` state
- [x] Removed `handleSaveRateConfig` and `fetchRateConfig` callbacks
- [x] Removed `fetchRateConfig` from useEffect dep array + activeTab effect
- [x] Updated the visit dialog hint to read from the selected staff member's `inpatient_fee_inr` (across both `doctorsList` and `nursesList`)
- [x] Backend `GET/PUT /api/inpatient/rate-config` left intact with deprecation comment (frontend no longer calls it)

### Phase 8 — Visit creation flows ✅ DONE
- [x] Backend `create_visit` is the single PatientVisit creation point — already updated in Phase 2 to read `inpatient_fee_inr` from the visiting user
- [x] Frontend visit-entry hint surfaces the user's fee in the dialog before save

### Phase 9 — Tests ✅ DONE
- [x] Added `TestRateRefactor` class with 10 tests:
  - Doctor user creation rejected without fee, with zero fee, accepted with positive fee
  - Nurse user creation rejected without fee, accepted with positive fee
  - Procedure CRUD round-trip (create, list, update, soft-delete, hidden when `active_only=true`)
  - Procedure duplicate-name rejected (400)
  - PatientVisit `charge_amount` auto-fills from the visiting user's `inpatient_fee_inr`
  - OT with `procedure_id` auto-fills `procedure_charge`, `surgeon_fee`, `anaesthetist_fee`
  - OT with free-text procedure name (no `procedure_id`) leaves `procedure_charge` at 0
- [x] Updated existing `TestInpatientE2E::test_create_visit` to set the seed doctor's `inpatient_fee_inr=300` first (it was relying on the now-deprecated rate config)
- [x] Full suite: **150 passed, 1 skipped**

### Phase 10 — Manual QA / dogfood (for the user)
- [ ] After pulling: run `cd backend && ./venv/bin/python setup_hospital_roles.py` once to seed the new `view_procedures` / `manage_procedures` permission keys
- [ ] Restart backend (migration auto-runs and adds `procedure_id` + `procedure_charge` columns to `ot_schedules`)
- [ ] Walk through:
  - Create a new nurse user → confirm Inpatient Fee field is required
  - Create a new doctor user → confirm Inpatient Fee field is required
  - Add a procedure to the catalog (Sidebar → Procedures)
  - Create an OT schedule, pick the procedure → confirm procedure_charge / surgeon_fee / anaesthetist_fee auto-fill
  - Create a patient visit → confirm hint shows the staff member's fee, charge defaults to it
  - Verify printed bill totals are unchanged for existing admissions (old visits keep their `charge_amount` rows)
  - Verify Procedures tab is hidden for receptionist/nurse roles

---

## Files that will change

**Backend**
- `backend/app/models/auth.py` (or wherever `User` is defined — verify) — new column
- `backend/app/models/inpatient.py` — new `Procedure` model, optional `OTSchedule.procedure_charge`
- `backend/app/routes/admin.py` — user request schema + validation
- `backend/app/routes/inpatient.py` — visit creation, OT schedule creation, deprecate rate-config
- `backend/app/routes/procedures.py` — NEW
- `backend/main.py` — mount new router
- `backend/migrate_patient_fields.py` — `NEW_COLUMNS` additions
- `backend/setup_hospital_roles.py` — new permission keys + matrix entries
- `backend/tests/test_inpatient_smoke.py` — new test cases

**Frontend**
- `frontend/src/pages/modules/AdminModule.js` — nurse rate field, conditional required
- `frontend/src/pages/modules/InpatientModule.js` — Procedures tab, OT schedule integration, remove old rate UI

## Risks / things to watch

- ✅ User model location verified: `backend/app/models/user.py` line 27.
- Adding required fields to user creation will break any scripts/tests that create users without these fields. Audit before merging — `setup_initial_data.py` and `setup_hospital_roles.py` are the likely candidates.
- If multi-tenancy via `hospital_id` is in use elsewhere on inpatient models, the `Procedure` table needs the same FK.
- "Free-text fallback" for procedures not in the catalog (Phase 6) should be confirmed with user — they may want catalog-only.

## Out of scope (for this refactor)

- Per-procedure surgeon/anaesthetist breakdown in the catalog (catalog has a single rate; breakdown stays on OT schedule).
- Historical rate adjustments / rate-effective-dates.
- Migrating existing admission/visit `charge_amount` values to match new per-user rates.
