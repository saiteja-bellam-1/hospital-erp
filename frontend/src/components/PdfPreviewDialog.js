import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Printer } from 'lucide-react';

/**
 * Generic PDF preview dialog — letterhead follows Print Settings (server-side).
 *
 * Props:
 *   open    boolean
 *   onClose fn
 *   title   string
 *   path    string — API path to GET
 *   params  object — extra query params
 */
const PdfPreviewDialog = ({
  open, onClose, title = 'PDF Preview', path, params = {},
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
