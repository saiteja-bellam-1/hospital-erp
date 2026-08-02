import React from 'react';
import { Loader2 } from 'lucide-react';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Stepper } from './ui/stepper';

/**
 * Wide, non-scrolling form dialog with sticky header / stepper / footer.
 * Only the active step's fields should be passed as children.
 */
export default function SteppedFormDialog({
  open,
  onOpenChange,
  title,
  steps = [],
  activeStep = 0,
  onStepChange,
  onClose,
  onSave,
  onNext,
  saving = false,
  canProceed = true,
  saveLabel = 'Save',
  nextLabel = 'Next',
  loading = false,
  formNav = 'grid',
  contentClassName = 'max-w-6xl w-[96vw] max-h-[90vh] flex flex-col overflow-hidden gap-0 p-0',
  children,
}) {
  const isLast = steps.length === 0 || activeStep >= steps.length - 1;
  const isFirst = activeStep <= 0;

  const handleOpenChange = (next) => {
    onOpenChange?.(next);
    if (!next) onClose?.();
  };

  const handleStepClick = (index) => {
    if (index === activeStep) return;
    if (index < activeStep || steps[index - 1]?.completed) {
      onStepChange?.(index);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className={contentClassName} formNav={formNav}>
        <div className="shrink-0 border-b px-6 pt-5 pb-3 space-y-3">
          <DialogHeader className="space-y-0">
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          {steps.length > 0 && (
            <Stepper
              steps={steps}
              activeIndex={activeStep}
              onStepClick={handleStepClick}
            />
          )}
        </div>

        <div className="flex-1 min-h-0 overflow-hidden px-6 py-4">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-12 text-sm text-gray-500">
              <Loader2 className="h-5 w-5 animate-spin" />
              Loading form…
            </div>
          ) : (
            children
          )}
        </div>

        <div className="shrink-0 border-t px-6 py-3 flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={saving}
          >
            Cancel
          </Button>
          {!isFirst && (
            <Button
              type="button"
              variant="outline"
              onClick={() => onStepChange?.(activeStep - 1)}
              disabled={saving || loading}
            >
              Back
            </Button>
          )}
          {!isLast ? (
            <Button
              type="button"
              onClick={() => onNext?.()}
              disabled={saving || loading || !canProceed}
            >
              {nextLabel}
            </Button>
          ) : (
            <Button
              type="button"
              onClick={() => onSave?.()}
              disabled={saving || loading || !canProceed}
            >
              {saving ? (
                <><Loader2 className="h-4 w-4 mr-2 animate-spin" />Saving…</>
              ) : (
                saveLabel
              )}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
