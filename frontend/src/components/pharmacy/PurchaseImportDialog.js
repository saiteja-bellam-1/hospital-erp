import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { useToast } from '../../hooks/use-toast';
import { downloadPharmacyBlob } from './PharmacyImportDialog';
import {
  Upload, FileSpreadsheet, Loader2, CheckCircle2,
  AlertTriangle, RefreshCw, X, ArrowRight, Save, Trash2,
} from 'lucide-react';

const PREVIEW_LIMIT = 100;

const STATUS_STYLES = {
  new: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  update: 'bg-blue-50 text-blue-700 border-blue-200',
  skip: 'bg-slate-100 text-slate-500 border-slate-200',
  error: 'bg-red-50 text-red-700 border-red-200',
};

const STATUS_LABEL = {
  new: 'New',
  update: 'Update',
  skip: 'Skipped',
  error: 'Error',
};

const STEPS = [
  { id: 'details', label: '1. Details' },
  { id: 'rows', label: '2. Rows' },
  { id: 'mapping', label: '3. Mapping' },
  { id: 'import', label: '4. Import' },
];

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

export default function PurchaseImportDialog({ open, onOpenChange, onImported }) {
  const { toast } = useToast();
  const fileInputRef = useRef(null);

  const [step, setStep] = useState('details');
  const [file, setFile] = useState(null);
  const [suppliers, setSuppliers] = useState([]);
  const [supplierId, setSupplierId] = useState('');
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [entryDate, setEntryDate] = useState(todayISO());
  const [billDate, setBillDate] = useState(todayISO());
  const [rowStart, setRowStart] = useState('');
  const [rowEnd, setRowEnd] = useState('');
  const [onDuplicate, setOnDuplicate] = useState('skip');

  const [inspecting, setInspecting] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [savingMapping, setSavingMapping] = useState(false);
  const [inspect, setInspect] = useState(null);
  const [mapping, setMapping] = useState({});
  const [savedMappings, setSavedMappings] = useState([]);
  const [selectedPresetId, setSelectedPresetId] = useState('');
  const [summary, setSummary] = useState(null);
  const [done, setDone] = useState(null);
  const [mappingName, setMappingName] = useState('');
  const [mappingSaved, setMappingSaved] = useState(false);

  const reset = () => {
    setStep('details');
    setFile(null);
    setSupplierId('');
    setInvoiceNumber('');
    setEntryDate(todayISO());
    setBillDate(todayISO());
    setRowStart('');
    setRowEnd('');
    setOnDuplicate('skip');
    setInspect(null);
    setMapping({});
    setSelectedPresetId('');
    setSummary(null);
    setDone(null);
    setMappingName('');
    setMappingSaved(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleClose = (v) => {
    if (importing || analyzing || inspecting || savingMapping) return;
    if (!v) reset();
    onOpenChange(v);
  };

  const feedback = (msg, type) => {
    if (type === 'error') toast({ variant: 'destructive', title: msg });
    else toast({ title: msg });
  };

  const loadSuppliers = async () => {
    try {
      const r = await axios.get('/api/pharmacy/suppliers', { params: { active_only: true } });
      setSuppliers(r.data || []);
    } catch {
      setSuppliers([]);
    }
  };

  const loadSavedMappings = async () => {
    try {
      const r = await axios.get('/api/pharmacy/purchases/import/mappings');
      setSavedMappings(r.data || []);
    } catch {
      setSavedMappings([]);
    }
  };

  useEffect(() => {
    if (!open) return;
    loadSuppliers();
    loadSavedMappings();
  }, [open]);

  const inspectFile = async (f) => {
    setInspecting(true);
    setInspect(null);
    setMapping({});
    setSummary(null);
    setDone(null);
    setMappingSaved(false);
    try {
      const fd = new FormData();
      fd.append('file', f);
      const res = await axios.post('/api/pharmacy/purchases/import/inspect', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setInspect(res.data);
      setMapping(res.data.suggested_mapping || {});
      if (res.data.min_row) setRowStart(String(res.data.min_row));
      if (res.data.max_row) setRowEnd(String(res.data.max_row));
    } catch (err) {
      const detail = err.response?.data?.detail;
      feedback(typeof detail === 'string' ? detail : 'Could not read file columns', 'error');
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } finally {
      setInspecting(false);
    }
  };

  const onFileChange = (e) => {
    const f = e.target.files?.[0] || null;
    setFile(f);
    if (f) inspectFile(f);
    else {
      setInspect(null);
      setMapping({});
      setSummary(null);
      setDone(null);
      setRowStart('');
      setRowEnd('');
    }
  };

  const setColumnTarget = (header, target) => {
    setMapping((prev) => {
      const next = { ...prev };
      if (target && target !== 'ignore') {
        Object.keys(next).forEach((h) => {
          if (h !== header && next[h] === target) next[h] = 'ignore';
        });
      }
      next[header] = target;
      return next;
    });
    setSummary(null);
    setDone(null);
    setMappingSaved(false);
  };

  const mappedTargets = useMemo(
    () => new Set(Object.values(mapping).filter((v) => v && v !== 'ignore')),
    [mapping],
  );

  const applyPreset = (id) => {
    setSelectedPresetId(id);
    const preset = savedMappings.find((m) => String(m.id) === String(id));
    if (!preset) return;
    setMapping(preset.column_mapping || {});
    if (preset.default_row_start != null) setRowStart(String(preset.default_row_start));
    if (preset.default_row_end != null) setRowEnd(String(preset.default_row_end));
    setMappingName(preset.name || '');
    setSummary(null);
    setDone(null);
    setMappingSaved(false);
    feedback(`Loaded mapping “${preset.name}”`);
  };

  const deletePreset = async (id) => {
    try {
      await axios.delete(`/api/pharmacy/purchases/import/mappings/${id}`);
      setSavedMappings((prev) => prev.filter((m) => m.id !== id));
      if (String(selectedPresetId) === String(id)) setSelectedPresetId('');
      feedback('Saved mapping deleted');
    } catch (err) {
      const detail = err.response?.data?.detail;
      feedback(typeof detail === 'string' ? detail : 'Failed to delete mapping', 'error');
    }
  };

  const appendImportFields = (fd) => {
    fd.append('file', file);
    fd.append('on_duplicate', onDuplicate);
    fd.append('column_mapping', JSON.stringify(mapping));
    if (supplierId) fd.append('supplier_id', String(supplierId));
    if (invoiceNumber.trim()) fd.append('invoice_number', invoiceNumber.trim());
    if (entryDate) fd.append('entry_date', entryDate);
    if (billDate) fd.append('bill_date', billDate);
    if (rowStart !== '' && rowStart != null) fd.append('row_start', String(Number(rowStart)));
    if (rowEnd !== '' && rowEnd != null) fd.append('row_end', String(Number(rowEnd)));
  };

  const runImport = async (dryRun) => {
    if (!file) return;
    const setBusy = dryRun ? setAnalyzing : setImporting;
    setBusy(true);
    try {
      const fd = new FormData();
      appendImportFields(fd);
      fd.append('dry_run', dryRun ? 'true' : 'false');
      const res = await axios.post('/api/pharmacy/purchases/import', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      if (dryRun) {
        setSummary(res.data);
        setStep('import');
      } else {
        setDone(res.data);
        setSummary(res.data);
        onImported?.();
        feedback(
          `Imported: ${res.data.created} new, ${res.data.updated} updated, ${res.data.skipped} skipped`,
        );
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      feedback(typeof detail === 'string' ? detail : 'Import failed', 'error');
    } finally {
      setBusy(false);
    }
  };

  const saveMappingPreset = async () => {
    const name = mappingName.trim();
    if (!name) {
      feedback('Enter a name for this mapping', 'error');
      return;
    }
    if (mappedTargets.size === 0) {
      feedback('Map at least one column before saving', 'error');
      return;
    }
    setSavingMapping(true);
    try {
      const payload = {
        name,
        column_mapping: mapping,
        format_hint: inspect?.format_hint || null,
        default_row_start: rowStart !== '' ? Number(rowStart) : null,
        default_row_end: rowEnd !== '' ? Number(rowEnd) : null,
      };
      const res = await axios.post('/api/pharmacy/purchases/import/mappings', payload);
      setMappingSaved(true);
      await loadSavedMappings();
      setSelectedPresetId(String(res.data.id));
      feedback(`Mapping “${name}” saved`);
    } catch (err) {
      const detail = err.response?.data?.detail;
      feedback(typeof detail === 'string' ? detail : 'Failed to save mapping', 'error');
    } finally {
      setSavingMapping(false);
    }
  };

  const detailsReady = !!file && !!inspect && !!supplierId && !!entryDate;
  const rowsReady = detailsReady
    && rowStart !== '' && rowEnd !== ''
    && Number(rowStart) > 0
    && Number(rowEnd) >= Number(rowStart);
  const mappingReady = rowsReady && mappedTargets.size > 0;

  const targets = inspect?.targets || [];
  const targetsByGroup = useMemo(() => {
    const groups = [];
    let current = null;
    targets.forEach((t) => {
      const g = t.group || '';
      if (!current || current.label !== g) {
        current = { label: g, items: [] };
        groups.push(current);
      }
      current.items.push(t);
    });
    return groups;
  }, [targets]);

  const result = done || summary;
  const previewRows = result?.preview || [];
  const visiblePreview = previewRows.slice(0, PREVIEW_LIMIT);
  const hiddenCount = Math.max(0, previewRows.length - PREVIEW_LIMIT);
  const headers = inspect?.headers || [];
  const selectedSupplier = suppliers.find((s) => String(s.id) === String(supplierId));

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5 text-indigo-500" /> Import Purchases
          </DialogTitle>
        </DialogHeader>

        <Tabs value={step} onValueChange={setStep} className="w-full">
          <TabsList className="grid w-full grid-cols-4 h-auto">
            {STEPS.map((s) => (
              <TabsTrigger key={s.id} value={s.id} className="text-xs py-2">
                {s.label}
              </TabsTrigger>
            ))}
          </TabsList>

          <div className="max-h-[72vh] overflow-y-auto pr-1 mt-3 space-y-4">
            {/* -------- Step 1: Details -------- */}
            <TabsContent value="details" className="mt-0 space-y-4">
              <div className="text-xs text-slate-500 bg-slate-50 rounded-lg p-3 leading-relaxed">
                Choose the file and enter purchase header details. Supplier, invoice number, and
                dates from this step override values in the file.
              </div>

              <div className="border-2 border-dashed border-slate-200 rounded-lg p-5 text-center">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xlsx,.csv"
                  onChange={onFileChange}
                  className="hidden"
                />
                {file ? (
                  <div className="flex items-center justify-center gap-2 text-sm">
                    <FileSpreadsheet className="h-4 w-4 text-indigo-500" />
                    <span className="font-medium text-slate-700">{file.name}</span>
                    {inspecting && <Loader2 className="h-4 w-4 animate-spin text-slate-400" />}
                    {inspect && (
                      <Badge variant="outline" className="text-[10px]">
                        rows {inspect.min_row}–{inspect.max_row} · {inspect.format_hint === 'vendor_htf' ? 'vendor H/T/F' : 'flat'}
                      </Badge>
                    )}
                    <button type="button" className="text-slate-400 hover:text-red-500" onClick={reset}>
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ) : (
                  <>
                    <Upload className="h-8 w-8 text-slate-300 mx-auto mb-2" />
                    <p className="text-sm text-slate-500 mb-2">Choose an .xlsx or .csv purchase file</p>
                    <Button variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
                      Select File
                    </Button>
                  </>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Supplier *</Label>
                  <Select value={supplierId} onValueChange={setSupplierId}>
                    <SelectTrigger className="h-9 text-sm">
                      <SelectValue placeholder="Select supplier" />
                    </SelectTrigger>
                    <SelectContent className="max-h-72">
                      {suppliers.map((s) => (
                        <SelectItem key={s.id} value={String(s.id)} className="text-sm">
                          {s.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Invoice number *</Label>
                  <Input
                    className="h-9 text-sm"
                    value={invoiceNumber}
                    onChange={(e) => setInvoiceNumber(e.target.value)}
                    placeholder="e.g. 2026-27/TAX/1808"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Entry date *</Label>
                  <Input
                    type="date"
                    className="h-9 text-sm"
                    value={entryDate}
                    onChange={(e) => setEntryDate(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">Bill / invoice date</Label>
                  <Input
                    type="date"
                    className="h-9 text-sm"
                    value={billDate}
                    onChange={(e) => setBillDate(e.target.value)}
                  />
                </div>
              </div>

              <div className="flex justify-between items-center pt-2 border-t">
                <Button
                  variant="outline"
                  size="sm"
                  className="text-xs"
                  onClick={() => downloadPharmacyBlob(
                    '/api/pharmacy/purchases/import/template',
                    'pharmacy_purchases_import_template.xlsx',
                    toast,
                  )}
                >
                  <FileSpreadsheet className="h-3.5 w-3.5 mr-1.5" /> Template
                </Button>
                <Button size="sm" disabled={!detailsReady || !invoiceNumber.trim()} onClick={() => setStep('rows')}>
                  Next: Rows <ArrowRight className="h-3.5 w-3.5 ml-1" />
                </Button>
              </div>
            </TabsContent>

            {/* -------- Step 2: Rows -------- */}
            <TabsContent value="rows" className="mt-0 space-y-4">
              <div className="text-xs text-slate-500 bg-slate-50 rounded-lg p-3 leading-relaxed">
                Enter 1-based file line numbers for where data starts and ends (including any header/
                footer lines you want the importer to see). Available data lines in this file:{' '}
                <span className="font-medium text-slate-700">
                  {inspect ? `${inspect.min_row}–${inspect.max_row}` : '—'}
                </span>
                {' '}({inspect?.row_count || 0} parsed rows).
              </div>

              <div className="rounded-lg border border-slate-200 p-3 text-xs text-slate-600 space-y-1">
                <div><span className="text-slate-400">Supplier:</span> {selectedSupplier?.name || '—'}</div>
                <div><span className="text-slate-400">Invoice:</span> {invoiceNumber || '—'}</div>
                <div><span className="text-slate-400">Date:</span> {entryDate || '—'}</div>
                <div><span className="text-slate-400">File:</span> {file?.name || '—'}</div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Start row *</Label>
                  <Input
                    type="number"
                    min={1}
                    className="h-9 text-sm"
                    value={rowStart}
                    onChange={(e) => { setRowStart(e.target.value); setSummary(null); setDone(null); }}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">End row *</Label>
                  <Input
                    type="number"
                    min={1}
                    className="h-9 text-sm"
                    value={rowEnd}
                    onChange={(e) => { setRowEnd(e.target.value); setSummary(null); setDone(null); }}
                  />
                </div>
              </div>

              <div className="flex justify-between pt-2 border-t">
                <Button variant="outline" size="sm" onClick={() => setStep('details')}>Back</Button>
                <Button size="sm" disabled={!rowsReady} onClick={() => setStep('mapping')}>
                  Next: Mapping <ArrowRight className="h-3.5 w-3.5 ml-1" />
                </Button>
              </div>
            </TabsContent>

            {/* -------- Step 3: Mapping -------- */}
            <TabsContent value="mapping" className="mt-0 space-y-4">
              <div className="flex flex-wrap items-end gap-2">
                <div className="flex-1 min-w-[200px] space-y-1.5">
                  <Label className="text-xs">Load saved mapping</Label>
                  <Select
                    value={selectedPresetId || undefined}
                    onValueChange={applyPreset}
                  >
                    <SelectTrigger className="h-9 text-sm">
                      <SelectValue placeholder="Choose a saved mapping…" />
                    </SelectTrigger>
                    <SelectContent>
                      {savedMappings.length === 0 ? (
                        <div className="px-2 py-1.5 text-xs text-slate-400">No saved mappings yet</div>
                      ) : savedMappings.map((m) => (
                        <SelectItem key={m.id} value={String(m.id)} className="text-sm">
                          {m.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {selectedPresetId && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-xs text-red-600"
                    onClick={() => deletePreset(selectedPresetId)}
                  >
                    <Trash2 className="h-3.5 w-3.5 mr-1" /> Delete
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs"
                  onClick={() => {
                    setMapping(inspect?.suggested_mapping || {});
                    setSelectedPresetId('');
                    setSummary(null);
                    setDone(null);
                  }}
                >
                  Reset suggestions
                </Button>
              </div>

              {inspect && headers.length > 0 && (
                <div className="border border-slate-200 rounded-lg overflow-hidden">
                  <div className="grid grid-cols-[1fr_auto_1fr] gap-2 px-3 py-2 text-[10px] uppercase tracking-wider text-slate-400 border-b bg-slate-50">
                    <div>File column</div>
                    <div className="w-6" />
                    <div>ERP purchase field</div>
                  </div>
                  <div className="max-h-64 overflow-y-auto divide-y divide-slate-50">
                    {headers.map((header) => {
                      const samples = (inspect.samples?.[header] || []).filter(Boolean);
                      const value = mapping[header] || 'ignore';
                      return (
                        <div
                          key={header}
                          className="grid grid-cols-[1fr_auto_1fr] gap-2 items-center px-3 py-2 hover:bg-slate-50/80"
                        >
                          <div className="min-w-0">
                            <div className="text-sm font-mono font-medium text-slate-800 truncate">{header}</div>
                            {samples.length > 0 && (
                              <div className="text-[11px] text-slate-400 truncate mt-0.5" title={samples.join(' · ')}>
                                e.g. {samples.slice(0, 2).join(' · ')}
                              </div>
                            )}
                          </div>
                          <ArrowRight className="h-3.5 w-3.5 text-slate-300" />
                          <Select value={value} onValueChange={(v) => setColumnTarget(header, v)}>
                            <SelectTrigger className={`h-8 text-xs ${value !== 'ignore' ? 'border-indigo-200 bg-indigo-50/40' : ''}`}>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent className="max-h-72">
                              {targetsByGroup.map((group) => (
                                <React.Fragment key={group.label || 'root'}>
                                  {group.label ? (
                                    <div className="px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                                      {group.label}
                                    </div>
                                  ) : null}
                                  {group.items.map((t) => {
                                    const taken = mappedTargets.has(t.key) && mapping[header] !== t.key && t.key !== 'ignore';
                                    return (
                                      <SelectItem key={t.key} value={t.key} disabled={taken} className="text-xs">
                                        {t.label}{taken ? ' (mapped)' : ''}
                                      </SelectItem>
                                    );
                                  })}
                                </React.Fragment>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                      );
                    })}
                  </div>
                  <div className="px-3 py-2 bg-slate-50 border-t text-[11px] text-slate-500">
                    {mappedTargets.size} field{mappedTargets.size !== 1 ? 's' : ''} mapped
                    {mappedTargets.has('mrp') && !mappedTargets.has('rate_a') && (
                      <span> · Rate A/B will use MRP when not mapped separately</span>
                    )}
                  </div>
                </div>
              )}

              <div className="flex justify-between pt-2 border-t">
                <Button variant="outline" size="sm" onClick={() => setStep('rows')}>Back</Button>
                <Button size="sm" disabled={!mappingReady} onClick={() => setStep('import')}>
                  Next: Import <ArrowRight className="h-3.5 w-3.5 ml-1" />
                </Button>
              </div>
            </TabsContent>

            {/* -------- Step 4: Import -------- */}
            <TabsContent value="import" className="mt-0 space-y-4">
              <div className="rounded-lg border border-slate-200 p-3 text-xs text-slate-600 grid grid-cols-2 gap-x-4 gap-y-1">
                <div><span className="text-slate-400">Supplier:</span> {selectedSupplier?.name || '—'}</div>
                <div><span className="text-slate-400">Invoice:</span> {invoiceNumber || '—'}</div>
                <div><span className="text-slate-400">Entry date:</span> {entryDate || '—'}</div>
                <div><span className="text-slate-400">Rows:</span> {rowStart}–{rowEnd}</div>
                <div className="col-span-2"><span className="text-slate-400">File:</span> {file?.name || '—'}</div>
              </div>

              {!done && (
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-600">If invoice already exists:</span>
                    <Select
                      value={onDuplicate}
                      onValueChange={(v) => { setOnDuplicate(v); setSummary(null); }}
                    >
                      <SelectTrigger className="h-8 w-36 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="skip">Skip it</SelectItem>
                        <SelectItem value="update">Update draft</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => runImport(true)}
                    disabled={analyzing || !mappingReady}
                  >
                    {analyzing
                      ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      : <RefreshCw className="h-4 w-4 mr-2" />}
                    Preview
                  </Button>
                </div>
              )}

              {result && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  <SummaryStat label="New" value={result.created} color="text-emerald-600" />
                  <SummaryStat label="Update" value={result.updated} color="text-blue-600" />
                  <SummaryStat label="Skipped" value={result.skipped} color="text-slate-500" />
                  <SummaryStat label="Errors" value={result.error_count} color="text-red-600" />
                </div>
              )}

              {result?.masters_created?.length > 0 && (
                <div className="text-xs text-slate-600 bg-indigo-50/50 border border-indigo-100 rounded-lg p-3">
                  <span className="font-medium">Masters {done ? 'created' : 'to create'}:</span>
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {result.masters_created.map((m) => (
                      <Badge key={m} variant="outline" className="text-[10px]">{m}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {result?.errors?.length > 0 && (
                <div className="border border-red-100 rounded-lg overflow-hidden">
                  <div className="flex items-center gap-2 px-3 py-2 bg-red-50 text-red-700 text-xs font-semibold">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    {result.errors.length} row{result.errors.length !== 1 ? 's' : ''} need fixing
                  </div>
                  <div className="max-h-40 overflow-y-auto divide-y divide-red-50">
                    {result.errors.map((e, i) => (
                      <div key={i} className="flex items-start gap-2 px-3 py-1.5 text-xs">
                        <Badge variant="outline" className="text-[10px] shrink-0">row {e.row}</Badge>
                        <span className="text-slate-600">{e.message}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {visiblePreview.length > 0 && (
                <div className="border border-slate-200 rounded-lg overflow-hidden">
                  <div className="overflow-x-auto max-h-56">
                    <table className="w-full text-xs">
                      <thead className="sticky top-0 bg-slate-50">
                        <tr className="text-left text-[11px] text-slate-400 uppercase tracking-wider border-b">
                          <th className="py-2 px-3 w-14">Row</th>
                          <th className="py-2 px-3">Key</th>
                          <th className="py-2 px-3">Name</th>
                          <th className="py-2 px-3 w-24">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visiblePreview.map((r, i) => (
                          <tr key={i} className="border-b border-slate-50 last:border-0">
                            <td className="py-1.5 px-3 text-slate-400 font-mono">{r.row}</td>
                            <td className="py-1.5 px-3 font-mono text-slate-600">{r.key ?? '—'}</td>
                            <td className="py-1.5 px-3 text-slate-700">
                              {r.name ?? '—'}
                              {r.message && (
                                <span className={`block text-[11px] ${r.status === 'error' ? 'text-red-500' : 'text-slate-400'}`}>
                                  {r.message}
                                </span>
                              )}
                            </td>
                            <td className="py-1.5 px-3">
                              <span className={`inline-block text-[10px] font-medium px-2 py-0.5 rounded border ${STATUS_STYLES[r.status] || ''}`}>
                                {STATUS_LABEL[r.status] || r.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {hiddenCount > 0 && (
                    <div className="px-3 py-2 text-xs text-slate-500 bg-slate-50 border-t">
                      and {hiddenCount} more row{hiddenCount !== 1 ? 's' : ''}
                    </div>
                  )}
                </div>
              )}

              {done && (
                <div className="border border-emerald-100 bg-emerald-50/40 rounded-lg p-3 space-y-3">
                  <div className="flex items-center gap-1.5 text-sm text-emerald-700">
                    <CheckCircle2 className="h-4 w-4" /> Import complete — save this column mapping for next time?
                  </div>
                  {!mappingSaved ? (
                    <div className="flex flex-wrap items-end gap-2">
                      <div className="flex-1 min-w-[180px] space-y-1">
                        <Label className="text-xs">Mapping name</Label>
                        <Input
                          className="h-9 text-sm"
                          value={mappingName}
                          onChange={(e) => setMappingName(e.target.value)}
                          placeholder="e.g. Vasu Pharma CSV"
                        />
                      </div>
                      <Button size="sm" onClick={saveMappingPreset} disabled={savingMapping}>
                        {savingMapping
                          ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          : <Save className="h-4 w-4 mr-2" />}
                        Save mapping
                      </Button>
                    </div>
                  ) : (
                    <div className="text-xs text-emerald-700">
                      Mapping “{mappingName}” saved. You can load it on step 3 next time.
                    </div>
                  )}
                </div>
              )}

              <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-100">
                {!done ? (
                  <>
                    <Button variant="outline" size="sm" onClick={() => setStep('mapping')}>Back</Button>
                    <div className="flex gap-2">
                      <Button variant="outline" size="sm" onClick={() => handleClose(false)} disabled={importing}>
                        Cancel
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => runImport(false)}
                        disabled={!summary || importing || (summary.created + summary.updated === 0)}
                      >
                        {importing && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                        Confirm Import{summary ? ` (${summary.created + summary.updated})` : ''}
                      </Button>
                    </div>
                  </>
                ) : (
                  <>
                    <Button variant="outline" size="sm" onClick={reset}>Import Another</Button>
                    <Button size="sm" onClick={() => handleClose(false)}>Done</Button>
                  </>
                )}
              </div>
            </TabsContent>
          </div>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

function SummaryStat({ label, value, color }) {
  return (
    <div className="rounded-lg border border-slate-200 px-3 py-2 text-center">
      <div className={`text-lg font-bold ${color}`}>{value ?? 0}</div>
      <div className="text-[11px] text-slate-400 uppercase tracking-wider">{label}</div>
    </div>
  );
}
