import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Badge } from '../../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../../components/ui/dialog';
import { useToast } from '../../../../hooks/use-toast';
import { RefreshCw, Pill } from 'lucide-react';
import { errMsg } from '../../PharmacyModule';
import { printPdfFromUrl } from '../../../../utils/printPdf';

export default function PendingRxTab() {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState(null);
  const [qty, setQty] = useState({}); // item_id → qty string

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get('/api/pharmacy/prescriptions/pending');
      setRows(r.data || []);
    } catch { /* ignore */ } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const openDispense = (rx) => {
    setTarget(rx);
    const init = {};
    rx.items.forEach(it => { init[it.item_id] = String(it.quantity_remaining); });
    setQty(init);
    setOpen(true);
  };

  const submit = async () => {
    const items = target.items
      .map(it => ({ item_id: it.item_id, quantity: parseFloat(qty[it.item_id] || 0) }))
      .filter(x => x.quantity > 0);
    if (items.length === 0) {
      toast({ variant: 'destructive', title: 'Enter at least one quantity to dispense' });
      return;
    }
    try {
      const r = await axios.post(`/api/pharmacy/prescriptions/${target.id}/dispense`, { items });
      toast({ title: `Dispensed (Rx now ${r.data.status})` });
      const rxId = target.id;
      setOpen(false); load();
      // Auto-print the dispense slip
      printPdfFromUrl(`/api/pharmacy/prescriptions/${rxId}/dispense/pdf`);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Dispense failed', description: errMsg(e) });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex justify-between items-center">
          <span>Pending Prescriptions ({rows.length})</span>
          <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-3 w-3" /></Button>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? <p className="text-center py-6 text-sm text-gray-500">Loading…</p>
          : rows.length === 0 ? <p className="text-center py-6 text-sm text-gray-500">No pending prescriptions</p>
          : (
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-gray-600">
                <th className="py-2 pr-4">Rx #</th><th className="py-2 pr-4">Date</th>
                <th className="py-2 pr-4">Items</th><th className="py-2 pr-4">Status</th>
                <th className="py-2 text-right">Actions</th>
              </tr></thead>
              <tbody>
                {rows.map(rx => (
                  <tr key={rx.id} className="border-b hover:bg-gray-50">
                    <td className="py-2 pr-4 font-mono text-xs">{rx.prescription_number}</td>
                    <td className="py-2 pr-4 text-xs">{new Date(rx.prescription_date).toLocaleString()}</td>
                    <td className="py-2 pr-4">{rx.items.length}</td>
                    <td className="py-2 pr-4"><Badge variant="outline" className="text-xs">{rx.status}</Badge></td>
                    <td className="py-2 text-right">
                      <Button size="sm" onClick={() => openDispense(rx)}>
                        <Pill className="h-3 w-3 mr-1" /> Dispense
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle>Dispense — {target?.prescription_number}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <p className="text-xs text-gray-500">FIFO batch picking is used. Leave qty 0 to skip a line.</p>
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-gray-600">
                <th className="py-2 pr-4">Medicine</th><th className="py-2 pr-4">Prescribed</th>
                <th className="py-2 pr-4">Already</th><th className="py-2 pr-4">Remaining</th>
                <th className="py-2 pr-4">Dispense Qty</th>
              </tr></thead>
              <tbody>
                {target?.items.map(it => (
                  <tr key={it.item_id} className="border-b">
                    <td className="py-2 pr-4">{it.medicine_name}</td>
                    <td className="py-2 pr-4">{it.quantity_prescribed}</td>
                    <td className="py-2 pr-4">{it.quantity_dispensed}</td>
                    <td className="py-2 pr-4 font-medium">{it.quantity_remaining}</td>
                    <td className="py-2 pr-4">
                      <Input className="h-7 w-24" type="number" min="0" max={it.quantity_remaining}
                        value={qty[it.item_id] ?? 0}
                        onChange={e => setQty(s => ({ ...s, [it.item_id]: e.target.value }))} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={submit}>Dispense</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
