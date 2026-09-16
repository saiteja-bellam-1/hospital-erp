import axios from 'axios';

/**
 * Print a thermal label via server-rendered HTML with exact @page size (mm).
 * Prefer this over PDF for roll printers — Chrome/Edge honor @page size better.
 *
 * @param {string} urlOrPath - Absolute API path (e.g. "/api/pharmacy/.../label.html")
 * @param {object} [options]
 *   params {object} query params (layout overrides)
 *   method {'get'|'post'}
 *   body {object} POST JSON body
 *   onError {function(string)}
 * @returns {Promise<boolean>}
 */
export async function printThermalLabelHtml(urlOrPath, options = {}) {
  if (!urlOrPath) return false;

  const fail = (message) => {
    if (options.onError) options.onError(message);
    return false;
  };

  const method = (options.method || 'get').toLowerCase();
  const params = {
    ...(options.params || {}),
    _v: options.params?._v ?? Date.now(),
  };

  let html;
  try {
    const res = method === 'post'
      ? await axios.post(urlOrPath, options.body || {}, {
          params,
          responseType: 'text',
          headers: { Accept: 'text/html' },
          transformResponse: [(data) => data],
        })
      : await axios.get(urlOrPath, {
          params,
          responseType: 'text',
          headers: { Accept: 'text/html' },
          transformResponse: [(data) => data],
        });
    html = typeof res.data === 'string' ? res.data : String(res.data || '');
    if (!html.includes('<html') && !html.includes('<!DOCTYPE')) {
      try {
        const j = JSON.parse(html);
        return fail(typeof j.detail === 'string' ? j.detail : 'Could not load label HTML');
      } catch {
        return fail('Server returned an unexpected response');
      }
    }
  } catch (err) {
    const detail = err.response?.data;
    if (typeof detail === 'string') {
      try {
        const j = JSON.parse(detail);
        return fail(typeof j.detail === 'string' ? j.detail : detail.slice(0, 200));
      } catch {
        return fail(detail.slice(0, 200) || 'Could not load label HTML');
      }
    }
    if (typeof detail?.detail === 'string') return fail(detail.detail);
    return fail('Could not load label HTML');
  }

  const w = window.open('', '_blank', 'noopener,noreferrer,width=480,height=640');
  if (!w) {
    return fail('Pop-up blocked — allow pop-ups to print thermal labels, or use Download PDF');
  }
  try {
    w.document.open();
    w.document.write(html);
    w.document.close();
    return true;
  } catch (e) {
    console.error('printThermalLabelHtml: write failed', e);
    try { w.close(); } catch (_) { /* ignore */ }
    return fail('Could not open print window');
  }
}

/** Map a .pdf label path to the matching .html thermal print path. */
export function labelPdfPathToHtml(path) {
  if (!path || typeof path !== 'string') return null;
  if (path.endsWith('.html')) return path;
  if (path.endsWith('.pdf')) return `${path.slice(0, -4)}.html`;
  return null;
}
