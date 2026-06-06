import React, { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Printer, RefreshCw } from 'lucide-react';

/**
 * Live preview for Print Settings — POSTs draft form values, refreshes on change.
 */
const PrintSettingsPreviewDialog = ({
  open,
  onClose,
  reportType = 'opd_bill',
  reportLabel = 'OPD Bill',
  draftSettings,
}) => {
  const [pdfUrl, setPdfUrl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const debounceRef = useRef(null);
  const blobRef = useRef(null);

  const revokeBlob = useCallback(() => {
    if (blobRef.current) {
      try { URL.revokeObjectURL(blobRef.current); } catch {}
      blobRef.current = null;
    }
  }, []);

  const fetchPreview = useCallback(async () => {
    if (!open || !draftSettings) return;
    const gap = parseFloat(draftSettings.letterheadGapMm);
    if (Number.isNaN(gap) || gap < 0 || gap > 80) {
      setError('Letterhead gap must be between 0 and 80 mm');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await axios.post(
        '/api/hospital/print-settings/preview',
        {
          report_type: reportType,
          include_header_on_pdfs: draftSettings.includeHeaderOnPdfs,
          letterhead_gap_mm: gap,
          report_header_overrides: draftSettings.overrides || {},
        },
        { responseType: 'blob' }
      );
      revokeBlob();
      const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      blobRef.current = url;
      setPdfUrl(url);
    } catch (err) {
      console.error('Print preview failed', err);
      setError('Failed to generate preview');
      setPdfUrl(null);
    } finally {
      setLoading(false);
    }
  }, [open, reportType, draftSettings, revokeBlob]);

  useEffect(() => {
    if (!open) return undefined;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchPreview();
    }, 500);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [open, fetchPreview]);

  const handleClose = () => {
    revokeBlob();
    setPdfUrl(null);
    setError(null);
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

  const headerOn = draftSettings?.resolveIncludeHeader?.(reportType)
    ?? draftSettings?.includeHeaderOnPdfs;

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) handleClose(); }}>
      <DialogContent className="max-w-4xl max-h-[92vh] overflow-hidden">
        <DialogHeader>
          <DialogTitle>Preview — {reportLabel}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>
              Sample document with your current settings (unsaved changes included).
              Letterhead: <strong>{headerOn ? 'On' : 'Off'}</strong>
              {!headerOn && (
                <> · Gap: <strong>{draftSettings?.letterheadGapMm} mm</strong></>
              )}
            </span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={fetchPreview}
              disabled={loading}
              className="h-7 px-2"
            >
              <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>

          <div className="flex-1 min-h-[480px] border rounded-lg overflow-hidden bg-gray-50">
            {pdfUrl ? (
              <iframe
                src={pdfUrl}
                className="w-full h-full min-h-[480px] border-0"
                title={`Preview ${reportLabel}`}
              />
            ) : (
              <div className="w-full h-[480px] flex items-center justify-center text-sm text-gray-500">
                {loading ? 'Generating preview…' : (error || 'No preview')}
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
              <Printer className="h-4 w-4 mr-2" /> Print preview
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default PrintSettingsPreviewDialog;
