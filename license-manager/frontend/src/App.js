import React, { useState, useEffect, useCallback } from 'react';

const API = 'http://localhost:9000/api';

/* ─── Icons (inline SVGs) ─── */
const Icon = ({ d, className = "w-5 h-5" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d={d} />
  </svg>
);
const Icons = {
  dashboard: "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0a1 1 0 01-1-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 01-1 1",
  license: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
  plus: "M12 4v16m8-8H4",
  download: "M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4",
  refresh: "M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15",
  trash: "M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16",
  search: "M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z",
  check: "M5 13l4 4L19 7",
  x: "M6 18L18 6M6 6l12 12",
  shield: "M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z",
};

function App() {
  const [page, setPage] = useState('dashboard');
  const [dash, setDash] = useState(null);
  const [licenses, setLicenses] = useState([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [showForm, setShowForm] = useState(false);
  const [showRenew, setShowRenew] = useState(null);
  const [renewDays, setRenewDays] = useState(365);
  const [form, setForm] = useState({
    hospital_id: '', hospital_name: '', machine_id: '', plan: 'standard',
    max_users: 50, days: 365,
    features: ['outpatient', 'lab', 'ehr', 'admin'],
    modules: [], notes: ''
  });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);

  // Customer state
  const [customers, setCustomers] = useState([]);
  const [custSearch, setCustSearch] = useState('');
  const [showCustForm, setShowCustForm] = useState(false);
  const [editingCust, setEditingCust] = useState(null);
  const [custForm, setCustForm] = useState({ hospital_name: '', hospital_id: '', contact_person: '', phone: '', email: '', address: '', machine_id: '', notes: '' });
  const [selectedCust, setSelectedCust] = useState(null);
  const [custDetail, setCustDetail] = useState(null);
  const [showPayForm, setShowPayForm] = useState(false);
  const [payForm, setPayForm] = useState({ payment_type: 'license', payment_mode: 'cash', amount: '', invoice_number: '', description: '' });

  const fetchDash = useCallback(async () => {
    try { const r = await fetch(`${API}/dashboard`); setDash(await r.json()); } catch {}
  }, []);

  const fetchLicenses = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (statusFilter !== 'all') params.set('status', statusFilter);
      const r = await fetch(`${API}/licenses?${params}`);
      setLicenses(await r.json());
    } catch {}
  }, [search, statusFilter]);

  const fetchCustomers = useCallback(async () => {
    try {
      const params = custSearch ? `?search=${custSearch}` : '';
      const r = await fetch(`${API}/customers${params}`);
      setCustomers(await r.json());
    } catch {}
  }, [custSearch]);

  const fetchCustDetail = async (id) => {
    try {
      const r = await fetch(`${API}/customers/${id}`);
      setCustDetail(await r.json());
    } catch {}
  };

  useEffect(() => { fetchDash(); }, [fetchDash]);
  useEffect(() => { fetchLicenses(); }, [fetchLicenses]);
  useEffect(() => { fetchCustomers(); }, [fetchCustomers]);

  const showMessage = (text, type = 'success') => {
    setMsg({ text, type });
    setTimeout(() => setMsg(null), 4000);
  };

  const createLicense = async () => {
    if (!form.hospital_id || !form.hospital_name || !form.machine_id) return;
    setSaving(true);
    try {
      const r = await fetch(`${API}/licenses`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form)
      });
      if (r.ok) {
        showMessage('License generated successfully');
        setShowForm(false);
        setForm({ hospital_id: '', hospital_name: '', machine_id: '', plan: 'standard', max_users: 50, days: 365, features: ['outpatient', 'lab', 'ehr', 'admin'], modules: [], notes: '' });
        fetchLicenses(); fetchDash();
      } else {
        const e = await r.json();
        showMessage(e.detail || 'Generation failed', 'error');
      }
    } catch { showMessage('Failed to create license', 'error'); }
    finally { setSaving(false); }
  };

  const renewLicense = async (licenseId) => {
    const r = await fetch(`${API}/licenses/${licenseId}/renew`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ days: renewDays })
    });
    if (r.ok) {
      showMessage('License renewed — new file ready for download');
      setShowRenew(null);
      fetchLicenses(); fetchDash();
    } else {
      const e = await r.json();
      showMessage(e.detail || 'Renewal failed', 'error');
    }
  };

  const downloadLicense = (licenseId) => {
    window.open(`${API}/licenses/${licenseId}/download`, '_blank');
  };

  const deleteLicense = async (licenseId) => {
    if (!window.confirm('Delete this license record permanently?')) return;
    await fetch(`${API}/licenses/${licenseId}`, { method: 'DELETE' });
    showMessage('License record deleted');
    fetchLicenses(); fetchDash();
  };

  // Customer functions
  const saveCust = async () => {
    if (!custForm.hospital_name) return;
    setSaving(true);
    try {
      const url = editingCust ? `${API}/customers/${editingCust.id}` : `${API}/customers`;
      const method = editingCust ? 'PUT' : 'POST';
      const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(custForm) });
      if (r.ok) {
        showMessage(editingCust ? 'Customer updated' : 'Customer created');
        setShowCustForm(false); setEditingCust(null);
        setCustForm({ hospital_name: '', hospital_id: '', contact_person: '', phone: '', email: '', address: '', machine_id: '', notes: '' });
        fetchCustomers(); fetchDash();
        if (selectedCust) fetchCustDetail(selectedCust);
      } else { const e = await r.json(); showMessage(e.detail || 'Failed', 'error'); }
    } catch { showMessage('Failed', 'error'); }
    finally { setSaving(false); }
  };

  const openEditCust = (c) => {
    setEditingCust(c);
    setCustForm({ hospital_name: c.hospital_name, hospital_id: c.hospital_id || '', contact_person: c.contact_person || '', phone: c.phone || '', email: c.email || '', address: c.address || '', machine_id: c.machine_id || '', notes: c.notes || '' });
    setShowCustForm(true);
  };

  const deleteCust = async (id) => {
    if (!window.confirm('Delete this customer and all related records?')) return;
    await fetch(`${API}/customers/${id}`, { method: 'DELETE' });
    showMessage('Customer deleted');
    fetchCustomers(); fetchDash();
    if (selectedCust === id) { setSelectedCust(null); setCustDetail(null); }
  };

  const recordPayment = async () => {
    if (!payForm.amount || !selectedCust) return;
    setSaving(true);
    try {
      const r = await fetch(`${API}/payments`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payForm, customer_id: selectedCust, amount: parseFloat(payForm.amount) })
      });
      if (r.ok) {
        showMessage('Payment recorded');
        setShowPayForm(false);
        setPayForm({ payment_type: 'license', payment_mode: 'cash', amount: '', invoice_number: '', description: '' });
        fetchCustDetail(selectedCust); fetchDash();
      } else { const e = await r.json(); showMessage(e.detail || 'Failed', 'error'); }
    } catch { showMessage('Failed', 'error'); }
    finally { setSaving(false); }
  };

  const deletePayment = async (payId) => {
    if (!window.confirm('Delete this payment record?')) return;
    await fetch(`${API}/payments/${payId}`, { method: 'DELETE' });
    showMessage('Payment deleted');
    fetchCustDetail(selectedCust);
  };

  const formatDate = (d) => {
    if (!d) return '—';
    try { return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }); }
    catch { return d; }
  };

  const allFeatures = ['outpatient', 'inpatient', 'lab', 'pharmacy', 'ehr', 'admin', 'billing'];

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: Icons.dashboard },
    { id: 'licenses', label: 'Licenses', icon: Icons.license },
    { id: 'customers', label: 'Customers', icon: "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" },
  ];

  /* ─── Status helpers ─── */
  const statusConfig = {
    active: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', dot: 'bg-emerald-400', label: 'Active' },
    expiring_soon: { bg: 'bg-amber-500/10', text: 'text-amber-400', dot: 'bg-amber-400', label: 'Expiring' },
    expired: { bg: 'bg-red-500/10', text: 'text-red-400', dot: 'bg-red-400', label: 'Expired' },
    renewed: { bg: 'bg-slate-500/10', text: 'text-slate-400', dot: 'bg-slate-500', label: 'Renewed' },
  };

  const StatusBadge = ({ status }) => {
    const c = statusConfig[status] || statusConfig.expired;
    return (
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold tracking-wide uppercase ${c.bg} ${c.text}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
        {c.label}
      </span>
    );
  };

  const DaysLeft = ({ days }) => {
    const color = days <= 0 ? 'text-red-400' : days <= 30 ? 'text-amber-400' : 'text-emerald-400';
    const bg = days <= 0 ? 'bg-red-500/10' : days <= 30 ? 'bg-amber-500/10' : 'bg-emerald-500/10';
    return (
      <span className={`font-mono font-bold text-sm ${color} ${bg} px-2 py-0.5 rounded`}>
        {days <= 0 ? 'EXP' : days}
      </span>
    );
  };

  const FeatureTag = ({ name }) => (
    <span className="px-1.5 py-0.5 bg-slate-700/50 text-slate-300 rounded text-[10px] font-medium capitalize tracking-wide">
      {name}
    </span>
  );

  /* ─── Modal wrapper ─── */
  const Modal = ({ open, onClose, children, wide }) => {
    if (!open) return null;
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
        <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
        <div className={`relative ${wide ? 'max-w-2xl' : 'max-w-md'} w-full mx-4 bg-slate-850 border border-slate-700/50 rounded-2xl shadow-2xl animate-slideIn max-h-[90vh] overflow-y-auto scrollbar-thin`}
          onClick={e => e.stopPropagation()}>
          {children}
        </div>
      </div>
    );
  };

  /* ─── Form input ─── */
  const Input = ({ label, required, ...props }) => (
    <div>
      <label className="block text-xs font-medium text-slate-400 mb-1.5">
        {label} {required && <span className="text-amber-400">*</span>}
      </label>
      <input {...props}
        className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-colors" />
    </div>
  );

  return (
    <div className="flex h-screen bg-slate-950">

      {/* ─── Sidebar ─── */}
      <aside className="w-60 bg-slate-925 border-r border-slate-800/50 flex flex-col">
        <div className="p-5 border-b border-slate-800/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-gradient-to-br from-blue-500 to-cyan-400 rounded-lg flex items-center justify-center">
              <Icon d={Icons.shield} className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-white tracking-tight">KT License</h1>
              <p className="text-[10px] text-slate-500 font-medium tracking-widest uppercase">Manager</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {navItems.map(item => (
            <button key={item.id} onClick={() => setPage(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-medium transition-all duration-150
                ${page === item.id
                  ? 'bg-blue-600/15 text-blue-400 shadow-sm shadow-blue-500/5'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800/50'}`}>
              <Icon d={item.icon} className="w-[18px] h-[18px]" />
              {item.label}
            </button>
          ))}
        </nav>

        <div className="p-4 border-t border-slate-800/50">
          <p className="text-[10px] text-slate-600 text-center">KT Health Soft v1.0</p>
        </div>
      </aside>

      {/* ─── Main ─── */}
      <div className="flex-1 flex flex-col min-w-0">

        {/* Toast */}
        {msg && (
          <div className="fixed top-4 right-4 z-[60] animate-fadeIn">
            <div className={`px-4 py-3 rounded-xl text-sm font-medium shadow-lg border ${
              msg.type === 'error'
                ? 'bg-red-500/10 border-red-500/20 text-red-300'
                : 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300'
            }`}>
              {msg.text}
            </div>
          </div>
        )}

        <main className="flex-1 overflow-y-auto p-6 scrollbar-thin">

          {/* ═══════ DASHBOARD ═══════ */}
          {page === 'dashboard' && (
            <div className="space-y-6 animate-fadeIn">
              <div>
                <h2 className="text-2xl font-bold text-white">Dashboard</h2>
                <p className="text-sm text-slate-500 mt-1">License overview and recent activity</p>
              </div>

              {/* Stats */}
              {dash && (
                <div className="grid grid-cols-3 md:grid-cols-6 gap-4">
                  {[
                    { label: 'Customers', value: dash.total_customers || 0, color: 'from-blue-600/20 to-blue-700/10', accent: 'text-blue-400' },
                    { label: 'Total Licenses', value: dash.total, color: 'from-slate-600 to-slate-700', accent: 'text-white' },
                    { label: 'Active', value: dash.active, color: 'from-emerald-600/20 to-emerald-700/10', accent: 'text-emerald-400' },
                    { label: 'Expiring Soon', value: dash.expiring_soon, color: 'from-amber-600/20 to-amber-700/10', accent: 'text-amber-400' },
                    { label: 'Expired', value: dash.expired, color: 'from-red-600/20 to-red-700/10', accent: 'text-red-400' },
                    { label: 'Revenue', value: `₹${(dash.total_revenue || 0).toLocaleString('en-IN')}`, color: 'from-cyan-600/20 to-cyan-700/10', accent: 'text-cyan-400' },
                  ].map((c, i) => (
                    <div key={i} className={`bg-gradient-to-br ${c.color} rounded-xl p-5 stat-glow`}
                      style={{ animationDelay: `${i * 0.05}s` }}>
                      <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">{c.label}</p>
                      <p className={`text-4xl font-bold mt-2 font-mono ${c.accent}`}>{c.value}</p>
                    </div>
                  ))}
                </div>
              )}

              {/* Recent Licenses */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Recent Licenses</h3>
                  <button onClick={() => setPage('licenses')} className="text-xs text-blue-400 hover:text-blue-300">
                    View all →
                  </button>
                </div>
                <div className="bg-slate-925 border border-slate-800/50 rounded-xl overflow-hidden">
                  {licenses.slice(0, 5).map((lic, i) => (
                    <div key={lic.license_id}
                      className={`flex items-center justify-between px-5 py-3.5 ${i < Math.min(licenses.length, 5) - 1 ? 'border-b border-slate-800/30' : ''}`}
                      style={{ animationDelay: `${i * 0.04}s` }}>
                      <div className="flex items-center gap-4">
                        <div className="w-9 h-9 rounded-lg bg-slate-800 flex items-center justify-center text-xs font-bold text-slate-400 font-mono">
                          {lic.hospital_name?.charAt(0)}
                        </div>
                        <div>
                          <p className="text-sm font-semibold text-white">{lic.hospital_name}</p>
                          <p className="text-xs text-slate-500 font-mono">{lic.machine_id}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <DaysLeft days={lic.days_left} />
                        <StatusBadge status={lic.computed_status} />
                      </div>
                    </div>
                  ))}
                  {licenses.length === 0 && (
                    <div className="text-center py-12 text-slate-600 text-sm">No licenses generated yet</div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ═══════ LICENSES ═══════ */}
          {page === 'licenses' && (
            <div className="space-y-5 animate-fadeIn">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-2xl font-bold text-white">Licenses</h2>
                  <p className="text-sm text-slate-500 mt-1">{licenses.length} license{licenses.length !== 1 ? 's' : ''} total</p>
                </div>
                <button onClick={() => setShowForm(true)}
                  className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-sm font-semibold transition-colors shadow-lg shadow-blue-600/20">
                  <Icon d={Icons.plus} className="w-4 h-4" />
                  Generate License
                </button>
              </div>

              {/* Filters */}
              <div className="flex gap-3">
                <div className="relative flex-1 max-w-xs">
                  <Icon d={Icons.search} className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                  <input value={search} onChange={e => setSearch(e.target.value)}
                    placeholder="Search hospital, ID, machine..."
                    className="w-full bg-slate-925 border border-slate-700/50 rounded-xl pl-10 pr-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50" />
                </div>
                <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
                  className="bg-slate-925 border border-slate-700/50 rounded-xl px-3 py-2.5 text-sm text-slate-300 focus:outline-none focus:border-blue-500/50 appearance-none pr-8"
                  style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2364748b' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 10px center' }}>
                  <option value="all">All Status</option>
                  <option value="active">Active</option>
                  <option value="expiring_soon">Expiring Soon</option>
                  <option value="expired">Expired</option>
                </select>
              </div>

              {/* Table */}
              <div className="bg-slate-925 border border-slate-800/50 rounded-xl overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-800/50">
                      {['Hospital', 'Machine ID', 'Plan', 'Modules', 'Issued', 'Expires', 'Days', 'Status', 'Actions'].map(h => (
                        <th key={h} className="text-left px-4 py-3 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {licenses.map((lic, i) => (
                      <tr key={lic.license_id} className="border-b border-slate-800/20 hover:bg-slate-800/20 transition-colors">
                        <td className="px-4 py-3.5">
                          <p className="font-semibold text-white">{lic.hospital_name}</p>
                          <p className="text-[11px] text-slate-500 font-mono mt-0.5">{lic.hospital_id}</p>
                          {lic.notes?.startsWith('Renewed from') && (
                            <p className="text-[10px] text-blue-400/70 mt-0.5">{lic.notes}</p>
                          )}
                        </td>
                        <td className="px-4 py-3.5 font-mono text-xs text-slate-300">{lic.machine_id}</td>
                        <td className="px-4 py-3.5">
                          <span className="capitalize text-slate-300">{lic.plan}</span>
                          <p className="text-[10px] text-slate-500 mt-0.5">{lic.max_users} users</p>
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="flex flex-wrap gap-1 max-w-[150px]">
                            {(lic.features || []).slice(0, 4).map(f => <FeatureTag key={f} name={f} />)}
                            {(lic.features || []).length > 4 && (
                              <span className="text-[10px] text-slate-500">+{lic.features.length - 4}</span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 text-xs text-slate-400">{formatDate(lic.issued_at)}</td>
                        <td className="px-4 py-3.5 text-xs text-slate-400">{formatDate(lic.expires_at)}</td>
                        <td className="px-4 py-3.5"><DaysLeft days={lic.days_left} /></td>
                        <td className="px-4 py-3.5"><StatusBadge status={lic.computed_status} /></td>
                        <td className="px-4 py-3.5">
                          <div className="flex gap-1.5">
                            <button onClick={() => downloadLicense(lic.license_id)} title="Download .lic"
                              className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors">
                              <Icon d={Icons.download} className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => { setShowRenew(lic); setRenewDays(365); }} title="Renew"
                              className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors">
                              <Icon d={Icons.refresh} className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => deleteLicense(lic.license_id)} title="Delete"
                              className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors">
                              <Icon d={Icons.trash} className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                    {licenses.length === 0 && (
                      <tr>
                        <td colSpan={9} className="text-center py-16 text-slate-600">
                          <Icon d={Icons.license} className="w-10 h-10 mx-auto mb-3 opacity-30" />
                          <p className="text-sm">No licenses found</p>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ═══════ CUSTOMERS ═══════ */}
          {page === 'customers' && !selectedCust && (
            <div className="space-y-5 animate-fadeIn">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-2xl font-bold text-white">Customers</h2>
                  <p className="text-sm text-slate-500 mt-1">{customers.length} customer{customers.length !== 1 ? 's' : ''}</p>
                </div>
                <button onClick={() => { setEditingCust(null); setCustForm({ hospital_name: '', hospital_id: '', contact_person: '', phone: '', email: '', address: '', machine_id: '', notes: '' }); setShowCustForm(true); }}
                  className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-sm font-semibold transition-colors shadow-lg shadow-blue-600/20">
                  <Icon d={Icons.plus} className="w-4 h-4" /> Add Customer
                </button>
              </div>

              <div className="relative max-w-xs">
                <Icon d={Icons.search} className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <input value={custSearch} onChange={e => setCustSearch(e.target.value)} placeholder="Search customers..."
                  className="w-full bg-slate-925 border border-slate-700/50 rounded-xl pl-10 pr-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50" />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {customers.map(c => (
                  <div key={c.id} className="bg-slate-925 border border-slate-800/50 rounded-xl p-5 hover:border-slate-700/50 transition-colors cursor-pointer"
                    onClick={() => { setSelectedCust(c.id); fetchCustDetail(c.id); }}>
                    <div className="flex items-start justify-between mb-3">
                      <div>
                        <h3 className="font-semibold text-white">{c.hospital_name}</h3>
                        {c.hospital_id && <p className="text-xs text-slate-500 font-mono mt-0.5">{c.hospital_id}</p>}
                      </div>
                      <span className={`w-2 h-2 rounded-full mt-1.5 ${c.is_active ? 'bg-emerald-400' : 'bg-slate-600'}`} />
                    </div>
                    {c.contact_person && <p className="text-sm text-slate-400">{c.contact_person}</p>}
                    <div className="flex gap-3 mt-2 text-xs text-slate-500">
                      {c.phone && <span>{c.phone}</span>}
                      {c.machine_id && <span className="font-mono">{c.machine_id}</span>}
                    </div>
                    <div className="flex gap-1.5 mt-3" onClick={e => e.stopPropagation()}>
                      <button onClick={() => openEditCust(c)} className="px-2 py-1 text-[11px] bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700">Edit</button>
                      <button onClick={() => deleteCust(c.id)} className="px-2 py-1 text-[11px] bg-red-500/10 text-red-400 rounded-lg hover:bg-red-500/20">Delete</button>
                    </div>
                  </div>
                ))}
                {customers.length === 0 && (
                  <div className="col-span-full text-center py-16 text-slate-600">
                    <p className="text-sm">No customers yet. Add your first customer.</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ═══════ CUSTOMER DETAIL ═══════ */}
          {page === 'customers' && selectedCust && custDetail && (
            <div className="space-y-5 animate-fadeIn">
              <div className="flex items-center gap-3">
                <button onClick={() => { setSelectedCust(null); setCustDetail(null); }}
                  className="p-2 text-slate-400 hover:text-white bg-slate-800/50 rounded-lg">
                  ←
                </button>
                <div>
                  <h2 className="text-2xl font-bold text-white">{custDetail.customer.hospital_name}</h2>
                  <div className="flex gap-3 text-xs text-slate-500 mt-1">
                    {custDetail.customer.hospital_id && <span className="font-mono">{custDetail.customer.hospital_id}</span>}
                    {custDetail.customer.contact_person && <span>{custDetail.customer.contact_person}</span>}
                    {custDetail.customer.phone && <span>{custDetail.customer.phone}</span>}
                    {custDetail.customer.email && <span>{custDetail.customer.email}</span>}
                  </div>
                </div>
              </div>

              {/* Summary cards */}
              <div className="grid grid-cols-4 gap-4">
                {[
                  { label: 'Licenses', value: custDetail.summary.total_licenses, accent: 'text-blue-400' },
                  { label: 'Active', value: custDetail.summary.active_licenses, accent: 'text-emerald-400' },
                  { label: 'Payments', value: custDetail.summary.total_payments, accent: 'text-cyan-400' },
                  { label: 'Total Paid', value: `₹${custDetail.summary.total_paid.toLocaleString('en-IN')}`, accent: 'text-amber-400' },
                ].map((c, i) => (
                  <div key={i} className="bg-slate-925 border border-slate-800/50 rounded-xl p-4 stat-glow">
                    <p className="text-[11px] text-slate-500 uppercase tracking-wider">{c.label}</p>
                    <p className={`text-2xl font-bold mt-1 font-mono ${c.accent}`}>{c.value}</p>
                  </div>
                ))}
              </div>

              {/* Licenses */}
              <div className="bg-slate-925 border border-slate-800/50 rounded-xl overflow-hidden">
                <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800/30">
                  <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Licenses</h3>
                  <button onClick={() => {
                    setForm({ ...form, customer_id: selectedCust, hospital_id: custDetail.customer.hospital_id || '', hospital_name: custDetail.customer.hospital_name, machine_id: custDetail.customer.machine_id || '' });
                    setShowForm(true);
                  }} className="text-xs text-blue-400 hover:text-blue-300 font-medium">+ Generate</button>
                </div>
                {custDetail.licenses.length === 0 ? (
                  <p className="text-center py-8 text-slate-600 text-sm">No licenses</p>
                ) : custDetail.licenses.map((lic, i) => (
                  <div key={lic.license_id} className={`flex items-center justify-between px-5 py-3 ${i < custDetail.licenses.length - 1 ? 'border-b border-slate-800/20' : ''}`}>
                    <div className="flex items-center gap-4">
                      <div>
                        <p className="text-sm text-white font-mono">{lic.machine_id}</p>
                        <p className="text-[11px] text-slate-500">{lic.plan} &bull; {formatDate(lic.issued_at)} → {formatDate(lic.expires_at)}</p>
                        {lic.notes?.startsWith('Renewed') && <p className="text-[10px] text-blue-400/60">{lic.notes}</p>}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="flex gap-1">
                        {(lic.features || []).slice(0, 3).map(f => <FeatureTag key={f} name={f} />)}
                      </div>
                      <DaysLeft days={lic.days_left} />
                      <StatusBadge status={lic.computed_status} />
                      <button onClick={() => downloadLicense(lic.license_id)} title="Download"
                        className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20">
                        <Icon d={Icons.download} className="w-3.5 h-3.5" />
                      </button>
                      <button onClick={() => { setShowRenew(lic); setRenewDays(365); }} title="Renew"
                        className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20">
                        <Icon d={Icons.refresh} className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {/* Payments */}
              <div className="bg-slate-925 border border-slate-800/50 rounded-xl overflow-hidden">
                <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800/30">
                  <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Payment History</h3>
                  <button onClick={() => setShowPayForm(true)} className="text-xs text-blue-400 hover:text-blue-300 font-medium">+ Record Payment</button>
                </div>
                {custDetail.payments.length === 0 ? (
                  <p className="text-center py-8 text-slate-600 text-sm">No payments recorded</p>
                ) : custDetail.payments.map((pay, i) => (
                  <div key={pay.id} className={`flex items-center justify-between px-5 py-3 ${i < custDetail.payments.length - 1 ? 'border-b border-slate-800/20' : ''}`}>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-semibold text-emerald-400">₹{pay.amount.toLocaleString('en-IN')}</span>
                        <span className="px-1.5 py-0.5 bg-slate-700/50 text-slate-400 rounded text-[10px] capitalize">{pay.payment_type}</span>
                        <span className="px-1.5 py-0.5 bg-slate-700/50 text-slate-400 rounded text-[10px] capitalize">{pay.payment_mode}</span>
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {formatDate(pay.payment_date)}
                        {pay.invoice_number && <span> &bull; Inv: {pay.invoice_number}</span>}
                        {pay.description && <span> &bull; {pay.description}</span>}
                      </p>
                    </div>
                    <button onClick={() => deletePayment(pay.id)} className="p-1.5 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20">
                      <Icon d={Icons.trash} className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </main>
      </div>

      {/* ═══════ GENERATE MODAL ═══════ */}
      <Modal open={showForm} onClose={() => setShowForm(false)} wide>
        <div className="p-6 space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-white">Generate License</h2>
              <p className="text-xs text-slate-500 mt-0.5">Create a new signed license file</p>
            </div>
            <button onClick={() => setShowForm(false)} className="p-1 text-slate-500 hover:text-white">
              <Icon d={Icons.x} className="w-5 h-5" />
            </button>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Input label="Hospital ID" required value={form.hospital_id}
              onChange={e => setForm({...form, hospital_id: e.target.value})} placeholder="HOSP01" />
            <Input label="Hospital Name" required value={form.hospital_name}
              onChange={e => setForm({...form, hospital_name: e.target.value})} placeholder="City Hospital" />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Input label="Machine ID" required value={form.machine_id}
              onChange={e => setForm({...form, machine_id: e.target.value})} placeholder="CA86-C087-6261" />
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Validity</label>
              <select value={form.days} onChange={e => setForm({...form, days: parseInt(e.target.value)})}
                className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/50">
                <option value={30}>1 Month</option>
                <option value={90}>3 Months</option>
                <option value={180}>6 Months</option>
                <option value={365}>1 Year</option>
                <option value={730}>2 Years</option>
                <option value={1095}>3 Years</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Plan</label>
              <select value={form.plan} onChange={e => setForm({...form, plan: e.target.value})}
                className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/50">
                <option value="standard">Standard</option>
                <option value="professional">Professional</option>
                <option value="enterprise">Enterprise</option>
              </select>
            </div>
            <Input label="Max Users" type="number" value={form.max_users}
              onChange={e => setForm({...form, max_users: parseInt(e.target.value) || 50})} />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-2">Modules</label>
            <div className="flex flex-wrap gap-2">
              {allFeatures.map(f => {
                const active = form.features.includes(f);
                return (
                  <button key={f} type="button" onClick={() => {
                    const feats = active ? form.features.filter(x => x !== f) : [...form.features, f];
                    setForm({...form, features: feats});
                  }}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-all border ${
                      active
                        ? 'bg-blue-500/15 border-blue-500/30 text-blue-400'
                        : 'bg-slate-800/30 border-slate-700/30 text-slate-500 hover:text-slate-300'
                    }`}>
                    {active && <span className="mr-1">✓</span>}
                    {f}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Notes</label>
            <textarea value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} rows={2}
              placeholder="Optional notes about this license..."
              className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50 resize-none" />
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-700/30">
            <button onClick={() => setShowForm(false)}
              className="px-4 py-2.5 text-sm text-slate-400 hover:text-white rounded-lg transition-colors">
              Cancel
            </button>
            <button onClick={createLicense}
              disabled={saving || !form.hospital_id || !form.hospital_name || !form.machine_id}
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:hover:bg-blue-600 text-white text-sm font-semibold rounded-xl transition-colors shadow-lg shadow-blue-600/20">
              {saving ? 'Generating...' : 'Generate License'}
            </button>
          </div>
        </div>
      </Modal>

      {/* ═══════ RENEW MODAL ═══════ */}
      <Modal open={!!showRenew} onClose={() => setShowRenew(null)}>
        {showRenew && (
          <div className="p-6 space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-white">Renew License</h2>
              <button onClick={() => setShowRenew(null)} className="p-1 text-slate-500 hover:text-white">
                <Icon d={Icons.x} className="w-5 h-5" />
              </button>
            </div>

            <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-4 space-y-2">
              <p className="text-sm font-semibold text-white">{showRenew.hospital_name}</p>
              <div className="flex gap-4 text-xs text-slate-400">
                <span className="font-mono">{showRenew.machine_id}</span>
                <span>Plan: {showRenew.plan}</span>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={showRenew.computed_status} />
                <DaysLeft days={showRenew.days_left} />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Extend by</label>
              <select value={renewDays} onChange={e => setRenewDays(parseInt(e.target.value))}
                className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/50">
                <option value={30}>1 Month</option>
                <option value={90}>3 Months</option>
                <option value={180}>6 Months</option>
                <option value={365}>1 Year</option>
                <option value={730}>2 Years</option>
                <option value={1095}>3 Years</option>
              </select>
            </div>

            <p className="text-xs text-slate-500">
              A new license file will be generated. The old license will be marked as renewed.
              The customer will need to download and upload the new .lic file.
            </p>

            <div className="flex justify-end gap-3 pt-3 border-t border-slate-700/30">
              <button onClick={() => setShowRenew(null)}
                className="px-4 py-2.5 text-sm text-slate-400 hover:text-white rounded-lg transition-colors">
                Cancel
              </button>
              <button onClick={() => renewLicense(showRenew.license_id)}
                className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold rounded-xl transition-colors shadow-lg shadow-emerald-600/20">
                Renew License
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* ═══════ CUSTOMER FORM MODAL ═══════ */}
      <Modal open={showCustForm} onClose={() => setShowCustForm(false)} wide>
        <div className="p-6 space-y-5">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-white">{editingCust ? 'Edit Customer' : 'Add Customer'}</h2>
            <button onClick={() => setShowCustForm(false)} className="p-1 text-slate-500 hover:text-white">
              <Icon d={Icons.x} className="w-5 h-5" />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input label="Hospital Name" required value={custForm.hospital_name}
              onChange={e => setCustForm({...custForm, hospital_name: e.target.value})} placeholder="City Hospital" />
            <Input label="Hospital ID" value={custForm.hospital_id}
              onChange={e => setCustForm({...custForm, hospital_id: e.target.value})} placeholder="HOSP01" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input label="Contact Person" value={custForm.contact_person}
              onChange={e => setCustForm({...custForm, contact_person: e.target.value})} placeholder="Dr. John" />
            <Input label="Phone" value={custForm.phone}
              onChange={e => setCustForm({...custForm, phone: e.target.value})} placeholder="9876543210" />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input label="Email" value={custForm.email}
              onChange={e => setCustForm({...custForm, email: e.target.value})} placeholder="hospital@email.com" />
            <Input label="Machine ID" value={custForm.machine_id}
              onChange={e => setCustForm({...custForm, machine_id: e.target.value})} placeholder="CA86-C087-6261" />
          </div>
          <Input label="Address" value={custForm.address}
            onChange={e => setCustForm({...custForm, address: e.target.value})} placeholder="Full address" />
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Notes</label>
            <textarea value={custForm.notes} onChange={e => setCustForm({...custForm, notes: e.target.value})} rows={2}
              placeholder="Optional notes..."
              className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50 resize-none" />
          </div>
          <div className="flex justify-end gap-3 pt-3 border-t border-slate-700/30">
            <button onClick={() => setShowCustForm(false)} className="px-4 py-2.5 text-sm text-slate-400 hover:text-white rounded-lg">Cancel</button>
            <button onClick={saveCust} disabled={saving || !custForm.hospital_name}
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-sm font-semibold rounded-xl shadow-lg shadow-blue-600/20">
              {saving ? 'Saving...' : editingCust ? 'Update' : 'Add Customer'}
            </button>
          </div>
        </div>
      </Modal>

      {/* ═══════ PAYMENT FORM MODAL ═══════ */}
      <Modal open={showPayForm} onClose={() => setShowPayForm(false)}>
        <div className="p-6 space-y-5">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-white">Record Payment</h2>
            <button onClick={() => setShowPayForm(false)} className="p-1 text-slate-500 hover:text-white">
              <Icon d={Icons.x} className="w-5 h-5" />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Payment Type</label>
              <select value={payForm.payment_type} onChange={e => setPayForm({...payForm, payment_type: e.target.value})}
                className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/50">
                <option value="license">License Fee</option>
                <option value="renewal">Renewal Fee</option>
                <option value="support">Support Fee</option>
                <option value="setup">Setup Fee</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Payment Mode</label>
              <select value={payForm.payment_mode} onChange={e => setPayForm({...payForm, payment_mode: e.target.value})}
                className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/50">
                <option value="cash">Cash</option>
                <option value="upi">UPI</option>
                <option value="bank_transfer">Bank Transfer</option>
                <option value="card">Card</option>
                <option value="cheque">Cheque</option>
                <option value="online">Online</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input label="Amount" required type="number" value={payForm.amount}
              onChange={e => setPayForm({...payForm, amount: e.target.value})} placeholder="0.00" />
            <Input label="Invoice Number" value={payForm.invoice_number}
              onChange={e => setPayForm({...payForm, invoice_number: e.target.value})} placeholder="INV-001" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Description</label>
            <textarea value={payForm.description} onChange={e => setPayForm({...payForm, description: e.target.value})} rows={2}
              placeholder="Payment description..."
              className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50 resize-none" />
          </div>
          <div className="flex justify-end gap-3 pt-3 border-t border-slate-700/30">
            <button onClick={() => setShowPayForm(false)} className="px-4 py-2.5 text-sm text-slate-400 hover:text-white rounded-lg">Cancel</button>
            <button onClick={recordPayment} disabled={saving || !payForm.amount}
              className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm font-semibold rounded-xl shadow-lg shadow-emerald-600/20">
              {saving ? 'Recording...' : 'Record Payment'}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default App;
