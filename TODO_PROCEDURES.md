# Procedures (Outpatient) — Billing-only module

For day-care centres: hospital admin curates a procedure catalog; receptionist /
doctor picks from the catalog (or adds free-form lines) and generates a bill
against an existing patient. Reuses the central Bill model so the existing
Billing dashboard, payments, refunds, credit notes, and PDF pipeline all light
up automatically.

## Backend

- [ ] [B] Model `OutpatientProcedure` (id, name, code unique-per-hospital, default_price, category, is_active, hospital_id)
- [ ] [B] Migration in `migrate_patient_fields.NEW_COLUMNS` (or `create_all()` — new table, no migration needed)
- [ ] [B] Routes (`backend/app/routes/outpatient_procedures.py` registered in `main.py`):
  - `GET /api/outpatient/procedures` (active by default; admin sees inactive too)
  - `POST /api/outpatient/procedures` — admin only
  - `PATCH /api/outpatient/procedures/{id}` — admin only
  - `DELETE /api/outpatient/procedures/{id}` — soft delete
  - `POST /api/outpatient/procedure-bills` — body `{patient_id, items[{procedure_id?, item_name?, quantity, unit_price}], discount_amount?, tax_percentage?, notes?}` → creates `Bill(bill_type='procedure')` + `BillItem` rows; `PROC-YYYYMMDD-NNNN` numbering; audit-logged
  - `GET /api/outpatient/procedure-bills` — paginated list with patient + total + status
- [ ] [B] Extend `/api/hospital/billing` to include `bill_type='procedure'` rows so they show up in the central Billing dashboard
- [ ] [T] `tests/test_outpatient_procedures.py` — catalog CRUD, bill creation (catalog + free-form), zero-amount rejected, list, permission gating

## Frontend

- [ ] [F] New page `frontend/src/pages/modules/ProceduresBilling.js`:
  - Tab: **Generate Bill** — patient picker (`/api/patients/search`), line items (catalog dropdown OR free-form name + price), qty, live total, optional discount/tax, "Create & Print"
  - Tab: **Recent Bills** — list of recent procedure bills, status, actions (View, Pay, Print)
  - Tab: **Procedure Catalog** (admin only) — table with add/edit/deactivate
- [ ] [F] Route wired in `App.js` / `Dashboard.js` at `/dashboard/reception/procedures`
- [ ] [F] Sidebar entry "Procedures" added in `useNavigationSections.js` **below Lab Packages** for receptionist; also accessible to doctor and admins
- [ ] [F] Sidebar section dropdowns **collapsed by default** (flip the `isCollapsed` default; auto-expand only the section containing the active route)

## Cross-cutting
- Reuse `generate_bill_pdf` for the procedure bill receipt
- Reuse the existing Bill Detail dialog / Pay flow from BillingModule (procedure bills appear as `bill_type='procedure'`)
- Permission: gate by role membership (`receptionist | doctor | hospital_admin | super_admin`); no new granular permission needed for v1
