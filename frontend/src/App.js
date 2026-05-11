import React from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from './components/ui/toaster';

import { useAuth } from './contexts/AuthContext';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import HelpDocs from './pages/HelpDocs';
import ProtectedRoute from './components/ProtectedRoute';
import ForcePasswordChangeDialog from './components/ForcePasswordChangeDialog';
import MaintenanceModal from './components/MaintenanceModal';

function App() {
  const { loading, user } = useAuth();

  // Installation / initial seeding is owned entirely by the Inno Setup
  // installer (Windows) + bootstrap_from_seed.py (first launch). The browser
  // never bootstraps the DB — by the time we render, there is either an
  // admin user to log in as, or the operator needs to (re)run the installer.

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  return (
    <>
      <Routes>
        <Route
          path="/login"
          element={user ? <Navigate to="/dashboard/home" replace /> : <Login />}
        />

        <Route
          path="/dashboard/*"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />

        <Route
          path="/help/docs"
          element={
            <ProtectedRoute>
              <HelpDocs />
            </ProtectedRoute>
          }
        />

        <Route
          path="/"
          element={<Navigate to={user ? "/dashboard/home" : "/login"} replace />}
        />
      </Routes>
      {user?.must_change_password && <ForcePasswordChangeDialog />}
      <MaintenanceModal />
      <Toaster />
    </>
  );
}

export default App;
