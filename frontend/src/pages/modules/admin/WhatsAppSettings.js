import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import axios from 'axios';
import { useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../../components/ui/tabs';
import { useToast } from '../../../hooks/use-toast';
import { MessageCircle, Link2, BarChart3, FileText, RotateCcw, Save } from 'lucide-react';

const KIND_LABELS = {
  consultation_confirmation: 'Consultation confirmation',
  lab_order_confirmation: 'Lab order confirmation',
  lab_report: 'Lab report',
  prescription: 'Prescription',
  consultation_invoice: 'Consultation invoice',
  lab_invoice: 'Lab invoice',
  pharmacy_invoice: 'Pharmacy invoice',
};
const USAGE_LABELS = { ...KIND_LABELS, custom: 'Other (free text)' };

const PLACEHOLDERS = ['patient_name', 'hospital_name', 'doctor_name', 'date', 'time', 'order_number'];
const SAMPLE = {
  patient_name: 'Asha Reddy', hospital_name: 'Your Hospital', doctor_name: 'Dr. Rao',
  date: '12 Dec 2026', time: '10:30 AM', order_number: 'LAB-1042',
};

// Mirrors backend render_message so the preview matches what patients receive.
const renderPreview = (tpl) => {
  const when = [SAMPLE.date, SAMPLE.time].filter(Boolean).join(' ');
  const ctx = {
    ...SAMPLE,
    when_clause: when ? ` for ${when}` : '',
    doctor_clause: SAMPLE.doctor_name ? ` with ${SAMPLE.doctor_name}` : '',
    order_clause: SAMPLE.order_number ? ` (${SAMPLE.order_number})` : '',
  };
  return (tpl || '').replace(/\{(\w+)\}/g, (_, k) => (k in ctx ? ctx[k] : ''));
};

const RANGES = [
  { id: 'today', label: 'Today' },
  { id: 'month', label: 'This month' },
  { id: 'all', label: 'All time' },
  { id: 'custom', label: 'Custom' },
];

const ymd = (d) => {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};

const rangeParams = (range, from, to) => {
  const now = new Date();
  if (range === 'today') return { date_from: ymd(now), date_to: ymd(now) };
  if (range === 'month') return { date_from: ymd(new Date(now.getFullYear(), now.getMonth(), 1)), date_to: ymd(now) };
  if (range === 'custom') return { ...(from ? { date_from: from } : {}), ...(to ? { date_to: to } : {}) };
  return {};
};

const errText = (e, fallback) => {
  const d = e?.response?.data?.detail;
  return typeof d === 'string' ? d : fallback;
};

const STATE_TEXT = {
  disabled: 'Disabled',
  stopped: 'Service not running',
  starting: 'Starting…',
  connecting: 'Connecting…',
  qr: 'Waiting for QR scan',
  connected: 'Connected',
  loggedout: 'Logged out — rescan to relink',
  unavailable: 'Unavailable',
  off: 'Not linked',
  backup: 'Connected (backup number)',
};

const SLOT_INFO = {
  primary: { title: 'Primary number', hint: 'All messages go out from this number.' },
  secondary: { title: 'Secondary number (backup)', hint: 'Used automatically when the primary is not connected or a send fails.' },
};
const SLOTS = ['primary', 'secondary'];

// One linked-number slot: status, phone, QR to scan, link / unlink.
function SlotCard({ slot, session, onUnlink, onStart, busy }) {
  const info = SLOT_INFO[slot] || { title: slot, hint: '' };
  const st = session?.state || 'off';
  return (
    <Card className={st === 'connected' ? 'border-green-300' : ''}>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">{info.title}</CardTitle>
            <p className="mt-0.5 text-xs text-gray-500">{info.hint}</p>
          </div>
          <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${PILL[st] || 'bg-gray-100 text-gray-600'}`}>
            {STATE_TEXT[st] || st}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {st === 'connected' && (
          <div className="flex items-center justify-between gap-2 rounded-md bg-green-50 px-3 py-2">
            <span className="text-sm font-medium text-green-800">{session.phone ? `+${session.phone}` : 'Linked'}</span>
            <Button size="sm" variant="outline" onClick={() => onUnlink(slot)} disabled={busy}>Unlink</Button>
          </div>
        )}
        {st === 'qr' && session.qr && (
          <div className="flex flex-col items-center gap-2">
            <img src={session.qr} alt={`WhatsApp QR code for ${info.title}`} className="h-52 w-52 rounded border" />
            <p className="text-center text-xs text-gray-500">
              On the phone for this number: WhatsApp → Settings → Linked devices → Link a device, then scan.
            </p>
            {slot !== 'primary' && (
              <Button size="sm" variant="ghost" onClick={() => onUnlink(slot)} disabled={busy}>Cancel</Button>
            )}
          </div>
        )}
        {st === 'off' && (
          <div className="py-4 text-center">
            <p className="mb-3 text-sm text-gray-500">
              {slot === 'primary' ? 'Waiting for the WhatsApp service…' : 'No backup number linked.'}
            </p>
            {slot !== 'primary' && (
              <Button size="sm" onClick={() => onStart(slot)} disabled={busy}>
                <Link2 className="mr-1 h-4 w-4" /> Link a backup number
              </Button>
            )}
          </div>
        )}
        {['starting', 'connecting', 'stopped', 'unavailable', 'loggedout'].includes(st) && (
          <p className="py-4 text-center text-sm text-gray-500">
            {st === 'unavailable' ? (session?.message || 'The WhatsApp service is unavailable.') : 'A QR code will appear here when the service is ready…'}
          </p>
        )}
        {session?.message && st !== 'unavailable' && <p className="text-xs text-red-600">{session.message}</p>}
      </CardContent>
    </Card>
  );
}

const PILL = {
  connected: 'bg-green-100 text-green-800',
  qr: 'bg-amber-100 text-amber-800',
  starting: 'bg-amber-100 text-amber-800',
  connecting: 'bg-amber-100 text-amber-800',
  disabled: 'bg-gray-100 text-gray-600',
};

const WhatsAppSettings = () => {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [settings, setSettings] = useState(null);       // last saved server state
  const [conn, setConn] = useState({ state: 'disabled' });
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState('connection');

  // templates tab (drafts live here so switching tabs never loses edits)
  const [draft, setDraft] = useState({});
  const [draftCc, setDraftCc] = useState('91');
  const [selectedKind, setSelectedKind] = useState(Object.keys(KIND_LABELS)[0]);
  const editorRef = useRef(null);

  // usage tab
  const [range, setRange] = useState('month');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = (await axios.get('/api/whatsapp/settings')).data;
      setSettings(data);
      setDraft(data.templates);
      setDraftCc(data.default_country_code);
    } catch (e) {
      toast({ title: 'Error', description: errText(e, 'Failed to load WhatsApp settings'), variant: 'destructive' });
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const loadStats = useCallback(async () => {
    if (range === 'custom' && from && to && from > to) return;
    setStatsLoading(true);
    try {
      setStats((await axios.get('/api/whatsapp/stats', { params: rangeParams(range, from, to) })).data);
    } catch (e) {
      toast({ title: 'Error', description: errText(e, 'Failed to load message counts'), variant: 'destructive' });
    } finally {
      setStatsLoading(false);
    }
  }, [range, from, to, toast]);

  useEffect(() => { if (tab === 'usage') loadStats(); }, [tab, loadStats]);

  // Poll connection while enabled (QR refreshes every ~20 s on the WhatsApp side).
  useEffect(() => {
    if (!settings?.enabled) { setConn({ state: 'disabled' }); return undefined; }
    let stop = false;
    const tick = async () => {
      try {
        const r = await axios.get('/api/whatsapp/connection');
        if (!stop) setConn(r.data);
      } catch { /* keep last state */ }
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => { stop = true; clearInterval(id); };
  }, [settings?.enabled]);

  const save = async (patch, okMsg) => {
    setSaving(true);
    try {
      const r = await axios.put('/api/whatsapp/settings', patch);
      setSettings(r.data);
      if (patch.templates) { setDraft(r.data.templates); setDraftCc(r.data.default_country_code); }
      queryClient.invalidateQueries({ queryKey: ['whatsapp-status'] });
      toast({ title: okMsg || 'Saved' });
    } catch (e) {
      toast({ title: 'Error', description: errText(e, 'Failed to save'), variant: 'destructive' });
    } finally {
      setSaving(false);
    }
  };

  const [slotBusy, setSlotBusy] = useState(false);

  const unlink = async (slot = 'primary') => {
    const label = SLOT_INFO[slot]?.title || slot;
    if (!window.confirm(`Unlink the ${label.toLowerCase()}?`)) return;
    setSlotBusy(true);
    try {
      await axios.post('/api/whatsapp/logout', null, { params: { slot } });
      toast({ title: `${label} unlinked` });
      queryClient.invalidateQueries({ queryKey: ['whatsapp-status'] });
    } catch (e) {
      toast({ title: 'Error', description: errText(e, 'Failed to unlink'), variant: 'destructive' });
    } finally {
      setSlotBusy(false);
    }
  };

  const startSlot = async (slot) => {
    setSlotBusy(true);
    try {
      await axios.post(`/api/whatsapp/connection/${slot}/start`);
    } catch (e) {
      toast({ title: 'Error', description: errText(e, 'Could not start linking'), variant: 'destructive' });
    } finally {
      setSlotBusy(false);
    }
  };

  const dirtyKinds = useMemo(() => {
    if (!settings) return new Set();
    return new Set(Object.keys(KIND_LABELS).filter((k) => (draft[k] || '') !== (settings.templates[k] || '')));
  }, [draft, settings]);
  const dirty = dirtyKinds.size > 0 || (settings && draftCc !== settings.default_country_code);

  const insertPlaceholder = (name) => {
    const el = editorRef.current;
    const token = `{${name}}`;
    const cur = draft[selectedKind] || '';
    if (!el) { setDraft({ ...draft, [selectedKind]: cur + token }); return; }
    const s = el.selectionStart ?? cur.length;
    const e = el.selectionEnd ?? cur.length;
    setDraft({ ...draft, [selectedKind]: cur.slice(0, s) + token + cur.slice(e) });
    requestAnimationFrame(() => { el.focus(); el.setSelectionRange(s + token.length, s + token.length); });
  };

  if (!settings) return <p className="text-sm text-gray-500">Loading…</p>;

  const sessions = conn.sessions || {};
  const anyConnected = SLOTS.some((sl) => sessions[sl]?.state === 'connected');
  const pillState = !settings.enabled ? 'disabled'
    : sessions.primary?.state === 'connected' || conn.state === 'connected' ? 'connected'
    : anyConnected ? 'backup'
    : conn.state;

  return (
    <div className="space-y-4">
      {/* Always-visible header: master switch + live status */}
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
          <div className="flex items-center gap-3 min-w-0">
            <div className="rounded-full bg-green-100 p-2.5"><MessageCircle className="h-5 w-5 text-green-700" /></div>
            <div className="min-w-0">
              <div className="font-semibold">WhatsApp messaging</div>
              <div className="text-xs text-gray-500">Staff-triggered messages and documents to patients via WhatsApp Web</div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${PILL[pillState] || 'bg-red-100 text-red-700'}`}>
              {STATE_TEXT[pillState] || pillState}
            </span>
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox" className="h-5 w-5" checked={settings.enabled} disabled={saving}
                onChange={(e) => save({ enabled: e.target.checked }, e.target.checked ? 'WhatsApp enabled' : 'WhatsApp disabled')}
              />
              <span className="text-sm font-medium">{settings.enabled ? 'Enabled' : 'Disabled'}</span>
            </label>
          </div>
        </CardContent>
      </Card>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="h-auto">
          <TabsTrigger value="connection" className="gap-1.5"><Link2 className="h-4 w-4" /> Connection</TabsTrigger>
          <TabsTrigger value="usage" className="gap-1.5"><BarChart3 className="h-4 w-4" /> Usage</TabsTrigger>
          <TabsTrigger value="templates" className="gap-1.5">
            <FileText className="h-4 w-4" /> Templates
            {dirty && <span className="ml-1 h-2 w-2 rounded-full bg-amber-500" title="Unsaved changes" />}
          </TabsTrigger>
        </TabsList>

        {/* ---------------- Connection ---------------- */}
        <TabsContent value="connection" className="mt-4">
          {!settings.enabled ? (
            <Card><CardContent className="py-10 text-center text-sm text-gray-500">
              Turn on <strong>WhatsApp messaging</strong> above to link the hospital&apos;s number.
            </CardContent></Card>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-gray-600">
                Messages are sent from the <strong>primary</strong> number. If it is not connected or a send fails,
                the <strong>secondary</strong> number takes over automatically, so staff can keep sending.
              </p>
              <div className="grid gap-4 md:grid-cols-2">
                {SLOTS.map((sl) => (
                  <SlotCard
                    key={sl}
                    slot={sl}
                    session={{
                      ...(sessions[sl] || (sl === 'primary' ? conn : { state: 'off' })),
                      ...(conn.message && ['unavailable', 'starting'].includes(conn.state) ? { message: conn.message } : {}),
                    }}
                    onUnlink={unlink}
                    onStart={startSlot}
                    busy={slotBusy}
                  />
                ))}
              </div>
            </div>
          )}
        </TabsContent>

        {/* ---------------- Usage ---------------- */}
        <TabsContent value="usage" className="mt-4 space-y-4">
          {stats && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {[['Today', stats.summary.today], ['This month', stats.summary.this_month], ['All time', stats.summary.all_time]].map(([label, s]) => (
                <Card key={label}><CardContent className="py-4">
                  <div className="text-xs text-gray-500">{label}</div>
                  <div className="text-2xl font-semibold text-green-700">{s.sent}</div>
                  <div className="text-xs text-gray-500">
                    {s.whatsapp_messages} WhatsApp msgs
                    {s.failed > 0 && <span className="text-red-600"> · {s.failed} failed</span>}
                  </div>
                </CardContent></Card>
              ))}
            </div>
          )}

          <Card>
            <CardHeader className="pb-3">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div className="flex flex-wrap items-end gap-2">
                  {RANGES.map((r) => (
                    <Button key={r.id} size="sm" variant={range === r.id ? 'default' : 'outline'} onClick={() => setRange(r.id)}>{r.label}</Button>
                  ))}
                  {range === 'custom' && (
                    <>
                      <div>
                        <Label htmlFor="wa-from" className="text-xs">From</Label>
                        <Input id="wa-from" type="date" className="h-8 w-40" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} />
                      </div>
                      <div>
                        <Label htmlFor="wa-to" className="text-xs">To</Label>
                        <Input id="wa-to" type="date" className="h-8 w-40" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} />
                      </div>
                    </>
                  )}
                </div>
                <Button variant="outline" size="sm" onClick={loadStats} disabled={statsLoading}>
                  {statsLoading ? 'Refreshing…' : 'Refresh'}
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {stats && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs uppercase text-gray-500">
                        <th className="py-2 pr-3 font-medium">Topic</th>
                        <th className="py-2 px-3 text-right font-medium">Sent</th>
                        <th className="py-2 px-3 text-right font-medium">Failed</th>
                        <th className="py-2 pl-3 text-right font-medium">WhatsApp msgs</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.by_kind.map((r) => (
                        <tr key={r.kind} className="border-b last:border-0">
                          <td className="py-2 pr-3">{USAGE_LABELS[r.kind] || r.kind}</td>
                          <td className={`py-2 px-3 text-right tabular-nums ${r.sent ? 'font-medium' : 'text-gray-400'}`}>{r.sent}</td>
                          <td className={`py-2 px-3 text-right tabular-nums ${r.failed ? 'text-red-600' : 'text-gray-400'}`}>{r.failed}</td>
                          <td className={`py-2 pl-3 text-right tabular-nums ${r.whatsapp_messages ? '' : 'text-gray-400'}`}>{r.whatsapp_messages}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t-2 font-semibold">
                        <td className="py-2 pr-3">Total</td>
                        <td className="py-2 px-3 text-right tabular-nums">{stats.sent}</td>
                        <td className="py-2 px-3 text-right tabular-nums">{stats.failed}</td>
                        <td className="py-2 pl-3 text-right tabular-nums">{stats.whatsapp_messages}</td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              )}
              {stats?.by_number && (
                <p className="mt-3 text-xs text-gray-600">
                  Sent from: <strong>Primary</strong> {stats.by_number.primary || 0}
                  {' · '}<strong>Secondary (backup)</strong> {stats.by_number.secondary || 0}
                </p>
              )}
              <p className="mt-3 text-xs text-gray-500">
                &quot;Sent&quot; = one press of Send. &quot;WhatsApp msgs&quot; also counts each extra attachment,
                because WhatsApp delivers every file as its own message.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ---------------- Templates ---------------- */}
        <TabsContent value="templates" className="mt-4">
          <Card>
            <CardContent className="space-y-4 py-4">
              <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                  <Label htmlFor="wa-cc">Default country code</Label>
                  <Input id="wa-cc" className="h-9 w-28" value={draftCc} onChange={(e) => setDraftCc(e.target.value)} />
                </div>
                <div className="flex items-center gap-2">
                  {dirty && <span className="text-xs text-amber-700">Unsaved changes</span>}
                  <Button
                    variant="outline" disabled={saving}
                    onClick={() => setDraft({ ...settings.default_templates })}
                  >
                    <RotateCcw className="h-4 w-4 mr-1.5" /> Reset all
                  </Button>
                  <Button
                    disabled={saving || !dirty}
                    onClick={() => save({ default_country_code: draftCc, templates: draft }, 'Templates saved')}
                  >
                    <Save className="h-4 w-4 mr-1.5" /> Save
                  </Button>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-[220px_1fr]">
                <ul className="space-y-1">
                  {Object.entries(KIND_LABELS).map(([kind, label]) => (
                    <li key={kind}>
                      <button
                        type="button"
                        onClick={() => setSelectedKind(kind)}
                        className={`flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors ${
                          selectedKind === kind ? 'bg-green-50 font-medium text-green-800 ring-1 ring-green-200' : 'hover:bg-gray-100'
                        }`}
                      >
                        <span className="truncate">{label}</span>
                        {dirtyKinds.has(kind) && <span className="ml-2 h-2 w-2 shrink-0 rounded-full bg-amber-500" />}
                      </button>
                    </li>
                  ))}
                </ul>

                <div className="space-y-3 min-w-0">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="wa-editor">{KIND_LABELS[selectedKind]}</Label>
                    <Button
                      type="button" variant="ghost" size="sm" className="h-7 text-xs"
                      disabled={(draft[selectedKind] || '') === (settings.default_templates[selectedKind] || '')}
                      onClick={() => setDraft({ ...draft, [selectedKind]: settings.default_templates[selectedKind] })}
                    >
                      <RotateCcw className="h-3 w-3 mr-1" /> Reset to default
                    </Button>
                  </div>
                  <Textarea
                    id="wa-editor" ref={editorRef} rows={6}
                    value={draft[selectedKind] || ''}
                    onChange={(e) => setDraft({ ...draft, [selectedKind]: e.target.value })}
                  />
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-xs text-gray-500 mr-1">Insert:</span>
                    {PLACEHOLDERS.map((p) => (
                      <button
                        key={p} type="button" onClick={() => insertPlaceholder(p)}
                        className="rounded-full border bg-gray-50 px-2 py-0.5 text-xs text-gray-700 hover:bg-green-50 hover:border-green-300"
                      >
                        {`{${p}}`}
                      </button>
                    ))}
                  </div>
                  <div>
                    <div className="mb-1 text-xs text-gray-500">Preview (sample data)</div>
                    <div className="rounded-lg bg-[#e7f7dc] border border-green-200 p-3 text-sm whitespace-pre-wrap break-words">
                      {renderPreview(draft[selectedKind]) || <span className="text-gray-400">Empty — the default text will be used.</span>}
                    </div>
                  </div>
                  <p className="text-xs text-gray-500">Staff can still edit the text before each send.</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default WhatsAppSettings;
