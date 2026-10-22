/**
 * Per-print label layout helpers for BarcodeLabelPrintDialog.
 * Hospital customisation sizes are the seed (one saved size per label kind).
 */

import {
  applyThermalRollLayout,
  computeLabelPageSizeMm,
  labelPageSizeLabel,
} from './labelPageSize';

export const LABEL_SIZE_PRESETS = {
  thermal_70x40: {
    width_mm: 70, height_mm: 40, labels_per_row: 1, labels_per_column: 1, sheet_mode: 'thermal',
  },
  thermal_50x30: {
    width_mm: 50, height_mm: 30, labels_per_row: 1, labels_per_column: 1, sheet_mode: 'thermal',
  },
  thermal_40x30: {
    width_mm: 40, height_mm: 30, labels_per_row: 1, labels_per_column: 1, sheet_mode: 'thermal',
  },
  thermal_38x25: {
    width_mm: 38, height_mm: 25, labels_per_row: 1, labels_per_column: 1, sheet_mode: 'thermal',
  },
  thermal_38x25_2up: {
    width_mm: 38, height_mm: 25, labels_per_row: 2, labels_per_column: 1, gutter_mm: 2, sheet_mode: 'thermal',
  },
  thermal_38x25_3up: {
    width_mm: 38, height_mm: 25, labels_per_row: 3, labels_per_column: 1, gutter_mm: 2, sheet_mode: 'thermal',
  },
  avery_3x8: {
    width_mm: 66, height_mm: 25.4, labels_per_row: 3, labels_per_column: 8,
    sheet_mode: 'avery', sheet_width_mm: 210, sheet_height_mm: 297,
  },
};

const STORAGE_PREFIX = 'kthealth.labelPrint.';

export const LABEL_DPI_OPTIONS = [
  { value: '203', label: '203 dpi — standard thermal' },
  { value: '300', label: '300 dpi — sharper' },
  { value: '600', label: '600 dpi — fine' },
];

const LABEL_DPI_CHOICES = [203, 300, 600];

export function normalizeLabelDpi(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 203;
  return LABEL_DPI_CHOICES.reduce(
    (best, choice) => (Math.abs(choice - n) < Math.abs(best - n) ? choice : best),
    203,
  );
}

const DEFAULTS_BY_KIND = {
  lab: { width_mm: 50, height_mm: 30, labels_per_row: 1, labels_per_column: 1, gutter_mm: 2, sheet_mode: 'thermal', margin_top_mm: 2, margin_left_mm: 2, dpi: 203 },
  pharmacy: { width_mm: 38, height_mm: 25, labels_per_row: 1, labels_per_column: 1, gutter_mm: 2, sheet_mode: 'thermal', margin_top_mm: 2, margin_left_mm: 2, dpi: 203 },
  patient_file: { width_mm: 70, height_mm: 40, labels_per_row: 1, labels_per_column: 1, gutter_mm: 2, sheet_mode: 'thermal', margin_top_mm: 2, margin_left_mm: 2, dpi: 203 },
};

function settingsKeyForKind(kind) {
  if (kind === 'lab') return 'lab_label_settings';
  if (kind === 'patient_file') return 'patient_file_label_settings';
  return 'pharmacy_label_settings';
}

export function defaultLayoutForKind(kind) {
  return { ...(DEFAULTS_BY_KIND[kind] || DEFAULTS_BY_KIND.pharmacy) };
}

/** Seed dialog layout from the hospital size saved for this label kind. */
export function seedLabelPrintLayout(kind, printSettings, { allowMultiUp = true } = {}) {
  const key = settingsKeyForKind(kind);
  const hospital = printSettings?.[key] || {};
  let layout = {
    ...defaultLayoutForKind(kind),
    ...hospital,
  };
  if (!allowMultiUp && (layout.sheet_mode || 'thermal') === 'thermal') {
    layout = { ...layout, labels_per_row: 1, labels_per_column: 1 };
  }
  return applyThermalRollLayout(layout);
}

/** Drop a browser-only size so the hospital customisation is what prints next. */
export function forgetLabelPrintLayout(kind) {
  try {
    localStorage.removeItem(`${STORAGE_PREFIX}${kind}`);
  } catch {
    /* ignore */
  }
}

export function rememberLabelPrintLayout(kind, layout) {
  try {
    const toStore = {
      width_mm: Number(layout.width_mm),
      height_mm: Number(layout.height_mm),
      labels_per_row: Number(layout.labels_per_row) || 1,
      labels_per_column: Number(layout.labels_per_column) || 1,
      gutter_mm: Number(layout.gutter_mm) || 2,
      sheet_mode: layout.sheet_mode || 'thermal',
      margin_top_mm: Number(layout.margin_top_mm) || 2,
      margin_left_mm: Number(layout.margin_left_mm) || 2,
      sheet_width_mm: Number(layout.sheet_width_mm) || 210,
      sheet_height_mm: Number(layout.sheet_height_mm) || 297,
      dpi: normalizeLabelDpi(layout.dpi),
    };
    localStorage.setItem(`${STORAGE_PREFIX}${kind}`, JSON.stringify(toStore));
  } catch {
    /* ignore */
  }
}

/** Query params sent to label PDF endpoints (only layout fields). */
export function layoutToQueryParams(layout, { forceSingle = true } = {}) {
  let s = { ...(layout || {}) };
  if (forceSingle && (s.sheet_mode || 'thermal') === 'thermal') {
    s = { ...s, labels_per_row: 1, labels_per_column: 1 };
  }
  s = applyThermalRollLayout(s);
  const params = {
    width_mm: Number(s.width_mm),
    height_mm: Number(s.height_mm),
    labels_per_row: Math.max(1, Number(s.labels_per_row) || 1),
    labels_per_column: Math.max(1, Number(s.labels_per_column) || 1),
    gutter_mm: Number(s.gutter_mm) || 0,
    sheet_mode: s.sheet_mode || 'thermal',
    margin_top_mm: Number(s.margin_top_mm) || 0,
    margin_left_mm: Number(s.margin_left_mm) || 0,
    dpi: normalizeLabelDpi(s.dpi),
  };
  if (params.sheet_mode === 'avery') {
    params.sheet_width_mm = Number(s.sheet_width_mm) || 210;
    params.sheet_height_mm = Number(s.sheet_height_mm) || 297;
  }
  return params;
}

export function layoutPageLabel(layout, { forceSingle = true } = {}) {
  const params = layoutToQueryParams(layout, { forceSingle });
  return labelPageSizeLabel(computeLabelPageSizeMm(params));
}

export function hospitalSettingsPayloadKey(kind) {
  return settingsKeyForKind(kind);
}
