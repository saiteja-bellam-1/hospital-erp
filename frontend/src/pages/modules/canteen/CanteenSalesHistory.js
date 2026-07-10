import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Card, CardContent } from '../../../components/ui/card';
import { Input } from '../../../components/ui/input';
import { useToast } from '../../../hooks/use-toast';
import { RefreshCw, Printer } from 'lucide-react';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';
import { localDateString } from '../../../utils/localDate';

function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join('; ');
  return e?.message || 'Request failed';
}

export default function CanteenSalesHistory({ canVoid = false }) {
  const { toast } = useToast();
  const [sales, setSales] = useState([]);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState('completed');
  const [fromDate, setFromDate] = useState(localDateString(new Date()));
  const [previewId, setPreviewId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (statusFilter !== 'all') params.status = statusFilter;
      if (fromDate) params.from_date = fromDate;
      const res = await axios.get('/api/canteen/sales', { params });
      setSales(res.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Failed to load sales', description: errMsg(e) });
    } finally {
      setLoading(false);
    }
  }, [statusFilter, fromDate, toast]);

  useEffect(() => { load(); }, [load]);

  const voidSale = async (sale) => {
    const reason = window.prompt('Void reason (optional):', '') ?? null;
    if (reason === null) return;
    try {
      await axios.post(`/api/canteen/sales/${sale.id}/void`, { reason: reason || null });
      toast({ title: 'Sale voided', description: sale.sale_number });
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Void failed', description: errMsg(e) });
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">Sales History</h2>
          <p className="text-xs text-gray-500">Walk-in canteen POS receipts.</p>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <Input type="date" className="h-8 w-36 text-xs" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
          <select className="h-8 text-xs border rounded-md px-2" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="completed">Completed</option>
            <option value="voided">Voided</option>
            <option value="all">All</option>
          </select>
          <Button size="sm" variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
        </div>
      </div>

      <div className="space-y-2">
        {sales.length === 0 ? (
          <Card><CardContent className="py-10 text-center text-sm text-gray-500">No sales in this view.</CardContent></Card>
        ) : sales.map((s) => (
          <Card key={s.id}>
            <CardContent className="p-3 text-sm space-y-1">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <div className="font-medium">{s.sale_number}</div>
                  <div className="text-xs text-gray-500">
                    {s.sale_date ? new Date(s.sale_date).toLocaleString() : ''}
                    {s.customer_name ? ` · ${s.customer_name}` : ' · Walk-in'}
                    {` · ${(s.payment_type || '').toUpperCase()}`}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Badge className={s.status === 'voided' ? 'bg-red-100 text-red-800' : 'bg-green-100 text-green-800'}>
                    {s.status}
                  </Badge>
                  <span className="font-semibold">₹{parseFloat(s.grand_total || 0).toFixed(2)}</span>
                </div>
              </div>
              <ul className="text-xs text-gray-700">
                {(s.items || []).map((li) => (
                  <li key={li.id}>{li.item_name} × {li.quantity}</li>
                ))}
              </ul>
              <div className="flex gap-2 pt-1">
                <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setPreviewId(s.id)}>
                  <Printer className="h-3.5 w-3.5 mr-1" /> Receipt
                </Button>
                {canVoid && s.status === 'completed' && (
                  <Button size="sm" variant="ghost" className="h-7 text-xs text-red-600" onClick={() => voidSale(s)}>
                    Void
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <PdfPreviewDialog
        open={!!previewId}
        onClose={() => setPreviewId(null)}
        title="Canteen sale receipt"
        path={previewId ? `/api/canteen/sales/${previewId}/receipt/pdf` : null}
      />
    </div>
  );
}
