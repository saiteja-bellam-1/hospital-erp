import axios from 'axios';
import { fetchPdfIncludeHeaderSetting, getCachedPdfIncludeHeader } from '../hooks/usePdfPrintSettings';

/**
 * Print a PDF using a hidden iframe.
 *
 * Accepts either:
 *   - a blob: URL (already-fetched PDF), or
 *   - an API path (e.g. "/api/inpatient/.../pdf"). Fetches with auth; letterhead
 *     follows Hospital Config print settings via include_header query param.
 *
 * @param {string} urlOrPath - blob: URL or API path
 * @param {object} [options]
 *   params {object}  Extra query params (API-path mode only).
 *   filename {string}  Reserved; informational only.
 */
export const printPdfFromUrl = async (urlOrPath, options = {}) => {
  if (!urlOrPath) return;

  let blobUrl = urlOrPath;
  let createdBlobHere = false;

  if (!urlOrPath.startsWith('blob:')) {
    await fetchPdfIncludeHeaderSetting();
    const params = { ...(options.params || {}) };
    params.include_header = getCachedPdfIncludeHeader();

    try {
      const res = await axios.get(urlOrPath, { responseType: 'blob', params });
      blobUrl = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      createdBlobHere = true;
    } catch (err) {
      console.error('printPdfFromUrl: failed to fetch PDF', err);
      return;
    }
  }

  const iframe = document.createElement('iframe');
  iframe.style.display = 'none';
  document.body.appendChild(iframe);
  iframe.src = blobUrl;
  iframe.onload = () => {
    try { iframe.contentWindow.print(); } catch (e) { console.error(e); }
    setTimeout(() => {
      try { document.body.removeChild(iframe); } catch (e) {}
      if (createdBlobHere) URL.revokeObjectURL(blobUrl);
    }, 1000);
  };
};
