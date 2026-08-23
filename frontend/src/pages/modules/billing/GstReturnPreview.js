import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { formatInr } from './BillingReportControls';

function money(v) {
  return formatInr(v);
}

function FormTable({ headers, rows, firstWide }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="bg-gray-100 text-gray-700">
            {headers.map((h) => (
              <th key={h} className="border px-2 py-1.5 text-left font-semibold">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(rows || []).map((row, i) => (
            <tr key={i}>
              {row.map((cell, j) => (
                <td
                  key={j}
                  className={`border px-2 py-1 ${j === 0 && firstWide ? 'w-[42%]' : ''} ${j > 0 ? 'text-right tabular-nums' : ''}`}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Gst3bTables({ data }) {
  if (!data) return null;
  const t31 = data.table_3_1 || {};
  const t4 = data.table_4 || {};
  const t5 = data.table_5 || {};
  const p = data.table_6_1 || {};
  const taxRow = (r = {}) => [money(r.taxable), money(r.igst), money(r.cgst), money(r.sgst), money(r.cess)];
  const itcRow = (r = {}) => [money(r.igst), money(r.cgst), money(r.sgst), money(r.cess)];
  const pay = (r = {}) => [money(r.payable), money(r.itc), money(r.cash)];
  const chk = data.check || {};

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle className="text-base">3.1 Outward supplies</CardTitle></CardHeader>
        <CardContent>
          <FormTable
            firstWide
            headers={['Nature of Supplies', 'Taxable value', 'IGST', 'CGST', 'SGST', 'Cess']}
            rows={[
              ['(a) Outward taxable supplies (other than zero rated, Nil rated and exempted)', ...taxRow(t31.a)],
              ['(b) Outward taxable supplies (zero rated)', ...taxRow(t31.b)],
              ['(c) Other Outward supplies (Nil rated, exempted)', ...taxRow(t31.c)],
              ['(d) Inward supplies (liable to reverse charge)', ...taxRow(t31.d)],
              ['(e) Non-GST outward supplies', ...taxRow(t31.e)],
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">3.2 Inter-state supplies to unregistered / composition / UIN</CardTitle></CardHeader>
        <CardContent>
          {(data.table_3_2 || []).length ? (
            <FormTable
              headers={['Place of supply', 'Taxable value', 'IGST']}
              rows={(data.table_3_2 || []).map((r) => [r.place_of_supply || '—', money(r.taxable), money(r.igst)])}
            />
          ) : (
            <p className="text-sm text-gray-500">None in this period.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">4. Eligible ITC</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          <FormTable
            firstWide
            headers={['Details', 'IGST', 'CGST', 'SGST', 'Cess']}
            rows={[
              ['(A)(1) Import of Goods', ...itcRow(t4.a1_import_goods)],
              ['(A)(2) Import of Services', ...itcRow(t4.a2_import_services)],
              ['(A)(3) Inward supplies liable to reverse charge', ...itcRow(t4.a3_rcm)],
              ['(A)(4) Inward supplies from ISD', ...itcRow(t4.a4_isd)],
              ['(A)(5) All other ITC', ...itcRow(t4.a5_all_other)],
              ['(B)(1) Rules 38, 42 & 43 / section 17(5)', ...itcRow(t4.b1_rules)],
              ['(B)(2) Others', ...itcRow(t4.b2_others)],
              ['(C) Net ITC available (A)-(B)', ...itcRow(t4.c_net)],
              ['(D)(1) ITC reclaimed (earlier 4(B)(2))', ...itcRow(t4.d1_reclaimed)],
              ['(D)(2) Ineligible ITC (s.16(4) / PoS)', ...itcRow(t4.d2_ineligible)],
            ]}
          />
          {t4.footnote && <p className="text-xs text-gray-500">{t4.footnote}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">5. Exempt, nil-rated and non-GST inward</CardTitle></CardHeader>
        <CardContent>
          <FormTable
            firstWide
            headers={['Nature of Supplies', 'Inter-State', 'Intra-State']}
            rows={[
              ['Composition / exempt / nil rated', money((t5.composition_nil_exempt || {}).inter), money((t5.composition_nil_exempt || {}).intra)],
              ['Non GST supply', money((t5.non_gst || {}).inter), money((t5.non_gst || {}).intra)],
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">6.1 Payment of tax</CardTitle></CardHeader>
        <CardContent>
          <FormTable
            headers={['Description', 'Tax payable', 'Paid through ITC', 'Paid in cash']}
            rows={[
              ['Integrated Tax', ...pay(p.igst)],
              ['Central Tax', ...pay(p.cgst)],
              ['State/UT Tax', ...pay(p.sgst)],
              ['Cess', ...pay(p.cess)],
            ]}
          />
        </CardContent>
      </Card>

      <p className="text-xs text-gray-500">
        GSTR-1 vs 3B:{' '}
        taxable {chk.gstr1_3b_taxable_match ? 'match' : 'review'}
        {' · '}tax {chk.gstr1_3b_tax_match ? 'match' : 'review'}
        {' · '}ITC {chk.itc_matches_gstr2 ? 'match' : 'review'}
      </p>
    </div>
  );
}

export function SimpleRowsTable({ columns, rows, empty }) {
  if (!(rows || []).length) {
    return <p className="text-sm text-gray-500">{empty || 'No rows in this period.'}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="bg-gray-100 text-gray-700">
            {columns.map((c) => (
              <th key={c.key} className={`border px-2 py-1.5 font-semibold ${c.align === 'right' ? 'text-right' : 'text-left'}`}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => {
                const val = row[c.key];
                const display = c.money ? money(val) : (val === 0 ? '0' : (val ?? ''));
                return (
                  <td key={c.key} className={`border px-2 py-1 ${c.align === 'right' ? 'text-right tabular-nums' : ''}`}>
                    {display}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
