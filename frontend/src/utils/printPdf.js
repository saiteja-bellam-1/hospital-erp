import axios from 'axios';

const PRINT_RENDER_DELAY_MS = 500;
const CLEANUP_DELAY_MS = 60_000;

/**
 * Validate that a blob response is plausibly a PDF (not a JSON error page).
 * @returns {Promise<boolean>}
 */
async function isPdfBlob(blob, contentType = '') {
  if (!blob || blob.size < 80) return false;
  if (contentType.includes('application/pdf')) return true;
  try {
    const header = await blob.slice(0, 5).text();
    return header.startsWith('%PDF');
  } catch {
    return false;
  }
}

/**
 * Parse a FastAPI error body from a blob response.
 */
async function parseApiErrorFromBlob(blob) {
  try {
    const text = await blob.text();
    const json = JSON.parse(text);
    if (typeof json.detail === 'string') return json.detail;
    if (json.detail?.message) return json.detail.message;
    return text.slice(0, 200);
  } catch {
    return 'Server returned an unexpected response';
  }
}

/**
 * Print a PDF using an off-screen iframe.
 *
 * Accepts either:
 *   - a blob: URL (already-fetched PDF), or
 *   - an API path (e.g. "/api/inpatient/.../pdf"). Fetches with auth; letterhead
 *     is resolved server-side from Print Settings (global + per-report overrides).
 *     Do not pass include_header unless intentionally overriding the hospital default.
 *
 * Hidden iframes with display:none often produce blank prints on Windows
 * Chrome/Edge; we keep the iframe in the layout at 0×0 instead. Blob URLs are
 * kept alive long enough for the OS print dialog to finish loading the PDF.
 *
 * @param {string} urlOrPath - blob: URL or API path
 * @param {object} [options]
 *   params {object}  Extra query params (API-path mode only).
 *   filename {string}  Reserved; informational only.
 *   onError {function(string)}  Called with a user-facing message on failure.
 * @returns {Promise<boolean>} false when fetch/validation/print failed
 */
export const printPdfFromUrl = async (urlOrPath, options = {}) => {
  if (!urlOrPath) return false;

  const fail = (message) => {
    if (options.onError) options.onError(message);
    return false;
  };

  let blobUrl = urlOrPath;
  let createdBlobHere = false;

  if (!urlOrPath.startsWith('blob:')) {
    const params = { ...(options.params || {}) };

    try {
      const res = await axios.get(urlOrPath, { responseType: 'blob', params });
      const contentType = res.headers['content-type'] || '';
      if (!(await isPdfBlob(res.data, contentType))) {
        const msg = await parseApiErrorFromBlob(res.data);
        console.error('printPdfFromUrl: server returned non-PDF response', msg);
        return fail(msg);
      }
      blobUrl = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      createdBlobHere = true;
    } catch (err) {
      console.error('printPdfFromUrl: failed to fetch PDF', err);
      const blob = err.response?.data;
      if (blob instanceof Blob) {
        return fail(await parseApiErrorFromBlob(blob));
      }
      return fail(typeof err.response?.data?.detail === 'string'
        ? err.response.data.detail
        : 'Could not load the PDF');
    }
  }

  return new Promise((resolve) => {
    const iframe = document.createElement('iframe');
    // Off-screen but rendered — display:none breaks PDF printing on Windows.
    iframe.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;';
    document.body.appendChild(iframe);

    let settled = false;
    const done = (ok) => {
      if (settled) return;
      settled = true;
      resolve(ok);
    };

    const scheduleCleanup = () => {
      setTimeout(() => {
        try { document.body.removeChild(iframe); } catch (_) { /* ignore */ }
        if (createdBlobHere) {
          try { URL.revokeObjectURL(blobUrl); } catch (_) { /* ignore */ }
        }
      }, CLEANUP_DELAY_MS);
    };

    const triggerPrint = () => {
      if (settled) return;
      setTimeout(() => {
        if (settled) return;
        try {
          iframe.contentWindow?.focus();
          iframe.contentWindow?.print();
          done(true);
          scheduleCleanup();
        } catch (e) {
          console.error('printPdfFromUrl: print() failed', e);
          if (createdBlobHere) {
            try { URL.revokeObjectURL(blobUrl); } catch (_) { /* ignore */ }
          }
          try { document.body.removeChild(iframe); } catch (_) { /* ignore */ }
          if (options.onError) options.onError('Print dialog could not be opened');
          done(false);
        }
      }, PRINT_RENDER_DELAY_MS);
    };

    // Some browsers never fire onload for PDF blobs in a hidden iframe.
    const loadTimeout = setTimeout(triggerPrint, 10_000);

    iframe.onload = () => {
      clearTimeout(loadTimeout);
      triggerPrint();
    };

    iframe.src = blobUrl;
  });
};

/**
 * Fetch a PDF from the API and return a blob: URL for iframe preview.
 * Caller must revoke the URL when done.
 * @returns {Promise<string>}
 */
export async function fetchPdfBlobUrl(urlOrPath, options = {}) {
  const params = { ...(options.params || {}) };
  const res = await axios.get(urlOrPath, { responseType: 'blob', params });
  const contentType = res.headers['content-type'] || '';
  if (!(await isPdfBlob(res.data, contentType))) {
    const msg = await parseApiErrorFromBlob(res.data);
    throw new Error(msg);
  }
  return URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
}
