import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '../../../../components/ui/button';
import { Badge } from '../../../../components/ui/badge';
import ActionKpiCard from '../../../../components/dashboard/ActionKpiCard';
import DashboardDrillDialog from '../../../../components/dashboard/DashboardDrillDialog';
import {
  TestTube, Activity, ClipboardList, CheckCircle, Upload, RefreshCw,
  Clock, Beaker, AlertTriangle, Calendar, BedDouble, Banknote, Droplets, Package,
} from 'lucide-react';
import { useAuth } from '../../../../contexts/AuthContext';
import { normalizeUserRoles, canAccessLabAdminDashboard } from '../../../../hooks/useNavigationSections';
import { useLabFeedback } from '../useLabFeedback';
import LabTestImportDialog from '../LabTestImportDialog';
import { localDateString } from '../../../../utils/localDate';

const PIPELINE = ['ordered', 'collected', 'processing'];

const queuePath = (query = {}) => {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([k, v]) => {
    if (v != null && v !== '') params.set(k, v);
  });
  const qs = params.toString();
  return qs ? `/dashboard/lab-home?${qs}` : '/dashboard/lab-home';
};

export default function DashboardTab() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isLabAdmin = canAccessLabAdminDashboard(normalizeUserRoles(user));
  const { showFeedback, FeedbackToast } = useLabFeedback();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
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

  const loadSampleTypes = useCallback(async () => {
    const r = await axios.get('/api/lab/sample-types');
    return Array.isArray(r.data) ? r.data : [];
  }, []);

  const loadPackages = useCallback(async () => {
    const r = await axios.get('/api/lab/packages', { params: { active_only: true } });
    return Array.isArray(r.data) ? r.data : [];
  }, []);

  const closeDrill = () => setDrill(null);

  const goQueue = (query) => {
    closeDrill();
    navigate(queuePath(query));
  };

  const wrapViewAll = (viewAll) => {
    if (!viewAll) return undefined;
    return {
      ...viewAll,
      onClick: () => {
        closeDrill();
        viewAll.onClick();
      },
    };
  };

  const renderOrderRows = (rows, actionLabel = 'Open queue', onOpen) => (
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
                onClick={() => (onOpen ? onOpen(o) : goQueue())}
              >
                {actionLabel}
              </Button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  const renderCatalogRows = (rows, kind) => {
    const managePath = {
      tests: '/dashboard/lab/tests',
      categories: '/dashboard/lab/categories',
      sampleTypes: '/dashboard/lab/sample-types',
      packages: '/dashboard/lab/packages',
      missingParams: null,
    }[kind];
    return (
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            <th className="py-2 pr-3 font-medium">Name</th>
            {kind === 'tests' && <th className="py-2 pr-3 font-medium">Category</th>}
            {kind === 'missingParams' && <th className="py-2 pr-3 font-medium">Code</th>}
            <th className="py-2 text-right font-medium">Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 100).map((r) => (
            <tr key={r.id} className="border-b">
              <td className="py-2 pr-3">{r.name || r.test_name || '—'}</td>
              {kind === 'tests' && <td className="py-2 pr-3 text-xs">{r.category_name || '—'}</td>}
              {kind === 'missingParams' && <td className="py-2 pr-3 font-mono text-xs">{r.test_code || '—'}</td>}
              <td className="py-2 text-right">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    closeDrill();
                    if (kind === 'missingParams') {
                      navigate(`/dashboard/lab/tests/${r.id}/parameters`);
                    } else {
                      navigate(managePath);
                    }
                  }}
                >
                  {kind === 'missingParams' ? 'Add parameters' : 'Manage'}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  };

  const n = (key) => stats?.[key] || 0;

  return (
    <div className="space-y-4">
      <FeedbackToast />

      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-base font-semibold">Today&apos;s overview</h2>
          <p className="text-sm text-muted-foreground">
            Pipeline and lab operations · {today}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => navigate('/dashboard/lab-home')}>
            Open queue
          </Button>
          {isLabAdmin && (
            <Button size="sm" variant="outline" onClick={() => setShowImport(true)}>
              <Upload className="h-4 w-4 mr-1" /> Import
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={fetchStats} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-medium mb-2">Pipeline</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <ActionKpiCard
            icon={Clock}
            label="Awaiting collection"
            value={n('ordered_count')}
            sub="Samples not yet collected"
            tone={n('ordered_count') > 0 ? 'blue' : 'slate'}
            onClick={() => setDrill({
              type: 'orders',
              title: 'Awaiting collection',
              description: 'Paid / IPD orders still at ordered status',
              loadRows: async () => {
                const rows = await loadOrders({ status: 'ordered' });
                return rows.filter((o) => o.status === 'ordered');
              },
              viewAll: { label: 'Open lab queue', onClick: () => navigate(queuePath({ status: 'ordered' })) },
            })}
          />
          <ActionKpiCard
            icon={Beaker}
            label="Collected"
            value={n('collected_count')}
            sub="Ready to process"
            tone={n('collected_count') > 0 ? 'amber' : 'slate'}
            onClick={() => setDrill({
              type: 'orders',
              title: 'Collected samples',
              loadRows: () => loadOrders({ status: 'collected' }),
              viewAll: { label: 'Open lab queue', onClick: () => navigate(queuePath({ status: 'collected' })) },
            })}
          />
          <ActionKpiCard
            icon={Activity}
            label="Processing"
            value={n('processing_count')}
            sub="Results in progress"
            tone={n('processing_count') > 0 ? 'purple' : 'slate'}
            onClick={() => setDrill({
              type: 'orders',
              title: 'Processing',
              loadRows: () => loadOrders({ status: 'processing' }),
              viewAll: { label: 'Open lab queue', onClick: () => navigate(queuePath({ status: 'processing' })) },
            })}
          />
          <ActionKpiCard
            icon={AlertTriangle}
            label="STAT / urgent"
            value={n('urgent_count')}
            sub="Priority work still open"
            tone={n('urgent_count') > 0 ? 'red' : 'slate'}
            onClick={() => setDrill({
              type: 'orders',
              title: 'STAT / urgent orders',
              description: 'Urgent or STAT orders not yet completed',
              loadRows: async () => {
                const rows = await loadOrders();
                return rows.filter(
                  (o) => PIPELINE.includes(o.status) && (o.priority === 'urgent' || o.priority === 'stat'),
                );
              },
              viewAll: { label: 'Open lab queue', onClick: () => navigate('/dashboard/lab-home') },
            })}
          />
        </div>
      </div>

      <div>
        <h3 className="text-sm font-medium mb-2">Today</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <ActionKpiCard
            icon={Calendar}
            label="Orders today"
            value={n('orders_today')}
            sub="New orders dated today"
            tone="cyan"
            onClick={() => setDrill({
              type: 'orders',
              title: 'Orders today',
              loadRows: async () => {
                const rows = await loadOrders({ date_from: today, date_to: today });
                return rows.filter((o) => o.status !== 'cancelled');
              },
              viewAll: { label: 'Open lab queue', onClick: () => navigate('/dashboard/lab-home') },
            })}
          />
          <ActionKpiCard
            icon={CheckCircle}
            label="Completed today"
            value={n('completed_today')}
            sub="Reports finished today"
            tone="green"
            onClick={() => setDrill({
              type: 'orders',
              title: 'Completed today',
              loadRows: async () => {
                const rows = await loadOrders({ status: 'completed' });
                return rows.filter((o) => (o.completion_date || '').slice(0, 10) === today);
              },
              viewAll: { label: 'Open lab queue', onClick: () => navigate(queuePath({ tab: 'completed' })) },
            })}
          />
          <ActionKpiCard
            icon={BedDouble}
            label="IPD in pipeline"
            value={n('ipd_pending_count')}
            sub="Ward orders still open"
            tone={n('ipd_pending_count') > 0 ? 'orange' : 'slate'}
            onClick={() => setDrill({
              type: 'orders',
              title: 'IPD orders in pipeline',
              description: 'Admission-linked orders not yet completed',
              loadRows: async () => {
                const rows = await loadOrders();
                return rows.filter((o) => o.admission_id && PIPELINE.includes(o.status));
              },
              viewAll: { label: 'Open lab queue', onClick: () => navigate('/dashboard/lab-home') },
            })}
          />
        </div>
      </div>

      {isLabAdmin && (
        <>
          <div>
            <h3 className="text-sm font-medium mb-2">Needs attention</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              <ActionKpiCard
                icon={Banknote}
                label="Unpaid OPD"
                value={n('unpaid_opd_count')}
                sub="Waiting for reception payment"
                tone={n('unpaid_opd_count') > 0 ? 'orange' : 'slate'}
                onClick={() => setDrill({
                  type: 'unpaid',
                  title: 'Unpaid OPD lab orders',
                  description: 'Outpatient orders the lab queue will not show until paid',
                  loadRows: async () => {
                    const rows = await loadOrders();
                    return rows.filter(
                      (o) => o.payment_status === 'pending' && !o.admission_id && o.status !== 'cancelled',
                    );
                  },
                  viewAll: {
                    label: 'Open reception lab orders',
                    onClick: () => navigate('/dashboard/reception/lab-orders'),
                  },
                })}
              />
              <ActionKpiCard
                icon={ClipboardList}
                label="Tests missing parameters"
                value={n('tests_missing_parameters')}
                sub="Cannot enter results yet"
                tone={n('tests_missing_parameters') > 0 ? 'purple' : 'slate'}
                onClick={() => setDrill({
                  type: 'missingParams',
                  title: 'Tests missing parameters',
                  description: 'Active tests with no result fields defined',
                  loadRows: async () => {
                    const rows = await loadTests();
                    return rows.filter((t) => !(t.parameters && t.parameters.length));
                  },
                  viewAll: { label: 'Manage tests', onClick: () => navigate('/dashboard/lab/tests') },
                })}
              />
            </div>
          </div>

          <div>
            <h3 className="text-sm font-medium mb-2">Catalog</h3>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <ActionKpiCard
                icon={TestTube}
                label="Active tests"
                value={n('total_tests')}
                sub="Tests in the catalog"
                tone="blue"
                onClick={() => setDrill({
                  type: 'tests',
                  title: 'Lab tests',
                  loadRows: loadTests,
                  viewAll: { label: 'Manage tests', onClick: () => navigate('/dashboard/lab/tests') },
                })}
              />
              <ActionKpiCard
                icon={ClipboardList}
                label="Categories"
                value={n('total_categories')}
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
                icon={Droplets}
                label="Sample types"
                value={n('total_sample_types')}
                sub="Blood, urine, serum, …"
                tone="cyan"
                onClick={() => setDrill({
                  type: 'sampleTypes',
                  title: 'Sample types',
                  loadRows: loadSampleTypes,
                  viewAll: { label: 'Manage sample types', onClick: () => navigate('/dashboard/lab/sample-types') },
                })}
              />
              <ActionKpiCard
                icon={Package}
                label="Packages"
                value={n('total_packages')}
                sub="Active test bundles"
                tone="green"
                onClick={() => setDrill({
                  type: 'packages',
                  title: 'Lab packages',
                  loadRows: loadPackages,
                  viewAll: { label: 'Manage packages', onClick: () => navigate('/dashboard/lab/packages') },
                })}
              />
            </div>
          </div>
        </>
      )}

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
          if (drill?.type === 'sampleTypes') return renderCatalogRows(rows, 'sampleTypes');
          if (drill?.type === 'packages') return renderCatalogRows(rows, 'packages');
          if (drill?.type === 'missingParams') return renderCatalogRows(rows, 'missingParams');
          if (drill?.type === 'unpaid') {
            return renderOrderRows(rows, 'Collect payment', () => {
              closeDrill();
              navigate('/dashboard/reception/lab-orders');
            });
          }
          return renderOrderRows(rows);
        }}
        viewAll={wrapViewAll(drill?.viewAll)}
      />
    </div>
  );
}
