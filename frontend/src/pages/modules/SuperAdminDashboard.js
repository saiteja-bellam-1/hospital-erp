import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { useAuth } from '../../contexts/AuthContext';
import axios from 'axios';
import {
  Users, Shield, Activity, Clock, CheckCircle2, XCircle,
  Monitor, UserCheck, LogIn, Loader2, RefreshCw, Database
} from 'lucide-react';
import ActionKpiCard from '../../components/dashboard/ActionKpiCard';
import DashboardDrillDialog from '../../components/dashboard/DashboardDrillDialog';

const SuperAdminDashboard = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [drill, setDrill] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const res = await axios.get('/api/admin/super-dashboard');
      setData(res.data);
    } catch (err) {
      console.error('Dashboard fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const loadUsers = useCallback(async (filter = 'all') => {
    const r = await axios.get('/api/admin/users');
    const rows = Array.isArray(r.data) ? r.data : [];
    if (filter === 'active') return rows.filter((u) => u.is_active);
    if (filter === 'inactive') return rows.filter((u) => !u.is_active);
    return rows;
  }, []);

  const formatTime = (ts) => {
    if (!ts) return '';
    try {
      const d = new Date(ts);
      return d.toLocaleString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
    } catch { return ts; }
  };

  const formatDate = (ts) => {
    if (!ts) return '';
    try {
      return new Date(ts).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
    } catch { return ts; }
  };

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (!data) return null;

  const licColors = {
    active: 'bg-green-100 text-green-700',
    expiring_soon: 'bg-yellow-100 text-yellow-700',
    expired: 'bg-red-100 text-red-700',
    no_license: 'bg-gray-100 text-gray-600',
  };

  const categoryColors = {
    auth: 'bg-blue-100 text-blue-700', patient: 'bg-green-100 text-green-700',
    appointment: 'bg-purple-100 text-purple-700', lab: 'bg-cyan-100 text-cyan-700',
    admin: 'bg-red-100 text-red-700', billing: 'bg-orange-100 text-orange-700',
    referral: 'bg-indigo-100 text-indigo-700', prescription: 'bg-pink-100 text-pink-700',
  };

  const maxActivity = Math.max(...(data.audit.daily_activity || []).map(d => d.count), 1);

  const closeDrill = () => setDrill(null);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">System Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">Welcome back, {user.full_name}</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchData}>
          <RefreshCw className="h-4 w-4 mr-1" /> Refresh
        </Button>
      </div>

      {/* Top Stats */}
      <div className="grid gap-3 grid-cols-2 md:grid-cols-3 lg:grid-cols-6">
        <ActionKpiCard
          icon={Users}
          label="Total Users"
          value={data.users.total}
          sub="All accounts"
          tone="blue"
          onClick={() => setDrill({
            type: 'users',
            title: 'All users',
            loadRows: () => loadUsers('all'),
            viewAll: { label: 'Manage users', onClick: () => navigate('/dashboard/admin/users') },
          })}
        />
        <ActionKpiCard
          icon={UserCheck}
          label="Active Users"
          value={data.users.active}
          sub="Currently active"
          tone="green"
          onClick={() => setDrill({
            type: 'users',
            title: 'Active users',
            loadRows: () => loadUsers('active'),
            viewAll: { label: 'Manage users', onClick: () => navigate('/dashboard/admin/users') },
          })}
        />
        <ActionKpiCard
          icon={LogIn}
          label="Logged In Today"
          value={data.users.logged_in_today}
          sub="Unique logins"
          tone="cyan"
          onClick={() => setDrill({
            type: 'logins',
            title: "Today's logins",
            loadRows: async () => data.recent_logins || [],
            viewAll: { label: 'Open audit logs', onClick: () => navigate('/dashboard/audit') },
          })}
        />
        <ActionKpiCard
          icon={XCircle}
          label="Inactive Users"
          value={data.users.inactive}
          sub="Archived / disabled"
          tone="slate"
          onClick={() => setDrill({
            type: 'users',
            title: 'Inactive users',
            loadRows: () => loadUsers('inactive'),
            viewAll: { label: 'Manage users', onClick: () => navigate('/dashboard/admin/users') },
          })}
        />
        <ActionKpiCard
          icon={Activity}
          label="Audit Logs Today"
          value={data.audit.today_logs}
          sub="System events today"
          tone="orange"
          onClick={() => navigate('/dashboard/audit')}
        />
        <ActionKpiCard
          icon={Database}
          label="Total Logs"
          value={(data.audit.total_logs || 0).toLocaleString()}
          sub="All-time audit entries"
          tone="slate"
          onClick={() => navigate('/dashboard/audit')}
        />
      </div>

      {/* License + Modules row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card
          className="cursor-pointer hover:shadow-md transition-shadow"
          role="button"
          tabIndex={0}
          onClick={() => navigate('/dashboard/license')}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate('/dashboard/license'); } }}
        >
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Shield className="h-5 w-5" /> License Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between mb-4">
              <Badge className={`text-xs ${licColors[data.license.status] || licColors.no_license}`}>
                {data.license.status?.replace('_', ' ').toUpperCase()}
              </Badge>
              {data.license.days_remaining != null && data.license.days_remaining > 0 && (
                <span className={`text-sm font-bold ${data.license.days_remaining <= 30 ? 'text-yellow-600' : 'text-green-600'}`}>
                  {data.license.days_remaining} days left
                </span>
              )}
            </div>
            <div className="space-y-2 text-sm">
              {data.license.hospital_name && (
                <div className="flex justify-between"><span className="text-gray-500">Hospital</span><span className="font-medium">{data.license.hospital_name}</span></div>
              )}
              {data.license.plan && (
                <div className="flex justify-between"><span className="text-gray-500">Plan</span><span className="font-medium capitalize">{data.license.plan}</span></div>
              )}
              {data.license.max_users && (
                <div className="flex justify-between"><span className="text-gray-500">Max Users</span><span className="font-medium">{data.license.max_users}</span></div>
              )}
              {data.license.expires_at && (
                <div className="flex justify-between"><span className="text-gray-500">Expires</span><span className="font-medium">{formatDate(data.license.expires_at)}</span></div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card
          className="cursor-pointer hover:shadow-md transition-shadow"
          role="button"
          tabIndex={0}
          onClick={() => navigate('/dashboard/admin/modules')}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate('/dashboard/admin/modules'); } }}
        >
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Monitor className="h-5 w-5" /> System Modules
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-2">
              {(data.modules || []).map(m => (
                <div key={m.name} className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${m.enabled ? 'bg-green-50 border-green-200' : 'bg-gray-50 border-gray-200'}`}>
                  {m.enabled
                    ? <CheckCircle2 className="h-4 w-4 text-green-500 flex-shrink-0" />
                    : <XCircle className="h-4 w-4 text-gray-400 flex-shrink-0" />}
                  <div>
                    <p className="text-sm font-medium">{m.display_name}</p>
                    {m.always_on && <p className="text-[10px] text-gray-400">Always on</p>}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Users by Role + Activity Trend */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-5 w-5" /> Users by Role
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {Object.entries(data.users.by_role || {}).sort((a, b) => b[1] - a[1]).map(([role, count]) => (
                <div
                  key={role}
                  className="flex items-center justify-between cursor-pointer hover:bg-gray-50 rounded px-1 py-0.5"
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate('/dashboard/admin/users')}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate('/dashboard/admin/users'); } }}
                >
                  <span className="text-sm capitalize text-gray-600">{role.replace(/_/g, ' ')}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-24 h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500 rounded-full" style={{ width: `${(count / Math.max(data.users.active, 1)) * 100}%` }} />
                    </div>
                    <span className="text-sm font-bold text-gray-700 w-6 text-right">{count}</span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Activity className="h-5 w-5" /> 7-Day Activity Trend
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-end gap-2 h-32">
              {(data.audit.daily_activity || []).map((d, i) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <span className="text-[10px] font-bold text-gray-600">{d.count}</span>
                  <div className="w-full bg-blue-100 rounded-t" style={{ height: `${Math.max((d.count / maxActivity) * 100, 4)}%` }}>
                    <div className="w-full h-full bg-blue-500 rounded-t opacity-80" />
                  </div>
                  <span className="text-[10px] text-gray-400">{d.day}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Audit Categories + Today's Logins */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card
          className="cursor-pointer hover:shadow-md transition-shadow"
          role="button"
          tabIndex={0}
          onClick={() => navigate('/dashboard/audit')}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate('/dashboard/audit'); } }}
        >
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Shield className="h-5 w-5" /> Activity by Category (This Week)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {Object.keys(data.audit.categories_this_week || {}).length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-4">No activity this week</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {Object.entries(data.audit.categories_this_week).sort((a, b) => b[1] - a[1]).map(([cat, count]) => (
                  <div key={cat} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium ${categoryColors[cat] || 'bg-gray-100 text-gray-600'}`}>
                    <span className="capitalize">{cat}</span>
                    <span className="font-bold">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <LogIn className="h-5 w-5" /> Today&apos;s Logins
              <Badge variant="outline" className="ml-auto">{data.recent_logins.length}</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {data.recent_logins.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-4">No logins today</p>
            ) : (
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {data.recent_logins.map((login, i) => (
                  <div key={i} className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-0">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full bg-blue-100 flex items-center justify-center text-xs font-bold text-blue-600">
                        {login.user_name?.charAt(0)}
                      </div>
                      <div>
                        <p className="text-sm font-medium">{login.user_name}</p>
                        <p className="text-[10px] text-gray-400 capitalize">{login.user_role?.replace(/_/g, ' ')}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-gray-500">{formatTime(login.time)}</p>
                      {login.ip && <p className="text-[10px] text-gray-400 font-mono">{login.ip}</p>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent System Actions */}
      <Card>
        <CardHeader className="pb-3 flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <Clock className="h-5 w-5" /> Recent System Actions
          </CardTitle>
          <Button size="sm" variant="outline" onClick={() => navigate('/dashboard/audit')}>
            View all
          </Button>
        </CardHeader>
        <CardContent>
          {data.recent_actions.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-6">No recent system actions</p>
          ) : (
            <div className="space-y-2">
              {data.recent_actions.map((action, i) => (
                <div key={i} className="flex items-center gap-3 py-2 border-b border-gray-50 last:border-0">
                  <Badge className={`text-[10px] capitalize w-20 justify-center ${categoryColors[action.category] || 'bg-gray-100'}`}>
                    {action.category}
                  </Badge>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-800 truncate">{action.description}</p>
                    <p className="text-[10px] text-gray-400">{action.user_name} &bull; {formatTime(action.time)}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <DashboardDrillDialog
        open={!!drill}
        onOpenChange={(open) => { if (!open) closeDrill(); }}
        title={drill?.title || ''}
        loadRows={drill?.loadRows || (async () => [])}
        viewAll={drill?.viewAll ? {
          ...drill.viewAll,
          onClick: () => {
            closeDrill();
            drill.viewAll.onClick();
          },
        } : undefined}
        renderRows={(rows) => {
          if (drill?.type === 'logins') {
            return (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">User</th>
                    <th className="py-2 pr-3 font-medium">Role</th>
                    <th className="py-2 pr-3 font-medium">Time</th>
                    <th className="py-2 font-medium">IP</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((login, i) => (
                    <tr key={i} className="border-b">
                      <td className="py-2 pr-3">{login.user_name || '—'}</td>
                      <td className="py-2 pr-3 capitalize text-xs">{(login.user_role || '').replace(/_/g, ' ') || '—'}</td>
                      <td className="py-2 pr-3 text-xs">{formatTime(login.time)}</td>
                      <td className="py-2 font-mono text-xs">{login.ip || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            );
          }
          return (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-3 font-medium">Name</th>
                  <th className="py-2 pr-3 font-medium">Username</th>
                  <th className="py-2 pr-3 font-medium">Role</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((u) => (
                  <tr key={u.id} className="border-b">
                    <td className="py-2 pr-3">{u.full_name || [u.first_name, u.last_name].filter(Boolean).join(' ') || '—'}</td>
                    <td className="py-2 pr-3 font-mono text-xs">{u.username || '—'}</td>
                    <td className="py-2 pr-3 capitalize text-xs">
                      {(u.user_role?.name || u.role || u.role_name || '').replace(/_/g, ' ') || '—'}
                    </td>
                    <td className="py-2 pr-3">
                      <Badge variant="outline">{u.is_active ? 'Active' : 'Inactive'}</Badge>
                    </td>
                    <td className="py-2 text-right">
                      <Button size="sm" variant="outline" onClick={() => { closeDrill(); navigate('/dashboard/admin/users'); }}>
                        Manage
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          );
        }}
      />
    </div>
  );
};

export default SuperAdminDashboard;
