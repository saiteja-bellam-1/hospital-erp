import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { useToast } from '../../hooks/use-toast';
import { useAuth } from '../../contexts/AuthContext';
import { Printer, Save, ArrowLeft, Eye, ChevronUp, ChevronDown, Receipt, FileText, LayoutTemplate, Users } from 'lucide-react';
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

const DEFAULT_VITAL_FIELDS = [
  'height', 'weight', 'blood_pressure', 'heart_rate', 'temperature', 'respiratory_rate', 'spo2',
];

const FALLBACK_VITAL_CATALOG = [
  { key: 'height', label: 'Height', unit: 'cms' },
  { key: 'weight', label: 'Weight', unit: 'Kg' },
  { key: 'blood_pressure', label: 'Blood Pressure', unit: '' },
  { key: 'heart_rate', label: 'Pulse', unit: '/min' },
  { key: 'temperature', label: 'Temperature', unit: '°F' },
  { key: 'respiratory_rate', label: 'Resp. Rate', unit: '/min' },
  { key: 'spo2', label: 'SpO2', unit: '%' },
  { key: 'bmi', label: 'BMI', unit: '' },
  { key: 'pain_scale', label: 'Pain Score', unit: '' },
];

const VITALS_LAYOUT_OPTIONS = [
  {
    value: 'show',
    label: 'Show vitals',
    description: 'Print selected vitals in the left column.',
  },
  {
    value: 'blank',
    label: 'Leave column blank',
    description: 'Keep an empty left column for pre-printed vitals stationery.',
  },
  {
    value: 'remove',
    label: 'Remove column',
    description: 'Drop the left column so medicines start from the left edge.',
  },
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
    <div className="flex-1 flex flex-col border rounded-lg p-3 bg-white text-sm font-mono w-full min-h-[11rem]">
      <p className="text-xs font-sans font-medium text-muted-foreground mb-2">Payment summary preview</p>
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-6 py-0.5">
          <span className="font-semibold">{label}</span>
          <span>{value}</span>
        </div>
      ))}
      <p className="text-[10px] font-sans text-muted-foreground mt-auto border-t pt-2">
        Amount in words uses net total (Total − Discount) on printed bills.
      </p>
    </div>
  );
};

const DocumentOverrideTable = ({ groups, overrides, onChange, namePrefix, onPreview }) => (
  <div className="space-y-4">
    {groups.map((group) => (
      <div key={`${namePrefix}-${group.module}`}>
        <h3 className="text-sm font-semibold text-foreground mb-2">{group.label}</h3>
        <div className="border rounded-lg overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/50">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Document</th>
                {OVERRIDE_OPTIONS.map((opt) => (
                  <th key={opt.value} className="text-center px-3 py-2 font-medium">
                    {opt.label}
                  </th>
                ))}
                <th className="text-center px-3 py-2 font-medium">Preview</th>
              </tr>
            </thead>
            <tbody>
              {group.items.map((item) => {
                const current = overrides[item.key] || 'inherit';
                return (
                  <tr key={item.key} className="border-t">
                    <td className="px-3 py-2">{item.label}</td>
                    {OVERRIDE_OPTIONS.map((opt) => (
                      <td key={opt.value} className="text-center px-3 py-2">
                        <input
                          type="radio"
                          name={`${namePrefix}-${item.key}`}
                          checked={current === opt.value}
                          onChange={() => onChange(item.key, opt.value)}
                          aria-label={`${item.label} — ${opt.label}`}
                        />
                      </td>
                    ))}
                    <td className="text-center px-3 py-2">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-8 w-8 p-0"
                        onClick={() => onPreview(item.key, item.label)}
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
  </div>
);

const PrintSettingsPage = () => {
  const { user } = useAuth();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settingsTab, setSettingsTab] = useState('bills');
  const [includeHeaderOnPdfs, setIncludeHeaderOnPdfs] = useState(true);
  const [includeFooterOnPdfs, setIncludeFooterOnPdfs] = useState(true);
  const [detailedBillingOnPdfs, setDetailedBillingOnPdfs] = useState(true);
  const [prescriptionVitalsLayout, setPrescriptionVitalsLayout] = useState('show');
  const [prescriptionVitalsColumnWidthIn, setPrescriptionVitalsColumnWidthIn] = useState(1.75);
  const [prescriptionVitalsColumnWidthMinIn, setPrescriptionVitalsColumnWidthMinIn] = useState(0.5);
  const [prescriptionVitalsColumnWidthMaxIn, setPrescriptionVitalsColumnWidthMaxIn] = useState(2.86);
  const [prescriptionVitalFields, setPrescriptionVitalFields] = useState(DEFAULT_VITAL_FIELDS);
  const [prescriptionVitalCatalog, setPrescriptionVitalCatalog] = useState([]);
  const [letterheadGapMm, setLetterheadGapMm] = useState(35);
  const [reportCatalog, setReportCatalog] = useState([]);
  const [footerReportCatalog, setFooterReportCatalog] = useState([]);
  const [overrides, setOverrides] = useState({});
  const [footerOverrides, setFooterOverrides] = useState({});
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewReport, setPreviewReport] = useState({ key: 'opd_bill', label: 'OPD Bill' });
  const [customisationLicensed, setCustomisationLicensed] = useState(null);

  const roles = user?.roles || [user?.role];
  const canEdit = roles.some((r) =>
    ['super_admin', 'hospital_admin', 'receptionist'].includes(r)
  );

  const draftSettings = useMemo(() => ({
    includeHeaderOnPdfs,
    includeFooterOnPdfs,
    detailedBillingOnPdfs,
    prescriptionIncludeVitals: prescriptionVitalsLayout === 'show',
    prescriptionVitalsLayout,
    prescriptionVitalsColumnWidthIn,
    prescriptionVitalFields,
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
  }), [
    includeHeaderOnPdfs,
    includeFooterOnPdfs,
    detailedBillingOnPdfs,
    prescriptionVitalsLayout,
    prescriptionVitalsColumnWidthIn,
    prescriptionVitalFields,
    letterheadGapMm,
    overrides,
    footerOverrides,
  ]);

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
        const layout = res.data.prescription_vitals_layout
          || (res.data.prescription_include_vitals === false ? 'blank' : 'show');
        setPrescriptionVitalsLayout(['show', 'blank', 'remove'].includes(layout) ? layout : 'show');
        setPrescriptionVitalsColumnWidthIn(res.data.prescription_vitals_column_width_in ?? 1.75);
        setPrescriptionVitalsColumnWidthMinIn(res.data.prescription_vitals_column_width_min_in ?? 0.5);
        setPrescriptionVitalsColumnWidthMaxIn(res.data.prescription_vitals_column_width_max_in ?? 2.86);
        setPrescriptionVitalFields(
          Array.isArray(res.data.prescription_vital_fields) && res.data.prescription_vital_fields.length
            ? res.data.prescription_vital_fields
            : DEFAULT_VITAL_FIELDS
        );
        setPrescriptionVitalCatalog(res.data.prescription_vital_catalog || []);
        setLetterheadGapMm(res.data.letterhead_gap_mm ?? 35);
        setReportCatalog(res.data.report_catalog || []);
        setFooterReportCatalog(res.data.footer_report_catalog || []);
        setOverrides(res.data.report_header_overrides || {});
        setFooterOverrides(res.data.report_footer_overrides || {});
        setCustomisationLicensed(!!res.data.customisation_licensed);
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
      if (value === 'inherit') delete next[key];
      else next[key] = value;
      return next;
    });
  };

  const setFooterOverride = (key, value) => {
    setFooterOverrides((prev) => {
      const next = { ...prev };
      if (value === 'inherit') delete next[key];
      else next[key] = value;
      return next;
    });
  };

  const toggleVitalField = (key) => {
    setPrescriptionVitalFields((prev) => {
      if (prev.includes(key)) {
        if (prev.length <= 1) return prev;
        return prev.filter((k) => k !== key);
      }
      const catalogKeys = (prescriptionVitalCatalog.length
        ? prescriptionVitalCatalog
        : FALLBACK_VITAL_CATALOG
      ).map((item) => item.key);
      const next = [...prev, key];
      return catalogKeys.filter((k) => next.includes(k));
    });
  };

  const moveVitalField = (key, direction) => {
    setPrescriptionVitalFields((prev) => {
      const idx = prev.indexOf(key);
      if (idx < 0) return prev;
      const swapWith = idx + direction;
      if (swapWith < 0 || swapWith >= prev.length) return prev;
      const next = [...prev];
      [next[idx], next[swapWith]] = [next[swapWith], next[idx]];
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
    const widthIn = parseFloat(prescriptionVitalsColumnWidthIn);
    if (
      prescriptionVitalsLayout !== 'remove'
      && (
        Number.isNaN(widthIn)
        || widthIn < prescriptionVitalsColumnWidthMinIn
        || widthIn > prescriptionVitalsColumnWidthMaxIn
      )
    ) {
      toast({
        variant: 'destructive',
        title: 'Invalid column width',
        description: `Vitals column width must be between ${prescriptionVitalsColumnWidthMinIn} and ${prescriptionVitalsColumnWidthMaxIn} inches`,
      });
      return;
    }
    if (prescriptionVitalFields.length === 0) {
      toast({
        variant: 'destructive',
        title: 'Select vitals',
        description: 'Choose at least one vital for collection and display.',
      });
      return;
    }
    setSaving(true);
    try {
      await axios.put('/api/hospital/print-settings', {
        include_header_on_pdfs: includeHeaderOnPdfs,
        include_footer_on_pdfs: includeFooterOnPdfs,
        detailed_billing_on_pdfs: detailedBillingOnPdfs,
        prescription_vitals_layout: prescriptionVitalsLayout,
        prescription_vitals_column_width_in: Number.isNaN(widthIn) ? 1.75 : widthIn,
        prescription_vital_fields: prescriptionVitalFields,
        letterhead_gap_mm: gap,
        report_header_overrides: overrides,
        report_footer_overrides: footerOverrides,
      });
      invalidatePdfPrintSettingsCache();
      queryClient.invalidateQueries({ queryKey: ['hospital-vitals-config'] });
      queryClient.invalidateQueries({ queryKey: ['hospital-print-settings'] });
      toast({ title: 'Saved', description: 'Customisations updated' });
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
      <p className="text-sm text-muted-foreground">
        You do not have permission to edit customisations.
      </p>
    );
  }

  if (!loading && customisationLicensed === false) {
    return (
      <div className="space-y-3 max-w-xl">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Printer className="h-6 w-6 shrink-0" />
          Customisations
        </h1>
        <p className="text-sm text-muted-foreground">
          Document customisations are not included in this license. Ask your vendor to issue a license with the Customisation add-on.
        </p>
        {roles.some((r) => ['super_admin', 'hospital_admin'].includes(r)) && (
          <Button asChild variant="outline">
            <Link to="/dashboard/license">Open License</Link>
          </Button>
        )}
      </div>
    );
  }

  const catalog = prescriptionVitalCatalog.length ? prescriptionVitalCatalog : FALLBACK_VITAL_CATALOG;
  const byKey = Object.fromEntries(catalog.map((item) => [item.key, item]));
  const selectedRows = prescriptionVitalFields.map((key) => byKey[key]).filter(Boolean);
  const unselectedRows = catalog.filter((item) => !prescriptionVitalFields.includes(item.key));

  return (
    <div className="space-y-6 min-w-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <Link
            to="/dashboard"
            className="text-muted-foreground hover:text-foreground shrink-0 mt-1"
            aria-label="Back to dashboard"
          >
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div className="min-w-0">
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Printer className="h-6 w-6 shrink-0" />
              Customisations
            </h1>
            <p className="text-sm text-muted-foreground mt-1 max-w-xl">
              Bills, letterhead, prescription vitals, and per-document overrides.
              Label sizes live under Administration → Appearance.
            </p>
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          className="shrink-0"
          onClick={() => openPreview('opd_bill', 'OPD Bill')}
          disabled={loading}
        >
          <Eye className="h-4 w-4 mr-2" />
          Preview bill
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <>
          <Tabs value={settingsTab} onValueChange={setSettingsTab} className="w-full">
            <TabsList className="grid w-full grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 h-auto gap-1">
              <TabsTrigger value="bills" className="gap-1.5 text-xs sm:text-sm">
                <Receipt className="h-4 w-4 shrink-0" /> Bills
              </TabsTrigger>
              <TabsTrigger value="letterhead" className="gap-1.5 text-xs sm:text-sm">
                <LayoutTemplate className="h-4 w-4 shrink-0" /> Letterhead
              </TabsTrigger>
              <TabsTrigger value="prescription" className="gap-1.5 text-xs sm:text-sm">
                <FileText className="h-4 w-4 shrink-0" /> Prescription
              </TabsTrigger>
              <TabsTrigger value="documents" className="gap-1.5 text-xs sm:text-sm">
                <Printer className="h-4 w-4 shrink-0" /> Documents
              </TabsTrigger>
              <TabsTrigger value="footers" className="gap-1.5 text-xs sm:text-sm">
                <Users className="h-4 w-4 shrink-0" /> Footers
              </TabsTrigger>
            </TabsList>

            <TabsContent value="bills" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Bill payment summary</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      className="mt-1 w-4 h-4 shrink-0"
                      checked={detailedBillingOnPdfs}
                      onChange={(e) => setDetailedBillingOnPdfs(e.target.checked)}
                    />
                    <div>
                      <p className="text-sm font-medium">Detailed billing on printed bills</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        When enabled, bills show net total, paid amount, and balance.
                        When disabled, only subtotal, discount, and total are shown.
                      </p>
                    </div>
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="flex flex-col">
                      <p className="text-xs font-medium text-muted-foreground mb-2">Current setting</p>
                      <BillSummaryPreview detailed={detailedBillingOnPdfs} />
                    </div>
                    <div className="flex flex-col">
                      <p className="text-xs font-medium text-muted-foreground mb-2">
                        {detailedBillingOnPdfs ? 'Simple layout (when unchecked)' : 'Detailed layout (when checked)'}
                      </p>
                      <BillSummaryPreview detailed={!detailedBillingOnPdfs} />
                    </div>
                  </div>
                  <Button type="button" variant="secondary" size="sm" onClick={() => openPreview('opd_bill', 'OPD Bill')}>
                    <Eye className="h-4 w-4 mr-2" />
                    Preview full bill PDF
                  </Button>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="letterhead" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Global letterhead defaults</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      className="mt-1 w-4 h-4 shrink-0"
                      checked={includeHeaderOnPdfs}
                      onChange={(e) => setIncludeHeaderOnPdfs(e.target.checked)}
                    />
                    <div>
                      <p className="text-sm font-medium">Include hospital letterhead on PDFs (default)</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Logo and hospital details from Administration → Hospital Info.
                        Individual documents can override on the Documents tab.
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
                      Blank space at the top for pre-printed letterhead. Default 35 mm.
                    </p>
                  </div>
                  <Button type="button" variant="secondary" size="sm" onClick={() => openPreview('opd_bill', 'OPD Bill')}>
                    <Eye className="h-4 w-4 mr-2" />
                    Preview with these settings
                  </Button>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="prescription" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Prescription vitals</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-3">
                    <p className="text-sm font-medium">Vitals column layout</p>
                    <div className="grid gap-2 max-w-2xl">
                      {VITALS_LAYOUT_OPTIONS.map((opt) => (
                        <label
                          key={opt.value}
                          className={`flex items-start gap-3 cursor-pointer rounded-lg border p-3 ${
                            prescriptionVitalsLayout === opt.value ? 'border-primary/40 bg-muted/30' : ''
                          }`}
                        >
                          <input
                            type="radio"
                            name="prescription-vitals-layout"
                            className="mt-1 w-4 h-4 shrink-0"
                            checked={prescriptionVitalsLayout === opt.value}
                            onChange={() => setPrescriptionVitalsLayout(opt.value)}
                          />
                          <div>
                            <p className="text-sm font-medium">{opt.label}</p>
                            <p className="text-xs text-muted-foreground mt-0.5">{opt.description}</p>
                          </div>
                        </label>
                      ))}
                    </div>
                    {prescriptionVitalsLayout !== 'remove' ? (
                      <div className="max-w-xs">
                        <Label htmlFor="vitals-column-width">
                          {prescriptionVitalsLayout === 'blank' ? 'Blank column width (inches)' : 'Left column width (inches)'}
                        </Label>
                        <Input
                          id="vitals-column-width"
                          type="number"
                          min={prescriptionVitalsColumnWidthMinIn}
                          max={prescriptionVitalsColumnWidthMaxIn}
                          step={0.05}
                          value={prescriptionVitalsColumnWidthIn}
                          onChange={(e) => setPrescriptionVitalsColumnWidthIn(e.target.value)}
                          className="mt-1"
                        />
                        <p className="text-xs text-muted-foreground mt-1">
                          {prescriptionVitalsColumnWidthMinIn}&quot; – {prescriptionVitalsColumnWidthMaxIn}&quot;. Default 1.75&quot;.
                        </p>
                      </div>
                    ) : null}
                  </div>
                  <div>
                    <p className="text-sm font-medium mb-1">Vitals to collect &amp; display</p>
                    <p className="text-xs text-muted-foreground mb-3">
                      Reception and nurses only see these fields when recording vitals.
                    </p>
                    <div className="border rounded-lg divide-y max-w-2xl">
                      {[...selectedRows, ...unselectedRows].map((item) => {
                        const selected = prescriptionVitalFields.includes(item.key);
                        const orderIdx = prescriptionVitalFields.indexOf(item.key);
                        return (
                          <div key={item.key} className="flex items-center gap-3 px-3 py-2">
                            <input
                              type="checkbox"
                              className="w-4 h-4 shrink-0"
                              checked={selected}
                              onChange={() => toggleVitalField(item.key)}
                              aria-label={`Show ${item.label}`}
                            />
                            <div className="flex-1 min-w-0">
                              <p className="text-sm font-medium">{item.label}</p>
                              {item.unit ? <p className="text-xs text-muted-foreground">{item.unit}</p> : null}
                            </div>
                            {selected ? (
                              <div className="flex items-center gap-1 shrink-0">
                                <span className="text-xs text-muted-foreground w-5 text-right">{orderIdx + 1}</span>
                                <Button type="button" variant="ghost" size="sm" className="h-7 w-7 p-0"
                                  disabled={orderIdx <= 0} onClick={() => moveVitalField(item.key, -1)}
                                  aria-label={`Move ${item.label} up`}>
                                  <ChevronUp className="h-4 w-4" />
                                </Button>
                                <Button type="button" variant="ghost" size="sm" className="h-7 w-7 p-0"
                                  disabled={orderIdx >= prescriptionVitalFields.length - 1}
                                  onClick={() => moveVitalField(item.key, 1)}
                                  aria-label={`Move ${item.label} down`}>
                                  <ChevronDown className="h-4 w-4" />
                                </Button>
                              </div>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                  <Button type="button" variant="secondary" size="sm" onClick={() => openPreview('prescription', 'Prescription')}>
                    <Eye className="h-4 w-4 mr-2" />
                    Preview prescription PDF
                  </Button>
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="documents" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Per-document letterhead</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    Override letterhead per document type. Lab report settings apply to single, package, and combined prints.
                  </p>
                  <DocumentOverrideTable
                    groups={groupedCatalog}
                    overrides={overrides}
                    onChange={setOverride}
                    namePrefix="override"
                    onPreview={openPreview}
                  />
                </CardContent>
              </Card>
            </TabsContent>

            <TabsContent value="footers" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">Staff footers (reception &amp; lab)</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      className="mt-1 w-4 h-4 shrink-0"
                      checked={includeFooterOnPdfs}
                      onChange={(e) => setIncludeFooterOnPdfs(e.target.checked)}
                    />
                    <div>
                      <p className="text-sm font-medium">Show staff names on PDF footers (default)</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        Bills show Prepared by / Printed by. Lab reports show technician and pathologist blocks.
                      </p>
                    </div>
                  </label>
                  <DocumentOverrideTable
                    groups={groupedFooterCatalog}
                    overrides={footerOverrides}
                    onChange={setFooterOverride}
                    namePrefix="footer-override"
                    onPreview={openPreview}
                  />
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>

          <Button onClick={handleSave} disabled={saving}>
            <Save className="h-4 w-4 mr-2" />
            {saving ? 'Saving…' : 'Save customisations'}
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
