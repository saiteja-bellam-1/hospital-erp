# Responsive Dialog Fix — TODO

**Goal:** No popup gets cropped on any screen size. Where forms are tall, reflow fields horizontally (multi-column grids) instead of forcing the user to scroll.

## Plan

### Phase 1 — Base safety net (DONE)
- [x] Added `max-h-[95vh]` + `overflow-y-auto` to shared `DialogContent` (`frontend/src/components/ui/dialog.jsx`). No popup can hard-crop now; if any dialog overflows it scrolls internally as a safety net.

### Phase 2 — Identified tall dialogs (DONE)
Top by input density: InpatientModule, ReceptionPatientsPage, OutpatientModule, BillingModule, ReceptionAppointmentsPage, AdmitPatientWizard, ReceptionDashboard, DischargeWizard, AvailabilityModule, LabModule, SuppliersTab, MedicinesTab.

### Phase 3 — Widen the 8 worst offenders (DONE)
- [x] `AdmitPatientWizard.js:392` — `max-w-3xl` → `max-w-5xl`.
- [x] `DischargeWizard.js:423` — `max-w-2xl` → `max-w-4xl`.
- [x] `ReceptionPatientsPage.js:713` (Register Patient) — `max-w-3xl` → `max-w-5xl`, grid `grid-cols-2` → `grid-cols-1 md:grid-cols-2 lg:grid-cols-3`.
- [x] `ReceptionPatientsPage.js:912` (Edit Patient) — same as above.
- [x] `ReceptionPackagesPage.js:297` (Booking) — `max-w-lg` → `max-w-2xl` + `max-h-[92vh] overflow-y-auto`.
- [x] `ReceptionAppointmentsPage.js:1209` (Schedule Appointment) — `max-w-2xl` → `max-w-3xl` + `max-h-[92vh] overflow-y-auto`.
- [x] `MedicinesTab.js`, `SuppliersTab.js` already had responsive 2–4 col grids + max-h — left as-is.
- [x] `LabTestBookingDialog.js` already had `max-h-[90vh] overflow-y-auto`; its form is a sequential flow (search → list → totals), not a grid form — left as-is.

### Phase 4 — Verify in browser
- [ ] User to confirm: open Register Patient, Admit Wizard, Discharge Wizard, Schedule Appointment, Book Package, and confirm none crop on the laptop screen size and the layouts use more horizontal room.
- Note: `overflow-hidden` is intentionally kept on PDF preview dialogs (LabTestBooking:184, ReceptionPackages:468, ReceptionAppointments:1647/1907/1992) — those host an iframe that handles its own scroll; the dialog itself is capped at 90vh and won't crop.

## Out of scope (covered by Phase 1 safety net)
~30+ other dialogs across InpatientModule, OutpatientModule, BillingModule, AvailabilityModule, etc. — they no longer crop (base fix) but were not individually widened. If any of these still feel cramped, list them and we'll widen them next pass.
