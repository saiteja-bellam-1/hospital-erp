import React from 'react';
import {
  Home, Users, Calendar, CalendarClock, Package, Share2, Receipt, TrendingUp,
  FileText, TestTube, LayoutDashboard, BedDouble, Scissors, FileCheck,
  CalendarDays, CalendarRange, Sparkles, AlertOctagon, RotateCcw, Building2,
  BarChart3, ClipboardList, Shield, Database, ScrollText, Activity,
} from 'lucide-react';

const I = (Icon) => <Icon className="h-[18px] w-[18px]" />;
const B = (Icon) => <Icon className="h-7 w-7" />;

/**
 * Builds the same role+module-aware section list used by the sidebar and HomeGrid.
 * Single source of truth — keep both views in sync.
 *
 * @param {{ roles: string[], enabledModules: Record<string, boolean> }} args
 * @returns {{ sections: Array<{ label: string, items: Array<{ text, icon, bigIcon, path }> }> }}
 */
export function useNavigationSections({ roles, enabledModules }) {
  const hasRole = (r) => roles.includes(r);
  const hasAnyRole = (...r) => r.some(x => roles.includes(x));

  const addedPaths = new Set();
  const sections = [];

  const make = (text, Icon, path) => ({ text, icon: I(Icon), bigIcon: B(Icon), path });
  const add = (items, item) => {
    if (!addedPaths.has(item.path)) { items.push(item); addedPaths.add(item.path); }
  };

  // ── HOME ──
  const homeItems = [make('Dashboard', Home, '/dashboard')];
  addedPaths.add('/dashboard');
  sections.push({ label: '', items: homeItems });

  // ── RECEPTION ──
  if (hasRole('receptionist')) {
    const items = [];
    add(items, make('Patients', Users, '/dashboard/reception/patients'));
    if (enabledModules.outpatient) {
      add(items, make('Appointments', Calendar, '/dashboard/reception/appointments'));
      add(items, make('Doctor Schedule', CalendarClock, '/dashboard/reception/doctor-availability'));
    }
    if (enabledModules.lab) {
      add(items, make('Lab Packages', Package, '/dashboard/reception/packages'));
    }
    add(items, make('Referrals', Share2, '/dashboard/reception/referrals'));
    if (enabledModules.billing) {
      add(items, make('Billing', Receipt, '/dashboard/billing'));
      // Centralised view of all generated bills (consultation, lab, admission)
      // with PDF download for each. Backend already authorises receptionist
      // for /api/hospital/billing.
      add(items, make('Bills History', BarChart3, '/dashboard/billing-dashboard'));
    }
    if (enabledModules.outpatient) {
      add(items, make('Reports', TrendingUp, '/dashboard/reception/reports'));
    }
    if (items.length > 0) sections.push({ label: 'Reception', items });
  }

  // ── DOCTOR ──
  if (hasRole('doctor') && enabledModules.outpatient) {
    const items = [];
    add(items, make('Availability', CalendarClock, '/dashboard/availability'));
    if (enabledModules.ehr) {
      add(items, make('EHR', FileText, '/dashboard/ehr'));
    }
    if (items.length > 0) sections.push({ label: 'Doctor', items });
  }

  // ── LAB ──
  if (hasAnyRole('lab_technician', 'lab_admin', 'hospital_admin', 'super_admin') && enabledModules.lab) {
    const items = [];
    add(items, make('Lab Dashboard', TestTube, '/dashboard/lab'));
    if (items.length > 0) sections.push({ label: 'Laboratory', items });
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
    if (hasAnyRole('hospital_admin', 'super_admin', 'inpatient_admin', 'doctor', 'nurse')) {
      add(items, make('Incidents', AlertOctagon, '/dashboard/inpatient/incidents'));
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
  if (hasAnyRole('super_admin', 'hospital_admin')) {
    const items = [];
    add(items, make('Billing', BarChart3, '/dashboard/billing-dashboard'));
    add(items, make('Users & Roles', ClipboardList, '/dashboard/admin'));
    add(items, make('Hospital Config', Building2, '/dashboard/hospital-admin'));
    add(items, make('License', Shield, '/dashboard/license'));
    add(items, make('Database', Database, '/dashboard/backup'));
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
