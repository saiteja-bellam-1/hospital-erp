import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import { Card, CardContent } from '../../../components/ui/card';
import { useToast } from '../../../hooks/use-toast';
import { Minus, Plus, RefreshCw, ShoppingCart, Trash2 } from 'lucide-react';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';

function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join('; ');
  return e?.message || 'Request failed';
}

/**
 * Walk-in canteen POS counter — catalog cart → cash/UPI/card sale → receipt.
 */
export default function CanteenSalesCounter({ canCreate = true, canViewSales = true }) {
  const { toast } = useToast();
  const [catalog, setCatalog] = useState([]);
  const [categories, setCategories] = useState([]);
  const [cart, setCart] = useState({}); // item_id → qty
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [paymentType, setPaymentType] = useState('cash');
  const [customerName, setCustomerName] = useState('');
  const [customerPhone, setCustomerPhone] = useState('');
  const [discount, setDiscount] = useState('');
  const [notes, setNotes] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [previewSaleId, setPreviewSaleId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [itemsRes, catsRes] = await Promise.all([
        axios.get('/api/canteen/items', { params: { active_only: true } }),
        axios.get('/api/canteen/categories', { params: { active_only: true } }),
      ]);
      setCatalog(itemsRes.data || []);
      setCategories(catsRes.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Failed to load menu', description: errMsg(e) });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (catalog || []).filter((it) => {
      if (categoryFilter !== 'all' && String(it.category_id) !== String(categoryFilter)) return false;
      if (q && !(`${it.name} ${it.description || ''}`.toLowerCase().includes(q))) return false;
      return true;
    });
  }, [catalog, categoryFilter, search]);

  const cartLines = useMemo(() => (
    Object.entries(cart)
      .filter(([, qty]) => qty > 0)
      .map(([id, qty]) => {
        const it = catalog.find((c) => String(c.id) === String(id));
        return it ? { ...it, quantity: qty, line_total: qty * parseFloat(it.price || 0) } : null;
      })
      .filter(Boolean)
  ), [cart, catalog]);

  const subtotal = cartLines.reduce((s, l) => s + l.line_total, 0);
  const discountAmt = Math.min(Math.max(0, parseFloat(discount) || 0), subtotal);
  const grandTotal = Math.max(0, subtotal - discountAmt);

  const setQty = (itemId, qty) => {
    setCart((prev) => {
      const next = { ...prev };
      if (qty <= 0) delete next[itemId];
      else next[itemId] = qty;
      return next;
    });
  };

  const clearCart = () => {
    setCart({});
    setDiscount('');
    setNotes('');
    setCustomerName('');
    setCustomerPhone('');
    setPaymentType('cash');
  };

  const checkout = async () => {
    if (!canCreate) return;
    if (!cartLines.length) {
      toast({ variant: 'destructive', title: 'Cart is empty' });
      return;
    }
    setBusy(true);
    try {
      const res = await axios.post('/api/canteen/sales', {
        payment_type: paymentType,
        customer_name: customerName || null,
        customer_phone: customerPhone || null,
        discount_amount: discountAmt,
        notes: notes || null,
        items: cartLines.map((l) => ({ item_id: l.id, quantity: l.quantity })),
      });
      toast({ title: 'Sale completed', description: res.data.sale_number });
      clearCart();
      if (canViewSales && res.data?.id) setPreviewSaleId(res.data.id);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Sale failed', description: errMsg(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <ShoppingCart className="h-5 w-5" /> Sales Counter
          </h2>
          <p className="text-xs text-gray-500">Walk-in / cash canteen sales (not charged to IP bills).</p>
        </div>
        <Button size="sm" variant="outline" onClick={load} disabled={loading}>
          <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh menu
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <Card className="lg:col-span-3">
          <CardContent className="p-3 space-y-3">
            <div className="flex flex-wrap gap-2">
              <Input
                className="h-8 text-xs flex-1 min-w-[160px]"
                placeholder="Search menu…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <select
                className="h-8 text-xs border rounded-md px-2 bg-white"
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
              >
                <option value="all">All categories</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            {filtered.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-8">No active menu items.</p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[560px] overflow-y-auto">
                {filtered.map((it) => {
                  const qty = cart[it.id] || 0;
                  return (
                    <div key={it.id} className="flex items-center justify-between border rounded-lg bg-white px-3 py-2 text-sm">
                      <button
                        type="button"
                        className="text-left min-w-0 flex-1 pr-2"
                        onClick={() => canCreate && setQty(it.id, qty + 1)}
                        disabled={!canCreate}
                      >
                        <div className="font-medium truncate">{it.is_veg ? '🟢' : '🔴'} {it.name}</div>
                        <div className="text-xs text-gray-500">
                          ₹{parseFloat(it.price).toFixed(2)}
                          {it.category_name ? ` · ${it.category_name}` : ''}
                        </div>
                      </button>
                      <div className="flex items-center gap-1 shrink-0">
                        <Button type="button" size="sm" variant="outline" className="h-7 w-7 p-0"
                          onClick={() => setQty(it.id, qty - 1)} disabled={!canCreate || qty <= 0}>
                          <Minus className="h-3 w-3" />
                        </Button>
                        <span className="w-6 text-center text-xs font-semibold">{qty}</span>
                        <Button type="button" size="sm" variant="outline" className="h-7 w-7 p-0"
                          onClick={() => setQty(it.id, qty + 1)} disabled={!canCreate}>
                          <Plus className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardContent className="p-3 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">Cart</h3>
              {cartLines.length > 0 && (
                <Button type="button" size="sm" variant="ghost" className="h-7 text-xs text-red-600"
                  onClick={clearCart} disabled={!canCreate}>
                  <Trash2 className="h-3.5 w-3.5 mr-1" /> Clear
                </Button>
              )}
            </div>

            {cartLines.length === 0 ? (
              <p className="text-xs text-gray-500 text-center py-6">Tap menu items to add.</p>
            ) : (
              <div className="space-y-1 max-h-48 overflow-y-auto text-xs">
                {cartLines.map((l) => (
                  <div key={l.id} className="flex justify-between gap-2">
                    <span className="truncate">{l.name} × {l.quantity}</span>
                    <span className="shrink-0 font-medium">₹{l.line_total.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            )}

            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Customer name</Label>
                <Input className="h-8 text-xs" value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder="Optional" disabled={!canCreate} />
              </div>
              <div>
                <Label className="text-xs">Phone</Label>
                <Input className="h-8 text-xs" value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)} placeholder="Optional" disabled={!canCreate} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Payment</Label>
                <select
                  className="w-full h-8 text-xs border rounded-md px-2 bg-white"
                  value={paymentType}
                  onChange={(e) => setPaymentType(e.target.value)}
                  disabled={!canCreate}
                >
                  <option value="cash">Cash</option>
                  <option value="upi">UPI</option>
                  <option value="card">Card</option>
                </select>
              </div>
              <div>
                <Label className="text-xs">Discount (₹)</Label>
                <Input className="h-8 text-xs" type="number" min="0" step="0.01" value={discount}
                  onChange={(e) => setDiscount(e.target.value)} disabled={!canCreate} />
              </div>
            </div>

            <div>
              <Label className="text-xs">Notes</Label>
              <Input className="h-8 text-xs" value={notes} onChange={(e) => setNotes(e.target.value)} disabled={!canCreate} />
            </div>

            <div className="border-t pt-2 text-sm space-y-1">
              <div className="flex justify-between text-xs text-gray-600">
                <span>Subtotal</span><span>₹{subtotal.toFixed(2)}</span>
              </div>
              {discountAmt > 0 && (
                <div className="flex justify-between text-xs text-gray-600">
                  <span>Discount</span><span>−₹{discountAmt.toFixed(2)}</span>
                </div>
              )}
              <div className="flex justify-between font-semibold">
                <span>Total</span><span>₹{grandTotal.toFixed(2)}</span>
              </div>
            </div>

            <Button className="w-full" onClick={checkout} disabled={!canCreate || busy || !cartLines.length}>
              {busy ? 'Processing…' : `Collect ₹${grandTotal.toFixed(2)}`}
            </Button>
          </CardContent>
        </Card>
      </div>

      <PdfPreviewDialog
        open={!!previewSaleId}
        onClose={() => setPreviewSaleId(null)}
        title="Canteen sale receipt"
        path={previewSaleId ? `/api/canteen/sales/${previewSaleId}/receipt/pdf` : null}
      />
    </div>
  );
}
