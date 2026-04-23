# Role Permissions — Administrator Guide

**Audience:** Hospital administrators configuring who in the hospital can do what.

**Scope:** How the permission system works, how to use the Role Permissions admin screen, the default matrix that ships out-of-box, and a complete permission reference.

> For clinical/operational feature usage, see [INPATIENT_USER_GUIDE.md](INPATIENT_USER_GUIDE.md).

---

## 1. How permissions work

The system uses **fine-grained, per-feature permissions** for the inpatient module. Every action (record vitals, finalise bill, close an incident, etc.) has its own permission key. Roles are granted specific permissions, not broad access levels.

### The decision flow

When a user clicks anything in the inpatient module, the system checks:

1. Is the user **Super Admin** or **Hospital Admin**? → allow (bypass)
2. Is the **inpatient module enabled** for the hospital? → if not, deny
3. Does the **license include the inpatient feature**? → if not, deny
4. Does **any of the user's roles have the specific permission**? → allow / deny

Roles can be multiple per user (a doctor who also helps with administration could have both `doctor` and `inpatient_admin` roles). Permissions are additive across roles — if any of the user's roles has the permission, the action is allowed.

### Two bypass roles

- **Super Admin** — unrestricted access everywhere. Typically reserved for the software vendor or senior IT.
- **Hospital Admin** — unrestricted access within one hospital. Typically the hospital's IT head or senior administrator.

These two bypass permission checks entirely and cannot be narrowed by the Role Permissions screen — the UI explicitly hides them from the role selector.

---

## 2. Using the Role Permissions admin screen

**Navigation:** Log in as Hospital Admin or Super Admin → **Hospital Administration** (left sidebar) → **Role Permissions** tab

### Layout

```
┌────────────────────────────────────────────────────────┐
│  Role Permissions                                      │
│  [Doctor] [Nurse] [Inpatient Admin] [Billing Admin]... │  ← Role selector
│  ────────────────────────────────────────────────────  │
│  | Inpatient | ...                                     │  ← Module tabs
│  ────────────────────────────────────────────────────  │
│  45 / 54 granted       [Select All] [Clear All]        │
│                                                        │
│  ▾ User category                                       │
│    ☑ record_vitals   Record patient vital signs        │
│    ☑ administer_medications   Administer meds...       │
│    ☐ finalize_bill   Finalize the admission bill       │
│    ...                                                 │
│  ▾ Admin category                                      │
│    ☐ manage_beds   Create/update/delete rooms...       │
│    ...                                                 │
│                                                        │
│                    [Unsaved] [Discard] [Save]          │
└────────────────────────────────────────────────────────┘
```

### Steps

1. **Pick a role** from the top row — e.g., "nurse". Super admin and hospital admin are hidden because they bypass all checks.
2. **Pick a module** — currently inpatient is the only fully-granular module; legacy modules (lab, pharmacy, outpatient) still use the older action-bucket system.
3. The checkbox grid shows every permission defined for that module, grouped by category (`user` — day-to-day operations, `admin` — configuration).
4. Tick/untick permissions as needed. Use **Select All** and **Clear All** for bulk changes.
5. The **Save** button highlights when you have unsaved changes. Click **Save** to commit, or **Discard** to revert.
6. All permission changes are **audit-logged** with the `admin` audit category, including before/after diff. Review via the Audit Logs page.

### What happens on save

- Backend validates every permission name against the official catalog — unknown names are rejected
- The role's permission list for that module is **replaced** with what you ticked (not merged)
- Future logins by users with this role pick up the new permissions immediately (no restart needed)
- Sessions already in progress retain the JWT; permissions are checked on each request, so changes take effect on the next backend call

---

## 3. Default role → permission matrix

This is what ships out-of-box. Most hospitals run with this unchanged for months before tweaking.

### Quick summary

| Role | Primary responsibility |
|---|---|
| **super_admin** | Vendor/IT senior — bypass all checks |
| **hospital_admin** | Hospital IT head — bypass all checks |
| **inpatient_admin** | Operations — rooms, beds, reservations, nurse assignments, pre-auth, quality investigations |
| **doctor** | Clinical — admit, treat, order, prescribe, discharge, consent, record mortality |
| **nurse** | Bedside — vitals, MAR, I/O, nursing notes, diet, housekeeping, report incidents |
| **billing_admin** | Finance — bills, deposits, refunds, packages, TPA, splits, catalogs |
| **receptionist** / **frontdesk** | Front desk — admit, deposits, reservations, documents |

### Detailed defaults

Legend: ✓ = granted by default, ✗ = not granted. Super Admin and Hospital Admin bypass and therefore have effective access to everything.

| Permission | nurse | doctor | inpatient_admin | billing_admin | receptionist/frontdesk |
|---|:---:|:---:|:---:|:---:|:---:|
| **Read & dashboards** | | | | | |
| view_occupancy | ✓ | ✓ | ✓ | ✓ | ✓ |
| view_vitals | ✓ | ✓ | ✗ | ✗ | ✗ |
| view_io | ✓ | ✓ | ✗ | ✗ | ✗ |
| view_mar | ✓ | ✓ | ✗ | ✗ | ✗ |
| view_bill | ✗ | ✓ | ✓ | ✓ | ✓ |
| view_documents | ✓ | ✓ | ✓ | ✓ | ✓ |
| view_readmissions | ✗ | ✓ | ✓ | ✗ | ✗ |
| view_mortality | ✗ | ✓ | ✓ | ✗ | ✗ |
| **Admission lifecycle** | | | | | |
| admit_patients | ✗ | ✓ | ✓ | ✗ | ✓ |
| update_admission | ✗ | ✓ | ✓ | ✗ | ✓ |
| discharge_patients | ✗ | ✓ | ✓ | ✗ | ✗ |
| record_mortality | ✗ | ✓ | ✗ | ✗ | ✗ |
| **Clinical** | | | | | |
| record_vitals | ✓ | ✓ | ✗ | ✗ | ✗ |
| record_io | ✓ | ✓ | ✗ | ✗ | ✗ |
| administer_medications | ✓ | ✓ | ✗ | ✗ | ✗ |
| manage_nursing_notes | ✓ | ✓ | ✗ | ✗ | ✗ |
| manage_diet_orders | ✓ | ✓ | ✗ | ✗ | ✗ |
| manage_allergies | ✓ | ✓ | ✗ | ✗ | ✗ |
| record_visits | ✓ | ✓ | ✗ | ✗ | ✗ |
| acknowledge_critical_alert | ✓ | ✓ | ✗ | ✗ | ✗ |
| record_consent | ✓ | ✓ | ✗ | ✗ | ✗ |
| withdraw_consent | ✗ | ✓ | ✗ | ✗ | ✗ |
| **Orders** | | | | | |
| order_labs | ✗ | ✓ | ✗ | ✗ | ✗ |
| prescribe_medications | ✗ | ✓ | ✗ | ✗ | ✗ |
| **OT** | | | | | |
| schedule_ot | ✗ | ✓ | ✓ | ✗ | ✗ |
| record_ot_charges | ✗ | ✗ | ✓ | ✓ | ✗ |
| **Rooms / beds / ops** | | | | | |
| manage_beds | ✗ | ✗ | ✓ | ✗ | ✗ |
| manage_wards | ✗ | ✗ | ✓ | ✗ | ✗ |
| set_room_rates | ✗ | ✗ | ✓ | ✗ | ✗ |
| transfer_beds | ✗ | ✓ | ✓ | ✗ | ✗ |
| initiate_ward_transfer | ✗ | ✓ | ✓ | ✗ | ✗ |
| accept_ward_transfer | ✓ | ✓ | ✓ | ✗ | ✗ |
| manage_housekeeping | ✓ | ✗ | ✓ | ✗ | ✗ |
| manage_reservations | ✗ | ✗ | ✓ | ✗ | ✓ |
| assign_nurses | ✗ | ✗ | ✓ | ✗ | ✗ |
| view_roster | ✓ | ✓ | ✓ | ✗ | ✗ |
| manage_roster | ✗ | ✗ | ✓ | ✗ | ✗ |
| **Billing** | | | | | |
| generate_interim_bill | ✗ | ✗ | ✗ | ✓ | ✗ |
| finalize_bill | ✗ | ✗ | ✗ | ✓ | ✗ |
| manage_packages | ✗ | ✗ | ✗ | ✓ | ✗ |
| manage_ancillary_charges | ✗ | ✗ | ✓ | ✓ | ✗ |
| receive_deposits | ✗ | ✗ | ✓ | ✓ | ✓ |
| issue_refunds | ✗ | ✗ | ✗ | ✓ | ✗ |
| manage_bill_splits | ✗ | ✗ | ✗ | ✓ | ✗ |
| **Insurance** | | | | | |
| update_claim_status | ✗ | ✗ | ✓ | ✓ | ✗ |
| manage_preauth | ✗ | ✗ | ✓ | ✓ | ✗ |
| manage_tpa | ✗ | ✗ | ✗ | ✓ | ✗ |
| **Quality & compliance** | | | | | |
| report_incident | ✓ | ✓ | ✓ | ✗ | ✗ |
| investigate_incident | ✗ | ✗ | ✓ | ✗ | ✗ |
| close_incident | ✗ | ✗ | ✓ | ✗ | ✗ |
| **Catalogs (admin setup)** | | | | | |
| manage_ancillary_catalog | ✗ | ✗ | ✗ | ✓ | ✗ |
| manage_surgery_packages | ✗ | ✗ | ✗ | ✓ | ✗ |
| manage_consent_templates | ✗ | ✗ | ✓ | ✓ | ✗ |
| set_critical_thresholds | ✗ | ✗ | ✓ | ✗ | ✗ |
| **Documents** | | | | | |
| upload_documents | ✗ | ✓ | ✓ | ✗ | ✓ |
| delete_documents | ✗ | ✗ | ✓ | ✗ | ✗ |

---

## 4. Complete permission reference

Use this as a lookup when deciding whether to grant a permission. Each entry describes what the permission unlocks.

### Read & dashboards

| Permission | Unlocks |
|---|---|
| `view_occupancy` | View rooms, beds, admission lists, ward dashboard, catalog lists (ancillary services, packages, TPA companies, consent templates) |
| `view_vitals` | Read vital signs for any admission |
| `view_io` | Read intake/output chart for any admission |
| `view_mar` | Read the Medication Administration Record |
| `view_bill` | View bill preview, bills history, balance summary, deposit receipts |
| `view_documents` | Download and list admission documents |
| `view_readmissions` | Access the 30-day readmissions report |
| `view_mortality` | Access mortality reports and death certificate PDFs |

### Admission lifecycle

| Permission | Unlocks |
|---|---|
| `admit_patients` | Create new admissions |
| `update_admission` | Edit admission details (insurance info, emergency contact, attending physician, etc.) |
| `discharge_patients` | Create discharge records |
| `record_mortality` | Fill mortality details (cause of death, MLC, autopsy, body handover) on death discharges |

### Clinical documentation

| Permission | Unlocks |
|---|---|
| `record_vitals` | POST new vital-sign recordings per shift |
| `record_io` | POST new intake/output entries per shift |
| `administer_medications` | Generate MAR schedule, mark doses Given/Missed/Refused/Held, record PRN doses |
| `manage_nursing_notes` | Create, edit, delete nursing notes |
| `manage_diet_orders` | Create and replace diet orders |
| `manage_allergies` | Record and edit patient allergies (patient-level, carries across admissions) |
| `record_visits` | Record ward-round visits (doctor / nurse / procedure) |
| `acknowledge_critical_alert` | Acknowledge or mark-addressed critical lab value alerts |
| `record_consent` | Record signed consent forms |
| `withdraw_consent` | Withdraw a previously signed consent with a reason |

### Orders

| Permission | Unlocks |
|---|---|
| `order_labs` | Order lab tests against an admission, trigger critical-value scans on results |
| `prescribe_medications` | Create prescriptions linked to an admission |

### OT (Operating Theatre)

| Permission | Unlocks |
|---|---|
| `schedule_ot` | Create and update OT schedules, change OT status (scheduled → in progress → completed / cancelled / postponed) |
| `record_ot_charges` | Set surgeon fee, anaesthetist fee, OT room charge, equipment charge, consumables charge, other charges on a completed OT |

### Rooms, beds, operations

| Permission | Unlocks |
|---|---|
| `manage_beds` | Create, update, delete rooms and beds |
| `manage_wards` | Configure ward-level settings (currently covered by manage_beds) |
| `set_room_rates` | Set daily room charges and visit rate configuration |
| `transfer_beds` | Change a patient's room or bed within an admission (requires transfer_reason) |
| `initiate_ward_transfer` | Start a pending inter-ward transfer with clinical handover note |
| `accept_ward_transfer` | Accept or cancel a pending ward transfer (receiving ward staff) |
| `manage_housekeeping` | Change bed status (available / occupied / cleaning / dirty / maintenance / out-of-service) |
| `manage_reservations` | Create, cancel, and convert bed reservations |
| `assign_nurses` | Assign nurses to admissions per shift, mark primary nurse |
| `view_roster` | View the nurse duty roster (shift schedule grid + coverage report + on-duty list) |
| `manage_roster` | Create, edit, bulk-assign, and delete entries on the nurse duty roster |

### Billing

| Permission | Unlocks |
|---|---|
| `generate_interim_bill` | Create mid-stay interim bills |
| `finalize_bill` | Create the end-of-stay final bill with discount and tax |
| `manage_packages` | Apply or remove surgery packages on an admission |
| `manage_ancillary_charges` | Add, update, delete ancillary service charges per admission |
| `receive_deposits` | Record advance deposits (initial, top-up) |
| `issue_refunds` | Issue refunds against deposit balance |
| `manage_bill_splits` | Split a finalised bill across cash, insurance, and TPA payers |

### Insurance

| Permission | Unlocks |
|---|---|
| `update_claim_status` | Advance the admission's insurance claim state machine (none → draft → submitted → approved / rejected) |
| `manage_preauth` | Create pre-authorisation requests, record decisions, request expansions, upload approval documents |
| `manage_tpa` | Maintain the TPA company master list |

### Quality & compliance

| Permission | Unlocks |
|---|---|
| `report_incident` | File incident reports (falls, medication errors, pressure ulcers, etc.) |
| `investigate_incident` | Advance an incident from `reported` to `investigating` and `resolved`, record investigation notes, root cause |
| `close_incident` | Close an investigated incident (final state) |

### Catalogs (setup)

| Permission | Unlocks |
|---|---|
| `manage_ancillary_catalog` | Maintain the ancillary services catalog (imaging, dialysis, physiotherapy, etc.) |
| `manage_surgery_packages` | Maintain the surgery packages catalog (cataract, LSCS, appendectomy, etc.) |
| `manage_consent_templates` | Maintain consent form templates (surgical, anaesthesia, blood transfusion, etc.) |
| `set_critical_thresholds` | Configure critical low/high values on lab test parameters |

### Documents

| Permission | Unlocks |
|---|---|
| `upload_documents` | Upload files to an admission (consent scans, referrals, insurance papers, lab reports) |
| `delete_documents` | Remove uploaded documents |

---

## 5. Common customisations

### Give a senior nurse the ability to close incidents

1. Create a new role `senior_nurse` (or use a custom role you've already created) via Admin → Roles
2. Grant it the nurse defaults PLUS `investigate_incident` and `close_incident`
3. Assign the role to the appropriate users

### Let only the Medical Superintendent close incidents

Keep the default (inpatient_admin can close). Ensure only the Medical Superintendent has the `inpatient_admin` role. No permission change needed.

### Let receptionists check patients in without admitting them formally

Currently there's no "arrival" / "check-in" distinction separate from admission. The receptionist has `admit_patients` by default. If you want to restrict this:

1. Remove `admit_patients` from receptionist
2. Add a nurse-or-doctor workflow where the receptionist creates a reservation, and the nurse or doctor on duty converts it to an admission

### Let billing admins see vitals (e.g., for query resolution)

1. Pick billing_admin in the Role Permissions screen
2. Tick `view_vitals`
3. Save

### Restrict refunds to senior billing staff only

Create a `senior_billing_admin` role, grant it everything `billing_admin` has plus `issue_refunds`. Remove `issue_refunds` from `billing_admin`.

---

## 6. Audit trail

Every change to role permissions is logged with:
- **Who** made the change (username)
- **When** (timestamp)
- **What** — role name, module, list of permissions added and removed

Audit entries appear on the Audit Logs page under the `admin` category with action `update_role_permissions`. The details JSON includes the diff:

```json
{
  "role": "nurse",
  "module": "inpatient",
  "added": ["close_incident"],
  "removed": ["manage_housekeeping"]
}
```

Retain these for NABH / regulatory reviews.

---

## 7. Troubleshooting

### User reports "Insufficient permissions" but should have access

1. Open Role Permissions screen
2. Select the user's role
3. Scroll to the relevant module tab
4. Verify the specific permission is ticked — the permission name appears in the error toast (e.g., "Permission 'finalize_bill' required on inpatient")
5. If unticked, tick and save

### User has multiple roles — do permissions add up?

Yes. If a user has `doctor` AND `billing_admin`, they effectively have the union of both permission lists.

### I changed a permission but the user still sees the old behaviour

- Have them refresh the page. Frontend caches enabled modules and role lists on login; permission changes take effect on the next backend call, but the UI may have stale "what's allowed" flags for toolbar buttons.
- If issue persists, ask them to log out and log back in to refresh everything.

### Hospital Admin accidentally revokes their own access

Not possible — the screen hides super_admin and hospital_admin from the role selector, and the backend rejects attempts to narrow their grants. Those two roles permanently bypass all permission checks.

### I want to see every permission a specific user has

1. Go to Admin → Users
2. Open the user's profile — it lists their role(s)
3. For each role, check Role Permissions screen

There's no per-user override today. If you need that, use a dedicated role for that user.

### Accidentally saved overly-restrictive permissions

Click **Discard** before saving, or if already saved, re-open the role and tick the permissions back. Changes are immediate — no undo, but the audit log shows the full diff so you can see exactly what was removed.

---

## 8. Operational recommendations

1. **Start with defaults.** The shipped matrix reflects typical Indian hospital practice. Customise only when specific departments complain or auditors raise flags.
2. **Document your customisations.** Keep a simple note ("Removed X from role Y because Z") alongside the audit log entry for future reference.
3. **Review permissions quarterly.** When staff change roles (promotion, rotation), their role should change, not the role's permissions.
4. **Onboard new hires with role assignment, not permission edits.** The role system exists so you don't manage permissions per-person.
5. **Use the matrix in training.** Print the default matrix and walk each team through what they own. Reduces "I can't do X" tickets dramatically.
