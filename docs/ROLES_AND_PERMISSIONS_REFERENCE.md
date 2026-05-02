# Roles & Permissions — Complete Reference

**Audience:** Hospital admins, super admins, and integrators who need a single source of truth for every role and every permission key in KT HEALTH ERP.

**Scope:** All system roles, every module-level permission, and the default permission grants seeded automatically by the application.

> For step-by-step instructions on customising role grants from the UI, see [PERMISSIONS_ADMIN_GUIDE.md](PERMISSIONS_ADMIN_GUIDE.md).

---

## 1. System roles

12 system roles are seeded automatically. They are created by the setup wizard and re-checked on every backend startup, so a fresh install and a long-running install always have the same role list.

| Role | Description | Bypass permission checks? |
|---|---|---|
| `super_admin` | Full system access — manages everything | Yes |
| `hospital_admin` | Hospital-level admin — manages users, settings, operations | Yes |
| `doctor` | Clinical access — consultations, prescriptions, lab orders, inpatient clinical work | No |
| `nurse` | Patient care — vitals, MAR, I/O, nursing notes, housekeeping | No |
| `inpatient_admin` | Bed/ward operations, room rates, nurse assignments, ward management | No |
| `billing_admin` | Bills, finalisation, refunds, packages, TPA / insurance catalogs | No |
| `lab_admin` | Lab module configuration — tests, rates, templates, equipment | No |
| `lab_technician` | Lab operations — process orders and enter results | No |
| `pharmacy_admin` | Pharmacy configuration — inventory, drug rates, suppliers | No |
| `pharmacist` | Medication dispensing and basic inventory | No |
| `frontdesk` | Reception duties — appointments, registration, queue, basic admissions | No |
| `receptionist` | Reception + cash counter — registration, payments, basic admissions | No |

`super_admin` and `hospital_admin` bypass all permission checks at the decorator level. They still have role grants seeded for them so the Role Permissions admin grid renders consistently.

> **Note:** Custom non-system roles can be created at any time from **Hospital Administration → Role Permissions** (super_admin only). The system roles above are protected and cannot be deleted.

---

## 2. How a permission is checked

```
Request lands on a route protected by require_feature_permission(module, key)
        │
        ▼
1. Is user super_admin or hospital_admin?           → ALLOW
        │
        ▼
2. Is the target module enabled (admin toggle)?     → if NO → DENY
        │
        ▼
3. Is the module included in the active license?    → if NO → DENY
        │
        ▼
4. Does any of the user's roles grant the key?      → if NO → DENY
        │
        ▼
                                                    → ALLOW
```

Two decorator styles co-exist:

- **`require_feature_permission(module, permission_name)`** — preferred. Granular per-feature key. Used by all 141 inpatient routes.
- **`require_permission(module, action)`** — legacy action-bucket check (`read` / `write` / `delete` / `admin`). Still used by lab, pharmacy, and outpatient.

---

## 3. Permission catalog — all modules

### 3.1 Admin module

| Key | Category | Description |
|---|---|---|
| `manage_users` | admin | Create and manage users |
| `manage_roles` | admin | Create and manage roles |
| `manage_modules` | admin | Enable / disable modules |
| `view_system_reports` | admin | View system reports |
| `manage_settings` | admin | Manage system settings |

### 3.2 Outpatient module

| Key | Category | Description |
|---|---|---|
| `schedule_appointments` | user | Schedule patient appointments |
| `manage_schedules` | admin | Manage doctor schedules |
| `register_patients` | user | Register new patients |
| `manage_queues` | user | Manage patient queues |
| `view_appointments` | user | View appointment details |
| `cancel_appointments` | user | Cancel appointments |

### 3.3 EHR module

| Key | Category | Description |
|---|---|---|
| `view_records` | user | View patient electronic health records |
| `edit_records` | user | Edit patient records |
| `create_prescriptions` | user | Create prescriptions |
| `manage_templates` | admin | Manage EHR templates |
| `view_history` | user | View patient medical history |
| `generate_reports` | user | Generate medical reports |

### 3.4 Laboratory module

| Key | Category | Description |
|---|---|---|
| `manage_tests` | admin | Create and manage lab test types |
| `set_rates` | admin | Set pricing for lab tests |
| `view_reports` | user | View lab reports |
| `create_reports` | user | Create lab reports |
| `manage_equipment` | admin | Manage lab equipment |
| `manage_templates` | admin | Create and edit report templates |

### 3.5 Pharmacy module

| Key | Category | Description |
|---|---|---|
| `manage_inventory` | admin | Manage medication inventory |
| `set_drug_rates` | admin | Set medication pricing |
| `dispense_medications` | user | Dispense medications |
| `view_prescriptions` | user | View patient prescriptions |
| `manage_suppliers` | admin | Manage drug suppliers |
| `generate_reports` | admin | Generate pharmacy reports |

### 3.6 Billing module

| Key | Category | Description |
|---|---|---|
| `manage_rates` | admin | Manage service rates and pricing |
| `process_payments` | user | Process patient payments |
| `generate_invoices` | user | Generate patient invoices |
| `view_financial_reports` | admin | View financial reports |
| `manage_insurance` | admin | Manage insurance claims |
| `handle_refunds` | admin | Process refunds |

### 3.7 Inpatient module (granular — 58 keys)

#### Read & dashboards
| Key | Category | Description |
|---|---|---|
| `view_occupancy` | user | View beds, rooms, dashboard, and admission lists |
| `view_vitals` | user | View patient vital signs |
| `view_io` | user | View fluid balance charts |
| `view_mar` | user | View Medication Administration Record |
| `view_bill` | user | View admission bills and previews |
| `view_documents` | user | Download and list admission documents |
| `view_readmissions` | user | View 30-day readmission reports |
| `view_mortality` | user | View mortality records and death certificates |
| `view_roster` | user | View the nurse shift roster |
| `view_procedures` | user | View the procedure catalog |

#### Admission lifecycle
| Key | Category | Description |
|---|---|---|
| `admit_patients` | user | Create admissions |
| `update_admission` | user | Update admission details |
| `discharge_patients` | user | Create discharge records |
| `record_mortality` | user | Record mortality details on death discharges |
| `transfer_beds` | user | Change a patient's room/bed within an admission |
| `initiate_ward_transfer` | user | Start a pending inter-ward transfer |
| `accept_ward_transfer` | user | Accept or cancel a pending ward transfer |

#### Rooms, beds, wards, staffing
| Key | Category | Description |
|---|---|---|
| `manage_beds` | admin | Create / update / delete rooms and beds |
| `manage_wards` | admin | Ward-level configuration |
| `set_room_rates` | admin | Set room rates and visit rate config |
| `manage_housekeeping` | user | Change bed status (cleaning / dirty / maintenance) |
| `manage_reservations` | user | Bed reservations CRUD + convert |
| `assign_nurses` | admin | Assign nurses to admissions per shift |
| `manage_roster` | admin | Build and edit the nurse shift roster |

#### Clinical documentation
| Key | Category | Description |
|---|---|---|
| `record_vitals` | user | Record patient vital signs during stay |
| `record_io` | user | Record intake / output fluid balance entries |
| `administer_medications` | user | Administer scheduled and PRN medications, update MAR |
| `manage_nursing_notes` | user | Create and edit nursing notes |
| `manage_diet_orders` | user | Create and edit diet orders |
| `manage_allergies` | user | Record and update patient allergies |
| `record_visits` | user | Record ward round / nurse visits |

#### Orders
| Key | Category | Description |
|---|---|---|
| `order_labs` | user | Order lab tests for admitted patients |
| `prescribe_medications` | user | Create prescriptions for admitted patients |

#### Operating theatre
| Key | Category | Description |
|---|---|---|
| `schedule_ot` | user | Schedule operating theatre procedures |
| `record_ot_charges` | admin | Set surgeon / anaesthetist / consumable charges on OT |

#### Billing
| Key | Category | Description |
|---|---|---|
| `generate_interim_bill` | user | Create interim bills during stay |
| `finalize_bill` | admin | Finalize the admission bill |
| `manage_packages` | admin | Apply or remove surgery packages on an admission |
| `manage_ancillary_charges` | user | Add / update / delete ancillary charges on admissions |
| `receive_deposits` | user | Record advance deposits |
| `issue_refunds` | admin | Issue refunds against deposits |
| `manage_bill_splits` | admin | Split bill across cash / insurance / TPA payers |

#### Insurance
| Key | Category | Description |
|---|---|---|
| `update_claim_status` | user | Advance the admission insurance claim state machine |
| `manage_preauth` | user | Create pre-auth requests, record decisions, request expansions |
| `manage_tpa` | admin | Maintain TPA company master |

#### Quality & compliance
| Key | Category | Description |
|---|---|---|
| `record_consent` | user | Record signed consents |
| `withdraw_consent` | user | Withdraw a previously signed consent |
| `report_incident` | user | File incident reports (falls, med errors, etc.) |
| `investigate_incident` | admin | Run investigations on incidents |
| `close_incident` | admin | Close incident investigations |
| `acknowledge_critical_alert` | user | Acknowledge / address critical lab value alerts |

#### Catalogs
| Key | Category | Description |
|---|---|---|
| `manage_ancillary_catalog` | admin | Maintain the ancillary services catalog |
| `manage_surgery_packages` | admin | Maintain surgery package catalog |
| `manage_consent_templates` | admin | Maintain consent form templates |
| `set_critical_thresholds` | admin | Configure critical lab value thresholds |
| `manage_procedures` | admin | Add, edit, and remove procedures with default rates |

#### Documents
| Key | Category | Description |
|---|---|---|
| `upload_documents` | user | Upload admission documents |
| `delete_documents` | admin | Delete admission documents |

---

## 4. Default role → permission matrix

What each role gets out-of-box. Customise in **Hospital Administration → Role Permissions**.

### 4.1 Outpatient

| Permission | doctor | nurse | receptionist | frontdesk | inpatient_admin | billing_admin |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| schedule_appointments | ✓ |   | ✓ | ✓ |   |   |
| manage_schedules |   |   |   |   |   |   |
| register_patients | ✓ |   | ✓ | ✓ |   |   |
| manage_queues | ✓ | ✓ | ✓ | ✓ |   |   |
| view_appointments | ✓ | ✓ | ✓ | ✓ |   |   |
| cancel_appointments | ✓ |   | ✓ | ✓ |   |   |

### 4.2 EHR

| Permission | doctor | nurse | receptionist | frontdesk | inpatient_admin |
|---|:---:|:---:|:---:|:---:|:---:|
| view_records | ✓ | ✓ | ✓ | ✓ | ✓ |
| edit_records | ✓ | ✓ |   |   |   |
| create_prescriptions | ✓ |   |   |   |   |
| view_history | ✓ | ✓ | ✓ | ✓ | ✓ |
| generate_reports | ✓ |   |   |   |   |
| manage_allergies |   | ✓ |   |   | ✓ |

### 4.3 Inpatient (clinical)

| Permission | doctor | nurse |
|---|:---:|:---:|
| view_occupancy | ✓ | ✓ |
| record_vitals / view_vitals | ✓ | ✓ |
| record_io / view_io | ✓ | ✓ |
| administer_medications / view_mar | ✓ | ✓ |
| manage_nursing_notes | ✓ | ✓ |
| manage_diet_orders | ✓ | ✓ |
| manage_allergies | ✓ | ✓ |
| record_visits | ✓ | ✓ |
| order_labs | ✓ |   |
| prescribe_medications | ✓ |   |
| record_consent | ✓ | ✓ |
| withdraw_consent | ✓ |   |
| report_incident | ✓ | ✓ |
| acknowledge_critical_alert | ✓ | ✓ |

### 4.4 Inpatient (admissions, ops, billing)

| Permission | doctor | inpatient_admin | billing_admin | receptionist | frontdesk | nurse |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| admit_patients | ✓ | ✓ |   | ✓ | ✓ |   |
| update_admission | ✓ | ✓ |   | ✓ | ✓ |   |
| discharge_patients | ✓ | ✓ |   |   |   |   |
| record_mortality | ✓ |   |   |   |   |   |
| transfer_beds | ✓ | ✓ |   |   |   |   |
| initiate_ward_transfer | ✓ | ✓ |   |   |   |   |
| accept_ward_transfer | ✓ | ✓ |   |   |   | ✓ |
| manage_beds / manage_wards / set_room_rates |   | ✓ |   |   |   |   |
| manage_housekeeping |   | ✓ |   |   |   | ✓ |
| manage_reservations |   | ✓ |   | ✓ | ✓ |   |
| assign_nurses / manage_roster |   | ✓ |   |   |   |   |
| view_roster | ✓ | ✓ |   |   |   | ✓ |
| schedule_ot | ✓ | ✓ |   |   |   |   |
| record_ot_charges |   | ✓ | ✓ |   |   |   |
| view_bill | ✓ | ✓ | ✓ | ✓ | ✓ |   |
| generate_interim_bill |   |   | ✓ |   |   |   |
| finalize_bill |   |   | ✓ |   |   |   |
| manage_packages |   |   | ✓ |   |   |   |
| manage_ancillary_charges |   | ✓ | ✓ |   |   |   |
| receive_deposits |   | ✓ | ✓ | ✓ | ✓ |   |
| issue_refunds |   |   | ✓ |   |   |   |
| manage_bill_splits |   |   | ✓ |   |   |   |
| update_claim_status / manage_preauth |   | ✓ | ✓ |   |   |   |
| manage_tpa |   |   | ✓ |   |   |   |
| manage_ancillary_catalog / manage_surgery_packages |   |   | ✓ |   |   |   |
| manage_consent_templates / set_critical_thresholds |   | ✓ |   |   |   |   |
| investigate_incident / close_incident |   | ✓ |   |   |   |   |
| view_readmissions / view_mortality |   | ✓ |   |   |   |   |
| upload_documents | ✓ | ✓ |   | ✓ |   |   |
| view_documents | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| delete_documents |   | ✓ |   |   |   |   |

### 4.5 Lab / Pharmacy / Billing

| Module | lab_admin | lab_technician | pharmacy_admin | pharmacist | billing_admin | doctor | receptionist |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Lab — full admin (manage_tests, set_rates, manage_equipment, manage_templates) | ✓ |   |   |   |   |   |   |
| Lab — view_reports / create_reports | ✓ | ✓ |   |   |   | ✓ |   |
| Pharmacy — full admin (manage_inventory, set_drug_rates, manage_suppliers, generate_reports) |   |   | ✓ |   |   |   |   |
| Pharmacy — dispense_medications / view_prescriptions / manage_inventory |   |   | ✓ | ✓ |   | view only |   |
| Billing — full admin (manage_rates, manage_insurance, handle_refunds, view_financial_reports) |   |   |   |   | ✓ |   |   |
| Billing — process_payments / generate_invoices |   |   |   |   | ✓ |   | ✓ |

---

## 5. Customising grants

1. Log in as `hospital_admin` or `super_admin`.
2. Navigate to **Hospital Administration → Role Permissions**.
3. Pick a role from the list (system roles can be edited; non-admin bypass roles only).
4. Use the checkbox grid grouped by category (`user` / `admin`).
5. Use **Select All** / **Clear All** within a category for bulk edits.
6. Click **Save**. Changes are audit-logged via `update_role_permissions`.

> Permission grants take effect on the user's next API call — no logout required. The frontend reloads role grants when a token is refreshed.

---

## 6. Where this is enforced (for developers)

| Layer | Mechanism |
|---|---|
| Route guards | `app/utils/auth.py` → `require_permission` (legacy) and `require_feature_permission` (granular) |
| Module gating | `LicenseMiddleware` + `SystemModule.is_enabled` toggle |
| Seeding (fresh install) | `app/routes/setup.py` → `_seed_roles`, `_seed_module_permissions`, `_seed_role_permissions` |
| Seeding (existing installs) | `main.py` → `_ensure_role_permissions()` runs on every startup, idempotently |
| Audit | `log_action("update_role_permissions", …)` on every save through the admin UI |

---

_Last updated: 2026-05-01. Keep in sync with `backend/app/routes/setup.py` (`SYSTEM_ROLES`, `_seed_module_permissions`, `_seed_role_permissions`)._
