import React, { useEffect, useMemo, useState, useCallback } from 'react';
import { Routes, Route, useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';

import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { useToast } from '../../hooks/use-toast';
import {
  Plus, Pencil, Trash2, RefreshCw, Search, Pill, ShoppingCart,
  LayoutDashboard, Receipt, Boxes, Truck, BookOpen, BarChart3,
} from 'lucide-react';

import SalesCounter from './pharmacy/SalesCounter';
import PurchaseEntry from './pharmacy/PurchaseEntry';
import DashboardTabImpl from './pharmacy/tabs/DashboardTab';
import MedicinesTabImpl from './pharmacy/tabs/MedicinesTab';
import InventoryTabImpl from './pharmacy/tabs/InventoryTab';
import PurchasesTabImpl from './pharmacy/tabs/PurchasesTab';
import SalesTabImpl from './pharmacy/tabs/SalesTab';
import PendingRxTabImpl from './pharmacy/tabs/PendingRxTab';
import ReportsTabImpl from './pharmacy/tabs/ReportsTab';
import SuppliersTabImpl from './pharmacy/tabs/SuppliersTab';

// ────────────────────────────────────────────────────────────────────────────
// Generic master CRUD table. Used for the 7 simple master tabs (categories,
// companies, suppliers, salts, racks, uoms, HSN). Each caller supplies fields
// + the API path; everything else is shared.
// ────────────────────────────────────────────────────────────────────────────

export function MasterTable({ title, path, fields, displayColumns }) {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const blank = useMemo(
    () => Object.fromEntries(fields.map(f => [f.key, f.default ?? ''])),
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

  const openCreate = () => {
    setEditing(null); setForm(blank); setOpen(true);
  };
  const openEdit = (row) => {
    setEditing(row); setForm({ ...blank, ...row }); setOpen(true);
  };

  const save = async () => {
    try {
      if (editing) {
        await axios.put(`/api/pharmacy/${path}/${editing.id}`, form);
        toast({ title: 'Updated' });
      } else {
        await axios.post(`/api/pharmacy/${path}`, form);
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
                    onChange={e => setForm(s => ({ ...s, [f.key]: e.target.value === '' ? '' : parseFloat(e.target.value) }))} />
                ) : (
                  <Input value={form[f.key] || ''} onChange={e => setForm(s => ({ ...s, [f.key]: e.target.value }))} />
                )}
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
// Pre-configured MasterTable instances for the simple catalog/inventory masters.
// Defined once so each section can render them without re-declaring field specs.
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
      { key: 'sgst_pct', label: 'SGST %', type: 'number', default: 0 },
      { key: 'cgst_pct', label: 'CGST %', type: 'number', default: 0 },
      { key: 'igst_pct', label: 'IGST %', type: 'number', default: 0 },
      { key: 'is_active', label: 'Active', type: 'bool', default: true },
    ]}
    displayColumns={[
      { key: 'code', label: 'Code' },
      { key: 'sgst_pct', label: 'SGST %' },
      { key: 'cgst_pct', label: 'CGST %' },
      { key: 'igst_pct', label: 'IGST %' },
    ]}
  />
);

// ────────────────────────────────────────────────────────────────────────────
// Section definitions — six top-level groups, each rendered as its own page.
// Sections with multiple panels use a secondary inner tab strip.
// ────────────────────────────────────────────────────────────────────────────

const SECTIONS = [
  {
    key: 'dashboard',
    label: 'Dashboard',
    icon: LayoutDashboard,
    panels: [{ key: 'overview', label: 'Overview', render: () => <DashboardTabImpl /> }],
  },
  {
    key: 'sales',
    label: 'Sales & Rx',
    icon: Receipt,
    panels: [
      { key: 'history', label: 'Sales History', render: () => <SalesTabImpl /> },
      { key: 'pending_rx', label: 'Pending Rx', render: () => <PendingRxTabImpl /> },
    ],
  },
  {
    key: 'inventory',
    label: 'Inventory',
    icon: Boxes,
    panels: [
      { key: 'stock', label: 'Stock', render: () => <InventoryTabImpl /> },
      { key: 'racks', label: 'Racks', render: () => <RacksMaster /> },
      { key: 'uoms', label: 'Units of Measure', render: () => <UomsMaster /> },
    ],
  },
  {
    key: 'procurement',
    label: 'Procurement',
    icon: Truck,
    panels: [
      { key: 'purchases', label: 'Purchases', render: () => <PurchasesTabImpl /> },
      { key: 'suppliers', label: 'Suppliers', render: () => <SuppliersTabImpl /> },
    ],
  },
  {
    key: 'catalog',
    label: 'Catalog',
    icon: BookOpen,
    panels: [
      { key: 'medicines', label: 'Medicines', render: () => <MedicinesTabImpl /> },
      { key: 'categories', label: 'Categories', render: () => <CategoriesMaster /> },
      { key: 'companies', label: 'Companies', render: () => <CompaniesMaster /> },
      { key: 'salts', label: 'Salts', render: () => <SaltsMaster /> },
      { key: 'hsn', label: 'Tax / HSN', render: () => <HsnMaster /> },
    ],
  },
  {
    key: 'reports',
    label: 'Reports',
    icon: BarChart3,
    panels: [{ key: 'reports', label: 'Reports', render: () => <ReportsTabImpl /> }],
  },
];

const SECTION_KEYS = SECTIONS.map(s => s.key);

// ────────────────────────────────────────────────────────────────────────────
// Module shell — six grouped top-level sections, each with optional sub-tabs.
// ────────────────────────────────────────────────────────────────────────────

const SECTION_BLURBS = {
  dashboard: 'Today\'s pharmacy activity at a glance',
  sales: 'Completed sales and pending prescriptions',
  inventory: 'Live stock, rack layout, and units of measure',
  procurement: 'Goods received and supplier directory',
  catalog: 'Medicines and supporting masters',
  reports: 'Sales, stock, and tax reports',
};

const PharmacyAdmin = () => {
  const navigate = useNavigate();
  const { section: sectionParam } = useParams();
  const section = SECTION_KEYS.includes(sectionParam) ? sectionParam : 'dashboard';
  const current = SECTIONS.find(s => s.key === section) || SECTIONS[0];
  const hasSubTabs = current.panels.length > 1;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-2">
            <Pill className="h-7 w-7" /> Pharmacy · {current.label}
          </h1>
          <p className="text-gray-600">{SECTION_BLURBS[current.key]}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => navigate('/dashboard/pharmacy/sales-counter')}>
            <ShoppingCart className="h-4 w-4 mr-2" /> Sales Counter
          </Button>
          <Button variant="outline" onClick={() => navigate('/dashboard/pharmacy/purchases/new')}>
            <Plus className="h-4 w-4 mr-2" /> New Purchase
          </Button>
        </div>
      </div>

      {hasSubTabs ? (
        <Tabs defaultValue={current.panels[0].key}>
          <TabsList className="flex flex-wrap h-auto">
            {current.panels.map(p => (
              <TabsTrigger key={p.key} value={p.key}>{p.label}</TabsTrigger>
            ))}
          </TabsList>
          {current.panels.map(p => (
            <TabsContent key={p.key} value={p.key}>{p.render()}</TabsContent>
          ))}
        </Tabs>
      ) : (
        current.panels[0].render()
      )}
    </div>
  );
};

// ────────────────────────────────────────────────────────────────────────────
// Top-level export wires routes — admin shell at /dashboard/pharmacy plus
// dedicated full-page sub-routes for the POS and purchase entry workflows.
// `/dashboard/pharmacy/:section` lets the sidebar (and bookmarks) deep-link
// directly to a section like Inventory.
// ────────────────────────────────────────────────────────────────────────────

const PharmacyModule = () => (
  <Routes>
    <Route index element={<PharmacyAdmin />} />
    <Route path="sales-counter" element={<SalesCounter />} />
    <Route path="purchases/new" element={<PurchaseEntry />} />
    <Route path=":section" element={<PharmacyAdmin />} />
    <Route path="*" element={<PharmacyAdmin />} />
  </Routes>
);

export default PharmacyModule;
