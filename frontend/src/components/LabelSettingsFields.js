import React from 'react';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';

const PRESETS = {
  thermal_50x30: { width_mm: 50, height_mm: 30, labels_per_row: 1, labels_per_column: 1, sheet_mode: 'thermal' },
  thermal_40x30: { width_mm: 40, height_mm: 30, labels_per_row: 1, labels_per_column: 1, sheet_mode: 'thermal' },
  thermal_38x25: { width_mm: 38, height_mm: 25, labels_per_row: 1, labels_per_column: 1, sheet_mode: 'thermal' },
  avery_3x8: { width_mm: 66, height_mm: 25.4, labels_per_row: 3, labels_per_column: 8, sheet_mode: 'avery', sheet_width_mm: 210, sheet_height_mm: 297 },
};

/** React controlled inputs must not receive null — use empty string instead. */
const numInputValue = (v) => (v == null ? '' : v);

function LabelSettingsFields({ title, settings, onChange, showLabName = false }) {
  const applyPreset = (key) => {
    const p = PRESETS[key];
    if (p) onChange({ ...settings, ...p });
  };

  return (
    <div className="space-y-3 rounded-lg border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        <Select onValueChange={applyPreset}>
          <SelectTrigger className="h-8 w-44 text-xs">
            <SelectValue placeholder="Preset…" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="thermal_50x30">Thermal 50×30 mm</SelectItem>
            <SelectItem value="thermal_40x30">Thermal 40×30 mm</SelectItem>
            <SelectItem value="thermal_38x25">Thermal 38×25 mm</SelectItem>
            <SelectItem value="avery_3x8">Avery 3×8 on A4</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <Label className="text-xs">Width (mm)</Label>
          <Input className="h-8" type="number" value={numInputValue(settings.width_mm)}
            onChange={(e) => onChange({ ...settings, width_mm: parseFloat(e.target.value) || 0 })} />
        </div>
        <div>
          <Label className="text-xs">Height (mm)</Label>
          <Input className="h-8" type="number" value={numInputValue(settings.height_mm)}
            onChange={(e) => onChange({ ...settings, height_mm: parseFloat(e.target.value) || 0 })} />
        </div>
        <div>
          <Label className="text-xs">Labels / row</Label>
          <Input className="h-8" type="number" min={1} value={numInputValue(settings.labels_per_row)}
            onChange={(e) => onChange({ ...settings, labels_per_row: parseInt(e.target.value, 10) || 1 })} />
        </div>
        <div>
          <Label className="text-xs">Labels / column</Label>
          <Input className="h-8" type="number" min={1} value={numInputValue(settings.labels_per_column)}
            onChange={(e) => onChange({ ...settings, labels_per_column: parseInt(e.target.value, 10) || 1 })} />
        </div>
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
          <Label className="text-xs">Gutter (mm)</Label>
          <Input className="h-8" type="number" value={numInputValue(settings.gutter_mm)}
            onChange={(e) => onChange({ ...settings, gutter_mm: parseFloat(e.target.value) || 0 })} />
        </div>
        <div>
          <Label className="text-xs">Sheet mode</Label>
          <Select value={settings.sheet_mode || 'thermal'} onValueChange={(v) => onChange({ ...settings, sheet_mode: v })}>
            <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="thermal">Thermal (one label/page)</SelectItem>
              <SelectItem value="avery">Avery sheet</SelectItem>
            </SelectContent>
          </Select>
        </div>
        {settings.sheet_mode === 'avery' && (
          <>
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
    </div>
  );
}

export default LabelSettingsFields;
