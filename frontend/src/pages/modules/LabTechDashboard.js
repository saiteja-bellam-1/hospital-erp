import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Textarea } from '../../components/ui/textarea';
import { Badge } from '../../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../../components/ui/dialog';
import {
  TestTube, Clock, CheckCircle, AlertCircle, RefreshCw, Loader2,
  User, FileText, Activity, Search, Beaker, Package, Printer
} from 'lucide-react';
import axios from 'axios';
import { format } from 'date-fns';
import JsBarcode from 'jsbarcode';

const LabTechDashboard = () => {
  const [orders, setOrders] = useState([]);
  const [completedOrders, setCompletedOrders] = useState([]);
  const [loading, setLoading] = useState(false);

  // Detect role for title
  const userData = JSON.parse(localStorage.getItem('user') || '{}');
  const isLabAdmin = userData.role === 'lab_admin';
  const [activeTab, setActiveTab] = useState('pending');
  const [statusFilter, setStatusFilter] = useState('all_pending');
  const [searchQuery, setSearchQuery] = useState('');

  // Result entry
  const [showEntryDialog, setShowEntryDialog] = useState(false);
  const [entryForm, setEntryForm] = useState(null);
  const [entryValues, setEntryValues] = useState({});
  const [remarkValues, setRemarkValues] = useState({});
  const [manualAbnormal, setManualAbnormal] = useState({});
  const [interpretation, setInterpretation] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Report view
  const [showReportDialog, setShowReportDialog] = useState(false);
  const [viewingReport, setViewingReport] = useState(null);

  // Stats
  const [stats, setStats] = useState(null);

  // Sample barcode dialog
  const [showBarcodeDialog, setShowBarcodeDialog] = useState(false);
  const [barcodeData, setBarcodeData] = useState(null);

  // Generate barcode as data URL when dialog opens
  const [barcodeImgSrc, setBarcodeImgSrc] = useState('');
  useEffect(() => {
    if (showBarcodeDialog && barcodeData?.sample_id) {
      try {
        const canvas = document.createElement('canvas');
        JsBarcode(canvas, barcodeData.sample_id, {
          format: 'CODE128',
          width: 1.5,
          height: 35,
          displayValue: false,
          margin: 0,
        });
        setBarcodeImgSrc(canvas.toDataURL('image/png'));
      } catch (e) {
        console.error('Barcode generation error:', e);
        setBarcodeImgSrc('');
      }
    }
  }, [showBarcodeDialog, barcodeData]);

  // Feedback
  const [feedback, setFeedback] = useState({ message: '', type: '' });

  const showFeedback = (message, type = 'success') => {
    setFeedback({ message, type });
    setTimeout(() => setFeedback({ message: '', type: '' }), 3000);
  };

  // ============ Data fetching ============

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch pending orders (ordered, collected, processing)
      const pendingRes = await axios.get('/api/lab/orders');
      const allOrders = pendingRes.data;
      const pending = allOrders.filter(o => ['ordered', 'collected', 'processing'].includes(o.status));
      const completed = allOrders.filter(o => o.status === 'completed');
      setOrders(pending);
      setCompletedOrders(completed);
    } catch (err) {
      console.error('Failed to fetch orders:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const res = await axios.get('/api/lab/stats');
      setStats(res.data);
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    }
  }, []);

  useEffect(() => {
    fetchOrders();
    fetchStats();
  }, [fetchOrders, fetchStats]);

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchOrders();
      fetchStats();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchOrders, fetchStats]);

  // ============ Status update ============

  const handleUpdateStatus = async (orderId, newStatus) => {
    try {
      const res = await axios.put(`/api/lab/orders/${orderId}/status?status=${newStatus}`);
      showFeedback(`Order marked as ${newStatus}`);
      fetchOrders();
      // Show barcode popup when sample is collected
      if (newStatus === 'collected' && res.data.sample_id) {
        setBarcodeData({
          sample_id: res.data.sample_id,
          order_number: res.data.order_number,
          patient_name: res.data.patient_name,
          test_name: res.data.test_name,
        });
        setShowBarcodeDialog(true);
      }
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to update status', 'error');
    }
  };

  // ============ Result entry ============

  const openEntryForm = async (orderId) => {
    try {
      const res = await axios.get(`/api/lab/orders/${orderId}/entry-form`);
      setEntryForm(res.data);
      const initialValues = {};
      res.data.parameters.forEach(p => {
        initialValues[p.id] = '';
      });
      setEntryValues(initialValues);
      setRemarkValues({});
      setManualAbnormal({});
      setInterpretation('');
      setShowEntryDialog(true);
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to load entry form', 'error');
    }
  };

  const handleSubmitResults = async () => {
    if (!entryForm) return;
    setSubmitting(true);
    try {
      const results = Object.entries(entryValues)
        .filter(([_, value]) => value !== '')
        .map(([paramId, value]) => ({
          parameter_id: parseInt(paramId),
          value: String(value),
          remarks: remarkValues[paramId] || null,
          manual_abnormal: manualAbnormal[paramId] || false
        }));

      await axios.post(`/api/lab/orders/${entryForm.order_id}/results`, {
        results,
        interpretation: interpretation || null
      });
      showFeedback('Results submitted successfully');
      setShowEntryDialog(false);
      fetchOrders();
      fetchStats();
    } catch (err) {
      showFeedback(err.response?.data?.detail || 'Failed to submit results', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  // ============ View report ============

  const openReport = async (reportId) => {
    try {
      const res = await axios.get(`/api/lab/reports/${reportId}`);
      setViewingReport(res.data);
      setShowReportDialog(true);
    } catch (err) {
      showFeedback('Failed to load report', 'error');
    }
  };

  // ============ Helpers ============

  const isValueAbnormal = (param, value) => {
    if (!value) return false;
    if (param.field_type === 'numeric' || param.field_type === 'less_than' || param.field_type === 'greater_than') {
      let clean = value.toString().trim().replace(/^[<>]\s*/, '');
      const numVal = parseFloat(clean);
      if (isNaN(numVal)) return false;
      if (param.field_type === 'less_than') {
        return param.reference_max != null && numVal >= param.reference_max;
      }
      if (param.field_type === 'greater_than') {
        return param.reference_min != null && numVal <= param.reference_min;
      }
      // Range type — also handle < > prefixed values
      if (value.toString().trim().startsWith('<')) {
        return param.reference_min != null && numVal <= param.reference_min;
      }
      if (value.toString().trim().startsWith('>')) {
        return param.reference_max != null && numVal >= param.reference_max;
      }
      if (param.reference_min != null && numVal < param.reference_min) return true;
      if (param.reference_max != null && numVal > param.reference_max) return true;
      return false;
    }
    // Select, preset types, text, manual, colour — check abnormal_values list
    const abnormalList = param.abnormal_values || [];
    if (abnormalList.length > 0) {
      return abnormalList.includes(value.trim());
    }
    return false;
  };

  const downloadPackageReport = async (packageBookingId, packageName, includeHeader = true) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/lab/reports/package/${packageBookingId}/download?include_header=${includeHeader}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${packageName}_report.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      } else {
        showFeedback('Failed to download package report', 'error');
      }
    } catch {
      showFeedback('Failed to download package report', 'error');
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'ordered': return 'bg-blue-100 text-blue-700';
      case 'collected': return 'bg-yellow-100 text-yellow-700';
      case 'processing': return 'bg-purple-100 text-purple-700';
      case 'completed': return 'bg-green-100 text-green-700';
      case 'cancelled': return 'bg-red-100 text-red-700';
      default: return 'bg-gray-100 text-gray-700';
    }
  };

  const getPriorityColor = (priority) => {
    switch (priority) {
      case 'urgent': return 'destructive';
      case 'stat': return 'destructive';
      default: return 'secondary';
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    try {
      return format(new Date(dateStr), 'dd MMM yyyy, hh:mm a');
    } catch {
      return dateStr;
    }
  };

  const filteredOrders = orders.filter(order => {
    if (statusFilter !== 'all_pending' && order.status !== statusFilter) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        order.patient_name?.toLowerCase().includes(q) ||
        order.test_name?.toLowerCase().includes(q) ||
        order.order_number?.toLowerCase().includes(q) ||
        order.package_name?.toLowerCase().includes(q)
      );
    }
    return true;
  });

  // Group orders: package orders grouped by package_booking_id, individual orders standalone
  const groupOrders = (orderList) => {
    const groups = [];
    const packageMap = {};
    for (const order of orderList) {
      if (order.package_booking_id) {
        if (!packageMap[order.package_booking_id]) {
          packageMap[order.package_booking_id] = {
            type: 'package',
            package_name: order.package_name || 'Package',
            package_booking_id: order.package_booking_id,
            patient_name: order.patient_name,
            doctor_name: order.doctor_name,
            priority: order.priority,
            order_date: order.order_date,
            orders: [],
          };
          groups.push(packageMap[order.package_booking_id]);
        }
        packageMap[order.package_booking_id].orders.push(order);
        // Escalate priority if any order is urgent/emergency
        if (order.priority === 'emergency' || (order.priority === 'urgent' && packageMap[order.package_booking_id].priority === 'normal')) {
          packageMap[order.package_booking_id].priority = order.priority;
        }
      } else {
        groups.push({ type: 'single', order });
      }
    }
    return groups;
  };

  // ============ Render ============

  const renderFeedback = () => {
    if (!feedback.message) return null;
    return (
      <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-lg shadow-lg text-white ${
        feedback.type === 'error' ? 'bg-red-500' : 'bg-green-500'
      }`}>
        {feedback.message}
      </div>
    );
  };

  const renderStats = () => (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-500">Pending Orders</p>
              <p className="text-2xl font-bold">{orders.filter(o => o.status === 'ordered').length}</p>
            </div>
            <Clock className="h-8 w-8 text-blue-500" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-500">Collected</p>
              <p className="text-2xl font-bold">{orders.filter(o => o.status === 'collected').length}</p>
            </div>
            <Beaker className="h-8 w-8 text-yellow-500" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-500">Processing</p>
              <p className="text-2xl font-bold">{orders.filter(o => o.status === 'processing').length}</p>
            </div>
            <Activity className="h-8 w-8 text-purple-500" />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-gray-500">Completed Today</p>
              <p className="text-2xl font-bold">{stats?.completed_today || 0}</p>
            </div>
            <CheckCircle className="h-8 w-8 text-green-500" />
          </div>
        </CardContent>
      </Card>
    </div>
  );

  const renderOrderCard = (order) => (
    <Card key={order.id} className={order.priority !== 'normal' ? 'border-red-300' : ''}>
      <CardContent className="py-4">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className="font-semibold">{order.patient_name}</span>
              <Badge className={getStatusColor(order.status)}>{order.status}</Badge>
              {order.order_source && (
                <Badge variant="outline" className="text-[10px] capitalize">{order.order_source}</Badge>
              )}
              {order.priority !== 'normal' && (
                <Badge variant={getPriorityColor(order.priority)}>
                  {order.priority.toUpperCase()}
                </Badge>
              )}
            </div>
            <div className="text-sm text-gray-500 space-y-0.5">
              <p><TestTube className="inline h-3 w-3 mr-1" />{order.test_name} ({order.test_code})</p>
              <p><User className="inline h-3 w-3 mr-1" />{order.doctor_name || 'N/A'}</p>
              <p><Clock className="inline h-3 w-3 mr-1" />{formatDate(order.order_date)}</p>
              <p className="text-xs text-gray-400">#{order.order_number}</p>
              {order.sample_id && (
                <p className="text-xs font-mono font-semibold text-indigo-600">
                  Sample: {order.sample_id}
                </p>
              )}
            </div>
          </div>
          <div className="flex flex-col gap-2 ml-4">
            {order.status === 'ordered' && (
              <Button size="sm" variant="outline" onClick={() => handleUpdateStatus(order.id, 'collected')}>
                Mark Collected
              </Button>
            )}
            {order.status === 'collected' && (
              <Button size="sm" variant="outline" onClick={() => handleUpdateStatus(order.id, 'processing')}>
                Start Processing
              </Button>
            )}
            {(order.status === 'collected' || order.status === 'processing') && (
              <Button size="sm" onClick={() => openEntryForm(order.id)}>
                <FileText className="h-3 w-3 mr-1" /> Enter Results
              </Button>
            )}
            {order.status === 'completed' && order.has_report && (
              <Button size="sm" variant="outline" onClick={() => openReport(order.report_id)}>
                View Report
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );

  const renderPackageGroup = (group, key) => {
    const completedCount = group.orders.filter(o => o.status === 'completed').length;
    const totalCount = group.orders.length;
    return (
      <Card key={`pkg-${key}`} className="border-2 border-indigo-200 bg-indigo-50/30">
        <CardContent className="py-3 px-4">
          {/* Package header */}
          <div className="flex items-center justify-between mb-3 pb-2 border-b border-indigo-200">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-gray-900">{group.patient_name}</span>
              <span className="text-gray-400">|</span>
              <Package className="h-4 w-4 text-indigo-600" />
              <span className="font-semibold text-indigo-700">{group.package_name}</span>
              <Badge className="bg-indigo-100 text-indigo-700 text-xs">{totalCount} tests</Badge>
              {completedCount > 0 && (
                <Badge className="bg-green-100 text-green-700 text-xs">{completedCount}/{totalCount} done</Badge>
              )}
              {group.priority !== 'normal' && (
                <Badge variant={getPriorityColor(group.priority)}>{group.priority.toUpperCase()}</Badge>
              )}
            </div>
            <div className="text-xs text-gray-500">
              <User className="inline h-3 w-3 mr-1" />{group.doctor_name || 'N/A'}
            </div>
          </div>
          {/* Individual tests within package */}
          <div className="space-y-2">
            {group.orders.map(order => (
              <div key={order.id} className="flex items-center justify-between bg-white rounded-lg p-3 border border-indigo-100">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="font-semibold text-sm">{order.patient_name}</span>
                    <span className="text-gray-300">|</span>
                    <TestTube className="h-3 w-3 text-gray-400" />
                    <span className="font-medium text-sm">{order.test_name} ({order.test_code})</span>
                    <Badge className={`text-xs ${getStatusColor(order.status)}`}>{order.status}</Badge>
                  </div>
                  <div className="flex items-center gap-3 ml-5">
                    <span className="text-xs text-gray-400">#{order.order_number}</span>
                    {order.sample_id && <span className="text-xs font-mono font-semibold text-indigo-600">Sample: {order.sample_id}</span>}
                  </div>
                </div>
                <div className="flex gap-2 ml-4">
                  {order.status === 'ordered' && (
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => handleUpdateStatus(order.id, 'collected')}>
                      Mark Collected
                    </Button>
                  )}
                  {order.status === 'collected' && (
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => handleUpdateStatus(order.id, 'processing')}>
                      Start Processing
                    </Button>
                  )}
                  {(order.status === 'collected' || order.status === 'processing') && (
                    <Button size="sm" className="h-7 text-xs" onClick={() => openEntryForm(order.id)}>
                      <FileText className="h-3 w-3 mr-1" /> Enter Results
                    </Button>
                  )}
                  {order.status === 'completed' && order.has_report && (
                    <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => openReport(order.report_id)}>
                      View Report
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
          {/* Download All Reports button */}
          {completedCount > 0 && (
            <div className="mt-3 pt-2 border-t border-indigo-200 flex gap-2">
              <Button size="sm" variant="outline" className="h-7 text-xs border-indigo-300 text-indigo-700"
                onClick={() => downloadPackageReport(group.package_booking_id, group.package_name, true)}>
                <FileText className="h-3 w-3 mr-1" /> Download All Reports (With Header)
              </Button>
              <Button size="sm" variant="ghost" className="h-7 text-xs text-indigo-600"
                onClick={() => downloadPackageReport(group.package_booking_id, group.package_name, false)}>
                Without Header
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    );
  };

  const renderPendingTab = () => (
    <div className="space-y-4">
      <div className="flex flex-col md:flex-row gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <Input placeholder="Search patient, test, order #..." value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)} className="pl-10" />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all_pending">All Pending</SelectItem>
            <SelectItem value="ordered">Ordered</SelectItem>
            <SelectItem value="collected">Collected</SelectItem>
            <SelectItem value="processing">Processing</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={fetchOrders}>
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
        </div>
      ) : filteredOrders.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-500">
            No pending orders found.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {groupOrders(filteredOrders).map((group, gi) =>
            group.type === 'package' ? renderPackageGroup(group, gi) : renderOrderCard(group.order)
          )}
        </div>
      )}
    </div>
  );

  const renderCompletedTab = () => (
    <div className="space-y-3">
      {completedOrders.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-gray-500">
            No completed orders yet.
          </CardContent>
        </Card>
      ) : (
        groupOrders(completedOrders).map((group, gi) =>
          group.type === 'package' ? renderPackageGroup(group, gi) : renderOrderCard(group.order)
        )
      )}
    </div>
  );

  const renderEntryDialog = () => {
    if (!entryForm) return null;
    return (
      <Dialog open={showEntryDialog} onOpenChange={setShowEntryDialog}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Enter Results - {entryForm.test_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 mb-4">
            <p className="text-sm text-gray-500">
              Patient: <strong>{entryForm.patient_name}</strong>
              {entryForm.patient_gender && <span> ({entryForm.patient_gender})</span>}
            </p>
            <p className="text-sm text-gray-500">Order: #{entryForm.order_number}</p>
          </div>

          <div className="space-y-1">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-gray-500">
                  <th className="pb-2 pr-3">Parameter</th>
                  <th className="pb-2 pr-3">Value</th>
                  <th className="pb-2 pr-3">Unit</th>
                  <th className="pb-2 pr-3">Reference Range</th>
                  <th className="pb-2">Remarks</th>
                </tr>
              </thead>
              <tbody>
                {entryForm.parameters.map(param => {
                  const value = entryValues[param.id] || '';
                  const abnormal = param.field_type === 'manual' ? (manualAbnormal[param.id] || false) : isValueAbnormal(param, value);
                  return (
                    <tr key={param.id} className={`border-b ${abnormal ? 'bg-red-50' : ''}`}>
                      <td className="py-2 pr-3 font-medium">{param.parameter_name}</td>
                      <td className="py-2 pr-3">
                        {(() => {
                          const presetOptions = {
                            positive_negative: ['Positive', 'Negative'],
                            reactive: ['Reactive', 'Non-Reactive'],
                            presence_absence: ['Present', 'Absent'],
                            cloudy_clear: ['Clear', 'Cloudy', 'Slightly Cloudy', 'Inflamed'],
                          };
                          const opts = param.possible_values || presetOptions[param.field_type];
                          if (opts) {
                            return (
                              <Select value={value}
                                onValueChange={(v) => setEntryValues({ ...entryValues, [param.id]: v })}>
                                <SelectTrigger className={`w-[170px] h-8 ${abnormal ? 'border-red-500 text-red-600 font-bold' : ''}`}>
                                  <SelectValue placeholder="Select..." />
                                </SelectTrigger>
                                <SelectContent>
                                  {opts.map(pv => (
                                    <SelectItem key={pv} value={pv}>{pv}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            );
                          }
                          if (param.field_type === 'less_than') {
                            return (
                              <div className="flex items-center gap-1">
                                <span className="text-sm font-bold text-gray-500">&lt;</span>
                                <Input type="number" step="any" value={value}
                                  onChange={(e) => setEntryValues({ ...entryValues, [param.id]: e.target.value })}
                                  className={`w-[130px] h-8 ${abnormal ? 'border-red-500 text-red-600 font-bold' : ''}`}
                                  placeholder="Value" />
                              </div>
                            );
                          }
                          if (param.field_type === 'greater_than') {
                            return (
                              <div className="flex items-center gap-1">
                                <span className="text-sm font-bold text-gray-500">&gt;</span>
                                <Input type="number" step="any" value={value}
                                  onChange={(e) => setEntryValues({ ...entryValues, [param.id]: e.target.value })}
                                  className={`w-[130px] h-8 ${abnormal ? 'border-red-500 text-red-600 font-bold' : ''}`}
                                  placeholder="Value" />
                              </div>
                            );
                          }
                          if (param.field_type === 'numeric') {
                            return (
                              <div className="flex items-center gap-1">
                                <div className="flex border rounded-md overflow-hidden h-8">
                                  <button type="button"
                                    className={`px-1.5 text-xs font-bold border-r ${value.toString().startsWith('<') ? 'bg-blue-100 text-blue-700' : 'bg-gray-50 text-gray-400 hover:bg-gray-100'}`}
                                    onClick={() => { const c = value.toString().replace(/^[<>]/, ''); setEntryValues({ ...entryValues, [param.id]: value.toString().startsWith('<') ? c : `<${c}` }); }}
                                  >&lt;</button>
                                  <input type="text" inputMode="decimal"
                                    value={value.toString().replace(/^[<>]/, '')}
                                    onChange={(e) => { const p = value.toString().startsWith('<') ? '<' : value.toString().startsWith('>') ? '>' : ''; setEntryValues({ ...entryValues, [param.id]: p + e.target.value }); }}
                                    className={`w-[100px] h-full px-2 text-sm outline-none ${abnormal ? 'text-red-600 font-bold' : ''}`}
                                    placeholder="Value" />
                                  <button type="button"
                                    className={`px-1.5 text-xs font-bold border-l ${value.toString().startsWith('>') ? 'bg-blue-100 text-blue-700' : 'bg-gray-50 text-gray-400 hover:bg-gray-100'}`}
                                    onClick={() => { const c = value.toString().replace(/^[<>]/, ''); setEntryValues({ ...entryValues, [param.id]: value.toString().startsWith('>') ? c : `>${c}` }); }}
                                  >&gt;</button>
                                </div>
                              </div>
                            );
                          }
                          // text, manual, colour — free text input
                          return (
                            <Input type="text" value={value}
                              onChange={(e) => setEntryValues({ ...entryValues, [param.id]: e.target.value })}
                              className={`w-[150px] h-8 ${abnormal ? 'border-red-500 text-red-600 font-bold' : ''}`}
                              placeholder={param.field_type === 'colour' ? 'e.g. Pale Yellow' : 'Enter value'} />
                          );
                        })()}
                      </td>
                      <td className="py-2 pr-3 text-gray-500">{param.unit || '-'}</td>
                      <td className="py-2 text-gray-500 text-xs">
                        {param.field_type === 'less_than' && param.reference_max != null
                          ? `< ${param.reference_max}`
                          : param.field_type === 'greater_than' && param.reference_min != null
                            ? `> ${param.reference_min}`
                            : param.reference_min != null && param.reference_max != null
                              ? `${param.reference_min} - ${param.reference_max}`
                              : param.reference_min != null
                                ? `> ${param.reference_min}`
                                : param.reference_max != null
                                  ? `< ${param.reference_max}`
                                  : param.normal_value
                                    ? param.normal_value
                                    : '-'}
                        {abnormal && (
                          <span className="ml-2 text-red-600 font-bold">
                            <AlertCircle className="inline h-3 w-3" /> Abnormal
                          </span>
                        )}
                      </td>
                      <td className="py-2">
                        <div className="flex items-center gap-2">
                          {param.field_type === 'manual' && (
                            <label className="flex items-center gap-1 cursor-pointer whitespace-nowrap" title="Mark as abnormal">
                              <input type="checkbox" checked={manualAbnormal[param.id] || false}
                                onChange={(e) => setManualAbnormal({ ...manualAbnormal, [param.id]: e.target.checked })}
                                className="w-3.5 h-3.5 rounded border-red-300 text-red-500" />
                              <span className="text-[10px] text-red-500 font-medium">Abnormal</span>
                            </label>
                          )}
                          <Input
                            type="text"
                            value={remarkValues[param.id] || ''}
                            onChange={(e) => setRemarkValues({ ...remarkValues, [param.id]: e.target.value })}
                            className="w-[120px] h-8 text-xs"
                            placeholder="Remarks"
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-4">
            <Label>Interpretation / Notes</Label>
            <Textarea value={interpretation} onChange={(e) => setInterpretation(e.target.value)}
              placeholder="Optional interpretation or notes..." rows={3} />
          </div>

          <div className="flex justify-end gap-2 mt-4">
            <Button variant="outline" onClick={() => setShowEntryDialog(false)}>Cancel</Button>
            <Button onClick={handleSubmitResults} disabled={submitting}>
              {submitting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
              Submit Results
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    );
  };

  const renderReportDialog = () => {
    if (!viewingReport) return null;
    return (
      <Dialog open={showReportDialog} onOpenChange={setShowReportDialog}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Lab Report - {viewingReport.test_name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 mb-4">
            <p className="text-sm">Patient: <strong>{viewingReport.patient_name}</strong>
              {viewingReport.patient_gender && ` (${viewingReport.patient_gender})`}
              {viewingReport.patient_age && `, ${viewingReport.patient_age} yrs`}
            </p>
            <p className="text-sm text-gray-500">Order: #{viewingReport.order_number}</p>
            <p className="text-sm text-gray-500">Date: {formatDate(viewingReport.report_date)}</p>
            {viewingReport.doctor_name && (
              <p className="text-sm text-gray-500">Doctor: {viewingReport.doctor_name}</p>
            )}
          </div>

          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-gray-500">
                <th className="pb-2 pr-3">Parameter</th>
                <th className="pb-2 pr-3">Result</th>
                <th className="pb-2 pr-3">Unit</th>
                <th className="pb-2 pr-3">Reference</th>
                <th className="pb-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {viewingReport.results.map((r, idx) => (
                <tr key={idx} className={`border-b ${r.is_abnormal ? 'bg-red-50' : ''}`}>
                  <td className="py-2 pr-3 font-medium">{r.parameter_name}</td>
                  <td className={`py-2 pr-3 ${r.is_abnormal ? 'text-red-600 font-bold' : ''}`}>
                    {r.value}
                  </td>
                  <td className="py-2 pr-3 text-gray-500">{r.unit || '-'}</td>
                  <td className="py-2 pr-3 text-gray-500 text-xs">
                    {r.reference_min != null || r.reference_max != null
                      ? `${r.reference_min ?? '–'} - ${r.reference_max ?? '–'}`
                      : '-'}
                  </td>
                  <td className="py-2">
                    {r.is_abnormal ? (
                      <Badge variant="destructive" className="text-xs">
                        <AlertCircle className="h-3 w-3 mr-1" /> Abnormal
                      </Badge>
                    ) : r.field_type === 'numeric' && (r.reference_min != null || r.reference_max != null) ? (
                      <Badge variant="secondary" className="text-xs">Normal</Badge>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {viewingReport.interpretation && (
            <div className="mt-4 p-3 bg-gray-50 rounded-lg">
              <p className="text-sm font-medium text-gray-700">Interpretation</p>
              <p className="text-sm text-gray-600 mt-1">{viewingReport.interpretation}</p>
            </div>
          )}

          <div className="flex justify-end gap-2 mt-4">
            {[true, false].map(withHeader => (
              <Button key={String(withHeader)} variant="outline" onClick={async () => {
                try {
                  const res = await axios.get(`/api/lab/reports/${viewingReport.id}/download?include_header=${withHeader}`, {
                    responseType: 'blob'
                  });
                  const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
                  const printWin = window.open(url, '_blank');
                  if (printWin) {
                    printWin.addEventListener('load', () => {
                      setTimeout(() => printWin.print(), 500);
                    });
                  }
                } catch (err) {
                  console.error('Failed to print PDF:', err);
                }
              }}>
                <Printer className="h-4 w-4 mr-2" /> Print {withHeader ? 'With Header' : 'Without Header'}
              </Button>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    );
  };

  return (
    <div className="space-y-6">
      {renderFeedback()}

      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-gray-900">{isLabAdmin ? 'Lab Admin Dashboard' : 'Lab Technician Dashboard'}</h1>
        <Button variant="outline" onClick={() => { fetchOrders(); fetchStats(); }}>
          <RefreshCw className="h-4 w-4 mr-2" /> Refresh
        </Button>
      </div>

      {renderStats()}

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="pending">
            Pending Orders ({orders.length})
          </TabsTrigger>
          <TabsTrigger value="completed">
            Completed ({completedOrders.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="pending">{renderPendingTab()}</TabsContent>
        <TabsContent value="completed">{renderCompletedTab()}</TabsContent>
      </Tabs>

      {renderEntryDialog()}
      {renderReportDialog()}

      {/* Sample Barcode Dialog */}
      <Dialog open={showBarcodeDialog} onOpenChange={setShowBarcodeDialog}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <TestTube className="h-5 w-5" /> Sample Label
            </DialogTitle>
          </DialogHeader>
          {barcodeData && (
            <div className="space-y-4">
              {/* Label preview */}
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-4 bg-white text-center">
                <p className="text-sm font-semibold">{barcodeData.patient_name}</p>
                <p className="text-xs text-gray-500">{barcodeData.test_name}</p>
                <div className="mt-2 mb-1">
                  {barcodeImgSrc && <img src={barcodeImgSrc} alt="barcode" className="mx-auto" style={{ height: 45, maxWidth: '80%' }} />}
                </div>
                <p className="text-sm font-bold font-mono tracking-widest">{barcodeData.sample_id}</p>
                <p className="text-[10px] text-gray-400 mt-0.5">#{barcodeData.order_number}</p>
              </div>
              <div className="flex gap-2 justify-center">
                <Button onClick={() => {
                  const printWin = window.open('', '_blank', 'width=400,height=300');
                  printWin.document.write(`<html><head><title>Sample Label</title>
                    <style>
                      @page { size: 50mm 30mm; margin: 0; }
                      * { box-sizing: border-box; margin: 0; padding: 0; }
                      body { width: 50mm; height: 30mm; font-family: Arial, sans-serif; text-align: center; padding: 1.5mm 2mm; overflow: hidden; }
                      .name { font-size: 7pt; font-weight: bold; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                      .test { font-size: 5.5pt; color: #555; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 0.5mm; }
                      .barcode { margin: 1mm auto; }
                      .barcode img { height: 10mm; max-width: 44mm; }
                      .sid { font-size: 8pt; font-weight: bold; font-family: monospace; letter-spacing: 0.8px; margin-top: 0.5mm; }
                      .order { font-size: 4.5pt; color: #888; margin-top: 0.3mm; }
                    </style></head><body>
                    <div class="name">${barcodeData.patient_name}</div>
                    <div class="test">${barcodeData.test_name}</div>
                    <div class="barcode"><img src="${barcodeImgSrc}" /></div>
                    <div class="sid">${barcodeData.sample_id}</div>
                    <div class="order">#${barcodeData.order_number}</div>
                    </body></html>`);
                  printWin.document.close();
                  printWin.focus();
                  setTimeout(() => { printWin.print(); printWin.close(); }, 400);
                }} className="gap-1">
                  <Printer className="h-4 w-4" /> Print Label
                </Button>
                <Button variant="outline" onClick={() => setShowBarcodeDialog(false)}>Close</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default LabTechDashboard;
