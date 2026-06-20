import React from 'react';
import {
  Home, Users, Calendar, CalendarClock, Package, Share2, Receipt, TrendingUp,
  FileText, TestTube, LayoutDashboard, BedDouble, Scissors, FileCheck,
  CalendarDays, CalendarRange, Sparkles, RotateCcw, Building2, Printer,
  BarChart3, ClipboardList, Shield, Database, ScrollText, Activity, Stethoscope,
  DownloadCloud, Pill, ShoppingCart, Boxes, Truck, BookOpen,
} from 'lucide-react';

const I = (Icon) => <Icon className="h-[18px] w-[18px]" />;
const B = (Icon) => <Icon className="h-7 w-7" />;

const LAB_ADMIN_DASHBOARD_ROLES = ['lab_admin', 'hospital_admin', 'super_admin'];

/** Normalize role entries from login/profile user objects or raw arrays. */
export function normalizeUserRoles(userOrRoles) {
  if (Array.isArray(userOrRoles)) {
    return userOrRoles.map((r) => (typeof r === 'string' ? r : r?.name)).filter(Boolean);
  }
  const r = userOrRoles?.roles;
  if (Array.isArray(r) && r.length > 0) {
    return r.map((x) => (typeof x === 'string' ? x : x?.name)).filter(Boolean);
  }
  return userOrRoles?.role ? [userOrRoles.role] : [];
}

export function canAccessLabAdminDashboard(roles) {
  const normalized = normalizeUserRoles(roles);
  return normalized.some((r) => LAB_ADMIN_DASHBOARD_ROLES.includes(r));
}

/**
 * Builds the same role+module-aware section list used by the sidebar and HomeGrid.
 * Single source of truth — keep both views in sync.
 *
 * @param {{ roles: string[], enabledModules: Record<string, boolean> }} args
 * @returns {{ sections: Array<{ label: string, items: Array<{ text, icon, bigIcon, path }> }> }}
 */
export function useNavigationSections({ roles: rawRoles, enabledModules }) {
  const roles = normalizeUserRoles(rawRoles);
  const hasRole = (r) => roles.includes(r);
  const hasAnyRole = (...r) => r.some((x) => roles.includes(x));
  const isLabStaff = hasAnyRole('lab_admin', 'lab_technician');
  const isDoctor = hasRole('doctor');
  // Lab staff always get lab nav; doctors always get OPD nav — other roles
  // still respect the module toggle.
  const labEnabled = isLabStaff || !!enabledModules.lab;
  const outpatientEnabled = isDoctor || !!enabledModules.outpatient;

  const addedPaths = new Set();
  const sections = [];

  const make = (text, Icon, path) => ({ text, icon: I(Icon), bigIcon: B(Icon), path });
  const add = (items, item) => {
    if (!addedPaths.has(item.path)) { items.push(item); addedPaths.add(item.path); }
  };

  // ── HOME ──
  // If the user has more than one role-specific dashboard, surface each as its
  // own sidebar item (e.g. "Reception Dashboard", "Lab Tech Dashboard") so
  // nothing gets shadowed by the priority fallback at /dashboard.
  const roleDashboards = getRoleDashboards({ hasRole, hasAnyRole, enabledModules, isLabStaff });
  const homeItems = [];
  if (roleDashboards.length > 0) {
    roleDashboards.forEach((d) => {
      homeItems.push(make(d.label, Home, d.path));
      addedPaths.add(d.path);
    });
  } else {
    homeItems.push(make('Dashboard', Home, '/dashboard'));
    addedPaths.add('/dashboard');
  }
  sections.push({ label: '', items: homeItems });

  // ── OUTPATIENT ── (visible to receptionist + hospital/super admin)
  // Front-desk operations: patients, appointments, packages, day-care services,
  // referrals, and the central billing views. Admins see the same items so they
  // can manage OPD operations without needing a receptionist role.
  if (hasAnyRole('receptionist', 'hospital_admin', 'super_admin')) {
    const items = [];
    add(items, make('Patients', Users, '/dashboard/reception/patients'));
    if (enabledModules.outpatient) {
      add(items, make('Appointments', Calendar, '/dashboard/reception/appointments'));
      add(items, make('Doctor Schedule', CalendarClock, '/dashboard/reception/doctor-availability'));
    }
    if (enabledModules.lab) {
      add(items, make('Lab Packages', Package, '/dashboard/reception/packages'));
      add(items, make('Lab Orders', TestTube, '/dashboard/reception/lab-orders'));
    }
    add(items, make('Day Care', Stethoscope, '/dashboard/reception/procedures'));
    add(items, make('Referrals', Share2, '/dashboard/reception/referrals'));
    // Billing is always available — always-on module, backend authorises
    // receptionist/admin for it.
    add(items, make('Billing', Receipt, '/dashboard/billing'));
    if (enabledModules.outpatient) {
      add(items, make('Reports', TrendingUp, '/dashboard/reception/reports'));
    }
    if (items.length > 0) sections.push({ label: 'Outpatient', items });
  }

  // ── PRINT SETTINGS (reception + hospital admin) ──
  if (hasAnyRole('receptionist', 'hospital_admin', 'super_admin')) {
    const items = [];
    add(items, make('Print Settings', Printer, '/dashboard/print-settings'));
    if (items.length > 0) sections.push({ label: 'Settings', items });
  }

  // ── DOCTOR ──
  if (isDoctor && outpatientEnabled) {
    const items = [];
    add(items, make('Availability', CalendarClock, '/dashboard/availability'));
    if (enabledModules.ehr) {
      add(items, make('EHR', FileText, '/dashboard/ehr'));
    }
    add(items, make('Day Care', Stethoscope, '/dashboard/reception/procedures'));
    if (items.length > 0) sections.push({ label: 'Doctor', items });
  }

  // ── LAB (configuration — lab admin / hospital admin only) ──
  if (canAccessLabAdminDashboard(roles) && labEnabled) {
    const items = [];
    add(items, make('Lab Admin Dashboard', TestTube, '/dashboard/lab'));
    if (items.length > 0) sections.push({ label: 'Laboratory', items });
  }

  // ── PHARMACY ──
  if (enabledModules.pharmacy && hasAnyRole('pharmacist', 'pharmacy_admin', 'hospital_admin', 'super_admin')) {
    const items = [];
    add(items, make('Pharmacy', Pill, '/dashboard/pharmacy'));
    add(items, make('Sales Counter', ShoppingCart, '/dashboard/pharmacy/sales-counter'));
    add(items, make('Sales & Rx', Receipt, '/dashboard/pharmacy/sales'));
    add(items, make('Inventory', Boxes, '/dashboard/pharmacy/inventory'));
    add(items, make('Procurement', Truck, '/dashboard/pharmacy/procurement'));
    add(items, make('Catalog', BookOpen, '/dashboard/pharmacy/catalog'));
    add(items, make('Pharmacy Reports', BarChart3, '/dashboard/pharmacy/reports'));
    if (items.length > 0) sections.push({ label: 'Pharmacy', items });
  }

  // ── EHR (admin who isn't a doctor) ──
  if (hasAnyRole('hospital_admin', 'super_admin') && !hasRole('doctor') && enabledModules.ehr) {
    const items = [];
    add(items, make('EHR', FileText, '/dashboard/ehr'));
    if (items.length > 0) sections.push({ label: 'Health Records', items });
  }

  // ── INPATIENT ──
  if (enabledModules.inpatient && hasAnyRole('hospital_admin', 'super_admin', 'inpatient_admin', 'billing_admin', 'receptionist', 'frontdesk', 'nurse', 'doctor')) {
    const items = [];
    add(items, make('Ward Overview', LayoutDashboard, '/dashboard/inpatient'));
    add(items, make('Active Admissions', BedDouble, '/dashboard/inpatient/admissions'));
    add(items, make('ER Triage Queue', Activity, '/dashboard/inpatient/triage'));
    if (hasAnyRole('hospital_admin', 'super_admin', 'inpatient_admin', 'doctor', 'billing_admin')) {
      add(items, make('Discharge History', FileText, '/dashboard/inpatient/discharge'));
    }
    if (hasAnyRole('hospital_admin', 'super_admin', 'inpatient_admin', 'doctor')) {
      add(items, make('OT Schedule', Scissors, '/dashboard/inpatient/ot'));
    }
    if (hasAnyRole('hospital_admin', 'super_admin', 'inpatient_admin', 'billing_admin')) {
      add(items, make('Pre-Authorisations', FileCheck, '/dashboard/inpatient/preauth'));
    }
    if (hasAnyRole('hospital_admin', 'super_admin', 'inpatient_admin', 'receptionist', 'frontdesk')) {
      add(items, make('Reservations', CalendarDays, '/dashboard/inpatient/reservations'));
    }
    if (hasAnyRole('hospital_admin', 'super_admin', 'inpatient_admin', 'doctor', 'nurse')) {
      add(items, make('Duty Roster', CalendarRange, '/dashboard/inpatient/duty-roster'));
    }
    if (hasAnyRole('hospital_admin', 'super_admin', 'inpatient_admin', 'nurse')) {
      add(items, make('Housekeeping', Sparkles, '/dashboard/inpatient/housekeeping'));
    }
    if (hasAnyRole('hospital_admin', 'super_admin', 'inpatient_admin', 'doctor')) {
      add(items, make('Quality Reports', RotateCcw, '/dashboard/inpatient/quality'));
    }
    if (hasAnyRole('hospital_admin', 'super_admin', 'inpatient_admin')) {
      add(items, make('Management Reports', FileText, '/dashboard/inpatient/reports'));
    }
    if (hasAnyRole('hospital_admin', 'super_admin', 'inpatient_admin')) {
      add(items, make('Room Management', Building2, '/dashboard/inpatient/rooms'));
    }
    if (hasAnyRole('hospital_admin', 'super_admin', 'billing_admin')) {
      add(items, make('Billing Setup', Package, '/dashboard/inpatient/billing-setup'));
    }
    if (hasAnyRole('hospital_admin', 'super_admin', 'inpatient_admin', 'doctor')) {
      add(items, make('Procedures', Scissors, '/dashboard/inpatient/procedures'));
    }
    if (items.length > 0) sections.push({ label: 'Inpatient', items });
  }

  // ── ADMIN ──
  // Billing dashboard and Day Care live under the Outpatient group above for
  // admins, so they're omitted here to avoid duplicates.
  if (hasAnyRole('super_admin', 'hospital_admin')) {
    const items = [];
    add(items, make('Users & Roles', ClipboardList, '/dashboard/admin'));
    add(items, make('Hospital Config', Building2, '/dashboard/hospital-admin'));
    add(items, make('License', Shield, '/dashboard/license'));
    add(items, make('Database', Database, '/dashboard/backup'));
    add(items, make('Software Update', DownloadCloud, '/dashboard/software-update'));
    add(items, make('Audit Logs', ScrollText, '/dashboard/audit'));
    sections.push({ label: 'Admin', items });
  }

  // ── NURSE ──
  if (hasRole('nurse') && !hasAnyRole('receptionist', 'doctor', 'hospital_admin', 'super_admin')) {
    const items = [];
    add(items, make('Patients', Users, '/dashboard/patients'));
    if (items.length > 0) sections.push({ label: 'Nursing', items });
  }

  return { sections };
}

/**
 * Returns the role-specific dashboards a user is entitled to, in priority order.
 * Mirrors the legacy HomeDashboard switch in Dashboard.js so the sidebar and
 * the /dashboard fallback agree on what counts as a "dashboard".
 */
export function getRoleDashboards({ hasRole, hasAnyRole, enabledModules, isLabStaff = false }) {
  const out = [];
  if (hasRole('super_admin')) {
    out.push({ key: 'super_admin', label: 'Admin Dashboard', path: '/dashboard/admin-home' });
  }
  if (hasRole('hospital_admin') && !hasRole('super_admin')) {
    out.push({ key: 'hospital_admin', label: 'Admin Dashboard', path: '/dashboard/hospital-admin-home' });
  }
  if (hasRole('doctor')) {
    out.push({ key: 'doctor', label: 'Doctor Dashboard', path: '/dashboard/doctor-home' });
  }
  if (isLabStaff || (hasAnyRole('lab_admin', 'lab_technician') && enabledModules.lab)) {
    out.push({ key: 'lab', label: 'Lab Tech Dashboard', path: '/dashboard/lab-home' });
  }
  if (hasRole('receptionist') && enabledModules.outpatient) {
    out.push({ key: 'reception', label: 'Reception Dashboard', path: '/dashboard/reception-home' });
  }
  // Receptionist-only with lab (no outpatient, no lab role) — fall back to lab dashboard.
  if (
    hasRole('receptionist') &&
    !enabledModules.outpatient &&
    enabledModules.lab &&
    !hasAnyRole('lab_admin', 'lab_technician')
  ) {
    out.push({ key: 'lab', label: 'Lab Tech Dashboard', path: '/dashboard/lab-home' });
  }
  if (hasRole('nurse')) {
    out.push({ key: 'nurse', label: 'Nurse Dashboard', path: '/dashboard/nurse-home' });
  }
  return out;
}
