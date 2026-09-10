import React, { useState, useEffect, useCallback } from 'react';
import ktLogo from './assets/Final Logo KT (1).jpg';

const API = '/api';
const AUTH_KEY = 'kt_license_manager_auth';

function loadStoredAuth() {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.token || !parsed?.user) return null;
    return parsed;
  } catch {
    return null;
  }
}

async function apiFetch(path, options = {}, token) {
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  const r = await fetch(`${API}${path}`, { ...options, headers });
  if (r.status === 401) {
    const err = new Error('Unauthorized');
    err.status = 401;
    throw err;
  }
  return r;
}

const SUPPORT_STATUS_OPTIONS = [
  { value: 'open', label: 'Open' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'closed', label: 'Closed' },
];

const EMPTY_SUPPORT_FORM = {
  operator_name: '',
  cell_no: '',
  problem: '',
};

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
  key: "M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z",
  upload: "M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12",
  users: "M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z",
  support: "M18.364 5.636l-3.536 3.536m0 5.656l3.536 3.536M9.172 9.172L5.636 5.636m3.536 9.192l-3.536 3.536M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-5 0a4 4 0 11-8 0 4 4 0 018 0z",
  logout: "M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1",
};

/* ─── Reusable Components (defined outside App to prevent re-mount on re-render) ─── */

const StatusBadge = ({ status }) => {
  const statusConfig = {
    active: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', dot: 'bg-emerald-400', label: 'Active' },
    expiring_soon: { bg: 'bg-amber-500/10', text: 'text-amber-400', dot: 'bg-amber-400', label: 'Expiring' },
    expired: { bg: 'bg-red-500/10', text: 'text-red-400', dot: 'bg-red-400', label: 'Expired' },
    renewed: { bg: 'bg-slate-500/10', text: 'text-slate-400', dot: 'bg-slate-500', label: 'Renewed' },
  };
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

const FEATURE_LABELS = {
  physiotherapy: 'Physiotherapy',
  customisation: 'Customisation',
};

const FeatureTag = ({ name }) => (
  <span className="px-1.5 py-0.5 bg-slate-700/50 text-slate-300 rounded text-[10px] font-medium capitalize tracking-wide">
    {FEATURE_LABELS[name] || name}
  </span>
);

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

const GSTIN_RE = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;

const EMPTY_LICENSE_FORM = {
  customer_id: '',
  hospital_id: '', hospital_name: '', machine_id: '', plan: 'standard',
  max_users: 50, months: 12, days: 0,
  features: ['outpatient', 'lab', 'ehr', 'admin', 'billing', 'physiotherapy'],
  modules: [], notes: '',
  seller_id: '', seller_name: '', seller_address: '', seller_phone: '',
  gdrive_backup_enabled: false,
};

const EMPTY_CUST_FORM = {
  hospital_name: '', hospital_id: '', contact_person: '', phone: '',
  email: '', address: '', gst_number: '', machine_id: '', notes: '',
};

const LICENSE_STEPS = [
  { id: 'hospital', label: 'Hospital' },
  { id: 'plan', label: 'Plan' },
  { id: 'modules', label: 'Modules' },
  { id: 'options', label: 'Options' },
];

const CUSTOMISATION_ADDON = 'customisation';

function withFeature(features, key, on) {
  const next = (features || []).filter((f) => f !== key);
  if (on) next.push(key);
  return next;
}

function apiErrorMessage(payload, fallback) {
  const d = payload?.detail;
  if (typeof d === 'string' && d) return d;
  if (Array.isArray(d)) {
    const parts = d.map((x) => (typeof x === 'string' ? x : x.msg || x.message)).filter(Boolean);
    if (parts.length) return parts.join('; ');
  }
  return fallback;
}

function filenameFromDisposition(disposition, fallback) {
  if (!disposition) return fallback;
  const star = disposition.match(/filename\*=UTF-8''([^;]+)/i);
  if (star) {
    try { return decodeURIComponent(star[1]); } catch { return star[1]; }
  }
  const quoted = disposition.match(/filename="([^"]+)"/i);
  if (quoted) return quoted[1];
  const plain = disposition.match(/filename=([^;]+)/i);
  return plain ? plain[1].trim().replace(/^["']|["']$/g, '') : fallback;
}

const Stepper = ({ steps, current, onSelect }) => (
  <ol className="flex items-center gap-1.5">
    {steps.map((step, i) => {
      const done = i < current;
      const active = i === current;
      const clickable = done && typeof onSelect === 'function';
      return (
        <li key={step.id} className="flex items-center gap-1.5 min-w-0 flex-1">
          <div className={`flex items-center gap-2 min-w-0 ${i < steps.length - 1 ? 'flex-1' : ''}`}>
            <button type="button" disabled={!clickable} onClick={() => clickable && onSelect(i)}
              className={`shrink-0 w-6 h-6 rounded-full text-[11px] font-bold flex items-center justify-center ${
                done ? 'bg-emerald-500/20 text-emerald-400' : active ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-500'
              } ${clickable ? 'hover:ring-1 hover:ring-emerald-400/40' : ''}`}>
              {done ? '✓' : i + 1}
            </button>
            <span className={`text-[11px] font-medium truncate ${
              active ? 'text-white' : done ? 'text-emerald-400' : 'text-slate-500'
            }`}>{step.label}</span>
            {i < steps.length - 1 && (
              <span className={`hidden sm:block flex-1 h-px ${done ? 'bg-emerald-500/30' : 'bg-slate-800'}`} />
            )}
          </div>
        </li>
      );
    })}
  </ol>
);

const Input = ({ label, required, hint, ...props }) => (
  <div>
    <label className="block text-xs font-medium text-slate-400 mb-1.5">
      {label} {required && <span className="text-amber-400">*</span>}
    </label>
    <input {...props}
      className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20 transition-colors" />
    {hint && <p className="text-[10px] text-slate-500 mt-1">{hint}</p>}
  </div>
);

const ToggleRow = ({ checked, onChange, title, description }) => (
  <button type="button" onClick={() => onChange(!checked)}
    className={`w-full flex items-center justify-between gap-4 rounded-xl border px-4 py-3 text-left transition-colors ${
      checked ? 'bg-amber-500/10 border-amber-500/30' : 'bg-slate-800/30 border-slate-700/40 hover:border-slate-600'
    }`}>
    <div className="min-w-0">
      <p className={`text-sm font-semibold ${checked ? 'text-amber-300' : 'text-white'}`}>{title}</p>
      {description && <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">{description}</p>}
    </div>
    <span className={`relative shrink-0 w-11 h-6 rounded-full transition-colors ${checked ? 'bg-amber-500' : 'bg-slate-600'}`}
      role="switch" aria-checked={checked}>
      <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-5' : ''}`} />
    </span>
  </button>
);

function App() {
  const [auth, setAuth] = useState(() => loadStoredAuth());
  const token = auth?.token || null;
  const currentUser = auth?.user || null;
  const isAdmin = currentUser?.role === 'admin';
  const isAgent = currentUser?.role === 'support_agent';

  const [loginForm, setLoginForm] = useState({ username: '', password: '' });
  const [loginError, setLoginError] = useState('');
  const [loggingIn, setLoggingIn] = useState(false);

  const [page, setPage] = useState('dashboard');
  const [dash, setDash] = useState(null);
  const [licenses, setLicenses] = useState([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [showForm, setShowForm] = useState(false);
  const [formStep, setFormStep] = useState(0);
  const [processingRebind, setProcessingRebind] = useState(false);
  const [showRenew, setShowRenew] = useState(null);
  const [renewForm, setRenewForm] = useState({ months: 12, days: 0, plan: 'standard', max_users: 50, features: [], gdrive_backup_enabled: false, seller_id: '' });
  const [customDuration, setCustomDuration] = useState(false);
  const [renewCustomDuration, setRenewCustomDuration] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_LICENSE_FORM });
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  const [gdriveSettings, setGdriveSettings] = useState(null);

  // Customer state
  const [customers, setCustomers] = useState([]);
  const [custSearch, setCustSearch] = useState('');
  const [showCustForm, setShowCustForm] = useState(false);
  const [editingCust, setEditingCust] = useState(null);
  const [custForm, setCustForm] = useState({ ...EMPTY_CUST_FORM });

  // Seller state
  const [sellers, setSellers] = useState([]);
  const [showSellerForm, setShowSellerForm] = useState(false);
  const [editingSeller, setEditingSeller] = useState(null);
  const [sellerForm, setSellerForm] = useState({ name: '', address: '', phone: '' });
  const [selectedCust, setSelectedCust] = useState(null);
  const [custDetail, setCustDetail] = useState(null);
  const [showPayForm, setShowPayForm] = useState(false);
  const [payForm, setPayForm] = useState({ payment_type: 'license', payment_mode: 'cash', amount: '', invoice_number: '', description: '' });

  // Support log state
  const [supportLogs, setSupportLogs] = useState([]);
  const [allSupportLogs, setAllSupportLogs] = useState([]);
  const [supportSearch, setSupportSearch] = useState('');
  const [supportStatusFilter, setSupportStatusFilter] = useState('active');
  const [supportAgentFilter, setSupportAgentFilter] = useState('all');
  const [showSupportForm, setShowSupportForm] = useState(false);
  const [editingSupport, setEditingSupport] = useState(null);
  const [supportForm, setSupportForm] = useState({ ...EMPTY_SUPPORT_FORM });
  const [mineOnlyLogs, setMineOnlyLogs] = useState(false);

  // Users (admin)
  const [users, setUsers] = useState([]);
  const [showUserForm, setShowUserForm] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [userForm, setUserForm] = useState({ username: '', password: '', full_name: '', role: 'support_agent' });

  // Key management state
  const [keyStatus, setKeyStatus] = useState(null);

  const handleUnauthorized = useCallback(() => {
    localStorage.removeItem(AUTH_KEY);
    setAuth(null);
    setLoginError('Session expired. Please sign in again.');
  }, []);

  const persistAuth = (next) => {
    localStorage.setItem(AUTH_KEY, JSON.stringify(next));
    setAuth(next);
  };

  const logout = () => {
    localStorage.removeItem(AUTH_KEY);
    setAuth(null);
    setPage('dashboard');
    setSelectedCust(null);
    setCustDetail(null);
  };

  const doLogin = async (e) => {
    e?.preventDefault?.();
    setLoggingIn(true);
    setLoginError('');
    try {
      const r = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(loginForm),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) {
        setLoginError(apiErrorMessage(body, 'Login failed'));
        return;
      }
      persistAuth({ token: body.access_token, user: body.user });
      setLoginForm({ username: '', password: '' });
      setPage(body.user.role === 'support_agent' ? 'customers' : 'dashboard');
    } catch {
      setLoginError('Could not reach server');
    } finally {
      setLoggingIn(false);
    }
  };

  const fetchDash = useCallback(async () => {
    if (!token) return;
    try {
      const r = await apiFetch('/dashboard', {}, token);
      if (r.status === 401) return handleUnauthorized();
      setDash(await r.json());
    } catch (e) { if (e.status === 401) handleUnauthorized(); }
  }, [token, handleUnauthorized]);

  const fetchLicenses = useCallback(async () => {
    if (!token || currentUser?.role !== 'admin') return;
    try {
      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (statusFilter !== 'all') params.set('status', statusFilter);
      const r = await apiFetch(`/licenses?${params}`, {}, token);
      if (r.status === 401) return handleUnauthorized();
      setLicenses(await r.json());
    } catch (e) { if (e.status === 401) handleUnauthorized(); }
  }, [token, currentUser?.role, search, statusFilter, handleUnauthorized]);

  const fetchCustomers = useCallback(async () => {
    if (!token) return;
    try {
      const params = custSearch ? `?search=${encodeURIComponent(custSearch)}` : '';
      const r = await apiFetch(`/customers${params}`, {}, token);
      if (r.status === 401) return handleUnauthorized();
      setCustomers(await r.json());
    } catch (e) { if (e.status === 401) handleUnauthorized(); }
  }, [token, custSearch, handleUnauthorized]);

  const fetchCustDetail = async (id) => {
    if (!token) return;
    try {
      const r = await apiFetch(`/customers/${id}`, {}, token);
      if (r.status === 401) return handleUnauthorized();
      setCustDetail(await r.json());
    } catch (e) { if (e.status === 401) handleUnauthorized(); }
  };

  const fetchSupportLogs = async (customerId, mineOnly = mineOnlyLogs) => {
    if (!token || !customerId) return;
    try {
      const q = mineOnly ? '?mine_only=true' : '';
      const r = await apiFetch(`/customers/${customerId}/support-logs${q}`, {}, token);
      if (r.status === 401) return handleUnauthorized();
      setSupportLogs(await r.json());
    } catch (e) { if (e.status === 401) handleUnauthorized(); }
  };

  const fetchAllSupportLogs = useCallback(async () => {
    if (!token) return;
    try {
      const params = new URLSearchParams();
      if (supportStatusFilter && supportStatusFilter !== 'all') params.set('status', supportStatusFilter);
      if (supportSearch.trim()) params.set('search', supportSearch.trim());
      if (isAdmin && supportAgentFilter !== 'all') params.set('assistant_user_id', supportAgentFilter);
      if (!isAdmin) params.set('mine_only', 'true');
      const q = params.toString() ? `?${params}` : '';
      const r = await apiFetch(`/support-logs${q}`, {}, token);
      if (r.status === 401) return handleUnauthorized();
      setAllSupportLogs(await r.json());
    } catch (e) { if (e.status === 401) handleUnauthorized(); }
  }, [token, supportStatusFilter, supportSearch, supportAgentFilter, isAdmin, handleUnauthorized]);

  const fetchUsers = useCallback(async (all = false) => {
    if (!token) return;
    try {
      const q = all && currentUser?.role === 'admin' ? '?active_only=false' : '';
      const r = await apiFetch(`/users${q}`, {}, token);
      if (r.status === 401) return handleUnauthorized();
      setUsers(await r.json());
    } catch (e) { if (e.status === 401) handleUnauthorized(); }
  }, [token, currentUser?.role, handleUnauthorized]);

  const fetchKeyStatus = useCallback(async () => {
    if (!token || currentUser?.role !== 'admin') return;
    try {
      const r = await apiFetch('/keys/status', {}, token);
      if (r.status === 401) return handleUnauthorized();
      setKeyStatus(await r.json());
    } catch (e) { if (e.status === 401) handleUnauthorized(); }
  }, [token, currentUser?.role, handleUnauthorized]);

  const fetchSellers = useCallback(async () => {
    if (!token || currentUser?.role !== 'admin') return;
    try {
      const r = await apiFetch('/sellers', {}, token);
      if (r.status === 401) return handleUnauthorized();
      setSellers(await r.json());
    } catch (e) { if (e.status === 401) handleUnauthorized(); }
  }, [token, currentUser?.role, handleUnauthorized]);

  const fetchGdriveSettings = async () => {
    if (!token || currentUser?.role !== 'admin') return;
    try {
      const r = await apiFetch('/settings/gdrive', {}, token);
      if (r.status === 401) return handleUnauthorized();
      setGdriveSettings(await r.json());
    } catch (e) { if (e.status === 401) handleUnauthorized(); }
  };

  useEffect(() => {
    if (!token) return;
    fetchDash();
    if (isAdmin) fetchGdriveSettings();
  }, [token, isAdmin, fetchDash]);
  useEffect(() => { if (token && isAdmin) fetchLicenses(); }, [fetchLicenses, token, isAdmin]);
  useEffect(() => { if (token) fetchCustomers(); }, [fetchCustomers, token]);
  useEffect(() => { if (token && isAdmin) fetchKeyStatus(); }, [fetchKeyStatus, token, isAdmin]);
  useEffect(() => { if (token && isAdmin) fetchSellers(); }, [fetchSellers, token, isAdmin]);
  useEffect(() => { if (token) fetchUsers(isAdmin); }, [fetchUsers, token, isAdmin]);
  useEffect(() => {
    if (selectedCust && token) fetchSupportLogs(selectedCust, mineOnlyLogs);
  }, [selectedCust, token, mineOnlyLogs]);

  useEffect(() => {
    if (token && page === 'support') fetchAllSupportLogs();
  }, [token, page, fetchAllSupportLogs]);

  // Redirect agents away from admin-only pages
  useEffect(() => {
    if (isAgent && ['licenses', 'sellers', 'settings', 'users'].includes(page)) {
      setPage('customers');
    }
  }, [isAgent, page]);

  const showMessage = (text, type = 'success') => {
    setMsg({ text, type });
    setTimeout(() => setMsg(null), 4000);
  };

  const closeGenerateForm = () => {
    setShowForm(false);
    setFormStep(0);
    setCustomDuration(false);
  };

  const openGenerateForm = (prefill = {}) => {
    setForm({ ...EMPTY_LICENSE_FORM, ...prefill });
    setFormStep(0);
    setCustomDuration(false);
    setShowForm(true);
  };

  const generateStepError = (step = formStep) => {
    if (step === 0) {
      if (!form.hospital_id?.trim()) return 'Hospital ID is required';
      if (!form.hospital_name?.trim()) return 'Hospital name is required';
      if (!form.machine_id?.trim()) return 'Machine ID is required';
    }
    if (step === 1) {
      if ((form.months || 0) <= 0 && (form.days || 0) <= 0) return 'Validity must be at least 1 day';
    }
    if (step === 2) {
      if (!form.features?.length) return 'Select at least one module';
    }
    return null;
  };

  const nextGenerateStep = () => {
    const err = generateStepError();
    if (err) { showMessage(err, 'error'); return; }
    setFormStep((s) => Math.min(s + 1, LICENSE_STEPS.length - 1));
  };

  const applyCustomerToLicenseForm = (customerId) => {
    if (!customerId) {
      setForm((prev) => ({ ...prev, customer_id: '' }));
      return;
    }
    const c = customers.find((x) => String(x.id) === String(customerId));
    if (!c) {
      setForm((prev) => ({ ...prev, customer_id: customerId }));
      return;
    }
    setForm((prev) => ({
      ...prev,
      customer_id: c.id,
      hospital_id: c.hospital_id || '',
      hospital_name: c.hospital_name || '',
      machine_id: c.machine_id || '',
    }));
  };

  const createLicense = async () => {
    const err = generateStepError(0) || generateStepError(1) || generateStepError(2);
    if (err) { showMessage(err, 'error'); return; }
    setSaving(true);
    try {
      const payload = { ...form };
      payload.hospital_id = payload.hospital_id.trim();
      payload.hospital_name = payload.hospital_name.trim();
      payload.machine_id = payload.machine_id.trim();
      if (payload.customer_id === '' || payload.customer_id == null) {
        payload.customer_id = null;
      } else {
        payload.customer_id = Number(payload.customer_id);
      }
      // Build seller object if name is provided
      if (payload.seller_name) {
        payload.seller = { name: payload.seller_name, address: payload.seller_address || null, phone: payload.seller_phone || null };
      }
      delete payload.seller_name; delete payload.seller_address; delete payload.seller_phone; delete payload.seller_id;
      const r = await apiFetch('/licenses', {
        method: 'POST', body: JSON.stringify(payload)
      }, token);
      if (r.ok) {
        const linked = !!payload.customer_id;
        showMessage(linked
          ? 'License generated — download it from this customer’s licenses'
          : 'License generated successfully');
        closeGenerateForm();
        setForm({ ...EMPTY_LICENSE_FORM });
        fetchLicenses(); fetchDash();
        const custId = payload.customer_id || selectedCust;
        if (custId) fetchCustDetail(custId);
      } else {
        const e = await r.json();
        showMessage(apiErrorMessage(e, 'Generation failed'), 'error');
      }
    } catch { showMessage('Failed to create license', 'error'); }
    finally { setSaving(false); }
  };

  const renewLicense = async (licenseId) => {
    if ((renewForm.months || 0) <= 0 && (renewForm.days || 0) <= 0) { showMessage('Validity must be at least 1 day', 'error'); return; }
    const payload = { ...renewForm };
    // Build seller if selected
    if (payload.seller_id) {
      const s = sellers.find(s => String(s.id) === payload.seller_id);
      if (s) payload.seller = { name: s.name, address: s.address || null, phone: s.phone || null };
    }
    delete payload.seller_id;
    const r = await apiFetch(`/licenses/${licenseId}/renew`, {
      method: 'POST', body: JSON.stringify(payload)
    }, token);
    if (r.ok) {
      showMessage('License renewed — new file ready for download');
      setShowRenew(null);
      fetchLicenses(); fetchDash();
      if (selectedCust) fetchCustDetail(selectedCust);
    } else {
      const e = await r.json();
      showMessage(e.detail || 'Renewal failed', 'error');
    }
  };

  const processRebind = async (file) => {
    setProcessingRebind(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const r = await apiFetch('/licenses/process-rebind', { method: 'POST', body: fd }, token);
      if (!r.ok) {
        let detail = 'Could not process rebind request';
        try { detail = (await r.json()).detail || detail; } catch {}
        showMessage(typeof detail === 'string' ? detail : 'Could not process rebind request', 'error');
        return;
      }
      // Success — the response is the rebound .lic file. Download it for the vendor to send back.
      const blob = await r.blob();
      const disposition = r.headers.get('Content-Disposition') || '';
      const filename = filenameFromDisposition(disposition, 'rebound.lic');
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      showMessage('Rebind processed — new .lic downloaded. Send it to the hospital to upload.');
      fetchLicenses(); fetchDash();
    } catch {
      showMessage('Could not process rebind request', 'error');
    } finally { setProcessingRebind(false); }
  };

  const downloadLicense = async (licenseId) => {
    try {
      const r = await apiFetch(`/licenses/${licenseId}/download`, {}, token);
      if (!r.ok) { showMessage('Failed to download license', 'error'); return; }
      const blob = await r.blob();
      const disposition = r.headers.get('Content-Disposition') || '';
      const filename = filenameFromDisposition(disposition, `${licenseId}.lic`);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      showMessage('Failed to download license', 'error');
    }
  };

  const deleteLicense = async (licenseId) => {
    if (!window.confirm('Delete this license record permanently?')) return;
    await apiFetch(`/licenses/${licenseId}`, { method: 'DELETE' }, token);
    showMessage('License record deleted');
    fetchLicenses(); fetchDash();
  };

  // Customer functions
  const saveCust = async ({ generateAfter = false } = {}) => {
    if (!custForm.hospital_name) return;
    if (custForm.gst_number && !GSTIN_RE.test(custForm.gst_number)) {
      showMessage('Invalid GST number — expected 15-char GSTIN (e.g. 22AAAAA0000A1Z5)', 'error');
      return;
    }
    setSaving(true);
    const isEdit = !!editingCust;
    try {
      const path = isEdit ? `/customers/${editingCust.id}` : '/customers';
      const method = isEdit ? 'PUT' : 'POST';
      const savedForm = { ...custForm };
      const r = await apiFetch(path, { method, body: JSON.stringify(custForm) }, token);
      if (r.ok) {
        const body = await r.json().catch(() => ({}));
        setShowCustForm(false); setEditingCust(null);
        setCustForm({ ...EMPTY_CUST_FORM });
        fetchCustomers(); fetchDash();

        if (!isEdit && generateAfter && body.id) {
          showMessage('Customer created — finish the license wizard');
          const newCust = {
            id: body.id,
            hospital_name: savedForm.hospital_name,
            hospital_id: savedForm.hospital_id || null,
            contact_person: savedForm.contact_person || null,
            phone: savedForm.phone || null,
            email: savedForm.email || null,
            address: savedForm.address || null,
            gst_number: savedForm.gst_number || null,
            machine_id: savedForm.machine_id || null,
            notes: savedForm.notes || null,
            is_active: 1,
          };
          setCustomers((prev) => [newCust, ...prev.filter((c) => c.id !== body.id)]);
          setSelectedCust(body.id);
          fetchCustDetail(body.id);
          openGenerateForm({
            customer_id: body.id,
            hospital_id: savedForm.hospital_id || '',
            hospital_name: savedForm.hospital_name,
            machine_id: savedForm.machine_id || '',
          });
        } else {
          showMessage(isEdit ? 'Customer updated' : 'Customer created');
          if (selectedCust) fetchCustDetail(selectedCust);
        }
      } else { const e = await r.json(); showMessage(apiErrorMessage(e, 'Failed'), 'error'); }
    } catch { showMessage('Failed', 'error'); }
    finally { setSaving(false); }
  };

  const openEditCust = (c) => {
    setEditingCust(c);
    setCustForm({ hospital_name: c.hospital_name, hospital_id: c.hospital_id || '', contact_person: c.contact_person || '', phone: c.phone || '', email: c.email || '', address: c.address || '', gst_number: c.gst_number || '', machine_id: c.machine_id || '', notes: c.notes || '' });
    setShowCustForm(true);
  };

  const deleteCust = async (id) => {
    if (!window.confirm('Delete this customer and all related records?')) return;
    await apiFetch(`/customers/${id}`, { method: 'DELETE' }, token);
    showMessage('Customer deleted');
    fetchCustomers(); fetchDash();
    if (selectedCust === id) { setSelectedCust(null); setCustDetail(null); }
  };

  const recordPayment = async () => {
    if (!payForm.amount || !selectedCust) return;
    setSaving(true);
    try {
      const r = await apiFetch('/payments', {
        method: 'POST',
        body: JSON.stringify({ ...payForm, customer_id: selectedCust, amount: parseFloat(payForm.amount) })
      }, token);
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
    await apiFetch(`/payments/${payId}`, { method: 'DELETE' }, token);
    showMessage('Payment deleted');
    fetchCustDetail(selectedCust);
  };

  const formatDate = (d) => {
    if (!d) return '—';
    try { return new Date(d).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' }); }
    catch { return d; }
  };

  const saveSeller = async () => {
    if (!sellerForm.name) return;
    try {
      const path = editingSeller ? `/sellers/${editingSeller.id}` : '/sellers';
      const method = editingSeller ? 'PUT' : 'POST';
      const r = await apiFetch(path, { method, body: JSON.stringify(sellerForm) }, token);
      if (r.ok) {
        showMessage(editingSeller ? 'Seller updated' : 'Seller created');
        setShowSellerForm(false); setEditingSeller(null);
        setSellerForm({ name: '', address: '', phone: '' });
        fetchSellers();
      } else { const e = await r.json(); showMessage(e.detail || 'Failed', 'error'); }
    } catch { showMessage('Failed to save seller', 'error'); }
  };

  const deleteSeller = async (id) => {
    if (!window.confirm('Deactivate this seller?')) return;
    try {
      await apiFetch(`/sellers/${id}`, { method: 'DELETE' }, token);
      showMessage('Seller deactivated');
      fetchSellers();
    } catch { showMessage('Failed', 'error'); }
  };

  const formatDateTime = (d) => {
    if (!d) return '—';
    try {
      return new Date(d).toLocaleString('en-IN', {
        day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
      });
    } catch { return d; }
  };

  const openSupportForm = (log = null) => {
    if (log) {
      setEditingSupport(log);
      setSupportForm({
        operator_name: log.operator_name || '',
        cell_no: log.cell_no || '',
        problem: log.problem || '',
      });
    } else {
      setEditingSupport(null);
      setSupportForm({ ...EMPTY_SUPPORT_FORM });
    }
    setShowSupportForm(true);
  };

  const saveSupportLog = async () => {
    if (!supportForm.operator_name?.trim() || !supportForm.cell_no?.trim() || !supportForm.problem?.trim() || !selectedCust) {
      showMessage('Caller name, phone number, and problem are required', 'error');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        operator_name: supportForm.operator_name.trim(),
        cell_no: supportForm.cell_no.trim(),
        problem: supportForm.problem.trim(),
      };
      if (!editingSupport) {
        payload.status = 'open';
        payload.assistant_user_id = currentUser?.id;
      }
      const path = editingSupport
        ? `/support-logs/${editingSupport.id}`
        : `/customers/${selectedCust}/support-logs`;
      const method = editingSupport ? 'PUT' : 'POST';
      const r = await apiFetch(path, { method, body: JSON.stringify(payload) }, token);
      if (r.ok) {
        showMessage(editingSupport ? 'Support log updated' : 'Support ticket opened — received time recorded');
        setShowSupportForm(false);
        setEditingSupport(null);
        setSupportForm({ ...EMPTY_SUPPORT_FORM });
        if (selectedCust) {
          fetchSupportLogs(selectedCust, mineOnlyLogs);
          fetchCustDetail(selectedCust);
        }
        fetchDash();
        if (page === 'support') fetchAllSupportLogs();
      } else {
        const e = await r.json();
        showMessage(apiErrorMessage(e, 'Failed to save support log'), 'error');
      }
    } catch (e) {
      if (e.status === 401) handleUnauthorized();
      else showMessage('Failed to save support log', 'error');
    } finally { setSaving(false); }
  };

  const updateSupportStatus = async (log, nextStatus) => {
    if (!log || log.status === nextStatus) return;
    const canEdit = isAdmin || log.created_by_user_id === currentUser?.id || log.assistant_user_id === currentUser?.id;
    if (!canEdit) {
      showMessage('You can only update your own support tickets', 'error');
      return;
    }
    // Optimistic UI
    const patch = (prev) => prev.map((row) => (
      row.id === log.id ? { ...row, status: nextStatus } : row
    ));
    setSupportLogs(patch);
    setAllSupportLogs(patch);
    try {
      const r = await apiFetch(`/support-logs/${log.id}`, {
        method: 'PUT',
        body: JSON.stringify({ status: nextStatus }),
      }, token);
      if (r.ok) {
        const body = await r.json();
        const apply = (prev) => prev.map((row) => (row.id === log.id ? { ...row, ...body.log } : row));
        setSupportLogs(apply);
        setAllSupportLogs(apply);
        if (nextStatus === 'closed') {
          showMessage('Ticket closed — closed time recorded');
        }
        fetchDash();
      } else {
        const e = await r.json();
        showMessage(apiErrorMessage(e, 'Failed to update status'), 'error');
        if (selectedCust) fetchSupportLogs(selectedCust, mineOnlyLogs);
        if (page === 'support') fetchAllSupportLogs();
      }
    } catch (e) {
      if (e.status === 401) handleUnauthorized();
      else showMessage('Failed to update status', 'error');
      if (selectedCust) fetchSupportLogs(selectedCust, mineOnlyLogs);
      if (page === 'support') fetchAllSupportLogs();
    }
  };

  const deleteSupportLog = async (logId) => {
    if (!window.confirm('Delete this support log?')) return;
    try {
      const r = await apiFetch(`/support-logs/${logId}`, { method: 'DELETE' }, token);
      if (r.ok) {
        showMessage('Support log deleted');
        setAllSupportLogs((prev) => prev.filter((row) => row.id !== logId));
        if (selectedCust) {
          fetchSupportLogs(selectedCust, mineOnlyLogs);
          fetchCustDetail(selectedCust);
        }
        fetchDash();
      } else {
        const e = await r.json();
        showMessage(apiErrorMessage(e, 'Delete failed'), 'error');
      }
    } catch (e) {
      if (e.status === 401) handleUnauthorized();
      else showMessage('Delete failed', 'error');
    }
  };

  const saveUser = async () => {
    if (!userForm.full_name?.trim() || (!editingUser && (!userForm.username?.trim() || !userForm.password))) {
      showMessage('Fill required user fields', 'error');
      return;
    }
    setSaving(true);
    try {
      const path = editingUser ? `/users/${editingUser.id}` : '/users';
      const method = editingUser ? 'PUT' : 'POST';
      const payload = editingUser
        ? {
            full_name: userForm.full_name.trim(),
            role: userForm.role,
            ...(userForm.password ? { password: userForm.password } : {}),
          }
        : {
            username: userForm.username.trim(),
            password: userForm.password,
            full_name: userForm.full_name.trim(),
            role: userForm.role,
          };
      const r = await apiFetch(path, { method, body: JSON.stringify(payload) }, token);
      if (r.ok) {
        showMessage(editingUser ? 'User updated' : 'User created');
        setShowUserForm(false);
        setEditingUser(null);
        setUserForm({ username: '', password: '', full_name: '', role: 'support_agent' });
        fetchUsers(true);
      } else {
        const e = await r.json();
        showMessage(apiErrorMessage(e, 'Failed'), 'error');
      }
    } catch { showMessage('Failed to save user', 'error'); }
    finally { setSaving(false); }
  };

  const allModules = ['outpatient', 'inpatient', 'lab', 'pharmacy', 'physiotherapy', 'ehr', 'admin', 'billing'];

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: Icons.dashboard, roles: ['admin', 'support_agent'] },
    { id: 'support', label: 'Support', icon: Icons.support, roles: ['admin', 'support_agent'] },
    { id: 'licenses', label: 'Licenses', icon: Icons.license, roles: ['admin'] },
    { id: 'customers', label: 'Customers', icon: "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z", roles: ['admin', 'support_agent'] },
    { id: 'sellers', label: 'Sellers', icon: "M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4", roles: ['admin'] },
    { id: 'users', label: 'Users', icon: Icons.users, roles: ['admin'] },
    { id: 'settings', label: 'Key Settings', icon: Icons.key, roles: ['admin'] },
  ].filter((item) => item.roles.includes(currentUser?.role));

  if (!auth) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6">
        <div className="w-full max-w-md bg-slate-925 border border-slate-800/50 rounded-2xl p-8 shadow-2xl">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-11 h-11 bg-white rounded-lg overflow-hidden">
              <img src={ktLogo} alt="KT Health" className="w-full h-full object-contain" />
            </div>
            <div>
              <h1 className="text-lg font-bold text-white">KT License Manager</h1>
              <p className="text-xs text-slate-500 uppercase tracking-widest">Sign in</p>
            </div>
          </div>
          <form onSubmit={doLogin} className="space-y-4">
            <Input label="Username" required value={loginForm.username}
              onChange={(e) => setLoginForm({ ...loginForm, username: e.target.value })}
              autoComplete="username" placeholder="admin" />
            <Input label="Password" required type="password" value={loginForm.password}
              onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
              autoComplete="current-password" placeholder="••••••••" />
            {loginError && <p className="text-sm text-red-400">{loginError}</p>}
            <button type="submit" disabled={loggingIn}
              className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-xl text-sm font-semibold">
              {loggingIn ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
          <p className="text-[11px] text-slate-600 mt-6 text-center">
            Default admin: <span className="text-slate-400">admin / admin123</span> — change after first login
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-slate-950">

      {/* ─── Sidebar ─── */}
      <aside className="w-60 bg-slate-925 border-r border-slate-800/50 flex flex-col">
        <div className="p-5 border-b border-slate-800/50">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-white rounded-lg flex items-center justify-center overflow-hidden">
              <img src={ktLogo} alt="KT Health" className="w-full h-full object-contain" />
            </div>
            <div>
              <h1 className="text-sm font-bold text-white tracking-tight">KT License</h1>
              <p className="text-[10px] text-slate-500 font-medium tracking-widest uppercase">Manager</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-3 space-y-1">
          {navItems.map(item => (
            <button key={item.id} onClick={() => { setPage(item.id); if (item.id !== 'customers') { setSelectedCust(null); setCustDetail(null); } }}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] font-medium transition-all duration-150
                ${page === item.id
                  ? 'bg-blue-600/15 text-blue-400 shadow-sm shadow-blue-500/5'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800/50'}`}>
              <Icon d={item.icon} className="w-[18px] h-[18px]" />
              {item.label}
            </button>
          ))}
        </nav>

        <div className="p-4 border-t border-slate-800/50 space-y-3">
          <div className="px-1">
            <p className="text-xs font-medium text-white truncate">{currentUser?.full_name}</p>
            <p className="text-[10px] text-slate-500 capitalize">{currentUser?.role?.replace('_', ' ')}</p>
          </div>
          <button onClick={logout}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-[12px] text-slate-400 hover:text-white hover:bg-slate-800/50">
            <Icon d={Icons.logout} className="w-4 h-4" /> Sign out
          </button>
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
                <p className="text-sm text-slate-500 mt-1">
                  {isAdmin ? 'License overview, revenue, and live support activity' : 'Customers and your support activity'}
                </p>
              </div>

              {/* Stats */}
              {dash && (
                <div className={`grid gap-4 ${isAdmin ? 'grid-cols-2 md:grid-cols-4 xl:grid-cols-7' : 'grid-cols-2 md:grid-cols-4'}`}>
                  {(isAdmin ? [
                    { label: 'Customers', value: dash.total_customers || 0, color: 'from-blue-600/20 to-blue-700/10', accent: 'text-blue-400' },
                    { label: 'Total Licenses', value: dash.total, color: 'from-slate-600 to-slate-700', accent: 'text-white' },
                    { label: 'Active', value: dash.active, color: 'from-emerald-600/20 to-emerald-700/10', accent: 'text-emerald-400' },
                    { label: 'Expiring Soon', value: dash.expiring_soon, color: 'from-amber-600/20 to-amber-700/10', accent: 'text-amber-400' },
                    { label: 'Expired', value: dash.expired, color: 'from-red-600/20 to-red-700/10', accent: 'text-red-400' },
                    { label: 'Open Support', value: dash.open_support || 0, color: 'from-violet-600/20 to-violet-700/10', accent: 'text-violet-300', onClick: () => setPage('support') },
                    { label: 'Revenue', value: `₹${(dash.total_revenue || 0).toLocaleString('en-IN')}`, color: 'from-cyan-600/20 to-cyan-700/10', accent: 'text-cyan-400' },
                  ] : [
                    { label: 'Customers', value: dash.total_customers || 0, color: 'from-blue-600/20 to-blue-700/10', accent: 'text-blue-400' },
                    { label: 'My Support Logs', value: dash.my_support_logs || 0, color: 'from-violet-600/20 to-violet-700/10', accent: 'text-violet-300', onClick: () => setPage('support') },
                    { label: 'My Open Tickets', value: dash.my_open_support || 0, color: 'from-amber-600/20 to-amber-700/10', accent: 'text-amber-400', onClick: () => setPage('support') },
                    { label: 'In Progress', value: dash.support_in_progress || 0, color: 'from-blue-600/20 to-blue-700/10', accent: 'text-blue-400', onClick: () => setPage('support') },
                  ]).map((c, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={c.onClick}
                      disabled={!c.onClick}
                      className={`bg-gradient-to-br ${c.color} rounded-xl p-5 stat-glow text-left ${c.onClick ? 'hover:ring-1 hover:ring-white/10 cursor-pointer' : 'cursor-default'}`}
                      style={{ animationDelay: `${i * 0.05}s` }}>
                      <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">{c.label}</p>
                      <p className={`text-3xl xl:text-4xl font-bold mt-2 font-mono ${c.accent}`}>{c.value}</p>
                    </button>
                  ))}
                </div>
              )}

              {/* Recent Support — both roles */}
              {dash?.recent_support?.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">
                      {isAdmin ? 'Recent Support Activity' : 'My Recent Tickets'}
                    </h3>
                    <button onClick={() => setPage('support')} className="text-xs text-blue-400 hover:text-blue-300">
                      Support dashboard →
                    </button>
                  </div>
                  <div className="bg-slate-925 border border-slate-800/50 rounded-xl overflow-hidden">
                    {dash.recent_support.slice(0, 6).map((log, i) => (
                      <button
                        key={log.id}
                        type="button"
                        onClick={() => {
                          setSelectedCust(log.customer_id);
                          setPage('customers');
                          fetchCustDetail(log.customer_id);
                        }}
                        className={`w-full flex items-center justify-between gap-4 px-5 py-3.5 text-left hover:bg-slate-800/30 ${
                          i < Math.min(dash.recent_support.length, 6) - 1 ? 'border-b border-slate-800/30' : ''
                        }`}
                      >
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-white truncate">{log.hospital_name || 'Customer'}</p>
                          <p className="text-xs text-slate-500 truncate mt-0.5">{log.problem}</p>
                        </div>
                        <div className="flex items-center gap-3 shrink-0">
                          <span className="text-[11px] text-slate-500 hidden sm:inline">{formatDateTime(log.start_time)}</span>
                          <span className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                            log.status === 'open' ? 'bg-amber-500/10 text-amber-400'
                              : log.status === 'in_progress' ? 'bg-blue-500/10 text-blue-400'
                              : log.status === 'resolved' ? 'bg-emerald-500/10 text-emerald-400'
                              : 'bg-slate-500/10 text-slate-400'
                          }`}>
                            {SUPPORT_STATUS_OPTIONS.find(s => s.value === log.status)?.label || log.status}
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Recent Licenses — admin only */}
              {isAdmin && (
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
              )}

              {isAgent && (
                <div className="bg-slate-925 border border-slate-800/50 rounded-xl p-6">
                  <p className="text-sm text-slate-300">Open a customer to log support calls, or review all your tickets on the Support dashboard.</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button onClick={() => setPage('customers')}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-xl">
                      Go to Customers
                    </button>
                    <button onClick={() => setPage('support')}
                      className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-semibold rounded-xl border border-slate-700/50">
                      Support Dashboard
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ═══════ SUPPORT DASHBOARD ═══════ */}
          {page === 'support' && (
            <div className="space-y-6 animate-fadeIn">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-2xl font-bold text-white">Support Dashboard</h2>
                  <p className="text-sm text-slate-500 mt-1">
                    {isAdmin
                      ? 'All support tickets across customers — status, agents, and recent activity'
                      : 'Your support tickets and open workload'}
                  </p>
                </div>
                <button
                  onClick={() => { fetchDash(); fetchAllSupportLogs(); }}
                  className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-sm font-semibold border border-slate-700/50 flex items-center gap-2"
                >
                  <Icon d={Icons.refresh} className="w-4 h-4" /> Refresh
                </button>
              </div>

              {dash && (
                <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
                  {[
                    { label: 'Open', value: dash.support_open || 0, color: 'from-amber-600/20 to-amber-700/10', accent: 'text-amber-400', filter: 'open' },
                    { label: 'In Progress', value: dash.support_in_progress || 0, color: 'from-blue-600/20 to-blue-700/10', accent: 'text-blue-400', filter: 'in_progress' },
                    { label: 'Active', value: dash.open_support || 0, color: 'from-violet-600/20 to-violet-700/10', accent: 'text-violet-300', filter: 'active' },
                    { label: 'Resolved', value: dash.support_resolved || 0, color: 'from-emerald-600/20 to-emerald-700/10', accent: 'text-emerald-400', filter: 'resolved' },
                    { label: 'Closed', value: dash.support_closed || 0, color: 'from-slate-600/30 to-slate-700/10', accent: 'text-slate-300', filter: 'closed' },
                    { label: 'Total', value: dash.support_total || 0, color: 'from-cyan-600/20 to-cyan-700/10', accent: 'text-cyan-400', filter: 'all' },
                  ].map((c) => (
                    <button
                      key={c.filter}
                      type="button"
                      onClick={() => setSupportStatusFilter(c.filter)}
                      className={`bg-gradient-to-br ${c.color} rounded-xl p-5 text-left transition-all ${
                        supportStatusFilter === c.filter ? 'ring-1 ring-blue-400/50' : 'hover:ring-1 hover:ring-white/10'
                      }`}
                    >
                      <p className="text-xs font-medium text-slate-400 uppercase tracking-wider">{c.label}</p>
                      <p className={`text-3xl font-bold mt-2 font-mono ${c.accent}`}>{c.value}</p>
                    </button>
                  ))}
                </div>
              )}

              {isAdmin && dash?.support_by_agent?.length > 0 && (
                <div>
                  <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">By Agent</h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {dash.support_by_agent.map((agent) => (
                      <button
                        key={agent.id}
                        type="button"
                        onClick={() => setSupportAgentFilter(String(agent.id))}
                        className={`bg-slate-925 border rounded-xl p-4 text-left transition-colors ${
                          supportAgentFilter === String(agent.id)
                            ? 'border-blue-500/40 bg-blue-600/10'
                            : 'border-slate-800/50 hover:border-slate-700'
                        }`}
                      >
                        <p className="text-sm font-semibold text-white">{agent.full_name}</p>
                        <p className="text-[11px] text-slate-500 mt-0.5">@{agent.username}</p>
                        <div className="flex gap-4 mt-3">
                          <div>
                            <p className="text-[10px] uppercase tracking-wider text-slate-500">Open</p>
                            <p className="text-lg font-mono font-bold text-amber-400">{agent.open_logs}</p>
                          </div>
                          <div>
                            <p className="text-[10px] uppercase tracking-wider text-slate-500">Total</p>
                            <p className="text-lg font-mono font-bold text-slate-200">{agent.total_logs}</p>
                          </div>
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="bg-slate-925 border border-slate-800/50 rounded-xl overflow-hidden">
                <div className="flex flex-wrap items-center gap-3 px-5 py-3 border-b border-slate-800/30">
                  <div className="relative flex-1 min-w-[180px]">
                    <Icon d={Icons.search} className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                    <input
                      value={supportSearch}
                      onChange={(e) => setSupportSearch(e.target.value)}
                      placeholder="Search hospital, caller, phone, problem…"
                      className="w-full bg-slate-900 border border-slate-700/50 rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50"
                    />
                  </div>
                  <select
                    value={supportStatusFilter}
                    onChange={(e) => setSupportStatusFilter(e.target.value)}
                    className="bg-slate-900 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none"
                  >
                    <option value="active">Active (open + in progress)</option>
                    <option value="all">All statuses</option>
                    {SUPPORT_STATUS_OPTIONS.map((s) => (
                      <option key={s.value} value={s.value}>{s.label}</option>
                    ))}
                  </select>
                  {isAdmin && (
                    <select
                      value={supportAgentFilter}
                      onChange={(e) => setSupportAgentFilter(e.target.value)}
                      className="bg-slate-900 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none"
                    >
                      <option value="all">All agents</option>
                      {users.map((u) => (
                        <option key={u.id} value={String(u.id)}>{u.full_name}</option>
                      ))}
                    </select>
                  )}
                  {(supportSearch || supportStatusFilter !== 'active' || supportAgentFilter !== 'all') && (
                    <button
                      type="button"
                      onClick={() => {
                        setSupportSearch('');
                        setSupportStatusFilter('active');
                        setSupportAgentFilter('all');
                      }}
                      className="text-xs text-slate-400 hover:text-white"
                    >
                      Clear filters
                    </button>
                  )}
                </div>

                {allSupportLogs.length === 0 ? (
                  <p className="text-center py-12 text-slate-600 text-sm">No support tickets match these filters</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead>
                        <tr className="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-800/40">
                          <th className="px-4 py-2.5 font-medium">Hospital</th>
                          <th className="px-4 py-2.5 font-medium">Caller</th>
                          <th className="px-4 py-2.5 font-medium">Problem</th>
                          <th className="px-4 py-2.5 font-medium">Status</th>
                          <th className="px-4 py-2.5 font-medium">Received</th>
                          <th className="px-4 py-2.5 font-medium">Closed</th>
                          <th className="px-4 py-2.5 font-medium">Assistant</th>
                          <th className="px-4 py-2.5 font-medium" />
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/30">
                        {allSupportLogs.map((log) => {
                          const canEditStatus = isAdmin || log.created_by_user_id === currentUser?.id || log.assistant_user_id === currentUser?.id;
                          return (
                            <tr key={log.id} className="hover:bg-slate-800/20">
                              <td className="px-4 py-3">
                                <button
                                  type="button"
                                  className="text-left"
                                  onClick={() => {
                                    setSelectedCust(log.customer_id);
                                    setPage('customers');
                                    fetchCustDetail(log.customer_id);
                                  }}
                                >
                                  <p className="text-white font-medium whitespace-nowrap hover:text-blue-300">{log.hospital_name || '—'}</p>
                                  {log.hospital_id && (
                                    <p className="text-[11px] text-slate-500 font-mono">{log.hospital_id}</p>
                                  )}
                                </button>
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap">
                                <p className="text-white font-medium">{log.operator_name}</p>
                                <p className="text-[11px] text-slate-500">{log.cell_no || '—'}</p>
                              </td>
                              <td className="px-4 py-3 text-slate-300 max-w-xs truncate" title={log.problem}>{log.problem}</td>
                              <td className="px-4 py-3">
                                {canEditStatus ? (
                                  <select
                                    value={log.status}
                                    onChange={(e) => updateSupportStatus(log, e.target.value)}
                                    className={`px-2 py-1 rounded-lg text-[11px] font-semibold uppercase border-0 focus:outline-none focus:ring-1 focus:ring-blue-500/40 cursor-pointer ${
                                      log.status === 'open' ? 'bg-amber-500/10 text-amber-400'
                                        : log.status === 'in_progress' ? 'bg-blue-500/10 text-blue-400'
                                        : log.status === 'resolved' ? 'bg-emerald-500/10 text-emerald-400'
                                        : 'bg-slate-500/10 text-slate-400'
                                    }`}
                                  >
                                    {SUPPORT_STATUS_OPTIONS.map((s) => (
                                      <option key={s.value} value={s.value} className="bg-slate-900 text-white normal-case">{s.label}</option>
                                    ))}
                                  </select>
                                ) : (
                                  <span className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                                    log.status === 'open' ? 'bg-amber-500/10 text-amber-400'
                                      : log.status === 'in_progress' ? 'bg-blue-500/10 text-blue-400'
                                      : log.status === 'resolved' ? 'bg-emerald-500/10 text-emerald-400'
                                      : 'bg-slate-500/10 text-slate-400'
                                  }`}>
                                    {SUPPORT_STATUS_OPTIONS.find(s => s.value === log.status)?.label || log.status}
                                  </span>
                                )}
                              </td>
                              <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">{formatDateTime(log.start_time)}</td>
                              <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">{formatDateTime(log.end_time)}</td>
                              <td className="px-4 py-3 text-slate-300 whitespace-nowrap">{log.assistant?.full_name || '—'}</td>
                              <td className="px-4 py-3 whitespace-nowrap">
                                <div className="flex gap-1 justify-end">
                                  <button
                                    onClick={() => {
                                      setSelectedCust(log.customer_id);
                                      setPage('customers');
                                      fetchCustDetail(log.customer_id);
                                    }}
                                    className="px-2 py-1 text-[11px] bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700"
                                  >
                                    Open
                                  </button>
                                  {(isAdmin || log.created_by_user_id === currentUser?.id) && (
                                    <button onClick={() => deleteSupportLog(log.id)}
                                      className="px-2 py-1 text-[11px] bg-red-500/10 text-red-400 rounded-lg hover:bg-red-500/20">Delete</button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ═══════ LICENSES ═══════ */}
          {page === 'licenses' && isAdmin && (
            <div className="space-y-5 animate-fadeIn">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-2xl font-bold text-white">Licenses</h2>
                  <p className="text-sm text-slate-500 mt-1">{licenses.length} license{licenses.length !== 1 ? 's' : ''} total</p>
                </div>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-2 px-4 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-sm font-semibold transition-colors cursor-pointer border border-slate-700/50">
                    <Icon d={Icons.upload || "M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"} className="w-4 h-4" />
                    {processingRebind ? 'Processing…' : 'Process Rebind Request'}
                    <input type="file" accept=".json,.rebind.json,application/json" className="hidden"
                      disabled={processingRebind}
                      onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ''; if (f) processRebind(f); }} />
                  </label>
                  <button onClick={() => openGenerateForm()}
                    className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-sm font-semibold transition-colors shadow-lg shadow-blue-600/20">
                    <Icon d={Icons.plus} className="w-4 h-4" />
                    Generate License
                  </button>
                </div>
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
                            <button onClick={() => { setShowRenew(lic); setRenewCustomDuration(false); setRenewForm({ months: 12, days: 0, plan: lic.plan || 'standard', max_users: lic.max_users || 50, features: lic.features || [], gdrive_backup_enabled: false, seller_id: '' }); }} title="Renew"
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
                {isAdmin && (
                <button onClick={() => { setEditingCust(null); setCustForm({ ...EMPTY_CUST_FORM }); setShowCustForm(true); }}
                  className="flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-sm font-semibold transition-colors shadow-lg shadow-blue-600/20">
                  <Icon d={Icons.plus} className="w-4 h-4" /> Add Customer
                </button>
                )}
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
                    {c.gst_number && <p className="text-xs text-slate-500 font-mono mt-1">GST: {c.gst_number}</p>}
                    <div className="flex gap-3 mt-2 text-xs text-slate-500">
                      {c.phone && <span>{c.phone}</span>}
                      {c.machine_id && <span className="font-mono">{c.machine_id}</span>}
                    </div>
                    <div className="flex gap-1.5 mt-3" onClick={e => e.stopPropagation()}>
                      {isAdmin && (
                        <>
                          <button onClick={() => openEditCust(c)} className="px-2 py-1 text-[11px] bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700">Edit</button>
                          <button onClick={() => deleteCust(c.id)} className="px-2 py-1 text-[11px] bg-red-500/10 text-red-400 rounded-lg hover:bg-red-500/20">Delete</button>
                        </>
                      )}
                      <button onClick={() => { setSelectedCust(c.id); fetchCustDetail(c.id); }}
                        className="px-2 py-1 text-[11px] bg-blue-500/10 text-blue-400 rounded-lg hover:bg-blue-500/20">
                        Support Log
                      </button>
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
              {/* Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <button onClick={() => { setSelectedCust(null); setCustDetail(null); }}
                    className="p-2 text-slate-400 hover:text-white bg-slate-800/50 rounded-lg">←</button>
                  <div>
                    <h2 className="text-2xl font-bold text-white">{custDetail.customer.hospital_name}</h2>
                    <div className="flex gap-3 text-xs text-slate-500 mt-1">
                      {custDetail.customer.hospital_id && <span className="font-mono bg-slate-800/50 px-1.5 py-0.5 rounded">{custDetail.customer.hospital_id}</span>}
                      {custDetail.customer.machine_id && <span className="font-mono bg-slate-800/50 px-1.5 py-0.5 rounded">{custDetail.customer.machine_id}</span>}
                    </div>
                  </div>
                </div>
                {isAdmin && (
                <button onClick={() => openEditCust(custDetail.customer)}
                  className="px-3 py-2 text-xs bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700">Edit Customer</button>
                )}
              </div>

              {/* Customer Info + Summary */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {/* Contact Info */}
                <div className="bg-slate-925 border border-slate-800/50 rounded-xl p-4 space-y-2">
                  <p className="text-[11px] text-slate-500 uppercase tracking-wider">Contact Details</p>
                  {custDetail.customer.contact_person && <p className="text-sm text-white">{custDetail.customer.contact_person}</p>}
                  {custDetail.customer.phone && <p className="text-xs text-slate-400">{custDetail.customer.phone}</p>}
                  {custDetail.customer.email && <p className="text-xs text-slate-400">{custDetail.customer.email}</p>}
                  {custDetail.customer.gst_number && <p className="text-xs text-slate-400 font-mono">GST: {custDetail.customer.gst_number}</p>}
                  {custDetail.customer.address && <p className="text-xs text-slate-500 mt-1">{custDetail.customer.address}</p>}
                  {!custDetail.customer.contact_person && !custDetail.customer.phone && <p className="text-xs text-slate-600">No contact info</p>}
                </div>

                {/* Summary Stats */}
                <div className="lg:col-span-2 grid grid-cols-2 md:grid-cols-4 gap-3">
                  {(isAdmin ? [
                    { label: 'Licenses', value: custDetail.summary.total_licenses, accent: 'text-blue-400' },
                    { label: 'Active', value: custDetail.summary.active_licenses, accent: 'text-emerald-400' },
                    { label: 'Payments', value: custDetail.summary.total_payments, accent: 'text-cyan-400' },
                    { label: 'Total Paid', value: `₹${custDetail.summary.total_paid.toLocaleString('en-IN')}`, accent: 'text-amber-400' },
                  ] : [
                    { label: 'Support Logs', value: custDetail.summary.support_logs || supportLogs.length, accent: 'text-blue-400' },
                    { label: 'My Logs', value: custDetail.summary.my_support_logs || 0, accent: 'text-violet-300' },
                    { label: 'License Status', value: custDetail.summary.active_licenses > 0 ? 'Active' : '—', accent: 'text-emerald-400' },
                    { label: 'Expires Soon', value: (custDetail.licenses || []).filter(l => l.computed_status === 'expiring_soon').length, accent: 'text-amber-400' },
                  ]).map((c, i) => (
                    <div key={i} className="bg-slate-925 border border-slate-800/50 rounded-xl p-4">
                      <p className="text-[11px] text-slate-500 uppercase tracking-wider">{c.label}</p>
                      <p className={`text-xl font-bold mt-1 font-mono ${c.accent}`}>{c.value}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Support Given Log */}
              <div className="bg-slate-925 border border-slate-800/50 rounded-xl overflow-hidden">
                <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3 border-b border-slate-800/30">
                  <div className="flex items-center gap-3">
                    <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Support Given Log</h3>
                    {isAgent && (
                      <label className="flex items-center gap-2 text-[11px] text-slate-400">
                        <input type="checkbox" checked={mineOnlyLogs} onChange={(e) => setMineOnlyLogs(e.target.checked)}
                          className="rounded border-slate-600" />
                        My activity only
                      </label>
                    )}
                  </div>
                  <button onClick={() => openSupportForm()}
                    className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-lg transition-colors">
                    + Log Support
                  </button>
                </div>
                {supportLogs.length === 0 ? (
                  <p className="text-center py-8 text-slate-600 text-sm">No support logs yet</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead>
                        <tr className="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-800/40">
                          <th className="px-4 py-2.5 font-medium">Caller Name</th>
                          <th className="px-4 py-2.5 font-medium">Phone</th>
                          <th className="px-4 py-2.5 font-medium">Problem</th>
                          <th className="px-4 py-2.5 font-medium">Status</th>
                          <th className="px-4 py-2.5 font-medium">Received</th>
                          <th className="px-4 py-2.5 font-medium">Closed At</th>
                          <th className="px-4 py-2.5 font-medium">Assistant</th>
                          <th className="px-4 py-2.5 font-medium" />
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/30">
                        {supportLogs.map((log) => {
                          const canEditStatus = isAdmin || log.created_by_user_id === currentUser?.id || log.assistant_user_id === currentUser?.id;
                          return (
                          <tr key={log.id} className="hover:bg-slate-800/20">
                            <td className="px-4 py-3 text-white font-medium whitespace-nowrap">{log.operator_name}</td>
                            <td className="px-4 py-3 text-slate-400 whitespace-nowrap">{log.cell_no || '—'}</td>
                            <td className="px-4 py-3 text-slate-300 max-w-xs truncate" title={log.problem}>{log.problem}</td>
                            <td className="px-4 py-3">
                              {canEditStatus ? (
                                <select
                                  value={log.status}
                                  onChange={(e) => updateSupportStatus(log, e.target.value)}
                                  className={`px-2 py-1 rounded-lg text-[11px] font-semibold uppercase border-0 focus:outline-none focus:ring-1 focus:ring-blue-500/40 cursor-pointer ${
                                    log.status === 'open' ? 'bg-amber-500/10 text-amber-400'
                                      : log.status === 'in_progress' ? 'bg-blue-500/10 text-blue-400'
                                      : log.status === 'resolved' ? 'bg-emerald-500/10 text-emerald-400'
                                      : 'bg-slate-500/10 text-slate-400'
                                  }`}
                                >
                                  {SUPPORT_STATUS_OPTIONS.map((s) => (
                                    <option key={s.value} value={s.value} className="bg-slate-900 text-white normal-case">{s.label}</option>
                                  ))}
                                </select>
                              ) : (
                                <span className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                                  log.status === 'open' ? 'bg-amber-500/10 text-amber-400'
                                    : log.status === 'in_progress' ? 'bg-blue-500/10 text-blue-400'
                                    : log.status === 'resolved' ? 'bg-emerald-500/10 text-emerald-400'
                                    : 'bg-slate-500/10 text-slate-400'
                                }`}>
                                  {SUPPORT_STATUS_OPTIONS.find(s => s.value === log.status)?.label || log.status}
                                </span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">{formatDateTime(log.start_time)}</td>
                            <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">{formatDateTime(log.end_time)}</td>
                            <td className="px-4 py-3 text-slate-300 whitespace-nowrap">{log.assistant?.full_name || '—'}</td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              <div className="flex gap-1 justify-end">
                                {canEditStatus && (
                                  <button onClick={() => openSupportForm(log)}
                                    className="px-2 py-1 text-[11px] bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700">Edit</button>
                                )}
                                {(isAdmin || log.created_by_user_id === currentUser?.id) && (
                                  <button onClick={() => deleteSupportLog(log.id)}
                                    className="px-2 py-1 text-[11px] bg-red-500/10 text-red-400 rounded-lg hover:bg-red-500/20">Delete</button>
                                )}
                              </div>
                            </td>
                          </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Licenses — admin manages; agents see status only */}
              {isAdmin && (
              <div className="bg-slate-925 border border-slate-800/50 rounded-xl overflow-hidden">
                <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800/30">
                  <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Licenses</h3>
                  <button onClick={() => openGenerateForm({
                    customer_id: selectedCust,
                    hospital_id: custDetail.customer.hospital_id || '',
                    hospital_name: custDetail.customer.hospital_name,
                    machine_id: custDetail.customer.machine_id || '',
                  })} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-lg transition-colors">
                    + Generate License
                  </button>
                </div>
                {custDetail.licenses.length === 0 ? (
                  <p className="text-center py-8 text-slate-600 text-sm">No licenses yet. Generate the first one above.</p>
                ) : (
                  <div className="divide-y divide-slate-800/20">
                    {custDetail.licenses.map(lic => (
                      <div key={lic.license_id} className="px-5 py-4">
                        <div className="flex items-start justify-between">
                          <div className="space-y-1.5">
                            <div className="flex items-center gap-2">
                              <StatusBadge status={lic.computed_status} />
                              <span className="text-sm font-semibold text-white capitalize">{lic.plan}</span>
                              <span className="text-xs text-slate-500 font-mono">{lic.machine_id}</span>
                              <DaysLeft days={lic.days_left} />
                            </div>
                            <div className="flex items-center gap-3 text-xs text-slate-500">
                              <span>Issued: {formatDate(lic.issued_at)}</span>
                              <span>→ Expires: {formatDate(lic.expires_at)}</span>
                              <span>{lic.max_users} users</span>
                            </div>
                            <div className="flex flex-wrap gap-1 mt-1">
                              {(lic.features || []).map(f => <FeatureTag key={f} name={f} />)}
                            </div>
                            {lic.notes && <p className="text-[10px] text-blue-400/60 mt-1">{lic.notes}</p>}
                          </div>
                          <div className="flex items-center gap-2 shrink-0 ml-4">
                            <button onClick={() => downloadLicense(lic.license_id)} title="Download .lic"
                              className="px-2.5 py-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 text-xs font-medium flex items-center gap-1">
                              <Icon d={Icons.download} className="w-3 h-3" /> Download
                            </button>
                            {lic.computed_status !== 'renewed' && (
                              <button onClick={() => { setShowRenew(lic); setRenewCustomDuration(false); setRenewForm({ months: 12, days: 0, plan: lic.plan || 'standard', max_users: lic.max_users || 50, features: lic.features || [], gdrive_backup_enabled: false, seller_id: '' }); }} title="Renew"
                                className="px-2.5 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 text-xs font-medium flex items-center gap-1">
                                <Icon d={Icons.refresh} className="w-3 h-3" /> Renew
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              )}

              {/* Payments — admin only */}
              {isAdmin && (
              <div className="bg-slate-925 border border-slate-800/50 rounded-xl overflow-hidden">
                <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800/30">
                  <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Payment History</h3>
                  <button onClick={() => setShowPayForm(true)} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-lg transition-colors">
                    + Record Payment
                  </button>
                </div>
                {custDetail.payments.length === 0 ? (
                  <p className="text-center py-8 text-slate-600 text-sm">No payments recorded</p>
                ) : (
                  <div className="divide-y divide-slate-800/20">
                    {custDetail.payments.map(pay => (
                      <div key={pay.id} className="flex items-center justify-between px-5 py-3">
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
                )}
              </div>
              )}
            </div>
          )}

          {/* ═══════ USERS (admin) ═══════ */}
          {page === 'users' && isAdmin && (
            <div className="space-y-5 animate-fadeIn">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-2xl font-bold text-white">Users & Access</h2>
                  <p className="text-sm text-slate-500 mt-1">Admins manage licenses; support agents log customer support</p>
                </div>
                <button onClick={() => {
                  setEditingUser(null);
                  setUserForm({ username: '', password: '', full_name: '', role: 'support_agent' });
                  setShowUserForm(true);
                }} className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-xl">
                  + Add User
                </button>
              </div>
              <div className="bg-slate-925 border border-slate-800/50 rounded-xl overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-800/40">
                      <th className="px-5 py-3 text-left font-medium">Name</th>
                      <th className="px-5 py-3 text-left font-medium">Username</th>
                      <th className="px-5 py-3 text-left font-medium">Role</th>
                      <th className="px-5 py-3 text-left font-medium">Status</th>
                      <th className="px-5 py-3 text-right font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/30">
                    {users.map((u) => (
                      <tr key={u.id}>
                        <td className="px-5 py-3 text-white font-medium">{u.full_name}</td>
                        <td className="px-5 py-3 text-slate-400 font-mono text-xs">{u.username}</td>
                        <td className="px-5 py-3 capitalize text-slate-300">{u.role.replace('_', ' ')}</td>
                        <td className="px-5 py-3">
                          <span className={`text-[11px] font-semibold ${u.is_active ? 'text-emerald-400' : 'text-slate-500'}`}>
                            {u.is_active ? 'Active' : 'Inactive'}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-right">
                          <button onClick={() => {
                            setEditingUser(u);
                            setUserForm({ username: u.username, password: '', full_name: u.full_name, role: u.role });
                            setShowUserForm(true);
                          }} className="px-2 py-1 text-[11px] bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700">Edit</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ═══════ SELLERS ═══════ */}
          {page === 'sellers' && isAdmin && (
            <div className="space-y-6 animate-fadeIn">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-2xl font-bold text-white">Sellers / Vendors</h2>
                  <p className="text-sm text-slate-500 mt-1">Manage 3rd party vendors who resell licenses</p>
                </div>
                <button onClick={() => { setEditingSeller(null); setSellerForm({ name: '', address: '', phone: '' }); setShowSellerForm(true); }}
                  className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-xl transition-colors shadow-lg shadow-blue-600/20">
                  + Add Seller
                </button>
              </div>

              {sellers.length === 0 ? (
                <div className="text-center py-16 text-slate-500">
                  <p className="text-lg">No sellers added yet</p>
                  <p className="text-sm mt-1">Add a vendor to embed their details in licenses</p>
                </div>
              ) : (
                <div className="grid gap-3">
                  {sellers.map(s => (
                    <div key={s.id} className="bg-slate-900/50 border border-slate-800/50 rounded-xl p-4 flex items-center justify-between">
                      <div>
                        <p className="text-white font-semibold">{s.name}</p>
                        {s.address && <p className="text-xs text-slate-400 mt-0.5">{s.address}</p>}
                        {s.phone && <p className="text-xs text-slate-400">{s.phone}</p>}
                      </div>
                      <div className="flex gap-2">
                        <button onClick={() => { setEditingSeller(s); setSellerForm({ name: s.name, address: s.address || '', phone: s.phone || '' }); setShowSellerForm(true); }}
                          className="px-3 py-1.5 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors">
                          Edit
                        </button>
                        <button onClick={() => deleteSeller(s.id)}
                          className="px-3 py-1.5 text-xs bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded-lg transition-colors">
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Seller Form Modal */}
              {showSellerForm && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                  <div className="bg-slate-900 border border-slate-700/50 rounded-2xl w-full max-w-md p-6 space-y-4">
                    <h3 className="text-lg font-bold text-white">{editingSeller ? 'Edit Seller' : 'Add Seller'}</h3>
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5">Company Name *</label>
                      <input value={sellerForm.name} onChange={e => setSellerForm({...sellerForm, name: e.target.value})}
                        placeholder="ABC Health Solutions"
                        className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5">Address</label>
                      <input value={sellerForm.address} onChange={e => setSellerForm({...sellerForm, address: e.target.value})}
                        placeholder="Full address"
                        className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50" />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5">Contact Number</label>
                      <input value={sellerForm.phone} onChange={e => setSellerForm({...sellerForm, phone: e.target.value})}
                        placeholder="9876543210"
                        className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50" />
                    </div>
                    <div className="flex justify-end gap-3 pt-2">
                      <button onClick={() => { setShowSellerForm(false); setEditingSeller(null); }}
                        className="px-4 py-2.5 text-sm text-slate-400 hover:text-white rounded-lg transition-colors">Cancel</button>
                      <button onClick={saveSeller} disabled={!sellerForm.name}
                        className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-sm font-semibold rounded-xl transition-colors">
                        {editingSeller ? 'Update' : 'Add Seller'}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ═══════ KEY SETTINGS ═══════ */}
          {page === 'settings' && isAdmin && (
            <div className="space-y-6 animate-fadeIn max-w-2xl">
              <div>
                <h2 className="text-2xl font-bold text-white">Key Settings</h2>
                <p className="text-sm text-slate-500 mt-1">Signing keys are embedded in the application</p>
              </div>

              {/* Status */}
              <div className="bg-slate-925 border border-slate-800/50 rounded-xl p-6 space-y-4">
                <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Key Status</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div className="flex items-center gap-3 p-4 rounded-xl border bg-emerald-500/5 border-emerald-500/20">
                    <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-emerald-500/15">
                      <Icon d={Icons.key} className="w-5 h-5 text-emerald-400" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-white">Private Key</p>
                      <p className="text-xs text-emerald-400">Embedded</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 p-4 rounded-xl border bg-emerald-500/5 border-emerald-500/20">
                    <div className="w-10 h-10 rounded-lg flex items-center justify-center bg-emerald-500/15">
                      <Icon d={Icons.shield} className="w-5 h-5 text-emerald-400" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-white">Public Key</p>
                      <p className="text-xs text-emerald-400">Embedded</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Public Key Display */}
              {keyStatus?.public_key && (
                <div className="bg-slate-925 border border-slate-800/50 rounded-xl p-6 space-y-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Public Key</h3>
                    <button onClick={() => { navigator.clipboard.writeText(keyStatus.public_key); showMessage('Public key copied'); }}
                      className="text-xs text-blue-400 hover:text-blue-300 font-medium">Copy</button>
                  </div>
                  <p className="text-xs text-slate-500">This public key is embedded in the main hospital app at <code className="text-amber-400">app/licensing/crypto.py</code> for license verification.</p>
                  <pre className="bg-slate-950 border border-slate-800/50 rounded-lg p-4 text-xs text-emerald-400 font-mono overflow-x-auto whitespace-pre">
                    {keyStatus.public_key}
                  </pre>
                </div>
              )}

              {/* Google Drive Configuration (OAuth) */}
              <div className="bg-slate-925 border border-slate-800/50 rounded-xl p-6 space-y-4">
                <h3 className="text-sm font-semibold text-slate-300 uppercase tracking-wider">Google Drive Backup</h3>
                <p className="text-xs text-slate-500">Connect your Google Drive using OAuth. The refresh token will be embedded in licenses so hospital apps can upload backups to your Drive automatically.</p>

                {/* Status */}
                {gdriveSettings?.connected ? (
                  <div className="flex items-center justify-between p-3 rounded-xl border bg-emerald-500/5 border-emerald-500/20">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-emerald-500/15">
                        <span className="text-emerald-400 text-sm">✓</span>
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-white">Google Drive Connected</p>
                        <p className="text-xs text-emerald-400">OAuth refresh token saved</p>
                      </div>
                    </div>
                    <button onClick={async () => {
                      try { await apiFetch('/settings/gdrive/disconnect', { method: 'POST' }, token); showMessage('Disconnected'); fetchGdriveSettings(); } catch {}
                    }} className="text-xs text-red-400 hover:text-red-300">Disconnect</button>
                  </div>
                ) : (
                  <div className="flex items-center gap-3 p-3 rounded-xl border bg-amber-500/5 border-amber-500/20">
                    <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-amber-500/15">
                      <span className="text-amber-400 text-sm">!</span>
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-white">Not Connected</p>
                      <p className="text-xs text-amber-400">Set up OAuth credentials and connect below</p>
                    </div>
                  </div>
                )}

                <div className="space-y-3">
                  {/* Step 1: OAuth Credentials */}
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5">Step 1: OAuth Client ID</label>
                    <input id="gdrive-client-id" placeholder="From Google Cloud Console → Credentials → OAuth 2.0 Client"
                      className="w-full bg-slate-950 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50 mb-2" />
                    <label className="block text-xs font-medium text-slate-400 mb-1.5">OAuth Client Secret</label>
                    <div className="flex gap-2">
                      <input id="gdrive-client-secret" type="password" placeholder="Client secret"
                        className="flex-1 bg-slate-950 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50" />
                      <button onClick={async () => {
                        const cid = document.getElementById('gdrive-client-id').value;
                        const cs = document.getElementById('gdrive-client-secret').value;
                        if (!cid || !cs) { showMessage('Enter both Client ID and Secret', 'error'); return; }
                        try {
                          const r = await apiFetch('/settings/gdrive/oauth-credentials', {
                            method: 'POST',
                            body: JSON.stringify({ client_id: cid, client_secret: cs })
                          }, token);
                          if (r.ok) { showMessage('OAuth credentials saved'); fetchGdriveSettings(); }
                          else { const d = await r.json(); showMessage(d.detail || 'Failed', 'error'); }
                        } catch { showMessage('Failed', 'error'); }
                      }} className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-xl transition-colors">Save</button>
                    </div>
                    <p className="text-[10px] text-slate-500 mt-1">Redirect URI: <code className="text-amber-400">http://localhost:9000/api/settings/gdrive/oauth-callback</code></p>
                  </div>

                  {/* Step 2: Connect */}
                  {gdriveSettings?.has_credentials && !gdriveSettings?.connected && (
                    <div>
                      <label className="block text-xs font-medium text-slate-400 mb-1.5">Step 2: Connect Google Drive</label>
                      <button onClick={async () => {
                        try {
                          const r = await apiFetch('/settings/gdrive/auth-url', {}, token);
                          const d = await r.json();
                          if (d.auth_url) window.open(d.auth_url, '_blank');
                        } catch { showMessage('Failed to get auth URL', 'error'); }
                      }} className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-xl transition-colors">
                        Connect Google Drive
                      </button>
                      <p className="text-[10px] text-slate-500 mt-1">Opens Google login. Authorize and return here.</p>
                    </div>
                  )}

                  {/* Step 3: Folder ID */}
                  <div>
                    <label className="block text-xs font-medium text-slate-400 mb-1.5">{gdriveSettings?.connected ? 'Step 3' : 'Also set'}: Drive Folder ID</label>
                    <div className="flex gap-2">
                      <input value={gdriveSettings?.folder_id || ''} onChange={(e) => setGdriveSettings({...gdriveSettings, folder_id: e.target.value})}
                        placeholder="Paste folder ID from Google Drive URL"
                        className="flex-1 bg-slate-950 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50" />
                      <button onClick={async () => {
                        if (!gdriveSettings?.folder_id) return;
                        try {
                          const r = await apiFetch('/settings/gdrive', {
                            method: 'POST',
                            body: JSON.stringify({ folder_id: gdriveSettings.folder_id })
                          }, token);
                          if (r.ok) { showMessage('Folder ID saved'); fetchGdriveSettings(); }
                        } catch {}
                      }} className="px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-xl transition-colors">Save</button>
                    </div>
                    <p className="text-[10px] text-slate-500 mt-1">Create a folder in Google Drive, copy the ID from the URL after /folders/</p>
                  </div>

                  {/* Test Connection */}
                  <div>
                    <button onClick={async () => {
                      try {
                        const r = await apiFetch('/settings/gdrive/health', {}, token);
                        const d = await r.json();
                        if (d.healthy) showMessage(`Connected! Folder: "${d.folder_name}"`);
                        else showMessage(`Failed: ${d.error}`, 'error');
                      } catch { showMessage('Health check failed', 'error'); }
                    }}
                      disabled={!gdriveSettings?.configured}
                      className="px-4 py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-sm font-semibold rounded-xl transition-colors">
                      Test Connection
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* ═══════ GENERATE MODAL ═══════ */}
      <Modal open={showForm} onClose={closeGenerateForm} wide>
        <div className="p-6 space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-white">Generate License</h2>
              <p className="text-xs text-slate-500 mt-0.5">Step {formStep + 1} of {LICENSE_STEPS.length} — {LICENSE_STEPS[formStep].label}</p>
            </div>
            <button onClick={closeGenerateForm} className="p-1 text-slate-500 hover:text-white">
              <Icon d={Icons.x} className="w-5 h-5" />
            </button>
          </div>

          <Stepper steps={LICENSE_STEPS} current={formStep} onSelect={setFormStep} />

          {formStep === 0 && (
            <div className="space-y-4 min-h-[220px]">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">Customer (optional)</label>
                <select
                  value={form.customer_id === '' || form.customer_id == null ? '' : String(form.customer_id)}
                  onChange={(e) => applyCustomerToLicenseForm(e.target.value)}
                  className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/50"
                >
                  <option value="">No customer (orphan license)</option>
                  {customers.map((c) => (
                    <option key={c.id} value={c.id}>{c.hospital_name}{c.hospital_id ? ` (${c.hospital_id})` : ''}</option>
                  ))}
                </select>
                <p className="text-[10px] text-slate-500 mt-1">Selecting a customer prefills hospital fields below.</p>
              </div>
              <Input label="Hospital ID" required value={form.hospital_id}
                onChange={e => setForm({...form, hospital_id: e.target.value})} placeholder="HOSP01" />
              <Input label="Hospital Name" required value={form.hospital_name} maxLength={200}
                onChange={e => setForm({...form, hospital_name: e.target.value})}
                placeholder="St. Mary's Hospital & Research (P) Ltd."
                hint="Ampersands, apostrophes, brackets, and other punctuation are allowed." />
              <Input label="Machine ID" required value={form.machine_id}
                onChange={e => setForm({...form, machine_id: e.target.value})} placeholder="CA86-C087-6261" />
            </div>
          )}

          {formStep === 1 && (
            <div className="space-y-4 min-h-[220px]">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">Validity</label>
                <select value={customDuration ? 'custom' : String(form.months)}
                  onChange={e => {
                    if (e.target.value === 'custom') { setCustomDuration(true); }
                    else { setCustomDuration(false); setForm({...form, months: parseInt(e.target.value), days: 0}); }
                  }}
                  className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/50">
                  <option value="1">1 Month</option>
                  <option value="3">3 Months</option>
                  <option value="6">6 Months</option>
                  <option value="12">1 Year</option>
                  <option value="24">2 Years</option>
                  <option value="36">3 Years</option>
                  <option value="custom">Custom</option>
                </select>
                {customDuration && (
                  <div className="grid grid-cols-2 gap-2 mt-2">
                    <div>
                      <label className="block text-[10px] text-slate-500 mb-1">Months</label>
                      <input type="number" min={0} value={form.months}
                        onChange={e => setForm({...form, months: parseInt(e.target.value) || 0})}
                        className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50" />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-500 mb-1">Days</label>
                      <input type="number" min={0} value={form.days}
                        onChange={e => setForm({...form, days: parseInt(e.target.value) || 0})}
                        className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50" />
                    </div>
                  </div>
                )}
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
            </div>
          )}

          {formStep === 2 && (
            <div className="space-y-4 min-h-[220px]">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-2">Modules</label>
                <div className="flex flex-wrap gap-2">
                  {allModules.map(f => {
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
                        {FEATURE_LABELS[f] || f}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-2">Add-ons</label>
                <ToggleRow
                  checked={form.features.includes(CUSTOMISATION_ADDON)}
                  onChange={(on) => setForm({ ...form, features: withFeature(form.features, CUSTOMISATION_ADDON, on) })}
                  title="Customisation"
                  description="Unlocks white-label branding (app name, logo, favicon). Print customisations are always included. Leave off unless this customer bought the add-on."
                />
              </div>
            </div>
          )}

          {formStep === 3 && (
            <div className="space-y-4 min-h-[220px]">
              <div className="bg-slate-800/30 border border-slate-700/30 rounded-xl p-4 space-y-1.5">
                <p className="text-sm font-semibold text-white">{form.hospital_name || '—'}</p>
                <div className="flex flex-wrap gap-3 text-xs text-slate-400">
                  <span className="font-mono">{form.hospital_id || '—'}</span>
                  <span className="font-mono">{form.machine_id || '—'}</span>
                  <span className="capitalize">{form.plan}</span>
                  <span>{form.max_users} users</span>
                  <span>{form.months || 0} mo {form.days || 0} d</span>
                </div>
                <div className="flex flex-wrap gap-1 pt-1">
                  {form.features.map(f => <FeatureTag key={f} name={f} />)}
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">Notes</label>
                <textarea value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} rows={2}
                  placeholder="Optional notes about this license..."
                  className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50 resize-none" />
              </div>
              <div className="border-t border-slate-700/30 pt-4">
                <label className="block text-xs font-medium text-slate-400 mb-2">Sold via 3rd Party Vendor (Optional)</label>
                <select value={form.seller_id || ''} onChange={e => {
                  const id = e.target.value;
                  if (!id) {
                    setForm({...form, seller_id: '', seller_name: '', seller_address: '', seller_phone: ''});
                  } else {
                    const s = sellers.find(s => String(s.id) === id);
                    if (s) setForm({...form, seller_id: id, seller_name: s.name, seller_address: s.address || '', seller_phone: s.phone || ''});
                  }
                }}
                  className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/50">
                  <option value="">No vendor (direct sale)</option>
                  {sellers.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
                {form.seller_name && (
                  <div className="mt-2 p-2.5 bg-slate-800/50 rounded-lg text-xs text-slate-400 space-y-0.5">
                    <p className="text-white font-medium">{form.seller_name}</p>
                    {form.seller_address && <p>{form.seller_address}</p>}
                    {form.seller_phone && <p>{form.seller_phone}</p>}
                  </div>
                )}
              </div>
              <div className="border-t border-slate-700/30 pt-4 space-y-3">
                <label className="block text-xs font-medium text-slate-400">Add-ons</label>
                <ToggleRow
                  checked={form.features.includes(CUSTOMISATION_ADDON)}
                  onChange={(on) => setForm({ ...form, features: withFeature(form.features, CUSTOMISATION_ADDON, on) })}
                  title="Customisation"
                  description="White-label branding: app name, logo, and favicon."
                />
              </div>
              <div className="border-t border-slate-700/30 pt-4">
                <label className="flex items-center gap-2.5 cursor-pointer">
                  <input type="checkbox" checked={form.gdrive_backup_enabled}
                    onChange={(e) => setForm({...form, gdrive_backup_enabled: e.target.checked})}
                    disabled={!gdriveSettings?.configured}
                    className="w-4 h-4 rounded border-slate-600" />
                  <span className="text-sm text-slate-300">Enable Google Drive Backup</span>
                </label>
                {!gdriveSettings?.configured && (
                  <p className="text-[11px] text-amber-400/70 mt-1.5 ml-6">
                    {!gdriveSettings?.connected ? 'Connect Google Drive in Key Settings first' : 'Set folder ID in Key Settings first'}
                  </p>
                )}
                {form.gdrive_backup_enabled && gdriveSettings?.configured && (
                  <p className="text-[11px] text-green-400/70 mt-1.5 ml-6">Service account: {gdriveSettings.service_account_email}</p>
                )}
              </div>
            </div>
          )}

          <div className="flex justify-between gap-3 pt-3 border-t border-slate-700/30">
            <button onClick={formStep === 0 ? closeGenerateForm : () => setFormStep((s) => s - 1)}
              className="px-4 py-2.5 text-sm text-slate-400 hover:text-white rounded-lg transition-colors">
              {formStep === 0 ? 'Cancel' : 'Back'}
            </button>
            {formStep < LICENSE_STEPS.length - 1 ? (
              <button onClick={nextGenerateStep}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold rounded-xl transition-colors shadow-lg shadow-blue-600/20">
                Next
              </button>
            ) : (
              <button onClick={createLicense} disabled={saving}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:hover:bg-blue-600 text-white text-sm font-semibold rounded-xl transition-colors shadow-lg shadow-blue-600/20">
                {saving ? 'Generating...' : 'Generate License'}
              </button>
            )}
          </div>
        </div>
      </Modal>

      {/* ═══════ RENEW MODAL ═══════ */}
      <Modal open={!!showRenew} onClose={() => setShowRenew(null)} wide>
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
                <span className="font-mono">{showRenew.hospital_id}</span>
                <span className="font-mono">{showRenew.machine_id}</span>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={showRenew.computed_status} />
                <DaysLeft days={showRenew.days_left} />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">Validity</label>
                <select value={renewCustomDuration ? 'custom' : String(renewForm.months)}
                  onChange={e => {
                    if (e.target.value === 'custom') { setRenewCustomDuration(true); }
                    else { setRenewCustomDuration(false); setRenewForm({...renewForm, months: parseInt(e.target.value), days: 0}); }
                  }}
                  className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/50">
                  <option value="1">1 Month</option>
                  <option value="3">3 Months</option>
                  <option value="6">6 Months</option>
                  <option value="12">1 Year</option>
                  <option value="24">2 Years</option>
                  <option value="36">3 Years</option>
                  <option value="custom">Custom</option>
                </select>
                {renewCustomDuration && (
                  <div className="grid grid-cols-2 gap-2 mt-2">
                    <div>
                      <label className="block text-[10px] text-slate-500 mb-1">Months</label>
                      <input type="number" min={0} value={renewForm.months}
                        onChange={e => setRenewForm({...renewForm, months: parseInt(e.target.value) || 0})}
                        className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50" />
                    </div>
                    <div>
                      <label className="block text-[10px] text-slate-500 mb-1">Days</label>
                      <input type="number" min={0} value={renewForm.days}
                        onChange={e => setRenewForm({...renewForm, days: parseInt(e.target.value) || 0})}
                        className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500/50" />
                    </div>
                  </div>
                )}
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">Plan</label>
                <select value={renewForm.plan} onChange={e => setRenewForm({...renewForm, plan: e.target.value})}
                  className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/50">
                  <option value="standard">Standard</option>
                  <option value="premium">Premium</option>
                  <option value="enterprise">Enterprise</option>
                  <option value="basic">Basic</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1.5">Max Users</label>
                <input type="number" min={1} value={renewForm.max_users} onChange={e => setRenewForm({...renewForm, max_users: parseInt(e.target.value) || 50})}
                  className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/50" />
              </div>
            </div>

            {/* Modules */}
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Modules</label>
              <div className="flex flex-wrap gap-2">
                {allModules.map(f => {
                  const active = renewForm.features.includes(f);
                  return (
                    <button key={f} onClick={() => {
                      const feats = active ? renewForm.features.filter(x => x !== f) : [...renewForm.features, f];
                      setRenewForm({...renewForm, features: feats});
                    }}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                        active ? 'bg-blue-600/20 border-blue-500/40 text-blue-400' : 'bg-slate-800/50 border-slate-700/30 text-slate-500 hover:text-slate-300'
                      }`}>
                      {active && <span className="mr-1">✓</span>}
                      {FEATURE_LABELS[f] || f}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Add-ons</label>
              <ToggleRow
                checked={renewForm.features.includes(CUSTOMISATION_ADDON)}
                onChange={(on) => setRenewForm({ ...renewForm, features: withFeature(renewForm.features, CUSTOMISATION_ADDON, on) })}
                title="Customisation"
                description="Unlocks white-label branding (app name, logo, favicon)."
              />
            </div>

            {/* Seller */}
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">Sold via Vendor</label>
              <select value={renewForm.seller_id} onChange={e => setRenewForm({...renewForm, seller_id: e.target.value})}
                className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/50">
                <option value="">No vendor (direct sale)</option>
                {sellers.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>

            {/* Google Drive */}
            <label className="flex items-center gap-2.5 cursor-pointer">
              <input type="checkbox" checked={renewForm.gdrive_backup_enabled}
                onChange={e => setRenewForm({...renewForm, gdrive_backup_enabled: e.target.checked})}
                disabled={!gdriveSettings?.configured}
                className="w-4 h-4 rounded border-slate-600" />
              <span className="text-sm text-slate-300">Enable Google Drive Backup</span>
              {!gdriveSettings?.configured && <span className="text-[10px] text-amber-400/70">(not configured)</span>}
            </label>

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
              onChange={e => setCustForm({...custForm, hospital_name: e.target.value})}
              placeholder="St. Mary's Hospital & Research (P) Ltd."
              hint="Ampersands, apostrophes, brackets, and other punctuation are allowed." />
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
          <div className="grid grid-cols-2 gap-4">
            <Input label="GST Number" value={custForm.gst_number} maxLength={15}
              onChange={e => setCustForm({...custForm, gst_number: e.target.value.toUpperCase()})} placeholder="22AAAAA0000A1Z5" />
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
            {editingCust ? (
              <button onClick={() => saveCust()} disabled={saving || !custForm.hospital_name}
                className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-sm font-semibold rounded-xl shadow-lg shadow-blue-600/20">
                {saving ? 'Saving...' : 'Update'}
              </button>
            ) : (
              <>
                <button onClick={() => saveCust({ generateAfter: false })} disabled={saving || !custForm.hospital_name}
                  className="px-4 py-2.5 text-sm text-slate-300 bg-slate-800 hover:bg-slate-700 disabled:opacity-40 rounded-xl transition-colors">
                  {saving ? 'Saving...' : 'Add only'}
                </button>
                <button onClick={() => saveCust({ generateAfter: true })} disabled={saving || !custForm.hospital_name}
                  className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-sm font-semibold rounded-xl shadow-lg shadow-blue-600/20">
                  {saving ? 'Saving...' : 'Add & Generate License'}
                </button>
              </>
            )}
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

      {/* ═══════ SUPPORT LOG MODAL ═══════ */}
      <Modal open={showSupportForm} onClose={() => setShowSupportForm(false)} wide>
        <div className="p-6 space-y-5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-white">{editingSupport ? 'Edit Support Details' : 'New Support Ticket'}</h2>
              {!editingSupport && (
                <p className="text-xs text-slate-500 mt-1">Received time is recorded automatically when you save</p>
              )}
              {editingSupport && (
                <p className="text-xs text-slate-500 mt-1">
                  Received {formatDateTime(editingSupport.start_time)}
                  {editingSupport.end_time ? ` · Closed ${formatDateTime(editingSupport.end_time)}` : ''}
                </p>
              )}
            </div>
            <button onClick={() => setShowSupportForm(false)} className="p-1 text-slate-500 hover:text-white">
              <Icon d={Icons.x} className="w-5 h-5" />
            </button>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Input label="Caller Name" required value={supportForm.operator_name}
              onChange={(e) => setSupportForm({ ...supportForm, operator_name: e.target.value })}
              placeholder="Who is calling?" autoFocus />
            <Input label="Phone Number" required value={supportForm.cell_no}
              onChange={(e) => setSupportForm({ ...supportForm, cell_no: e.target.value })}
              placeholder="Caller mobile number" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Problem <span className="text-amber-400">*</span></label>
            <textarea value={supportForm.problem} onChange={(e) => setSupportForm({ ...supportForm, problem: e.target.value })}
              rows={4} placeholder="What issue did they report?"
              className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-blue-500/50 resize-none" />
          </div>
          <div className="flex justify-end gap-3 pt-3 border-t border-slate-700/30">
            <button onClick={() => setShowSupportForm(false)} className="px-4 py-2.5 text-sm text-slate-400 hover:text-white rounded-lg">Cancel</button>
            <button onClick={saveSupportLog} disabled={saving}
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-sm font-semibold rounded-xl">
              {saving ? 'Saving…' : (editingSupport ? 'Update Details' : 'Open Ticket')}
            </button>
          </div>
        </div>
      </Modal>

      {/* ═══════ USER FORM MODAL ═══════ */}
      <Modal open={showUserForm} onClose={() => setShowUserForm(false)}>
        <div className="p-6 space-y-5">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-bold text-white">{editingUser ? 'Edit User' : 'Add User'}</h2>
            <button onClick={() => setShowUserForm(false)} className="p-1 text-slate-500 hover:text-white">
              <Icon d={Icons.x} className="w-5 h-5" />
            </button>
          </div>
          {!editingUser && (
            <Input label="Username" required value={userForm.username}
              onChange={(e) => setUserForm({ ...userForm, username: e.target.value })}
              placeholder="login username" />
          )}
          <Input label="Full Name" required value={userForm.full_name}
            onChange={(e) => setUserForm({ ...userForm, full_name: e.target.value })}
            placeholder="Display name" />
          <div>
            <label className="block text-xs font-medium text-slate-400 mb-1.5">Role</label>
            <select value={userForm.role} onChange={(e) => setUserForm({ ...userForm, role: e.target.value })}
              className="w-full bg-slate-925 border border-slate-700/50 rounded-lg px-3 py-2.5 text-sm text-white focus:outline-none focus:border-blue-500/50">
              <option value="support_agent">Support Agent</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <Input label={editingUser ? 'New Password (optional)' : 'Password'} required={!editingUser} type="password"
            value={userForm.password}
            onChange={(e) => setUserForm({ ...userForm, password: e.target.value })}
            placeholder={editingUser ? 'Leave blank to keep' : 'Min 6 characters'} />
          <div className="flex justify-end gap-3 pt-3 border-t border-slate-700/30">
            <button onClick={() => setShowUserForm(false)} className="px-4 py-2.5 text-sm text-slate-400 hover:text-white rounded-lg">Cancel</button>
            <button onClick={saveUser} disabled={saving}
              className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-sm font-semibold rounded-xl">
              {saving ? 'Saving…' : (editingUser ? 'Update User' : 'Create User')}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

export default App;
