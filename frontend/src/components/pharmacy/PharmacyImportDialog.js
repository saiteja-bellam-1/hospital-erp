import React, { useRef, useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../ui/select';
import { useToast } from '../../hooks/use-toast';
import {
  Upload, FileSpreadsheet, Loader2, CheckCircle2,
  AlertTriangle, RefreshCw, X, Download,
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

export async function downloadPharmacyBlob(url, fallbackName, toast) {
  try {
    const res = await axios.get(url, { responseType: 'blob' });
    const contentType = res.headers['content-type'] || '';
    if (contentType.includes('application/json')) {
      const text = await res.data.text?.() || await new Response(res.data).text();
      let detail = 'Failed to download file';
      try { detail = JSON.parse(text).detail || detail; } catch { /* keep default */ }
      throw new Error(typeof detail === 'string' ? detail : 'Failed to download file');
    }
    const disposition = res.headers['content-disposition'] || '';
    const match = disposition.match(/filename=([^;]+)/);
    const name = match ? match[1].trim().replace(/"/g, '') : fallbackName;
    const blobUrl = window.URL.createObjectURL(new Blob([res.data]));
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(blobUrl);
  } catch (err) {
    const msg = err.message || 'Failed to download file';
    toast?.({ variant: 'destructive', title: msg });
    throw err;
  }
}

export default function PharmacyImportDialog({
  open,
  onOpenChange,
  onImported,
  title,
  entityLabel,
  importUrl,
  templateUrl,
  exportUrl,
  helpText,
  duplicateLabel = 'If a record already exists:',
  showDuplicateSelect = true,
  showAffectStock = false,
  defaultAffectStock = false,
  showFeedback,
}) {
  const { toast } = useToast();
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [onDuplicate, setOnDuplicate] = useState('skip');
  const [affectStock, setAffectStock] = useState(defaultAffectStock);
  const [analyzing, setAnalyzing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [summary, setSummary] = useState(null);
  const [done, setDone] = useState(null);

  const feedback = (msg, type) => {
    if (showFeedback) {
      showFeedback(msg, type);
    } else if (type === 'error') {
      toast({ variant: 'destructive', title: msg });
    } else {
      toast({ title: msg });
    }
  };

  const reset = () => {
    setFile(null);
    setSummary(null);
    setDone(null);
    setOnDuplicate('skip');
    setAffectStock(defaultAffectStock);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleClose = (v) => {
    if (importing || analyzing) return;
    if (!v) reset();
    onOpenChange(v);
  };

  const runImport = async (dryRun) => {
    if (!file) return;
    const setBusy = dryRun ? setAnalyzing : setImporting;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('dry_run', dryRun ? 'true' : 'false');
      fd.append('on_duplicate', onDuplicate);
      if (showAffectStock) {
        fd.append('affect_stock', affectStock ? 'true' : 'false');
      }
      const res = await axios.post(importUrl, fd, {
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

  const onFileChange = (e) => {
    const f = e.target.files?.[0] || null;
    setFile(f);
    setSummary(null);
    setDone(null);
  };

  const handleExport = async () => {
    if (!exportUrl) return;
    setExporting(true);
    try {
      const fallback = `${entityLabel.replace(/\s+/g, '_')}_export.xlsx`;
      await downloadPharmacyBlob(exportUrl, fallback, toast);
      feedback('Export downloaded');
    } catch {
      /* toast already shown */
    } finally {
      setExporting(false);
    }
  };

  const result = done || summary;
  const previewRows = result?.preview || [];
  const showSheetCol = previewRows.some((r) => r.sheet);
  const visiblePreview = previewRows.slice(0, PREVIEW_LIMIT);
  const hiddenCount = Math.max(0, previewRows.length - PREVIEW_LIMIT);

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5 text-indigo-500" /> {title}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 max-h-[75vh] overflow-y-auto pr-1">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-slate-500">Start from a template:</span>
            <Button
              variant="outline"
              size="sm"
              className="text-xs"
              onClick={() => downloadPharmacyBlob(templateUrl, `${entityLabel}_import_template.xlsx`, toast)}
            >
              <FileSpreadsheet className="h-3.5 w-3.5 mr-1.5" /> Excel template
            </Button>
            {exportUrl && (
              <Button
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={handleExport}
                disabled={exporting}
              >
                {exporting
                  ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                  : <Download className="h-3.5 w-3.5 mr-1.5" />}
                Export current {entityLabel}
              </Button>
            )}
          </div>

          {helpText && (
            <div className="text-xs text-slate-500 bg-slate-50 rounded-lg p-3 leading-relaxed">
              {helpText}
            </div>
          )}

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
                <button
                  type="button"
                  className="text-slate-400 hover:text-red-500"
                  onClick={() => {
                    setFile(null);
                    setSummary(null);
                    setDone(null);
                    if (fileInputRef.current) fileInputRef.current.value = '';
                  }}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <>
                <Upload className="h-8 w-8 text-slate-300 mx-auto mb-2" />
                <p className="text-sm text-slate-500 mb-2">Choose an .xlsx or .csv file to import {entityLabel}</p>
                <Button variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
                  Select File
                </Button>
              </>
            )}
          </div>

          {file && !done && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-3">
                {showDuplicateSelect && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-600">{duplicateLabel}</span>
                    <Select
                      value={onDuplicate}
                      onValueChange={(v) => { setOnDuplicate(v); setSummary(null); }}
                    >
                      <SelectTrigger className="h-8 w-36 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="skip">Skip it</SelectItem>
                        <SelectItem value="update">Update it</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
                {showAffectStock && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-600">Stock:</span>
                    <Select
                      value={affectStock ? 'deduct' : 'record'}
                      onValueChange={(v) => { setAffectStock(v === 'deduct'); setSummary(null); }}
                    >
                      <SelectTrigger className="h-8 w-44 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="record">Record only (no stock)</SelectItem>
                        <SelectItem value="deduct">Deduct stock</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
              <Button size="sm" variant="outline" onClick={() => runImport(true)} disabled={analyzing}>
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
                    <Badge variant="outline" className="text-[10px] shrink-0">
                      {e.sheet ? `${e.sheet} · ` : ''}row {e.row}
                    </Badge>
                    <span className="text-slate-600">{e.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {visiblePreview.length > 0 && (
            <div className="border border-slate-200 rounded-lg overflow-hidden">
              <div className="overflow-x-auto max-h-72">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-slate-50">
                    <tr className="text-left text-[11px] text-slate-400 uppercase tracking-wider border-b">
                      <th className="py-2 px-3 w-14">Row</th>
                      <th className="py-2 px-3">Key</th>
                      <th className="py-2 px-3">Name</th>
                      {showSheetCol && <th className="py-2 px-3">Sheet</th>}
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
                        {showSheetCol && (
                          <td className="py-1.5 px-3 text-slate-500">{r.sheet || '—'}</td>
                        )}
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
