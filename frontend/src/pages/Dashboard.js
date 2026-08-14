import React, { useState, useEffect } from 'react';
import { Routes, Route, useLocation, Navigate } from 'react-router-dom';
import {
  Shield,
  Phone,
  Headphones,
  MapPin,
  Mail,
  X as XIcon,
  Wifi,
  Menu,
} from 'lucide-react';
import axios from 'axios';

import { useAuth } from '../contexts/AuthContext';
import {
  LayoutPreferencesProvider,
  useLayoutPreferences,
} from '../contexts/LayoutPreferencesContext';
import AppSidebar from '../components/layout/AppSidebar';
import AppHeader from '../components/layout/AppHeader';
import DashboardHome from './modules/DashboardHome';
import HospitalAdminDashboard from './modules/HospitalAdminDashboard';
import SuperAdminDashboard from './modules/SuperAdminDashboard';
import AuditLogsPage from './modules/AuditLogsPage';
import SupportContactPage from './modules/SupportContactPage';
import PatientsModule from './modules/PatientsModule';
import LabModule from './modules/LabModule';
import PharmacyModule from './modules/PharmacyModule';
import CanteenModule from './modules/CanteenModule';
import PhysiotherapyModule from './modules/PhysiotherapyModule';
import BillingModule from './modules/BillingModule';
import EHRModule from './modules/EHRModule';
import OutpatientModule from './modules/OutpatientModule';
import InpatientModule from './modules/InpatientModule';
import AdminModule from './modules/AdminModule';
import HospitalAdminModule from './modules/HospitalAdminModule';
import CatchUpBills from './modules/admin/CatchUpBills';
import SettlementsPage from './modules/admin/SettlementsPage';
import PrintSettingsPage from './modules/PrintSettingsPage';
import DoctorDashboard from './modules/DoctorDashboard';
import ReceptionDashboard from './modules/reception/ReceptionDashboard';
import ReceptionPatientsPage from './modules/reception/ReceptionPatientsPage';
import ReceptionAppointmentsPage from './modules/reception/ReceptionAppointmentsPage';
import DoctorAvailabilityPage from './modules/reception/DoctorAvailabilityPage';
import ReceptionReportsPage from './modules/reception/ReceptionReportsPage';
import ReceptionPackagesPage from './modules/reception/ReceptionPackagesPage';
import ProceduresBillingPage from './modules/reception/ProceduresBillingPage';
import ReferralManagementPage from './modules/reception/ReferralManagementPage';
import ReceptionLabOrdersPage from './modules/reception/ReceptionLabOrdersPage';
import NurseDashboard from './modules/NurseDashboard';
import AvailabilityModule from './modules/AvailabilityModule';
import LabTechDashboard from './modules/LabTechDashboard';
import ConsultationPage from './modules/ConsultationPage';
import LicenseManagement from './modules/LicenseManagement';
import BackupManagement from './modules/BackupManagement';
import SoftwareUpdate from './modules/SoftwareUpdate';
import LicenseBanner from '../components/LicenseBanner';
import BackupHealthBanner from '../components/BackupHealthBanner';
import SetupProgressBanner from '../components/SetupProgressBanner';
import { useNavigationSections, normalizeUserRoles, canAccessLabAdminDashboard } from '../hooks/useNavigationSections';
import HomeGrid from './modules/HomeGrid';
import SetupWizard from './setup/SetupWizard';

const HomeDashboard = ({ hasRole, enabledModules }) => {
  // Priority-based: show the most relevant dashboard for the user
  if (hasRole('super_admin')) return <SuperAdminDashboard />;
  if (hasRole('hospital_admin')) return <HospitalAdminDashboard />;
  // Doctors always get their dashboard (same pattern as lab staff below).
  if (hasRole('doctor')) return <DoctorDashboard />;
  if (hasRole('lab_admin') || hasRole('lab_technician')) return <LabTechDashboard />;
  if (hasRole('receptionist') && enabledModules.outpatient) return <ReceptionDashboard />;
  if (hasRole('receptionist') && enabledModules.lab) return <LabTechDashboard />;
  if (hasRole('physiotherapist') && enabledModules.physiotherapy) {
    return <Navigate to="/dashboard/physiotherapy/today" replace />;
  }
  if (hasRole('nurse')) return <NurseDashboard />;
  return <DashboardHome />;
};

const DashboardShell = () => {
  const { user, logout, licenseStatus, setLicenseStatus } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showSupportPopup, setShowSupportPopup] = useState(false);
  const [pwaInstallPrompt, setPwaInstallPrompt] = useState(null);
  const [appVersion, setAppVersion] = useState('');
  const [networkInfo, setNetworkInfo] = useState(null);

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

  // Sidebar section collapse state — persisted per user in localStorage.
  // Map of { [sectionLabel]: boolean }. true => collapsed, false => user expanded.
  // Default behaviour: sections are *collapsed* unless explicitly opened by the
  // user OR the user navigates to a page inside the section (auto-open below).
  // Bumped key to v2 to ignore any stale all-expanded state in old browsers.
  const SIDEBAR_STATE_KEY = 'sidebar_section_state_v2';
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
    // Treat anything not explicitly `false` as currently collapsed, so the
    // first click should expand (set to false), not collapse-again.
    setCollapsedSections(prev => ({
      ...prev,
      [label]: prev[label] === false ? true : false,
    }));
  };

  useEffect(() => {
    if (!user) return;
    const roleList = (() => {
      const r = user?.roles;
      if (Array.isArray(r) && r.length > 0) {
        return r.map((x) => (typeof x === 'string' ? x : x?.name)).filter(Boolean);
      }
      return user?.role ? [user.role] : [];
    })();
    if (roleList.some((name) => name === 'lab_admin' || name === 'lab_technician')) {
      setEnabledModules((prev) => ({ ...prev, lab: true }));
    }
    if (roleList.some((name) => name === 'doctor')) {
      setEnabledModules((prev) => ({ ...prev, outpatient: true }));
    }
  }, [user]);

  useEffect(() => {
    const fetchEnabledModules = async () => {
      try {
        const response = await axios.get('/api/system/enabled-modules');
        const moduleMap = {};
        response.data.forEach(module => {
          moduleMap[module.module_name] = module.is_enabled;
        });
        // billing + admin aren't toggleable — they're always on. If the API
        // didn't include them as rows, treat them as enabled so nav items
        // gated on enabledModules.billing don't silently disappear.
        if (moduleMap.billing === undefined) moduleMap.billing = true;
        if (moduleMap.admin === undefined) moduleMap.admin = true;
        // Lab staff must always see lab navigation even while modules are loading.
        const r = user?.roles;
        const roleList = Array.isArray(r) && r.length > 0
          ? r.map((x) => (typeof x === 'string' ? x : x?.name)).filter(Boolean)
          : (user?.role ? [user.role] : []);
        if (roleList.some((name) => name === 'lab_admin' || name === 'lab_technician')) {
          moduleMap.lab = true;
        }
        if (roleList.some((name) => name === 'doctor')) {
          moduleMap.outpatient = true;
        }
        setEnabledModules(moduleMap);
      } catch (error) {
        console.error('Failed to fetch enabled modules:', error);
        const roleList = (() => {
          const r = user?.roles;
          if (Array.isArray(r) && r.length > 0) {
            return r.map((x) => (typeof x === 'string' ? x : x?.name)).filter(Boolean);
          }
          return user?.role ? [user.role] : [];
        })();
        const isLabStaff = roleList.some((name) => name === 'lab_admin' || name === 'lab_technician');
        const isDoctor = roleList.some((name) => name === 'doctor');
        setEnabledModules({
          outpatient: isDoctor,
          inpatient: false,
          lab: isLabStaff,
          pharmacy: false,
          ehr: false,
          billing: true,
          admin: true
        });
      }
    };

    const refreshLicenseStatus = async () => {
      try {
        const roleList = normalizeUserRoles(user);
        const isLicenseAdmin = roleList.some(
          (r) => r === 'super_admin' || r === 'hospital_admin',
        );
        // Full /status is admin-only; other roles must use the public endpoint
        // or the footer/banner lose days_remaining after refresh fails with 403.
        if (isLicenseAdmin) {
          const res = await axios.get('/api/license/status');
          setLicenseStatus(res.data);
          localStorage.setItem('licenseStatus', JSON.stringify(res.data));
        } else {
          const res = await axios.get('/api/license/status/public');
          setLicenseStatus((prev) => {
            const next = {
              ...(prev || {}),
              ...res.data,
              seller_info: res.data.seller_info ?? prev?.seller_info ?? null,
              expires_at: res.data.expires_at ?? prev?.expires_at ?? null,
            };
            try {
              localStorage.setItem('licenseStatus', JSON.stringify(next));
            } catch { /* ignore */ }
            return next;
          });
        }
      } catch { /* keep existing licenseStatus from login */ }
    };

    if (user) {
      fetchEnabledModules();
      refreshLicenseStatus();
      axios.get('/api/system/version').then(r => setAppVersion(r.data.version)).catch(() => {});
    }
  }, [user]);

  useEffect(() => {
    if (showSupportPopup && !networkInfo) {
      axios.get('/api/system/network-info').then(r => setNetworkInfo(r.data)).catch(() => {});
    }
  }, [showSupportPopup, networkInfo]);

  // Close sidebar on route change (mobile)
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  const roles = normalizeUserRoles(user);
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
    // Sections are collapsed by default (anything not explicitly `false`).
    // When the user lands on a page inside a section, mark that section
    // expanded so they can see siblings.
    if (activeSectionLabel && collapsedSections[activeSectionLabel] !== false) {
      setCollapsedSections(prev => ({ ...prev, [activeSectionLabel]: false }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const userInitials = user.full_name
    ? user.full_name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2)
    : 'U';

  const { navLayout } = useLayoutPreferences();
  const isHeaderMode = navLayout === 'header';

  const sidebarProps = {
    sidebarOpen,
    onClose: () => setSidebarOpen(false),
    navigationSections,
    collapsedSections,
    onToggleSection: toggleSection,
    isActive,
    hideOnDesktop: isHeaderMode,
    showSearch: !isHeaderMode,
    pwaInstallPrompt,
    setPwaInstallPrompt,
    logout,
    user,
    userInitials,
    roleLabel: getRoleLabel(),
  };

  return (
    <div
      className={`h-screen overflow-hidden ${isHeaderMode ? 'flex flex-col' : 'flex'}`}
      style={{ background: 'hsl(var(--background))' }}
    >
      {isHeaderMode && (
        <AppHeader
          navigationSections={navigationSections}
          isActive={isActive}
          onOpenMobileMenu={() => setSidebarOpen(true)}
          logout={logout}
          user={user}
          userInitials={userInitials}
          roleLabel={getRoleLabel()}
        />
      )}

      <div className="flex flex-1 min-h-0 min-w-0">
        <AppSidebar {...sidebarProps} />

        {/* Main content area */}
        <div className="flex-1 flex flex-col min-w-0">
          <LicenseBanner licenseStatus={licenseStatus} />
          <BackupHealthBanner />
          {hasAnyRole('super_admin', 'hospital_admin') && <SetupProgressBanner />}

          {/* Mobile menu button — sidebar mode only (header mode uses AppHeader hamburger) */}
          {!isHeaderMode && (
            <div className="lg:hidden flex items-center h-12 px-4 flex-shrink-0 bg-white border-b border-border">
              <button
                type="button"
                className="p-2 -ml-2 rounded-lg hover:bg-gray-100 transition-colors"
                onClick={() => setSidebarOpen(true)}
              >
                <Menu className="h-5 w-5 text-gray-600" />
              </button>
            </div>
          )}

          {/* Page content */}
          <main className={`flex-1 min-h-0 ${
            location.pathname.includes('/pharmacy/sales-counter')
              ? 'overflow-hidden flex flex-col'
              : 'overflow-y-auto'
          } ${(location.pathname.startsWith('/dashboard/inpatient') || location.pathname === '/dashboard/home' || location.pathname.includes('/pharmacy/sales-counter')) ? '' : 'p-4 lg:p-6'}`}>
            <div className={location.pathname.includes('/pharmacy/sales-counter') ? 'flex-1 min-h-0 flex flex-col overflow-hidden' : undefined}>
            <Routes>
              <Route
                path="/"
                element={
                  <HomeDashboard hasRole={hasRole} enabledModules={enabledModules} />
                }
              />
              {/* Per-role dashboards — surfaced as separate sidebar items when a
                  user has more than one role-dashboard, so neither one is hidden
                  behind the priority fallback at /dashboard. */}
              <Route path="/admin-home" element={<SuperAdminDashboard />} />
              <Route path="/hospital-admin-home" element={<HospitalAdminDashboard />} />
              <Route path="/doctor-home" element={<DoctorDashboard />} />
              <Route path="/lab-home" element={<LabTechDashboard />} />
              <Route path="/reception-home" element={<ReceptionDashboard />} />
              <Route path="/nurse-home" element={<NurseDashboard />} />
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
              <Route path="/reception/lab-orders" element={<ReceptionLabOrdersPage />} />
              <Route path="/reception/procedures" element={<ProceduresBillingPage />} />
              <Route path="/reception/referrals" element={<ReferralManagementPage />} />
              <Route path="/patients/*" element={<PatientsModule />} />
              <Route
                path="lab/*"
                element={
                  canAccessLabAdminDashboard(roles)
                    ? <LabModule />
                    : <Navigate to="/dashboard/lab-home" replace />
                }
              />
              <Route path="/pharmacy/*" element={<PharmacyModule />} />
              <Route path="/canteen/*" element={<CanteenModule />} />
              <Route path="/physiotherapy/*" element={<PhysiotherapyModule />} />
              <Route path="/billing/*" element={<BillingModule />} />
              <Route path="/ehr/*" element={<EHRModule />} />
              <Route path="/consultation" element={<ConsultationPage />} />
              <Route path="/availability/*" element={<AvailabilityModule />} />
              <Route path="/outpatient/*" element={hasRole('doctor') ? <DoctorDashboard /> : <OutpatientModule />} />
              <Route path="/inpatient/*" element={<InpatientModule />} />
              <Route path="/admin/*" element={<AdminModule />} />
              <Route path="/hospital-admin/*" element={<HospitalAdminModule />} />
              <Route path="/setup" element={
                hasAnyRole('super_admin', 'hospital_admin')
                  ? <SetupWizard />
                  : <Navigate to="/dashboard/home" replace />
              } />
              <Route path="/settlements" element={<SettlementsPage />} />
              <Route path="/catch-up" element={<CatchUpBills />} />
              <Route path="/print-settings" element={<PrintSettingsPage />} />
              <Route path="/license" element={<LicenseManagement />} />
              <Route path="/backup" element={<BackupManagement />} />
              <Route path="/software-update" element={<SoftwareUpdate />} />
              <Route path="/audit" element={<AuditLogsPage />} />
              <Route path="/support-contact" element={
                <SupportContactPage sellerInfo={licenseStatus?.seller_info} />
              } />
            </Routes>
            </div>
          </main>

          <footer className="flex-shrink-0 py-2 px-3 text-center text-xs text-gray-400 bg-white border-t border-gray-100 flex flex-wrap items-center justify-center gap-x-2 gap-y-1">
            <span>
              Powered by <span className="font-medium text-gray-500">KT HEALTH ERP</span>
              {licenseStatus?.seller_info?.name
                ? <> &mdash; Sold by <span className="font-medium text-gray-500">{licenseStatus.seller_info.name}</span></>
                : <> &mdash; Developed by KT Health Soft</>
              }
            </span>
            {licenseStatus?.days_remaining != null && (
              <span className="inline-flex items-center gap-1.5">
                <span className="text-gray-300" aria-hidden>·</span>
                <Shield className="h-3 w-3 text-gray-400" />
                <span>License:</span>
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
                  <span>
                    (expires {new Date(licenseStatus.expires_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })})
                  </span>
                )}
              </span>
            )}
          </footer>
        </div>
      </div>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Floating Support Button */}
      <div className="fixed bottom-6 right-6 z-50">
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

                {networkInfo?.ips?.length > 0 && (
                  <div className="space-y-2.5">
                    <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Network Access</p>
                    <div className="bg-blue-50 rounded-xl p-3.5 space-y-1.5">
                      <p className="text-xs text-gray-500 mb-2">Other devices on this network can open the app at:</p>
                      {networkInfo.ips.map(ip => (
                        <div key={ip} className="flex items-center gap-2">
                          <Wifi className="h-3.5 w-3.5 text-blue-500 flex-shrink-0" />
                          <code className="text-xs font-mono font-semibold text-blue-700 select-all">
                            http://{ip}:{networkInfo.port}
                          </code>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {appVersion && (
                  <p className="text-center text-[10px] text-gray-400 pt-2 border-t border-gray-100">
                    KT HEALTH ERP v{appVersion}
                  </p>
                )}
              </div>
            </div>
          </>
        )}

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

const Dashboard = () => (
  <LayoutPreferencesProvider>
    <DashboardShell />
  </LayoutPreferencesProvider>
);

export default Dashboard;
