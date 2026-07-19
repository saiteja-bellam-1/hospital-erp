import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '../../../../components/ui/card';
import { Button } from '../../../../components/ui/button';
import {
  TestTube, Plus, Activity, ClipboardList, CheckCircle, Loader2, Database, Upload,
} from 'lucide-react';
import { useLabFeedback } from '../useLabFeedback';
import LabTestImportDialog from '../LabTestImportDialog';

export default function DashboardTab() {
  const navigate = useNavigate();
  const { showFeedback, confirm, FeedbackToast, ConfirmDialogEl } = useLabFeedback();
  const [stats, setStats] = useState(null);
  const [seeding, setSeeding] = useState(false);
  const [showImport, setShowImport] = useState(false);

  const fetchStats = useCallback(async () => {
    try {
      const res = await axios.get('/api/lab/stats');
      setStats(res.data);
    } catch (err) {
      console.error('Failed to fetch stats:', err);
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

  return (
    <div className="space-y-6">
      <FeedbackToast />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">Total Tests</p>
                <p className="text-2xl font-bold">{stats?.total_tests || 0}</p>
              </div>
              <TestTube className="h-8 w-8 text-blue-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">Categories</p>
                <p className="text-2xl font-bold">{stats?.total_categories || 0}</p>
              </div>
              <ClipboardList className="h-8 w-8 text-purple-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">Pending Orders</p>
                <p className="text-2xl font-bold">{stats?.pending_orders || 0}</p>
              </div>
              <Activity className="h-8 w-8 text-orange-500" />
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-gray-500">Completed Today</p>
                <p className="text-2xl font-bold">{stats?.completed_today || 0}</p>
              </div>
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Quick Actions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => navigate('/dashboard/lab/tests')}>
              <Plus className="h-4 w-4 mr-2" /> New Test
            </Button>
            <Button variant="outline" onClick={() => navigate('/dashboard/lab/categories')}>
              <Plus className="h-4 w-4 mr-2" /> New Category
            </Button>
            <Button variant="outline" onClick={() => setShowImport(true)}>
              <Upload className="h-4 w-4 mr-2" /> Import Tests
            </Button>
            <Button variant="outline" onClick={handleSeedDefaults} disabled={seeding}>
              {seeding ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Database className="h-4 w-4 mr-2" />}
              Seed Default Tests
            </Button>
          </div>
        </CardContent>
      </Card>

      <LabTestImportDialog
        open={showImport}
        onOpenChange={setShowImport}
        onImported={fetchStats}
        showFeedback={showFeedback}
      />

      <ConfirmDialogEl />
    </div>
  );
}
