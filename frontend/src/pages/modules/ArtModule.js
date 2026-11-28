import React, { useCallback, useEffect, useState } from 'react';
import { Routes, Route, Link, useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import PatientSearchPicker from '../../components/PatientSearchPicker';
import { printPdfFromUrl } from '../../utils/printPdf';

function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join('; ');
  return e?.message || 'Request failed';
}

async function errorFromBlob(e) {
  const data = e?.response?.data;
  if (data && typeof data.text === 'function') {
    try {
      const parsed = JSON.parse(await data.text());
      if (typeof parsed.detail === 'string') return parsed.detail;
    } catch {
      /* The body was not a JSON error. */
    }
  }
  return errMsg(e);
}

async function downloadPdf(path, filename) {
  const res = await axios.get(path, { responseType: 'blob' });
  const type = res.headers['content-type'] || '';
  if (!type.includes('application/pdf')) {
    const parsed = JSON.parse(await res.data.text());
    const detail = typeof parsed.detail === 'string' ? parsed.detail : 'Could not download the form';
    throw new Error(detail);
  }
  const url = URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

const todayISO = () => new Date().toISOString().slice(0, 10);
const rupee = (n) => `₹${Number(n || 0).toLocaleString('en-IN')}`;
const pct = (rate) => (rate === null || rate === undefined ? '—' : `${Math.round(Number(rate) * 100)}%`);

function mmList(text) {
  return String(text || '')
    .split(',')
    .map((part) => part.trim())
    .filter((part) => part !== '')
    .map(Number)
    .filter((n) => !Number.isNaN(n));
}

const selectClass = 'flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2';

const PLAIN = {
  couple: 'Couple',
  single_woman: 'Single woman',
  oi: 'Ovulation medicines, then timed intercourse',
  iui_husband: "IUI with the husband's sperm",
  iui_donor: 'IUI with donor sperm',
  ivf: 'IVF (eggs and sperm mixed in the lab)',
  icsi: 'ICSI (one sperm injected into each egg)',
  freeze_all: 'Freeze all embryos, transfer later',
  fet: 'Frozen embryo transfer',
  oocyte_freeze: 'Egg freezing',
  sperm_freeze: 'Sperm freezing',
  package: 'One package price, paid at the start',
  itemised: 'A separate bill for each visit',
  planned: 'Planned',
  stimulation: 'On stimulation',
  triggered: 'Trigger injection given',
  retrieval: 'Eggs collected',
  fertilisation: 'Fertilisation done',
  culture: 'Embryos in the lab',
  transfer: 'Embryo transferred',
  luteal: 'Waiting for the pregnancy test',
  outcome: 'Outcome recorded',
  cancelled: 'Cancelled',
  scheduled: 'Booked',
  checked_in: 'Checked in',
  done: 'Done',
  waiting: 'Waiting',
  called: 'Called in',
  stored: 'In the bank',
  issued_internal: 'Issued to a patient here',
  issued_external: 'Sent to another clinic',
  received_external: 'Received for a patient',
  active: 'In use',
  maintenance: 'Under repair',
  report: 'Lab report',
  id_proof: 'Identity proof',
  full: 'Full',
  adequate: 'Adequate',
  low: 'Low',
  pending: 'Not paid',
  partial: 'Part paid',
  paid: 'Paid',
  credit_note: 'Refund',
  reactive: 'Reactive',
  non_reactive: 'Non-reactive',
  open: 'Open',
  closed: 'Closed',
  scan: 'Monitoring scan',
  iui: 'IUI',
  counsellor: 'Counsellor visit',
  opu: 'Egg collection',
  beta_hcg: 'Pregnancy blood test',
  oocyte: 'Egg donor',
  sperm: 'Sperm donor',
  embryo: 'Embryo',
  screening: 'Still being screened',
  cleared: 'Cleared to use',
  retired: 'No longer in use',
  in_culture: 'In the incubator',
  frozen: 'Frozen',
  thawed: 'Thawed',
  transferred: 'Transferred',
  discarded: 'Discarded',
  antagonist: 'Antagonist protocol',
  natural: 'Natural cycle',
  unspecified: 'Protocol not recorded',
  unassigned: 'No doctor assigned',
};

const CONSENT_PLAIN = {
  couple_treatment: 'Consent to start treatment',
  iui_husband: "IUI with the husband's sperm",
  iui_donor: 'IUI with donor sperm',
  embryo_freeze: 'Consent to freeze embryos',
  gamete_freeze: 'Consent to freeze eggs or sperm',
  parental_assent: 'A parent agrees to freeze eggs or sperm',
  oocyte_retrieval: 'Consent for egg collection',
  donor_sperm: 'Sperm donor’s own consent',
  donor_oocyte: 'Egg donor’s own consent',
  death_incapacity: 'What happens to stored samples if someone dies or cannot decide',
  withdrawal: 'Withdraw an earlier consent',
  discard: 'Consent to discard eggs, sperm, or embryos',
};

function plain(code) {
  if (code === null || code === undefined || code === '') return '—';
  const key = String(code);
  if (PLAIN[key]) return PLAIN[key];
  if (CONSENT_PLAIN[key]) return CONSENT_PLAIN[key];
  return key.replace(/_/g, ' ');
}

function Shell({ title, description, actions, children }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">{title}</h2>
          {description && <p className="mt-1 text-sm text-gray-500 max-w-2xl">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  );
}

function Notice({ error, info }) {
  if (!error && !info) return null;
  const tone = error
    ? 'border-red-200 bg-red-50 text-red-700'
    : 'border-emerald-200 bg-emerald-50 text-emerald-800';
  return <div className={`rounded-md border px-3 py-2 text-sm ${tone}`}>{error || info}</div>;
}

function Field({ label, hint, children, className = '' }) {
  return (
    <div className={`space-y-1.5 ${className}`}>
      <Label className="text-sm font-medium text-gray-700">{label}</Label>
      {children}
      {hint && <p className="text-xs text-gray-500">{hint}</p>}
    </div>
  );
}

function Choice({ value, onChange, options }) {
  return (
    <div className={`grid gap-2 ${options.length > 2 ? 'sm:grid-cols-2' : 'sm:grid-cols-2'}`}>
      {options.map((opt) => {
        const selected = String(value) === String(opt.value);
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`rounded-md border px-3 py-2 text-left ${selected ? 'border-blue-600 bg-blue-50 ring-1 ring-blue-600' : 'border-gray-200 hover:bg-gray-50'}`}
          >
            <span className="block text-sm font-medium text-gray-900">{opt.label}</span>
            {opt.hint && <span className="mt-0.5 block text-xs text-gray-500">{opt.hint}</span>}
          </button>
        );
      })}
    </div>
  );
}

function Empty({ children }) {
  return <p className="py-6 text-center text-sm text-gray-500">{children}</p>;
}

function BoardPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [day, setDay] = useState(todayISO());

  const load = useCallback(async () => {
    try {
      const res = await axios.get('/api/art/board', { params: { on: day } });
      setData(res.data);
      setError('');
    } catch (e) {
      setError(errMsg(e));
    }
  }, [day]);

  useEffect(() => { load(); }, [load]);

  async function setQueue(row, status) {
    try {
      await axios.post(`/api/art/queue/${row.id}/status`, { status });
      load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  return (
    <Shell
      title="Today"
      description="Who is waiting, which procedures are booked, and what needs attention."
      actions={(
        <>
          <Input className="w-40" type="date" value={day} onChange={(e) => setDay(e.target.value)} aria-label="Date" />
          <Button variant="outline" onClick={load}>Refresh</Button>
        </>
      )}
    >
      <Notice error={error} />
      {data && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card>
            <CardHeader><CardTitle className="text-base">Waiting queue</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {data.queue.length === 0 && <Empty>No one has checked in.</Empty>}
              {data.queue.map((row) => (
                <div key={row.id || row.token_no} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">Token {row.token_no}{row.name ? ` · ${row.name}` : ''}</p>
                    <p className="text-xs text-gray-500">{plain(row.status)}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {row.status === 'waiting' && <Button variant="outline" size="sm" onClick={() => setQueue(row, 'called')}>Call in</Button>}
                    {row.status === 'called' && <Button variant="outline" size="sm" onClick={() => setQueue(row, 'done')}>Seen</Button>}
                    <Link className="text-sm text-blue-700" to={`/dashboard/art/cases/${row.case_id}`}>Open case</Link>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Booked procedures</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {data.appointments.length === 0 && <Empty>Nothing booked for this day.</Empty>}
              {data.appointments.map((row) => (
                <div key={row.id} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{plain(row.kind)}{row.name ? ` · ${row.name}` : ''}</p>
                    <p className="text-xs text-gray-500">
                      {row.scheduled_time || 'No time set'} · {row.room || 'Room not set'}
                      {['iui', 'opu', 'transfer'].includes(row.kind) && row.status === 'scheduled' && !row.timeout_done ? ' · Time-out still to do' : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge variant="outline">{plain(row.status)}</Badge>
                    <Link className="text-sm text-blue-700" to={`/dashboard/art/cases/${row.case_id}`}>Open case</Link>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Needs attention</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex items-center justify-between rounded-md border px-3 py-2">
                <span>Unpaid fertility bills</span>
                <span className="font-medium">{data.pending_art_bills}</span>
              </div>
              {data.cryo_renewals.length === 0 && <Empty>No frozen samples are due for renewal.</Empty>}
              {data.cryo_renewals.map((row) => (
                <div
                  key={row.code}
                  className={`rounded-md border px-3 py-2 ${row.overdue ? 'border-red-200 bg-red-50 text-red-700' : 'border-amber-200 bg-amber-50 text-amber-900'}`}
                >
                  {row.overdue
                    ? `${row.code} storage renewal was due on ${row.renewal_due}`
                    : `${row.code} storage renews on ${row.renewal_due}`}
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      )}
    </Shell>
  );
}

function CasesPage() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState('');
  const [caseType, setCaseType] = useState('couple');
  const [woman, setWoman] = useState(null);
  const [partner, setPartner] = useState(null);
  const navigate = useNavigate();

  const load = useCallback(async () => {
    try {
      const res = await axios.get('/api/art/cases');
      setRows(res.data);
    } catch (e) {
      setError(errMsg(e));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function createCase() {
    try {
      const res = await axios.post('/api/art/cases', {
        case_type: caseType,
        woman_patient_id: woman?.id,
        partner_patient_id: caseType === 'couple' ? partner?.id : null,
      });
      navigate(`/dashboard/art/cases/${res.data.id}`);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  return (
    <Shell title="Cases" description="A case links the woman, and her partner when there is one, to every cycle that follows.">
      <Notice error={error} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Open a new case</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <Field label="Who is being treated">
              <Choice
                value={caseType}
                onChange={setCaseType}
                options={[
                  { value: 'couple', label: 'A couple', hint: 'The woman and her husband or partner' },
                  { value: 'single_woman', label: 'A single woman', hint: 'No partner on this case' },
                ]}
              />
            </Field>
            <PatientSearchPicker label="Woman" value={woman} onChange={setWoman} />
            {caseType === 'couple' && (
              <PatientSearchPicker label="Husband or partner" value={partner} onChange={setPartner} id="partner_search" />
            )}
            <Button onClick={createCase} disabled={!woman || (caseType === 'couple' && !partner)}>Open case</Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Open cases</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {rows.length === 0 && <Empty>No fertility cases yet.</Empty>}
            {rows.map((row) => (
              <Link key={row.id} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 hover:bg-gray-50" to={`/dashboard/art/cases/${row.id}`}>
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{row.woman_name}{row.partner_name ? ` and ${row.partner_name}` : ''}</p>
                  <p className="text-xs text-gray-500">{row.case_number}</p>
                </div>
                <Badge variant="outline">{plain(row.case_type)}</Badge>
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>
    </Shell>
  );
}

function CasePage() {
  const { caseId } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [workup, setWorkup] = useState({});
  const [note, setNote] = useState('');
  const [forms, setForms] = useState([]);
  const [formCode, setFormCode] = useState('couple_treatment');
  const [signedBy, setSignedBy] = useState('');
  const [packages, setPackages] = useState([]);
  const [cycleType, setCycleType] = useState('iui_husband');
  const [billingMode, setBillingMode] = useState('package');
  const [packageId, setPackageId] = useState('');
  const navigate = useNavigate();
  const staff = useStaff();

  const load = useCallback(async () => {
    try {
      const [caseRes, formRes, pkgRes] = await Promise.all([
        axios.get(`/api/art/cases/${caseId}`),
        axios.get('/api/art/consent-forms'),
        axios.get('/api/art/packages'),
      ]);
      setData(caseRes.data);
      setWorkup(caseRes.data.workup || {});
      setForms(formRes.data);
      setPackages(pkgRes.data);
      if (caseRes.data.case_type === 'single_woman') setCycleType((current) => (current === 'iui_husband' ? 'oi' : current));
      setError('');
    } catch (e) {
      setError(errMsg(e));
    }
  }, [caseId]);
  useEffect(() => { load(); }, [load]);

  async function saveWorkup() {
    const payload = {};
    Object.entries(workup).forEach(([key, value]) => {
      if (value !== '' && value !== null && value !== undefined) payload[key] = value;
    });
    try {
      await axios.put(`/api/art/cases/${caseId}/workup`, payload);
      setInfo('Assessment saved.');
      setError('');
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function addNote() {
    try {
      await axios.post(`/api/art/cases/${caseId}/notes`, { note });
      setNote('');
      setInfo('Counsellor note saved.');
      load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function addConsent() {
    try {
      await axios.post(`/api/art/cases/${caseId}/consents`, { form_code: formCode, signed_by_name: signedBy });
      setSignedBy('');
      setInfo('Signed copy recorded.');
      load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function downloadConsent() {
    try {
      await downloadPdf(
        `/api/art/cases/${caseId}/consent-form.pdf`,
        `${data?.case_number || 'consent'}-${formCode}.pdf`,
      );
      setInfo('Form downloaded. Sign the paper copy, then record it here.');
      setError('');
    } catch (e) {
      setError(await errorFromBlob(e));
    }
  }

  async function withdraw(row) {
    try {
      await axios.post(`/api/art/consents/${row.id}/withdraw`);
      setInfo('Consent withdrawn. Procedures that need it are blocked until a new one is signed.');
      setError('');
      load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function setCaseStatus(status) {
    try {
      await axios.post(`/api/art/cases/${caseId}/status`, { status });
      setInfo(status === 'closed' ? 'Case closed.' : 'Case reopened.');
      setError('');
      load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function checkIn() {
    try {
      const res = await axios.post('/api/art/queue', { case_id: Number(caseId) });
      setInfo(`Checked in. Token ${res.data.token_no}.`);
      setError('');
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function startCycle() {
    try {
      const res = await axios.post(`/api/art/cases/${caseId}/cycles`, {
        cycle_type: cycleType,
        billing_mode: billingMode,
        package_template_id: billingMode === 'package' ? Number(packageId) : null,
        collect_advance: billingMode === 'package',
        payment_method: 'cash',
      });
      navigate(`/dashboard/art/cycles/${res.data.id}`);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  if (!data) {
    return (
      <Shell title="Case">
        <Notice error={error} info={error ? '' : 'Loading the case…'} />
      </Shell>
    );
  }

  const cycleOptions = [
    { value: 'oi', label: 'Ovulation medicines', hint: 'Tablets or injections, then timed intercourse' },
    ...(data.case_type === 'couple' ? [{ value: 'iui_husband', label: "IUI, husband's sperm", hint: 'Prepared sperm placed in the womb' }] : []),
    { value: 'iui_donor', label: 'IUI, donor sperm', hint: 'Uses a donor sample' },
    { value: 'ivf', label: 'IVF', hint: 'Eggs collected and mixed with sperm' },
    { value: 'icsi', label: 'ICSI', hint: 'One sperm injected into each egg' },
    { value: 'freeze_all', label: 'Freeze all embryos', hint: 'No transfer in this cycle' },
    { value: 'fet', label: 'Frozen embryo transfer', hint: 'Uses embryos already in storage' },
    { value: 'oocyte_freeze', label: 'Egg freezing', hint: 'Store eggs, no transfer now' },
    { value: 'sperm_freeze', label: 'Sperm freezing', hint: 'Store a sperm sample' },
  ];

  return (
    <Shell
      title={data.woman_name}
      description={`${data.case_number}${data.partner_name ? ` · Partner ${data.partner_name}` : ''} · ${plain(data.case_type)}${data.status === 'closed' ? ' · Closed' : ''}`}
      actions={(
        <>
          {data.status === 'open' && <Button variant="outline" onClick={checkIn}>Check in for today</Button>}
          <Button variant="outline" onClick={() => setCaseStatus(data.status === 'open' ? 'closed' : 'open')}>
            {data.status === 'open' ? 'Close case' : 'Reopen case'}
          </Button>
        </>
      )}
    >
      <Notice error={error} info={info} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">First assessment</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Years trying" hint="How long they have been trying for a pregnancy">
                <Input value={workup.infertility_years ?? ''} onChange={(e) => setWorkup({ ...workup, infertility_years: e.target.value })} />
              </Field>
              <Field label="AMH" hint="Egg-reserve blood test">
                <Input value={workup.amh ?? ''} onChange={(e) => setWorkup({ ...workup, amh: e.target.value })} />
              </Field>
              <Field label="Follicle count" hint="Antral follicles seen on the scan">
                <Input value={workup.antral_follicle_count ?? ''} onChange={(e) => setWorkup({ ...workup, antral_follicle_count: e.target.value })} />
              </Field>
            </div>
            <Field label="Tubes and womb">
              <div className="grid gap-3 sm:grid-cols-2">
                <Input placeholder="Tubes, for example both open" value={workup.tubal_status || ''} onChange={(e) => setWorkup({ ...workup, tubal_status: e.target.value })} />
                <Input placeholder="Womb findings" value={workup.uterus_findings || ''} onChange={(e) => setWorkup({ ...workup, uterus_findings: e.target.value })} />
              </div>
            </Field>
            <Field label="Semen report">
              <Textarea value={workup.semen_summary || ''} onChange={(e) => setWorkup({ ...workup, semen_summary: e.target.value })} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Diagnosis">
                <Textarea value={workup.diagnosis || ''} onChange={(e) => setWorkup({ ...workup, diagnosis: e.target.value })} />
              </Field>
              <Field label="Agreed plan">
                <Textarea value={workup.treatment_plan || ''} onChange={(e) => setWorkup({ ...workup, treatment_plan: e.target.value })} />
              </Field>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Earlier pregnancies">
                <Input value={workup.prior_pregnancies ?? ''} onChange={(e) => setWorkup({ ...workup, prior_pregnancies: e.target.value })} />
              </Field>
              <Field label="Earlier treatment cycles">
                <Input value={workup.prior_cycles ?? ''} onChange={(e) => setWorkup({ ...workup, prior_cycles: e.target.value })} />
              </Field>
            </div>
            <Button onClick={saveWorkup}>Save assessment</Button>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle className="text-base">Start a treatment cycle</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <Field label="Treatment" hint="IVF and ICSI stay closed until the clinic is registered as Level 2 and the licence includes the lab.">
                <select className={selectClass} value={cycleType} onChange={(e) => setCycleType(e.target.value)}>
                  {cycleOptions.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                </select>
              </Field>
              <Field label="How this cycle is billed">
                <Choice
                  value={billingMode}
                  onChange={setBillingMode}
                  options={[
                    { value: 'package', label: 'Package', hint: 'One price, collected when the cycle starts' },
                    { value: 'itemised', label: 'Each visit billed separately', hint: 'Scans, procedures, and medicines as they happen' },
                  ]}
                />
              </Field>
              {billingMode === 'package' && (
                <Field label="Package" hint="The printed estimate keeps this price even if the billing choice changes later.">
                  <select className={selectClass} value={packageId} onChange={(e) => setPackageId(e.target.value)}>
                    <option value="">Choose a package</option>
                    {packages.map((pkg) => (
                      <option key={pkg.id} value={pkg.id}>{pkg.name} · {rupee(pkg.price)}</option>
                    ))}
                  </select>
                </Field>
              )}
              <Button onClick={startCycle} disabled={data.status !== 'open' || (billingMode === 'package' && !packageId)}>Start cycle</Button>
              {data.status !== 'open' && <p className="text-xs text-gray-500">Reopen the case to start a new cycle.</p>}
              <div className="space-y-2 border-t pt-3">
                {data.cycles.length === 0 && <p className="text-sm text-gray-500">No cycles yet.</p>}
                {data.cycles.map((cycle) => (
                  <Link key={cycle.id} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 hover:bg-gray-50" to={`/dashboard/art/cycles/${cycle.id}`}>
                    <div>
                      <p className="text-sm font-medium">{cycle.cycle_number}</p>
                      <p className="text-xs text-gray-500">{plain(cycle.cycle_type)}</p>
                    </div>
                    <Badge variant="outline">{plain(cycle.status)}</Badge>
                  </Link>
                ))}
              </div>
            </CardContent>
          </Card>

          <AppointmentsCard caseId={caseId} cycles={data.cycles} appointments={data.appointments || []} staff={staff} onChanged={load} />

          <Card>
            <CardHeader><CardTitle className="text-base">Consents</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-gray-500">Download a form filled with this case. Sign it on paper, file it, then record who signed. A procedure stays blocked until that record is here.</p>
              {data.consents.length === 0 && <p className="text-sm text-gray-500">No signed form recorded yet.</p>}
              {data.consents.map((row) => (
                <div key={row.id} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2">
                  <div>
                    <p className="text-sm font-medium">{CONSENT_PLAIN[row.form_code] || plain(row.form_code)}</p>
                    <p className="text-xs text-gray-500">Signed by {row.signed_by_name}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{row.withdrawn_at ? 'Withdrawn' : 'Active'}</Badge>
                    {!row.withdrawn_at && row.form_code !== 'withdrawal' && (
                      <Button variant="outline" size="sm" onClick={() => withdraw(row)}>Withdraw</Button>
                    )}
                  </div>
                </div>
              ))}
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Form">
                  <select className={selectClass} value={formCode} onChange={(e) => setFormCode(e.target.value)}>
                    {forms.map((form) => (
                      <option key={form.code} value={form.code}>{CONSENT_PLAIN[form.code] || form.label}</option>
                    ))}
                  </select>
                </Field>
                <Field label="Signed by" hint="Write this after the paper copy has been signed">
                  <Input value={signedBy} onChange={(e) => setSignedBy(e.target.value)} />
                </Field>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={downloadConsent}>Download for signing</Button>
                <Button onClick={addConsent} disabled={!signedBy.trim()}>Record signed copy</Button>
              </div>
              <p className="text-xs text-gray-500">The donor’s own consent is downloaded from the donor bank, where the donor’s name is kept.</p>
            </CardContent>
          </Card>

          <DocumentsCard caseId={caseId} documents={data.documents || []} onChanged={load} />

          <Card>
            <CardHeader><CardTitle className="text-base">Counsellor notes</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {data.notes.length === 0 && <p className="text-sm text-gray-500">No counselling note yet.</p>}
              {data.notes.map((row) => (
                <p key={row.id} className="rounded-md border px-3 py-2 text-sm">{row.note}</p>
              ))}
              <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="What was discussed" />
              <Button onClick={addNote} disabled={!note.trim()}>Save note</Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </Shell>
  );
}

const IUI_TYPES = ['iui_husband', 'iui_donor'];
const EGG_TYPES = ['ivf', 'icsi', 'freeze_all', 'oocyte_freeze'];
const FERT_TYPES = ['ivf', 'icsi', 'freeze_all'];
const TRANSFER_TYPES = ['ivf', 'icsi', 'fet'];
const LAB_TYPES = ['ivf', 'icsi', 'freeze_all', 'fet', 'oocyte_freeze', 'sperm_freeze'];
const NO_PREGNANCY_TYPES = ['freeze_all', 'oocyte_freeze', 'sperm_freeze'];
const TIMEOUT_KINDS = ['iui', 'opu', 'transfer'];
const PAY_METHODS = [
  { value: 'cash', label: 'Cash' },
  { value: 'card', label: 'Card' },
  { value: 'upi', label: 'UPI' },
  { value: 'bank_transfer', label: 'Bank transfer' },
];
const YES_NO = [
  { value: 'unknown', label: 'Not known yet' },
  { value: 'yes', label: 'Yes' },
  { value: 'no', label: 'No' },
];

function toYesNo(value) {
  if (value === true) return 'yes';
  if (value === false) return 'no';
  return 'unknown';
}

function fromYesNo(value) {
  if (value === 'yes') return true;
  if (value === 'no') return false;
  return null;
}

function numOrNull(value) {
  if (value === '' || value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isNaN(n) ? null : n;
}

function useStaff() {
  const [staff, setStaff] = useState({ me: null, staff: [] });
  useEffect(() => {
    axios.get('/api/art/staff').then((res) => setStaff(res.data)).catch(() => {});
  }, []);
  return staff;
}

function StaffSelect({ value, onChange, people, placeholder = 'Choose a person' }) {
  return (
    <select className={selectClass} value={value || ''} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}>
      <option value="">{placeholder}</option>
      {people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}
    </select>
  );
}

function appointmentKinds(cycleType) {
  const kinds = ['scan', 'counsellor', 'beta_hcg'];
  if (IUI_TYPES.includes(cycleType)) kinds.splice(1, 0, 'iui');
  if (EGG_TYPES.includes(cycleType)) kinds.splice(1, 0, 'opu');
  if (TRANSFER_TYPES.includes(cycleType)) kinds.splice(1, 0, 'transfer');
  return kinds;
}

function TimeoutForm({ appt, staff, onDone, setError }) {
  const [form, setForm] = useState({ patient_name: '', dob_confirmed: false, witness_id: null });
  const others = staff.staff.filter((p) => p.id !== staff.me);

  async function save() {
    try {
      await axios.post(`/api/art/appointments/${appt.id}/timeout`, form);
      setError('');
      onDone('Time-out recorded.');
    } catch (e) {
      setError(errMsg(e));
    }
  }

  return (
    <div className="space-y-3 rounded-md border border-amber-200 bg-amber-50 p-3">
      <p className="text-sm text-amber-900">Before the procedure, ask the woman to say her full name and date of birth. A second person watches.</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name she says">
          <Input value={form.patient_name} onChange={(e) => setForm({ ...form, patient_name: e.target.value })} />
        </Field>
        <Field label="Witness">
          <StaffSelect value={form.witness_id} onChange={(id) => setForm({ ...form, witness_id: id })} people={others} />
        </Field>
      </div>
      <label className="flex items-start gap-2 text-sm">
        <input className="mt-1" type="checkbox" checked={form.dob_confirmed} onChange={(e) => setForm({ ...form, dob_confirmed: e.target.checked })} />
        <span className="font-medium">Her date of birth matches the chart</span>
      </label>
      <Button size="sm" onClick={save} disabled={!form.patient_name.trim() || !form.dob_confirmed || !form.witness_id}>Record time-out</Button>
    </div>
  );
}

function AppointmentsCard({ caseId, cycles, fixedCycle, appointments, staff, onChanged }) {
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [openTimeout, setOpenTimeout] = useState(null);
  const openCycles = (cycles || []).filter((c) => !['cancelled', 'outcome'].includes(c.status));
  const [form, setForm] = useState({
    cycle_id: fixedCycle ? fixedCycle.id : '',
    kind: 'scan',
    scheduled_date: todayISO(),
    scheduled_time: '',
    room: '',
  });
  const chosenCycle = fixedCycle || openCycles.find((c) => String(c.id) === String(form.cycle_id));
  const kinds = chosenCycle ? appointmentKinds(chosenCycle.cycle_type) : ['scan', 'counsellor'];

  function done(message) {
    setInfo(message);
    setOpenTimeout(null);
    onChanged();
  }

  async function book() {
    try {
      await axios.post('/api/art/appointments', {
        case_id: Number(caseId),
        cycle_id: chosenCycle ? chosenCycle.id : null,
        kind: form.kind,
        scheduled_date: form.scheduled_date,
        scheduled_time: form.scheduled_time || null,
        room: form.room || null,
      });
      setError('');
      setForm({ ...form, scheduled_time: '', room: '' });
      done('Booked.');
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function act(appt, action) {
    try {
      await axios.post(`/api/art/appointments/${appt.id}/${action}`);
      setError('');
      done(action === 'complete' ? 'Marked as done.' : 'Booking cancelled.');
    } catch (e) {
      setError(errMsg(e));
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Bookings</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <Notice error={error} info={info} />
        {appointments.length === 0 && <Empty>Nothing booked yet.</Empty>}
        {appointments.map((appt) => {
          const needsTimeout = TIMEOUT_KINDS.includes(appt.kind);
          const open = appt.status === 'scheduled';
          return (
            <div key={appt.id} className="space-y-2 rounded-md border px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium">{plain(appt.kind)}</p>
                  <p className="text-xs text-gray-500">
                    {appt.scheduled_date}{appt.scheduled_time ? ` at ${appt.scheduled_time}` : ''} · {appt.room || 'Room not set'}
                    {needsTimeout ? ` · ${appt.timeout_done ? 'Time-out done' : 'Time-out still to do'}` : ''}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">{plain(appt.status)}</Badge>
                  {open && needsTimeout && !appt.timeout_done && (
                    <Button variant="outline" size="sm" onClick={() => setOpenTimeout(openTimeout === appt.id ? null : appt.id)}>Time-out</Button>
                  )}
                  {open && (!needsTimeout || appt.timeout_done) && (
                    <Button size="sm" onClick={() => act(appt, 'complete')}>Mark done</Button>
                  )}
                  {open && <Button variant="outline" size="sm" onClick={() => act(appt, 'cancel')}>Cancel</Button>}
                </div>
              </div>
              {openTimeout === appt.id && <TimeoutForm appt={appt} staff={staff} onDone={done} setError={setError} />}
            </div>
          );
        })}
        <div className="space-y-3 border-t pt-3">
          <div className="grid gap-3 sm:grid-cols-2">
            {!fixedCycle && (
              <Field label="Cycle" hint="IUI, egg collection, and transfer are booked on a cycle">
                <select className={selectClass} value={form.cycle_id} onChange={(e) => setForm({ ...form, cycle_id: e.target.value, kind: 'scan' })}>
                  <option value="">No cycle</option>
                  {openCycles.map((c) => <option key={c.id} value={c.id}>{c.cycle_number} · {plain(c.cycle_type)}</option>)}
                </select>
              </Field>
            )}
            <Field label="What is booked">
              <select className={selectClass} value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                {kinds.map((kind) => <option key={kind} value={kind}>{plain(kind)}</option>)}
              </select>
            </Field>
            <Field label="Date">
              <Input type="date" value={form.scheduled_date} onChange={(e) => setForm({ ...form, scheduled_date: e.target.value })} />
            </Field>
            <Field label="Time">
              <Input type="time" value={form.scheduled_time} onChange={(e) => setForm({ ...form, scheduled_time: e.target.value })} />
            </Field>
            <Field label="Room">
              <Input value={form.room} onChange={(e) => setForm({ ...form, room: e.target.value })} />
            </Field>
          </div>
          <Button onClick={book} disabled={!form.scheduled_date}>Book</Button>
        </div>
      </CardContent>
    </Card>
  );
}

function DetailsCard({ cycle, staff, onSaved, setError }) {
  const [form, setForm] = useState({ protocol: cycle.protocol || '', clinician_id: cycle.clinician_id, protocol_change_reason: '' });
  const changingProtocol = (cycle.protocol || '') !== form.protocol && cycle.protocol && cycle.status !== 'planned';

  async function save() {
    try {
      await axios.patch(`/api/art/cycles/${cycle.id}`, {
        protocol: form.protocol,
        clinician_id: form.clinician_id,
        protocol_change_reason: form.protocol_change_reason || null,
      });
      setError('');
      onSaved('Doctor and protocol saved.');
    } catch (e) {
      setError(errMsg(e));
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Doctor and protocol</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Treating doctor">
            <StaffSelect value={form.clinician_id} onChange={(id) => setForm({ ...form, clinician_id: id })} people={staff.staff} placeholder="No doctor assigned" />
          </Field>
          <Field label="Stimulation protocol" hint="For example antagonist, long agonist, or natural">
            <Input value={form.protocol} onChange={(e) => setForm({ ...form, protocol: e.target.value })} />
          </Field>
        </div>
        {changingProtocol && (
          <Field label="Why the protocol is changing">
            <Input value={form.protocol_change_reason} onChange={(e) => setForm({ ...form, protocol_change_reason: e.target.value })} />
          </Field>
        )}
        {cycle.protocol_change_reason && <p className="text-xs text-gray-500">Last protocol change: {cycle.protocol_change_reason}</p>}
        <Button onClick={save} disabled={changingProtocol && !form.protocol_change_reason.trim()}>Save</Button>
      </CardContent>
    </Card>
  );
}

function BillingCard({ cycle, closed, onSaved, setError }) {
  const [bills, setBills] = useState([]);
  const [services, setServices] = useState([]);
  const [packages, setPackages] = useState([]);
  const [payAmounts, setPayAmounts] = useState({});
  const [payMethod, setPayMethod] = useState('cash');
  const [charge, setCharge] = useState({ service_code: '', description: '', amount: '', kind: 'service' });
  const [mode, setMode] = useState({ open: false, package_template_id: '', reason: '', agreed_price: '' });
  const [cancel, setCancel] = useState({ open: false, reason: '', refund_method: 'cash' });

  const load = useCallback(async () => {
    try {
      const [b, s, p] = await Promise.all([
        axios.get(`/api/art/cycles/${cycle.id}/bills`),
        axios.get('/api/art/services'),
        axios.get('/api/art/packages'),
      ]);
      setBills(b.data);
      setServices(s.data.filter((row) => row.is_active));
      setPackages(p.data.filter((row) => row.is_active));
    } catch (e) {
      setError(errMsg(e));
    }
  }, [cycle.id, setError]);
  useEffect(() => { load(); }, [load]);

  async function run(fn, message) {
    try {
      await fn();
      setError('');
      await load();
      onSaved(message);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  const collect = (bill) => run(
    () => axios.post(`/api/art/bills/${bill.id}/payments`, { amount: Number(payAmounts[bill.id] || bill.balance), payment_method: payMethod }),
    'Payment collected.',
  );
  const postCharge = () => run(async () => {
    await axios.post(`/api/art/cycles/${cycle.id}/charges`, {
      service_code: charge.kind === 'service' ? (charge.service_code || null) : null,
      description: charge.description || null,
      amount: numOrNull(charge.amount),
      kind: charge.kind,
    });
    setCharge({ service_code: '', description: '', amount: '', kind: charge.kind });
  }, 'Charge added.');
  const switchMode = () => run(async () => {
    await axios.post(`/api/art/cycles/${cycle.id}/billing-mode`, {
      billing_mode: cycle.billing_mode === 'package' ? 'itemised' : 'package',
      reason: mode.reason,
      package_template_id: mode.package_template_id ? Number(mode.package_template_id) : null,
      agreed_price: numOrNull(mode.agreed_price),
    });
    setMode({ open: false, package_template_id: '', reason: '', agreed_price: '' });
  }, 'Billing changed.');
  const cancelCycle = () => run(async () => {
    await axios.post(`/api/art/cycles/${cycle.id}/cancel`, { reason: cancel.reason, refund_method: cancel.refund_method });
    setCancel({ open: false, reason: '', refund_method: 'cash' });
  }, 'Cycle cancelled. Unpaid bills were voided and any refund was posted.');

  const toPackage = cycle.billing_mode !== 'package';
  const canPostCharge = charge.kind === 'service' ? (charge.service_code || (charge.description && charge.amount)) : (charge.description && charge.amount);

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Bills and payments</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        {bills.length === 0 && <Empty>No bills on this cycle yet.</Empty>}
        {bills.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="py-2 pr-3 font-medium">Bill</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 text-right font-medium">Amount</th>
                  <th className="py-2 pr-3 text-right font-medium">Paid</th>
                  <th className="py-2 pr-3 text-right font-medium">Still due</th>
                  <th className="py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {bills.map((bill) => (
                  <tr key={bill.id} className="border-b last:border-0">
                    <td className="py-2 pr-3">
                      <p className="font-medium">{bill.bill_number}</p>
                      <p className="text-xs text-gray-500">{bill.bill_type === 'credit_note' ? 'Refund' : (bill.notes || '').split(' | ')[0]}</p>
                    </td>
                    <td className="py-2 pr-3">{plain(bill.status)}</td>
                    <td className="py-2 pr-3 text-right">{rupee(bill.total_amount)}</td>
                    <td className="py-2 pr-3 text-right">{rupee(bill.paid)}</td>
                    <td className="py-2 pr-3 text-right">{bill.bill_type === 'credit_note' ? '—' : rupee(bill.balance)}</td>
                    <td className="py-2">
                      {bill.bill_type === 'art' && ['pending', 'partial'].includes(bill.status) && bill.balance > 0 && (
                        <div className="flex items-center justify-end gap-2">
                          <Input
                            className="h-8 w-24"
                            value={payAmounts[bill.id] ?? ''}
                            placeholder={String(bill.balance)}
                            onChange={(e) => setPayAmounts({ ...payAmounts, [bill.id]: e.target.value })}
                            aria-label="Amount"
                          />
                          <Button size="sm" onClick={() => collect(bill)}>Collect</Button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {bills.some((b) => b.bill_type === 'art' && b.balance > 0 && ['pending', 'partial'].includes(b.status)) && (
          <Field label="Paid by" className="max-w-xs">
            <select className={selectClass} value={payMethod} onChange={(e) => setPayMethod(e.target.value)}>
              {PAY_METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
          </Field>
        )}

        {!closed && (
          <div className="space-y-3 border-t pt-3">
            <p className="text-sm font-medium text-gray-900">Add a charge</p>
            <Choice
              value={charge.kind}
              onChange={(kind) => setCharge({ ...charge, kind })}
              options={[
                { value: 'service', label: 'A service', hint: 'Scan, procedure, or lab test from the price list' },
                { value: 'medicine', label: 'A medicine', hint: cycle.includes_medicines ? 'Counts against the package medicine allowance' : 'Billed on its own' },
              ]}
            />
            <div className="grid gap-3 sm:grid-cols-3">
              {charge.kind === 'service' && (
                <Field label="Service">
                  <select className={selectClass} value={charge.service_code} onChange={(e) => setCharge({ ...charge, service_code: e.target.value })}>
                    <option value="">Something not on the list</option>
                    {services.map((row) => <option key={row.id} value={row.code}>{row.name} · {rupee(row.default_price)}</option>)}
                  </select>
                </Field>
              )}
              <Field label="Description" hint={charge.service_code ? 'Leave blank to use the service name' : ''}>
                <Input value={charge.description} onChange={(e) => setCharge({ ...charge, description: e.target.value })} />
              </Field>
              <Field label="Amount" hint={charge.service_code ? 'Leave blank to use the list price' : ''}>
                <Input value={charge.amount} onChange={(e) => setCharge({ ...charge, amount: e.target.value })} />
              </Field>
            </div>
            <Button variant="outline" onClick={postCharge} disabled={!canPostCharge}>Add charge</Button>
          </div>
        )}

        {!closed && (
          <div className="flex flex-wrap gap-2 border-t pt-3">
            <Button variant="outline" onClick={() => setMode({ ...mode, open: !mode.open })}>
              {toPackage ? 'Move to a package' : 'Bill each visit instead'}
            </Button>
            <Button variant="outline" onClick={() => setCancel({ ...cancel, open: !cancel.open })}>Cancel this cycle</Button>
          </div>
        )}
        {!closed && mode.open && (
          <div className="space-y-3 rounded-md border p-3">
            <p className="text-sm text-gray-600">
              {toPackage
                ? 'A package advance bill is raised. Unpaid visit bills that the package covers are voided. Paid ones stay paid.'
                : 'The unpaid package advance is voided and each visit already covered gets its own bill. This is not possible once the advance has been paid.'}
            </p>
            {toPackage && (
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Package">
                  <select className={selectClass} value={mode.package_template_id} onChange={(e) => setMode({ ...mode, package_template_id: e.target.value })}>
                    <option value="">Choose a package</option>
                    {packages.map((pkg) => <option key={pkg.id} value={pkg.id}>{pkg.name} · {rupee(pkg.price)}</option>)}
                  </select>
                </Field>
                <Field label="Agreed price" hint="Leave blank to use the package price">
                  <Input value={mode.agreed_price} onChange={(e) => setMode({ ...mode, agreed_price: e.target.value })} />
                </Field>
              </div>
            )}
            <Field label="Reason">
              <Input value={mode.reason} onChange={(e) => setMode({ ...mode, reason: e.target.value })} />
            </Field>
            <Button onClick={switchMode} disabled={!mode.reason.trim() || (toPackage && !mode.package_template_id)}>Change billing</Button>
          </div>
        )}
        {!closed && cancel.open && (
          <div className="space-y-3 rounded-md border border-red-200 bg-red-50 p-3">
            <p className="text-sm text-red-700">
              Unpaid bills are voided. For a package, the clinic keeps {rupee(cycle.estimate_snapshot?.cancel_keep_amount)} of what was paid and refunds the rest.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Reason">
                <Input value={cancel.reason} onChange={(e) => setCancel({ ...cancel, reason: e.target.value })} />
              </Field>
              <Field label="Refund paid by">
                <select className={selectClass} value={cancel.refund_method} onChange={(e) => setCancel({ ...cancel, refund_method: e.target.value })}>
                  {PAY_METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
                </select>
              </Field>
            </div>
            <Button onClick={cancelCycle} disabled={!cancel.reason.trim()}>Cancel cycle</Button>
          </div>
        )}
        {cycle.cancel_reason && <p className="text-sm text-gray-600">Cancelled: {cycle.cancel_reason}</p>}
      </CardContent>
    </Card>
  );
}

function StimulationCard({ cycle, closed, onSaved, setError }) {
  const blank = { name: '', dose: '', route: 'SC' };
  const nextDay = (cycle.stimulation.length ? Math.max(...cycle.stimulation.map((d) => d.day_number)) + 1 : 1);
  const [day, setDay] = useState({
    day_number: nextDay, drugs: [{ ...blank }], left: '', right: '',
    endometrium_mm: '', e2: '', lh: '', progesterone: '', notes: '',
  });
  const [trigger, setTrigger] = useState({ drug: '', trigger_at: '' });
  const rank = ['planned', 'stimulation', 'triggered'];
  const canMonitor = !closed && rank.includes(cycle.status);
  const sizes = (list) => (list && list.length ? list.join(', ') : '—');

  function setDrug(index, key, value) {
    setDay({ ...day, drugs: day.drugs.map((d, i) => (i === index ? { ...d, [key]: value } : d)) });
  }

  async function saveDay() {
    try {
      await axios.post(`/api/art/cycles/${cycle.id}/stimulation`, {
        day_number: Number(day.day_number),
        drugs: day.drugs.filter((d) => d.name.trim()),
        follicles_left: mmList(day.left),
        follicles_right: mmList(day.right),
        endometrium_mm: numOrNull(day.endometrium_mm),
        e2: numOrNull(day.e2),
        lh: numOrNull(day.lh),
        progesterone: numOrNull(day.progesterone),
        notes: day.notes || null,
      });
      setError('');
      setDay({
        day_number: Number(day.day_number) + 1, drugs: day.drugs, left: '', right: '',
        endometrium_mm: '', e2: '', lh: '', progesterone: '', notes: '',
      });
      onSaved('Monitoring day saved.');
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function saveTrigger() {
    try {
      await axios.post(`/api/art/cycles/${cycle.id}/trigger`, { drug: trigger.drug, trigger_at: trigger.trigger_at });
      setError('');
      onSaved('Trigger recorded. Egg collection is usually 34 to 36 hours later.');
    } catch (e) {
      setError(errMsg(e));
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Stimulation monitoring</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        {cycle.stimulation.length === 0 && <Empty>No monitoring day recorded yet.</Empty>}
        {cycle.stimulation.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="py-2 pr-3 font-medium">Day</th>
                  <th className="py-2 pr-3 font-medium">Medicine</th>
                  <th className="py-2 pr-3 font-medium">Left ovary (mm)</th>
                  <th className="py-2 pr-3 font-medium">Right ovary (mm)</th>
                  <th className="py-2 pr-3 font-medium">Lining (mm)</th>
                  <th className="py-2 pr-3 font-medium">E2</th>
                  <th className="py-2 pr-3 font-medium">LH</th>
                  <th className="py-2 font-medium">P4</th>
                </tr>
              </thead>
              <tbody>
                {cycle.stimulation.map((row) => (
                  <tr key={row.id} className="border-b last:border-0">
                    <td className="py-2 pr-3">{row.day_number}</td>
                    <td className="py-2 pr-3">{(row.drugs || []).map((d) => `${d.name || ''} ${d.dose || ''}`.trim()).join(', ') || '—'}</td>
                    <td className="py-2 pr-3">{sizes(row.follicles_left)}</td>
                    <td className="py-2 pr-3">{sizes(row.follicles_right)}</td>
                    <td className="py-2 pr-3">{row.endometrium_mm ?? '—'}</td>
                    <td className="py-2 pr-3">{row.e2 ?? '—'}</td>
                    <td className="py-2 pr-3">{row.lh ?? '—'}</td>
                    <td className="py-2">{row.progesterone ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {cycle.trigger_at && (
          <p className="rounded-md border px-3 py-2 text-sm">Trigger: {cycle.trigger_drug} on {cycle.trigger_at.replace('T', ' ').slice(0, 16)}</p>
        )}
        {canMonitor && (
          <div className="space-y-4 border-t pt-3">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Field label="Cycle day"><Input value={day.day_number} onChange={(e) => setDay({ ...day, day_number: e.target.value })} /></Field>
              <Field label="Womb lining" hint="Thickness in millimetres">
                <Input value={day.endometrium_mm} onChange={(e) => setDay({ ...day, endometrium_mm: e.target.value })} />
              </Field>
              <Field label="Left ovary follicles" hint="Sizes in mm, separated by commas">
                <Input value={day.left} onChange={(e) => setDay({ ...day, left: e.target.value })} />
              </Field>
              <Field label="Right ovary follicles" hint="Sizes in mm, separated by commas">
                <Input value={day.right} onChange={(e) => setDay({ ...day, right: e.target.value })} />
              </Field>
              <Field label="Estradiol (E2)"><Input value={day.e2} onChange={(e) => setDay({ ...day, e2: e.target.value })} /></Field>
              <Field label="LH"><Input value={day.lh} onChange={(e) => setDay({ ...day, lh: e.target.value })} /></Field>
              <Field label="Progesterone (P4)"><Input value={day.progesterone} onChange={(e) => setDay({ ...day, progesterone: e.target.value })} /></Field>
              <Field label="Notes"><Input value={day.notes} onChange={(e) => setDay({ ...day, notes: e.target.value })} /></Field>
            </div>
            <div className="space-y-2">
              <Label className="text-sm font-medium text-gray-700">Medicines given today</Label>
              {day.drugs.map((drug, index) => (
                // eslint-disable-next-line react/no-array-index-key
                <div key={index} className="grid gap-2 sm:grid-cols-3">
                  <Input placeholder="Medicine" value={drug.name} onChange={(e) => setDrug(index, 'name', e.target.value)} />
                  <Input placeholder="Dose, for example 150 IU" value={drug.dose} onChange={(e) => setDrug(index, 'dose', e.target.value)} />
                  <select className={selectClass} value={drug.route} onChange={(e) => setDrug(index, 'route', e.target.value)}>
                    <option value="SC">Injection under the skin</option>
                    <option value="IM">Injection into the muscle</option>
                    <option value="oral">By mouth</option>
                    <option value="vaginal">Vaginal</option>
                  </select>
                </div>
              ))}
              <Button variant="outline" size="sm" onClick={() => setDay({ ...day, drugs: [...day.drugs, { ...blank }] })}>Add another medicine</Button>
            </div>
            <Button onClick={saveDay}>Save this day</Button>
          </div>
        )}
        {canMonitor && cycle.cycle_type !== 'sperm_freeze' && (
          <div className="space-y-3 border-t pt-3">
            <p className="text-sm font-medium text-gray-900">Trigger injection</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Medicine and dose"><Input value={trigger.drug} onChange={(e) => setTrigger({ ...trigger, drug: e.target.value })} /></Field>
              <Field label="Given at"><Input type="datetime-local" value={trigger.trigger_at} onChange={(e) => setTrigger({ ...trigger, trigger_at: e.target.value })} /></Field>
            </div>
            <Button variant="outline" onClick={saveTrigger} disabled={!trigger.drug.trim() || !trigger.trigger_at}>Record trigger</Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function WitnessField({ value, onChange, staff, kind = 'lab' }) {
  const people = staff.staff.filter((p) => p.id !== staff.me && (kind === 'bank' ? p.can_witness_bank : p.can_witness_lab));
  return (
    <Field label="Witness" hint={people.length ? 'A second person checks the labels. You are recorded as the operator.' : 'No one else holds the witness permission yet.'}>
      <StaffSelect value={value} onChange={onChange} people={people} />
    </Field>
  );
}

function SpecimenRow({ row, cycle, staff, closed, onSaved, setError }) {
  const [panel, setPanel] = useState('');
  const [witnessId, setWitnessId] = useState(null);
  const [grade, setGrade] = useState({ day: '', grade: '', stage: '' });
  const [freeze, setFreeze] = useState({ tank: '', canister: '', cane: '', position: '', renewal_due: '', oncofertility: false });
  const [renewal, setRenewal] = useState({ renewal_due: row.renewal_due || '', oncofertility: row.oncofertility });
  const working = ['in_culture', 'thawed'].includes(row.disposition);
  const canTransfer = row.sample_type === 'embryo' && working && row.thaw_survived !== false && TRANSFER_TYPES.includes(cycle.cycle_type);

  async function post(path, body, message) {
    try {
      await axios.post(path, body);
      setError('');
      setPanel('');
      onSaved(message);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  const dispose = (disposition, extra = {}) => post(
    `/api/art/specimens/${row.id}/dispose`,
    { disposition, witness_id: witnessId, ...extra },
    disposition === 'freeze' ? 'Frozen and placed in storage.' : `Marked as ${plain(disposition === 'transfer' ? 'transferred' : 'discarded').toLowerCase()}.`,
  );
  const lastGrade = (row.grades || []).slice(-1)[0];

  return (
    <div className="space-y-2 rounded-md border px-3 py-2 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-medium">{row.code} · {plain(row.sample_type)}</p>
          <p className="text-xs text-gray-500">
            {lastGrade ? `Day ${lastGrade.day} grade ${lastGrade.grade}${lastGrade.stage ? ` (${lastGrade.stage})` : ''}` : 'Not graded yet'}
            {row.tank ? ` · Tank ${row.tank} / ${row.canister} / ${row.cane} / ${row.position}` : ''}
            {row.renewal_due ? ` · Renew by ${row.renewal_due}` : ''}
            {row.thaw_survived === false ? ' · Did not survive thawing' : ''}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{plain(row.disposition)}</Badge>
          {!closed && working && cycle.culture_open && <Button variant="outline" size="sm" onClick={() => setPanel(panel === 'grade' ? '' : 'grade')}>Grade</Button>}
          {!closed && row.disposition === 'in_culture' && <Button variant="outline" size="sm" onClick={() => setPanel(panel === 'freeze' ? '' : 'freeze')}>Freeze</Button>}
          {!closed && canTransfer && <Button variant="outline" size="sm" onClick={() => setPanel(panel === 'transfer' ? '' : 'transfer')}>Transfer</Button>}
          {!['discarded', 'transferred'].includes(row.disposition) && <Button variant="outline" size="sm" onClick={() => setPanel(panel === 'discard' ? '' : 'discard')}>Discard</Button>}
          {row.disposition === 'frozen' && <Button variant="outline" size="sm" onClick={() => setPanel(panel === 'renew' ? '' : 'renew')}>Storage renewal</Button>}
        </div>
      </div>
      {panel === 'grade' && (
        <div className="grid gap-3 rounded-md border p-3 sm:grid-cols-4">
          <Field label="Day"><Input value={grade.day} onChange={(e) => setGrade({ ...grade, day: e.target.value })} /></Field>
          <Field label="Grade"><Input placeholder="For example 4AA" value={grade.grade} onChange={(e) => setGrade({ ...grade, grade: e.target.value })} /></Field>
          <Field label="Stage"><Input placeholder="Cleavage or blastocyst" value={grade.stage} onChange={(e) => setGrade({ ...grade, stage: e.target.value })} /></Field>
          <div className="flex items-end">
            <Button size="sm" disabled={!grade.day || !grade.grade.trim()} onClick={() => post(`/api/art/specimens/${row.id}/grade`, { day: Number(grade.day), grade: grade.grade, stage: grade.stage || null }, 'Grade saved.')}>Save grade</Button>
          </div>
        </div>
      )}
      {panel === 'freeze' && (
        <div className="space-y-3 rounded-md border p-3">
          <div className="grid gap-3 sm:grid-cols-4">
            {['tank', 'canister', 'cane', 'position'].map((key) => (
              <Field key={key} label={key.charAt(0).toUpperCase() + key.slice(1)}>
                <Input value={freeze[key]} onChange={(e) => setFreeze({ ...freeze, [key]: e.target.value })} />
              </Field>
            ))}
            <Field label="Renew storage by"><Input type="date" value={freeze.renewal_due} onChange={(e) => setFreeze({ ...freeze, renewal_due: e.target.value })} /></Field>
            <WitnessField value={witnessId} onChange={setWitnessId} staff={staff} />
          </div>
          <label className="flex items-start gap-2">
            <input className="mt-1" type="checkbox" checked={freeze.oncofertility} onChange={(e) => setFreeze({ ...freeze, oncofertility: e.target.checked })} />
            <span>
              <span className="font-medium">Frozen before cancer treatment</span>
              <span className="block text-xs text-gray-500">Allows storage past 10 years with the required permission.</span>
            </span>
          </label>
          <Button
            size="sm"
            disabled={!witnessId || !['tank', 'canister', 'cane', 'position'].every((k) => freeze[k].trim())}
            onClick={() => dispose('freeze', { ...freeze, renewal_due: freeze.renewal_due || null })}
          >
            Freeze
          </Button>
        </div>
      )}
      {(panel === 'transfer' || panel === 'discard') && (
        <div className="space-y-3 rounded-md border p-3">
          <p className="text-gray-600">
            {panel === 'transfer'
              ? 'Mark this embryo as placed in the womb. The signed treatment consent must be on file.'
              : 'Discarded material cannot be restored. A signed discard form must be on file.'}
          </p>
          <div className="max-w-sm"><WitnessField value={witnessId} onChange={setWitnessId} staff={staff} /></div>
          <Button size="sm" disabled={!witnessId} onClick={() => dispose(panel)}>{panel === 'transfer' ? 'Mark transferred' : 'Discard'}</Button>
        </div>
      )}
      {panel === 'renew' && (
        <div className="space-y-3 rounded-md border p-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Renew storage until"><Input type="date" value={renewal.renewal_due} onChange={(e) => setRenewal({ ...renewal, renewal_due: e.target.value })} /></Field>
          </div>
          <label className="flex items-start gap-2">
            <input className="mt-1" type="checkbox" checked={Boolean(renewal.oncofertility)} onChange={(e) => setRenewal({ ...renewal, oncofertility: e.target.checked })} />
            <span className="font-medium">Frozen before cancer treatment</span>
          </label>
          <Button size="sm" disabled={!renewal.renewal_due} onClick={() => post(`/api/art/specimens/${row.id}/renew`, renewal, 'Storage renewed.')}>Save renewal</Button>
        </div>
      )}
    </div>
  );
}

function EmbryologyCard({ cycle, staff, closed, onSaved, setError }) {
  const [witnessId, setWitnessId] = useState(null);
  const [retrieval, setRetrieval] = useState({ follicles_aspirated: '', oocytes_retrieved: '', mature_mii: '', intermediate_mi: '', immature_gv: '' });
  const [fert, setFert] = useState({ method: cycle.cycle_type === 'icsi' ? 'icsi' : 'ivf', oocytes_inseminated: '', normally_fertilised: '', media_lots: '' });
  const [sampleType, setSampleType] = useState(cycle.cycle_type === 'oocyte_freeze' ? 'oocyte' : 'embryo');
  const [thaw, setThaw] = useState({ id: null, survived: true });
  const isMine = cycle.culture_operator_id === staff.me;
  const thawable = cycle.frozen_for_case.filter((s) => (cycle.cycle_type === 'fet' ? s.sample_type === 'embryo' : s.sample_type === 'oocyte'));
  const sampleOptions = cycle.cycle_type === 'sperm_freeze' ? ['sperm'] : ['embryo', 'oocyte', 'sperm'];

  async function post(path, body, message) {
    try {
      await axios.post(path, body);
      setError('');
      onSaved(message);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  const counts = (obj) => Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, Number(v || 0)]));

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Embryology</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-3 text-sm">
          <div className="rounded-md border px-3 py-2">
            <p className="text-gray-500">Eggs collected</p>
            <p className="font-medium">{cycle.retrieval_oocytes ?? '—'}</p>
            {cycle.retrieval_at && <p className="text-xs text-gray-500">MII {cycle.retrieval_mii ?? 0} · MI {cycle.retrieval_mi ?? 0} · GV {cycle.retrieval_gv ?? 0}</p>}
          </div>
          <div className="rounded-md border px-3 py-2">
            <p className="text-gray-500">How they were fertilised</p>
            <p className="font-medium">{cycle.fert_method ? plain(cycle.fert_method) : '—'}</p>
            {cycle.fert_at && <p className="text-xs text-gray-500">{cycle.fert_inseminated} inseminated</p>}
          </div>
          <div className="rounded-md border px-3 py-2"><p className="text-gray-500">Eggs that fertilised normally</p><p className="font-medium">{cycle.fert_normal ?? '—'}</p></div>
        </div>

        {!closed && (
          <div className="max-w-sm">
            <WitnessField value={witnessId} onChange={setWitnessId} staff={staff} />
          </div>
        )}

        {!closed && EGG_TYPES.includes(cycle.cycle_type) && !cycle.retrieval_at && (
          <div className="space-y-3 border-t pt-3">
            <p className="text-sm font-medium text-gray-900">Egg collection</p>
            {!cycle.trigger_at && <p className="text-sm text-gray-500">Record the trigger injection first.</p>}
            <div className="grid gap-3 sm:grid-cols-5">
              <Field label="Follicles drained"><Input value={retrieval.follicles_aspirated} onChange={(e) => setRetrieval({ ...retrieval, follicles_aspirated: e.target.value })} /></Field>
              <Field label="Eggs collected"><Input value={retrieval.oocytes_retrieved} onChange={(e) => setRetrieval({ ...retrieval, oocytes_retrieved: e.target.value })} /></Field>
              <Field label="Mature (MII)"><Input value={retrieval.mature_mii} onChange={(e) => setRetrieval({ ...retrieval, mature_mii: e.target.value })} /></Field>
              <Field label="MI"><Input value={retrieval.intermediate_mi} onChange={(e) => setRetrieval({ ...retrieval, intermediate_mi: e.target.value })} /></Field>
              <Field label="GV"><Input value={retrieval.immature_gv} onChange={(e) => setRetrieval({ ...retrieval, immature_gv: e.target.value })} /></Field>
            </div>
            <Button
              disabled={!witnessId || !cycle.trigger_at || retrieval.oocytes_retrieved === ''}
              onClick={() => post(`/api/art/cycles/${cycle.id}/retrieval`, { ...counts(retrieval), witness_id: witnessId }, 'Egg collection recorded.')}
            >
              Save egg collection
            </Button>
          </div>
        )}

        {!closed && FERT_TYPES.includes(cycle.cycle_type) && cycle.retrieval_at && !cycle.fert_at && (
          <div className="space-y-3 border-t pt-3">
            <p className="text-sm font-medium text-gray-900">Fertilisation</p>
            <Choice
              value={fert.method}
              onChange={(method) => setFert({ ...fert, method })}
              options={[
                { value: 'ivf', label: 'IVF', hint: 'Eggs and sperm placed together' },
                { value: 'icsi', label: 'ICSI', hint: 'Mature eggs only, one sperm each' },
              ]}
            />
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Eggs inseminated"><Input value={fert.oocytes_inseminated} onChange={(e) => setFert({ ...fert, oocytes_inseminated: e.target.value })} /></Field>
              <Field label="Fertilised normally (2PN)"><Input value={fert.normally_fertilised} onChange={(e) => setFert({ ...fert, normally_fertilised: e.target.value })} /></Field>
              <Field label="Media lot numbers" hint="Separated by commas"><Input value={fert.media_lots} onChange={(e) => setFert({ ...fert, media_lots: e.target.value })} /></Field>
            </div>
            <Button
              disabled={!witnessId || fert.oocytes_inseminated === ''}
              onClick={() => post(`/api/art/cycles/${cycle.id}/fertilisation`, {
                method: fert.method,
                oocytes_inseminated: Number(fert.oocytes_inseminated || 0),
                normally_fertilised: Number(fert.normally_fertilised || 0),
                media_lots: fert.media_lots.split(',').map((x) => x.trim()).filter(Boolean),
                witness_id: witnessId,
              }, 'Fertilisation recorded.')}
            >
              Save fertilisation
            </Button>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3">
          <p className="text-sm text-gray-600">
            Incubator worksheet is {cycle.culture_open ? `open${isMine ? ' on your bench' : ' on another bench'}` : 'closed'}.
            {' '}Only one patient’s worksheet can be open on a bench at a time.
          </p>
          {!closed && !cycle.culture_open && <Button variant="outline" onClick={() => post(`/api/art/cycles/${cycle.id}/culture/open`, {}, 'Worksheet opened.')}>Open worksheet</Button>}
          {cycle.culture_open && <Button variant="outline" onClick={() => post(`/api/art/cycles/${cycle.id}/culture/close`, {}, 'Worksheet closed.')}>Close worksheet</Button>}
        </div>

        {!closed && cycle.culture_open && cycle.cycle_type !== 'fet' && (
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Add to the worksheet" className="w-56">
              <select className={selectClass} value={sampleType} onChange={(e) => setSampleType(e.target.value)}>
                {sampleOptions.map((t) => <option key={t} value={t}>{plain(t)}</option>)}
              </select>
            </Field>
            <Button variant="outline" onClick={() => post(`/api/art/cycles/${cycle.id}/specimens`, { sample_type: sampleType }, 'Added to the worksheet.')}>Add</Button>
          </div>
        )}

        {cycle.specimens.length === 0 && <Empty>No eggs or embryos on this worksheet yet.</Empty>}
        {cycle.specimens.map((row) => (
          <SpecimenRow key={row.id} row={row} cycle={cycle} staff={staff} closed={closed} onSaved={onSaved} setError={setError} />
        ))}

        {!closed && ['fet', 'ivf', 'icsi'].includes(cycle.cycle_type) && thawable.length > 0 && (
          <div className="space-y-3 border-t pt-3">
            <p className="text-sm font-medium text-gray-900">{cycle.cycle_type === 'fet' ? 'Frozen embryos for this couple' : 'Frozen eggs for this woman'}</p>
            {thawable.map((row) => (
              <div key={row.id} className="flex flex-wrap items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
                <div>
                  <p className="font-medium">{row.code}</p>
                  <p className="text-xs text-gray-500">Tank {row.tank} / {row.canister} / {row.cane} / {row.position} · Frozen {row.storage_start || '—'}</p>
                </div>
                <Button variant="outline" size="sm" onClick={() => setThaw({ id: thaw.id === row.id ? null : row.id, survived: true })}>Thaw into this cycle</Button>
                {thaw.id === row.id && (
                  <div className="w-full space-y-3 rounded-md border p-3">
                    <Field label="Did it survive thawing?">
                      <Choice
                        value={thaw.survived ? 'yes' : 'no'}
                        onChange={(v) => setThaw({ ...thaw, survived: v === 'yes' })}
                        options={[{ value: 'yes', label: 'Survived' }, { value: 'no', label: 'Did not survive' }]}
                      />
                    </Field>
                    <Button
                      size="sm"
                      disabled={!witnessId}
                      onClick={() => post(`/api/art/specimens/${row.id}/thaw`, { into_cycle_id: cycle.id, survived: thaw.survived, witness_id: witnessId }, 'Thawed into this cycle.')}
                    >
                      Record thaw
                    </Button>
                    {!witnessId && <p className="text-xs text-gray-500">Choose the witness above first.</p>}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function OutcomeCard({ cycle, onSaved, setError }) {
  const [form, setForm] = useState({
    beta_hcg_value: cycle.beta_hcg_value ?? '',
    beta_hcg_positive: toYesNo(cycle.beta_hcg_positive),
    clinical_pregnancy: toYesNo(cycle.clinical_pregnancy),
    miscarriage: toYesNo(cycle.miscarriage),
    live_birth: toYesNo(cycle.live_birth),
    complication: cycle.complication || '',
    outcome_notes: cycle.outcome_notes || '',
  });
  const noPregnancy = NO_PREGNANCY_TYPES.includes(cycle.cycle_type);

  async function save() {
    const body = { complication: form.complication || null, outcome_notes: form.outcome_notes || null };
    if (!noPregnancy) {
      Object.assign(body, {
        beta_hcg_value: numOrNull(form.beta_hcg_value),
        beta_hcg_positive: fromYesNo(form.beta_hcg_positive),
        clinical_pregnancy: fromYesNo(form.clinical_pregnancy),
        miscarriage: fromYesNo(form.miscarriage),
        live_birth: fromYesNo(form.live_birth),
      });
    }
    try {
      await axios.post(`/api/art/cycles/${cycle.id}/outcome`, body);
      setError('');
      onSaved('Outcome saved. You can come back and add later results.');
    } catch (e) {
      setError(errMsg(e));
    }
  }

  const yesNo = (key, label, hint) => (
    <Field label={label} hint={hint}>
      <Choice value={form[key]} onChange={(v) => setForm({ ...form, [key]: v })} options={YES_NO} />
    </Field>
  );

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">{noPregnancy ? 'How the cycle ended' : 'Pregnancy result'}</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        {!noPregnancy && (
          <>
            <p className="text-sm text-gray-500">Results come in over weeks. Save what is known now and add the rest later.</p>
            <div className="grid gap-4 lg:grid-cols-2">
              <Field label="Pregnancy blood test (beta hCG)" hint="Value in mIU/mL">
                <Input value={form.beta_hcg_value} onChange={(e) => setForm({ ...form, beta_hcg_value: e.target.value })} />
              </Field>
              {yesNo('beta_hcg_positive', 'Blood test positive')}
              {yesNo('clinical_pregnancy', 'Pregnancy sac seen on the scan', 'This is the clinical pregnancy used in the results')}
              {yesNo('miscarriage', 'Miscarriage')}
              {yesNo('live_birth', 'Live birth')}
            </div>
          </>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Complication" hint="For example ovarian hyperstimulation or bleeding">
            <Input value={form.complication} onChange={(e) => setForm({ ...form, complication: e.target.value })} />
          </Field>
          <Field label="Notes"><Input value={form.outcome_notes} onChange={(e) => setForm({ ...form, outcome_notes: e.target.value })} /></Field>
        </div>
        <Button onClick={save}>Save result</Button>
      </CardContent>
    </Card>
  );
}

function CyclePage() {
  const { cycleId } = useParams();
  const [cycle, setCycle] = useState(null);
  const [centre, setCentre] = useState(null);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [version, setVersion] = useState(0);
  const staff = useStaff();

  const load = useCallback(async () => {
    try {
      const [cycleRes, centreRes] = await Promise.all([
        axios.get(`/api/art/cycles/${cycleId}`),
        axios.get('/api/art/centre'),
      ]);
      setCycle(cycleRes.data);
      setCentre(centreRes.data);
      setVersion((v) => v + 1);
    } catch (e) {
      setError(errMsg(e));
    }
  }, [cycleId]);
  useEffect(() => { load(); }, [load]);

  const saved = useCallback((message) => {
    setInfo(message);
    setError('');
    load();
  }, [load]);

  async function printEstimate() {
    try {
      await printPdfFromUrl(`/api/art/cycles/${cycleId}/estimate.pdf`);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  if (!cycle) {
    return <Shell title="Cycle"><Notice error={error} info={error ? '' : 'Loading the cycle…'} /></Shell>;
  }
  const snap = cycle.estimate_snapshot || {};
  const closed = ['cancelled', 'outcome'].includes(cycle.status);
  const showOutcome = cycle.status !== 'cancelled' && (
    cycle.status === 'outcome'
    || NO_PREGNANCY_TYPES.includes(cycle.cycle_type)
    || (IUI_TYPES.includes(cycle.cycle_type) && cycle.status === 'luteal')
    || (TRANSFER_TYPES.includes(cycle.cycle_type) && ['transfer', 'luteal'].includes(cycle.status))
    || (cycle.cycle_type === 'oi' && cycle.status !== 'planned')
  );

  return (
    <Shell
      title={cycle.cycle_number}
      description={`${plain(cycle.cycle_type)} · ${plain(cycle.status)}`}
      actions={(
        <>
          <Button variant="outline" asChild>
            <Link to={`/dashboard/art/cases/${cycle.case_id}`}>Back to case</Link>
          </Button>
          <Button variant="outline" onClick={printEstimate}>Print estimate</Button>
        </>
      )}
    >
      <Notice error={error} info={info} />
      <Card>
        <CardHeader><CardTitle className="text-base">What was agreed</CardTitle></CardHeader>
        <CardContent>
          <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 text-sm">
            <div><dt className="text-gray-500">Billing now</dt><dd className="font-medium">{plain(cycle.billing_mode)}</dd></div>
            <div><dt className="text-gray-500">Original estimate</dt><dd className="font-medium">{plain(snap.billing_mode)} · {rupee(snap.agreed_price)}</dd></div>
            <div><dt className="text-gray-500">Package</dt><dd className="font-medium">{snap.package_name || 'No package'}</dd></div>
            <div><dt className="text-gray-500">Included in the price</dt><dd className="font-medium">{(snap.included_service_codes || []).join(', ') || 'Nothing listed'}</dd></div>
            <div>
              <dt className="text-gray-500">Medicines</dt>
              <dd className="font-medium">
                {cycle.includes_medicines
                  ? `Included${cycle.medicine_limit ? `, ${rupee(cycle.medicine_consumed)} of ${rupee(cycle.medicine_limit)} used` : ''}`
                  : 'Billed separately'}
              </dd>
            </div>
            <div><dt className="text-gray-500">Kept if the cycle is cancelled</dt><dd className="font-medium">{rupee(snap.cancel_keep_amount)}</dd></div>
            {cycle.donor_code && (
              <div><dt className="text-gray-500">Donor code on this chart</dt><dd className="font-medium">{cycle.donor_code}</dd></div>
            )}
            {cycle.billing_mode_change_reason && (
              <div><dt className="text-gray-500">Why billing changed</dt><dd className="font-medium">{cycle.billing_mode_change_reason}</dd></div>
            )}
          </dl>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-2">
        {!closed && <DetailsCard key={`d${version}`} cycle={cycle} staff={staff} onSaved={saved} setError={setError} />}
        <AppointmentsCard caseId={cycle.case_id} fixedCycle={cycle} appointments={cycle.appointments} staff={staff} onChanged={load} />
      </div>

      {cycle.cycle_type !== 'sperm_freeze' && (
        <StimulationCard key={`s${version}`} cycle={cycle} closed={closed} onSaved={saved} setError={setError} />
      )}

      {LAB_TYPES.includes(cycle.cycle_type) && centre?.lab_enabled && (
        <EmbryologyCard cycle={cycle} staff={staff} closed={closed} onSaved={saved} setError={setError} />
      )}
      {LAB_TYPES.includes(cycle.cycle_type) && centre && !centre.lab_enabled && (
        <Card><CardContent className="pt-6 text-sm text-gray-500">The embryology lab stays closed until the clinic is registered as Level 2 and the licence includes the lab.</CardContent></Card>
      )}

      {showOutcome && <OutcomeCard key={`o${version}`} cycle={cycle} onSaved={saved} setError={setError} />}

      <BillingCard cycle={cycle} closed={closed} onSaved={saved} setError={setError} />
    </Shell>
  );
}

function CatalogPage() {
  const [services, setServices] = useState([]);
  const [packages, setPackages] = useState([]);
  const [error, setError] = useState('');
  const [service, setService] = useState({ code: '', name: '', default_price: '' });
  const [pkg, setPkg] = useState({
    name: '', price: '', included: '', includes_medicines: false, cancel_keep_amount: '0',
  });

  const load = useCallback(async () => {
    try {
      const [s, p] = await Promise.all([axios.get('/api/art/services'), axios.get('/api/art/packages')]);
      setServices(s.data);
      setPackages(p.data);
    } catch (e) {
      setError(errMsg(e));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function addService() {
    try {
      await axios.post('/api/art/services', {
        code: service.code, name: service.name, default_price: Number(service.default_price || 0),
      });
      setService({ code: '', name: '', default_price: '' });
      setError('');
      load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function addPackage() {
    try {
      await axios.post('/api/art/packages', {
        name: pkg.name,
        price: Number(pkg.price || 0),
        included_service_codes: pkg.included.split(',').map((c) => c.trim()).filter(Boolean),
        includes_medicines: pkg.includes_medicines,
        cancel_keep_amount: Number(pkg.cancel_keep_amount || 0),
      });
      setError('');
      load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  return (
    <Shell title="Prices" description="Services are what you bill. A package is one price that covers the service codes you list.">
      <Notice error={error} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Services</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {services.length === 0 && <Empty>No services yet. Add a scan or IUI price below.</Empty>}
            {services.length > 0 && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-500">
                    <th className="py-2 font-medium">Code</th>
                    <th className="py-2 font-medium">Name</th>
                    <th className="py-2 text-right font-medium">Price</th>
                  </tr>
                </thead>
                <tbody>
                  {services.map((row) => (
                    <tr key={row.id} className="border-b last:border-0">
                      <td className="py-2 pr-3 font-medium">{row.code}</td>
                      <td className="py-2 pr-3">{row.name}</td>
                      <td className="py-2 text-right">{rupee(row.default_price)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Code" hint="Short code used inside a package"><Input value={service.code} onChange={(e) => setService({ ...service, code: e.target.value })} /></Field>
              <Field label="Name"><Input value={service.name} onChange={(e) => setService({ ...service, name: e.target.value })} /></Field>
              <Field label="Price"><Input value={service.default_price} onChange={(e) => setService({ ...service, default_price: e.target.value })} /></Field>
            </div>
            <Button onClick={addService} disabled={!service.code || !service.name}>Add service</Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-base">Packages</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            {packages.length === 0 && <Empty>No packages yet.</Empty>}
            {packages.map((row) => (
              <div key={row.id} className="rounded-md border px-3 py-2 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-medium">{row.name}</p>
                  <p>{rupee(row.price)}</p>
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  Covers {(row.included_service_codes || []).join(', ') || 'no listed services'}.
                  {' '}{row.includes_medicines ? 'Medicines are included.' : 'Medicines are billed separately.'}
                  {' '}If cancelled, the clinic keeps {rupee(row.cancel_keep_amount)}.
                </p>
              </div>
            ))}
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Package name"><Input value={pkg.name} onChange={(e) => setPkg({ ...pkg, name: e.target.value })} /></Field>
              <Field label="Package price"><Input value={pkg.price} onChange={(e) => setPkg({ ...pkg, price: e.target.value })} /></Field>
            </div>
            <Field label="Services included" hint="Codes from the list on the left, separated by commas. Example: SCAN, IUI">
              <Input value={pkg.included} onChange={(e) => setPkg({ ...pkg, included: e.target.value })} />
            </Field>
            <label className="flex items-start gap-2 text-sm">
              <input className="mt-1" type="checkbox" checked={pkg.includes_medicines} onChange={(e) => setPkg({ ...pkg, includes_medicines: e.target.checked })} />
              <span>
                <span className="font-medium">Include stimulation medicines in this price</span>
                <span className="block text-xs text-gray-500">Leave this off to bill medicines from the pharmacy as they are dispensed.</span>
              </span>
            </label>
            <Field label="Amount kept if the patient cancels" hint="The rest of what they already paid is refunded">
              <Input value={pkg.cancel_keep_amount} onChange={(e) => setPkg({ ...pkg, cancel_keep_amount: e.target.value })} />
            </Field>
            <Button onClick={addPackage} disabled={!pkg.name}>Add package</Button>
          </CardContent>
        </Card>
      </div>
    </Shell>
  );
}

async function downloadFile(path, filename, params) {
  const res = await axios.get(path, { responseType: 'blob', params });
  const url = URL.createObjectURL(res.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function DocumentsCard({ caseId, documents, onChanged }) {
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [name, setName] = useState('');
  const [type, setType] = useState('report');
  const [file, setFile] = useState(null);
  const [inputKey, setInputKey] = useState(0);

  async function upload() {
    const body = new FormData();
    body.append('document_name', name);
    body.append('document_type', type);
    body.append('file', file);
    try {
      await axios.post(`/api/art/cases/${caseId}/documents`, body);
      setName('');
      setFile(null);
      setInputKey((k) => k + 1);
      setError('');
      setInfo('Uploaded.');
      onChanged();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function open(row) {
    try {
      await downloadFile(`/api/art/documents/${row.id}/download`, row.file_name);
    } catch (e) {
      setError(await errorFromBlob(e));
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle className="text-base">Reports and scans</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <Notice error={error} info={info} />
        {documents.length === 0 && <p className="text-sm text-gray-500">Nothing uploaded yet.</p>}
        {documents.map((row) => (
          <div key={row.id} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{row.document_name}</p>
              <p className="text-xs text-gray-500">{plain(row.document_type)} · {(row.created_at || '').slice(0, 10)}</p>
            </div>
            <Button variant="outline" size="sm" onClick={() => open(row)}>Download</Button>
          </div>
        ))}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="For example AMH report" /></Field>
          <Field label="Type">
            <select className={selectClass} value={type} onChange={(e) => setType(e.target.value)}>
              <option value="report">Lab report</option>
              <option value="scan">Scan</option>
              <option value="consent">Signed consent</option>
              <option value="id_proof">Identity proof</option>
              <option value="other">Other</option>
            </select>
          </Field>
        </div>
        <Field label="File" hint="PDF, image, Word, or text. Up to 10 MB.">
          <Input key={inputKey} type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </Field>
        <Button onClick={upload} disabled={!name.trim() || !file}>Upload</Button>
      </CardContent>
    </Card>
  );
}

const SCREEN_KEYS = [
  { key: 'hiv', label: 'HIV' },
  { key: 'hbsag', label: 'Hepatitis B (HBsAg)' },
  { key: 'hcv', label: 'Hepatitis C' },
  { key: 'vdrl', label: 'Syphilis (VDRL)' },
];
const SCREEN_VALUES = [
  { value: 'pending', label: 'Result awaited' },
  { value: 'non_reactive', label: 'Non-reactive' },
  { value: 'reactive', label: 'Reactive' },
];

function DonorRow({ row, onSaved, setError }) {
  const [panel, setPanel] = useState('');
  const [screening, setScreening] = useState(() => Object.fromEntries(SCREEN_KEYS.map(({ key }) => [key, row.screening?.[key] || 'pending'])));
  const [insurance, setInsurance] = useState({ policy_no: row.insurance_policy_no || '', valid_until: row.insurance_valid_until || '', amount: row.insurance_amount ?? '' });
  const [count, setCount] = useState(row.oocytes_retrieved ?? '');
  const [straw, setStraw] = useState({ sample_code: '', tank: '', canister: '', cane: '', position: '' });

  async function post(path, body, message) {
    try {
      await axios.post(path, body);
      setError('');
      setPanel('');
      onSaved(message);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function consentForm() {
    try {
      await downloadPdf(`/api/art/donors/${row.id}/consent-form.pdf`, `${row.donor_code}-consent.pdf`);
      setError('');
    } catch (e) {
      setError(await errorFromBlob(e));
    }
  }

  const toggle = (name) => setPanel(panel === name ? '' : name);
  const checklist = [
    { done: row.screening_complete, label: 'Infection screen clear' },
    ...(row.donor_type === 'oocyte' ? [{ done: row.insurance_on_file, label: '12 months of insurance' }] : []),
  ];

  return (
    <div className="space-y-2 rounded-md border px-3 py-2 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-medium">{row.legal_name}</p>
          <p className="text-xs text-gray-500">
            {row.donor_code} · {plain(row.donor_type)} · {row.phone || 'No phone'}
            {row.over_intended_cap ? ` · ${row.oocytes_retrieved} eggs collected, more than the intended 7` : ''}
          </p>
          <p className="text-xs text-gray-500">{checklist.map((c) => `${c.done ? '✓' : '○'} ${c.label}`).join(' · ')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{plain(row.status)}</Badge>
          <Button variant="outline" size="sm" onClick={() => toggle('screen')}>Screening</Button>
          {row.donor_type === 'oocyte' && <Button variant="outline" size="sm" onClick={() => toggle('insurance')}>Insurance</Button>}
          {row.status !== 'cleared' && <Button size="sm" onClick={() => post(`/api/art/donors/${row.id}/clear`, {}, 'Donor cleared to use.')}>Clear to use</Button>}
          {row.status === 'cleared' && <Button variant="outline" size="sm" onClick={() => toggle('store')}>Store a straw</Button>}
          {row.donor_type === 'oocyte' && <Button variant="outline" size="sm" onClick={() => toggle('count')}>Eggs collected</Button>}
          <Button variant="outline" size="sm" onClick={consentForm}>Consent form</Button>
        </div>
      </div>
      {panel === 'screen' && (
        <div className="space-y-3 rounded-md border p-3">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {SCREEN_KEYS.map(({ key, label }) => (
              <Field key={key} label={label}>
                <select className={selectClass} value={screening[key]} onChange={(e) => setScreening({ ...screening, [key]: e.target.value })}>
                  {SCREEN_VALUES.map((v) => <option key={v.value} value={v.value}>{v.label}</option>)}
                </select>
              </Field>
            ))}
          </div>
          <p className="text-xs text-gray-500">If a cleared donor gets a reactive or awaited result, they go back to screening and their straws cannot be issued.</p>
          <Button size="sm" onClick={() => post(`/api/art/donors/${row.id}/screening`, screening, 'Screening saved.')}>Save screening</Button>
        </div>
      )}
      {panel === 'insurance' && (
        <div className="space-y-3 rounded-md border p-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Policy number"><Input value={insurance.policy_no} onChange={(e) => setInsurance({ ...insurance, policy_no: e.target.value })} /></Field>
            <Field label="Valid until" hint="At least 12 months from today"><Input type="date" value={insurance.valid_until} onChange={(e) => setInsurance({ ...insurance, valid_until: e.target.value })} /></Field>
            <Field label="Cover amount"><Input value={insurance.amount} onChange={(e) => setInsurance({ ...insurance, amount: e.target.value })} /></Field>
          </div>
          <Button
            size="sm"
            disabled={!insurance.policy_no.trim() || !insurance.valid_until || insurance.amount === ''}
            onClick={() => post(`/api/art/donors/${row.id}/insurance`, { ...insurance, amount: Number(insurance.amount) }, 'Insurance saved.')}
          >
            Save insurance
          </Button>
        </div>
      )}
      {panel === 'count' && (
        <div className="flex flex-wrap items-end gap-3 rounded-md border p-3">
          <Field label="Eggs collected from this donor" hint="The intended number is not more than 7. The real count is still recorded." className="w-72">
            <Input value={count} onChange={(e) => setCount(e.target.value)} />
          </Field>
          <Button size="sm" disabled={count === ''} onClick={() => post(`/api/art/donors/${row.id}/retrieval`, { oocytes_retrieved: Number(count) }, 'Egg count saved.')}>Save</Button>
        </div>
      )}
      {panel === 'store' && (
        <div className="space-y-3 rounded-md border p-3">
          <div className="grid gap-3 sm:grid-cols-5">
            <Field label="Straw code"><Input value={straw.sample_code} onChange={(e) => setStraw({ ...straw, sample_code: e.target.value })} /></Field>
            {['tank', 'canister', 'cane', 'position'].map((key) => (
              <Field key={key} label={key.charAt(0).toUpperCase() + key.slice(1)}>
                <Input value={straw[key]} onChange={(e) => setStraw({ ...straw, [key]: e.target.value })} />
              </Field>
            ))}
          </div>
          <Button size="sm" disabled={!straw.sample_code.trim()} onClick={() => post('/api/art/bank/units', { donor_id: row.id, ...straw }, 'Straw stored.')}>Store straw</Button>
        </div>
      )}
    </div>
  );
}

function IssueForm({ unit, staff, onSaved, setError }) {
  const [destination, setDestination] = useState('internal');
  const [cases, setCases] = useState([]);
  const [caseId, setCaseId] = useState('');
  const [cycles, setCycles] = useState([]);
  const [cycleId, setCycleId] = useState('');
  const [clinic, setClinic] = useState('');
  const [witnessId, setWitnessId] = useState(null);
  const fits = unit.sample_type === 'oocyte' ? ['ivf', 'icsi'] : ['iui_donor', 'ivf', 'icsi'];

  useEffect(() => {
    axios.get('/api/art/cases').then((res) => setCases(res.data.filter((c) => c.status === 'open'))).catch(() => {});
  }, []);
  useEffect(() => {
    setCycleId('');
    if (!caseId) { setCycles([]); return; }
    axios.get(`/api/art/cases/${caseId}`)
      .then((res) => setCycles(res.data.cycles.filter((c) => fits.includes(c.cycle_type) && !['cancelled', 'outcome'].includes(c.status))))
      .catch((e) => setError(errMsg(e)));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  async function issue() {
    try {
      await axios.post(`/api/art/bank/units/${unit.id}/issue`, {
        destination,
        case_id: destination === 'internal' ? Number(caseId) : null,
        cycle_id: destination === 'internal' ? Number(cycleId) : null,
        external_clinic_name: destination === 'external' ? clinic : null,
        witness_id: witnessId,
      });
      setError('');
      onSaved(destination === 'internal' ? 'Issued. The cycle now shows the donor code.' : 'Sent to the outside clinic.');
    } catch (e) {
      setError(errMsg(e));
    }
  }

  const ready = witnessId && (destination === 'internal' ? caseId && cycleId : clinic.trim());
  return (
    <div className="space-y-3 rounded-md border p-3">
      <Choice
        value={destination}
        onChange={setDestination}
        options={[
          { value: 'internal', label: 'A patient here', hint: 'The cycle chart shows only the donor code' },
          { value: 'external', label: 'Another registered clinic', hint: 'Sent out of this bank' },
        ]}
      />
      {destination === 'internal' ? (
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Case">
            <select className={selectClass} value={caseId} onChange={(e) => setCaseId(e.target.value)}>
              <option value="">Choose a case</option>
              {cases.map((c) => <option key={c.id} value={c.id}>{c.case_number} · {c.woman_name}</option>)}
            </select>
          </Field>
          <Field label="Cycle" hint={unit.sample_type === 'oocyte' ? 'Donor eggs go to an IVF or ICSI cycle' : 'Donor sperm goes to a donor IUI, IVF, or ICSI cycle'}>
            <select className={selectClass} value={cycleId} onChange={(e) => setCycleId(e.target.value)} disabled={!caseId}>
              <option value="">Choose a cycle</option>
              {cycles.map((c) => <option key={c.id} value={c.id}>{c.cycle_number} · {plain(c.cycle_type)}</option>)}
            </select>
          </Field>
        </div>
      ) : (
        <Field label="Receiving clinic"><Input value={clinic} onChange={(e) => setClinic(e.target.value)} /></Field>
      )}
      <div className="max-w-sm"><WitnessField value={witnessId} onChange={setWitnessId} staff={staff} kind="bank" /></div>
      <Button size="sm" disabled={!ready} onClick={issue}>Issue straw</Button>
    </div>
  );
}

function BankPage() {
  const [codes, setCodes] = useState([]);
  const [identity, setIdentity] = useState(null);
  const [units, setUnits] = useState(null);
  const [partners, setPartners] = useState([]);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [form, setForm] = useState({ donor_type: 'oocyte', legal_name: '', phone: '', address: '', date_of_birth: '' });
  const [issuing, setIssuing] = useState(null);
  const [partner, setPartner] = useState({ name: '', registration_no: '', city: '', phone: '' });
  const [receive, setReceive] = useState({
    partner_bank_id: '', donor_code: '', sample_code: '', sample_type: 'sperm', tank: '', canister: '', cane: '', position: '', witness_id: null,
  });
  const staff = useStaff();

  const load = useCallback(async () => {
    try {
      const [res, partnerRes] = await Promise.all([axios.get('/api/art/donors/codes'), axios.get('/api/art/partner-banks')]);
      setCodes(res.data);
      setPartners(partnerRes.data);
      const optional = async (path, set) => {
        try {
          set((await axios.get(path)).data);
        } catch (e) {
          if (e?.response?.status === 403) set(null);
          else throw e;
        }
      };
      await optional('/api/art/donors', setIdentity);
      await optional('/api/art/bank/units', setUnits);
    } catch (e) {
      setError(errMsg(e));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const saved = useCallback((message) => {
    setInfo(message);
    setError('');
    setIssuing(null);
    load();
  }, [load]);

  async function post(path, body, message, reset) {
    try {
      await axios.post(path, body);
      if (reset) reset();
      saved(message);
    } catch (e) {
      setError(errMsg(e));
    }
  }

  const addDonor = () => post('/api/art/donors', {
    ...form, date_of_birth: form.date_of_birth || null, address: form.address || null, phone: form.phone || null,
  }, 'Donor registered. Record the screening next.', () => setForm({ donor_type: 'oocyte', legal_name: '', phone: '', address: '', date_of_birth: '' }));

  return (
    <Shell
      title="Donor bank"
      description="The patient chart shows a donor code only. The donor’s name and phone stay in the bank file."
    >
      <Notice error={error} info={info} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Codes used on patient charts</CardTitle></CardHeader>
          <CardContent>
            {codes.length === 0 && <Empty>No donors registered.</Empty>}
            {codes.length > 0 && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-500">
                    <th className="py-2 font-medium">Code</th>
                    <th className="py-2 font-medium">Donates</th>
                    <th className="py-2 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {codes.map((row) => (
                    <tr key={row.id} className="border-b last:border-0">
                      <td className="py-2 font-medium">{row.donor_code}</td>
                      <td className="py-2">{plain(row.donor_type)}</td>
                      <td className="py-2">{plain(row.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {identity === null && (
              <p className="mt-3 text-xs text-gray-500">Names are hidden for this login. Bank staff can open the identity file.</p>
            )}
          </CardContent>
        </Card>
        {identity && (
          <Card>
            <CardHeader><CardTitle className="text-base">Register a donor</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <Field label="What they donate">
                <Choice
                  value={form.donor_type}
                  onChange={(value) => setForm({ ...form, donor_type: value })}
                  options={[
                    { value: 'oocyte', label: 'Eggs', hint: 'Needs 12 months of insurance before they can be cleared' },
                    { value: 'sperm', label: 'Sperm', hint: 'Cleared after the infection screen' },
                  ]}
                />
              </Field>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Full legal name"><Input value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} /></Field>
                <Field label="Date of birth"><Input type="date" value={form.date_of_birth} onChange={(e) => setForm({ ...form, date_of_birth: e.target.value })} /></Field>
                <Field label="Phone"><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
                <Field label="Address"><Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></Field>
              </div>
              <Button onClick={addDonor} disabled={!form.legal_name.trim()}>Register donor</Button>
            </CardContent>
          </Card>
        )}
      </div>

      {identity && (
        <Card>
          <CardHeader><CardTitle className="text-base">Bank identity file</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {identity.length === 0 && <Empty>No donors registered.</Empty>}
            {identity.map((row) => <DonorRow key={row.id} row={row} onSaved={saved} setError={setError} />)}
          </CardContent>
        </Card>
      )}

      {units && (
        <Card>
          <CardHeader><CardTitle className="text-base">Straws in the bank</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {units.length === 0 && <Empty>No straws stored yet.</Empty>}
            {units.map((unit) => (
              <div key={unit.id} className="space-y-2 rounded-md border px-3 py-2 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-medium">{unit.sample_code} · {plain(unit.sample_type)} · Donor {unit.donor_code}</p>
                    <p className="text-xs text-gray-500">
                      {unit.tank ? `Tank ${unit.tank} / ${unit.canister || '—'} / ${unit.cane || '—'} / ${unit.position || '—'}` : 'Location not recorded'}
                      {unit.partner_bank ? ` · From ${unit.partner_bank}` : ''}
                      {unit.case_number ? ` · Issued to ${unit.case_number}` : ''}
                      {unit.external_clinic_name ? ` · Sent to ${unit.external_clinic_name}` : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{plain(unit.status)}</Badge>
                    {unit.status === 'stored' && (
                      <Button variant="outline" size="sm" onClick={() => setIssuing(issuing === unit.id ? null : unit.id)}>Issue</Button>
                    )}
                  </div>
                </div>
                {issuing === unit.id && <IssueForm unit={unit} staff={staff} onSaved={saved} setError={setError} />}
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {units && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader><CardTitle className="text-base">Receive from an outside bank</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {partners.length === 0 && <p className="text-sm text-gray-500">Add the outside bank first.</p>}
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="From">
                  <select className={selectClass} value={receive.partner_bank_id} onChange={(e) => setReceive({ ...receive, partner_bank_id: e.target.value })}>
                    <option value="">Choose a bank</option>
                    {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </Field>
                <Field label="Sample">
                  <select className={selectClass} value={receive.sample_type} onChange={(e) => setReceive({ ...receive, sample_type: e.target.value })}>
                    <option value="sperm">Sperm</option>
                    <option value="oocyte">Eggs</option>
                  </select>
                </Field>
                <Field label="Their donor code"><Input value={receive.donor_code} onChange={(e) => setReceive({ ...receive, donor_code: e.target.value })} /></Field>
                <Field label="Straw code"><Input value={receive.sample_code} onChange={(e) => setReceive({ ...receive, sample_code: e.target.value })} /></Field>
                {['tank', 'canister', 'cane', 'position'].map((key) => (
                  <Field key={key} label={key.charAt(0).toUpperCase() + key.slice(1)}>
                    <Input value={receive[key]} onChange={(e) => setReceive({ ...receive, [key]: e.target.value })} />
                  </Field>
                ))}
              </div>
              <p className="text-xs text-gray-500">The straw is stored here. Issue it to a cycle from the list above.</p>
              <div className="max-w-sm">
                <WitnessField value={receive.witness_id} onChange={(id) => setReceive({ ...receive, witness_id: id })} staff={staff} kind="bank" />
              </div>
              <Button
                disabled={!receive.partner_bank_id || !receive.donor_code.trim() || !receive.sample_code.trim() || !receive.witness_id}
                onClick={() => post('/api/art/bank/receive', { ...receive, partner_bank_id: Number(receive.partner_bank_id) }, 'Received and stored.', () => setReceive({
                  ...receive, donor_code: '', sample_code: '', position: '',
                }))}
              >
                Receive
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-base">Outside banks</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {partners.length === 0 && <Empty>No outside banks yet.</Empty>}
              {partners.map((p) => (
                <div key={p.id} className="rounded-md border px-3 py-2 text-sm">
                  <p className="font-medium">{p.name}</p>
                  <p className="text-xs text-gray-500">{p.registration_no || 'Registration not recorded'}{p.city ? ` · ${p.city}` : ''}</p>
                </div>
              ))}
              {identity && (
                <>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Field label="Bank name"><Input value={partner.name} onChange={(e) => setPartner({ ...partner, name: e.target.value })} /></Field>
                    <Field label="Registration number"><Input value={partner.registration_no} onChange={(e) => setPartner({ ...partner, registration_no: e.target.value })} /></Field>
                    <Field label="City"><Input value={partner.city} onChange={(e) => setPartner({ ...partner, city: e.target.value })} /></Field>
                    <Field label="Phone"><Input value={partner.phone} onChange={(e) => setPartner({ ...partner, phone: e.target.value })} /></Field>
                  </div>
                  <Button variant="outline" disabled={!partner.name.trim()} onClick={() => post('/api/art/partner-banks', partner, 'Outside bank added.', () => setPartner({ name: '', registration_no: '', city: '', phone: '' }))}>Add outside bank</Button>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </Shell>
  );
}

function CryoPage() {
  const [rows, setRows] = useState([]);
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [tank, setTank] = useState('');
  const [log, setLog] = useState({ tank_name: '', nitrogen_level: 'full', temperature_c: '', alarm: false });

  const load = useCallback(async () => {
    try {
      const [inv, tl] = await Promise.all([axios.get('/api/art/cryo/inventory'), axios.get('/api/art/cryo/tank-logs')]);
      setRows(inv.data);
      setLogs(tl.data);
      setError('');
    } catch (e) {
      setError(errMsg(e));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function saveLog() {
    try {
      await axios.post('/api/art/cryo/tank-log', { ...log, temperature_c: numOrNull(log.temperature_c) });
      setLog({ ...log, temperature_c: '', alarm: false });
      setInfo('Tank check recorded.');
      load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  const tanks = [...new Set(rows.map((r) => r.tank || 'No tank'))];
  const shown = rows.filter((r) => !tank || (r.tank || 'No tank') === tank);

  return (
    <Shell title="Cryo storage" description="Everything in the tanks, where it sits, and when storage must be renewed. Bank straws show the donor code only.">
      <Notice error={error} info={info} />
      <Card>
        <CardHeader><CardTitle className="text-base">What is in storage</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          <Field label="Tank" className="max-w-xs">
            <select className={selectClass} value={tank} onChange={(e) => setTank(e.target.value)}>
              <option value="">All tanks</option>
              {tanks.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          {shown.length === 0 && <Empty>Nothing is in storage.</Empty>}
          {shown.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-500">
                    <th className="py-2 pr-3 font-medium">Code</th>
                    <th className="py-2 pr-3 font-medium">What</th>
                    <th className="py-2 pr-3 font-medium">Belongs to</th>
                    <th className="py-2 pr-3 font-medium">Tank / canister / cane / position</th>
                    <th className="py-2 font-medium">Renew by</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((r) => (
                    <tr key={`${r.kind}-${r.id}`} className="border-b last:border-0">
                      <td className="py-2 pr-3 font-medium">{r.code}</td>
                      <td className="py-2 pr-3">{plain(r.sample_type)}</td>
                      <td className="py-2 pr-3">
                        {r.kind === 'patient'
                          ? <Link className="text-blue-700" to={`/dashboard/art/cases/${r.case_id}`}>{r.name} · {r.case_number}</Link>
                          : `Bank · donor ${r.donor_code}`}
                      </td>
                      <td className="py-2 pr-3">{[r.tank, r.canister, r.cane, r.position].map((x) => x || '—').join(' / ')}</td>
                      <td className={`py-2 ${r.overdue ? 'font-medium text-red-700' : ''}`}>
                        {r.kind === 'patient' ? (r.renewal_due || 'Not set') : '—'}
                        {r.overdue ? ' (overdue)' : ''}
                        {r.oncofertility ? ' · Cancer treatment' : ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-base">Tank checks</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-4">
            <Field label="Tank"><Input value={log.tank_name} onChange={(e) => setLog({ ...log, tank_name: e.target.value })} /></Field>
            <Field label="Nitrogen level">
              <select className={selectClass} value={log.nitrogen_level} onChange={(e) => setLog({ ...log, nitrogen_level: e.target.value })}>
                <option value="full">Full</option>
                <option value="adequate">Adequate</option>
                <option value="low">Low, needs topping up</option>
              </select>
            </Field>
            <Field label="Temperature (°C)"><Input value={log.temperature_c} onChange={(e) => setLog({ ...log, temperature_c: e.target.value })} /></Field>
            <label className="flex items-end gap-2 pb-2 text-sm">
              <input type="checkbox" checked={log.alarm} onChange={(e) => setLog({ ...log, alarm: e.target.checked })} />
              <span className="font-medium">Alarm went off</span>
            </label>
          </div>
          <Button onClick={saveLog} disabled={!log.tank_name.trim()}>Record check</Button>
          {logs.length === 0 && <Empty>No tank checks recorded yet.</Empty>}
          {logs.map((row) => (
            <div key={row.id} className={`flex flex-wrap items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm ${row.alarm ? 'border-red-200 bg-red-50 text-red-700' : ''}`}>
              <span className="font-medium">{row.tank_name}</span>
              <span>{plain(row.nitrogen_level)}{row.temperature_c !== null && row.temperature_c !== undefined ? ` · ${row.temperature_c} °C` : ''}{row.alarm ? ' · Alarm' : ''}</span>
              <span className="text-xs text-gray-500">{(row.recorded_at || '').replace('T', ' ').slice(0, 16)} · {row.recorded_by}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </Shell>
  );
}

function RegistersPage() {
  const now = new Date();
  const [period, setPeriod] = useState({ year: now.getFullYear(), month: now.getMonth() + 1 });
  const [registry, setRegistry] = useState(null);
  const [equipment, setEquipment] = useState([]);
  const [grievances, setGrievances] = useState([]);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [item, setItem] = useState({ name: '', asset_code: '', location: '', installed_on: '' });
  const [change, setChange] = useState({ id: null, note: '', status: 'active' });
  const [complaint, setComplaint] = useState({ complainant_name: '', summary: '' });
  const [resolutions, setResolutions] = useState({});

  const load = useCallback(async () => {
    try {
      const [eq, gr] = await Promise.all([axios.get('/api/art/equipment'), axios.get('/api/art/grievances')]);
      setEquipment(eq.data);
      setGrievances(gr.data);
    } catch (e) {
      setError(errMsg(e));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const loadRegistry = useCallback(async () => {
    try {
      setRegistry((await axios.get('/api/art/registry', { params: period })).data);
    } catch (e) {
      setError(errMsg(e));
    }
  }, [period]);
  useEffect(() => { loadRegistry(); }, [loadRegistry]);

  async function run(fn, message) {
    try {
      await fn();
      setError('');
      setInfo(message);
      load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  async function exportCsv() {
    try {
      await downloadFile('/api/art/registry', `art-registry-${period.year}-${String(period.month).padStart(2, '0')}.csv`, { ...period, format: 'csv' });
    } catch (e) {
      setError(await errorFromBlob(e));
    }
  }

  const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const clinic = registry?.clinic;
  const bank = registry?.bank;

  return (
    <Shell title="Registers" description="The monthly return, the equipment log, and complaints. These are the records an inspection asks for.">
      <Notice error={error} info={info} />
      <Card>
        <CardHeader><CardTitle className="text-base">Monthly return</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Month" className="w-44">
              <select className={selectClass} value={period.month} onChange={(e) => setPeriod({ ...period, month: Number(e.target.value) })}>
                {months.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
              </select>
            </Field>
            <Field label="Year" className="w-28">
              <Input value={period.year} onChange={(e) => setPeriod({ ...period, year: Number(e.target.value) || period.year })} />
            </Field>
            <Button variant="outline" onClick={exportCsv}>Download CSV</Button>
          </div>
          {clinic && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 text-sm">
              {[
                ['New cases', clinic.enrolments],
                ['IUI done', clinic.procedures.iui],
                ['Egg collections', clinic.procedures.opu],
                ['Embryo transfers', `${clinic.procedures.transfer} (${clinic.procedures.embryos_transferred ?? 0} embryos)`],
                ['Outcomes recorded', clinic.outcomes],
                ['Donors screened', bank.donors_screened],
                ['Donors cleared', bank.donors_cleared],
                ['Straws issued / received', `${bank.samples_issued} / ${bank.samples_received}`],
              ].map(([label, value]) => (
                <div key={label} className="rounded-md border px-3 py-2"><p className="text-gray-500">{label}</p><p className="font-medium">{value}</p></div>
              ))}
            </div>
          )}
          {clinic && clinic.complications.length > 0 && (
            <div className="space-y-1 text-sm">
              <p className="font-medium text-gray-900">Complications</p>
              {clinic.complications.map((c) => <p key={c.cycle_number} className="text-gray-600">{c.cycle_number}: {c.complication}</p>)}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle className="text-base">Equipment</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {equipment.length === 0 && <Empty>No equipment recorded.</Empty>}
            {equipment.map((row) => (
              <div key={row.id} className="space-y-2 rounded-md border px-3 py-2 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-medium">{row.name}{row.asset_code ? ` · ${row.asset_code}` : ''}</p>
                    <p className="text-xs text-gray-500">
                      {row.location || 'Location not set'} · Installed {row.installed_on || '—'}
                      {row.last_change_on ? ` · Last change ${row.last_change_on}: ${row.change_note || ''}` : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{plain(row.status)}</Badge>
                    <Button variant="outline" size="sm" onClick={() => setChange(change.id === row.id ? { id: null, note: '', status: 'active' } : { id: row.id, note: '', status: row.status })}>Log a change</Button>
                  </div>
                </div>
                {change.id === row.id && (
                  <div className="grid gap-3 rounded-md border p-3 sm:grid-cols-3">
                    <Field label="What changed" className="sm:col-span-2"><Input value={change.note} onChange={(e) => setChange({ ...change, note: e.target.value })} /></Field>
                    <Field label="Status">
                      <select className={selectClass} value={change.status} onChange={(e) => setChange({ ...change, status: e.target.value })}>
                        <option value="active">In use</option>
                        <option value="maintenance">Under repair</option>
                        <option value="retired">No longer in use</option>
                      </select>
                    </Field>
                    <Button
                      size="sm"
                      disabled={!change.note.trim()}
                      onClick={() => run(async () => {
                        await axios.patch(`/api/art/equipment/${row.id}`, { name: row.name, status: change.status, change_note: change.note, last_change_on: todayISO() });
                        setChange({ id: null, note: '', status: 'active' });
                      }, 'Change logged.')}
                    >
                      Save
                    </Button>
                  </div>
                )}
              </div>
            ))}
            <div className="grid gap-3 border-t pt-3 sm:grid-cols-2">
              <Field label="Name"><Input value={item.name} onChange={(e) => setItem({ ...item, name: e.target.value })} placeholder="For example CO2 incubator" /></Field>
              <Field label="Asset code"><Input value={item.asset_code} onChange={(e) => setItem({ ...item, asset_code: e.target.value })} /></Field>
              <Field label="Where it is"><Input value={item.location} onChange={(e) => setItem({ ...item, location: e.target.value })} /></Field>
              <Field label="Installed on"><Input type="date" value={item.installed_on} onChange={(e) => setItem({ ...item, installed_on: e.target.value })} /></Field>
            </div>
            <Button
              variant="outline"
              disabled={!item.name.trim()}
              onClick={() => run(async () => {
                await axios.post('/api/art/equipment', { ...item, installed_on: item.installed_on || null });
                setItem({ name: '', asset_code: '', location: '', installed_on: '' });
              }, 'Equipment added.')}
            >
              Add equipment
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle className="text-base">Complaints</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {grievances.length === 0 && <Empty>No complaints recorded.</Empty>}
            {grievances.map((row) => (
              <div key={row.id} className="space-y-2 rounded-md border px-3 py-2 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="font-medium">{row.reference} · {row.complainant_name}</p>
                    <p className="text-xs text-gray-500">Opened {row.opened_on || '—'}{row.closed_on ? ` · Closed ${row.closed_on}` : ''}</p>
                  </div>
                  <Badge variant="outline">{plain(row.status)}</Badge>
                </div>
                <p className="text-gray-700">{row.summary}</p>
                {row.resolution && <p className="text-gray-600">Resolution: {row.resolution}</p>}
                {row.status !== 'closed' && (
                  <div className="flex flex-wrap items-end gap-2">
                    <Field label="How it was resolved" className="min-w-0 flex-1">
                      <Input value={resolutions[row.id] || ''} onChange={(e) => setResolutions({ ...resolutions, [row.id]: e.target.value })} />
                    </Field>
                    <Button
                      size="sm"
                      disabled={!(resolutions[row.id] || '').trim()}
                      onClick={() => run(() => axios.post(`/api/art/grievances/${row.id}/close`, { resolution: resolutions[row.id] }), 'Complaint closed.')}
                    >
                      Close
                    </Button>
                  </div>
                )}
              </div>
            ))}
            <div className="space-y-3 border-t pt-3">
              <Field label="Who complained"><Input value={complaint.complainant_name} onChange={(e) => setComplaint({ ...complaint, complainant_name: e.target.value })} /></Field>
              <Field label="What it is about"><Textarea value={complaint.summary} onChange={(e) => setComplaint({ ...complaint, summary: e.target.value })} /></Field>
              <Button
                variant="outline"
                disabled={!complaint.complainant_name.trim() || !complaint.summary.trim()}
                onClick={() => run(async () => {
                  await axios.post('/api/art/grievances', complaint);
                  setComplaint({ complainant_name: '', summary: '' });
                }, 'Complaint recorded.')}
              >
                Record complaint
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </Shell>
  );
}

function RateTable({ title, rows, labelOf }) {
  const entries = Object.entries(rows || {});
  return (
    <Card>
      <CardHeader><CardTitle className="text-base">{title}</CardTitle></CardHeader>
      <CardContent>
        {entries.length === 0 && <Empty>No outcomes recorded yet.</Empty>}
        {entries.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-gray-500">
                <th className="py-2 font-medium">Group</th>
                <th className="py-2 text-right font-medium">Started</th>
                <th className="py-2 text-right font-medium">Reached IUI or transfer</th>
                <th className="py-2 text-right font-medium">Clinical pregnancies</th>
                <th className="py-2 text-right font-medium">Rate</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([key, row]) => (
                <tr key={key} className="border-b last:border-0">
                  <td className="py-2 pr-3">{labelOf ? labelOf(key) : plain(key)}</td>
                  <td className="py-2 text-right">{row.cycles_started ?? row.cycles}</td>
                  <td className="py-2 text-right">{row.treated ?? row.cycles}</td>
                  <td className="py-2 text-right">{row.clinical_pregnancies}</td>
                  <td className="py-2 text-right">{pct(row.clinical_pregnancy_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}

function ReportsPage() {
  const [outcomes, setOutcomes] = useState(null);
  const [kpis, setKpis] = useState(undefined);
  const [error, setError] = useState('');

  useEffect(() => {
    axios.get('/api/art/reports/outcomes').then((res) => setOutcomes(res.data)).catch((e) => setError(errMsg(e)));
    axios.get('/api/art/reports/lab-kpis').then((res) => setKpis(res.data)).catch(() => setKpis(null));
  }, []);

  return (
    <Shell title="Results" description="Pregnancy rates use clinical pregnancy, not only a positive blood test, out of the cycles that reached IUI, embryo transfer, or timed intercourse. Cancelled cycles are counted as started. Lab figures come from the embryology worksheet.">
      <Notice error={error} />
      <div className="grid gap-4 lg:grid-cols-2">
        <RateTable title="By treatment" rows={outcomes?.by_cycle_type} />
        <RateTable title="By the woman’s age at the start" rows={outcomes?.by_age} labelOf={(key) => (key === 'unknown' ? 'Date of birth missing' : `${key} years`)} />
        <RateTable title="By stimulation protocol" rows={outcomes?.by_protocol} />
        <RateTable title="By doctor" rows={outcomes?.by_clinician} labelOf={(key) => plain(key)} />
      </div>
      {kpis === null && (
        <p className="text-sm text-gray-500">Embryology figures stay closed until the clinic is registered as Level 2 and the licence includes the lab.</p>
      )}
      {kpis && (
        <div className="grid gap-4 sm:grid-cols-3">
          <Card><CardContent className="pt-6"><p className="text-sm text-gray-500">Eggs that fertilised normally</p><p className="text-2xl font-semibold">{pct(kpis.fertilisation_rate)}</p><p className="text-xs text-gray-500">{kpis.normally_fertilised} of {kpis.oocytes_inseminated}</p></CardContent></Card>
          <Card><CardContent className="pt-6"><p className="text-sm text-gray-500">Embryos that reached day 5 or 6</p><p className="text-2xl font-semibold">{pct(kpis.blastocyst_rate)}</p><p className="text-xs text-gray-500">{kpis.blastocysts} of {kpis.embryos}</p></CardContent></Card>
          <Card><CardContent className="pt-6"><p className="text-sm text-gray-500">Frozen embryos that survived thawing</p><p className="text-2xl font-semibold">{pct(kpis.thaw_survival_rate)}</p><p className="text-xs text-gray-500">{kpis.thaw_survived} of {kpis.thawed}</p></CardContent></Card>
        </div>
      )}
    </Shell>
  );
}

function SetupPage() {
  const [form, setForm] = useState(null);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');

  useEffect(() => {
    axios.get('/api/art/centre').then((res) => setForm(res.data)).catch((e) => setError(errMsg(e)));
  }, []);

  async function save() {
    try {
      const res = await axios.put('/api/art/centre', {
        clinic_level: Number(form.clinic_level),
        clinic_registration_no: form.clinic_registration_no,
        clinic_valid_until: form.clinic_valid_until || null,
        director_name: form.director_name,
        bank_enabled: Boolean(form.bank_enabled),
        bank_registration_no: form.bank_registration_no,
        bank_valid_until: form.bank_valid_until || null,
      });
      setForm(res.data);
      setError('');
      setInfo(res.data.lab_enabled
        ? 'IVF and the embryology lab are open.'
        : 'This clinic can run workup and IUI. The lab stays closed until the registration is Level 2 and the licence includes it.');
    } catch (e) {
      setError(errMsg(e));
    }
  }

  if (!form) {
    return <Shell title="Clinic setup"><Notice error={error} info={error ? '' : 'Loading clinic setup…'} /></Shell>;
  }

  return (
    <Shell title="Clinic setup" description="These details match the ART clinic registration and, when you hold one, the ART bank registration.">
      <Card className="max-w-2xl">
        <CardContent className="space-y-4 pt-6">
          <Notice error={error} info={info} />
          <Field label="What this clinic is registered to do">
            <Choice
              value={form.clinic_level}
              onChange={(value) => setForm({ ...form, clinic_level: value })}
              options={[
                { value: 1, label: 'Level 1', hint: 'Investigations and IUI' },
                { value: 2, label: 'Level 2', hint: 'IVF, ICSI, and the embryology lab' },
              ]}
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Clinic registration number">
              <Input value={form.clinic_registration_no || ''} onChange={(e) => setForm({ ...form, clinic_registration_no: e.target.value })} />
            </Field>
            <Field label="Clinic registration valid until">
              <Input type="date" value={form.clinic_valid_until || ''} onChange={(e) => setForm({ ...form, clinic_valid_until: e.target.value })} />
            </Field>
            <Field label="Clinic director" className="sm:col-span-2">
              <Input value={form.director_name || ''} onChange={(e) => setForm({ ...form, director_name: e.target.value })} />
            </Field>
          </div>
          <label className="flex items-start gap-2 text-sm">
            <input className="mt-1" type="checkbox" checked={Boolean(form.bank_enabled)} onChange={(e) => setForm({ ...form, bank_enabled: e.target.checked })} />
            <span>
              <span className="font-medium">This centre runs its own donor bank</span>
              <span className="block text-xs text-gray-500">Leave this off if you only receive samples from outside banks.</span>
            </span>
          </label>
          {form.bank_enabled && (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Bank registration number">
                <Input value={form.bank_registration_no || ''} onChange={(e) => setForm({ ...form, bank_registration_no: e.target.value })} />
              </Field>
              <Field label="Bank registration valid until">
                <Input type="date" value={form.bank_valid_until || ''} onChange={(e) => setForm({ ...form, bank_valid_until: e.target.value })} />
              </Field>
            </div>
          )}
          <Button onClick={save}>Save clinic setup</Button>
        </CardContent>
      </Card>
    </Shell>
  );
}

export default function ArtModule() {
  return (
    <Routes>
      <Route path="board" element={<BoardPage />} />
      <Route path="cases" element={<CasesPage />} />
      <Route path="cases/:caseId" element={<CasePage />} />
      <Route path="cycles/:cycleId" element={<CyclePage />} />
      <Route path="catalog" element={<CatalogPage />} />
      <Route path="bank" element={<BankPage />} />
      <Route path="cryo" element={<CryoPage />} />
      <Route path="registers" element={<RegistersPage />} />
      <Route path="reports" element={<ReportsPage />} />
      <Route path="setup" element={<SetupPage />} />
      <Route path="*" element={<BoardPage />} />
    </Routes>
  );
}
