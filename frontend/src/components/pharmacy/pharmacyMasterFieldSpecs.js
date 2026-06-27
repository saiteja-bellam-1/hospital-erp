/** Field specs for pharmacy catalog masters — shared by MasterTable and inline + quick-create. */

export const PHARMACY_MASTER_FIELD_SPECS = {
  categories: {
    createTitle: 'Add Category',
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'description', label: 'Description', type: 'textarea' },
      { key: 'is_active', label: 'Active', type: 'bool', default: true },
    ],
  },
  companies: {
    createTitle: 'Add Company',
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'contact', label: 'Contact' },
      { key: 'is_active', label: 'Active', type: 'bool', default: true },
    ],
  },
  salts: {
    createTitle: 'Add Salt / Composition',
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'description', label: 'Description', type: 'textarea' },
      { key: 'is_active', label: 'Active', type: 'bool', default: true },
    ],
  },
  racks: {
    createTitle: 'Add Rack',
    fields: [
      { key: 'code', label: 'Code', required: true },
      { key: 'location', label: 'Location' },
      { key: 'description', label: 'Description', type: 'textarea' },
      { key: 'is_active', label: 'Active', type: 'bool', default: true },
    ],
  },
  uoms: {
    createTitle: 'Add Unit of Measure',
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'abbreviation', label: 'Abbreviation' },
      { key: 'decimal_supported', label: 'Decimal supported', type: 'bool', default: false },
      { key: 'is_active', label: 'Active', type: 'bool', default: true },
    ],
  },
  hsn: {
    createTitle: 'Add HSN Code',
    fields: [
      { key: 'code', label: 'HSN Code', required: true },
      { key: 'description', label: 'Description', type: 'textarea' },
      { key: 'sgst_pct', label: 'SGST %', type: 'number', default: 0 },
      { key: 'cgst_pct', label: 'CGST %', type: 'number', default: 0 },
      { key: 'igst_pct', label: 'IGST %', type: 'number', default: 0 },
      { key: 'is_active', label: 'Active', type: 'bool', default: true },
    ],
  },
};

export function blankFromMasterFields(fields) {
  return Object.fromEntries(
    fields.map((f) => [f.key, f.default ?? (f.type === 'bool' ? false : '')]),
  );
}

export function payloadFromMasterForm(form, fields) {
  const payload = { is_active: true };
  fields.forEach((f) => {
    const raw = form[f.key];
    if (f.type === 'number') {
      payload[f.key] = raw === '' || raw == null ? (f.default ?? 0) : parseFloat(raw);
    } else if (f.type === 'bool') {
      payload[f.key] = !!raw;
    } else {
      const s = String(raw ?? '').trim();
      payload[f.key] = s || null;
    }
  });
  return payload;
}
