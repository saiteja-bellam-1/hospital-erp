/** Normalize FastAPI / axios error detail for toast messages. */
export function detailMessage(detail, fallback = 'Request failed') {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => e.msg || e.message || JSON.stringify(e)).join(', ');
  }
  if (detail && typeof detail === 'object' && typeof detail.message === 'string') {
    return detail.message;
  }
  return fallback;
}

export function errorDetail(err, fallback = 'Request failed') {
  return detailMessage(err?.response?.data?.detail ?? err?.message, fallback);
}
