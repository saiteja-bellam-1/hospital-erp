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
  User, FileText, Activity, Search, Beaker
} from 'lucide-react';
import axios from 'axios';
import { format } from 'date-fns';

const LabTechDashboard = () => {
  const [orders, setOrders] = useState([]);
  const [completedOrders, setCompletedOrders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('pending');
  const [statusFilter, setStatusFilter] = useState('all_pending');
  const [searchQuery, setSearchQuery] = useState('');

  // Result entry
  const [showEntryDialog, setShowEntryDialog] = useState(false);
  const [entryForm, setEntryForm] = useState(null);
  const [entryValues, setEntryValues] = useState({});
  const [interpretation, setInterpretation] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Report view
  const [showReportDialog, setShowReportDialog] = useState(false);
  const [viewingReport, setViewingReport] = useState(null);

  // Stats
  const [stats, setStats] = useState(null);

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
      await axios.put(`/api/lab/orders/${orderId}/status?status=${newStatus}`);
      showFeedback(`Order marked as ${newStatus}`);
      fetchOrders();
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
          value: String(value)
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
    if (param.field_type !== 'numeric' || !value) return false;
    const numVal = parseFloat(value);
    if (isNaN(numVal)) return false;
    if (param.reference_min != null && numVal < param.reference_min) return true;
    if (param.reference_max != null && numVal > param.reference_max) return true;
    return false;
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
        order.order_number?.toLowerCase().includes(q)
      );
    }
    return true;
  });

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
          {filteredOrders.map(renderOrderCard)}
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
        completedOrders.map(renderOrderCard)
      )}
    </div>
  );

  const renderEntryDialog = () => {
    if (!entryForm) return null;
    return (
      <Dialog open={showEntryDialog} onOpenChange={setShowEntryDialog}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
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
                  <th className="pb-2">Reference Range</th>
                </tr>
              </thead>
              <tbody>
                {entryForm.parameters.map(param => {
                  const value = entryValues[param.id] || '';
                  const abnormal = isValueAbnormal(param, value);
                  return (
                    <tr key={param.id} className={`border-b ${abnormal ? 'bg-red-50' : ''}`}>
                      <td className="py-2 pr-3 font-medium">{param.parameter_name}</td>
                      <td className="py-2 pr-3">
                        {param.field_type === 'select' && param.possible_values ? (
                          <Select value={value}
                            onValueChange={(v) => setEntryValues({ ...entryValues, [param.id]: v })}>
                            <SelectTrigger className="w-[150px] h-8">
                              <SelectValue placeholder="Select..." />
                            </SelectTrigger>
                            <SelectContent>
                              {param.possible_values.map(pv => (
                                <SelectItem key={pv} value={pv}>{pv}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        ) : (
                          <Input
                            type={param.field_type === 'numeric' ? 'number' : 'text'}
                            step="any"
                            value={value}
                            onChange={(e) => setEntryValues({ ...entryValues, [param.id]: e.target.value })}
                            className={`w-[150px] h-8 ${abnormal ? 'border-red-500 text-red-600 font-bold' : ''}`}
                            placeholder="Enter value"
                          />
                        )}
                      </td>
                      <td className="py-2 pr-3 text-gray-500">{param.unit || '-'}</td>
                      <td className="py-2 text-gray-500 text-xs">
                        {param.reference_min != null || param.reference_max != null
                          ? `${param.reference_min ?? '–'} - ${param.reference_max ?? '–'}`
                          : '-'}
                        {abnormal && (
                          <span className="ml-2 text-red-600 font-bold">
                            <AlertCircle className="inline h-3 w-3" /> Abnormal
                          </span>
                        )}
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
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
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

          <div className="flex justify-end mt-4">
            <Button variant="outline" onClick={async () => {
              try {
                const res = await axios.get(`/api/lab/reports/${viewingReport.id}/download`, {
                  responseType: 'blob'
                });
                const url = window.URL.createObjectURL(new Blob([res.data]));
                const a = document.createElement('a');
                a.href = url;
                a.download = `lab_report_${viewingReport.order_number}.pdf`;
                a.click();
                window.URL.revokeObjectURL(url);
              } catch (err) {
                console.error('Failed to download PDF:', err);
              }
            }}>
              <FileText className="h-4 w-4 mr-2" /> Download PDF
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    );
  };

  return (
    <div className="space-y-6">
      {renderFeedback()}

      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold text-gray-900">Lab Technician Dashboard</h1>
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
    </div>
  );
};

export default LabTechDashboard;
