# Inpatient Module — Frontend Design (post gap-fix)

Scope: pages, sections, and UI flow for the gaps we just shipped on the
backend (B1 payer schemes, B2 payer conversion, B3 referring doctor + IP
acceptance, B4 duty doctor, B5 face-sheet / case-sheet, B6 gate pass).
The aim is a coherent **flow**, not a pile of dialogs.

Stack assumed: React 18 + Tailwind + shadcn/ui (matches the rest of the app).

---

## 1. Flow at a glance

```
Reception ──┐
            │
            ▼
   ┌────────────────────────┐
   │ Admit Patient — Wizard │  (3 steps: identity → clinical/payer →
   └─────────┬──────────────┘    declarations)
             │
             ▼ (creates Admission with acceptance_status='pending')
   ┌────────────────────────┐
   │ Pending Acceptance     │  IP doctor / inpatient_admin queue
   │ Queue (IP floor)       │
   └─────────┬──────────────┘
             │ accept / reject
             ▼ (acceptance_status='accepted' unlocks clinical actions)
   ┌────────────────────────┐
   │ Active Admission       │  Slide-over with tab groups:
   │  Detail                │   Clinical · Orders · Billing · Operations
   └─────────┬──────────────┘
             │
             ▼ (discharge submitted, bill cleared)
   ┌────────────────────────┐
   │ Discharge Exit /       │  Generate Gate Pass; print
   │ Gate Pass              │
   └────────────────────────┘
```

Supporting screens (sidebar):
- **Duty Roster** (doctors + nurses, unified)
- **Payer Schemes** (Hospital Administration sub-tab)

---

## 2. Sidebar (Inpatient Module)

New/changed items in **bold**.

```
┌──────────────────────────────┐
│  Ward Overview               │
│  Active Admissions           │
│ ▸ Admit Patient   (action)   │  ← opens the 3-step wizard
│ ★ Pending Acceptance  [3]    │  ← NEW, badge = count waiting
│  Discharge History           │
│ ★ Ready for Gate Pass  [2]   │  ← NEW, badge = discharged + bill cleared
│  OT Schedule                 │
│  Pre-Authorisations          │
│  Reservations                │
│ ★ Duty Roster                │  ← NEW (doctors + nurses)
│  Housekeeping                │
│  Quality Reports             │
│  Room Management             │
│  Billing Setup               │
└──────────────────────────────┘
```

"Admit Patient" is a deliberate top-level CTA (not buried in a dropdown)
because the spoken flow starts there.

---

## 3. Admit Patient Wizard — 3 steps

Replaces the current single overflowing dialog. Each step is its own panel,
saved progressively (draft auto-saves so reception can pause).

### Step 1 — Identity & Bed

```
┌──────────────────────────────────────────────────────────────┐
│ Admit Patient                            Step 1 of 3   [×]   │
│ ●───────○───────○                                            │
│ Identity   Clinical   Declarations                           │
├──────────────────────────────────────────────────────────────┤
│ Patient                                                      │
│ ┌───────────────────────────────┐  [ Quick-register new ▸]  │
│ │ 🔍 Search patient by name/MRN │                            │
│ └───────────────────────────────┘                            │
│ Selected: Ramesh Kumar  (M / 54)  · MRN MED-2026-00417       │
│                                                              │
│ ─── Bed assignment ─────────────────────────────────────     │
│ Ward / Room *      [ ICU-A — Bed 3  ▾ ]                      │
│ Type               ICU · ₹2,500 / day                        │
│ Estimated stay     [  3  ] days                              │
│                                                              │
│ Admission type *   ( ) Elective  (●) Emergency  ( ) Transfer │
│ Triage (if emerg)  [ 2 — Emergent ▾ ]                        │
│                                                              │
│                                       [ Cancel ] [  Next →  ]│
└──────────────────────────────────────────────────────────────┘
```

### Step 2 — Doctors, Payer & Deposit

The heart of the spoken flow. Three sub-sections in one scrollable panel.

```
┌──────────────────────────────────────────────────────────────┐
│ Admit Patient                            Step 2 of 3         │
│ ●───────●───────○                                            │
├──────────────────────────────────────────────────────────────┤
│ ── Doctors ─────────────────────────────────────────────     │
│ Referring doctor      ◉ Internal  ○ External                 │
│   Internal:  [ Dr. Rao, Cardiology  ▾ ]                      │
│   External:  ────────────────────────────                    │
│ Admitting / joining * [ Dr. Sharma, MD DM Cardio ▾ ]         │
│ Attending (under)     [ Dr. Iyer, MS Surgery ▾ ]             │
│ □ Require IP-doctor acceptance before clinical actions       │
│   (recommended; uncheck only if admitting doctor will        │
│    also handle the patient on the floor)                     │
│                                                              │
│ ── Payer ───────────────────────────────────────────────     │
│ How is the patient paying? *                                 │
│  ┌─────────┐ ┌────────────┐ ┌──────────────┐ ┌──────────┐    │
│  │  Cash   │ │ Aarogyasri │ │  Teachers'   │ │  Private │    │
│  │   ●     │ │   scheme   │ │   scheme     │ │ insurance│    │
│  └─────────┘ └────────────┘ └──────────────┘ └──────────┘    │
│  ┌──────────┐ ┌──────────────┐                               │
│  │   TPA    │ │ Govt employee│                               │
│  └──────────┘ └──────────────┘                               │
│                                                              │
│ (visible if non-cash chosen)                                 │
│ Scheme member ID    [ AGS-1029-3811           ]              │
│ Approval status     [ Pending ▾ ]   Ref [ AGS-APR-... ]      │
│ Approved amount ₹   [           ]                            │
│                                                              │
│ ── Advance deposit ─────────────────────────────────────     │
│ Amount ₹            [   5000        ]                        │
│ Method              [ Cash ▾ ]   Receipt # [ auto ]          │
│ □ Waive deposit (emergency) — requires reason                │
│                                                              │
│                              [ ← Back ] [ Save draft ] [Next→]│
└──────────────────────────────────────────────────────────────┘
```

Visual nuance: payer choices are large radio cards (not a dropdown) so
the operator sees the full set at once. The currently selected card has
a coloured border; everything else stays neutral.

### Step 3 — Declarations (face-sheet + case-sheet)

```
┌──────────────────────────────────────────────────────────────┐
│ Admit Patient                            Step 3 of 3         │
│ ●───────●───────●                                            │
├──────────────────────────────────────────────────────────────┤
│ Required signed forms                                        │
│                                                              │
│ ┌──────────────────────────────┐  ┌──────────────────────────│
│ │ 📄 Face Sheet                 │  │ 📄 Case Sheet (declar.) │
│ │ Admission identification +    │  │ General consent /       │
│ │ responsible person details    │  │ liability declaration   │
│ │                               │  │                         │
│ │   [ Preview ]                 │  │   [ Preview ]           │
│ │   [ Sign & attach ]           │  │   [ Sign & attach ]     │
│ │                               │  │                         │
│ │   ⚠ Not yet signed            │  │   ✓ Signed by Ramesh K. │
│ └──────────────────────────────┘  └──────────────────────────│
│                                                              │
│ Both must be signed before admission can be finalised.       │
│ (Sign now reuses the existing consent signature dialog.)     │
│                                                              │
│                              [ ← Back ] [ Save draft ]       │
│                                            [ Admit patient ] │
└──────────────────────────────────────────────────────────────┘
```

The wizard creates the `Admission` row only on the final "Admit patient"
click; everything before is held in client-side draft state +
auto-checkpointed to localStorage by admission-draft key.

---

## 4. Pending Acceptance Queue (NEW page)

For IP doctors / inpatient_admin: the patients who have been admitted
but not yet accepted by the floor team. This is what your hospital
already does informally with "admitted under us, accept" — now explicit.

```
┌────────────────────────────────────────────────────────────────┐
│ Pending Acceptance                                             │
│                                                                │
│ ┌──────────────────────────────────────────────────────────┐   │
│ │  Patient        Ward / Bed     Admit time   Admitted by  │   │
│ ├──────────────────────────────────────────────────────────┤   │
│ │ Ramesh Kumar    ICU-A / B3     10:42 AM     Dr. Sharma   │   │
│ │ Cardiology · 54 M · Emergency · Triage 2                 │   │
│ │ Referring: Dr. Rao  |  Payer: Aarogyasri (pending)       │   │
│ │                          [ View detail ▸ ] [ Accept ▸ ]  │   │
│ │                                                          │   │
│ │ Suma Devi       Gen-W2 / 5     09:11 AM     Dr. Reddy    │   │
│ │ Internal med · 41 F · Elective                           │   │
│ │ Referring: (external) Dr. Khan  |  Payer: Cash           │   │
│ │                          [ View detail ▸ ] [ Accept ▸ ]  │   │
│ └──────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘

Accept dialog:
┌──────────────────────────────────────┐
│ Accept admission                     │
│                                      │
│ Patient: Ramesh Kumar (ICU-A / B3)   │
│ Accepting doctor *  [ Dr. Iyer  ▾ ]  │
│                                      │
│   [ Cancel ]    [ Accept admission ] │
└──────────────────────────────────────┘

Reject dialog:
┌──────────────────────────────────────┐
│ Reject admission                     │
│                                      │
│ Reason *  ┌──────────────────────┐   │
│           │                      │   │
│           └──────────────────────┘   │
│                                      │
│   [ Cancel ]    [ Reject — patient   │
│                   must be re-admitted]│
└──────────────────────────────────────┘
```

Banner inside any admission detail view while `acceptance_status=pending`:

```
┌──────────────────────────────────────────────────────────────┐
│ ⏳ Awaiting IP doctor acceptance.                            │
│   Clinical actions (vitals, MAR, visits, I/O) are locked.    │
│   [ Accept ]   [ Reject ]                                    │
└──────────────────────────────────────────────────────────────┘
```

The Clinical / Orders tabs render with disabled buttons + a tooltip
("Locked until IP doctor accepts") while pending. After accept, the
banner switches to a green check + collapse, and the tabs unlock.

---

## 5. Active Admission Detail (slide-over)

Same shell as today (slide-over from the admissions list), but the
header strip and tabs reflect the new fields.

```
┌──────────────────────────────────────────────────────────────────┐
│  Ramesh Kumar  · M / 54 · MRN MED-2026-00417           [×]       │
│  ICU-A / B3    Adm: 12/05 10:42    Stay: 2d                      │
│                                                                  │
│  ── Doctors ──────────────────────────────────────────────       │
│  Referring  Dr. Rao (Cardiology)                                 │
│  Admitting  Dr. Sharma     Attending  Dr. Iyer                   │
│                                                                  │
│  ── Payer ────────────────────────────────────────────────       │
│  [ Aarogyasri · Pending · ₹50,000 ]   [ Change payer ▾ ]         │
│                                                                  │
│  ── Status chips ─────────────────────────────────────────       │
│  ✓ Accepted   · Bill ₹14,200   · Deposits ₹5,000   · Bal ₹9,200  │
├──────────────────────────────────────────────────────────────────┤
│  Clinical · Orders & Care · Billing · Operations                 │
│  └─Vitals · MAR · I/O · Nursing · Allergies · Consents           │
├──────────────────────────────────────────────────────────────────┤
│  (active tab body — Vitals chart etc.)                           │
└──────────────────────────────────────────────────────────────────┘
```

### Change Payer dialog (B2)

```
┌──────────────────────────────────────────────────┐
│ Change payer                                     │
│                                                  │
│ Current  Aarogyasri (pending) · ₹50,000          │
│                                                  │
│ New payer *                                      │
│  ( ) Cash    (●) Private insurance               │
│  ( ) TPA     ( ) Govt scheme — Teachers'         │
│                                                  │
│ Member ID    [ POL-198273           ]            │
│ Status       [ Approved ▾ ]                      │
│ Ref / amount [ INS-1029 ]  ₹[ 75000 ]            │
│                                                  │
│ Reason *  ┌──────────────────────────────────┐   │
│           │ Aarogyasri approval rejected     │   │
│           │ — patient switching to private   │   │
│           └──────────────────────────────────┘   │
│                                                  │
│ ℹ Future charges go to the new payer. Already-   │
│   finalised bill splits remain on the old payer. │
│                                                  │
│        [ Cancel ]   [ Change payer ]             │
└──────────────────────────────────────────────────┘
```

Below the payer chip in the detail header, a small "View history" link
expands an inline timeline:

```
Payer history
  • 14/05 14:30  Aarogyasri → Private insurance
    "Aarogyasri approval rejected" — by reception (Priya)
  • 12/05 10:42  Cash → Aarogyasri (initial)
```

### Clinical tab — Visits (B4 duty doctor)

The "Add visit" dialog gains a visit-type selector with three explicit
options instead of a generic dropdown:

```
┌──────────────────────────────────────────────────┐
│ Add visit                                        │
│                                                  │
│ Visit type *                                     │
│  ┌──────────────┐ ┌──────────────┐ ┌───────────┐ │
│  │ Doctor       │ │ Duty doctor  │ │  Nurse    │ │
│  │ (consultant) │ │   (round)    │ │  visit    │ │
│  │      ●       │ │              │ │           │ │
│  └──────────────┘ └──────────────┘ └───────────┘ │
│                                                  │
│ Visitor *                                        │
│   [ Dr. Sharma — consultant fee ₹1,000  ▾ ]      │
│                                                  │
│ ── (if Duty doctor selected) ─────────────────   │
│   Duty doctors on-floor right now:               │
│     ● Dr. Kapoor  (afternoon shift, ICU)         │
│     ○ Dr. Nair    (afternoon shift, on-call)     │
│   Charge: ₹500 (institutional duty rate)         │
│                                                  │
│ Round checklist                                  │
│  ☑ Vitals reviewed  ☑ Labs reviewed              │
│  ☐ Pain assessed    ☐ Family updated             │
│ Plan for today  ┌────────────────────────────┐   │
│                 │                            │   │
│                 └────────────────────────────┘   │
│                                                  │
│            [ Cancel ]   [ Record visit ]         │
└──────────────────────────────────────────────────┘
```

For Duty Doctor, the visitor list comes from
`GET /api/inpatient/duty-doctor/on-duty?at=now` so the operator only
sees doctors who are actually rostered for this shift. The fee preview
on the right of the visitor row clarifies why duty doctor visits all
charge the same flat amount.

If someone tries to record a duty visit for a non-rostered doctor, the
backend 409 is surfaced as a red toast:

```
✗ Dr. Iyer is not on the afternoon duty roster.
  Record this as a regular doctor_visit, or add a roster
  entry from Duty Roster.
```

### Operations tab — Documents

Add a "Required signed forms" section at the top that surfaces face-sheet
and case-sheet status. Same visual as in the wizard step 3 — click to
sign / view PDF.

---

## 6. Duty Roster (NEW page)

One page, two role tabs. Reuses the existing nurse-roster grid layout
so we don't reinvent it.

```
┌─────────────────────────────────────────────────────────────────┐
│ Duty Roster      [ Doctors | Nurses ]            Week of 12 May │
│                                                                 │
│ ┌────────┬───────┬───────┬───────┬───────┬───────┬───────┬────┐ │
│ │        │ Mon12 │ Tue13 │ Wed14 │ Thu15 │ Fri16 │ Sat17 │Sun │ │
│ ├────────┼───────┼───────┼───────┼───────┼───────┼───────┼────┤ │
│ │Dr. Kap.│ M ICU │ M ICU │ M ICU │ —     │ N gen │ N gen │ —  │ │
│ │Dr. Nair│ A ICU │ A ICU │ leave │ leave │ —     │ M ICU │M IC│ │
│ │Dr. Sin.│ N gen │ —     │ M gen │ A gen │ A gen │ —     │N ge│ │
│ └────────┴───────┴───────┴───────┴───────┴───────┴───────┴────┘ │
│  M morning · A afternoon · N night · "leave"/"—" rest day        │
│                                                                 │
│ [ + Add entry ]   [ Bulk-assign week ▸ ]   [ Coverage report ]  │
└─────────────────────────────────────────────────────────────────┘
```

Click a cell → small popover to edit / delete / switch status. Bulk-assign
mirrors the nurse-roster bulk dialog.

A right-side "Now on duty" panel for quick reference:

```
┌─────────────────────────────────┐
│ Now on duty (Tue 14:35 — afternoon) │
│                                 │
│  ICU                            │
│   • Dr. Nair (working)          │
│  General Ward                   │
│   • Dr. Singh (on call)         │
│                                 │
│  Nurses                         │
│   • S. Latha · S. Rita · ...    │
└─────────────────────────────────┘
```

---

## 7. Payer Schemes (Hospital Administration → new tab)

Lives under Hospital Administration (not Inpatient sidebar) because it's
configuration, not daily ops.

```
┌─────────────────────────────────────────────────────────────────┐
│ Hospital Administration                                         │
│ [ Users · Roles · Role permissions · Modules · Payer schemes ]  │
├─────────────────────────────────────────────────────────────────┤
│  Payer schemes                          [ + Add scheme ]        │
│                                                                 │
│  Code        Name                      Type            Active   │
│  ───────────────────────────────────────────────────────────    │
│  CASH        Cash                      Cash             ✓        │
│  AAROGYASRI  Aarogyasri                Govt scheme      ✓        │
│  TEACHERS    Teachers' Health Scheme   Govt scheme      ✓        │
│  EJHS        Employee Health Scheme    Govt scheme      ✓        │
│  PRIVATE     Private Insurance         Private ins.     ✓        │
│  TPA         TPA (Third Party Admin)   TPA              ✓        │
│  CGHS        CGHS                      Govt scheme      ✓ (edit) │
│                                                                 │
│  (click row to edit · drag handle to reorder appearance         │
│   on the admit wizard's payer card grid)                        │
└─────────────────────────────────────────────────────────────────┘
```

Add/edit form keeps it tiny: code, name, scheme_type (dropdown), active,
optional notes.

---

## 8. Ready for Gate Pass (NEW page) + the Gate Pass slip

A focused queue: discharged patients whose bill is settled (or who
have a waiver) and who haven't received a gate pass yet.

```
┌──────────────────────────────────────────────────────────────────┐
│ Ready for Gate Pass                                              │
│                                                                  │
│  Patient        Discharged      Final bill     Balance   Status  │
│  ──────────────────────────────────────────────────────────────  │
│  Ramesh Kumar   14/05 16:12     ₹14,200        ₹0       ● Ready  │
│                                                  [ Issue pass ▸ ]│
│                                                                  │
│  Suma Devi      14/05 11:30     ₹8,500         ₹2,500   ⚠ Bal.   │
│                                                  [ Override... ] │
│                                                                  │
│  Iqbal Singh    13/05 18:45     ₹6,200         ₹0       ✓ Issued │
│                          GP-ADM-0291-A4F2  [ Reprint ]           │
└──────────────────────────────────────────────────────────────────┘
```

Issue Pass dialog:

```
┌──────────────────────────────────────────────────┐
│ Issue gate pass — Ramesh Kumar                   │
│                                                  │
│ Outstanding balance     ₹0.00     ✓ cleared      │
│                                                  │
│ Attendant name *        [ Lakshmi Kumar      ]   │
│ Relationship            [ Wife                ]  │
│ Vehicle no.             [ TS09 AB 1234        ]  │
│ Notes                   [                     ]  │
│                                                  │
│ (if balance > 0, an "Override reason *" textarea │
│  appears here — required by backend)             │
│                                                  │
│              [ Cancel ]   [ Issue & Print ]      │
└──────────────────────────────────────────────────┘
```

Printed gate-pass slip (PDF rendered by backend; preview before print):

```
┌────────────────────────────────────────────────┐
│      KT HEALTH ERP — HOSPITAL NAME             │
│ ────────────────────────────────────────────── │
│        GATE PASS / DISCHARGE EXIT SLIP         │
│                                                │
│  Pass No        GP-ADM-0417-A4F2               │
│  Issued at      14/05/2026 17:08               │
│  Admission No   ADM-0417                       │
│  Patient        Ramesh Kumar  (MED-2026-00417) │
│  Attendant      Lakshmi Kumar (Wife)           │
│  Vehicle No.    TS09 AB 1234                   │
│                                                │
│  Bill cleared — outstanding balance ₹0.00      │
│                                                │
│  QR: 9f2a13...                                 │
│                                                │
│  ─────────────────────  ─────────────────────  │
│  Security signature      Attendant signature   │
└────────────────────────────────────────────────┘
```

Reprint is allowed (audit logged). Issuing a second pass for the same
admission is not — backend already enforces.

---

## 9. State transitions — summary

| Where it changes              | Who can act                        | UI surface                                |
|-------------------------------|------------------------------------|-------------------------------------------|
| `acceptance_status` pending→accepted | doctor, inpatient_admin (`accept_admission`) | Pending Acceptance queue + admission banner |
| `acceptance_status` pending→rejected | same                               | same                                      |
| `payer_scheme_id` / `payer_type`     | billing_admin, inpatient_admin (`convert_payer`) | "Change payer" dialog in admission detail |
| Duty-doctor visit recorded            | any user with `record_visits`, must be on roster | Add Visit dialog                          |
| Face-sheet / case-sheet signed        | doctor / nurse / receptionist (`record_consent`) | Wizard step 3 + Operations tab            |
| Gate pass issued                      | receptionist, billing_admin (`issue_gate_pass`) | Ready for Gate Pass queue                 |

---

## 10. What needs new components vs. reused

**New components (build):**
- `AdmitPatientWizard` — 3-step stepper with draft auto-save
- `PayerSelector` — radio-card grid backed by `/payer-schemes`
- `AcceptanceBanner` — pending/accepted/rejected variants
- `PendingAcceptanceQueue` page
- `ChangePayerDialog` + inline `PayerHistoryTimeline`
- `DutyRosterGrid` (extend nurse roster grid to two role tabs)
- `OnDutyPanel` — right-side sidebar component
- `PayerSchemesAdmin` table + edit dialog
- `ReadyForGatePassQueue` page
- `IssueGatePassDialog` (with override branch)

**Reuse without changes:**
- `printPdf.js` (gate-pass preview/print)
- Existing Consent signing dialog (face-sheet / case-sheet flow into it)
- Admission slide-over shell (just new header strip + new "Documents"
  banner)
- Bill / Deposits tabs

---

## 11. Decisions locked (2026-05-16)

1. **3-step wizard** for Admit Patient.
2. **Pending Acceptance** = a sub-tab on Active Admissions (badge on
   the tab), not a separate sidebar entry.
3. **Duty Roster** = one page, two tabs (Doctors + Nurses).
4. **Gate pass UI forces balance-cleared.** No override branch surfaced
   in the UI — the backend's override path is reserved for back-office
   scripts / future paper-only escape hatch.
5. **Payer cards = text + icons** (Lucide icons next to each label).

Build order: Payer Schemes admin → Admit Wizard → Pending Acceptance
tab → Admission detail header → Change Payer → Add Visit (duty
doctor) → Duty Roster (doctors tab added to existing nurse roster) →
Gate Pass queue.
