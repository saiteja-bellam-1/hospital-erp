import React from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Download, Eye, Loader2, Printer, RefreshCw } from 'lucide-react';
import { fetchPdfBlobUrl, printPdfFromUrl } from '../../utils/printPdf';
import { usePdfPrintSettings } from '../../hooks/usePdfPrintSettings';
import { applyThermalRollLayout } from '../../utils/labelPageSize';
import {
  LABEL_SIZE_PRESETS,
  layoutPageLabel,
  layoutToQueryParams,
  rememberLabelPrintLayout,
  seedLabelPrintLayout,
} from '../../utils/labelPrintLayout';

const labelPath = (inventoryId) => `/api/pharmacy/inventory/${inventoryId}/label.pdf`;
const BULK_LABEL_PATH = '/api/pharmacy/inventory/labels.pdf';

function labelRequestParams(layoutParams, extra = {}) {
  return { reprint: true, _v: Date.now(), ...layoutParams, ...extra };
}

/** Build printable label rows from purchase line items. */
export function buildPurchaseLabelLines(items, medicineLookup = {}) {
  return (items || []).map((it, idx) => {
    const inventoryId = it.inventory_id ?? it.inventoryId ?? null;
    const medicineName = it.medicine_name
      || medicineLookup[it.medicine_id]?.name
      || (it.medicine_id ? `Medicine #${it.medicine_id}` : 'Unknown');
    return {
      key: inventoryId || `line-${idx}`,
      inventoryId,
      medicineName,
      batchNumber: it.batch_number || '—',
      lineNumber: idx + 1,
    };
  });
}

/**
 * Popup to preview and print pharmacy batch labels for a confirmed purchase.
 * Size / sheet controls live in-dialog (same pattern as BarcodeLabelPrintDialog).
 */
export default function PurchaseLabelsDialog({
  open,
  onClose,
  title = 'Print batch labels',
  lines = [],
}) {
  const printable = React.useMemo(
    () => lines.filter((l) => l.inventoryId),
    [lines],
  );
  const { settings, isLoading: settingsLoading } = usePdfPrintSettings();
  const [layout, setLayout] = React.useState(() => seedLabelPrintLayout('pharmacy', null, { allowMultiUp: true }));
  const [layoutReady, setLayoutReady] = React.useState(false);
  const [selectedId, setSelectedId] = React.useState(null);
  const [pdfUrl, setPdfUrl] = React.useState(null);
  const [loadingPreview, setLoadingPreview] = React.useState(false);
  const [busy, setBusy] = React.useState(null);
  const [error, setError] = React.useState('');
  const [loadKey, setLoadKey] = React.useState(0);

  const useBulkPreview = printable.length > 1;
  const layoutParams = React.useMemo(
    () => layoutToQueryParams(layout, { forceSingle: !useBulkPreview }),
    [layout, useBulkPreview],
  );
  const pageLabel = layoutPageLabel(layout, { forceSingle: !useBulkPreview });
  const aspectRatio = `${layoutParams.width_mm} / ${layoutParams.height_mm}`;
  const stickersAcross = Math.max(1, Number(layoutParams.labels_per_row) || 1);

  React.useEffect(() => {
    if (!open) {
      setLayoutReady(false);
      return;
    }
    if (settingsLoading && settings == null) return;
    setLayout(seedLabelPrintLayout('pharmacy', settings, { allowMultiUp: true }));
    setLayoutReady(true);
    setLoadKey(Date.now());
  }, [open, settings, settingsLoading]);

  React.useEffect(() => {
    if (!open) {
      setSelectedId(null);
      setPdfUrl((prev) => {
        if (prev) window.URL.revokeObjectURL(prev);
        return null;
      });
      setError('');
      setBusy(null);
      return;
    }
    if (printable.length && !printable.some((l) => l.inventoryId === selectedId)) {
      setSelectedId(printable[0].inventoryId);
    }
  }, [open, printable, selectedId]);

  React.useEffect(() => {
    let cancelled = false;
    let createdUrl = null;
    const load = async () => {
      if (!open || !layoutReady) {
        setPdfUrl((prev) => {
          if (prev) window.URL.revokeObjectURL(prev);
          return null;
        });
        return;
      }
      if (!useBulkPreview && !selectedId) {
        setPdfUrl((prev) => {
          if (prev) window.URL.revokeObjectURL(prev);
          return null;
        });
        return;
      }
      setLoadingPreview(true);
      setError('');
      try {
        let url;
        const params = labelRequestParams(layoutParams, { _v: loadKey });
        if (useBulkPreview) {
          const ids = printable.map((l) => l.inventoryId);
          const res = await axios.post(
            BULK_LABEL_PATH,
            { inventory_ids: ids },
            { params, responseType: 'blob' },
          );
          url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
        } else {
          url = await fetchPdfBlobUrl(labelPath(selectedId), { params });
        }
        if (cancelled) {
          window.URL.revokeObjectURL(url);
          return;
        }
        createdUrl = url;
        setPdfUrl((prev) => {
          if (prev) window.URL.revokeObjectURL(prev);
          return url;
        });
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Could not load label preview');
        }
      } finally {
        if (!cancelled) setLoadingPreview(false);
      }
    };
    load();
    return () => {
      cancelled = true;
      if (createdUrl) window.URL.revokeObjectURL(createdUrl);
    };
  }, [open, selectedId, useBulkPreview, printable, layoutParams, layoutReady, loadKey]);

  const updateLayout = (patch) => {
    setLayout((prev) => applyThermalRollLayout({ ...prev, ...patch }));
  };

  const printOne = async (inventoryId) => {
    setError('');
    setBusy(inventoryId);
    try {
      rememberLabelPrintLayout('pharmacy', layout);
      await printPdfFromUrl(labelPath(inventoryId), {
        params: labelRequestParams(layoutToQueryParams(layout, { forceSingle: true })),
        onError: setError,
      });
    } finally {
      setBusy(null);
    }
  };

  const printAllCombined = async () => {
    const ids = printable.map((l) => l.inventoryId);
    if (!ids.length) return;
    setBusy('combined');
    setError('');
    try {
      rememberLabelPrintLayout('pharmacy', layout);
      const res = await axios.post(
        BULK_LABEL_PATH,
        { inventory_ids: ids },
        { params: labelRequestParams(layoutParams), responseType: 'blob' },
      );
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      await printPdfFromUrl(url, { onError: setError });
      window.URL.revokeObjectURL(url);
    } catch {
      setError('Could not print combined labels');
    } finally {
      setBusy(null);
    }
  };

  const printAllSequential = async () => {
    setBusy('sequence');
    setError('');
    rememberLabelPrintLayout('pharmacy', layout);
    const singleParams = layoutToQueryParams(layout, { forceSingle: true });
    for (const line of printable) {
      const ok = await printPdfFromUrl(
        labelPath(line.inventoryId),
        { params: labelRequestParams(singleParams), onError: setError },
      );
      if (!ok) break;
    }
    setBusy(null);
  };

  const downloadCombined = async () => {
    const ids = printable.map((l) => l.inventoryId);
    if (!ids.length) return;
    setBusy('download');
    setError('');
    try {
      const res = await axios.post(
        BULK_LABEL_PATH,
        { inventory_ids: ids },
        { params: labelRequestParams(layoutParams), responseType: 'blob' },
      );
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const a = document.createElement('a');
      a.href = url;
      a.download = 'purchase_labels.pdf';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      setError('Download failed');
    } finally {
      setBusy(null);
    }
  };

  const isBusy = busy != null;
  const numVal = (v) => (v == null || Number.isNaN(v) ? '' : v);

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose?.()}>
      <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col gap-3 sm:max-w-4xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        {printable.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No batch labels are linked to this purchase yet. Confirm the purchase first, or check
            that each line has a stock batch.
          </p>
        ) : (
          <>
            <div className="rounded-lg border bg-slate-50/80 p-3 flex flex-wrap items-end gap-3">
              <div className="min-w-[10rem]">
                <Label className="text-xs">Preset</Label>
                <Select
                  onValueChange={(key) => {
                    const p = LABEL_SIZE_PRESETS[key];
                    if (p) {
                      updateLayout(p);
                      setLoadKey(Date.now());
                    }
                  }}
                >
                  <SelectTrigger className="h-8 text-xs bg-white">
                    <SelectValue placeholder="Match sticker size…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="thermal_38x25">Thermal 38×25 mm (1 across)</SelectItem>
                    <SelectItem value="thermal_38x25_2up">Thermal 38×25 mm (2 across)</SelectItem>
                    <SelectItem value="thermal_38x25_3up">Thermal 38×25 mm (3 across)</SelectItem>
                    <SelectItem value="thermal_50x30">Thermal 50×30 mm</SelectItem>
                    <SelectItem value="thermal_70x40">Thermal 70×40 mm</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Width (mm)</Label>
                <Input
                  className="h-8 w-24 bg-white"
                  type="number"
                  value={numVal(layout.width_mm)}
                  onChange={(e) => updateLayout({ width_mm: parseFloat(e.target.value) || 0 })}
                  onBlur={() => setLoadKey(Date.now())}
                />
              </div>
              <div>
                <Label className="text-xs">Height (mm)</Label>
                <Input
                  className="h-8 w-24 bg-white"
                  type="number"
                  value={numVal(layout.height_mm)}
                  onChange={(e) => updateLayout({ height_mm: parseFloat(e.target.value) || 0 })}
                  onBlur={() => setLoadKey(Date.now())}
                />
              </div>
              <div>
                <Label className="text-xs">Across</Label>
                <Select
                  value={String(Math.max(1, Number(layout.labels_per_row) || 1))}
                  onValueChange={(v) => {
                    updateLayout({ labels_per_row: parseInt(v, 10), labels_per_column: 1 });
                    setLoadKey(Date.now());
                  }}
                >
                  <SelectTrigger className="h-8 w-20 text-xs bg-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">1</SelectItem>
                    <SelectItem value="2">2</SelectItem>
                    <SelectItem value="3">3</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <Button type="button" variant="outline" size="sm" className="h-8" onClick={() => setLoadKey(Date.now())}>
                <RefreshCw className="h-3.5 w-3.5 mr-1" /> Update preview
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 min-h-0 flex-1 overflow-hidden">
              <div className="border rounded-lg overflow-hidden flex flex-col min-h-[12rem] md:max-h-[22rem]">
                <p className="text-xs font-medium text-muted-foreground px-3 py-2 border-b bg-muted/30">
                  {printable.length} batch{printable.length === 1 ? '' : 'es'}
                </p>
                <ul className="overflow-y-auto flex-1 divide-y text-sm">
                  {lines.map((line) => {
                    const canPrint = Boolean(line.inventoryId);
                    const active = line.inventoryId === selectedId;
                    return (
                      <li
                        key={line.key}
                        className={`px-3 py-2 flex items-start gap-2 ${active ? 'bg-primary/5' : ''} ${canPrint ? '' : 'opacity-60'}`}
                      >
                        <button
                          type="button"
                          className="flex-1 min-w-0 text-left"
                          disabled={!canPrint}
                          onClick={() => canPrint && setSelectedId(line.inventoryId)}
                        >
                          <span className="font-medium block truncate">
                            {line.lineNumber}. {line.medicineName}
                          </span>
                          <span className="text-xs text-muted-foreground font-mono">
                            Batch {line.batchNumber}
                          </span>
                          {!canPrint && (
                            <span className="text-xs text-amber-700 block">No stock batch linked</span>
                          )}
                        </button>
                        {canPrint && (
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            className="shrink-0 h-8"
                            disabled={isBusy}
                            onClick={() => printOne(line.inventoryId)}
                          >
                            {busy === line.inventoryId ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Printer className="h-3.5 w-3.5" />
                            )}
                          </Button>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>

              <div className="border rounded-lg flex flex-col min-h-[12rem] md:min-h-[22rem] bg-white">
                <p className="text-xs font-medium text-muted-foreground px-3 py-2 border-b bg-muted/30 flex items-center gap-1">
                  <Eye className="h-3.5 w-3.5" />
                  {useBulkPreview ? `Preview — all ${printable.length}` : 'Preview'}
                </p>
                <div className="flex-1 p-2 min-h-0">
                  {loadingPreview && (
                    <p className="text-sm text-muted-foreground p-2">Loading preview…</p>
                  )}
                  {!loadingPreview && pdfUrl && (
                    <iframe
                      title="Label preview"
                      src={pdfUrl}
                      className="w-full border rounded"
                      style={{ aspectRatio, maxHeight: '14rem' }}
                    />
                  )}
                  {!loadingPreview && !pdfUrl && selectedId && (
                    <p className="text-sm text-muted-foreground p-2">Preview unavailable</p>
                  )}
                  {!selectedId && (
                    <p className="text-sm text-muted-foreground p-2">Select a batch to preview</p>
                  )}
                </div>
              </div>
            </div>

            <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">
              PDF page: <span className="font-mono">{pageLabel}</span>.
              Choose your label printer in the OS dialog; paper size = that page; scale 100% (not Fit to page).
              {stickersAcross > 1 && printable.length > 1 ? (
                <> Use <strong>Print all (one row)</strong> to fill {stickersAcross} across.</>
              ) : null}
            </div>
          </>
        )}

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex flex-wrap gap-2 justify-end pt-1">
          {printable.length > 0 && (
            <>
              <Button type="button" variant="outline" size="sm" disabled={isBusy} onClick={downloadCombined}>
                {busy === 'download' ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Download className="h-4 w-4 mr-1" />}
                Download all
              </Button>
              <Button type="button" size="sm" disabled={isBusy} onClick={printAllCombined}>
                {busy === 'combined' ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Printer className="h-4 w-4 mr-1" />}
                {stickersAcross > 1 ? 'Print all (one row)' : 'Print combined PDF'}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={isBusy || printable.length < 2}
                onClick={printAllSequential}
              >
                {busy === 'sequence' ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Printer className="h-4 w-4 mr-1" />}
                Print one-by-one
              </Button>
            </>
          )}
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
