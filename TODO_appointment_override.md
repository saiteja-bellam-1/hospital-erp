# TODO — Receptionist Override Doctor Availability

## Goal
Allow receptionist / hospital_admin / super_admin to override doctor schedule constraints when booking an outpatient appointment. Override must NOT bypass existing-appointment conflicts (no double-booking). Reason is required and audit-logged.

## Decisions
- Allowed roles: receptionist, hospital_admin, super_admin
- Bypasses: off-days, leave, holiday, outside working hours, breaks, doctor status (unavailable/busy)
- Does NOT bypass: existing appointment conflicts (double-booking still blocked)
- Audit: reason required, logged via existing `log_action`
- UI: checkbox "Override doctor availability" → reveals manual time input + reason field

## Tasks
- [x] Backend: add `override_availability` (Bool, default False) + `override_reason` (String) columns to `Appointment` model
- [x] Backend: add columns to `migrate_patient_fields.py` NEW_COLUMNS for `appointments` table
- [x] Backend: extend `AppointmentCreate` schema with `override_availability: bool = False`, `override_reason: Optional[str] = None`
- [x] Backend: in `POST /api/appointments/` — if override flag set: validate role in allowed set, require reason, skip schedule/status check, still run conflict-only check
- [x] Backend: add a helper `AvailabilityService.has_conflict()` (or inline conflict query) so we can keep just the double-booking guard
- [x] Backend: audit log the override with reason
- [x] Frontend: ReceptionAppointmentsPage.js — add checkbox + reason field + manual time input when override toggled
- [x] Frontend: send override fields in POST; skip pre-flight `checkAvailability` call when override is on
- [x] Test manually with a doctor on leave / outside hours
