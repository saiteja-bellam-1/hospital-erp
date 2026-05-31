# Inpatient Billing — Unified Flow

Goal: collapse 5 scattered touchpoints (initial deposit at admit → Billing tab finalize → DischargeWizard settle → PaymentCollectionTab → GatePassTab) into ONE end-to-end flow on a new "Billing & Discharge" page.

Decisions (locked):
- New unified page (not extending DischargeWizard).
- Remove PaymentCollectionTab + GatePassTab.
- Block discharge until balance = 0; allow override with reason.
- Auto-generate final bill on "Confirm Discharge" via `POST /admissions/{id}/bill/finalize-and-settle`.
- Backend already releases room on discharge (bed → cleaning, available_beds recomputed). No backend change needed for that.

## Tasks

### 1. Build the unified page
- [ ] Create `frontend/src/pages/modules/inpatient/BillingDischargePage.js`
- [ ] Layout: left = patient/admission header + running bill (live `GET /admissions/{id}/bill`); right = deposits panel (list + add) + actions panel.
- [ ] Actions panel sections:
  - [ ] **Add Deposit** (any time during stay) — reuses existing `POST /admissions/{id}/deposits`.
  - [ ] **Review & Discharge** — opens confirmation dialog showing: final bill preview, current deposits sum, outstanding balance, payment-to-collect field (pre-filled with balance), method/reference, optional override reason if balance > 0 and operator chooses to bypass.
  - [ ] On confirm: call `POST /bill/finalize-and-settle` (atomic finalize + settlement) → then `POST /discharge` → then `POST /gate-pass` → then trigger PDF prints for final bill + gatepass.
  - [ ] Show step-by-step progress (spinner per step) so a failure at step N is clear.
- [ ] Surface room/bed release in the success toast ("Room {n}, Bed {label} released — status: cleaning").

### 2. Wire into InpatientModule navigation
- [ ] In `InpatientModule.js`, replace the separate **Billing**, **Payment Collection**, and **Gate Pass** subtabs with a single **Billing & Discharge** entry.
- [ ] From the Active admissions list and the Discharged admissions list, "Billing" / "Discharge" / "Collect Payment" / "Issue Gatepass" buttons all route to `BillingDischargePage` for that admission.
- [ ] Page adapts based on `admission.status`:
  - `admitted` → full flow available (deposits + finalize + discharge + gatepass).
  - `discharged` with outstanding dues → only "Collect Payment" + "Issue Gatepass" enabled (post-discharge cleanup path, kept here so users don't lose access to it).
  - `discharged` settled with gatepass → read-only summary + reprint buttons.

### 3. Remove the old tabs
- [ ] Delete `frontend/src/pages/modules/inpatient/PaymentCollectionTab.js`.
- [ ] Delete `frontend/src/pages/modules/inpatient/GatePassTab.js`.
- [ ] Remove their imports + tab definitions from `InpatientModule.js`.
- [ ] Remove the "Billing" subtab from `InpatientModule.js` (its content moves into the unified page).
- [ ] Strip the post-discharge "navigate to Billing tab and open finalize dialog" code from `InpatientModule.js`.

### 4. Keep DischargeWizard intact (revised plan)
Orchestration: BillingDischargePage calls `POST /bill/finalize-and-settle` FIRST → opens DischargeWizard → its existing `/discharge` POST succeeds (bill exists, balance zero) → on `onDischarged` callback, page opens gatepass dialog and prints. No edits to DischargeWizard. Its built-in 409 gate handling + in-wizard settle dialog stay as a safety net for edge cases.

### 5. Permission + gating
- [ ] All new actions reuse existing inpatient permission keys (`bill.view`, `bill.finalize`, `deposit.create`, `discharge.create`, `gatepass.issue`). No new perms needed; verify each button hides correctly per role.

### 6. QA checklist
- [ ] Happy path: admit → add deposit → run up charges → unified page shows running bill → confirm discharge with balance auto-collected → bill+gatepass print → bed status = cleaning, room.available_beds decremented.
- [ ] Balance = 0 path: finalize-and-settle handles zero-balance correctly (no settlement deposit row).
- [ ] Outstanding dues + override: operator types override reason → discharge proceeds, gatepass issued with override recorded.
- [ ] Refund path: deposits > final bill → settlement creates refund deposit, gatepass issued.
- [ ] Re-open a discharged admission: page is read-only, reprint works.
- [ ] Room release verified: check `Bed.status` and `RoomManagement.available_beds` before/after.

### 7. Out of scope (not touching now)
- Backend routes — already correct.
- Inpatient daily-charge cron.
- BillDetailDialog — reuse as-is for the running-bill preview.
- AdmitPatientWizard initial deposit — leave as-is (sensible entry point for first deposit).
