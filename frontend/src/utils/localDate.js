/** Local calendar date as YYYY-MM-DD (avoids UTC shift from toISOString). */
export function localDateString(date = new Date()) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** YYYY-MM-DD for today ± N calendar days in local system time. */
export function localDateStringOffset(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return localDateString(d);
}

/** Monday (or today if Monday) of the week containing `date`, as YYYY-MM-DD. */
export function localWeekStart(date = new Date()) {
  const d = date instanceof Date ? new Date(date) : new Date(date);
  const day = d.getDay(); // 0 = Sunday
  const diff = day === 0 ? 6 : day - 1;
  d.setDate(d.getDate() - diff);
  return localDateString(d);
}

/** First day of the month containing `date`, as YYYY-MM-DD. */
export function localMonthStart(date = new Date()) {
  const d = date instanceof Date ? new Date(date) : new Date(date);
  return localDateString(new Date(d.getFullYear(), d.getMonth(), 1));
}

/** Previous calendar month as { from, to } YYYY-MM-DD inclusive. */
export function localLastMonthRange(date = new Date()) {
  const d = date instanceof Date ? new Date(date) : new Date(date);
  const from = new Date(d.getFullYear(), d.getMonth() - 1, 1);
  const to = new Date(d.getFullYear(), d.getMonth(), 0);
  return { from: localDateString(from), to: localDateString(to) };
}

/** Local datetime as YYYY-MM-DDTHH:mm for <input type="datetime-local">. */
export function localDateTimeString(date = new Date()) {
  const d = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(d.getTime())) return '';
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const h = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${y}-${m}-${day}T${h}:${min}`;
}

/**
 * Convert a datetime-local value (or Date/ISO string) to a naive local
 * ISO string for the API — no UTC conversion, no trailing Z.
 */
export function localDateTimeToApi(value) {
  if (!value) return value;
  if (typeof value === 'string') {
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return `${value}:00`;
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(value)) return value.slice(0, 19);
  }
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return `${localDateTimeString(d)}:00`;
}
