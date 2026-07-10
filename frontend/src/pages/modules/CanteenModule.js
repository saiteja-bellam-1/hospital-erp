import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Routes, Route, Navigate, useLocation, Link } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { useToast } from '../../hooks/use-toast';
import { Plus, Pencil, RefreshCw, Search, UtensilsCrossed } from 'lucide-react';
import { useCanteenPermissions } from '../../hooks/useCanteenPermissions';
import CanteenOrderPanel from './canteen/CanteenOrderPanel';
import CanteenSalesCounter from './canteen/CanteenSalesCounter';
import CanteenSalesHistory from './canteen/CanteenSalesHistory';

function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join('; ');
  return e?.message || 'Request failed';
}

const STATUS_FLOW = ['pending', 'preparing', 'ready', 'delivered'];
const STATUS_BADGE = {
  pending: 'bg-blue-100 text-blue-800',
  preparing: 'bg-amber-100 text-amber-800',
  ready: 'bg-purple-100 text-purple-800',
  delivered: 'bg-green-100 text-green-800',
  cancelled: 'bg-gray-100 text-gray-500',
};

function CatalogPage({ hasPerm }) {
  const { toast } = useToast();
  const canManage = hasPerm('manage_catalog');
  const [items, setItems] = useState([]);
  const [categories, setCategories] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [itemOpen, setItemOpen] = useState(false);
  const [catOpen, setCatOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [itemForm, setItemForm] = useState({
    name: '', description: '', category_id: '', price: '', is_veg: true, is_active: true, sort_order: 0,
  });
  const [catForm, setCatForm] = useState({ name: '', sort_order: 0, is_active: true });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [i, c] = await Promise.all([
        axios.get('/api/canteen/items', { params: { active_only: false } }),
        axios.get('/api/canteen/categories', { params: { active_only: false } }),
      ]);
      setItems(i.data || []);
      setCategories(c.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Failed to load catalog', description: errMsg(e) });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return items;
    return items.filter((it) => `${it.name} ${it.category_name || ''}`.toLowerCase().includes(q));
  }, [items, search]);

  const openCreateItem = () => {
    setEditing(null);
    setItemForm({ name: '', description: '', category_id: '', price: '', is_veg: true, is_active: true, sort_order: 0 });
    setItemOpen(true);
  };
  const openEditItem = (row) => {
    setEditing(row);
    setItemForm({
      name: row.name || '',
      description: row.description || '',
      category_id: row.category_id || '',
      price: String(row.price ?? ''),
      is_veg: !!row.is_veg,
      is_active: !!row.is_active,
      sort_order: row.sort_order || 0,
    });
    setItemOpen(true);
  };

  const saveItem = async () => {
    const payload = {
      name: itemForm.name.trim(),
      description: itemForm.description || null,
      category_id: itemForm.category_id ? Number(itemForm.category_id) : null,
      price: parseFloat(itemForm.price || 0),
      is_veg: !!itemForm.is_veg,
      is_active: !!itemForm.is_active,
      sort_order: Number(itemForm.sort_order) || 0,
    };
    if (!payload.name) {
      toast({ variant: 'destructive', title: 'Name required' });
      return;
    }
    try {
      if (editing) {
        await axios.put(`/api/canteen/items/${editing.id}`, {
          ...payload,
          category_id: itemForm.category_id === '' ? 0 : payload.category_id,
        });
      } else {
        await axios.post('/api/canteen/items', payload);
      }
      setItemOpen(false);
      toast({ title: editing ? 'Item updated' : 'Item created' });
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Save failed', description: errMsg(e) });
    }
  };

  const saveCategory = async () => {
    if (!catForm.name.trim()) {
      toast({ variant: 'destructive', title: 'Category name required' });
      return;
    }
    try {
      await axios.post('/api/canteen/categories', {
        name: catForm.name.trim(),
        sort_order: Number(catForm.sort_order) || 0,
        is_active: true,
      });
      setCatOpen(false);
      setCatForm({ name: '', sort_order: 0, is_active: true });
      toast({ title: 'Category created' });
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Save failed', description: errMsg(e) });
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <UtensilsCrossed className="h-5 w-5" /> Catalog
          </h2>
          <p className="text-xs text-gray-500">Menu items and prices used when ordering for IP patients.</p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
          {canManage && (
            <>
              <Button size="sm" variant="outline" onClick={() => setCatOpen(true)}>Add category</Button>
              <Button size="sm" onClick={openCreateItem}><Plus className="h-3.5 w-3.5 mr-1" /> Add item</Button>
            </>
          )}
        </div>
      </div>

      <div className="relative max-w-sm">
        <Search className="absolute left-2 top-2.5 h-4 w-4 text-gray-400" />
        <Input className="pl-8 h-9" placeholder="Search items…" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      <Card>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b text-xs text-gray-600">
              <tr>
                <th className="text-left px-3 py-2">Item</th>
                <th className="text-left px-3 py-2">Category</th>
                <th className="text-right px-3 py-2">Price</th>
                <th className="text-center px-3 py-2">Status</th>
                {canManage && <th className="w-16" />}
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={5} className="text-center text-gray-500 py-8">No catalog items yet.</td></tr>
              ) : filtered.map((it) => (
                <tr key={it.id} className="border-b last:border-0">
                  <td className="px-3 py-2">
                    <div className="font-medium">{it.is_veg ? '🟢' : '🔴'} {it.name}</div>
                    {it.description && <div className="text-xs text-gray-500">{it.description}</div>}
                  </td>
                  <td className="px-3 py-2 text-gray-600">{it.category_name || '—'}</td>
                  <td className="px-3 py-2 text-right font-medium">₹{parseFloat(it.price).toFixed(2)}</td>
                  <td className="px-3 py-2 text-center">
                    <Badge className={it.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-500'}>
                      {it.is_active ? 'Active' : 'Inactive'}
                    </Badge>
                  </td>
                  {canManage && (
                    <td className="px-3 py-2 text-right">
                      <Button size="sm" variant="ghost" className="h-8 w-8 p-0" onClick={() => openEditItem(it)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Dialog open={itemOpen} onOpenChange={setItemOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>{editing ? 'Edit item' : 'New item'}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Name *</Label>
              <Input value={itemForm.name} onChange={(e) => setItemForm((p) => ({ ...p, name: e.target.value }))} />
            </div>
            <div>
              <Label>Description</Label>
              <Textarea value={itemForm.description} onChange={(e) => setItemForm((p) => ({ ...p, description: e.target.value }))} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label>Category</Label>
                <select
                  className="w-full h-9 border rounded-md px-2 text-sm"
                  value={itemForm.category_id}
                  onChange={(e) => setItemForm((p) => ({ ...p, category_id: e.target.value }))}
                >
                  <option value="">None</option>
                  {categories.filter((c) => c.is_active || String(c.id) === String(itemForm.category_id)).map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label>Price (₹) *</Label>
                <Input type="number" min="0" step="0.01" value={itemForm.price}
                  onChange={(e) => setItemForm((p) => ({ ...p, price: e.target.value }))} />
              </div>
            </div>
            <div className="flex gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={itemForm.is_veg}
                  onChange={(e) => setItemForm((p) => ({ ...p, is_veg: e.target.checked }))} />
                Vegetarian
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={itemForm.is_active}
                  onChange={(e) => setItemForm((p) => ({ ...p, is_active: e.target.checked }))} />
                Active
              </label>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setItemOpen(false)}>Cancel</Button>
            <Button onClick={saveItem}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={catOpen} onOpenChange={setCatOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>New category</DialogTitle></DialogHeader>
          <div>
            <Label>Name *</Label>
            <Input value={catForm.name} onChange={(e) => setCatForm((p) => ({ ...p, name: e.target.value }))} placeholder="e.g. Breakfast" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCatOpen(false)}>Cancel</Button>
            <Button onClick={saveCategory}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function KitchenPage({ hasPerm }) {
  const { toast } = useToast();
  const canStatus = hasPerm('manage_order_status');
  const [orders, setOrders] = useState([]);
  const [statusFilter, setStatusFilter] = useState('open');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter === 'open') {
        // fetch all non-cancelled, filter client-side to non-delivered
      } else if (statusFilter === 'all') {
        params.include_cancelled = true;
      } else {
        params.status = statusFilter;
      }
      const res = await axios.get('/api/canteen/orders', { params });
      let rows = res.data || [];
      if (statusFilter === 'open') {
        rows = rows.filter((o) => !['delivered', 'cancelled'].includes(o.status));
      }
      setOrders(rows);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Failed to load orders', description: errMsg(e) });
    } finally {
      setLoading(false);
    }
  }, [statusFilter, toast]);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh open queue so kitchen staff see new IP orders
  useEffect(() => {
    if (statusFilter !== 'open') return undefined;
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, [statusFilter, load]);

  const advance = async (order, next) => {
    try {
      await axios.patch(`/api/canteen/orders/${order.id}/status`, { status: next });
      toast({ title: `Order → ${next}` });
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Update failed', description: errMsg(e) });
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">IP Food Orders</h2>
          <p className="text-xs text-gray-500">
            Orders placed by nurse / reception for admitted patients. Update status as you prepare and deliver.
          </p>
        </div>
        <div className="flex gap-2 items-center">
          <select className="h-8 text-xs border rounded-md px-2" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="open">Open</option>
            <option value="pending">Pending</option>
            <option value="preparing">Preparing</option>
            <option value="ready">Ready</option>
            <option value="delivered">Delivered</option>
            <option value="all">All</option>
          </select>
          <Button size="sm" variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
        </div>
      </div>

      <div className="space-y-2">
        {orders.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center text-gray-500 text-sm space-y-1">
              <div>No IP food orders in this view.</div>
              <div className="text-xs">When ward staff order from an admission’s Food tab, those orders appear here.</div>
            </CardContent>
          </Card>
        ) : orders.map((o) => {
          const idx = STATUS_FLOW.indexOf(o.status);
          const next = idx >= 0 && idx < STATUS_FLOW.length - 1 ? STATUS_FLOW[idx + 1] : null;
          return (
            <Card key={o.id}>
              <CardContent className="p-4 text-sm space-y-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="font-medium">
                      {o.patient_name || `Patient #${o.patient_id}`}
                      {o.room_number ? ` · Room ${o.room_number}` : ''}
                      {o.ward ? ` · ${o.ward}` : ''}
                    </div>
                    <div className="text-xs text-gray-500">
                      Adm #{o.admission_number || o.admission_id}
                      {o.serve_date ? ` · Serve ${o.serve_date}` : ''}
                      {o.ordered_at ? ` · Ordered ${new Date(o.ordered_at).toLocaleString()}` : ''}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge className={STATUS_BADGE[o.status] || ''}>{o.status}</Badge>
                    <span className="font-semibold">₹{parseFloat(o.total || 0).toFixed(2)}</span>
                  </div>
                </div>
                <ul className="text-xs text-gray-700">
                  {(o.items || []).map((li) => (
                    <li key={li.id}>{li.item_name} × {li.quantity}</li>
                  ))}
                </ul>
                {o.notes && <p className="text-xs italic text-gray-500">{o.notes}</p>}
                {canStatus && next && (
                  <Button size="sm" onClick={() => advance(o, next)}>
                    Mark {next}
                  </Button>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

function PlaceOrderPage({ hasPerm }) {
  const { toast } = useToast();
  const [admissions, setAdmissions] = useState([]);
  const [admissionId, setAdmissionId] = useState('');
  const [q, setQ] = useState('');

  useEffect(() => {
    axios.get('/api/canteen/active-admissions', { params: { limit: 100 } })
      .then((res) => setAdmissions(res.data || []))
      .catch((e) => toast({ variant: 'destructive', title: 'Failed to load admissions', description: errMsg(e) }));
  }, [toast]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return admissions.slice(0, 50);
    return admissions.filter((a) => {
      const hay = `${a.patient_name || ''} ${a.admission_number || ''} ${a.room_number || ''}`.toLowerCase();
      return hay.includes(s);
    }).slice(0, 50);
  }, [admissions, q]);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold">Order for patient</h2>
        <p className="text-xs text-gray-500">Select an active admission, then order from the canteen catalog.</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="md:col-span-1">
          <CardHeader className="py-3"><CardTitle className="text-sm">Active admissions</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            <Input className="h-8 text-xs" placeholder="Search patient / room…" value={q} onChange={(e) => setQ(e.target.value)} />
            <div className="max-h-[420px] overflow-y-auto space-y-1">
              {filtered.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  onClick={() => setAdmissionId(String(a.id))}
                  className={`w-full text-left text-xs border rounded px-2 py-1.5 ${
                    String(admissionId) === String(a.id) ? 'border-blue-500 bg-blue-50' : 'hover:bg-gray-50'
                  }`}
                >
                  <div className="font-medium">{a.patient_name}</div>
                  <div className="text-gray-500">#{a.admission_number} · Room {a.room_number || '—'}</div>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card className="md:col-span-2">
          <CardContent className="p-4">
            <CanteenOrderPanel
              admissionId={admissionId ? Number(admissionId) : null}
              canPlaceOrder={hasPerm('place_order')}
              canViewOrders={hasPerm('view_orders')}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function CanteenNav({ hasPerm }) {
  const loc = useLocation();
  const links = [];
  // IP ward orders first — kitchen staff (canteen_sales) need this queue
  if (hasPerm('view_orders') || hasPerm('manage_order_status')) {
    links.push({ to: '/dashboard/canteen/orders', label: 'IP Food Orders' });
  }
  if (hasPerm('create_sale')) {
    links.push({ to: '/dashboard/canteen/pos', label: 'Sales Counter' });
  }
  if (hasPerm('view_sales')) {
    links.push({ to: '/dashboard/canteen/sales', label: 'Sales History' });
  }
  if (hasPerm('view_catalog') || hasPerm('manage_catalog')) {
    links.push({ to: '/dashboard/canteen/catalog', label: 'Catalog' });
  }
  if (hasPerm('place_order')) {
    links.push({ to: '/dashboard/canteen/order', label: 'Order for patient' });
  }
  return (
    <div className="flex gap-1 border-b mb-4 overflow-x-auto">
      {links.map((l) => (
        <Link
          key={l.to}
          to={l.to}
          className={`px-4 py-2 text-sm whitespace-nowrap ${
            loc.pathname.startsWith(l.to)
              ? 'border-b-2 border-blue-600 font-semibold text-blue-700'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          {l.label}
        </Link>
      ))}
    </div>
  );
}

export default function CanteenModule() {
  const { loaded, hasPerm } = useCanteenPermissions();

  if (!loaded) {
    return <div className="p-6 text-sm text-gray-500">Loading canteen…</div>;
  }

  // canteen_sales: land on IP food queue; admin with catalog lands on catalog; POS otherwise
  const defaultPath = hasPerm('manage_order_status') && !hasPerm('manage_catalog')
    ? 'orders'
    : hasPerm('manage_catalog')
      ? 'catalog'
      : hasPerm('create_sale')
        ? 'pos'
        : hasPerm('view_orders')
          ? 'orders'
          : hasPerm('view_sales')
            ? 'sales'
            : hasPerm('place_order')
              ? 'order'
              : null;

  if (!defaultPath) {
    return (
      <div className="p-6 text-sm text-gray-600">
        You do not have canteen permissions. Ask an admin to grant canteen access or assign the canteen_admin / canteen_sales role.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <CanteenNav hasPerm={hasPerm} />
      <Routes>
        <Route index element={<Navigate to={defaultPath} replace />} />
        <Route path="pos" element={
          <CanteenSalesCounter canCreate={hasPerm('create_sale')} canViewSales={hasPerm('view_sales')} />
        } />
        <Route path="sales" element={<CanteenSalesHistory canVoid={hasPerm('void_sale')} />} />
        <Route path="catalog" element={<CatalogPage hasPerm={hasPerm} />} />
        <Route path="orders" element={<KitchenPage hasPerm={hasPerm} />} />
        <Route path="order" element={<PlaceOrderPage hasPerm={hasPerm} />} />
        <Route path="*" element={<Navigate to={defaultPath} replace />} />
      </Routes>
    </div>
  );
}
