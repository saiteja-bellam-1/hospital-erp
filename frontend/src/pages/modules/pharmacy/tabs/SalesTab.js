import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Badge } from '../../../../components/ui/badge';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Textarea } from '../../../../components/ui/textarea';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../../components/ui/dialog';
import { useToast } from '../../../../hooks/use-toast';
import { Plus, RefreshCw, Ban, Printer, Pencil, Upload, RotateCcw } from 'lucide-react';
import { errMsg } from '../../PharmacyModule';
import PdfPreviewDialog from '../../../../components/PdfPreviewDialog';
import PharmacyImportDialog from '../../../../components/pharmacy/PharmacyImportDialog';
import { usePharmacyStore } from '../../../../contexts/PharmacyStoreContext';
import { usePharmacyPermissions } from '../../../../hooks/usePharmacyPermissions';

export default function SalesTab() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const { storeParams } = usePharmacyStore();
  const { hasPerm } = usePharmacyPermissions();
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [voidOpen, setVoidOpen] = useState(false);
  const [voidTarget, setVoidTarget] = useState(null);
  const [voidReason, setVoidReason] = useState('');
  const [previewSaleId, setPreviewSaleId] = useState(null);
  const [importOpen, setImportOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { ...storeParams };
      if (search) params.search = search;
      const r = await axios.get('/api/pharmacy/sales', { params });
      setRows(r.data || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [search, storeParams]);
  useEffect(() => { load(); }, [load]);

  const submitVoid = async () => {
    try {
      await axios.post(`/api/pharmacy/sales/${voidTarget.id}/void`, { reason: voidReason });
      toast({ title: 'Sale voided' });
      setVoidOpen(false); load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Void failed', description: errMsg(e) });
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap justify-between items-center gap-2">
          <span>Sales ({rows.length})</span>
          <div className="flex gap-2 items-center">
            <Input className="h-8 w-56" placeholder="Search sale # / patient / doctor…"
              value={search} onChange={e => setSearch(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); load(); } }}
              data-nav-skip />
            <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-3 w-3" /></Button>
            {hasPerm('create_sale') && (
              <Button size="sm" variant="outline" onClick={() => setImportOpen(true)}>
                <Upload className="h-3 w-3 mr-1" /> Import
              </Button>
            )}
            <Button size="sm" onClick={() => navigate('/dashboard/pharmacy/sales-counter')}>
              <Plus className="h-3 w-3 mr-1" /> Sales Counter
            </Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? <p className="text-center py-6 text-sm text-gray-500">Loading…</p>
          : rows.length === 0 ? <p className="text-center py-6 text-sm text-gray-500">No sales yet</p>
          : (
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-gray-600">
                <th className="py-2 pr-4">Sale #</th><th className="py-2 pr-4">Date</th>
                <th className="py-2 pr-4">Patient</th><th className="py-2 pr-4">Doctor</th>
                <th className="py-2 pr-4">Payment</th><th className="py-2 pr-4">Items</th>
                <th className="py-2 pr-4">Total</th><th className="py-2 pr-4">Status</th>
                <th className="py-2 text-right">Actions</th>
              </tr></thead>
              <tbody>
                {rows.map(s => (
                  <tr key={s.id} className="border-b hover:bg-gray-50">
                    <td className="py-2 pr-4 font-mono text-xs">{s.sale_number}</td>
                    <td className="py-2 pr-4 text-xs">{new Date(s.sale_date).toLocaleString()}</td>
                    <td className="py-2 pr-4">
                      <div>{s.patient_name || '—'}</div>
                      {s.patient_phone && <div className="text-xs text-gray-500">{s.patient_phone}</div>}
                    </td>
                    <td className="py-2 pr-4 text-xs">{s.doctor_name || '—'}</td>
                    <td className="py-2 pr-4 text-xs">{s.payment_type}</td>
                    <td className="py-2 pr-4">{s.items?.length || 0}</td>
                    <td className="py-2 pr-4 font-medium">₹{s.grand_total?.toFixed(2)}</td>
                    <td className="py-2 pr-4">
                      <Badge variant="outline" className={`text-xs ${s.status==='voided' ? 'text-red-600' : 'text-green-700'}`}>
                        {s.status}
                      </Badge>
                    </td>
                    <td className="py-2 text-right space-x-1">
                      <Button size="sm" variant="ghost" title="Preview & print invoice"
                        onClick={() => setPreviewSaleId(s.id)}>
                        <Printer className="h-3 w-3" />
                      </Button>
                      {s.status === 'completed' && hasPerm('create_sale_return') && (
                        <Button size="sm" variant="ghost" title="Sales return"
                          onClick={() => navigate(`/dashboard/pharmacy/sale-returns/new?saleId=${s.id}`)}>
                          <RotateCcw className="h-3 w-3 text-amber-600" />
                        </Button>
                      )}
                      {s.status === 'completed' && hasPerm('edit_sale') && (
                        <Button size="sm" variant="ghost" title="Edit sale"
                          onClick={() => navigate(`/dashboard/pharmacy/sales-counter/${s.id}/edit`)}>
                          <Pencil className="h-3 w-3 text-blue-600" />
                        </Button>
                      )}
                      {s.status === 'completed' && (
                        <Button size="sm" variant="ghost" onClick={() => { setVoidTarget(s); setVoidReason(''); setVoidOpen(true); }}>
                          <Ban className="h-3 w-3 text-red-500" />
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </CardContent>

      <Dialog open={voidOpen} onOpenChange={setVoidOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Void Sale {voidTarget?.sale_number}</DialogTitle></DialogHeader>
          <div>
            <Label>Reason</Label>
            <Textarea value={voidReason} onChange={e => setVoidReason(e.target.value)} placeholder="Customer cancelled, wrong meds, etc." />
            <p className="text-xs text-gray-500 mt-2">
              {voidTarget?.stock_affected === false
                ? 'This sale was imported without stock changes — voiding will not adjust inventory.'
                : 'Voiding will restore stock to each batch and reverse the sale.'}
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setVoidOpen(false)}>Cancel</Button>
            <Button onClick={submitVoid} disabled={!voidReason} className="bg-red-600 hover:bg-red-700">Void</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <PdfPreviewDialog
        open={!!previewSaleId}
        onClose={() => setPreviewSaleId(null)}
        title="Sale Invoice Preview"
        path={previewSaleId ? `/api/pharmacy/sales/${previewSaleId}/invoice/pdf` : null}
      />

      <PharmacyImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        onImported={load}
        title="Import previous sales"
        entityLabel="sales"
        importUrl="/api/pharmacy/sales/import"
        templateUrl="/api/pharmacy/sales/import/template"
        showDuplicateSelect={false}
        showAffectStock
        defaultAffectStock={false}
        helpText={(
          <>
            Download the Excel template, fill one row per line item (same <code className="text-[11px]">sale_number</code> groups
            lines into one bill), then preview and confirm. Choose <strong>Record only</strong> when migrating history
            from another system so inventory is not changed, or <strong>Deduct stock</strong> when batches still have
            stock to remove. Medicines must already exist in the catalog.
          </>
        )}
      />
    </Card>
  );
}
