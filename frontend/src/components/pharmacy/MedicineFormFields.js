import React from 'react';
import FormNavContainer from '../FormNavContainer';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import PharmacyMasterSelectWithCreate from './PharmacyMasterSelectWithCreate';
import { costPcsFromMrp, roundMoney } from '../../utils/pharmacyUnits';

const PRICE_KEYS = [
  'unit_price', 'mrp', 'purchase_rate', 'rate_a', 'rate_b', 'cost_pcs',
  'default_discount_pct', 'item_discount_pct',
];

export const EMPTY_MEDICINE_FORM = {
  medicine_code: '', name: '', generic_name: '', manufacturer: '',
  category_id: null, dosage_form: '', strength: '',
  unit_price: 0, mrp: 0, purchase_rate: 0, rate_a: 0, rate_b: 0, cost_pcs: 0,
  default_discount_pct: 0, item_discount_pct: 0,
  hsn_id: null, company_id: null, rack_id: null, salt_id: null, uom_id: null,
  barcode: '', packaging: '', strip_conversion_factor: 1,
  decimal_supported: false, is_active: true, is_hidden: false, requires_prescription: true,
  is_narcotic: false, is_high_alert: false, is_schedule_h: false,
  is_schedule_h1: false, is_tramadol: false, is_controlled: false,
  description: '', side_effects: '', contraindications: '', storage_conditions: '',
  min_qty: 0, max_qty: 0, reorder_qty: 0,
};

export function patchMedicineForm(prev, patch) {
  const next = { ...prev, ...patch };
  next.cost_pcs = costPcsFromMrp(next);
  return next;
}

export function prepareMedicinePayload(form) {
  const payload = { ...form, cost_pcs: costPcsFromMrp(form) };
  ['category_id', 'company_id', 'rack_id', 'salt_id', 'uom_id', 'hsn_id'].forEach((k) => {
    if (payload[k] === '' || payload[k] === undefined) payload[k] = null;
  });
  PRICE_KEYS.forEach((k) => {
    if (payload[k] !== undefined && payload[k] !== null && payload[k] !== '') {
      payload[k] = roundMoney(payload[k]);
    }
  });
  if (!payload.unit_price && payload.rate_a) {
    payload.unit_price = payload.rate_a;
  }
  return payload;
}

const Section = ({ title, children }) => (
  <div className="border rounded p-3 mb-3 bg-gray-50/40">
    <p className="text-xs font-semibold text-gray-600 uppercase tracking-wide mb-2">{title}</p>
    {children}
  </div>
);

const Grid = ({ children }) => <div className="grid grid-cols-2 md:grid-cols-3 gap-3">{children}</div>;

const F = ({ label, children }) => (
  <div>
    <Label className="text-xs">{label}</Label>
    {children}
  </div>
);

const Num = ({ value, onChange }) => (
  <Input
    type="number"
    step="0.01"
    min="0"
    value={value ?? 0}
    onChange={(e) => {
      const raw = e.target.value;
      if (raw === '') {
        onChange(0);
        return;
      }
      onChange(roundMoney(raw));
    }}
  />
);

const Check = ({ checked, onChange }) => (
  <label className="flex items-center gap-2 text-sm pt-1">
    <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
  </label>
);

/**
 * Full pharmacy medicine catalog form — shared by Medicines tab and POS quick-create.
 */
export default function MedicineFormFields({
  form,
  onChange,
  masters,
  onMastersChange,
}) {
  const set = (k, v) => onChange({ ...form, [k]: v });
  const patch = (updates) => onChange(patchMedicineForm(form, updates));

  const {
    categories, companies, racks, salts, uoms, hsnList,
  } = masters;

  const setCategories = (list) => onMastersChange({ ...masters, categories: list });
  const setCompanies = (list) => onMastersChange({ ...masters, companies: list });
  const setRacks = (list) => onMastersChange({ ...masters, racks: list });
  const setSalts = (list) => onMastersChange({ ...masters, salts: list });
  const setUoms = (list) => onMastersChange({ ...masters, uoms: list });
  const setHsnList = (list) => onMastersChange({ ...masters, hsnList: list });

  return (
    <FormNavContainer mode="grid">
      <Section title="Basic">
        <Grid>
          <F label="Code *"><Input value={form.medicine_code} onChange={(e) => set('medicine_code', e.target.value)} /></F>
          <F label="Name *"><Input value={form.name} onChange={(e) => set('name', e.target.value)} /></F>
          <F label="Generic Name"><Input value={form.generic_name} onChange={(e) => set('generic_name', e.target.value)} /></F>
          <F label="Category *">
            <PharmacyMasterSelectWithCreate path="categories" value={form.category_id}
              onChange={(v) => set('category_id', v)} options={categories} onOptionsChange={setCategories}
              placeholder="Pick category" />
          </F>
          <F label="Company">
            <PharmacyMasterSelectWithCreate path="companies" value={form.company_id}
              onChange={(v) => set('company_id', v)} options={companies} onOptionsChange={setCompanies}
              placeholder="(none)" allowEmpty />
          </F>
          <F label="Salt / Composition">
            <PharmacyMasterSelectWithCreate path="salts" value={form.salt_id}
              onChange={(v) => set('salt_id', v)} options={salts} onOptionsChange={setSalts}
              placeholder="(none)" allowEmpty />
          </F>
          <F label="Rack">
            <PharmacyMasterSelectWithCreate path="racks" value={form.rack_id}
              onChange={(v) => set('rack_id', v)} options={racks} onOptionsChange={setRacks}
              placeholder="(none)" allowEmpty labelKey="code" />
          </F>
          <F label="Unit of Measure">
            <PharmacyMasterSelectWithCreate path="uoms" value={form.uom_id}
              onChange={(v) => set('uom_id', v)} options={uoms} onOptionsChange={setUoms}
              placeholder="(none)" allowEmpty
              format={(u) => `${u.name}${u.abbreviation ? ` (${u.abbreviation})` : ''}`} />
          </F>
          <F label="Dosage Form"><Input value={form.dosage_form || ''} onChange={(e) => set('dosage_form', e.target.value)} placeholder="tablet / syrup / inj" /></F>
          <F label="Strength"><Input value={form.strength || ''} onChange={(e) => set('strength', e.target.value)} placeholder="500mg" /></F>
          <F label="Barcode"><Input value={form.barcode || ''} onChange={(e) => set('barcode', e.target.value)} /></F>
          <F label="Packaging (display only)"><Input value={form.packaging || ''} onChange={(e) => set('packaging', e.target.value)} placeholder="e.g. box of 10 strips" /></F>
          <F label="Tablets per strip (sheet)">
            <Input
              type="number"
              min="1"
              value={form.strip_conversion_factor ?? 1}
              onChange={(e) => patch({
                strip_conversion_factor: e.target.value === '' ? 1 : Math.max(1, parseInt(e.target.value, 10) || 1),
              })}
            />
            <p className="text-[10px] text-gray-500 mt-0.5">Tabs in one strip. MRP and Rate A/B are per strip; cost/tab = MRP ÷ this number.</p>
          </F>
          <F label="Decimal supported">
            <Check checked={form.decimal_supported} onChange={(v) => set('decimal_supported', v)} />
          </F>
          <F label="Active"><Check checked={form.is_active} onChange={(v) => set('is_active', v)} /></F>
          <F label="Hidden from sales"><Check checked={form.is_hidden} onChange={(v) => set('is_hidden', v)} /></F>
        </Grid>
      </Section>

      <Section title="Pricing & Tax">
        <Grid>
          <F label="MRP (per strip)"><Num value={form.mrp} onChange={(v) => patch({ mrp: v })} /></F>
          <F label="Purchase Rate (P-Rate)"><Num value={form.purchase_rate} onChange={(v) => set('purchase_rate', v)} /></F>
          <F label="Rate A (per strip)"><Num value={form.rate_a} onChange={(v) => set('rate_a', v)} /></F>
          <F label="Rate B (per strip)"><Num value={form.rate_b} onChange={(v) => set('rate_b', v)} /></F>
          <F label="Cost / piece (per tab)">
            <p className="text-sm pt-2 font-medium">₹{(form.cost_pcs || 0).toFixed(2)}</p>
            <p className="text-[10px] text-gray-500">Auto: MRP ÷ {form.strip_conversion_factor || 1} tabs</p>
          </F>
          <F label="Default Discount %"><Num value={form.default_discount_pct} onChange={(v) => set('default_discount_pct', v)} /></F>
          <F label="Item-level Discount %"><Num value={form.item_discount_pct} onChange={(v) => set('item_discount_pct', v)} /></F>
          <F label="HSN / Tax">
            <PharmacyMasterSelectWithCreate path="hsn" value={form.hsn_id}
              onChange={(v) => set('hsn_id', v)} options={hsnList} onOptionsChange={setHsnList}
              placeholder="(none)" allowEmpty labelKey="code"
              format={(h) => `${h.code} (SGST ${h.sgst_pct}% + CGST ${h.cgst_pct}%)`} />
          </F>
        </Grid>
      </Section>

      <Section title="Inventory Thresholds">
        <Grid>
          <F label="Min Qty (low-stock alert)"><Num value={form.min_qty} onChange={(v) => set('min_qty', Math.round(v))} /></F>
          <F label="Max Qty"><Num value={form.max_qty} onChange={(v) => set('max_qty', Math.round(v))} /></F>
          <F label="Reorder Qty"><Num value={form.reorder_qty} onChange={(v) => set('reorder_qty', Math.round(v))} /></F>
        </Grid>
      </Section>

      <Section title="Regulatory">
        <Grid>
          <F label="Requires Prescription"><Check checked={form.requires_prescription} onChange={(v) => set('requires_prescription', v)} /></F>
          <F label="Narcotic"><Check checked={form.is_narcotic} onChange={(v) => set('is_narcotic', v)} /></F>
          <F label="Schedule H"><Check checked={form.is_schedule_h} onChange={(v) => set('is_schedule_h', v)} /></F>
          <F label="Schedule H1"><Check checked={form.is_schedule_h1} onChange={(v) => set('is_schedule_h1', v)} /></F>
          <F label="Tramadol"><Check checked={form.is_tramadol} onChange={(v) => set('is_tramadol', v)} /></F>
          <F label="Controlled"><Check checked={form.is_controlled} onChange={(v) => set('is_controlled', v)} /></F>
          <F label="High-alert"><Check checked={form.is_high_alert} onChange={(v) => set('is_high_alert', v)} /></F>
        </Grid>
      </Section>

      <Section title="Notes">
        <F label="Description"><Textarea rows={2} value={form.description || ''} onChange={(e) => set('description', e.target.value)} /></F>
        <F label="Side Effects"><Textarea rows={2} value={form.side_effects || ''} onChange={(e) => set('side_effects', e.target.value)} /></F>
        <F label="Storage Conditions"><Textarea rows={2} value={form.storage_conditions || ''} onChange={(e) => set('storage_conditions', e.target.value)} /></F>
      </Section>
    </FormNavContainer>
  );
}
