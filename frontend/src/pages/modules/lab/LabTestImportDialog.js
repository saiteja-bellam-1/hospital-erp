import React, { useRef, useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../components/ui/dialog';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '../../../components/ui/select';
import {
  Upload, FileSpreadsheet, FileText, Loader2, CheckCircle2,
  AlertTriangle, RefreshCw, X,
} from 'lucide-react';

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

export default function LabTestImportDialog({ open, onOpenChange, onImported, showFeedback }) {
  const fileInputRef = useRef(null);
  const [file, setFile] = useState(null);
  const [onDuplicate, setOnDuplicate] = useState('skip');
  const [analyzing, setAnalyzing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [summary, setSummary] = useState(null); // dry-run result
  const [done, setDone] = useState(null);        // committed result

  const reset = () => {
    setFile(null);
    setSummary(null);
    setDone(null);
    setOnDuplicate('skip');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleClose = (v) => {
    if (importing || analyzing) return;
    if (!v) reset();
    onOpenChange(v);
  };

  const downloadBlob = async (url, fallbackName) => {
    try {
      const res = await axios.get(url, { responseType: 'blob' });
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
      showFeedback?.('Failed to download file', 'error');
    }
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
      const res = await axios.post('/api/lab/tests/import', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      if (dryRun) {
        setSummary(res.data);
      } else {
        setDone(res.data);
        onImported?.();
        showFeedback?.(
          `Imported: ${res.data.created} new, ${res.data.updated} updated, ${res.data.skipped} skipped`,
        );
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      showFeedback?.(typeof detail === 'string' ? detail : 'Import failed', 'error');
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

  const result = done || summary;

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5 text-indigo-500" /> Import Lab Tests
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 max-h-[75vh] overflow-y-auto pr-1">
          {/* Templates */}
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-slate-500">Start from a template:</span>
            <Button variant="outline" size="sm" className="text-xs"
              onClick={() => downloadBlob('/api/lab/tests/import/template', 'lab_tests_import_template.xlsx')}>
              <FileSpreadsheet className="h-3.5 w-3.5 mr-1.5" /> Excel template
            </Button>
            <Button variant="outline" size="sm" className="text-xs"
              onClick={() => downloadBlob('/api/lab/tests/import/sample-csv', 'lab_tests_sample.csv')}>
              <FileText className="h-3.5 w-3.5 mr-1.5" /> Sample CSV
            </Button>
          </div>

          <div className="text-xs text-slate-500 bg-slate-50 rounded-lg p-3 leading-relaxed">
            Fill the <span className="font-medium">Tests</span> sheet (required: test_code, name, category, cost).
            Missing categories and sample types are created automatically. Add reference ranges on the
            optional <span className="font-medium">Parameters</span> sheet of the Excel template.
            CSV imports tests only.
          </div>

          {/* File picker */}
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
                <button className="text-slate-400 hover:text-red-500"
                  onClick={() => { setFile(null); setSummary(null); setDone(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}>
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : (
              <>
                <Upload className="h-8 w-8 text-slate-300 mx-auto mb-2" />
                <p className="text-sm text-slate-500 mb-2">Choose an .xlsx or .csv file to import</p>
                <Button variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
                  Select File
                </Button>
              </>
            )}
          </div>

          {/* Duplicate handling + analyze */}
          {file && !done && (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-600">If a test code already exists:</span>
                <Select value={onDuplicate} onValueChange={(v) => { setOnDuplicate(v); setSummary(null); }}>
                  <SelectTrigger className="h-8 w-36 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="skip">Skip it</SelectItem>
                    <SelectItem value="update">Update it</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button size="sm" variant="outline" onClick={() => runImport(true)} disabled={analyzing}>
                {analyzing ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-2" />}
                Preview
              </Button>
            </div>
          )}

          {/* Summary counts */}
          {result && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <SummaryStat label="New" value={result.created} color="text-emerald-600" />
              <SummaryStat label="Update" value={result.updated} color="text-blue-600" />
              <SummaryStat label="Skipped" value={result.skipped} color="text-slate-500" />
              <SummaryStat label="Errors" value={result.error_count} color="text-red-600" />
            </div>
          )}

          {/* Auto-created notice */}
          {result && (result.categories_created?.length > 0 || result.sample_types_created?.length > 0) && (
            <div className="text-xs text-slate-600 bg-indigo-50/50 border border-indigo-100 rounded-lg p-3 space-y-1">
              {result.categories_created?.length > 0 && (
                <div><span className="font-medium">Categories {done ? 'created' : 'to create'}:</span> {result.categories_created.join(', ')}</div>
              )}
              {result.sample_types_created?.length > 0 && (
                <div><span className="font-medium">Sample types {done ? 'created' : 'to create'}:</span> {result.sample_types_created.join(', ')}</div>
              )}
            </div>
          )}

          {/* Errors list */}
          {result?.errors?.length > 0 && (
            <div className="border border-red-100 rounded-lg overflow-hidden">
              <div className="flex items-center gap-2 px-3 py-2 bg-red-50 text-red-700 text-xs font-semibold">
                <AlertTriangle className="h-3.5 w-3.5" />
                {result.errors.length} row{result.errors.length !== 1 ? 's' : ''} need fixing
              </div>
              <div className="max-h-40 overflow-y-auto divide-y divide-red-50">
                {result.errors.map((e, i) => (
                  <div key={i} className="flex items-start gap-2 px-3 py-1.5 text-xs">
                    <Badge variant="outline" className="text-[10px] shrink-0">{e.sheet} · row {e.row}</Badge>
                    <span className="text-slate-600">{e.message}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Preview table */}
          {result?.preview?.length > 0 && (
            <div className="border border-slate-200 rounded-lg overflow-hidden">
              <div className="overflow-x-auto max-h-72">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-slate-50">
                    <tr className="text-left text-[11px] text-slate-400 uppercase tracking-wider border-b">
                      <th className="py-2 px-3 w-14">Row</th>
                      <th className="py-2 px-3">Code</th>
                      <th className="py-2 px-3">Name</th>
                      <th className="py-2 px-3">Category</th>
                      <th className="py-2 px-3 w-16 text-center">Params</th>
                      <th className="py-2 px-3 w-24">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.preview.map((r, i) => (
                      <tr key={i} className="border-b border-slate-50 last:border-0">
                        <td className="py-1.5 px-3 text-slate-400 font-mono">{r.row}</td>
                        <td className="py-1.5 px-3 font-mono text-slate-600">{r.test_code}</td>
                        <td className="py-1.5 px-3 text-slate-700">
                          {r.name}
                          {r.status === 'error' && r.message && (
                            <span className="block text-[11px] text-red-500">{r.message}</span>
                          )}
                        </td>
                        <td className="py-1.5 px-3 text-slate-500">{r.category || '–'}</td>
                        <td className="py-1.5 px-3 text-center text-slate-500">{r.parameter_count || 0}</td>
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
            </div>
          )}

          {/* Actions */}
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
