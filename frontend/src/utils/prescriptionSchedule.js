/** Shared prescription schedule / food-timing options (consultation + inpatient). */

export const FREQUENCY_OPTIONS = [
  { value: '1-0-0', label: 'Morning only' },
  { value: '0-1-0', label: 'Afternoon only' },
  { value: '0-0-1', label: 'Night only' },
  { value: '1-0-1', label: 'Morning & Night' },
  { value: '1-1-0', label: 'Morning & Afternoon' },
  { value: '1-1-1', label: 'Three times a day' },
  { value: '0-1-1', label: 'Afternoon & Night' },
];

export const FOOD_TIMING_OPTIONS = [
  { value: 'before_food', label: 'Before food' },
  { value: 'after_food', label: 'After food' },
  { value: 'with_food', label: 'With food' },
  { value: 'on_empty_stomach', label: 'Empty stomach' },
  { value: 'anytime', label: 'Anytime' },
];

const FOOD_TIMING_LABELS = Object.fromEntries(
  FOOD_TIMING_OPTIONS.map((o) => [o.value, o.label.toLowerCase()]),
);

/** Human-readable dosage line matching consultation / OPD prescription PDFs. */
export function buildDosageInstruction(dosage, frequencySchedule = '1-0-0', foodTiming = 'after_food') {
  const schedule = frequencySchedule || '1-0-0';
  const [morning, afternoon, night] = schedule.split('-');
  const timings = [];
  if (morning === '1') timings.push('morning');
  if (afternoon === '1') timings.push('afternoon');
  if (night === '1') timings.push('night');
  const frequencyText = timings.length > 0 ? timings.join(', ') : 'once daily';
  const foodLabel = FOOD_TIMING_LABELS[foodTiming] || 'after food';
  return `${dosage || '1 dose'} - ${frequencyText} ${foodLabel}`;
}

export const BLANK_INPATIENT_RX_ITEM = {
  medicine_id: '',
  medicine_name: '',
  dosage: '',
  frequency_schedule: '1-0-0',
  food_timing: 'after_food',
  duration: '',
  quantity_prescribed: 1,
  instructions: '',
};
