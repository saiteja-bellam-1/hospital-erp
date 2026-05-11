import React, { useState, useEffect } from 'react';
import { Routes, Route, useLocation, useNavigate, Link } from 'react-router-dom';
import {
  Menu,
  LogOut,
  Shield,
  X,
  ChevronRight,
  ChevronDown,
  BookOpen,
  Phone,
  Monitor,
  Headphones,
  MapPin,
  Mail,
  X as XIcon,
  LayoutGrid,
} from 'lucide-react';
import axios from 'axios';

import { useAuth } from '../contexts/AuthContext';
import hospitalLogo from '../assets/Final Logo KT (1).jpg';
import DashboardHome from './modules/DashboardHome';
import HospitalAdminDashboard from './modules/HospitalAdminDashboard';
import SuperAdminDashboard from './modules/SuperAdminDashboard';
import BillingDashboard from './modules/BillingDashboard';
import AuditLogsPage from './modules/AuditLogsPage';
import SupportContactPage from './modules/SupportContactPage';
import PatientsModule from './modules/PatientsModule';
import LabModule from './modules/LabModule';
import PharmacyModule from './modules/PharmacyModule';
import BillingModule from './modules/BillingModule';
import EHRModule from './modules/EHRModule';
import OutpatientModule from './modules/OutpatientModule';
import InpatientModule from './modules/InpatientModule';
import AdminModule from './modules/AdminModule';
import HospitalAdminModule from './modules/HospitalAdminModule';
import DoctorDashboard from './modules/DoctorDashboard';
import ReceptionistDashboard from './modules/ReceptionistDashboard';
import ReceptionDashboard from './modules/reception/ReceptionDashboard';
import ReceptionPatientsPage from './modules/reception/ReceptionPatientsPage';
import ReceptionAppointmentsPage from './modules/reception/ReceptionAppointmentsPage';
import DoctorAvailabilityPage from './modules/reception/DoctorAvailabilityPage';
import ReceptionReportsPage from './modules/reception/ReceptionReportsPage';
import ReceptionPackagesPage from './modules/reception/ReceptionPackagesPage';
import ReferralManagementPage from './modules/reception/ReferralManagementPage';
import NurseDashboard from './modules/NurseDashboard';
import AvailabilityModule from './modules/AvailabilityModule';
import LabTechDashboard from './modules/LabTechDashboard';
import ConsultationPage from './modules/ConsultationPage';
import LicenseManagement from './modules/LicenseManagement';
import BackupManagement from './modules/BackupManagement';
import LicenseBanner from '../components/LicenseBanner';
import BackupHealthBanner from '../components/BackupHealthBanner';
import { useNavigationSections } from '../hooks/useNavigationSections';
import HomeGrid from './modules/HomeGrid';

const HomeDashboard = ({ hasRole, enabledModules }) => {
  // Priority-based: show the most relevant dashboard for the user
  if (hasRole('super_admin')) return <SuperAdminDashboard />;
  if (hasRole('hospital_admin')) return <HospitalAdminDashboard />;
  if (hasRole('doctor') && enabledModules.outpatient) return <DoctorDashboard />;
  if (hasRole('lab_admin') || hasRole('lab_technician')) return <LabTechDashboard />;
  if (hasRole('receptionist') && enabledModules.outpatient) return <ReceptionDashboard />;
  if (hasRole('receptionist') && enabledModules.lab) return <LabTechDashboard />;
  if (hasRole('nurse')) return <NurseDashboard />;
  return <DashboardHome />;
};

const Dashboard = () => {
  const { user, logout, licenseStatus, setLicenseStatus } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showSupportPopup, setShowSupportPopup] = useState(false);
  const [pwaInstallPrompt, setPwaInstallPrompt] = useState(null);
  const [appVersion, setAppVersion] = useState('');

  // Capture the PWA install prompt
  useEffect(() => {
    const handler = (e) => {
      e.preventDefault();
      setPwaInstallPrompt(e);
    };
    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);
  const [enabledModules, setEnabledModules] = useState({});
  const location = useLocation();
  const navigate = useNavigate();

  // Sidebar section collapse state — persisted per user in localStorage.
  // Map of { [sectionLabel]: boolean (true = collapsed) }. Sections not in the map default to expanded.
  const SIDEBAR_STATE_KEY = 'sidebar_section_state_v1';
  const [collapsedSections, setCollapsedSections] = useState(() => {
    try {
      const raw = localStorage.getItem(SIDEBAR_STATE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  });
  useEffect(() => {
    try { localStorage.setItem(SIDEBAR_STATE_KEY, JSON.stringify(collapsedSections)); } catch { /* ignore */ }
  }, [collapsedSections]);
  const toggleSection = (label) => {
    setCollapsedSections(prev => ({ ...prev, [label]: !prev[label] }));
  };

  useEffect(() => {
    const fetchEnabledModules = async () => {
      try {
        const response = await axios.get('/api/system/enabled-modules');
        const moduleMap = {};
        response.data.forEach(module => {
          moduleMap[module.module_name] = module.is_enabled;
        });
        setEnabledModules(moduleMap);
      } catch (error) {
        console.error('Failed to fetch enabled modules:', error);
        setEnabledModules({
          outpatient: false,
          inpatient: false,
          lab: false,
          pharmacy: false,
          ehr: false,
          billing: true,
          admin: true
        });
      }
    };

    const refreshLicenseStatus = async () => {
      try {
        const res = await axios.get('/api/license/status');
        setLicenseStatus(res.data);
        localStorage.setItem('licenseStatus', JSON.stringify(res.data));
      } catch {}
    };

    if (user) {
      fetchEnabledModules();
      refreshLicenseStatus();
      axios.get('/api/system/version').then(r => setAppVersion(r.data.version)).catch(() => {});
    }
  }, [user]);

  // Close sidebar on route change (mobile)
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  // Multi-role helper
  const roles = user.roles || [user.role];
  const hasRole = (r) => roles.includes(r);
  const hasAnyRole = (...r) => r.some(x => roles.includes(x));

  const getRoleLabel = () => {
    const labels = {
      super_admin: 'Super Admin',
      hospital_admin: 'Hospital Admin',
      doctor: 'Doctor',
      receptionist: 'Receptionist',
      lab_technician: 'Lab Technician',
      lab_admin: 'Lab Admin',
      nurse: 'Nurse',
    };
    return roles.map(r => labels[r] || r).join(', ') || 'Staff';
  };

  // Navigation sections — single source of truth shared with HomeGrid (see hooks/useNavigationSections.js).
  const { sections: navigationSections } = useNavigationSections({ roles, enabledModules });

  const isActive = (path) => {
    if (path === '/dashboard') return location.pathname === '/dashboard';
    return location.pathname.startsWith(path);
  };

  // When the route changes, auto-open the section that contains the active item
  // so the user always sees where they are. We never auto-collapse — user toggles win.
  useEffect(() => {
    const activeSectionLabel = navigationSections.find(sec =>
      sec.items.some(item => isActive(item.path))
    )?.label;
    if (activeSectionLabel && collapsedSections[activeSectionLabel]) {
      setCollapsedSections(prev => ({ ...prev, [activeSectionLabel]: false }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const userInitials = user.full_name
    ? user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : 'U';

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'hsl(var(--background))' }}>
      {/* Sidebar */}
      <aside className={`
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        fixed inset-y-0 left-0 z-50 w-[260px] flex flex-col
        transform transition-transform duration-300 ease-in-out
        lg:translate-x-0 lg:static lg:inset-0
      `}
        style={{
          background: 'hsl(var(--sidebar-bg))',
          borderRight: '1px solid hsl(var(--sidebar-border))',
        }}
      >
        {/* Logo area */}
        <div className="flex items-center justify-between h-16 px-5 flex-shrink-0"
          style={{ borderBottom: '1px solid hsl(var(--sidebar-border))' }}
        >
          <div className="flex items-center gap-2">
            <img
              src={hospitalLogo}
              alt="KT Health Soft"
              className="h-9 w-auto max-w-[180px] rounded"
              style={{ filter: 'brightness(1.1) contrast(1.05)' }}
            />
          </div>
          <button
            className="lg:hidden p-1 rounded-md hover:bg-white/10 transition-colors"
            style={{ color: 'hsl(var(--sidebar-fg))' }}
            onClick={() => setSidebarOpen(false)}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Navigation */}
        <nav className="sidebar-nav flex-1 overflow-y-auto py-4 px-3">
          {navigationSections.map((section, sIdx) => {
            // Sections without a label (e.g. Home) stay flat — no header, always visible.
            const isCollapsible = !!section.label;
            const isCollapsed = isCollapsible && !!collapsedSections[section.label];
            return (
              <div key={section.label || `section-${sIdx}`} className={sIdx > 0 ? 'mt-3' : ''}>
                {isCollapsible && (
                  <button
                    type="button"
                    onClick={() => toggleSection(section.label)}
                    className="w-full flex items-center justify-between px-3 mb-1 py-1.5 rounded-md text-[11px] font-semibold tracking-wider uppercase transition-colors"
                    style={{ color: 'hsl(var(--sidebar-muted))' }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = 'hsl(var(--sidebar-hover))'; e.currentTarget.style.color = '#fff'; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'hsl(var(--sidebar-muted))'; }}
                  >
                    <span>{section.label}</span>
                    {isCollapsed
                      ? <ChevronRight className="h-3.5 w-3.5 opacity-70" />
                      : <ChevronDown className="h-3.5 w-3.5 opacity-70" />}
                  </button>
                )}
                {!isCollapsed && (
                  <div className="space-y-0.5">
                    {section.items.map((item) => {
                      const active = isActive(item.path);
                      return (
                        <Link
                          key={item.text}
                          to={item.path}
                          className={`
                            group flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13.5px] font-medium
                            transition-all duration-150 relative
                            ${active ? 'nav-item-active' : ''}
                          `}
                          style={{
                            color: active ? '#fff' : 'hsl(var(--sidebar-fg))',
                            background: active ? 'hsl(var(--sidebar-active))' : 'transparent',
                          }}
                          onMouseEnter={(e) => {
                            if (!active) {
                              e.currentTarget.style.background = 'hsl(var(--sidebar-hover))';
                              e.currentTarget.style.color = '#fff';
                            }
                          }}
                          onMouseLeave={(e) => {
                            if (!active) {
                              e.currentTarget.style.background = 'transparent';
                              e.currentTarget.style.color = 'hsl(var(--sidebar-fg))';
                            }
                          }}
                        >
                          <span className="flex-shrink-0 opacity-80 group-hover:opacity-100" style={active ? { opacity: 1 } : {}}>
                            {item.icon}
                          </span>
                          <span className="truncate">{item.text}</span>
                          {active && (
                            <ChevronRight className="h-3.5 w-3.5 ml-auto opacity-60" />
                          )}
                        </Link>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* Separator */}
        <div className="mx-3 my-1" style={{ borderTop: '1px solid hsl(var(--sidebar-border))' }} />

        {/* Help link */}
        <div className="px-3 pb-1">
          <Link
            to="/help/docs"
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-all duration-150"
            style={{ color: 'hsl(var(--sidebar-fg))' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'hsl(var(--sidebar-hover))';
              e.currentTarget.style.color = '#fff';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.color = 'hsl(var(--sidebar-fg))';
            }}
          >
            <BookOpen className="h-[18px] w-[18px] opacity-80" />
            <span>Help & Docs</span>
          </Link>
        </div>

        {/* Add to Desktop */}
        <div className="px-3 pb-1">
          <button
            onClick={async () => {
              if (pwaInstallPrompt) {
                pwaInstallPrompt.prompt();
                const result = await pwaInstallPrompt.userChoice;
                if (result.outcome === 'accepted') setPwaInstallPrompt(null);
              } else {
                const link = document.createElement('a');
                link.href = '/api/system/desktop-shortcut';
                link.download = 'KT HEALTH ERP.url';
                link.click();
              }
            }}
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-all duration-150 w-full"
            style={{ color: 'hsl(var(--sidebar-fg))' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'hsl(var(--sidebar-hover))';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
            }}
          >
            <Monitor className="h-[18px] w-[18px] opacity-80" />
            <span>Add to Desktop</span>
          </button>
        </div>

        {/* Logout button */}
        <div className="px-3 pb-1">
          <button
            onClick={logout}
            className="flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-all duration-150 w-full"
            style={{ color: 'hsl(var(--sidebar-fg))' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'hsla(0, 70%, 50%, 0.25)';
              e.currentTarget.style.color = '#fca5a5';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.color = 'hsl(var(--sidebar-fg))';
            }}
          >
            <LogOut className="h-[18px] w-[18px] opacity-80" />
            <span>Log out</span>
          </button>
        </div>

        {/* User info at bottom of sidebar */}
        <div className="flex-shrink-0 p-3" style={{ borderTop: '1px solid hsl(var(--sidebar-border))' }}>
          <div className="flex items-center gap-3 px-2 py-2 rounded-lg"
            style={{ background: 'hsl(var(--sidebar-hover))' }}
          >
            <div
              className="h-8 w-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
              style={{
                background: 'hsl(var(--sidebar-active))',
                color: '#fff',
              }}
            >
              {userInitials}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate" style={{ color: '#fff' }}>
                {user.full_name}
              </p>
              <p className="text-[11px] truncate" style={{ color: 'hsl(var(--sidebar-muted))' }}>
                {getRoleLabel()}
              </p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* License Banner */}
        <LicenseBanner licenseStatus={licenseStatus} />
        <BackupHealthBanner />

        {/* Mobile menu button */}
        <div className="lg:hidden flex items-center h-12 px-4 flex-shrink-0 bg-white border-b border-border">
          <button
            className="p-2 -ml-2 rounded-lg hover:bg-gray-100 transition-colors"
            onClick={() => setSidebarOpen(true)}
          >
            <Menu className="h-5 w-5 text-gray-600" />
          </button>
        </div>

        {/* Page content */}
        <main className={`flex-1 overflow-y-auto ${(location.pathname.startsWith('/dashboard/inpatient') || location.pathname === '/dashboard/home') ? '' : 'p-4 lg:p-6'}`}>
          {hasAnyRole('hospital_admin', 'receptionist') && licenseStatus?.days_remaining != null && (
            <div className="flex items-center justify-end gap-1.5 text-xs mb-4">
              <Shield className="h-3.5 w-3.5 text-gray-400" />
              <span className="text-gray-400">License:</span>
              <span className={`font-semibold ${
                licenseStatus.days_remaining > 30 ? 'text-green-600' :
                licenseStatus.days_remaining > 0 ? 'text-amber-600' :
                'text-red-600'
              }`}>
                {licenseStatus.days_remaining > 0
                  ? `${licenseStatus.days_remaining} days remaining`
                  : licenseStatus.status === 'grace_period'
                    ? `Grace period — ${Math.abs(licenseStatus.days_remaining)} days overdue`
                    : 'Expired'
                }
              </span>
              {licenseStatus.expires_at && (
                <span className="text-gray-400">
                  (expires {new Date(licenseStatus.expires_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })})
                </span>
              )}
            </div>
          )}
          <Routes>
            <Route
              path="/"
              element={
                <HomeDashboard hasRole={hasRole} enabledModules={enabledModules} />
              }
            />
            <Route
              path="/home"
              element={
                <HomeGrid
                  enabledModules={enabledModules}
                  pwaInstallPrompt={pwaInstallPrompt}
                  onOpenSupport={() => setShowSupportPopup(true)}
                />
              }
            />
            <Route path="/reception/patients" element={<ReceptionPatientsPage />} />
            <Route path="/reception/appointments" element={<ReceptionAppointmentsPage />} />
            <Route path="/reception/doctor-availability" element={<DoctorAvailabilityPage />} />
            <Route path="/reception/reports" element={<ReceptionReportsPage />} />
            <Route path="/reception/packages" element={<ReceptionPackagesPage />} />
            <Route path="/reception/referrals" element={<ReferralManagementPage />} />
            <Route path="/patients/*" element={<PatientsModule />} />
            <Route path="/lab/*" element={<LabModule />} />
            <Route path="/pharmacy/*" element={<PharmacyModule />} />
            <Route path="/billing/*" element={<BillingModule />} />
            <Route path="/ehr/*" element={<EHRModule />} />
            <Route path="/consultation" element={<ConsultationPage />} />
            <Route path="/availability/*" element={<AvailabilityModule />} />
            <Route path="/outpatient/*" element={hasRole('doctor') ? <DoctorDashboard /> : <OutpatientModule />} />
            <Route path="/inpatient/*" element={<InpatientModule />} />
            <Route path="/admin/*" element={<AdminModule />} />
            <Route path="/hospital-admin/*" element={<HospitalAdminModule />} />
            <Route path="/license" element={<LicenseManagement />} />
            <Route path="/backup" element={<BackupManagement />} />
            <Route path="/billing-dashboard" element={<BillingDashboard />} />
            <Route path="/audit" element={<AuditLogsPage />} />
            <Route path="/support-contact" element={
              <SupportContactPage sellerInfo={licenseStatus?.seller_info} />
            } />
          </Routes>
        </main>

        {/* Footer — pinned to bottom of content area */}
        <footer className="flex-shrink-0 py-2 text-center text-xs text-gray-400 bg-white border-t border-gray-100">
          Powered by <span className="font-medium text-gray-500">KT HEALTH ERP</span>
          {licenseStatus?.seller_info?.name
            ? <> &mdash; Sold by <span className="font-medium text-gray-500">{licenseStatus.seller_info.name}</span></>
            : <> &mdash; Developed by KT Health Soft</>
          }
        </footer>
      </div>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Floating Menu Grid Button — sits above the support button */}
      <div className="fixed bottom-24 right-6 z-50 group">
        <button
          onClick={() => navigate('/dashboard/home')}
          aria-label="All Menus"
          className="h-14 w-14 rounded-full shadow-lg flex items-center justify-center transition-all duration-200 bg-emerald-600 hover:bg-emerald-700 hover:scale-105"
        >
          <LayoutGrid className="h-6 w-6 text-white" />
        </button>
        <span className="pointer-events-none absolute right-16 top-1/2 -translate-y-1/2 whitespace-nowrap rounded-md bg-gray-900 px-2 py-1 text-xs text-white opacity-0 group-hover:opacity-100 transition-opacity">
          All Menus
        </span>
      </div>

      {/* Floating Support Button */}
      <div className="fixed bottom-6 right-6 z-50">
        {/* Popup */}
        {showSupportPopup && (
          <>
            <div className="fixed inset-0" onClick={() => setShowSupportPopup(false)} />
            <div className="absolute bottom-16 right-0 w-80 bg-white rounded-2xl shadow-2xl border border-gray-200 overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-200">
              <div className="bg-blue-600 px-5 py-4 flex items-center justify-between">
                <div>
                  <h3 className="text-white font-semibold text-sm">Support Contact</h3>
                  <p className="text-blue-200 text-xs mt-0.5">We're here to help</p>
                </div>
                <button onClick={() => setShowSupportPopup(false)} className="text-white/70 hover:text-white">
                  <XIcon className="h-4 w-4" />
                </button>
              </div>
              <div className="p-4 space-y-4 max-h-[60vh] overflow-y-auto">
                {/* Vendor section */}
                {licenseStatus?.seller_info?.name && (
                  <div className="space-y-2.5">
                    <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Your Vendor</p>
                    <div className="bg-gray-50 rounded-xl p-3.5 space-y-2">
                      <p className="font-semibold text-sm text-gray-900">{licenseStatus.seller_info.name}</p>
                      {licenseStatus.seller_info.address && (
                        <div className="flex items-start gap-2">
                          <MapPin className="h-3.5 w-3.5 text-gray-400 mt-0.5 flex-shrink-0" />
                          <p className="text-xs text-gray-600">{licenseStatus.seller_info.address}</p>
                        </div>
                      )}
                      {licenseStatus.seller_info.phone && (
                        <div className="flex items-center gap-2">
                          <Phone className="h-3.5 w-3.5 text-gray-400 flex-shrink-0" />
                          <a href={`tel:${licenseStatus.seller_info.phone}`} className="text-xs text-blue-600 font-medium hover:underline">{licenseStatus.seller_info.phone}</a>
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* KT Health section */}
                <div className="space-y-2.5">
                  <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                    {licenseStatus?.seller_info?.name ? 'Product Support' : 'Support'}
                  </p>
                  <div className="bg-gray-50 rounded-xl p-3.5 space-y-2">
                    <p className="font-semibold text-sm text-gray-900">KT Health Soft</p>
                    <div className="flex items-center gap-2">
                      <Phone className="h-3.5 w-3.5 text-gray-400 flex-shrink-0" />
                      <a href="tel:+919876543210" className="text-xs text-blue-600 font-medium hover:underline">+91 98765 43210</a>
                    </div>
                    <div className="flex items-center gap-2">
                      <Mail className="h-3.5 w-3.5 text-gray-400 flex-shrink-0" />
                      <a href="mailto:support@kthealthsoft.com" className="text-xs text-blue-600 font-medium hover:underline">support@kthealthsoft.com</a>
                    </div>
                  </div>
                </div>

                {/* Version */}
                {appVersion && (
                  <p className="text-center text-[10px] text-gray-400 pt-2 border-t border-gray-100">
                    KT HEALTH ERP v{appVersion}
                  </p>
                )}
              </div>
            </div>
          </>
        )}

        {/* Floating button */}
        <button
          onClick={() => setShowSupportPopup(!showSupportPopup)}
          className={`h-14 w-14 rounded-full shadow-lg flex items-center justify-center transition-all duration-200 ${
            showSupportPopup
              ? 'bg-gray-600 hover:bg-gray-700 rotate-0'
              : 'bg-blue-600 hover:bg-blue-700 hover:scale-105'
          }`}
        >
          {showSupportPopup
            ? <XIcon className="h-6 w-6 text-white" />
            : <Headphones className="h-6 w-6 text-white" />
          }
        </button>
      </div>
    </div>
  );
};

export default Dashboard;
