import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Badge } from '../../components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import axios from 'axios';
import {
  Search, Download, Shield, Activity, Users, Clock, ChevronLeft, ChevronRight, Settings, Loader2,
  ChevronDown, ChevronUp, X
} from 'lucide-react';

const categoryColors = {
  auth: 'bg-blue-100 text-blue-700',
  patient: 'bg-green-100 text-green-700',
  appointment: 'bg-purple-100 text-purple-700',
  lab: 'bg-cyan-100 text-cyan-700',
  prescription: 'bg-pink-100 text-pink-700',
  consultation: 'bg-amber-100 text-amber-700',
  admin: 'bg-red-100 text-red-700',
  referral: 'bg-indigo-100 text-indigo-700',
  billing: 'bg-orange-100 text-orange-700',
};

const AuditLogsPage = () => {
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  // Filters
  const today = new Date().toISOString().split('T')[0];
  const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().split('T')[0];
  const [dateFrom, setDateFrom] = useState(weekAgo);
  const [dateTo, setDateTo] = useState(today);
  const [category, setCategory] = useState('all');
  const [search, setSearch] = useState('');
  const [userFilter, setUserFilter] = useState('all');
  const [userList, setUserList] = useState([]);
  const [actionFilter, setActionFilter] = useState('all');
  const [resourceTypeFilter, setResourceTypeFilter] = useState('all');
  const [resourceIdFilter, setResourceIdFilter] = useState('');
  const [distinctValues, setDistinctValues] = useState({ categories: [], actions: [], resource_types: [] });
  const [expandedRow, setExpandedRow] = useState(null);

  // Retention
  const [retention, setRetention] = useState(90);
  const [showRetention, setShowRetention] = useState(false);
  const [retentionInput, setRetentionInput] = useState(90);

  const fetchUsers = async () => {
    try {
      const res = await axios.get('/api/admin/users');
      setUserList(res.data || []);
    } catch {}
  };

  const fetchDistinctValues = async () => {
    try {
      const res = await axios.get('/api/audit/distinct-values');
      setDistinctValues(res.data || { categories: [], actions: [], resource_types: [] });
    } catch {}
  };

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.set('date_from', dateFrom);
      params.set('date_to', dateTo);
      params.set('page', page);
      params.set('page_size', 30);
      if (category !== 'all') params.set('category', category);
      if (userFilter !== 'all') params.set('user_id', userFilter);
      if (actionFilter !== 'all') params.set('action', actionFilter);
      if (resourceTypeFilter !== 'all') params.set('resource_type', resourceTypeFilter);
      if (resourceIdFilter.trim()) params.set('resource_id', resourceIdFilter.trim());
      if (search) params.set('search', search);

      const res = await axios.get(`/api/audit/logs?${params}`);
      setLogs(res.data.logs);
      setTotal(res.data.total);
      setTotalPages(res.data.total_pages);
    } catch {}
    finally { setLoading(false); }
  }, [dateFrom, dateTo, category, userFilter, actionFilter, resourceTypeFilter, resourceIdFilter, search, page]);

  const fetchStats = async () => {
    try {
      const res = await axios.get('/api/audit/stats');
      setStats(res.data);
      setRetention(res.data.retention_days);
      setRetentionInput(res.data.retention_days);
    } catch {}
  };

  useEffect(() => { fetchLogs(); }, [fetchLogs]);
  useEffect(() => { fetchStats(); fetchUsers(); fetchDistinctValues(); }, []);

  const exportCSV = async () => {
    try {
      const params = new URLSearchParams();
      params.set('date_from', dateFrom);
      params.set('date_to', dateTo);
      if (category !== 'all') params.set('category', category);
      if (userFilter !== 'all') params.set('user_id', userFilter);
      if (actionFilter !== 'all') params.set('action', actionFilter);
      if (resourceTypeFilter !== 'all') params.set('resource_type', resourceTypeFilter);
      if (resourceIdFilter.trim()) params.set('resource_id', resourceIdFilter.trim());
      if (search) params.set('search', search);
      const res = await axios.get(`/api/audit/logs/export?${params}`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit_logs_${dateFrom}_to_${dateTo}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch {
      // fallback
    }
  };

  const saveRetention = async () => {
    try {
      await axios.put('/api/audit/retention', { retention_days: retentionInput });
      setRetention(retentionInput);
      setShowRetention(false);
    } catch {}
  };

  const runCleanup = async () => {
    if (!window.confirm(`Delete logs older than ${retention} days?`)) return;
    try {
      const res = await axios.post('/api/audit/cleanup');
      alert(res.data.message);
      fetchLogs(); fetchStats();
    } catch {}
  };

  const formatTime = (ts) => {
    if (!ts) return '';
    try {
      const d = new Date(ts);
      return d.toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: true });
    } catch { return ts; }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Audit Logs</h1>
          <p className="text-muted-foreground text-sm">Track all user activity across the system</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setShowRetention(!showRetention)}>
          <Settings className="h-4 w-4 mr-1" /> Retention: {retention} days
        </Button>
      </div>

      {/* Retention config */}
      {showRetention && (
        <Card>
          <CardContent className="pt-4 pb-3">
            <div className="flex items-end gap-3">
              <div>
                <Label className="text-xs">Retention Period (days)</Label>
                <Input type="number" min={7} value={retentionInput}
                  onChange={e => setRetentionInput(parseInt(e.target.value) || 90)} className="w-32 h-9" />
              </div>
              <Button size="sm" className="h-9" onClick={saveRetention}>Save</Button>
              <Button size="sm" variant="destructive" className="h-9" onClick={runCleanup}>
                Cleanup Now
              </Button>
              <p className="text-xs text-gray-400 ml-2">Logs older than {retentionInput} days will be auto-deleted on app startup</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card><CardContent className="pt-5 pb-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-gray-500">Total Logs</p>
                <p className="text-xl font-bold">{stats.total_logs.toLocaleString()}</p>
              </div>
              <Shield className="h-8 w-8 text-blue-500" />
            </div>
          </CardContent></Card>
          <Card><CardContent className="pt-5 pb-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-gray-500">Today</p>
                <p className="text-xl font-bold">{stats.today_logs}</p>
              </div>
              <Activity className="h-8 w-8 text-green-500" />
            </div>
          </CardContent></Card>
          <Card><CardContent className="pt-5 pb-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-gray-500">Active Users Today</p>
                <p className="text-xl font-bold">{stats.active_users_today}</p>
              </div>
              <Users className="h-8 w-8 text-purple-500" />
            </div>
          </CardContent></Card>
          <Card><CardContent className="pt-5 pb-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-gray-500">Categories</p>
                <div className="flex flex-wrap gap-1 mt-1">
                  {Object.entries(stats.categories || {}).slice(0, 4).map(([cat, count]) => (
                    <span key={cat} className={`text-[10px] px-1.5 py-0.5 rounded ${categoryColors[cat] || 'bg-gray-100'}`}>
                      {cat}: {count}
                    </span>
                  ))}
                </div>
              </div>
              <Clock className="h-8 w-8 text-orange-500" />
            </div>
          </CardContent></Card>
        </div>
      )}

      {/* Filters */}
      <Card>
        <CardContent className="pt-4 pb-3">
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <Label className="text-xs">From</Label>
              <Input type="date" value={dateFrom} onChange={e => { setDateFrom(e.target.value); setPage(1); }} className="w-[140px] h-9" />
            </div>
            <div>
              <Label className="text-xs">To</Label>
              <Input type="date" value={dateTo} onChange={e => { setDateTo(e.target.value); setPage(1); }} className="w-[140px] h-9" />
            </div>
            <div>
              <Label className="text-xs">Category</Label>
              <Select value={category} onValueChange={v => { setCategory(v); setPage(1); }}>
                <SelectTrigger className="w-[140px] h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  {distinctValues.categories.map(c => (
                    <SelectItem key={c} value={c} className="capitalize">{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Action</Label>
              <Select value={actionFilter} onValueChange={v => { setActionFilter(v); setPage(1); }}>
                <SelectTrigger className="w-[160px] h-9"><SelectValue /></SelectTrigger>
                <SelectContent className="max-h-72">
                  <SelectItem value="all">All Actions</SelectItem>
                  {distinctValues.actions.map(a => (
                    <SelectItem key={a} value={a} className="capitalize">{a.replace(/_/g, ' ')}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Resource Type</Label>
              <Select value={resourceTypeFilter} onValueChange={v => { setResourceTypeFilter(v); setPage(1); }}>
                <SelectTrigger className="w-[160px] h-9"><SelectValue /></SelectTrigger>
                <SelectContent className="max-h-72">
                  <SelectItem value="all">All Types</SelectItem>
                  {distinctValues.resource_types.map(r => (
                    <SelectItem key={r} value={r} className="capitalize">{r.replace(/_/g, ' ')}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Resource ID</Label>
              <Input placeholder="exact id..." value={resourceIdFilter}
                onChange={e => { setResourceIdFilter(e.target.value); setPage(1); }} className="w-[120px] h-9" />
            </div>
            <div>
              <Label className="text-xs">User</Label>
              <Select value={userFilter} onValueChange={v => { setUserFilter(v); setPage(1); }}>
                <SelectTrigger className="w-[160px] h-9"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Users</SelectItem>
                  {userList.map(u => (
                    <SelectItem key={u.id} value={String(u.id)}>
                      {u.first_name} {u.last_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs">Search</Label>
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
                <Input placeholder="Description..." value={search}
                  onChange={e => { setSearch(e.target.value); setPage(1); }} className="pl-8 w-[180px] h-9" />
              </div>
            </div>
            <p className="text-xs text-gray-400">{total} result{total !== 1 ? 's' : ''}</p>
            {(category !== 'all' || userFilter !== 'all' || actionFilter !== 'all' || resourceTypeFilter !== 'all' || resourceIdFilter || search) && (
              <Button variant="ghost" size="sm" className="h-9 text-xs"
                onClick={() => {
                  setCategory('all'); setUserFilter('all'); setActionFilter('all');
                  setResourceTypeFilter('all'); setResourceIdFilter(''); setSearch(''); setPage(1);
                }}>
                <X className="h-3 w-3 mr-1" /> Clear
              </Button>
            )}
            <Button variant="outline" size="sm" className="h-9" onClick={exportCSV} disabled={total === 0}>
              <Download className="h-4 w-4 mr-1" /> Export CSV
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Log Table */}
      <Card>
        <CardContent className="pt-4">
          {loading ? (
            <div className="flex justify-center py-12"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>
          ) : logs.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <Shield className="h-10 w-10 mx-auto mb-2 text-gray-300" />
              <p className="text-sm">No audit logs found for the selected filters.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-500">
                    <th className="pb-2 pr-2 w-6"></th>
                    <th className="pb-2 pr-3">Time</th>
                    <th className="pb-2 pr-3">User</th>
                    <th className="pb-2 pr-3">Category</th>
                    <th className="pb-2 pr-3">Action</th>
                    <th className="pb-2 pr-3">Resource</th>
                    <th className="pb-2 pr-3">Description</th>
                    <th className="pb-2">IP</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map(log => {
                    const isOpen = expandedRow === log.id;
                    let detailsObj = null;
                    if (log.details) {
                      try { detailsObj = JSON.parse(log.details); } catch { detailsObj = log.details; }
                    }
                    return (
                      <React.Fragment key={log.id}>
                        <tr className="border-b hover:bg-gray-50 cursor-pointer"
                            onClick={() => setExpandedRow(isOpen ? null : log.id)}>
                          <td className="py-2.5 pr-2 text-gray-400">
                            {isOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                          </td>
                          <td className="py-2.5 pr-3 text-xs text-gray-500 whitespace-nowrap">{formatTime(log.timestamp)}</td>
                          <td className="py-2.5 pr-3">
                            <p className="text-sm font-medium">{log.user_name}</p>
                            {log.user_role && <p className="text-[10px] text-gray-400 capitalize">{log.user_role.replace('_', ' ')}</p>}
                          </td>
                          <td className="py-2.5 pr-3">
                            <Badge className={`text-[10px] capitalize ${categoryColors[log.category] || 'bg-gray-100'}`}>
                              {log.category}
                            </Badge>
                          </td>
                          <td className="py-2.5 pr-3 text-xs capitalize">{log.action?.replace(/_/g, ' ')}</td>
                          <td className="py-2.5 pr-3 text-xs">
                            {log.resource_type && (
                              <>
                                <span className="capitalize text-gray-700">{log.resource_type.replace(/_/g, ' ')}</span>
                                {log.resource_id && <span className="text-gray-400 font-mono ml-1">#{log.resource_id}</span>}
                              </>
                            )}
                          </td>
                          <td className="py-2.5 pr-3 text-xs text-gray-600 max-w-[280px] truncate">{log.description}</td>
                          <td className="py-2.5 text-xs text-gray-400 font-mono">{log.ip_address}</td>
                        </tr>
                        {isOpen && (
                          <tr className="bg-gray-50 border-b">
                            <td></td>
                            <td colSpan={7} className="py-3 pr-3">
                              <div className="space-y-2">
                                {log.description && (
                                  <div>
                                    <p className="text-[10px] uppercase text-gray-400 mb-0.5">Description</p>
                                    <p className="text-xs text-gray-700">{log.description}</p>
                                  </div>
                                )}
                                {detailsObj && (
                                  <div>
                                    <p className="text-[10px] uppercase text-gray-400 mb-0.5">Details</p>
                                    <pre className="text-[11px] bg-white border rounded p-2 overflow-x-auto max-h-64 font-mono text-gray-700">
{typeof detailsObj === 'string' ? detailsObj : JSON.stringify(detailsObj, null, 2)}
                                    </pre>
                                  </div>
                                )}
                                {log.resource_type && log.resource_id && (
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setResourceTypeFilter(log.resource_type);
                                      setResourceIdFilter(log.resource_id);
                                      setPage(1);
                                    }}
                                    className="text-[11px] text-blue-600 hover:underline"
                                  >
                                    Show all activity for this {log.resource_type.replace(/_/g, ' ')} →
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-4 pt-3 border-t">
              <p className="text-xs text-gray-500">Page {page} of {totalPages}</p>
              <div className="flex gap-1">
                <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button size="sm" variant="outline" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default AuditLogsPage;
