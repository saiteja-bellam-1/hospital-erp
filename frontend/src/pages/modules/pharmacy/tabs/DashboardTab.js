import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Button } from '../../../../components/ui/button';
import { Badge } from '../../../../components/ui/badge';
import ActionKpiCard from '../../../../components/dashboard/ActionKpiCard';
import DashboardDrillDialog from '../../../../components/dashboard/DashboardDrillDialog';
import {
  ShoppingCart, Receipt, AlertTriangle, Pill, RefreshCw, CalendarX2, BedDouble, Banknote,
  RotateCcw, Link2,
} from 'lucide-react';
import { usePharmacyStore } from '../../../../contexts/PharmacyStoreContext';
import { usePharmacyPermissions } from '../../../../hooks/usePharmacyPermissions';
import { localDateString } from '../../../../utils/localDate';

const fmtMoney = (n) => `₹${Number(n || 0).toFixed(2)}`;

const EXPIRY_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'expired', label: 'Expired' },
  { id: 'soon', label: 'Expiring soon' },
];

export default function DashboardTab() {
  const navigate = useNavigate();
  const { storeParams } = usePharmacyStore();
  const { hasPerm, hasAnyPerm } = usePharmacyPermissions();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [drill, setDrill] = useState(null); // { type, title, description, ... }
  const [expiryFilter, setExpiryFilter] = useState('all');
  const today = localDateString();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get('/api/pharmacy/dashboard', { params: storeParams });
      setData(r.data);
    } catch {
      /* best-effort */
    } finally {
      setLoading(false);
    }
  }, [storeParams]);

  useEffect(() => { load(); }, [load]);

  const posTotal = data?.today_pos_sales_total ?? data?.today_sales_total ?? 0;
  const posCount = data?.today_pos_sales_count ?? data?.today_sales_count ?? 0;
  const ipTotal = data?.today_ip_medicines_total ?? 0;
  const ipCount = data?.today_ip_medicines_count ?? 0;
  const billingTotal = Number(posTotal) + Number(ipTotal);

  const openDrill = (cfg) => setDrill(cfg);
  const closeDrill = () => {
    setDrill(null);
    setExpiryFilter('all');
  };

  const loadSales = useCallback(async (billingMode) => {
    const params = {
      ...storeParams,
      status: 'completed',
      date_from: today,
      date_to: today,
      limit: 100,
    };
    if (billingMode) params.billing_mode = billingMode;
    const r = await axios.get('/api/pharmacy/sales', { params });
    return r.data || [];
  }, [storeParams, today]);

  const loadPurchases = useCallback(async () => {
    const r = await axios.get('/api/pharmacy/purchases', {
      params: { ...storeParams, date_from: today, date_to: today },
    });
    return r.data || [];
  }, [storeParams, today]);

  const loadLowStock = useCallback(async () => {
    const r = await axios.get('/api/pharmacy/inventory/low-stock', { params: storeParams });
    return r.data || [];
  }, [storeParams]);

  const loadExpiring = useCallback(async () => {
    const r = await axios.get('/api/pharmacy/inventory/expiring', {
      params: { ...storeParams, days: 90 },
    });
    return r.data || [];
  }, [storeParams]);

  const loadPendingRx = useCallback(async () => {
    const r = await axios.get('/api/pharmacy/prescriptions/pending', { params: { limit: 100 } });
    return r.data || [];
  }, []);

  const loadSaleReturns = useCallback(async () => {
    const r = await axios.get('/api/pharmacy/sale-returns', {
      params: { ...storeParams, date_from: today, date_to: today },
    });
    return (r.data || []).filter((row) => row.status !== 'cancelled');
  }, [storeParams, today]);

  const loadUnmapped = useCallback(async () => {
    const r = await axios.get('/api/pharmacy/medicines/unmapped', { params: { limit: 100 } });
    return r.data || [];
  }, []);

  const drillLoaders = useMemo(() => ({
    pos_sales: () => loadSales('cash_at_pharmacy'),
    ip_sales: () => loadSales('inpatient_bill'),
    all_sales: () => loadSales(null),
    purchases: loadPurchases,
    low_stock: loadLowStock,
    expiring: loadExpiring,
    pending_rx: loadPendingRx,
    sale_returns: loadSaleReturns,
    unmapped: loadUnmapped,
  }), [loadSales, loadPurchases, loadLowStock, loadExpiring, loadPendingRx, loadSaleReturns, loadUnmapped]);

  const renderDrillRows = (type, rows) => {
    if (type === 'pos_sales' || type === 'ip_sales' || type === 'all_sales') {
      return (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-600">
              <th className="py-2 pr-3">Sale #</th>
              <th className="py-2 pr-3">Patient</th>
              <th className="py-2 pr-3">Time</th>
              <th className="py-2 pr-3">Total</th>
              <th className="py-2 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id} className="border-b hover:bg-gray-50">
                <td className="py-2 pr-3 font-mono text-xs">{s.sale_number}</td>
                <td className="py-2 pr-3">{s.patient_name || '—'}</td>
                <td className="py-2 pr-3 text-xs">{s.sale_date ? new Date(s.sale_date).toLocaleTimeString() : '—'}</td>
                <td className="py-2 pr-3 tabular-nums">{fmtMoney(s.grand_total)}</td>
                <td className="py-2 text-right">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      closeDrill();
                      navigate(`/dashboard/pharmacy/sales-counter/${s.id}/edit`);
                    }}
                  >
                    Open
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      );
    }

    if (type === 'purchases') {
      return (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-600">
              <th className="py-2 pr-3">Purchase #</th>
              <th className="py-2 pr-3">Supplier</th>
              <th className="py-2 pr-3">Status</th>
              <th className="py-2 pr-3">Total</th>
              <th className="py-2 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} className="border-b hover:bg-gray-50">
                <td className="py-2 pr-3 font-mono text-xs">{p.purchase_number}</td>
                <td className="py-2 pr-3">{p.supplier_name || '—'}</td>
                <td className="py-2 pr-3"><Badge variant="outline">{p.status}</Badge></td>
                <td className="py-2 pr-3 tabular-nums">{fmtMoney(p.grand_total)}</td>
                <td className="py-2 text-right">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      closeDrill();
                      navigate(`/dashboard/pharmacy/purchases/${p.id}/edit`);
                    }}
                  >
                    Open
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      );
    }

    if (type === 'low_stock') {
      return (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-600">
              <th className="py-2 pr-3">Medicine</th>
              <th className="py-2 pr-3">On hand</th>
              <th className="py-2 pr-3">Min</th>
              <th className="py-2 pr-3">Short</th>
              <th className="py-2 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const short = Math.max(0, (r.min_qty || 0) - (r.total_stock || 0));
              return (
                <tr key={r.medicine_id} className="border-b hover:bg-gray-50">
                  <td className="py-2 pr-3">
                    <div className="font-medium">{r.name}</div>
                    <div className="text-xs text-gray-500 font-mono">{r.medicine_code}</div>
                  </td>
                  <td className="py-2 pr-3 tabular-nums text-orange-700 font-medium">{r.total_stock}</td>
                  <td className="py-2 pr-3 tabular-nums">{r.min_qty}</td>
                  <td className="py-2 pr-3 tabular-nums">{short}</td>
                  <td className="py-2 text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        closeDrill();
                        navigate('/dashboard/pharmacy/purchases/new');
                      }}
                    >
                      Purchase
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      );
    }

    if (type === 'expiring') {
      const filtered = rows.filter((b) => {
        if (expiryFilter === 'expired') return (b.days_to_expiry ?? 0) < 0;
        if (expiryFilter === 'soon') return (b.days_to_expiry ?? 0) >= 0;
        return true;
      });
      if (filtered.length === 0) {
        return <p className="text-center py-8 text-sm text-gray-500">No batches in this filter</p>;
      }
      return (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-600">
              <th className="py-2 pr-3">Medicine</th>
              <th className="py-2 pr-3">Batch</th>
              <th className="py-2 pr-3">Qty</th>
              <th className="py-2 pr-3">Expiry</th>
              <th className="py-2 pr-3">Days</th>
              <th className="py-2 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((b) => {
              const expired = (b.days_to_expiry ?? 0) < 0;
              return (
                <tr key={b.batch_id} className="border-b hover:bg-gray-50">
                  <td className="py-2 pr-3">
                    <div className="font-medium">{b.medicine_name}</div>
                    <div className="text-xs text-gray-500 font-mono">{b.medicine_code || ''}</div>
                  </td>
                  <td className="py-2 pr-3 font-mono text-xs">{b.batch_number}</td>
                  <td className="py-2 pr-3 tabular-nums">{b.quantity_in_stock}</td>
                  <td className="py-2 pr-3 text-xs">{b.expiry_date}</td>
                  <td className="py-2 pr-3">
                    <Badge variant="outline" className={expired ? 'border-red-300 text-red-700' : 'border-orange-300 text-orange-700'}>
                      {expired ? `${Math.abs(b.days_to_expiry)}d ago` : `${b.days_to_expiry}d`}
                    </Badge>
                  </td>
                  <td className="py-2 text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        closeDrill();
                        navigate('/dashboard/pharmacy/inventory?expiring=90');
                      }}
                    >
                      Inventory
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      );
    }

    if (type === 'pending_rx') {
      return (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-600">
              <th className="py-2 pr-3">Rx #</th>
              <th className="py-2 pr-3">Patient</th>
              <th className="py-2 pr-3">Doctor</th>
              <th className="py-2 pr-3">Items</th>
              <th className="py-2 pr-3">Status</th>
              <th className="py-2 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((rx) => (
              <tr key={rx.id} className="border-b hover:bg-gray-50">
                <td className="py-2 pr-3 font-mono text-xs">{rx.prescription_number}</td>
                <td className="py-2 pr-3">{rx.patient_name || '—'}</td>
                <td className="py-2 pr-3 text-xs">{rx.doctor_name || '—'}</td>
                <td className="py-2 pr-3">{rx.items?.length || 0}</td>
                <td className="py-2 pr-3"><Badge variant="outline">{rx.status}</Badge></td>
                <td className="py-2 text-right">
                  <Button
                    size="sm"
                    onClick={() => {
                      closeDrill();
                      navigate('/dashboard/pharmacy/pending-rx');
                    }}
                  >
                    Dispense
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      );
    }

    if (type === 'sale_returns') {
      return (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-600">
              <th className="py-2 pr-3">Return #</th>
              <th className="py-2 pr-3">Patient</th>
              <th className="py-2 pr-3">Status</th>
              <th className="py-2 pr-3">Total</th>
              <th className="py-2 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-b hover:bg-gray-50">
                <td className="py-2 pr-3 font-mono text-xs">{r.return_number}</td>
                <td className="py-2 pr-3">{r.patient_name || '—'}</td>
                <td className="py-2 pr-3"><Badge variant="outline">{r.status}</Badge></td>
                <td className="py-2 pr-3 tabular-nums">{fmtMoney(r.grand_total)}</td>
                <td className="py-2 text-right">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      closeDrill();
                      navigate(`/dashboard/pharmacy/sale-returns/${r.id}`);
                    }}
                  >
                    Open
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      );
    }

    if (type === 'unmapped') {
      return (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-gray-600">
              <th className="py-2 pr-3">Code</th>
              <th className="py-2 pr-3">Name</th>
              <th className="py-2 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id} className="border-b hover:bg-gray-50">
                <td className="py-2 pr-3 font-mono text-xs">{m.medicine_code}</td>
                <td className="py-2 pr-3">{m.name}</td>
                <td className="py-2 text-right">
                  <Button
                    size="sm"
                    onClick={() => {
                      closeDrill();
                      navigate('/dashboard/pharmacy/unmapped-medicines');
                    }}
                  >
                    Map
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      );
    }

    return null;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-base font-semibold">Today&apos;s overview</h2>
          <p className="text-sm text-muted-foreground">
            Billing, stock alerts, and pending work
            {today ? ` · ${today}` : ''}
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={load} disabled={loading}>
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {loading && !data ? (
        <p className="text-sm text-muted-foreground py-6">Loading…</p>
      ) : data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <ActionKpiCard
              icon={Banknote}
              label="POS Sales"
              value={fmtMoney(posTotal)}
              sub={`${posCount} cash sale(s) today`}
              tone="green"
              onClick={hasPerm('view_sales') ? () => openDrill({
                type: 'pos_sales',
                title: 'POS sales today',
                description: 'Cash-at-pharmacy sales completed today',
                viewAll: {
                  label: 'View all sales',
                  onClick: () => navigate(`/dashboard/pharmacy/sales?date_from=${today}&date_to=${today}&billing_mode=cash_at_pharmacy`),
                },
              }) : undefined}
            />
            <ActionKpiCard
              icon={BedDouble}
              label="Inpatient Medicines"
              value={fmtMoney(ipTotal)}
              sub={`${ipCount} Rx / deferred sale(s) today`}
              tone="blue"
              onClick={hasPerm('view_sales') ? () => openDrill({
                type: 'ip_sales',
                title: 'Inpatient medicines today',
                description: 'Deferred-to-admission sales today (Rx-only dispenses appear under Pending Rx when still open)',
                viewAll: {
                  label: 'View all sales',
                  onClick: () => navigate(`/dashboard/pharmacy/sales?date_from=${today}&date_to=${today}&billing_mode=inpatient_bill`),
                },
              }) : undefined}
            />
            <ActionKpiCard
              icon={ShoppingCart}
              label="Total Pharmacy Billing"
              value={fmtMoney(billingTotal)}
              sub="POS + inpatient medicines"
              tone="amber"
              onClick={hasPerm('view_sales') ? () => openDrill({
                type: 'all_sales',
                title: 'All pharmacy sales today',
                description: 'Completed POS and inpatient deferred sales',
                viewAll: {
                  label: 'View all sales',
                  onClick: () => navigate(`/dashboard/pharmacy/sales?date_from=${today}&date_to=${today}`),
                },
              }) : undefined}
            />
          </div>

          <div>
            <h3 className="text-sm font-medium mb-2">Needs attention</h3>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <ActionKpiCard
                icon={AlertTriangle}
                label="Low Stock"
                value={data.low_stock_count}
                sub="Medicines below min"
                tone={data.low_stock_count > 0 ? 'orange' : 'slate'}
                onClick={hasPerm('view_low_stock') ? () => openDrill({
                  type: 'low_stock',
                  title: 'Low stock medicines',
                  description: 'On-hand quantity at or below minimum',
                  viewAll: {
                    label: 'Open inventory',
                    onClick: () => navigate('/dashboard/pharmacy/inventory?low=1'),
                  },
                }) : undefined}
              />
              <ActionKpiCard
                icon={CalendarX2}
                label="Expiring Soon"
                value={data.expiring_soon_count ?? 0}
                sub={
                  (data.already_expired_count ?? 0) > 0
                    ? `${data.already_expired_count} already expired · within 90 days`
                    : 'Batches within 90 days'
                }
                tone={(data.already_expired_count ?? 0) > 0
                  ? 'red'
                  : (data.expiring_soon_count ?? 0) > 0 ? 'orange' : 'slate'}
                onClick={hasPerm('view_expiring') ? () => {
                  setExpiryFilter((data.already_expired_count ?? 0) > 0 ? 'expired' : 'all');
                  openDrill({
                    type: 'expiring',
                    title: 'Expiring & expired batches',
                    description: 'Active batches with stock expiring within 90 days',
                    viewAll: {
                      label: 'Open inventory',
                      onClick: () => navigate('/dashboard/pharmacy/inventory?expiring=90'),
                    },
                  });
                } : undefined}
              />
              <ActionKpiCard
                icon={Pill}
                label="Pending Rx"
                value={data.pending_rx_count}
                sub="Awaiting dispensing"
                tone={data.pending_rx_count > 0 ? 'blue' : 'slate'}
                onClick={hasAnyPerm('view_dispense_queue', 'create_sale') ? () => openDrill({
                  type: 'pending_rx',
                  title: 'Pending prescriptions',
                  description: 'Prescriptions awaiting full or partial dispense',
                  viewAll: {
                    label: 'Open Pending Rx',
                    onClick: () => navigate('/dashboard/pharmacy/pending-rx'),
                  },
                }) : undefined}
              />
              {hasAnyPerm('manage_medicines', 'dispense_rx') && (
                <ActionKpiCard
                  icon={Link2}
                  label="Unmapped Meds"
                  value={data.unmapped_medicines_count ?? 0}
                  sub="Free-text IP medicines"
                  tone={(data.unmapped_medicines_count ?? 0) > 0 ? 'purple' : 'slate'}
                  onClick={() => openDrill({
                    type: 'unmapped',
                    title: 'Unmapped medicines',
                    description: 'Free-text stubs from inpatient orders — map to catalog',
                    viewAll: {
                      label: 'Open unmapped list',
                      onClick: () => navigate('/dashboard/pharmacy/unmapped-medicines'),
                    },
                  })}
                />
              )}
            </div>
          </div>

          <div>
            <h3 className="text-sm font-medium mb-2">Today&apos;s operations</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <ActionKpiCard
                icon={Receipt}
                label="Purchases"
                value={fmtMoney(data.today_purchases_total)}
                sub={`${data.today_purchases_count} purchase(s)`}
                tone="cyan"
                onClick={hasPerm('view_purchases') ? () => openDrill({
                  type: 'purchases',
                  title: "Today's purchases",
                  description: 'Purchases with entry date today',
                  viewAll: {
                    label: 'Open purchases',
                    onClick: () => navigate(`/dashboard/pharmacy/purchases?date_from=${today}&date_to=${today}`),
                  },
                }) : undefined}
              />
              {hasPerm('view_sale_returns') && (
                <ActionKpiCard
                  icon={RotateCcw}
                  label="Sale Returns"
                  value={data.today_sale_returns_count ?? 0}
                  sub="Returns dated today"
                  tone={(data.today_sale_returns_count ?? 0) > 0 ? 'amber' : 'slate'}
                  onClick={() => openDrill({
                    type: 'sale_returns',
                    title: "Today's sale returns",
                    description: 'Sale returns with return date today',
                    viewAll: {
                      label: 'Open sale returns',
                      onClick: () => navigate('/dashboard/pharmacy/sale-returns'),
                    },
                  })}
                />
              )}
            </div>
          </div>
        </>
      ) : (
        <p className="text-sm text-muted-foreground text-center py-8">Unable to load dashboard summary.</p>
      )}

      <DashboardDrillDialog
        open={!!drill}
        onOpenChange={(open) => { if (!open) closeDrill(); }}
        title={drill?.title || ''}
        description={drill?.description}
        loadRows={drill ? (drillLoaders[drill.type] || (async () => [])) : (async () => [])}
        renderRows={(rows) => renderDrillRows(drill?.type, rows)}
        viewAll={drill?.viewAll}
        filterBar={drill?.type === 'expiring' ? (
          <div className="flex flex-wrap gap-2">
            {EXPIRY_FILTERS.map((f) => (
              <Button
                key={f.id}
                size="sm"
                variant={expiryFilter === f.id ? 'default' : 'outline'}
                onClick={() => setExpiryFilter(f.id)}
              >
                {f.label}
              </Button>
            ))}
          </div>
        ) : null}
      />
    </div>
  );
}
