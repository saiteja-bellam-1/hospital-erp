import { useMemo } from 'react';
import {
  labLabelPageSize,
  labelPageSizeLabel,
  patientFileLabelPageSize,
  pharmacyLabelPageSize,
  stickersAcrossRoll,
} from '../utils/labelPageSize';
import { usePdfPrintSettings } from './usePdfPrintSettings';

function resolveLabelSettings(kind, settings) {
  if (kind === 'lab') return settings?.lab_label_settings;
  if (kind === 'patient_file') return settings?.patient_file_label_settings;
  return settings?.pharmacy_label_settings;
}

function resolvePageSize(kind, settings) {
  if (kind === 'lab') return labLabelPageSize(settings);
  if (kind === 'patient_file') return patientFileLabelPageSize(settings);
  return pharmacyLabelPageSize(settings);
}

/** Resolved PDF page dimensions for label preview iframes. */
export function useLabelPageSize(kind = 'pharmacy') {
  const { settings, isLoading } = usePdfPrintSettings();
  const labelSettings = resolveLabelSettings(kind, settings);
  const page = useMemo(() => resolvePageSize(kind, settings), [kind, settings]);
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
