import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

/**
 * Hospital-wide PDF print settings (letterhead, gap, per-report overrides).
 * Backend resolves include_header per PDF endpoint; this hook is for the settings UI
 * and optional client-side preview helpers.
 */

let cachedSettings = null;
let cachePromise = null;

export function resolveIncludeHeaderForReport(settings, reportType) {
  if (!settings) return true;
  const globalDefault = settings.include_header_on_pdfs !== false;
  const overrides = settings.report_header_overrides || {};
  if (reportType && overrides[reportType]) {
    const ov = overrides[reportType];
    if (ov === 'on') return true;
    if (ov === 'off') return false;
  }
  return globalDefault;
}

const FOOTER_REPORT_KEYS = new Set(['opd_bill', 'lab_bill', 'lab_report']);

export function resolveIncludeFooterForReport(settings, reportType) {
  if (!settings) return true;
  if (reportType && !FOOTER_REPORT_KEYS.has(reportType)) return true;
  const globalDefault = settings.include_footer_on_pdfs !== false;
  const overrides = settings.report_footer_overrides || {};
  if (reportType && overrides[reportType]) {
    const ov = overrides[reportType];
    if (ov === 'on') return true;
    if (ov === 'off') return false;
  }
  return globalDefault;
}

export function usePdfPrintSettings() {
  const query = useQuery({
    queryKey: ['hospital-print-settings'],
    queryFn: async () => {
      const res = await axios.get('/api/hospital/print-settings');
      cachedSettings = res.data;
      return res.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  const settings = query.data;
  const includeHeaderOnPdfs = settings?.include_header_on_pdfs !== false;
  const includeFooterOnPdfs = settings?.include_footer_on_pdfs !== false;

  return {
    settings,
    includeHeaderOnPdfs,
    includeFooterOnPdfs,
    letterheadGapMm: settings?.letterhead_gap_mm ?? 35,
    reportCatalog: settings?.report_catalog ?? [],
    footerReportCatalog: settings?.footer_report_catalog ?? [],
    reportHeaderOverrides: settings?.report_header_overrides ?? {},
    reportFooterOverrides: settings?.report_footer_overrides ?? {},
    isLoading: query.isLoading,
    refetch: query.refetch,
    resolveIncludeHeader: (reportType) => resolveIncludeHeaderForReport(settings, reportType),
    resolveIncludeFooter: (reportType) => resolveIncludeFooterForReport(settings, reportType),
  };
}

/** For non-React callers — cached after first fetch. */
export async function fetchPdfPrintSettings() {
  if (cachePromise) return cachePromise;
  cachePromise = axios
    .get('/api/hospital/print-settings')
    .then((res) => {
      cachedSettings = res.data;
      return cachedSettings;
    })
    .catch(() => cachedSettings || { include_header_on_pdfs: true, letterhead_gap_mm: 35 });
  return cachePromise;
}

/** @deprecated use fetchPdfPrintSettings */
export async function fetchPdfIncludeHeaderSetting() {
  const s = await fetchPdfPrintSettings();
  return resolveIncludeHeaderForReport(s, null);
}

export function getCachedPdfIncludeHeader(reportType = null) {
  return resolveIncludeHeaderForReport(cachedSettings, reportType);
}

export function invalidatePdfPrintSettingsCache() {
  cachePromise = null;
  cachedSettings = null;
}

/** @deprecated use invalidatePdfPrintSettingsCache */
export function invalidatePdfIncludeHeaderCache() {
  invalidatePdfPrintSettingsCache();
}

/** Merge extra query params for PDF API calls (server resolves letterhead). */
export async function pdfRequestParams(extra = {}) {
  return { ...extra };
}
