import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Badge } from '../../../../components/ui/badge';
import { useToast } from '../../../../hooks/use-toast';
import { Plus, RefreshCw, ArrowLeftRight, Printer, Undo2 } from 'lucide-react';
import { errMsg } from '../../PharmacyModule';
import { usePharmacyStore } from '../../../../contexts/PharmacyStoreContext';
import { printPdfFromUrl } from '../../../../utils/printPdf';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../../../../components/ui/dialog';
import { Textarea } from '../../../../components/ui/textarea';
import { Label } from '../../../../components/ui/label';

export default function TransfersTab() {
  const { toast } = useToast();
  const { storeParams } = usePharmacyStore();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState(null);
  const [revokeReason, setRevokeReason] = useState('');
  const [revoking, setRevoking] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get('/api/pharmacy/transfers', { params: storeParams });
      setRows(r.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Load failed', description: errMsg(e) });
    } finally {
      setLoading(false);
    }
  }, [storeParams, toast]);

  useEffect(() => { load(); }, [load]);

  const submitRevoke = async () => {
    if (!revokeTarget) return;
    const reason = revokeReason.trim();
    if (reason.length < 2) {
      toast({ variant: 'destructive', title: 'Reason required' });
      return;
    }
    setRevoking(true);
    try {
      await axios.post(`/api/pharmacy/transfers/${revokeTarget.id}/revoke`, { reason });
      toast({ title: 'Transfer revoked' });
      setRevokeTarget(null);
      setRevokeReason('');
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Revoke failed', description: errMsg(e) });
    } finally {
      setRevoking(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          <ArrowLeftRight className="h-5 w-5" /> Stock Transfers
        </CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
          <Button size="sm" asChild>
            <Link to="/dashboard/pharmacy/transfers/new">
              <Plus className="h-4 w-4 mr-1" /> New Transfer
            </Link>
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-gray-600">
                <th className="py-2 pr-4">Number</th>
                <th className="py-2 pr-4">Date</th>
                <th className="py-2 pr-4">From</th>
                <th className="py-2 pr-4">To</th>
                <th className="py-2 pr-4">Items</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-b">
                  <td className="py-2 pr-4 font-mono">{row.transfer_number}</td>
                  <td className="py-2 pr-4">{row.entry_date}</td>
                  <td className="py-2 pr-4">{row.from_store_name}</td>
                  <td className="py-2 pr-4">{row.to_store_name}</td>
                  <td className="py-2 pr-4">{row.item_count}</td>
                  <td className="py-2 pr-4">
                    <Badge variant={row.status === 'confirmed' ? 'default' : 'secondary'}>{row.status}</Badge>
                  </td>
                  <td className="py-2">
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => printPdfFromUrl(`/api/pharmacy/transfers/${row.id}/pdf`)}>
                        <Printer className="h-4 w-4" />
                      </Button>
                      {row.status === 'confirmed' && (
                        <Button size="sm" variant="ghost" onClick={() => { setRevokeTarget(row); setRevokeReason(''); }}>
                          <Undo2 className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && !loading && (
                <tr><td colSpan={7} className="py-8 text-center text-gray-500">No transfers yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </CardContent>
      <Dialog open={!!revokeTarget} onOpenChange={(v) => !v && setRevokeTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke transfer {revokeTarget?.transfer_number}</DialogTitle>
          </DialogHeader>
          <div className="py-2">
            <Label>Reason</Label>
            <Textarea value={revokeReason} onChange={(e) => setRevokeReason(e.target.value)} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRevokeTarget(null)}>Cancel</Button>
            <Button onClick={submitRevoke} disabled={revoking}>Revoke</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}
