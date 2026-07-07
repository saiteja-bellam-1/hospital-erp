import React, { useEffect, useRef, useState } from 'react';
import { Loader2, Plus, Sparkles } from 'lucide-react';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import {
  formatBatchLabel,
  formatMoney,
  pricingSource,
  stripSaleRate,
  supportsStripSale,
  tabSaleRate,
} from '../../utils/pharmacyUnits';

/**
 * Keyboard-navigable batch picker.
 * ↑/↓ navigate · Enter select · Esc cancel (calls onCancel if provided).
 * When showRateTierStep is set, batch pick is followed by Rate A / B selection.
 */
export default function PharmacyBatchSelectDialog({
  open,
  onOpenChange,
  medicine,
  manufacturer = '',
  batches = [],
  loading = false,
  includeAutoOption = false,
  showNewBatchOption = false,
  showRateTierStep = false,
  initialRateTier = 'A',
  onSelectBatch,
  onSelectAuto,
  onNewBatch,
  onCancel,
}) {
  const [highlight, setHighlight] = useState(0);
  const [step, setStep] = useState('batch');
  const [pending, setPending] = useState(null);
  const [rateTier, setRateTier] = useState('A');
  const listRef = useRef(null);

  const autoOffset = includeAutoOption ? 1 : 0;
  const newOffset = showNewBatchOption ? 1 : 0;
  const optionCount = autoOffset + batches.length + newOffset;

  const resetFlow = () => {
    setStep('batch');
    setPending(null);
    setRateTier(initialRateTier || 'A');
    setHighlight(0);
  };

  useEffect(() => {
    if (open) resetFlow();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, medicine?.id]);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => listRef.current?.focus(), 50);
    return () => clearTimeout(t);
  }, [open, loading, step]);

  useEffect(() => {
    if (!open || loading || step !== 'batch') return;
    const el = listRef.current?.querySelector(`[data-batch-idx="${highlight}"]`);
    el?.scrollIntoView({ block: 'nearest' });
  }, [highlight, open, loading, step]);

  const finishSelection = (tier) => {
    if (!pending) return;
    if (pending.kind === 'auto') {
      onSelectAuto?.(tier);
    } else if (pending.kind === 'batch') {
      onSelectBatch?.(pending.batch, tier);
    }
    onOpenChange?.(false);
  };

  const goToRateStep = (nextPending) => {
    if (showRateTierStep) {
      setPending(nextPending);
      setRateTier(initialRateTier || 'A');
      setStep('rate');
      return;
    }
    if (nextPending.kind === 'auto') onSelectAuto?.();
    else if (nextPending.kind === 'batch') onSelectBatch?.(nextPending.batch);
    onOpenChange?.(false);
  };

  const chooseHighlight = (idx) => {
    if (includeAutoOption && idx === 0) {
      goToRateStep({ kind: 'auto' });
      return;
    }
    const batchIdx = idx - autoOffset;
    if (batchIdx >= 0 && batchIdx < batches.length) {
      goToRateStep({ kind: 'batch', batch: batches[batchIdx] });
      return;
    }
    if (showNewBatchOption) onNewBatch?.();
  };

  const handleBatchKeyDown = (e) => {
    if (loading) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      e.stopPropagation();
      setHighlight((i) => Math.min(i + 1, optionCount - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      e.stopPropagation();
      setHighlight((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      e.stopPropagation();
      chooseHighlight(highlight);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      if (onCancel) onCancel();
      else onOpenChange?.(false);
    }
  };

  const handleRateKeyDown = (e) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      setRateTier('A');
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      setRateTier('B');
    } else if (e.key === 'Enter') {
      e.preventDefault();
      finishSelection(rateTier);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setStep('batch');
      setPending(null);
    }
  };

  const rateSource = pending?.kind === 'batch'
    ? pricingSource(medicine, pending.batch)
    : pricingSource(medicine, batches[0] || null);

  const rateHint = (tier) => {
    const stripR = stripSaleRate(rateSource, tier);
    const tabR = tabSaleRate(rateSource, tier, stripR);
    if (!stripR) return 'Not set';
    if (supportsStripSale(rateSource)) {
      return `Tab ₹${formatMoney(tabR)} · Strip ₹${formatMoney(stripR)}`;
    }
    return `₹${formatMoney(tabR)} each`;
  };

  const pendingLabel = pending?.kind === 'auto'
    ? 'Auto (nearest expiry)'
    : pending?.batch?.batch_number || '';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" formNav={false}>
        <DialogHeader>
          <DialogTitle>{step === 'rate' ? 'Select rate' : 'Select batch'}</DialogTitle>
        </DialogHeader>

        {medicine && (
          <div className="rounded-md border bg-gray-50 px-3 py-2 text-sm">
            <div className="font-medium text-gray-900">{medicine.name}</div>
            <div className="text-xs text-gray-500">
              {[medicine.medicine_code, manufacturer].filter(Boolean).join(' · ')}
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading batches…
          </div>
        ) : step === 'rate' ? (
          <div className="space-y-3" onKeyDown={handleRateKeyDown} tabIndex={0}>
            <div className="rounded-md border px-3 py-2 text-sm bg-white">
              <div className="text-xs text-gray-500">Batch</div>
              <div className="font-medium">{pendingLabel}</div>
              {pending?.kind === 'batch' && (
                <div className="text-xs text-gray-500 mt-0.5">{formatBatchLabel(pending.batch)}</div>
              )}
            </div>
            <p className="text-xs text-gray-500">Choose selling rate for this line.</p>
            <div className="grid grid-cols-2 gap-2">
              {['A', 'B'].map((tier) => (
                <button
                  key={tier}
                  type="button"
                  className={`rounded-md border px-3 py-3 text-left transition-colors ${
                    rateTier === tier
                      ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-200'
                      : 'hover:bg-gray-50'
                  }`}
                  onClick={() => setRateTier(tier)}
                >
                  <div className="font-semibold text-gray-900">Rate {tier}</div>
                  <div className="text-xs text-gray-500 mt-1">{rateHint(tier)}</div>
                </button>
              ))}
            </div>
            <p className="text-[11px] text-gray-400">
              ←→ switch rate · Enter confirm · Esc back
            </p>
            <DialogFooter className="gap-2 sm:gap-0">
              <Button type="button" variant="outline" onClick={() => { setStep('batch'); setPending(null); }}>
                Back
              </Button>
              <Button type="button" onClick={() => finishSelection(rateTier)}>
                Confirm
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <>
            <p className="text-xs text-gray-500">
              {includeAutoOption
                ? 'Pick a batch to sell from, or use auto to deduct nearest expiry first.'
                : 'Pick an existing batch or enter a new batch number below.'}
            </p>
            <div
              ref={listRef}
              tabIndex={0}
              role="listbox"
              aria-label="Available batches"
              aria-activedescendant={open ? `batch-opt-${highlight}` : undefined}
              className="max-h-64 overflow-y-auto rounded-md border divide-y outline-none focus:ring-2 focus:ring-blue-200"
              onKeyDown={handleBatchKeyDown}
            >
              {includeAutoOption && (
                <button
                  type="button"
                  id="batch-opt-0"
                  data-batch-idx={0}
                  role="option"
                  aria-selected={highlight === 0}
                  className={`w-full text-left px-3 py-2.5 text-sm flex items-center gap-2 transition-colors ${
                    highlight === 0 ? 'bg-blue-50 ring-1 ring-inset ring-blue-200' : 'hover:bg-gray-50'
                  }`}
                  onMouseEnter={() => setHighlight(0)}
                  onClick={() => goToRateStep({ kind: 'auto' })}
                >
                  <Sparkles className="h-4 w-4 text-amber-600 shrink-0" />
                  <span className="font-medium">Auto (nearest expiry)</span>
                </button>
              )}
              {batches.map((batch, batchIdx) => {
                const idx = autoOffset + batchIdx;
                return (
                  <button
                    key={batch.id}
                    type="button"
                    id={`batch-opt-${idx}`}
                    data-batch-idx={idx}
                    role="option"
                    aria-selected={highlight === idx}
                    className={`w-full text-left px-3 py-2.5 text-sm transition-colors ${
                      highlight === idx ? 'bg-blue-50 ring-1 ring-inset ring-blue-200' : 'hover:bg-gray-50'
                    }`}
                    onMouseEnter={() => setHighlight(idx)}
                    onClick={() => goToRateStep({ kind: 'batch', batch })}
                  >
                    <div className="font-medium">{batch.batch_number}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{formatBatchLabel(batch)}</div>
                    {batch.supplier_name && (
                      <div className="text-[11px] text-gray-400 mt-0.5">Supplier: {batch.supplier_name}</div>
                    )}
                  </button>
                );
              })}
              {showNewBatchOption && (() => {
                const idx = autoOffset + batches.length;
                return (
                <button
                  type="button"
                  id={`batch-opt-${idx}`}
                  data-batch-idx={idx}
                  role="option"
                  aria-selected={highlight === idx}
                  className={`w-full text-left px-3 py-2.5 text-sm flex items-center gap-2 transition-colors ${
                    highlight === idx ? 'bg-blue-50 ring-1 ring-inset ring-blue-200' : 'hover:bg-gray-50'
                  }`}
                  onMouseEnter={() => setHighlight(idx)}
                  onClick={() => onNewBatch?.()}
                >
                  <Plus className="h-4 w-4 text-blue-600 shrink-0" />
                  <span className="font-medium text-blue-700">Enter new batch</span>
                </button>
                );
              })()}
            </div>
            <p className="text-[11px] text-gray-400">
              ↑↓ navigate · Enter select · Esc cancel
            </p>
          </>
        )}

        {showNewBatchOption && step === 'batch' && (
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onNewBatch?.()}>
              Enter new batch
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
