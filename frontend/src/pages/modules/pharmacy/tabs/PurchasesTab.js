import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Badge } from '../../../../components/ui/badge';
import { Textarea } from '../../../../components/ui/textarea';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '../../../../components/ui/dialog';
import { Plus, RefreshCw, Printer, Undo2 } from 'lucide-react';
import { printPdfFromUrl } from '../../../../utils/printPdf';
import { useToast } from '../../../../hooks/use-toast';
import { errMsg } from '../../PharmacyModule';

export default function PurchasesTab() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState(null);
  const [revokeReason, setRevokeReason] = useState('');
  const [revoking, setRevoking] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get('/api/pharmacy/purchases');
      setRows(r.data || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const submitRevoke = async () => {
    if (!revokeTarget) return;
    const reason = revokeReason.trim();
    if (reason.length < 2) {
      toast({ variant: 'destructive', title: 'Reason required', description: 'Type at least 2 characters.' });
      return;
    }
    setRevoking(true);
    try {
      const r = await axios.post(`/api/pharmacy/purchases/${revokeTarget.id}/revoke`, { reason });
      const partial = r.data.status === 'revoked_partial';
      toast({
        title: partial ? `Partially revoked ${r.data.purchase_number}` : `Revoked ${r.data.purchase_number}`,
        description: partial
          ? 'Some items were already sold — only the un-sold portion was reversed.'
          : 'All items reversed from inventory.',
      });
      setRevokeTarget(null); setRevokeReason('');
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Revoke failed', description: errMsg(e) });
    } finally { setRevoking(false); }
  };

  const statusColor = (s) => (
    s === 'confirmed' ? 'text-green-700'
    : s === 'revoked' ? 'text-red-700'
    : s === 'revoked_partial' ? 'text-orange-700'
    : 'text-gray-600'
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex justify-between items-center">
          <span>Purchases ({rows.length})</span>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-3 w-3" /></Button>
            <Button size="sm" onClick={() => navigate('/dashboard/pharmacy/purchases/new')}>
              <Plus className="h-3 w-3 mr-1" /> New Purchase
            </Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? <p className="text-center py-6 text-sm text-gray-500">Loading…</p>
          : rows.length === 0 ? <p className="text-center py-6 text-sm text-gray-500">No purchases yet</p>
          : (
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-gray-600">
                <th className="py-2 pr-4">Purchase #</th><th className="py-2 pr-4">Entry Date</th>
                <th className="py-2 pr-4">Supplier</th><th className="py-2 pr-4">Invoice #</th>
                <th className="py-2 pr-4">Items</th><th className="py-2 pr-4">Total</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 text-right">Actions</th>
              </tr></thead>
              <tbody>
                {rows.map(p => (
                  <tr key={p.id} className="border-b hover:bg-gray-50">
                    <td className="py-2 pr-4 font-mono text-xs">{p.purchase_number}</td>
                    <td className="py-2 pr-4 text-xs">{p.entry_date}</td>
                    <td className="py-2 pr-4">{p.supplier_name || '—'}</td>
                    <td className="py-2 pr-4 text-xs">{p.invoice_number || '—'}</td>
                    <td className="py-2 pr-4">{p.items?.length || 0}</td>
                    <td className="py-2 pr-4 font-medium">₹{p.grand_total?.toFixed(2)}</td>
                    <td className="py-2 pr-4">
                      <Badge variant="outline" className={`text-xs ${statusColor(p.status)}`}>{p.status}</Badge>
                    </td>
                    <td className="py-2 text-right">
                      <Button size="sm" variant="ghost" title="Print purchase"
                        onClick={() => printPdfFromUrl(`/api/pharmacy/purchases/${p.id}/pdf`, { include_header: false })}>
                        <Printer className="h-3 w-3" />
                      </Button>
                      {p.status === 'confirmed' && (
                        <Button size="sm" variant="ghost" title="Revoke purchase"
                          onClick={() => { setRevokeTarget(p); setRevokeReason(''); }}>
                          <Undo2 className="h-3 w-3 text-red-500" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </CardContent>

      <Dialog open={!!revokeTarget} onOpenChange={(o) => { if (!o) { setRevokeTarget(null); setRevokeReason(''); } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke {revokeTarget?.purchase_number}</DialogTitle>
            <DialogDescription>
              Reverses the un-sold portion of this purchase from inventory.
              Any quantity that has already been sold or dispensed stays out —
              the purchase will be marked <span className="font-medium">revoked_partial</span> in that case.
              This action is logged in the audit trail.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <label className="text-xs font-medium">Reason</label>
            <Textarea
              rows={3}
              placeholder="e.g. wrong supplier, batch returned, data entry error"
              value={revokeReason}
              onChange={(e) => setRevokeReason(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setRevokeTarget(null); setRevokeReason(''); }} disabled={revoking}>Cancel</Button>
            <Button onClick={submitRevoke} disabled={revoking}>
              {revoking ? 'Revoking…' : 'Revoke Purchase'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
