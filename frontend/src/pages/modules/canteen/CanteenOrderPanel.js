import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import { Textarea } from '../../../components/ui/textarea';
import { useToast } from '../../../hooks/use-toast';
import { Plus, Minus, RefreshCw, Trash2 } from 'lucide-react';
import { localDateString } from '../../../utils/localDate';

const STATUS_BADGE = {
  pending: 'bg-blue-100 text-blue-800',
  preparing: 'bg-amber-100 text-amber-800',
  ready: 'bg-purple-100 text-purple-800',
  delivered: 'bg-green-100 text-green-800',
  cancelled: 'bg-gray-100 text-gray-500',
};

function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join('; ');
  return e?.message || 'Request failed';
}

/**
 * Order food for an admitted patient from the canteen catalog.
 * Used in IP admission Food tab and Canteen → Place Order.
 */
export default function CanteenOrderPanel({
  admissionId,
  canPlaceOrder = false,
  canViewOrders = true,
  compact = false,
}) {
  const { toast } = useToast();
  const [catalog, setCatalog] = useState([]);
  const [categories, setCategories] = useState([]);
  const [orders, setOrders] = useState([]);
  const [cart, setCart] = useState({}); // item_id → qty
  const [notes, setNotes] = useState('');
  const [serveDate, setServeDate] = useState(localDateString(new Date()));
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!admissionId) return;
    setLoading(true);
    try {
      const [itemsRes, catsRes, ordersRes] = await Promise.all([
        axios.get('/api/canteen/items', { params: { active_only: true } }),
        axios.get('/api/canteen/categories', { params: { active_only: true } }),
        canViewOrders
          ? axios.get(`/api/canteen/admissions/${admissionId}/orders`)
          : Promise.resolve({ data: [] }),
      ]);
      setCatalog(itemsRes.data || []);
      setCategories(catsRes.data || []);
      setOrders(ordersRes.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Failed to load canteen', description: errMsg(e) });
    } finally {
      setLoading(false);
    }
  }, [admissionId, canViewOrders, toast]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (catalog || []).filter((it) => {
      if (categoryFilter !== 'all' && String(it.category_id) !== String(categoryFilter)) return false;
      if (q && !(`${it.name} ${it.description || ''}`.toLowerCase().includes(q))) return false;
      return true;
    });
  }, [catalog, categoryFilter, search]);

  const cartLines = useMemo(() => {
    return Object.entries(cart)
      .filter(([, qty]) => qty > 0)
      .map(([id, qty]) => {
        const it = catalog.find((c) => String(c.id) === String(id));
        return it ? { ...it, quantity: qty, line_total: qty * parseFloat(it.price || 0) } : null;
      })
      .filter(Boolean);
  }, [cart, catalog]);

  const cartTotal = cartLines.reduce((s, l) => s + l.line_total, 0);

  const setQty = (itemId, qty) => {
    setCart((prev) => {
      const next = { ...prev };
      if (qty <= 0) delete next[itemId];
      else next[itemId] = qty;
      return next;
    });
  };

  const placeOrder = async () => {
    if (!cartLines.length) {
      toast({ variant: 'destructive', title: 'Cart is empty' });
      return;
    }
    setBusy(true);
    try {
      await axios.post('/api/canteen/orders', {
        admission_id: admissionId,
        notes: notes || null,
        serve_date: serveDate || null,
        items: cartLines.map((l) => ({ item_id: l.id, quantity: l.quantity })),
      });
      toast({ title: 'Order placed' });
      setCart({});
      setNotes('');
      await load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Order failed', description: errMsg(e) });
    } finally {
      setBusy(false);
    }
  };

  const cancelOrder = async (orderId) => {
    setBusy(true);
    try {
      await axios.post(`/api/canteen/orders/${orderId}/cancel`, { reason: 'Cancelled by staff' });
      toast({ title: 'Order cancelled' });
      await load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Cancel failed', description: errMsg(e) });
    } finally {
      setBusy(false);
    }
  };

  const unbilledTotal = (orders || []).reduce((s, o) => (
    o.status !== 'cancelled' && !o.billed ? s + parseFloat(o.total || 0) : s
  ), 0);

  if (!admissionId) {
    return <p className="text-sm text-gray-500">Select an admission to order food.</p>;
  }

  return (
    <div className={`space-y-4 ${compact ? '' : ''}`}>
      <div className="flex items-center justify-between">
        <div className="text-xs text-gray-500">
          Unbilled canteen: <strong className="text-gray-800">₹{unbilledTotal.toFixed(2)}</strong>
        </div>
        <Button size="sm" variant="ghost" onClick={load} disabled={loading}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </Button>
      </div>

      {canPlaceOrder && (
        <div className="border rounded-lg p-3 space-y-3 bg-gray-50">
          <div className="flex flex-wrap gap-2 items-end">
            <div className="flex-1 min-w-[140px]">
              <Label className="text-xs">Search menu</Label>
              <Input className="h-8 text-xs" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Idli, tea…" />
            </div>
            <div className="w-40">
              <Label className="text-xs">Category</Label>
              <select
                className="w-full h-8 text-xs border rounded-md px-2 bg-white"
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
              >
                <option value="all">All</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div className="w-36">
              <Label className="text-xs">Serve date</Label>
              <Input type="date" className="h-8 text-xs" value={serveDate} onChange={(e) => setServeDate(e.target.value)} />
            </div>
          </div>

          {filtered.length === 0 ? (
            <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded p-2">
              No active catalog items. Canteen admin must add items under Canteen → Catalog.
            </p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-56 overflow-y-auto">
              {filtered.map((it) => {
                const qty = cart[it.id] || 0;
                return (
                  <div key={it.id} className="flex items-center justify-between border rounded bg-white px-2 py-1.5 text-xs">
                    <div className="min-w-0 pr-2">
                      <div className="font-medium truncate">
                        {it.is_veg ? '🟢' : '🔴'} {it.name}
                      </div>
                      <div className="text-gray-500">₹{parseFloat(it.price).toFixed(2)}
                        {it.category_name ? ` · ${it.category_name}` : ''}
                      </div>
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      <Button type="button" size="sm" variant="outline" className="h-7 w-7 p-0"
                        onClick={() => setQty(it.id, qty - 1)} disabled={qty <= 0}>
                        <Minus className="h-3 w-3" />
                      </Button>
                      <span className="w-5 text-center font-medium">{qty}</span>
                      <Button type="button" size="sm" variant="outline" className="h-7 w-7 p-0"
                        onClick={() => setQty(it.id, qty + 1)}>
                        <Plus className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {cartLines.length > 0 && (
            <div className="border-t pt-2 space-y-2">
              <div className="text-xs space-y-1">
                {cartLines.map((l) => (
                  <div key={l.id} className="flex justify-between">
                    <span>{l.name} × {l.quantity}</span>
                    <span>₹{l.line_total.toFixed(2)}</span>
                  </div>
                ))}
                <div className="flex justify-between font-semibold border-t pt-1">
                  <span>Total</span>
                  <span>₹{cartTotal.toFixed(2)}</span>
                </div>
              </div>
              <div>
                <Label className="text-xs">Notes (diet / allergies)</Label>
                <Textarea className="text-xs min-h-[56px]" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. no salt, soft diet" />
              </div>
              <Button size="sm" onClick={placeOrder} disabled={busy}>
                Place order · ₹{cartTotal.toFixed(2)}
              </Button>
            </div>
          )}
        </div>
      )}

      {canViewOrders && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wide">Orders</h4>
          {orders.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-3">No canteen orders yet.</p>
          ) : (
            orders.map((o) => (
              <div key={o.id} className="border rounded-lg p-3 text-xs space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge className={STATUS_BADGE[o.status] || 'bg-gray-100'}>{o.status}</Badge>
                    {o.billed && <Badge className="bg-amber-100 text-amber-800">billed</Badge>}
                    <span className="text-gray-500">
                      {o.serve_date || (o.ordered_at ? o.ordered_at.slice(0, 10) : '')}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold">₹{parseFloat(o.total || 0).toFixed(2)}</span>
                    {canPlaceOrder && !o.billed && !['delivered', 'cancelled'].includes(o.status) && (
                      <Button type="button" size="sm" variant="ghost" className="h-7 w-7 p-0 text-red-500"
                        onClick={() => cancelOrder(o.id)} disabled={busy}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                </div>
                <ul className="text-gray-700">
                  {(o.items || []).map((li) => (
                    <li key={li.id}>{li.item_name} × {li.quantity} @ ₹{parseFloat(li.unit_price).toFixed(2)}</li>
                  ))}
                </ul>
                {o.notes && <p className="text-gray-500 italic">{o.notes}</p>}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
