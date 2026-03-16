import React, { useState, useEffect } from 'react';
import { Routes, Route, useLocation, Link } from 'react-router-dom';
import {
  Menu,
  Home,
  Users,
  Stethoscope,
  Pill,
  Receipt,
  FileText,
  UserPlus,
  Bed,
  Settings,
  LogOut,
  Building2,
  Calendar,
  TrendingUp,
  Shield,
  Database,
  X,
  ChevronRight,
  BookOpen,
  Package,
} from 'lucide-react';
import axios from 'axios';

import { useAuth } from '../contexts/AuthContext';
import hospitalLogo from '../assets/Final Logo KT (1).jpg';
import DashboardHome from './modules/DashboardHome';
import HospitalAdminDashboard from './modules/HospitalAdminDashboard';
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
import NurseDashboard from './modules/NurseDashboard';
import AvailabilityModule from './modules/AvailabilityModule';
import LabTechDashboard from './modules/LabTechDashboard';
import ConsultationPage from './modules/ConsultationPage';
import LicenseManagement from './modules/LicenseManagement';
import BackupManagement from './modules/BackupManagement';
import LicenseBanner from '../components/LicenseBanner';

const Dashboard = () => {
  const { user, logout, licenseStatus } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [enabledModules, setEnabledModules] = useState({});
  const location = useLocation();

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
          outpatient: true,
          inpatient: true,
          lab: true,
          pharmacy: true,
          ehr: true,
          admin: true
        });
      }
    };

    if (user) {
      fetchEnabledModules();
    }
  }, [user]);

  // Close sidebar on route change (mobile)
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

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
    return labels[user.role] || 'Staff';
  };

  // Build navigation with sections
  const getNavigationSections = () => {
    if (user.role === 'receptionist') {
      return [
        {
          label: 'Main',
          items: [
            { text: 'Reception Desk', icon: <Home className="h-[18px] w-[18px]" />, path: '/dashboard' },
            { text: 'Patients', icon: <Users className="h-[18px] w-[18px]" />, path: '/dashboard/reception/patients' },
            { text: 'Appointments', icon: <Calendar className="h-[18px] w-[18px]" />, path: '/dashboard/reception/appointments' },
            { text: 'Lab Packages', icon: <Package className="h-[18px] w-[18px]" />, path: '/dashboard/reception/packages' },
          ]
        },
        {
          label: 'Info',
          items: [
            { text: 'Doctor Schedule', icon: <Stethoscope className="h-[18px] w-[18px]" />, path: '/dashboard/reception/doctor-availability' },
            { text: 'Reports', icon: <TrendingUp className="h-[18px] w-[18px]" />, path: '/dashboard/reception/reports' },
          ]
        }
      ];
    }

    if (user.role === 'lab_technician') {
      return [{
        label: 'Main',
        items: [
          { text: 'Lab Dashboard', icon: <Home className="h-[18px] w-[18px]" />, path: '/dashboard' },
          { text: 'Laboratory', icon: <Stethoscope className="h-[18px] w-[18px]" />, path: '/dashboard/lab' },
        ]
      }];
    }

    if (user.role === 'lab_admin') {
      return [{
        label: 'Main',
        items: [
          { text: 'Lab Dashboard', icon: <Home className="h-[18px] w-[18px]" />, path: '/dashboard' },
          { text: 'Lab Configuration', icon: <Settings className="h-[18px] w-[18px]" />, path: '/dashboard/lab' },
        ]
      }];
    }

    if (user.role === 'nurse') {
      return [{
        label: 'Main',
        items: [
          { text: 'Nurse Station', icon: <Home className="h-[18px] w-[18px]" />, path: '/dashboard' },
        ]
      }];
    }

    // Admin / Doctor / Others
    const mainItems = [
      { text: 'Dashboard', icon: <Home className="h-[18px] w-[18px]" />, path: '/dashboard' },
    ];
    if (user.role !== 'doctor' && user.role !== 'hospital_admin') {
      mainItems.push({ text: 'Patients', icon: <Users className="h-[18px] w-[18px]" />, path: '/dashboard/patients' });
    }

    const moduleItems = [];
    if ((user.role === 'super_admin' || user.role === 'hospital_admin' || user.role === 'lab_admin') && enabledModules.lab) {
      moduleItems.push({ text: 'Laboratory', icon: <Stethoscope className="h-[18px] w-[18px]" />, path: '/dashboard/lab' });
    }
    if ((user.role === 'super_admin' || user.role === 'hospital_admin' || user.role === 'pharmacy_admin' || user.role === 'doctor') && enabledModules.pharmacy) {
      moduleItems.push({ text: 'Pharmacy', icon: <Pill className="h-[18px] w-[18px]" />, path: '/dashboard/pharmacy' });
    }
    if ((user.role === 'super_admin' || user.role === 'hospital_admin' || user.role === 'billing_admin') && enabledModules.billing) {
      moduleItems.push({ text: 'Billing', icon: <Receipt className="h-[18px] w-[18px]" />, path: '/dashboard/billing' });
    }
    if (user.role === 'super_admin' || user.role === 'hospital_admin' || user.role === 'doctor') {
      moduleItems.push({ text: 'EHR', icon: <FileText className="h-[18px] w-[18px]" />, path: '/dashboard/ehr' });
    }
    if (user.role === 'doctor') {
      moduleItems.push({ text: 'Availability', icon: <Calendar className="h-[18px] w-[18px]" />, path: '/dashboard/availability' });
    }
    if ((user.role === 'super_admin' || user.role === 'hospital_admin' || user.role === 'outpatient_admin') && enabledModules.outpatient) {
      moduleItems.push({ text: 'Outpatient', icon: <UserPlus className="h-[18px] w-[18px]" />, path: '/dashboard/outpatient' });
    }
    if ((user.role === 'super_admin' || user.role === 'hospital_admin' || user.role === 'inpatient_admin') && enabledModules.inpatient) {
      moduleItems.push({ text: 'Inpatient', icon: <Bed className="h-[18px] w-[18px]" />, path: '/dashboard/inpatient' });
    }

    const adminItems = [];
    if (user.role === 'super_admin' || user.role === 'hospital_admin') {
      adminItems.push({ text: 'Administration', icon: <Settings className="h-[18px] w-[18px]" />, path: '/dashboard/admin' });
      adminItems.push({ text: 'Hospital Config', icon: <Building2 className="h-[18px] w-[18px]" />, path: '/dashboard/hospital-admin' });
      adminItems.push({ text: 'License', icon: <Shield className="h-[18px] w-[18px]" />, path: '/dashboard/license' });
      adminItems.push({ text: 'Backup', icon: <Database className="h-[18px] w-[18px]" />, path: '/dashboard/backup' });
    }

    const sections = [{ label: 'Overview', items: mainItems }];
    if (moduleItems.length > 0) sections.push({ label: 'Modules', items: moduleItems });
    if (adminItems.length > 0) sections.push({ label: 'Settings', items: adminItems });
    return sections;
  };

  const navigationSections = getNavigationSections();

  const isActive = (path) => {
    if (path === '/dashboard') return location.pathname === '/dashboard';
    return location.pathname.startsWith(path);
  };

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
          {navigationSections.map((section, sIdx) => (
            <div key={section.label} className={sIdx > 0 ? 'mt-6' : ''}>
              <p
                className="px-3 mb-2 text-[11px] font-semibold tracking-wider uppercase"
                style={{ color: 'hsl(var(--sidebar-muted))' }}
              >
                {section.label}
              </p>
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
            </div>
          ))}
        </nav>

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
        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Routes>
            <Route
              path="/"
              element={
                user.role === 'doctor' ? <DoctorDashboard /> :
                user.role === 'receptionist' ? <ReceptionDashboard /> :
                user.role === 'lab_technician' ? <LabTechDashboard /> :
                user.role === 'lab_admin' ? <LabTechDashboard /> :
                user.role === 'nurse' ? <NurseDashboard /> :
                user.role === 'hospital_admin' ? <HospitalAdminDashboard /> :
                <DashboardHome />
              }
            />
            <Route path="/reception/patients" element={<ReceptionPatientsPage />} />
            <Route path="/reception/appointments" element={<ReceptionAppointmentsPage />} />
            <Route path="/reception/doctor-availability" element={<DoctorAvailabilityPage />} />
            <Route path="/reception/reports" element={<ReceptionReportsPage />} />
            <Route path="/reception/packages" element={<ReceptionPackagesPage />} />
            <Route path="/patients/*" element={<PatientsModule />} />
            <Route path="/lab/*" element={<LabModule />} />
            <Route path="/pharmacy/*" element={<PharmacyModule />} />
            <Route path="/billing/*" element={<BillingModule />} />
            <Route path="/ehr/*" element={<EHRModule />} />
            <Route path="/consultation" element={<ConsultationPage />} />
            <Route path="/availability/*" element={<AvailabilityModule />} />
            <Route path="/outpatient/*" element={user.role === 'doctor' ? <DoctorDashboard /> : <OutpatientModule />} />
            <Route path="/inpatient/*" element={<InpatientModule />} />
            <Route path="/admin/*" element={<AdminModule />} />
            <Route path="/hospital-admin/*" element={<HospitalAdminModule />} />
            <Route path="/license" element={<LicenseManagement />} />
            <Route path="/backup" element={<BackupManagement />} />
          </Routes>
        </main>

        {/* Footer — pinned to bottom of content area */}
        <footer className="flex-shrink-0 py-2 text-center text-xs text-gray-400 bg-white border-t border-gray-100">
          Powered by <span className="font-medium text-gray-500">KT HEALTH ERP</span> &mdash; Developed by KT Health Soft
        </footer>
      </div>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
    </div>
  );
};

export default Dashboard;
