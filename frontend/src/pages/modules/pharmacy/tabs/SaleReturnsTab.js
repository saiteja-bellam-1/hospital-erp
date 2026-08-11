import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Badge } from '../../../../components/ui/badge';
import { Input } from '../../../../components/ui/input';
import { useToast } from '../../../../hooks/use-toast';
import { errMsg } from '../../PharmacyModule';
import { Plus, RefreshCw, Printer, Eye } from 'lucide-react';
import PdfPreviewDialog from '../../../../components/PdfPreviewDialog';
import { usePharmacyStore } from '../../../../contexts/PharmacyStoreContext';
import { usePharmacyPermissions } from '../../../../hooks/usePharmacyPermissions';

export default function SaleReturnsTab() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const { storeParams } = usePharmacyStore();
  const { hasPerm } = usePharmacyPermissions();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [previewId, setPreviewId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { ...storeParams };
      if (search) params.search = search;
      const r = await axios.get('/api/pharmacy/sale-returns', { params });
      setRows(r.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Failed to load', description: errMsg(e) });
    } finally {
      setLoading(false);
    }
  }, [search, storeParams, toast]);

  useEffect(() => { load(); }, [load]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap justify-between items-center gap-2">
          <span>Sales Returns ({rows.length})</span>
          <div className="flex gap-2 items-center">
            <Input className="h-8 w-48" placeholder="Search…" value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); load(); } }} />
            <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-3 w-3" /></Button>
            {hasPerm('create_sale_return') && (
              <Button size="sm" onClick={() => navigate('/dashboard/pharmacy/sale-returns/new')}>
                <Plus className="h-3 w-3 mr-1" /> New Return
              </Button>
            )}
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? <p className="text-center py-6 text-sm text-gray-500">Loading…</p>
          : rows.length === 0 ? <p className="text-center py-6 text-sm text-gray-500">No sales returns yet</p>
          : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-600">
                  <th className="py-2 pr-4">Return #</th>
                  <th className="py-2 pr-4">Date</th>
                  <th className="py-2 pr-4">Patient</th>
                  <th className="py-2 pr-4">Sale</th>
                  <th className="py-2 pr-4">Total</th>
                  <th className="py-2 pr-4">Settlement</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b hover:bg-gray-50">
                    <td className="py-2 pr-4 font-mono text-xs">{r.return_number}</td>
                    <td className="py-2 pr-4 text-xs">{r.return_date}</td>
                    <td className="py-2 pr-4">{r.patient_name || '—'}</td>
                    <td className="py-2 pr-4 text-xs">{r.sale_number || '—'}</td>
                    <td className="py-2 pr-4">₹{(r.grand_total || 0).toFixed(2)}</td>
                    <td className="py-2 pr-4 text-xs">{r.settlement_method || '—'}</td>
                    <td className="py-2 pr-4">
                      <Badge variant="outline" className="text-xs">{r.status}</Badge>
                    </td>
                    <td className="py-2 text-right space-x-1">
                      <Button size="sm" variant="ghost" onClick={() => navigate(`/dashboard/pharmacy/sale-returns/${r.id}`)}>
                        <Eye className="h-3 w-3" />
                      </Button>
                      {r.status === 'confirmed' && (
                        <Button size="sm" variant="ghost" onClick={() => setPreviewId(r.id)}>
                          <Printer className="h-3 w-3" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </CardContent>
      <PdfPreviewDialog
        open={!!previewId}
        onClose={() => setPreviewId(null)}
        title="Credit Note Preview"
        path={previewId ? `/api/pharmacy/sale-returns/${previewId}/credit-note/pdf` : null}
      />
    </Card>
  );
}
