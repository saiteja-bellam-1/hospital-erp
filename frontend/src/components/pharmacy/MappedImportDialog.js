import React, { useEffect, useRef, useState } from 'react';
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
  AlertTriangle, RefreshCw, X, ArrowRight, Save, Trash2, Plus,
} from 'lucide-react';
import QuickMedicineDialog from './QuickMedicineDialog';

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
  { id: 'details', label: '1. File' },
  { id: 'rows', label: '2. Rows' },
  { id: 'mapping', label: '3. Mapping' },
  { id: 'import', label: '4. Import' },
];

export const MEDICINE_MAP_FIELDS = [
  { key: 'medicine_code', label: 'Medicine code', required: true },
  { key: 'name', label: 'Name', required: true },
  { key: 'category', label: 'Category', required: true },
  { key: 'generic_name', label: 'Generic name', required: false },
  { key: 'mrp', label: 'MRP', required: false },
  { key: 'purchase_rate', label: 'Purchase rate (PTR)', required: false },
  { key: 'rate_a', label: 'Rate A (sale)', required: false },
  { key: 'rate_b', label: 'Rate B (sale)', required: false },
  { key: 'packaging', label: 'Pack / packaging', required: false },
  { key: 'strip_conversion_factor', label: 'Tabs / strip', required: false },
  { key: 'manufacturer', label: 'Manufacturer', required: false },
  { key: 'company', label: 'Company', required: false },
  { key: 'hsn_code', label: 'HSN code', required: false },
  { key: 'sgst_pct', label: 'SGST %', required: false },
  { key: 'cgst_pct', label: 'CGST %', required: false },
  { key: 'salt', label: 'Salt', required: false },
  { key: 'uom', label: 'UoM', required: false },
  { key: 'rack_code', label: 'Rack', required: false },
  { key: 'barcode', label: 'Barcode', required: false },
  { key: 'dosage_form', label: 'Dosage form', required: false },
  { key: 'strength', label: 'Strength', required: false },
  { key: 'unit_price', label: 'Unit price', required: false },
];

export const SALE_MAP_FIELDS = [
  { key: 'sale_date', label: 'Sale date', required: true },
  { key: 'quantity', label: 'Quantity', required: true },
  { key: 'medicine_name', label: 'Medicine name', required: false },
  { key: 'medicine_code', label: 'Medicine code', required: false },
  { key: 'sale_number', label: 'Sale / bill number', required: false },
  { key: 'batch_number', label: 'Batch number', required: false },
  { key: 'rate', label: 'Rate', required: false },
  { key: 'discount_pct', label: 'Discount %', required: false },
  { key: 'qty_unit', label: 'Qty unit (tablet / strip)', required: false },
  { key: 'rate_tier', label: 'Rate tier (A / B)', required: false },
  { key: 'payment_type', label: 'Payment (cash / credit)', required: false },
  { key: 'tax_mode', label: 'Tax mode', required: false },
  { key: 'store_code', label: 'Store code', required: false },
  { key: 'patient_name', label: 'Patient name', required: false },
  { key: 'patient_phone', label: 'Patient phone', required: false },
  { key: 'patient_address', label: 'Patient address', required: false },
  { key: 'doctor_name', label: 'Doctor name', required: false },
  { key: 'doctor_number', label: 'Doctor number', required: false },
  { key: 'bill_discount_amount', label: 'Bill discount', required: false },
];

function toColLetter(raw) {
  return String(raw || '').toUpperCase().replace(/[^A-Z]/g, '').slice(0, 3);
}

function excelLetterFromIndex(idx) {
  let n = idx + 1;
  let s = '';
  while (n > 0) {
    const rem = (n - 1) % 26;
    s = String.fromCharCode(65 + rem) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

function normalizeLoadedMapping(raw, fieldKeys) {
  if (!raw || typeof raw !== 'object') return {};
  const keys = Object.keys(raw);
  const next = {};
  if (keys.some((k) => fieldKeys.has(k))) {
    keys.forEach((k) => {
      const letter = toColLetter(raw[k]);
      if (fieldKeys.has(k) && letter) next[k] = letter;
    });
    return next;
  }
  keys.forEach((h) => {
    const field = raw[h];
    if (!field || field === 'ignore' || !fieldKeys.has(field)) return;
    const m = String(h).match(/^cl(\d+)$/i);
    if (m) next[field] = excelLetterFromIndex(parseInt(m[1], 10) - 1);
    else {
      const letter = toColLetter(h);
      if (letter) next[field] = letter;
    }
  });
  return next;
}

function unmatchedName(item) {
  if (!item) return '';
  return typeof item === 'string' ? item : String(item.name || '');
}

function normalizeUnmatched(list) {
  return (list || []).map((item) => (typeof item === 'string' ? { name: item } : item));
}

function prefillFromUnmatched(item) {
  const raw = typeof item === 'string' ? { name: item } : (item || {});
  const vendor = String(raw.medicine_code || '').trim();
  return {
    name: raw.name || '',
    medicine_code: vendor.length > 0 && vendor.length <= 20 ? vendor : '',
    pack_size: raw.pack_size || '',
    manufacturer: raw.manufacturer || '',
    mrp: raw.mrp,
    purchase_rate: raw.purchase_rate,
    rate_a: raw.mrp,
    rate_b: raw.mrp,
    strip_conversion_factor: raw.strip_conversion_factor || 1,
  };
}

export default function MappedImportDialog({
  open,
  onOpenChange,
  onImported,
  title,
  entityLabel,
  inspectUrl,
  importUrl,
  templateUrl,
  mappingsUrl,
  mapFields,
  detailsHelp,
  mappingHelp,
  importHelp,
  fileHint,
  showDuplicateSelect = true,
  showAffectStock = false,
  defaultAffectStock = false,
  showUnmatchedMedicines = false,
  requireAny = null,
  commitLabel = 'Import',
}) {
  const { toast } = useToast();
  const fileInputRef = useRef(null);
  const fieldKeys = new Set((mapFields || []).map((f) => f.key));
  const requiredFields = (mapFields || []).filter((f) => f.required);

  const [step, setStep] = useState('details');
  const [file, setFile] = useState(null);
  const [rowStart, setRowStart] = useState('');
  const [rowEnd, setRowEnd] = useState('');
  const [onDuplicate, setOnDuplicate] = useState('skip');
  const [affectStock, setAffectStock] = useState(defaultAffectStock);

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
  const [medicineDialogOpen, setMedicineDialogOpen] = useState(false);
  const [medicinePrefill, setMedicinePrefill] = useState({});
  const unmatchedQueueRef = useRef([]);

  const reset = () => {
    setStep('details');
    setFile(null);
    setRowStart('');
    setRowEnd('');
    setOnDuplicate('skip');
    setAffectStock(defaultAffectStock);
    setInspect(null);
    setMapping({});
    setSelectedPresetId('');
    setSummary(null);
    setDone(null);
    setMappingName('');
    setMappingSaved(false);
    setMedicineDialogOpen(false);
    setMedicinePrefill({});
    unmatchedQueueRef.current = [];
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleClose = (v) => {
    if (importing || analyzing || inspecting || savingMapping || medicineDialogOpen) return;
    if (!v) reset();
    onOpenChange(v);
  };

  const feedback = (msg, type) => {
    if (type === 'error') toast({ variant: 'destructive', title: msg });
    else toast({ title: msg });
  };

  const loadSavedMappings = async () => {
    try {
      const r = await axios.get(mappingsUrl);
      setSavedMappings(r.data || []);
    } catch {
      setSavedMappings([]);
    }
  };

  useEffect(() => {
    if (!open) return;
    loadSavedMappings();
  }, [open, mappingsUrl]);

  const inspectFile = async (f, { rowStart: rs, rowEnd: re, preserveRows = false, preserveMapping = false } = {}) => {
    setInspecting(true);
    setSummary(null);
    setDone(null);
    setMappingSaved(false);
    try {
      const fd = new FormData();
      fd.append('file', f);
      const startVal = rs !== undefined && rs !== null && rs !== '' ? Number(rs) : 1;
      fd.append('row_start', String(startVal));
      if (re !== undefined && re !== null && re !== '') {
        fd.append('row_end', String(Number(re)));
      }
      const res = await axios.post(inspectUrl, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setInspect(res.data);
      if (!preserveRows) {
        const nextStart = res.data.header_detected && res.data.suggested_row_start
          ? res.data.suggested_row_start
          : (res.data.min_row || startVal || 1);
        setRowStart(String(nextStart));
      }
      if (!preserveMapping && Object.keys(res.data.suggested_letter_mapping || {}).length) {
        setMapping(res.data.suggested_letter_mapping);
      }
      return res.data;
    } catch (err) {
      const detail = err.response?.data?.detail;
      feedback(typeof detail === 'string' ? detail : 'Could not read file columns', 'error');
      if (!preserveRows) {
        setInspect(null);
        setMapping({});
        setFile(null);
        if (fileInputRef.current) fileInputRef.current.value = '';
      }
      throw err;
    } finally {
      setInspecting(false);
    }
  };

  const onFileChange = (e) => {
    const f = e.target.files?.[0] || null;
    setFile(f);
    if (f) {
      setRowStart('1');
      setRowEnd('');
      setMapping({});
      inspectFile(f, { rowStart: 1, rowEnd: '' });
    } else {
      setInspect(null);
      setMapping({});
      setSummary(null);
      setDone(null);
      setRowStart('');
      setRowEnd('');
    }
  };

  const setFieldLetter = (field, raw) => {
    const letter = toColLetter(raw);
    setMapping((prev) => {
      const next = { ...prev };
      if (letter) next[field] = letter;
      else delete next[field];
      return next;
    });
    setSummary(null);
    setDone(null);
    setMappingSaved(false);
  };

  const anyGroupReady = !requireAny || requireAny.every((group) => (
    group.some((k) => toColLetter(mapping[k]))
  ));
  const mappingReady = requiredFields.every((f) => toColLetter(mapping[f.key])) && anyGroupReady;

  const applyPreset = (id) => {
    setSelectedPresetId(id);
    const preset = savedMappings.find((m) => String(m.id) === String(id));
    if (!preset) return;
    setMapping(normalizeLoadedMapping(preset.column_mapping || {}, fieldKeys));
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
      await axios.delete(`${mappingsUrl}/${id}`);
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
    if (rowStart !== '' && rowStart != null) fd.append('row_start', String(Number(rowStart)));
    if (rowEnd !== '' && rowEnd != null) fd.append('row_end', String(Number(rowEnd)));
    if (showAffectStock) fd.append('affect_stock', affectStock ? 'true' : 'false');
  };

  const runImport = async (dryRun) => {
    if (!file) return null;
    const setBusy = dryRun ? setAnalyzing : setImporting;
    setBusy(true);
    try {
      const fd = new FormData();
      appendImportFields(fd);
      fd.append('dry_run', dryRun ? 'true' : 'false');
      const res = await axios.post(importUrl, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      if (dryRun) {
        setSummary(res.data);
        setStep('import');
        return res.data;
      }
      setDone(res.data);
      onImported?.();
      feedback(
        `Imported: ${res.data.created} new, ${res.data.updated} updated, ${res.data.skipped} skipped`,
      );
      return res.data;
    } catch (err) {
      const detail = err.response?.data?.detail;
      feedback(typeof detail === 'string' ? detail : 'Import failed', 'error');
      return null;
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
    if (!mappingReady) {
      feedback('Enter columns for all required fields before saving', 'error');
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
      const res = await axios.post(mappingsUrl, payload);
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

  const detailsReady = !!file && !!inspect;
  const rowsReady = detailsReady
    && rowStart !== ''
    && Number(rowStart) > 0
    && (rowEnd === '' || Number(rowEnd) >= Number(rowStart));
  const canProceedMapping = rowsReady && mappingReady;

  const result = done || summary;
  const previewRows = result?.preview || [];
  const visiblePreview = previewRows.slice(0, PREVIEW_LIMIT);
  const hiddenCount = Math.max(0, previewRows.length - PREVIEW_LIMIT);
  const unmatched = showUnmatchedMedicines ? normalizeUnmatched(result?.unmatched_medicines) : [];
  const otherErrors = (result?.errors || []).filter((e) => {
    const m = String(e.message || '').toLowerCase();
    return !showUnmatchedMedicines || !m.includes('not found');
  });

  const openAddMedicine = (item, rest = []) => {
    unmatchedQueueRef.current = rest;
    setMedicinePrefill(prefillFromUnmatched(item));
    setMedicineDialogOpen(true);
  };

  const startAddQueue = (fromItem) => {
    const startIdx = fromItem
      ? unmatched.findIndex((u) => unmatchedName(u) === unmatchedName(fromItem))
      : 0;
    const idx = startIdx < 0 ? 0 : startIdx;
    const item = unmatched[idx];
    if (!item) return;
    openAddMedicine(item, unmatched.slice(idx + 1));
  };

  const handleMedicineCreated = async (created) => {
    const rest = [...unmatchedQueueRef.current];
    unmatchedQueueRef.current = [];
    setMedicineDialogOpen(false);
    const data = await runImport(true);
    const still = normalizeUnmatched(data?.unmatched_medicines);
    if (!still.length) return;
    const createdKey = unmatchedName(created).trim().toLowerCase();
    const remaining = still.filter((u) => unmatchedName(u).trim().toLowerCase() !== createdKey);
    const next = rest.find((q) => remaining.some(
      (s) => unmatchedName(s).toLowerCase() === unmatchedName(q).toLowerCase(),
    )) || remaining[0];
    if (!next) return;
    const nextRest = remaining.filter(
      (s) => unmatchedName(s).toLowerCase() !== unmatchedName(next).toLowerCase(),
    );
    openAddMedicine(next, nextRest);
  };

  const canCommit = !!summary
    && unmatched.length === 0
    && (summary.created + summary.updated + summary.skipped + (summary.error_count || 0) > 0
      || (summary.preview || []).length > 0)
    && !importing;

  return (
    <>
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5 text-indigo-500" /> {title}
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
            <TabsContent value="details" className="mt-0 space-y-4">
              <div className="text-xs text-slate-500 bg-slate-50 rounded-lg p-3 leading-relaxed">
                {detailsHelp}
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
                        {inspect.file_line_count || inspect.row_count || 0} lines
                      </Badge>
                    )}
                    <button type="button" className="text-slate-400 hover:text-red-500" onClick={reset}>
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                ) : (
                  <>
                    <Upload className="h-8 w-8 text-slate-300 mx-auto mb-2" />
                    <p className="text-sm text-slate-500 mb-2">{fileHint || `Choose an .xlsx or .csv ${entityLabel} file`}</p>
                    <Button variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
                      Select File
                    </Button>
                  </>
                )}
              </div>

              {showDuplicateSelect && (
                <div className="space-y-1.5">
                  <Label className="text-xs">If a record already exists</Label>
                  <Select value={onDuplicate} onValueChange={setOnDuplicate}>
                    <SelectTrigger className="h-9 text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="skip">Skip existing</SelectItem>
                      <SelectItem value="update">Update existing</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}

              {showAffectStock && (
                <div className="space-y-1.5">
                  <Label className="text-xs">Stock</Label>
                  <Select
                    value={affectStock ? 'deduct' : 'record'}
                    onValueChange={(v) => setAffectStock(v === 'deduct')}
                  >
                    <SelectTrigger className="h-9 text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="record">Record only (do not change stock)</SelectItem>
                      <SelectItem value="deduct">Deduct stock from existing batches</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}

              <div className="flex justify-between items-center pt-2 border-t">
                <Button
                  variant="outline"
                  size="sm"
                  className="text-xs"
                  onClick={() => downloadPharmacyBlob(templateUrl, `${entityLabel}_import_template.xlsx`, toast)}
                >
                  <FileSpreadsheet className="h-3.5 w-3.5 mr-1.5" /> Template
                </Button>
                <Button size="sm" disabled={!detailsReady} onClick={() => setStep('rows')}>
                  Next: Rows <ArrowRight className="h-3.5 w-3.5 ml-1" />
                </Button>
              </div>
            </TabsContent>

            <TabsContent value="rows" className="mt-0 space-y-4">
              <div className="text-xs text-slate-500 bg-slate-50 rounded-lg p-3 leading-relaxed">
                <span className="font-medium text-slate-700">Start row</span> is the first
                {' '}<span className="font-medium text-slate-700">data</span> line (not the header).
                Rows above it are ignored. <span className="font-medium text-slate-700">End row</span> is
                optional — leave blank to import through the end of the file.
                {inspect?.file_line_count ? (
                  <span>
                    {' '}This file has{' '}
                    <span className="font-medium text-slate-700">{inspect.file_line_count}</span> lines.
                  </span>
                ) : null}
                {inspect?.header_detected ? (
                  <span className="block mt-1 text-emerald-700">
                    Header row detected — start row is set to the first data line.
                  </span>
                ) : null}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs">Start row (first data line) *</Label>
                  <Input
                    type="number"
                    min={1}
                    className="h-9 text-sm"
                    value={rowStart}
                    onChange={(e) => { setRowStart(e.target.value); setSummary(null); setDone(null); }}
                    placeholder="1"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs">End row (optional)</Label>
                  <Input
                    type="number"
                    min={1}
                    className="h-9 text-sm"
                    value={rowEnd}
                    onChange={(e) => { setRowEnd(e.target.value); setSummary(null); setDone(null); }}
                    placeholder={inspect?.file_line_count ? `Through ${inspect.file_line_count}` : 'Through end of file'}
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
                    setMapping({});
                    setSelectedPresetId('');
                    setSummary(null);
                    setDone(null);
                  }}
                >
                  Clear columns
                </Button>
              </div>

              <div className="text-xs text-slate-500 bg-slate-50 rounded-lg p-3 leading-relaxed">
                {mappingHelp || (
                  <>
                    Type the Excel column letter for each field (A, B, C, … AA). Fields marked *
                    must be mapped.
                    {requireAny ? ' Map at least one of medicine name or medicine code.' : null}
                  </>
                )}
              </div>

              {inspect?.header_preview?.length > 0 && (
                <div className="text-[11px] text-slate-500 border border-slate-100 rounded-md px-3 py-2">
                  <span className="font-medium text-slate-600">Detected headers: </span>
                  {inspect.header_preview.slice(0, 12).map((h) => (
                    <span key={h.letter} className="mr-2">
                      <span className="font-mono text-slate-700">{h.letter}</span>
                      {h.value ? ` ${h.value}` : ''}
                    </span>
                  ))}
                </div>
              )}

              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <div className="grid grid-cols-[1fr_6rem] gap-2 px-3 py-2 text-[10px] uppercase tracking-wider text-slate-400 border-b bg-slate-50">
                  <div>Field</div>
                  <div>Column</div>
                </div>
                <div className="divide-y divide-slate-50 max-h-80 overflow-y-auto">
                  {mapFields.map((f) => (
                    <div key={f.key} className="grid grid-cols-[1fr_6rem] gap-2 items-center px-3 py-2">
                      <Label className={`text-sm ${f.required ? 'text-slate-800' : 'text-slate-600'}`}>
                        {f.label}
                        {f.required && <span className="text-red-500 ml-0.5">*</span>}
                      </Label>
                      <Input
                        className="h-8 text-sm font-mono uppercase text-center"
                        value={mapping[f.key] || ''}
                        onChange={(e) => setFieldLetter(f.key, e.target.value)}
                        placeholder={f.required ? 'A' : ''}
                        maxLength={3}
                      />
                    </div>
                  ))}
                </div>
              </div>

              <div className="border border-slate-200 rounded-lg p-3 space-y-2">
                <div className="text-xs font-medium text-slate-700">Save this mapping</div>
                <div className="text-[11px] text-slate-500">
                  Name and save the current column map (and row range) to reuse on similar files.
                </div>
                <div className="flex flex-wrap items-end gap-2">
                  <div className="flex-1 min-w-[180px] space-y-1">
                    <Label className="text-xs">Mapping name</Label>
                    <Input
                      className="h-9 text-sm"
                      value={mappingName}
                      onChange={(e) => { setMappingName(e.target.value); setMappingSaved(false); }}
                      placeholder="e.g. Vendor catalog CSV"
                    />
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={saveMappingPreset}
                    disabled={savingMapping || !mappingReady || !mappingName.trim()}
                  >
                    {savingMapping
                      ? <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      : <Save className="h-4 w-4 mr-2" />}
                    {mappingSaved ? 'Saved' : 'Save mapping'}
                  </Button>
                </div>
              </div>

              <div className="flex justify-between pt-2 border-t">
                <Button variant="outline" size="sm" onClick={() => setStep('rows')}>Back</Button>
                <Button size="sm" disabled={!canProceedMapping} onClick={() => setStep('import')}>
                  Next: Import <ArrowRight className="h-3.5 w-3.5 ml-1" />
                </Button>
              </div>
            </TabsContent>

            <TabsContent value="import" className="mt-0 space-y-4">
              <div className="rounded-lg border border-slate-200 p-3 text-xs text-slate-600 grid grid-cols-2 gap-x-4 gap-y-1">
                <div><span className="text-slate-400">Rows:</span> {rowStart}{rowEnd ? `–${rowEnd}` : ' → end'}</div>
                <div><span className="text-slate-400">File:</span> {file?.name || '—'}</div>
                {showAffectStock && (
                  <div className="col-span-2">
                    <span className="text-slate-400">Stock:</span>{' '}
                    {affectStock ? 'Deduct from batches' : 'Record only'}
                  </div>
                )}
              </div>

              {!done && (
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-xs text-slate-500">
                    {importHelp || 'Preview the rows, then confirm the import.'}
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
                  <SummaryStat label="Updated" value={result.updated} color="text-blue-600" />
                  <SummaryStat label="Skipped" value={result.skipped} color="text-slate-500" />
                  <SummaryStat label="Errors" value={result.error_count} color="text-red-600" />
                </div>
              )}

              {unmatched.length > 0 && (
                <div className="border border-amber-200 bg-amber-50/60 rounded-lg p-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 text-xs font-semibold text-amber-800">
                      <AlertTriangle className="h-3.5 w-3.5" />
                      {unmatched.length} medicine{unmatched.length !== 1 ? 's' : ''} not in catalog
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs bg-white"
                      onClick={() => startAddQueue()}
                      disabled={analyzing || medicineDialogOpen}
                    >
                      <Plus className="h-3.5 w-3.5 mr-1" />
                      Add missing
                    </Button>
                  </div>
                  <p className="text-[11px] text-amber-800/80">
                    Add each item here (category is required). After save, Preview runs again.
                    Import stays blocked until every name matches.
                  </p>
                  <div className="border border-amber-100 rounded-md bg-white max-h-48 overflow-y-auto divide-y divide-amber-50">
                    {unmatched.map((item) => (
                      <div key={unmatchedName(item)} className="flex items-center gap-2 px-2.5 py-1.5">
                        <div className="min-w-0 flex-1">
                          <div className="text-xs font-medium text-slate-800 truncate">
                            {unmatchedName(item)}
                          </div>
                          <div className="text-[10px] text-slate-400 truncate">
                            {[item.medicine_code, item.pack_size, item.manufacturer]
                              .filter(Boolean)
                              .join(' · ') || `Row ${item.row || '—'}`}
                          </div>
                        </div>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-[11px] shrink-0"
                          onClick={() => startAddQueue(item)}
                          disabled={analyzing || medicineDialogOpen}
                        >
                          <Plus className="h-3 w-3 mr-1" />
                          Add
                        </Button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {otherErrors.length > 0 && (
                <div className="border border-red-100 rounded-lg overflow-hidden">
                  <div className="flex items-center gap-2 px-3 py-2 bg-red-50 text-red-700 text-xs font-semibold">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    {otherErrors.length} row{otherErrors.length !== 1 ? 's' : ''} need fixing
                  </div>
                  <div className="max-h-40 overflow-y-auto divide-y divide-red-50">
                    {otherErrors.map((e, i) => (
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
                <div className="border border-emerald-100 bg-emerald-50/40 rounded-lg px-3 py-2 text-sm text-emerald-700 flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4" /> Import complete.
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
                        disabled={!canCommit || unmatched.length > 0}
                      >
                        {importing && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                        {commitLabel}
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
    {showUnmatchedMedicines && (
      <QuickMedicineDialog
        open={medicineDialogOpen}
        onOpenChange={(v) => {
          setMedicineDialogOpen(v);
          if (!v && !analyzing) unmatchedQueueRef.current = [];
        }}
        prefill={medicinePrefill}
        lockName
        onCreated={handleMedicineCreated}
      />
    )}
    </>
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
