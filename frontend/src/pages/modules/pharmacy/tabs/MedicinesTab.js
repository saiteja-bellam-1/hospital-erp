import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Textarea } from '../../../../components/ui/textarea';
import { Badge } from '../../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../../components/ui/select';
import { useToast } from '../../../../hooks/use-toast';
import { Plus, Pencil, Trash2, RefreshCw, Search } from 'lucide-react';
import { errMsg } from '../../PharmacyModule';
import PharmacyMasterSelectWithCreate from '../../../../components/pharmacy/PharmacyMasterSelectWithCreate';

const BLANK = {
  medicine_code: '', name: '', generic_name: '', manufacturer: '',
  category_id: null, dosage_form: '', strength: '',
  unit_price: 0, mrp: 0, purchase_rate: 0, rate_a: 0, rate_b: 0, cost_pcs: 0,
  default_discount_pct: 0, item_discount_pct: 0,
  hsn_id: null, company_id: null, rack_id: null, salt_id: null, uom_id: null,
  barcode: '', packaging: '', strip_conversion_factor: 1,
  decimal_supported: false, is_active: true, is_hidden: false, requires_prescription: true,
  is_narcotic: false, is_high_alert: false, is_schedule_h: false,
  is_schedule_h1: false, is_tramadol: false, is_controlled: false,
  description: '', side_effects: '', contraindications: '', storage_conditions: '',
  min_qty: 0, max_qty: 0, reorder_qty: 0,
};

export default function MedicinesTab() {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState('');
  const [scheduleFilter, setScheduleFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(BLANK);

  // Master lists for dropdowns
  const [categories, setCategories] = useState([]);
  const [companies, setCompanies] = useState([]);
  const [racks, setRacks] = useState([]);
  const [salts, setSalts] = useState([]);
  const [uoms, setUoms] = useState([]);
  const [hsnList, setHsnList] = useState([]);

  const loadMasters = useCallback(async () => {
    try {
      const [c, co, r, sa, u, h] = await Promise.all([
        axios.get('/api/pharmacy/categories'),
        axios.get('/api/pharmacy/companies'),
        axios.get('/api/pharmacy/racks'),
        axios.get('/api/pharmacy/salts'),
        axios.get('/api/pharmacy/uoms'),
        axios.get('/api/pharmacy/hsn'),
      ]);
      setCategories(c.data || []); setCompanies(co.data || []); setRacks(r.data || []);
      setSalts(sa.data || []); setUoms(u.data || []); setHsnList(h.data || []);
    } catch (e) { /* tolerate */ }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { include_hidden: true, active_only: false };
      if (search) params.search = search;
      if (scheduleFilter) params.schedule = scheduleFilter;
      if (categoryFilter) params.category_id = categoryFilter;
      const r = await axios.get('/api/pharmacy/medicines', { params });
      setRows(r.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Failed to load medicines', description: errMsg(e) });
    } finally { setLoading(false); }
  }, [search, scheduleFilter, categoryFilter, toast]);

  useEffect(() => { loadMasters(); }, [loadMasters]);
  useEffect(() => { load(); }, [load]);

  const openCreate = () => { setEditing(null); setForm(BLANK); setOpen(true); };
  const openEdit = (row) => {
    setEditing(row);
    setForm({ ...BLANK, ...row });
    setOpen(true);
  };

  const save = async () => {
    try {
      const payload = { ...form };
      // Strip empty selects
      ['category_id', 'company_id', 'rack_id', 'salt_id', 'uom_id', 'hsn_id'].forEach(k => {
        if (payload[k] === '' || payload[k] === undefined) payload[k] = null;
      });
      if (!payload.category_id) {
        toast({ variant: 'destructive', title: 'Category is required' }); return;
      }
      if (editing) {
        await axios.put(`/api/pharmacy/medicines/${editing.id}`, payload);
        toast({ title: 'Medicine updated' });
      } else {
        await axios.post('/api/pharmacy/medicines', payload);
        toast({ title: 'Medicine created' });
      }
      setOpen(false); load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Save failed', description: errMsg(e) });
    }
  };

  const remove = async (row) => {
    if (!window.confirm(`Delete ${row.name}?`)) return;
    try {
      await axios.delete(`/api/pharmacy/medicines/${row.id}`);
      toast({ title: 'Deleted' }); load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Delete failed', description: errMsg(e) });
    }
  };

  const set = (k, v) => setForm(s => ({ ...s, [k]: v }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between flex-wrap gap-2">
          <span>Medicines ({rows.length})</span>
          <div className="flex flex-wrap gap-2 items-center">
            <div className="relative">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-gray-400" />
              <Input className="pl-8 h-8 w-56" placeholder="Search name / code / barcode…"
                value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            <Select value={scheduleFilter || 'any'} onValueChange={v => setScheduleFilter(v === 'any' ? '' : v)}>
              <SelectTrigger className="w-40 h-8"><SelectValue placeholder="Any schedule" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="any">Any schedule</SelectItem>
                <SelectItem value="h">Schedule H</SelectItem>
                <SelectItem value="h1">Schedule H1</SelectItem>
                <SelectItem value="narcotic">Narcotic</SelectItem>
                <SelectItem value="tramadol">Tramadol</SelectItem>
                <SelectItem value="controlled">Controlled</SelectItem>
              </SelectContent>
            </Select>
            <Select value={categoryFilter ? String(categoryFilter) : 'any'} onValueChange={v => setCategoryFilter(v === 'any' ? '' : Number(v))}>
              <SelectTrigger className="w-40 h-8"><SelectValue placeholder="Any category" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="any">Any category</SelectItem>
                {categories.map(c => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}
              </SelectContent>
            </Select>
            <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-3 w-3" /></Button>
            <Button size="sm" onClick={openCreate}><Plus className="h-3 w-3 mr-1" /> New</Button>
          </div>
        </CardTitle>
      </CardHeader>

      <CardContent>
        {loading ? (
          <p className="text-center py-6 text-gray-500 text-sm">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="text-center py-6 text-gray-500 text-sm">No medicines yet</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-600">
                  <th className="py-2 pr-4">Code</th>
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Strength</th>
                  <th className="py-2 pr-4">MRP / Rate A</th>
                  <th className="py-2 pr-4">Flags</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(m => (
                  <tr key={m.id} className="border-b hover:bg-gray-50">
                    <td className="py-2 pr-4 font-mono text-xs">{m.medicine_code}</td>
                    <td className="py-2 pr-4">
                      <div className="font-medium">{m.name}</div>
                      {m.generic_name && <div className="text-xs text-gray-500">{m.generic_name}</div>}
                    </td>
                    <td className="py-2 pr-4 text-xs">{m.dosage_form} {m.strength}</td>
                    <td className="py-2 pr-4 text-xs">₹{m.mrp || 0} / ₹{m.rate_a || m.unit_price || 0}</td>
                    <td className="py-2 pr-4">
                      <div className="flex flex-wrap gap-1">
                        {m.is_narcotic && <Badge variant="outline" className="text-[10px] text-red-700">NARC</Badge>}
                        {m.is_schedule_h && <Badge variant="outline" className="text-[10px]">H</Badge>}
                        {m.is_schedule_h1 && <Badge variant="outline" className="text-[10px] text-orange-700">H1</Badge>}
                        {m.is_tramadol && <Badge variant="outline" className="text-[10px]">TRAM</Badge>}
                        {m.is_high_alert && <Badge variant="outline" className="text-[10px] text-yellow-700">HIGH</Badge>}
                      </div>
                    </td>
                    <td className="py-2 pr-4">
                      {!m.is_active && <Badge variant="outline" className="text-xs text-gray-400">Deleted</Badge>}
                      {m.is_active && m.is_hidden && <Badge variant="outline" className="text-xs text-gray-500">Hidden</Badge>}
                      {m.is_active && !m.is_hidden && <Badge variant="outline" className="text-xs">Active</Badge>}
                    </td>
                    <td className="py-2 text-right">
                      <Button size="sm" variant="ghost" onClick={() => openEdit(m)}><Pencil className="h-3 w-3" /></Button>
                      <Button size="sm" variant="ghost" onClick={() => remove(m)}><Trash2 className="h-3 w-3 text-red-500" /></Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing ? `Edit Medicine — ${editing.name}` : 'New Medicine'}</DialogTitle>
          </DialogHeader>

          {/* ─── Basic ─── */}
          <Section title="Basic">
            <Grid>
              <F label="Code *"><Input value={form.medicine_code} onChange={e => set('medicine_code', e.target.value)} /></F>
              <F label="Name *"><Input value={form.name} onChange={e => set('name', e.target.value)} /></F>
              <F label="Generic Name"><Input value={form.generic_name} onChange={e => set('generic_name', e.target.value)} /></F>
              <F label="Category *">
                <PharmacyMasterSelectWithCreate path="categories" value={form.category_id}
                  onChange={v => set('category_id', v)} options={categories} onOptionsChange={setCategories}
                  placeholder="Pick category" />
              </F>
              <F label="Company">
                <PharmacyMasterSelectWithCreate path="companies" value={form.company_id}
                  onChange={v => set('company_id', v)} options={companies} onOptionsChange={setCompanies}
                  placeholder="(none)" allowEmpty />
              </F>
              <F label="Salt / Composition">
                <PharmacyMasterSelectWithCreate path="salts" value={form.salt_id}
                  onChange={v => set('salt_id', v)} options={salts} onOptionsChange={setSalts}
                  placeholder="(none)" allowEmpty />
              </F>
              <F label="Rack">
                <PharmacyMasterSelectWithCreate path="racks" value={form.rack_id}
                  onChange={v => set('rack_id', v)} options={racks} onOptionsChange={setRacks}
                  placeholder="(none)" allowEmpty labelKey="code" />
              </F>
              <F label="Unit of Measure">
                <PharmacyMasterSelectWithCreate path="uoms" value={form.uom_id}
                  onChange={v => set('uom_id', v)} options={uoms} onOptionsChange={setUoms}
                  placeholder="(none)" allowEmpty
                  format={u => `${u.name}${u.abbreviation ? ` (${u.abbreviation})` : ''}`} />
              </F>
              <F label="Dosage Form"><Input value={form.dosage_form || ''} onChange={e => set('dosage_form', e.target.value)} placeholder="tablet / syrup / inj" /></F>
              <F label="Strength"><Input value={form.strength || ''} onChange={e => set('strength', e.target.value)} placeholder="500mg" /></F>
              <F label="Barcode"><Input value={form.barcode || ''} onChange={e => set('barcode', e.target.value)} /></F>
              <F label="Packaging"><Input value={form.packaging || ''} onChange={e => set('packaging', e.target.value)} placeholder="10 tabs x 10 strips" /></F>
              <F label="Strip Conversion Factor">
                <Input type="number" value={form.strip_conversion_factor ?? 1}
                  onChange={e => set('strip_conversion_factor', e.target.value === '' ? 1 : parseInt(e.target.value))} />
              </F>
              <F label="Decimal supported">
                <Check checked={form.decimal_supported} onChange={v => set('decimal_supported', v)} />
              </F>
              <F label="Active"><Check checked={form.is_active} onChange={v => set('is_active', v)} /></F>
              <F label="Hidden from sales"><Check checked={form.is_hidden} onChange={v => set('is_hidden', v)} /></F>
            </Grid>
          </Section>

          {/* ─── Pricing & Tax ─── */}
          <Section title="Pricing & Tax">
            <Grid>
              <F label="MRP"><Num value={form.mrp} onChange={v => set('mrp', v)} /></F>
              <F label="Purchase Rate (P-Rate)"><Num value={form.purchase_rate} onChange={v => set('purchase_rate', v)} /></F>
              <F label="Rate A"><Num value={form.rate_a} onChange={v => set('rate_a', v)} /></F>
              <F label="Rate B"><Num value={form.rate_b} onChange={v => set('rate_b', v)} /></F>
              <F label="Cost / piece"><Num value={form.cost_pcs} onChange={v => set('cost_pcs', v)} /></F>
              <F label="Default Discount %"><Num value={form.default_discount_pct} onChange={v => set('default_discount_pct', v)} /></F>
              <F label="Item-level Discount %"><Num value={form.item_discount_pct} onChange={v => set('item_discount_pct', v)} /></F>
              <F label="HSN / Tax">
                <PharmacyMasterSelectWithCreate path="hsn" value={form.hsn_id}
                  onChange={v => set('hsn_id', v)} options={hsnList} onOptionsChange={setHsnList}
                  placeholder="(none)" allowEmpty labelKey="code"
                  format={h => `${h.code} (SGST ${h.sgst_pct}% + CGST ${h.cgst_pct}%)`} />
              </F>
            </Grid>
          </Section>

          {/* ─── Inventory thresholds ─── */}
          <Section title="Inventory Thresholds">
            <Grid>
              <F label="Min Qty (low-stock alert)"><Num value={form.min_qty} onChange={v => set('min_qty', Math.round(v))} /></F>
              <F label="Max Qty"><Num value={form.max_qty} onChange={v => set('max_qty', Math.round(v))} /></F>
              <F label="Reorder Qty"><Num value={form.reorder_qty} onChange={v => set('reorder_qty', Math.round(v))} /></F>
            </Grid>
          </Section>

          {/* ─── Regulatory ─── */}
          <Section title="Regulatory">
            <Grid>
              <F label="Requires Prescription"><Check checked={form.requires_prescription} onChange={v => set('requires_prescription', v)} /></F>
              <F label="Narcotic"><Check checked={form.is_narcotic} onChange={v => set('is_narcotic', v)} /></F>
              <F label="Schedule H"><Check checked={form.is_schedule_h} onChange={v => set('is_schedule_h', v)} /></F>
              <F label="Schedule H1"><Check checked={form.is_schedule_h1} onChange={v => set('is_schedule_h1', v)} /></F>
              <F label="Tramadol"><Check checked={form.is_tramadol} onChange={v => set('is_tramadol', v)} /></F>
              <F label="Controlled"><Check checked={form.is_controlled} onChange={v => set('is_controlled', v)} /></F>
              <F label="High-alert"><Check checked={form.is_high_alert} onChange={v => set('is_high_alert', v)} /></F>
            </Grid>
          </Section>

          {/* ─── Notes ─── */}
          <Section title="Notes">
            <F label="Description"><Textarea rows={2} value={form.description || ''} onChange={e => set('description', e.target.value)} /></F>
            <F label="Side Effects"><Textarea rows={2} value={form.side_effects || ''} onChange={e => set('side_effects', e.target.value)} /></F>
            <F label="Storage Conditions"><Textarea rows={2} value={form.storage_conditions || ''} onChange={e => set('storage_conditions', e.target.value)} /></F>
          </Section>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save}>{editing ? 'Save' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─── small layout helpers, local to this file ───────────────────────────────
const Section = ({ title, children }) => (
  <div className="border rounded p-3 mb-3 bg-gray-50/40">
    <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">{title}</p>
    {children}
  </div>
);
const Grid = ({ children }) => <div className="grid grid-cols-2 md:grid-cols-3 gap-3">{children}</div>;
const F = ({ label, children }) => (
  <div>
    <Label className="text-xs">{label}</Label>
    {children}
  </div>
);
const Num = ({ value, onChange }) => (
  <Input type="number" step="0.01" value={value ?? 0}
    onChange={e => onChange(e.target.value === '' ? 0 : parseFloat(e.target.value))} />
);
const Check = ({ checked, onChange }) => (
  <label className="flex items-center gap-2 text-sm pt-1">
    <input type="checkbox" checked={!!checked} onChange={e => onChange(e.target.checked)} />
  </label>
);
