# Critical Features TODO - Outpatient Module

## 1. Queue Management (Token Numbers)
- [x] Add `token_number` column to Appointment model
- [x] Add `queue_position` column to Appointment model
- [x] Create token generation logic (daily reset, per-doctor)
- [x] Add API endpoint to get current queue (GET /queue/{doctor_id})
- [x] Add "Call Next Patient" API endpoint (POST /queue/{doctor_id}/call-next)
- [x] Update frontend with token display on appointment cards

## 2. Check-in / Check-out
- [x] Add `checked_out_at` column to Appointment model
- [x] Add check-in API endpoint (POST /{id}/check-in) - sets checked_in_at, assigns token
- [x] Add check-out API endpoint (POST /{id}/check-out) - sets checked_out_at
- [x] Add check-in/check-out buttons in frontend

## 3. Reschedule Appointment
- [x] Add reschedule API endpoint (POST /{id}/reschedule) - validates new slot
- [x] Add `rescheduled_from_id` column to track original appointment
- [x] Add reschedule dialog in frontend with slot picker

## 4. Cancel with Reason
- [x] Add `cancellation_reason` column to Appointment model
- [x] Update cancel flow to require reason (POST /{id}/cancel)
- [x] Add cancel dialog with reason input in frontend

## 5. Edit Patient (NOT email)
- [x] Backend PUT endpoint already exists
- [x] Add edit patient dialog/form in frontend (ReceptionPatientsPage)
