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
 * Print a PDF using an off-screen iframe.
 *
 * Accepts either:
 *   - a blob: URL (already-fetched PDF), or
 *   - an API path (e.g. "/api/inpatient/.../pdf"). Fetches with auth; letterhead
 *     is resolved server-side from Print Settings.
 *
 * Hidden iframes with display:none often produce blank prints on Windows
 * Chrome/Edge; we keep the iframe in the layout at 0×0 instead. Blob URLs are
 * kept alive long enough for the OS print dialog to finish loading the PDF.
 *
 * @param {string} urlOrPath - blob: URL or API path
 * @param {object} [options]
 *   params {object}  Extra query params (API-path mode only).
 *   filename {string}  Reserved; informational only.
 * @returns {Promise<boolean>} false when fetch/validation/print failed
 */
export const printPdfFromUrl = async (urlOrPath, options = {}) => {
  if (!urlOrPath) return false;

  let blobUrl = urlOrPath;
  let createdBlobHere = false;

  if (!urlOrPath.startsWith('blob:')) {
    const params = { ...(options.params || {}) };

    try {
      const res = await axios.get(urlOrPath, { responseType: 'blob', params });
      const contentType = res.headers['content-type'] || '';
      if (!(await isPdfBlob(res.data, contentType))) {
        try {
          const text = await res.data.text();
          console.error('printPdfFromUrl: server returned non-PDF response', text.slice(0, 500));
        } catch (_) { /* ignore */ }
        return false;
      }
      blobUrl = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      createdBlobHere = true;
    } catch (err) {
      console.error('printPdfFromUrl: failed to fetch PDF', err);
      return false;
    }
  }

  return new Promise((resolve) => {
    const iframe = document.createElement('iframe');
    // Off-screen but rendered — display:none breaks PDF printing on Windows.
    iframe.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;';
    document.body.appendChild(iframe);
    iframe.src = blobUrl;

    const cleanup = () => {
      setTimeout(() => {
        try { document.body.removeChild(iframe); } catch (_) { /* ignore */ }
        if (createdBlobHere) {
          try { URL.revokeObjectURL(blobUrl); } catch (_) { /* ignore */ }
        }
        resolve(true);
      }, CLEANUP_DELAY_MS);
    };

    iframe.onload = () => {
      setTimeout(() => {
        try {
          iframe.contentWindow?.focus();
          iframe.contentWindow?.print();
        } catch (e) {
          console.error('printPdfFromUrl: print() failed', e);
          if (createdBlobHere) {
            try { URL.revokeObjectURL(blobUrl); } catch (_) { /* ignore */ }
          }
          try { document.body.removeChild(iframe); } catch (_) { /* ignore */ }
          resolve(false);
          return;
        }
        cleanup();
      }, PRINT_RENDER_DELAY_MS);
    };
  });
};
