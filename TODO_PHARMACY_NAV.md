# Pharmacy Module — Navigation Redesign

Collapse 14 flat tabs into 6 grouped top-level sections, each with sub-tabs where needed. No new sidebar entries.

## Grouping
1. **Dashboard** — standalone
2. **Sales & Rx** — Sales History · Pending Rx (Sales Counter button stays in header)
3. **Inventory** — Stock · Racks · Units of Measure
4. **Procurement** — Purchases · Suppliers (New Purchase button stays in header)
5. **Catalog** — Medicines · Categories · Companies · Salts · Tax / HSN
6. **Reports** — standalone

## Tasks
- [x] Read current PharmacyModule.js + sidebar nav
- [ ] Refactor PharmacyAdmin into 6 grouped top tabs with nested sub-tabs
- [ ] Wire `/dashboard/pharmacy/:section` so existing sidebar "Inventory" link lands on the Inventory section
- [ ] Verify no behavioural changes to underlying tab components (they remain unchanged)
