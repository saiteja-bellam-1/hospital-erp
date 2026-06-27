import React from 'react';
import FormNavContainer from '../FormNavContainer';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';

export const EMPTY_SUPPLIER_FORM = {
  name: '',
  station: '', account_group: 'Sundry Creditors', balancing_method: 'bill_by_bill',
  opening_balance: 0, opening_balance_dr_cr: 'Dr',
  hold_payment: false, hold_payment_pct: 0, ledger_date: '', freeze_upto: '',
  contact_person: '', designation: '',
  phone_office: '', phone_residence: '', mobile: '', phone: '',
  fax: '', email: '', website: '',
  mail_to: '', address: '', pin_code: '',
  state: '', state_code: '', country: 'India',
  gst_heading: 'local', gstin: '', gstin_no: '', gstin_date: '',
  dl_number: '', dl_expiry: '',
  vat_number: '', vat_expiry: '',
  st_number: '', st_expiry: '',
  food_license_no: '', food_license_expiry: '',
  extra_license_no: '', extra_license_expiry: '',
  pan_number: '',
  narco_sch_h_billing: 'allow_all', bill_import: 'mobile',
  ledger_category: 'OTHERS', ledger_type: 'unregistered',
  color_tag: 'normal', is_hidden: false, is_active: true,
};

const DATE_KEYS = [
  'ledger_date', 'freeze_upto', 'gstin_date', 'dl_expiry', 'vat_expiry',
  'st_expiry', 'food_license_expiry', 'extra_license_expiry',
];

export function prepareSupplierPayload(form) {
  const payload = { ...form };
  DATE_KEYS.forEach((k) => {
    if (payload[k] === '' || payload[k] === undefined) payload[k] = null;
  });
  return payload;
}

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
  <Input
    type="number"
    step="0.01"
    value={value ?? 0}
    onChange={(e) => onChange(e.target.value === '' ? 0 : parseFloat(e.target.value))}
  />
);

const Check = ({ checked, onChange }) => (
  <label className="flex items-center gap-2 text-sm pt-1">
    <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
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

/** Full supplier form — shared by Suppliers tab and purchase-entry quick-add. */
export default function SupplierFormFields({ form, onChange }) {
  const set = (k, v) => onChange({ ...form, [k]: v });

  return (
    <FormNavContainer mode="grid">
      <Section title="Basic">
        <Grid>
          <F label="Ledger Name *" colSpan={2}><Input value={form.name} onChange={(e) => set('name', e.target.value)} /></F>
          <F label="Station"><Input value={form.station} onChange={(e) => set('station', e.target.value)} /></F>
          <F label="Account Group"><Input value={form.account_group} onChange={(e) => set('account_group', e.target.value)} /></F>
          <F label="Balancing Method">
            <Sel value={form.balancing_method} onChange={(v) => set('balancing_method', v)}
              options={[['bill_by_bill', 'Bill by Bill'], ['on_account', 'On Account']]} />
          </F>
          <F label="Opening Balance"><Num value={form.opening_balance} onChange={(v) => set('opening_balance', v)} /></F>
          <F label="Dr / Cr">
            <Sel value={form.opening_balance_dr_cr} onChange={(v) => set('opening_balance_dr_cr', v)}
              options={[['Dr', 'Dr'], ['Cr', 'Cr']]} />
          </F>
          <F label="Hold Payment"><Check checked={form.hold_payment} onChange={(v) => set('hold_payment', v)} /></F>
          <F label="% (if GSTR1 not uploaded)"><Num value={form.hold_payment_pct} onChange={(v) => set('hold_payment_pct', v)} /></F>
          <F label="Ledger Date"><Input type="date" value={form.ledger_date || ''} onChange={(e) => set('ledger_date', e.target.value)} /></F>
          <F label="Freeze Upto"><Input type="date" value={form.freeze_upto || ''} onChange={(e) => set('freeze_upto', e.target.value)} /></F>
        </Grid>
      </Section>

      <Section title="Contact">
        <Grid>
          <F label="Contact Person"><Input value={form.contact_person} onChange={(e) => set('contact_person', e.target.value)} /></F>
          <F label="Designation"><Input value={form.designation} onChange={(e) => set('designation', e.target.value)} /></F>
          <F label="Mobile"><Input value={form.mobile} onChange={(e) => set('mobile', e.target.value)} /></F>
          <F label="Phone (Off.)"><Input value={form.phone_office} onChange={(e) => set('phone_office', e.target.value)} /></F>
          <F label="Phone (Res.)"><Input value={form.phone_residence} onChange={(e) => set('phone_residence', e.target.value)} /></F>
          <F label="Fax"><Input value={form.fax} onChange={(e) => set('fax', e.target.value)} /></F>
          <F label="Email"><Input value={form.email} onChange={(e) => set('email', e.target.value)} /></F>
          <F label="Web Site"><Input value={form.website} onChange={(e) => set('website', e.target.value)} /></F>
        </Grid>
      </Section>

      <Section title="Address">
        <Grid>
          <F label="Mail to" colSpan={2}><Input value={form.mail_to} onChange={(e) => set('mail_to', e.target.value)} /></F>
          <F label="Address" colSpan={3}><Textarea rows={2} value={form.address} onChange={(e) => set('address', e.target.value)} /></F>
          <F label="Pin Code"><Input value={form.pin_code} onChange={(e) => set('pin_code', e.target.value)} /></F>
          <F label="State"><Input value={form.state} onChange={(e) => set('state', e.target.value)} placeholder="TELANGANA" /></F>
          <F label="State Code"><Input value={form.state_code} onChange={(e) => set('state_code', e.target.value)} placeholder="36" /></F>
          <F label="Country"><Input value={form.country} onChange={(e) => set('country', e.target.value)} /></F>
        </Grid>
      </Section>

      <Section title="GST & Licenses">
        <Grid>
          <F label="GST Heading">
            <Sel value={form.gst_heading} onChange={(v) => set('gst_heading', v)}
              options={[['local', 'Local'], ['interstate', 'Interstate'], ['composition', 'Composition'], ['exempt', 'Exempt']]} />
          </F>
          <F label="Ledger Type">
            <Sel value={form.ledger_type} onChange={(v) => set('ledger_type', v)}
              options={[['registered', 'Registered'], ['unregistered', 'Unregistered'], ['composition', 'Composition']]} />
          </F>
          <F label="GSTIN No."><Input value={form.gstin_no} onChange={(e) => set('gstin_no', e.target.value)} /></F>
          <F label="GSTIN Date"><Input type="date" value={form.gstin_date || ''} onChange={(e) => set('gstin_date', e.target.value)} /></F>
          <F label="D.L. No."><Input value={form.dl_number} onChange={(e) => set('dl_number', e.target.value)} /></F>
          <F label="D.L. Exp."><Input type="date" value={form.dl_expiry || ''} onChange={(e) => set('dl_expiry', e.target.value)} /></F>
          <F label="VAT No."><Input value={form.vat_number} onChange={(e) => set('vat_number', e.target.value)} /></F>
          <F label="VAT Exp."><Input type="date" value={form.vat_expiry || ''} onChange={(e) => set('vat_expiry', e.target.value)} /></F>
          <F label="S.T. No."><Input value={form.st_number} onChange={(e) => set('st_number', e.target.value)} /></F>
          <F label="S.T. Exp."><Input type="date" value={form.st_expiry || ''} onChange={(e) => set('st_expiry', e.target.value)} /></F>
          <F label="Food Licence No."><Input value={form.food_license_no} onChange={(e) => set('food_license_no', e.target.value)} /></F>
          <F label="Food Licence Exp."><Input type="date" value={form.food_license_expiry || ''} onChange={(e) => set('food_license_expiry', e.target.value)} /></F>
          <F label="Extra Heading No."><Input value={form.extra_license_no} onChange={(e) => set('extra_license_no', e.target.value)} /></F>
          <F label="Extra Heading Exp."><Input type="date" value={form.extra_license_expiry || ''} onChange={(e) => set('extra_license_expiry', e.target.value)} /></F>
          <F label="I.T. PAN No."><Input value={form.pan_number} onChange={(e) => set('pan_number', e.target.value)} /></F>
        </Grid>
      </Section>

      <Section title="Misc">
        <Grid>
          <F label="Narco / Sch-H Item Billing">
            <Sel value={form.narco_sch_h_billing} onChange={(v) => set('narco_sch_h_billing', v)}
              options={[['allow_all', 'Allow All'], ['restrict', 'Restrict'], ['block', 'Block']]} />
          </F>
          <F label="Bill Import">
            <Sel value={form.bill_import} onChange={(v) => set('bill_import', v)}
              options={[['mobile', 'Mobile'], ['erp', 'ERP to ERP'], ['manual', 'Manual']]} />
          </F>
          <F label="Ledger Category"><Input value={form.ledger_category} onChange={(e) => set('ledger_category', e.target.value)} /></F>
          <F label="Color Tag">
            <Sel value={form.color_tag} onChange={(v) => set('color_tag', v)}
              options={[['normal', 'Normal'], ['red', 'Red'], ['yellow', 'Yellow'], ['green', 'Green']]} />
          </F>
          <F label="Active"><Check checked={form.is_active} onChange={(v) => set('is_active', v)} /></F>
          <F label="Hide"><Check checked={form.is_hidden} onChange={(v) => set('is_hidden', v)} /></F>
        </Grid>
      </Section>
    </FormNavContainer>
  );
}
