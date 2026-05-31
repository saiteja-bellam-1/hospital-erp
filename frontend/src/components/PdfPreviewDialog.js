import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Printer } from 'lucide-react';

/**
 * Generic PDF preview dialog used across modules.
 *
 * Fetches the PDF as a blob, shows it in an iframe, exposes an "Include header"
 * checkbox that re-fetches on toggle, and prints via a hidden iframe.
 *
 * Props:
 *   open          boolean   — controlled open state
 *   onClose       fn        — close handler
 *   title         string    — dialog title
 *   path          string    — API path to GET (e.g. "/api/pharmacy/sales/12/invoice/pdf")
 *   params        object    — extra query params (excluding include_header)
 *   defaultHeader boolean   — initial value for the Include header toggle (default false)
 */
const PdfPreviewDialog = ({
  open, onClose, title = 'PDF Preview', path, params = {}, defaultHeader = false,
}) => {
  const [includeHeader, setIncludeHeader] = useState(defaultHeader);
  const [pdfUrl, setPdfUrl] = useState(null);
  const [loading, setLoading] = useState(false);

  // Reset header preference whenever the dialog opens for a new document
  useEffect(() => {
    if (open) setIncludeHeader(defaultHeader);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, path]);

  // (Re)fetch the PDF whenever the path or header toggle changes while open.
  useEffect(() => {
    let cancelled = false;
    let createdUrl = null;
    const fetchPdf = async () => {
      if (!open || !path) return;
      setLoading(true);
      try {
        const res = await axios.get(path, {
          responseType: 'blob',
          params: { ...params, include_header: includeHeader },
        });
        if (cancelled) return;
        const url = window.URL.createObjectURL(
          new Blob([res.data], { type: 'application/pdf' })
        );
        createdUrl = url;
        setPdfUrl(prev => {
          if (prev) window.URL.revokeObjectURL(prev);
          return url;
        });
      } catch (e) {
        console.error('PdfPreviewDialog: fetch failed', e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchPdf();
    return () => {
      cancelled = true;
      // Created URLs are revoked when replaced or on dialog close (below)
      if (createdUrl && createdUrl !== pdfUrl) {
        try { window.URL.revokeObjectURL(createdUrl); } catch {}
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, path, includeHeader]);

  const handleClose = () => {
    if (pdfUrl) {
      try { window.URL.revokeObjectURL(pdfUrl); } catch {}
      setPdfUrl(null);
    }
    onClose && onClose();
  };

  const handlePrint = () => {
    if (!pdfUrl) return;
    const iframe = document.createElement('iframe');
    iframe.style.display = 'none';
    document.body.appendChild(iframe);
    iframe.src = pdfUrl;
    iframe.onload = () => {
      try { iframe.contentWindow.print(); } catch (e) { console.error(e); }
      setTimeout(() => {
        try { document.body.removeChild(iframe); } catch {}
      }, 1000);
    };
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose(); }}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col space-y-4">
          <div className="flex-1 min-h-[500px] border rounded-lg overflow-hidden bg-gray-50">
            {pdfUrl ? (
              <iframe
                src={pdfUrl}
                className="w-full h-full min-h-[500px] border-0"
                title={title}
              />
            ) : (
              <div className="w-full h-[500px] flex items-center justify-center text-sm text-gray-500">
                {loading ? 'Loading PDF…' : 'No PDF loaded'}
              </div>
            )}
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="pdf-preview-header"
                checked={includeHeader}
                onChange={(e) => setIncludeHeader(e.target.checked)}
                className="w-4 h-4"
                disabled={loading}
              />
              <Label htmlFor="pdf-preview-header" className="text-sm">
                Include header
              </Label>
            </div>
            <Button variant="outline" onClick={handleClose} className="flex-1">
              Close
            </Button>
            <Button
              onClick={handlePrint}
              disabled={!pdfUrl || loading}
              className="flex-1 bg-blue-600 hover:bg-blue-700"
            >
              <Printer className="h-4 w-4 mr-2" /> Print
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default PdfPreviewDialog;
