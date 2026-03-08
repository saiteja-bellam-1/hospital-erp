import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Button } from '../components/ui/button';
import { Avatar, AvatarFallback } from '../components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
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
  User,
  Building2,
  Calendar,
  TrendingUp,
  Shield,
} from 'lucide-react';
import axios from 'axios';

import { useAuth } from '../contexts/AuthContext';
import hospitalLogo from '../assets/Final Logo KT (1).jpg';
import DashboardHome from './modules/DashboardHome';
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
import NurseDashboard from './modules/NurseDashboard';
import AvailabilityModule from './modules/AvailabilityModule';
import LabTechDashboard from './modules/LabTechDashboard';
import ConsultationPage from './modules/ConsultationPage';
import LicenseManagement from './modules/LicenseManagement';
import LicenseBanner from '../components/LicenseBanner';

const Dashboard = () => {
  const { user, logout, licenseStatus } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [enabledModules, setEnabledModules] = useState({});

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
        // Set default values if API fails
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

  // Define navigation items based on user role and enabled modules
  const getNavigationItems = () => {
    // Separate navigation for receptionist with dedicated pages
    if (user.role === 'receptionist') {
      return [
        { text: 'Reception Desk', icon: <Home className="h-4 w-4" />, path: '/dashboard' },
        { text: 'Patients', icon: <Users className="h-4 w-4" />, path: '/dashboard/reception/patients' },
        { text: 'Appointments', icon: <Calendar className="h-4 w-4" />, path: '/dashboard/reception/appointments' },
        { text: 'Doctor Schedule', icon: <Stethoscope className="h-4 w-4" />, path: '/dashboard/reception/doctor-availability' },
        { text: 'Reports', icon: <TrendingUp className="h-4 w-4" />, path: '/dashboard/reception/reports' }
      ];
    }

    // Lab technician navigation
    if (user.role === 'lab_technician') {
      return [
        { text: 'Lab Dashboard', icon: <Home className="h-4 w-4" />, path: '/dashboard' },
        { text: 'Laboratory', icon: <Stethoscope className="h-4 w-4" />, path: '/dashboard/lab' }
      ];
    }

    // Simplified navigation for nurse
    if (user.role === 'nurse') {
      return [
        { text: 'Nurse Station', icon: <Home className="h-4 w-4" />, path: '/dashboard' }
      ];
    }

    const baseItems = [
      { text: 'Dashboard', icon: <Home className="h-4 w-4" />, path: '/dashboard' },
    ];

    // Patients nav - not for doctors (they use EHR instead)
    if (user.role !== 'doctor') {
      baseItems.push({ text: 'Patients', icon: <Users className="h-4 w-4" />, path: '/dashboard/patients' });
    }

    const moduleItems = [];

    // Add modules based on user role AND module enablement
    if ((user.role === 'super_admin' || user.role === 'hospital_admin' || user.role === 'lab_admin')
        && enabledModules.lab) {
      moduleItems.push({ text: 'Laboratory', icon: <Stethoscope className="h-4 w-4" />, path: '/dashboard/lab' });
    }

    if ((user.role === 'super_admin' || user.role === 'hospital_admin' || user.role === 'pharmacy_admin' || user.role === 'doctor') 
        && enabledModules.pharmacy) {
      moduleItems.push({ text: 'Pharmacy', icon: <Pill className="h-4 w-4" />, path: '/dashboard/pharmacy' });
    }

    if ((user.role === 'super_admin' || user.role === 'hospital_admin' || user.role === 'billing_admin') 
        && enabledModules.billing) {
      moduleItems.push({ text: 'Billing', icon: <Receipt className="h-4 w-4" />, path: '/dashboard/billing' });
    }

    // EHR is always enabled
    if (user.role === 'super_admin' || user.role === 'hospital_admin' || user.role === 'doctor') {
      moduleItems.push({ text: 'EHR', icon: <FileText className="h-4 w-4" />, path: '/dashboard/ehr' });
    }

    // Availability management for doctors
    if (user.role === 'doctor') {
      moduleItems.push({ text: 'Availability', icon: <Calendar className="h-4 w-4" />, path: '/dashboard/availability' });
    }

    if ((user.role === 'super_admin' || user.role === 'hospital_admin' || user.role === 'outpatient_admin')
        && enabledModules.outpatient) {
      moduleItems.push({ text: 'Outpatient', icon: <UserPlus className="h-4 w-4" />, path: '/dashboard/outpatient' });
    }

    if ((user.role === 'super_admin' || user.role === 'hospital_admin' || user.role === 'inpatient_admin') 
        && enabledModules.inpatient) {
      moduleItems.push({ text: 'Inpatient', icon: <Bed className="h-4 w-4" />, path: '/dashboard/inpatient' });
    }

    // Admin is always enabled
    const adminItems = [];
    if (user.role === 'super_admin' || user.role === 'hospital_admin') {
      adminItems.push({ text: 'Administration', icon: <Settings className="h-4 w-4" />, path: '/dashboard/admin' });
    }
    if (user.role === 'super_admin' || user.role === 'hospital_admin') {
      adminItems.push({ text: 'Hospital Config', icon: <Building2 className="h-4 w-4" />, path: '/dashboard/hospital-admin' });
    }
    if (user.role === 'super_admin' || user.role === 'hospital_admin') {
      adminItems.push({ text: 'License', icon: <Shield className="h-4 w-4" />, path: '/dashboard/license' });
    }

    return [...baseItems, ...moduleItems, ...adminItems];
  };

  const navigationItems = getNavigationItems();

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Sidebar */}
      <div className={`${
        sidebarOpen ? 'translate-x-0' : '-translate-x-full'
      } fixed inset-y-0 left-0 z-50 w-64 bg-white shadow-lg transform transition-transform duration-300 ease-in-out lg:translate-x-0 lg:static lg:inset-0`}>
        <div className="flex items-center justify-between h-16 px-6 bg-white border-b">
          <div className="flex items-center">
            <img 
              src={hospitalLogo} 
              alt="KT Health Soft - Hospital Management System" 
              className="h-10 w-auto max-w-[200px]"
            />
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden text-gray-600"
            onClick={() => setSidebarOpen(false)}
          >
            ×
          </Button>
        </div>
        <nav className="mt-8">
          {navigationItems.map((item) => (
            <a
              key={item.text}
              href={item.path}
              className="flex items-center px-6 py-3 text-gray-600 hover:bg-gray-100 hover:text-gray-900"
            >
              {item.icon}
              <span className="ml-3">{item.text}</span>
            </a>
          ))}
        </nav>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col lg:ml-0">
        {/* License Banner */}
        <LicenseBanner licenseStatus={licenseStatus} />
        {/* Top bar */}
        <header className="flex items-center justify-between h-16 px-6 bg-white border-b">
          <div className="flex items-center">
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden"
              onClick={() => setSidebarOpen(true)}
            >
              <Menu className="h-6 w-6" />
            </Button>
            <h2 className="ml-4 text-xl font-semibold text-gray-800">
              {user.role === 'super_admin' ? 'Super Admin' : 
               user.role === 'hospital_admin' ? 'Hospital Admin' :
               user.role === 'doctor' ? 'Doctor Portal' :
               user.role === 'receptionist' ? 'Reception Desk' :
               user.role === 'lab_technician' ? 'Lab Technician' :
               user.role === 'nurse' ? 'Nurse Station' :
               'User Portal'}
            </h2>
          </div>
          
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="relative h-8 w-8 rounded-full">
                <Avatar className="h-8 w-8">
                  <AvatarFallback>
                    <User className="h-4 w-4" />
                  </AvatarFallback>
                </Avatar>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent className="w-56" align="end" forceMount>
              <DropdownMenuLabel className="font-normal">
                <div className="flex flex-col space-y-1">
                  <p className="text-sm font-medium leading-none">{user.full_name}</p>
                  <p className="text-xs leading-none text-muted-foreground">
                    {user.email}
                  </p>
                </div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem>
                <User className="mr-2 h-4 w-4" />
                <span>Profile</span>
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={logout}>
                <LogOut className="mr-2 h-4 w-4" />
                <span>Log out</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">
          <Routes>
            <Route 
              path="/" 
              element={
                user.role === 'doctor' ? <DoctorDashboard /> :
                user.role === 'receptionist' ? <ReceptionDashboard /> :
                user.role === 'lab_technician' ? <LabTechDashboard /> :
                user.role === 'nurse' ? <NurseDashboard /> :
                <DashboardHome />
              } 
            />
            <Route path="/reception/patients" element={<ReceptionPatientsPage />} />
            <Route path="/reception/appointments" element={<ReceptionAppointmentsPage />} />
            <Route path="/reception/doctor-availability" element={<DoctorAvailabilityPage />} />
            <Route path="/reception/reports" element={<ReceptionReportsPage />} />
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
          </Routes>
        </main>
      </div>

      {/* Overlay for mobile */}
      {sidebarOpen && (
        <div 
          className="fixed inset-0 bg-black bg-opacity-50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}
    </div>
  );
};

export default Dashboard;