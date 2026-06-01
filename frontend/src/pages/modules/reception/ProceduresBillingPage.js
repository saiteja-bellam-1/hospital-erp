import React, { useState, useEffect, useCallback, useMemo } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import { Textarea } from '../../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../../components/ui/tabs';
import { useToast } from '../../../hooks/use-toast';
import { useAuth } from '../../../contexts/AuthContext';
import { printPdfFromUrl } from '../../../utils/printPdf';
import {
  Loader2, Plus, Trash2, Printer, Receipt, Edit2, FileText, RefreshCw,
} from 'lucide-react';

const fmt = (n) => `₹${Number(n || 0).toFixed(2)}`;

const ProceduresBillingPage = () => {
  const { toast } = useToast();
  const { user } = useAuth();
  const roles = useMemo(() => (
    Array.isArray(user?.roles) ? user.roles
      : typeof user?.role === 'string' ? [user.role] : []
  ), [user]);
  const isAdmin = roles.some((r) => ['super_admin', 'hospital_admin'].includes(r));

  const [tab, setTab] = useState('generate');
  const [procedures, setProcedures] = useState([]);
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(false);

  // Referrals
  const [referrals, setReferrals] = useState([]);
  const [referredBy, setReferredBy] = useState('');

  // Patient search
  const [patientQuery, setPatientQuery] = useState('');
  const [patientResults, setPatientResults] = useState([]);
  const [patient, setPatient] = useState(null);

  // Bill builder
  const [lines, setLines] = useState([{ kind: 'catalog', procedure_id: '', item_name: '', quantity: 1, unit_price: '' }]);
  const [discount, setDiscount] = useState('');
  const [taxPct, setTaxPct] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Catalog dialog
  const [catalogDialog, setCatalogDialog] = useState({ open: false, mode: 'create', form: { name: '', code: '', category: '', default_price: '', description: '', is_active: true } });

  const fetchProcedures = useCallback(async (includeInactive = false) => {
    try {
      const res = await axios.get(`/api/outpatient/procedures?include_inactive=${includeInactive}`);
      setProcedures(res.data || []);
    } catch (_) { setProcedures([]); }
  }, []);

  const fetchRecent = useCallback(async () => {
    try {
      const res = await axios.get('/api/outpatient/procedure-bills?limit=100');
      setRecent(res.data || []);
    } catch (_) { setRecent([]); }
  }, []);

  const fetchReferrals = useCallback(async () => {
    try {
      const res = await axios.get('/api/referrals/all');
      setReferrals(res.data || []);
    } catch (_) {
      try {
        const res = await axios.get('/api/referrals');
        setReferrals(res.data || []);
      } catch (__) { setReferrals([]); }
    }
  }, []);

  useEffect(() => { fetchProcedures(); fetchRecent(); fetchReferrals(); }, [fetchProcedures, fetchRecent, fetchReferrals]);

  // ------- Patient search -------
  const searchPatients = async (q) => {
    setPatientQuery(q);
    if (q.trim().length < 2) { setPatientResults([]); return; }
    try {
      const res = await axios.post('/api/patients/search', { search_term: q.trim() });
      setPatientResults((res.data?.patients || []).slice(0, 8));
    } catch (_) { setPatientResults([]); }
  };

  // ------- Bill builder helpers -------
  const updateLine = (idx, patch) => {
    setLines((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], ...patch };
      return next;
    });
  };
  const addLine = () => setLines((prev) => [...prev, { kind: 'catalog', procedure_id: '', item_name: '', quantity: 1, unit_price: '' }]);
  const removeLine = (idx) => setLines((prev) => prev.filter((_, i) => i !== idx));

  const lineTotal = (line) => {
    let unit = 0;
    if (line.kind === 'catalog' && line.procedure_id) {
      const p = procedures.find((x) => String(x.id) === String(line.procedure_id));
      unit = line.unit_price !== '' ? parseFloat(line.unit_price) : (p?.default_price || 0);
    } else {
      unit = parseFloat(line.unit_price) || 0;
    }
    const qty = parseInt(line.quantity) || 0;
    return Math.max(0, unit * qty);
  };
  const subtotal = lines.reduce((s, l) => s + lineTotal(l), 0);
  const discountVal = Math.min(parseFloat(discount) || 0, subtotal);
  const taxVal = (subtotal - discountVal) * ((parseFloat(taxPct) || 0) / 100);
  const total = subtotal - discountVal + taxVal;

  const resetBuilder = () => {
    setPatient(null);
    setPatientQuery('');
    setLines([{ kind: 'catalog', procedure_id: '', item_name: '', quantity: 1, unit_price: '' }]);
    setDiscount(''); setTaxPct(''); setNotes(''); setReferredBy('');
  };

  const submitBill = async (print = true) => {
    if (!patient) {
      toast({ variant: 'destructive', title: 'Pick a patient' });
      return;
    }
    const payloadItems = lines.map((l) => {
      if (l.kind === 'catalog' && l.procedure_id) {
        return {
          procedure_id: parseInt(l.procedure_id),
          quantity: parseInt(l.quantity) || 1,
          ...(l.unit_price !== '' ? { unit_price: parseFloat(l.unit_price) } : {}),
        };
      }
      return {
        item_name: (l.item_name || '').trim(),
        quantity: parseInt(l.quantity) || 1,
        unit_price: parseFloat(l.unit_price) || 0,
      };
    }).filter((it) => it.procedure_id || (it.item_name && it.unit_price > 0));
    if (!payloadItems.length) {
      toast({ variant: 'destructive', title: 'Add at least one line' });
      return;
    }
    setSubmitting(true);
    try {
      const r = await axios.post('/api/outpatient/procedure-bills', {
        patient_id: patient.id,
        items: payloadItems,
        discount_amount: parseFloat(discount) || 0,
        tax_percentage: parseFloat(taxPct) || 0,
        notes: notes || null,
        referred_by: referredBy ? referredBy.trim() : null,
      });
      toast({ title: 'Bill created', description: `${r.data.bill_number} — ${fmt(r.data.total_amount)}` });
      if (print && r.data.bill_id) {
        try {
          const pdf = await axios.get(
            `/api/hospital/billing/bills/${r.data.bill_id}/pdf`,
            { responseType: 'blob' },
          );
          const url = URL.createObjectURL(new Blob([pdf.data], { type: 'application/pdf' }));
          printPdfFromUrl(url);
          setTimeout(() => URL.revokeObjectURL(url), 60_000);
        } catch (_) { /* receipt is best-effort */ }
      }
      resetBuilder();
      fetchRecent();
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast({ variant: 'destructive', title: 'Failed', description: typeof detail === 'string' ? detail : 'Could not create bill' });
    } finally { setSubmitting(false); }
  };

  // ------- Catalog CRUD -------
  const openCreate = () => setCatalogDialog({ open: true, mode: 'create',
    form: { name: '', code: '', category: '', default_price: '', description: '', is_active: true } });
  const openEdit = (p) => setCatalogDialog({ open: true, mode: 'edit',
    form: { id: p.id, name: p.name, code: p.code || '', category: p.category || '',
            default_price: p.default_price, description: p.description || '', is_active: p.is_active } });

  const submitCatalog = async () => {
    const f = catalogDialog.form;
    if (!f.name.trim() || !(f.default_price >= 0)) {
      toast({ variant: 'destructive', title: 'Name and price are required' });
      return;
    }
    try {
      const payload = {
        name: f.name.trim(), code: f.code || null, category: f.category || null,
        default_price: parseFloat(f.default_price), description: f.description || null,
        is_active: !!f.is_active,
      };
      if (catalogDialog.mode === 'edit') {
        await axios.patch(`/api/outpatient/procedures/${f.id}`, payload);
      } else {
        await axios.post('/api/outpatient/procedures', payload);
      }
      toast({ title: 'Procedure saved' });
      setCatalogDialog({ ...catalogDialog, open: false });
      fetchProcedures(true);
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast({ variant: 'destructive', title: 'Save failed', description: typeof detail === 'string' ? detail : '' });
    }
  };

  const deactivate = async (p) => {
    if (!window.confirm(`Deactivate "${p.name}"? Existing bills are unaffected.`)) return;
    try {
      await axios.delete(`/api/outpatient/procedures/${p.id}`);
      toast({ title: 'Deactivated' });
      fetchProcedures(true);
    } catch (_) {
      toast({ variant: 'destructive', title: 'Could not deactivate' });
    }
  };

  // ------- Print existing bill -------
  const printBill = async (billId) => {
    try {
      const pdf = await axios.get(
        `/api/hospital/billing/bills/${billId}/pdf`,
        { responseType: 'blob' },
      );
      const url = URL.createObjectURL(new Blob([pdf.data], { type: 'application/pdf' }));
      printPdfFromUrl(url);
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (_) {
      toast({ variant: 'destructive', title: 'Could not load PDF' });
    }
  };

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Day Care Billing</h1>
          <p className="text-sm text-muted-foreground">Bill walk-in services from your day-care catalog or one-off items.</p>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="generate"><Receipt className="h-4 w-4 mr-1" /> Generate Bill</TabsTrigger>
          <TabsTrigger value="recent"><FileText className="h-4 w-4 mr-1" /> Recent Bills</TabsTrigger>
          {isAdmin && <TabsTrigger value="catalog"><Edit2 className="h-4 w-4 mr-1" /> Service Catalog</TabsTrigger>}
        </TabsList>

        {/* --- Generate Bill --- single card with internal dividers for a tighter layout */}
        <TabsContent value="generate" className="mt-4">
          <Card>
            <CardContent className="pt-4 space-y-4">
              {/* Patient + Referred-by row */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="md:col-span-2 relative">
                  <Label className="text-xs">Patient *</Label>
                  {patient ? (
                    <div className="flex items-center justify-between bg-blue-50 rounded p-2 mt-1">
                      <span className="text-sm">
                        <span className="font-semibold">{patient.first_name} {patient.last_name}</span>
                        <span className="text-xs text-gray-500 ml-2">{patient.primary_phone}</span>
                        <span className="text-xs text-gray-400 ml-2">MRN: {patient.patient_id}</span>
                      </span>
                      <Button size="sm" variant="ghost" onClick={() => { setPatient(null); setPatientResults([]); }}>Change</Button>
                    </div>
                  ) : (
                    <>
                      <Input placeholder="Search by name or phone..." value={patientQuery}
                        onChange={(e) => searchPatients(e.target.value)} />
                      {patientResults.length > 0 && (
                        <div className="absolute z-20 mt-1 w-full bg-white border rounded shadow max-h-48 overflow-auto">
                          {patientResults.map((p) => (
                            <button key={p.id} type="button"
                              className="block w-full text-left px-3 py-2 text-sm hover:bg-gray-100"
                              onClick={() => { setPatient(p); setPatientResults([]); }}>
                              {p.first_name} {p.last_name}
                              <span className="text-xs text-gray-500 ml-2">{p.primary_phone}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
                <div>
                  <Label className="text-xs">Referred by</Label>
                  <Select value={referredBy || '__none__'} onValueChange={(v) => setReferredBy(v === '__none__' ? '' : v)}>
                    <SelectTrigger><SelectValue placeholder="Self" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">Self</SelectItem>
                      {referrals.length === 0 && (
                        <SelectItem value="_empty" disabled>No referrals configured</SelectItem>
                      )}
                      {referrals.map((r) => (
                        <SelectItem key={r.id} value={r.name}>
                          {r.name}{r.specialization ? ` — ${r.specialization}` : ''}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="border-t pt-3">
                <div className="flex items-center justify-between mb-2">
                  <Label className="text-sm font-semibold">Line items</Label>
                  <Button variant="outline" size="sm" onClick={addLine}>
                    <Plus className="h-3.5 w-3.5 mr-1" /> Add line
                  </Button>
                </div>
                <div className="space-y-2">
                  {lines.map((line, idx) => (
                    <div key={idx} className="grid grid-cols-12 gap-2 items-center">
                      <Select value={line.kind} onValueChange={(v) => updateLine(idx, { kind: v, procedure_id: '', item_name: '', unit_price: '' })}>
                        <SelectTrigger className="col-span-2 h-9 text-xs"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="catalog">Catalog</SelectItem>
                          <SelectItem value="custom">Custom</SelectItem>
                        </SelectContent>
                      </Select>
                      {line.kind === 'catalog' ? (
                        <Select value={String(line.procedure_id || '')}
                          onValueChange={(v) => updateLine(idx, { procedure_id: v })}>
                          <SelectTrigger className="col-span-5 h-9 text-xs"><SelectValue placeholder="Pick a service" /></SelectTrigger>
                          <SelectContent>
                            {procedures.length === 0 && <SelectItem value="_none" disabled>No services in catalog</SelectItem>}
                            {procedures.map((p) => (
                              <SelectItem key={p.id} value={String(p.id)}>
                                {p.name} {p.code ? `(${p.code})` : ''} — {fmt(p.default_price)}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <Input className="col-span-5 h-9 text-xs" placeholder="Service description"
                          value={line.item_name}
                          onChange={(e) => updateLine(idx, { item_name: e.target.value })} />
                      )}
                      <Input className="col-span-1 h-9 text-xs" type="number" min="1" placeholder="Qty"
                        value={line.quantity} onChange={(e) => updateLine(idx, { quantity: e.target.value })} />
                      <Input className="col-span-2 h-9 text-xs" type="number" min="0" step="0.01"
                        placeholder={line.kind === 'catalog' ? 'override price (optional)' : 'unit price'}
                        value={line.unit_price}
                        onChange={(e) => updateLine(idx, { unit_price: e.target.value })} />
                      <div className="col-span-1 text-xs text-right font-semibold">{fmt(lineTotal(line))}</div>
                      <Button variant="ghost" size="sm" className="col-span-1 text-red-600"
                        disabled={lines.length === 1} onClick={() => removeLine(idx)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>

              <div className="border-t pt-3 grid grid-cols-2 md:grid-cols-4 gap-3 items-end">
                <div>
                  <Label className="text-xs">Discount (₹)</Label>
                  <Input type="number" min="0" step="0.01" value={discount} onChange={(e) => setDiscount(e.target.value)} />
                </div>
                <div>
                  <Label className="text-xs">Tax %</Label>
                  <Input type="number" min="0" max="100" step="0.01" value={taxPct} onChange={(e) => setTaxPct(e.target.value)} />
                </div>
                <div className="col-span-2">
                  <Label className="text-xs">Notes <span className="text-gray-400">(printed on the bill)</span></Label>
                  <Textarea rows={1} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional remarks (shown on receipt)" />
                </div>
              </div>

              <div className="border-t pt-3 flex flex-wrap items-end justify-between gap-3">
                <div className="space-y-0.5 text-sm">
                  <div className="flex gap-3"><span className="text-gray-500 w-20">Subtotal:</span><span className="font-semibold">{fmt(subtotal)}</span></div>
                  <div className="flex gap-3"><span className="text-gray-500 w-20">Discount:</span><span className="font-semibold">-{fmt(discountVal)}</span></div>
                  <div className="flex gap-3"><span className="text-gray-500 w-20">Tax:</span><span className="font-semibold">{fmt(taxVal)}</span></div>
                  <div className="flex gap-3 text-lg"><span className="text-gray-700 w-20">Total:</span><span className="font-bold">{fmt(total)}</span></div>
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" onClick={resetBuilder}>Reset</Button>
                  <Button variant="outline" disabled={submitting || total <= 0 || !patient} onClick={() => submitBill(false)}>
                    Save only
                  </Button>
                  <Button disabled={submitting || total <= 0 || !patient} onClick={() => submitBill(true)}>
                    {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Printer className="h-4 w-4 mr-1" /> Create &amp; Print</>}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* --- Recent --- */}
        <TabsContent value="recent" className="space-y-3 mt-4">
          <div className="flex justify-end">
            <Button variant="outline" size="sm" onClick={fetchRecent}>
              <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
            </Button>
          </div>
          <Card>
            <CardContent className="pt-4">
              {recent.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-6">No procedure bills yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead><tr className="border-b text-left text-gray-500">
                      <th className="pb-2 pr-3">Bill #</th>
                      <th className="pb-2 pr-3">Date</th>
                      <th className="pb-2 pr-3">Patient</th>
                      <th className="pb-2 pr-3 text-right">Total</th>
                      <th className="pb-2 pr-3 text-right">Balance</th>
                      <th className="pb-2 pr-3">Status</th>
                      <th className="pb-2 pr-3"></th>
                    </tr></thead>
                    <tbody>
                      {recent.map((b) => (
                        <tr key={b.bill_id} className="border-b">
                          <td className="py-2 pr-3 font-mono text-xs">{b.bill_number}</td>
                          <td className="py-2 pr-3 text-xs">{b.bill_date ? new Date(b.bill_date).toLocaleString() : ''}</td>
                          <td className="py-2 pr-3">{b.patient_name} <span className="text-xs text-gray-400">{b.patient_phone}</span></td>
                          <td className="py-2 pr-3 text-right font-semibold">{fmt(b.total_amount)}</td>
                          <td className="py-2 pr-3 text-right">{b.balance_due > 0 ? fmt(b.balance_due) : '—'}</td>
                          <td className="py-2 pr-3"><Badge variant="outline" className="text-xs capitalize">{b.status}</Badge></td>
                          <td className="py-2 pr-3 text-right">
                            <Button variant="ghost" size="sm" onClick={() => printBill(b.bill_id)}>
                              <Printer className="h-3.5 w-3.5" />
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* --- Catalog --- */}
        {isAdmin && (
          <TabsContent value="catalog" className="space-y-3 mt-4">
            <div className="flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => fetchProcedures(true)}>
                <RefreshCw className="h-3.5 w-3.5 mr-1" /> Refresh
              </Button>
              <Button size="sm" onClick={openCreate}>
                <Plus className="h-4 w-4 mr-1" /> New Service
              </Button>
            </div>
            <Card>
              <CardContent className="pt-4">
                {procedures.length === 0 ? (
                  <p className="text-sm text-gray-500 text-center py-6">No day-care services yet. Add your first.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead><tr className="border-b text-left text-gray-500">
                        <th className="pb-2 pr-3">Name</th>
                        <th className="pb-2 pr-3">Code</th>
                        <th className="pb-2 pr-3">Category</th>
                        <th className="pb-2 pr-3 text-right">Price</th>
                        <th className="pb-2 pr-3">Active</th>
                        <th className="pb-2 pr-3"></th>
                      </tr></thead>
                      <tbody>
                        {procedures.map((p) => (
                          <tr key={p.id} className={`border-b ${!p.is_active ? 'opacity-50' : ''}`}>
                            <td className="py-2 pr-3 font-medium">{p.name}</td>
                            <td className="py-2 pr-3 font-mono text-xs">{p.code || '—'}</td>
                            <td className="py-2 pr-3 text-xs">{p.category || '—'}</td>
                            <td className="py-2 pr-3 text-right">{fmt(p.default_price)}</td>
                            <td className="py-2 pr-3">{p.is_active ? <Badge className="bg-green-100 text-green-800 text-xs">active</Badge> : <Badge variant="outline" className="text-xs">inactive</Badge>}</td>
                            <td className="py-2 pr-3 text-right">
                              <Button variant="ghost" size="sm" onClick={() => openEdit(p)}><Edit2 className="h-3.5 w-3.5" /></Button>
                              {p.is_active && <Button variant="ghost" size="sm" className="text-red-600" onClick={() => deactivate(p)}><Trash2 className="h-3.5 w-3.5" /></Button>}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>

      {/* Catalog dialog */}
      <Dialog open={catalogDialog.open} onOpenChange={(o) => !o && setCatalogDialog({ ...catalogDialog, open: false })}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>{catalogDialog.mode === 'edit' ? 'Edit Service' : 'New Day-Care Service'}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Name *</Label>
              <Input value={catalogDialog.form.name}
                onChange={(e) => setCatalogDialog({ ...catalogDialog, form: { ...catalogDialog.form, name: e.target.value } })} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Code</Label>
                <Input value={catalogDialog.form.code}
                  onChange={(e) => setCatalogDialog({ ...catalogDialog, form: { ...catalogDialog.form, code: e.target.value } })} />
              </div>
              <div>
                <Label className="text-xs">Category</Label>
                <Input value={catalogDialog.form.category}
                  onChange={(e) => setCatalogDialog({ ...catalogDialog, form: { ...catalogDialog.form, category: e.target.value } })} />
              </div>
            </div>
            <div>
              <Label className="text-xs">Default Price (₹) *</Label>
              <Input type="number" min="0" step="0.01" value={catalogDialog.form.default_price}
                onChange={(e) => setCatalogDialog({ ...catalogDialog, form: { ...catalogDialog.form, default_price: e.target.value } })} />
            </div>
            <div>
              <Label className="text-xs">Description</Label>
              <Textarea rows={2} value={catalogDialog.form.description}
                onChange={(e) => setCatalogDialog({ ...catalogDialog, form: { ...catalogDialog.form, description: e.target.value } })} />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={catalogDialog.form.is_active}
                onChange={(e) => setCatalogDialog({ ...catalogDialog, form: { ...catalogDialog.form, is_active: e.target.checked } })} />
              Active
            </label>
            <div className="flex justify-end gap-2 pt-2 border-t">
              <Button variant="outline" onClick={() => setCatalogDialog({ ...catalogDialog, open: false })}>Cancel</Button>
              <Button onClick={submitCatalog}>Save</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ProceduresBillingPage;
