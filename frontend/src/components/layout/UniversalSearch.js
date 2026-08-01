import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { FileText, Loader2, Search, User } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Input } from '../ui/input';

const RECENT_PAGES_KEY = 'universal_search_recent_pages_v1';
const MAX_RECENT = 5;

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

/**
 * Cmd/Ctrl+K command palette: nav pages + patient search.
 */
export default function UniversalSearch({
  navigationSections = [],
  open: controlledOpen,
  onOpenChange,
  triggerClassName = '',
  triggerVariant = 'default',
}) {
  const navigate = useNavigate();
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

  const emptyQueryPages = useMemo(() => {
    if (recentPages.length > 0) {
      return recentPages.filter((r) => allPages.some((p) => p.path === r.path)).slice(0, MAX_RECENT);
    }
    return allPages.slice(0, 5);
  }, [recentPages, allPages]);

  const pageResults = query.trim() ? filteredPages : emptyQueryPages;

  const flatResults = useMemo(() => {
    const items = [];
    pageResults.forEach((p) => items.push({ type: 'page', ...p }));
    if (query.trim() && !patientsDenied) {
      patients.forEach((p) => items.push({ type: 'patient', patient: p }));
    }
    return items;
  }, [pageResults, patients, query, patientsDenied]);

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
  }, [query, patients, pageResults.length]);

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
            {pageResults.length > 0 && (
              <div className="px-2 pb-1">
                <p className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {query.trim() ? 'Pages' : recentPages.length ? 'Recent' : 'Pages'}
                </p>
                {pageResults.map((page, i) => {
                  const idx = i;
                  const active = highlight === idx;
                  return (
                    <button
                      key={`page-${page.path}-${page.text}`}
                      type="button"
                      className={`w-full flex items-center gap-3 rounded-md px-2 py-2 text-left text-sm ${
                        active ? 'bg-accent text-accent-foreground' : 'hover:bg-muted'
                      }`}
                      onMouseEnter={() => setHighlight(idx)}
                      onClick={() => goToPage(page)}
                    >
                      <FileText className="h-4 w-4 opacity-60 flex-shrink-0" />
                      <span className="flex-1 min-w-0">
                        <span className="font-medium block truncate">{page.text}</span>
                        {page.section && (
                          <span className="text-xs text-muted-foreground">{page.section}</span>
                        )}
                      </span>
                    </button>
                  );
                })}
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

            {!query.trim() && pageResults.length === 0 && (
              <p className="px-4 py-6 text-sm text-center text-muted-foreground">
                Type to search pages or patients
              </p>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
