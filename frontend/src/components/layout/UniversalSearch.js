import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { FileText, Loader2, Search, User, Zap } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Input } from '../ui/input';
import { useAuth } from '../../contexts/AuthContext';
import { normalizeUserRoles } from '../../hooks/useNavigationSections';

const RECENT_PAGES_KEY = 'universal_search_recent_pages_v1';
const MAX_RECENT = 5;
const MAX_QUICK = 6;

/** Preferred quick-jump paths per role (order = priority). Only shown if in nav. */
const ROLE_QUICK_PATHS = {
  receptionist: [
    '/dashboard/reception-home',
    '/dashboard/reception/appointments',
    '/dashboard/reception/patients',
    '/dashboard/billing',
    '/dashboard/reception/lab-orders',
    '/dashboard/reception/procedures',
  ],
  doctor: [
    '/dashboard/doctor-home',
    '/dashboard/ehr',
    '/dashboard/inpatient/admissions',
    '/dashboard/availability',
    '/dashboard/inpatient/ot',
  ],
  lab_technician: [
    '/dashboard/lab-home',
    '/dashboard/reception/lab-orders',
  ],
  lab_admin: [
    '/dashboard/lab-home',
    '/dashboard/lab',
    '/dashboard/lab/tests',
    '/dashboard/lab/packages',
  ],
  nurse: [
    '/dashboard/nurse-home',
    '/dashboard/inpatient/admissions',
    '/dashboard/inpatient',
    '/dashboard/inpatient/housekeeping',
    '/dashboard/ehr',
  ],
  hospital_admin: [
    '/dashboard/hospital-admin-home',
    '/dashboard/hospital-admin',
    '/dashboard/billing',
    '/dashboard/reception/appointments',
    '/dashboard/inpatient',
    '/dashboard/admin',
  ],
  super_admin: [
    '/dashboard/admin-home',
    '/dashboard/admin',
    '/dashboard/license',
    '/dashboard/backup',
    '/dashboard/hospital-admin',
  ],
  inpatient_admin: [
    '/dashboard/inpatient',
    '/dashboard/inpatient/admissions',
    '/dashboard/inpatient/discharge',
    '/dashboard/inpatient/rooms',
  ],
  billing_admin: [
    '/dashboard/billing',
    '/dashboard/settlements',
    '/dashboard/inpatient/admissions',
    '/dashboard/catch-up',
  ],
  frontdesk: [
    '/dashboard/reception/patients',
    '/dashboard/reception/appointments',
    '/dashboard/inpatient/admissions',
    '/dashboard/billing',
  ],
  pharmacy_admin: [
    '/dashboard/pharmacy',
    '/dashboard/pharmacy/sales-counter',
    '/dashboard/pharmacy/inventory',
    '/dashboard/pharmacy/purchases',
  ],
  pharmacist: [
    '/dashboard/pharmacy/sales-counter',
    '/dashboard/pharmacy/pending-rx',
    '/dashboard/pharmacy/inventory',
    '/dashboard/pharmacy/sales',
  ],
  pharmacy_pos_operator: [
    '/dashboard/pharmacy/sales-counter',
    '/dashboard/pharmacy/sales',
    '/dashboard/pharmacy/pending-rx',
  ],
  satellite_pharmacy_admin: [
    '/dashboard/pharmacy/inventory',
    '/dashboard/pharmacy/transfers',
    '/dashboard/pharmacy/sales-counter',
  ],
  pharmacy_transfer_clerk: [
    '/dashboard/pharmacy/transfers',
    '/dashboard/pharmacy/inventory',
  ],
  canteen_admin: [
    '/dashboard/canteen',
  ],
  canteen_sales: [
    '/dashboard/canteen',
  ],
};

function loadRecentPages() {
  try {
    const raw = localStorage.getItem(RECENT_PAGES_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function pushRecentPage(entry) {
  try {
    const prev = loadRecentPages().filter((p) => p.path !== entry.path);
    const next = [entry, ...prev].slice(0, MAX_RECENT);
    localStorage.setItem(RECENT_PAGES_KEY, JSON.stringify(next));
  } catch {
    /* ignore */
  }
}

function flattenNavPages(sections) {
  const pages = [];
  for (const section of sections || []) {
    for (const item of section.items || []) {
      pages.push({
        text: item.text,
        path: item.path,
        section: section.label || '',
      });
    }
  }
  return pages;
}

function patientDisplayName(p) {
  const name = [p.first_name, p.last_name].filter(Boolean).join(' ').trim();
  return name || p.full_name || 'Patient';
}

/** Build role-aware quick jumps that intersect with pages the user can open. */
function buildQuickActions(roles, allPages) {
  const byPath = new Map(allPages.map((p) => [p.path, p]));
  const seen = new Set();
  const actions = [];

  for (const role of roles) {
    const paths = ROLE_QUICK_PATHS[role] || [];
    for (const path of paths) {
      if (seen.has(path)) continue;
      const page = byPath.get(path);
      if (!page) continue;
      seen.add(path);
      actions.push({ ...page, quick: true });
      if (actions.length >= MAX_QUICK) return actions;
    }
  }

  // Fallback: first few nav pages (role dashboards often sit at the top)
  if (actions.length === 0) {
    for (const page of allPages) {
      if (seen.has(page.path)) continue;
      seen.add(page.path);
      actions.push({ ...page, quick: true });
      if (actions.length >= Math.min(MAX_QUICK, 4)) break;
    }
  }

  return actions;
}

/**
 * Cmd/Ctrl+K command palette: nav pages + patient search + role quick actions.
 */
export default function UniversalSearch({
  navigationSections = [],
  open: controlledOpen,
  onOpenChange,
  triggerClassName = '',
  triggerVariant = 'default',
}) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const roles = useMemo(() => normalizeUserRoles(user), [user]);

  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen !== undefined ? controlledOpen : internalOpen;
  const setOpen = onOpenChange || setInternalOpen;

  const [query, setQuery] = useState('');
  const [patients, setPatients] = useState([]);
  const [searchingPatients, setSearchingPatients] = useState(false);
  const [patientsDenied, setPatientsDenied] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [recentPages, setRecentPages] = useState(() => loadRecentPages());
  const inputRef = useRef(null);

  const allPages = useMemo(() => flattenNavPages(navigationSections), [navigationSections]);

  const quickActions = useMemo(
    () => buildQuickActions(roles, allPages),
    [roles, allPages],
  );

  const filteredPages = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return allPages.filter(
      (p) =>
        p.text.toLowerCase().includes(q) ||
        p.path.toLowerCase().includes(q) ||
        (p.section && p.section.toLowerCase().includes(q)),
    ).slice(0, 8);
  }, [allPages, query]);

  const recentForEmpty = useMemo(() => {
    const quickPaths = new Set(quickActions.map((p) => p.path));
    return recentPages
      .filter((r) => allPages.some((p) => p.path === r.path) && !quickPaths.has(r.path))
      .slice(0, MAX_RECENT);
  }, [recentPages, allPages, quickActions]);

  const pageResults = query.trim() ? filteredPages : [];

  const flatResults = useMemo(() => {
    const items = [];
    if (!query.trim()) {
      quickActions.forEach((p) => items.push({ type: 'page', ...p }));
      recentForEmpty.forEach((p) => items.push({ type: 'page', ...p }));
    } else {
      pageResults.forEach((p) => items.push({ type: 'page', ...p }));
      if (!patientsDenied) {
        patients.forEach((p) => items.push({ type: 'patient', patient: p }));
      }
    }
    return items;
  }, [query, quickActions, recentForEmpty, pageResults, patients, patientsDenied]);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [setOpen]);

  useEffect(() => {
    if (!open) {
      setQuery('');
      setPatients([]);
      setHighlight(0);
      setSearchingPatients(false);
      return;
    }
    setRecentPages(loadRecentPages());
    const t = setTimeout(() => inputRef.current?.focus(), 50);
    return () => clearTimeout(t);
  }, [open]);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setPatients([]);
      setSearchingPatients(false);
      return undefined;
    }
    setSearchingPatients(true);
    const timer = setTimeout(async () => {
      try {
        const res = await axios.post('/api/patients/search', {
          search_term: q,
          sort_by: 'name',
          sort_order: 'asc',
        });
        setPatients((res.data?.patients || []).slice(0, 8));
        setPatientsDenied(false);
      } catch (err) {
        setPatients([]);
        if (err?.response?.status === 403) setPatientsDenied(true);
      } finally {
        setSearchingPatients(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    setHighlight(0);
  }, [query, patients, pageResults.length, quickActions.length, recentForEmpty.length]);

  const hasReceptionPatients = allPages.some((p) => p.path === '/dashboard/reception/patients');
  const patientsPath = hasReceptionPatients ? '/dashboard/reception/patients' : '/dashboard/patients';

  const goToPage = useCallback(
    (page) => {
      pushRecentPage({ text: page.text, path: page.path, section: page.section || '' });
      setOpen(false);
      navigate(page.path);
    },
    [navigate, setOpen],
  );

  const goToPatient = useCallback(
    (patient) => {
      setOpen(false);
      const uuid = patient?.patient_id;
      if (uuid) {
        navigate(`/dashboard/ehr/patient/${encodeURIComponent(uuid)}`);
        return;
      }
      navigate(patientsPath, { state: { searchPatient: patient } });
    },
    [navigate, patientsPath, setOpen],
  );

  const selectIndex = useCallback(
    (idx) => {
      const item = flatResults[idx];
      if (!item) return;
      if (item.type === 'page') goToPage(item);
      else if (item.type === 'patient') goToPatient(item.patient);
    },
    [flatResults, goToPage, goToPatient],
  );

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight((h) => (flatResults.length ? (h + 1) % flatResults.length : 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((h) =>
        flatResults.length ? (h - 1 + flatResults.length) % flatResults.length : 0,
      );
    } else if (e.key === 'Enter') {
      e.preventDefault();
      selectIndex(highlight);
    }
  };

  const isCompact = triggerVariant === 'compact' || triggerVariant === 'header-compact';
  const isSidebar = triggerVariant === 'sidebar';
  const isHeader = triggerVariant === 'header' || triggerVariant === 'header-compact';

  const defaultTriggerClass = isSidebar
    ? 'flex items-center gap-2 w-full px-3 py-2 rounded-lg text-[13px] font-medium transition-colors'
    : isHeader
      ? `inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition-colors ${
          isCompact ? '' : 'min-w-[180px] max-w-[280px]'
        }`
      : isCompact
        ? 'inline-flex items-center gap-2 rounded-md border border-border bg-white px-2.5 py-1.5 text-sm text-muted-foreground hover:bg-gray-50'
        : 'inline-flex items-center gap-2 rounded-lg border border-border bg-white/90 px-3 py-1.5 text-sm text-muted-foreground shadow-sm hover:bg-white min-w-[180px] max-w-[280px]';

  const renderPageRow = (page, idx, icon) => {
    const active = highlight === idx;
    return (
      <button
        key={`page-${page.path}-${page.text}-${idx}`}
        type="button"
        className={`w-full flex items-center gap-3 rounded-md px-2 py-2 text-left text-sm ${
          active ? 'bg-accent text-accent-foreground' : 'hover:bg-muted'
        }`}
        onMouseEnter={() => setHighlight(idx)}
        onClick={() => goToPage(page)}
      >
        {icon}
        <span className="flex-1 min-w-0">
          <span className="font-medium block truncate">{page.text}</span>
          {page.section && (
            <span className="text-xs text-muted-foreground">{page.section}</span>
          )}
        </span>
      </button>
    );
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={triggerClassName || defaultTriggerClass}
        style={
          isSidebar || isHeader
            ? {
                color: 'hsl(var(--sidebar-fg))',
                background: 'hsl(var(--sidebar-hover))',
                border: isHeader ? '1px solid hsl(var(--sidebar-border))' : undefined,
              }
            : undefined
        }
        aria-label="Open universal search"
      >
        <Search className="h-4 w-4 flex-shrink-0 opacity-70" />
        {!isCompact && (
          <span className="flex-1 text-left truncate">
            {isSidebar ? 'Search…' : 'Search pages or patients…'}
          </span>
        )}
        {isHeader && !isCompact && (
          <kbd
            className="hidden sm:inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-medium"
            style={{
              border: '1px solid hsl(var(--sidebar-border))',
              color: 'hsl(var(--sidebar-muted))',
              background: 'hsl(var(--sidebar-bg))',
            }}
          >
            ⌘K
          </kbd>
        )}
        {!isSidebar && !isHeader && (
          <kbd className="hidden sm:inline-flex items-center gap-0.5 rounded border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
            ⌘K
          </kbd>
        )}
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          formNav={false}
          className="max-w-lg p-0 gap-0 overflow-hidden top-[15%] translate-y-0 sm:rounded-xl"
        >
          <DialogHeader className="px-4 pt-4 pb-0 sr-only">
            <DialogTitle>Universal search</DialogTitle>
          </DialogHeader>
          <div className="flex items-center gap-2 border-b px-4 py-3">
            <Search className="h-4 w-4 text-muted-foreground flex-shrink-0" />
            <Input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Search pages or patients…"
              className="border-0 shadow-none focus-visible:ring-0 px-0 h-9"
            />
            {searchingPatients && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
          </div>

          <div className="max-h-[min(60vh,420px)] overflow-y-auto py-2">
            {!query.trim() && quickActions.length > 0 && (
              <div className="px-2 pb-1">
                <p className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Quick actions
                </p>
                {quickActions.map((page, i) =>
                  renderPageRow(
                    page,
                    i,
                    <Zap className="h-4 w-4 opacity-60 flex-shrink-0 text-amber-500" />,
                  ),
                )}
              </div>
            )}

            {!query.trim() && recentForEmpty.length > 0 && (
              <div className="px-2 pb-1">
                <p className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Recent
                </p>
                {recentForEmpty.map((page, i) =>
                  renderPageRow(
                    page,
                    quickActions.length + i,
                    <FileText className="h-4 w-4 opacity-60 flex-shrink-0" />,
                  ),
                )}
              </div>
            )}

            {query.trim() && pageResults.length > 0 && (
              <div className="px-2 pb-1">
                <p className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Pages
                </p>
                {pageResults.map((page, i) =>
                  renderPageRow(
                    page,
                    i,
                    <FileText className="h-4 w-4 opacity-60 flex-shrink-0" />,
                  ),
                )}
              </div>
            )}

            {query.trim() && !patientsDenied && (
              <div className="px-2 pb-1">
                <p className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Patients
                </p>
                {patients.length === 0 && !searchingPatients ? (
                  <p className="px-2 py-2 text-sm text-muted-foreground">No patients found</p>
                ) : (
                  patients.map((patient, i) => {
                    const idx = pageResults.length + i;
                    const active = highlight === idx;
                    const mrn = patient.mrn || patient.patient_id || '';
                    return (
                      <button
                        key={patient.patient_id || patient.id || i}
                        type="button"
                        className={`w-full flex items-center gap-3 rounded-md px-2 py-2 text-left text-sm ${
                          active ? 'bg-accent text-accent-foreground' : 'hover:bg-muted'
                        }`}
                        onMouseEnter={() => setHighlight(idx)}
                        onClick={() => goToPatient(patient)}
                      >
                        <User className="h-4 w-4 opacity-60 flex-shrink-0" />
                        <span className="flex-1 min-w-0">
                          <span className="font-medium block truncate">{patientDisplayName(patient)}</span>
                          <span className="text-xs text-muted-foreground truncate block">
                            {[patient.primary_phone, mrn].filter(Boolean).join(' · ')}
                          </span>
                        </span>
                      </button>
                    );
                  })
                )}
              </div>
            )}

            {query.trim() && patientsDenied && (
              <p className="px-4 py-2 text-sm text-muted-foreground">No access to patient search</p>
            )}

            {!query.trim() && quickActions.length === 0 && recentForEmpty.length === 0 && (
              <p className="px-4 py-6 text-sm text-center text-muted-foreground">
                Type to search pages or patients
              </p>
            )}

            {query.trim() && pageResults.length === 0 && patients.length === 0 && !searchingPatients && !patientsDenied && (
              <p className="px-4 py-6 text-sm text-center text-muted-foreground">
                No matching pages or patients
              </p>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
