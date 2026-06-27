import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Badge } from '../../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../../components/ui/select';
import { useToast } from '../../../../hooks/use-toast';
import { Plus, Pencil, Trash2, RefreshCw, Search } from 'lucide-react';
import { errMsg } from '../../PharmacyModule';
import { usePharmacyMedicineMasters } from '../../../../hooks/usePharmacyMedicineMasters';
import MedicineFormFields, {
  EMPTY_MEDICINE_FORM,
  prepareMedicinePayload,
} from '../../../../components/pharmacy/MedicineFormFields';
import { costPcsFromMrp } from '../../../../utils/pharmacyUnits';

export default function MedicinesTab() {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState('');
  const [scheduleFilter, setScheduleFilter] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_MEDICINE_FORM);

  const { masters, setMasters, reload: loadMasters } = usePharmacyMedicineMasters(true);
  const { categories } = masters;

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

  const openCreate = () => { setEditing(null); setForm(EMPTY_MEDICINE_FORM); setOpen(true); };
  const openEdit = (row) => {
    const merged = { ...EMPTY_MEDICINE_FORM, ...row };
    merged.cost_pcs = costPcsFromMrp(merged);
    setEditing(row);
    setForm(merged);
    setOpen(true);
  };

  const save = async () => {
    try {
      const payload = prepareMedicinePayload(form);
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
        <DialogContent className="max-w-4xl max-h-[85vh] overflow-y-auto" formNav="grid">
          <DialogHeader>
            <DialogTitle>{editing ? `Edit Medicine — ${editing.name}` : 'New Medicine'}</DialogTitle>
          </DialogHeader>

          <MedicineFormFields
            form={form}
            onChange={setForm}
            masters={masters}
            onMastersChange={setMasters}
          />

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save}>{editing ? 'Save' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
