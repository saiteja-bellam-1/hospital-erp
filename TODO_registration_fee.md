# Registration Fee Feature - TODO

## Tasks

- [x] 1. Backend: Add API endpoints for hospital admin to get/set registration fee
  - GET `/api/hospital/registration-fee` → returns current fee
  - PUT `/api/hospital/registration-fee` → sets the fee (stored in HospitalSettings)

- [x] 2. Backend: Add `registration_fee` column to Appointment model

- [x] 3. Backend: Modify appointment creation to auto-add registration fee for new patients
  - Checks if patient has any previous appointments
  - If no → adds registration fee from HospitalSettings
  - final_amount = consultation_fee + registration_fee - discount_amount

- [x] 4. Backend: Update bill generation to show registration fee as separate line item
  - Updated `get_appointment_bill` endpoint (JSON)
  - Updated `download_appointment_bill` endpoint (PDF)

- [x] 5. Backend: Migration script for adding registration_fee column to existing DBs
  - Added to migrate_patient_fields.py (auto-runs on startup)

- [x] 6. Frontend: Add "Billing Settings" tab in HospitalAdminModule
  - Registration fee input with save button
  - Description explaining the fee

- [x] 7. Frontend: Show registration fee in appointment booking flow (ReceptionAppointmentsPage)
  - Fee summary section shows consultation fee + registration fee for new patients
  - Fetches patient fee info via `/api/appointments/patient-fee-info/{uuid}`

- [x] 8. Frontend: Show registration fee in appointment list and bill preview
  - Appointment list shows "incl. reg. ₹X" for appointments with registration fee
  - Bill preview already uses backend data which includes registration fee item

## COMPLETED
