import React, { useCallback, useEffect, useState } from 'react';
import { NavLink, Routes, Route, Link, useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import PatientSearchPicker from '../../components/PatientSearchPicker';
import { printPdfFromUrl } from '../../utils/printPdf';
import { useAuth } from '../../contexts/AuthContext';

function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join('; ');
  return e?.message || 'Request failed';
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

const NAV = [
  ['/dashboard/art/board', 'Today'],
  ['/dashboard/art/cases', 'Cases'],
  ['/dashboard/art/catalog', 'Prices'],
  ['/dashboard/art/bank', 'Donor bank'],
  ['/dashboard/art/reports', 'Results'],
  ['/dashboard/art/setup', 'Clinic setup'],
];

function artLinks(user) {
  const roles = user?.roles || (user?.role ? [user.role] : []);
  const has = (...names) => names.some((name) => roles.includes(name));
  const admin = has('hospital_admin', 'super_admin');
  const billing = admin || has('billing_admin');
  const reports = billing || has('art_clinician', 'art_embryologist', 'art_bank_officer');
  return NAV.filter(([to]) => {
    if (to.endsWith('/catalog')) return billing;
    if (to.endsWith('/reports')) return reports;
    if (to.endsWith('/setup')) return admin;
    return true;
  });
}

function Shell({ title, description, actions, children }) {
  const { user } = useAuth();
  const links = artLinks(user);
  return (
    <div className="space-y-4">
      <nav className="flex flex-wrap gap-1 border-b pb-2">
        {links.map(([to, label]) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => (
              `rounded-md px-3 py-1.5 text-sm ${isActive ? 'bg-blue-600 text-white' : 'text-gray-600 hover:bg-gray-100'}`
            )}
          >
            {label}
          </NavLink>
        ))}
      </nav>
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
                <div key={row.token_no} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2">
                  <div>
                    <p className="text-sm font-medium">Token {row.token_no}</p>
                    <p className="text-xs text-gray-500">{plain(row.status)}</p>
                  </div>
                  <Link className="text-sm text-blue-700" to={`/dashboard/art/cases/${row.case_id}`}>Open case</Link>
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
                  <div>
                    <p className="text-sm font-medium">{plain(row.kind)}</p>
                    <p className="text-xs text-gray-500">{row.room || 'Room not set'}</p>
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
                <div key={row.code} className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
                  {row.code} storage renews on {row.renewal_due}
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
      setInfo('Consent recorded.');
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
      description={`${data.case_number}${data.partner_name ? ` · Partner ${data.partner_name}` : ''} · ${plain(data.case_type)}`}
      actions={<Button variant="outline" onClick={checkIn}>Check in for today</Button>}
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
              <Button onClick={startCycle} disabled={billingMode === 'package' && !packageId}>Start cycle</Button>
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

          <Card>
            <CardHeader><CardTitle className="text-base">Signed consents</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {data.consents.length === 0 && <p className="text-sm text-gray-500">No consent on file. A procedure stays blocked until the matching form is signed.</p>}
              {data.consents.map((row) => (
                <div key={row.id} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2">
                  <div>
                    <p className="text-sm font-medium">{CONSENT_PLAIN[row.form_code] || plain(row.form_code)}</p>
                    <p className="text-xs text-gray-500">Signed by {row.signed_by_name}</p>
                  </div>
                  <Badge variant="outline">{row.withdrawn_at ? 'Withdrawn' : 'Active'}</Badge>
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
                <Field label="Signed by">
                  <Input value={signedBy} onChange={(e) => setSignedBy(e.target.value)} />
                </Field>
              </div>
              <Button onClick={addConsent} disabled={!signedBy.trim()}>Record consent</Button>
            </CardContent>
          </Card>

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

function CyclePage() {
  const { cycleId } = useParams();
  const [cycle, setCycle] = useState(null);
  const [centre, setCentre] = useState(null);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  const [day, setDay] = useState({
    day_number: 1, drug: '', dose: '', left: '', right: '', endometrium_mm: '', e2: '',
  });

  const load = useCallback(async () => {
    try {
      const [cycleRes, centreRes] = await Promise.all([
        axios.get(`/api/art/cycles/${cycleId}`),
        axios.get('/api/art/centre'),
      ]);
      setCycle(cycleRes.data);
      setCentre(centreRes.data);
    } catch (e) {
      setError(errMsg(e));
    }
  }, [cycleId]);
  useEffect(() => { load(); }, [load]);

  async function saveDay() {
    try {
      await axios.post(`/api/art/cycles/${cycleId}/stimulation`, {
        day_number: Number(day.day_number),
        drugs: day.drug ? [{ name: day.drug, dose: day.dose, route: 'SC' }] : [],
        follicles_left: mmList(day.left),
        follicles_right: mmList(day.right),
        endometrium_mm: day.endometrium_mm ? Number(day.endometrium_mm) : null,
        e2: day.e2 ? Number(day.e2) : null,
      });
      setInfo('Monitoring day saved.');
      setError('');
      load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

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
  const sizes = (list) => (list && list.length ? list.join(', ') : '—');

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
            <div><dt className="text-gray-500">Medicines</dt><dd className="font-medium">{snap.includes_medicines ? 'Included in the package' : 'Billed separately from the pharmacy'}</dd></div>
            <div><dt className="text-gray-500">Kept if the cycle is cancelled</dt><dd className="font-medium">{rupee(snap.cancel_keep_amount)}</dd></div>
            {cycle.donor_code && (
              <div><dt className="text-gray-500">Donor code on this chart</dt><dd className="font-medium">{cycle.donor_code}</dd></div>
            )}
          </dl>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Stimulation monitoring</CardTitle></CardHeader>
        <CardContent className="space-y-4">
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
                    <th className="py-2 font-medium">Estradiol</th>
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
                      <td className="py-2">{row.e2 ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Cycle day"><Input value={day.day_number} onChange={(e) => setDay({ ...day, day_number: e.target.value })} /></Field>
            <Field label="Medicine"><Input value={day.drug} onChange={(e) => setDay({ ...day, drug: e.target.value })} /></Field>
            <Field label="Dose"><Input value={day.dose} onChange={(e) => setDay({ ...day, dose: e.target.value })} /></Field>
            <Field label="Estradiol (E2)"><Input value={day.e2} onChange={(e) => setDay({ ...day, e2: e.target.value })} /></Field>
            <Field label="Left ovary follicles" hint="Sizes in mm, separated by commas" className="lg:col-span-2">
              <Input value={day.left} onChange={(e) => setDay({ ...day, left: e.target.value })} />
            </Field>
            <Field label="Right ovary follicles" hint="Sizes in mm, separated by commas" className="lg:col-span-2">
              <Input value={day.right} onChange={(e) => setDay({ ...day, right: e.target.value })} />
            </Field>
            <Field label="Womb lining" hint="Thickness in millimetres">
              <Input value={day.endometrium_mm} onChange={(e) => setDay({ ...day, endometrium_mm: e.target.value })} />
            </Field>
          </div>
          <Button onClick={saveDay}>Save this day</Button>
        </CardContent>
      </Card>

      {centre?.lab_enabled && (
        <Card>
          <CardHeader><CardTitle className="text-base">Embryology</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-3 text-sm">
              <div className="rounded-md border px-3 py-2"><p className="text-gray-500">Eggs collected</p><p className="font-medium">{cycle.retrieval_oocytes ?? '—'}</p></div>
              <div className="rounded-md border px-3 py-2"><p className="text-gray-500">How they were fertilised</p><p className="font-medium">{cycle.fert_method ? plain(cycle.fert_method) : '—'}</p></div>
              <div className="rounded-md border px-3 py-2"><p className="text-gray-500">Eggs that fertilised normally</p><p className="font-medium">{cycle.fert_normal ?? '—'}</p></div>
            </div>
            <p className="text-sm text-gray-600">Incubator worksheet is {cycle.culture_open ? 'open for this patient' : 'closed'}.</p>
            {cycle.specimens.length === 0 && <Empty>No eggs or embryos on this worksheet yet.</Empty>}
            {cycle.specimens.map((row) => (
              <div key={row.id} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
                <div>
                  <p className="font-medium">{row.code}</p>
                  <p className="text-xs text-gray-500">{plain(row.sample_type)}{row.tank ? ` · Tank ${row.tank}` : ''}</p>
                </div>
                <Badge variant="outline">{plain(row.disposition)}</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
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

function BankPage() {
  const [codes, setCodes] = useState([]);
  const [identity, setIdentity] = useState(null);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ donor_type: 'oocyte', legal_name: '', phone: '' });

  const load = useCallback(async () => {
    try {
      const res = await axios.get('/api/art/donors/codes');
      setCodes(res.data);
      try {
        const full = await axios.get('/api/art/donors');
        setIdentity(full.data);
      } catch (e) {
        if (e?.response?.status === 403) setIdentity(null);
        else throw e;
      }
    } catch (e) {
      setError(errMsg(e));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function addDonor() {
    try {
      await axios.post('/api/art/donors', form);
      setForm({ donor_type: 'oocyte', legal_name: '', phone: '' });
      setError('');
      load();
    } catch (e) {
      setError(errMsg(e));
    }
  }

  return (
    <Shell
      title="Donor bank"
      description="The patient chart shows a donor code only. The donor’s name and phone stay in the bank file."
    >
      <Notice error={error} />
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
            <CardHeader><CardTitle className="text-base">Bank identity file</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              {identity.map((row) => (
                <div key={row.id} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
                  <div>
                    <p className="font-medium">{row.legal_name}</p>
                    <p className="text-xs text-gray-500">{row.donor_code} · {row.phone || 'No phone'}</p>
                  </div>
                  <Badge variant="outline">{plain(row.status)}</Badge>
                </div>
              ))}
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="What they donate" className="sm:col-span-2">
                  <Choice
                    value={form.donor_type}
                    onChange={(value) => setForm({ ...form, donor_type: value })}
                    options={[
                      { value: 'oocyte', label: 'Eggs', hint: 'Needs 12 months of insurance before they can be cleared' },
                      { value: 'sperm', label: 'Sperm', hint: 'Cleared after the infection screen' },
                    ]}
                  />
                </Field>
                <Field label="Full legal name"><Input value={form.legal_name} onChange={(e) => setForm({ ...form, legal_name: e.target.value })} /></Field>
                <Field label="Phone"><Input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
              </div>
              <Button onClick={addDonor} disabled={!form.legal_name.trim()}>Register donor</Button>
            </CardContent>
          </Card>
        )}
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
                <th className="py-2 text-right font-medium">Cycles</th>
                <th className="py-2 text-right font-medium">Clinical pregnancies</th>
                <th className="py-2 text-right font-medium">Rate</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([key, row]) => (
                <tr key={key} className="border-b last:border-0">
                  <td className="py-2 pr-3">{labelOf ? labelOf(key) : plain(key)}</td>
                  <td className="py-2 text-right">{row.cycles}</td>
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
    <Shell title="Results" description="Pregnancy rates use clinical pregnancy, not only a positive blood test. Lab figures come from the embryology worksheet.">
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
        director_name: form.director_name,
        bank_enabled: true,
        bank_registration_no: form.bank_registration_no,
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
            <Field label="Clinic director">
              <Input value={form.director_name || ''} onChange={(e) => setForm({ ...form, director_name: e.target.value })} />
            </Field>
            <Field label="Bank registration number" hint="Leave blank if this centre does not run its own donor bank" className="sm:col-span-2">
              <Input value={form.bank_registration_no || ''} onChange={(e) => setForm({ ...form, bank_registration_no: e.target.value })} />
            </Field>
          </div>
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
      <Route path="reports" element={<ReportsPage />} />
      <Route path="setup" element={<SetupPage />} />
      <Route path="*" element={<BoardPage />} />
    </Routes>
  );
}
