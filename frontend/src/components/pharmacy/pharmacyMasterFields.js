/** Minimal quick-create field specs for pharmacy master dropdowns. */
export const PHARMACY_MASTER_FIELDS = {
  categories: {
    createTitle: 'Add Category',
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'description', label: 'Description', type: 'textarea' },
    ],
  },
  companies: {
    createTitle: 'Add Company',
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'contact', label: 'Contact' },
    ],
  },
  salts: {
    createTitle: 'Add Salt / Composition',
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'description', label: 'Description', type: 'textarea' },
    ],
  },
  racks: {
    createTitle: 'Add Rack',
    fields: [
      { key: 'code', label: 'Code', required: true },
      { key: 'location', label: 'Location' },
    ],
  },
  uoms: {
    createTitle: 'Add Unit of Measure',
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'abbreviation', label: 'Abbreviation' },
    ],
  },
  hsn: {
    createTitle: 'Add HSN Code',
    fields: [
      { key: 'code', label: 'HSN Code', required: true },
      { key: 'sgst_pct', label: 'SGST %', type: 'number', default: 0 },
      { key: 'cgst_pct', label: 'CGST %', type: 'number', default: 0 },
      { key: 'igst_pct', label: 'IGST %', type: 'number', default: 0 },
    ],
  },
  suppliers: {
    createTitle: 'Add Supplier',
    fields: [
      { key: 'name', label: 'Name', required: true },
      { key: 'mobile', label: 'Mobile' },
      { key: 'gstin_no', label: 'GSTIN' },
    ],
  },
};

export function blankFromFields(fields) {
  return Object.fromEntries(
    fields.map((f) => [f.key, f.default ?? '']),
  );
}
