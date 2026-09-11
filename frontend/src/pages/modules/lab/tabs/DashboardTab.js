import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../../../../components/ui/button';
import { Badge } from '../../../../components/ui/badge';
import ActionKpiCard from '../../../../components/dashboard/ActionKpiCard';
import DashboardDrillDialog from '../../../../components/dashboard/DashboardDrillDialog';
import {
  TestTube, Activity, ClipboardList, CheckCircle, Loader2, Database, Upload, RefreshCw,
} from 'lucide-react';
import { useLabFeedback } from '../useLabFeedback';
import LabTestImportDialog from '../LabTestImportDialog';
import { localDateString } from '../../../../utils/localDate';

export default function DashboardTab() {
  const navigate = useNavigate();
  const { showFeedback, confirm, FeedbackToast, ConfirmDialogEl } = useLabFeedback();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [drill, setDrill] = useState(null);
  const today = localDateString();

  const fetchStats = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/lab/stats');
      setStats(res.data);
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchStats(); }, [fetchStats]);

  const handleSeedDefaults = () => {
    confirm(
      'This will seed default lab tests (CBC, LFT, RFT, etc.) with standard parameters and reference ranges. Existing tests will not be duplicated. Continue?',
      async () => {
        setSeeding(true);
        try {
          const res = await axios.post('/api/lab/seed-defaults');
          showFeedback(res.data.message || 'Default tests seeded successfully');
          fetchStats();
        } catch (err) {
          showFeedback(err.response?.data?.detail || 'Failed to seed defaults', 'error');
        } finally {
          setSeeding(false);
        }
      },
      'Seed Default Tests'
    );
  };

  const loadOrders = useCallback(async (params = {}) => {
    const r = await axios.get('/api/lab/orders', { params });
    return Array.isArray(r.data) ? r.data : [];
  }, []);

  const loadTests = useCallback(async () => {
    const r = await axios.get('/api/lab/tests');
    return Array.isArray(r.data) ? r.data : [];
  }, []);

  const loadCategories = useCallback(async () => {
    const r = await axios.get('/api/lab/categories');
    return Array.isArray(r.data) ? r.data : [];
  }, []);

  const closeDrill = () => setDrill(null);

  const renderOrderRows = (rows) => (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left text-muted-foreground">
          <th className="py-2 pr-3 font-medium">Order</th>
          <th className="py-2 pr-3 font-medium">Patient</th>
          <th className="py-2 pr-3 font-medium">Test</th>
          <th className="py-2 pr-3 font-medium">Status</th>
          <th className="py-2 text-right font-medium">Action</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((o) => (
          <tr key={o.id} className="border-b">
            <td className="py-2 pr-3 font-mono text-xs">{o.order_number || o.id}</td>
            <td className="py-2 pr-3">{o.patient_name || '—'}</td>
            <td className="py-2 pr-3">{o.test_name || '—'}</td>
            <td className="py-2 pr-3"><Badge variant="outline">{o.status}</Badge></td>
            <td className="py-2 text-right">
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  closeDrill();
                  navigate('/dashboard/lab-home');
                }}
              >
                Open queue
              </Button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  const renderCatalogRows = (rows, kind) => (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b text-left text-muted-foreground">
          <th className="py-2 pr-3 font-medium">Name</th>
          {kind === 'tests' && <th className="py-2 pr-3 font-medium">Category</th>}
          <th className="py-2 text-right font-medium">Action</th>
        </tr>
      </thead>
      <tbody>
        {rows.slice(0, 100).map((r) => (
          <tr key={r.id} className="border-b">
            <td className="py-2 pr-3">{r.name || r.test_name || '—'}</td>
            {kind === 'tests' && <td className="py-2 pr-3 text-xs">{r.category_name || '—'}</td>}
            <td className="py-2 text-right">
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  closeDrill();
                  navigate(kind === 'tests' ? '/dashboard/lab/tests' : '/dashboard/lab/categories');
                }}
              >
                Manage
              </Button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <div className="space-y-4">
      <FeedbackToast />

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-base font-semibold">Today&apos;s overview</h2>
          <p className="text-sm text-muted-foreground">
            Catalog and order pipeline · {today}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => setShowImport(true)}>
            <Upload className="h-4 w-4 mr-1" /> Import
          </Button>
          <Button size="sm" variant="outline" onClick={handleSeedDefaults} disabled={seeding}>
            {seeding ? <Loader2 className="h-4 w-4 mr-1 animate-spin" /> : <Database className="h-4 w-4 mr-1" />}
            Seed defaults
          </Button>
          <Button size="sm" variant="outline" onClick={fetchStats} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <ActionKpiCard
          icon={TestTube}
          label="Total Tests"
          value={stats?.total_tests || 0}
          sub="Active catalog tests"
          tone="blue"
          onClick={() => setDrill({
            type: 'tests',
            title: 'Lab tests',
            description: 'Tests in the active catalog',
            loadRows: loadTests,
            viewAll: { label: 'Manage tests', onClick: () => navigate('/dashboard/lab/tests') },
          })}
        />
        <ActionKpiCard
          icon={ClipboardList}
          label="Categories"
          value={stats?.total_categories || 0}
          sub="Test categories"
          tone="purple"
          onClick={() => setDrill({
            type: 'categories',
            title: 'Lab categories',
            loadRows: loadCategories,
            viewAll: { label: 'Manage categories', onClick: () => navigate('/dashboard/lab/categories') },
          })}
        />
        <ActionKpiCard
          icon={Activity}
          label="Pending Orders"
          value={stats?.pending_orders || 0}
          sub="Ordered / collected / processing"
          tone={(stats?.pending_orders || 0) > 0 ? 'orange' : 'slate'}
          onClick={() => setDrill({
            type: 'pending',
            title: 'Pending lab orders',
            description: 'Orders not yet completed',
            loadRows: async () => {
              const rows = await loadOrders();
              return rows.filter((o) => ['ordered', 'collected', 'processing'].includes(o.status));
            },
            viewAll: { label: 'Open lab queue', onClick: () => navigate('/dashboard/lab-home') },
          })}
        />
        <ActionKpiCard
          icon={CheckCircle}
          label="Completed Today"
          value={stats?.completed_today || 0}
          sub="Reports finished today"
          tone="green"
          onClick={() => setDrill({
            type: 'completed',
            title: 'Completed today',
            loadRows: () => loadOrders({ status: 'completed', date_from: today, date_to: today }),
            viewAll: { label: 'Open lab queue', onClick: () => navigate('/dashboard/lab-home') },
          })}
        />
      </div>

      <LabTestImportDialog
        open={showImport}
        onOpenChange={setShowImport}
        onImported={fetchStats}
        showFeedback={showFeedback}
      />

      <DashboardDrillDialog
        open={!!drill}
        onOpenChange={(open) => { if (!open) closeDrill(); }}
        title={drill?.title || ''}
        description={drill?.description}
        loadRows={drill?.loadRows || (async () => [])}
        renderRows={(rows) => {
          if (drill?.type === 'tests') return renderCatalogRows(rows, 'tests');
          if (drill?.type === 'categories') return renderCatalogRows(rows, 'categories');
          return renderOrderRows(rows);
        }}
        viewAll={drill?.viewAll}
      />

      <ConfirmDialogEl />
    </div>
  );
}
