import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Home, Users, Receipt, TrendingUp,
  FileText, LayoutDashboard, Building2, Printer,
  BarChart3, Shield, Database, ScrollText, RotateCcw,
  DownloadCloud, Pill, ShoppingCart, Boxes, Truck, BookOpen, LayoutGrid, Plus,
  Warehouse, Tags, Layers, Ruler, Percent, Link2, ArrowLeftRight, Store,
  IndianRupee, Settings2, Undo2, UserCheck, PanelTop,
} from 'lucide-react';
import { PHARMACY_ROLE_NAMES } from './usePharmacyPermissions';

const I = (Icon) => <Icon className="h-[18px] w-[18px]" />;
const B = (Icon) => <Icon className="h-7 w-7" />;

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

  const [pharmacyPermState, setPharmacyPermState] = useState({
    loaded: !enabledModules?.pharmacy,
    isAdmin: false,
    modules: {},
  });

  useEffect(() => {
    if (!enabledModules?.pharmacy) {
      setPharmacyPermState({ loaded: true, isAdmin: false, modules: {} });
      return;
    }
    let cancelled = false;
    axios.get('/api/admin/me/permissions')
      .then((res) => {
        if (cancelled) return;
        setPharmacyPermState({
          loaded: true,
          isAdmin: !!res.data?.is_admin,
          modules: res.data?.modules || {},
        });
      })
      .catch(() => {
        if (!cancelled) setPharmacyPermState({ loaded: true, isAdmin: false, modules: {} });
      });
    return () => { cancelled = true; };
  }, [enabledModules?.pharmacy]);

  const hasPharmacyPerm = (key) => {
    if (pharmacyPermState.isAdmin) return true;
    const mods = pharmacyPermState.modules || {};
    if (mods['*']?.includes('*')) return true;
    const list = mods.pharmacy || [];
    return list.includes('*') || list.includes(key);
  };

  const hasPharmacyAccess = enabledModules.pharmacy && (
    hasAnyRole(...PHARMACY_ROLE_NAMES)
    || (pharmacyPermState.modules.pharmacy && pharmacyPermState.modules.pharmacy.length > 0)
  );

  const addedPaths = new Set();
  const sections = [];

  const make = (text, Icon, path) => ({ text, icon: I(Icon), bigIcon: B(Icon), path });
  const add = (items, item) => {
    if (!item) return;
    if (!addedPaths.has(item.path)) { items.push(item); addedPaths.add(item.path); }
  };

  // ── HOME ──
  // If the user has more than one role-specific dashboard, surface each as its
  // own sidebar item so nothing gets shadowed by the priority fallback at /dashboard.
  const roleDashboards = getRoleDashboards({ hasRole, hasAnyRole, enabledModules });
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

  // ── BILLING ── always-on hub (ledger + GST / sales reports)
  if (hasAnyRole('receptionist', 'hospital_admin', 'super_admin', 'billing_admin')) {
    const items = [];
    add(items, make('Bills', Receipt, '/dashboard/billing'));
    if (hasAnyRole('hospital_admin', 'super_admin', 'billing_admin')) {
      add(items, make('Sales Summary', TrendingUp, '/dashboard/billing/sales-summary'));
      if (enabledModules.pharmacy) {
        add(items, make('Purchase Summary', Truck, '/dashboard/billing/purchase-summary'));
      }
      add(items, make('GST Reports', Percent, '/dashboard/billing/gst'));
      add(items, make('GST Returns', DownloadCloud, '/dashboard/billing/gst-export'));
    }
    if (hasAnyRole('hospital_admin', 'super_admin')) {
      add(items, make('Catch-up Bills', FileText, '/dashboard/catch-up'));
      add(items, make('Registration Fee', Receipt, '/dashboard/hospital-admin/billing'));
    }
    if (items.length > 0) sections.push({ label: 'Billing', items });
  }

  // ── CUSTOMISATIONS (reception staff only — admins get it under Administration) ──
  if (hasRole('receptionist') && !hasAnyRole('hospital_admin', 'super_admin')) {
    const items = [];
    add(items, make('Customisations', Printer, '/dashboard/print-settings'));
    if (items.length > 0) sections.push({ label: 'Settings', items });
  }

  // ── PHARMACY ── (flat routes — one sidebar item per screen)
  if (hasPharmacyAccess) {
    const ops = [];
    add(ops, hasPharmacyPerm('view_reports') && make('Dashboard', LayoutDashboard, '/dashboard/pharmacy'));
    add(ops, hasPharmacyPerm('create_sale') && make('Sales Counter', ShoppingCart, '/dashboard/pharmacy/sales-counter'));
    add(ops, hasPharmacyPerm('dispense_rx') && make('Pending Rx', Pill, '/dashboard/pharmacy/pending-rx'));
    add(ops, hasPharmacyPerm('dispense_rx') && make('Unmapped Medicines', Link2, '/dashboard/pharmacy/unmapped-medicines'));
    add(ops, hasPharmacyPerm('view_sales') && make('Sales History', Receipt, '/dashboard/pharmacy/sales'));
    add(ops, hasPharmacyPerm('view_sale_returns') && make('Sales Returns', RotateCcw, '/dashboard/pharmacy/sale-returns'));
    add(ops, hasPharmacyPerm('create_purchase') && make('New Purchase', Plus, '/dashboard/pharmacy/purchases/new'));
    add(ops, hasPharmacyPerm('view_purchases') && make('Purchases', Truck, '/dashboard/pharmacy/purchases'));
    add(ops, hasPharmacyPerm('view_purchase_returns') && make('Purchase Returns', Undo2, '/dashboard/pharmacy/purchase-returns'));
    add(ops, hasPharmacyPerm('view_supplier_payments') && make('Supplier Payments', IndianRupee, '/dashboard/pharmacy/supplier-payments'));
    add(ops, hasPharmacyPerm('view_transfers') && make('Stock Transfers', ArrowLeftRight, '/dashboard/pharmacy/transfers'));
    add(ops, hasPharmacyPerm('view_inventory') && make('Stock', Boxes, '/dashboard/pharmacy/inventory'));
    if (ops.length > 0) sections.push({ label: 'Pharmacy', items: ops });

    const setup = [];
    add(setup, hasPharmacyPerm('manage_medicines') && make('Medicines', BookOpen, '/dashboard/pharmacy/medicines'));
    add(setup, hasPharmacyPerm('manage_suppliers') && make('Suppliers', Warehouse, '/dashboard/pharmacy/suppliers'));
    add(setup, hasPharmacyPerm('manage_categories') && make('Categories', Tags, '/dashboard/pharmacy/masters/categories'));
    add(setup, hasPharmacyPerm('manage_companies') && make('Companies', Building2, '/dashboard/pharmacy/masters/companies'));
    add(setup, hasPharmacyPerm('manage_salts') && make('Salts', Layers, '/dashboard/pharmacy/masters/salts'));
    add(setup, hasPharmacyPerm('manage_hsn_tax') && make('Tax / HSN', Percent, '/dashboard/pharmacy/masters/hsn'));
    add(setup, hasPharmacyPerm('manage_racks') && make('Racks', LayoutGrid, '/dashboard/pharmacy/masters/racks'));
    add(setup, hasPharmacyPerm('manage_uoms') && make('Units of Measure', Ruler, '/dashboard/pharmacy/masters/uoms'));
    add(setup, hasPharmacyPerm('manage_stores') && make('Stores', Store, '/dashboard/pharmacy/masters/stores'));
    add(setup, hasPharmacyPerm('set_rates') && make('Setup', Settings2, '/dashboard/pharmacy/setup'));
    add(setup, hasPharmacyPerm('view_reports') && make('Reports', BarChart3, '/dashboard/pharmacy/reports'));
    if (setup.length > 0) sections.push({ label: 'Pharmacy Setup', items: setup });
  }

  // ── ADMINISTRATION ── people, hospital identity, onboarding
  if (hasAnyRole('super_admin', 'hospital_admin')) {
    const admin = [];
    add(admin, make('Users', Users, '/dashboard/admin/users'));
    add(admin, make('Roles & Permissions', Shield, '/dashboard/admin/roles'));
    add(admin, make('Doctor Profiles', UserCheck, '/dashboard/hospital-admin/doctors'));
    add(admin, make('Hospital Info', Building2, '/dashboard/hospital-admin/info'));
    add(admin, make('Appearance', PanelTop, '/dashboard/hospital-admin/appearance'));
    add(admin, make('Customisations', Printer, '/dashboard/print-settings'));
    if (admin.length > 0) sections.push({ label: 'Administration', items: admin });

    const system = [];
    add(system, make('License', Shield, '/dashboard/license'));
    add(system, make('Database', Database, '/dashboard/backup'));
    add(system, make('Software Update', DownloadCloud, '/dashboard/software-update'));
    add(system, make('Audit Logs', ScrollText, '/dashboard/audit'));
    if (system.length > 0) sections.push({ label: 'System', items: system });
  }

  return { sections };
}

/**
 * Returns the role-specific dashboards a user is entitled to, in priority order.
 * Mirrors the legacy HomeDashboard switch in Dashboard.js so the sidebar and
 * the /dashboard fallback agree on what counts as a "dashboard".
 */
export function getRoleDashboards({ hasRole, hasAnyRole, enabledModules }) {
  const out = [];
  if (hasRole('super_admin')) {
    out.push({ key: 'super_admin', label: 'Admin Dashboard', path: '/dashboard/admin-home' });
  }
  if (hasRole('hospital_admin') && !hasRole('super_admin')) {
    out.push({ key: 'hospital_admin', label: 'Admin Dashboard', path: '/dashboard/hospital-admin-home' });
  }
  return out;
}
