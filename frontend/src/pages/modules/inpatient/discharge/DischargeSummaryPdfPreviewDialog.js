import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '../../../../components/ui/dialog';
import { Button } from '../../../../components/ui/button';
import { useToast } from '../../../../hooks/use-toast';
import { fetchPdfBlobUrl } from '../../../../utils/printPdf';
import { CheckCircle2, Eye, Loader2, RefreshCw } from 'lucide-react';

/**
 * Inline PDF preview before the doctor marks a discharge summary ready for print.
 * Letterhead follows hospital Print Settings (resolved server-side), same as bills/reports.
 */
export default function DischargeSummaryPdfPreviewDialog({
  open,
  onClose,
  admissionId,
  admissionLabel = '',
  confirmLabel = 'Confirm & mark ready for print',
  onConfirm,
  confirming = false,
}) {
  const { toast } = useToast();
  const [pdfUrl, setPdfUrl] = useState(null);
  const [loading, setLoading] = useState(false);
  const pdfUrlRef = useRef(null);

  const previewPath = admissionId
    ? `/api/inpatient/admissions/${admissionId}/discharge-summary/pdf/preview`
    : null;

  const revokeBlobUrl = useCallback(() => {
    if (pdfUrlRef.current) {
      URL.revokeObjectURL(pdfUrlRef.current);
      pdfUrlRef.current = null;
    }
    setPdfUrl(null);
  }, []);

  const assignBlobUrl = useCallback((url) => {
    if (pdfUrlRef.current) {
      URL.revokeObjectURL(pdfUrlRef.current);
    }
    pdfUrlRef.current = url;
    setPdfUrl(url);
  }, []);

  const loadPreview = useCallback(async () => {
    if (!previewPath) return;
    setLoading(true);
    try {
      const url = await fetchPdfBlobUrl(previewPath);
      assignBlobUrl(url);
    } catch (err) {
      revokeBlobUrl();
      toast({
        variant: 'destructive',
        title: 'Preview failed',
        description: err.message || 'Could not load discharge summary PDF',
      });
    } finally {
      setLoading(false);
    }
  }, [previewPath, assignBlobUrl, revokeBlobUrl, toast]);

  useEffect(() => {
    if (!open) {
      revokeBlobUrl();
      return undefined;
    }
    if (!previewPath) return undefined;

    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const url = await fetchPdfBlobUrl(previewPath);
        if (cancelled) {
          URL.revokeObjectURL(url);
        } else {
          assignBlobUrl(url);
        }
      } catch (err) {
        if (!cancelled) {
          revokeBlobUrl();
          toast({
            variant: 'destructive',
            title: 'Preview failed',
            description: err.message || 'Could not load discharge summary PDF',
          });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      revokeBlobUrl();
    };
  }, [open, admissionId, previewPath, assignBlobUrl, revokeBlobUrl, toast]);

  const handleClose = () => {
    revokeBlobUrl();
    onClose?.();
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
      <DialogContent className="max-w-4xl max-h-[92vh] flex flex-col overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Eye className="h-5 w-5" />
            Preview discharge summary
            {admissionLabel && (
              <span className="text-sm font-normal text-gray-500">— {admissionLabel}</span>
            )}
          </DialogTitle>
        </DialogHeader>

        <div className="flex-1 min-h-0 flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-4 text-sm">
            <p className="text-xs text-muted-foreground">
              Letterhead and top gap follow{' '}
              <Link to="/dashboard/print-settings" className="underline hover:text-foreground">
                Print Settings
              </Link>
              {' '}(Discharge Summary).
            </p>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={loading || confirming}
              onClick={loadPreview}
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                : <RefreshCw className="h-3.5 w-3.5 mr-1" />}
              Refresh
            </Button>
            <span className="text-xs text-gray-500">
              Draft previews show a DRAFT watermark until you confirm.
            </span>
          </div>

          <div className="flex-1 min-h-[50vh] border rounded-lg bg-gray-50 overflow-hidden">
            {loading && !pdfUrl && (
              <div className="h-full flex items-center justify-center text-gray-500 text-sm">
                <Loader2 className="h-5 w-5 mr-2 animate-spin" /> Loading preview…
              </div>
            )}
            {!loading && !pdfUrl && (
              <div className="h-full flex items-center justify-center text-gray-500 text-sm px-4 text-center">
                Preview could not be loaded. Use Refresh or go back and save the draft again.
              </div>
            )}
            {pdfUrl && (
              <iframe
                key={pdfUrl}
                src={pdfUrl}
                title="Discharge summary preview"
                className="w-full h-full min-h-[50vh] bg-white"
              />
            )}
          </div>
        </div>

        <DialogFooter className="gap-2 flex-wrap sm:justify-between border-t pt-3">
          <Button variant="outline" onClick={handleClose} disabled={confirming}>
            Back to edit
          </Button>
          <Button onClick={onConfirm} disabled={loading || confirming || !pdfUrl}>
            {confirming
              ? <><Loader2 className="h-4 w-4 mr-1 animate-spin" /> Finalizing…</>
              : <><CheckCircle2 className="h-4 w-4 mr-1" /> {confirmLabel}</>}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
