import React from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Download, Loader2, Printer, RefreshCw } from 'lucide-react';
import { printPdfFromUrl } from '../utils/printPdf';
import { usePdfPrintSettings } from '../hooks/usePdfPrintSettings';
import {
  LABEL_SIZE_PRESETS,
  hospitalSettingsPayloadKey,
  layoutPageLabel,
  layoutToQueryParams,
  rememberLabelPrintLayout,
  seedLabelPrintLayout,
} from '../utils/labelPrintLayout';
import { applyThermalRollLayout } from '../utils/labelPageSize';

const EMPTY_QUERY_PARAMS = {};
const numVal = (v) => (v == null || Number.isNaN(v) ? '' : v);

/**
 * Dedicated barcode / thermal-label print dialog (document-print style).
 *
 * Exposes sticker size, sheet mode, and stickers-across controls so staff can
 * match physical stock. PDF regenerates with layout query params.
 *
 * Props:
 *   allowMultiUp — when true (default), show Across + multi-up presets
 */
export default function BarcodeLabelPrintDialog({
  open,
  onClose,
  title = 'Print barcode label',
  path,
  params = {},
  filename = 'label.pdf',
  bulkBody = null,
  labelKind = 'pharmacy',
  allowMultiUp = true,
}) {
  // Always send the dialog's across/size choices; do not force 1-up in the query.
  const { settings, isLoading: settingsLoading, refetch } = usePdfPrintSettings();
  const [layout, setLayout] = React.useState(() => seedLabelPrintLayout(labelKind, null, { allowMultiUp: true }));
  const [layoutReady, setLayoutReady] = React.useState(false);
  const [rememberSize, setRememberSize] = React.useState(true);
  const [saveHospitalDefault, setSaveHospitalDefault] = React.useState(false);
  const [savingDefault, setSavingDefault] = React.useState(false);
  const [pdfUrl, setPdfUrl] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState('');
  const [loadKey, setLoadKey] = React.useState(0);
  const queryParams = params ?? EMPTY_QUERY_PARAMS;

  React.useEffect(() => {
    if (!open) {
      setLayoutReady(false);
      return;
    }
    if (settingsLoading && settings == null) return;
    setLayout(seedLabelPrintLayout(labelKind, settings, { allowMultiUp: true }));
    setLayoutReady(true);
    setLoadKey(Date.now());
  }, [open, labelKind, settings, settingsLoading]);

  const layoutParams = React.useMemo(
    () => layoutToQueryParams(layout, { forceSingle: false }),
    [layout],
  );

  const pageLabel = layoutPageLabel(layout, { forceSingle: false });
  const stickersAcross = Math.max(1, Number(layoutParams.labels_per_row) || 1);
  const isLandscape = Number(layoutParams.width_mm) > Number(layoutParams.height_mm)
    || (stickersAcross > 1 && (layout.sheet_mode || 'thermal') === 'thermal');
  const aspectRatio = `${layoutParams.width_mm} / ${layoutParams.height_mm}`;

  const requestConfig = React.useMemo(() => ({
    params: {
      ...queryParams,
      ...layoutParams,
      _v: loadKey,
      ...(bulkBody ? { reprint: queryParams.reprint ?? true } : {}),
    },
    responseType: 'blob',
  }), [queryParams, layoutParams, bulkBody, loadKey]);

  React.useEffect(() => {
    let cancelled = false;
    let createdUrl = null;
    const load = async () => {
      if (!open || !path || !layoutReady) return;
      setLoading(true);
      setError('');
      try {
        const res = bulkBody
          ? await axios.post(path, bulkBody, requestConfig)
          : await axios.get(path, requestConfig);
        if (cancelled) return;
        const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
        createdUrl = url;
        setPdfUrl((prev) => {
          if (prev) window.URL.revokeObjectURL(prev);
          return url;
        });
      } catch (err) {
        if (!cancelled) {
          const detail = err.response?.data;
          let msg = 'Could not load label PDF';
          if (detail instanceof Blob) {
            try {
              const j = JSON.parse(await detail.text());
              if (typeof j.detail === 'string') msg = j.detail;
            } catch { /* ignore */ }
          } else if (typeof detail?.detail === 'string') {
            msg = detail.detail;
          }
          setError(msg);
          setPdfUrl((prev) => {
            if (prev) window.URL.revokeObjectURL(prev);
            return null;
          });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
      if (createdUrl) window.URL.revokeObjectURL(createdUrl);
    };
  }, [open, path, bulkBody, requestConfig, layoutReady]);

  React.useEffect(() => {
    if (!open) {
      setPdfUrl((prev) => {
        if (prev) window.URL.revokeObjectURL(prev);
        return null;
      });
      setError('');
    }
  }, [open]);

  const updateLayout = (patch) => {
    setLayout((prev) => applyThermalRollLayout({ ...prev, ...patch }));
  };

  const applyPreset = (key) => {
    const p = LABEL_SIZE_PRESETS[key];
    if (!p) return;
    updateLayout(p);
    setLoadKey(Date.now());
  };

  const reloadPreview = () => setLoadKey(Date.now());

  const persistBeforePrint = async () => {
    if (rememberSize) rememberLabelPrintLayout(labelKind, layout);
    if (saveHospitalDefault) {
      setSavingDefault(true);
      try {
        const key = hospitalSettingsPayloadKey(labelKind);
        await axios.put('/api/hospital/print-settings', {
          [key]: {
            ...layout,
            ...layoutToQueryParams(layout, { forceSingle: false }),
          },
        });
        refetch?.();
      } catch (err) {
        setError(typeof err.response?.data?.detail === 'string'
          ? err.response.data.detail
          : 'Could not save hospital default (need Appearance permission)');
      } finally {
        setSavingDefault(false);
      }
    }
  };

  const handlePrint = async () => {
    await persistBeforePrint();
    if (pdfUrl) {
      await printPdfFromUrl(pdfUrl, { onError: (msg) => setError(msg) });
      return;
    }
    if (!path) return;
    try {
      const res = bulkBody
        ? await axios.post(path, bulkBody, requestConfig)
        : await axios.get(path, requestConfig);
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      await printPdfFromUrl(url, { onError: (msg) => setError(msg) });
      window.URL.revokeObjectURL(url);
    } catch {
      setError('Print failed');
    }
  };

  const handleDownload = async () => {
    await persistBeforePrint();
    if (!pdfUrl) return;
    const a = document.createElement('a');
    a.href = pdfUrl;
    a.download = filename;
    a.click();
  };

  const isThermal = (layout.sheet_mode || 'thermal') === 'thermal';

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose?.()}>
      <DialogContent className="max-w-3xl max-h-[92vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Hospital defaults live under{' '}
            <Link to="/dashboard/hospital-admin/appearance" className="underline hover:text-foreground">
              Appearance → Label printing
            </Link>
            . Change size below to match your physical stickers — preview regenerates for this print only.
          </p>

          <div className="rounded-lg border bg-slate-50/80 p-3 space-y-3">
            <div className="flex flex-wrap items-end gap-3">
              <div className="min-w-[10rem]">
                <Label className="text-xs">Preset</Label>
                <Select onValueChange={applyPreset}>
                  <SelectTrigger className="h-8 text-xs bg-white">
                    <SelectValue placeholder="Match sticker size…" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="thermal_70x40">Thermal 70×40 mm (1 across)</SelectItem>
                    <SelectItem value="thermal_50x30">Thermal 50×30 mm (1 across)</SelectItem>
                    <SelectItem value="thermal_40x30">Thermal 40×30 mm (1 across)</SelectItem>
                    <SelectItem value="thermal_38x25">Thermal 38×25 mm (1 across)</SelectItem>
                    <SelectItem value="thermal_38x25_2up">Thermal 38×25 mm (2 across)</SelectItem>
                    <SelectItem value="thermal_38x25_3up">Thermal 38×25 mm (3 across)</SelectItem>
                    <SelectItem value="avery_3x8">Avery 3×8 on A4</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Width (mm)</Label>
                <Input
                  className="h-8 w-24 bg-white"
                  type="number"
                  min={20}
                  max={120}
                  step={0.1}
                  value={numVal(layout.width_mm)}
                  onChange={(e) => updateLayout({ width_mm: parseFloat(e.target.value) || 0 })}
                  onBlur={reloadPreview}
                />
              </div>
              <div>
                <Label className="text-xs">Height (mm)</Label>
                <Input
                  className="h-8 w-24 bg-white"
                  type="number"
                  min={20}
                  max={120}
                  step={0.1}
                  value={numVal(layout.height_mm)}
                  onChange={(e) => updateLayout({ height_mm: parseFloat(e.target.value) || 0 })}
                  onBlur={reloadPreview}
                />
              </div>
              <div>
                <Label className="text-xs">Mode</Label>
                <Select
                  value={layout.sheet_mode || 'thermal'}
                  onValueChange={(v) => {
                    updateLayout({ sheet_mode: v });
                    setLoadKey(Date.now());
                  }}
                >
                  <SelectTrigger className="h-8 w-32 text-xs bg-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="thermal">Thermal roll</SelectItem>
                    <SelectItem value="avery">Avery sheet</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {isThermal && (
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
              )}
              <Button type="button" variant="outline" size="sm" className="h-8" onClick={reloadPreview} disabled={loading}>
                <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
                Update preview
              </Button>
            </div>

            <div className="flex flex-wrap gap-4 text-xs text-gray-600">
              <label className="inline-flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 rounded border-gray-300"
                  checked={rememberSize}
                  onChange={(e) => setRememberSize(e.target.checked)}
                />
                Remember size on this browser
              </label>
              <label className="inline-flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="h-3.5 w-3.5 rounded border-gray-300"
                  checked={saveHospitalDefault}
                  onChange={(e) => setSaveHospitalDefault(e.target.checked)}
                />
                Also save as hospital default
              </label>
            </div>
          </div>

          <div className="border rounded-lg overflow-hidden bg-gray-50 flex items-center justify-center min-h-[200px]">
            {loading && (
              <div className="flex items-center gap-2 text-sm text-gray-500 py-12">
                <Loader2 className="h-4 w-4 animate-spin" /> Loading label…
              </div>
            )}
            {!loading && error && <p className="text-sm text-red-600 p-4">{error}</p>}
            {!loading && !error && pdfUrl && (
              <iframe
                key={pdfUrl}
                title={title}
                src={pdfUrl}
                className="w-full border-0 bg-white"
                style={{ aspectRatio, maxHeight: 'min(360px, 45vh)', maxWidth: isLandscape ? '100%' : '420px' }}
              />
            )}
          </div>

          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950 space-y-1">
            <p>
              <span className="font-semibold">PDF page:</span>{' '}
              <span className="font-mono">{pageLabel}</span>
              {isThermal && stickersAcross > 1
                ? ` (${stickersAcross} stickers across — one label prints in the left slot; right slots stay blank unless you print a combined batch)`
                : isThermal
                  ? ' (one sticker)'
                  : ''}.
            </p>
            <p>
              In the system print dialog: choose your <span className="font-medium">label printer</span>,
              set paper / custom size to <span className="font-mono">{pageLabel}</span>,
              scale <span className="font-medium">100% / Actual size</span> — not Fit to page.
            </p>
          </div>

          <div className="flex flex-wrap gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
            <Button variant="outline" size="sm" onClick={handleDownload} disabled={!pdfUrl || loading || savingDefault}>
              <Download className="h-4 w-4 mr-1" /> Download
            </Button>
            <Button size="sm" className="bg-blue-600 hover:bg-blue-700" onClick={handlePrint} disabled={(!path && !pdfUrl) || loading || savingDefault}>
              {(loading || savingDefault) ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Printer className="h-4 w-4 mr-1" />}
              Print
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
