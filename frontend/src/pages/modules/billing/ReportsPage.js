import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from '../../../components/ui/select';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '../../../components/ui/dropdown-menu';
import { ChevronDown, Download, FileSpreadsheet, FileText, Loader2 } from 'lucide-react';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';
import PatientSearchPicker from '../../../components/PatientSearchPicker';
import {
  BILLING_MODULES, BillingPeriodFilter, MoneyTable, formatInr, defaultReportRange,
  rateAmountColumns, flattenRateRows, filterBillingModules,
} from './BillingReportControls';
import { localMonthStart } from '../../../utils/localDate';

const REPORT_CATALOG = [
  { id: 'sales', label: 'Sales register', group: 'Hospital-wide', passthrough: true, uses: ['period', 'module', 'patient'], hint: 'Invoices across modules' },
  { id: 'daily-collection', label: 'Daily collection', group: 'Hospital-wide', passthrough: true, uses: ['period', 'module', 'patient'], hint: 'Cash / UPI / card by day' },
  { id: 'doctor-efficiency', label: 'Doctor efficiency', group: 'Hospital-wide', requires: 'inpatient', uses: ['period'], hint: 'OPD consults, IP admissions, visits, OT, LOS' },
  { id: 'doctor-revenue', label: 'Doctor revenue', group: 'Hospital-wide', uses: ['period', 'module', 'patient'], hint: 'OPD and IP billed to each doctor' },
  { id: 'tax-summary', label: 'Tax summary', group: 'Hospital-wide', passthrough: true, uses: ['period', 'module', 'patient'], hint: 'GST register by day' },
  { id: 'outstanding', label: 'Outstanding', group: 'Hospital-wide', passthrough: true, uses: ['period', 'module', 'patient'], hint: 'Unpaid billed amounts' },

  { id: 'opd-activity', label: 'OPD activity', group: 'OPD', moduleScope: 'opd', requires: 'outpatient', uses: ['period'], hint: 'Appointments, no-shows, and doctor load' },

  { id: 'lab-volume', label: 'Lab volume & TAT', group: 'Laboratory', moduleScope: 'lab', requires: 'lab', uses: ['period'], hint: 'Orders, pending vs completed, average turnaround' },

  { id: 'bed-occupancy', label: 'Bed occupancy', group: 'Inpatient', moduleScope: 'inpatient', requires: 'inpatient', uses: [], hint: 'Live occupancy by ward and room type' },
  { id: 'monthly-outcomes', label: 'Monthly outcomes', group: 'Inpatient', moduleScope: 'inpatient', requires: 'inpatient', uses: ['month'], hint: 'Occupancy, mortality, readmissions, LOS' },
  { id: 'readmissions', label: 'Readmissions (30-day)', group: 'Inpatient', moduleScope: 'inpatient', requires: 'inpatient', uses: [], hint: 'Patients readmitted within 30 days' },
  { id: 'mortality', label: 'Mortality', group: 'Inpatient', moduleScope: 'inpatient', requires: 'inpatient', uses: ['period'], hint: 'Deaths in the selected period' },

  { id: 'pharmacy-sales', label: 'Pharmacy sales', group: 'Pharmacy', moduleScope: 'pharmacy', requires: 'pharmacy', uses: ['period'], hint: 'POS sales by day' },
  { id: 'pharmacy-stock', label: 'Stock on hand', group: 'Pharmacy', moduleScope: 'pharmacy', requires: 'pharmacy', uses: [], hint: 'Current stock value and low-stock items' },

  { id: 'daycare-volume', label: 'Day care volume', group: 'Day Care', moduleScope: 'day_care', uses: ['period'], hint: 'Procedure / day-care bills' },

  { id: 'physio-summary', label: 'Physio utilization', group: 'Physiotherapy', moduleScope: 'physiotherapy', requires: 'physiotherapy', uses: ['period'], hint: 'Sessions, no-shows, therapist load, collections' },

  { id: 'canteen-activity', label: 'Canteen activity', group: 'Canteen', moduleScope: 'canteen', requires: 'inpatient', uses: ['period'], hint: 'POS sales and IP food orders' },
];

const PATHS = {
  sales: '/api/hospital/billing/reports/sales-summary',
  'daily-collection': '/api/hospital/billing/reports/daily-collection',
  'doctor-efficiency': '/api/hospital/billing/reports/doctor-efficiency',
  'doctor-revenue': '/api/hospital/billing/reports/doctor-revenue',
  'tax-summary': '/api/hospital/billing/reports/tax-summary',
  outstanding: '/api/hospital/billing/reports/outstanding',
  'opd-activity': '/api/hospital/billing/reports/opd-activity',
  'lab-volume': '/api/hospital/billing/reports/lab-volume',
  'bed-occupancy': '/api/hospital/billing/reports/bed-occupancy',
  'monthly-outcomes': '/api/hospital/billing/reports/monthly-outcomes',
  readmissions: '/api/hospital/billing/reports/readmissions',
  mortality: '/api/hospital/billing/reports/mortality',
  'pharmacy-sales': '/api/hospital/billing/reports/pharmacy-sales',
  'pharmacy-stock': '/api/hospital/billing/reports/pharmacy-stock',
  'daycare-volume': '/api/hospital/billing/reports/daycare-volume',
  'physio-summary': '/api/hospital/billing/reports/physio-summary',
  'canteen-activity': '/api/hospital/billing/reports/canteen-activity',
};

function occupancyPct(occupied, total) {
  if (!total) return 0;
  return Math.round((Number(occupied || 0) * 1000) / Number(total)) / 10;
}

function KpiCards({ items }) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
      {items.map(([label, val]) => (
        <Card key={label}>
          <CardContent className="pt-4 pb-3">
            <div className="text-xs text-gray-500">{label}</div>
            <div className="text-lg font-semibold">{val ?? 0}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function ReportsPage() {
  const range = defaultReportRange();
  const [kind, setKind] = useState('doctor-efficiency');
  const [periodMode, setPeriodMode] = useState('range');
  const [dateFrom, setDateFrom] = useState(range.from);
  const [dateTo, setDateTo] = useState(range.to);
  const [month, setMonth] = useState(localMonthStart().slice(0, 7));
  const [module, setModule] = useState('all');
  const [patient, setPatient] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [pdfOpen, setPdfOpen] = useState(false);
  const [enabledModules, setEnabledModules] = useState({});

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await axios.get('/api/system/enabled-modules');
        const map = {};
        (res.data || []).forEach((m) => { map[m.module_name] = !!m.is_enabled; });
        if (!cancelled) setEnabledModules(map);
      } catch {
        if (!cancelled) setEnabledModules({});
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const moduleOptions = useMemo(
    () => (Object.keys(enabledModules).length
      ? filterBillingModules(enabledModules)
      : BILLING_MODULES),
    [enabledModules],
  );

  const reportOptions = useMemo(() => {
    const loaded = Object.keys(enabledModules).length > 0;
    const moduleKey = module === 'pharmacy_ip' ? 'pharmacy' : module;
    return REPORT_CATALOG.filter((r) => {
      if (r.requires && loaded && !enabledModules[r.requires]) return false;
      if (moduleKey === 'all') return true;
      if (r.passthrough) return true;
      if (r.moduleScope === moduleKey) return true;
      return false;
    });
  }, [enabledModules, module]);

  useEffect(() => {
    if (!moduleOptions.some((m) => m.id === module)) setModule('all');
  }, [moduleOptions, module]);

  useEffect(() => {
    if (!reportOptions.some((r) => r.id === kind)) {
      const scoped = reportOptions.find((r) => r.moduleScope);
      setKind(scoped?.id || reportOptions[0]?.id || 'sales');
    }
  }, [reportOptions, kind]);

  const kindMeta = reportOptions.find((k) => k.id === kind) || REPORT_CATALOG[0];
  const uses = kindMeta.uses || [];

  const filterParams = useMemo(() => {
    const params = {};
    const needed = (REPORT_CATALOG.find((k) => k.id === kind) || {}).uses || [];
    if (needed.includes('period')) {
      params.date_from = dateFrom;
      params.date_to = dateTo;
    }
    if (needed.includes('month')) params.month = month;
    if (needed.includes('module') && module && module !== 'all') params.module = module;
    if (needed.includes('patient') && patient?.id) params.patient_id = patient.id;
    return params;
  }, [kind, dateFrom, dateTo, month, module, patient]);

  const endpoint = PATHS[kind] || PATHS.sales;

  const run = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(endpoint, { params: filterParams });
      setData(res.data);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [endpoint, filterParams]);

  useEffect(() => { run(); }, [run]);

  const fileStem = [
    kind.replace(/-/g, '_'),
    module || 'all',
    patient?.id ? `p${patient.id}` : null,
    uses.includes('month') ? month : `${dateFrom}_to_${dateTo}`,
  ].filter(Boolean).join('_');

  const downloadExcel = async () => {
    if (kind !== 'sales') return;
    setExporting(true);
    try {
      const res = await axios.get('/api/hospital/billing/reports/sales-summary.xlsx', {
        params: filterParams,
        responseType: 'blob',
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${fileStem}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
      alert('Could not export Excel');
    } finally {
      setExporting(false);
    }
  };

  const downloadCsv = () => {
    if (!data) return;
    let header = [];
    let lines = [];
    if (kind === 'daily-collection') {
      const methods = data.methods || [];
      header = ['Date', 'Net total', 'Refunds', ...methods];
      lines = (data.rows || []).map((r) => [
        r.date, r.total, r.refunds, ...methods.map((m) => r.by_method?.[m] || 0),
      ]);
    } else if (kind === 'doctor-revenue') {
      header = ['Doctor', 'Consultations', 'Consult revenue', 'Admissions', 'Admission revenue', 'Total'];
      lines = (data.rows || []).map((r) => [
        r.doctor_name, r.consultation_count, r.consultation_revenue,
        r.admission_count, r.admission_revenue, r.total_revenue,
      ]);
    } else if (kind === 'tax-summary') {
      header = ['Date', 'Bills', 'Taxable value', 'Tax amount'];
      lines = (data.rows || []).map((r) => [r.date, r.bill_count, r.taxable_value, r.tax_amount]);
    } else if (kind === 'outstanding') {
      header = ['Module', 'Bills', 'Billed', 'Collected', 'Outstanding'];
      lines = (data.rows || []).map((r) => [r.module_label, r.count, r.billed, r.collected, r.outstanding]);
    } else if (kind === 'doctor-efficiency') {
      header = ['Doctor', 'OPD consults', 'OPD revenue', 'Admissions', 'Discharges', 'Visits', 'OT surgeon', 'Avg LOS', 'Deaths', 'IP billed'];
      lines = (data.rows || []).map((r) => [
        r.doctor_name, r.opd_consults, r.opd_revenue, r.admissions, r.discharges,
        r.visits, r.ot_as_surgeon, r.average_los_days, r.deaths, r.total_billed_attributable,
      ]);
    } else if (kind === 'bed-occupancy') {
      header = ['Department', 'Rooms', 'Beds', 'Occupied', 'Free', 'Cleaning', 'On leave', 'Occupancy %'];
      lines = (data.by_department || []).map((r) => [
        r.department, r.rooms, r.total_beds, r.occupied, r.free, r.cleaning, r.on_leave,
        occupancyPct(r.occupied, r.total_beds),
      ]);
    } else if (kind === 'monthly-outcomes') {
      const tot = data.totals || {};
      header = ['Metric', 'Value'];
      lines = [
        ['Admissions', tot.admissions],
        ['Discharges', tot.discharges],
        ['Deaths', tot.deaths],
        ['Mortality %', tot.mortality_rate_pct],
        ['Readmissions', tot.readmissions],
        ['Readmit %', tot.readmission_rate_pct],
        ['Avg occupancy %', tot.average_occupancy_pct],
      ];
    } else if (kind === 'opd-activity') {
      header = ['Doctor', 'Appointments', 'Completed', 'No-show', 'Cancelled', 'No-show %', 'Billed', 'Collected'];
      lines = (data.rows || []).map((r) => [
        r.doctor_name, r.count, r.completed, r.no_show, r.cancelled, r.no_show_pct, r.billed, r.collected,
      ]);
    } else if (kind === 'lab-volume') {
      header = ['Test', 'Orders', 'Completed', 'Pending', 'Billed'];
      lines = (data.rows || []).map((r) => [r.test, r.count, r.completed, r.pending, r.billed]);
    } else if (kind === 'readmissions') {
      header = ['Admission #', 'Patient', 'Admitted', 'Days since last discharge', 'Reason', 'Status'];
      lines = (data.rows || []).map((r) => [
        r.admission_number, r.patient_name, r.admission_date, r.days_since_last_discharge, r.reason, r.status,
      ]);
    } else if (kind === 'mortality') {
      header = ['Admission #', 'Patient', 'Discharge date', 'Cause of death', 'MLC', 'Autopsy'];
      lines = (data.rows || []).map((r) => [
        r.admission_number, r.patient_name, r.discharge_date, r.cause_of_death, r.mlc_required, r.autopsy_done,
      ]);
    } else if (kind === 'pharmacy-sales') {
      header = ['Date', 'Bills', 'Billed', 'Tax', 'Discount'];
      lines = (data.rows || []).map((r) => [r.date, r.count, r.billed, r.tax, r.discount]);
    } else if (kind === 'pharmacy-stock') {
      header = ['Medicine', 'Stock', 'Batches', 'Min qty', 'Nearest expiry', 'Low stock'];
      lines = (data.rows || []).map((r) => [
        r.name, r.total_stock, r.batches, r.min_qty, r.nearest_expiry, r.low_stock ? 'yes' : 'no',
      ]);
    } else if (kind === 'daycare-volume') {
      header = ['Date', 'Number', 'Party', 'Billed', 'Status'];
      lines = (data.rows || []).map((r) => [r.date, r.number, r.party, r.billed, r.status]);
    } else if (kind === 'physio-summary') {
      header = ['Therapist', 'Completed', 'No-show', 'Cancelled', 'Scheduled'];
      lines = (data.rows || []).map((r) => [
        r.therapist_name, r.completed, r.no_show, r.cancelled, r.scheduled,
      ]);
    } else if (kind === 'canteen-activity') {
      header = ['Date', 'Number', 'Party', 'Billed', 'Status'];
      lines = (data.rows || []).map((r) => [r.date, r.number, r.party, r.billed, r.status]);
    } else if (data.invoices) {
      header = ['Date', 'Number', 'Module', 'Party', 'Tax', 'Grand', 'Status'];
      lines = (data.invoices || []).map((r) => [
        r.date, r.number, r.module_label, r.party, r.tax, r.billed, r.status,
      ]);
    } else {
      const sample = (data.rows || [])[0] || {};
      header = Object.keys(sample);
      lines = (data.rows || []).map((r) => header.map((k) => r[k]));
    }
    const csv = [header, ...lines]
      .map((row) => row.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${fileStem}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const t = data?.totals || {};
  const groups = [...new Set(reportOptions.map((r) => r.group))];
  const pdfPath = kind === 'sales'
    ? '/api/hospital/billing/reports/sales-summary.pdf'
    : kind === 'bed-occupancy'
      ? '/api/inpatient/reports/census/pdf'
      : kind === 'doctor-efficiency'
        ? '/api/inpatient/reports/doctor-productivity/pdf'
        : kind === 'monthly-outcomes'
          ? '/api/inpatient/reports/monthly-outcomes/pdf'
          : null;

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Reports</h1>
          <p className="text-sm text-gray-600">
            One catalog for every module — occupancy, doctor load, lab volume, pharmacy stock, and billing.
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" disabled={exporting || loading}>
              {exporting ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Download className="h-4 w-4 mr-1" />}
              Export
              <ChevronDown className="h-3.5 w-3.5 ml-1 opacity-70" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {pdfPath && (
              <DropdownMenuItem onSelect={() => setPdfOpen(true)}>
                <FileText className="h-4 w-4 mr-2" /> Export PDF
              </DropdownMenuItem>
            )}
            {kind === 'sales' && (
              <DropdownMenuItem onSelect={() => { downloadExcel(); }} disabled={exporting}>
                <FileSpreadsheet className="h-4 w-4 mr-2" /> Export Excel (.xlsx)
              </DropdownMenuItem>
            )}
            <DropdownMenuItem onSelect={() => downloadCsv()} disabled={!data}>
              <FileText className="h-4 w-4 mr-2" /> Export CSV
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Card>
        <CardContent className="pt-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <Label className="text-xs">Report</Label>
              <Select value={kind} onValueChange={setKind}>
                <SelectTrigger className="w-[260px] h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {groups.map((g) => (
                    <SelectGroup key={g}>
                      <SelectLabel>{g}</SelectLabel>
                      {reportOptions.filter((r) => r.group === g).map((r) => (
                        <SelectItem key={r.id} value={r.id}>{r.label}</SelectItem>
                      ))}
                    </SelectGroup>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Module</Label>
              <Select value={module} onValueChange={setModule}>
                <SelectTrigger className="w-[160px] h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {moduleOptions.map((m) => (
                    <SelectItem key={m.id} value={m.id}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {uses.includes('period') && (
              <BillingPeriodFilter
                mode={periodMode}
                onMode={setPeriodMode}
                dateFrom={dateFrom}
                dateTo={dateTo}
                onFrom={setDateFrom}
                onTo={setDateTo}
              />
            )}
            {uses.includes('month') && (
              <div>
                <Label className="text-xs">Month</Label>
                <Input type="month" value={month} onChange={(e) => setMonth(e.target.value)} className="w-[160px] h-9" />
              </div>
            )}
            {uses.includes('patient') && (
              <div className="min-w-[240px] flex-1 max-w-sm">
                <PatientSearchPicker
                  value={patient}
                  onChange={setPatient}
                  label="Patient"
                  compact
                  allowRegister={false}
                  placeholder="Name, phone, or ID…"
                />
              </div>
            )}
            <Button onClick={run} disabled={loading} size="sm" className="h-9">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Run'}
            </Button>
          </div>
        </CardContent>
      </Card>

      {kind === 'doctor-efficiency' && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              ['OPD consults', t.opd_consults, 'count'],
              ['Admissions', t.admissions, 'count'],
              ['IP visits', t.visits, 'count'],
              ['OT (surgeon)', t.ot_as_surgeon, 'count'],
              ['IP attributable', t.total_billed_attributable, 'money'],
            ].map(([label, val, kindCol]) => (
              <Card key={label}>
                <CardContent className="pt-4 pb-3">
                  <div className="text-xs text-gray-500">{label}</div>
                  <div className="text-lg font-semibold">
                    {kindCol === 'money' ? formatInr(val) : (val || 0)}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Doctor efficiency</CardTitle>
              <p className="text-xs font-normal text-gray-500 mt-1">{kindMeta.hint}.</p>
            </CardHeader>
            <CardContent>
              {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                <MoneyTable
                  columns={[
                    { key: 'doctor_name', label: 'Doctor' },
                    { key: 'opd_consults', label: 'OPD', align: 'right' },
                    { key: 'opd_revenue', label: 'OPD ₹', align: 'right', money: true },
                    { key: 'admissions', label: 'Adm', align: 'right' },
                    { key: 'discharges', label: 'Dis', align: 'right' },
                    { key: 'visits', label: 'Visits', align: 'right' },
                    { key: 'ot_as_surgeon', label: 'OT', align: 'right' },
                    { key: 'average_los_days', label: 'Avg LOS', align: 'right' },
                    { key: 'deaths', label: 'Deaths', align: 'right' },
                    { key: 'total_billed_attributable', label: 'IP ₹', align: 'right', money: true },
                  ]}
                  rows={data?.rows || []}
                  totals={{
                    opd_consults: t.opd_consults,
                    opd_revenue: t.opd_revenue,
                    admissions: t.admissions,
                    visits: t.visits,
                    ot_as_surgeon: t.ot_as_surgeon,
                    total_billed_attributable: t.total_billed_attributable,
                  }}
                />
              )}
            </CardContent>
          </Card>
        </>
      )}

      {kind === 'bed-occupancy' && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              ['Occupancy', `${t.occupancy_pct ?? 0}%`],
              ['Occupied', t.occupied],
              ['Free', t.free],
              ['Cleaning', t.cleaning],
              ['Total beds', t.total_beds],
            ].map(([label, val]) => (
              <Card key={label}>
                <CardContent className="pt-4 pb-3">
                  <div className="text-xs text-gray-500">{label}</div>
                  <div className="text-lg font-semibold">{val ?? 0}</div>
                </CardContent>
              </Card>
            ))}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">By department</CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                  <MoneyTable
                    columns={[
                      { key: 'department', label: 'Department' },
                      { key: 'rooms', label: 'Rooms', align: 'right' },
                      { key: 'total_beds', label: 'Beds', align: 'right' },
                      { key: 'occupied', label: 'Occupied', align: 'right' },
                      { key: 'free', label: 'Free', align: 'right' },
                      { key: 'occupancy_pct', label: 'Occ %', align: 'right', pct: true },
                    ]}
                    rows={(data?.by_department || []).map((r) => ({
                      ...r,
                      occupancy_pct: occupancyPct(r.occupied, r.total_beds),
                    }))}
                  />
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">By room type</CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                  <MoneyTable
                    columns={[
                      { key: 'room_type', label: 'Room type' },
                      { key: 'total_beds', label: 'Beds', align: 'right' },
                      { key: 'occupied', label: 'Occupied', align: 'right' },
                      { key: 'free', label: 'Free', align: 'right' },
                      { key: 'occupancy_pct', label: 'Occ %', align: 'right', pct: true },
                    ]}
                    rows={(data?.by_room_type || []).map((r) => ({
                      ...r,
                      occupancy_pct: occupancyPct(r.occupied, r.total_beds),
                    }))}
                  />
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {kind === 'monthly-outcomes' && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
            {[
              ['Admissions', t.admissions],
              ['Discharges', t.discharges],
              ['Deaths', t.deaths],
              ['Mortality %', t.mortality_rate_pct != null ? `${t.mortality_rate_pct}%` : '—'],
              ['Readmissions', t.readmissions],
              ['Readmit %', t.readmission_rate_pct != null ? `${t.readmission_rate_pct}%` : '—'],
              ['Avg occupancy', t.average_occupancy_pct != null ? `${t.average_occupancy_pct}%` : '—'],
            ].map(([label, val]) => (
              <Card key={label}>
                <CardContent className="pt-4 pb-3">
                  <div className="text-xs text-gray-500">{label}</div>
                  <div className="text-lg font-semibold">{val ?? 0}</div>
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Monthly outcomes</CardTitle>
              <p className="text-xs font-normal text-gray-500 mt-1">
                {kindMeta.hint}{data?.month ? ` · ${data.month}` : ''}.
              </p>
            </CardHeader>
            <CardContent>
              {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <p className="text-sm font-medium mb-2">Readmissions by window</p>
                    <MoneyTable
                      columns={[
                        { key: 'window', label: 'Days since discharge' },
                        { key: 'count', label: 'Count', align: 'right' },
                      ]}
                      rows={Object.entries(data?.readmissions?.by_window_days || {}).map(([window, count]) => ({ window, count }))}
                    />
                  </div>
                  <div>
                    <p className="text-sm font-medium mb-2">Length of stay</p>
                    <MoneyTable
                      columns={[
                        { key: 'scope', label: 'Scope' },
                        { key: 'count', label: 'Count', align: 'right' },
                        { key: 'mean', label: 'Mean', align: 'right' },
                        { key: 'median', label: 'Median', align: 'right' },
                      ]}
                      rows={[
                        { scope: 'Overall', ...(data?.length_of_stay?.overall || {}) },
                        ...Object.entries(data?.length_of_stay?.by_department || {}).map(([scope, s]) => ({ scope, ...s })),
                      ]}
                    />
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {kind === 'sales' && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            {[
              ['Billed', t.billed],
              ['Taxable', t.taxable],
              ['Tax', t.tax],
              ['Tax %', t.tax_pct, 'pct'],
              ['Bills', t.count, 'count'],
            ].map(([label, val, kindCol]) => (
              <Card key={label}>
                <CardContent className="pt-4 pb-3">
                  <div className="text-xs text-gray-500">{label}</div>
                  <div className="text-lg font-semibold">
                    {kindCol === 'count' ? (val || 0)
                      : kindCol === 'pct' ? `${Number(val || 0).toFixed(2)}%`
                        : formatInr(val)}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Invoices by tax rate</CardTitle>
              <p className="text-xs font-normal text-gray-500 mt-1">
                {kindMeta.hint}. Each rate column is billed amount at that GST %.
              </p>
            </CardHeader>
            <CardContent>
              {loading ? (
                <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
              ) : (
                <MoneyTable
                  columns={[
                    { key: 'date', label: 'Date' },
                    { key: 'number', label: 'Number' },
                    { key: 'module_label', label: 'Module' },
                    { key: 'party', label: 'Party' },
                    ...rateAmountColumns(data?.tax_rate_columns, 'amount'),
                    { key: 'tax', label: 'Tax', align: 'right', money: true },
                    { key: 'billed', label: 'Grand', align: 'right', money: true },
                    { key: 'status', label: 'Status' },
                  ]}
                  rows={flattenRateRows(data?.invoices, data?.tax_rate_columns, 'amount')}
                  totals={flattenRateRows([t], data?.tax_rate_columns, 'amount')[0] || t}
                />
              )}
            </CardContent>
          </Card>
        </>
      )}

      {kind === 'daily-collection' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Daily collection</CardTitle>
            <p className="text-xs font-normal text-gray-500 mt-1">
              Net collections by payment method. Refunds are shown separately and already netted in the total.
            </p>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
            ) : (
              <MoneyTable
                columns={[
                  { key: 'date', label: 'Date' },
                  ...(data?.methods || []).map((m) => ({
                    key: `m_${m}`, label: m, align: 'right', money: true,
                  })),
                  { key: 'refunds', label: 'Refunds', align: 'right', money: true },
                  { key: 'total', label: 'Net', align: 'right', money: true },
                ]}
                rows={(data?.rows || []).map((r) => ({
                  ...r,
                  ...Object.fromEntries((data?.methods || []).map((m) => [`m_${m}`, r.by_method?.[m] || 0])),
                }))}
                totals={{
                  total: t.net_collected,
                  refunds: t.refunds,
                  ...Object.fromEntries((data?.methods || []).map((m) => [
                    `m_${m}`,
                    (data?.rows || []).reduce((s, r) => s + Number(r.by_method?.[m] || 0), 0),
                  ])),
                }}
              />
            )}
          </CardContent>
        </Card>
      )}

      {kind === 'doctor-revenue' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Doctor revenue</CardTitle>
            <p className="text-xs font-normal text-gray-500 mt-1">
              OPD consultations and inpatient admissions. Lab and pharmacy are not attributed to a single doctor.
            </p>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
            ) : (
              <MoneyTable
                columns={[
                  { key: 'doctor_name', label: 'Doctor' },
                  { key: 'consultation_count', label: 'Consults', align: 'right' },
                  { key: 'consultation_revenue', label: 'Consult revenue', align: 'right', money: true },
                  { key: 'admission_count', label: 'Admissions', align: 'right' },
                  { key: 'admission_revenue', label: 'Admission revenue', align: 'right', money: true },
                  { key: 'total_revenue', label: 'Total', align: 'right', money: true },
                ]}
                rows={data?.rows || []}
                totals={{
                  consultation_count: (data?.rows || []).reduce((s, r) => s + Number(r.consultation_count || 0), 0),
                  consultation_revenue: t.consultation_total,
                  admission_count: (data?.rows || []).reduce((s, r) => s + Number(r.admission_count || 0), 0),
                  admission_revenue: t.admission_total,
                  total_revenue: t.grand_total,
                }}
              />
            )}
          </CardContent>
        </Card>
      )}

      {kind === 'tax-summary' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Tax summary</CardTitle>
            <p className="text-xs font-normal text-gray-500 mt-1">
              Per-day taxable value and tax on non-cancelled hospital ledger bills.
            </p>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
            ) : (
              <MoneyTable
                columns={[
                  { key: 'date', label: 'Date' },
                  { key: 'bill_count', label: 'Bills', align: 'right' },
                  { key: 'taxable_value', label: 'Taxable', align: 'right', money: true },
                  { key: 'tax_amount', label: 'Tax', align: 'right', money: true },
                ]}
                rows={data?.rows || []}
                totals={{
                  bill_count: t.bill_count,
                  taxable_value: t.taxable_value,
                  tax_amount: t.tax_amount,
                }}
              />
            )}
          </CardContent>
        </Card>
      )}

      {kind === 'outstanding' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Outstanding by module</CardTitle>
            <p className="text-xs font-normal text-gray-500 mt-1">
              Billed minus collected for the selected period. Modules with nothing outstanding are hidden.
            </p>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
            ) : (
              <MoneyTable
                columns={[
                  { key: 'module_label', label: 'Module' },
                  { key: 'count', label: 'Bills', align: 'right' },
                  { key: 'billed', label: 'Billed', align: 'right', money: true },
                  { key: 'collected', label: 'Collected', align: 'right', money: true },
                  { key: 'outstanding', label: 'Outstanding', align: 'right', money: true },
                ]}
                rows={data?.rows || []}
                totals={t}
              />
            )}
          </CardContent>
        </Card>
      )}

      {kind === 'opd-activity' && (
        <>
          <KpiCards items={[
            ['Appointments', t.appointments],
            ['Completed', t.completed],
            ['No-show', `${t.no_show ?? 0}${t.no_show_pct != null ? ` (${t.no_show_pct}%)` : ''}`],
            ['Billed', formatInr(t.billed)],
            ['Collected', formatInr(t.collected)],
          ]} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">By status</CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                  <MoneyTable
                    columns={[
                      { key: 'status', label: 'Status' },
                      { key: 'count', label: 'Count', align: 'right' },
                    ]}
                    rows={data?.by_status || []}
                  />
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">By type</CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                  <MoneyTable
                    columns={[
                      { key: 'type', label: 'Type' },
                      { key: 'count', label: 'Count', align: 'right' },
                    ]}
                    rows={data?.by_type || []}
                  />
                )}
              </CardContent>
            </Card>
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Doctor load</CardTitle>
              <p className="text-xs font-normal text-gray-500 mt-1">{kindMeta.hint}.</p>
            </CardHeader>
            <CardContent>
              {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                <MoneyTable
                  columns={[
                    { key: 'doctor_name', label: 'Doctor' },
                    { key: 'count', label: 'Appts', align: 'right' },
                    { key: 'completed', label: 'Done', align: 'right' },
                    { key: 'no_show', label: 'No-show', align: 'right' },
                    { key: 'cancelled', label: 'Cancelled', align: 'right' },
                    { key: 'no_show_pct', label: 'No-show %', align: 'right', pct: true },
                    { key: 'billed', label: 'Billed', align: 'right', money: true },
                    { key: 'collected', label: 'Collected', align: 'right', money: true },
                  ]}
                  rows={data?.rows || []}
                  totals={{
                    count: t.appointments,
                    completed: t.completed,
                    no_show: t.no_show,
                    billed: t.billed,
                    collected: t.collected,
                  }}
                />
              )}
            </CardContent>
          </Card>
        </>
      )}

      {kind === 'lab-volume' && (
        <>
          <KpiCards items={[
            ['Orders', t.orders],
            ['Completed', t.completed],
            ['Pending', t.pending],
            ['Avg TAT', t.avg_tat_hours != null ? `${t.avg_tat_hours} h` : '—'],
            ['Billed', formatInr(t.billed)],
          ]} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">By status</CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                  <MoneyTable
                    columns={[
                      { key: 'status', label: 'Status' },
                      { key: 'count', label: 'Count', align: 'right' },
                    ]}
                    rows={data?.by_status || []}
                  />
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Top tests</CardTitle>
                <p className="text-xs font-normal text-gray-500 mt-1">{kindMeta.hint}.</p>
              </CardHeader>
              <CardContent>
                {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                  <MoneyTable
                    columns={[
                      { key: 'test', label: 'Test' },
                      { key: 'count', label: 'Orders', align: 'right' },
                      { key: 'completed', label: 'Done', align: 'right' },
                      { key: 'pending', label: 'Pending', align: 'right' },
                      { key: 'billed', label: 'Billed', align: 'right', money: true },
                    ]}
                    rows={data?.rows || []}
                    totals={{
                      count: t.orders,
                      completed: t.completed,
                      pending: t.pending,
                      billed: t.billed,
                    }}
                  />
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {kind === 'readmissions' && (
        <>
          <KpiCards items={[['30-day readmissions', t.count]]} />
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Readmissions within 30 days</CardTitle>
              <p className="text-xs font-normal text-gray-500 mt-1">{kindMeta.hint}.</p>
            </CardHeader>
            <CardContent>
              {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                <MoneyTable
                  columns={[
                    { key: 'admission_number', label: 'Admission #' },
                    { key: 'patient_name', label: 'Patient' },
                    { key: 'admission_date', label: 'Admitted' },
                    { key: 'days_since_last_discharge', label: 'Days since last DC', align: 'right' },
                    { key: 'reason', label: 'Reason' },
                    { key: 'status', label: 'Status' },
                  ]}
                  rows={data?.rows || []}
                />
              )}
            </CardContent>
          </Card>
        </>
      )}

      {kind === 'mortality' && (
        <>
          <KpiCards items={[
            ['Deaths', t.count],
            ['MLC', t.mlc],
          ]} />
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Mortality</CardTitle>
              <p className="text-xs font-normal text-gray-500 mt-1">{kindMeta.hint}.</p>
            </CardHeader>
            <CardContent>
              {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                <MoneyTable
                  columns={[
                    { key: 'admission_number', label: 'Admission #' },
                    { key: 'patient_name', label: 'Patient' },
                    { key: 'discharge_date', label: 'Discharge date' },
                    { key: 'cause_of_death', label: 'Cause of death' },
                    { key: 'mlc_required', label: 'MLC' },
                    { key: 'autopsy_done', label: 'Autopsy' },
                  ]}
                  rows={(data?.rows || []).map((r) => ({
                    ...r,
                    mlc_required: r.mlc_required ? 'Yes' : 'No',
                    autopsy_done: r.autopsy_done ? 'Yes' : 'No',
                  }))}
                />
              )}
            </CardContent>
          </Card>
        </>
      )}

      {kind === 'pharmacy-sales' && (
        <>
          <KpiCards items={[
            ['Bills', t.count],
            ['Billed', formatInr(t.billed)],
            ['Tax', formatInr(t.tax)],
            ['Discount', formatInr(t.discount)],
          ]} />
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Pharmacy sales by day</CardTitle>
              <p className="text-xs font-normal text-gray-500 mt-1">{kindMeta.hint}.</p>
            </CardHeader>
            <CardContent>
              {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                <MoneyTable
                  columns={[
                    { key: 'date', label: 'Date' },
                    { key: 'count', label: 'Bills', align: 'right' },
                    { key: 'billed', label: 'Billed', align: 'right', money: true },
                    { key: 'tax', label: 'Tax', align: 'right', money: true },
                    { key: 'discount', label: 'Discount', align: 'right', money: true },
                  ]}
                  rows={data?.rows || []}
                  totals={t}
                />
              )}
            </CardContent>
          </Card>
        </>
      )}

      {kind === 'pharmacy-stock' && (
        <>
          <KpiCards items={[
            ['SKUs', t.skus],
            ['Low stock', t.low_stock],
            ['Value (MRP)', formatInr(t.stock_value_mrp)],
            ['Value (cost)', formatInr(t.stock_value_cost)],
          ]} />
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Stock on hand</CardTitle>
              <p className="text-xs font-normal text-gray-500 mt-1">{kindMeta.hint}. Low-stock items are listed first.</p>
            </CardHeader>
            <CardContent>
              {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                <MoneyTable
                  columns={[
                    { key: 'name', label: 'Medicine' },
                    { key: 'total_stock', label: 'Stock', align: 'right' },
                    { key: 'batches', label: 'Batches', align: 'right' },
                    { key: 'min_qty', label: 'Min qty', align: 'right' },
                    { key: 'nearest_expiry', label: 'Nearest expiry' },
                    { key: 'low_stock', label: 'Low' },
                  ]}
                  rows={(data?.rows || []).map((r) => ({
                    ...r,
                    low_stock: r.low_stock ? 'Yes' : '',
                  }))}
                />
              )}
            </CardContent>
          </Card>
        </>
      )}

      {kind === 'daycare-volume' && (
        <>
          <KpiCards items={[
            ['Bills', t.count],
            ['Billed', formatInr(t.billed)],
            ['Collected', formatInr(t.collected)],
            ['Outstanding', formatInr(t.outstanding)],
          ]} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">By status</CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                  <MoneyTable
                    columns={[
                      { key: 'status', label: 'Status' },
                      { key: 'count', label: 'Count', align: 'right' },
                      { key: 'billed', label: 'Billed', align: 'right', money: true },
                    ]}
                    rows={data?.by_status || []}
                  />
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Day care / procedure bills</CardTitle>
                <p className="text-xs font-normal text-gray-500 mt-1">{kindMeta.hint}.</p>
              </CardHeader>
              <CardContent>
                {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                  <MoneyTable
                    columns={[
                      { key: 'date', label: 'Date' },
                      { key: 'number', label: 'Number' },
                      { key: 'party', label: 'Party' },
                      { key: 'billed', label: 'Billed', align: 'right', money: true },
                      { key: 'status', label: 'Status' },
                    ]}
                    rows={data?.rows || []}
                    totals={{ billed: t.billed }}
                  />
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {kind === 'physio-summary' && (
        <>
          <KpiCards items={[
            ['Sessions', t.sessions],
            ['Completed', t.completed],
            ['No-show', t.no_show],
            ['Collections', formatInr(t.collections)],
            ['Outstanding', formatInr(t.outstanding)],
          ]} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">By status</CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                  <MoneyTable
                    columns={[
                      { key: 'status', label: 'Status' },
                      { key: 'count', label: 'Count', align: 'right' },
                    ]}
                    rows={data?.by_status || []}
                  />
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Therapist utilization</CardTitle>
                <p className="text-xs font-normal text-gray-500 mt-1">{kindMeta.hint}.</p>
              </CardHeader>
              <CardContent>
                {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                  <MoneyTable
                    columns={[
                      { key: 'therapist_name', label: 'Therapist' },
                      { key: 'completed', label: 'Done', align: 'right' },
                      { key: 'no_show', label: 'No-show', align: 'right' },
                      { key: 'cancelled', label: 'Cancelled', align: 'right' },
                      { key: 'scheduled', label: 'Scheduled', align: 'right' },
                    ]}
                    rows={data?.rows || []}
                    totals={{
                      completed: t.completed,
                      no_show: t.no_show,
                      cancelled: t.cancelled,
                    }}
                  />
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {kind === 'canteen-activity' && (
        <>
          <KpiCards items={[
            ['POS bills', t.pos_bills],
            ['POS amount', formatInr(t.pos_amount)],
            ['IP food orders', t.ip_orders],
            ['IP billed', t.ip_billed],
          ]} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">POS by payment</CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                  <MoneyTable
                    columns={[
                      { key: 'method', label: 'Method' },
                      { key: 'count', label: 'Bills', align: 'right' },
                      { key: 'amount', label: 'Amount', align: 'right', money: true },
                    ]}
                    rows={data?.by_payment || []}
                  />
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">IP food orders by status</CardTitle>
              </CardHeader>
              <CardContent>
                {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                  <MoneyTable
                    columns={[
                      { key: 'status', label: 'Status' },
                      { key: 'count', label: 'Count', align: 'right' },
                    ]}
                    rows={data?.ip_by_status || []}
                  />
                )}
              </CardContent>
            </Card>
          </div>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Canteen POS sales</CardTitle>
              <p className="text-xs font-normal text-gray-500 mt-1">{kindMeta.hint}.</p>
            </CardHeader>
            <CardContent>
              {loading ? <Loader2 className="h-5 w-5 animate-spin text-gray-400" /> : (
                <MoneyTable
                  columns={[
                    { key: 'date', label: 'Date' },
                    { key: 'number', label: 'Number' },
                    { key: 'party', label: 'Party' },
                    { key: 'billed', label: 'Billed', align: 'right', money: true },
                    { key: 'status', label: 'Status' },
                  ]}
                  rows={data?.rows || []}
                  totals={{ billed: t.pos_amount }}
                />
              )}
            </CardContent>
          </Card>
        </>
      )}

      {pdfPath && (
        <PdfPreviewDialog
          open={pdfOpen}
          onClose={() => setPdfOpen(false)}
          path={pdfPath}
          params={kind === 'monthly-outcomes' ? { month } : (kind === 'bed-occupancy' ? {} : filterParams)}
          title={`${kindMeta.label} PDF`}
          filename={`${fileStem}.pdf`}
          letterheadReportType={kind === 'sales' ? 'billing_sales_summary' : null}
        />
      )}
    </div>
  );
}
