# Sidebar Dropdowns + Inpatient Padding Fix

## Tasks

### 1. Remove outer page padding for `/inpatient/*` only ✅ DONE
- [x] `<main>` className now reads `${location.pathname.startsWith('/dashboard/inpatient') ? '' : 'p-4 lg:p-6'}` — inpatient routes are full-bleed; every other module keeps its 16/24px padding.

### 2. Collapsible sidebar sections ✅ DONE
- [x] Each section label is now a button with a `ChevronDown` (open) / `ChevronRight` (collapsed) icon.
- [x] Default state: all sections start expanded; once a user collapses one it stays collapsed across reloads.
- [x] Auto-open: a `useEffect` on `location.pathname` opens the section that contains the active route (only opens — never auto-collapses, so user choices stick).
- [x] Persisted in `localStorage` under key `sidebar_section_state_v1`.
- [x] Home section (no label) stays flat / always visible.
- [x] Section header has hover state matching nav items.

## Files to change
- `frontend/src/pages/Dashboard.js` — both tasks live here.

## Out of scope
- Reorganising which items go in which section.
- Adding/removing sidebar items.
- Mobile-specific behaviour changes (the `lg:` responsive logic stays).
