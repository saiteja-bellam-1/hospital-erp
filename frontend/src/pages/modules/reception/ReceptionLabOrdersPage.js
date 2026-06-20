import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { useToast } from '../../../hooks/use-toast';
import { useAuth } from '../../../contexts/AuthContext';
import {
  TestTube,
  RefreshCw,
  Printer,
  Search,
  Package,
  ArrowLeft,
} from 'lucide-react';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';

const getLabStatusColor = (status) => {
  const colors = {
    ordered: 'bg-blue-100 text-blue-800',
    collected: 'bg-yellow-100 text-yellow-800',
    processing: 'bg-orange-100 text-orange-800',
    completed: 'bg-green-100 text-green-800',
    cancelled: 'bg-red-100 text-red-800',
  };
  return colors[status] || 'bg-gray-100 text-gray-800';
};

const formatDate = (value) => {
  if (!value) return '—';
  return new Date(value).toLocaleDateString();
};

const ReceptionLabOrdersPage = () => {
  const { toast } = useToast();
  const { user } = useAuth();
  const roles = (() => {
    const r = user?.roles;
    if (Array.isArray(r) && r.length > 0) {
      return r.map((x) => (typeof x === 'string' ? x : x?.name)).filter(Boolean);
    }
    return user?.role ? [user.role] : [];
  })();
  const dashboardPath = roles.some((role) => ['lab_admin', 'lab_technician'].includes(role))
    ? '/dashboard/lab-home'
    : '/dashboard/reception-home';
  const today = new Date().toISOString().split('T')[0];
  const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [dateFrom, setDateFrom] = useState(thirtyDaysAgo);
  const [dateTo, setDateTo] = useState(today);
  const [reportPreview, setReportPreview] = useState(null);

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const params = new URLSearchParams({
        status: 'completed',
        date_from: dateFrom,
        date_to: dateTo,
      });
      const res = await fetch(`/api/lab/orders?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setOrders(Array.isArray(data) ? data : []);
      } else {
        setOrders([]);
        toast({ variant: 'destructive', title: 'Error', description: 'Failed to load lab orders' });
      }
    } catch (err) {
      console.error('Failed to fetch lab orders:', err);
      setOrders([]);
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to load lab orders' });
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, toast]);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

  const openReportPreview = (reportId, orderNumber, packageBookingId = null) => {
    if (packageBookingId) {
      setReportPreview({
        path: `/api/lab/reports/package/${packageBookingId}/download`,
        title: `${orderNumber} — All Reports`,
      });
    } else {
      setReportPreview({
        path: `/api/lab/reports/${reportId}/download`,
        title: `Lab Report — ${orderNumber}`,
      });
    }
  };

  const filteredOrders = orders.filter((order) => {
    if (!searchTerm) return true;
    const q = searchTerm.toLowerCase();
    return (
      order.patient_name?.toLowerCase().includes(q) ||
      order.test_name?.toLowerCase().includes(q) ||
      order.order_number?.toLowerCase().includes(q) ||
      order.doctor_name?.toLowerCase().includes(q) ||
      order.package_name?.toLowerCase().includes(q)
    );
  });

  const packageGroups = {};
  const standalone = [];
  for (const order of filteredOrders) {
    if (order.package_booking_id) {
      if (!packageGroups[order.package_booking_id]) {
        packageGroups[order.package_booking_id] = {
          name: order.package_name || 'Package',
          patient_name: order.patient_name,
          doctor_name: order.doctor_name,
          orders: [],
        };
      }
      packageGroups[order.package_booking_id].orders.push(order);
    } else {
      standalone.push(order);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link to={dashboardPath}>
              <Button variant="ghost" size="sm" className="text-gray-500 -ml-2">
                <ArrowLeft className="h-4 w-4 mr-1" /> Dashboard
              </Button>
            </Link>
          </div>
          <h1 className="text-3xl font-bold text-gray-900">Completed Lab Orders</h1>
          <p className="text-gray-600">View and print reports for completed lab tests</p>
        </div>
        <Button variant="outline" onClick={fetchOrders} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <Card>
        <CardContent className="p-6">
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <Label>From</Label>
              <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </div>
            <div>
              <Label>To</Label>
              <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </div>
            <Button variant="outline" onClick={() => { setDateFrom(today); setDateTo(today); }}>
              Today
            </Button>
            <Button variant="outline" onClick={() => { setDateFrom(thirtyDaysAgo); setDateTo(today); }}>
              Last 30 days
            </Button>
            <div className="flex-1 min-w-[200px]">
              <Label>Search</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                <Input
                  className="pl-9"
                  placeholder="Patient, test, order #..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TestTube className="h-5 w-5" />
            <span>Completed Orders</span>
            <Badge variant="outline">{filteredOrders.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="text-center py-12">
              <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4 text-blue-600" />
              <p className="text-gray-600">Loading lab orders...</p>
            </div>
          ) : filteredOrders.length === 0 ? (
            <div className="text-center py-12">
              <TestTube className="h-10 w-10 text-gray-400 mx-auto mb-2" />
              <p className="text-gray-500">No completed lab orders found for this period</p>
            </div>
          ) : (
            <div className="space-y-4">
              {Object.entries(packageGroups).map(([bookingId, pkg]) => (
                <div key={bookingId} className="border-2 border-indigo-200 bg-indigo-50/30 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3 pb-2 border-b border-indigo-200">
                    <Package className="h-4 w-4 text-indigo-600" />
                    <span className="font-semibold text-indigo-700">{pkg.name}</span>
                    <Badge className="bg-indigo-100 text-indigo-700 text-xs">{pkg.orders.length} tests</Badge>
                    <span className="text-sm text-gray-500 ml-auto">
                      {pkg.patient_name} • {pkg.doctor_name || '—'}
                    </span>
                    {pkg.orders.some((o) => o.has_report) && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs border-indigo-300 text-indigo-700"
                        onClick={() => openReportPreview(null, pkg.name, Number(bookingId))}
                      >
                        <Printer className="h-3 w-3 mr-1" /> All Reports
                      </Button>
                    )}
                  </div>
                  <div className="space-y-2">
                    {pkg.orders.map((order) => (
                      <div
                        key={order.id}
                        className="flex items-center justify-between bg-white rounded p-3 border border-indigo-100"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-medium">{order.test_name}</span>
                            <Badge className={`text-xs ${getLabStatusColor(order.status)}`}>{order.status}</Badge>
                          </div>
                          <p className="text-xs text-gray-500 mt-1">
                            #{order.order_number} • {formatDate(order.completion_date || order.order_date)}
                          </p>
                        </div>
                        {order.has_report && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="h-7 text-xs ml-2"
                            onClick={() => openReportPreview(order.report_id, order.order_number)}
                          >
                            <Printer className="h-3 w-3 mr-1" /> Report
                          </Button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              {standalone.map((order) => (
                <div
                  key={order.id}
                  className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-gray-900">{order.patient_name}</span>
                      <Badge className={`text-xs ${getLabStatusColor(order.status)}`}>{order.status}</Badge>
                      {order.payment_status === 'paid' ? (
                        <Badge className="text-xs bg-green-100 text-green-800">Paid</Badge>
                      ) : (
                        <Badge className="text-xs bg-red-100 text-red-800">Unpaid</Badge>
                      )}
                    </div>
                    <p className="text-sm text-gray-600 mt-1">
                      {order.test_name} — ₹{(order.amount || 0).toFixed(0)}
                    </p>
                    <p className="text-xs text-gray-400">
                      #{order.order_number} • {order.doctor_name || '—'} • Completed {formatDate(order.completion_date || order.order_date)}
                    </p>
                  </div>
                  {order.has_report && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-8 text-xs ml-2"
                      onClick={() => openReportPreview(order.report_id, order.order_number)}
                    >
                      <Printer className="h-3 w-3 mr-1" /> View Report
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <PdfPreviewDialog
        open={!!reportPreview}
        onClose={() => setReportPreview(null)}
        title={reportPreview?.title || 'Lab Report Preview'}
        path={reportPreview?.path || null}
      />
    </div>
  );
};

export default ReceptionLabOrdersPage;
