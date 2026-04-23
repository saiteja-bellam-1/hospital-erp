# Inpatient Module — User Guide

**Audience:** Doctors, nurses, receptionists, billing staff, inpatient administrators, and hospital administrators using the KT HEALTH ERP inpatient module day-to-day.

**Scope:** This guide covers every feature available in the inpatient module, what each role can do, and the end-to-end workflows for a typical admitted patient.

> For developer / API reference, see `backend/CLAUDE.md`.
> For permission configuration, see [PERMISSIONS_ADMIN_GUIDE.md](PERMISSIONS_ADMIN_GUIDE.md).

---

## 1. At a glance — what's in the module

The inpatient module supports the full stay lifecycle from pre-admission to post-discharge reporting:

| Stage | Features |
|---|---|
| **Pre-admission** | Bed reservations · Insurance pre-authorisation |
| **Admission** | Room/bed allocation · Readmission auto-detection · Patient allergies banner · Initial deposit |
| **Stay — Clinical** | Vital signs · Intake/Output (I/O) fluid balance · Medication Administration Record (MAR) · Nursing notes · Diet orders · Consent forms · Critical lab value alerts |
| **Stay — Orders** | Ward-round visits · Lab orders · Prescriptions · OT scheduling |
| **Stay — Billing** | Live running bill · Interim bills · Surgery packages · Ancillary service charges · Deposits & refunds · Insurance claim tracking · TPA bill splits |
| **Stay — Operations** | Bed transfers (room & ward) · Bed housekeeping · Nurse-patient assignments · Nurse duty roster (shift schedule) |
| **Discharge** | Normal / AMA / Transfer / Death workflows · Discharge summary PDF · Mortality details + death certificate |
| **Reporting** | 30-day readmission dashboard · Mortality reports · Incident reports & investigations |

---

## 2. Who can do what — role quick reference

The module honours fine-grained permissions. The defaults below ship out of the box; the hospital administrator can customise them via **Hospital Administration → Role Permissions** (see [PERMISSIONS_ADMIN_GUIDE.md](PERMISSIONS_ADMIN_GUIDE.md)).

### 🏥 Super Admin / Hospital Admin
**Bypass all permission checks.** Full access to every feature. Typically responsible for:
- Initial module setup (rooms, beds, rate config)
- Creating user accounts and assigning roles
- Customising role permissions
- Quality oversight, mortality reviews, incident closure

### 🩺 Doctor
Clinical care and ward management. Can:
- **Admit & discharge patients** (including death discharges with mortality details)
- **Record vital signs, I/O fluid balance, nursing notes, diet orders**
- **Administer medications** via MAR, record PRN doses
- **Order lab tests**, write prescriptions
- **Schedule OT procedures**
- **Record and withdraw consent forms**
- **Initiate and accept ward transfers**
- **Report incidents** (falls, medication errors, etc.)
- **Acknowledge critical lab value alerts**
- **Record patient allergies**
- **View bills and quality reports** (readmissions, mortality)
- **Upload admission documents** (consent scans, insurance papers)

_Cannot_: Finalise bills, issue refunds, apply surgery packages, manage TPA companies, investigate or close incidents.

### 👩‍⚕️ Nurse
Bedside care and shift documentation. Can:
- **Record vital signs, I/O fluid balance** (intake/output every shift)
- **Administer medications** via MAR — Given, Missed, Refused, Held, and PRN doses
- **Write nursing notes** per shift
- **Manage diet orders** and record dietary restrictions
- **Record patient allergies** (visible as red banner across the module)
- **Record ward round visits** (as nurse visits)
- **Witness consent forms** (record only, not withdraw)
- **Accept pending ward transfers** when receiving patients on your ward
- **Manage bed housekeeping** (mark beds as cleaning, dirty, out-of-service, or ready)
- **Report incidents** — falls, medication errors, pressure ulcers, needle sticks, etc.
- **Acknowledge critical lab value alerts**
- **View documents** uploaded for any admission

Use the **"My Patients only"** toggle on the Nurse Dashboard to filter the ward list to only patients you're assigned to for the current shift.

_Cannot_: Admit or discharge patients, finalise bills, apply packages, investigate incidents, withdraw consents.

### 💼 Inpatient Admin
Operational oversight and configuration. Can:
- **Admit, update, and discharge patients**
- **Create and manage rooms, beds, wards** (room types, bed counts, rate cards)
- **Set visit rate configuration** (doctor visit, nurse visit, procedure rates)
- **Manage bed housekeeping** and monitor turnover statistics
- **Create and convert bed reservations**
- **Assign nurses to admissions** (per shift, mark primary nurse)
- **Initiate ward transfers** and **transfer beds** between rooms
- **Schedule OT procedures** and **record OT charges** (surgeon, anaesthetist, room, equipment, consumables)
- **Add ancillary service charges** (imaging, dialysis, physiotherapy) to admissions
- **Manage pre-authorisations** — submit requests, record decisions, handle expansions
- **Update claim status** through the insurance workflow
- **Investigate and close incident reports**
- **Record deposits** (initial and top-ups)
- **Configure consent templates**, **set critical lab thresholds**
- **View readmission and mortality reports**
- **Upload and delete admission documents**

_Cannot_: Finalise bills, issue refunds, apply surgery packages, manage TPA catalog, administer medications, record clinical observations.

### 💰 Billing Admin
Financial operations and catalog management. Can:
- **View and generate interim bills** throughout the stay
- **Finalise the admission bill** at discharge (with discount and tax)
- **Apply surgery packages** to admissions
- **Manage ancillary service charges** (add, update, delete) and **record OT charges**
- **Receive deposits** and **issue refunds**
- **Configure bill splits** across cash, insurance, and TPA
- **Maintain the ancillary services catalog**, **surgery packages catalog**, and **TPA company list**
- **Manage pre-authorisations** and **update claim status**
- **View documents** uploaded for billing evidence

_Cannot_: Admit or discharge patients, record clinical observations (vitals, MAR, nursing notes), investigate incidents.

### 📋 Receptionist / Front Desk
Patient-facing scheduling and admission desk. Can:
- **Admit patients** at the front desk
- **Update admission details** (emergency contact, insurance info)
- **Receive initial deposits** and print receipts
- **Create bed reservations** for future elective admissions
- **View bills** and admission documents
- **Upload admission documents** (ID proofs, insurance papers)

_Cannot_: Anything clinical, any bill finalisation, any refund.

---

## 3. End-to-end workflow — a patient's journey

Here is the complete flow a patient may go through, mapped to who does what:

### Step 1 — Optional pre-admission (Receptionist / Inpatient Admin)

**Reserve a bed** for an elective admission scheduled in the future.
- Navigate to **Inpatient → Reservations**
- Click **New Reservation**, select patient, reservation date, target room type (or specific bed), and reason (elective / post-op recovery / transfer)
- When the patient arrives, click **Convert to Admission** on the reservation card

**Request insurance pre-authorisation** if the patient is covered under cashless insurance or a TPA.
- Navigate to **Inpatient → Pre-Authorisations**
- Click **New Request**, enter insurance provider, policy number, requested amount, and optional TPA
- Once the insurer responds, open the request and click **Record Decision** (Approved / Rejected / Expired)
- Upload the approval document if issued
- Request expansion if treatment costs exceed the initial approval

### Step 2 — Admission (Doctor / Inpatient Admin / Receptionist)

From **Active Admissions** click **New Admission**:
1. Search and select the patient
2. Pick admitting doctor, room, and bed
3. Choose admission type (elective / emergency / transfer), admission reason, condition on admission
4. Enter insurance details (optional) and emergency contact
5. Submit

On submission, the system automatically:
- Assigns an admission number `ADM{YYYYMMDDHHMMSS}`
- Decrements the room's available bed count
- **Checks readmission history** — if the patient had a discharge within the last 30 days, the admission is flagged with a `Readmit` badge, previous admission linked, and days-since-discharge shown
- Shows a **red allergy banner** at the top of the admission view if the patient has any active allergies (severity determines colour — anaphylaxis is red, moderate is orange)
- Shows a **red critical lab alert banner** if the patient has any outstanding critical lab values

Record the **initial deposit** immediately via the **Deposits** tab (cash / card / UPI / cheque / online / bank transfer). Print the receipt PDF for the family.

### Step 3 — During the stay

The admission slide-over has 14 sub-tabs organised into 4 primary groups. Click the group name (Clinical / Orders & Care / Billing / Operations) to see only the relevant sub-tabs.

#### 🟢 Clinical group — Nurses and Doctors

**Vitals (Nurse/Doctor)** — Record BP, HR, RR, Temp, SpO₂, Pain, GCS, blood glucose every shift. Out-of-range values are automatically flagged in red and the admission shows an abnormal indicator.

**MAR — Medication Administration Record (Nurse/Doctor)** —
- Click **Generate Schedule (24h)** to materialise scheduled doses from the patient's active prescriptions (supports BD, TDS, QID, Q4H, Q6H, Q8H, Q12H, STAT, HS)
- For each scheduled dose, click **Administer** and record Given / Missed / Refused / Held with time, route, and any notes
- For PRN (as-needed) medications, click **Record PRN Dose** with indication and dose given
- Overdue doses show a red `overdue` badge
- The administer dialog checks the patient's allergies and warns if the medicine name matches a recorded drug allergy

**I/O — Intake/Output Fluid Balance (Nurse/Doctor)** —
- Record intake (oral, IV, NG tube, blood product, irrigation) and output (urine, drain, NG aspirate, vomitus, stool, blood loss) per shift
- The page shows per-shift totals and a running **net balance** (positive = net intake, indicating fluid retention)
- Critical for ICU and post-op patients

**Nursing (Nurse/Doctor)** — Free-text nursing notes by shift and note type (observation, medication, vitals, procedure, handover, general).

**Diet (Nurse/Doctor)** — Diet orders with type (regular, diabetic, liquid, soft, NPO, low salt, renal, cardiac), meal instructions, allergies, and notes. Creating a new diet order automatically deactivates the previous active order. The Nurse Dashboard has a separate page listing all active diet orders across the ward for meal delivery staff.

**Allergies (Nurse/Doctor)** — Patient-level allergy register (carries across all admissions). Categorised by type (drug / food / environmental / other) and severity (mild / moderate / severe / anaphylaxis). Drug allergies trigger warnings during prescription and MAR administration.

**Consents (Nurse records, Doctor withdraws)** — Signed consent forms for surgical procedures, anaesthesia, blood transfusions, high-risk procedures, etc. Templates are managed in Billing Setup. Patient signature is captured as typed name or drawn image. Guardian consent requires guardian name and relationship. Print signed consent PDFs. Withdrawing a consent preserves the original record with a withdrawal reason.

#### 🔵 Orders & Care group — Doctors

**Visits (Doctor/Nurse)** — Ward-round visits, auto-charged based on the hospital's rate configuration.

**Lab (Doctor)** — Order lab tests directly against the admission. Critical values detected by configured thresholds auto-create alerts visible as the red banner.

**Meds (Doctor)** — View and manage prescriptions linked to the admission.

#### 💰 Billing group — Billing Admin (and Inpatient Admin for oversight)

**Bill tab** — Live running bill showing:
- Room charges (room rate × stay days)
- Visit charges (grouped by type)
- OT procedure charges (surgeon + anaesthetist + OT room + equipment + consumables)
- Ancillary service charges (imaging, dialysis, etc.)
- Pharmacy (dispensed prescriptions)
- Lab test charges
- Discount (flat ₹ or percentage) and tax (percentage)

If a surgery package is applied, the bill switches to package mode showing the agreed price plus any excess (extra days, services not included in the package). The **Bills issued** list shows all interim and final bills for the admission.

Actions:
- **Generate Interim** — creates a mid-stay bill snapshot. Items on the interim bill are marked billed so they won't appear on subsequent bills.
- **Finalise Bill** — end-of-stay bill that includes all remaining unbilled items
- **Apply Package** — switch the billing mode for this admission
- **Add Service Charge** — add an ancillary service (requires Inpatient Admin or Billing Admin)
- **Split** (on each finalised bill) — distribute the bill across cash / insurance / TPA payers. Sum must equal bill total.
- **Print Bill** — PDF with optional hospital header

**Deposits tab** — Balance summary at top shows collected, refunded, net deposits, total billed, and current balance (positive = credit / refund due; negative = patient owes). Actions:
- **Receive Deposit** (initial or top-up, multiple payment methods)
- **Issue Refund** (only when balance is positive, won't exceed available credit)
- Receipt PDF for every entry

**Insurance tab** — Track insurance claim state through the workflow: none → draft → submitted → approved/rejected → draft (if rejected).

#### 🟣 Operations group — Inpatient Admin, Nurses

**Staff tab** — Two sub-sections:

*Nurse Assignments*:
- Click **Assign Nurse** to allocate a nurse to this admission for a specific shift (morning / afternoon / night) on a specific date
- Mark one nurse as **primary** per shift — the primary flag is automatically moved if you assign another
- Nurses see only their assigned patients in the Nurse Dashboard when they enable the "My Patients only" toggle

*Bed / Ward Transfers*:
- History of every bed or room change (auto-logged from any admission edit that changes room/bed)
- Each transfer shows transfer type (bed change / room change / ward change), reason, who moved the patient, and timestamp
- Click **Initiate Ward Transfer** for a structured inter-ward transfer
    - Target room + bed (optional)
    - Mandatory **reason** and **clinical handover note**
    - Creates a transfer in **pending** state
    - The receiving ward's nurse or doctor accepts via the **Accept** button — only then does the admission's bed/room actually change
    - Pending transfers also appear on the **Housekeeping** page for receiving ward staff to action

**Docs tab** — Upload and view admission documents (consent forms, referral letters, insurance docs, lab reports, discharge summaries). Max 10 MB per file. Supports PDF, JPEG, PNG, GIF, WebP, and Word (.doc/.docx).

### Step 4 — Discharge (Doctor or Inpatient Admin)

Click **Discharge** from the admission header:
1. Pick discharge type — **normal**, **against medical advice (AMA)**, **transfer**, or **death**
2. Fill condition on discharge, discharge summary, diagnosis, treatment given, medications prescribed, follow-up instructions, follow-up date, diet & activity restrictions
3. Submit

On submission:
- Admission status changes to `discharged`
- Total stay days calculated automatically
- Structured bed is auto-flipped to **cleaning** status (visible on the Housekeeping page for the cleaning team). The bed won't count as available until cleaning completes.
- If discharge type is **death**, the **Mortality Details** dialog opens automatically (see next step)

#### Death discharge — Mortality workflow (Doctor)

When discharge type is `death`, a follow-up dialog collects:
- Cause of death (free-text; pre-populated from discharge diagnosis)
- Time of death
- Death certificate number
- MLC required? MLC number (if applicable)
- Autopsy done? Autopsy findings
- Body handed over to whom? Relationship, handover time, ID proof

Once saved, the death certificate PDF can be generated via **Quality Reports → Mortality Records → Certificate** button.

### Step 5 — Post-discharge billing (Billing Admin)

- **Finalise the bill** if not already done at discharge
- **Split the final bill** across cash, insurance, and TPA payers
- **Issue a refund** if the deposit balance is positive (patient has credit)
- Update **claim status** to `submitted` then `approved`/`rejected` when the insurer decides

### Step 6 — Quality & safety reports

**Incidents** — any clinical staff can report (falls, medication errors, pressure ulcers, needle sticks, infections, equipment failures, documentation errors, wrong patient, other). Incidents progress through state machine: **reported → investigating → resolved → closed**. Inpatient administrators investigate and close incidents, recording:
- Investigation notes
- Root cause
- Resolution
- Corrective actions
- Preventive measures

Monthly report shows counts by type, severity, and status.

**Readmissions** — Quality Reports page shows patients readmitted within 30 days of their previous discharge, with days-since-last-discharge and admission reason.

**Mortality Records** — list of all death discharges with cause, MLC/autopsy flags, death certificate number, and handover details. Certificate PDF downloadable from the record.

---

## 4. Where each feature lives in the UI

**Main left sidebar — Inpatient section** (visibility depends on your role):
1. **Ward Overview** — bed occupancy dashboard
2. **Active Admissions** — list of admitted patients, search, open any for the slide-over
3. **Discharge History** — past discharges with PDF summaries (admin / doctor / billing)
4. **OT Schedule** — procedure calendar, status tracking, charges entry (admin / doctor)
5. **Pre-Authorisations** — insurance pre-auth requests and decisions (admin / billing)
6. **Reservations** — future bed bookings and conversion to admission (admin / receptionist / front desk)
7. **Duty Roster** — weekly nurse shift schedule grid, bulk assignment, coverage check (admin / nurse / doctor)
8. **Housekeeping** — beds awaiting cleaning + pending ward transfers + turnover stats (admin / nurse)
9. **Incidents** — incident reports and investigations (admin / nurse / doctor)
10. **Quality Reports** — 30-day readmissions + mortality records (admin / doctor)
11. **Room Management** — rooms, beds, rate configuration (admin only)
12. **Billing Setup** — catalogs (Ancillary Services, Surgery Packages, TPA Companies, Consent Templates) (admin / billing)

Each item is a direct URL under `/dashboard/inpatient/...` — nav highlights as you navigate, and browser back/forward works as expected.

**Admission slide-over (opened by clicking any admitted patient):**
Grouped 14-tab layout — Clinical (Vitals, MAR, I/O, Nursing, Diet, Allergies, Consents), Orders & Care (Visits, Lab, Meds), Billing (Bill, Deposits, Insurance), Operations (Staff, Docs).

**Nurse Dashboard:**
- Ward Admissions list with the **"My Patients only"** toggle (filters by current shift assignments)
- Active Diet Orders across all admitted patients
- Quick **Record Visit** action from any admission row
- Separate **Vitals** entry from the patient search (EHR-level vitals, not admission-scoped)

**Doctor Dashboard:**
- Ward Rounds — list of admissions where the current doctor is admitting or attending physician
- Per-admission: visit history, nursing notes, admission details, record new doctor visit

---

## 4a. The duty roster

The **Duty Roster** page (Inpatient sidebar) lets the inpatient administrator plan which nurses are scheduled to work which shifts on which dates. This is separate from the per-admission **nurse assignment** (Staff tab) — the roster is the *master schedule*, the assignment is *which patients each on-duty nurse is responsible for*.

### What you see

A weekly grid:
- **Rows:** every active nurse on staff (anyone with the `nurse` role)
- **Columns:** 7 days, with each day split into 3 shift cells — **M** (morning), **A** (afternoon), **N** (night)
- **Cells:** colour-coded status badges
    - 🟢 `W` (working — green)
    - 🔵 `O` (on call — blue)
    - 🟠 `L` (leave — orange)
    - ⚪ `-` (off / rest day — grey)
    - ➕ (empty — click to assign)
- **Footer row:** "Working / shift" — count of working nurses per shift per day. **Red highlight** if below the configured minimum staffing threshold.

### Working with the grid

- **Click any cell** — opens the assign/edit dialog for that single (nurse, date, shift). Pick status (working / on call / leave / off), optional ward, optional notes. If editing an existing entry, you can also remove it.
- **Bulk Assign** button (top right) — apply the same status across many nurses × date range × shifts in one shot. Useful for "Nurses A, B, C all morning shifts next week" or "Nurses D, E on leave Monday–Wednesday". Tick **Overwrite** to replace any existing entries in the range.
- **Prev Week / Next Week / This Week** — navigate the schedule
- **Min/shift** input — adjust the minimum staffing threshold; the coverage row recalculates instantly

### Status meanings

| Status | What it means | Counts toward minimum coverage? | Can be assigned to patients? |
|---|---|:---:|:---:|
| **working** | Scheduled to work this shift | ✓ | ✓ |
| **on_call** | Available if needed (backup) | ✗ | ✓ |
| **leave** | On approved leave (sick, planned vacation) | ✗ | ✗ |
| **off** | Scheduled rest day | ✗ | ✗ |

### How the roster integrates with patient assignment

When you go to **Active Admissions → open a patient → Staff tab → Assign Nurse**, the dropdown by default shows **only nurses on duty** (working or on_call) for the selected shift and date. There's an "On-duty only" toggle in the dialog if you need to override (e.g., emergency where a nurse off-duty must be called in).

If no nurses are rostered for that shift/date, the dialog warns you and prompts you to either uncheck the filter or update the duty roster first.

### Coverage warning

The bottom row of the grid shows the count of nurses rostered as `working` for each (date, shift). Cells highlighted in red indicate the count is **below the minimum** (default 2). Adjust the **Min/shift** field at the top to set your hospital's standard. Many small hospitals run 2-2-2; larger ones run 4-3-3 (more day staff). ICUs typically need 1:2 nurse-to-patient ratios so the threshold should reflect bed count.

### Permissions

| Action | Permission | Default roles |
|---|---|---|
| View the roster | `view_roster` | nurse, doctor, inpatient_admin (super/hospital admin bypass) |
| Create / edit / bulk / delete entries | `manage_roster` | inpatient_admin (super/hospital admin bypass) |

Nurses can see when they're scheduled (own and team), but only the inpatient administrator can plan and edit. Customise via Hospital Administration → Role Permissions.

### Tips

- **Plan a fortnight at a time.** Use Bulk Assign to set the standard pattern (e.g., "Nurse A always works morning Mon-Fri") then tweak individual cells for leave or shift swaps.
- **Mark approved leaves immediately.** This prevents accidental patient assignment to nurses who are off.
- **Use `on_call` for backup staff.** The patient-assignment dropdown still includes them but the coverage count doesn't, which honestly reflects who's expected at the bedside.
- **Check coverage every Friday for the next week.** Red cells in the footer row are an early warning of understaffed shifts that need swaps or relief.

---

## 5. Common questions

**Q: Why does the "My Patients only" toggle show no patients?**
A: You haven't been assigned to any admissions for today's shift. An inpatient admin assigns nurses via the **Staff** tab of each admission.

**Q: Why am I getting "Insufficient permissions" when I try to finalise a bill?**
A: Only billing admins can finalise bills by default. Ask your hospital administrator to either do it for you or grant your role the `finalize_bill` permission via **Hospital Administration → Role Permissions**.

**Q: Can I edit a signed consent?**
A: No — signed consents are immutable for compliance. To correct an error, **withdraw** the consent (records the withdrawal reason) and create a new one.

**Q: The readmission badge is on my new admission. What does it mean?**
A: The patient was discharged within the last 30 days. The badge tooltip shows days since the previous discharge. This is informational — no workflow is blocked.

**Q: A bed is stuck in "cleaning" — can I mark it ready without actually cleaning?**
A: Yes — navigate to **Inpatient → Housekeeping** and click **Mark Ready** on the bed card. This is audited so use judgement.

**Q: A consent template I configured isn't appearing in the Record Consent dialog.**
A: The template's `consent_type` must match the consent type you're recording. If a patient needs a surgical consent, only surgical templates show up. Check the template's type in **Billing Setup → Consent Templates**.

**Q: Can I void a finalised bill?**
A: Not directly. Instead, issue a refund against the deposit and generate a fresh interim or final bill for the corrected amount. The original bill record is preserved for audit.

**Q: A critical lab alert is stuck as "new" — how do I clear it?**
A: Either **Acknowledge** it (you've seen it, no action yet) or **Mark Addressed** with notes describing what you did (e.g., "Administered Kayexalate for hyperkalemia"). Addressed alerts are immutable.

**Q: Refund is rejected — says "exceeds available credit".**
A: The refund amount can't exceed the balance summary's `Balance` value (positive balance = credit available for refund). If the patient still owes money, you can't refund anything.

---

## 6. Tips for operators

- **Use interim billing for long stays.** Generate an interim bill at least weekly for patients staying 7+ days. Insurance claims often require interim submissions.
- **Record I/O every shift in ICU.** Missing entries skew the balance calculation and hide clinical deterioration.
- **Set critical lab thresholds early.** Configure `critical_low` and `critical_high` on each relevant `LabTestParameter` via the admin UI. Every future lab result will be scanned against these.
- **Pre-fill common consent templates.** Adding surgical, anaesthesia, and blood transfusion templates in Billing Setup saves typing the same content for every patient.
- **Assign nurses at the start of each shift.** Primary nurse should be marked for clarity in handovers.
- **Check the Housekeeping page each morning.** Cleaning turnover delays have a direct impact on bed availability for emergency admissions.
- **Close incidents promptly.** Open incidents count against your hospital's quality metrics in the monthly report.

---

## 7. Glossary

| Term | Meaning |
|---|---|
| **Admission** | A single inpatient stay. Starts with admit, ends with discharge. |
| **AMA** | Against Medical Advice — discharge initiated by the patient against the doctor's recommendation. |
| **Ancillary service** | Chargeable service delivered during the stay outside of visits/OT/pharmacy/lab (imaging, physiotherapy, dialysis, etc.). |
| **Bill split** | Distribution of a single bill amount across multiple payers (cash / insurance / TPA). Must sum to the bill total. |
| **Bed reservation** | Future bed booking for an expected admission. |
| **Interim bill** | A mid-stay bill snapshot. Items on it are marked billed and excluded from subsequent bills. |
| **MAR** | Medication Administration Record — per-dose log for each scheduled or PRN medication. |
| **MLC** | Medico-Legal Case — a case that requires police/legal notification (accidents, assaults, suspicious deaths). |
| **Net balance (I/O)** | Total intake minus total output. Positive = fluid retention. |
| **OT** | Operating Theatre. |
| **Package** | Fixed-price bundle for a specific surgery or treatment (e.g., cataract, LSCS, appendectomy). Includes a defined number of stay days and services. |
| **Pre-authorisation** | Insurance or TPA's advance approval for cashless treatment, valid for a specified amount and duration. |
| **PRN** | Pro Re Nata — "as needed" medication, not on a fixed schedule. |
| **Readmission** | A new admission within 30 days of the patient's last discharge. |
| **Shift** | Nursing shift — morning / afternoon / night. Used to scope vitals, I/O, nursing notes, diet orders, nurse assignments. |
| **TPA** | Third Party Administrator — intermediary that processes insurance claims on behalf of the insurer. |
| **Transfer (ward)** | Movement of an admitted patient between wards. Structured transfers require a clinical handover note and acceptance by the receiving ward. |
