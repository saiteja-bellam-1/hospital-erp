import React, { useCallback, useEffect, useState } from 'react';
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '../../../../components/ui/dialog';
import { Button } from '../../../../components/ui/button';
import { Label } from '../../../../components/ui/label';
import { useToast } from '../../../../hooks/use-toast';
import { fetchPdfBlobUrl } from '../../../../utils/printPdf';
import { usePdfPrintSettings } from '../../../../hooks/usePdfPrintSettings';
import { CheckCircle2, Eye, Loader2, RefreshCw } from 'lucide-react';

/**
 * Inline PDF preview before the doctor marks a discharge summary ready for print.
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
  const { resolveIncludeHeader, isLoading: settingsLoading } = usePdfPrintSettings();
  const [includeHeader, setIncludeHeader] = useState(true);
  const [pdfUrl, setPdfUrl] = useState(null);
  const [loading, setLoading] = useState(false);

  const previewPath = admissionId
    ? `/api/inpatient/admissions/${admissionId}/discharge-summary/pdf/preview`
    : null;

  const revokeUrl = useCallback(() => {
    if (pdfUrl) {
      URL.revokeObjectURL(pdfUrl);
      setPdfUrl(null);
    }
  }, [pdfUrl]);

  const loadPreview = useCallback(async (headerFlag) => {
    if (!previewPath) return;
    setLoading(true);
    try {
      revokeUrl();
      const url = await fetchPdfBlobUrl(previewPath, {
        params: { include_header: headerFlag },
      });
      setPdfUrl(url);
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Preview failed',
        description: err.message || 'Could not load discharge summary PDF',
      });
    } finally {
      setLoading(false);
    }
  }, [previewPath, revokeUrl, toast]);

  useEffect(() => {
    if (!open) {
      revokeUrl();
      return undefined;
    }
    if (settingsLoading || !previewPath) return undefined;

    const defaultHeader = resolveIncludeHeader('discharge_summary');
    setIncludeHeader(defaultHeader);

    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        revokeUrl();
        const url = await fetchPdfBlobUrl(previewPath, {
          params: { include_header: defaultHeader },
        });
        if (cancelled) {
          URL.revokeObjectURL(url);
        } else {
          setPdfUrl(url);
        }
      } catch (err) {
        if (!cancelled) {
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
      revokeUrl();
    };
  }, [open, admissionId, previewPath, settingsLoading, resolveIncludeHeader, revokeUrl, toast]);

  const handleHeaderToggle = (checked) => {
    setIncludeHeader(checked);
    loadPreview(checked);
  };

  const handleClose = () => {
    revokeUrl();
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
            <div className="flex items-center gap-2">
              <input
                id="ds-preview-header"
                type="checkbox"
                className="rounded"
                checked={includeHeader}
                disabled={loading || confirming}
                onChange={(e) => handleHeaderToggle(e.target.checked)}
              />
              <Label htmlFor="ds-preview-header" className="font-normal cursor-pointer">
                Include hospital header
              </Label>
            </div>
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={loading || confirming}
              onClick={() => loadPreview(includeHeader)}
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
            {pdfUrl && (
              <iframe
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
