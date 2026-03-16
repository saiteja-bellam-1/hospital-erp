import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Toaster } from './components/ui/toaster';

import { useAuth } from './contexts/AuthContext';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import SetupWizard from './pages/SetupWizard';
import HelpDocs from './pages/HelpDocs';
import ProtectedRoute from './components/ProtectedRoute';

function App() {
  const { loading, user } = useAuth();
  const [setupComplete, setSetupComplete] = useState(null); // null = checking

  useEffect(() => {
    fetch('/api/setup/status')
      .then(res => res.json())
      .then(data => setSetupComplete(data.setup_complete))
      .catch(() => setSetupComplete(true)); // If API fails, assume setup done (dev mode)
  }, []);

  if (loading || setupComplete === null) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
      </div>
    );
  }

  // Show setup wizard if not yet configured
  if (!setupComplete) {
    return (
      <>
        <SetupWizard onComplete={() => {
          setSetupComplete(true);
          window.location.reload(); // Reload so backend picks up new DB
        }} />
        <Toaster />
      </>
    );
  }

  return (
    <>
      <Routes>
        <Route
          path="/login"
          element={user ? <Navigate to="/dashboard" replace /> : <Login />}
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
          element={<Navigate to={user ? "/dashboard" : "/login"} replace />}
        />
      </Routes>
      <Toaster />
    </>
  );
}

export default App;
