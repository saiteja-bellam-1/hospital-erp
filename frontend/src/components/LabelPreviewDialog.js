import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Download, Printer } from 'lucide-react';
import axios from 'axios';
import { printPdfFromUrl } from '../utils/printPdf';
import { useLabelPageSize } from '../hooks/useLabelPageSize';

const EMPTY_QUERY_PARAMS = {};

/**
 * Label PDF preview — no letterhead; page size comes from server label settings.
 */
export default function LabelPreviewDialog({
  open,
  onClose,
  title = 'Label Preview',
  path,
  params = {},
  filename = 'label.pdf',
  bulkBody = null,
  labelKind = 'pharmacy',
}) {
  const { page, aspectRatio, isLandscape, pageLabel } = useLabelPageSize(labelKind);
  const [pdfUrl, setPdfUrl] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState('');
  const [loadKey, setLoadKey] = React.useState(0);
  const queryParams = params ?? EMPTY_QUERY_PARAMS;

  React.useEffect(() => {
    if (open) setLoadKey(Date.now());
  }, [open, path, bulkBody, queryParams]);

  const requestConfig = React.useMemo(() => ({
    params: {
      ...queryParams,
      _v: loadKey,
      ...(bulkBody ? { reprint: queryParams.reprint ?? true } : {}),
    },
    responseType: 'blob',
  }), [queryParams, bulkBody, loadKey]);

  React.useEffect(() => {
    let cancelled = false;
    let createdUrl = null;
    const load = async () => {
      if (!open || !path) return;
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
  }, [open, path, bulkBody, requestConfig]);

  React.useEffect(() => {
    if (!open) {
      setPdfUrl((prev) => {
        if (prev) window.URL.revokeObjectURL(prev);
        return null;
      });
      setError('');
    }
  }, [open]);

  const handlePrint = async () => {
    if (pdfUrl) {
      await printPdfFromUrl(pdfUrl, { onError: (msg) => setError(msg) });
      return;
    }
    if (!path) return;
    if (bulkBody) {
      try {
        const res = await axios.post(path, bulkBody, requestConfig);
        const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
        await printPdfFromUrl(url, { onError: (msg) => setError(msg) });
        window.URL.revokeObjectURL(url);
      } catch (err) {
        setError('Print failed');
      }
    } else {
      printPdfFromUrl(path, { params: queryParams, onError: (msg) => setError(msg) });
    }
  };

  const handleDownload = () => {
    if (!pdfUrl) return;
    const a = document.createElement('a');
    a.href = pdfUrl;
    a.download = filename;
    a.click();
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose?.()}>
      <DialogContent className={isLandscape ? 'max-w-2xl' : 'max-w-md'}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          {loading && <p className="text-sm text-gray-500">Loading label…</p>}
          {error && <p className="text-sm text-red-600">{error}</p>}
          {pdfUrl && (
            <iframe
              title={title}
              src={pdfUrl}
              className="w-full border rounded bg-white"
              style={{ aspectRatio, maxHeight: 'min(280px, 50vh)' }}
            />
          )}
          <p className="text-xs text-gray-500">
            PDF page size: <span className="font-medium text-gray-700">{pageLabel}</span>
            {isLandscape ? ' (landscape)' : ''}.
            {' '}In the OS print dialog pick this exact custom paper size, scale 100%, not Fit to page.
            {page.width_mm > 50 && (
              <> With 2-column settings, one label prints in the left slot; the right slot stays blank.</>
            )}
          </p>
          <div className="flex gap-2 justify-end">
            <Button variant="outline" size="sm" onClick={handleDownload} disabled={!pdfUrl}>
              <Download className="h-4 w-4 mr-1" /> Download
            </Button>
            <Button size="sm" onClick={handlePrint} disabled={!path && !pdfUrl}>
              <Printer className="h-4 w-4 mr-1" /> Print
            </Button>
            <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
