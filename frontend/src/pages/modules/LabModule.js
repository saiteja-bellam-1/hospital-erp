import React from 'react';
import { Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { normalizeUserRoles, canAccessLabAdminDashboard } from '../../hooks/useNavigationSections';
import { TestTube } from 'lucide-react';
import LabTestParametersPage from './LabTestParametersPage';
import DashboardTab from './lab/tabs/DashboardTab';
import TestsTab from './lab/tabs/TestsTab';
import CategoriesTab from './lab/tabs/CategoriesTab';
import SampleTypesTab from './lab/tabs/SampleTypesTab';
import PackagesTab from './lab/tabs/PackagesTab';

export const LAB_PAGE_META = {
  '': { title: 'Dashboard', blurb: 'Lab catalog overview and quick actions' },
  'tests': { title: 'Test Catalog', blurb: 'Manage individual lab tests and pricing' },
  'categories': { title: 'Categories', blurb: 'Test category master' },
  'sample-types': { title: 'Sample Types', blurb: 'Blood, urine, serum, and other sample types' },
  'packages': { title: 'Packages', blurb: 'Bundle tests into discounted packages' },
};

function labPathKey(pathname) {
  const prefix = '/dashboard/lab';
  if (!pathname.startsWith(prefix)) return '';
  const rest = pathname.slice(prefix.length).replace(/^\//, '');
  if (rest.startsWith('tests/') && rest.includes('/parameters')) return 'tests';
  return rest.split('/')[0] || '';
}

function LabPageShell() {
  const { pathname } = useLocation();
  const key = labPathKey(pathname);
  const meta = LAB_PAGE_META[key] || { title: 'Laboratory', blurb: '' };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-2">
          <TestTube className="h-7 w-7" /> Laboratory · {meta.title}
        </h1>
        {meta.blurb && <p className="text-gray-600 mt-1">{meta.blurb}</p>}
      </div>
      <Outlet />
    </div>
  );
}

const LabAdminRouteGuard = ({ children }) => {
  const { user } = useAuth();
  if (!canAccessLabAdminDashboard(normalizeUserRoles(user))) {
    return <Navigate to="/dashboard/lab-home" replace />;
  }
  return children;
};

const LabModule = () => (
  <LabAdminRouteGuard>
    <Routes>
      <Route path="tests/:testId/parameters" element={<LabTestParametersPage />} />

      <Route element={<LabPageShell />}>
        <Route index element={<DashboardTab />} />
        <Route path="tests" element={<TestsTab />} />
        <Route path="categories" element={<CategoriesTab />} />
        <Route path="sample-types" element={<SampleTypesTab />} />
        <Route path="packages" element={<PackagesTab />} />
      </Route>

      <Route path="*" element={<Navigate to="/dashboard/lab" replace />} />
    </Routes>
  </LabAdminRouteGuard>
);

export default LabModule;
