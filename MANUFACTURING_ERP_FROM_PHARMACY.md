# Manufacturing ERP — Starter Blueprint (from KT HEALTH Pharmacy)

> **Purpose:** Clone the pharmacy module’s UI + backend patterns into a standalone manufacturing ERP.  
> **Swap:** patients → **customers**. Keep suppliers, purchases, stock, sales, returns, payments, multi-warehouse, GST/HSN, reports.  
> **DB:** PostgreSQL (this hospital app uses SQLite; notes below for the swap).  
> **Source of truth in this repo:** `backend/app/models/pharmacy.py`, `backend/app/routes/pharmacy*.py`, `frontend/src/pages/modules/PharmacyModule.js` + `pharmacy/`.

---

## 1. What you are cloning

Pharmacy in KT HEALTH ERP is already a full **inventory + trading ERP**:

| Area | What exists |
|------|-------------|
| Catalog | Products (medicines), categories, companies, suppliers, UoM, HSN/tax, racks, barcodes |
| Warehouses | Master + satellite stores, user↔store assignment, transfers |
| Procurement | Purchase draft → confirm → edit/revoke; free qty; batch + expiry |
| Inventory | Batch stock (base unit), FEFO picking, stock ledger, adjustments, expiry write-off |
| Sales / POS | Counter sales, Rate A/B, discounts, inclusive/exclusive tax, void/edit |
| Returns | Sale returns (restock + settlement); purchase returns → challan → supplier CN → debit note → allocate |
| AP | Supplier payables, payments with bill allocation |
| Import/export | Excel/CSV for masters, products, suppliers, opening stock, purchases, sales |
| Reports + PDF | Sales, purchases, stock, tax, margin, aging, movement, invoices, challans |
| Auth | JWT + granular feature permissions (~60 keys) |

**Hospital-only pieces to drop or replace** when building manufacturing:

| Drop / replace | Why |
|----------------|-----|
| Pending Rx / dispense / cancel Rx | Clinical prescriptions |
| Unmapped medicines (IP free-text → catalog) | Inpatient charting |
| `PatientSearchPicker`, `patient_ip_id`, `admission_id`, `billing_mode=inpatient_bill` | Hospital billing |
| Narcotic / Schedule H / MAR fields | Drug regulation (optional: map to “controlled goods”) |
| `hospital_id` tenancy name | Rename to `org_id` / `company_id` |

Everything else maps 1:1 to manufacturing trading ops.

---

## 2. Rename map (pharmacy → manufacturing)

Use these names in the new codebase so domain language is clean.

| Pharmacy term | Manufacturing term | Notes |
|---------------|--------------------|-------|
| Hospital | Organization / Company | Tenant root |
| Pharmacy module | Inventory / Trading / Sales | Or keep “ERP” as product name |
| Medicine / Item | Product / SKU | Table: `products` |
| MedicineCategory | ProductCategory | |
| PharmacyCompany | Brand / Manufacturer | Product brand master |
| PharmacySalt | Composition / Spec (optional) | Or drop |
| PharmacyRack | Bin / Location | Shelf location inside warehouse |
| PharmacyStore | Warehouse | `master` / `satellite` → `central` / `depot` |
| PharmacySupplier | Supplier / Vendor | **Keep as-is** |
| Patient (on sale) | **Customer** | Free-text or proper `customers` master |
| Doctor | Salesperson / Reference | Free-text or FK |
| Sale / POS | Sale / Invoice / Counter sale | |
| Purchase | Purchase / GRN | |
| Transfer | Inter-warehouse transfer | |
| Strip / tablet | Pack / base unit | Same math: `pack_conversion_factor` |
| Prescription | *(omit)* or Sales Order | Only if you add SO later |
| Rate A / Rate B | Price list A / B | Wholesale vs retail |
| MRP | MRP / list price | India retail |

**Suggested table prefixes:** `mfg_` or no prefix (`products`, `warehouses`, `purchases`, …). Avoid `pharmacy_*` in the new app.

---

## 3. Recommended stack (match this repo)

Keep the same application shape; only change the database driver.

| Layer | Hospital pharmacy (today) | Manufacturing target |
|-------|---------------------------|----------------------|
| API | FastAPI + SQLAlchemy | **Same** |
| Auth | JWT HS256, bcrypt, `require_feature_permission` | **Same** |
| Frontend | React 18, Tailwind, shadcn/ui, axios, react-router | **Same** |
| State | Local `useState` + axios (no Redux); store context | **Same** |
| PDF | ReportLab + `printPdf.js` / `PdfPreviewDialog` | **Same** |
| DB | SQLite (`kthealth_erp.db`) | **PostgreSQL** |
| Deploy | LAN / Windows exe optional | Your choice (Docker + Postgres recommended) |

### PostgreSQL instead of SQLite

In this repo, `backend/config/database.py` builds:

```python
url = f"sqlite:///{db_path}"
create_engine(url, connect_args={"check_same_thread": False})
```

For manufacturing, use something like:

```python
# Example — read from env
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://user:pass@localhost:5432/manufacturing_erp",
)
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)
```

**Postgres-specific adaptations:**

| Topic | Guidance |
|-------|----------|
| Driver | `psycopg2-binary` or `psycopg` (v3); URL prefix `postgresql+psycopg2://` |
| Migrations | Prefer **Alembic** (this hospital app uses `create_all` + ad-hoc `migrate_*.py` — fine for SQLite, fragile for Postgres prod) |
| Types | Prefer `Numeric(12, 4)` for money/qty over `Float`; use `JSONB` for flexible JSON columns |
| Booleans / dates | SQLAlchemy maps cleanly; enable timezone-aware `DateTime(timezone=True)` |
| Concurrency | Use `SELECT … FOR UPDATE` on batch rows during sale confirm to avoid oversell |
| Unique numbers | `sale_number`, `purchase_number` — use sequences or advisory locks under concurrency |
| FKs | Postgres enforces FKs; fix any “logical FK as plain Integer” patterns (e.g. inventory `purchase_id`) into real FKs |
| Full-text / search | Optional `pg_trgm` for product/customer name search |
| Soft delete | Keep `is_active` pattern; don’t hard-delete stock-linked masters |

---

## 4. Architecture to copy

```
manufacturing-erp/
  backend/
    main.py                          # FastAPI app, include routers
    config/database.py               # Postgres engine + Session + get_db
    app/
      models/
        product.py                   # ← from pharmacy.py (split if large)
        inventory.py
        purchase.py
        sale.py
        returns.py
        warehouse.py
        customer.py                  # NEW — replace free-text patient
      routes/
        products.py / purchases.py / sales.py / …
        # or one fat router like pharmacy.py (~6k lines) then split later
      services/
        stock.py                     # credit/debit batch + ledger
        warehouse_service.py
        returns.py
        pricing.py                   # pack↔base + GST
        import_export.py
      utils/
        auth.py                      # JWT + require_feature_permission
        pdf_service.py
  frontend/
    src/
      pages/modules/InventoryModule.js   # ← PharmacyModule.js
      pages/modules/inventory/…          # tabs + entry screens
      components/inventory/…
      contexts/WarehouseContext.js       # ← PharmacyStoreContext
      hooks/useInventoryPermissions.js
      utils/units.js, hsnTax.js, printPdf.js
```

### Core invariants (do not break)

1. **Stock is always in base units** (smallest unit). Pack qty × conversion factor → base.
2. **Batch identity** = product + batch# + expiry + warehouse.
3. **Every stock move writes a signed ledger row** (`qty_delta` + / −).
4. **Confirm gates stock** — drafts do not move stock (except sale, which creates completed immediately in pharmacy POS).
5. **Tax rates are snapshotted** on purchase/sale lines (SGST/CGST/IGST %) so old invoices stay stable when HSN master changes.
6. **Revoke is proportional** — only reverse unsold / remaining qty when stock was already consumed.

---

## 5. Domain model (tables)

Rename prefixes when you implement. Columns below mirror `backend/app/models/pharmacy.py`.

### 5.1 Masters

#### `products` ← `medicines`

| Column | Type | Notes |
|--------|------|-------|
| id | PK | |
| product_code | String(20) | ← medicine_code |
| name | String(200) | |
| generic_name / description | | Optional |
| category_id | FK | Required |
| mrp, purchase_rate, rate_a, rate_b, cost_pcs | Float/Numeric | Rates usually **per pack** |
| default_discount_pct, item_discount_pct | | |
| barcode | indexed | |
| packaging | display | e.g. "10 pcs × 10 packs" |
| decimal_supported | bool | Fractional qty |
| pack_conversion_factor | int default 1 | ← strip_conversion_factor |
| rate_unit | `base` \| `pack` | ← tablet \| strip |
| company_id, rack_id, uom_id, hsn_id | FKs | |
| min_qty, max_qty, reorder_qty | | Alerts |
| is_active, is_hidden | | Hide from POS without delete |
| last_purchase_date | Date | Prevent older GRN overwriting rates |
| org_id | FK | ← hospital_id |

**Drop for manufacturing (or remap):** `requires_prescription`, `is_narcotic`, `is_schedule_h/h1`, `is_tramadol`, `is_controlled`, `is_high_alert`, clinical text fields.

#### Other masters

| Table ← pharmacy | Purpose |
|------------------|---------|
| `product_categories` ← `medicine_categories` | Categories |
| `brands` ← `pharmacy_companies` | Brand / maker |
| `suppliers` ← `pharmacy_suppliers` | Full ledger-style vendor master (GST, DL optional → trade licenses, opening balance, hold payment, address) |
| `uoms` ← `pharmacy_uoms` | Unit of measure + `decimal_supported` |
| `hsn_codes` ← `pharmacy_hsn_codes` | code, sgst_pct, cgst_pct, igst_pct |
| `racks` / `bins` ← `pharmacy_racks` | Location codes |
| `customers` **NEW** | Replace free-text patient fields on sales |

#### `customers` (new — replace patient)

Suggested columns (mirror sale free-text + make it a real master):

| Column | Notes |
|--------|-------|
| id, code, name | |
| phone, email, address, pin_code, state, state_code, gstin | India B2B |
| opening_balance, credit_limit | Optional AR |
| price_tier | `A` \| `B` default Rate A/B |
| is_active, org_id | |

On sales: prefer `customer_id` FK; still allow walk-in name/phone overrides.

#### Warehouses ← stores

| Table | Purpose |
|-------|---------|
| `warehouses` ← `pharmacy_stores` | code, name, `warehouse_type` (`central`\|`depot`), parent_id, `can_receive_supplier_purchase`, is_default |
| `user_warehouses` ← `pharmacy_user_stores` | M2M access |

### 5.2 Inventory

#### `inventory_batches` ← `pharmacy_inventory`

One row per **(product, batch_number, expiry_date, warehouse_id)**.

| Column | Notes |
|--------|-------|
| quantity_in_stock | **Base units** |
| cost_price, selling_price | |
| mrp, purchase_rate, rate_a, rate_b | Per-batch overrides |
| pack_conversion_factor | Per-batch SCF |
| free_quantity | FOC received |
| hsn_id, supplier_id, purchase_id | |
| warehouse_id, org_id | |

#### `stock_ledger` ← `pharmacy_stock_ledger`

| Column | Notes |
|--------|-------|
| product_id, batch_id, warehouse_id | |
| txn_type | See list below |
| qty_delta | Signed |
| reference_type, reference_id | Polymorphic link |
| performed_by, notes, org_id, created_at | |

**`txn_type` values to implement:**

`purchase`, `purchase_revoke`, `sale`, `sale_return`, `return_in`, `return_out`, `adjustment`, `expiry_writeoff`, `transfer_out`, `transfer_in`

(Omit `rx_dispense` / `rx_cancel` unless you add work-order issue.)

#### `stock_adjustments` ← `pharmacy_stock_adjustments`

Manual adjust audit + ledger row.

### 5.3 Procurement & AP

| Table ← pharmacy | Lifecycle |
|------------------|-----------|
| `purchases` + `purchase_items` | `draft` → `confirmed` → `revoked` / `revoked_partial` |
| `supplier_payments` + allocations | `recorded` \| `voided` |
| `purchase_import_mappings` | Saved Excel column maps |

**Purchase header fields:** entry_date, supplier_id, invoice_number, bill_date, payment_type (`cash`\|`credit`), purchase_type, tax_mode (`exclusive` default), warehouse_id, notes, totals, audit (confirmed_by/at, revoked_*, edit_*).

**Purchase line:** product_id, batch_number, expiry_date, quantity + free_quantity (**packs**), rates, discount_pct, hsn_id, tax snapshot, inventory_id after confirm.

### 5.4 Sales

| Table ← pharmacy | Notes |
|------------------|-------|
| `sales` + `sale_items` | status `completed` \| `voided`; `stock_affected` flag for imports |

**Sale header (customer instead of patient):**

```
customer_id (nullable) OR customer_name, customer_phone, customer_address
salesperson_name / reference
payment_type: cash | credit
tax_mode: inclusive (default) | exclusive
bill_discount_amount
warehouse_id
```

**Sale line:** batch_id, quantity (base), qty_base + qty_packs display fields, rate, rate_tier A|B, discount_pct, tax snapshot, line_total.

### 5.5 Returns

| Flow | Tables | Stock when? |
|------|--------|-------------|
| Customer return | `sale_returns` + items | On **confirm** if `restock=true` → `sale_return` ledger |
| Supplier return | `purchase_returns` → `return_challans` → `supplier_credit_notes` → `debit_notes` + allocations | Stock leaves on **challan create** (`return_out`) |

Purchase return status machine:

```
draft → confirmed → challan_created → cn_recorded → debit_note_issued → completed
                 ↘ cancelled
```

### 5.6 Transfers

`transfers` + `transfer_items`: `draft` → `confirmed` → `revoked` / `revoked_partial`.  
Confirm: debit source batch (`transfer_out`), credit/merge dest batch (`transfer_in`).

---

## 6. Business rules (copy exactly)

### Units / packs

```
base_received = (qty_packs + free_packs) × pack_conversion_factor
sale_deduct   = qty_base + (qty_packs × pack_conversion_factor)
tab_rate      = pack_rate / pack_conversion_factor   # for billing in base units
```

- Purchase quantities are in **packs**; stock stores **base**.
- Batch conversion factor overrides product master when > 0.
- Rates (MRP, Rate A/B, purchase rate) are typically **per pack**.

### Pricing & GST

- Purchase tax default: **exclusive**. Sale tax default: **inclusive**.
- Tax % from HSN; IGST ≈ SGST + CGST for interstate.
- Snapshot `sgst_pct`, `cgst_pct`, `igst_pct` on lines at save/confirm.
- Optional org setting: tax on free quantity.
- Bill-level flat discount after line tax.
- Updating product MRP/purchase_rate from a confirmed purchase only if entry_date ≥ product.last_purchase_date.

### Batch picking (FEFO)

When sale line has no `batch_id`: pick batches by **expiry ASC**, then id (FEFO). One cart line may split across multiple batches → multiple sale item rows.

### Stock movements

| Event | Stock | Ledger |
|-------|-------|--------|
| Confirm purchase | + | `purchase` |
| Sale (stock_affected) | − | `sale` |
| Void/edit sale | + restore | `return_in` |
| Confirm sale return (restock) | + | `sale_return` |
| Create return challan | − | `return_out` |
| Adjust / expiry write-off | ± | `adjustment` / `expiry_writeoff` |
| Confirm transfer | − source / + dest | `transfer_out` / `transfer_in` |
| Revoke purchase | − remaining unsold | `purchase_revoke` |

**Payables formula:**  
`purchase.grand_total − payment_allocations − debit_note_allocations`

---

## 7. API surface to recreate

Mount under `/api/inventory` or `/api/erp` (pharmacy uses `/api/pharmacy`).

### Pattern

- Granular: `require_feature_permission(Modules.INVENTORY, "create_sale")`
- Soft-delete masters (`is_active=False`)
- List endpoints accept `active_only`, search, `warehouse_id` / `store_id`
- PDFs: `?include_header=true|false` + frontend `PdfPreviewDialog` / `printPdfFromUrl`

### Endpoint groups (mirror pharmacy)

| Group | Key routes |
|-------|------------|
| Health / settings | `GET /health`, `GET\|PUT /pos-settings` |
| Catalog CRUD | `/categories`, `/brands`, `/suppliers`, `/customers`, `/hsn`, `/uoms`, `/racks`, `/products`, lookup by barcode/name |
| Inventory | `/inventory`, `/inventory/batches`, low-stock, expiring, adjust, ledger, opening-stock import |
| Purchases | CRUD draft, `POST …/confirm`, `…/revoke`, PDF |
| Sales | `POST /sales`, edit, void, list, invoice PDF |
| Sale returns | draft → confirm/cancel, credit-note PDF |
| Purchase returns | confirm, challan, supplier-CN, debit-note, allocate |
| Supplier payments | create, list, void/delete, `GET /suppliers/{id}/payables` |
| Warehouses | CRUD, user assignment, settings, `GET /warehouses/my` |
| Transfers | draft → confirm → revoke, PDF |
| Import/export | products, suppliers, masters, opening stock, purchases, sales |
| Reports | dashboard, sales, purchases, stock-on-hand, tax-summary, daily-closeout, margin, supplier-aging, movement (+ PDFs) |

### Source files in this repo

```
backend/app/routes/pharmacy.py           # catalog, inventory, purchase, sale, reports, PDFs
backend/app/routes/pharmacy_stores.py    # stores, transfers
backend/app/routes/pharmacy_returns.py   # returns, payments, CN/DN
backend/app/routes/pharmacy_import.py     # import/export HTTP
backend/app/services/pharmacy_stock.py
backend/app/services/pharmacy_store_service.py
backend/app/services/pharmacy_returns.py
backend/app/services/pharmacy_import.py
backend/app/services/pharmacy_sales_import.py
backend/app/utils/pharmacy_pricing.py
backend/app/utils/pdf_service.py         # generate_pharmacy_* helpers
```

---

## 8. Frontend map (clone UI 1:1)

### Shell

- `PharmacyModule.js` → module router + `PharmacyStoreProvider` + `MasterTable` + permission gates.
- Two nav sections (from `useNavigationSections.js`): **Operations** + **Setup**.
- List pages use shell + warehouse selector; entry screens are full-page (own header).

### Routes to recreate

Base path example: `/dashboard/inventory/…`

#### Operations

| Path | Screen ← source | Perm |
|------|-----------------|------|
| `/` | DashboardTab | view_reports |
| `/sales-counter` | SalesCounter | create_sale |
| `/sales-counter/:id/edit` | SalesCounter | edit_sale |
| `/sales` | SalesTab | view_sales |
| `/sale-returns` | SaleReturnsTab | view_sale_returns |
| `/sale-returns/new`, `/:id` | SaleReturnEntry | create / view |
| `/purchases/new`, `/:id/edit` | PurchaseEntry | create / edit |
| `/purchases` | PurchasesTab | view_purchases |
| `/purchase-returns`… | PurchaseReturnsTab + Entry | view / create |
| `/supplier-payments` | SupplierPaymentsTab | view_supplier_payments |
| `/transfers`, `/transfers/new` | TransfersTab + Entry | view / create |
| `/inventory` | InventoryTab | view_inventory |

#### Setup

| Path | Screen | Perm |
|------|--------|------|
| `/products` | MedicinesTab → ProductsTab | manage_products |
| `/customers` | **NEW** (mirror SuppliersTab) | manage_customers |
| `/suppliers` | SuppliersTab | manage_suppliers |
| `/masters/*` | MasterTable | manage_* |
| `/masters/warehouses` | StoresTab | manage_warehouses |
| `/setup` | SetupTab (POS defaults) | set_rates |
| `/reports` | ReportsTab | view_reports |

**Omit:** `pending-rx`, `unmapped-medicines`.

### Shared components to copy

| Component | Role |
|-----------|------|
| `PharmacyStoreSelector` | Active warehouse switcher |
| `PharmacyBatchSelectDialog` | Keyboard batch picker + Rate A/B |
| `PharmacyMedicinePicker` | Debounced product lookup + quick create |
| `MedicineFormFields` / `SupplierFormFields` | Stepped create/edit forms |
| `QuickMedicineDialog` / `QuickSupplierDialog` | Inline create from entry screens |
| `PharmacyMasterSelectWithCreate` | Select + create master |
| `PharmacyImportDialog` / `PurchaseImportDialog` | Excel import UX |
| `MasterTable` | Generic CRUD table |
| `PdfPreviewDialog` + `printPdf.js` | Print pipeline |

### State patterns

| Concern | Pattern |
|---------|---------|
| Auth | AuthContext + JWT in localStorage + axios 401 logout |
| Warehouse scope | Context; `activeStoreId` in localStorage; API `?store_id=` |
| Permissions | `GET /api/admin/me/permissions` → module key list |
| Server data | `useState` + axios per screen |
| POS cart | `sessionStorage` keyed by warehouse |
| Forms | Keyboard nav via `FormNavContainer` |

### Sales Counter → Customer Counter UX

Keep layout; rename fields:

| Current | Manufacturing |
|---------|---------------|
| Patient phone / name / address | Customer phone / name / address (+ customer picker) |
| IP-ID | Customer code / PO number (optional) |
| Doctor name / number | Salesperson / reference |
| billing_mode inpatient | Drop; only cash/credit |
| Pending Rx prefill | Optional: open sales order prefill later |

### Utils to port

- `frontend/src/utils/pharmacyUnits.js` — pack/base math, money rounding, display blanks for zero
- `frontend/src/utils/pharmacyHsnTax.js` — line tax inclusive/exclusive
- `frontend/src/utils/printPdf.js` — blob → iframe print

---

## 9. Permissions catalog

Seed the same granularity (`db_seed.py` `_PHARMACY_ALL`). Rename module to `inventory` / `manufacturing`.

### Keys

```
# Catalog
view_catalog, manage_products, manage_brands, manage_suppliers, manage_customers,
manage_racks, manage_uoms, manage_categories, manage_hsn_tax

# Pricing
set_rates, set_discounts

# Inventory
view_inventory, adjust_stock, view_stock_ledger, view_low_stock, view_expiring

# Purchase
create_purchase, edit_purchase, confirm_purchase, revoke_purchase, delete_purchase, view_purchases

# Sale
create_sale, edit_sale, void_sale, void_sale_legacy, view_sales, apply_discount, select_rate_tier

# Sale returns
create_sale_return, confirm_sale_return, view_sale_returns, cancel_sale_return

# Purchase returns / AP docs
create_purchase_return, confirm_purchase_return, view_purchase_returns,
create_return_challan, record_supplier_credit_note, issue_debit_note, allocate_debit_note

# Payments
create_supplier_payment, view_supplier_payments, delete_supplier_payment

# Reports
view_reports

# Warehouses
manage_warehouses, view_all_warehouses,
create_transfer, edit_transfer, confirm_transfer, revoke_transfer, view_transfers
```

### Suggested default roles

| Role | Access |
|------|--------|
| `org_admin` / `inventory_admin` | All keys |
| `store_manager` | Counter + purchases view + returns + reports; limited adjust |
| `pos_operator` | create/view sale, apply discount, select rate tier |
| `warehouse_clerk` | transfers + view inventory/catalog |
| `purchase_clerk` | create/edit purchase; confirm optional |

Admins bypass permission checks; warehouse assignment still scopes data unless `view_all_warehouses`.

---

## 10. End-to-end workflows

```
Setup masters (categories, HSN, UoM, brands, warehouses)
    → Products + Suppliers + Customers
    → Purchase Entry (draft) → Confirm → stock on central warehouse
    → Optional Transfer central → depot
    → Sales Counter (FEFO / pick batch) → Invoice PDF
    → Sale Return (restock + refund/credit)
    → Purchase Return → Challan (stock out) → Supplier CN → Debit Note → Allocate to bills
    → Supplier Payments (allocate to credit purchases)
    → Reports / closeout
```

### Document lifecycles (cheat sheet)

```
Purchase:     draft → confirm (stock+) → [edit+reason] → revoke (stock− remaining) → delete revoked
Sale:         create (stock−) → edit/void (stock+ if stock_affected)
Sale return:  draft → confirm (optional restock+) | cancel
Purchase ret: draft → confirm → challan(stock−) → CN → DN → allocate → completed
Transfer:     draft → confirm (out/in) → revoke
Payment:      recorded → voided (delete allocation)
```

---

## 11. UI patterns checklist

Copy these so the manufacturing app “feels” the same:

- [ ] Flat sidebar routes (not nested tabs for main nav)
- [ ] Dual sections: Operations | Setup
- [ ] Card + HTML table lists (search, Refresh, primary CTA)
- [ ] Soft-delete confirm on masters
- [ ] Stepped dialogs for product / supplier / customer
- [ ] Line-item dialogs on purchase/sale (batch, expiry, tax, free qty)
- [ ] Warehouse selector top-right; lock when user has one warehouse
- [ ] Numeric inputs: no spinner; blank for zero; dual pack/base qty when factor > 1
- [ ] Import: upload → preview (new/update/skip/error) → confirm
- [ ] PDF: preview dialog + “Include header” re-fetch
- [ ] POS: full viewport height; cart in sessionStorage
- [ ] Permission gate on route + hide buttons without keys
- [ ] Relative API URLs (no hardcoded host)

---

## 12. Implementation plan (suggested order)

### Phase 0 — Scaffold

1. New repo: FastAPI + React twin of this stack.
2. Postgres + Alembic; `org` + `users` + `roles` + JWT auth.
3. Module enable flag + permission seed.

### Phase 1 — Masters + warehouses

1. Port master CRUD (`MasterTable` + `_register_master_crud` pattern).
2. Products (from Medicine form), Suppliers, **Customers**.
3. Warehouses + user assignment + warehouse context.

### Phase 2 — Stock + purchases

1. `stock.py` credit/debit + ledger.
2. Purchase entry + confirm + revoke.
3. Inventory views, adjust, opening stock import.
4. Transfers.

### Phase 3 — Sales + returns + AP

1. Sales counter (customer picker).
2. Sale void/edit, sale returns.
3. Purchase returns pipeline + supplier payments.
4. Payables aging.

### Phase 4 — Polish

1. Reports + all PDFs.
2. Excel import/export parity.
3. Concurrent stock locking (Postgres `FOR UPDATE`).
4. Optional: sales orders, BOM/manufacturing orders (net-new — not in pharmacy).

---

## 13. What pharmacy does *not* include (future manufacturing)

Add later only if needed — **not** in the pharmacy clone:

- Bill of Materials / work orders / MRP
- Shop-floor production / WIP
- Machine / capacity planning
- Quality inspection (IQC/OQC) workflows
- Serial-number tracking (pharmacy is batch/lot only)
- Multi-currency
- Full accounting GL (pharmacy has AP payables only)

You can still sell “manufactured goods” as finished SKUs with the trading module alone.

---

## 14. File inventory (reference this repo)

### Backend

```
backend/app/models/pharmacy.py
backend/app/routes/pharmacy.py
backend/app/routes/pharmacy_stores.py
backend/app/routes/pharmacy_returns.py
backend/app/routes/pharmacy_import.py
backend/app/services/pharmacy_stock.py
backend/app/services/pharmacy_store_service.py
backend/app/services/pharmacy_returns.py
backend/app/services/pharmacy_reversal.py      # Rx/IP — mostly skip
backend/app/services/pharmacy_import.py
backend/app/services/pharmacy_sales_import.py
backend/app/services/pharmacy_service.py      # legacy helpers
backend/app/utils/pharmacy_pricing.py
backend/app/services/db_seed.py               # _PHARMACY_ALL + role matrices
backend/migrate_pharmacy.py
backend/migrate_pharmacy_stores.py
backend/tests/test_pharmacy_*.py
```

### Frontend

```
frontend/src/pages/modules/PharmacyModule.js
frontend/src/pages/modules/pharmacy/
  SalesCounter.js
  PurchaseEntry.js
  PurchaseReturnEntry.js
  SaleReturnEntry.js
  TransferEntry.js
  saleEditUtils.js
  tabs/
    DashboardTab.js, SalesTab.js, PurchasesTab.js, InventoryTab.js,
    MedicinesTab.js, SuppliersTab.js, StoresTab.js, TransfersTab.js,
    SaleReturnsTab.js, PurchaseReturnsTab.js, SupplierPaymentsTab.js,
    ReportsTab.js, SetupTab.js,
    PendingRxTab.js, UnmappedMedicinesTab.js   # skip
frontend/src/components/pharmacy/*
frontend/src/contexts/PharmacyStoreContext.js
frontend/src/hooks/usePharmacyPermissions.js
frontend/src/hooks/usePharmacyMedicineMasters.js
frontend/src/utils/pharmacyUnits.js
frontend/src/utils/pharmacyHsnTax.js
frontend/src/utils/printPdf.js
frontend/src/hooks/useNavigationSections.js   # pharmacy nav block
```

### Historical requirements (partial / older)

```
Pharmacy_Module_Requirements.md   # original functional brief (item/purchase/sale)
TODO_pharmacy_module.md           # planning — may be stale
TODO_PHARMACY_*.md                # gaps/hardening — may be stale
```

Prefer **code** over TODO md files when behavior conflicts.

---

## 15. Quick Postgres schema sketch (starter)

```sql
-- Illustrative; generate real DDL via Alembic from SQLAlchemy models.

CREATE TABLE organizations (
  id SERIAL PRIMARY KEY,
  name VARCHAR(200) NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE warehouses (
  id SERIAL PRIMARY KEY,
  org_id INT NOT NULL REFERENCES organizations(id),
  code VARCHAR(30) NOT NULL,
  name VARCHAR(150) NOT NULL,
  warehouse_type VARCHAR(20) NOT NULL DEFAULT 'central',
  parent_warehouse_id INT REFERENCES warehouses(id),
  can_receive_supplier_purchase BOOLEAN DEFAULT FALSE,
  is_default BOOLEAN DEFAULT FALSE,
  is_active BOOLEAN DEFAULT TRUE,
  UNIQUE (org_id, code)
);

CREATE TABLE customers (
  id SERIAL PRIMARY KEY,
  org_id INT NOT NULL REFERENCES organizations(id),
  code VARCHAR(30),
  name VARCHAR(150) NOT NULL,
  phone VARCHAR(30),
  gstin VARCHAR(30),
  address TEXT,
  price_tier VARCHAR(10) DEFAULT 'A',
  is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE products (
  id SERIAL PRIMARY KEY,
  org_id INT NOT NULL REFERENCES organizations(id),
  product_code VARCHAR(20) NOT NULL,
  name VARCHAR(200) NOT NULL,
  category_id INT NOT NULL,
  mrp NUMERIC(12,4) DEFAULT 0,
  purchase_rate NUMERIC(12,4) DEFAULT 0,
  rate_a NUMERIC(12,4) DEFAULT 0,
  rate_b NUMERIC(12,4) DEFAULT 0,
  pack_conversion_factor INT DEFAULT 1,
  barcode VARCHAR(50),
  hsn_id INT,
  min_qty INT DEFAULT 0,
  is_active BOOLEAN DEFAULT TRUE,
  is_hidden BOOLEAN DEFAULT FALSE
);

CREATE TABLE inventory_batches (
  id SERIAL PRIMARY KEY,
  org_id INT NOT NULL REFERENCES organizations(id),
  warehouse_id INT NOT NULL REFERENCES warehouses(id),
  product_id INT NOT NULL REFERENCES products(id),
  batch_number VARCHAR(50) NOT NULL,
  expiry_date DATE NOT NULL,
  quantity_in_stock NUMERIC(14,4) NOT NULL DEFAULT 0,
  mrp NUMERIC(12,4) DEFAULT 0,
  purchase_rate NUMERIC(12,4) DEFAULT 0,
  rate_a NUMERIC(12,4) DEFAULT 0,
  rate_b NUMERIC(12,4) DEFAULT 0,
  pack_conversion_factor INT DEFAULT 1,
  supplier_id INT,
  purchase_id INT,
  is_active BOOLEAN DEFAULT TRUE,
  UNIQUE (warehouse_id, product_id, batch_number, expiry_date)
);

CREATE TABLE stock_ledger (
  id SERIAL PRIMARY KEY,
  org_id INT NOT NULL REFERENCES organizations(id),
  warehouse_id INT REFERENCES warehouses(id),
  product_id INT NOT NULL REFERENCES products(id),
  batch_id INT REFERENCES inventory_batches(id),
  txn_type VARCHAR(30) NOT NULL,
  qty_delta NUMERIC(14,4) NOT NULL,
  reference_type VARCHAR(30),
  reference_id INT,
  performed_by INT,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- purchases, purchase_items, sales, sale_items, returns, payments, transfers:
-- copy columns from pharmacy.py with Numeric types + real FKs.
```

---

## 16. Acceptance criteria (parity checklist)

You have a successful clone when:

1. Create product + supplier + customer + warehouse.
2. Confirm purchase with batch/expiry/free qty → stock increases; ledger shows `purchase`.
3. Transfer to second warehouse → source down, dest up.
4. Sell from counter with FEFO → stock down; invoice PDF prints.
5. Void sale → stock restored.
6. Sale return with restock → stock up + credit note PDF.
7. Purchase return → challan reduces stock → DN allocates against purchase payable.
8. Supplier payment allocates to credit bills; aging report matches.
9. Permissions hide nav and block APIs.
10. Warehouse scoping isolates stock for non-admin users.

---

## 17. How to use this doc day-to-day

1. Open the matching file in this repo (section 14) and port screen-by-screen.
2. Keep business rules (section 6) identical until manufacturing-specific needs appear.
3. Always implement **customer** as a first-class master (don’t leave free-text forever).
4. Use Postgres + Alembic from day one; don’t start on SQLite then migrate.
5. Split the fat `pharmacy.py` router into domain routers as you port — easier than cloning a 6k-line file.

When in doubt, the running pharmacy UI under **Dashboard → Pharmacy / Pharmacy Setup** is the UX contract; this document is the structural contract.
