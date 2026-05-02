# TODO — Home Menu Grid + Quick-Launch FAB

Goal: ERP-style launcher page that shows all sidebar nav items as a grid of cards, plus a 4-square floating button (above the support FAB) to jump there from any page.

## Decisions (locked)
- Route: `/dashboard/home` becomes the post-login landing.
- Existing stats overview (`HomeDashboard` with role-priority routing) stays at `/dashboard` — reachable from the grid.
- Layout: grouped by section (Reception / Doctor / Laboratory / Inpatient / Admin / Tools) — same grouping as the sidebar.
- Card content: icon + label only (clean).
- Tools section on grid: Help & Docs, Add to Desktop, Support Contact, Logout.
- Sidebar stays visible on the grid page.
- Single source of truth: extract sidebar's `getNavigationSections()` into a shared hook so sidebar + grid never drift.

## Tasks

- [x] Create this TODO file.
- [ ] Extract `getNavigationSections` from `Dashboard.js` into `frontend/src/hooks/useNavigationSections.js`. Hook returns `{ sections, isActive }`. Dashboard sidebar consumes the hook.
- [ ] Build `frontend/src/pages/modules/HomeGrid.js`:
  - Hero header (welcome + role hint).
  - For each section: section label + responsive grid (`grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5`).
  - Card: icon (large), label, hover lift, click → `navigate(item.path)`.
  - Tools section appended last with Help/Desktop/Support/Logout.
- [ ] Wire routes in `Dashboard.js`:
  - Add `<Route path="/home" element={<HomeGrid ... />} />`.
  - Pass `pwaInstallPrompt`, `setShowSupportPopup`, `logout` so Tools cards work.
- [ ] Update `App.js`:
  - `/login` redirect target: `/dashboard` → `/dashboard/home`.
  - Root `/` redirect target: `/dashboard` → `/dashboard/home`.
- [ ] Add a floating "menu grid" FAB in `Dashboard.js`:
  - `LayoutGrid` icon from lucide.
  - Stacked above the existing Headphones support button (`bottom-24 right-6` so it sits above the `bottom-6` support button with gap).
  - Click → `navigate('/dashboard/home')`.
  - Tooltip on hover: "All Menus".

## Verification
- Login → lands on grid.
- Grid renders only sections allowed by current user's roles + enabled modules.
- Click each card → navigates correctly.
- Floating grid button visible on every dashboard route, including the grid itself.
- Sidebar still works as before.
