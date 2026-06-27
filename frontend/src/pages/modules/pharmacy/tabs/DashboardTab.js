import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent } from '../../../../components/ui/card';
import { ShoppingCart, Receipt, AlertTriangle, Pill, RefreshCw, CalendarX2 } from 'lucide-react';
import { Button } from '../../../../components/ui/button';
import { usePharmacyStore } from '../../../../contexts/PharmacyStoreContext';

const KpiCard = ({ icon: Icon, label, value, sub, color = 'text-gray-900' }) => (
  <Card>
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

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={load} disabled={loading}>
          <RefreshCw className="h-3 w-3 mr-1" /> Refresh
        </Button>
      </div>
      {data && (
        <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-4">
          <KpiCard icon={ShoppingCart} label="Today's Sales" value={`₹${data.today_sales_total.toFixed(2)}`} sub={`${data.today_sales_count} sale(s)`} color="text-green-700" />
          <KpiCard icon={Receipt} label="Today's Purchases" value={`₹${data.today_purchases_total.toFixed(2)}`} sub={`${data.today_purchases_count} purchase(s)`} />
          <KpiCard icon={AlertTriangle} label="Low Stock" value={data.low_stock_count} sub="Medicines below min" color={data.low_stock_count > 0 ? 'text-orange-600' : ''} />
          <KpiCard icon={Pill} label="Pending Rx" value={data.pending_rx_count} sub="Awaiting dispensing" />
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
      )}
    </div>
  );
}
