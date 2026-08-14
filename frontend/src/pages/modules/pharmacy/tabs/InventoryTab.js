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
import { Search, RefreshCw, Sliders, ScrollText, Upload, Download, Loader2, X, Trash2 } from 'lucide-react';
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

  const [correctOpen, setCorrectOpen] = useState(false);
  const [correctTarget, setCorrectTarget] = useState(null);
  const [correctScf, setCorrectScf] = useState('1');
  const [correctQty, setCorrectQty] = useState('');
  const [correctReason, setCorrectReason] = useState('');
  const [correctUpdateMedicine, setCorrectUpdateMedicine] = useState(true);
  const [correctUpdatePurchase, setCorrectUpdatePurchase] = useState(true);
  const [correctSaving, setCorrectSaving] = useState(false);

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

  const openCorrect = (batch) => {
    if (!canAdjustStock) return;
    setCorrectTarget(batch);
    setCorrectScf(String(Math.max(1, parseInt(batch.strip_conversion_factor, 10) || 1)));
    setCorrectQty(String(batch.quantity_in_stock ?? ''));
    setCorrectReason('');
    setCorrectUpdateMedicine(true);
    setCorrectUpdatePurchase(true);
    setCorrectOpen(true);
  };
  const saveCorrect = async () => {
    if (!canAdjustStock || !correctTarget || !correctReason.trim()) return;
    const scf = Math.max(1, parseInt(correctScf, 10) || 1);
    const qty = parseFloat(correctQty);
    if (Number.isNaN(qty) || qty < 0) {
      toast({ variant: 'destructive', title: 'Enter a valid stock quantity (tabs)' });
      return;
    }
    if (!window.confirm(
      'Force-correct Tabs/strip and stock on this batch?\n\n'
      + 'Past sales are left as-is. Future strip sales will use the new Tabs/strip.\n'
      + 'Stock is set to the absolute quantity you enter (not a delta).',
    )) return;
    setCorrectSaving(true);
    try {
      await axios.post('/api/pharmacy/inventory/correct-strip-stock', {
        batch_id: correctTarget.id,
        strip_conversion_factor: scf,
        quantity_in_stock: qty,
        reason: correctReason.trim(),
        update_medicine_scf: correctUpdateMedicine,
        update_purchase_lines: correctUpdatePurchase,
      });
      toast({ title: 'Strip factor and stock corrected' });
      setCorrectOpen(false);
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Correction failed', description: errMsg(e) });
    } finally {
      setCorrectSaving(false);
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

  const deleteLegacyLedger = async (row) => {
    if (!canAdjustStock || !row?.can_delete) return;
    const label = `${row.txn_type} ${row.qty_delta >= 0 ? '+' : ''}${row.qty_delta}`;
    if (!window.confirm(
      `Delete ledger entry ${label}?\n\n`
      + 'This only removes the ledger row. Current stock is not changed.\n'
      + 'Use this to clean up leftover rows from the old purchase-edit reverse path.',
    )) return;
    try {
      await axios.delete(`/api/pharmacy/inventory/ledger/${row.id}`);
      toast({ title: 'Ledger entry deleted', description: 'Stock unchanged' });
      load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Delete failed', description: errMsg(e) });
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
            <div className="mb-4 space-y-2">
            <div className="flex flex-wrap items-end gap-3 rounded-md border bg-gray-50/80 p-3">
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
            {canAdjustStock ? (
              <p className="text-xs text-gray-500">
                Delete is available on leftover <span className="font-mono">purchase_edit_reverse</span> rows
                and duplicate purchase credits from the old purchase-edit path. Stock on hand is not changed.
              </p>
            ) : null}
            </div>
          )}
          {loading ? <p className="text-center py-6 text-sm text-gray-500">Loading…</p>
            : data.length === 0 ? <p className="text-center py-6 text-sm text-gray-500">No records</p>
            : (
              <TableForView
                view={view}
                data={data}
                onAdjust={canAdjustStock ? openAdjust : null}
                onCorrect={canAdjustStock ? openCorrect : null}
                canAdjust={canAdjustStock}
                onDeleteLedger={canAdjustStock ? deleteLegacyLedger : null}
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

      <Dialog open={correctOpen} onOpenChange={setCorrectOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Correct Tabs/strip &amp; stock — {correctTarget?.batch_number}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2.5 py-2">
              Leaves past sales as-is. Sets Tabs/strip and absolute stock on this batch with no sold-qty checks.
              Use when a wrong strip factor inflated stock and you do not want to void bills.
            </p>
            <div className="text-xs text-gray-500">
              {correctTarget?.medicine_name}
              {' • '}current: {correctTarget?.quantity_in_stock} tabs
              {' @ '}{correctTarget?.strip_conversion_factor || 1} tabs/strip
            </div>
            <div>
              <Label>Correct Tabs / strip</Label>
              <Input
                className={pharmacyNoSpinInputClass}
                type="number"
                min={1}
                step={1}
                value={correctScf}
                onChange={(e) => setCorrectScf(e.target.value)}
              />
            </div>
            <div>
              <Label>Correct stock (tabs, absolute)</Label>
              <Input
                className={pharmacyNoSpinInputClass}
                type="number"
                min={0}
                step="any"
                value={displayPharmacyNumericInput(correctQty)}
                onChange={(e) => setCorrectQty(e.target.value)}
              />
              {(() => {
                const scf = Math.max(1, parseInt(correctScf, 10) || 1);
                const qty = parseFloat(correctQty);
                if (Number.isNaN(qty) || qty < 0 || scf <= 1) return null;
                return (
                  <p className="text-[10px] text-gray-500 mt-0.5">
                    ≈ {(qty / scf).toLocaleString(undefined, { maximumFractionDigits: 2 })} strips
                  </p>
                );
              })()}
            </div>
            <div>
              <Label>Reason</Label>
              <Textarea
                value={correctReason}
                onChange={(e) => setCorrectReason(e.target.value)}
                placeholder="Wrong Tabs/strip on purchase; correcting batch + stock"
              />
            </div>
            <label className="flex items-start gap-2 text-xs text-gray-700">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={correctUpdateMedicine}
                onChange={(e) => setCorrectUpdateMedicine(e.target.checked)}
              />
              <span>Also update medicine master Tabs/strip</span>
            </label>
            <label className="flex items-start gap-2 text-xs text-gray-700">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={correctUpdatePurchase}
                onChange={(e) => setCorrectUpdatePurchase(e.target.checked)}
              />
              <span>Also update linked purchase line Tabs/strip (does not rewrite purchase qty or sales)</span>
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCorrectOpen(false)} disabled={correctSaving}>Cancel</Button>
            <Button
              onClick={saveCorrect}
              disabled={correctSaving || !correctReason.trim() || correctQty === ''}
            >
              {correctSaving ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : null}
              Force correct
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function TableForView({ view, data, onAdjust, onCorrect, canAdjust, onDeleteLedger }) {
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
                  <td className="py-2 text-right whitespace-nowrap space-x-1">
                    <Button size="sm" variant="outline" onClick={() => onAdjust(b)}>Adjust</Button>
                    {onCorrect ? (
                      <Button size="sm" variant="outline" onClick={() => onCorrect(b)}>Correct strip</Button>
                    ) : null}
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
  const showLedgerActions = Boolean(onDeleteLedger);
  return (
    <table className="w-full text-sm">
      <thead><tr className="border-b text-left text-gray-600">
        <th className="py-2 pr-4">Time</th><th className="py-2 pr-4">Type</th>
        <th className="py-2 pr-4">Medicine</th><th className="py-2 pr-4">Batch</th>
        <th className="py-2 pr-4">Qty Δ</th><th className="py-2 pr-4">By</th>
        <th className="py-2 pr-4">Reference</th><th className="py-2 pr-4">Notes</th>
        {showLedgerActions ? <th className="py-2 text-right">Actions</th> : null}
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
            {showLedgerActions ? (
              <td className="py-2 text-right">
                {l.can_delete ? (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 w-8 p-0"
                    title="Delete legacy ledger row (stock unchanged)"
                    onClick={() => onDeleteLedger(l)}
                  >
                    <Trash2 className="h-3.5 w-3.5 text-red-500" />
                  </Button>
                ) : (
                  <span className="text-xs text-gray-300">—</span>
                )}
              </td>
            ) : null}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
