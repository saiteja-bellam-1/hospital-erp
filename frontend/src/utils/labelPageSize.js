/** Compute thermal/Avery PDF page size (mm) from saved label settings. */

const DEFAULT_PHARMACY = {
  width_mm: 38,
  height_mm: 25,
  labels_per_row: 1,
  labels_per_column: 1,
  gutter_mm: 2,
  sheet_mode: 'thermal',
  sheet_width_mm: 210,
  sheet_height_mm: 297,
};

const DEFAULT_LAB = {
  width_mm: 50,
  height_mm: 30,
  labels_per_row: 1,
  labels_per_column: 1,
  gutter_mm: 2,
  sheet_mode: 'thermal',
  sheet_width_mm: 210,
  sheet_height_mm: 297,
};

/** Thermal rolls: stickers only sit side-by-side across the roll (one peel row). */
export function applyThermalRollLayout(settings) {
  const s = settings || {};
  if ((s.sheet_mode || 'thermal') !== 'thermal') return { ...s };
  let row = Math.max(1, Number(s.labels_per_row) || 1);
  const col = Math.max(1, Number(s.labels_per_column) || 1);
  if (col > 1 && row === 1) row = col;
  return { ...s, labels_per_row: row, labels_per_column: 1 };
}

export function computeLabelPageSizeMm(settings) {
  const s = applyThermalRollLayout(settings || {});
  if (s.sheet_mode === 'avery') {
    return {
      width_mm: Number(s.sheet_width_mm) || 210,
      height_mm: Number(s.sheet_height_mm) || 297,
    };
  }
  const labelW = Number(s.width_mm) || 38;
  const labelH = Number(s.height_mm) || 25;
  const cols = Math.max(1, Number(s.labels_per_row) || 1);
  const rows = Math.max(1, Number(s.labels_per_column) || 1);
  const gutter = Number(s.gutter_mm) || 0;
  return {
    width_mm: cols * labelW + Math.max(0, cols - 1) * gutter,
    height_mm: rows * labelH + Math.max(0, rows - 1) * gutter,
  };
}

export function pharmacyLabelPageSize(printSettings) {
  return computeLabelPageSizeMm({
    ...DEFAULT_PHARMACY,
    ...(printSettings?.pharmacy_label_settings || {}),
  });
}

export function labLabelPageSize(printSettings) {
  return computeLabelPageSizeMm({
    ...DEFAULT_LAB,
    ...(printSettings?.lab_label_settings || {}),
  });
}

export function labelPageSizeLabel(page) {
  const w = Math.round(page.width_mm * 10) / 10;
  const h = Math.round(page.height_mm * 10) / 10;
  return `${w} × ${h} mm`;
}

export function stickersAcrossRoll(settings) {
  const s = applyThermalRollLayout(settings || {});
  return Math.max(1, Number(s.labels_per_row) || 1);
}
