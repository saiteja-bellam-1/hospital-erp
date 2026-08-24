import React from 'react';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { localDateString, localDateStringOffset, localWeekStart, localMonthStart, localLastMonthRange } from '../../../utils/localDate';

export const BILLING_MODULES = [
  { id: 'all', label: 'All' },
  { id: 'inpatient', label: 'Inpatient' },
  { id: 'pharmacy', label: 'Pharmacy' },
  { id: 'pharmacy_ip', label: 'Pharmacy (IP)' },
  { id: 'day_care', label: 'Day Care' },
  { id: 'catch_up', label: 'Catch-up' },
];

/** GST filing groups — Pharmacy keeps its own GSTIN; the rest file as Hospital GST. */
export const GST_SCOPES = [
  { id: 'all', label: 'All', hint: 'Combined working paper (not a filing)' },
  { id: 'hospital', label: 'Hospital GST', hint: 'IP, day care' },
  { id: 'pharmacy', label: 'Pharmacy GST', hint: 'Pharmacy OP and IP' },
];

export function formatInr(val) {
  return `₹${Number(val || 0).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function defaultReportRange() {
  return { from: localDateStringOffset(-30), to: localDateString() };
}

export function BillingDateRange({ dateFrom, dateTo, onFrom, onTo, className }) {
  const applyPreset = (id) => {
    const today = localDateString();
    if (id === 'today') { onFrom(today); onTo(today); return; }
    if (id === 'week') { onFrom(localWeekStart()); onTo(today); return; }
    if (id === 'month') { onFrom(localMonthStart()); onTo(today); return; }
    if (id === 'last_month') {
      const { from, to } = localLastMonthRange();
      onFrom(from); onTo(to);
    }
  };
  return (
    <div className={className || 'flex flex-wrap gap-3 items-end'}>
      <div>
        <Label className="text-xs">From</Label>
        <Input type="date" value={dateFrom} onChange={(e) => onFrom(e.target.value)} className="w-[150px] h-9" />
      </div>
      <div>
        <Label className="text-xs">To</Label>
        <Input type="date" value={dateTo} onChange={(e) => onTo(e.target.value)} className="w-[150px] h-9" />
      </div>
      <div className="flex flex-wrap gap-1">
        {[
          { id: 'today', label: 'Today' },
          { id: 'week', label: 'This week' },
          { id: 'month', label: 'This month' },
          { id: 'last_month', label: 'Last month' },
        ].map((p) => (
          <Button key={p.id} type="button" size="sm" variant="outline" className="h-9 px-2.5 text-xs" onClick={() => applyPreset(p.id)}>
            {p.label}
          </Button>
        ))}
      </div>
    </div>
  );
}

export function GstinBanner({ data, module = 'all' }) {
  const gstin = data?.gstin || data?.hospital?.gstin || '';
  const label = data?.gstin_label || data?.hospital?.gstin_label || '';
  const gstins = data?.gstins || data?.hospital?.gstins || [];
  const showAll = (!module || module === 'all') && gstins.length > 0;

  if (showAll) {
    return (
      <p className="text-xs text-gray-600">
        {gstins.map((g, i) => (
          <span key={g.module || i}>
            {i > 0 ? <span className="text-gray-400"> · </span> : null}
            <span className="font-medium">{g.label}</span>
            {' '}GSTIN <span className="font-mono tracking-wide">{g.gstin}</span>
          </span>
        ))}
      </p>
    );
  }
  if (gstin) {
    return (
      <p className="text-xs text-gray-600">
        {label ? <span className="font-medium">{label} </span> : null}
        GSTIN <span className="font-mono tracking-wide">{gstin}</span>
      </p>
    );
  }
  return (
    <p className="text-xs text-amber-700">
      No GSTIN on file for this filing. Enter a GST number in Module Settings, enable "Use hospital GSTIN", or set Hospital GSTIN for Hospital GST.
    </p>
  );
}

export function GstScopeChips({ value, onChange }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {GST_SCOPES.map((m) => (
        <Button
          key={m.id}
          type="button"
          size="sm"
          variant={value === m.id ? 'default' : 'outline'}
          className="h-8 px-2.5 text-xs"
          title={m.hint}
          onClick={() => onChange(m.id)}
        >
          {m.label}
        </Button>
      ))}
    </div>
  );
}

export function ModuleChips({ value, onChange, enabled = null }) {
  const items = BILLING_MODULES.filter((m) => {
    if (!enabled) return true;
    if (m.id === 'all') return true;
    return enabled[m.id] !== false;
  });
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((m) => (
        <Button
          key={m.id}
          type="button"
          size="sm"
          variant={value === m.id ? 'default' : 'outline'}
          className="h-8 px-2.5 text-xs"
          onClick={() => onChange(m.id)}
        >
          {m.label}
        </Button>
      ))}
    </div>
  );
}

export function formatPct(val) {
  if (val == null || val === '' || Number.isNaN(Number(val))) return '—';
  const n = Number(val);
  if (n === 0) return '0%';
  return `${Number(n.toFixed(2))}%`;
}

/** Normalize API rate to the same key the backend uses ("5" not "5.0"). */
export function rateKey(rate) {
  const n = Number(rate);
  if (Number.isNaN(n)) return String(rate);
  return Number.isInteger(n) ? String(n) : String(n);
}

/**
 * Dynamic GST rate columns. Cell values are bill amounts at that rate
 * (taxable + tax by default — the actual charged amount for lines at that %).
 */
export function rateAmountColumns(taxRateColumns, field = 'amount') {
  return (taxRateColumns || []).map((r) => {
    const key = rateKey(r);
    const isExempt = Number(key) === 0;
    return {
      key: `rate_${key}`,
      label: isExempt ? 'Exempt' : `${key}%`,
      align: 'right',
      money: true,
      emptyDash: true,
      rateKey: key,
      rateField: field,
    };
  });
}

/** Flatten tax_by_rate into rate_<pct> fields for MoneyTable. */
export function flattenRateRows(rows, taxRateColumns, field = 'amount') {
  const cols = taxRateColumns || [];
  return (rows || []).map((r) => {
    const out = { ...r };
    const by = r.tax_by_rate || {};
    cols.forEach((rate) => {
      const key = rateKey(rate);
      const bucket = by[key] ?? by[String(rate)] ?? null;
      out[`rate_${key}`] = bucket ? Number(bucket[field] ?? 0) : null;
    });
    return out;
  });
}

export function MoneyTable({ columns, rows, totals }) {
  const cell = (c, row, isTotal = false) => {
    const v = row?.[c.key];
    if (c.emptyDash && (v == null || v === '')) return '—';
    if (c.money) return formatInr(v);
    if (c.pct) return formatPct(v);
    if (isTotal && c.key && (v == null || v === '')) return '';
    return v ?? '—';
  };
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500">
            {columns.map((c) => (
              <th key={c.key} className={`pb-2 pr-3 whitespace-nowrap ${c.align === 'right' ? 'text-right' : ''}`}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r._key || r.bucket || r.number || i} className="border-b">
              {columns.map((c) => (
                <td key={c.key} className={`py-2 pr-3 whitespace-nowrap ${c.align === 'right' ? 'text-right' : ''}`}>
                  {cell(c, r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {totals && (
          <tfoot>
            <tr className="border-t font-semibold">
              {columns.map((c, i) => (
                <td key={c.key} className={`py-2 pr-3 whitespace-nowrap ${c.align === 'right' ? 'text-right' : ''}`}>
                  {i === 0 ? 'Total' : cell(c, totals, true)}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}
