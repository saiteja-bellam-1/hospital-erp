import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/card';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Label } from '../../../components/ui/label';
import { Badge } from '../../../components/ui/badge';
import {
  RefreshCw,
  Calendar,
  TrendingUp,
  Users,
  IndianRupee,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle
} from 'lucide-react';

const ReceptionReportsPage = () => {
  const [reportDate, setReportDate] = useState(new Date().toISOString().split('T')[0]);
  const [reportData, setReportData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchReport(reportDate);
  }, []);

  const fetchReport = async (date) => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`/api/appointments/reports/daily-summary?report_date=${date}`, {
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' }
      });
      if (response.ok) {
        const data = await response.json();
        setReportData(data);
      }
    } catch (error) {
      console.error('Error fetching report:', error);
    } finally {
      setLoading(false);
    }
  };

  const statusLabels = {
    scheduled: 'Scheduled',
    confirmed: 'Checked In',
    in_progress: 'In Progress',
    completed: 'Completed',
    cancelled: 'Cancelled',
    no_show: 'No Show'
  };

  const statusColors = {
    scheduled: 'bg-blue-100 text-blue-800',
    confirmed: 'bg-green-100 text-green-800',
    in_progress: 'bg-yellow-100 text-yellow-800',
    completed: 'bg-gray-100 text-gray-800',
    cancelled: 'bg-red-100 text-red-800',
    no_show: 'bg-orange-100 text-orange-800'
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Reports & Analytics</h1>
          <p className="text-gray-600">Daily appointment summary and revenue breakdown</p>
        </div>
        <Button variant="outline" onClick={() => fetchReport(reportDate)}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Refresh
        </Button>
      </div>

      {/* Date Picker */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-end gap-4">
            <div>
              <Label>Report Date</Label>
              <Input
                type="date"
                value={reportDate}
                onChange={(e) => {
                  setReportDate(e.target.value);
                  fetchReport(e.target.value);
                }}
              />
            </div>
            <Button variant="outline" onClick={() => {
              const today = new Date().toISOString().split('T')[0];
              setReportDate(today);
              fetchReport(today);
            }}>Today</Button>
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <Card>
          <CardContent className="p-8 text-center">
            <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4 text-blue-600" />
            <p className="text-gray-600">Loading report...</p>
          </CardContent>
        </Card>
      ) : reportData ? (
        <>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <Card>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-500">Total Appointments</p>
                    <p className="text-3xl font-bold">{reportData.total_appointments}</p>
                  </div>
                  <Calendar className="h-10 w-10 text-blue-500 opacity-80" />
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-500">Total Billed</p>
                    <p className="text-3xl font-bold text-green-600">₹{reportData.revenue?.total_billed?.toLocaleString()}</p>
                  </div>
                  <IndianRupee className="h-10 w-10 text-green-500 opacity-80" />
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-500">Collected</p>
                    <p className="text-3xl font-bold text-blue-600">₹{reportData.revenue?.total_collected?.toLocaleString()}</p>
                  </div>
                  <CheckCircle className="h-10 w-10 text-blue-500 opacity-80" />
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-gray-500">Pending</p>
                    <p className="text-3xl font-bold text-orange-600">₹{reportData.revenue?.pending?.toLocaleString()}</p>
                  </div>
                  <AlertCircle className="h-10 w-10 text-orange-500 opacity-80" />
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Status Breakdown */}
            <Card>
              <CardHeader>
                <CardTitle>Appointment Status</CardTitle>
              </CardHeader>
              <CardContent>
                {Object.keys(reportData.by_status || {}).length === 0 ? (
                  <p className="text-gray-500 text-center py-4">No appointments</p>
                ) : (
                  <div className="space-y-3">
                    {Object.entries(reportData.by_status).map(([status, count]) => (
                      <div key={status} className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Badge className={statusColors[status] || 'bg-gray-100'}>{statusLabels[status] || status}</Badge>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="w-32 bg-gray-200 rounded-full h-2">
                            <div
                              className="bg-blue-500 h-2 rounded-full"
                              style={{ width: `${(count / reportData.total_appointments) * 100}%` }}
                            />
                          </div>
                          <span className="font-semibold w-8 text-right">{count}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Type Breakdown */}
            <Card>
              <CardHeader>
                <CardTitle>Appointment Types</CardTitle>
              </CardHeader>
              <CardContent>
                {Object.keys(reportData.by_type || {}).length === 0 ? (
                  <p className="text-gray-500 text-center py-4">No data</p>
                ) : (
                  <div className="space-y-3">
                    {Object.entries(reportData.by_type).map(([type, count]) => (
                      <div key={type} className="flex items-center justify-between">
                        <span className="capitalize">{type}</span>
                        <div className="flex items-center gap-2">
                          <div className="w-32 bg-gray-200 rounded-full h-2">
                            <div
                              className="bg-green-500 h-2 rounded-full"
                              style={{ width: `${(count / reportData.total_appointments) * 100}%` }}
                            />
                          </div>
                          <span className="font-semibold w-8 text-right">{count}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Doctor-wise Breakdown */}
            <Card>
              <CardHeader>
                <CardTitle>Doctor-wise Summary</CardTitle>
              </CardHeader>
              <CardContent>
                {Object.keys(reportData.by_doctor || {}).length === 0 ? (
                  <p className="text-gray-500 text-center py-4">No data</p>
                ) : (
                  <div className="space-y-3">
                    {Object.entries(reportData.by_doctor).map(([doctor, data]) => (
                      <div key={doctor} className="border rounded-lg p-3">
                        <div className="flex justify-between items-start">
                          <div>
                            <p className="font-medium">{doctor}</p>
                            <p className="text-sm text-gray-500">{data.count} appointments</p>
                          </div>
                          <div className="text-right">
                            <p className="font-medium text-green-600">₹{data.revenue?.toLocaleString()}</p>
                            <p className="text-xs text-gray-500">Collected: ₹{data.collected?.toLocaleString()}</p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Payment Methods */}
            <Card>
              <CardHeader>
                <CardTitle>Payment Methods</CardTitle>
              </CardHeader>
              <CardContent>
                {Object.keys(reportData.payment_methods || {}).length === 0 ? (
                  <p className="text-gray-500 text-center py-4">No payments recorded</p>
                ) : (
                  <div className="space-y-3">
                    {Object.entries(reportData.payment_methods).map(([method, data]) => (
                      <div key={method} className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="capitalize">{method}</Badge>
                          <span className="text-sm text-gray-500">{data.count} payments</span>
                        </div>
                        <span className="font-semibold text-green-600">₹{data.amount?.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      ) : (
        <Card>
          <CardContent className="p-8 text-center">
            <TrendingUp className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <p className="text-gray-600">Select a date to view the report</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default ReceptionReportsPage;
