# Package — Granular Lab Test Inclusion

## Decisions locked
- **Scope**: Lab only (Pharmacy & Ancillary deferred).
- **Hospital scoping**: lab test picker shows only the package's own hospital.
- **Bundles**: not surfaced — operator picks individual lab tests.
- **Default mode**: when operator first ticks "Lab", coverage defaults to `"all"` (backwards compat).
- **Behaviour for uncovered tests**: lab tests ordered that are NOT in the package whitelist bill normally (added to the bill as itemised line items).

## Data model (`SurgeryPackage`)
Add two columns (idempotent migration):
- `lab_coverage_mode` VARCHAR(20) DEFAULT `"all"` — `"all"` | `"selected"`
- `included_lab_test_ids` JSON nullable — list of `LabTest.id` ints

Existing packages: `lab_coverage_mode` defaults to `"all"`, `included_lab_test_ids` stays NULL → no behavior change.

## Backend (`backend/app/routes/inpatient.py`)
- [ ] **Model**: add the 2 columns to `SurgeryPackage`.
- [ ] **Migration**: append both columns to `NEW_COLUMNS` in `migrate_patient_fields.py`.
- [ ] **Pydantic**: extend `PackageCreate` / `PackageUpdate` to accept `lab_coverage_mode` + `included_lab_test_ids`. Validate:
  - mode ∈ `{"all", "selected"}`
  - test IDs exist + belong to the package's hospital
  - mode auto-coerced to `"all"` if "lab" not in `included_services`
- [ ] **Helper**: `_pkg_lab_covered(pkg_block, lab_test_id) -> bool` — returns True only when "lab" in `included_services` AND (mode=="all" OR test_id in whitelist).
- [ ] **`_compute_admission_charges`**: stop zeroing the whole lab category when "lab" is included. Iterate `_lab_orders` and:
  - Sum `lab_total` from uncovered orders only.
  - Add `included_in_package: bool` per lab order in a new `lab_entries` list (for the UI).
- [ ] **`_create_admission_bill_record_inner`**: in the lab loop, emit BillItem only when the order is uncovered (covered orders still get `inpatient_bill_id` stamped so they don't reappear later).
- [ ] **Bill preview**: include `lab_entries` + `lab_coverage_mode` + `included_lab_test_ids` in `package` block of the response.

## Frontend
- [ ] **Package builder UI** (find: surgery package create/edit dialog in `HospitalAdminModule.js`):
  - When operator ticks "Lab" in `included_services`, reveal a panel with:
    - Radio: **All lab tests** (default) / **Only selected tests below**
    - When "Only selected": searchable multi-select / checkbox list of all active LabTests for the hospital
  - Saving: pack `lab_coverage_mode` + `included_lab_test_ids` into the payload.
- [ ] **Bill tab** (`InpatientModule.js`):
  - Replace single "Lab Tests" row with per-test breakdown when package is partial (mode == "selected").
  - Each row shows: test name, amount, `Included` chip if covered.
  - When mode == "all" and lab is included → keep current single-row "Included" presentation.

## Tests (`backend/tests/test_billing_comprehensive.py`)
- [ ] `mode="all"` + lab included → all orders covered (regression).
- [ ] `mode="selected"` + whitelist=[A] + orders=[A,B] → A covered, B billed.
- [ ] `mode="selected"` + empty whitelist + orders=[A,B] → both billed.
- [ ] `"lab"` not in included_services → all orders billed (no change).
- [ ] Cancel bill with mixed covered/uncovered → uncovered orders released, covered orders also released (stamp behavior unchanged).

## Out of scope (this iteration)
- Pharmacy / Ancillary granular inclusions
- Lab test bundle expansion in picker
- Cross-hospital test picking
