# Round 2 - Feature TODO

## 1. Time format fix (09:30:00 -> 09:30 AM)
- [x] Add formatTime helper in ReceptionAppointmentsPage
- [x] Apply to appointment_time display

## 2. Double "Dr." prefix fix
- [x] Removed "Dr." prefix from ReceptionDashboard (backend already adds it)

## 3. Start Consultation button (in_progress)
- [x] Add backend endpoint POST /{id}/start-consultation
- [x] Add "Start" button for checked-in patients in frontend

## 4. No-show marking
- [x] Add backend endpoint POST /{id}/no-show
- [x] Add "No Show" button in frontend
- [x] Added no_show to status filter dropdown

## 5. Patient visit history
- [x] Add backend endpoint GET /patient/{patient_uuid}/history
- [x] Add "History" button + dialog in ReceptionPatientsPage

## 6. Doctor schedule view (week calendar)
- [x] Enhanced DoctorAvailabilityPage with Day/Week toggle
- [x] Week view shows 7-day grid with slots/appointments per day
- [x] Week navigation with prev/next buttons

## 7. Appointment notes/follow-up
- [x] Add backend PUT /{id}/notes endpoint
- [x] Add notes dialog (FileText icon button) on each appointment card

## 8. Reports & analytics
- [x] Add backend GET /reports/daily-summary endpoint
- [x] Create ReceptionReportsPage with summary cards, status/type/doctor/payment breakdown
- [x] Add route + nav item in Dashboard
