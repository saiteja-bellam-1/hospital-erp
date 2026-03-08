# Doctor Dashboard - Feature TODO

## 1. Appointment time formatting (09:30:00 -> 09:30 AM)
- [x] Add formatTime helper in DoctorDashboard
- [x] Apply to appointment_time display
- [x] Apply to completed appointments dialog

## 2. Patient history access from appointment card
- [x] Add "History" button on each appointment card
- [x] Fetch patient visit history using /api/appointments/patient/{uuid}/history
- [x] Show history dialog with past visits

## 3. Consultation/EHR recording
- [x] Add "Consult" button for in_progress appointments
- [x] Create consultation dialog with chief complaint, examination findings, present history
- [x] Wire to backend consultation creation (POST /api/consultations/)
- [x] Add update and complete consultation endpoints (PUT /api/consultations/by-id/{id})
- [x] Link prescription to active consultation when creating

## 4. Token/queue visibility
- [x] Show token number on appointment cards
- [x] Add queue summary card (current token, waiting count)
- [x] Fetch queue data from /api/appointments/queue/{doctor_id}

## 5. Summary stats cards
- [x] Add cards: Total, Scheduled, Checked In, In Progress, Completed, No Show
- [x] Calculate from appointments array

## 6. Follow-up tracking
- [x] Follow-up date in consultation dialog
- [x] Follow-up date in prescription form (saved to appointment notes)
- [x] Follow-up date saved on consultation completion

## 7. Auto-refresh appointments
- [x] Add polling interval (30s) to refresh appointments + queue
- [x] Show last refreshed timestamp

## 8. Appointment notes
- [x] Add Notes icon button on appointment cards
- [x] Wire to PUT /api/appointments/{id}/notes endpoint
- [x] Show existing notes on card

## 9. Remove duplicate availability tab
- [x] Removed availability tab from DoctorDashboard (keep separate Availability nav item)
- [x] Updated tabs from 4 to 3

## Deferred (Lab Module)
- Lab order submission not wired up (placeholder notice added)
- Lab orders tab is placeholder
- Lab results viewing
- Billing view from doctor side
