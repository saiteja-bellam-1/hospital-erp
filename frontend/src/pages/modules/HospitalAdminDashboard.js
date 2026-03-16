import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import {
  Users,
  Stethoscope,
  Receipt,
  Calendar,
  TrendingUp,
  Activity,
  FlaskConical,
  Clock,
  UserPlus,
  DollarSign,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Loader2,
} from 'lucide-react';
import { Button } from '../../components/ui/button';
import axios from 'axios';
import { useAuth } from '../../contexts/AuthContext';

const formatCurrency = (val) => {
  if (val == null) return '\u20B90';
  return '\u20B9' + Number(val).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
};

const formatTime = (isoStr) => {
  if (!isoStr) return '';
  const d = new Date(isoStr);
  const now = new Date();
  const diffMs = now - d;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
};

const statusColors = {
  scheduled: 'bg-blue-100 text-blue-700',
  confirmed: 'bg-cyan-100 text-cyan-700',
  checked_in: 'bg-amber-100 text-amber-700',
  in_progress: 'bg-purple-100 text-purple-700',
  completed: 'bg-green-100 text-green-700',
  cancelled: 'bg-red-100 text-red-700',
  no_show: 'bg-gray-100 text-gray-600',
};

const labStatusColors = {
  ordered: 'bg-blue-100 text-blue-700',
  collected: 'bg-amber-100 text-amber-700',
  processing: 'bg-purple-100 text-purple-700',
  completed: 'bg-green-100 text-green-700',
  paid: 'bg-green-100 text-green-700',
  pending: 'bg-red-100 text-red-700',
};

const HospitalAdminDashboard = () => {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(new Date());

  const fetchDashboard = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await axios.get('/api/hospital/dashboard-overview');
      setData(res.data);
      setLastRefresh(new Date());
    } catch (err) {
      console.error('Dashboard fetch error:', err);
      setError('Failed to load dashboard data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboard();
    const interval = setInterval(fetchDashboard, 60000); // refresh every 60s
    return () => clearInterval(interval);
  }, [fetchDashboard]);

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <AlertCircle className="h-10 w-10 text-red-400" />
        <p className="text-gray-600">{error}</p>
        <Button variant="outline" size="sm" onClick={fetchDashboard}>Retry</Button>
      </div>
    );
  }

  const d = data || {};
  const patients = d.patients || {};
  const appointments = d.appointments || {};
  const revenue = d.revenue || {};
  const lab = d.lab || {};
  const staff = d.staff || {};
  const doctorPerf = d.doctor_performance || [];
  const recentActivity = d.recent_activity || [];
  const pendingLabs = d.pending_labs || [];
  const weeklyTrend = d.weekly_trend || [];

  const totalRevenueToday = (revenue.today || 0) + (revenue.lab_today || 0);
  const totalRevenueMonth = (revenue.this_month || 0) + (revenue.lab_this_month || 0);

  // Weekly trend bar chart max
  const maxTrend = Math.max(...weeklyTrend.map(w => w.count), 1);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Hospital Overview</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Welcome back, {user.full_name} &middot; {new Date().toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={fetchDashboard}
          disabled={loading}
          className="gap-1.5"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">Refresh</span>
        </Button>
      </div>

      {/* KPI Cards Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Today's Appointments */}
        <Card className="border-0 shadow-sm bg-gradient-to-br from-blue-50 to-white">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-medium text-blue-600 uppercase tracking-wide">Today's Appointments</p>
                <p className="text-3xl font-bold text-gray-900 mt-1">{appointments.total_today || 0}</p>
                <div className="flex items-center gap-1.5 mt-1.5">
                  <CheckCircle2 className="h-3 w-3 text-green-500" />
                  <span className="text-xs text-gray-500">
                    {appointments.by_status?.completed || 0} completed
                  </span>
                </div>
              </div>
              <div className="h-10 w-10 rounded-xl bg-blue-100 flex items-center justify-center">
                <Calendar className="h-5 w-5 text-blue-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Total Patients */}
        <Card className="border-0 shadow-sm bg-gradient-to-br from-emerald-50 to-white">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-medium text-emerald-600 uppercase tracking-wide">Total Patients</p>
                <p className="text-3xl font-bold text-gray-900 mt-1">{patients.total || 0}</p>
                <div className="flex items-center gap-1.5 mt-1.5">
                  <UserPlus className="h-3 w-3 text-emerald-500" />
                  <span className="text-xs text-gray-500">
                    +{patients.new_today || 0} today
                  </span>
                </div>
              </div>
              <div className="h-10 w-10 rounded-xl bg-emerald-100 flex items-center justify-center">
                <Users className="h-5 w-5 text-emerald-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Revenue Today */}
        <Card className="border-0 shadow-sm bg-gradient-to-br from-amber-50 to-white">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-medium text-amber-600 uppercase tracking-wide">Revenue Today</p>
                <p className="text-3xl font-bold text-gray-900 mt-1">{formatCurrency(totalRevenueToday)}</p>
                <div className="flex items-center gap-1.5 mt-1.5">
                  <Clock className="h-3 w-3 text-amber-500" />
                  <span className="text-xs text-gray-500">
                    {formatCurrency(revenue.today_pending || 0)} pending
                  </span>
                </div>
              </div>
              <div className="h-10 w-10 rounded-xl bg-amber-100 flex items-center justify-center">
                <DollarSign className="h-5 w-5 text-amber-600" />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Lab Orders */}
        <Card className="border-0 shadow-sm bg-gradient-to-br from-purple-50 to-white">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-medium text-purple-600 uppercase tracking-wide">Lab Orders Today</p>
                <p className="text-3xl font-bold text-gray-900 mt-1">{lab.orders_today || 0}</p>
                <div className="flex items-center gap-1.5 mt-1.5">
                  <Activity className="h-3 w-3 text-purple-500" />
                  <span className="text-xs text-gray-500">
                    {lab.pending || 0} pending
                  </span>
                </div>
              </div>
              <div className="h-10 w-10 rounded-xl bg-purple-100 flex items-center justify-center">
                <FlaskConical className="h-5 w-5 text-purple-600" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Second Row: Revenue Summary + Appointment Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Revenue Breakdown */}
        <Card className="border-0 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Receipt className="h-4 w-4 text-gray-500" />
              Revenue Breakdown
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between py-2 px-3 rounded-lg bg-gray-50">
              <div>
                <p className="text-xs text-gray-500">Consultation Revenue</p>
                <p className="text-sm font-semibold text-gray-900">{formatCurrency(revenue.today || 0)}</p>
              </div>
              <span className="text-xs text-gray-400">Today</span>
            </div>
            <div className="flex items-center justify-between py-2 px-3 rounded-lg bg-gray-50">
              <div>
                <p className="text-xs text-gray-500">Lab Revenue</p>
                <p className="text-sm font-semibold text-gray-900">{formatCurrency(revenue.lab_today || 0)}</p>
              </div>
              <span className="text-xs text-gray-400">Today</span>
            </div>
            <div className="border-t pt-3 mt-2">
              <div className="flex items-center justify-between py-2 px-3 rounded-lg bg-blue-50">
                <div>
                  <p className="text-xs text-blue-600 font-medium">Monthly Total</p>
                  <p className="text-lg font-bold text-gray-900">{formatCurrency(totalRevenueMonth)}</p>
                </div>
                <div className="text-right">
                  <p className="text-[10px] text-gray-400">Consult: {formatCurrency(revenue.this_month || 0)}</p>
                  <p className="text-[10px] text-gray-400">Lab: {formatCurrency(revenue.lab_this_month || 0)}</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Appointment Status Breakdown */}
        <Card className="border-0 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Calendar className="h-4 w-4 text-gray-500" />
              Today's Appointment Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            {Object.keys(appointments.by_status || {}).length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-6">No appointments today</p>
            ) : (
              <div className="space-y-2">
                {Object.entries(appointments.by_status || {}).sort((a, b) => b[1] - a[1]).map(([status, count]) => (
                  <div key={status} className="flex items-center justify-between py-1.5">
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary" className={`text-[10px] px-2 py-0.5 ${statusColors[status] || 'bg-gray-100 text-gray-600'}`}>
                        {status.replace(/_/g, ' ')}
                      </Badge>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-24 h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full bg-blue-500 transition-all"
                          style={{ width: `${(count / (appointments.total_today || 1)) * 100}%` }}
                        />
                      </div>
                      <span className="text-sm font-semibold text-gray-700 w-6 text-right">{count}</span>
                    </div>
                  </div>
                ))}
                <div className="border-t pt-2 mt-2 flex items-center justify-between">
                  <span className="text-xs text-gray-500">Consultations recorded</span>
                  <span className="text-sm font-semibold text-gray-700">{appointments.consultations_today || 0}</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Weekly Trend */}
        <Card className="border-0 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-gray-500" />
              Weekly Appointment Trend
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-end justify-between gap-1.5 h-32">
              {weeklyTrend.map((w, i) => {
                const isToday = i === weeklyTrend.length - 1;
                const height = maxTrend > 0 ? (w.count / maxTrend) * 100 : 0;
                return (
                  <div key={w.date} className="flex-1 flex flex-col items-center gap-1">
                    <span className="text-[10px] font-medium text-gray-500">{w.count}</span>
                    <div className="w-full relative" style={{ height: '80px' }}>
                      <div
                        className={`absolute bottom-0 w-full rounded-t transition-all ${isToday ? 'bg-blue-500' : 'bg-blue-200'}`}
                        style={{ height: `${Math.max(height, 4)}%` }}
                      />
                    </div>
                    <span className={`text-[10px] font-medium ${isToday ? 'text-blue-600' : 'text-gray-400'}`}>
                      {w.day}
                    </span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Third Row: Doctor Performance + Recent Activity + Pending Labs */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Doctor Performance */}
        <Card className="border-0 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Stethoscope className="h-4 w-4 text-gray-500" />
              Doctor Performance (Today)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {doctorPerf.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-6">No doctor activity today</p>
            ) : (
              <div className="space-y-3">
                {doctorPerf.map((doc, i) => (
                  <div key={i} className="flex items-center gap-3 py-2 px-3 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors">
                    <div className="h-8 w-8 rounded-full bg-blue-100 flex items-center justify-center text-xs font-bold text-blue-600 flex-shrink-0">
                      {doc.name.replace('Dr. ', '').split(' ').map(n => n[0]).join('').slice(0, 2)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">{doc.name}</p>
                      <p className="text-[10px] text-gray-400">{doc.specialization || 'General'}</p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-sm font-semibold text-gray-900">
                        {doc.completed}/{doc.appointments}
                      </p>
                      <p className="text-[10px] text-gray-400">{formatCurrency(doc.revenue)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Activity */}
        <Card className="border-0 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <Activity className="h-4 w-4 text-gray-500" />
              Recent Completions
            </CardTitle>
          </CardHeader>
          <CardContent>
            {recentActivity.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-6">No recent activity</p>
            ) : (
              <div className="space-y-2">
                {recentActivity.map((a, i) => (
                  <div key={i} className="flex items-center gap-3 py-2 px-3 rounded-lg hover:bg-gray-50 transition-colors">
                    <div className="h-7 w-7 rounded-full bg-green-100 flex items-center justify-center flex-shrink-0">
                      <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">{a.patient}</p>
                      <p className="text-[10px] text-gray-400 truncate">{a.doctor}</p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-xs font-medium text-gray-600">{formatCurrency(a.amount)}</p>
                      <p className="text-[10px] text-gray-400">{formatTime(a.time)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Pending Lab Orders */}
        <Card className="border-0 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <FlaskConical className="h-4 w-4 text-gray-500" />
              Pending Lab Orders
            </CardTitle>
          </CardHeader>
          <CardContent>
            {pendingLabs.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-6">No pending lab orders</p>
            ) : (
              <div className="space-y-2">
                {pendingLabs.map((lo, i) => (
                  <div key={i} className="flex items-center gap-3 py-2 px-3 rounded-lg hover:bg-gray-50 transition-colors">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">{lo.patient}</p>
                      <p className="text-[10px] text-gray-400 truncate">{lo.test}</p>
                    </div>
                    <div className="flex flex-col items-end gap-1 flex-shrink-0">
                      <Badge variant="secondary" className={`text-[9px] px-1.5 py-0 ${labStatusColors[lo.status] || 'bg-gray-100 text-gray-600'}`}>
                        {lo.status}
                      </Badge>
                      <Badge variant="secondary" className={`text-[9px] px-1.5 py-0 ${labStatusColors[lo.payment_status] || 'bg-gray-100 text-gray-600'}`}>
                        {lo.payment_status === 'paid' ? 'Paid' : 'Unpaid'}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Staff Summary Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-0 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-indigo-100 flex items-center justify-center">
              <Stethoscope className="h-4.5 w-4.5 text-indigo-600" />
            </div>
            <div>
              <p className="text-xs text-gray-500">Active Doctors</p>
              <p className="text-xl font-bold text-gray-900">{staff.total_doctors || 0}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-teal-100 flex items-center justify-center">
              <Users className="h-4.5 w-4.5 text-teal-600" />
            </div>
            <div>
              <p className="text-xs text-gray-500">Total Staff</p>
              <p className="text-xl font-bold text-gray-900">{staff.total_staff || 0}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-emerald-100 flex items-center justify-center">
              <CheckCircle2 className="h-4.5 w-4.5 text-emerald-600" />
            </div>
            <div>
              <p className="text-xs text-gray-500">Lab Completed Today</p>
              <p className="text-xl font-bold text-gray-900">{lab.completed_today || 0}</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-orange-100 flex items-center justify-center">
              <UserPlus className="h-4.5 w-4.5 text-orange-600" />
            </div>
            <div>
              <p className="text-xs text-gray-500">New Patients (Month)</p>
              <p className="text-xl font-bold text-gray-900">{patients.new_this_month || 0}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Last updated */}
      <p className="text-[10px] text-gray-300 text-center">
        Last updated: {lastRefresh.toLocaleTimeString('en-IN')} &middot; Auto-refreshes every 60s
      </p>
    </div>
  );
};

export default HospitalAdminDashboard;
