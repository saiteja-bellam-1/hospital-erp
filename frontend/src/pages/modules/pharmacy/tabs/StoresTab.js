import React, { useCallback, useEffect, useState } from 'react';
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
import { Plus, Pencil, RefreshCw, Store } from 'lucide-react';
import { errMsg } from '../../PharmacyModule';
import { usePharmacyStore } from '../../../../contexts/PharmacyStoreContext';

const blankForm = {
  code: '',
  name: '',
  store_type: 'satellite',
  parent_store_id: null,
  location: '',
  description: '',
  is_active: true,
};

export default function StoresTab() {
  const { toast } = useToast();
  const { refresh: refreshContext, requireStoreAssignment } = usePharmacyStore();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(blankForm);
  const [staff, setStaff] = useState([]);
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignUser, setAssignUser] = useState(null);
  const [assignStoreIds, setAssignStoreIds] = useState([]);
  const masterStore = rows.find((r) => r.store_type === 'master');

  const loadStaff = useCallback(async () => {
    try {
      const r = await axios.get('/api/pharmacy/stores/staff');
      setStaff(r.data || []);
    } catch {
      setStaff([]);
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get('/api/pharmacy/stores', { params: { active_only: false } });
      setRows(r.data || []);
      await loadStaff();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Load failed', description: errMsg(e) });
    } finally {
      setLoading(false);
    }
  }, [toast, loadStaff]);

  useEffect(() => { load(); }, [load]);

  const openCreate = () => {
    setEditing(null);
    setForm({ ...blankForm, parent_store_id: masterStore?.id ?? null });
    setOpen(true);
  };

  const openEdit = (row) => {
    setEditing(row);
    setForm({
      code: row.code,
      name: row.name,
      store_type: row.store_type,
      parent_store_id: row.parent_store_id,
      location: row.location || '',
      description: row.description || '',
      is_active: row.is_active,
    });
    setOpen(true);
  };

  const save = async () => {
    try {
      const payload = {
        ...form,
        parent_store_id: form.store_type === 'satellite' ? (form.parent_store_id || masterStore?.id) : null,
      };
      if (editing) {
        await axios.put(`/api/pharmacy/stores/${editing.id}`, payload);
        toast({ title: 'Store updated' });
      } else {
        await axios.post('/api/pharmacy/stores', payload);
        toast({ title: 'Store created' });
      }
      setOpen(false);
      load();
      refreshContext();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Save failed', description: errMsg(e) });
    }
  };

  const openAssign = (user) => {
    setAssignUser(user);
    setAssignStoreIds(user.store_ids || []);
    setAssignOpen(true);
  };

  const toggleAssignStore = (storeId) => {
    setAssignStoreIds((prev) => (
      prev.includes(storeId) ? prev.filter((id) => id !== storeId) : [...prev, storeId]
    ));
  };

  const saveAssignment = async () => {
    if (!assignUser) return;
    try {
      await axios.put(`/api/pharmacy/users/${assignUser.id}/stores`, { store_ids: assignStoreIds });
      toast({ title: 'Store assignment saved' });
      setAssignOpen(false);
      loadStaff();
      refreshContext();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Assignment failed', description: errMsg(e) });
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Store className="h-5 w-5" /> Pharmacy Stores
          </CardTitle>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={load} disabled={loading}>
              <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </Button>
            <Button size="sm" onClick={openCreate}>
              <Plus className="h-4 w-4 mr-1" /> Add Store
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gray-600 mb-4">
            Master pharmacy receives supplier purchases. Satellite stores receive stock via transfers and bill patients locally.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-600">
                  <th className="py-2 pr-4">Code</th>
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Location</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b">
                    <td className="py-2 pr-4 font-mono">{row.code}</td>
                    <td className="py-2 pr-4">{row.name}</td>
                    <td className="py-2 pr-4 capitalize">{row.store_type}</td>
                    <td className="py-2 pr-4">{row.location || '—'}</td>
                    <td className="py-2 pr-4">
                      {row.is_default && <Badge className="mr-1">Default</Badge>}
                      <Badge variant={row.is_active ? 'default' : 'secondary'}>
                        {row.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td className="py-2">
                      {!row.is_default && (
                        <Button size="sm" variant="ghost" onClick={() => openEdit(row)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Staff store access</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gray-600 mb-4">
            Assign pharmacists and POS operators to one or more stores. When store assignment is required, users without an assignment cannot bill at any store.
          </p>
          {requireStoreAssignment && staff.some((u) => !(u.store_ids || []).length) && (
            <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 mb-4">
              Some staff have no store assigned — they will be blocked from pharmacy operations until assigned.
            </p>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-600">
                  <th className="py-2 pr-4">User</th>
                  <th className="py-2 pr-4">Role</th>
                  <th className="py-2 pr-4">Assigned stores</th>
                  <th className="py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {staff.map((u) => (
                  <tr key={u.id} className="border-b">
                    <td className="py-2 pr-4">{u.display_name} <span className="text-gray-400">({u.username})</span></td>
                    <td className="py-2 pr-4">{u.role_name}</td>
                    <td className="py-2 pr-4">
                      {(u.store_ids || []).length === 0
                        ? <span className="text-amber-600">None assigned</span>
                        : rows.filter((s) => u.store_ids.includes(s.id)).map((s) => s.code).join(', ')}
                    </td>
                    <td className="py-2">
                      <Button size="sm" variant="outline" onClick={() => openAssign(u)}>Assign</Button>
                    </td>
                  </tr>
                ))}
                {staff.length === 0 && (
                  <tr><td colSpan={4} className="py-6 text-center text-gray-500">No pharmacy staff users found</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Dialog open={assignOpen} onOpenChange={setAssignOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Assign stores — {assignUser?.display_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 py-2">
            {rows.filter((s) => s.is_active).map((s) => (
              <label key={s.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={assignStoreIds.includes(s.id)}
                  onChange={() => toggleAssignStore(s.id)}
                />
                {s.code} — {s.name}
              </label>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAssignOpen(false)}>Cancel</Button>
            <Button onClick={saveAssignment}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit Store' : 'New Satellite Store'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div>
              <Label>Code</Label>
              <Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} />
            </div>
            <div>
              <Label>Name</Label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <Label>Block / Floor location</Label>
              <Input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
            </div>
            <div>
              <Label>Description</Label>
              <Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </div>
            {editing && (
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="store-active"
                  checked={form.is_active}
                  onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                />
                <Label htmlFor="store-active">Active</Label>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
