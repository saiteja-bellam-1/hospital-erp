import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import {
  AlertCircle, CheckCircle2, ChevronLeft, ChevronRight, Clock3,
  Download, FileSpreadsheet, Loader2, RotateCcw, Settings2, Upload,
} from 'lucide-react';

import { Button } from '../../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Input } from '../../components/ui/input';
import { Stepper } from '../../components/ui/stepper';
import { Textarea } from '../../components/ui/textarea';

const PRE_FLIGHT = [
  'Hospital legal name, address, registration/tax details and contact information',
  'A clear hospital logo in PNG, JPEG or WebP format (maximum 2 MB)',
  'List of departments and wards using the exact names staff should see',
  'Doctors, nurses and staff details, including unique email addresses',
  'OPD registration fee amount (even if zero)',
  'Room list with room types, daily charges and bed counts (if inpatient is licensed)',
  'Nursing visit rates by room type (if inpatient is licensed)',
  'Ancillary services such as imaging, oxygen and physiotherapy (optional)',
  'Pharmacy medicine catalogue with medicine codes and pricing (if pharmacy is licensed)',
  'Pharmacy supplier list for purchases (if pharmacy is licensed)',
  'Opening stock batches — optional; can wait until first purchase',
  'Letterhead choice: ERP-generated header or pre-printed stationery',
  'A writable local or network folder for database backups',
];

const ROOM_TYPE_LABELS = {
  general: 'General Ward',
  semi_private: 'Semi-Private',
  private: 'Private',
  suite: 'Suite / Deluxe',
  icu: 'ICU',
  hdu: 'HDU / Step-Down',
  nicu: 'NICU',
  picu: 'PICU',
  isolation: 'Isolation',
  labour: 'Labour & Delivery',
  recovery: 'Post-Op Recovery',
  daycare: 'Day Care',
  emergency: 'Emergency / Casualty',
  operation: 'Operation Theatre',
};

const EMBEDDED_STEPS = new Set([
  'hospital_profile',
  'logo',
  'print_settings',
  'departments',
  'opd_registration_fee',
  'rooms_and_beds',
  'room_type_nursing_rates',
  'ancillary_catalog',
  'doctor_ip_rates',
  'opd_procedures',
  'payer_schemes',
  'pharmacy_medicines',
  'pharmacy_suppliers',
  'pharmacy_opening_stock',
]);

async function download(url, fallbackName) {
  const response = await axios.get(url, { responseType: 'blob' });
  const disposition = response.headers['content-disposition'] || '';
  const match = disposition.match(/filename="?([^";]+)"?/i);
  const blobUrl = window.URL.createObjectURL(new Blob([response.data]));
  const anchor = document.createElement('a');
  anchor.href = blobUrl;
  anchor.download = match?.[1] || fallbackName;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(blobUrl);
}

function ImportPanel({
  templateKey,
  templateLabel,
  importUrl,
  templateUrl,
  onImported,
  busy,
  setBusy,
  setError,
  variant = 'onboarding',
  onDuplicate = 'skip',
}) {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);

  const runImport = async () => {
    if (!file) return;
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const formData = new FormData();
      formData.append('file', file);
      if (variant === 'pharmacy') {
        formData.append('dry_run', 'false');
        formData.append('on_duplicate', onDuplicate);
      }
      const response = await axios.post(importUrl, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResult(response.data);
      const pharmacyOk = variant === 'pharmacy'
        && typeof response.data?.created === 'number';
      const onboardingOk = response.data?.ok === true;
      if (pharmacyOk || onboardingOk) {
        setFile(null);
        await onImported?.();
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Import failed.');
    } finally {
      setBusy(false);
    }
  };

  const downloadTemplate = () => {
    if (templateUrl) {
      return download(templateUrl, `${templateKey || 'setup'}_template.xlsx`);
    }
    return download(`/api/onboarding/templates/${templateKey}`, `${templateKey}_setup_template.xlsx`);
  };

  const pharmacySuccess = variant === 'pharmacy' && result && typeof result.created === 'number';
  const onboardingSuccess = result?.ok === true;
  const success = pharmacySuccess || onboardingSuccess;

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50/70 p-4">
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={downloadTemplate}>
          <FileSpreadsheet className="mr-2 h-4 w-4 text-emerald-600" /> Download {templateLabel} template
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          type="file"
          accept=".xlsx,.csv"
          className="max-w-sm"
          onChange={(event) => {
            setFile(event.target.files?.[0] || null);
            setResult(null);
          }}
        />
        <Button size="sm" onClick={runImport} disabled={!file || busy}>
          {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
          Upload and import
        </Button>
      </div>
      {result && (
        <div className={`rounded-md border p-3 text-sm ${success ? 'border-emerald-200 bg-emerald-50 text-emerald-800' : 'border-red-200 bg-red-50 text-red-700'}`}>
          {success ? (
            <div className="space-y-1">
              <p>
                Import complete
                {result.created_rooms != null && ` — ${result.created_rooms} rooms, ${result.created_beds} beds`}
                {result.created != null && ` — ${result.created} created`}
                {result.updated != null && ` — ${result.updated} updated`}
                {result.upserted != null && ` — ${result.upserted} rates saved`}
                {result.skipped ? `, ${result.skipped} skipped` : ''}
                {result.error_count ? `, ${result.error_count} row errors` : ''}
              </p>
              {result.masters_created?.length > 0 && (
                <p className="text-xs">
                  Auto-created masters: {result.masters_created.slice(0, 8).join(', ')}
                  {result.masters_created.length > 8 ? ` (+${result.masters_created.length - 8} more)` : ''}
                </p>
              )}
              {(result.errors || []).length > 0 && (
                <div className="mt-2 space-y-1 text-amber-800">
                  {(result.errors || []).slice(0, 6).map((item, index) => (
                    <p key={index} className="text-xs">
                      {item.sheet ? `${item.sheet} ` : ''}row {item.row}: {item.message}
                    </p>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-1">
              <p className="font-medium">Fix these rows and try again (nothing was saved):</p>
              {(result.errors || []).slice(0, 8).map((item, index) => (
                <p key={index} className="text-xs">
                  {item.sheet} row {item.row}: {item.message}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function SetupWizard() {
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [departmentsText, setDepartmentsText] = useState('');
  const [hospitalForm, setHospitalForm] = useState({});
  const [printForm, setPrintForm] = useState({});
  const [registrationFee, setRegistrationFee] = useState('0');
  const [nursingRates, setNursingRates] = useState([]);
  const [logoFile, setLogoFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const [statusResponse, templateResponse, hospitalResponse, printResponse, feeResponse] = await Promise.all([
        axios.get('/api/onboarding/status'),
        axios.get('/api/onboarding/templates'),
        axios.get('/api/hospital/info'),
        axios.get('/api/hospital/print-settings'),
        axios.get('/api/hospital/registration-fee').catch(() => ({ data: { registration_fee: 0 } })),
      ]);
      setStatus(statusResponse.data);
      setTemplates(templateResponse.data);
      setHospitalForm(hospitalResponse.data);
      setPrintForm(printResponse.data);
      setRegistrationFee(String(feeResponse.data.registration_fee ?? 0));
      setDepartmentsText((statusResponse.data.departments || []).join('\n'));

      const hasInpatient = (statusResponse.data.steps || []).some((step) => step.key === 'rooms_and_beds');
      if (hasInpatient) {
        try {
          const rates = await axios.get('/api/inpatient/room-type-rates');
          setNursingRates(
            (rates.data || []).map((row) => ({
              room_type: row.room_type,
              label: row.room_type_label || ROOM_TYPE_LABELS[row.room_type] || row.room_type,
              nursing_charge_per_visit: row.nursing_charge_per_visit ?? '',
            })),
          );
        } catch {
          setNursingRates(
            Object.entries(ROOM_TYPE_LABELS).map(([room_type, label]) => ({
              room_type,
              label,
              nursing_charge_per_visit: '',
            })),
          );
        }
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Unable to load guided setup.');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const wizardSteps = useMemo(() => [
    { key: 'prepare', label: 'Prepare', completed: false },
    ...(status?.steps || []),
    { key: 'review', label: 'Review', completed: !!status?.completed },
  ], [status]);

  const current = wizardSteps[activeIndex];
  const setupStep = status?.steps?.find((step) => step.key === current?.key);

  const updateStep = async (key, nextStatus) => {
    setBusy(true);
    setError('');
    try {
      const response = await axios.put(`/api/onboarding/steps/${key}`, { status: nextStatus });
      setStatus(response.data);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Could not update the setup step.');
    } finally {
      setBusy(false);
    }
  };

  const saveDepartments = async () => {
    const names = departmentsText.split(/\r?\n|,/).map((name) => name.trim()).filter(Boolean);
    setBusy(true);
    try {
      const response = await axios.put('/api/onboarding/departments', { names });
      setStatus(response.data);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Could not save departments.');
    } finally {
      setBusy(false);
    }
  };

  const saveHospitalProfile = async () => {
    setBusy(true);
    setError('');
    try {
      await axios.put('/api/hospital/info', hospitalForm);
      await load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Could not save the hospital profile.');
    } finally {
      setBusy(false);
    }
  };

  const uploadLogo = async () => {
    if (!logoFile) return;
    setBusy(true);
    setError('');
    try {
      const formData = new FormData();
      formData.append('file', logoFile);
      const upload = await axios.post('/api/hospital/upload-file', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      await axios.put('/api/hospital/info', { logo_url: upload.data.url });
      setLogoFile(null);
      await load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Could not upload the hospital logo.');
    } finally {
      setBusy(false);
    }
  };

  const savePrintSettings = async () => {
    setBusy(true);
    setError('');
    try {
      const layout = printForm.prescription_vitals_layout
        || (printForm.prescription_include_vitals === false ? 'blank' : 'show');
      await axios.put('/api/hospital/print-settings', {
        include_header_on_pdfs: !!printForm.include_header_on_pdfs,
        include_footer_on_pdfs: !!printForm.include_footer_on_pdfs,
        detailed_billing_on_pdfs: !!printForm.detailed_billing_on_pdfs,
        prescription_vitals_layout: layout,
        prescription_vital_fields: Array.isArray(printForm.prescription_vital_fields)
          ? printForm.prescription_vital_fields
          : undefined,
        letterhead_gap_mm: Number(printForm.letterhead_gap_mm ?? 35),
      });
      await load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Could not save print settings.');
    } finally {
      setBusy(false);
    }
  };

  const previewPrintSettings = async () => {
    try {
      const response = await axios.post('/api/hospital/print-settings/preview', {
        ...printForm,
        report_type: 'opd_bill',
        letterhead_gap_mm: Number(printForm.letterhead_gap_mm ?? 35),
      }, { responseType: 'blob' });
      window.open(window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' })), '_blank', 'noopener,noreferrer');
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Could not generate the PDF preview.');
    }
  };

  const saveRegistrationFee = async () => {
    setBusy(true);
    setError('');
    try {
      await axios.put('/api/hospital/registration-fee', {
        registration_fee: Number(registrationFee || 0),
      });
      await load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Could not save the registration fee.');
    } finally {
      setBusy(false);
    }
  };

  const saveNursingRates = async () => {
    setBusy(true);
    setError('');
    try {
      const rates = nursingRates
        .filter((row) => row.nursing_charge_per_visit !== '' && row.nursing_charge_per_visit != null)
        .map((row) => ({
          room_type: row.room_type,
          nursing_charge_per_visit: Number(row.nursing_charge_per_visit),
        }));
      if (!rates.length) {
        setError('Enter at least one nursing rate before saving.');
        setBusy(false);
        return;
      }
      const response = await axios.put('/api/onboarding/nursing-rates', { rates });
      setStatus(response.data);
      await load();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Could not save nursing rates.');
    } finally {
      setBusy(false);
    }
  };

  if (!status) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        {error ? <p className="text-sm text-red-600">{error}</p> : <Loader2 className="h-7 w-7 animate-spin text-blue-600" />}
      </div>
    );
  }

  const progress = status.total_count
    ? Math.round((status.completed_count / status.total_count) * 100)
    : 0;

  return (
    <div className="mx-auto max-w-6xl space-y-5 p-4 md:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Guided hospital setup</h1>
          <p className="mt-1 text-sm text-slate-500">
            Complete this checklist at your own pace. You can leave and return at any time.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load}>
          <RotateCcw className="mr-2 h-4 w-4" /> Recheck progress
        </Button>
      </div>

      <Card>
        <CardContent className="pt-5">
          <div className="mb-2 flex justify-between text-sm">
            <span className="font-medium text-slate-700">{status.completed_count} of {status.total_count} steps complete</span>
            <span className="text-slate-500">{progress}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-emerald-500 transition-all" style={{ width: `${progress}%` }} />
          </div>
          <div className="mt-4"><Stepper steps={wizardSteps} activeIndex={activeIndex} onStepClick={setActiveIndex} /></div>
        </CardContent>
      </Card>

      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          <AlertCircle className="h-4 w-4" /> {error}
        </div>
      )}

      {current?.key === 'prepare' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">Before you begin</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <p className="text-sm text-slate-600">
              Gather these items before starting. Setup usually takes 60–120 minutes depending on catalogues.
            </p>
            <div className="grid gap-2 md:grid-cols-2">
              {PRE_FLIGHT.map((item) => (
                <div key={item} className="flex gap-2 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" /> {item}
                </div>
              ))}
            </div>
            <div className="rounded-lg border border-blue-100 bg-blue-50/60 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-medium text-slate-800">Sample spreadsheet files</p>
                  <p className="text-xs text-slate-500">Download all files together or choose an individual template.</p>
                </div>
                <Button onClick={() => download('/api/onboarding/templates/all.zip', 'kthealth_setup_templates.zip')}>
                  <Download className="mr-2 h-4 w-4" /> Download all
                </Button>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {templates.map((template) => (
                  <Button
                    key={template.key}
                    variant="outline"
                    size="sm"
                    onClick={() => download(`/api/onboarding/templates/${template.key}`, template.filename)}
                  >
                    <FileSpreadsheet className="mr-2 h-4 w-4 text-emerald-600" /> {template.label}
                  </Button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {setupStep && (
        <Card>
          <CardHeader>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <CardTitle className="text-xl">{setupStep.label}</CardTitle>
                <p className="mt-2 max-w-2xl text-sm text-slate-500">{setupStep.description}</p>
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <Clock3 className="h-4 w-4" /> About {setupStep.minutes} minutes
                {setupStep.required && <span className="rounded bg-amber-100 px-2 py-1 text-amber-700">Required</span>}
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {setupStep.key === 'hospital_profile' && (
              <div className="grid max-w-3xl gap-4 md:grid-cols-2">
                {[
                  ['name', 'Hospital name'],
                  ['phone', 'Phone'],
                  ['email', 'Email'],
                  ['registration_number', 'Registration number'],
                  ['tax_id', 'Tax ID'],
                  ['mrn_prefix', 'MRN prefix'],
                  ['city', 'City'],
                  ['state', 'State'],
                  ['postal_code', 'Postal code'],
                  ['country', 'Country'],
                ].map(([key, label]) => (
                  <label key={key} className="space-y-1.5 text-sm font-medium text-slate-700">
                    <span>{label}</span>
                    <Input
                      value={hospitalForm[key] || ''}
                      onChange={(event) => setHospitalForm((form) => ({ ...form, [key]: event.target.value }))}
                    />
                  </label>
                ))}
                <label className="space-y-1.5 text-sm font-medium text-slate-700 md:col-span-2">
                  <span>Address</span>
                  <Textarea
                    rows={3}
                    value={hospitalForm.address || ''}
                    onChange={(event) => setHospitalForm((form) => ({ ...form, address: event.target.value }))}
                  />
                </label>
                <div className="md:col-span-2">
                  <Button onClick={saveHospitalProfile} disabled={busy}>
                    {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Save hospital profile
                  </Button>
                </div>
              </div>
            )}

            {setupStep.key === 'logo' && (
              <div className="flex max-w-2xl flex-wrap items-center gap-4">
                {hospitalForm.logo_url && (
                  <div className="flex h-24 w-40 items-center justify-center rounded-lg border bg-white p-2">
                    <img src={hospitalForm.logo_url} alt="Current hospital logo" className="max-h-full max-w-full object-contain" />
                  </div>
                )}
                <div className="space-y-2">
                  <Input
                    type="file"
                    accept=".png,.jpg,.jpeg,.webp"
                    onChange={(event) => setLogoFile(event.target.files?.[0] || null)}
                  />
                  <p className="text-xs text-slate-500">PNG, JPEG or WebP; maximum 2 MB.</p>
                  <Button onClick={uploadLogo} disabled={!logoFile || busy}>
                    {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Upload logo
                  </Button>
                </div>
              </div>
            )}

            {setupStep.key === 'print_settings' && (
              <div className="max-w-2xl space-y-4">
                {[
                  ['include_header_on_pdfs', 'Show hospital letterhead on PDFs'],
                  ['include_footer_on_pdfs', 'Show staff/signature footers'],
                  ['detailed_billing_on_pdfs', 'Show detailed totals, paid amount and balance'],
                ].map(([key, label]) => (
                  <label key={key} className="flex items-center justify-between gap-4 rounded-lg border p-3 text-sm text-slate-700">
                    <span>{label}</span>
                    <input
                      type="checkbox"
                      checked={!!printForm[key]}
                      onChange={(event) => setPrintForm((form) => ({ ...form, [key]: event.target.checked }))}
                      className="h-4 w-4 rounded border-slate-300"
                    />
                  </label>
                ))}

                <div className="space-y-2 rounded-lg border p-3">
                  <p className="text-sm font-medium text-slate-800">Prescription vitals column</p>
                  {[
                    ['show', 'Show vitals on prescription'],
                    ['blank', 'Leave blank column (pre-printed stationery)'],
                    ['remove', 'Remove column (medicines full width)'],
                  ].map(([value, label]) => (
                    <label key={value} className="flex items-center gap-2 text-sm text-slate-700">
                      <input
                        type="radio"
                        name="setup-vitals-layout"
                        checked={(printForm.prescription_vitals_layout || 'show') === value}
                        onChange={() => setPrintForm((form) => ({
                          ...form,
                          prescription_vitals_layout: value,
                          prescription_include_vitals: value === 'show',
                        }))}
                      />
                      {label}
                    </label>
                  ))}
                </div>

                <div className="space-y-2 rounded-lg border p-3">
                  <p className="text-sm font-medium text-slate-800">Vitals to collect after appointments</p>
                  <p className="text-xs text-slate-500">
                    Reception and nurses will only see these fields on Record Vitals.
                  </p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {(printForm.prescription_vital_catalog || [
                      { key: 'height', label: 'Height' },
                      { key: 'weight', label: 'Weight' },
                      { key: 'blood_pressure', label: 'Blood Pressure' },
                      { key: 'heart_rate', label: 'Pulse' },
                      { key: 'temperature', label: 'Temperature' },
                      { key: 'respiratory_rate', label: 'Resp. Rate' },
                      { key: 'spo2', label: 'SpO2' },
                      { key: 'bmi', label: 'BMI' },
                      { key: 'pain_scale', label: 'Pain Score' },
                    ]).map((item) => {
                      const selected = (printForm.prescription_vital_fields || []).includes(item.key);
                      return (
                        <label key={item.key} className="flex items-center gap-2 text-sm text-slate-700">
                          <input
                            type="checkbox"
                            className="h-4 w-4 rounded border-slate-300"
                            checked={selected}
                            onChange={() => {
                              setPrintForm((form) => {
                                const current = Array.isArray(form.prescription_vital_fields)
                                  ? form.prescription_vital_fields
                                  : [];
                                const next = selected
                                  ? current.filter((k) => k !== item.key)
                                  : [...current, item.key];
                                return {
                                  ...form,
                                  prescription_vital_fields: next.length
                                    ? next
                                    : current.length
                                      ? current
                                      : [item.key],
                                };
                              });
                            }}
                          />
                          {item.label}
                        </label>
                      );
                    })}
                  </div>
                </div>

                <label className="block space-y-1.5 text-sm font-medium text-slate-700">
                  <span>Top gap for pre-printed stationery (mm)</span>
                  <Input
                    type="number"
                    min="0"
                    max="80"
                    className="max-w-40"
                    value={printForm.letterhead_gap_mm ?? 35}
                    onChange={(event) => setPrintForm((form) => ({ ...form, letterhead_gap_mm: event.target.value }))}
                  />
                </label>
                <div className="flex gap-2">
                  <Button onClick={savePrintSettings} disabled={busy}>
                    {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Save customisations
                  </Button>
                  <Button variant="outline" onClick={previewPrintSettings}>Preview sample bill</Button>
                </div>
              </div>
            )}

            {setupStep.key === 'departments' && (
              <div className="max-w-xl space-y-2">
                <label className="text-sm font-medium text-slate-700">Department and ward names</label>
                <Textarea
                  rows={8}
                  value={departmentsText}
                  onChange={(event) => setDepartmentsText(event.target.value)}
                  placeholder={'Emergency\nOutpatient\nGeneral Ward\nICU'}
                />
                <p className="text-xs text-slate-500">Enter one name per line. These remain suggestions; existing room records keep their current text.</p>
                <Button onClick={saveDepartments} disabled={busy}>
                  {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Save names
                </Button>
              </div>
            )}

            {setupStep.key === 'opd_registration_fee' && (
              <div className="max-w-md space-y-3">
                <label className="block space-y-1.5 text-sm font-medium text-slate-700">
                  <span>Registration fee (INR)</span>
                  <Input
                    type="number"
                    min="0"
                    step="1"
                    value={registrationFee}
                    onChange={(event) => setRegistrationFee(event.target.value)}
                  />
                </label>
                <p className="text-xs text-slate-500">
                  Charged once when a new outpatient is registered. Enter 0 if your hospital does not charge a registration fee.
                </p>
                <Button onClick={saveRegistrationFee} disabled={busy}>
                  {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Save registration fee
                </Button>
              </div>
            )}

            {setupStep.key === 'rooms_and_beds' && (
              <div className="space-y-3">
                <p className="text-sm text-slate-600">
                  Import rooms from Excel. Beds are created automatically from bed_count unless you fill the Beds sheet.
                </p>
                <ImportPanel
                  templateKey="rooms"
                  templateLabel="rooms"
                  importUrl="/api/onboarding/import/rooms"
                  onImported={load}
                  busy={busy}
                  setBusy={setBusy}
                  setError={setError}
                />
                <Button variant="outline" onClick={() => navigate('/dashboard/inpatient/rooms')}>
                  <Settings2 className="mr-2 h-4 w-4" /> Open room management
                </Button>
              </div>
            )}

            {setupStep.key === 'room_type_nursing_rates' && (
              <div className="space-y-4">
                <div className="overflow-hidden rounded-lg border">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
                      <tr>
                        <th className="px-3 py-2">Room type</th>
                        <th className="px-3 py-2 w-48">Nursing charge / day (INR)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {nursingRates.map((row) => (
                        <tr key={row.room_type} className="border-t">
                          <td className="px-3 py-2 text-slate-700">{row.label}</td>
                          <td className="px-3 py-2">
                            <Input
                              type="number"
                              min="0"
                              value={row.nursing_charge_per_visit}
                              onChange={(event) => setNursingRates((current) => current.map((item) => (
                                item.room_type === row.room_type
                                  ? { ...item, nursing_charge_per_visit: event.target.value }
                                  : item
                              )))}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button onClick={saveNursingRates} disabled={busy}>
                    {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Save nursing rates
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => download('/api/onboarding/templates/nursing_rates', 'nursing_rates_setup_template.xlsx')}
                  >
                    <FileSpreadsheet className="mr-2 h-4 w-4" /> Template
                  </Button>
                </div>
                <ImportPanel
                  templateKey="nursing_rates"
                  templateLabel="nursing rates"
                  importUrl="/api/onboarding/import/nursing-rates"
                  onImported={load}
                  busy={busy}
                  setBusy={setBusy}
                  setError={setError}
                />
              </div>
            )}

            {setupStep.key === 'ancillary_catalog' && (
              <ImportPanel
                templateKey="ancillary_services"
                templateLabel="ancillary services"
                importUrl="/api/onboarding/import/ancillary-services"
                onImported={load}
                busy={busy}
                setBusy={setBusy}
                setError={setError}
              />
            )}

            {setupStep.key === 'doctor_ip_rates' && (
              <div className="space-y-3">
                <p className="text-sm text-slate-600">
                  Each doctor should have an inpatient fee. Optional room-type overrides can be imported below.
                </p>
                <ImportPanel
                  templateKey="doctor_room_rates"
                  templateLabel="doctor room rates"
                  importUrl="/api/onboarding/import/doctor-room-rates"
                  onImported={load}
                  busy={busy}
                  setBusy={setBusy}
                  setError={setError}
                />
                <Button variant="outline" onClick={() => navigate('/dashboard/admin/users')}>
                  <Settings2 className="mr-2 h-4 w-4" /> Open Users
                </Button>
              </div>
            )}

            {setupStep.key === 'opd_procedures' && (
              <ImportPanel
                templateKey="opd_procedures"
                templateLabel="OPD procedures"
                importUrl="/api/onboarding/import/opd-procedures"
                onImported={load}
                busy={busy}
                setBusy={setBusy}
                setError={setError}
              />
            )}

            {setupStep.key === 'payer_schemes' && (
              <div className="space-y-3 text-sm text-slate-600">
                <p>
                  Default payer types are already seeded: Cash, Private Insurance, TPA, Aarogyasri,
                  Teachers&apos; Health Scheme and Employee Health Scheme.
                </p>
                <p>
                  Review them and add any hospital-specific schemes. Point-of-sale payment methods
                  (cash, card, UPI, cheque) are built in and do not need setup.
                </p>
                <Button variant="outline" onClick={() => navigate('/dashboard/hospital-admin/payers')}>
                  <Settings2 className="mr-2 h-4 w-4" /> Open payer schemes
                </Button>
              </div>
            )}

            {setupStep.key === 'users' && (
              <div className="flex flex-wrap gap-2">
                {templates.filter((item) => ['doctors', 'nurses', 'staff'].includes(item.key)).map((template) => (
                  <Button
                    key={template.key}
                    variant="outline"
                    size="sm"
                    onClick={() => download(`/api/onboarding/templates/${template.key}`, template.filename)}
                  >
                    <FileSpreadsheet className="mr-2 h-4 w-4" /> {template.label} template
                  </Button>
                ))}
              </div>
            )}

            {setupStep.key === 'lab_catalogue' && (
              <Button variant="outline" onClick={() => download('/api/lab/tests/import/template', 'lab_tests_import_template.xlsx')}>
                <FileSpreadsheet className="mr-2 h-4 w-4" /> Download detailed lab template
              </Button>
            )}

            {setupStep.key === 'pharmacy_medicines' && (
              <div className="space-y-3">
                <p className="text-sm text-slate-600">
                  Import the medicine catalogue. Missing categories, companies, salts, racks, UoMs and HSN codes
                  are created automatically. You can also download the masters workbook first if you prefer to
                  seed lookups separately.
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => download('/api/pharmacy/masters/import/template', 'pharmacy_masters_import_template.xlsx')}
                  >
                    <FileSpreadsheet className="mr-2 h-4 w-4" /> Masters template (optional)
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => navigate('/dashboard/pharmacy/medicines')}>
                    <Settings2 className="mr-2 h-4 w-4" /> Open medicines
                  </Button>
                </div>
                <ImportPanel
                  templateKey="pharmacy_medicines"
                  templateLabel="medicines"
                  templateUrl="/api/pharmacy/medicines/import/template"
                  importUrl="/api/pharmacy/medicines/import"
                  variant="pharmacy"
                  onDuplicate="skip"
                  onImported={load}
                  busy={busy}
                  setBusy={setBusy}
                  setError={setError}
                />
              </div>
            )}

            {setupStep.key === 'pharmacy_suppliers' && (
              <div className="space-y-3">
                <p className="text-sm text-slate-600">
                  Import suppliers used for pharmacy purchases. Existing names are skipped by default.
                </p>
                <Button variant="outline" size="sm" onClick={() => navigate('/dashboard/pharmacy/suppliers')}>
                  <Settings2 className="mr-2 h-4 w-4" /> Open suppliers
                </Button>
                <ImportPanel
                  templateKey="pharmacy_suppliers"
                  templateLabel="suppliers"
                  templateUrl="/api/pharmacy/suppliers/import/template"
                  importUrl="/api/pharmacy/suppliers/import"
                  variant="pharmacy"
                  onDuplicate="skip"
                  onImported={load}
                  busy={busy}
                  setBusy={setBusy}
                  setError={setError}
                />
              </div>
            )}

            {setupStep.key === 'pharmacy_opening_stock' && (
              <div className="space-y-3">
                <p className="text-sm text-slate-600">
                  Seed opening batches after medicines exist. Quantity on update is absolute (not a delta).
                  Leave <span className="font-medium">store_code</span> blank to use the master store.
                  Skip this step if you will start with supplier purchases instead.
                </p>
                <Button variant="outline" size="sm" onClick={() => navigate('/dashboard/pharmacy/inventory')}>
                  <Settings2 className="mr-2 h-4 w-4" /> Open inventory
                </Button>
                <ImportPanel
                  templateKey="pharmacy_opening_stock"
                  templateLabel="opening stock"
                  templateUrl="/api/pharmacy/opening-stock/import/template"
                  importUrl="/api/pharmacy/opening-stock/import"
                  variant="pharmacy"
                  onDuplicate="skip"
                  onImported={load}
                  busy={busy}
                  setBusy={setBusy}
                  setError={setError}
                />
              </div>
            )}

            {!EMBEDDED_STEPS.has(setupStep.key) && (
              <Button onClick={() => navigate(setupStep.path)}>
                <Settings2 className="mr-2 h-4 w-4" /> Open {setupStep.label}
              </Button>
            )}

            <div className="flex flex-wrap items-center gap-2 border-t pt-4">
              {setupStep.completed ? (
                <span className="flex items-center gap-2 text-sm font-medium text-emerald-700">
                  <CheckCircle2 className="h-5 w-5" /> This step is complete
                </span>
              ) : (
                <>
                  {setupStep.can_mark_complete && (
                    <Button variant="outline" size="sm" onClick={() => updateStep(setupStep.key, 'completed')} disabled={busy}>
                      Mark reviewed
                    </Button>
                  )}
                  {!setupStep.required && (
                    <Button variant="ghost" size="sm" onClick={() => updateStep(setupStep.key, 'skipped')} disabled={busy}>
                      Skip for now
                    </Button>
                  )}
                  {!setupStep.can_mark_complete && (
                    <span className="text-xs text-slate-500">Completion is detected automatically after you save the required data.</span>
                  )}
                </>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {current?.key === 'review' && (
        <Card>
          <CardHeader><CardTitle className="text-xl">Go-live review</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {status.steps.map((step) => (
              <button
                key={step.key}
                type="button"
                onClick={() => setActiveIndex(wizardSteps.findIndex((item) => item.key === step.key))}
                className="flex w-full items-center justify-between rounded-lg border p-3 text-left hover:bg-slate-50"
              >
                <span>
                  <span className="block text-sm font-medium text-slate-800">{step.label}</span>
                  <span className="text-xs text-slate-500">{step.required ? 'Required' : 'Optional'}</span>
                </span>
                <span className={step.completed ? 'text-emerald-600' : step.skipped ? 'text-slate-400' : 'text-amber-600'}>
                  {step.completed ? 'Complete' : step.skipped ? 'Skipped' : 'Needs attention'}
                </span>
              </button>
            ))}
            {status.completed && (
              <div className="rounded-lg bg-emerald-50 p-4 text-sm font-medium text-emerald-700">
                All required setup steps are complete. The hospital is ready for day-to-day use.
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <div className="flex justify-between">
        <Button variant="outline" disabled={activeIndex === 0} onClick={() => setActiveIndex((value) => value - 1)}>
          <ChevronLeft className="mr-2 h-4 w-4" /> Previous
        </Button>
        <Button disabled={activeIndex >= wizardSteps.length - 1} onClick={() => setActiveIndex((value) => value + 1)}>
          Next <ChevronRight className="ml-2 h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
