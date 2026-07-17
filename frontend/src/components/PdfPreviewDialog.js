import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Download, Printer } from 'lucide-react';

/**
 * Generic PDF preview dialog — letterhead follows Print Settings (server-side).
 *
 * Props:
 *   open     boolean
 *   onClose  fn
 *   title    string
 *   path     string — API path to GET
 *   params   object — extra query params
 *   filename string — optional download filename (defaults to document.pdf)
 */
const PdfPreviewDialog = ({
  open, onClose, title = 'PDF Preview', path, params = {}, filename = 'document.pdf',
}) => {
  const [pdfUrl, setPdfUrl] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let createdUrl = null;
    const fetchPdf = async () => {
      if (!open || !path) return;
      setLoading(true);
      try {
        const res = await axios.get(path, {
          responseType: 'blob',
          params: { ...params },
        });
        if (cancelled) return;
        const url = window.URL.createObjectURL(
          new Blob([res.data], { type: 'application/pdf' })
        );
        createdUrl = url;
        setPdfUrl((prev) => {
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
      if (createdUrl) {
        try { window.URL.revokeObjectURL(createdUrl); } catch {}
      }
    };
  }, [open, path, JSON.stringify(params)]);

  const handleClose = () => {
    if (pdfUrl) {
      try { window.URL.revokeObjectURL(pdfUrl); } catch {}
      setPdfUrl(null);
    }
    onClose && onClose();
  };

  const handlePrint = async () => {
    if (!pdfUrl) return;
    const { printPdfFromUrl } = await import('../utils/printPdf');
    await printPdfFromUrl(pdfUrl);
  };

  const handleDownload = () => {
    if (!pdfUrl) return;
    const anchor = document.createElement('a');
    anchor.href = pdfUrl;
    anchor.download = filename || 'document.pdf';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose(); }}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col space-y-4">
          <p className="text-xs text-muted-foreground">
            Letterhead and top gap are configured under{' '}
            <Link to="/dashboard/print-settings" className="underline hover:text-foreground">
              Print Settings
            </Link>.
          </p>
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
            <Button variant="outline" onClick={handleClose} className="flex-1">
              Close
            </Button>
            <Button
              variant="outline"
              onClick={handleDownload}
              disabled={!pdfUrl || loading}
              className="flex-1"
            >
              <Download className="h-4 w-4 mr-2" /> Download
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
