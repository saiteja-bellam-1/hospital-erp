import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { patchHsnForm } from '../../utils/pharmacyHsnTax';
import { payloadFromMasterForm } from '../../components/pharmacy/pharmacyMasterFieldSpecs';
import { Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom';
import axios from 'axios';

import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { useToast } from '../../hooks/use-toast';
import { Plus, Pencil, Trash2, RefreshCw, Search, Pill } from 'lucide-react';

import SalesCounter from './pharmacy/SalesCounter';
import PurchaseEntry from './pharmacy/PurchaseEntry';
import TransferEntry from './pharmacy/TransferEntry';
import DashboardTabImpl from './pharmacy/tabs/DashboardTab';
import MedicinesTabImpl from './pharmacy/tabs/MedicinesTab';
import InventoryTabImpl from './pharmacy/tabs/InventoryTab';
import PurchasesTabImpl from './pharmacy/tabs/PurchasesTab';
import SalesTabImpl from './pharmacy/tabs/SalesTab';
import PendingRxTabImpl from './pharmacy/tabs/PendingRxTab';
import UnmappedMedicinesTabImpl from './pharmacy/tabs/UnmappedMedicinesTab';
import ReportsTabImpl from './pharmacy/tabs/ReportsTab';
import SuppliersTabImpl from './pharmacy/tabs/SuppliersTab';
import StoresTabImpl from './pharmacy/tabs/StoresTab';
import TransfersTabImpl from './pharmacy/tabs/TransfersTab';
import PharmacyStoreSelector from '../../components/pharmacy/PharmacyStoreSelector';
import { PharmacyStoreProvider } from '../../contexts/PharmacyStoreContext';
import { usePharmacyPermissions } from '../../hooks/usePharmacyPermissions';

// ────────────────────────────────────────────────────────────────────────────
// Generic master CRUD table. Used for the simple catalog/inventory masters.
// ────────────────────────────────────────────────────────────────────────────

export function MasterTable({ title, path, fields, displayColumns }) {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const blank = useMemo(
    () => Object.fromEntries(fields.map(f => [
      f.key,
      f.type === 'number' ? (f.default === 0 ? '' : (f.default ?? '')) : (f.default ?? ''),
    ])),
    [fields]
  );
  const [form, setForm] = useState(blank);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`/api/pharmacy/${path}`, { params: { active_only: false } });
      setRows(r.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Failed to load', description: errMsg(e) });
    } finally { setLoading(false); }
  }, [path, toast]);

  useEffect(() => { load(); }, [load]);

  const patchForm = (key, value) => {
    setForm((s) => (path === 'hsn' ? patchHsnForm(s, key, value) : { ...s, [key]: value }));
  };

  const openCreate = () => {
    setEditing(null);
    const initial = path === 'hsn' ? patchHsnForm(blank, 'sgst_pct', blank.sgst_pct ?? '') : blank;
    setForm(initial);
    setOpen(true);
  };
  const openEdit = (row) => {
    setEditing(row);
    const merged = { ...blank, ...row };
    fields.forEach((f) => {
      if (f.type === 'number' && (merged[f.key] === 0 || merged[f.key] === '0')) {
        merged[f.key] = '';
      }
    });
    setForm(path === 'hsn' ? patchHsnForm(merged, 'sgst_pct', merged.sgst_pct ?? '') : merged);
    setOpen(true);
  };

  const save = async () => {
    const payload = payloadFromMasterForm(form, fields);
    try {
      if (editing) {
        await axios.put(`/api/pharmacy/${path}/${editing.id}`, payload);
        toast({ title: 'Updated' });
      } else {
        await axios.post(`/api/pharmacy/${path}`, payload);
        toast({ title: 'Created' });
      }
      setOpen(false); load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Save failed', description: errMsg(e) });
    }
  };

  const remove = async (row) => {
    if (!window.confirm(`Delete "${row.name || row.code}"? (Soft delete)`)) return;
    try {
      await axios.delete(`/api/pharmacy/${path}/${row.id}`);
      toast({ title: 'Deleted' });
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Delete failed', description: errMsg(e) });
    }
  };

  const filtered = rows.filter(r => {
    if (!search) return true;
    const hay = displayColumns.map(c => String(r[c.key] ?? '')).join(' ').toLowerCase();
    return hay.includes(search.toLowerCase());
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>{title} ({filtered.length})</span>
          <div className="flex gap-2 items-center">
            <div className="relative">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-gray-400" />
              <Input className="pl-8 h-8 w-48" placeholder="Search…" value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-3 w-3" /></Button>
            <Button size="sm" onClick={openCreate}><Plus className="h-3 w-3 mr-1" /> New</Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <p className="text-center py-6 text-gray-500 text-sm">Loading…</p>
        ) : filtered.length === 0 ? (
          <p className="text-center py-6 text-gray-500 text-sm">No records</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-600">
                  {displayColumns.map(c => <th key={c.key} className="py-2 pr-4">{c.label}</th>)}
                  <th className="py-2">Status</th>
                  <th className="py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(r => (
                  <tr key={r.id} className="border-b hover:bg-gray-50">
                    {displayColumns.map(c => (
                      <td key={c.key} className="py-2 pr-4">{String(r[c.key] ?? '—')}</td>
                    ))}
                    <td className="py-2">
                      {r.is_active ? <Badge variant="outline" className="text-xs">Active</Badge>
                        : <Badge variant="outline" className="text-xs text-gray-500">Inactive</Badge>}
                    </td>
                    <td className="py-2 text-right">
                      <Button size="sm" variant="ghost" onClick={() => openEdit(r)}><Pencil className="h-3 w-3" /></Button>
                      <Button size="sm" variant="ghost" onClick={() => remove(r)}><Trash2 className="h-3 w-3 text-red-500" /></Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>{editing ? 'Edit' : 'New'} {title}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            {fields.map(f => (
              <div key={f.key}>
                <Label>{f.label}{f.required && ' *'}</Label>
                {f.type === 'textarea' ? (
                  <Textarea value={form[f.key] || ''} onChange={e => setForm(s => ({ ...s, [f.key]: e.target.value }))} />
                ) : f.type === 'bool' ? (
                  <label className="flex items-center gap-2 text-sm pt-1">
                    <input type="checkbox" checked={!!form[f.key]}
                      onChange={e => setForm(s => ({ ...s, [f.key]: e.target.checked }))} />
                    Enabled
                  </label>
                ) : f.type === 'number' ? (
                  <Input type="number" step="0.01" value={form[f.key] ?? ''}
                    onChange={e => patchForm(f.key, e.target.value === '' ? '' : parseFloat(e.target.value))} />
                ) : (
                  <Input value={form[f.key] || ''} onChange={e => patchForm(f.key, e.target.value)} />
                )}
                {f.hint && <p className="text-[11px] text-muted-foreground mt-0.5">{f.hint}</p>}
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save}>{editing ? 'Save' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

export function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  return e?.message || 'Request failed';
}

// ────────────────────────────────────────────────────────────────────────────
// Master table pages — one route each under /masters/*
// ────────────────────────────────────────────────────────────────────────────

const CategoriesMaster = () => (
  <MasterTable
    title="Categories" path="categories"
    fields={[
      { key: 'name', label: 'Name', required: true },
      { key: 'description', label: 'Description', type: 'textarea' },
      { key: 'is_active', label: 'Active', type: 'bool', default: true },
    ]}
    displayColumns={[
      { key: 'name', label: 'Name' },
      { key: 'description', label: 'Description' },
    ]}
  />
);

const CompaniesMaster = () => (
  <MasterTable
    title="Companies" path="companies"
    fields={[
      { key: 'name', label: 'Name', required: true },
      { key: 'contact', label: 'Contact' },
      { key: 'is_active', label: 'Active', type: 'bool', default: true },
    ]}
    displayColumns={[
      { key: 'name', label: 'Name' },
      { key: 'contact', label: 'Contact' },
    ]}
  />
);

const SaltsMaster = () => (
  <MasterTable
    title="Salts / Compositions" path="salts"
    fields={[
      { key: 'name', label: 'Name', required: true },
      { key: 'description', label: 'Description', type: 'textarea' },
      { key: 'is_active', label: 'Active', type: 'bool', default: true },
    ]}
    displayColumns={[
      { key: 'name', label: 'Name' },
      { key: 'description', label: 'Description' },
    ]}
  />
);

const RacksMaster = () => (
  <MasterTable
    title="Racks" path="racks"
    fields={[
      { key: 'code', label: 'Code', required: true },
      { key: 'location', label: 'Location' },
      { key: 'description', label: 'Description', type: 'textarea' },
      { key: 'is_active', label: 'Active', type: 'bool', default: true },
    ]}
    displayColumns={[
      { key: 'code', label: 'Code' },
      { key: 'location', label: 'Location' },
    ]}
  />
);

const UomsMaster = () => (
  <MasterTable
    title="Units of Measure" path="uoms"
    fields={[
      { key: 'name', label: 'Name', required: true },
      { key: 'abbreviation', label: 'Abbreviation' },
      { key: 'decimal_supported', label: 'Decimal supported', type: 'bool', default: false },
      { key: 'is_active', label: 'Active', type: 'bool', default: true },
    ]}
    displayColumns={[
      { key: 'name', label: 'Name' },
      { key: 'abbreviation', label: 'Abbreviation' },
      { key: 'decimal_supported', label: 'Decimal?' },
    ]}
  />
);

const HsnMaster = () => (
  <MasterTable
    title="HSN / Tax Codes" path="hsn"
    fields={[
      { key: 'code', label: 'HSN Code', required: true },
      { key: 'description', label: 'Description', type: 'textarea' },
      { key: 'sgst_pct', label: 'SGST %', type: 'number', default: '' },
      { key: 'cgst_pct', label: 'CGST %', type: 'number', default: '' },
      {
        key: 'igst_pct',
        label: 'IGST %',
        type: 'number',
        default: '',
        hint: 'Auto-filled as SGST + CGST; you can edit to override.',
      },
      { key: 'is_active', label: 'Active', type: 'bool', default: true },
    ]}
    displayColumns={[
      { key: 'code', label: 'Code' },
      { key: 'description', label: 'Description' },
      { key: 'sgst_pct', label: 'SGST %' },
      { key: 'cgst_pct', label: 'CGST %' },
      { key: 'igst_pct', label: 'IGST %' },
    ]}
  />
);

// ────────────────────────────────────────────────────────────────────────────
// Flat page metadata — one entry per sidebar route
// ────────────────────────────────────────────────────────────────────────────

export const PHARMACY_PAGE_META = {
  '': { title: 'Dashboard', blurb: "Today's pharmacy activity at a glance" },
  'pending-rx': { title: 'Pending Rx', blurb: 'Prescriptions awaiting dispensing' },
  'unmapped-medicines': { title: 'Unmapped Medicines', blurb: 'Free-text inpatient orders awaiting catalog mapping' },
  'sales': { title: 'Sales History', blurb: 'Completed counter sales and voids' },
  'purchases': { title: 'Purchases', blurb: 'Confirmed and draft goods received' },
  'transfers': { title: 'Stock Transfers', blurb: 'Move stock from master to satellite pharmacies' },
  'inventory': { title: 'Stock', blurb: 'Live stock, batches, low-stock alerts, and ledger' },
  'medicines': { title: 'Medicines', blurb: 'Drug catalog — pricing, flags, and barcodes' },
  'suppliers': { title: 'Suppliers', blurb: 'Vendor directory and GST details' },
  'masters/categories': { title: 'Categories', blurb: 'Medicine category master' },
  'masters/companies': { title: 'Companies', blurb: 'Manufacturer / marketing company master' },
  'masters/salts': { title: 'Salts / Compositions', blurb: 'Active ingredient master' },
  'masters/hsn': { title: 'Tax / HSN', blurb: 'HSN codes and GST rates' },
  'masters/racks': { title: 'Racks', blurb: 'Shelf and rack location codes' },
  'masters/uoms': { title: 'Units of Measure', blurb: 'Sale and stock units' },
  'masters/stores': { title: 'Stores', blurb: 'Master and satellite pharmacy locations' },
  'reports': { title: 'Reports', blurb: 'Sales, stock, tax, and register reports' },
};

function PharmacyPermGate({ permission, anyOf, children }) {
  const { loaded, hasPerm, hasAnyPerm } = usePharmacyPermissions();
  if (!loaded) return null;
  const allowed = anyOf ? hasAnyPerm(...anyOf) : hasPerm(permission);
  if (!allowed) return <Navigate to="/dashboard" replace />;
  return children;
}

function pharmacyPathKey(pathname) {
  const prefix = '/dashboard/pharmacy';
  if (!pathname.startsWith(prefix)) return '';
  const rest = pathname.slice(prefix.length).replace(/^\//, '');
  return rest;
}

function PharmacyPageShell() {
  const { pathname } = useLocation();
  const key = pharmacyPathKey(pathname);
  const meta = PHARMACY_PAGE_META[key] || { title: 'Pharmacy', blurb: '' };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-2">
            <Pill className="h-7 w-7" /> Pharmacy · {meta.title}
          </h1>
          {meta.blurb && <p className="text-gray-600">{meta.blurb}</p>}
        </div>
        <PharmacyStoreSelector />
      </div>
      <Outlet />
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────────────
// Routes — flat nav (one screen per URL); full-page workflows stay separate
// ────────────────────────────────────────────────────────────────────────────

const PharmacyModule = () => (
  <PharmacyStoreProvider>
    <Routes>
      <Route path="sales-counter" element={
        <PharmacyPermGate permission="create_sale"><SalesCounter /></PharmacyPermGate>
      } />
      <Route path="purchases/new" element={
        <PharmacyPermGate permission="create_purchase"><PurchaseEntry /></PharmacyPermGate>
      } />
      <Route path="purchases/:id/edit" element={
        <PharmacyPermGate permission="edit_purchase"><PurchaseEntry /></PharmacyPermGate>
      } />
      <Route path="transfers/new" element={
        <PharmacyPermGate permission="create_transfer"><TransferEntry /></PharmacyPermGate>
      } />

      <Route element={<PharmacyPageShell />}>
        <Route index element={
          <PharmacyPermGate permission="view_reports"><DashboardTabImpl /></PharmacyPermGate>
        } />
        <Route path="pending-rx" element={
          <PharmacyPermGate permission="dispense_rx"><PendingRxTabImpl /></PharmacyPermGate>
        } />
        <Route path="unmapped-medicines" element={
          <PharmacyPermGate anyOf={['dispense_rx', 'manage_medicines']}><UnmappedMedicinesTabImpl /></PharmacyPermGate>
        } />
        <Route path="sales" element={
          <PharmacyPermGate permission="view_sales"><SalesTabImpl /></PharmacyPermGate>
        } />
        <Route path="purchases" element={
          <PharmacyPermGate permission="view_purchases"><PurchasesTabImpl /></PharmacyPermGate>
        } />
        <Route path="transfers" element={
          <PharmacyPermGate permission="view_transfers"><TransfersTabImpl /></PharmacyPermGate>
        } />
        <Route path="inventory" element={
          <PharmacyPermGate permission="view_inventory"><InventoryTabImpl /></PharmacyPermGate>
        } />
        <Route path="medicines" element={
          <PharmacyPermGate permission="manage_medicines"><MedicinesTabImpl /></PharmacyPermGate>
        } />
        <Route path="suppliers" element={
          <PharmacyPermGate permission="manage_suppliers"><SuppliersTabImpl /></PharmacyPermGate>
        } />
        <Route path="masters/categories" element={
          <PharmacyPermGate permission="manage_categories"><CategoriesMaster /></PharmacyPermGate>
        } />
        <Route path="masters/companies" element={
          <PharmacyPermGate permission="manage_companies"><CompaniesMaster /></PharmacyPermGate>
        } />
        <Route path="masters/salts" element={
          <PharmacyPermGate permission="manage_salts"><SaltsMaster /></PharmacyPermGate>
        } />
        <Route path="masters/hsn" element={
          <PharmacyPermGate permission="manage_hsn_tax"><HsnMaster /></PharmacyPermGate>
        } />
        <Route path="masters/racks" element={
          <PharmacyPermGate permission="manage_racks"><RacksMaster /></PharmacyPermGate>
        } />
        <Route path="masters/uoms" element={
          <PharmacyPermGate permission="manage_uoms"><UomsMaster /></PharmacyPermGate>
        } />
        <Route path="masters/stores" element={
          <PharmacyPermGate permission="manage_stores"><StoresTabImpl /></PharmacyPermGate>
        } />
        <Route path="reports" element={
          <PharmacyPermGate permission="view_reports"><ReportsTabImpl /></PharmacyPermGate>
        } />

        {/* Legacy section URLs → flat routes */}
        <Route path="dashboard" element={<Navigate to="/dashboard/pharmacy" replace />} />
        <Route path="procurement" element={<Navigate to="/dashboard/pharmacy/purchases" replace />} />
        <Route path="catalog" element={<Navigate to="/dashboard/pharmacy/medicines" replace />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard/pharmacy" replace />} />
    </Routes>
  </PharmacyStoreProvider>
);

export default PharmacyModule;
