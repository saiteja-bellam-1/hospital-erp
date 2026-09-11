import React, { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import ActionKpiCard from '../../../components/dashboard/ActionKpiCard';
import DashboardDrillDialog from '../../../components/dashboard/DashboardDrillDialog';
import { useToast } from '../../../hooks/use-toast';
import { useCanteenPermissions } from '../../../hooks/useCanteenPermissions';
import { localDateString } from '../../../utils/localDate';
import {
  RefreshCw, Clock, Flame, PackageCheck, Truck, Banknote, UtensilsCrossed,
} from 'lucide-react';

const fmt = (n) => `₹${Number(n || 0).toFixed(2)}`;

const STATUS_BADGE = {
  pending: 'bg-blue-100 text-blue-800',
  preparing: 'bg-amber-100 text-amber-800',
  ready: 'bg-purple-100 text-purple-800',
  delivered: 'bg-green-100 text-green-800',
  cancelled: 'bg-gray-100 text-gray-500',
  completed: 'bg-green-100 text-green-800',
  voided: 'bg-red-100 text-red-700',
};

function errMsg(e) {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join('; ');
  return e?.message || 'Request failed';
}

export default function CanteenDashboard() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const { hasPerm } = useCanteenPermissions();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drill, setDrill] = useState(null);
  const today = localDateString();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/canteen/dashboard');
      setData(res.data);
    } catch (e) {
      toast({ variant: 'destructive', title: 'Failed to load dashboard', description: errMsg(e) });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => { load(); }, [load]);

  const status = data?.orders_by_status || {};
  const closeDrill = () => setDrill(null);

  const loadOrders = useCallback(async (statusFilter) => {
    const params = { from_date: today, to_date: today };
    if (statusFilter === 'open') {
      /* fetch all non-cancelled and filter client-side */
    } else if (statusFilter) {
      params.status = statusFilter;
    } else {
      params.include_cancelled = true;
    }
    const r = await axios.get('/api/canteen/orders', { params });
    let rows = Array.isArray(r.data) ? r.data : [];
    if (statusFilter === 'open') {
      rows = rows.filter((o) => ['pending', 'preparing', 'ready'].includes(o.status));
    }
    return rows;
  }, [today]);

  const loadSales = useCallback(async () => {
    const r = await axios.get('/api/canteen/sales', {
      params: { from_date: today, to_date: today, status: 'completed', limit: 100 },
    });
    return Array.isArray(r.data) ? r.data : [];
  }, [today]);

  const renderOrderRows = (rows) => (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left text-muted-foreground">
          <th className="py-2 pr-3 font-medium">Patient</th>
          <th className="py-2 pr-3 font-medium">Room</th>
          <th className="py-2 pr-3 font-medium">Items</th>
          <th className="py-2 pr-3 font-medium">Status</th>
          <th className="py-2 text-right font-medium">Action</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((o) => (
          <tr key={o.id} className="border-b">
            <td className="py-2 pr-3">{o.patient_name || `Patient #${o.patient_id}`}</td>
            <td className="py-2 pr-3 text-xs">{o.room_number || '—'}</td>
            <td className="py-2 pr-3 text-xs">
              {(o.items || []).map((i) => `${i.quantity}× ${i.item_name}`).join(', ') || '—'}
            </td>
            <td className="py-2 pr-3">
              <Badge className={STATUS_BADGE[o.status] || ''}>{o.status}</Badge>
            </td>
            <td className="py-2 text-right">
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  closeDrill();
                  navigate(`/dashboard/canteen/orders?status=${o.status || 'open'}`);
                }}
              >
                Open queue
              </Button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  const renderSaleRows = (rows) => (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left text-muted-foreground">
          <th className="py-2 pr-3 font-medium">Sale #</th>
          <th className="py-2 pr-3 font-medium">Customer</th>
          <th className="py-2 pr-3 font-medium">Payment</th>
          <th className="py-2 pr-3 font-medium">Total</th>
          <th className="py-2 text-right font-medium">Action</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((s) => (
          <tr key={s.id} className="border-b">
            <td className="py-2 pr-3 font-mono text-xs">{s.sale_number}</td>
            <td className="py-2 pr-3">{s.customer_name || 'Walk-in'}</td>
            <td className="py-2 pr-3 text-xs uppercase">{s.payment_type || '—'}</td>
            <td className="py-2 pr-3 tabular-nums">{fmt(s.grand_total)}</td>
            <td className="py-2 text-right">
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  closeDrill();
                  navigate('/dashboard/canteen/sales');
                }}
              >
                History
              </Button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-base font-semibold">Today&apos;s overview</h2>
          <p className="text-sm text-muted-foreground">
            Kitchen queue and walk-in sales
            {data?.date ? ` · ${data.date}` : ` · ${today}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {(hasPerm('view_orders') || hasPerm('manage_order_status')) && (
            <Button asChild size="sm" variant="outline">
              <Link to="/dashboard/canteen/orders">IP Food Orders</Link>
            </Button>
          )}
          {hasPerm('create_sale') && (
            <Button asChild size="sm" variant="outline">
              <Link to="/dashboard/canteen/pos">Sales Counter</Link>
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      {loading && !data ? (
        <p className="text-sm text-muted-foreground py-6">Loading…</p>
      ) : data ? (
        <>
          <div>
            <h3 className="text-sm font-medium mb-2">Kitchen queue (today)</h3>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <ActionKpiCard
                icon={UtensilsCrossed}
                label="Open Orders"
                value={data.open_orders ?? 0}
                sub={`${data.orders_today ?? 0} total today`}
                tone={(data.open_orders ?? 0) > 0 ? 'orange' : 'slate'}
                onClick={hasPerm('view_orders') ? () => setDrill({
                  type: 'orders',
                  title: 'Open IP food orders',
                  description: 'Pending, preparing, and ready for today',
                  loadRows: () => loadOrders('open'),
                  viewAll: {
                    label: 'Open kitchen queue',
                    onClick: () => navigate('/dashboard/canteen/orders?status=open'),
                  },
                }) : undefined}
              />
              <ActionKpiCard
                icon={Clock}
                label="Pending"
                value={status.pending || 0}
                sub="Awaiting kitchen"
                tone={(status.pending || 0) > 0 ? 'blue' : 'slate'}
                onClick={hasPerm('view_orders') ? () => setDrill({
                  type: 'orders',
                  title: 'Pending orders',
                  loadRows: () => loadOrders('pending'),
                  viewAll: {
                    label: 'Open kitchen queue',
                    onClick: () => navigate('/dashboard/canteen/orders?status=pending'),
                  },
                }) : undefined}
              />
              <ActionKpiCard
                icon={Flame}
                label="Preparing"
                value={status.preparing || 0}
                sub="In kitchen"
                tone={(status.preparing || 0) > 0 ? 'amber' : 'slate'}
                onClick={hasPerm('view_orders') ? () => setDrill({
                  type: 'orders',
                  title: 'Preparing orders',
                  loadRows: () => loadOrders('preparing'),
                  viewAll: {
                    label: 'Open kitchen queue',
                    onClick: () => navigate('/dashboard/canteen/orders?status=preparing'),
                  },
                }) : undefined}
              />
              <ActionKpiCard
                icon={PackageCheck}
                label="Ready"
                value={status.ready || 0}
                sub="Awaiting delivery"
                tone={(status.ready || 0) > 0 ? 'purple' : 'slate'}
                onClick={hasPerm('view_orders') ? () => setDrill({
                  type: 'orders',
                  title: 'Ready for delivery',
                  loadRows: () => loadOrders('ready'),
                  viewAll: {
                    label: 'Open kitchen queue',
                    onClick: () => navigate('/dashboard/canteen/orders?status=ready'),
                  },
                }) : undefined}
              />
            </div>
          </div>

          <div>
            <h3 className="text-sm font-medium mb-2">Today&apos;s operations</h3>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <ActionKpiCard
                icon={Truck}
                label="Delivered Today"
                value={status.delivered || 0}
                sub="Completed ward orders"
                tone="green"
                onClick={hasPerm('view_orders') ? () => setDrill({
                  type: 'orders',
                  title: 'Delivered today',
                  loadRows: () => loadOrders('delivered'),
                  viewAll: {
                    label: 'Open kitchen queue',
                    onClick: () => navigate('/dashboard/canteen/orders?status=delivered'),
                  },
                }) : undefined}
              />
              {hasPerm('view_sales') && (
                <ActionKpiCard
                  icon={Banknote}
                  label="POS Sales"
                  value={fmt(data.today_sales_total)}
                  sub={`${data.today_sales_count || 0} walk-in sale(s)`}
                  tone="green"
                  onClick={() => setDrill({
                    type: 'sales',
                    title: 'POS sales today',
                    loadRows: loadSales,
                    viewAll: {
                      label: 'Open sales history',
                      onClick: () => navigate('/dashboard/canteen/sales'),
                    },
                  })}
                />
              )}
              {(hasPerm('view_catalog') || hasPerm('manage_catalog')) && (
                <ActionKpiCard
                  icon={UtensilsCrossed}
                  label="Active Menu Items"
                  value={data.active_catalog_items || 0}
                  sub="Sellable catalog items"
                  tone="cyan"
                  onClick={() => navigate('/dashboard/canteen/catalog')}
                />
              )}
            </div>
          </div>
        </>
      ) : (
        <p className="text-sm text-muted-foreground text-center py-8">Unable to load dashboard.</p>
      )}

      <DashboardDrillDialog
        open={!!drill}
        onOpenChange={(open) => { if (!open) closeDrill(); }}
        title={drill?.title || ''}
        description={drill?.description}
        loadRows={drill?.loadRows || (async () => [])}
        renderRows={(rows) => (drill?.type === 'sales' ? renderSaleRows(rows) : renderOrderRows(rows))}
        viewAll={drill?.viewAll ? {
          ...drill.viewAll,
          onClick: () => {
            closeDrill();
            drill.viewAll.onClick();
          },
        } : undefined}
      />
    </div>
  );
}
