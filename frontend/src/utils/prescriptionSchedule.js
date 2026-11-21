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

/** Select value that reveals the hour-gap field. Stored schedules use q8h, q6h, and so on. */
export const EVERY_HOURS_OPTION = 'every-hours';

/** Gap in hours for a q8h-style schedule, or null when it is a morning/afternoon/night code. */
export function everyHoursGap(schedule) {
  const match = String(schedule || '').trim().match(/^q(\d+)h$/i);
  if (!match) return null;
  const hours = parseInt(match[1], 10);
  if (!Number.isFinite(hours) || hours < 1 || hours > 24) return null;
  return hours;
}

/** Build a stored schedule from the hour gap the doctor typed. */
export function everyHoursSchedule(hours) {
  const parsed = parseInt(hours, 10);
  const gap = Number.isFinite(parsed) ? Math.min(24, Math.max(1, parsed)) : 8;
  return `q${gap}h`;
}

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
  const foodLabel = FOOD_TIMING_LABELS[foodTiming] || 'after food';
  const hours = everyHoursGap(schedule);
  if (hours) {
    const unit = hours === 1 ? 'hour' : 'hours';
    return `${dosage || '1 dose'} - every ${hours} ${unit} ${foodLabel}`;
  }
  const [morning, afternoon, night] = schedule.split('-');
  const timings = [];
  if (morning === '1') timings.push('morning');
  if (afternoon === '1') timings.push('afternoon');
  if (night === '1') timings.push('night');
  const frequencyText = timings.length > 0 ? timings.join(', ') : 'once daily';
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

/** Take-home meds on discharge — same schedule fields as consultation Rx. */
export const BLANK_TAKE_HOME_MED = {
  medicine_id: '',
  medicine_name: '',
  dosage: '',
  frequency_schedule: '1-0-0',
  food_timing: 'after_food',
  duration: '',
  quantity: '',
  instructions: '',
};

export function frequencyScheduleLabel(schedule = '1-0-0') {
  const hours = everyHoursGap(schedule);
  if (hours) return `Every ${hours} ${hours === 1 ? 'hour' : 'hours'}`;
  return FREQUENCY_OPTIONS.find((o) => o.value === schedule)?.label || schedule;
}

export function foodTimingLabel(timing = 'after_food') {
  return FOOD_TIMING_OPTIONS.find((o) => o.value === timing)?.label || timing;
}

/** Shown on quantity fields that fill themselves from dosage, schedule, and duration. */
export const MEDICINE_QTY_HINT = 'Filled from dosage, how often it is taken, and duration. You can edit it.';

const DOSE_NUMBER = '(?:\\d+(?:\\.\\d+)?|\\.\\d+)';
const DOSE_UNIT_RE = new RegExp(
  `(${DOSE_NUMBER})\\s*(tabs?|tablets?|caps?|capsules?|drops?|mls?|millilit(?:er|re)s?|tsp|tsps|teaspoons?|tbsp|tablespoons?|puffs?|sachets?|amps?|ampoules?|vials?|units?|inj)\\b`,
  'i',
);
const STRENGTH_RE = /\d+(?:\.\d+)?\s*(?:mg|mcg|µg|ug|g|gm|gms|iu|i\.u|%)\b/i;
const SCHEDULE_RE = /(\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?){1,3})/;
const AS_NEEDED_RE = /\b(sos|s\.o\.s|prn|p\.r\.n|stat|as needed|as required|if needed)\b/i;

function roundQty(value) {
  if (!Number.isFinite(value) || value <= 0) return null;
  const rounded = Math.round(value * 1000) / 1000;
  return rounded > 0 ? rounded : null;
}

/** Doses in a day. 1-0-1 is 2. Every 8 hours (q8h) is 3. Null when it is not a schedule. */
export function dosesPerDay(frequencySchedule) {
  const raw = String(frequencySchedule || '').trim();
  const hours = everyHoursGap(raw);
  if (hours) return 24 / hours;
  const match = raw.match(/^(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?)){1,3}$/);
  if (!match) return null;
  const parts = raw.split('-').map((part) => parseFloat(part.trim()));
  if (parts.some((n) => !Number.isFinite(n) || n < 0 || n > 10)) return null;
  const sum = parts.reduce((total, n) => total + n, 0);
  return sum > 0 ? sum : null;
}

function embeddedSchedule(dosage) {
  const match = String(dosage || '').match(SCHEDULE_RE);
  if (!match) return null;
  const parts = match[1].split('-').map((part) => parseFloat(part.trim()));
  if (parts.some((n) => !Number.isFinite(n) || n < 0 || n > 10)) return null;
  const sum = parts.reduce((total, n) => total + n, 0);
  if (sum <= 0) return null;
  return { sum, max: Math.max(...parts) };
}

function frequencyFromText(dosage) {
  const text = String(dosage || '').toLowerCase();
  if (!text) return null;
  const everyHours = text.match(/\bq\s*(\d+)\s*h\b/);
  if (everyHours) {
    const hours = parseInt(everyHours[1], 10);
    if (hours > 0 && hours <= 24) return Math.max(1, Math.round(24 / hours));
  }
  if (/\b(qid|q\.i\.d|4\s*times|four times)\b/.test(text)) return 4;
  if (/\b(tds|t\.d\.s|tid|t\.i\.d|thrice|3\s*times|three times)\b/.test(text)) return 3;
  if (/\b(bd|b\.d|bid|b\.i\.d|twice|2\s*times|two times)\b/.test(text)) return 2;
  const dayParts = ['morning', 'afternoon', 'night'].filter((part) => (
    new RegExp(`\\b${part}\\b`).test(text)
  ));
  if (dayParts.length > 0) return dayParts.length;
  if (/\b(od|o\.d|hs|h\.s|once daily|once a day|once|one time|daily)\b/.test(text)) return 1;
  const embedded = embeddedSchedule(text);
  if (embedded && embedded.max <= 1) return embedded.sum;
  return null;
}

/** Units given at each administration. Strength-only text such as "500 mg" counts as 1. */
export function parseDoseUnits(dosage) {
  const text = String(dosage || '').trim().toLowerCase().replace(/½/g, '1/2');
  if (!text) return null;
  const fraction = text.match(/(\d+)\s*\/\s*(\d+)/);
  if (fraction) {
    const units = parseFloat(fraction[1]) / parseFloat(fraction[2]);
    if (units > 0 && units <= 10) return units;
  }
  const withoutSchedule = text.replace(SCHEDULE_RE, ' ');
  const unit = withoutSchedule.match(DOSE_UNIT_RE);
  if (unit && withoutSchedule[unit.index - 1] !== '/') {
    const units = parseFloat(unit[1]);
    if (units > 0) return units;
  }
  if (STRENGTH_RE.test(text) && !DOSE_UNIT_RE.test(withoutSchedule)) return 1;
  if (/\b(one|a)\s+(tab|tablet|cap|capsule|drop)\b/.test(withoutSchedule)) return 1;
  const bare = withoutSchedule.match(new RegExp(DOSE_NUMBER));
  if (bare) {
    const units = parseFloat(bare[0]);
    if (units > 0 && units <= 8) return units;
  }
  if (/\b(tab|tablet|cap|capsule)\b/.test(withoutSchedule)) return 1;
  return null;
}

/** Days in a duration such as "5", "5 days", "2 weeks", or "1 month". */
export function parseDurationDays(duration) {
  const text = String(duration || '').trim().toLowerCase();
  if (!text) return null;
  if (/\bfortnight\b/.test(text)) return 14;
  if (/\b(?:a|one)\s+week\b/.test(text)) return 7;
  if (/\b(?:a|one)\s+month\b/.test(text)) return 30;
  const weeks = text.match(/(\d+(?:\.\d+)?)\s*(?:weeks?|wks?|w)\b/);
  if (weeks) return Math.max(1, Math.round(parseFloat(weeks[1]) * 7));
  const months = text.match(/(\d+(?:\.\d+)?)\s*(?:months?|mons?)\b/);
  if (months) return Math.max(1, Math.round(parseFloat(months[1]) * 30));
  const days = text.match(/(\d+(?:\.\d+)?)\s*(?:days?|d)\b/);
  if (days) return Math.max(1, Math.round(parseFloat(days[1])));
  const bare = text.match(/^(\d+(?:\.\d+)?)$/);
  if (bare) return Math.max(1, Math.round(parseFloat(bare[1])));
  const any = text.match(/(\d+)/);
  if (!any) return null;
  const value = parseInt(any[1], 10);
  return value > 0 ? value : null;
}

/**
 * Tablets (or other units) for the full course.
 * Schedule codes count administrations per day. A dosage written as 2-0-2 is already
 * the daily total. Returns null for SOS/PRN or when dosage and duration are incomplete.
 */
export function calcMedicineQuantity({ dosage, frequencySchedule, duration } = {}) {
  if (AS_NEEDED_RE.test(String(dosage || ''))) return null;
  const days = parseDurationDays(duration);
  if (!days) return null;

  const fieldTimes = dosesPerDay(frequencySchedule);
  const embedded = embeddedSchedule(dosage);
  const hasUnit = DOSE_UNIT_RE.test(String(dosage || '').replace(/½/g, '1/2'));
  const scheduleOnly = Boolean(embedded) && !hasUnit && !STRENGTH_RE.test(String(dosage || ''));

  if (scheduleOnly) {
    return roundQty(embedded.sum * days);
  }

  const perDose = parseDoseUnits(dosage);
  if (!perDose) return null;
  let perDay = fieldTimes;
  if (perDay == null) perDay = frequencyFromText(dosage);
  if (perDay == null) perDay = 1;
  return roundQty(perDose * perDay * days);
}

const QTY_DRIVER_FIELDS = new Set(['dosage', 'frequency_schedule', 'duration']);

/** Update one medicine row, recalculating quantity when dosage, schedule, or duration changes. */
export function patchMedicineLine(line, field, value, qtyKey = 'quantity_prescribed') {
  const next = { ...(line || {}), [field]: value };
  if (!QTY_DRIVER_FIELDS.has(field)) return next;
  const qty = calcMedicineQuantity({
    dosage: next.dosage,
    frequencySchedule: next.frequency_schedule,
    duration: next.duration,
  });
  if (qty == null) return next;
  const stored = typeof line?.[qtyKey] === 'number' ? qty : String(qty);
  return { ...next, [qtyKey]: stored };
}

/** Quantity already typed on the row, or the calculated course when that field is empty. */
export function medicineQuantityOrCalculated(line, qtyKey = 'quantity_prescribed') {
  const typed = parseFloat(line?.[qtyKey]);
  if (typed > 0) return Math.round(typed * 1000) / 1000;
  return calcMedicineQuantity({
    dosage: line?.dosage,
    frequencySchedule: line?.frequency_schedule,
    duration: line?.duration,
  }) || 1;
}

/** Map a take-home med form row to the discharge API payload. */
export function serializeTakeHomeMed(m) {
  const schedule = m.frequency_schedule || '1-0-0';
  const food = m.food_timing || 'after_food';
  const extra = m.instructions?.trim() || '';
  const foodLabel = foodTimingLabel(food);
  return {
    medicine_id: m.medicine_id ? parseInt(m.medicine_id, 10) : null,
    medicine_name: m.medicine_name.trim(),
    dosage: m.dosage?.trim() || null,
    frequency: frequencyScheduleLabel(schedule),
    duration: m.duration?.trim() || null,
    quantity: m.quantity ? (Math.round(parseFloat(m.quantity) * 1000) / 1000 || null) : null,
    instructions: extra ? `${foodLabel}. ${extra}` : foodLabel,
    frequency_schedule: schedule,
    food_timing: food,
  };
}
