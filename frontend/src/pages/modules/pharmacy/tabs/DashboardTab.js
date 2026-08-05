import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../../../../components/ui/card';
import {
  ShoppingCart, Receipt, AlertTriangle, Pill, RefreshCw, CalendarX2, BedDouble, Banknote,
} from 'lucide-react';
import { Button } from '../../../../components/ui/button';
import { usePharmacyStore } from '../../../../contexts/PharmacyStoreContext';

const fmtMoney = (n) => `₹${Number(n || 0).toFixed(2)}`;

const KpiCard = ({ icon: Icon, label, value, sub, color = 'text-gray-900', accent }) => (
  <Card className={accent ? `border-l-4 ${accent}` : undefined}>
    <CardContent className="pt-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500">{label}</p>
          <p className={`text-2xl font-bold ${color}`}>{value}</p>
          {sub && <p className="text-xs text-gray-500 mt-1">{sub}</p>}
        </div>
        <Icon className="h-8 w-8 text-gray-300" />
      </div>
    </CardContent>
  </Card>
);

export default function DashboardTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const { storeParams } = usePharmacyStore();

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get('/api/pharmacy/dashboard', { params: storeParams });
      setData(r.data);
    } catch (e) { /* silent — dashboard tab is best-effort */ }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [storeParams]);

  const posTotal = data?.today_pos_sales_total ?? data?.today_sales_total ?? 0;
  const posCount = data?.today_pos_sales_count ?? data?.today_sales_count ?? 0;
  const ipTotal = data?.today_ip_medicines_total ?? 0;
  const ipCount = data?.today_ip_medicines_count ?? 0;
  const billingTotal = Number(posTotal) + Number(ipTotal);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-gray-900">Today&apos;s billing</h2>
          <p className="text-sm text-gray-500">
            POS cash sales and inpatient medicines charged to admission bills
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={load} disabled={loading}>
          <RefreshCw className="h-3 w-3 mr-1" /> Refresh
        </Button>
      </div>

      {data && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <KpiCard
              icon={Banknote}
              label="POS Sales"
              value={fmtMoney(posTotal)}
              sub={`${posCount} cash sale(s) today`}
              color="text-green-700"
              accent="border-l-green-500"
            />
            <KpiCard
              icon={BedDouble}
              label="Inpatient Medicines"
              value={fmtMoney(ipTotal)}
              sub={`${ipCount} Rx / deferred sale(s) today`}
              color="text-blue-700"
              accent="border-l-blue-500"
            />
            <KpiCard
              icon={ShoppingCart}
              label="Total Pharmacy Billing"
              value={fmtMoney(billingTotal)}
              sub="POS + inpatient medicines"
              color="text-gray-900"
              accent="border-l-gray-400"
            />
          </div>

          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-3">Operations</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <KpiCard
                icon={Receipt}
                label="Today's Purchases"
                value={fmtMoney(data.today_purchases_total)}
                sub={`${data.today_purchases_count} purchase(s)`}
              />
              <KpiCard
                icon={AlertTriangle}
                label="Low Stock"
                value={data.low_stock_count}
                sub="Medicines below min"
                color={data.low_stock_count > 0 ? 'text-orange-600' : ''}
              />
              <KpiCard
                icon={Pill}
                label="Pending Rx"
                value={data.pending_rx_count}
                sub="Awaiting dispensing"
              />
              <KpiCard
                icon={CalendarX2}
                label="Expiring Soon"
                value={data.expiring_soon_count ?? 0}
                sub={
                  (data.already_expired_count ?? 0) > 0
                    ? `${data.already_expired_count} already expired · within 90 days`
                    : 'Batches within 90 days'
                }
                color={(data.already_expired_count ?? 0) > 0
                  ? 'text-red-600'
                  : (data.expiring_soon_count ?? 0) > 0 ? 'text-orange-600' : ''}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
