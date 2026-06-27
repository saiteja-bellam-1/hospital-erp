import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Textarea } from '../../../../components/ui/textarea';
import { Badge } from '../../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../../components/ui/dialog';
import { useToast } from '../../../../hooks/use-toast';
import { Search, RefreshCw, AlertTriangle, Sliders, ScrollText } from 'lucide-react';
import { errMsg } from '../../PharmacyModule';
import { usePharmacyStore } from '../../../../contexts/PharmacyStoreContext';

export default function InventoryTab() {
  const { toast } = useToast();
  const { storeParams } = usePharmacyStore();
  const [view, setView] = useState('stock');     // stock | batches | low | expiring | ledger
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  const [adjustOpen, setAdjustOpen] = useState(false);
  const [adjustTarget, setAdjustTarget] = useState(null);
  const [adjustQty, setAdjustQty] = useState('');
  const [adjustReason, setAdjustReason] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      let url, params = {};
      if (view === 'stock') { url = '/api/pharmacy/inventory'; if (search) params.search = search; }
      else if (view === 'batches') { url = '/api/pharmacy/inventory/batches'; }
      else if (view === 'low') { url = '/api/pharmacy/inventory/low-stock'; }
      else if (view === 'ledger') { url = '/api/pharmacy/inventory/ledger'; params.limit = 200; }
      const r = await axios.get(url, { params: { ...params, ...storeParams } });
      setData(r.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Load failed', description: errMsg(e) });
    } finally { setLoading(false); }
  }, [view, search, toast, storeParams]);

  useEffect(() => { load(); }, [load]);

  const openAdjust = (batch) => {
    setAdjustTarget(batch); setAdjustQty(''); setAdjustReason(''); setAdjustOpen(true);
  };
  const saveAdjust = async () => {
    if (!adjustTarget || !adjustQty || !adjustReason) return;
    try {
      await axios.post('/api/pharmacy/inventory/adjust', {
        batch_id: adjustTarget.id,
        qty_change: parseFloat(adjustQty),
        reason: adjustReason,
      });
      toast({ title: 'Stock adjusted' });
      setAdjustOpen(false); load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Adjustment failed', description: errMsg(e) });
    }
  };

  const tabBtn = (v, label, Icon) => (
    <Button size="sm" variant={view === v ? 'default' : 'outline'} onClick={() => setView(v)}>
      <Icon className="h-3 w-3 mr-1" /> {label}
    </Button>
  );

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader>
          <CardTitle className="flex flex-wrap items-center gap-2 justify-between">
            <div className="flex flex-wrap gap-2">
              {tabBtn('stock', 'Stock', ScrollText)}
              {tabBtn('batches', 'All Batches', ScrollText)}
              {tabBtn('low', 'Low Stock', AlertTriangle)}
              {tabBtn('ledger', 'Stock Ledger', Sliders)}
            </div>
            <div className="flex items-center gap-2">
              {view === 'stock' && (
                <div className="relative">
                  <Search className="absolute left-2 top-2.5 h-4 w-4 text-gray-400" />
                  <Input className="pl-8 h-8 w-56" placeholder="Search…" value={search} onChange={e => setSearch(e.target.value)} />
                </div>
              )}
              <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-3 w-3" /></Button>
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? <p className="text-center py-6 text-sm text-gray-500">Loading…</p>
            : data.length === 0 ? <p className="text-center py-6 text-sm text-gray-500">No records</p>
            : <TableForView view={view} data={data} onAdjust={openAdjust} />}
        </CardContent>
      </Card>

      <Dialog open={adjustOpen} onOpenChange={setAdjustOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Adjust Stock — {adjustTarget?.batch_number}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="text-xs text-gray-500">
              {adjustTarget?.medicine_name} • current qty: {adjustTarget?.quantity_in_stock}
            </div>
            <div>
              <Label>Qty change (signed: +5 to add, −3 to remove)</Label>
              <Input type="number" step="any" value={adjustQty} onChange={e => setAdjustQty(e.target.value)} />
            </div>
            <div>
              <Label>Reason</Label>
              <Textarea value={adjustReason} onChange={e => setAdjustReason(e.target.value)} placeholder="Damaged, recount, etc." />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAdjustOpen(false)}>Cancel</Button>
            <Button onClick={saveAdjust} disabled={!adjustQty || !adjustReason}>Adjust</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function TableForView({ view, data, onAdjust }) {
  if (view === 'stock' || view === 'low') {
    return (
      <table className="w-full text-sm">
        <thead><tr className="border-b text-left text-gray-600">
          <th className="py-2 pr-4">Code</th><th className="py-2 pr-4">Medicine</th>
          <th className="py-2 pr-4">Rack</th><th className="py-2 pr-4">UoM</th>
          <th className="py-2 pr-4">Total Stock</th><th className="py-2 pr-4">Min</th>
          <th className="py-2 pr-4">Batches</th>
          <th className="py-2 pr-4">Status</th>
        </tr></thead>
        <tbody>
          {data.map(r => (
            <tr key={r.medicine_id} className="border-b hover:bg-gray-50">
              <td className="py-2 pr-4 font-mono text-xs">{r.medicine_code}</td>
              <td className="py-2 pr-4">{r.name}</td>
              <td className="py-2 pr-4 text-xs">{r.rack_code || '—'}</td>
              <td className="py-2 pr-4 text-xs">{r.uom || '—'}</td>
              <td className="py-2 pr-4">{r.total_stock}</td>
              <td className="py-2 pr-4">{r.min_qty}</td>
              <td className="py-2 pr-4">{r.batch_count}</td>
              <td className="py-2 pr-4">
                {r.is_low_stock
                  ? <Badge variant="outline" className="text-xs text-orange-700">LOW</Badge>
                  : <Badge variant="outline" className="text-xs">OK</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  if (view === 'batches') {
    return (
      <table className="w-full text-sm">
        <thead><tr className="border-b text-left text-gray-600">
          <th className="py-2 pr-4">Medicine</th><th className="py-2 pr-4">Batch</th>
          <th className="py-2 pr-4">Qty</th>
          <th className="py-2 pr-4">MRP</th><th className="py-2 pr-4">P-Rate</th>
          <th className="py-2 pr-4">Supplier</th><th className="py-2 text-right">Actions</th>
        </tr></thead>
        <tbody>
          {data.map(b => (
            <tr key={b.id} className="border-b hover:bg-gray-50">
              <td className="py-2 pr-4">{b.medicine_name}</td>
              <td className="py-2 pr-4 font-mono text-xs">{b.batch_number}</td>
              <td className="py-2 pr-4">{b.quantity_in_stock}</td>
              <td className="py-2 pr-4">₹{b.mrp}</td>
              <td className="py-2 pr-4">₹{b.purchase_rate}</td>
              <td className="py-2 pr-4 text-xs">{b.supplier_name || '—'}</td>
              <td className="py-2 text-right">
                <Button size="sm" variant="outline" onClick={() => onAdjust(b)}>Adjust</Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  // ledger
  return (
    <table className="w-full text-sm">
      <thead><tr className="border-b text-left text-gray-600">
        <th className="py-2 pr-4">Time</th><th className="py-2 pr-4">Type</th>
        <th className="py-2 pr-4">Medicine</th><th className="py-2 pr-4">Batch</th>
        <th className="py-2 pr-4">Qty Δ</th><th className="py-2 pr-4">By</th>
        <th className="py-2 pr-4">Reference</th><th className="py-2 pr-4">Notes</th>
      </tr></thead>
      <tbody>
        {data.map(l => (
          <tr key={l.id} className="border-b hover:bg-gray-50">
            <td className="py-2 pr-4 text-xs">{new Date(l.created_at).toLocaleString()}</td>
            <td className="py-2 pr-4"><Badge variant="outline" className="text-xs">{l.txn_type}</Badge></td>
            <td className="py-2 pr-4">{l.medicine_name}</td>
            <td className="py-2 pr-4 font-mono text-xs">{l.batch_number || '—'}</td>
            <td className={`py-2 pr-4 font-mono ${l.qty_delta >= 0 ? 'text-green-700' : 'text-red-600'}`}>
              {l.qty_delta >= 0 ? '+' : ''}{l.qty_delta}
            </td>
            <td className="py-2 pr-4 text-xs">{l.performed_by_name || '—'}</td>
            <td className="py-2 pr-4 text-xs">{l.reference_type}#{l.reference_id}</td>
            <td className="py-2 pr-4 text-xs">{l.notes || '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
