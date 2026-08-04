import React, { useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../ui/select';
import { useToast } from '../../hooks/use-toast';
import { downloadPharmacyBlob } from './PharmacyImportDialog';
import {
  Upload, FileSpreadsheet, Loader2, CheckCircle2,
  AlertTriangle, RefreshCw, X, ArrowRight,
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

const REQUIRED_HINTS = [
  'supplier_name or supplier_or_invoice',
  'medicine_name or medicine_code',
  'batch_number',
  'expiry_date',
  'quantity',
  'purchase_rate',
];

export default function PurchaseImportDialog({ open, onOpenChange, onImported }) {
  const { toast } = useToast();
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [onDuplicate, setOnDuplicate] = useState('skip');
  const [inspecting, setInspecting] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [inspect, setInspect] = useState(null);
  const [mapping, setMapping] = useState({});
  const [summary, setSummary] = useState(null);
  const [done, setDone] = useState(null);

  const reset = () => {
    setFile(null);
    setInspect(null);
    setMapping({});
    setSummary(null);
    setDone(null);
    setOnDuplicate('skip');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleClose = (v) => {
    if (importing || analyzing || inspecting) return;
    if (!v) reset();
    onOpenChange(v);
  };

  const feedback = (msg, type) => {
    if (type === 'error') toast({ variant: 'destructive', title: msg });
    else toast({ title: msg });
  };

  const inspectFile = async (f) => {
    setInspecting(true);
    setInspect(null);
    setMapping({});
    setSummary(null);
    setDone(null);
    try {
      const fd = new FormData();
      fd.append('file', f);
      const res = await axios.post('/api/pharmacy/purchases/import/inspect', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setInspect(res.data);
      setMapping(res.data.suggested_mapping || {});
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
    }
  };

  const setColumnTarget = (header, target) => {
    setMapping((prev) => {
      const next = { ...prev };
      // One ERP field ← one source column (clear prior owner)
      if (target && target !== 'ignore') {
        Object.keys(next).forEach((h) => {
          if (h !== header && next[h] === target) next[h] = 'ignore';
        });
      }
      next[header] = target;
      return next;
    });
    setSummary(null);
  };

  const mappedTargets = useMemo(
    () => new Set(Object.values(mapping).filter((v) => v && v !== 'ignore')),
    [mapping],
  );

  const runImport = async (dryRun) => {
    if (!file) return;
    const setBusy = dryRun ? setAnalyzing : setImporting;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('dry_run', dryRun ? 'true' : 'false');
      fd.append('on_duplicate', onDuplicate);
      fd.append('column_mapping', JSON.stringify(mapping));
      const res = await axios.post('/api/pharmacy/purchases/import', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      if (dryRun) {
        setSummary(res.data);
      } else {
        setDone(res.data);
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

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5 text-indigo-500" /> Import Purchases
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 max-h-[80vh] overflow-y-auto pr-1">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-slate-500">Optional starting point:</span>
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
              <FileSpreadsheet className="h-3.5 w-3.5 mr-1.5" /> Excel template
            </Button>
          </div>

          <div className="text-xs text-slate-500 bg-slate-50 rounded-lg p-3 leading-relaxed">
            Upload a vendor tax-invoice CSV or any purchase spreadsheet. Map each file column (left)
            to the ERP purchase field (right). Unmapped rate A/B default from MRP when MRP is mapped.
            Imports create <span className="font-medium text-slate-700">draft</span> purchases —
            review and Confirm to add stock. Missing medicines and HSN codes are auto-created
            (category General) from the line details. Supplier must already exist.
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
                    {inspect.row_count} rows · {inspect.format_hint === 'vendor_htf' ? 'vendor H/T/F' : 'flat'}
                  </Badge>
                )}
                <button
                  type="button"
                  className="text-slate-400 hover:text-red-500"
                  onClick={reset}
                >
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

          {inspect && headers.length > 0 && !done && (
            <div className="border border-slate-200 rounded-lg overflow-hidden">
              <div className="flex items-center justify-between gap-2 px-3 py-2 bg-slate-50 border-b">
                <div>
                  <div className="text-xs font-semibold text-slate-700">Column mapping</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">
                    Suggested mapping applied — adjust any column. Needed: {REQUIRED_HINTS.join(', ')}.
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs h-7"
                  onClick={() => {
                    setMapping(inspect.suggested_mapping || {});
                    setSummary(null);
                  }}
                >
                  Reset suggestions
                </Button>
              </div>

              <div className="grid grid-cols-[1fr_auto_1fr] gap-2 px-3 py-2 text-[10px] uppercase tracking-wider text-slate-400 border-b bg-white sticky top-0">
                <div>File column</div>
                <div className="w-6" />
                <div>ERP purchase field</div>
              </div>

              <div className="max-h-72 overflow-y-auto divide-y divide-slate-50">
                {headers.map((header) => {
                  const samples = (inspect.samples?.[header] || []).filter(Boolean);
                  const value = mapping[header] || 'ignore';
                  return (
                    <div
                      key={header}
                      className="grid grid-cols-[1fr_auto_1fr] gap-2 items-center px-3 py-2 hover:bg-slate-50/80"
                    >
                      <div className="min-w-0">
                        <div className="text-sm font-mono font-medium text-slate-800 truncate">
                          {header}
                        </div>
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
                                  <SelectItem
                                    key={t.key}
                                    value={t.key}
                                    disabled={taken}
                                    className="text-xs"
                                  >
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

          {file && inspect && !done && (
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
                disabled={analyzing || inspecting || mappedTargets.size === 0}
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

          {result?.errors?.length > 0 && (
            <div className="border border-red-100 rounded-lg overflow-hidden">
              <div className="flex items-center gap-2 px-3 py-2 bg-red-50 text-red-700 text-xs font-semibold">
                <AlertTriangle className="h-3.5 w-3.5" />
                {result.errors.length} row{result.errors.length !== 1 ? 's' : ''} need fixing
              </div>
              <div className="max-h-40 overflow-y-auto divide-y divide-red-50">
                {result.errors.map((e, i) => (
                  <div key={i} className="flex items-start gap-2 px-3 py-1.5 text-xs">
                    <Badge variant="outline" className="text-[10px] shrink-0">
                      row {e.row}
                    </Badge>
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

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
            {done ? (
              <>
                <div className="flex items-center gap-1.5 text-sm text-emerald-600 mr-auto">
                  <CheckCircle2 className="h-4 w-4" /> Import complete
                </div>
                <Button variant="outline" size="sm" onClick={reset}>Import Another</Button>
                <Button size="sm" onClick={() => handleClose(false)}>Done</Button>
              </>
            ) : (
              <>
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
              </>
            )}
          </div>
        </div>
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
