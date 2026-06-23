import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../../components/ui/dialog';
import { useToast } from '../../../../hooks/use-toast';
import { RefreshCw, Link2 } from 'lucide-react';
import PharmacyMasterSelectWithCreate from '../../../../components/pharmacy/PharmacyMasterSelectWithCreate';
import { errMsg } from '../../PharmacyModule';

export default function UnmappedMedicinesTab() {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState(null);
  const [categories, setCategories] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const [form, setForm] = useState({
    rate_a: '',
    category_id: '',
    generic_name: '',
    strength: '',
    dosage_form: '',
    merge_into_medicine_id: '',
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (search.trim()) params.search = search.trim();
      const r = await axios.get('/api/pharmacy/medicines/unmapped', { params });
      setRows(r.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Failed to load', description: errMsg(e) });
    } finally { setLoading(false); }
  }, [search, toast]);

  const loadMasters = useCallback(async () => {
    try {
      const [c, m] = await Promise.all([
        axios.get('/api/pharmacy/categories'),
        axios.get('/api/pharmacy/medicines', { params: { active_only: true, include_hidden: false, limit: 500 } }),
      ]);
      setCategories(c.data || []);
      setCatalog(m.data || []);
    } catch { /* tolerate */ }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadMasters(); }, [loadMasters]);

  const openMap = (row) => {
    setTarget(row);
    setForm({
      rate_a: '',
      category_id: categories[0]?.id ? String(categories[0].id) : '',
      generic_name: '',
      strength: '',
      dosage_form: '',
      merge_into_medicine_id: '',
    });
    setOpen(true);
  };

  const submit = async () => {
    if (!target) return;
    const mergeId = form.merge_into_medicine_id ? parseInt(form.merge_into_medicine_id, 10) : null;
    if (!mergeId && (!form.rate_a || parseFloat(form.rate_a) <= 0)) {
      toast({ variant: 'destructive', title: 'Enter a valid Rate-A price' });
      return;
    }
    if (!mergeId && !form.category_id) {
      toast({ variant: 'destructive', title: 'Select a category' });
      return;
    }
    try {
      await axios.post(`/api/pharmacy/medicines/${target.id}/map`, {
        rate_a: mergeId ? 1 : parseFloat(form.rate_a),
        category_id: mergeId ? (catalog.find(m => m.id === mergeId)?.category_id || parseInt(form.category_id, 10)) : parseInt(form.category_id, 10),
        generic_name: form.generic_name || null,
        strength: form.strength || null,
        dosage_form: form.dosage_form || null,
        merge_into_medicine_id: mergeId,
      });
      toast({ title: mergeId ? 'Merged into catalog medicine' : 'Medicine mapped to catalog' });
      setOpen(false);
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Map failed', description: errMsg(e) });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex justify-between items-center gap-2 flex-wrap">
          <span>Unmapped Medicines ({rows.length})</span>
          <div className="flex gap-2 items-center">
            <Input
              className="h-8 w-48"
              placeholder="Search…"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-3 w-3" /></Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-gray-500 mb-3">
          Free-text medicines ordered from inpatient wards. Map them here with a price before dispensing.
        </p>
        {loading ? <p className="text-center py-6 text-sm text-gray-500">Loading…</p>
          : rows.length === 0 ? <p className="text-center py-6 text-sm text-gray-500">No unmapped medicines</p>
          : (
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-gray-600">
                <th className="py-2 pr-4">Code</th>
                <th className="py-2 pr-4">Name</th>
                <th className="py-2 pr-4">Created</th>
                <th className="py-2 text-right">Actions</th>
              </tr></thead>
              <tbody>
                {rows.map(r => (
                  <tr key={r.id} className="border-b hover:bg-gray-50">
                    <td className="py-2 pr-4 font-mono text-xs">{r.medicine_code}</td>
                    <td className="py-2 pr-4">{r.name}</td>
                    <td className="py-2 pr-4 text-xs text-gray-500">
                      {r.created_at ? new Date(r.created_at).toLocaleString() : '—'}
                    </td>
                    <td className="py-2 text-right">
                      <Button size="sm" variant="outline" onClick={() => openMap(r)}>
                        <Link2 className="h-3 w-3 mr-1" /> Map
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Map — {target?.name}</DialogTitle></DialogHeader>
          <div className="space-y-3 text-sm">
            <div>
              <Label className="text-xs">Merge into existing catalog item (optional)</Label>
              <select
                className="w-full border rounded h-9 px-2 text-sm"
                value={form.merge_into_medicine_id}
                onChange={e => setForm(f => ({ ...f, merge_into_medicine_id: e.target.value }))}
              >
                <option value="">— Promote as new catalog item —</option>
                {catalog.map(m => (
                  <option key={m.id} value={m.id}>{m.name} ({m.medicine_code})</option>
                ))}
              </select>
            </div>
            {!form.merge_into_medicine_id && (
              <>
                <div>
                  <Label className="text-xs">Rate-A (₹) *</Label>
                  <Input type="number" min="0.01" step="0.01" value={form.rate_a}
                    onChange={e => setForm(f => ({ ...f, rate_a: e.target.value }))} />
                </div>
                <div>
                  <Label className="text-xs">Category *</Label>
                  <PharmacyMasterSelectWithCreate
                    path="categories"
                    value={form.category_id}
                    onChange={v => setForm(f => ({ ...f, category_id: v }))}
                    options={categories}
                    onOptionsChange={setCategories}
                    createFields={[{ key: 'name', label: 'Name', required: true }]}
                    createTitle="New Category"
                    placeholder="Select category…"
                  />
                </div>
                <div>
                  <Label className="text-xs">Strength</Label>
                  <Input value={form.strength} onChange={e => setForm(f => ({ ...f, strength: e.target.value }))} />
                </div>
                <div>
                  <Label className="text-xs">Dosage form</Label>
                  <Input value={form.dosage_form} onChange={e => setForm(f => ({ ...f, dosage_form: e.target.value }))} />
                </div>
              </>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={submit}>Save mapping</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
