# Inpatient Flow — Gap Fix & Cleanup Plan

Source: conversation on 2026-05-16. Compares the spoken IP flow against built features.
Two cleanups + six feature gaps. Each task lists files to touch and acceptance criteria.

Legend: ☐ todo · ◐ in progress · ☑ done

---

## A. CLEANUPS (remove from product)

### A1. Remove Incident reporting & investigation entirely  ☐
**Backend**
- `backend/app/models/inpatient.py` — delete `class Incident`; drop `MedicationAdministration.incident_id` FK column + relationship (lines ~520–522, ~847)
- `backend/app/routes/inpatient.py` — delete all routes/models referencing incidents (lines 7165–7430 region: `IncidentCreate`, `IncidentInvestigate`, `IncidentResponse`, `_incident_to_response`, `POST /incidents`, `GET /mar/{mar_id}/incident`, `GET /incidents/{id}/mar`, `GET /incidents`, `GET /incidents/{id}`, `POST /incidents/{id}/investigate`, `GET /incidents/reports/monthly`)
- `backend/app/services/db_seed.py` — remove `report_incident`, `investigate_incident`, `close_incident` from permission catalog (lines 61, 157–159) and from every role grant (lines 230, 248, 263)
- `backend/app/utils/dependencies.py` — drop any `report_incident` etc. from nurse/doctor default arrays if present
- Write idempotent migration `backend/migrate_drop_incidents.py` to: drop `incidents` table, drop `medication_administrations.incident_id` column. Wire it into `main.py` startup like `migrate_patient_fields`.
- `backend/tests/test_inpatient_smoke.py` — delete any incident-related test cases; update role boundary tests so doctor/nurse/billing_admin no longer expect `report_incident`.

**Frontend**
- `frontend/src/pages/modules/InpatientModule.js` — remove `incidents` state, fetchers, form, dialog, tab, sidebar entry, and the `incidents` key in tabs map (~lines 67, 386–393, 832–847, 1002–1004, render block).
- `frontend/src/hooks/useNavigationSections.js:110` — remove the `Incidents` nav entry.
- `frontend/src/pages/HelpDocs.js` — drop incident-related help section.

**Acceptance**: no references to `Incident` / `/incidents` route in repo; smoke tests pass; `manage_diet_orders` and incident permissions don't appear in Role Permissions UI.

---

### A2. Remove Diet ordering subsystem entirely  ☐
Keep only the free-text `diet_instructions` field on the discharge summary (it's just a string on `DischargeRecord` — no module surface).

**Backend**
- `backend/app/models/inpatient.py` — delete `class DietOrder` (line 329) and `class DietMealLog` (line 434); remove `diet_orders` relationship on `Admission` (line 108); leave `discharge_record.diet_instructions` text field as-is.
- `backend/app/routes/inpatient.py` — delete `DietOrderCreate/Update/Response`, `DietMealLogCreate`, `_diet_to_response`, and all routes: `POST/GET/PUT/DELETE /admissions/{id}/diet-orders`, `GET /diet-orders/active`, `POST /diet-orders/{id}/meal-log`, `GET /admissions/{id}/diet-meal-logs`, `GET /diet/kitchen-ticket/pdf` (lines 500–520, 3882–4140 region).
- `backend/app/services/db_seed.py` — remove `manage_diet_orders` from permission catalog (line 137) and every role grant (lines 53, 225, 244).
- `backend/app/utils/dependencies.py:110` — remove `manage_diet_orders` from default grants.
- `backend/app/utils/pdf_service.py` — remove the kitchen-ticket PDF generator (~line 2281 region: `ward/room/bed with diet type and allergies`). Keep the `Diet:` line in the discharge summary PDF (~line 1802) since that reads `discharge_data.diet_instructions`.
- Migration `backend/migrate_drop_diet.py`: drop `diet_meal_logs` then `diet_orders` tables. Wire into `main.py` startup.
- Tests: drop diet-related cases; adjust nurse role boundary test.

**Frontend**
- `frontend/src/pages/modules/InpatientModule.js` — remove `dietOrders`, `showDietDialog`, `dietForm` state, `fetchDietOrders`, the Diet sub-tab inside admission slide-over (Clinical group), the dialog, and the call on admission select (~line 1160).
- `frontend/src/pages/modules/NurseDashboard.js` — remove `activeDietOrders` state, fetch (`/api/inpatient/diet-orders/active`), and the Active Diet Orders card (lines 51, 84–85, 597–630).
- `frontend/src/pages/HelpDocs.js` — drop diet-order help section.

**Acceptance**: no `/diet-orders` API references; Clinical tab in admission slide-over has 6 tabs (Vitals, MAR, I/O, Nursing, Allergies, Consents); NurseDashboard no longer shows diet card.

---

## B. GAPS — features still to build

### B1. Payer-type & scheme master + admission payer selection  ☐
**Goal**: at admission, operator picks one of Cash / Private Insurance / TPA / Govt Scheme (Aarogyasri, Teachers, Govt-Employee, …). Scheme list is editable.

**Backend**
- New model `PayerScheme` (id, code, name, scheme_type [`cash|private_insurance|tpa|govt_scheme`], active, notes). Seed defaults: Cash, Aarogyasri, Teachers' Health Scheme, Govt Employee Health Scheme, Private Insurance, TPA.
- Extend `Admission` with: `payer_scheme_id` (FK, nullable for back-compat), `payer_type` (denormalised string mirroring scheme_type for fast filtering), `scheme_member_id` (e.g., Aarogyasri card no.), `scheme_approval_status` (`none|pending|approved|rejected|disconnected`), `scheme_approval_ref`, `scheme_approval_amount`.
- CRUD routes `/api/inpatient/payer-schemes` gated by new permission `manage_payer_schemes` (hospital_admin + billing_admin).
- Migration `backend/migrate_add_payer_scheme.py` for the new columns + table; wire into startup.
- Update `_compute_admission_charges` / `BillSplit` so `payer_type` enum accepts the new values (or maps govt scheme → tpa internally with scheme attribution).

**Frontend**
- Admission create dialog: dropdown sourced from `/payer-schemes?active=true`. If scheme_type != cash, show member-id / approval fields.
- New "Payer Schemes" management screen under Hospital Administration.

**Acceptance**: new admission can be tagged with Aarogyasri + member id; final bill split shows scheme name on the bill PDF.

---

### B2. Convert payer mode mid-stay  ☐
**Goal**: when scheme approval is disconnected/rejected, allow switching to Cash (or another scheme) without re-admitting.

**Backend**
- New table `AdmissionPayerChange` (admission_id, from_scheme_id, to_scheme_id, reason, changed_by_id, changed_at).
- Endpoint `PATCH /admissions/{id}/payer` (body: `payer_scheme_id`, `reason`, member fields). Permission `convert_payer` (billing_admin, hospital_admin). Updates admission denormalised fields + logs row + audit.
- Bill recalculation: any **already-finalised** `BillSplit` rows remain immutable; **future** charges go to the new payer. Document this on the API.

**Frontend**
- In admission slide-over → Billing group → Insurance tab, add "Change Payer" button beside current payer card. Modal with new scheme picker + reason. Show full history beneath.

**Acceptance**: changing from Aarogyasri → Cash mid-stay is reflected in subsequent bills; audit log + history visible.

---

### B3. Referring doctor + IP doctor accept-admission handshake  ☐
**Goal**: capture *referring* doctor distinct from admitting/attending; require IP-floor doctor to explicitly accept the admission before clinical activity opens up.

**Backend**
- `Admission`: add `referring_doctor_id` (FK users, nullable), `referring_external_name` (str, nullable for external referrers), `acceptance_status` (`pending|accepted|rejected`, default `pending`), `accepted_by_doctor_id`, `accepted_at`, `rejection_reason`.
- Routes: `POST /admissions/{id}/accept` (perm `accept_admission`), `POST /admissions/{id}/reject` (perm `accept_admission`). Block clinical writes (vitals/MAR/visits/lab/meds) while `acceptance_status != accepted` via a small `_require_accepted(admission)` helper called inside affected route handlers.
- Migration adds columns; default existing admissions to `accepted` so back-compat is preserved.

**Frontend**
- Admission create form: add Referring Doctor (typeahead users with doctor role + free-text external).
- Admission slide-over header: pending banner with Accept / Reject buttons (visible to users holding `accept_admission`).
- Disable clinical tabs while pending.

**Acceptance**: a new admission shows banner "Awaiting IP doctor acceptance"; after Accept, Vitals/MAR become editable; rejection sends admission to a rejected state requiring re-admit.

---

### B4. Duty-doctor visit subtype + fee handling  ☐
**Goal**: distinguish consultant rounds from duty-doctor rounds; allow separate fee treatment.

**Backend**
- `PatientVisit.visit_type` regex widened to include `duty_doctor_visit`. Don't break existing rows — keep `doctor_visit`.
- `InpatientRateConfig` (or per-doctor fee config): add `duty_visit_fee` knob distinct from `visit_fee`.
- Billing logic in `_compute_admission_charges`: when visit_type is `duty_doctor_visit`, use duty_visit_fee.
- No new permission — existing `record_visits` covers it.

**Frontend**
- Visit logging dialog: visit-type radio gains "Duty Doctor Visit"; show fee preview from the rate config.
- Bill breakdown: separate "Duty doctor visits" line.

**Acceptance**: morning consultant visit (₹1000) and a duty-doctor entry in between both appear with correct fees on the interim bill.

---

### B5. Face-sheet + case-sheet consent templates  ☐
**Goal**: seed the two declaration forms once you provide the content; render via existing consent pipeline.

**Backend**
- Seed migration: insert two `ConsentTemplate` rows (`face_sheet`, `case_sheet_declaration`) with placeholder content if not already present. Mark as `required_on_admission=true` (new boolean on `ConsentTemplate`, default false).
- Optional warning on admission UI if required templates aren't signed yet — non-blocking unless `acceptance_status` transition is attempted.

**Frontend**
- Consents tab inside admission slide-over already exists; add a banner listing unsigned required-on-admission templates and a "Sign now" shortcut.

**Acceptance**: face-sheet and case-sheet appear in the consent picker; signing produces the existing consent PDF.

> Blocked on: **content from user** for both forms.

---

### B6. Gate pass on discharge  ☐
**Goal**: after Discharge Summary submitted + final bill cleared, generate a printable Gate Pass for security at exit.

**Backend**
- `GatePass` model (admission_id, generated_at, generated_by_id, vehicle_no nullable, attendant_name nullable, qr_token).
- Endpoint `POST /admissions/{id}/gate-pass` — guard: discharge must exist + outstanding bill balance must be 0 (or override flag with reason).
- `GET /admissions/{id}/gate-pass/pdf` reusing `pdf_service` patterns (uniform header toggle, printPdf.js).
- Permission `issue_gate_pass` (receptionist, billing_admin).

**Frontend**
- Discharge tab → "Generate Gate Pass" button enabled only when bill cleared. Opens the standard preview/print dialog.

**Acceptance**: discharged patient with zero balance → gate pass PDF prints; printing blocked otherwise with a clear message.

---

## Sequencing
1. **A1 + A2** (cleanups) — small, isolated, unblock UI for the new layout decisions in B-series.
2. **B1** payer master + admission payer column.
3. **B2** payer conversion (depends on B1).
4. **B3** referring doctor + acceptance handshake (independent of B1/B2; can run in parallel).
5. **B4** duty-doctor visit fees (small).
6. **B5** consent templates seeded (blocked on content).
7. **B6** gate pass (last — depends on no other gap).

## Risks / Notes
- The `_ensure_role_permissions()` overwrite-on-startup behavior (per memory) means any new perms in `db_seed.py` will roll out cleanly to existing installs, but any operator who already customized grants will be reset. Worth flagging in release notes.
- Dropping incident & diet tables is destructive — migrations should `IF EXISTS` and SQLite ALTER limitations may require table-rebuild for `medication_administrations.incident_id` removal.
- `_compute_admission_charges` is the single source of bill truth — every B-task that touches money (B1, B2, B4) must update it and add a smoke test.
