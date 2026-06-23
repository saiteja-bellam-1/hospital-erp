import React from 'react';
import { Label } from '../ui/label';
import { FREQUENCY_OPTIONS, FOOD_TIMING_OPTIONS } from '../../utils/prescriptionSchedule';

/**
 * Schedule + food-timing dropdowns used on consultation and inpatient Rx forms.
 */
export default function PrescriptionScheduleFields({
  frequencySchedule = '1-0-0',
  foodTiming = 'after_food',
  onFrequencyChange,
  onFoodTimingChange,
  labelClassName = 'text-[10px] text-gray-500',
  selectClassName = 'w-full h-9 text-xs border border-gray-200 rounded px-2 bg-white',
}) {
  return (
    <>
      <div>
        <Label className={labelClassName}>When to take *</Label>
        <select
          value={frequencySchedule || '1-0-0'}
          onChange={(e) => onFrequencyChange(e.target.value)}
          className={selectClassName}
        >
          {FREQUENCY_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
      <div>
        <Label className={labelClassName}>Food timing *</Label>
        <select
          value={foodTiming || 'after_food'}
          onChange={(e) => onFoodTimingChange(e.target.value)}
          className={selectClassName}
        >
          {FOOD_TIMING_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
    </>
  );
}
