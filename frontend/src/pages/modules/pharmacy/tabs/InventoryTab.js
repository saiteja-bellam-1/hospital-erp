import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Textarea } from '../../../../components/ui/textarea';
import { Badge } from '../../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../../components/ui/select';
import { useToast } from '../../../../hooks/use-toast';
import { Search, RefreshCw, Sliders, ScrollText, Upload, Download, Loader2, X } from 'lucide-react';
import PharmacyImportDialog, { downloadPharmacyBlob } from '../../../../components/pharmacy/PharmacyImportDialog';
import PharmacyMedicinePicker from '../../../../components/pharmacy/PharmacyMedicinePicker';
import { errMsg } from '../../PharmacyModule';
import { usePharmacyStore } from '../../../../contexts/PharmacyStoreContext';
import { displayPharmacyNumericInput, formatMoney, pharmacyNoSpinInputClass } from '../../../../utils/pharmacyUnits';
import { usePharmacyPermissions } from '../../../../hooks/usePharmacyPermissions';

const LEDGER_TXN_TYPES = [
  { value: 'purchase', label: 'Purchase' },
  { value: 'purchase_edit_reverse', label: 'Purchase edit reverse' },
  { value: 'purchase_revoke', label: 'Purchase revoke' },
  { value: 'sale', label: 'Sale' },
  { value: 'return_in', label: 'Return in' },
  { value: 'rx_dispense', label: 'Rx dispense' },
  { value: 'rx_cancel', label: 'Rx cancel' },
  { value: 'adjustment', label: 'Adjustment' },
  { value: 'opening_stock', label: 'Opening stock' },
  { value: 'expiry_writeoff', label: 'Expiry write-off' },
  { value: 'transfer_in', label: 'Transfer in' },
  { value: 'transfer_out', label: 'Transfer out' },
  { value: 'transfer_revoke_in', label: 'Transfer revoke in' },
  { value: 'transfer_revoke_out', label: 'Transfer revoke out' },
];

export default function InventoryTab() {
  const { toast } = useToast();
  const { storeParams } = usePharmacyStore();
  const { hasPerm } = usePharmacyPermissions();
  const canAdjustStock = hasPerm('adjust_stock');
  const [view, setView] = useState('stock');     // stock | batches | ledger
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');

  const [ledgerMedicine, setLedgerMedicine] = useState(null);
  const [ledgerBatchId, setLedgerBatchId] = useState('');
  const [ledgerTxnType, setLedgerTxnType] = useState('');
  const [ledgerDateFrom, setLedgerDateFrom] = useState('');
  const [ledgerDateTo, setLedgerDateTo] = useState('');
  const [batchesForFilter, setBatchesForFilter] = useState([]);

  const [adjustOpen, setAdjustOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [adjustTarget, setAdjustTarget] = useState(null);
  const [adjustQty, setAdjustQty] = useState('');
  const [adjustReason, setAdjustReason] = useState('');

  useEffect(() => {
    if (view !== 'ledger' || !ledgerMedicine?.id) {
      setBatchesForFilter([]);
      return;
    }
    let cancelled = false;
    axios.get('/api/pharmacy/inventory/batches', {
      params: { medicine_id: ledgerMedicine.id, ...storeParams },
    }).then((r) => {
      if (!cancelled) setBatchesForFilter(r.data || []);
    }).catch(() => {
      if (!cancelled) setBatchesForFilter([]);
    });
    return () => { cancelled = true; };
  }, [view, ledgerMedicine, storeParams]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      let url; const params = {};
      if (view === 'stock') { url = '/api/pharmacy/inventory'; if (search) params.search = search; }
      else if (view === 'batches') { url = '/api/pharmacy/inventory/batches'; }
      else if (view === 'ledger') {
        url = '/api/pharmacy/inventory/ledger';
        params.limit = 200;
        if (ledgerMedicine?.id) params.medicine_id = ledgerMedicine.id;
        if (ledgerBatchId) params.batch_id = Number(ledgerBatchId);
        if (ledgerTxnType) params.txn_type = ledgerTxnType;
        if (ledgerDateFrom) params.date_from = ledgerDateFrom;
        if (ledgerDateTo) params.date_to = ledgerDateTo;
      }
      const r = await axios.get(url, { params: { ...params, ...storeParams } });
      setData(r.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Load failed', description: errMsg(e) });
    } finally { setLoading(false); }
  }, [view, search, toast, storeParams, ledgerMedicine, ledgerBatchId, ledgerTxnType, ledgerDateFrom, ledgerDateTo]);

  useEffect(() => { load(); }, [load]);

  const selectLedgerMedicine = (m) => {
    setLedgerMedicine(m || null);
    setLedgerBatchId('');
  };

  const openAdjust = (batch) => {
    if (!canAdjustStock) return;
    setAdjustTarget(batch); setAdjustQty(''); setAdjustReason(''); setAdjustOpen(true);
  };
  const saveAdjust = async () => {
    if (!canAdjustStock || !adjustTarget || !adjustQty || !adjustReason) return;
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

  const handleExport = async () => {
    setExporting(true);
    try {
      await downloadPharmacyBlob('/api/pharmacy/opening-stock/export/xlsx', 'opening_stock_export.xlsx', toast);
      toast({ title: 'Batches exported' });
    } catch {
      /* toast already shown */
    } finally {
      setExporting(false);
    }
  };

  const showStockImportExport = view === 'stock' || view === 'batches';

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
              {showStockImportExport && (
                <>
                  {canAdjustStock && (
                    <Button size="sm" variant="outline" onClick={() => setImportOpen(true)}>
                      <Upload className="h-3 w-3 mr-1" /> Import opening stock
                    </Button>
                  )}
                  <Button size="sm" variant="outline" onClick={handleExport} disabled={exporting}>
                    {exporting ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Download className="h-3 w-3 mr-1" />}
                    Export batches
                  </Button>
                </>
              )}
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {view === 'ledger' && (
            <div className="mb-4 flex flex-wrap items-end gap-3 rounded-md border bg-gray-50/80 p-3">
              <div className="min-w-[14rem] flex-1 space-y-1">
                <Label className="text-xs text-gray-600">Medicine</Label>
                <div className="flex items-center gap-1">
                  <PharmacyMedicinePicker
                    className="flex-1"
                    value={ledgerMedicine?.id || null}
                    medicine={ledgerMedicine}
                    onSelect={selectLedgerMedicine}
                    placeholder="Filter by medicine…"
                  />
                  {ledgerMedicine && (
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8 shrink-0"
                      title="Clear medicine"
                      onClick={() => selectLedgerMedicine(null)}
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </div>
              </div>
              <div className="w-44 space-y-1">
                <Label className="text-xs text-gray-600">Batch</Label>
                <Select
                  value={ledgerBatchId || 'any'}
                  onValueChange={(v) => setLedgerBatchId(v === 'any' ? '' : v)}
                  disabled={!ledgerMedicine}
                >
                  <SelectTrigger className="h-8">
                    <SelectValue placeholder={ledgerMedicine ? 'Any batch' : 'Pick medicine first'} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Any batch</SelectItem>
                    {batchesForFilter.map((b) => (
                      <SelectItem key={b.id} value={String(b.id)}>
                        {b.batch_number}
                        {b.quantity_in_stock != null ? ` (${b.quantity_in_stock})` : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="w-48 space-y-1">
                <Label className="text-xs text-gray-600">Entry type</Label>
                <Select
                  value={ledgerTxnType || 'any'}
                  onValueChange={(v) => setLedgerTxnType(v === 'any' ? '' : v)}
                >
                  <SelectTrigger className="h-8">
                    <SelectValue placeholder="Any type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="any">Any type</SelectItem>
                    {LEDGER_TXN_TYPES.map((t) => (
                      <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="w-36 space-y-1">
                <Label className="text-xs text-gray-600">From</Label>
                <Input
                  type="date"
                  className="h-8"
                  value={ledgerDateFrom}
                  onChange={(e) => setLedgerDateFrom(e.target.value)}
                />
              </div>
              <div className="w-36 space-y-1">
                <Label className="text-xs text-gray-600">To</Label>
                <Input
                  type="date"
                  className="h-8"
                  value={ledgerDateTo}
                  onChange={(e) => setLedgerDateTo(e.target.value)}
                />
              </div>
            </div>
          )}
          {loading ? <p className="text-center py-6 text-sm text-gray-500">Loading…</p>
            : data.length === 0 ? <p className="text-center py-6 text-sm text-gray-500">No records</p>
            : (
              <TableForView
                view={view}
                data={data}
                onAdjust={canAdjustStock ? openAdjust : null}
                canAdjust={canAdjustStock}
              />
            )}
        </CardContent>
      </Card>

      <PharmacyImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        onImported={load}
        title="Import Opening Stock"
        entityLabel="opening stock"
        importUrl="/api/pharmacy/opening-stock/import"
        templateUrl="/api/pharmacy/opening-stock/import/template"
        exportUrl="/api/pharmacy/opening-stock/export/xlsx"
        duplicateLabel="If a batch already exists:"
        helpText="Each row sets opening stock for a medicine batch. The medicine must already exist in the catalog. Quantity is treated as absolute when updating an existing batch. store_code is optional and defaults to the master store."
      />

      <Dialog open={adjustOpen} onOpenChange={setAdjustOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Adjust Stock — {adjustTarget?.batch_number}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div className="text-xs text-gray-500">
              {adjustTarget?.medicine_name} • current qty: {adjustTarget?.quantity_in_stock} tabs
              {(adjustTarget?.strip_conversion_factor || 1) > 1
                ? ` (${adjustTarget.strip_conversion_factor} tabs/strip)`
                : ''}
            </div>
            <div>
              <Label>Qty change (signed: +5 to add, −3 to remove)</Label>
              <Input className={pharmacyNoSpinInputClass} type="number" step="any"
                value={displayPharmacyNumericInput(adjustQty)}
                onChange={e => setAdjustQty(e.target.value)} />
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

function TableForView({ view, data, onAdjust, canAdjust }) {
  if (view === 'stock') {
    return (
      <table className="w-full text-sm">
        <thead><tr className="border-b text-left text-gray-600">
          <th className="py-2 pr-4">Code</th><th className="py-2 pr-4">Medicine</th>
          <th className="py-2 pr-4">Manufacturer</th>
          <th className="py-2 pr-4">Rack</th><th className="py-2 pr-4">UoM</th>
          <th className="py-2 pr-4">Stock (tabs)</th>
          <th className="py-2 pr-4">Free</th>
          <th className="py-2 pr-4">Tabs/Strip</th>
          <th className="py-2 pr-4">Supplier</th>
          <th className="py-2 pr-4">Batches</th>
        </tr></thead>
        <tbody>
          {data.map(r => {
            const scf = Math.max(1, parseInt(r.strip_conversion_factor, 10) || 1);
            const tabs = Number(r.total_stock) || 0;
            const free = Number(r.free_quantity) || 0;
            return (
              <tr key={r.medicine_id} className="border-b hover:bg-gray-50">
                <td className="py-2 pr-4 font-mono text-xs">{r.medicine_code}</td>
                <td className="py-2 pr-4">{r.name}</td>
                <td className="py-2 pr-4 text-xs">{r.manufacturer || '—'}</td>
                <td className="py-2 pr-4 text-xs">{r.rack_code || '—'}</td>
                <td className="py-2 pr-4 text-xs">{r.uom || '—'}</td>
                <td className="py-2 pr-4 tabular-nums">
                  {tabs}
                  {scf > 1 && tabs > 0 ? (
                    <div className="text-[10px] text-gray-400">
                      ≈ {(tabs / scf).toLocaleString(undefined, { maximumFractionDigits: 2 })} strips
                    </div>
                  ) : null}
                </td>
                <td className="py-2 pr-4 tabular-nums">{free || '—'}</td>
                <td className="py-2 pr-4 tabular-nums">{scf}</td>
                <td className="py-2 pr-4 text-xs">{r.supplier_name || '—'}</td>
                <td className="py-2 pr-4">{r.batch_count}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }
  if (view === 'batches') {
    return (
      <table className="w-full text-sm">
        <thead><tr className="border-b text-left text-gray-600">
          <th className="py-2 pr-4">Medicine</th>
          <th className="py-2 pr-4">Manufacturer</th>
          <th className="py-2 pr-4">Batch</th>
          <th className="py-2 pr-4">Qty (tabs)</th>
          <th className="py-2 pr-4">Free</th>
          <th className="py-2 pr-4">Tabs/Strip</th>
          <th className="py-2 pr-4">MRP</th><th className="py-2 pr-4">P-Rate</th>
          <th className="py-2 pr-4">Rate A</th>
          <th className="py-2 pr-4">Supplier</th>
          {canAdjust ? <th className="py-2 text-right">Actions</th> : null}
        </tr></thead>
        <tbody>
          {data.map(b => {
            const scf = Math.max(1, parseInt(b.strip_conversion_factor, 10) || 1);
            const tabs = Number(b.quantity_in_stock) || 0;
            const free = Number(b.free_quantity) || 0;
            return (
              <tr key={b.id} className="border-b hover:bg-gray-50">
                <td className="py-2 pr-4">{b.medicine_name}</td>
                <td className="py-2 pr-4 text-xs">{b.manufacturer || '—'}</td>
                <td className="py-2 pr-4 font-mono text-xs">{b.batch_number}</td>
                <td className="py-2 pr-4 tabular-nums">
                  {tabs}
                  {scf > 1 && tabs > 0 ? (
                    <div className="text-[10px] text-gray-400">
                      ≈ {(tabs / scf).toLocaleString(undefined, { maximumFractionDigits: 2 })} strips
                    </div>
                  ) : null}
                </td>
                <td className="py-2 pr-4 tabular-nums">{free || '—'}</td>
                <td className="py-2 pr-4 tabular-nums">{scf}</td>
                <td className="py-2 pr-4">₹{formatMoney(b.mrp)}</td>
                <td className="py-2 pr-4">₹{formatMoney(b.purchase_rate)}</td>
                <td className="py-2 pr-4">₹{formatMoney(b.rate_a)}</td>
                <td className="py-2 pr-4 text-xs">{b.supplier_name || '—'}</td>
                {canAdjust ? (
                  <td className="py-2 text-right">
                    <Button size="sm" variant="outline" onClick={() => onAdjust(b)}>Adjust</Button>
                  </td>
                ) : null}
              </tr>
            );
          })}
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
