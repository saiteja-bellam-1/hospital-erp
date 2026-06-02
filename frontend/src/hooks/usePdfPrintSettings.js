import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

/**
 * Hospital-wide PDF letterhead setting from Hospital Config.
 * Query param `include_header` on PDF endpoints follows this value.
 */
export function usePdfPrintSettings() {
  const query = useQuery({
    queryKey: ['hospital-print-settings'],
    queryFn: async () => {
      const res = await axios.get('/api/hospital/print-settings');
      return res.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  const includeHeaderOnPdfs = query.data?.include_header_on_pdfs !== false;

  return {
    includeHeaderOnPdfs,
    isLoading: query.isLoading,
    refetch: query.refetch,
  };
}

/** For non-React callers (e.g. printPdf.js) — cached after first fetch. */
let cachedIncludeHeader = true;
let cachePromise = null;

export async function fetchPdfIncludeHeaderSetting() {
  if (cachePromise) return cachePromise;
  cachePromise = axios
    .get('/api/hospital/print-settings')
    .then((res) => {
      cachedIncludeHeader = res.data?.include_header_on_pdfs !== false;
      return cachedIncludeHeader;
    })
    .catch(() => cachedIncludeHeader);
  return cachePromise;
}

export function getCachedPdfIncludeHeader() {
  return cachedIncludeHeader;
}

export function invalidatePdfIncludeHeaderCache() {
  cachePromise = null;
  cachedIncludeHeader = true;
}

/** Merge hospital print setting into query params for PDF API calls. */
export async function pdfRequestParams(extra = {}) {
  await fetchPdfIncludeHeaderSetting();
  return { ...extra, include_header: getCachedPdfIncludeHeader() };
}
