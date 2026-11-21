import React from 'react';
import { Label } from '../ui/label';
import {
  EVERY_HOURS_OPTION,
  FOOD_TIMING_OPTIONS,
  FREQUENCY_OPTIONS,
  everyHoursGap,
  everyHoursSchedule,
} from '../../utils/prescriptionSchedule';

/**
 * When-to-take dropdown. Choosing "Every N hours" shows a gap the doctor can set.
 */
export function FrequencySelect({
  value = '1-0-0',
  onChange,
  selectClassName = 'w-full h-9 text-xs border border-gray-200 rounded px-2 bg-white',
}) {
  const hours = everyHoursGap(value);
  const selectValue = hours ? EVERY_HOURS_OPTION : (value || '1-0-0');

  return (
    <div className="space-y-1">
      <select
        value={selectValue}
        onChange={(e) => {
          const next = e.target.value;
          onChange(next === EVERY_HOURS_OPTION ? everyHoursSchedule(8) : next);
        }}
        className={selectClassName}
      >
        {FREQUENCY_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
        <option value={EVERY_HOURS_OPTION}>Every N hours</option>
      </select>
      {hours != null && (
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-gray-500 shrink-0">Every</span>
          <input
            type="number"
            min="1"
            max="24"
            step="1"
            aria-label="Hours between doses"
            value={hours}
            onChange={(e) => onChange(everyHoursSchedule(e.target.value))}
            className="w-12 h-7 text-xs border border-gray-200 rounded px-1 text-center bg-white"
          />
          <span className="text-[10px] text-gray-500 shrink-0">hrs</span>
        </div>
      )}
    </div>
  );
}

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
        <FrequencySelect
          value={frequencySchedule}
          onChange={onFrequencyChange}
          selectClassName={selectClassName}
        />
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
