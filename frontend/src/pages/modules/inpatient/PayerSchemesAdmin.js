import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  Card, CardContent, CardHeader, CardTitle
} from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Badge } from '../../../components/ui/badge';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from '../../../components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue
} from '../../../components/ui/select';
import { useToast } from '../../../hooks/use-toast';
import {
  Banknote, Shield, FileCheck2, Landmark, Plus, Edit, Trash2,
  Loader2, CheckCircle2, Power
} from 'lucide-react';

const SCHEME_TYPES = [
  { value: 'cash',              label: 'Cash',              icon: Banknote   },
  { value: 'private_insurance', label: 'Private Insurance', icon: Shield     },
  { value: 'tpa',               label: 'TPA',               icon: FileCheck2 },
  { value: 'govt_scheme',       label: 'Govt Scheme',       icon: Landmark   },
];

const typeMeta = (t) => SCHEME_TYPES.find(s => s.value === t) || SCHEME_TYPES[0];

const EMPTY_FORM = { code: '', name: '', scheme_type: 'govt_scheme', active: true, notes: '' };

const PayerSchemesAdmin = () => {
  const { toast } = useToast();
  const [schemes, setSchemes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);  // scheme being edited, or null for create
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  const fetchSchemes = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/inpatient/payer-schemes', {
        params: { active_only: false }
      });
      setSchemes(res.data || []);
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail
        : 'Failed to load payer schemes';
      toast({ variant: 'destructive', title: 'Error', description: msg });
      setSchemes([]);
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { fetchSchemes(); }, [fetchSchemes]);

  const openCreate = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  };

  const openEdit = (scheme) => {
    setEditing(scheme);
    setForm({
      code: scheme.code,
      name: scheme.name,
      scheme_type: scheme.scheme_type,
      active: scheme.active,
      notes: scheme.notes || '',
    });
    setDialogOpen(true);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.code.trim() || !form.name.trim()) {
      toast({ variant: 'destructive', title: 'Missing fields',
              description: 'Code and Name are required.' });
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await axios.put(`/api/inpatient/payer-schemes/${editing.id}`, form);
        toast({ title: 'Updated', description: `${form.name} updated.` });
      } else {
        await axios.post('/api/inpatient/payer-schemes', form);
        toast({ title: 'Created', description: `${form.name} added.` });
      }
      setDialogOpen(false);
      fetchSchemes();
    } catch (err) {
      const msg = typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail
        : 'Save failed';
      toast({ variant: 'destructive', title: 'Error', description: msg });
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (scheme) => {
    try {
      await axios.put(`/api/inpatient/payer-schemes/${scheme.id}`,
        { active: !scheme.active });
      fetchSchemes();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error',
              description: 'Could not toggle active state' });
    }
  };

  const remove = async (scheme) => {
    if (!window.confirm(`Deactivate "${scheme.name}"? Admissions already on this scheme keep it; the option just stops appearing on new admissions.`)) {
      return;
    }
    try {
      await axios.delete(`/api/inpatient/payer-schemes/${scheme.id}`);
      toast({ title: 'Deactivated', description: `${scheme.name} deactivated.` });
      fetchSchemes();
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error',
              description: 'Could not deactivate' });
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Payer Schemes</CardTitle>
          <p className="text-sm text-gray-500 mt-1">
            Payment modes offered at admission: cash, private insurance, TPA, and government schemes
            (Aarogyasri, Teachers', CGHS, etc.). The order here drives the payer card grid on the admit wizard.
          </p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="h-4 w-4 mr-2" /> Add scheme
        </Button>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex items-center justify-center py-8 text-gray-500">
            <Loader2 className="h-5 w-5 animate-spin mr-2" /> Loading…
          </div>
        ) : schemes.length === 0 ? (
          <div className="text-center py-10 text-gray-500 text-sm">
            No payer schemes yet. Click <b>Add scheme</b> to create one.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b bg-gray-50">
                  <th className="text-left py-2 px-3 font-medium">Code</th>
                  <th className="text-left py-2 px-3 font-medium">Name</th>
                  <th className="text-left py-2 px-3 font-medium">Type</th>
                  <th className="text-left py-2 px-3 font-medium">Notes</th>
                  <th className="text-left py-2 px-3 font-medium">Status</th>
                  <th className="text-right py-2 px-3 font-medium w-32">Actions</th>
                </tr>
              </thead>
              <tbody>
                {schemes.map(s => {
                  const meta = typeMeta(s.scheme_type);
                  const Icon = meta.icon;
                  return (
                    <tr key={s.id} className="border-b hover:bg-gray-50">
                      <td className="py-2 px-3 font-mono text-xs">{s.code}</td>
                      <td className="py-2 px-3 font-medium">{s.name}</td>
                      <td className="py-2 px-3">
                        <span className="inline-flex items-center gap-1.5 text-xs text-gray-700">
                          <Icon className="h-3.5 w-3.5" />
                          {meta.label}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-gray-600 text-xs max-w-xs truncate">
                        {s.notes || '—'}
                      </td>
                      <td className="py-2 px-3">
                        {s.active
                          ? <Badge className="bg-green-100 text-green-800 text-xs">Active</Badge>
                          : <Badge className="bg-gray-100 text-gray-600 text-xs">Inactive</Badge>}
                      </td>
                      <td className="py-2 px-3 text-right">
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0"
                                title={s.active ? 'Deactivate temporarily' : 'Reactivate'}
                                onClick={() => toggleActive(s)}>
                          {s.active
                            ? <Power className="h-4 w-4 text-amber-600" />
                            : <CheckCircle2 className="h-4 w-4 text-green-600" />}
                        </Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0"
                                title="Edit"
                                onClick={() => openEdit(s)}>
                          <Edit className="h-4 w-4 text-blue-600" />
                        </Button>
                        <Button size="sm" variant="ghost" className="h-7 w-7 p-0"
                                title="Deactivate (soft delete)"
                                onClick={() => remove(s)}>
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit payer scheme' : 'Add payer scheme'}</DialogTitle>
          </DialogHeader>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <Label>Code *</Label>
              <Input
                value={form.code}
                onChange={e => setForm(p => ({ ...p, code: e.target.value.toUpperCase() }))}
                placeholder="e.g. AAROGYASRI, PRIVATE, CGHS"
                disabled={!!editing}
                required
              />
              {editing && (
                <p className="text-xs text-gray-500 mt-1">Code is immutable once created.</p>
              )}
            </div>
            <div>
              <Label>Display name *</Label>
              <Input
                value={form.name}
                onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                placeholder="e.g. Aarogyasri"
                required
              />
            </div>
            <div>
              <Label>Scheme type *</Label>
              <Select
                value={form.scheme_type}
                onValueChange={v => setForm(p => ({ ...p, scheme_type: v }))}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {SCHEME_TYPES.map(t => {
                    const Icon = t.icon;
                    return (
                      <SelectItem key={t.value} value={t.value}>
                        <span className="inline-flex items-center gap-2">
                          <Icon className="h-4 w-4" /> {t.label}
                        </span>
                      </SelectItem>
                    );
                  })}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Notes</Label>
              <Textarea
                value={form.notes}
                onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                rows={2}
                placeholder="Optional. E.g., approval cell phone, copay rules."
              />
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={form.active}
                onChange={e => setForm(p => ({ ...p, active: e.target.checked }))}
              />
              Active — show this option in the admit wizard
            </label>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={saving}>
                {saving && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {editing ? 'Save changes' : 'Create scheme'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  );
};

export default PayerSchemesAdmin;
