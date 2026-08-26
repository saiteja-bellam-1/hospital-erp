import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Routes, Route, Navigate, useLocation, Link } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { useToast } from '../../hooks/use-toast';
import { useAuth } from '../../contexts/AuthContext';
import PatientSearchPicker from '../../components/PatientSearchPicker';
import { printPdfFromUrl } from '../../utils/printPdf';
import {
  Activity, Calendar, Package, BookOpen, Users, BarChart3, Plus, RefreshCw,
  CheckCircle2, Play, UserX, XCircle, Loader2, Download,
} from 'lucide-react';

function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join('; ');
  return e?.message || 'Request failed';
}

const fmt = (n) => `₹${Number(n || 0).toFixed(2)}`;
const todayISO = () => new Date().toISOString().slice(0, 10);

const STATUS_BADGE = {
  scheduled: 'bg-blue-100 text-blue-800',
  checked_in: 'bg-amber-100 text-amber-800',
  in_progress: 'bg-purple-100 text-purple-800',
  completed: 'bg-green-100 text-green-800',
  no_show: 'bg-gray-100 text-gray-600',
  cancelled: 'bg-red-100 text-red-700',
};

function usePhysioRoles() {
  const { user } = useAuth();
  const roles = useMemo(() => (
    Array.isArray(user?.roles) ? user.roles
      : typeof user?.role === 'string' ? [user.role] : []
  ), [user]);
  const isAdmin = roles.some((r) => ['super_admin', 'hospital_admin'].includes(r));
  return {
    roles,
    isAdmin,
    canCatalog: isAdmin || roles.some((r) => ['receptionist'].includes(r)),
    canSchedule: isAdmin || roles.some((r) => ['receptionist', 'frontdesk', 'physiotherapist'].includes(r)),
    canAttend: isAdmin || roles.some((r) => ['receptionist', 'frontdesk', 'physiotherapist'].includes(r)),
    canPackages: isAdmin || roles.some((r) => ['receptionist', 'frontdesk', 'billing_admin'].includes(r)),
    canReports: isAdmin || roles.some((r) => ['receptionist', 'billing_admin'].includes(r)),
    canSchedules: isAdmin || roles.some((r) => ['receptionist'].includes(r)),
  };
}

function NavTabs({ onSellPackage, canSellPackage }) {
  const loc = useLocation();
  const base = '/dashboard/physiotherapy';
  const tabs = [
    { to: `${base}/today`, label: "Today's Board", icon: Activity },
    { to: `${base}/appointments`, label: 'Appointments', icon: Calendar },
    { to: `${base}/packages`, label: 'Packages', icon: Package },
    { to: `${base}/catalog`, label: 'Catalog', icon: BookOpen },
    { to: `${base}/therapists`, label: 'Therapists', icon: Users },
    { to: `${base}/reports`, label: 'Reports', icon: BarChart3 },
  ];
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
      <div className="flex flex-wrap gap-2">
        {tabs.map(({ to, label, icon: Icon }) => {
          const active = loc.pathname.startsWith(to);
          return (
            <Link key={to} to={to}>
              <Button variant={active ? 'default' : 'outline'} size="sm" className="gap-1.5">
                <Icon className="h-4 w-4" />
                {label}
              </Button>
            </Link>
          );
        })}
      </div>
      {canSellPackage && (
        <Button size="sm" onClick={onSellPackage} className="gap-1.5">
          <Package className="h-4 w-4" />
          Sell package
        </Button>
      )}
    </div>
  );
}

function SellPackageDialog({ open, onOpenChange, onSold }) {
  const { toast } = useToast();
  const [templates, setTemplates] = useState([]);
  const [patient, setPatient] = useState(null);
  const [sellForm, setSellForm] = useState({ template_id: '', payment_method: 'cash', notes: '' });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPatient(null);
    setSellForm({ template_id: '', payment_method: 'cash', notes: '' });
    axios.get('/api/physiotherapy/package-templates')
      .then((r) => setTemplates((r.data || []).filter((t) => t.is_active !== false)))
      .catch(() => setTemplates([]));
  }, [open]);

  const sell = async () => {
    if (!patient?.id) {
      toast({ title: 'Select a patient', variant: 'destructive' });
      return;
    }
    if (!sellForm.template_id) {
      toast({ title: 'Select a package template', variant: 'destructive' });
      return;
    }
    setLoading(true);
    try {
      const res = await axios.post('/api/physiotherapy/packages/sell', {
        patient_id: patient.id,
        template_id: Number(sellForm.template_id),
        payment_method: sellForm.payment_method,
        notes: sellForm.notes || null,
      });
      onOpenChange(false);
      onSold?.();
      toast({ title: 'Package sold', description: res.data.bill_number });
      if (res.data.bill_id) {
        printPdfFromUrl(`/api/hospital/billing/bills/${res.data.bill_id}/pdf`);
      }
    } catch (e) {
      toast({ title: 'Sell failed', description: errMsg(e), variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Sell package</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div>
            <Label>Patient</Label>
            <PatientSearchPicker value={patient} onChange={setPatient} />
          </div>
          <div>
            <Label>Template</Label>
            <Select value={sellForm.template_id} onValueChange={(v) => setSellForm({ ...sellForm, template_id: v })}>
              <SelectTrigger><SelectValue placeholder="Select package" /></SelectTrigger>
              <SelectContent>
                {templates.map((t) => (
                  <SelectItem key={t.id} value={String(t.id)}>{t.name} — {fmt(t.price)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Payment</Label>
            <Select value={sellForm.payment_method} onValueChange={(v) => setSellForm({ ...sellForm, payment_method: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="cash">Cash</SelectItem>
                <SelectItem value="upi">UPI</SelectItem>
                <SelectItem value="card">Card</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button onClick={sell} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
            Sell & print bill
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CatalogPage() {
  const { toast } = useToast();
  const { canCatalog } = usePhysioRoles();
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({
    name: '', code: '', default_price: '', duration_minutes: 30, description: '', is_active: true,
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/physiotherapy/services?include_inactive=true');
      setServices(res.data || []);
    } catch (e) {
      toast({ title: 'Failed to load catalog', description: errMsg(e), variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const save = async () => {
    try {
      const payload = {
        ...form,
        default_price: Number(form.default_price || 0),
        duration_minutes: Number(form.duration_minutes || 30),
      };
      if (editing) {
        await axios.patch(`/api/physiotherapy/services/${editing.id}`, payload);
      } else {
        await axios.post('/api/physiotherapy/services', payload);
      }
      setOpen(false);
      setEditing(null);
      load();
      toast({ title: editing ? 'Service updated' : 'Service created' });
    } catch (e) {
      toast({ title: 'Save failed', description: errMsg(e), variant: 'destructive' });
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Service catalog</CardTitle>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={load}><RefreshCw className="h-4 w-4" /></Button>
          {canCatalog && (
            <Button size="sm" onClick={() => {
              setEditing(null);
              setForm({ name: '', code: '', default_price: '', duration_minutes: 30, description: '', is_active: true });
              setOpen(true);
            }}>
              <Plus className="h-4 w-4 mr-1" /> Add service
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left border-b">
                  <th className="py-2">Name</th>
                  <th>Code</th>
                  <th>Price</th>
                  <th>Duration</th>
                  <th>Status</th>
                  {canCatalog && <th />}
                </tr>
              </thead>
              <tbody>
                {services.map((s) => (
                  <tr key={s.id} className="border-b">
                    <td className="py-2 font-medium">{s.name}</td>
                    <td>{s.code || '—'}</td>
                    <td>{fmt(s.default_price)}</td>
                    <td>{s.duration_minutes} min</td>
                    <td>
                      <Badge variant="outline" className={s.is_active ? 'text-green-700' : 'text-gray-500'}>
                        {s.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    {canCatalog && (
                      <td>
                        <Button variant="ghost" size="sm" onClick={() => {
                          setEditing(s);
                          setForm({
                            name: s.name, code: s.code || '', default_price: String(s.default_price),
                            duration_minutes: s.duration_minutes, description: s.description || '',
                            is_active: s.is_active,
                          });
                          setOpen(true);
                        }}>Edit</Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
      <Dialog
        open={open}
        onOpenChange={(o) => {
          setOpen(o);
          if (!o) {
            setEditing(null);
            setForm({ name: '', code: '', default_price: '', duration_minutes: 30, description: '', is_active: true });
          }
        }}
      >
        <DialogContent>
          <DialogHeader><DialogTitle>{editing ? 'Edit service' : 'New service'}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
            <div><Label>Code</Label><Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /></div>
            <div className="grid grid-cols-2 gap-2">
              <div><Label>Price</Label><Input type="number" value={form.default_price} onChange={(e) => setForm({ ...form, default_price: e.target.value })} /></div>
              <div><Label>Duration (min)</Label><Input type="number" value={form.duration_minutes} onChange={(e) => setForm({ ...form, duration_minutes: e.target.value })} /></div>
            </div>
            <div><Label>Description</Label><Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
            <div>
              <Label>Status</Label>
              <Select
                value={form.is_active ? 'active' : 'inactive'}
                onValueChange={(v) => setForm({ ...form, is_active: v === 'active' })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={save}>Save</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

const EMPTY_TEMPLATE_FORM = {
  name: '', service_id: '', session_count: 10, price: '', validity_days: 90, description: '', is_active: true,
};

function PackagesPage() {
  const { toast } = useToast();
  const { canPackages, canSchedule } = usePhysioRoles();
  const [templates, setTemplates] = useState([]);
  const [sold, setSold] = useState([]);
  const [services, setServices] = useState([]);
  const [therapists, setTherapists] = useState([]);
  const [tmplOpen, setTmplOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState(null);
  const [bookOpen, setBookOpen] = useState(false);
  const [bookPrefill, setBookPrefill] = useState({ package: null, patient: null });
  const [tmplForm, setTmplForm] = useState({ ...EMPTY_TEMPLATE_FORM });

  const load = useCallback(async () => {
    try {
      const [t, p, s, th] = await Promise.all([
        axios.get('/api/physiotherapy/package-templates?include_inactive=true'),
        axios.get('/api/physiotherapy/packages'),
        axios.get('/api/physiotherapy/services'),
        axios.get('/api/physiotherapy/therapists'),
      ]);
      setTemplates(t.data || []);
      setSold(p.data || []);
      setServices(s.data || []);
      setTherapists(th.data || []);
    } catch (e) {
      toast({ title: 'Failed to load packages', description: errMsg(e), variant: 'destructive' });
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const openNewTemplate = () => {
    setEditingTemplate(null);
    setTmplForm({ ...EMPTY_TEMPLATE_FORM });
    setTmplOpen(true);
  };

  const openEditTemplate = (t) => {
    setEditingTemplate(t);
    setTmplForm({
      name: t.name || '',
      service_id: t.service_id ? String(t.service_id) : '',
      session_count: t.session_count,
      price: String(t.price ?? ''),
      validity_days: t.validity_days,
      description: t.description || '',
      is_active: t.is_active !== false,
    });
    setTmplOpen(true);
  };

  const openBookFromPackage = (pkg) => {
    setBookPrefill({
      package: pkg,
      patient: pkg.patient_id ? {
        id: pkg.patient_id,
        first_name: (pkg.patient_name || '').split(' ')[0] || '',
        last_name: (pkg.patient_name || '').split(' ').slice(1).join(' ') || '',
        primary_phone: '',
      } : null,
    });
    setBookOpen(true);
  };
  const saveTemplate = async () => {
    try {
      const payload = {
        ...tmplForm,
        service_id: tmplForm.service_id ? Number(tmplForm.service_id) : null,
        session_count: Number(tmplForm.session_count),
        price: Number(tmplForm.price || 0),
        validity_days: Number(tmplForm.validity_days),
      };
      if (editingTemplate) {
        await axios.patch(`/api/physiotherapy/package-templates/${editingTemplate.id}`, payload);
      } else {
        await axios.post('/api/physiotherapy/package-templates', payload);
      }
      setTmplOpen(false);
      setEditingTemplate(null);
      load();
      toast({ title: editingTemplate ? 'Package template updated' : 'Package template created' });
    } catch (e) {
      toast({ title: 'Failed', description: errMsg(e), variant: 'destructive' });
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Package templates</CardTitle>
          {canPackages && (
            <Button size="sm" onClick={openNewTemplate}><Plus className="h-4 w-4 mr-1" /> Template</Button>
          )}
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b">
                <th className="py-2">Name</th>
                <th>Service</th>
                <th>Sessions</th>
                <th>Price</th>
                <th>Validity</th>
                <th>Status</th>
                {canPackages && <th />}
              </tr>
            </thead>
            <tbody>
              {templates.map((t) => (
                <tr key={t.id} className="border-b">
                  <td className="py-2">{t.name}</td>
                  <td>{t.service_name || 'Any modality'}</td>
                  <td>{t.session_count}</td>
                  <td>{fmt(t.price)}</td>
                  <td>{t.validity_days} days</td>
                  <td>
                    <Badge variant="outline" className={t.is_active !== false ? 'text-green-700' : 'text-gray-500'}>
                      {t.is_active !== false ? 'Active' : 'Inactive'}
                    </Badge>
                  </td>
                  {canPackages && (
                    <td>
                      <Button variant="ghost" size="sm" onClick={() => openEditTemplate(t)}>Edit</Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Sold packages</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b">
                <th className="py-2">Patient</th><th>Package</th><th>Remaining</th><th>Status</th><th>Expires</th><th />
              </tr>
            </thead>
            <tbody>
              {sold.map((p) => (
                <tr key={p.id} className="border-b">
                  <td className="py-2">{p.patient_name}</td>
                  <td>{p.name}</td>
                  <td>{p.sessions_remaining}/{p.sessions_total}</td>
                  <td><Badge variant="outline">{p.status}</Badge></td>
                  <td>{p.expires_at ? new Date(p.expires_at).toLocaleDateString() : '—'}</td>
                  <td>
                    {canSchedule && p.status === 'active' && p.sessions_remaining > 0 && (
                      <Button size="sm" variant="outline" onClick={() => openBookFromPackage(p)}>
                        Book session
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <BookDialog
        open={bookOpen}
        onOpenChange={(o) => { setBookOpen(o); if (!o) setBookPrefill({ package: null, patient: null }); }}
        onSaved={load}
        therapists={therapists}
        services={services}
        initialPackage={bookPrefill.package}
        initialPatient={bookPrefill.patient}
      />

      <Dialog
        open={tmplOpen}
        onOpenChange={(o) => {
          setTmplOpen(o);
          if (!o) {
            setEditingTemplate(null);
            setTmplForm({ ...EMPTY_TEMPLATE_FORM });
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editingTemplate ? 'Edit package template' : 'New package template'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div><Label>Name</Label><Input value={tmplForm.name} onChange={(e) => setTmplForm({ ...tmplForm, name: e.target.value })} /></div>
            <div>
              <Label>Service (optional)</Label>
              <Select value={tmplForm.service_id || 'any'} onValueChange={(v) => setTmplForm({ ...tmplForm, service_id: v === 'any' ? '' : v })}>
                <SelectTrigger><SelectValue placeholder="Any modality" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="any">Any modality</SelectItem>
                  {services.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div><Label>Sessions</Label><Input type="number" value={tmplForm.session_count} onChange={(e) => setTmplForm({ ...tmplForm, session_count: e.target.value })} /></div>
              <div><Label>Price</Label><Input type="number" value={tmplForm.price} onChange={(e) => setTmplForm({ ...tmplForm, price: e.target.value })} /></div>
              <div><Label>Validity days</Label><Input type="number" value={tmplForm.validity_days} onChange={(e) => setTmplForm({ ...tmplForm, validity_days: e.target.value })} /></div>
            </div>
            <div>
              <Label>Description</Label>
              <Textarea value={tmplForm.description} onChange={(e) => setTmplForm({ ...tmplForm, description: e.target.value })} />
            </div>
            <div>
              <Label>Status</Label>
              <Select
                value={tmplForm.is_active ? 'active' : 'inactive'}
                onValueChange={(v) => setTmplForm({ ...tmplForm, is_active: v === 'active' })}
              >
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="inactive">Inactive</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button onClick={saveTemplate}>{editingTemplate ? 'Save' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function BookDialog({ open, onOpenChange, onSaved, therapists, services, initialPackage = null, initialPatient = null }) {
  const { toast } = useToast();
  const [patient, setPatient] = useState(null);
  const [form, setForm] = useState({
    therapist_id: '', service_id: '', appointment_date: todayISO(),
    appointment_time: '10:00', session_type: 'treatment', referral_source: '', chief_complaint: '',
    is_walk_in: false, package_id: '',
    billing_mode: 'a_la_carte', payment_method: 'cash', mark_paid: true, unit_price: '',
  });
  const [packages, setPackages] = useState([]);

  useEffect(() => {
    if (!open) return;
    const p = initialPatient || null;
    setPatient(p);
    const pkgId = initialPackage?.id ? String(initialPackage.id) : '';
    const svcId = initialPackage?.service_id ? String(initialPackage.service_id) : '';
    setForm((prev) => ({
      ...prev,
      therapist_id: '',
      service_id: svcId,
      appointment_date: todayISO(),
      appointment_time: '10:00',
      session_type: 'treatment',
      referral_source: '',
      chief_complaint: '',
      is_walk_in: false,
      package_id: pkgId,
      billing_mode: pkgId ? 'package' : 'a_la_carte',
      payment_method: 'cash',
      mark_paid: true,
      unit_price: '',
    }));
  }, [open, initialPackage, initialPatient]);

  useEffect(() => {
    if (!patient?.id) { setPackages([]); return; }
    axios.get(`/api/physiotherapy/packages/patient/${patient.id}/active`)
      .then((r) => {
        const list = r.data || [];
        setPackages(list);
        // Prefer selected package if still valid
        setForm((prev) => {
          if (prev.package_id && list.some((x) => String(x.id) === prev.package_id)) return prev;
          if (list.length === 1 && prev.billing_mode === 'package') {
            return { ...prev, package_id: String(list[0].id) };
          }
          return prev;
        });
      })
      .catch(() => setPackages([]));
  }, [patient]);

  useEffect(() => {
    if (form.billing_mode !== 'a_la_carte' || !form.service_id) return;
    const svc = services.find((s) => String(s.id) === String(form.service_id));
    if (svc && form.unit_price === '') {
      setForm((prev) => ({ ...prev, unit_price: String(svc.default_price ?? '') }));
    }
  }, [form.billing_mode, form.service_id, form.unit_price, services]);

  const submit = async () => {
    if (!patient?.id || !form.therapist_id) {
      toast({ title: 'Patient and therapist required', variant: 'destructive' });
      return;
    }
    if (form.billing_mode === 'package' && !form.package_id) {
      toast({ title: 'Select a package with remaining sessions', variant: 'destructive' });
      return;
    }
    if (form.billing_mode === 'a_la_carte' && !form.service_id) {
      toast({ title: 'Select a service for à la carte billing', variant: 'destructive' });
      return;
    }
    try {
      const res = await axios.post('/api/physiotherapy/appointments', {
        patient_id: patient.id,
        therapist_id: Number(form.therapist_id),
        service_id: form.service_id ? Number(form.service_id) : null,
        appointment_date: form.appointment_date,
        appointment_time: form.appointment_time || null,
        session_type: form.session_type,
        referral_source: form.referral_source || null,
        chief_complaint: form.chief_complaint || null,
        is_walk_in: form.is_walk_in,
        package_id: form.billing_mode === 'package' && form.package_id ? Number(form.package_id) : null,
        billing_mode: form.billing_mode,
        unit_price: form.billing_mode === 'a_la_carte' && form.unit_price !== '' ? Number(form.unit_price) : null,
        payment_method: form.payment_method,
        mark_paid: form.billing_mode === 'a_la_carte' ? form.mark_paid : false,
      });
      onOpenChange(false);
      setPatient(null);
      onSaved?.();
      const msg = form.billing_mode === 'package'
        ? `Booked from package (${res.data.package_sessions_remaining ?? '?'} left)`
        : form.billing_mode === 'a_la_carte'
          ? `Booked & billed${res.data.bill_number ? ` — ${res.data.bill_number}` : ''}`
          : 'Session booked';
      toast({ title: msg });
      if (res.data.bill_id) {
        printPdfFromUrl(`/api/hospital/billing/bills/${res.data.bill_id}/pdf`);
      }
    } catch (e) {
      toast({ title: 'Booking failed', description: errMsg(e), variant: 'destructive' });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader><DialogTitle>Book session</DialogTitle></DialogHeader>
        <div className="space-y-3 max-h-[70vh] overflow-y-auto">
          <div><Label>Patient</Label><PatientSearchPicker value={patient} onChange={setPatient} /></div>
          <div>
            <Label>Billing</Label>
            <Select value={form.billing_mode} onValueChange={(v) => setForm({
              ...form,
              billing_mode: v,
              package_id: v === 'package' ? form.package_id : '',
            })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="package">Use package balance</SelectItem>
                <SelectItem value="a_la_carte">À la carte (bill now)</SelectItem>
                <SelectItem value="none">No charge yet</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {form.billing_mode === 'package' && (
            <div>
              <Label>Package</Label>
              {packages.length === 0 ? (
                <p className="text-xs text-muted-foreground mt-1">No active packages — sell one first, or switch to à la carte.</p>
              ) : (
                <Select value={form.package_id || ''} onValueChange={(v) => setForm({ ...form, package_id: v })}>
                  <SelectTrigger><SelectValue placeholder="Select package" /></SelectTrigger>
                  <SelectContent>
                    {packages.map((p) => (
                      <SelectItem key={p.id} value={String(p.id)}>
                        {p.name} — {p.sessions_remaining}/{p.sessions_total} left
                        {p.service_name ? ` · ${p.service_name}` : ' · any modality'}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          )}
          <div>
            <Label>Therapist</Label>
            <Select value={form.therapist_id} onValueChange={(v) => setForm({ ...form, therapist_id: v })}>
              <SelectTrigger><SelectValue placeholder="Select therapist" /></SelectTrigger>
              <SelectContent>
                {therapists.map((t) => <SelectItem key={t.id} value={String(t.id)}>{t.full_name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Service{form.billing_mode === 'a_la_carte' ? ' *' : ''}</Label>
            <Select
              value={form.service_id || 'none'}
              onValueChange={(v) => {
                const id = v === 'none' ? '' : v;
                const svc = services.find((s) => String(s.id) === id);
                setForm({
                  ...form,
                  service_id: id,
                  unit_price: svc ? String(svc.default_price ?? '') : form.unit_price,
                });
              }}
            >
              <SelectTrigger><SelectValue placeholder="Select service" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None</SelectItem>
                {services.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)}>{s.name} — {fmt(s.default_price)}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {form.billing_mode === 'a_la_carte' && (
            <>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label>Price</Label>
                  <Input type="number" value={form.unit_price} onChange={(e) => setForm({ ...form, unit_price: e.target.value })} />
                </div>
                <div>
                  <Label>Payment</Label>
                  <Select value={form.payment_method} onValueChange={(v) => setForm({ ...form, payment_method: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cash">Cash</SelectItem>
                      <SelectItem value="upi">UPI</SelectItem>
                      <SelectItem value="card">Card</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.mark_paid} onChange={(e) => setForm({ ...form, mark_paid: e.target.checked })} />
                Collect payment now
              </label>
            </>
          )}
          <div className="grid grid-cols-2 gap-2">
            <div><Label>Date</Label><Input type="date" value={form.appointment_date} onChange={(e) => setForm({ ...form, appointment_date: e.target.value })} /></div>
            <div><Label>Time</Label><Input type="time" value={form.appointment_time} onChange={(e) => setForm({ ...form, appointment_time: e.target.value })} /></div>
          </div>
          <div>
            <Label>Type</Label>
            <Select value={form.session_type} onValueChange={(v) => setForm({ ...form, session_type: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="assessment">Assessment</SelectItem>
                <SelectItem value="treatment">Treatment</SelectItem>
                <SelectItem value="review">Review</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div><Label>Referral source</Label><Input value={form.referral_source} onChange={(e) => setForm({ ...form, referral_source: e.target.value })} placeholder="Self / Doctor / Hospital" /></div>
          <div><Label>Chief complaint</Label><Textarea value={form.chief_complaint} onChange={(e) => setForm({ ...form, chief_complaint: e.target.value })} /></div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={form.is_walk_in} onChange={(e) => setForm({ ...form, is_walk_in: e.target.checked })} />
            Walk-in (check in now)
          </label>
        </div>
        <DialogFooter>
          <Button onClick={submit}>
            {form.billing_mode === 'package' ? 'Book from package' : form.billing_mode === 'a_la_carte' ? 'Book & bill' : 'Book'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CompleteDialog({ appt, open, onOpenChange, onDone }) {
  const { toast } = useToast();
  const [note, setNote] = useState('');
  const [usePackage, setUsePackage] = useState(true);
  const [packageId, setPackageId] = useState('');
  const [packages, setPackages] = useState([]);
  const [markPaid, setMarkPaid] = useState(false);
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [unitPrice, setUnitPrice] = useState('');

  const prepaid = !!(appt?.package_id || appt?.bill_id);

  useEffect(() => {
    if (!appt?.patient_id) return;
    setNote('');
    setPackageId(appt.package_id ? String(appt.package_id) : '');
    setUsePackage(!!appt.package_id);
    if (appt.package_id || appt.bill_id) {
      setPackages([]);
      return;
    }
    axios.get(`/api/physiotherapy/packages/patient/${appt.patient_id}/active`, {
      params: appt.service_id ? { service_id: appt.service_id } : {},
    }).then((r) => setPackages(r.data || [])).catch(() => setPackages([]));
  }, [appt]);

  const submit = async () => {
    try {
      const res = await axios.post(`/api/physiotherapy/appointments/${appt.id}/complete`, {
        session_note: note || null,
        use_package: prepaid ? !!appt.package_id : (usePackage && !!packageId),
        package_id: prepaid ? (appt.package_id || null) : (packageId ? Number(packageId) : null),
        mark_paid: prepaid ? false : markPaid,
        payment_method: (!prepaid && markPaid) ? paymentMethod : null,
        unit_price: (!prepaid && unitPrice !== '') ? Number(unitPrice) : null,
      });
      onOpenChange(false);
      onDone?.();
      toast({ title: 'Session completed' });
      if (res.data.bill_id && !prepaid) {
        printPdfFromUrl(`/api/hospital/billing/bills/${res.data.bill_id}/pdf`);
      }
    } catch (e) {
      toast({ title: 'Complete failed', description: errMsg(e), variant: 'destructive' });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Complete session — {appt?.patient_name}</DialogTitle></DialogHeader>
        <div className="space-y-3">
          {prepaid && (
            <p className="text-sm text-muted-foreground border rounded-md p-2 bg-muted/40">
              {appt.package_id
                ? 'Package session already reserved at booking — completing will not charge again.'
                : 'À la carte bill already created at booking — completing will not charge again.'}
            </p>
          )}
          <div><Label>Session note</Label><Textarea value={note} onChange={(e) => setNote(e.target.value)} /></div>
          {!prepaid && packages.length > 0 && (
            <>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={usePackage} onChange={(e) => setUsePackage(e.target.checked)} />
                Consume package session
              </label>
              {usePackage && (
                <Select value={packageId} onValueChange={setPackageId}>
                  <SelectTrigger><SelectValue placeholder="Select package" /></SelectTrigger>
                  <SelectContent>
                    {packages.map((p) => (
                      <SelectItem key={p.id} value={String(p.id)}>{p.name} ({p.sessions_remaining} left)</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </>
          )}
          {!prepaid && (!usePackage || packages.length === 0) && (
            <>
              <div><Label>Unit price (optional override)</Label><Input type="number" value={unitPrice} onChange={(e) => setUnitPrice(e.target.value)} /></div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={markPaid} onChange={(e) => setMarkPaid(e.target.checked)} />
                Collect payment now
              </label>
              {markPaid && (
                <Select value={paymentMethod} onValueChange={setPaymentMethod}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cash">Cash</SelectItem>
                    <SelectItem value="upi">UPI</SelectItem>
                    <SelectItem value="card">Card</SelectItem>
                  </SelectContent>
                </Select>
              )}
            </>
          )}
        </div>
        <DialogFooter><Button onClick={submit}>Complete</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AppointmentsBoard({ dateFilter }) {
  const { toast } = useToast();
  const { canSchedule, canAttend } = usePhysioRoles();
  const [rows, setRows] = useState([]);
  const [therapists, setTherapists] = useState([]);
  const [services, setServices] = useState([]);
  const [dateFrom, setDateFrom] = useState(todayISO());
  const [dateTo, setDateTo] = useState(todayISO());
  const [bookOpen, setBookOpen] = useState(false);
  const [bookPrefill, setBookPrefill] = useState({ package: null, patient: null });
  const [completeAppt, setCompleteAppt] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const isTodayBoard = Boolean(dateFilter);

  const apptParams = useMemo(() => {
    if (isTodayBoard) return { date: dateFilter || todayISO() };
    return { date_from: dateFrom, date_to: dateTo };
  }, [isTodayBoard, dateFilter, dateFrom, dateTo]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (!isTodayBoard && dateFrom && dateTo && dateFrom > dateTo) {
        toast({ title: 'Invalid range', description: 'From date must be on or before To date', variant: 'destructive' });
        setLoading(false);
        return;
      }
      const [a, t, s] = await Promise.all([
        axios.get('/api/physiotherapy/appointments', { params: apptParams }),
        axios.get('/api/physiotherapy/therapists'),
        axios.get('/api/physiotherapy/services'),
      ]);
      setRows(a.data || []);
      setTherapists(t.data || []);
      setServices(s.data || []);
    } catch (e) {
      toast({ title: 'Failed to load', description: errMsg(e), variant: 'destructive' });
    } finally {
      setLoading(false);
    }
  }, [apptParams, isTodayBoard, dateFrom, dateTo, toast]);

  useEffect(() => { load(); }, [load]);

  const act = async (id, action) => {
    try {
      await axios.post(`/api/physiotherapy/appointments/${id}/${action}`);
      load();
    } catch (e) {
      toast({ title: 'Action failed', description: errMsg(e), variant: 'destructive' });
    }
  };

  const downloadPdf = async () => {
    if (!isTodayBoard && dateFrom && dateTo && dateFrom > dateTo) {
      toast({ title: 'Invalid range', description: 'From date must be on or before To date', variant: 'destructive' });
      return;
    }
    setExporting(true);
    try {
      const res = await axios.get('/api/physiotherapy/appointments/export.pdf', {
        params: apptParams,
        responseType: 'blob',
      });
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const header = await blob.slice(0, 5).text();
      if (!header.startsWith('%PDF')) {
        let msg = 'Server returned an unexpected response';
        try {
          const json = JSON.parse(await blob.text());
          if (typeof json.detail === 'string') msg = json.detail;
        } catch { /* ignore */ }
        throw new Error(msg);
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = isTodayBoard
        ? `physio_appointments_${dateFilter || todayISO()}.pdf`
        : `physio_appointments_${dateFrom}_to_${dateTo}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast({ title: 'Download failed', description: errMsg(e) || e.message, variant: 'destructive' });
    } finally {
      setExporting(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 flex-wrap">
        <CardTitle>{isTodayBoard ? "Today's board" : 'Appointments'}</CardTitle>
        <div className="flex gap-2 items-center flex-wrap">
          {!isTodayBoard && (
            <>
              <div className="flex items-center gap-1.5">
                <Label className="text-xs text-muted-foreground whitespace-nowrap">From</Label>
                <Input type="date" className="w-40" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
              </div>
              <div className="flex items-center gap-1.5">
                <Label className="text-xs text-muted-foreground whitespace-nowrap">To</Label>
                <Input type="date" className="w-40" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
              </div>
            </>
          )}
          <Button variant="outline" size="sm" onClick={load}><RefreshCw className="h-4 w-4" /></Button>
          <Button variant="outline" size="sm" onClick={downloadPdf} disabled={exporting}>
            {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4 mr-1" />}
            Download PDF
          </Button>
          {canSchedule && (
            <Button size="sm" onClick={() => { setBookPrefill({ package: null, patient: null }); setBookOpen(true); }}>
              <Plus className="h-4 w-4 mr-1" /> Book
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {loading ? <Loader2 className="animate-spin h-5 w-5" /> : (
          <div className="space-y-2">
            {rows.length === 0 && (
              <p className="text-sm text-muted-foreground">
                {isTodayBoard ? 'No sessions for this date.' : 'No sessions in this date range.'}
              </p>
            )}
            {rows.map((r) => (
              <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 border rounded-md p-3">
                <div>
                  <div className="font-medium">{r.patient_name}
                    <Badge className={`ml-2 ${STATUS_BADGE[r.status] || ''}`}>{r.status}</Badge>
                    {r.package_id && <Badge variant="outline" className="ml-1 text-xs">Package</Badge>}
                    {r.bill_id && <Badge variant="outline" className="ml-1 text-xs">Billed</Badge>}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {!isTodayBoard && r.appointment_date ? `${r.appointment_date} · ` : ''}
                    {r.appointment_time || '—'} · {r.therapist_name} · {r.service_name || r.session_type}
                    {r.appointment_number ? ` · ${r.appointment_number}` : ''}
                  </div>
                </div>
                <div className="flex gap-1 flex-wrap">
                  {canSchedule && r.status === 'scheduled' && (
                    <Button size="sm" variant="outline" onClick={() => act(r.id, 'check-in')}>
                      <CheckCircle2 className="h-3.5 w-3.5 mr-1" /> Check-in
                    </Button>
                  )}
                  {canAttend && ['scheduled', 'checked_in'].includes(r.status) && (
                    <Button size="sm" variant="outline" onClick={() => act(r.id, 'start')}>
                      <Play className="h-3.5 w-3.5 mr-1" /> Start
                    </Button>
                  )}
                  {canAttend && ['scheduled', 'checked_in', 'in_progress'].includes(r.status) && (
                    <Button size="sm" onClick={() => setCompleteAppt(r)}>Complete</Button>
                  )}
                  {canSchedule && ['scheduled', 'checked_in'].includes(r.status) && (
                    <Button size="sm" variant="ghost" onClick={() => act(r.id, 'no-show')}>
                      <UserX className="h-3.5 w-3.5 mr-1" /> No-show
                    </Button>
                  )}
                  {canSchedule && !['completed', 'cancelled'].includes(r.status) && (
                    <Button size="sm" variant="ghost" onClick={() => act(r.id, 'cancel')}>
                      <XCircle className="h-3.5 w-3.5 mr-1" /> Cancel
                    </Button>
                  )}
                  {r.bill_id && (
                    <Button size="sm" variant="outline" onClick={() => printPdfFromUrl(`/api/hospital/billing/bills/${r.bill_id}/pdf`)}>
                      Bill
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
      <BookDialog
        open={bookOpen}
        onOpenChange={(o) => { setBookOpen(o); if (!o) setBookPrefill({ package: null, patient: null }); }}
        onSaved={load}
        therapists={therapists}
        services={services}
        initialPackage={bookPrefill.package}
        initialPatient={bookPrefill.patient}
      />
      <CompleteDialog appt={completeAppt} open={!!completeAppt} onOpenChange={(o) => !o && setCompleteAppt(null)} onDone={load} />
    </Card>
  );
}

function TherapistsPage() {
  const { toast } = useToast();
  const { canSchedules } = usePhysioRoles();
  const [therapists, setTherapists] = useState([]);
  const [selected, setSelected] = useState(null);
  const [avail, setAvail] = useState(null);
  const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];

  const load = useCallback(async () => {
    try {
      const res = await axios.get('/api/physiotherapy/therapists');
      setTherapists(res.data || []);
    } catch (e) {
      toast({ title: 'Failed', description: errMsg(e), variant: 'destructive' });
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const loadAvail = async (id) => {
    setSelected(id);
    const res = await axios.get(`/api/physiotherapy/therapists/${id}/availability`);
    setAvail(res.data);
  };

  const save = async () => {
    try {
      await axios.put(`/api/physiotherapy/therapists/${selected}/availability`, {
        weekly_schedule: avail.weekly_schedule,
        default_session_duration: avail.default_session_duration,
        buffer_minutes: avail.buffer_minutes,
        max_advance_booking_days: avail.max_advance_booking_days,
      });
      toast({ title: 'Schedule saved' });
    } catch (e) {
      toast({ title: 'Save failed', description: errMsg(e), variant: 'destructive' });
    }
  };

  return (
    <div className="grid md:grid-cols-3 gap-4">
      <Card>
        <CardHeader><CardTitle>Therapists</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {therapists.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No users with the physiotherapist role. Create one under Administration → Users.
            </p>
          )}
          {therapists.map((t) => (
            <Button key={t.id} variant={selected === t.id ? 'default' : 'outline'} className="w-full justify-start" onClick={() => loadAvail(t.id)}>
              {t.full_name}
            </Button>
          ))}
        </CardContent>
      </Card>
      <Card className="md:col-span-2">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Weekly availability</CardTitle>
          {canSchedules && avail && <Button size="sm" onClick={save}>Save</Button>}
        </CardHeader>
        <CardContent>
          {!avail ? <p className="text-sm text-muted-foreground">Select a therapist</p> : (
            <div className="space-y-2">
              {days.map((d) => {
                const row = avail.weekly_schedule?.[d] || { enabled: false, start_time: '09:00', end_time: '17:00' };
                return (
                  <div key={d} className="flex items-center gap-2 text-sm">
                    <label className="w-28 capitalize flex items-center gap-2">
                      <input
                        type="checkbox"
                        disabled={!canSchedules}
                        checked={!!row.enabled}
                        onChange={(e) => setAvail({
                          ...avail,
                          weekly_schedule: {
                            ...avail.weekly_schedule,
                            [d]: { ...row, enabled: e.target.checked },
                          },
                        })}
                      />
                      {d}
                    </label>
                    <Input
                      type="time"
                      className="w-28"
                      disabled={!canSchedules || !row.enabled}
                      value={row.start_time || '09:00'}
                      onChange={(e) => setAvail({
                        ...avail,
                        weekly_schedule: {
                          ...avail.weekly_schedule,
                          [d]: { ...row, start_time: e.target.value },
                        },
                      })}
                    />
                    <span>to</span>
                    <Input
                      type="time"
                      className="w-28"
                      disabled={!canSchedules || !row.enabled}
                      value={row.end_time || '17:00'}
                      onChange={(e) => setAvail({
                        ...avail,
                        weekly_schedule: {
                          ...avail.weekly_schedule,
                          [d]: { ...row, end_time: e.target.value },
                        },
                      })}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ReportsPage() {
  const { toast } = useToast();
  const [from, setFrom] = useState(todayISO());
  const [to, setTo] = useState(todayISO());
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await axios.get('/api/physiotherapy/reports/summary', {
        params: { date_from: from, date_to: to },
      });
      setData(res.data);
    } catch (e) {
      toast({ title: 'Failed to load report', description: errMsg(e), variant: 'destructive' });
    }
  }, [from, to, toast]);

  useEffect(() => { load(); }, [load]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between flex-wrap gap-2">
        <CardTitle>Ops reports</CardTitle>
        <div className="flex gap-2 items-center">
          <Input type="date" className="w-36" value={from} onChange={(e) => setFrom(e.target.value)} />
          <Input type="date" className="w-36" value={to} onChange={(e) => setTo(e.target.value)} />
          <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-4 w-4" /></Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {!data ? <Loader2 className="animate-spin" /> : (
          <>
            <div className="grid sm:grid-cols-4 gap-3">
              <div className="border rounded-md p-3"><div className="text-xs text-muted-foreground">Sessions</div><div className="text-xl font-semibold">{data.total_sessions}</div></div>
              <div className="border rounded-md p-3"><div className="text-xs text-muted-foreground">Collections</div><div className="text-xl font-semibold">{fmt(data.collections?.total)}</div></div>
              <div className="border rounded-md p-3"><div className="text-xs text-muted-foreground">Outstanding</div><div className="text-xl font-semibold">{fmt(data.outstanding_dues)}</div></div>
              <div className="border rounded-md p-3"><div className="text-xs text-muted-foreground">Sessions owed</div><div className="text-xl font-semibold">{data.package_liability?.sessions_owed || 0}</div></div>
            </div>
            <div>
              <h4 className="font-medium mb-2">Collections by method</h4>
              <p className="text-sm">Cash {fmt(data.collections?.cash)} · UPI {fmt(data.collections?.upi)} · Card {fmt(data.collections?.card)} · Other {fmt(data.collections?.other)}</p>
            </div>
            <div>
              <h4 className="font-medium mb-2">Therapist utilization</h4>
              <table className="w-full text-sm">
                <thead><tr className="border-b text-left"><th className="py-1">Therapist</th><th>Completed</th><th>No-show</th><th>Cancelled</th><th>Scheduled</th></tr></thead>
                <tbody>
                  {(data.therapist_utilization || []).map((t) => (
                    <tr key={t.therapist_id} className="border-b">
                      <td className="py-1">{t.therapist_name}</td>
                      <td>{t.completed}</td>
                      <td>{t.no_show}</td>
                      <td>{t.cancelled}</td>
                      <td>{t.scheduled}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function PhysiotherapyModule() {
  const { canPackages } = usePhysioRoles();
  const [sellOpen, setSellOpen] = useState(false);
  const [sellTick, setSellTick] = useState(0);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Physiotherapy</h1>
        <p className="text-sm text-muted-foreground">Clinic sessions, packages, and billing</p>
      </div>
      <NavTabs
        canSellPackage={canPackages}
        onSellPackage={() => setSellOpen(true)}
      />
      <SellPackageDialog
        open={sellOpen}
        onOpenChange={setSellOpen}
        onSold={() => setSellTick((n) => n + 1)}
      />
      <Routes>
        <Route index element={<Navigate to="today" replace />} />
        <Route path="today" element={<AppointmentsBoard dateFilter={todayISO()} />} />
        <Route path="appointments" element={<AppointmentsBoard />} />
        <Route path="packages" element={<PackagesPage key={sellTick} />} />
        <Route path="catalog" element={<CatalogPage />} />
        <Route path="therapists" element={<TherapistsPage />} />
        <Route path="reports" element={<ReportsPage />} />
      </Routes>
    </div>
  );
}
