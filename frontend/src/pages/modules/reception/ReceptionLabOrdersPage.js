import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Textarea } from '../../../components/ui/textarea';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../../components/ui/dialog';
import { useToast } from '../../../hooks/use-toast';
import { useAuth } from '../../../contexts/AuthContext';
import {
  TestTube,
  RefreshCw,
  Printer,
  Search,
  Package,
  ArrowLeft,
  Banknote,
  Clock,
  CheckCircle,
  XCircle,
  Receipt,
} from 'lucide-react';
import PdfPreviewDialog from '../../../components/PdfPreviewDialog';
import { localDateString, localDateStringOffset } from '../../../utils/localDate';
import { matchesLabOrderSearch } from '../../../utils/barcodeSearch';

const STATUS_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'pending', label: 'Pending' },
  { id: 'ordered', label: 'Ordered' },
  { id: 'completed', label: 'Completed' },
];

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

const isInpatientOrder = (order) => order?.order_source === 'inpatient' || !!order?.admission_id;

const matchesStatusFilter = (order, filter) => {
  if (filter === 'all') return true;
  if (order.status === 'cancelled') return false;
  if (filter === 'pending') return order.payment_status !== 'paid';
  if (filter === 'ordered') return order.status === 'ordered';
  if (filter === 'completed') return order.status === 'completed';
  return true;
};

const emptyMessage = (filter) => {
  if (filter === 'pending') return 'No pending lab orders for this period';
  if (filter === 'ordered') return 'No orders with ordered status for this period';
  if (filter === 'completed') return 'No completed lab orders for this period';
  return 'No lab orders found for this period';
};

const errorDetail = (data, fallback) => (
  typeof data?.detail === 'string' ? data.detail : fallback
);

const ReceptionLabOrdersPage = () => {
  const { toast } = useToast();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const roles = (() => {
    const r = user?.roles;
    if (Array.isArray(r) && r.length > 0) {
      return r.map((x) => (typeof x === 'string' ? x : x?.name)).filter(Boolean);
    }
    return user?.role ? [user.role] : [];
  })();
  const dashboardPath = roles.some((role) => ['lab_admin', 'lab_technician'].includes(role))
    ? '/dashboard/lab-home'
    : '/dashboard/outpatient';
  const today = localDateString();
  const thirtyDaysAgo = localDateStringOffset(-30);
  const initialStatus = STATUS_FILTERS.some((f) => f.id === searchParams.get('status'))
    ? searchParams.get('status')
    : 'all';

  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [dateFrom, setDateFrom] = useState(searchParams.get('range') === 'today' ? today : thirtyDaysAgo);
  const [dateTo, setDateTo] = useState(today);
  const [statusFilter, setStatusFilter] = useState(initialStatus);
  const [reportPreview, setReportPreview] = useState(null);

  const [showLabPaymentDialog, setShowLabPaymentDialog] = useState(false);
  const [pendingLabOrders, setPendingLabOrders] = useState([]);
  const [labPaymentLoading, setLabPaymentLoading] = useState(false);
  const [labPaymentMethod, setLabPaymentMethod] = useState('cash');
  const [labDiscount, setLabDiscount] = useState('');
  const [labBillPdfUrl, setLabBillPdfUrl] = useState(null);
  const [showLabBillPreview, setShowLabBillPreview] = useState(false);
  const [showLabCancelDialog, setShowLabCancelDialog] = useState(false);
  const [labCancelOrder, setLabCancelOrder] = useState(null);
  const [labCancelReason, setLabCancelReason] = useState('');
  const [labCancelLoading, setLabCancelLoading] = useState(false);

  const fetchOrders = useCallback(async (search = '') => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const params = new URLSearchParams({
        date_from: dateFrom,
        date_to: dateTo,
        reception_view: 'true',
      });
      const q = (search || '').trim();
      if (q) params.set('search', q);
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
    const t = setTimeout(() => fetchOrders(searchTerm), 300);
    return () => clearTimeout(t);
  }, [searchTerm, fetchOrders]);

  const applyStatusFilter = (id) => {
    setStatusFilter(id);
    const next = new URLSearchParams(searchParams);
    if (id === 'all') next.delete('status');
    else next.set('status', id);
    setSearchParams(next, { replace: true });
  };

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

  const openLabPaymentDialog = async (patientId) => {
    setLabPaymentLoading(true);
    setShowLabPaymentDialog(true);
    setPendingLabOrders([]);
    setLabDiscount('');
    setLabPaymentMethod('cash');
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/lab/orders/patient/${patientId}/pending-payment`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setPendingLabOrders(await res.json());
    } catch (err) {
      console.error('Failed to fetch pending lab payments:', err);
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to load pending payments' });
    } finally {
      setLabPaymentLoading(false);
    }
  };

  const collectAllLabPayments = async () => {
    if (pendingLabOrders.length === 0 || labPaymentLoading) return;
    const patientId = pendingLabOrders[0].patient_id;
    setLabPaymentLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/lab/orders/patient/${patientId}/bill`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ payment_method: labPaymentMethod, discount_amount: parseFloat(labDiscount) || 0 }),
      });
      if (res.ok) {
        const blob = await res.blob();
        if (labBillPdfUrl) window.URL.revokeObjectURL(labBillPdfUrl);
        const url = window.URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
        setLabBillPdfUrl(url);
        setShowLabBillPreview(true);
        setShowLabPaymentDialog(false);
        setPendingLabOrders([]);
        toast({ title: 'Payment collected', description: 'Lab bill is ready to print' });
        fetchOrders(searchTerm);
      } else {
        const err = await res.json().catch(() => ({}));
        toast({ variant: 'destructive', title: 'Error', description: errorDetail(err, 'Bill generation failed') });
      }
    } catch (err) {
      toast({ variant: 'destructive', title: 'Error', description: 'Failed to generate lab bill' });
    } finally {
      setLabPaymentLoading(false);
    }
  };

  const openLabCancelDialog = (order) => {
    setLabCancelOrder(order);
    setLabCancelReason('');
    setShowLabCancelDialog(true);
  };

  const confirmCancelLabOrder = async () => {
    if (!labCancelOrder) return;
    setLabCancelLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/lab/orders/${labCancelOrder.id}/cancel`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: labCancelReason.trim() || null }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast({ variant: 'destructive', title: 'Unable to cancel', description: errorDetail(err, 'Failed to cancel lab order') });
        return;
      }
      setShowLabCancelDialog(false);
      setLabCancelOrder(null);
      setPendingLabOrders((rows) => rows.filter((order) => order.id !== labCancelOrder.id));
      toast({ title: 'Order cancelled', description: `${labCancelOrder.test_name} was cancelled` });
      fetchOrders(searchTerm);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Unable to cancel', description: 'Failed to cancel lab order' });
    } finally {
      setLabCancelLoading(false);
    }
  };

  const closeBillPreview = () => {
    if (labBillPdfUrl) {
      window.URL.revokeObjectURL(labBillPdfUrl);
      setLabBillPdfUrl(null);
    }
    setShowLabBillPreview(false);
  };

  const searchedOrders = useMemo(
    () => orders.filter((order) => matchesLabOrderSearch(order, searchTerm)),
    [orders, searchTerm],
  );

  const counts = useMemo(() => ({
    all: searchedOrders.length,
    pending: searchedOrders.filter((order) => matchesStatusFilter(order, 'pending')).length,
    ordered: searchedOrders.filter((order) => matchesStatusFilter(order, 'ordered')).length,
    completed: searchedOrders.filter((order) => matchesStatusFilter(order, 'completed')).length,
  }), [searchedOrders]);

  const filteredOrders = searchedOrders.filter((order) => matchesStatusFilter(order, statusFilter));

  const packageGroups = {};
  const standalone = [];
  for (const order of filteredOrders) {
    if (order.package_booking_id) {
      if (!packageGroups[order.package_booking_id]) {
        packageGroups[order.package_booking_id] = {
          name: order.package_name || 'Package',
          patient_name: order.patient_name,
          patient_id: order.patient_id,
          doctor_name: order.doctor_name,
          orders: [],
        };
      }
      packageGroups[order.package_booking_id].orders.push(order);
    } else {
      standalone.push(order);
    }
  }

  const pendingTotal = pendingLabOrders.reduce((sum, order) => sum + (order.amount || 0), 0);
  const payableTotal = pendingTotal - (parseFloat(labDiscount) || 0);

  const renderOrderActions = (order, { showCollect = true } = {}) => (
    <div className="flex items-center gap-1 ml-2 shrink-0">
      {order.payment_status !== 'paid' && order.status === 'ordered' && (
        <Button
          size="sm"
          variant="ghost"
          className="h-8 px-2 text-xs text-red-600 hover:bg-red-50 hover:text-red-700"
          onClick={() => openLabCancelDialog(order)}
        >
          <XCircle className="h-3.5 w-3.5 mr-1" />
          Cancel
        </Button>
      )}
      {showCollect && order.payment_status !== 'paid' && order.status !== 'cancelled' && (
        <Button size="sm" className="h-8 px-2 text-xs" onClick={() => openLabPaymentDialog(order.patient_id)}>
          <Banknote className="h-3.5 w-3.5 mr-1" />
          Collect Payment
        </Button>
      )}
      {order.has_report && (
        <Button
          size="sm"
          variant="outline"
          className="h-8 text-xs"
          onClick={() => openReportPreview(order.report_id, order.order_number)}
        >
          <Printer className="h-3 w-3 mr-1" /> View Report
        </Button>
      )}
    </div>
  );

  const renderMeta = (order) => (
    <div className="flex items-center gap-2 flex-wrap">
      <Badge className={`text-xs ${getLabStatusColor(order.status)}`}>{order.status}</Badge>
      {order.status !== 'cancelled' && (
        order.payment_status === 'paid' ? (
          <Badge className="text-xs bg-green-100 text-green-800">Paid</Badge>
        ) : (
          <Badge className="text-xs bg-red-100 text-red-800">Pending</Badge>
        )
      )}
      {isInpatientOrder(order) && (
        <Badge className="text-xs bg-orange-100 text-orange-800">Inpatient</Badge>
      )}
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link to={dashboardPath}>
              <Button variant="ghost" size="sm" className="text-gray-500 -ml-2">
                <ArrowLeft className="h-4 w-4 mr-1" /> Dashboard
              </Button>
            </Link>
          </div>
          <h1 className="text-3xl font-bold text-gray-900">Lab Orders</h1>
          <p className="text-gray-600">Pending payment, ordered, and completed tests, including inpatient orders</p>
        </div>
        <Button variant="outline" onClick={() => fetchOrders(searchTerm)} disabled={loading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <button
          type="button"
          onClick={() => applyStatusFilter('pending')}
          className={`rounded-lg border p-4 text-left transition-shadow hover:shadow-md ${statusFilter === 'pending' ? 'border-red-300 bg-red-50 ring-2 ring-red-200' : 'bg-white'}`}
        >
          <div className="flex items-center gap-2 text-sm font-medium text-red-700">
            <Banknote className="h-4 w-4" /> Pending payment
          </div>
          <p className="mt-1 text-2xl font-semibold text-gray-900">{counts.pending}</p>
          <p className="text-xs text-gray-500">Unpaid, including ward orders</p>
        </button>
        <button
          type="button"
          onClick={() => applyStatusFilter('ordered')}
          className={`rounded-lg border p-4 text-left transition-shadow hover:shadow-md ${statusFilter === 'ordered' ? 'border-blue-300 bg-blue-50 ring-2 ring-blue-200' : 'bg-white'}`}
        >
          <div className="flex items-center gap-2 text-sm font-medium text-blue-700">
            <Clock className="h-4 w-4" /> Ordered
          </div>
          <p className="mt-1 text-2xl font-semibold text-gray-900">{counts.ordered}</p>
          <p className="text-xs text-gray-500">Status is ordered</p>
        </button>
        <button
          type="button"
          onClick={() => applyStatusFilter('completed')}
          className={`rounded-lg border p-4 text-left transition-shadow hover:shadow-md ${statusFilter === 'completed' ? 'border-green-300 bg-green-50 ring-2 ring-green-200' : 'bg-white'}`}
        >
          <div className="flex items-center gap-2 text-sm font-medium text-green-700">
            <CheckCircle className="h-4 w-4" /> Completed
          </div>
          <p className="mt-1 text-2xl font-semibold text-gray-900">{counts.completed}</p>
          <p className="text-xs text-gray-500">Reports ready to print</p>
        </button>
      </div>

      <Card>
        <CardContent className="p-6 space-y-4">
          <div className="flex flex-wrap gap-2">
            {STATUS_FILTERS.map((filter) => (
              <Button
                key={filter.id}
                size="sm"
                variant={statusFilter === filter.id ? 'default' : 'outline'}
                onClick={() => applyStatusFilter(filter.id)}
              >
                {filter.label}
                <Badge variant="secondary" className="ml-2">{counts[filter.id]}</Badge>
              </Button>
            ))}
          </div>
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
                  placeholder="Patient, test, order #, or scan barcode…"
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
            <span>
              {statusFilter === 'pending' && 'Pending payment'}
              {statusFilter === 'ordered' && 'Ordered'}
              {statusFilter === 'completed' && 'Completed'}
              {statusFilter === 'all' && 'All lab orders'}
            </span>
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
              <p className="text-gray-500">{emptyMessage(statusFilter)}</p>
            </div>
          ) : (
            <div className="space-y-4">
              {Object.entries(packageGroups).map(([bookingId, pkg]) => (
                <div key={bookingId} className="border-2 border-indigo-200 bg-indigo-50/30 rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-3 pb-2 border-b border-indigo-200 flex-wrap">
                    <Package className="h-4 w-4 text-indigo-600" />
                    <span className="font-semibold text-indigo-700">{pkg.name}</span>
                    <Badge className="bg-indigo-100 text-indigo-700 text-xs">{pkg.orders.length} tests</Badge>
                    {pkg.orders.some(isInpatientOrder) && (
                      <Badge className="text-xs bg-orange-100 text-orange-800">Inpatient</Badge>
                    )}
                    <span className="text-sm text-gray-500 ml-auto">
                      {pkg.patient_name} • {pkg.doctor_name || '—'}
                    </span>
                    {pkg.orders.some((order) => order.payment_status !== 'paid' && order.status !== 'cancelled') && (
                      <Button size="sm" className="h-7 text-xs" onClick={() => openLabPaymentDialog(pkg.patient_id)}>
                        <Banknote className="h-3 w-3 mr-1" /> Collect Payment
                      </Button>
                    )}
                    {pkg.orders.some((order) => order.has_report) && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7 text-xs border-indigo-300 text-indigo-700"
                        onClick={() => openReportPreview(null, pkg.name, bookingId)}
                      >
                        <Printer className="h-3 w-3 mr-1" /> All Reports
                      </Button>
                    )}
                  </div>
                  <div className="space-y-2">
                    {pkg.orders.map((order) => (
                      <div
                        key={order.id}
                        className="flex items-center justify-between bg-white rounded p-3 border border-indigo-100 gap-2"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-medium">{order.test_name}</span>
                            {renderMeta(order)}
                          </div>
                          <p className="text-xs text-gray-500 mt-1">
                            #{order.order_number} • ₹{(order.amount || 0).toFixed(0)} • {formatDate(order.completion_date || order.order_date)}
                          </p>
                        </div>
                        {renderOrderActions(order, { showCollect: false })}
                      </div>
                    ))}
                  </div>
                </div>
              ))}

              {standalone.map((order) => (
                <div
                  key={order.id}
                  className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border gap-2"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-gray-900">{order.patient_name}</span>
                      {renderMeta(order)}
                    </div>
                    <p className="text-sm text-gray-600 mt-1">
                      {order.test_name} — ₹{(order.amount || 0).toFixed(0)}
                    </p>
                    <p className="text-xs text-gray-400">
                      #{order.order_number} • {order.doctor_name || '—'} • {order.status === 'completed' ? 'Completed' : 'Ordered'} {formatDate(order.completion_date || order.order_date)}
                    </p>
                  </div>
                  {renderOrderActions(order)}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={showLabPaymentDialog} onOpenChange={setShowLabPaymentDialog}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <TestTube className="h-5 w-5" />
              Lab Order Payments
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {labPaymentLoading && pendingLabOrders.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <RefreshCw className="h-6 w-6 animate-spin mx-auto mb-2" />
                Loading...
              </div>
            ) : pendingLabOrders.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                <TestTube className="h-10 w-10 mx-auto mb-2 text-gray-300" />
                <p>No pending lab payments for this patient.</p>
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium text-gray-700">Pending payment ({pendingLabOrders.length})</p>
                  <p className="font-semibold text-green-700">Total: ₹{pendingTotal.toFixed(2)}</p>
                </div>
                <div className="border rounded-lg divide-y max-h-48 overflow-y-auto">
                  {pendingLabOrders.map((order) => (
                    <div key={order.id} className="p-3 flex items-center justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="font-medium text-sm">{order.test_name}</p>
                        <p className="text-xs text-gray-500">
                          {order.order_number}
                          {isInpatientOrder(order) ? ' · Inpatient' : ''}
                          {order.doctor_name ? ` · ${order.doctor_name}` : ''}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <p className="font-semibold text-sm">₹{(order.amount || 0).toFixed(2)}</p>
                        {order.status === 'ordered' && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-7 px-2 text-xs text-red-600 hover:bg-red-50 hover:text-red-700"
                            onClick={() => openLabCancelDialog(order)}
                          >
                            <XCircle className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="bg-gray-50 rounded-lg p-3 space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span>Subtotal</span>
                    <span>₹{pendingTotal.toFixed(2)}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span>Discount</span>
                    <div className="flex items-center gap-1">
                      <span className="text-gray-400">₹</span>
                      <Input
                        type="number"
                        min="0"
                        step="0.01"
                        value={labDiscount}
                        onChange={(e) => setLabDiscount(e.target.value)}
                        placeholder="0"
                        className="w-24 h-7 text-right text-sm"
                      />
                    </div>
                  </div>
                  <hr />
                  <div className="flex items-center justify-between font-semibold">
                    <span>Total</span>
                    <span>₹{payableTotal.toFixed(2)}</span>
                  </div>
                </div>
                <div>
                  <Label className="text-xs">Payment method</Label>
                  <Select value={labPaymentMethod} onValueChange={setLabPaymentMethod}>
                    <SelectTrigger className="h-8">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="cash">Cash</SelectItem>
                      <SelectItem value="card">Card</SelectItem>
                      <SelectItem value="upi">UPI</SelectItem>
                      <SelectItem value="online">Online</SelectItem>
                      <SelectItem value="insurance">Insurance</SelectItem>
                      <SelectItem value="cheque">Cheque</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <Button className="w-full" onClick={collectAllLabPayments} disabled={labPaymentLoading}>
                  {labPaymentLoading ? 'Generating bill...' : `Pay & download bill (₹${payableTotal.toFixed(2)})`}
                </Button>
              </>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showLabCancelDialog} onOpenChange={(open) => {
        if (!open && !labCancelLoading) {
          setShowLabCancelDialog(false);
          setLabCancelOrder(null);
          setLabCancelReason('');
        }
      }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <XCircle className="h-5 w-5 text-red-600" />
              Cancel lab order
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {labCancelOrder && (
              <div className="rounded-lg border border-red-100 bg-red-50/60 p-3">
                <p className="text-sm font-semibold text-gray-900">{labCancelOrder.test_name}</p>
                <p className="mt-1 text-xs text-gray-600">#{labCancelOrder.order_number}</p>
              </div>
            )}
            <div>
              <Label htmlFor="lab-orders-cancel-reason" className="text-xs">Reason (optional)</Label>
              <Textarea
                id="lab-orders-cancel-reason"
                value={labCancelReason}
                onChange={(event) => setLabCancelReason(event.target.value)}
                placeholder="For example: Patient declined the test"
                rows={3}
                maxLength={500}
                className="mt-1"
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" disabled={labCancelLoading} onClick={() => setShowLabCancelDialog(false)}>
                Keep order
              </Button>
              <Button variant="destructive" disabled={labCancelLoading} onClick={confirmCancelLabOrder}>
                {labCancelLoading ? 'Cancelling…' : 'Cancel order'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showLabBillPreview} onOpenChange={(open) => { if (!open) closeBillPreview(); }}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Receipt className="h-5 w-5" /> Lab bill preview
            </DialogTitle>
          </DialogHeader>
          <div className="flex flex-col space-y-4">
            <div className="flex-1 min-h-[400px] border rounded-lg overflow-hidden">
              {labBillPdfUrl && (
                <iframe src={labBillPdfUrl} className="w-full h-full min-h-[400px] border-0" title="Lab bill preview" />
              )}
            </div>
            <div className="flex items-center gap-3">
              <Button variant="outline" onClick={closeBillPreview} className="flex-1">Close</Button>
              <Button
                className="flex-1 bg-blue-600 hover:bg-blue-700"
                onClick={() => {
                  if (!labBillPdfUrl) return;
                  const iframe = document.createElement('iframe');
                  iframe.style.display = 'none';
                  document.body.appendChild(iframe);
                  iframe.src = labBillPdfUrl;
                  iframe.onload = () => {
                    iframe.contentWindow.print();
                    setTimeout(() => document.body.removeChild(iframe), 1000);
                  };
                }}
              >
                <Printer className="h-4 w-4 mr-2" /> Print bill
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <PdfPreviewDialog
        open={!!reportPreview}
        onClose={() => setReportPreview(null)}
        title={reportPreview?.title || 'Lab Report Preview'}
        path={reportPreview?.path || null}
        letterheadReportType="lab_report"
      />
    </div>
  );
};

export default ReceptionLabOrdersPage;
