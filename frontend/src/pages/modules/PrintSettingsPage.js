import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { useToast } from '../../hooks/use-toast';
import { useAuth } from '../../contexts/AuthContext';
import { Printer, Save, ArrowLeft, Eye } from 'lucide-react';
import { invalidatePdfPrintSettingsCache, resolveIncludeHeaderForReport, resolveIncludeFooterForReport } from '../../hooks/usePdfPrintSettings';
import PrintSettingsPreviewDialog from '../../components/PrintSettingsPreviewDialog';

const MODULE_ORDER = ['outpatient', 'laboratory', 'billing', 'inpatient', 'pharmacy'];
const FOOTER_MODULE_ORDER = ['outpatient', 'laboratory'];
const MODULE_LABELS = {
  outpatient: 'Outpatient',
  laboratory: 'Laboratory',
  billing: 'Billing',
  inpatient: 'Inpatient',
  pharmacy: 'Pharmacy',
};

const OVERRIDE_OPTIONS = [
  { value: 'inherit', label: 'Default' },
  { value: 'on', label: 'On' },
  { value: 'off', label: 'Off' },
];

const BILL_PREVIEW_ROWS = {
  detailed: [
    ['Total Amt', '1500.00'],
    ['Discount', '100.00'],
    ['Net Total', '1400.00'],
    ['Paid Amt', '1400.00'],
    ['Balance', '0.00'],
  ],
  simple: [
    ['Sub Total', '1500.00'],
    ['Discount', '100.00'],
    ['Total Amt', '1400.00'],
  ],
};

const BillSummaryPreview = ({ detailed }) => {
  const rows = detailed ? BILL_PREVIEW_ROWS.detailed : BILL_PREVIEW_ROWS.simple;
  return (
    <div className="border rounded-lg p-3 bg-white text-sm font-mono max-w-xs">
      <p className="text-xs font-sans font-medium text-muted-foreground mb-2">Payment summary preview</p>
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-6 py-0.5">
          <span className="font-semibold">{label}</span>
          <span>{value}</span>
        </div>
      ))}
      <p className="text-[10px] font-sans text-muted-foreground mt-2 border-t pt-2">
        Amount in words uses net total (Total − Discount) on printed bills.
      </p>
    </div>
  );
};

const PrintSettingsPage = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [includeHeaderOnPdfs, setIncludeHeaderOnPdfs] = useState(true);
  const [includeFooterOnPdfs, setIncludeFooterOnPdfs] = useState(true);
  const [detailedBillingOnPdfs, setDetailedBillingOnPdfs] = useState(true);
  const [letterheadGapMm, setLetterheadGapMm] = useState(35);
  const [reportCatalog, setReportCatalog] = useState([]);
  const [footerReportCatalog, setFooterReportCatalog] = useState([]);
  const [overrides, setOverrides] = useState({});
  const [footerOverrides, setFooterOverrides] = useState({});
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewReport, setPreviewReport] = useState({ key: 'opd_bill', label: 'OPD Bill' });

  const roles = user?.roles || [user?.role];
  const canEdit = roles.some((r) =>
    ['super_admin', 'hospital_admin', 'receptionist'].includes(r)
  );

  const draftSettings = useMemo(() => ({
    includeHeaderOnPdfs,
    includeFooterOnPdfs,
    detailedBillingOnPdfs,
    letterheadGapMm,
    overrides,
    footerOverrides,
    resolveIncludeHeader: (reportType) =>
      resolveIncludeHeaderForReport(
        { include_header_on_pdfs: includeHeaderOnPdfs, report_header_overrides: overrides },
        reportType
      ),
    resolveIncludeFooter: (reportType) =>
      resolveIncludeFooterForReport(
        { include_footer_on_pdfs: includeFooterOnPdfs, report_footer_overrides: footerOverrides },
        reportType
      ),
  }), [includeHeaderOnPdfs, includeFooterOnPdfs, detailedBillingOnPdfs, letterheadGapMm, overrides, footerOverrides]);

  const openPreview = useCallback((key, label) => {
    setPreviewReport({ key, label });
    setPreviewOpen(true);
  }, []);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await axios.get('/api/hospital/print-settings');
        setIncludeHeaderOnPdfs(res.data.include_header_on_pdfs !== false);
        setIncludeFooterOnPdfs(res.data.include_footer_on_pdfs !== false);
        setDetailedBillingOnPdfs(res.data.detailed_billing_on_pdfs !== false);
        setLetterheadGapMm(res.data.letterhead_gap_mm ?? 35);
        setReportCatalog(res.data.report_catalog || []);
        setFooterReportCatalog(res.data.footer_report_catalog || []);
        setOverrides(res.data.report_header_overrides || {});
        setFooterOverrides(res.data.report_footer_overrides || {});
      } catch {
        toast({
          variant: 'destructive',
          title: 'Error',
          description: 'Failed to load print settings',
        });
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [toast]);

  const groupedCatalog = useMemo(() => {
    const groups = {};
    reportCatalog.forEach((item) => {
      const mod = item.module || 'other';
      if (!groups[mod]) groups[mod] = [];
      groups[mod].push(item);
    });
    return MODULE_ORDER.filter((m) => groups[m]?.length).map((m) => ({
      module: m,
      label: MODULE_LABELS[m] || m,
      items: groups[m],
    }));
  }, [reportCatalog]);

  const groupedFooterCatalog = useMemo(() => {
    const groups = {};
    footerReportCatalog.forEach((item) => {
      const mod = item.module || 'other';
      if (!groups[mod]) groups[mod] = [];
      groups[mod].push(item);
    });
    return FOOTER_MODULE_ORDER.filter((m) => groups[m]?.length).map((m) => ({
      module: m,
      label: MODULE_LABELS[m] || m,
      items: groups[m],
    }));
  }, [footerReportCatalog]);

  const setOverride = (key, value) => {
    setOverrides((prev) => {
      const next = { ...prev };
      if (value === 'inherit') {
        delete next[key];
      } else {
        next[key] = value;
      }
      return next;
    });
  };

  const setFooterOverride = (key, value) => {
    setFooterOverrides((prev) => {
      const next = { ...prev };
      if (value === 'inherit') {
        delete next[key];
      } else {
        next[key] = value;
      }
      return next;
    });
  };

  const handleSave = async () => {
    const gap = parseFloat(letterheadGapMm);
    if (Number.isNaN(gap) || gap < 0 || gap > 80) {
      toast({
        variant: 'destructive',
        title: 'Invalid gap',
        description: 'Letterhead gap must be between 0 and 80 mm',
      });
      return;
    }
    setSaving(true);
    try {
      await axios.put('/api/hospital/print-settings', {
        include_header_on_pdfs: includeHeaderOnPdfs,
        include_footer_on_pdfs: includeFooterOnPdfs,
        detailed_billing_on_pdfs: detailedBillingOnPdfs,
        letterhead_gap_mm: gap,
        report_header_overrides: overrides,
        report_footer_overrides: footerOverrides,
      });
      invalidatePdfPrintSettingsCache();
      toast({ title: 'Saved', description: 'Print settings updated' });
    } catch (err) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: err.response?.data?.detail || 'Failed to save print settings',
      });
    } finally {
      setSaving(false);
    }
  };

  if (!canEdit) {
    return (
      <div className="p-6">
        <p className="text-sm text-muted-foreground">
          You do not have permission to edit print settings.
        </p>
      </div>
    );
  }

  return (
    <div className="p-4 md:p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link
          to="/dashboard"
          className="text-muted-foreground hover:text-foreground"
          aria-label="Back to dashboard"
        >
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <div className="flex-1">
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Printer className="h-6 w-6" />
            Print Settings
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure letterhead and top gap for pre-printed stationery. Use preview to check alignment
            before saving.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => openPreview('opd_bill', 'OPD Bill')}
          disabled={loading}
        >
          <Eye className="h-4 w-4 mr-2" />
          Preview
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Bill payment summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-1 w-4 h-4"
                  checked={detailedBillingOnPdfs}
                  onChange={(e) => setDetailedBillingOnPdfs(e.target.checked)}
                />
                <div>
                  <p className="text-sm font-medium">Detailed billing on printed bills</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    When enabled, bills show net total, paid amount, and balance.
                    When disabled, only total amount and discount are shown — discount is
                    deducted from the total; net total, paid, and balance lines are hidden.
                  </p>
                </div>
              </label>

              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">Current setting</p>
                  <BillSummaryPreview detailed={detailedBillingOnPdfs} />
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">Compare</p>
                  <BillSummaryPreview detailed={!detailedBillingOnPdfs} />
                  <p className="text-[10px] text-muted-foreground mt-1">
                    {detailedBillingOnPdfs ? 'Simple layout (when unchecked)' : 'Detailed layout (when checked)'}
                  </p>
                </div>
              </div>

              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => openPreview('opd_bill', 'OPD Bill')}
              >
                <Eye className="h-4 w-4 mr-2" />
                Preview full bill PDF
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Global defaults</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-1 w-4 h-4"
                  checked={includeHeaderOnPdfs}
                  onChange={(e) => setIncludeHeaderOnPdfs(e.target.checked)}
                />
                <div>
                  <p className="text-sm font-medium">Include hospital letterhead on PDFs (default)</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    When enabled, logo and hospital details from Hospital Config appear at the top.
                    Individual documents below can override this.
                  </p>
                </div>
              </label>

              <div className="max-w-xs">
                <Label htmlFor="letterhead-gap">Letterhead gap when header is off (mm)</Label>
                <Input
                  id="letterhead-gap"
                  type="number"
                  min={0}
                  max={80}
                  step={1}
                  value={letterheadGapMm}
                  onChange={(e) => setLetterheadGapMm(e.target.value)}
                  className="mt-1"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Blank space at the top for pre-printed letterhead. Default 35 mm (~3.5 cm).
                </p>
              </div>

              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => openPreview('opd_bill', 'OPD Bill')}
              >
                <Eye className="h-4 w-4 mr-2" />
                Preview with these settings
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Per-document letterhead</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <p className="text-sm text-muted-foreground">
                Choose whether each printable document uses the digital letterhead, leaves gap only,
                or follows the global default above. Click Preview on any row to see that layout.
              </p>
              {groupedCatalog.map((group) => (
                <div key={group.module}>
                  <h3 className="text-sm font-semibold text-foreground mb-2">{group.label}</h3>
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/50">
                        <tr>
                          <th className="text-left px-3 py-2 font-medium">Document</th>
                          {OVERRIDE_OPTIONS.map((opt) => (
                            <th key={opt.value} className="text-center px-2 py-2 font-medium w-20">
                              {opt.label}
                            </th>
                          ))}
                          <th className="text-center px-2 py-2 font-medium w-16">Preview</th>
                        </tr>
                      </thead>
                      <tbody>
                        {group.items.map((item) => {
                          const current = overrides[item.key] || 'inherit';
                          return (
                            <tr key={item.key} className="border-t">
                              <td className="px-3 py-2">{item.label}</td>
                              {OVERRIDE_OPTIONS.map((opt) => (
                                <td key={opt.value} className="text-center px-2 py-2">
                                  <input
                                    type="radio"
                                    name={`override-${item.key}`}
                                    checked={current === opt.value}
                                    onChange={() => setOverride(item.key, opt.value)}
                                    aria-label={`${item.label} — ${opt.label}`}
                                  />
                                </td>
                              ))}
                              <td className="text-center px-2 py-2">
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  className="h-8 w-8 p-0"
                                  onClick={() => openPreview(item.key, item.label)}
                                  aria-label={`Preview ${item.label}`}
                                >
                                  <Eye className="h-4 w-4" />
                                </Button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Staff footers (reception &amp; lab)</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-1 w-4 h-4"
                  checked={includeFooterOnPdfs}
                  onChange={(e) => setIncludeFooterOnPdfs(e.target.checked)}
                />
                <div>
                  <p className="text-sm font-medium">Show staff names on PDF footers (default)</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    When enabled, bills show Prepared by / Printed by (receptionist name).
                    Lab reports show Lab Technician and pathologist signature block plus a generated timestamp.
                    The vendor line at the very bottom of the page is always shown.
                  </p>
                </div>
              </label>

              <p className="text-sm text-muted-foreground">
                Override per document for OPD bills, lab bills, and lab reports.
              </p>
              {groupedFooterCatalog.map((group) => (
                <div key={`footer-${group.module}`}>
                  <h3 className="text-sm font-semibold text-foreground mb-2">{group.label}</h3>
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/50">
                        <tr>
                          <th className="text-left px-3 py-2 font-medium">Document</th>
                          {OVERRIDE_OPTIONS.map((opt) => (
                            <th key={opt.value} className="text-center px-2 py-2 font-medium w-20">
                              {opt.label}
                            </th>
                          ))}
                          <th className="text-center px-2 py-2 font-medium w-16">Preview</th>
                        </tr>
                      </thead>
                      <tbody>
                        {group.items.map((item) => {
                          const current = footerOverrides[item.key] || 'inherit';
                          return (
                            <tr key={item.key} className="border-t">
                              <td className="px-3 py-2">{item.label}</td>
                              {OVERRIDE_OPTIONS.map((opt) => (
                                <td key={opt.value} className="text-center px-2 py-2">
                                  <input
                                    type="radio"
                                    name={`footer-override-${item.key}`}
                                    checked={current === opt.value}
                                    onChange={() => setFooterOverride(item.key, opt.value)}
                                    aria-label={`${item.label} footer — ${opt.label}`}
                                  />
                                </td>
                              ))}
                              <td className="text-center px-2 py-2">
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="sm"
                                  className="h-8 w-8 p-0"
                                  onClick={() => openPreview(item.key, item.label)}
                                  aria-label={`Preview ${item.label}`}
                                >
                                  <Eye className="h-4 w-4" />
                                </Button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Button onClick={handleSave} disabled={saving}>
            <Save className="h-4 w-4 mr-2" />
            {saving ? 'Saving…' : 'Save print settings'}
          </Button>
        </>
      )}

      <PrintSettingsPreviewDialog
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        reportType={previewReport.key}
        reportLabel={previewReport.label}
        draftSettings={draftSettings}
      />
    </div>
  );
};

export default PrintSettingsPage;
