import React from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import { Download, Eye, Loader2, Printer } from 'lucide-react';
import { fetchPdfBlobUrl, printPdfFromUrl } from '../../utils/printPdf';
import { useLabelPageSize } from '../../hooks/useLabelPageSize';

const labelPath = (inventoryId) => `/api/pharmacy/inventory/${inventoryId}/label.pdf`;
const BULK_LABEL_PATH = '/api/pharmacy/inventory/labels.pdf';

function labelRequestParams(extra = {}) {
  return { reprint: true, _v: Date.now(), ...extra };
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
 * Supports single-label print, combined PDF, or sequential one-by-one printing.
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
  const [selectedId, setSelectedId] = React.useState(null);
  const [pdfUrl, setPdfUrl] = React.useState(null);
  const [loadingPreview, setLoadingPreview] = React.useState(false);
  const [busy, setBusy] = React.useState(null);
  const [error, setError] = React.useState('');
  const { aspectRatio, pageLabel, isLandscape, stickersAcross } = useLabelPageSize('pharmacy');
  const useBulkPreview = printable.length > 1;

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
      if (!open) {
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
        if (useBulkPreview) {
          const ids = printable.map((l) => l.inventoryId);
          const res = await axios.post(
            BULK_LABEL_PATH,
            { inventory_ids: ids },
            { params: labelRequestParams(), responseType: 'blob' },
          );
          url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
        } else {
          url = await fetchPdfBlobUrl(labelPath(selectedId), { params: labelRequestParams() });
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
  }, [open, selectedId, useBulkPreview, printable]);

  const printOne = async (inventoryId) => {
    setError('');
    setBusy(inventoryId);
    try {
      await printPdfFromUrl(labelPath(inventoryId), { params: labelRequestParams(), onError: setError });
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
      const res = await axios.post(
        BULK_LABEL_PATH,
        { inventory_ids: ids },
        { params: labelRequestParams(), responseType: 'blob' },
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
    for (const line of printable) {
      const ok = await printPdfFromUrl(
        labelPath(line.inventoryId),
        { params: labelRequestParams(), onError: setError },
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
        { params: labelRequestParams(), responseType: 'blob' },
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

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose?.()}>
      <DialogContent className={`max-w-3xl max-h-[90vh] flex flex-col gap-3 ${isLandscape ? 'sm:max-w-4xl' : ''}`}>
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
                  {useBulkPreview ? `Preview — all ${printable.length} in one row` : 'Preview'}
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

            <p className="text-xs text-muted-foreground">
              PDF page: {pageLabel}.
              {stickersAcross > 1 && printable.length > 1 ? (
                <>
                  {' '}With {stickersAcross} across the roll, use <strong>Print combined PDF</strong> so all
                  barcodes print side-by-side on one peel line.
                </>
              ) : (
                <> In the print dialog use that custom paper size at 100% scale.</>
              )}
            </p>
          </>
        )}

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex flex-wrap gap-2 justify-end pt-1">
          {printable.length > 0 && (
            <>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={isBusy}
                onClick={downloadCombined}
              >
                {busy === 'download' ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <Download className="h-4 w-4 mr-1" />
                )}
                Download all
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={isBusy}
                onClick={printAllCombined}
              >
                {busy === 'combined' ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <Printer className="h-4 w-4 mr-1" />
                )}
                {stickersAcross > 1 ? 'Print all (one row)' : 'Print combined PDF'}
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={isBusy || printable.length < 2}
                onClick={printAllSequential}
              >
                {busy === 'sequence' ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <Printer className="h-4 w-4 mr-1" />
                )}
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
