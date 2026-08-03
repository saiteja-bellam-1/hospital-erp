import React, { useEffect, useRef, useState } from 'react';
import { Loader2, Plus, Sparkles } from 'lucide-react';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';
import {
  formatBatchExpiry,
  formatBatchLabel,
  formatMoney,
  pricingSource,
  stripSaleRate,
  supportsStripSale,
  tabSaleRate,
} from '../../utils/pharmacyUnits';

function formatExpiryCell(batch) {
  if (!batch?.expiry_date) return '—';
  const label = formatBatchExpiry(batch);
  return label ? label.replace(/^exp\s+/i, '') : '—';
}

function formatStockCell(batch) {
  if (!batch) return '—';
  const qty = batch.quantity_in_stock ?? 0;
  const scf = parseInt(batch.strip_conversion_factor, 10) || 0;
  if (scf > 1) {
    const strips = Math.floor(qty / scf);
    const rem = qty % scf;
    return rem > 0 ? `${qty} (${strips}s + ${rem})` : `${qty} (${strips} strips)`;
  }
  return String(qty);
}

function formatRateCell(batch, medicine, tier) {
  const src = pricingSource(medicine, batch);
  const stripR = stripSaleRate(src, tier);
  if (!stripR) return '—';
  const tabR = tabSaleRate(src, tier, stripR);
  if (supportsStripSale(src)) {
    return `₹${formatMoney(tabR)} / ₹${formatMoney(stripR)}`;
  }
  return `₹${formatMoney(tabR)}`;
}

/**
 * Keyboard-navigable batch picker (tabular layout).
 * ↑/↓ navigate · Enter select · Esc cancel.
 * When showRateTierStep is set, batch pick is followed by Rate A / B selection.
 * When rateOnly is set, opens directly on the rate step for the current line.
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
  rateOnly = false,
  initialRateTier = 'A',
  initialAuto = false,
  initialBatch = null,
  onSelectBatch,
  onSelectAuto,
  onSelectRateOnly,
  onNewBatch,
  onCancel,
}) {
  const [highlight, setHighlight] = useState(0);
  const [step, setStep] = useState('batch');
  const [pending, setPending] = useState(null);
  const [rateTier, setRateTier] = useState('A');
  const listRef = useRef(null);

  const nearestBatch = batches[0] || null;
  const autoOffset = includeAutoOption ? 1 : 0;
  const newOffset = showNewBatchOption ? 1 : 0;
  const optionCount = autoOffset + batches.length + newOffset;
  const totalStock = batches.reduce((sum, b) => sum + (parseFloat(b.quantity_in_stock) || 0), 0);
  const resolvedManufacturer = manufacturer
    || medicine?.company_name
    || medicine?.manufacturer
    || '';

  const buildPendingFromLine = () => {
    if (initialAuto || (!initialBatch && includeAutoOption)) {
      return { kind: 'auto' };
    }
    if (initialBatch) {
      return { kind: 'batch', batch: initialBatch };
    }
    return nearestBatch ? { kind: 'batch', batch: nearestBatch } : { kind: 'auto' };
  };

  const resetFlow = () => {
    setRateTier(initialRateTier || 'A');
    setHighlight(0);
    if (rateOnly) {
      setPending(buildPendingFromLine());
      setStep('rate');
    } else {
      setPending(null);
      setStep('batch');
    }
  };

  useEffect(() => {
    if (open) resetFlow();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, medicine?.id, rateOnly]);

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
    if (rateOnly) {
      onSelectRateOnly?.(tier);
      onOpenChange?.(false);
      return;
    }
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
    if (nextPending.kind === 'auto') onSelectAuto?.(initialRateTier || 'A');
    else if (nextPending.kind === 'batch') onSelectBatch?.(nextPending.batch, initialRateTier || 'A');
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
      if (rateOnly) {
        if (onCancel) onCancel();
        else onOpenChange?.(false);
      } else {
        setStep('batch');
        setPending(null);
      }
    }
  };

  const rateSource = pending?.kind === 'batch'
    ? pricingSource(medicine, pending.batch)
    : pricingSource(medicine, nearestBatch);

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
    ? (nearestBatch?.batch_number
      ? `Auto · ${nearestBatch.batch_number}`
      : 'Auto (nearest expiry)')
    : pending?.batch?.batch_number || '';

  const rowClass = (idx) => (
    `border-b last:border-b-0 transition-colors cursor-pointer ${
      highlight === idx ? 'bg-blue-50' : 'hover:bg-gray-50'
    }`
  );

  const cellPad = 'px-3 py-2.5 text-sm align-middle';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl w-[min(96vw,64rem)]" formNav={false}>
        <DialogHeader>
          <DialogTitle>{step === 'rate' ? 'Select rate' : 'Select batch'}</DialogTitle>
        </DialogHeader>

        {medicine && (
          <div className="rounded-md border bg-gray-50 px-4 py-3 text-sm flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="font-medium text-gray-900 text-base">{medicine.name}</div>
              <div className="text-xs text-gray-500 mt-0.5">
                {[medicine.medicine_code, resolvedManufacturer].filter(Boolean).join(' · ') || '—'}
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className="text-xs text-gray-500">Available stock</div>
              <div className="text-lg font-semibold text-gray-900 tabular-nums">{totalStock}</div>
              <div className="text-[11px] text-gray-400">{batches.length} batch{batches.length === 1 ? '' : 'es'}</div>
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center gap-2 py-12 text-sm text-gray-500">
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
              {pending?.kind === 'auto' && nearestBatch && (
                <div className="text-xs text-gray-500 mt-0.5">{formatBatchLabel(nearestBatch)}</div>
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
              ←→ switch rate · Enter confirm · Esc {rateOnly ? 'cancel' : 'back'}
            </p>
            <DialogFooter className="gap-2 sm:gap-0">
              {!rateOnly && (
                <Button type="button" variant="outline" onClick={() => { setStep('batch'); setPending(null); }}>
                  Back
                </Button>
              )}
              {rateOnly && (
                <Button type="button" variant="outline" onClick={() => { if (onCancel) onCancel(); else onOpenChange?.(false); }}>
                  Cancel
                </Button>
              )}
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
              className="rounded-md border outline-none focus:ring-2 focus:ring-blue-200 overflow-hidden"
              onKeyDown={handleBatchKeyDown}
            >
              <div className="max-h-[min(60vh,28rem)] overflow-auto">
                <table className="w-full text-sm border-collapse min-w-[720px]">
                  <thead className="sticky top-0 z-10 bg-gray-100 border-b">
                    <tr className="text-left text-xs font-medium text-gray-600 uppercase tracking-wide">
                      <th className={`${cellPad} w-[18%]`}>Batch</th>
                      <th className={`${cellPad} w-[10%]`}>Expiry</th>
                      <th className={`${cellPad} w-[14%] text-right`}>Stock</th>
                      <th className={`${cellPad} w-[18%]`}>Manufacturer</th>
                      <th className={`${cellPad} w-[18%]`}>Supplier</th>
                      <th className={`${cellPad} w-[11%] text-right`}>Rate A</th>
                      <th className={`${cellPad} w-[11%] text-right`}>Rate B</th>
                    </tr>
                  </thead>
                  <tbody>
                    {includeAutoOption && (
                      <tr
                        id="batch-opt-0"
                        data-batch-idx={0}
                        role="option"
                        aria-selected={highlight === 0}
                        className={rowClass(0)}
                        onMouseEnter={() => setHighlight(0)}
                        onClick={() => goToRateStep({ kind: 'auto' })}
                      >
                        <td className={cellPad}>
                          <div className="flex items-center gap-2 font-medium text-amber-800">
                            <Sparkles className="h-4 w-4 text-amber-600 shrink-0" />
                            <span>
                              Auto
                              {nearestBatch?.batch_number ? (
                                <span className="text-gray-700 font-normal"> · {nearestBatch.batch_number}</span>
                              ) : null}
                            </span>
                          </div>
                          <div className="text-[11px] text-gray-500 mt-0.5 pl-6">Nearest expiry first</div>
                        </td>
                        <td className={`${cellPad} text-gray-700 tabular-nums`}>
                          {formatExpiryCell(nearestBatch)}
                        </td>
                        <td className={`${cellPad} text-right font-medium tabular-nums text-gray-900`}>
                          {nearestBatch ? formatStockCell(nearestBatch) : '—'}
                          {batches.length > 1 && (
                            <div className="text-[11px] text-gray-500 font-normal">of {totalStock} total</div>
                          )}
                        </td>
                        <td className={`${cellPad} text-gray-700`}>
                          {nearestBatch?.manufacturer || resolvedManufacturer || '—'}
                        </td>
                        <td className={`${cellPad} text-gray-700`}>
                          {nearestBatch?.supplier_name || '—'}
                        </td>
                        <td className={`${cellPad} text-right tabular-nums text-gray-700`}>
                          {formatRateCell(nearestBatch, medicine, 'A')}
                        </td>
                        <td className={`${cellPad} text-right tabular-nums text-gray-700`}>
                          {formatRateCell(nearestBatch, medicine, 'B')}
                        </td>
                      </tr>
                    )}
                    {batches.map((batch, batchIdx) => {
                      const idx = autoOffset + batchIdx;
                      return (
                        <tr
                          key={batch.id}
                          id={`batch-opt-${idx}`}
                          data-batch-idx={idx}
                          role="option"
                          aria-selected={highlight === idx}
                          className={rowClass(idx)}
                          onMouseEnter={() => setHighlight(idx)}
                          onClick={() => goToRateStep({ kind: 'batch', batch })}
                        >
                          <td className={`${cellPad} font-medium text-gray-900`}>
                            {batch.batch_number || '—'}
                          </td>
                          <td className={`${cellPad} text-gray-700 tabular-nums`}>
                            {formatExpiryCell(batch)}
                          </td>
                          <td className={`${cellPad} text-right font-semibold tabular-nums text-gray-900`}>
                            {formatStockCell(batch)}
                          </td>
                          <td className={`${cellPad} text-gray-700`}>
                            {batch.manufacturer || resolvedManufacturer || '—'}
                          </td>
                          <td className={`${cellPad} text-gray-700`}>
                            {batch.supplier_name || '—'}
                          </td>
                          <td className={`${cellPad} text-right tabular-nums text-gray-700`}>
                            {formatRateCell(batch, medicine, 'A')}
                          </td>
                          <td className={`${cellPad} text-right tabular-nums text-gray-700`}>
                            {formatRateCell(batch, medicine, 'B')}
                          </td>
                        </tr>
                      );
                    })}
                    {showNewBatchOption && (() => {
                      const idx = autoOffset + batches.length;
                      return (
                        <tr
                          id={`batch-opt-${idx}`}
                          data-batch-idx={idx}
                          role="option"
                          aria-selected={highlight === idx}
                          className={rowClass(idx)}
                          onMouseEnter={() => setHighlight(idx)}
                          onClick={() => onNewBatch?.()}
                        >
                          <td className={cellPad} colSpan={7}>
                            <div className="flex items-center gap-2 font-medium text-blue-700">
                              <Plus className="h-4 w-4 shrink-0" />
                              Enter new batch
                            </div>
                          </td>
                        </tr>
                      );
                    })()}
                    {!includeAutoOption && batches.length === 0 && !showNewBatchOption && (
                      <tr>
                        <td colSpan={7} className={`${cellPad} text-center text-gray-500 py-8`}>
                          No batches available
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
            <p className="text-[11px] text-gray-400">
              ↑↓ navigate · Enter select · Esc cancel · Rate A/B shown as tab / strip when applicable
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
