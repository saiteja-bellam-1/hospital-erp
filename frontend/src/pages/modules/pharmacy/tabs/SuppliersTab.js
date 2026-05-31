import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import { Input } from '../../../../components/ui/input';
import { Label } from '../../../../components/ui/label';
import { Textarea } from '../../../../components/ui/textarea';
import { Badge } from '../../../../components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../../../../components/ui/dialog';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../../components/ui/select';
import { useToast } from '../../../../hooks/use-toast';
import { Plus, Pencil, Trash2, RefreshCw, Search } from 'lucide-react';
import { errMsg } from '../../PharmacyModule';

const BLANK = {
  name: '',
  // Accounting
  station: '', account_group: 'Sundry Creditors', balancing_method: 'bill_by_bill',
  opening_balance: 0, opening_balance_dr_cr: 'Dr',
  hold_payment: false, hold_payment_pct: 0, ledger_date: '', freeze_upto: '',
  // Contact
  contact_person: '', designation: '',
  phone_office: '', phone_residence: '', mobile: '', phone: '',
  fax: '', email: '', website: '',
  // Address
  mail_to: '', address: '', pin_code: '',
  state: '', state_code: '', country: 'India',
  // GST
  gst_heading: 'local', gstin: '', gstin_no: '', gstin_date: '',
  // Licenses
  dl_number: '', dl_expiry: '',
  vat_number: '', vat_expiry: '',
  st_number: '', st_expiry: '',
  food_license_no: '', food_license_expiry: '',
  extra_license_no: '', extra_license_expiry: '',
  pan_number: '',
  // Misc
  narco_sch_h_billing: 'allow_all', bill_import: 'mobile',
  ledger_category: 'OTHERS', ledger_type: 'unregistered',
  color_tag: 'normal', is_hidden: false, is_active: true,
};

export default function SuppliersTab() {
  const { toast } = useToast();
  const [rows, setRows] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(BLANK);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get('/api/pharmacy/suppliers', { params: { active_only: false } });
      setRows(r.data || []);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Load failed', description: errMsg(e) });
    } finally { setLoading(false); }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const openCreate = () => { setEditing(null); setForm(BLANK); setOpen(true); };
  const openEdit = (row) => {
    setEditing(row);
    // Coerce nulls → ''/0/false to keep inputs controlled
    const f = { ...BLANK };
    Object.keys(BLANK).forEach(k => {
      const v = row[k];
      if (v === null || v === undefined) {
        f[k] = BLANK[k];
      } else {
        f[k] = v;
      }
    });
    setForm(f);
    setOpen(true);
  };

  const save = async () => {
    try {
      // Convert empty-string dates to null so Pydantic accepts them
      const payload = { ...form };
      ['ledger_date', 'freeze_upto', 'gstin_date', 'dl_expiry', 'vat_expiry',
       'st_expiry', 'food_license_expiry', 'extra_license_expiry'].forEach(k => {
        if (payload[k] === '' || payload[k] === undefined) payload[k] = null;
      });
      if (editing) {
        await axios.put(`/api/pharmacy/suppliers/${editing.id}`, payload);
        toast({ title: 'Supplier updated' });
      } else {
        await axios.post('/api/pharmacy/suppliers', payload);
        toast({ title: 'Supplier created' });
      }
      setOpen(false); load();
    } catch (e) {
      toast({ variant: 'destructive', title: 'Save failed', description: errMsg(e) });
    }
  };

  const remove = async (row) => {
    if (!window.confirm(`Delete supplier "${row.name}"?`)) return;
    try { await axios.delete(`/api/pharmacy/suppliers/${row.id}`); toast({ title: 'Deleted' }); load(); }
    catch (e) { toast({ variant: 'destructive', title: 'Delete failed', description: errMsg(e) }); }
  };

  const set = (k, v) => setForm(s => ({ ...s, [k]: v }));

  const filtered = rows.filter(r => {
    if (!search) return true;
    const hay = `${r.name} ${r.mobile || ''} ${r.gstin_no || r.gstin || ''} ${r.dl_number || ''}`.toLowerCase();
    return hay.includes(search.toLowerCase());
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between flex-wrap gap-2">
          <span>Suppliers ({filtered.length})</span>
          <div className="flex gap-2 items-center">
            <div className="relative">
              <Search className="absolute left-2 top-2.5 h-4 w-4 text-gray-400" />
              <Input className="pl-8 h-8 w-56" placeholder="Search name / mobile / GSTIN / DL…"
                value={search} onChange={e => setSearch(e.target.value)} />
            </div>
            <Button size="sm" variant="outline" onClick={load}><RefreshCw className="h-3 w-3" /></Button>
            <Button size="sm" onClick={openCreate}><Plus className="h-3 w-3 mr-1" /> New Supplier</Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? <p className="text-center py-6 text-gray-500 text-sm">Loading…</p>
          : filtered.length === 0 ? <p className="text-center py-6 text-gray-500 text-sm">No suppliers</p>
          : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b text-left text-gray-600">
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Mobile</th>
                  <th className="py-2 pr-4">GSTIN</th>
                  <th className="py-2 pr-4">DL No.</th>
                  <th className="py-2 pr-4">DL Exp.</th>
                  <th className="py-2 pr-4">State</th>
                  <th className="py-2 pr-4">Type</th>
                  <th className="py-2 pr-4">Status</th>
                  <th className="py-2 text-right">Actions</th>
                </tr></thead>
                <tbody>
                  {filtered.map(s => (
                    <tr key={s.id} className="border-b hover:bg-gray-50">
                      <td className="py-2 pr-4">
                        <div className="font-medium">{s.name}</div>
                        {s.contact_person && <div className="text-xs text-gray-500">{s.contact_person}</div>}
                      </td>
                      <td className="py-2 pr-4 text-xs">{s.mobile || s.phone || '—'}</td>
                      <td className="py-2 pr-4 font-mono text-xs">{s.gstin_no || s.gstin || '—'}</td>
                      <td className="py-2 pr-4 text-xs">{s.dl_number || '—'}</td>
                      <td className="py-2 pr-4 text-xs">{s.dl_expiry || '—'}</td>
                      <td className="py-2 pr-4 text-xs">{s.state_code ? `${s.state_code}-${s.state || ''}` : (s.state || '—')}</td>
                      <td className="py-2 pr-4">
                        <Badge variant="outline" className="text-[10px]">{s.ledger_type || 'unregistered'}</Badge>
                      </td>
                      <td className="py-2 pr-4">
                        {!s.is_active && <Badge variant="outline" className="text-xs text-gray-400">Deleted</Badge>}
                        {s.is_active && s.is_hidden && <Badge variant="outline" className="text-xs text-gray-500">Hidden</Badge>}
                        {s.is_active && !s.is_hidden && <Badge variant="outline" className="text-xs">Active</Badge>}
                      </td>
                      <td className="py-2 text-right">
                        <Button size="sm" variant="ghost" onClick={() => openEdit(s)}><Pencil className="h-3 w-3" /></Button>
                        <Button size="sm" variant="ghost" onClick={() => remove(s)}><Trash2 className="h-3 w-3 text-red-500" /></Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-5xl max-h-[88vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing ? `Edit Supplier — ${editing.name}` : 'New Supplier'}</DialogTitle>
          </DialogHeader>

          <Section title="Basic">
            <Grid>
              <F label="Ledger Name *" colSpan={2}><Input value={form.name} onChange={e => set('name', e.target.value)} /></F>
              <F label="Station"><Input value={form.station} onChange={e => set('station', e.target.value)} /></F>
              <F label="Account Group"><Input value={form.account_group} onChange={e => set('account_group', e.target.value)} /></F>
              <F label="Balancing Method">
                <Sel value={form.balancing_method} onChange={v => set('balancing_method', v)}
                  options={[['bill_by_bill','Bill by Bill'],['on_account','On Account']]} />
              </F>
              <F label="Opening Balance"><Num value={form.opening_balance} onChange={v => set('opening_balance', v)} /></F>
              <F label="Dr / Cr">
                <Sel value={form.opening_balance_dr_cr} onChange={v => set('opening_balance_dr_cr', v)}
                  options={[['Dr','Dr'],['Cr','Cr']]} />
              </F>
              <F label="Hold Payment"><Check checked={form.hold_payment} onChange={v => set('hold_payment', v)} /></F>
              <F label="% (if GSTR1 not uploaded)"><Num value={form.hold_payment_pct} onChange={v => set('hold_payment_pct', v)} /></F>
              <F label="Ledger Date"><Input type="date" value={form.ledger_date || ''} onChange={e => set('ledger_date', e.target.value)} /></F>
              <F label="Freeze Upto"><Input type="date" value={form.freeze_upto || ''} onChange={e => set('freeze_upto', e.target.value)} /></F>
            </Grid>
          </Section>

          <Section title="Contact">
            <Grid>
              <F label="Contact Person"><Input value={form.contact_person} onChange={e => set('contact_person', e.target.value)} /></F>
              <F label="Designation"><Input value={form.designation} onChange={e => set('designation', e.target.value)} /></F>
              <F label="Mobile"><Input value={form.mobile} onChange={e => set('mobile', e.target.value)} /></F>
              <F label="Phone (Off.)"><Input value={form.phone_office} onChange={e => set('phone_office', e.target.value)} /></F>
              <F label="Phone (Res.)"><Input value={form.phone_residence} onChange={e => set('phone_residence', e.target.value)} /></F>
              <F label="Fax"><Input value={form.fax} onChange={e => set('fax', e.target.value)} /></F>
              <F label="Email"><Input value={form.email} onChange={e => set('email', e.target.value)} /></F>
              <F label="Web Site"><Input value={form.website} onChange={e => set('website', e.target.value)} /></F>
            </Grid>
          </Section>

          <Section title="Address">
            <Grid>
              <F label="Mail to" colSpan={2}><Input value={form.mail_to} onChange={e => set('mail_to', e.target.value)} /></F>
              <F label="Address" colSpan={3}><Textarea rows={2} value={form.address} onChange={e => set('address', e.target.value)} /></F>
              <F label="Pin Code"><Input value={form.pin_code} onChange={e => set('pin_code', e.target.value)} /></F>
              <F label="State"><Input value={form.state} onChange={e => set('state', e.target.value)} placeholder="TELANGANA" /></F>
              <F label="State Code"><Input value={form.state_code} onChange={e => set('state_code', e.target.value)} placeholder="36" /></F>
              <F label="Country"><Input value={form.country} onChange={e => set('country', e.target.value)} /></F>
            </Grid>
          </Section>

          <Section title="GST & Licenses">
            <Grid>
              <F label="GST Heading">
                <Sel value={form.gst_heading} onChange={v => set('gst_heading', v)}
                  options={[['local','Local'],['interstate','Interstate'],['composition','Composition'],['exempt','Exempt']]} />
              </F>
              <F label="Ledger Type">
                <Sel value={form.ledger_type} onChange={v => set('ledger_type', v)}
                  options={[['registered','Registered'],['unregistered','Unregistered'],['composition','Composition']]} />
              </F>
              <F label="GSTIN No."><Input value={form.gstin_no} onChange={e => set('gstin_no', e.target.value)} /></F>
              <F label="GSTIN Date"><Input type="date" value={form.gstin_date || ''} onChange={e => set('gstin_date', e.target.value)} /></F>
              <F label="D.L. No."><Input value={form.dl_number} onChange={e => set('dl_number', e.target.value)} /></F>
              <F label="D.L. Exp."><Input type="date" value={form.dl_expiry || ''} onChange={e => set('dl_expiry', e.target.value)} /></F>
              <F label="VAT No."><Input value={form.vat_number} onChange={e => set('vat_number', e.target.value)} /></F>
              <F label="VAT Exp."><Input type="date" value={form.vat_expiry || ''} onChange={e => set('vat_expiry', e.target.value)} /></F>
              <F label="S.T. No."><Input value={form.st_number} onChange={e => set('st_number', e.target.value)} /></F>
              <F label="S.T. Exp."><Input type="date" value={form.st_expiry || ''} onChange={e => set('st_expiry', e.target.value)} /></F>
              <F label="Food Licence No."><Input value={form.food_license_no} onChange={e => set('food_license_no', e.target.value)} /></F>
              <F label="Food Licence Exp."><Input type="date" value={form.food_license_expiry || ''} onChange={e => set('food_license_expiry', e.target.value)} /></F>
              <F label="Extra Heading No."><Input value={form.extra_license_no} onChange={e => set('extra_license_no', e.target.value)} /></F>
              <F label="Extra Heading Exp."><Input type="date" value={form.extra_license_expiry || ''} onChange={e => set('extra_license_expiry', e.target.value)} /></F>
              <F label="I.T. PAN No."><Input value={form.pan_number} onChange={e => set('pan_number', e.target.value)} /></F>
            </Grid>
          </Section>

          <Section title="Misc">
            <Grid>
              <F label="Narco / Sch-H Item Billing">
                <Sel value={form.narco_sch_h_billing} onChange={v => set('narco_sch_h_billing', v)}
                  options={[['allow_all','Allow All'],['restrict','Restrict'],['block','Block']]} />
              </F>
              <F label="Bill Import">
                <Sel value={form.bill_import} onChange={v => set('bill_import', v)}
                  options={[['mobile','Mobile'],['erp','ERP to ERP'],['manual','Manual']]} />
              </F>
              <F label="Ledger Category"><Input value={form.ledger_category} onChange={e => set('ledger_category', e.target.value)} /></F>
              <F label="Color Tag">
                <Sel value={form.color_tag} onChange={v => set('color_tag', v)}
                  options={[['normal','Normal'],['red','Red'],['yellow','Yellow'],['green','Green']]} />
              </F>
              <F label="Active"><Check checked={form.is_active} onChange={v => set('is_active', v)} /></F>
              <F label="Hide"><Check checked={form.is_hidden} onChange={v => set('is_hidden', v)} /></F>
            </Grid>
          </Section>

          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={save}>{editing ? 'Save' : 'Create'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

// ─── tiny layout helpers, local to this file ────────────────────────────────
const Section = ({ title, children }) => (
  <div className="border rounded p-3 mb-3 bg-gray-50/40">
    <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">{title}</p>
    {children}
  </div>
);
const Grid = ({ children }) => <div className="grid grid-cols-2 md:grid-cols-4 gap-3">{children}</div>;
const F = ({ label, children, colSpan = 1 }) => (
  <div style={{ gridColumn: `span ${colSpan}` }}>
    <Label className="text-xs">{label}</Label>
    {children}
  </div>
);
const Num = ({ value, onChange }) => (
  <Input type="number" step="0.01" value={value ?? 0}
    onChange={e => onChange(e.target.value === '' ? 0 : parseFloat(e.target.value))} />
);
const Check = ({ checked, onChange }) => (
  <label className="flex items-center gap-2 text-sm pt-1">
    <input type="checkbox" checked={!!checked} onChange={e => onChange(e.target.checked)} />
  </label>
);
const Sel = ({ value, onChange, options }) => (
  <Select value={value || ''} onValueChange={onChange}>
    <SelectTrigger className="h-9"><SelectValue /></SelectTrigger>
    <SelectContent>
      {options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
    </SelectContent>
  </Select>
);
