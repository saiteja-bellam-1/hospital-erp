# Outpatient Tokening System — Plan & Tasks

**Decisions locked in (2026-05-29):**
- Token pool: **per-doctor, per-date** (keep current behavior)
- Walk-ins: **must book full appointment first** (no shortcut)
- Public display screen: **deferred** (not in this phase)
- Token slip: **no separate PDF**; embed token number into the existing outpatient bill PDF

## Scope

Upgrade the existing minimal token system (token assigned at check-in, basic queue/call-next) into a usable OPD queue with priority, skip, recall, lifecycle tracking, and visibility in the consultation bill.

## Backend

### 1. Schema additions (`migrate_patient_fields.py NEW_COLUMNS`)
On `appointments`:
- `token_status TEXT` — `waiting | called | in_consult | skipped | completed | recalled` (default `waiting` when token is assigned)
- `token_called_at DATETIME`
- `token_skipped_at DATETIME`
- `token_recalled_at DATETIME`
- `priority_boost INTEGER DEFAULT 0` — emergency override; higher = served first

### 2. Queue ordering rule
`ORDER BY priority_boost DESC, token_number ASC` — emergency-boosted appointments jump to the front without renumbering. Apply in `/queue/{doctor_id}` and `/queue/{doctor_id}/call-next`.

### 3. New endpoints (`backend/app/routes/appointments.py`)
All under `require_permission(Modules.OUTPATIENT, "write")` to match the existing module convention.
- `POST /queue/{doctor_id}/skip/{appointment_id}` — set `token_status=skipped`, `token_skipped_at=now`. Stays in queue but excluded from next-up selection until recalled.
- `POST /queue/{doctor_id}/recall/{appointment_id}` — set `token_status=recalled`, `token_recalled_at=now`. Eligible for `call-next` again, sorted to top after current emergencies.
- `POST /queue/{doctor_id}/boost/{appointment_id}` — set `priority_boost=1` (or increment). Audit-logged.
- Update `call-next` to set `token_status=in_consult` and `token_called_at=now` on the new patient, `token_status=completed` on the outgoing one.
- Update `check-in` to set `token_status=waiting`.
- Update `/queue/{doctor_id}` response to include `token_status` and `priority_boost` per row.

### 4. Bill PDF integration
- In `GET /appointments/{appointment_id}/bill` and `/bill/download`, include `token_number` in the returned `bill_data` (e.g. as a top-line field next to `reg_no`).
- In `pdf_service.py:generate_bill_pdf`, render `Token #: <n>` in the patient/visit info block (right column, near appointment number). Skip the line if `token_number` is null.

### 5. Audit
`log_action()` calls for: `boost_token`, `skip_token`, `recall_token`.

## Frontend

### 6. Reception queue panel (`ReceptionAppointmentsPage.js` or new sub-page)
- Per-doctor queue list with badges: waiting / called / in-consult / skipped.
- Action buttons per row: **Skip**, **Recall**, **Boost** (emergency).
- Show `priority_boost` indicator (red dot) for boosted rows.
- Pull from existing `/queue/{doctor_id}` (extended response).

### 7. Doctor Dashboard (`DoctorDashboard.js`)
- Add **Skip** and **Recall** buttons next to existing "Now Serving" / Call-Next UI.
- Show waiting list with token numbers (already partial — extend to include skipped section).

### 8. Bill display
- Existing bill preview dialog auto-shows token from updated PDF; no extra UI work — just make sure the bill data is re-fetched after check-in.

## Permissions
No new permission keys — outpatient still uses legacy `read`/`write` bucket per [[backend_claude_md]] convention.

## Tasks

- [x] T1 — Add 5 new columns via `migrate_patient_fields.py NEW_COLUMNS` (idempotent)
- [x] T2 — Update `check-in` to set `token_status=waiting`
- [x] T3 — Implement `skip`, `recall`, `boost` endpoints
- [x] T4 — Update queue ordering (priority_boost DESC, token_number ASC) in `/queue/{doctor_id}` and `call-next`
- [x] T5 — Update `call-next` / `start-consultation` / `check-out` to manage `token_status` + `token_called_at` lifecycle
- [x] T6 — Add `token_number` to bill PDF: bill route response + `generate_bill_pdf` patient-info block
- [x] T7 — Frontend: Reception appointment rows show Boost / Recall + PRIORITY/SKIPPED badges
- [x] T8 — Frontend: Doctor Dashboard queue card has Call Next / Skip Current / Recall #N
- [ ] T9 — Manual smoke-test the full flow in the browser (user to verify)

## Out of scope (deferred)
- Public "Now Serving" display screen
- Walk-in instant token (no appointment)
- Token prefix/padding config, shared OPD pool, daily-reset config
- SMS/email notification on call
- KPI dashboard (avg wait, no-show %, skip rate)
