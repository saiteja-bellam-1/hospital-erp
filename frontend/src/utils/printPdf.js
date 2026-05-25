import axios from 'axios';

/**
 * Print a PDF using a hidden iframe.
 *
 * Accepts either:
 *   - a blob: URL (already-fetched PDF), or
 *   - an API path (e.g. "/api/inpatient/.../pdf"). In that case, the PDF is fetched
 *     with the current axios auth headers and converted to a blob URL before printing.
 *
 * @param {string} urlOrPath - blob: URL or API path
 * @param {object} [options]
 *   include_header {boolean}  Appends include_header=true query param (API-path mode only).
 *   params {object}           Extra query params (API-path mode only).
 *   filename {string}         Reserved; currently informational only.
 */
export const printPdfFromUrl = async (urlOrPath, options = {}) => {
  if (!urlOrPath) return;

  let blobUrl = urlOrPath;
  let createdBlobHere = false;

  if (!urlOrPath.startsWith('blob:')) {
    // API-path mode — fetch with auth and build blob URL
    const params = { ...(options.params || {}) };
    if (options.include_header) params.include_header = true;

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
