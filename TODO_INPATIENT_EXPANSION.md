# Inpatient Module — Expansion Plan

20 gaps to close, grouped into 5 phases by dependency + business value. Each item lists DB changes, backend routes, frontend changes, and integration touchpoints. Status legend: ⬜ pending · 🟡 in progress · ✅ done.

---

## Phase 1 — Patient safety & clinical (Group A)

### 1. Structured Vital Signs ✅
**DB:** New `VitalSigns` table — `id, admission_id FK, patient_id FK, recorded_by_id FK, recorded_at, bp_systolic, bp_diastolic, heart_rate, respiratory_rate, temperature_c, spo2, blood_glucose, pain_score (0-10), gcs_score (3-15), position, notes, is_abnormal, abnormal_flags JSON`.
**Backend:** `POST/GET/PUT/DELETE /api/inpatient/admissions/{id}/vitals`. Reference ranges + abnormal flagging in service layer.
**Frontend:** New "Vitals" tab in admission slide-over. Entry form, list view, trend graph (recharts). Latest-vitals snippet on admission card.
**Touchpoints:** NurseDashboard already POSTs `/api/patients/vitals` — migrate to inpatient endpoint when admission_id present.

### 2. Allergies & Alert Banner ✅
**DB:** New `PatientAllergy` table at patient level (carries across admissions) — `id, patient_id FK, allergy_type (drug/food/environmental/other), allergen, severity (mild/moderate/severe/anaphylaxis), reaction, recorded_by_id, recorded_at, is_active, notes`.
**Backend:** `GET/POST/PUT/DELETE /api/patients/{id}/allergies`. Drug-allergy check helper used by prescription routes (warning, non-blocking initially).
**Frontend:** Red allergy banner component visible on every admission view, patient view, prescription view. Allergy management dialog. Soft warning at prescription create when drug name matches.

### 3. Medication Administration Record (MAR) ✅
**DB:** Extend `PrescriptionItem` with `frequency, schedule_times JSON, duration_days, route, special_instructions, is_prn`. New `MedicationAdministration` table — `id, prescription_item_id FK, admission_id FK, scheduled_time, administered_at, administered_by_id, status (scheduled/given/missed/refused/held), dose_given, route, site, reason_if_not_given, witness_id, notes`.
**Backend:**
- `POST /api/inpatient/admissions/{id}/mar/generate` — materialise scheduled doses for active inpatient prescriptions.
- `GET /api/inpatient/admissions/{id}/mar` — today's grid.
- `GET /api/inpatient/admissions/{id}/mar/history`.
- `POST /api/inpatient/mar/{id}/administer` — given/missed/refused with timestamp.
- `POST /api/inpatient/admissions/{id}/mar/prn` — record PRN dose.

**Frontend:** New "MAR" tab. Time-grid (rows=meds, cols=times, cells=status chip). Quick "Mark as Given" with auto-timestamp + nurse from session. PRN admin form. Allergy check at admin time.

---

## Phase 2 — Billing & financial (Group B)

### 7. Advance Deposit & Running Balance ✅
**DB:** New `AdmissionDeposit` — `id, admission_id FK, amount, payment_method (cash/card/upi/cheque/online), reference_number, received_by_id, received_at, notes, deposit_type (initial/topup/refund)`.
**Backend:**
- `POST /api/inpatient/admissions/{id}/deposits`
- `GET /api/inpatient/admissions/{id}/deposits`
- `GET /api/inpatient/admissions/{id}/balance` — `total_deposits, total_charges, current_balance, refund_due`.
- `POST /api/inpatient/admissions/{id}/refund`
- `GET /api/inpatient/admissions/{id}/deposit-receipt/pdf`

**Frontend:** "Deposits & Balance" tab. Live balance pill in admission header (green/red by sign). Add-deposit dialog. Receipt PDF print via shared `printPdf.js`. Refund workflow on discharge.

### 8. Interim / Daily Billing ✅
**DB:** Add `bill_subtype` to `Bill` (interim/final/advance_receipt). Add `bill_id` FK to `PatientVisit` (replaces current boolean `billed`) so each charge knows which bill it landed in. Same for new pharmacy/lab/ancillary line accumulators.
**Backend:**
- `POST /api/inpatient/admissions/{id}/bill/interim` — snapshot of currently-unbilled charges.
- `GET /api/inpatient/admissions/{id}/bills` — all bills for an admission.
- `GET /api/inpatient/bills/{bill_id}/pdf`

Final bill at discharge skips already-billed items (no double-billing).
**Frontend:** Bills history list inside admission. "Generate Interim Bill" button. Final bill view shows interim bills as deductions.

### 9. OT Charges → Admission Bill ✅
**DB:** Extend `OTSchedule` with `surgeon_fee, anaesthetist_fee, ot_room_charge, equipment_charge, consumables_charge, other_charges, total_charges (computed), billed (bool), bill_id FK`.
**Backend:**
- `PUT /api/inpatient/ot/{ot_id}/charges`
- Bill calc reads completed-status OT entries linked to admission and adds line items.

**Frontend:** "OT Charges" form on OT detail (post-completion). OT charges section in admission bill preview + PDF.

### 10. Ancillary Services as Billable Items ✅
**DB:**
- `AncillaryServiceCatalog` — `id, hospital_id, service_name, category (imaging/physiotherapy/dialysis/oxygen/equipment/consumable/other), default_charge, charge_unit (per_session/per_hour/per_day/per_unit), is_active`.
- `AdmissionAncillaryCharge` — `id, admission_id FK, service_id FK, charged_at, quantity, unit_price, total_amount, performed_by_id, notes, billed, bill_id FK`.

**Backend:** Catalog CRUD (admin). `POST/GET/PUT/DELETE /api/inpatient/admissions/{id}/ancillary-charges`. Bill calc adds ancillary section.
**Frontend:** Catalog admin page. "Add Service Charge" dialog with service picker + qty. Ancillary section in bill.

### 11. Surgery Packages ✅
**DB:**
- `SurgeryPackage` — `id, hospital_id, package_name, package_code, base_price, included_room_type, included_stay_days, included_services JSON, excess_per_day_charge, description, is_active`.
- `AdmissionPackage` — `id, admission_id FK unique, package_id FK, agreed_price, applied_at, applied_by_id`.

**Backend:** Package CRUD. `POST /api/inpatient/admissions/{id}/package` (apply). Bill calc switches to package mode: `package_price + excess (extra days, services not in included list)`.
**Frontend:** Packages admin page. "Apply Package" option during/after admission. Bill clearly shows package vs excess split.

### 12. Insurance Pre-Authorisation ✅
**DB:**
- `InsurancePreAuth` — `id, admission_id FK nullable, patient_id FK, insurance_provider, policy_number, tpa_name, requested_amount, approved_amount, status (requested/approved/rejected/expansion_requested/expanded), request_date, approval_date, validity_days, approval_document_path, notes, created_by_id`.
- `InsurancePreAuthExpansion` — `id, preauth_id FK, requested_amount, approved_amount, status, requested_at, decided_at, document_path, reason`.

**Backend:** CRUD pre-auth. `POST /api/inpatient/preauth/{id}/expansion-request`. File upload for approval docs (reuse admission_docs upload pattern).
**Frontend:** Pre-auth list page (own sidebar item). Pre-auth dialog (can be created before admission). Approval doc upload. Status pill on admission card if pre-auth attached. Expansion request flow.

### 13. TPA Billing Split ✅
**DB:**
- `TPACompany` — `id, hospital_id, tpa_name, tpa_code, address, phone, email, default_discount_percent, contract_details, is_active`.
- `BillSplit` — `id, bill_id FK, payer_type (cash/insurance/tpa), payer_name, payer_id (FK to TPACompany when tpa), amount, payment_status (pending/received), payment_date, payment_reference, notes`.

**Backend:** TPA CRUD. `POST /api/billing/bills/{id}/split`. `GET /api/billing/tpa/outstanding` for receivables view.
**Frontend:** TPA management page (admin). Bill split UI on finalisation (cash + insurance + tpa rows that must sum to bill total). TPA outstanding dashboard for billing team.

---

## Phase 3 — Operational workflow (Group C)

### 14. Bed Transfer History ✅
**DB:** New `BedTransferHistory` — `id, admission_id FK, from_room_id, from_bed_id, to_room_id, to_bed_id, transferred_at, transferred_by_id, reason, transfer_type (room_change/ward_change/bed_change)`.
**Backend:** Admission update with new room/bed auto-creates a history entry. `GET /api/inpatient/admissions/{id}/transfers`.
**Frontend:** Transfer history in admission timeline. Reason field becomes mandatory in transfer dialog.

### 15. Bed Turnover / Housekeeping ✅
**DB:** Extend `Bed.status` enum with `cleaning, dirty, out_of_service`. New `BedTurnoverLog` — `id, bed_id FK, status_from, status_to, changed_at, changed_by_id, notes`.
**Backend:** `PATCH /api/inpatient/beds/{id}/cleaning` and `.../complete`. `GET /api/inpatient/beds/cleaning-pending`. On discharge, auto-set bed to `cleaning`.
**Frontend:** Housekeeping view (beds-needing-cleaning). Status update buttons on bed cards. Turnover-time metric on dashboard.

### 16. Bed Reservations ✅
**DB:** New `BedReservation` — `id, bed_id FK nullable, room_type, patient_id FK, reserved_for_date, reserved_by_id, reservation_reason (elective/post_op/transfer), status (active/converted/cancelled/expired), notes, related_admission_id FK nullable`.
**Backend:** Reservation CRUD. `POST /api/inpatient/reservations/{id}/convert` to admission. Reserved beds excluded from availability for the reserved date.
**Frontend:** Reservations tab. Calendar view. Reserve-bed during elective admission booking. Reservation count on bed availability view.

### 17. Nurse-to-Patient Assignments ✅
**DB:** New `NurseAssignment` — `id, admission_id FK, nurse_id FK, shift (morning/afternoon/night), assignment_date, assigned_by_id, is_primary, notes`. Unique on (admission_id, nurse_id, shift, assignment_date).
**Backend:** `POST /api/inpatient/admissions/{id}/assign-nurse`. `GET /api/inpatient/nurses/my-patients` (nurse perspective for the active shift). `GET /api/inpatient/admissions/{id}/nurse-assignments`.
**Frontend:** Assignment dashboard for nurse-in-charge / inpatient admin. "My Patients" view in NurseDashboard filtered by assignment. Assign-nurse dialog per admission.

### 18. Structured Inter-ward Transfer ✅
**DB:** Extend `BedTransferHistory` with `transfer_note (text), accepting_nurse_id, accepting_doctor_id, accepted_at`. Or new `WardTransfer` model if room/bed and ward transfers diverge.
**Backend:** `POST /api/inpatient/admissions/{id}/inter-ward-transfer` — requires transfer_note, sets pending state until accepting nurse/doctor confirms.
**Frontend:** Transfer dialog with target ward dropdown + mandatory transfer note (optional template). Pending-acceptance indicator. Accept action on receiving ward dashboard.

---

## Phase 4 — Compliance & quality (Group D)

### 19. Structured Consent Management ✅
**DB:**
- `ConsentTemplate` — `id, hospital_id, consent_type (surgical/anaesthesia/blood_transfusion/high_risk_procedure/general_treatment), template_name, content (text), language, is_active`.
- `Consent` — `id, admission_id FK, patient_id FK, consent_type, template_id FK, procedure_name, doctor_id FK, witness_name, patient_signature_path or _drawn (base64), witness_signature_path, risks_explained (text), language, signed_at, signed_by (patient/guardian/proxy), guardian_name, guardian_relationship, withdrawn_at, withdrawal_reason`.

**Backend:** Template CRUD. `POST/GET /api/inpatient/admissions/{id}/consents`. `GET /api/inpatient/consents/{id}/pdf`. `POST /api/inpatient/consents/{id}/withdraw`. Required-consents check before OT status flips to `in_progress`.
**Frontend:** Template manager (admin). Consent dialog with template picker + signature pad (canvas). Print signed consent. Consents-required checklist on OT detail.

### 20. Incident Reporting ✅
**DB:** New `Incident` — `id, hospital_id, admission_id FK nullable, patient_id FK nullable, incident_type (fall/medication_error/pressure_ulcer/needle_stick/infection/other), severity (low/medium/high/critical), incident_date, location, description, immediate_action, reported_by_id, witnessed_by, status (reported/investigating/resolved/closed), investigation_notes, resolution, root_cause, corrective_actions, preventive_measures`.
**Backend:** Incident CRUD. `GET /api/inpatient/incidents` filterable. `POST /api/inpatient/incidents/{id}/investigate`. `GET /api/inpatient/incidents/reports/monthly`.
**Frontend:** Reporting form accessible from any clinical screen (floating "Report Incident" action). Incident dashboard for quality team. Trend report by type/severity.

### 21. Readmission Detection ✅
**DB:** Add to `Admission`: `is_readmission (bool), days_since_last_discharge (int, computed), previous_admission_id FK nullable`.
**Backend:** On admission create, look up patient's most recent discharged admission; flag if within 30 days. `GET /api/inpatient/admissions/readmissions`. `GET /api/inpatient/admissions/{id}/readmission-info`. Dashboard widget: 30-day readmission rate.
**Frontend:** Readmission badge on admission card. Readmissions filter on dashboard. Readmission rate in analytics.

### 22. Mortality Tracking ✅
**DB:** Extend `DischargeRecord` with `cause_of_death, time_of_death, death_certificate_number, mlc_required (bool), mlc_number, autopsy_done (bool), autopsy_findings, body_handed_over_to, body_handover_relationship, body_handover_time, body_handover_id_proof`.
**Backend:** `PUT /api/inpatient/admissions/{id}/discharge/mortality` — only when discharge_type='death'. `GET /api/inpatient/admissions/mortality` reports. `GET /api/inpatient/admissions/{id}/death-certificate/pdf`.
**Frontend:** Mortality details form unlocks when discharge_type='death'. Death certificate PDF generation. Mortality dashboard (count, leading causes).

---

## Phase 5 — Visitor log (Group F)

### 28. Visitor Log ⬜ (de-scoped — user confirmed not a priority)
**DB:** New `PatientVisitorLog` (separate from staff `PatientVisit`) — `id, admission_id FK, patient_id FK, visitor_name, visitor_relationship, visitor_phone, visitor_id_proof_type, visitor_id_proof_number, visit_in_time, visit_out_time, purpose, notes, logged_by_id`.
**Backend:** `POST /api/inpatient/admissions/{id}/visitor-logs`. `GET /api/inpatient/admissions/{id}/visitor-logs`. `PATCH /api/inpatient/visitor-logs/{id}/checkout`. `GET /api/inpatient/visitors/today`.
**Frontend:** Visitors tab on admission. Reception view: "Currently visiting today". Quick check-in/out widget.

---

## Cross-cutting work (touches multiple phases)

### CC-1. Migration script ✅
Done incrementally — all Phase 1-4 + ICU columns are in `migrate_patient_fields.py NEW_COLUMNS`.

### CC-2. Permissions ✅
- **Complete overhaul shipped.** ~54 granular permission keys defined in `setup_hospital_roles.py` for the inpatient module.
- New `require_feature_permission(module, permission_name)` decorator in `dependencies.py`.
- All 141 inpatient routes migrated (one-shot script at `/tmp/replace_inpatient_perms.py`).
- Per-role default matrix seeded for nurse / doctor / inpatient_admin / billing_admin / receptionist / frontdesk.
- Role-permission admin UI in `HospitalAdminModule.js` → Role Permissions tab (`GET /api/admin/module-permissions`, `GET/PUT /api/admin/roles/{id}/permissions`).
- 15 boundary regression tests in `TestRoleBoundaries`.

### CC-3. PDF service ✅
Shipped: deposit receipt (`generate_deposit_receipt_pdf`), consent form (`generate_consent_pdf`), death certificate (`generate_death_certificate_pdf`). Interim bill reuses `generate_bill_pdf`.

### CC-4. License feature flags ⬜ (deferred)
Decide which sub-features gate behind license tier (e.g., MAR + consents + TPA → "premium"). Update license payload schema if so. User confirmed deferral — all features currently bundled under `inpatient` license feature.

### CC-5. Audit logging ✅
Audit `log_action()` calls in place for: deposit received, refund issued, MAR administered, consent signed/withdrawn, incident reported/investigated, mortality recorded, pre-auth decisions, ward transfer initiated/accepted, role-permission changes, finalize/interim bill creation.

### CC-6. Tests ⬜
Extend `tests/test_inpatient_smoke.py` with E2E scenarios for: vitals → MAR → deposit → interim bill → consent → discharge with mortality. Or split into `test_inpatient_clinical.py`, `test_inpatient_billing.py`.

### CC-7. Frontend sidebar reshuffle ⬜
Today: Ward Overview · Active Admissions · Discharge History · OT Schedule · Room Management.
Add (hidden behind feature flags where applicable): Pre-Authorisations · TPA & Billing Splits · Reservations · Housekeeping · Incidents · Mortality Reports.

---

## Suggested execution order

Sequenced for least dependency tangling:

1. **CC-1, CC-2, CC-3** — infrastructure first (migrations, permissions, PDF helpers).
2. **#1 Vitals** — small, isolated, builds the pattern for all "per-admission collection" tabs.
3. **#2 Allergies** — patient-level, surfaces in many places — get it in early.
4. **#7 Deposits** — independent, immediately useful for billing demos.
5. **#14 + #15 + #18** — bed transfer history, housekeeping, inter-ward transfer (related, ship together).
6. **#16 Reservations** — depends on #14/15 status enum extensions.
7. **#17 Nurse assignments** — independent.
8. **#10 Ancillary catalog + charges** → enables #9 OT charges (same pattern) → enables #8 interim billing (needs all charge sources to know `billed/bill_id`).
9. **#11 Packages** — modifies bill calc, easier after #8.
10. **#12 Pre-auth → #13 TPA splits** — pre-auth flows into bill split logic.
11. **#3 MAR** — biggest single feature; needs prescription model extension. Do after billing settles so MAR data isn't entangled.
12. **#19 Consents** — independent; do alongside #3.
13. **#20 Incidents** — independent.
14. **#21 Readmissions + #22 Mortality** — small, finish-up items.
15. **#28 Visitor log** — last, tiny.

---

## Open questions (please confirm before I start coding)

1. **Phase 1 first?** I recommend starting with CC-1/2/3 → #1 Vitals → #2 Allergies → #7 Deposits as the first shippable batch (clinical safety + immediate billing value).
2. **License tiering** — should MAR / Consents / TPA / Pre-auth be gated as "premium" features in the `.lic` payload, or all bundled into the existing `inpatient` feature?
3. **Allergy scope** — patient-level (carries across admissions) is what I assumed. Confirm.
4. **MAR generation** — auto-generate scheduled doses when prescription is created, or only when nurse opens the MAR tab for the day? Auto is cleaner; lazy is safer for edits.
5. **Signature pad** — for consents, is a touchscreen drawn signature acceptable, or do you need printed-and-rescanned PDFs? (Affects #19 scope a lot.)
6. **Tests** — keep extending `test_inpatient_smoke.py`, or split into clinical/billing/operational test files?

Reply with answers + which phase to start, and I'll convert Phase 1 into discrete tasks and begin executing one at a time.
