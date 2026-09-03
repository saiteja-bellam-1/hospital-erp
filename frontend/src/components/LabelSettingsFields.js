import React from 'react';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import {
  applyThermalRollLayout,
  computeLabelPageSizeMm,
  labelPageSizeLabel,
  stickersAcrossRoll,
} from '../utils/labelPageSize';

const PRESETS = {
  thermal_50x30: { width_mm: 50, height_mm: 30, labels_per_row: 1, labels_per_column: 1, sheet_mode: 'thermal' },
  thermal_40x30: { width_mm: 40, height_mm: 30, labels_per_row: 1, labels_per_column: 1, sheet_mode: 'thermal' },
  thermal_38x25: { width_mm: 38, height_mm: 25, labels_per_row: 1, labels_per_column: 1, sheet_mode: 'thermal' },
  thermal_38x25_2up: { width_mm: 38, height_mm: 25, labels_per_row: 2, labels_per_column: 1, gutter_mm: 2, sheet_mode: 'thermal' },
  thermal_38x25_3up: { width_mm: 38, height_mm: 25, labels_per_row: 3, labels_per_column: 1, gutter_mm: 2, sheet_mode: 'thermal' },
  avery_3x8: { width_mm: 66, height_mm: 25.4, labels_per_row: 3, labels_per_column: 8, sheet_mode: 'avery', sheet_width_mm: 210, sheet_height_mm: 297 },
};

/** React controlled inputs must not receive null — use empty string instead. */
const numInputValue = (v) => (v == null ? '' : v);

function LabelSettingsFields({ title, settings, onChange, showLabName = false }) {
  const isThermal = (settings.sheet_mode || 'thermal') === 'thermal';
  const normalized = applyThermalRollLayout(settings);
  const applyPreset = (key) => {
    const p = PRESETS[key];
    if (p) onChange({ ...settings, ...p });
  };
  const pageSize = labelPageSizeLabel(computeLabelPageSizeMm(normalized));
  const across = stickersAcrossRoll(normalized);

  const setStickersAcross = (count) => {
    onChange(applyThermalRollLayout({
      ...settings,
      labels_per_row: count,
      labels_per_column: 1,
    }));
  };

  return (
    <div className="space-y-3 rounded-lg border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">{title}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">PDF page: {pageSize}</p>
          {isThermal && across > 1 && (
            <p className="text-xs text-muted-foreground">
              {across} stickers side-by-side on one peel line — bulk print fills left to right.
            </p>
          )}
        </div>
        <Select onValueChange={applyPreset}>
          <SelectTrigger className="h-8 w-48 text-xs">
            <SelectValue placeholder="Preset…" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="thermal_50x30">Thermal 50×30 mm (1 across)</SelectItem>
            <SelectItem value="thermal_40x30">Thermal 40×30 mm (1 across)</SelectItem>
            <SelectItem value="thermal_38x25">Thermal 38×25 mm (1 across)</SelectItem>
            <SelectItem value="thermal_38x25_2up">Thermal 38×25 mm (2 across)</SelectItem>
            <SelectItem value="thermal_38x25_3up">Thermal 38×25 mm (3 across)</SelectItem>
            <SelectItem value="avery_3x8">Avery 3×8 on A4</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <Label className="text-xs">Sticker width (mm)</Label>
          <Input className="h-8" type="number" value={numInputValue(settings.width_mm)}
            onChange={(e) => onChange({ ...settings, width_mm: parseFloat(e.target.value) || 0 })} />
        </div>
        <div>
          <Label className="text-xs">Sticker height (mm)</Label>
          <Input className="h-8" type="number" value={numInputValue(settings.height_mm)}
            onChange={(e) => onChange({ ...settings, height_mm: parseFloat(e.target.value) || 0 })} />
        </div>
        {isThermal ? (
          <div>
            <Label className="text-xs">Stickers across roll</Label>
            <Select
              value={String(across)}
              onValueChange={(v) => setStickersAcross(parseInt(v, 10) || 1)}
            >
              <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="1">1 per line</SelectItem>
                <SelectItem value="2">2 per line</SelectItem>
                <SelectItem value="3">3 per line</SelectItem>
              </SelectContent>
            </Select>
          </div>
        ) : (
          <>
            <div>
              <Label className="text-xs">Labels per row (sheet)</Label>
              <Input className="h-8" type="number" min={1} value={numInputValue(settings.labels_per_row)}
                onChange={(e) => onChange({ ...settings, labels_per_row: parseInt(e.target.value, 10) || 1 })} />
            </div>
            <div>
              <Label className="text-xs">Labels per column (sheet)</Label>
              <Input className="h-8" type="number" min={1} value={numInputValue(settings.labels_per_column)}
                onChange={(e) => onChange({ ...settings, labels_per_column: parseInt(e.target.value, 10) || 1 })} />
            </div>
          </>
        )}
        <div>
          <Label className="text-xs">Gap between stickers (mm)</Label>
          <Input className="h-8" type="number" value={numInputValue(settings.gutter_mm)}
            onChange={(e) => onChange({ ...settings, gutter_mm: parseFloat(e.target.value) || 0 })} />
        </div>
        <div>
          <Label className="text-xs">Printer type</Label>
          <Select
            value={settings.sheet_mode || 'thermal'}
            onValueChange={(v) => onChange(applyThermalRollLayout({ ...settings, sheet_mode: v }))}
          >
            <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="thermal">Thermal roll</SelectItem>
              <SelectItem value="avery">Avery sheet</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {!isThermal && (
          <>
            <div>
              <Label className="text-xs">Margin top (mm)</Label>
              <Input className="h-8" type="number" value={numInputValue(settings.margin_top_mm)}
                onChange={(e) => onChange({ ...settings, margin_top_mm: parseFloat(e.target.value) || 0 })} />
            </div>
            <div>
              <Label className="text-xs">Margin left (mm)</Label>
              <Input className="h-8" type="number" value={numInputValue(settings.margin_left_mm)}
                onChange={(e) => onChange({ ...settings, margin_left_mm: parseFloat(e.target.value) || 0 })} />
            </div>
            <div>
              <Label className="text-xs">Sheet width (mm)</Label>
              <Input className="h-8" type="number" value={numInputValue(settings.sheet_width_mm)}
                onChange={(e) => onChange({ ...settings, sheet_width_mm: parseFloat(e.target.value) || 210 })} />
            </div>
            <div>
              <Label className="text-xs">Sheet height (mm)</Label>
              <Input className="h-8" type="number" value={numInputValue(settings.sheet_height_mm)}
                onChange={(e) => onChange({ ...settings, sheet_height_mm: parseFloat(e.target.value) || 297 })} />
            </div>
          </>
        )}
        {showLabName && (
          <div className="col-span-2">
            <Label className="text-xs">Lab name override (optional)</Label>
            <Input className="h-8" value={settings.lab_name_override || ''}
              onChange={(e) => onChange({ ...settings, lab_name_override: e.target.value || null })} />
          </div>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        {isThermal ? (
          <>
            Thermal: one PDF row matches one peel line on the roll. Printing 3 purchase batches with
            &ldquo;3 across&rdquo; places all three barcodes side-by-side — use <strong>Print combined PDF</strong>
            (not &ldquo;print in sequence&rdquo;). Set the OS print dialog to the computed page size at 100% scale.
          </>
        ) : (
          <>
            Avery: labels fill the sheet left-to-right, then top-to-bottom. Use margins to align with
            pre-cut sticker sheets.
          </>
        )}
      </p>
    </div>
  );
}

export default LabelSettingsFields;
