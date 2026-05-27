# Multi-role dashboards in sidebar

Problem: When a user has both Lab Tech and Receptionist roles, the single "Dashboard" entry resolves to only one of the two (priority-based) via `HomeDashboard` in `frontend/src/pages/Dashboard.js:61`. User wants both visible in the sidebar with their respective names. Generalize to all role combinations.

## Tasks
- [x] Add `getRoleDashboards({ roles, enabledModules })` helper in `useNavigationSections.js` that returns `[{ key, label, path, Component? }]` for every role-dashboard the user is entitled to.
- [x] In `useNavigationSections.js`, when >1 role-dashboards apply, replace the single "Dashboard" home item with one sidebar entry per role-dashboard (e.g., "Reception Dashboard", "Lab Tech Dashboard"). When ≤1, keep the existing single "Dashboard" entry pointing to `/dashboard`.
- [x] In `Dashboard.js`, add `<Route>`s for the per-role paths (`/dashboard/reception-home`, `/dashboard/lab-home`, `/dashboard/doctor-home`, `/dashboard/nurse-home`, `/dashboard/admin-home`, `/dashboard/hospital-admin-home`). Each renders the matching dashboard component directly.
- [x] Leave existing `/dashboard` → `HomeDashboard` priority fallback untouched (for single-role users and bookmarks).
- [x] Active-state highlighting: ensure sidebar `isActive(path)` works for the new paths.
