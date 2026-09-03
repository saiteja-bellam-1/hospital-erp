import { useMemo } from 'react';
import {
  labLabelPageSize,
  labelPageSizeLabel,
  pharmacyLabelPageSize,
  stickersAcrossRoll,
} from '../utils/labelPageSize';
import { usePdfPrintSettings } from './usePdfPrintSettings';

/** Resolved PDF page dimensions for label preview iframes. */
export function useLabelPageSize(kind = 'pharmacy') {
  const { settings, isLoading } = usePdfPrintSettings();
  const labelSettings = kind === 'lab'
    ? settings?.lab_label_settings
    : settings?.pharmacy_label_settings;
  const page = useMemo(() => (
    kind === 'lab' ? labLabelPageSize(settings) : pharmacyLabelPageSize(settings)
  ), [kind, settings]);
  const stickersAcross = useMemo(
    () => stickersAcrossRoll(labelSettings),
    [labelSettings],
  );
  const aspectRatio = `${page.width_mm} / ${page.height_mm}`;
  const isLandscape = page.width_mm > page.height_mm;
  return {
    page,
    aspectRatio,
    isLandscape,
    pageLabel: labelPageSizeLabel(page),
    stickersAcross,
    isLoading,
  };
}
